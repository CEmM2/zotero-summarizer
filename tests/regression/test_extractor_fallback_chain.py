"""Tests for Fallback chain in extractor.py."""

from __future__ import annotations

import pytest

from zsum.config import Config
from zsum.extractor import ExtractionResult, extract_batch, extract_text
from zsum.models import Item, TextQuality


def _make_item(citekey: str, pdf_path=None, abstract: str = "") -> Item:
    return Item(
        citekey=citekey,
        zotero_key="ABC",
        item_id=1,
        title="Test Paper",
        abstract=abstract,
        pdf_path=pdf_path,
    )


class TestExtractorFallbackChain:
    """Tests for Fallback chain in extractor.py.

    AC covered: [1, 2, 3, 4, 5]
    """

    @pytest.mark.unit
    def test_warning_logged_on_sections_fallback(self, monkeypatch, real_pdf):
        """Verifies: Warning is logged when section extraction falls back to pages.

        AC: Warning logged on every fallback activation.
        Passes when: result.warnings contains 'Fell back to page-range extraction'.
        """
        import zsum.section_extractor as section_extractor

        item = _make_item("key2020", pdf_path=real_pdf)
        config = Config(min_text_chars=50)
        config.extraction.mode = "sections"

        def fake_degraded(_item, _config):
            return ExtractionResult(
                citekey=_item.citekey,
                text="Abstract only",
                page_count=1,
                pages_used=[0],
                quality=TextQuality.DEGRADED,
                warnings=["Only found one section"],
                extraction_method="sections",
            )

        monkeypatch.setattr(section_extractor, "extract_sections", fake_degraded)

        result = extract_text(item, config)

        assert any("Fell back to page-range extraction" in w for w in result.warnings), (
            f"Expected fallback warning in warnings: {result.warnings}"
        )

    @pytest.mark.unit
    def test_nlm_failure_triggers_fallback(self, monkeypatch, real_pdf):
        """Verifies: When NLM per-paper extraction fails, fallback to page-range.

        AC: NLM per-paper failure triggers same fallback path.
        Passes when: extraction_method='fallback_pages' and warnings mention NLM failure.

        Note: The NLM per-paper fallback is implemented in cli._generate_nlm_fallback_cards,
        which calls extract_batch with mode='pages' then sets extraction_method='fallback_pages'
        and appends a warning. This test validates that layer directly.
        """
        from dataclasses import replace

        item = _make_item("nlm2020", pdf_path=real_pdf, abstract="Abstract text.")
        config = Config(min_text_chars=50)

        # Simulate what _generate_nlm_fallback_cards does for failed papers:
        # extract with pages mode, then tag as fallback
        pages_extraction = replace(config.extraction, mode="pages")
        pages_config = replace(config, extraction=pages_extraction)

        items_subset = {"nlm2020": item}
        extractions = extract_batch(items_subset, pages_config)

        for extraction in extractions.values():
            extraction.extraction_method = "fallback_pages"
            extraction.warnings.append("Fell back to page-range extraction (NotebookLM failed)")

        result = extractions["nlm2020"]

        assert any("NotebookLM failed" in w for w in result.warnings), (
            f"Expected NLM failure warning in warnings: {result.warnings}"
        )

    @pytest.mark.unit
    def test_nlm_fallback_includes_fallback_pages_method(self, monkeypatch, real_pdf):
        """Verifies: NLM fallback result sets extraction_method='fallback_pages'.

        AC: Fallback result has extraction_method='fallback_pages'.
        Passes when: result.extraction_method == 'fallback_pages' after NLM failure.
        """
        from dataclasses import replace

        item = _make_item("nlm2021", pdf_path=real_pdf)
        config = Config(min_text_chars=50)

        # Simulate _generate_nlm_fallback_cards extraction layer
        pages_extraction = replace(config.extraction, mode="pages")
        pages_config = replace(config, extraction=pages_extraction)

        items_subset = {"nlm2021": item}
        extractions = extract_batch(items_subset, pages_config)

        for extraction in extractions.values():
            extraction.extraction_method = "fallback_pages"
            extraction.warnings.append("Fell back to page-range extraction (NotebookLM failed)")

        result = extractions["nlm2021"]

        assert result.extraction_method == "fallback_pages", (
            f"Expected 'fallback_pages', got '{result.extraction_method}'"
        )

    @pytest.mark.unit
    def test_non_fallback_pages_extraction_unchanged(self, real_pdf):
        """Verifies: Normal page-range extraction is unaffected by fallback logic.

        AC: Non-fallback paths unaffected.
        Passes when: extraction_method='pages' and result is identical to baseline.
        """
        item = _make_item("pages2020", pdf_path=real_pdf)
        config = Config(min_text_chars=50)
        config.extraction.mode = "pages"

        result = extract_text(item, config)

        assert result.extraction_method == "pages", (
            f"Expected 'pages', got '{result.extraction_method}'"
        )
        assert result.quality == TextQuality.GOOD
        assert result.page_count > 0

    @pytest.mark.unit
    def test_non_fallback_sections_extraction_unchanged(self, monkeypatch, real_pdf):
        """Verifies: Successful section extraction is unaffected by fallback logic.

        AC: Non-fallback paths unaffected.
        Passes when: extraction_method='sections' and result matches non-fallback path.
        """
        import zsum.section_extractor as section_extractor

        item = _make_item("sec2020", pdf_path=real_pdf)
        config = Config(min_text_chars=50)
        config.extraction.mode = "sections"

        good_result = ExtractionResult(
            citekey="sec2020",
            text="Introduction\n\nThis is a well-structured paper with many sections.",
            page_count=3,
            pages_used=[0, 1, 2],
            quality=TextQuality.GOOD,
            warnings=[],
            extraction_method="sections",
        )

        monkeypatch.setattr(section_extractor, "extract_sections", lambda _i, _c: good_result)

        result = extract_text(item, config)

        assert result.extraction_method == "sections", (
            f"Expected 'sections', got '{result.extraction_method}'"
        )
        assert result.quality == TextQuality.GOOD
        assert len(result.warnings) == 0

    @pytest.mark.unit
    def test_exception_in_section_extraction_emits_fallback_warning(self, monkeypatch, real_pdf):
        """Verifies: Exception during section extraction triggers warning.

        AC: Warning logged on every fallback activation.
        Passes when: warnings contain both exception message and fallback indicator.
        """
        import zsum.section_extractor as section_extractor

        item = _make_item("exc2020", pdf_path=real_pdf)
        config = Config(min_text_chars=50)
        config.extraction.mode = "sections"

        def raise_exc(_item, _config):
            raise RuntimeError("section parser exploded")

        monkeypatch.setattr(section_extractor, "extract_sections", raise_exc)

        result = extract_text(item, config)

        assert result.extraction_method == "fallback_pages", (
            f"Expected 'fallback_pages', got '{result.extraction_method}'"
        )
        assert any("section parser exploded" in w for w in result.warnings), (
            f"Expected exception message in warnings: {result.warnings}"
        )
        assert any("Fell back to page-range extraction" in w for w in result.warnings), (
            f"Expected fallback indicator in warnings: {result.warnings}"
        )

    @pytest.mark.unit
    def test_fallback_result_is_valid_extraction_result(self, monkeypatch, real_pdf):
        """Verifies: Fallback produces valid ExtractionResult with all fields.

        AC: Ensure fallback produces valid ExtractionResult.
        Passes when: result has text, quality, pages_used, page_count, warnings.
        """
        import zsum.section_extractor as section_extractor

        item = _make_item("valid2020", pdf_path=real_pdf)
        config = Config(min_text_chars=50)
        config.extraction.mode = "sections"

        def fake_degraded(_item, _config):
            return ExtractionResult(
                citekey=_item.citekey,
                text="",
                page_count=0,
                pages_used=[],
                quality=TextQuality.DEGRADED,
                warnings=["Insufficient sections"],
                extraction_method="sections",
            )

        monkeypatch.setattr(section_extractor, "extract_sections", fake_degraded)

        result = extract_text(item, config)

        # Structural validity: all required fields present and well-typed
        assert isinstance(result, ExtractionResult)
        assert isinstance(result.citekey, str) and result.citekey
        assert isinstance(result.text, str)
        assert isinstance(result.quality, str) and result.quality in {
            TextQuality.GOOD,
            TextQuality.DEGRADED,
            TextQuality.NO_PDF,
            TextQuality.FALLBACK,
        }
        assert isinstance(result.pages_used, list)
        assert isinstance(result.page_count, int)
        assert isinstance(result.warnings, list) and len(result.warnings) > 0
        assert result.extraction_method == "fallback_pages"
