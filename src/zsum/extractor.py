"""PDF text extraction: first N + last N pages, with quality flagging."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .config import Config
from .models import Item, TextQuality
from .pdf_backends import get_pdf_backend

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Result of extracting text from a single PDF."""

    citekey: str
    text: str
    page_count: int
    pages_used: list[int]
    quality: str  # "good" | "degraded" | "no_pdf" | "fallback"
    warnings: list[str] = field(default_factory=list)
    extraction_method: str = "pages"  # "pages" | "sections" | "notebooklm" | "fallback_pages"


def extract_text(item: Item, config: Config) -> ExtractionResult:
    """Extract text from a paper PDF.

    Strategy dispatched by config.extraction.mode:
    - "pages": first N + last N pages (legacy default)
    - "sections": section-aware extraction, falls back to pages on failure
    - "notebooklm": skip extraction (NLM pipeline handles it separately)
    """
    mode = config.extraction.mode

    if item.pdf_path is None or not item.pdf_path.exists():
        extraction_method = mode if mode in {"sections", "notebooklm"} else "pages"
        return _no_pdf_result(item, extraction_method=extraction_method)

    if mode == "notebooklm":
        # NLM pipeline handles extraction+cards+digests separately
        return ExtractionResult(
            citekey=item.citekey,
            text=item.abstract or "",
            page_count=0,
            pages_used=[],
            quality=TextQuality.GOOD if item.abstract else TextQuality.NO_PDF,
            warnings=["Extraction skipped: NotebookLM mode"],
            extraction_method="notebooklm",
        )

    if mode == "sections":
        section_warnings: list[str] = []
        try:
            from .section_extractor import extract_sections

            result = extract_sections(item, config)
            if result.quality != TextQuality.DEGRADED:
                return result
            section_warnings = list(result.warnings)
            # Fallback to page-range
            logger.warning(
                "Section extraction insufficient for %s, falling back to page-range",
                item.citekey,
            )
        except Exception as e:
            section_warnings.append(f"Section extraction failed: {e}")
            logger.warning(
                "Section extraction failed for %s: %s, falling back to page-range",
                item.citekey,
                e,
            )
        try:
            fallback = _extract_from_pdf(item, config)
            fallback.extraction_method = "fallback_pages"
            fallback.warnings.extend(section_warnings)
            fallback.warnings.append(
                "Fell back to page-range extraction (section extraction failed)"
            )
            return fallback
        except Exception as e:
            logger.warning("Fallback extraction also failed for %s: %s", item.citekey, e)
            return ExtractionResult(
                citekey=item.citekey,
                text=item.abstract or "",
                page_count=0,
                pages_used=[],
                quality=TextQuality.DEGRADED,
                warnings=section_warnings + [f"Both section and page-range extraction failed: {e}"],
                extraction_method="fallback_pages",
            )

    # mode == "pages" (default)
    try:
        return _extract_from_pdf(item, config)
    except Exception as e:
        logger.warning("Failed to extract %s: %s", item.citekey, e)
        return ExtractionResult(
            citekey=item.citekey,
            text=item.abstract or "",
            page_count=0,
            pages_used=[],
            quality=TextQuality.DEGRADED,
            warnings=[f"Extraction failed: {e}"],
        )


def extract_batch(
    items: dict[str, Item],
    config: Config,
    skip_citekeys: set[str] | None = None,
) -> dict[str, ExtractionResult]:
    """Extract text for multiple items, skipping already-cached citekeys.

    Raises RuntimeError/ValueError up front when the configured PDF backend is
    unknown or not installed, so a misconfigured backend fails before the batch
    starts instead of silently degrading every item.
    """
    if config.extraction.mode != "notebooklm":
        get_pdf_backend(config.extraction.backend)  # preflight: fail fast

    skip = skip_citekeys or set()
    results: dict[str, ExtractionResult] = {}
    skipped = 0

    for citekey, item in items.items():
        if citekey in skip:
            skipped += 1
            continue
        results[citekey] = extract_text(item, config)

    total = len(results)
    good = sum(1 for r in results.values() if r.quality == TextQuality.GOOD)
    degraded = sum(1 for r in results.values() if r.quality == TextQuality.DEGRADED)
    no_pdf = sum(1 for r in results.values() if r.quality == TextQuality.NO_PDF)

    logger.info(
        "Extracted %d items (good=%d, degraded=%d, no_pdf=%d, skipped=%d)",
        total,
        good,
        degraded,
        no_pdf,
        skipped,
    )
    return results


def _no_pdf_result(item: Item, extraction_method: str = "pages") -> ExtractionResult:
    """Fallback when no PDF is available."""
    text = item.abstract or ""
    warnings = ["No PDF available"]
    if text:
        warnings.append("Using abstract as fallback text")
    return ExtractionResult(
        citekey=item.citekey,
        text=text,
        page_count=0,
        pages_used=[],
        quality=TextQuality.NO_PDF,
        warnings=warnings,
        extraction_method=extraction_method,
    )


