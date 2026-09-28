"""Tests for the extractor module."""

from __future__ import annotations

from zsum.config import Config
from zsum.extractor import (
    ExtractionResult,
    _assess_quality,
    _select_pages,
    extract_batch,
    extract_text,
    extraction_report,
)
from zsum.models import Item


class TestSelectPages:
    def test_short_doc_returns_all(self):
        assert _select_pages(3, 3, 2) == [0, 1, 2]

    def test_exact_boundary(self):
        assert _select_pages(5, 3, 2) == [0, 1, 2, 3, 4]

    def test_long_doc_first_and_last(self):
        pages = _select_pages(20, 3, 2)
        assert pages == [0, 1, 2, 18, 19]

    def test_no_duplicates(self):
        pages = _select_pages(4, 3, 2)
        assert len(pages) == len(set(pages))

    def test_single_page(self):
        assert _select_pages(1, 3, 2) == [0]


class TestAssessQuality:
    def test_good_text(self):
        config = Config(min_text_chars=500)
        warnings = []
        text = "This is a good academic paper with substantial content. " * 20
        assert _assess_quality(text, config, warnings) == "good"

    def test_too_short(self):
        config = Config(min_text_chars=500)
        warnings = []
        assert _assess_quality("short", config, warnings) == "degraded"

    def test_garbage_text(self):
        config = Config(min_text_chars=10)
        warnings = []
        garbage = "!@#$%^&*()_+" * 100
        assert _assess_quality(garbage, config, warnings) == "degraded"

    def test_empty_text(self):
        config = Config(min_text_chars=500)
        warnings = []
        assert _assess_quality("", config, warnings) == "degraded"


class TestExtractText:
    def test_no_pdf_uses_abstract(self):
        item = Item(
            citekey="test2020",
            zotero_key="ABC",
            item_id=1,
            title="Test",
            abstract="This is the abstract.",
            pdf_path=None,
        )
        result = extract_text(item, Config())
        assert result.quality == "no_pdf"
        assert result.text == "This is the abstract."
        assert result.extraction_method == "pages"

    def test_missing_pdf_file(self, tmp_path):
        item = Item(
            citekey="test2020",
            zotero_key="ABC",
            item_id=1,
            title="Test",
            abstract="Fallback",
            pdf_path=tmp_path / "nonexistent.pdf",
        )
        result = extract_text(item, Config())
        assert result.quality == "no_pdf"

    def test_no_pdf_no_abstract(self):
        item = Item(
            citekey="test2020",
            zotero_key="ABC",
            item_id=1,
            title="Test",
            pdf_path=None,
        )
        result = extract_text(item, Config())
        assert result.quality == "no_pdf"
        assert result.text == ""

    def test_sections_mode_no_pdf_preserves_mode_provenance(self):
        item = Item(
            citekey="test2020",
            zotero_key="ABC",
            item_id=1,
            title="Test",
            abstract="Fallback",
            pdf_path=None,
        )
        config = Config()
        config.extraction.mode = "sections"

        result = extract_text(item, config)

        assert result.quality == "no_pdf"
        assert result.extraction_method == "sections"

    def test_notebooklm_mode_no_pdf_preserves_mode_provenance(self):
        item = Item(
            citekey="test2020",
            zotero_key="ABC",
            item_id=1,
            title="Test",
            abstract="Fallback",
            pdf_path=None,
        )
        config = Config()
        config.extraction.mode = "notebooklm"

        result = extract_text(item, config)

        assert result.quality == "no_pdf"
        assert result.extraction_method == "notebooklm"

    def test_notebooklm_mode_skips_pdf_extraction_when_pdf_exists(self, real_pdf):
        item = Item(
            citekey="test2020",
            zotero_key="ABC",
            item_id=1,
            title="Test Paper",
            abstract="NotebookLM fallback abstract.",
            pdf_path=real_pdf,
        )
        config = Config()
        config.extraction.mode = "notebooklm"

        result = extract_text(item, config)

        assert result.quality == "good"
        assert result.text == "NotebookLM fallback abstract."
        assert result.page_count == 0
        assert result.pages_used == []
        assert result.extraction_method == "notebooklm"
        assert any("Extraction skipped: NotebookLM mode" in warning for warning in result.warnings)

    def test_sections_mode_uses_section_extractor(self, real_pdf):
        item = Item(
            citekey="test2020",
            zotero_key="ABC",
            item_id=1,
            title="Test Paper",
            pdf_path=real_pdf,
        )
        config = Config(min_text_chars=50)
        config.extraction.mode = "sections"

        result = extract_text(item, config)

        assert result.quality == "good"
        assert result.extraction_method == "sections"
        assert "introduction" in result.text.lower()
        assert "methods" in result.text.lower()

    def test_sections_mode_falls_back_to_pages_when_sections_are_degraded(
        self, monkeypatch, real_pdf
    ):
        import zsum.section_extractor as section_extractor

        item = Item(
            citekey="test2020",
            zotero_key="ABC",
            item_id=1,
            title="Test Paper",
            pdf_path=real_pdf,
        )
        config = Config(min_text_chars=50)
        config.extraction.mode = "sections"

        def fake_extract_sections(_item, _config):
            return ExtractionResult(
                citekey=_item.citekey,
                text="Abstract only",
                page_count=1,
                pages_used=[0],
                quality="degraded",
                warnings=["Only found one section"],
                extraction_method="sections",
            )

        monkeypatch.setattr(section_extractor, "extract_sections", fake_extract_sections)

        result = extract_text(item, config)

        assert result.extraction_method == "fallback_pages"
        assert result.quality == "good"
        assert any("Only found one section" in warning for warning in result.warnings)
        assert any("Fell back to page-range extraction" in warning for warning in result.warnings)

    def test_sections_mode_preserves_exception_warning_on_fallback(self, monkeypatch, real_pdf):
        import zsum.section_extractor as section_extractor

        item = Item(
            citekey="test2020",
            zotero_key="ABC",
            item_id=1,
            title="Test Paper",
            pdf_path=real_pdf,
        )
        config = Config(min_text_chars=50)
        config.extraction.mode = "sections"

        def raise_extract_sections(_item, _config):
            raise RuntimeError("boom")

        monkeypatch.setattr(section_extractor, "extract_sections", raise_extract_sections)

        result = extract_text(item, config)

        assert result.extraction_method == "fallback_pages"
        assert any("Section extraction failed: boom" in warning for warning in result.warnings)


