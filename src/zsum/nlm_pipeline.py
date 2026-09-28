"""NotebookLM runtime orchestration for paper cards and collection digests."""

from __future__ import annotations

import json
import logging
import math
import re
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TypeVar

from .cards import _build_user_prompt, _card_schema_for_stage, _parse_card_response
from .config import Config
from .digests import _bottom_up_order
from .extractor import ExtractionResult
from .llm import complete_with_retry
from .models import Collection, Item, LibraryIndex, PaperCard, TextQuality
from .prompts import load_prompt

logger = logging.getLogger(__name__)

NLMSourceKind = Literal["paper", "child_digest", "partial_digest"]
NLMNotebookPurpose = Literal["collection", "aggregate"]
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_FATAL_STATUS_CODES = frozenset({400, 401, 403, 404, 422})


class NotebookLMError(RuntimeError):
    """Raised when an `nlm` CLI operation fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        command: Sequence[str] | None = None,
    ):
        self.status_code = status_code
        self.command = tuple(command) if command is not None else None
        super().__init__(message)


class NotebookLMAuthError(NotebookLMError):
    """Raised when the `nlm` CLI reports an authentication or authorization failure."""


class NotebookLMRetryExhausted(NotebookLMError):
    """Raised when a retryable NotebookLM CLI operation keeps failing."""

    def __init__(self, last_error: NotebookLMError, attempts: int):
        self.last_error = last_error
        self.attempts = attempts
        super().__init__(
            f"NotebookLM CLI failed after {attempts} attempts: {last_error}",
            status_code=last_error.status_code,
            command=last_error.command,
        )


@dataclass(slots=True)
class NLMSourceMapping:
    """Metadata for one uploaded NotebookLM source."""

    source_id: str
    title: str
    kind: NLMSourceKind
    citekey: str | None = None
    collection_key: str | None = None


@dataclass(slots=True)
class NLMNotebookMapping:
    """NotebookLM notebook created for one collection batch or aggregate step."""

    collection_key: str
    notebook_id: str
    title: str
    purpose: NLMNotebookPurpose
    part_index: int
    total_parts: int
    sources: list[NLMSourceMapping] = field(default_factory=list)


@dataclass(slots=True)
class NLMBatchResult:
    """Outcome summary for a NotebookLM pipeline run."""

    cards: dict[str, PaperCard] = field(default_factory=dict)
    digests: dict[str, str] = field(default_factory=dict)
    failed_papers: list[str] = field(default_factory=list)
    notebooks_created: list[str] = field(default_factory=list)
    mappings: dict[str, list[NLMNotebookMapping]] = field(default_factory=dict)


@dataclass(slots=True)
class _NotebookSourceInput:
    """Internal representation of a source to upload into a notebook."""

    title: str
    kind: NLMSourceKind
    file_path: Path | None = None
    text: str | None = None
    citekey: str | None = None
    collection_key: str | None = None


def compute_direct_members(collection: Collection, index: LibraryIndex) -> list[str]:
    """Return citekeys in *collection* that are not also present in descendants."""
    descendant_items: set[str] = set()
    stack = list(collection.child_keys)
    seen: set[str] = set()

    while stack:
        child_key = stack.pop()
        if child_key in seen:
            continue
        seen.add(child_key)
        child = index.collections.get(child_key)
        if child is None:
            continue
        descendant_items.update(child.item_citekeys)
        stack.extend(child.child_keys)

    return [citekey for citekey in collection.item_citekeys if citekey not in descendant_items]


def create_collection_notebooks(
    collection: Collection,
    index: LibraryIndex,
    config: Config,
    *,
    child_digests: dict[str, str] | None = None,
) -> list[NLMNotebookMapping]:
    """Create one or more NotebookLM notebooks for a collection's direct sources."""
    sources = _build_collection_sources(collection, index, child_digests or {})
    return _create_notebooks_for_sources(
        collection.key,
        collection.name,
        sources,
        config,
        purpose="collection",
    )


def query_paper_card(notebook_id: str, source_id: str, item: Item, config: Config) -> PaperCard:
    """Query NotebookLM for one paper card and parse it into a `PaperCard`."""
    prompt = _build_nlm_paper_query(item, source_id)
    response_text = _nlm_query(notebook_id, prompt, config)
    if config.notebooklm.parse_locally:
        response_text = _convert_nlm_card_response(item, response_text, config)
    card, normalized_fields = _parse_card_response(
        response_text,
        item,
        TextQuality.GOOD,
        "notebooklm",
    )
    if normalized_fields:
        logger.warning(
            "NotebookLM card response for %s normalized fields: %s",
            item.citekey,
            ", ".join(normalized_fields),
        )
    return card


