"""Paper card generation: LLM-based structured summarization."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from . import llm as _llm
from .cache import extraction_signature, iter_version_matched_cards, save_card
from .classifier import normalize_paper_type
from .config import Config, LLMProviderConfig
from .extractor import ExtractionResult
from .llm import complete_with_retry
from .models import Item, PaperCard
from .prompts import load_prompt

logger = logging.getLogger(__name__)

# JSON Schema for structured output of paper cards.  Matches the contract
# described in the paper_card.txt prompt template.
_CARD_OUTPUT_SCHEMA: dict = {
    "title": "PaperCard",
    "type": "object",
    "properties": {
        "problem": {
            "type": "string",
            "description": "1-3 sentences describing the research question, gap, or motivation",
        },
        "methods": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Each entry is one concise sentence describing a method or technique",
        },
        "key_findings": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Each entry is one concise sentence stating a result or conclusion",
        },
        "limitations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Each entry is one concise sentence noting a limitation or assumption",
        },
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3-8 specific technical terms",
        },
        "paper_type": {
            "type": "string",
            "enum": ["research", "review", "survey", "meta-analysis", "tutorial"],
        },
    },
    "required": ["problem", "methods", "key_findings", "limitations", "keywords", "paper_type"],
    "additionalProperties": False,
}


def _card_schema_for_stage(config: Config) -> dict | None:
    """Return the card JSON schema if the provider for 'cards' supports structured output."""
    provider = config.llm.provider_for_stage("cards")
    # Codex and Anthropic CLI handle output_schema natively via their own flags.
    if provider in ("codex_exec", "anthropic"):
        return _CARD_OUTPUT_SCHEMA
    prov_config = config.llm.config_for_stage("cards")
    if isinstance(prov_config, LLMProviderConfig) and prov_config.structured_output:
        return _CARD_OUTPUT_SCHEMA
    return None


def generate_card(
    item: Item, extraction: ExtractionResult, config: Config
) -> tuple[PaperCard, list[str]]:
    """Generate a structured summary card for a single paper via LLM.

    Loads the paper_card prompt template, builds a user prompt from the item metadata and
    extracted text, calls the LLM with retry logic, and parses the JSON response into a
    PaperCard. Falls back to a stub card with minimal fields if JSON parsing fails.
    Returns a tuple of (PaperCard, normalized_fields) where normalized_fields lists any
    field names that were normalized from None to a default value.
    """
    system_prompt = load_prompt("paper_card.txt")
    user_prompt = _build_user_prompt(item, extraction)
    llm_config = config.llm.config_for_stage("cards")
    # Pass the card JSON schema when the provider supports structured output.
    schema = _card_schema_for_stage(config)
    response = complete_with_retry(
        system_prompt,
        user_prompt,
        config,
        stage="cards",
        max_tokens=llm_config.max_tokens_card,
        output_schema=schema,
    )
    card, normalized_fields = _parse_card_response(
        response.text,
        item,
        extraction.quality,
        extraction.extraction_method,
    )
    logger.info(
        "Generated card for %s (%d in / %d out)",
        item.citekey,
        response.input_tokens,
        response.output_tokens,
    )
    return card, normalized_fields


def generate_cards_batch(
    items: dict[str, Item],
    extractions: dict[str, ExtractionResult],
    config: Config,
    cache_dir: Path,
) -> dict[str, PaperCard]:
    """Generate paper cards for all items, loading valid cached cards and generating pending ones.

    Scans cache_dir/cards/ for existing JSON card files whose prompt_version matches config,
    skipping regeneration for those items. For each remaining item that has an extraction result,
    calls generate_card() and saves the result to cache. Returns a dict mapping citekey to
    PaperCard for all successfully loaded or generated cards.
    """
    cards_dir = cache_dir / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    cards: dict[str, PaperCard] = {}
    cached_count = 0
    signature = extraction_signature(config)
    for fp, data in iter_version_matched_cards(cards_dir, config.prompt_version, signature):
        try:
            card = PaperCard(**{k: v for k, v in data.items() if k != "_meta"})
            cards[card.citekey] = card
            cached_count += 1
        except Exception as e:
            logger.warning("Failed to load cached card %s: %s", fp.name, e)
    logger.info("Loaded %d cached cards", cached_count)

    pending = [ck for ck in items if ck not in cards and ck in extractions]
    logger.info(
        "Generating %d new cards (%d cached, %d total)",
        len(pending),
        cached_count,
        len(items),
    )

    generated = failed = 0
    # Collect normalized-field reports across the batch for aggregated warning.
    batch_normalized: dict[str, list[str]] = {}
    for i, citekey in enumerate(pending):
        try:
            card, normalized_fields = generate_card(items[citekey], extractions[citekey], config)
            cards[citekey] = card
            save_card(card, config, cards_dir)
            if normalized_fields:
                batch_normalized[citekey] = normalized_fields
            generated += 1
            if (i + 1) % 10 == 0:
                logger.info("Progress: %d/%d cards generated", i + 1, len(pending))
        except Exception as e:
            # Fatal errors (auth, config, parse) must surface immediately — per-card
            # retry is pointless and would spam N identical failures across the batch.
            # Transient errors (already exhausted by complete_with_retry) fall through
            # to per-card logging so one bad card does not abort the whole batch.
            if not _llm._is_transient(e):
                raise
            logger.error("Failed to generate card for %s: %s", citekey, e)
            failed += 1
    if batch_normalized:
        all_fields = sorted({f for fields in batch_normalized.values() for f in fields})
        logger.warning(
            "Normalized None fields in %d cards: %s",
            len(batch_normalized),
            all_fields,
        )
    logger.info(
        "Card generation complete: %d generated, %d failed, %d cached",
        generated,
        failed,
        cached_count,
    )
    return cards


def _build_user_prompt(item: Item, extraction: ExtractionResult) -> str:
    """Assemble item metadata and extracted PDF text into an LLM user prompt string."""
    parts = [f"Citation key: {item.citekey}", f"Title: {item.title}"]
    if item.authors:
        parts.append(f"Authors: {', '.join(item.authors)}")
    if item.year:
        parts.append(f"Year: {item.year}")
    if item.venue:
        parts.append(f"Venue: {item.venue}")
    if item.doi:
        parts.append(f"DOI: {item.doi}")
    parts.extend(
        [
            "",
            f"Text quality: {extraction.quality}",
            f"Extraction method: {extraction.extraction_method or 'unknown'}",
            f"Pages extracted: {len(extraction.pages_used)} of {extraction.page_count}",
            "",
        ]
    )
    if extraction.text:
        parts.extend(["--- EXTRACTED TEXT ---", extraction.text])
    elif item.abstract:
        parts.extend(["--- ABSTRACT ONLY ---", item.abstract])
    else:
        parts.extend(["--- NO TEXT AVAILABLE ---", "Generate card from metadata only."])
    return "\n".join(parts)


# Expected fields in the LLM JSON response.  At least one must be present
# for the payload to be considered a valid card structure.
_EXPECTED_LLM_FIELDS: frozenset[str] = frozenset(
    {"problem", "methods", "key_findings", "limitations", "keywords", "paper_type"}
)


def _make_stub_card(
    item: Item,
    text_quality: str,
    extraction_method: str | None = None,
) -> PaperCard:
    """Build a minimal stub card from item metadata (no LLM content)."""
    return PaperCard(
        citekey=item.citekey,
        title=item.title,
        authors=item.authors,
        year=item.year,
        venue=item.venue,
        doi=item.doi,
        text_quality=text_quality,
        paper_type=item.paper_type,
        extraction_method=extraction_method,
    )


def _decode_response(response_text: str, citekey: str | None = None) -> object | None:
    """Strip <think> blocks and markdown fences, then JSON-parse; return value or None."""
    import re

    text = response_text.strip()
    # Strip <think>...</think> blocks (may span multiple lines, may appear multiple times).
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if not text:
        logger.warning(
            "LLM response for %s is empty after stripping thinking blocks",
            citekey or "<unknown>",
        )
        return None
    if text.startswith("```"):
        lines = [ln for ln in text.split("\n") if not ln.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(
            "Failed to parse LLM JSON for %s: %s",
            citekey or "<unknown>",
            e,
        )
        return None
    return data


def _validate_structure(data: object, citekey: str) -> dict | None:
    """Check parsed JSON is a dict with expected card fields; else None."""
    if not isinstance(data, dict):
        logger.warning(
            "LLM response for %s is not a JSON object (got %s), treating as invalid",
            citekey,
            type(data).__name__,
        )
        return None

    if not data.keys() & _EXPECTED_LLM_FIELDS:
        logger.warning(
            "LLM response for %s has no expected card fields, treating as invalid",
            citekey,
        )
        return None

    return data


def _normalize_fields(data: dict, heuristic_type: str = "research") -> tuple[dict, list[str]]:
    """Coerce None/missing card values to defaults; return (values, names)."""
    normalized: list[str] = []

    # String fields: None or missing -> "unknown"
    raw_problem = data.get("problem")
    problem = raw_problem if isinstance(raw_problem, str) and raw_problem else "unknown"
    if raw_problem is None:
        normalized.append("problem")

    # List fields: None or missing -> [] (via _ensure_list, but track explicit None)
    raw_methods = data.get("methods")
    if raw_methods is None:
        normalized.append("methods")

    raw_key_findings = data.get("key_findings")
    if raw_key_findings is None:
        normalized.append("key_findings")

    raw_limitations = data.get("limitations")
    if raw_limitations is None:
        normalized.append("limitations")

    raw_keywords = data.get("keywords")
    if raw_keywords is None:
        normalized.append("keywords")

    raw_paper_type = data.get("paper_type")
    paper_type = normalize_paper_type(raw_paper_type, fallback=heuristic_type)

    values = {
        "problem": problem,
        "methods": _ensure_list(raw_methods),
        "key_findings": _ensure_list(raw_key_findings),
        "limitations": _ensure_list(raw_limitations),
        "keywords": _ensure_list(raw_keywords),
        "paper_type": paper_type,
    }
    return values, sorted(normalized)


def _parse_card_response(
    response_text: str,
    item: Item,
    text_quality: str,
    extraction_method: str | None = None,
) -> tuple[PaperCard, list[str]]:
    """Parse LLM JSON into a PaperCard via decode/validate/normalize."""
    # Stage 1: Decode
    data = _decode_response(response_text, item.citekey)
    if data is None:
        return _make_stub_card(item, text_quality, extraction_method), []

    # Stage 2: Validate
    validated = _validate_structure(data, item.citekey)
    if validated is None:
        return _make_stub_card(item, text_quality, extraction_method), []

    # Stage 3: Normalize
    values, normalized = _normalize_fields(validated, heuristic_type=item.paper_type)

    card = PaperCard(
        citekey=item.citekey,
        title=item.title,
        authors=item.authors,
        year=item.year,
        venue=item.venue,
        doi=item.doi,
        text_quality=text_quality,
        extraction_method=extraction_method,
        **values,
    )
    return card, normalized


def _ensure_list(value: list | str | None) -> list[str]:
    """Coerce a str, list, or None value to a list of strings."""
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [value]
    return []
