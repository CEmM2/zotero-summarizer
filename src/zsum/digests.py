"""Collection digest generation: synthesize paper cards into collection summaries."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from .cache import (
    any_card_content_changed,
    load_cached_redigests,
    load_membership,
    redigest_state_for_collection,
    save_digest_hashes,
    save_redigest,
)
from .config import Config, LLMProviderConfig
from .llm import complete_with_retry
from .models import Collection, LibraryIndex, PaperCard
from .prompts import load_prompt

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RedigestBatchResult:
    """Outcome summary for a batch redigest run."""

    redigests: dict[str, str]
    generated: int
    cached: int
    failed: int
    missing_first_pass: list[str]


class _StructuredDigest(BaseModel):
    """Structured digest sections used with schema-validated output."""

    summary: str = Field(min_length=1)
    key_themes: list[str] = Field(min_length=1)
    common_methods: list[str] = Field(min_length=1)
    gaps_and_limitations: list[str] = Field(min_length=1)
    model_config = {"extra": "forbid"}


def _use_structured_digest(provider: str, llm_config: object) -> bool:
    """Return True if the digest stage should use schema-validated structured output."""
    # Codex and Anthropic CLI always support structured output natively.
    if provider in ("codex_exec", "anthropic"):
        return True
    # OpenAI-compatible providers opt in via the structured_output config flag.
    return isinstance(llm_config, LLMProviderConfig) and llm_config.structured_output


def generate_digest(col: Collection, cards: dict[str, PaperCard], config: Config) -> str:
    """Generate a markdown digest for a single collection by synthesizing its paper cards via LLM.

    Loads the collection_digest prompt template, builds a user prompt from the collection metadata
    and the provided paper cards, and calls the LLM with retry logic. Returns the stripped markdown
    text produced by the LLM as a collection-level synthesis of the papers.
    """
    provider = config.llm.provider_for_stage("digests")
    llm_config = config.llm.config_for_stage("digests")
    use_structured = _use_structured_digest(provider, llm_config)
    prompt_name = "collection_digest_structured.txt" if use_structured else "collection_digest.txt"
    system_prompt = load_prompt(prompt_name)
    user_prompt = _build_digest_prompt(col, cards)
    if use_structured:
        response = complete_with_retry(
            system_prompt,
            user_prompt,
            config,
            stage="digests",
            max_tokens=llm_config.max_tokens_digest,
            output_schema=_StructuredDigest.model_json_schema(),
        )
        digest = _render_structured_digest(_StructuredDigest.model_validate_json(response.text))
    else:
        response = complete_with_retry(
            system_prompt,
            user_prompt,
            config,
            stage="digests",
            max_tokens=llm_config.max_tokens_digest,
        )
        digest = response.text.strip()
    logger.info(
        "Generated digest for '%s' (%d in / %d out)",
        col.name,
        response.input_tokens,
        response.output_tokens,
    )
    return digest


def generate_redigest(
    col: Collection,
    first_pass_digest: str,
    config: Config,
    cards: dict[str, PaperCard] | None = None,
) -> str:
    """Refine a first-pass digest into final publish-ready markdown."""
    llm_config = config.llm.config_for_stage("redigest")
    system_prompt = load_prompt("collection_redigest.txt")
    user_prompt = _build_redigest_prompt(col, first_pass_digest, cards or {})
    response = complete_with_retry(
        system_prompt,
        user_prompt,
        config,
        stage="redigest",
        max_tokens=llm_config.max_tokens_digest,
    )
    digest = response.text.strip()
    logger.info(
        "Generated redigest for '%s' (%d in / %d out)",
        col.name,
        response.input_tokens,
        response.output_tokens,
    )
    return digest


def generate_digests_batch(
    index: LibraryIndex,
    cards: dict[str, PaperCard],
    config: Config,
    cache_dir: Path,
) -> dict[str, str]:
    """Generate markdown digests for all collections, processing children before parents.

    Iterates collections in bottom-up order so child collection digests are available when
    parent collections are processed. For each collection, checks whether the cached digest is
    still valid by comparing membership and card content hashes; skips regeneration if valid.
    Returns a dict mapping collection key to markdown digest text for all generated or cached
    digests.

    """
    digests_dir = cache_dir / "digests"
    digests_dir.mkdir(parents=True, exist_ok=True)
    cards_dir = cache_dir / "cards"
    old_membership = load_membership(cache_dir)
    current_membership = {key: sorted(col.item_citekeys) for key, col in index.collections.items()}
    digests = {}
    cached = generated = failed = 0
    processing_order = _bottom_up_order(index)

    for col_key in processing_order:
        col = index.collections[col_key]
        old_members = old_membership.get(col_key, [])
        new_members = current_membership.get(col_key, [])
        digest_file = digests_dir / f"{col_key}.md"

        cache_valid = (
            digest_file.exists()
            and old_members == new_members
            and not any_card_content_changed(col_key, new_members, cards_dir, digests_dir)
        )
        if cache_valid:
            digests[col_key] = digest_file.read_text(encoding="utf-8")
            cached += 1
            continue

        col_cards = {ck: cards[ck] for ck in col.item_citekeys if ck in cards}
        if not col_cards:
            logger.warning("No cards for '%s', skipping", col.name)
            continue

        try:
            digest = generate_digest(col, col_cards, config)
            digests[col_key] = digest
            digest_file.write_text(digest, encoding="utf-8")
            save_digest_hashes(col_key, list(col_cards.keys()), cards_dir, digests_dir)
            generated += 1
        except Exception as e:
            logger.error("Failed digest for '%s': %s", col.name, e)
            failed += 1

    logger.info(
        "Digest generation: %d generated, %d cached, %d failed",
        generated,
        cached,
        failed,
    )
    return digests


def generate_redigests_batch(
    index: LibraryIndex,
    first_pass_digests: dict[str, str],
    config: Config,
    cache_dir: Path,
    *,
    cards: dict[str, PaperCard] | None = None,
    collections: list[Collection] | None = None,
    force: bool = False,
) -> RedigestBatchResult:
    """Generate final-pass redigests for collections with first-pass digests."""
    redigests_dir = cache_dir / "redigests"
    redigests_dir.mkdir(parents=True, exist_ok=True)
    cached_redigests = load_cached_redigests(cache_dir)
    all_cards = cards or {}
    selected_keys = (
        {col.key for col in collections}
        if collections is not None
        else set(index.collections.keys())
    )

    redigests: dict[str, str] = {}
    cached = generated = failed = 0
    missing_first_pass: list[str] = []

    for col_key in _bottom_up_order(index):
        if col_key not in selected_keys:
            continue

        col = index.collections[col_key]
        first_pass_digest = first_pass_digests.get(col_key, "").strip()
        if not first_pass_digest:
            logger.warning(
                "No first-pass digest for '%s'; skipping redigest for this collection",
                col.name,
            )
            missing_first_pass.append(col.name)
            continue

        if not force and redigest_state_for_collection(col_key, cache_dir, config) == "ok":
            cached_redigest = cached_redigests.get(col_key)
            if cached_redigest is not None:
                redigests[col_key] = cached_redigest
                cached += 1
                continue

        col_cards = {ck: all_cards[ck] for ck in col.item_citekeys if ck in all_cards}
        try:
            redigest = generate_redigest(col, first_pass_digest, config, col_cards)
            save_redigest(col_key, redigest, first_pass_digest, cache_dir, config)
            redigests[col_key] = redigest
            generated += 1
        except Exception as e:
            logger.error("Failed redigest for '%s': %s", col.name, e)
            failed += 1

    logger.info(
        "Redigest generation: %d generated, %d cached, %d missing first-pass digests, %d failed",
        generated,
        cached,
        len(missing_first_pass),
        failed,
    )
    return RedigestBatchResult(
        redigests=redigests,
        generated=generated,
        cached=cached,
        failed=failed,
        missing_first_pass=missing_first_pass,
    )


def _bottom_up_order(index: LibraryIndex) -> list[str]:
    """Return collection keys in child-before-parent topological order via DFS."""
    visited = set()
    order = []

    def visit(key):
        if key in visited:
            return
        col = index.collections.get(key)
        if not col:
            return
        for child_key in col.child_keys:
            visit(child_key)
        visited.add(key)
        order.append(key)

    for key in index.collections:
        visit(key)
    return order


def _build_digest_prompt(col: Collection, cards: dict[str, PaperCard]) -> str:
    """Assemble collection metadata and sorted paper card summaries into an LLM user prompt."""
    parts = [
        f"Collection: {col.name}",
        f"Path: {col.path}",
        f"Number of papers: {len(cards)}",
        "",
    ]
    for ck in sorted(cards.keys()):
        card = cards[ck]
        parts.append(f"--- {card.citekey} ---")
        parts.append(f"Title: {card.title}")
        if card.authors:
            parts.append(f"Authors: {', '.join(card.authors)}")
        if card.year:
            parts.append(f"Year: {card.year}")
        parts.append(f"Problem: {card.problem}")
        if card.methods:
            parts.append(f"Methods: {'; '.join(card.methods)}")
        if card.key_findings:
            parts.append(f"Key findings: {'; '.join(card.key_findings)}")
        if card.limitations:
            parts.append(f"Limitations: {'; '.join(card.limitations)}")
        parts.append("")
    return "\n".join(parts)


def _build_redigest_prompt(
    col: Collection,
    first_pass_digest: str,
    cards: dict[str, PaperCard],
) -> str:
    """Assemble collection metadata and the first-pass digest for refinement."""
    parts = [
        f"Collection: {col.name}",
        f"Path: {col.path}",
        "",
        "First-pass digest to refine:",
        "",
        first_pass_digest.strip(),
        "",
    ]
    if cards:
        parts.extend(["Grounding papers:", ""])
        for ck in sorted(cards):
            card = cards[ck]
            parts.append(f"- [[@{card.citekey}]] {card.title}")
        parts.append("")
    parts.extend(
        [
            "Refinement goals:",
            "- improve clarity, structure, and final readability",
            "- preserve factual content and citations from the first-pass digest",
            "- do not add claims beyond the supplied digest and collection context",
        ]
    )
    return "\n".join(parts)


def _render_structured_digest(digest: _StructuredDigest) -> str:
    """Render a schema-validated digest as canonical markdown."""
    summary = digest.summary.strip()
    if "[[@" not in summary:
        raise ValueError("Structured digest summary must include citekey wikilinks")

    key_themes = _clean_digest_items(digest.key_themes, "key_themes")
    common_methods = _clean_digest_items(digest.common_methods, "common_methods")
    gaps = _clean_digest_items(digest.gaps_and_limitations, "gaps_and_limitations")

    lines = [
        "## Summary",
        summary,
        "",
        "## Key Themes",
        *[f"- {item}" for item in key_themes],
        "",
        "## Common Methods",
        *[f"- {item}" for item in common_methods],
        "",
        "## Gaps and Limitations",
        *[f"- {item}" for item in gaps],
    ]
    return "\n".join(lines).strip()


def _clean_digest_items(items: list[str], field_name: str) -> list[str]:
    """Return non-empty bullet items or raise if the field is effectively empty."""
    cleaned = [item.strip() for item in items if item and item.strip()]
    if not cleaned:
        raise ValueError(f"Structured digest field '{field_name}' must not be empty")
    return cleaned