def query_collection_digest(
    notebooks: Sequence[NLMNotebookMapping],
    collection: Collection,
    config: Config,
) -> str:
    """Query NotebookLM for a collection digest from one or more notebook batches."""
    digest, _ = _query_collection_digest_with_aggregates(notebooks, collection, config)
    return digest


def run_nlm_pipeline(index: LibraryIndex, config: Config, cache_dir: Path) -> NLMBatchResult:
    """Run the NotebookLM orchestration stage.

    *cache_dir* is consumed by the CLI layer (cli.py) which handles persistence
    after this function returns. Kept in the signature for caller convenience.
    """
    result = NLMBatchResult()
    child_digests: dict[str, str] = {}

    try:
        for collection_key in _bottom_up_order(index):
            collection = index.collections[collection_key]
            direct_members = compute_direct_members(collection, index)
            notebooks = create_collection_notebooks(
                collection,
                index,
                config,
                child_digests=child_digests,
            )
            result.mappings[collection_key] = list(notebooks)
            result.notebooks_created.extend(notebook.notebook_id for notebook in notebooks)

            uploaded_citekeys = {
                source.citekey
                for notebook in notebooks
                for source in notebook.sources
                if source.kind == "paper" and source.citekey is not None
            }
            for citekey in direct_members:
                if citekey not in uploaded_citekeys:
                    _append_unique(result.failed_papers, citekey)

            for notebook in notebooks:
                for source in notebook.sources:
                    if source.kind != "paper" or source.citekey is None:
                        continue
                    if source.citekey in result.cards:
                        continue
                    item = index.items.get(source.citekey)
                    if item is None:
                        continue
                    try:
                        result.cards[source.citekey] = query_paper_card(
                            notebook.notebook_id,
                            source.source_id,
                            item,
                            config,
                        )
                    except Exception as exc:
                        logger.error(
                            "Failed NotebookLM card generation for %s in %s: %s",
                            source.citekey,
                            collection.name,
                            exc,
                        )
                        _append_unique(result.failed_papers, source.citekey)

            if not notebooks:
                continue

            try:
                digest, aggregate_notebooks = _query_collection_digest_with_aggregates(
                    notebooks,
                    collection,
                    config,
                )
            except Exception as exc:
                logger.error(
                    "Failed NotebookLM digest generation for '%s': %s", collection.name, exc
                )
                continue

            if aggregate_notebooks:
                result.mappings[collection_key].extend(aggregate_notebooks)
                result.notebooks_created.extend(
                    notebook.notebook_id for notebook in aggregate_notebooks
                )
            result.digests[collection_key] = digest
            child_digests[collection_key] = digest
    finally:
        if config.notebooklm.cleanup:
            cleanup_notebooks(result.notebooks_created, config)

    return result


def cleanup_notebooks(notebook_ids: Sequence[str], config: Config) -> None:
    """Best-effort cleanup of created NotebookLM notebooks."""
    seen: set[str] = set()
    for notebook_id in notebook_ids:
        if notebook_id in seen:
            continue
        seen.add(notebook_id)
        try:
            _nlm_delete_notebook(notebook_id, config)
        except Exception as exc:
            logger.warning("Failed to delete NotebookLM notebook %s: %s", notebook_id, exc)


def _build_collection_sources(
    collection: Collection,
    index: LibraryIndex,
    child_digests: dict[str, str],
) -> list[_NotebookSourceInput]:
    sources: list[_NotebookSourceInput] = []

    for citekey in compute_direct_members(collection, index):
        item = index.items.get(citekey)
        if item is None or item.pdf_path is None or not item.pdf_path.exists():
            logger.warning(
                "Skipping NotebookLM upload for %s in '%s': missing PDF",
                citekey,
                collection.name,
            )
            continue
        sources.append(
            _NotebookSourceInput(
                title=f"{citekey}: {item.title}",
                kind="paper",
                file_path=item.pdf_path,
                citekey=citekey,
            )
        )

    for child_key in collection.child_keys:
        digest_text = child_digests.get(child_key, "").strip()
        if not digest_text:
            continue
        child = index.collections.get(child_key)
        child_name = child.name if child is not None else child_key
        sources.append(
            _NotebookSourceInput(
                title=f"{child_name} digest",
                kind="child_digest",
                text=digest_text,
                collection_key=child_key,
            )
        )

    return sources