def _extract_from_pdf(item: Item, config: Config) -> ExtractionResult:
    """Extract text from first N + last N pages of a PDF."""
    if item.pdf_path is None:  # callers guard this; narrow for the type checker
        raise ValueError(f"Item {item.citekey} has no PDF path")

    warnings: list[str] = []

    backend = get_pdf_backend(config.extraction.backend)
    total_pages = backend.page_count(item.pdf_path)

    if config.max_pdf_pages is not None and total_pages > config.max_pdf_pages:
        text = item.abstract or ""
        return ExtractionResult(
            citekey=item.citekey,
            text=text,
            page_count=total_pages,
            pages_used=[],
            quality=TextQuality.NO_PDF,
            warnings=[
                f"Skipped: {total_pages} pages exceeds max_pdf_pages ({config.max_pdf_pages})"
            ],
        )

    pages_to_extract = _select_pages(total_pages, config.max_first_pages, config.max_last_pages)

    extracted = backend.page_texts(item.pdf_path, pages_to_extract)
    page_texts: list[str] = []
    for page_num in pages_to_extract:
        text = extracted.get(page_num, "")
        if text.strip():
            page_texts.append(text)

    full_text = "\n\n".join(page_texts)

    if len(full_text) > config.max_text_chars:
        full_text = full_text[: config.max_text_chars]
        warnings.append(f"Truncated to {config.max_text_chars} chars")

    quality = _assess_quality(full_text, config, warnings)

    if quality == TextQuality.DEGRADED and item.abstract:
        full_text = f"[ABSTRACT]\n{item.abstract}\n\n[EXTRACTED TEXT]\n{full_text}"
        warnings.append("Prepended abstract due to low extraction quality")
        if len(full_text) > config.max_text_chars:
            full_text = full_text[: config.max_text_chars]
            logger.warning(
                "Double truncation for %s: abstract prepend exceeded max_text_chars (%d)",
                item.citekey,
                config.max_text_chars,
            )

    return ExtractionResult(
        citekey=item.citekey,
        text=full_text,
        page_count=total_pages,
        pages_used=pages_to_extract,
        quality=quality,
        warnings=warnings,
    )


def _select_pages(total_pages: int, first_n: int, last_n: int) -> list[int]:
    """Select pages to extract, avoiding duplicates for short docs."""
    if total_pages <= first_n + last_n:
        return list(range(total_pages))

    first_pages = list(range(first_n))
    last_pages = list(range(total_pages - last_n, total_pages))

    seen: set[int] = set()
    result: list[int] = []
    for p in first_pages + last_pages:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


def _assess_quality(text: str, config: Config, warnings: list[str]) -> str:
    """Assess extraction quality based on text characteristics."""
    stripped = text.strip()

    if len(stripped) < config.min_text_chars:
        warnings.append(f"Text too short: {len(stripped)} chars < {config.min_text_chars}")
        return TextQuality.DEGRADED

    if stripped:
        letter_count = sum(1 for c in stripped if c.isalpha())
        letter_ratio = letter_count / len(stripped)
        if letter_ratio < 0.4:
            warnings.append(f"Low letter ratio: {letter_ratio:.2f} (possible scan/encoding issue)")
            return TextQuality.DEGRADED

    return TextQuality.GOOD


_PREVIEW_MAX_CHARS = 200


def extraction_report(results: dict[str, ExtractionResult]) -> str:
    """Generate a human-readable report of extraction results."""
    lines = ["# Extraction Report", ""]

    total = len(results)
    by_quality: dict[str, int] = {q.value: 0 for q in TextQuality}
    for r in results.values():
        if r.quality in by_quality:
            by_quality[r.quality] += 1
        else:
            logger.error(
                "extraction_report: unexpected quality value %r for item %r", r.quality, r.citekey
            )

    lines.append(f"**Total items:** {total}")
    lines.append(f"**Good:** {by_quality[TextQuality.GOOD]}")
    lines.append(f"**Degraded:** {by_quality[TextQuality.DEGRADED]}")
    lines.append(f"**No PDF:** {by_quality[TextQuality.NO_PDF]}")
    lines.append("")

    problem_items = [r for r in results.values() if r.quality != TextQuality.GOOD]
    if problem_items:
        lines.append("## Items needing attention")
        lines.append("")
        for r in sorted(problem_items, key=lambda x: x.citekey):
            lines.append(f"- **{r.citekey}** [{r.quality}]")
            for w in r.warnings:
                lines.append(f"  - {w}")
        lines.append("")

    # Text previews: bounded excerpt per item
    if results:
        lines.append("## Text Previews")
        lines.append("")
        for r in sorted(results.values(), key=lambda x: x.citekey):
            excerpt = _bounded_excerpt(r.text, _PREVIEW_MAX_CHARS)
            lines.append(f"- **{r.citekey}** [{r.quality}]: {excerpt}")
            for w in r.warnings:
                lines.append(f"  - {w}")
        lines.append("")

    return "\n".join(lines)


def _bounded_excerpt(text: str, max_chars: int) -> str:
    """Return first max_chars of text, with '...' if truncated."""
    # Collapse whitespace for a cleaner preview
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned if cleaned else "(no text)"
    return cleaned[:max_chars] + "..."
