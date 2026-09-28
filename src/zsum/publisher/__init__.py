"""Publisher: write Obsidian vault from index + cached cards/digests."""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import cast

import yaml

from ..config import Config
from ..models import CitationRecord, Collection, Item, LibraryIndex, PaperCard
from .resolver import (
    FilenameTracker,
    safe_filename,
)
from .resolver import (
    resolve_collection_wikilink as resolve_collection_wikilink,
)
from .resolver import (
    resolve_paper_wikilink as resolve_paper_wikilink,
)

# Backward-compatible private aliases. New code should use the public names
# from ``zsum.publisher.resolver``.
_FilenameTracker = FilenameTracker
_safe_filename = safe_filename

logger = logging.getLogger(__name__)


def _yaml_quote(value: str) -> str:
    """Wrap a string value in double quotes for safe YAML frontmatter output.

    Delegates to PyYAML to correctly handle all YAML special characters
    including newlines, tabs, colons, anchors (&), aliases (*), etc.
    """
    return cast(
        str,
        yaml.dump(value, default_style='"', default_flow_style=False),
    ).strip()


def publish_vault(
    index: LibraryIndex,
    config: Config,
    cards: dict[str, PaperCard] | None = None,
    digests: dict[str, str] | None = None,
    citations: dict[str, CitationRecord] | None = None,
) -> None:
    """Write the full Obsidian vault.

    Works in two modes:
    - Skeleton (Phase A): cards=None, digests=None -> metadata only
    - Full (Phase B): cards and digests populated -> summaries included
    """
    cards = cards or {}
    digests = digests or {}
    citations = citations or {}

    vault = config.vault_output
    collections_dir = vault / "Collections"
    collections_dir.mkdir(parents=True, exist_ok=True)

    col_tracker = _FilenameTracker()
    # Pre-register all collection names so wikilinks can reference already-resolved names
    for col in index.collections.values():
        col_tracker.resolve(col.name)

    top_n = getattr(config, "citations", None)
    top_n_value = top_n.top_n if top_n is not None else 10
    for col_key, col in index.collections.items():
        _write_collection_note(
            col,
            index,
            collections_dir,
            cards,
            digests.get(col_key, ""),
            col_tracker,
            citations,
            top_n_value,
        )
    col_tracker.log_summary()

    if config.generate_paper_notes:
        papers_dir = vault / "Papers"
        papers_dir.mkdir(parents=True, exist_ok=True)
        paper_tracker = _FilenameTracker()
        for citekey, item in index.items.items():
            card = cards.get(citekey)
            _write_paper_note(item, card, papers_dir, paper_tracker, citations.get(citekey))
        paper_tracker.log_summary()

    _write_index_note(index, vault, col_tracker)

    total_files = (
        len(index.collections) + (len(index.items) if config.generate_paper_notes else 0) + 1
    )
    logger.info("Published %d notes to %s", total_files, vault)


