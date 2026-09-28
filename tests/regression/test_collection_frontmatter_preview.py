"""Regression tests for collection frontmatter polish and preview rendering."""

from __future__ import annotations

from datetime import date

import pytest

from zsum.config import Config
from zsum.extractor import ExtractionResult, _bounded_excerpt, extraction_report
from zsum.models import Collection, Item, LibraryIndex
from zsum.publisher import publish_vault


def _make_index() -> LibraryIndex:
    item = Item(
        citekey="smith2024",
        zotero_key="ABCD1234",
        item_id=1,
        title="A Test Paper",
        authors=["Smith, J."],
        year=2024,
    )
    collection = Collection(
        key="COL1",
        name="Test Collection",
        item_citekeys=["smith2024"],
    )
    return LibraryIndex(items={"smith2024": item}, collections={"COL1": collection})


class TestCollectionFrontmatter:
    @pytest.mark.regression
    def test_collection_frontmatter_values_quoted(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(_make_index(), config)

        content = (vault / "Collections" / "Test Collection.md").read_text(encoding="utf-8")
        assert 'type: "collection"' in content
        assert f'created: "{date.today().isoformat()}"' in content


class TestPreviewRendering:
    """Preview rendering: bounded excerpts, quality labels, warnings."""

    @pytest.mark.unit
    def test_good_extraction_shows_bounded_excerpt(self):
        long_text = "A" * 300
        results = {
            "alpha2020": ExtractionResult(
                citekey="alpha2020",
                text=long_text,
                page_count=10,
                pages_used=[0, 1, 2],
                quality="good",
            ),
        }
        report = extraction_report(results)
        assert "## Text Previews" in report
        assert "**alpha2020** [good]:" in report
        # The excerpt must be at most 200 chars + "..."
        preview_line = [
            ln for ln in report.splitlines() if "**alpha2020**" in ln and "[good]:" in ln
        ][0]
        # After "- **alpha2020** [good]: ", the excerpt should be 200 A's + "..."
        excerpt_part = preview_line.split(": ", 1)[1]
        assert excerpt_part == "A" * 200 + "..."

    @pytest.mark.unit
    def test_degraded_extraction_shows_warnings_and_excerpt(self):
        results = {
            "beta2021": ExtractionResult(
                citekey="beta2021",
                text="Short degraded text.",
                page_count=2,
                pages_used=[0],
                quality="degraded",
                warnings=["Text too short: 20 chars < 500"],
            ),
        }
        report = extraction_report(results)
        assert "**beta2021** [degraded]:" in report
        assert "Short degraded text." in report
        assert "  - Text too short: 20 chars < 500" in report

    @pytest.mark.unit
    def test_no_pdf_shows_fallback_and_warnings(self):
        results = {
            "gamma2019": ExtractionResult(
                citekey="gamma2019",
                text="Abstract as fallback.",
                page_count=0,
                pages_used=[],
                quality="no_pdf",
                warnings=["No PDF available", "Using abstract as fallback text"],
            ),
        }
        report = extraction_report(results)
        assert "**gamma2019** [no_pdf]:" in report
        assert "Abstract as fallback." in report
        assert "  - No PDF available" in report
        assert "  - Using abstract as fallback text" in report

    @pytest.mark.unit
    def test_no_pdf_empty_text_shows_no_text_marker(self):
        results = {
            "delta2022": ExtractionResult(
                citekey="delta2022",
                text="",
                page_count=0,
                pages_used=[],
                quality="no_pdf",
                warnings=["No PDF available"],
            ),
        }
        report = extraction_report(results)
        assert "(no text)" in report

    @pytest.mark.unit
    def test_summary_section_still_at_top(self):
        results = {
            "item2020": ExtractionResult(
                citekey="item2020",
                text="Some text.",
                page_count=5,
                pages_used=[0],
                quality="good",
            ),
        }
        report = extraction_report(results)
        lines = report.splitlines()
        # Summary section must appear before Text Previews
        summary_idx = next(i for i, ln in enumerate(lines) if "**Total items:**" in ln)
        preview_idx = next(i for i, ln in enumerate(lines) if "## Text Previews" in ln)
        assert summary_idx < preview_idx

    @pytest.mark.unit
    def test_bounded_excerpt_exact_200_no_ellipsis(self):
        text = "X" * 200
        assert _bounded_excerpt(text, 200) == text

    @pytest.mark.unit
    def test_bounded_excerpt_201_adds_ellipsis(self):
        text = "X" * 201
        assert _bounded_excerpt(text, 200) == "X" * 200 + "..."

    @pytest.mark.unit
    def test_bounded_excerpt_collapses_whitespace(self):
        text = "hello   world\n\nnew paragraph"
        assert _bounded_excerpt(text, 200) == "hello world new paragraph"