def _create_notebooks_for_sources(
    collection_key: str,
    notebook_label: str,
    sources: Sequence[_NotebookSourceInput],
    config: Config,
    *,
    purpose: NLMNotebookPurpose,
) -> list[NLMNotebookMapping]:
    if not sources:
        return []

    chunks = list(_chunked(list(sources), _notebook_batch_size(config)))
    total_parts = len(chunks)
    notebooks: list[NLMNotebookMapping] = []

    for part_index, chunk in enumerate(chunks, start=1):
        notebook_title = notebook_label
        if total_parts > 1:
            notebook_title = f"{notebook_label} ({part_index}/{total_parts})"
        notebook_id = _nlm_create_notebook(notebook_title, config)
        mapping = NLMNotebookMapping(
            collection_key=collection_key,
            notebook_id=notebook_id,
            title=notebook_title,
            purpose=purpose,
            part_index=part_index,
            total_parts=total_parts,
        )
        for source in chunk:
            source_id = _nlm_add_source(
                notebook_id,
                config,
                file_path=source.file_path,
                text=source.text,
                title=source.title,
            )
            mapping.sources.append(
                NLMSourceMapping(
                    source_id=source_id,
                    title=source.title,
                    kind=source.kind,
                    citekey=source.citekey,
                    collection_key=source.collection_key,
                )
            )
        notebooks.append(mapping)

    return notebooks


def _query_collection_digest_with_aggregates(
    notebooks: Sequence[NLMNotebookMapping],
    collection: Collection,
    config: Config,
) -> tuple[str, list[NLMNotebookMapping]]:
    if not notebooks:
        return "", []

    if len(notebooks) == 1:
        digest = _nlm_query(
            notebooks[0].notebook_id,
            _build_nlm_digest_query(collection, notebooks[0]),
            config,
        ).strip()
        return digest, []

    partial_digests: list[tuple[str, str]] = []
    for notebook in notebooks:
        partial_text = _nlm_query(
            notebook.notebook_id,
            _build_nlm_digest_query(collection, notebook),
            config,
        ).strip()
        partial_digests.append(
            (f"{collection.name} partial digest {notebook.part_index}", partial_text)
        )

    aggregate_sources = _build_partial_digest_sources(collection, partial_digests, config)
    if not aggregate_sources:
        combined = "\n\n".join(text for _, text in partial_digests if text.strip())
        return combined, []
    aggregate_notebooks = _create_notebooks_for_sources(
        collection.key,
        f"{collection.name} digest aggregate",
        aggregate_sources,
        config,
        purpose="aggregate",
    )
    final_digest = _nlm_query(
        aggregate_notebooks[0].notebook_id,
        _build_nlm_digest_query(collection, aggregate_notebooks[0]),
        config,
    ).strip()
    return final_digest, aggregate_notebooks


def _build_partial_digest_sources(
    collection: Collection,
    partial_digests: Sequence[tuple[str, str]],
    config: Config,
) -> list[_NotebookSourceInput]:
    if not partial_digests:
        return []

    max_sources = _notebook_batch_size(config)
    group_size = max(1, math.ceil(len(partial_digests) / max_sources))
    sources: list[_NotebookSourceInput] = []

    for index, chunk in enumerate(_chunked(list(partial_digests), group_size), start=1):
        combined_chunks = [f"## {title}\n\n{text.strip()}" for title, text in chunk if text.strip()]
        if not combined_chunks:
            continue
        sources.append(
            _NotebookSourceInput(
                title=f"{collection.name} aggregate digest source {index}",
                kind="partial_digest",
                text="\n\n---\n\n".join(combined_chunks),
            )
        )

    return sources


def _build_nlm_paper_query(item: Item, source_id: str) -> str:
    template = load_prompt("nlm_paper_card_query.txt")
    return template.format(
        source_id=source_id,
        citekey=item.citekey,
        title=item.title,
        authors=", ".join(item.authors) or "unknown",
        year=item.year or "unknown",
        venue=item.venue or "unknown",
        doi=item.doi or "unknown",
    )


