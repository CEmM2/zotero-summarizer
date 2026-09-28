"""Tests for Replace defaultdict(int) in extraction_report.

Covers:
- AC-1: Unexpected quality value triggers logger.error
- AC-2: Known quality values counted correctly
- AC-3: No silent zero-defaulting for unknown values

Existing coverage:
- test_extractor.py::test_report_includes_counts: known values counted (COVERED)
- test_MR_L3_T.py::test_standard_quality_values_still_reported_correctly: known values (COVERED)
- test_MR_L3_T.py::test_unexpected_quality_value_no_error: no KeyError (PARTIAL, no logging check)
"""

import logging

import pytest

from zsum.extractor import ExtractionResult, extraction_report
from zsum.models import TextQuality


class TestExtractionReportCounts:
    """Tests for Replace defaultdict(int) in extraction_report."""

    @pytest.mark.unit
    def test_unexpected_quality_logs_error(self, caplog):
        """
        Verifies: extraction_report() logs logger.error for unexpected quality values.
        Covers: AC-1 (unexpected quality triggers logger.error)
        Passes when: caplog captures ERROR level entry containing the unexpected value.
        """
        results = {
            "paper1": ExtractionResult(
                citekey="paper1",
                text="some text",
                page_count=5,
                pages_used=[0, 1, 2],
                quality="unexpected_quality",
            ),
        }
        with caplog.at_level(logging.ERROR, logger="zsum.extractor"):
            extraction_report(results)

        assert any(
            "unexpected_quality" in record.message
            for record in caplog.records
            if record.levelno == logging.ERROR
        ), "Expected an ERROR log entry mentioning the unexpected quality value"

    @pytest.mark.unit
    def test_known_qualities_no_error_logged(self, caplog):
        """
        Verifies: extraction_report() does NOT log errors for known TextQuality values.
        Covers: AC-2 (known values counted correctly, no spurious errors)
        Passes when: caplog contains no ERROR level messages when all
        results use GOOD/DEGRADED/NO_PDF.
        """
        results = {
            "a": ExtractionResult(
                citekey="a",
                text="full text content here",
                page_count=8,
                pages_used=[0, 1],
                quality=TextQuality.GOOD,
            ),
            "b": ExtractionResult(
                citekey="b",
                text="short",
                page_count=2,
                pages_used=[0],
                quality=TextQuality.DEGRADED,
                warnings=["Text too short"],
            ),
            "c": ExtractionResult(
                citekey="c",
                text="",
                page_count=0,
                pages_used=[],
                quality=TextQuality.NO_PDF,
                warnings=["No PDF available"],
            ),
        }
        with caplog.at_level(logging.ERROR, logger="zsum.extractor"):
            report = extraction_report(results)

        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert not error_records, (
            f"Expected no ERROR logs for known quality values, got: {error_records}"
        )
        assert "**Good:** 1" in report
        assert "**Degraded:** 1" in report
        assert "**No PDF:** 1" in report