class TestExtractBatch:
    def test_skips_cached_citekeys(self):
        items = {
            "a": Item(citekey="a", zotero_key="A", item_id=1, title="A", pdf_path=None),
            "b": Item(citekey="b", zotero_key="B", item_id=2, title="B", pdf_path=None),
            "c": Item(citekey="c", zotero_key="C", item_id=3, title="C", pdf_path=None),
        }
        results = extract_batch(items, Config(), skip_citekeys={"a", "b"})
        assert len(results) == 1
        assert "c" in results

    def test_empty_skip_processes_all(self):
        items = {
            "a": Item(citekey="a", zotero_key="A", item_id=1, title="A", pdf_path=None),
            "b": Item(citekey="b", zotero_key="B", item_id=2, title="B", pdf_path=None),
        }
        results = extract_batch(items, Config())
        assert len(results) == 2


class TestExtractionReport:
    def test_report_includes_counts(self):
        results = {
            "a": ExtractionResult(
                citekey="a",
                text="ok",
                page_count=10,
                pages_used=[0],
                quality="good",
            ),
            "b": ExtractionResult(
                citekey="b",
                text="",
                page_count=0,
                pages_used=[],
                quality="no_pdf",
                warnings=["No PDF"],
            ),
            "c": ExtractionResult(
                citekey="c",
                text="x",
                page_count=5,
                pages_used=[0],
                quality="degraded",
                warnings=["Short"],
            ),
        }
        report = extraction_report(results)
        assert "**Total items:** 3" in report
        assert "**Good:** 1" in report

    def test_report_lists_problem_items(self):
        results = {
            "good": ExtractionResult(
                citekey="good",
                text="ok",
                page_count=10,
                pages_used=[0],
                quality="good",
            ),
            "bad": ExtractionResult(
                citekey="bad",
                text="",
                page_count=0,
                pages_used=[],
                quality="degraded",
                warnings=["Failed"],
            ),
        }
        report = extraction_report(results)
        assert "bad" in report


class TestRealPDFExtraction:
    def test_extracts_text_from_real_pdf(self, real_pdf):
        item = Item(
            citekey="test2020",
            zotero_key="ABC",
            item_id=1,
            title="Test Paper",
            pdf_path=real_pdf,
        )
        config = Config(min_text_chars=50)
        result = extract_text(item, config)
        assert result.quality == "good"
        assert "phase field" in result.text.lower()
        assert result.page_count == 3
        assert len(result.pages_used) == 3

    def test_truncation_at_max_chars(self, real_pdf):
        item = Item(
            citekey="test2020",
            zotero_key="ABC",
            item_id=1,
            title="Test Paper",
            pdf_path=real_pdf,
        )
        config = Config(max_text_chars=100)
        result = extract_text(item, config)
        assert len(result.text) <= 100
