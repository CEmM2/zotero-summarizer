"""Tests for Guard extraction_report against unexpected quality values.

Ensures that extraction_report() uses defaultdict(int) or .get(key, 0) to prevent
KeyError when results contain unexpected quality values not in the standard set
(good, degraded, no_pdf). This makes the function robust to future quality types
or corrupted data.
"""

from __future__ import annotations

import pytest

from zsum.extractor import ExtractionResult, extraction_report
from zsum.models import TextQuality


class TestExtractionReportQualityGuard:
    """
    Tests for Guard extraction_report against unexpected quality values
    Covers: [1] Unexpected quality values don't raise KeyError
    """

    @pytest.mark.unit
    def test_unexpected_quality_value_no_error(self):
        """
        Verifies: extraction_report handles unexpected quality strings without raising KeyError
        Covers: Unexpected quality values don't raise KeyError
        Passes when: extraction_report returns a valid report string when given results
        with non-standard quality values (e.g., "unknown", "custom", or any value
        not in {good, degraded, no_pdf})
        """
        results = {
            "paper1": ExtractionResult(
                citekey="paper1",
                text="some text",
                page_count=5,
                pages_used=[0, 1, 2],
                quality="unknown_quality",
            ),
        }
        # Should not raise KeyError
        report = extraction_report(results)
        assert isinstance(report, str)
        assert "paper1" in report

    @pytest.mark.unit
    def test_unexpected_quality_multiple_values(self):
        """
        Verifies: extraction_report handles multiple different unexpected quality values
        without raising KeyError.
        """
        results = {
            "paper1": ExtractionResult(
                citekey="paper1",
                text="some text",
                page_count=5,
                pages_used=[0, 1],
                quality="custom_quality",
            ),
            "paper2": ExtractionResult(
                citekey="paper2",
                text="other text",
                page_count=3,
                pages_used=[0],
                quality="another_new_type",
            ),
            "paper3": ExtractionResult(
                citekey="paper3",
                text="good text with many letters and words",
                page_count=10,
                pages_used=[0, 1, 2],
                quality=TextQuality.GOOD,
            ),
        }
        # Should not raise KeyError even with two unknown quality types
        report = extraction_report(results)
        assert isinstance(report, str)
        assert "**Total items:** 3" in report
        assert "**Good:** 1" in report

    @pytest.mark.unit
    def test_standard_quality_values_still_reported_correctly(self):
        """
        Verifies: standard quality values (good, degraded, no_pdf) are still reported
        correctly after the defaultdict change.
        """
        results = {
            "a": ExtractionResult(
                citekey="a",
                text="full text content here with many words",
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
        report = extraction_report(results)
        assert "**Total items:** 3" in report
        assert "**Good:** 1" in report
        assert "**Degraded:** 1" in report
        assert "**No PDF:** 1" in report

    @pytest.mark.unit
    def test_empty_results_no_error(self):
        """
        Verifies: extraction_report handles empty results dict without error.
        """
        report = extraction_report({})
        assert isinstance(report, str)
        assert "**Total items:** 0" in report
        assert "**Good:** 0" in report
        assert "**Degraded:** 0" in report
        assert "**No PDF:** 0" in report
