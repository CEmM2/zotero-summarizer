"""Boundary regression tests for text truncation after abstract prepend."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from zsum.config import Config
from zsum.extractor import _extract_from_pdf
from zsum.models import Item


def _make_item(tmp_path: Path, abstract: str = "") -> Item:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"")
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


class TestTruncationBoundaries:
    @pytest.mark.unit
    def test_one_over_boundary_truncates_and_logs_warning(self, tmp_path, caplog):
        extracted_text = "Body"
        prefix = "[ABSTRACT]\n"
        separator = "\n\n[EXTRACTED TEXT]\n"
        abstract = "A" * 21
        full_text = f"{prefix}{abstract}{separator}{extracted_text}"
        max_chars = len(full_text) - 1

        config = Config(max_text_chars=max_chars, min_text_chars=500)
        item = _make_item(tmp_path, abstract=abstract)
        mock_doc = _mock_backend([extracted_text])

        with (
            patch("zsum.extractor.get_pdf_backend", return_value=mock_doc),
            caplog.at_level(logging.WARNING, logger="zsum.extractor"),
        ):
            result = _extract_from_pdf(item, config)

        assert len(result.text) == max_chars
        assert result.text == full_text[:max_chars]
        assert any("Double truncation" in record.message for record in caplog.records)