def _write_collection_note(
    col: Collection,
    index: LibraryIndex,
    collections_dir: Path,
    cards: dict[str, PaperCard],
    digest_md: str,
    tracker: _FilenameTracker,
    citations: dict[str, CitationRecord] | None = None,
    top_n: int = 10,
) -> None:
    """Write a single collection note."""
    citations = citations or {}
    lines: list[str] = []

    lines.append("---")
    lines.append(f"type: {_yaml_quote('collection')}")
    lines.append(f"created: {_yaml_quote(date.today().isoformat())}")
    lines.append(f"paper_count: {len(col.item_citekeys)}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {col.name}")
    lines.append("")

    if col.parent_key and col.parent_key in index.collections:
        parent_name = index.collections[col.parent_key].name
        parent_safe = tracker.resolve(parent_name)
        lines.append(f"> Parent: [[{parent_safe}]]")
    else:
        lines.append("> Parent: [[Library Index]]")

    child_names = [index.collections[ck].name for ck in col.child_keys if ck in index.collections]
    if child_names:
        links = ", ".join(f"[[{tracker.resolve(name)}]]" for name in sorted(child_names))
        lines.append(f"> Subcollections: {links}")

    lines.append("")
    if digest_md:
        cleaned = re.sub(r"^\s*#{1,6}\s+[Ss]ummary\s*\n*", "", digest_md).lstrip("\n")
        lines.append("## Summary")
        lines.append("")
        lines.append(cleaned)
    else:
        pending_digest = "*Pending \u2014 run `zsum digests` to generate.*"
        lines.extend(
            [
                "## Summary",
                "",
                "*Summary pending \u2014 run `zsum digests` to generate.*",
                "",
                "## Key Themes",
                "",
                pending_digest,
                "",
                "## Common Methods",
                "",
                pending_digest,
                "",
                "## Gaps and Limitations",
                "",
                pending_digest,
            ]
        )
    lines.append("")

    review_keys: list[str] = []
    research_keys: list[str] = []
    for citekey in sorted(col.item_citekeys):
        item = index.items.get(citekey)
        if not item:
            continue
        card = cards.get(citekey)
        paper_type = card.paper_type if card else item.paper_type
        if paper_type in {"review", "survey", "meta-analysis"}:
            review_keys.append(citekey)
        else:
            research_keys.append(citekey)

    def _render_paper_line(citekey: str) -> str:
        item = index.items[citekey]
        card = cards.get(citekey)
        if card and card.problem != "unknown":
            desc = card.problem
            if len(desc) > 120:
                desc = desc[:117] + "..."
            return f"- [[@{citekey}]] — {desc}"
        author_str = item.authors[0] if item.authors else "Unknown"
        year_str = str(item.year) if item.year else "n.d."
        return f"- [[@{citekey}]] — {author_str} ({year_str}). {item.title}"

    if review_keys:
        lines.append("## Review Papers")
        lines.append("")
        for citekey in review_keys:
            lines.append(_render_paper_line(citekey))
        lines.append("")

    if citations:
        ranked = [
            (ck, citations[ck].citation_count)
            for ck in col.item_citekeys
            if ck in citations and citations[ck].citation_count is not None
        ]
        ranked.sort(key=lambda t: t[1] or 0, reverse=True)
        top = ranked[:top_n]
        if top:
            lines.append(f"## Most Cited Papers (top {len(top)})")
            lines.append("")
            for citekey, count in top:
                item = index.items.get(citekey)
                if not item:
                    continue
                lines.append(f"- [[@{citekey}]] — {count} citations")
            lines.append("")

    lines.append("## Papers in this Collection")
    lines.append("")
    for citekey in research_keys:
        lines.append(_render_paper_line(citekey))
    lines.append("")

    safe_name = tracker.resolve(col.name)
    filepath = collections_dir / f"{safe_name}.md"
    filepath.write_text("\n".join(lines), encoding="utf-8")


