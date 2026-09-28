"""Tests for the section-aware extractor."""

from __future__ import annotations

import pytest

from zsum.config import Config, ExtractionConfig
from zsum.models import Item
from zsum.section_extractor import extract_sections


def _make_item(pdf_path, citekey: str = "test2020") -> Item:
    return Item(
        citekey=citekey,
        zotero_key="ABC123",
        item_id=1,
        title="Section Extraction Test",
        abstract="Fallback abstract",
        pdf_path=pdf_path,
    )


@pytest.fixture
def toc_pdf(tmp_path):
    fitz = pytest.importorskip("fitz")

    pdf_path = tmp_path / "toc_sections.pdf"
    doc = fitz.open()
    sections = [
        (
            "Abstract",
            "Abstract\n\nThis study summarizes structured extraction and section parsing. "
            "It provides enough content to exceed minimum quality thresholds.",
        ),
        (
            "Introduction",
            "Introduction\n\nThe introduction describes why first-and-last-page extraction "
            "can fail "
            "for repository "
            "PDFs and reports.",
        ),
        (
            "Methods",
            "Methods\n\nWe combine table-of-contents slicing with fuzzy heading detection and "
            "numbered heading support.",
        ),
    ]
    toc = []
    for page_number, (title, body) in enumerate(sections, start=1):
        page = doc.new_page()
        page.insert_text((72, 72), body, fontsize=12)
        toc.append([1, title, page_number])
    doc.set_toc(toc)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def fuzzy_pdf(tmp_path):
    fitz = pytest.importorskip("fitz")

    pdf_path = tmp_path / "fuzzy_sections.pdf"
    doc = fitz.open()
    sections = [
        "Introductory Remarks\n\nThis opening section motivates the pipeline change and "
        "explains why "
        "semantic section targeting is more reliable than "
        "naive page windows.",
        "Methodology\n\nThe method section explains how headings are normalized, fuzzily "
        "matched, and grouped into canonical sections.",
        "Concluding Remarks\n\nThe closing section highlights fallback behavior and expected "
        "quality tracking across the pipeline.",
    ]
    for body in sections:
        page = doc.new_page()
        page.insert_text((72, 72), body, fontsize=12)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def numbered_pdf(tmp_path):
    fitz = pytest.importorskip("fitz")

    pdf_path = tmp_path / "numbered_sections.pdf"
    doc = fitz.open()
    sections = [
        "1 Introduction\n\nThis introduction uses numbered headings and still should be detected "
        "as a target section by the extractor.",
        "2. Methods\n\nThis methods section continues the numbered pattern and provides "
        "sufficient text for extraction.",
        "3 Conclusions\n\nThis conclusion verifies numbered headings work for the final section "
        "as well.",
    ]
    for body in sections:
        page = doc.new_page()
        page.insert_text((72, 72), body, fontsize=12)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def single_section_pdf(tmp_path):
    fitz = pytest.importorskip("fitz")

    pdf_path = tmp_path / "single_section.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Abstract\n\nOnly one section is present here, so the extraction result should be "
        "marked degraded and allow the caller to fall back.",
        fontsize=12,
    )
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def short_sections_pdf(tmp_path):
    fitz = pytest.importorskip("fitz")

    pdf_path = tmp_path / "short_sections.pdf"
    doc = fitz.open()
    for body in ["Introduction\n\nTiny.", "Methods\n\nBrief."]:
        page = doc.new_page()
        page.insert_text((72, 72), body, fontsize=12)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def noisy_sections_pdf(tmp_path):
    fitz = pytest.importorskip("fitz")

    pdf_path = tmp_path / "noisy_sections.pdf"
    doc = fitz.open()
    for body in [
        "Introduction\n\n" + "!@#$%^&*() " * 40,
        "Methods\n\n" + "1234567890 -=+ " * 40,
    ]:
        page = doc.new_page()
        page.insert_text((72, 72), body, fontsize=12)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


class TestSectionExtractor:
    def test_extracts_sections_from_toc(self, toc_pdf):
        config = Config(min_text_chars=50)
        result = extract_sections(_make_item(toc_pdf), config)

        assert result.quality == "good"
        assert result.extraction_method == "sections"
        assert result.pages_used == [0, 1, 2]
        assert "structured extraction" in result.text.lower()
        assert "combine table-of-contents slicing" in result.text.lower()

    def test_extracts_sections_from_detected_headings(self, real_pdf):
        config = Config(min_text_chars=50)
        result = extract_sections(_make_item(real_pdf), config)

        assert result.quality == "good"
        assert result.extraction_method == "sections"
        assert result.pages_used == [0, 1, 2]
        assert "introduction" in result.text.lower()
        assert "methods" in result.text.lower()
        assert "conclusions" in result.text.lower()

    def test_fuzzy_matching_handles_heading_variants(self, fuzzy_pdf):
        config = Config(min_text_chars=50)
        result = extract_sections(_make_item(fuzzy_pdf), config)

        assert result.quality == "good"
        assert "introductory remarks" in result.text.lower()
        assert "methodology" in result.text.lower()
        assert "concluding remarks" in result.text.lower()

    def test_detects_numbered_headings(self, numbered_pdf):
        config = Config(min_text_chars=50)
        result = extract_sections(_make_item(numbered_pdf), config)

        assert result.quality == "good"
        assert result.pages_used == [0, 1, 2]
        assert "1 introduction" in result.text.lower()
        assert "2. methods" in result.text.lower()
        assert "3 conclusions" in result.text.lower()

    def test_marks_result_degraded_when_too_few_sections_found(self, single_section_pdf):
        config = Config(min_text_chars=50)
        result = extract_sections(_make_item(single_section_pdf), config)

        assert result.quality == "degraded"
        assert result.extraction_method == "sections"
        assert any("Only found 1 target section" in warning for warning in result.warnings)

    def test_marks_short_section_text_degraded_even_with_two_sections(self, short_sections_pdf):
        config = Config(min_text_chars=50)
        result = extract_sections(_make_item(short_sections_pdf), config)

        assert result.quality == "degraded"
        assert any("Section text too short" in warning for warning in result.warnings)

    def test_marks_low_letter_ratio_degraded(self, noisy_sections_pdf):
        config = Config(min_text_chars=50)
        result = extract_sections(_make_item(noisy_sections_pdf), config)

        assert result.quality == "degraded"
        assert any(
            "Low letter ratio in section extraction" in warning for warning in result.warnings
        )

    def test_respects_custom_target_sections(self, fuzzy_pdf):
        config = Config(
            min_text_chars=50,
            extraction=ExtractionConfig(target_sections=["methodology", "conclusions"]),
        )
        result = extract_sections(_make_item(fuzzy_pdf), config)

        assert result.quality == "good"
        assert "methodology" in result.text.lower()
        assert "concluding remarks" in result.text.lower()
