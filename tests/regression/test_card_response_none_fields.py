"""Tests for Normalize None field values in _parse_card_response.

Covers None field value normalization in _parse_card_response.
Covers:
  AC-1: Card with None 'problem' field gets 'unknown' instead
  AC-2: No None values in serialized PaperCard JSON
  AC-3: Warning logged listing all normalized fields
"""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

import pytest

from tests.helpers import make_test_item as _make_item
from zsum.cards import _parse_card_response, generate_cards_batch
from zsum.extractor import ExtractionResult


def _make_extraction(**overrides) -> ExtractionResult:
    defaults = dict(
        citekey="smith2017",
        text="Some extracted text about fracture.",
        page_count=10,
        pages_used=[0, 1, 2, 8, 9],
        quality="good",
    )
    defaults.update(overrides)
    return ExtractionResult(**defaults)


class TestCardResponseNoneFields:
    """
    Tests for Normalize None field values in _parse_card_response.
    Covers: AC-1, AC-2, AC-3.
    """

    @pytest.mark.unit
    def test_none_problem_field_normalized_to_unknown(self):
        """
        Verifies: When LLM response contains None for 'problem' field,
        it is normalized to 'unknown' instead of remaining None.

        Covers: AC-1 — Card with None 'problem' field gets 'unknown' instead

        Passes when: _parse_card_response returns card.problem == 'unknown'
        and normalized_fields contains 'problem'.
        """
        response = json.dumps(
            {
                "problem": None,
                "methods": ["FEM"],
                "key_findings": ["Good result"],
                "limitations": ["2D only"],
                "keywords": ["fracture"],
            }
        )
        card, normalized_fields = _parse_card_response(response, _make_item(), "good")

        assert card.problem == "unknown", (
            f"Expected 'unknown' for None problem, got {card.problem!r}"
        )
        assert "problem" in normalized_fields, (
            f"Expected 'problem' in normalized_fields, got {normalized_fields}"
        )

    @pytest.mark.unit
    def test_none_methods_field_normalized(self):
        """
        Verifies: When LLM response contains None for 'methods' field,
        it is normalized to an empty list [] instead of None.

        Covers: AC-2 — No None values in serialized PaperCard JSON

        Passes when: _parse_card_response returns card.methods == []
        and 'methods' is listed in normalized_fields.
        """
        response = json.dumps(
            {
                "problem": "Crack propagation",
                "methods": None,
                "key_findings": ["Good result"],
                "limitations": ["2D only"],
                "keywords": ["fracture"],
            }
        )
        card, normalized_fields = _parse_card_response(response, _make_item(), "good")

        assert card.methods == [], f"Expected [] for None methods, got {card.methods!r}"
        assert "methods" in normalized_fields, (
            f"Expected 'methods' in normalized_fields, got {normalized_fields}"
        )

    @pytest.mark.unit
    def test_none_key_findings_field_normalized(self):
        """
        Verifies: When LLM response contains None for 'key_findings' field,
        it is normalized to an empty list [] instead of None.

        Covers: AC-2 — No None values in serialized PaperCard JSON

        Passes when: _parse_card_response returns card.key_findings == []
        and 'key_findings' is listed in normalized_fields.
        """
        response = json.dumps(
            {
                "problem": "Crack propagation",
                "methods": ["FEM"],
                "key_findings": None,
                "limitations": ["2D only"],
                "keywords": ["fracture"],
            }
        )
        card, normalized_fields = _parse_card_response(response, _make_item(), "good")

        assert card.key_findings == [], (
            f"Expected [] for None key_findings, got {card.key_findings!r}"
        )
        assert "key_findings" in normalized_fields, (
            f"Expected 'key_findings' in normalized_fields, got {normalized_fields}"
        )

    @pytest.mark.unit
    def test_none_limitations_field_normalized(self):
        """
        Verifies: When LLM response contains None for 'limitations' field,
        it is normalized to an empty list [] instead of None.

        Covers: AC-2 — No None values in serialized PaperCard JSON

        Passes when: _parse_card_response returns card.limitations == []
        and 'limitations' is listed in normalized_fields.
        """
        response = json.dumps(
            {
                "problem": "Crack propagation",
                "methods": ["FEM"],
                "key_findings": ["Good result"],
                "limitations": None,
                "keywords": ["fracture"],
            }
        )
        card, normalized_fields = _parse_card_response(response, _make_item(), "good")

        assert card.limitations == [], f"Expected [] for None limitations, got {card.limitations!r}"
        assert "limitations" in normalized_fields, (
            f"Expected 'limitations' in normalized_fields, got {normalized_fields}"
        )

    @pytest.mark.unit
    def test_validation_warnings_aggregated_and_logged(self, tmp_path, caplog):
        """
        Verifies: All None/missing field normalizations are logged in a single
        aggregated warning message at the end of batch processing instead of
        per-card warnings.

        Covers: AC-3 — Warning logged listing all normalized fields

        Passes when: caplog captures a single batch-level warning from
        generate_cards_batch mentioning normalized fields and card count.
        """
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()

        item = _make_item(citekey="smith2017")
        items = {"smith2017": item}
        extractions = {"smith2017": _make_extraction()}

        from zsum.config import Config

        config = Config(prompt_version=1)

        # LLM response with None problem and methods — should be normalized
        llm_response_text = json.dumps(
            {
                "problem": None,
                "methods": None,
                "key_findings": ["Result A"],
                "limitations": ["Limit B"],
                "keywords": ["kw1"],
            }
        )

        from zsum.llm import LLMResponse

        mock_response = LLMResponse(
            text=llm_response_text, model="test-model", input_tokens=10, output_tokens=20
        )

        with (
            caplog.at_level(logging.WARNING, logger="zsum.cards"),
            patch("zsum.cards.complete_with_retry", return_value=mock_response),
            patch("zsum.cards.load_prompt", return_value="system prompt"),
        ):
            generate_cards_batch(items, extractions, config, tmp_path)

        # One aggregated batch warning must be present
        batch_warnings = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "Normalized None fields" in r.message
        ]
        assert len(batch_warnings) == 1, (
            f"Expected 1 aggregated batch warning, got {len(batch_warnings)}: "
            f"{[r.message for r in batch_warnings]}"
        )
        warning_msg = batch_warnings[0].message
        assert "1 cards" in warning_msg or "1" in warning_msg, (
            f"Expected card count in warning, got: {warning_msg!r}"
        )

    @pytest.mark.unit
    def test_serialized_card_json_has_no_none_values(self):
        """
        Verifies: After normalization, the PaperCard can be serialized to JSON
        without any None values present for LLM-generated fields.

        Covers: AC-2 — No None values in serialized PaperCard JSON

        Passes when: json.dumps(card.model_dump()) produces valid JSON with no
        None values in the string fields and list fields.
        """
        # All LLM-provided fields are None — everything must be normalized
        response = json.dumps(
            {
                "problem": None,
                "methods": None,
                "key_findings": None,
                "limitations": None,
                "keywords": None,
            }
        )
        card, normalized_fields = _parse_card_response(response, _make_item(), "good")

        serialized = json.dumps(card.model_dump())
        data = json.loads(serialized)

        # LLM content fields must not be None in serialized output
        assert data["problem"] == "unknown", f"Expected 'unknown', got {data['problem']!r}"
        assert data["methods"] == [], f"Expected [], got {data['methods']!r}"
        assert data["key_findings"] == [], f"Expected [], got {data['key_findings']!r}"
        assert data["limitations"] == [], f"Expected [], got {data['limitations']!r}"
        assert data["keywords"] == [], f"Expected [], got {data['keywords']!r}"

        # All 5 fields were normalized
        expected = {"problem", "methods", "key_findings", "limitations", "keywords"}
        assert set(normalized_fields) == expected, (
            f"Expected all 5 fields normalized, got {normalized_fields}"
        )