def _write_paper_note(
    item: Item,
    card: PaperCard | None,
    papers_dir: Path,
    tracker: _FilenameTracker,
    citation: CitationRecord | None = None,
) -> None:
    """Write a single paper note."""
    lines: list[str] = []

    lines.append("---")
    lines.append("type: paper")
    lines.append(f"citekey: {_yaml_quote(item.citekey)}")
    lines.append(f"year: {item.year or 'unknown'}")
    paper_type = card.paper_type if card else item.paper_type
    lines.append(f"paper_type: {_yaml_quote(paper_type)}")
    lines.append("authors:")
    for author in item.authors:
        lines.append(f"  - {_yaml_quote(author)}")
    if item.venue:
        lines.append(f"venue: {_yaml_quote(item.venue)}")
    if item.doi:
        lines.append(f"doi: {_yaml_quote(item.doi)}")
    if citation and citation.citation_count is not None:
        lines.append(f"citation_count: {citation.citation_count}")
        lines.append(f"citation_source: {_yaml_quote(citation.source)}")
    if card and card.keywords:
        lines.append("keywords:")
        for kw in card.keywords:
            lines.append(f"  - {_yaml_quote(kw)}")
    elif item.tags:
        lines.append("keywords:")
        for tag in item.tags:
            lines.append(f"  - {_yaml_quote(tag)}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {item.citekey} \u2014 {item.title}")
    lines.append("")

    if card:
        lines.append("## Problem")
        lines.append(card.problem if card.problem != "unknown" else "*Pending*")
        lines.append("")
        lines.append("## Methods")
        if card.methods:
            for m in card.methods:
                lines.append(f"- {m}")
        else:
            lines.append("*Pending*")
        lines.append("")
        lines.append("## Key Findings")
        if card.key_findings:
            for kf in card.key_findings:
                lines.append(f"- {kf}")
        else:
            lines.append("*Pending*")
        lines.append("")
        lines.append("## Limitations")
        if card.limitations:
            for lim in card.limitations:
                lines.append(f"- {lim}")
        else:
            lines.append("*None noted*")
        lines.append("")
    else:
        lines.append("## Problem")
        lines.append("*Pending \u2014 run `zsum cards` to generate.*")
        lines.append("")
        lines.append("## Methods")
        lines.append("*Pending*")
        lines.append("")
        lines.append("## Key Findings")
        lines.append("*Pending*")
        lines.append("")
        lines.append("## Limitations")
        lines.append("*Pending*")
        lines.append("")

    if item.abstract:
        lines.append("## Abstract")
        lines.append(item.abstract)
        lines.append("")

    safe_name = tracker.resolve(f"@{item.citekey}")
    filepath = papers_dir / f"{safe_name}.md"
    filepath.write_text("\n".join(lines), encoding="utf-8")


def _write_index_note(index: LibraryIndex, vault: Path, col_tracker: _FilenameTracker) -> None:
    """Write the Library Index note (MOC)."""
    lines: list[str] = []

    lines.append("---")
    lines.append("type: moc")
    lines.append(f"created: {date.today().isoformat()}")
    lines.append(f"total_papers: {len(index.items)}")
    lines.append(f"total_collections: {len(index.collections)}")
    lines.append("---")
    lines.append("")
    lines.append("# Library Index")
    lines.append("")

    stats = index.stats
    review_count = sum(1 for item in index.items.values() if item.is_review)
    lines.append("## Overview")
    lines.append("")
    lines.append(f"- **Papers:** {stats['total_items']} ({stats['with_pdf']} with PDF)")
    lines.append(f"- **Reviews:** {review_count}")
    lines.append(f"- **Collections:** {stats['total_collections']}")
    lines.append("")
    lines.append("## Collections")
    lines.append("")

    roots = [
        col
        for col in index.collections.values()
        if col.parent_key is None or col.parent_key not in index.collections
    ]
    roots.sort(key=lambda c: c.name)

    for root in roots:
        _write_collection_tree(root, index, lines, col_tracker, depth=0)

    lines.append("")

    filepath = vault / "Library Index.md"
    filepath.write_text("\n".join(lines), encoding="utf-8")


def _write_collection_tree(
    col: Collection,
    index: LibraryIndex,
    lines: list[str],
    col_tracker: _FilenameTracker,
    depth: int,
) -> None:
    """Recursively write a collection tree as indented list."""
    indent = "  " * depth
    count = len(col.item_citekeys)
    safe_name = col_tracker.resolve(col.name)
    lines.append(f"{indent}- [[{safe_name}]] ({count} papers)")

    children = [index.collections[ck] for ck in col.child_keys if ck in index.collections]
    children.sort(key=lambda c: c.name)
    for child in children:
        _write_collection_tree(child, index, lines, col_tracker, depth + 1)


# ``_safe_filename`` and ``_FilenameTracker`` are now provided by
# ``zsum.publisher.resolver`` and re-exported above as backward-compatible
# private aliases.