def _build_nlm_digest_query(collection: Collection, notebook: NLMNotebookMapping) -> str:
    template = load_prompt("nlm_collection_digest_query.txt")
    source_titles = "\n".join(f"- {source.title}" for source in notebook.sources) or "- none"
    return template.format(
        collection_name=collection.name,
        collection_path=collection.path or collection.name,
        notebook_purpose=notebook.purpose,
        part_index=notebook.part_index,
        total_parts=notebook.total_parts,
        source_count=len(notebook.sources),
        source_titles=source_titles,
    )


def _convert_nlm_card_response(item: Item, nlm_response: str, config: Config) -> str:
    extraction = ExtractionResult(
        citekey=item.citekey,
        text=nlm_response,
        page_count=0,
        pages_used=[],
        quality=TextQuality.GOOD,
        warnings=["Converted from NotebookLM response"],
        extraction_method="notebooklm",
    )
    system_prompt = load_prompt("paper_card.txt")
    user_prompt = "\n\n".join(
        [
            _build_user_prompt(item, extraction),
            (
                "The text above is NotebookLM's grounded answer. Convert it into the "
                "exact JSON schema requested by the system prompt and do not add "
                "information."
            ),
        ]
    )
    llm_config = config.llm.config_for_stage("cards")
    response = complete_with_retry(
        system_prompt,
        user_prompt,
        config,
        stage="cards",
        max_tokens=llm_config.max_tokens_card,
        output_schema=_card_schema_for_stage(config),
    )
    return response.text


def _profile_args(config: Config) -> list[str]:
    if not config.notebooklm.profile:
        return []
    return ["--profile", config.notebooklm.profile]


def _nlm_create_notebook(title: str, config: Config) -> str:
    payload = _run_nlm_cli(
        ["notebook", "create", title, *_profile_args(config)],
        config,
        timeout=config.notebooklm.query_timeout,
    )
    return _extract_string_field(payload, ("notebook_id", "id"), "notebook id")


def _nlm_add_source(
    notebook_id: str,
    config: Config,
    *,
    file_path: Path | None = None,
    text: str | None = None,
    title: str,
) -> str:
    if (file_path is None) == (text is None):
        raise ValueError("Provide exactly one of file_path or text when adding a NotebookLM source")

    if file_path is not None:
        payload = _run_nlm_cli(
            [
                "source",
                "add",
                notebook_id,
                "--file",
                str(file_path),
                "--title",
                title,
                "--wait",
                "--wait-timeout",
                str(config.notebooklm.upload_timeout),
                *_profile_args(config),
            ],
            config,
            timeout=config.notebooklm.upload_timeout,
        )
    else:
        payload = _run_nlm_cli(
            [
                "source",
                "add",
                notebook_id,
                "--text",
                text or "",
                "--title",
                title,
                *_profile_args(config),
            ],
            config,
            timeout=config.notebooklm.upload_timeout,
        )
    return _extract_string_field(payload, ("source_id", "id"), "source id")


def _nlm_query(notebook_id: str, prompt: str, config: Config) -> str:
    payload = _run_nlm_cli(
        [
            "notebook",
            "query",
            notebook_id,
            prompt,
            "--json",
            "--timeout",
            str(config.notebooklm.query_timeout),
            *_profile_args(config),
        ],
        config,
        timeout=config.notebooklm.query_timeout,
    )
    return _extract_string_field(
        payload,
        ("response", "result", "answer", "text", "content"),
        "query response",
    )


def _nlm_delete_notebook(notebook_id: str, config: Config) -> None:
    _run_nlm_cli(
        ["notebook", "delete", notebook_id, "--confirm", *_profile_args(config)],
        config,
        timeout=config.notebooklm.query_timeout,
    )


