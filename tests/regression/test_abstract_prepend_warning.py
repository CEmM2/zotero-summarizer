"""Tests for Add truncation warning after abstract prepend.

Covers:
- AC-1: Double truncation logs a warning with citekey
- AC-2: Single truncation (no abstract prepend overflow) does not warn

Existing coverage (partial):
- test_MR_L1_T.py::test_abstract_prepend_respects_max_text_chars: truncation tested, no logging
- test_extractor.py::test_truncation_at_max_chars: truncation tested, no logging
"""

import logging

import pytest

from zsum.extractor import _extract_from_pdf
from zsum.models import Item


class TestAbstractPrependWarning:
    """Tests for Add truncation warning after abstract prepend."""

    @pytest.mark.unit
    def test_double_truncation_logs_warning(self, tmp_path, caplog):
        """
        Verifies: Second truncation after abstract prepend logs warning with citekey.
        Covers: AC-1 (double truncation logs warning with citekey)
        Passes when: caplog captures WARNING from zsum.extractor containing citekey.
        """
        fitz = pytest.importorskip("fitz")

        # Create a PDF with enough text to trigger initial truncation
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "B" * 5000)
        pdf_path = tmp_path / "test.pdf"
        doc.save(str(pdf_path))
        doc.close()

        item = Item(
            citekey="test2024",
            zotero_key="Z1",
            item_id=1,
            title="Test Paper",
            authors=["Author"],
            year=2024,
            abstract="A" * 2000,  # Long abstract — causes second truncation after prepend
            pdf_path=pdf_path,
        )

        # max_text_chars=500 -> initial text truncated to 500 chars.
        # After prepend "[ABSTRACT]\n" + 2000-char abstract + "\n\n[EXTRACTED TEXT]\n" + 500 chars
        # the combined string will be > 500, triggering the second truncation.
        # min_text_chars=9999 forces DEGRADED quality so abstract prepend happens.
        from zsum.config import Config

        config = Config(max_text_chars=500, min_text_chars=9999)

        with caplog.at_level(logging.WARNING, logger="zsum.extractor"):
            _extract_from_pdf(item, config)

        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("Double truncation" in msg and "test2024" in msg for msg in warning_messages), (
            f"Expected double-truncation warning with citekey 'test2024'; got: {warning_messages}"
        )

    @pytest.mark.unit
    def test_single_truncation_no_warning(self, tmp_path, caplog):
        """
        Verifies: Single truncation (no abstract prepend overflow) does not warn.
        Covers: AC-2 (no warning on single truncation)
        Passes when: caplog contains no WARNING about "Double truncation".
        """
        fitz = pytest.importorskip("fitz")

        # Create a PDF with long text to trigger the initial truncation
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "C" * 5000)
        pdf_path = tmp_path / "test_single.pdf"
        doc.save(str(pdf_path))
        doc.close()

        # No abstract — so the abstract prepend branch is never entered.
        item = Item(
            citekey="single2024",
            zotero_key="Z2",
            item_id=2,
            title="Single Truncation Paper",
            authors=["Author"],
            year=2024,
            abstract="",
            pdf_path=pdf_path,
        )

        from zsum.config import Config

        # Large enough max_text_chars to receive extracted text, then truncate once.
        config = Config(max_text_chars=500, min_text_chars=9999)

        with caplog.at_level(logging.WARNING, logger="zsum.extractor"):
            _extract_from_pdf(item, config)

        double_truncation_warnings = [
            r.message
            for r in caplog.records
            if r.levelno == logging.WARNING and "Double truncation" in r.message
        ]
        assert not double_truncation_warnings, (
            f"Expected no double-truncation warning; got: {double_truncation_warnings}"
        )
