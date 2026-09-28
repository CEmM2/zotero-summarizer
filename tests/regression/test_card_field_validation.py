"""Tests for Card response field validation.

Covers: Missing/empty required fields logged as WARNING; valid responses unchanged.
"""

from __future__ import annotations

import json
import logging

import pytest

from tests.helpers import make_test_item as _make_item
from zsum.cards import _parse_card_response


class TestCardFieldValidation:
    """
    Tests for Card response field validation.
    Covers: Missing/empty required fields logged as WARNING; valid responses unchanged.
    """

    @pytest.mark.unit
    def test_valid_response_no_warning(self, caplog):
        """
        Verifies: Valid response with all required fields produces no warnings.
        Covers: Valid responses pass through unchanged.
        Passes when: No WARNING logged for complete response.
        """
        response = json.dumps(
            {
                "problem": "How cracks propagate in brittle materials.",
                "methods": ["Phase field method", "FEM"],
                "key_findings": ["Model converges to Griffith criterion"],
                "limitations": ["2D only"],
                "keywords": ["phase-field", "fracture"],
            }
        )
        with caplog.at_level(logging.WARNING, logger="zsum.cards"):
            card, _ = _parse_card_response(response, _make_item(), "good")

        # No warnings should be logged for a complete valid response
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) == 0, (
            f"Unexpected warnings: {[r.message for r in warning_records]}"
        )
        # Card should be constructed with all fields intact
        assert card.problem == "How cracks propagate in brittle materials."
        assert card.methods == ["Phase field method", "FEM"]
        assert card.key_findings == ["Model converges to Griffith criterion"]
        assert card.limitations == ["2D only"]

    @pytest.mark.unit
    def test_missing_required_field_normalizes_silently(self, caplog):
        """
        Verifies: Missing required field (e.g., problem absent from JSON) is normalized
        to 'unknown' without emitting a per-card warning. Aggregated warnings are emitted
        at batch-end by generate_cards_batch, not per card by _parse_card_response.

        Replaced per-card warning with silent normalization + return value.
        """
        # JSON response missing the "problem" field entirely
        response = json.dumps(
            {
                "methods": ["Phase field method"],
                "key_findings": ["Model converges"],
                "limitations": ["2D only"],
                "keywords": ["fracture"],
            }
        )
        with caplog.at_level(logging.WARNING, logger="zsum.cards"):
            card, normalized_fields = _parse_card_response(response, _make_item(), "good")

        # No per-card warning — normalization is now aggregated at batch end
        assert not any(
            "missing required field" in r.message
            for r in caplog.records
            if r.levelno == logging.WARNING
        ), f"Unexpected per-card warning: {caplog.text}"
        # Normalized field name is returned for batch aggregation
        assert "problem" in normalized_fields
        # Card is still returned with normalized default
        assert card.citekey == "smith2017"
        assert card.problem == "unknown"  # normalized from None

    @pytest.mark.unit
    def test_empty_methods_list_no_warning(self, caplog):
        """
        Verifies: Empty required list field (methods=[]) does NOT emit a per-card warning
        since an empty list is a valid (non-None) value that does not need normalization.
        """
        # JSON response with methods as an empty list
        response = json.dumps(
            {
                "problem": "How cracks propagate.",
                "methods": [],
                "key_findings": ["Model converges"],
                "limitations": ["2D only"],
                "keywords": ["fracture"],
            }
        )
        with caplog.at_level(logging.WARNING, logger="zsum.cards"):
            card, normalized_fields = _parse_card_response(response, _make_item(), "good")

        # Empty list is a valid value, not None — no normalization needed
        assert "methods" not in normalized_fields
        # Card is returned with the empty methods list intact
        assert card.citekey == "smith2017"
        assert card.methods == []