def _run_nlm_cli(
    args: Sequence[str],
    config: Config,
    *,
    timeout: float,
    input_text: str | None = None,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> dict | str:
    if max_retries < 1:
        raise ValueError("max_retries must be >= 1")

    command = ["nlm", *args]
    last_error: NotebookLMError | None = None

    attempt = 0
    while attempt < max_retries:
        try:
            result = subprocess.run(
                command,
                input=input_text,
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise NotebookLMError(
                "NotebookLM CLI binary not found: 'nlm'. Install it and ensure it is on PATH.",
                status_code=404,
                command=command,
            ) from exc
        except subprocess.TimeoutExpired:
            last_error = NotebookLMError(
                f"NotebookLM CLI timed out after {timeout:.1f}s",
                status_code=504,
                command=command,
            )
        else:
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            combined_output = "\n".join(part for part in (stdout, stderr) if part)
            if result.returncode == 0:
                return _decode_nlm_payload(stdout)

            status_code = _extract_status_code(combined_output)
            message = combined_output.splitlines()[-1] if combined_output else "unknown error"
            error_class = (
                NotebookLMAuthError if _looks_like_auth_error(combined_output) else NotebookLMError
            )
            error = error_class(
                f"NotebookLM CLI failed with exit code {result.returncode}: {message}",
                status_code=status_code,
                command=command,
            )
            if isinstance(error, NotebookLMAuthError) or not _is_retryable_status(status_code):
                raise error
            last_error = error

        attempt += 1
        if attempt < max_retries and last_error is not None:
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "NotebookLM CLI call failed (attempt %d/%d): %s. Retrying in %.1fs",
                attempt,
                max_retries,
                last_error,
                delay,
            )
            time.sleep(delay)

    if last_error is None:
        raise NotebookLMError("NotebookLM CLI failed without returning an error payload")
    raise NotebookLMRetryExhausted(last_error, max_retries) from last_error


def _decode_nlm_payload(text: str) -> dict | str:
    stripped = text.strip()
    if not stripped:
        return ""

    payload = _extract_last_json_object(stripped)
    if payload is not None:
        return payload

    try:
        decoded = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    return decoded if isinstance(decoded, dict) else stripped


def _extract_string_field(payload: dict | str, names: Sequence[str], label: str) -> str:
    if isinstance(payload, dict):
        for name in names:
            value = payload.get(name)
            if isinstance(value, str) and value.strip():
                return value.strip()
    elif payload.strip():
        identifier = _extract_identifier(payload)
        if identifier is not None:
            return identifier
        return payload.strip()

    raise NotebookLMError(f"NotebookLM CLI returned no {label}")


def _extract_identifier(text: str) -> str | None:
    uuid_match = re.search(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
        r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b",
        text,
    )
    if uuid_match:
        return uuid_match.group(0)

    labeled_match = re.search(
        r"\b(?:id|notebook id|source id)\b\s*[:=]\s*([A-Za-z0-9._-]{6,})",
        text,
        flags=re.IGNORECASE,
    )
    if labeled_match:
        return labeled_match.group(1)

    return None


def _extract_last_json_object(text: str) -> dict | None:
    starts: list[int] = []
    candidates: list[tuple[int, int]] = []
    depth = 0
    in_string = False
    escape = False

    for index, character in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif character == "\\":
                escape = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            if depth == 0:
                starts.append(index)
            depth += 1
        elif character == "}" and depth > 0:
            depth -= 1
            if depth == 0 and starts:
                candidates.append((starts.pop(), index + 1))

    for start, end in reversed(candidates):
        try:
            payload = json.loads(text[start:end])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _extract_status_code(text: str) -> int | None:
    patterns = [
        r'"status(?:_code)?"\s*:\s*(\d{3})',
        r"\bHTTP\s+(\d{3})\b",
        r"\bstatus(?:_code)?\s*[=:]\s*(\d{3})\b",
        r"\b(?:code|status)\s+(\d{3})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))

    fallback = re.search(r"\b(401|403|404|422|429|500|502|503|504)\b", text)
    if fallback:
        return int(fallback.group(1))

    if any(
        needle in text
        for needle in (
            "Could not resolve host",
            "stream disconnected before completion",
            "timed out",
            "Temporary failure",
            "ECONNRESET",
            "ETIMEDOUT",
        )
    ):
        return 503
    return None


def _looks_like_auth_error(text: str) -> bool:
    lowered = text.lower()
    return any(
        needle in lowered
        for needle in (
            "http 401",
            "http 403",
            "status 401",
            "status 403",
            "code 401",
            "code 403",
            " 401 unauthorized",
            " 403 forbidden",
            "unauthorized",
            "forbidden",
            "authentication",
            "authorization",
            "login",
            "log in",
            "expired credential",
            "access denied",
            "permission denied",
        )
    )


def _is_retryable_status(status_code: int | None) -> bool:
    if status_code is None:
        return True
    if status_code in _RETRYABLE_STATUS_CODES:
        return True
    return status_code not in _FATAL_STATUS_CODES


def _notebook_batch_size(config: Config) -> int:
    return max(1, config.notebooklm.max_sources_per_notebook)


_T = TypeVar("_T")


def _chunked(values: Sequence[_T], size: int) -> list[list[_T]]:
    if size < 1:
        raise ValueError("chunk size must be >= 1")
    return [list(values[index : index + size]) for index in range(0, len(values), size)]


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
