"""Collection structure advisor: single-LLM-call, advisory-only."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .config import Config
from .llm import complete_with_retry
from .models import LibraryIndex, PaperCard, StructureAdvice, StructureSuggestion
from .prompts import load_prompt

logger = logging.getLogger(__name__)


def _sorted_hierarchy(index: LibraryIndex) -> list[tuple[int, str, int]]:
    """Yield ``(depth, name, paper_count)`` for each collection, parent-first."""

    collections = index.collections

    def depth(key: str) -> int:
        d = 0
        cur = collections.get(key)
        seen = set()
        while cur and cur.parent_key and cur.parent_key in collections and key not in seen:
            seen.add(key)
            key = cur.parent_key
            cur = collections[key]
            d += 1
        return d

    rows: list[tuple[int, str, int]] = []
    for col in sorted(collections.values(), key=lambda c: c.path):
        rows.append((depth(col.key), col.name, len(col.item_citekeys)))
    return rows


def _build_restructure_prompt(
    index: LibraryIndex,
    digests: dict[str, str],
    cards: dict[str, PaperCard] | None,
    max_digest_chars: int,
) -> str:
    parts: list[str] = ["Current collection structure (indent = depth):", ""]
    for depth, name, count in _sorted_hierarchy(index):
        indent = "  " * depth
        parts.append(f"{indent}- {name} ({count} papers)")

    parts.append("")
    parts.append("Per-collection context:")
    parts.append("")

    cards = cards or {}
    for col in sorted(index.collections.values(), key=lambda c: c.path):
        parts.append(f"### {col.name} — path: {col.path}")
        parts.append(f"Papers: {len(col.item_citekeys)}")
        digest = digests.get(col.key, "")
        if digest:
            if len(digest) > max_digest_chars:
                digest = digest[:max_digest_chars] + "..."
            parts.append(f"Summary: {digest}")
        else:
            # Fallback to titles + keywords from cards if available.
            bullets: list[str] = []
            for ck in col.item_citekeys[:10]:
                card = cards.get(ck)
                item = index.items.get(ck)
                if item is None:
                    continue
                kws = ", ".join((card.keywords if card else [])[:5])
                bullets.append(f"  - {item.title}" + (f" [{kws}]" if kws else ""))
            if bullets:
                parts.append("Sample papers:")
                parts.extend(bullets)
            else:
                parts.append("Summary: (no digest or card data available)")
        parts.append("")

    return "\n".join(parts)


_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


def _parse_advice_response(text: str) -> StructureAdvice:
    """Tolerant parser that pulls the first JSON object out of ``text``."""
    stripped = text.strip()
    # Strip <think>...</think> if present.
    stripped = re.sub(r"<think>.*?</think>", "", stripped, flags=re.DOTALL).strip()
    # Strip code fences.
    if stripped.startswith("```"):
        stripped = "\n".join(ln for ln in stripped.splitlines() if not ln.strip().startswith("```"))
    match = _JSON_BLOCK_RE.search(stripped)
    payload: dict = {}
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError as e:
            logger.warning("Restructure JSON parse failed: %s", e)

    suggestions_raw = payload.get("suggestions") or []
    suggestions: list[StructureSuggestion] = []
    for raw in suggestions_raw:
        if not isinstance(raw, dict):
            continue
        try:
            suggestions.append(
                StructureSuggestion(
                    type=str(raw.get("type", "")),
                    target=raw.get("target", ""),
                    proposed=raw.get("proposed", ""),
                    rationale=str(raw.get("rationale", "")),
                )
            )
        except Exception as e:
            logger.warning("Skipping bad suggestion: %s", e)

    return StructureAdvice(
        overall_assessment=str(payload.get("overall_assessment", "")),
        suggestions=suggestions,
        proposed_hierarchy=payload.get("proposed_hierarchy") or {},
    )


def advise_structure(
    index: LibraryIndex,
    digests: dict[str, str],
    cards: dict[str, PaperCard] | None,
    config: Config,
) -> StructureAdvice:
    """Call the LLM to produce an advisory report on the current collection structure."""
    system_prompt = load_prompt("restructure.txt")
    user_prompt = _build_restructure_prompt(
        index, digests, cards, config.restructure.max_digest_chars
    )
    llm_config = config.llm.config_for_stage("digests")
    response = complete_with_retry(
        system_prompt,
        user_prompt,
        config,
        stage="digests",
        max_tokens=llm_config.max_tokens_digest,
    )
    advice = _parse_advice_response(response.text)
    logger.info(
        "Structure advisor: %d suggestions (%d in / %d out tokens)",
        len(advice.suggestions),
        response.input_tokens,
        response.output_tokens,
    )
    return advice


def _render_hierarchy(tree: dict, depth: int = 0) -> list[str]:
    lines: list[str] = []
    if not isinstance(tree, dict):
        return lines
    for name, children in tree.items():
        lines.append(f"{'  ' * depth}- {name}")
        if isinstance(children, dict) and children:
            lines.extend(_render_hierarchy(children, depth + 1))
    return lines


def render_advice_report(advice: StructureAdvice, index: LibraryIndex) -> str:
    """Render the advisory as a standalone markdown report."""
    lines: list[str] = ["# Library Structure Advisory", ""]
    if advice.overall_assessment:
        lines.append("## Overall Assessment")
        lines.append("")
        lines.append(advice.overall_assessment)
        lines.append("")
    else:
        lines.append("_No overall assessment was produced._")
        lines.append("")

    if advice.suggestions:
        lines.append(f"## Suggestions ({len(advice.suggestions)})")
        lines.append("")
        for i, s in enumerate(advice.suggestions, 1):
            lines.append(f"### {i}. {s.type.title()} — {_fmt_target(s.target)}")
            lines.append("")
            if s.proposed:
                lines.append(f"**Proposed:** {_fmt_target(s.proposed)}")
                lines.append("")
            if s.rationale:
                lines.append(f"**Rationale:** {s.rationale}")
                lines.append("")
    else:
        lines.append("## Suggestions")
        lines.append("")
        lines.append("_The advisor did not propose any structural changes._")
        lines.append("")

    lines.append("## Current Structure")
    lines.append("")
    for depth, name, count in _sorted_hierarchy(index):
        lines.append(f"{'  ' * depth}- {name} ({count} papers)")
    lines.append("")

    if advice.proposed_hierarchy:
        lines.append("## Proposed Full Hierarchy")
        lines.append("")
        lines.extend(_render_hierarchy(advice.proposed_hierarchy))
        lines.append("")

    lines.append("---")
    lines.append(
        "_This is an advisory report. No changes have been made to your Zotero library."
        " To implement these suggestions, reorganize collections manually in Zotero._"
    )
    return "\n".join(lines)


def _fmt_target(target: str | list[str]) -> str:
    if isinstance(target, list):
        return ", ".join(str(t) for t in target)
    return str(target)


def save_advice(advice: StructureAdvice, report: str, cache_dir: Path) -> None:
    """Persist the advisory JSON and rendered markdown to the cache directory."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "restructure_advice.json").write_text(
        advice.model_dump_json(indent=2), encoding="utf-8"
    )
    (cache_dir / "restructure_report.md").write_text(report, encoding="utf-8")
