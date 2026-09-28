"""Section-aware PDF text extraction with TOC and heading heuristics."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from rapidfuzz import fuzz, process

from .config import Config
from .extractor import ExtractionResult
from .models import Item, TextQuality
from .pdf_backends import PdfBackend, PdfLine, TocEntry, get_pdf_backend

logger = logging.getLogger(__name__)

_NUMBERING_RE = re.compile(
    r"^(?:\(?[ivxlcdm\d]+(?:\.[ivxlcdm\d]+)*\)?[)\].:-]?\s+)+",
    re.IGNORECASE,
)

_SECTION_ALIASES: dict[str, set[str]] = {
    "abstract": {"abstract", "executive summary"},
    "introduction": {
        "introduction",
        "intro",
        "introductory remarks",
        "introduction and background",
    },
    "background": {"background", "technical background"},
    "related work": {
        "related work",
        "prior work",
        "previous work",
        "literature review",
    },
    "methods": {
        "method",
        "methods",
        "methodology",
        "approach",
        "materials and methods",
        "methods and materials",
    },
    "materials": {"materials", "data and materials"},
    "experimental": {
        "experimental",
        "experiments",
        "experimental setup",
        "evaluation setup",
    },
    "results": {"results", "findings", "experimental results"},
    "discussion": {"discussion", "analysis", "general discussion"},
    "conclusion": {
        "conclusion",
        "conclusions",
        "concluding remarks",
        "final remarks",
        "conclusion and future work",
    },
    "summary": {"summary", "overview"},
}


@dataclass(frozen=True)
class _TocCandidate:
    """TOC heading candidate used to slice page ranges."""

    toc_index: int
    level: int
    label: str
    title: str
    start_page: int


@dataclass
class _CapturedSections:
    """Internal representation of section extraction output before wrapping."""

    text: str
    pages_used: list[int]
    unique_sections: int
    warnings: list[str]


@dataclass(frozen=True)
class _HeadingCandidate:
    """Detected in-document heading candidate."""

    label: str
    line_index: int


def extract_sections(item: Item, config: Config) -> ExtractionResult:
    """Extract semantically relevant sections from a PDF.

    Uses a TOC-based strategy when available and falls back to heading detection from
    page text. If fewer than two target sections are found, the result is marked
    degraded so the caller can decide whether to fall back to page-range extraction.
    """
    if item.pdf_path is None or not item.pdf_path.exists():
        return ExtractionResult(
            citekey=item.citekey,
            text=item.abstract or "",
            page_count=0,
            pages_used=[],
            quality=TextQuality.NO_PDF,
            warnings=["No PDF available for section extraction"],
            extraction_method="sections",
        )

    backend = get_pdf_backend(config.extraction.backend)
    total_pages = backend.page_count(item.pdf_path)
    if config.max_pdf_pages is not None and total_pages > config.max_pdf_pages:
        return ExtractionResult(
            citekey=item.citekey,
            text="",
            page_count=total_pages,
            pages_used=[],
            quality=TextQuality.DEGRADED,
            warnings=[
                f"Skipped section extraction: {total_pages} pages exceeds "
                f"max_pdf_pages ({config.max_pdf_pages})"
            ],
            extraction_method="sections",
        )

    target_aliases = _build_target_aliases(config.extraction.target_sections)
    toc_entries = backend.toc(item.pdf_path)
    toc_capture = _extract_from_toc(
        backend,
        item.pdf_path,
        toc_entries,
        total_pages,
        target_aliases,
        config.extraction.fuzzy_threshold,
    )
    lines = backend.lines(item.pdf_path)
    heading_capture = _extract_from_headings(
        lines,
        target_aliases,
        config.extraction.fuzzy_threshold,
    )
    capture = max(
        (toc_capture, heading_capture),
        key=lambda result: (result.unique_sections, len(result.text.strip())),
    )

    warnings: list[str] = []
    if toc_capture.text and capture is not toc_capture:
        warnings.append("TOC boundaries were incomplete; used detected headings instead")
    warnings.extend(capture.warnings)

    text = capture.text.strip()
    if len(text) > config.max_text_chars:
        text = text[: config.max_text_chars]
        warnings.append(f"Truncated section extraction to {config.max_text_chars} chars")

    quality = _assess_section_quality(text, capture.unique_sections, config, warnings)
    if capture.unique_sections < 2:
        warnings.append(
            f"Only found {capture.unique_sections} target section(s); expected at least 2"
        )

    return ExtractionResult(
        citekey=item.citekey,
        text=text,
        page_count=total_pages,
        pages_used=capture.pages_used,
        quality=quality,
        warnings=_dedupe(warnings),
        extraction_method="sections",
    )


def _build_target_aliases(target_sections: list[str]) -> dict[str, str]:
    """Expand configured target sections into normalized alias → canonical label mappings."""
    aliases: dict[str, str] = {}
    for target in target_sections:
        normalized_target = _strip_numbering(_normalize_heading(target))
        if not normalized_target:
            continue
        canonical = _resolve_canonical_target(normalized_target)
        aliases[canonical] = canonical
        for alias in _SECTION_ALIASES.get(canonical, set()):
            aliases[_normalize_heading(alias)] = canonical
    return aliases


def _resolve_canonical_target(target: str) -> str:
    """Resolve a normalized target section to a canonical label."""
    for canonical, aliases in _SECTION_ALIASES.items():
        if target == canonical or target in aliases:
            return canonical
    return target


def _extract_from_toc(
    backend: PdfBackend,
    path: Path,
    toc_entries: list[TocEntry],
    total_pages: int,
    target_aliases: dict[str, str],
    threshold: int,
) -> _CapturedSections:
    """Extract sections by slicing page ranges from the PDF TOC."""
    if not toc_entries:
        return _CapturedSections(text="", pages_used=[], unique_sections=0, warnings=[])

    candidates: list[_TocCandidate] = []
    for toc_index, entry in enumerate(toc_entries):
        label = _match_section_name(entry.title, target_aliases, threshold)
        if label is None:
            continue
        candidates.append(
            _TocCandidate(
                toc_index=toc_index,
                level=entry.level,
                label=label,
                title=entry.title,
                start_page=entry.page_index,
            )
        )

    if not candidates:
        return _CapturedSections(text="", pages_used=[], unique_sections=0, warnings=[])

    # Resolve each candidate's page range, then fetch all needed pages in one
    # backend call (pdfminer re-parses the document per call).
    ranges: list[tuple[_TocCandidate, range]] = []
    needed_pages: set[int] = set()
    for candidate in candidates:
        end_page = _resolve_toc_end_page(
            toc_entries, candidate.toc_index, candidate.level, total_pages
        )
        if end_page <= candidate.start_page:
            end_page = min(candidate.start_page + 1, total_pages)
        page_range = range(candidate.start_page, end_page)
        ranges.append((candidate, page_range))
        needed_pages.update(page_range)

    page_texts = backend.page_texts(path, sorted(needed_pages))

    sections: list[str] = []
    pages_used: set[int] = set()
    seen_labels: set[str] = set()
    for candidate, page_range in ranges:
        if candidate.label in seen_labels:
            continue
        page_chunks: list[str] = []
        for page_index in page_range:
            page_text = page_texts.get(page_index, "").strip()
            if not page_text:
                continue
            page_chunks.append(page_text)
            pages_used.add(page_index)
        if not page_chunks:
            continue
        sections.append("\n\n".join(page_chunks))
        seen_labels.add(candidate.label)

    return _CapturedSections(
        text="\n\n".join(sections).strip(),
        pages_used=sorted(pages_used),
        unique_sections=len(seen_labels),
        warnings=[],
    )


def _resolve_toc_end_page(
    toc_entries: list[TocEntry],
    start_index: int,
    start_level: int,
    total_pages: int,
) -> int:
    """Return the page where a TOC section should stop."""
    for entry in toc_entries[start_index + 1 :]:
        if entry.level <= start_level and entry.page_index > 0:
            return min(entry.page_index, total_pages)
    return total_pages


def _extract_from_headings(
    lines: list[PdfLine],
    target_aliases: dict[str, str],
    threshold: int,
) -> _CapturedSections:
    """Extract sections by detecting headings from page text and font cues."""
    if not lines:
        return _CapturedSections(text="", pages_used=[], unique_sections=0, warnings=[])

    body_font_size = _estimate_body_font_size(lines)
    candidates: list[_HeadingCandidate] = []
    for line_index, line in enumerate(lines):
        label = _match_section_name(line.text, target_aliases, threshold)
        if label is None:
            continue
        normalized = _strip_numbering(_normalize_heading(line.text))
        if not _looks_like_heading(line.text, line.font_size, body_font_size) and (
            normalized not in target_aliases
        ):
            continue
        if candidates and candidates[-1].label == label:
            continue
        candidates.append(_HeadingCandidate(label=label, line_index=line_index))

    if not candidates:
        return _CapturedSections(text="", pages_used=[], unique_sections=0, warnings=[])

    sections: list[str] = []
    pages_used: set[int] = set()
    seen_labels: set[str] = set()
    for index, candidate in enumerate(candidates):
        if candidate.label in seen_labels:
            continue
        end_index = candidates[index + 1].line_index if index + 1 < len(candidates) else len(lines)
        chunk = lines[candidate.line_index : end_index]
        chunk_text = "\n".join(fragment.text for fragment in chunk).strip()
        if not chunk_text:
            continue
        sections.append(chunk_text)
        pages_used.update(fragment.page_index for fragment in chunk)
        seen_labels.add(candidate.label)

    return _CapturedSections(
        text="\n\n".join(sections).strip(),
        pages_used=sorted(pages_used),
        unique_sections=len(seen_labels),
        warnings=[],
    )


def _estimate_body_font_size(lines: list[PdfLine]) -> float:
    """Estimate the dominant body font size for heading prominence checks."""
    candidates = [line.font_size for line in lines if 40 <= len(line.text) <= 400]
    if not candidates:
        candidates = [line.font_size for line in lines if len(line.text) >= 10]
    if not candidates:
        candidates = [line.font_size for line in lines]
    return float(median(candidates)) if candidates else 0.0


def _looks_like_heading(text: str, font_size: float, body_font_size: float) -> bool:
    """Return True when a line resembles a heading rather than body prose."""
    compact = " ".join(text.split())
    if not compact or len(compact) > 120:
        return False
    words = compact.split()
    if len(words) > 12:
        return False
    if compact.endswith((".", ";", "?", "!")) and not _NUMBERING_RE.match(compact):
        return False
    alpha_count = sum(1 for char in compact if char.isalpha())
    if alpha_count < 3:
        return False
    prominent_font = font_size >= body_font_size + 0.5 if body_font_size else False
    return (
        prominent_font
        or compact.istitle()
        or compact.isupper()
        or bool(_NUMBERING_RE.match(compact))
    )


def _match_section_name(text: str, target_aliases: dict[str, str], threshold: int) -> str | None:
    """Resolve a heading string to one of the configured target sections."""
    normalized = _strip_numbering(_normalize_heading(text))
    if not normalized:
        return None
    if normalized in target_aliases:
        return target_aliases[normalized]
    best_match = process.extractOne(
        normalized,
        list(target_aliases.keys()),
        scorer=fuzz.ratio,
    )
    if best_match is None:
        return None
    alias, score, _index = best_match
    if score < threshold:
        return None
    return target_aliases[alias]


def _normalize_heading(text: str) -> str:
    """Normalize heading text for fuzzy matching."""
    normalized = text.replace("\xa0", " ").replace("\u200b", " ").strip().casefold()
    normalized = re.sub(r"[‐‑–—]", "-", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip(" :-–—")


def _strip_numbering(text: str) -> str:
    """Strip common leading section numbering from a heading candidate."""
    return _NUMBERING_RE.sub("", text).strip()


def _dedupe(values: list[str]) -> list[str]:
    """Preserve order while removing duplicate warnings."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _assess_section_quality(
    text: str,
    unique_sections: int,
    config: Config,
    warnings: list[str],
) -> str:
    """Assess extracted section text quality before accepting it as good."""
    stripped = text.strip()
    if unique_sections < 2 or not stripped:
        return TextQuality.DEGRADED

    if len(stripped) < config.min_text_chars:
        warnings.append(f"Section text too short: {len(stripped)} chars < {config.min_text_chars}")
        return TextQuality.DEGRADED

    letter_count = sum(1 for char in stripped if char.isalpha())
    letter_ratio = letter_count / len(stripped)
    if letter_ratio < 0.4:
        warnings.append(
            f"Low letter ratio in section extraction: {letter_ratio:.2f} "
            "(possible scan/encoding issue)"
        )
        return TextQuality.DEGRADED

    return TextQuality.GOOD
