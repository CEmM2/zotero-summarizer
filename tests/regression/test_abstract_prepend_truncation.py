"""Tests for Apply max_text_chars cap after abstract prepend.

Ensures that when text extraction quality is degraded and an abstract is
prepended to the extracted text, the final combined text is still truncated
to respect the max_text_chars limit. This prevents the abstract prepend
from causing the result to exceed the configured maximum.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from zsum.config import Config
from zsum.extractor import extract_text
from zsum.models import Item


def _make_item(tmp_path: Path, abstract: str = "") -> Item:
    """Build a minimal Item with a real (empty) pdf file so _extract_from_pdf is invoked."""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"")  # file must exist; the PDF backend is mocked anyway
    return Item(
        citekey="smith2020",
        zotero_key="ABC123",
        item_id=1,
        title="Test Paper",
        abstract=abstract,
        pdf_path=pdf,
    )


class _FakeBackend:
    """Minimal PdfBackend stand-in yielding fixed page texts."""

    name = "fake"

    def __init__(self, page_texts: list[str]):
        self._texts = page_texts

    def page_count(self, path):
        return len(self._texts)

    def page_texts(self, path, pages):
        return {i: self._texts[i] for i in pages if 0 <= i < len(self._texts)}

    def lines(self, path, pages=None):
        return []

    def toc(self, path):
        return []


def _mock_backend(page_texts: list[str]) -> _FakeBackend:
    """Return a fake PdfBackend for patching zsum.extractor.get_pdf_backend."""
    return _FakeBackend(page_texts)


class TestAbstractPrependTruncation:
    """
    Tests for Apply max_text_chars cap after abstract prepend
    Covers: [1] Total text never exceeds max_text_chars
    """

    @pytest.mark.unit
    def test_abstract_prepend_respects_max_text_chars(self, tmp_path):
        """
        Verifies: text is truncated after abstract prepend so total length <= max_text_chars
        Covers: Total text never exceeds max_text_chars
        Passes when: len(result.text) <= config.max_text_chars even when abstract + extracted text
        would exceed it.
        """
        # max_text_chars = 200; degraded extracted text is short (below min_text_chars=500)
        # abstract = ~300 chars; after prepend the combined text would be well above 200
        max_chars = 200
        abstract = "A " * 150  # ~300 chars
        extracted_text = "x " * 5  # 10 chars — triggers DEGRADED quality

        config = Config(
            max_text_chars=max_chars,
            min_text_chars=500,  # force DEGRADED so abstract is prepended
        )
        item = _make_item(tmp_path, abstract=abstract)

        mock_doc = _mock_backend([extracted_text])

        with patch("zsum.extractor.get_pdf_backend", return_value=mock_doc):
            result = extract_text(item, config)

        assert result.quality == "degraded"
        assert len(result.text) <= max_chars, (
            f"Expected text length <= {max_chars}, got {len(result.text)}"
        )

    @pytest.mark.unit
    def test_abstract_prepend_not_truncated_when_within_limit(self, tmp_path):
        """
        Verifies: when the combined abstract + extracted text is within max_text_chars, no
        additional truncation occurs and the full prepended text is preserved.
        """
        max_chars = 5000
        abstract = "Short abstract."
        extracted_text = "Short body."  # will be DEGRADED due to min_text_chars

        config = Config(
            max_text_chars=max_chars,
            min_text_chars=500,  # force DEGRADED
        )
        item = _make_item(tmp_path, abstract=abstract)

        mock_doc = _mock_backend([extracted_text])

        with patch("zsum.extractor.get_pdf_backend", return_value=mock_doc):
            result = extract_text(item, config)

        assert result.quality == "degraded"
        # The prepended text should contain both the abstract and the extracted portion
        assert "[ABSTRACT]" in result.text
        assert abstract in result.text
        assert len(result.text) <= max_chars

    @pytest.mark.unit
    def test_abstract_prepend_exact_boundary_not_truncated(self, tmp_path):
        extracted_text = "Body"
        prefix = "[ABSTRACT]\n"
        separator = "\n\n[EXTRACTED TEXT]\n"
        abstract = "A" * 20
        max_chars = len(prefix) + len(abstract) + len(separator) + len(extracted_text)

        config = Config(max_text_chars=max_chars, min_text_chars=500)
        item = _make_item(tmp_path, abstract=abstract)
        mock_doc = _mock_backend([extracted_text])

        with patch("zsum.extractor.get_pdf_backend", return_value=mock_doc):
            result = extract_text(item, config)

        assert result.quality == "degraded"
        assert result.text == f"{prefix}{abstract}{separator}{extracted_text}"
        assert len(result.text) == max_chars
        assert all("Truncated to" not in warning for warning in result.warnings)

    @pytest.mark.unit
    def test_good_quality_text_not_double_truncated(self, tmp_path):
        """
        Verifies: when quality is GOOD (no abstract prepend), the text is truncated only
        by the initial cap and never re-truncated (unchanged behavior).
        """
        max_chars = 50
        # Enough good text to exceed max but still be GOOD quality (letter ratio ok)
        good_text = "This is a good academic paper with substantial content. " * 20

        config = Config(
            max_text_chars=max_chars,
            min_text_chars=10,  # low threshold so quality = GOOD
        )
        item = _make_item(tmp_path, abstract="Some abstract")

        mock_doc = _mock_backend([good_text])

        with patch("zsum.extractor.get_pdf_backend", return_value=mock_doc):
            result = extract_text(item, config)

        assert result.quality == "good"
        assert len(result.text) <= max_chars
        # No abstract prepend for good quality
        assert "[ABSTRACT]" not in result.text
