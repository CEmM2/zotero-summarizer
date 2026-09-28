"""Separate schema validation from normalization in card parsing.

Validates the three-stage refactor of _parse_card_response:
1. Decode (JSON parse)
2. Validate (dict with recognizable card structure)
3. Normalize (None/missing -> defaults)

Also verifies that metadata always comes from the Item, never from
the LLM payload.
"""

from __future__ import annotations

import json

from tests.helpers import make_test_item as _make_item
from zsum.cards import (
    _decode_response,
    _make_stub_card,
    _normalize_fields,
    _parse_card_response,
    _validate_structure,
)


class TestDecodeStage:
    """Unit tests for _decode_response (Stage 1)."""

    def test_valid_json_dict(self):
        data = _decode_response('{"problem": "test"}')
        assert data == {"problem": "test"}

    def test_valid_json_array(self):
        data = _decode_response("[1, 2, 3]")
        assert data == [1, 2, 3]

    def test_invalid_json(self):
        assert _decode_response("not json") is None

    def test_empty_string(self):
        assert _decode_response("") is None

    def test_strips_markdown_fences(self):
        body = '{"problem": "test"}'
        data = _decode_response(f"```json\n{body}\n```")
        assert data == {"problem": "test"}

    def test_strips_fences_without_language(self):
        body = '{"problem": "test"}'
        data = _decode_response(f"```\n{body}\n```")
        assert data == {"problem": "test"}


class TestValidateStage:
    """Unit tests for _validate_structure (Stage 2)."""

    def test_valid_dict_with_expected_field(self):
        data = {"problem": "test", "methods": []}
        assert _validate_structure(data, "key1") == data

    def test_non_dict_rejected(self):
        assert _validate_structure([1, 2], "key1") is None
        assert _validate_structure("hello", "key1") is None
        assert _validate_structure(42, "key1") is None
        assert _validate_structure(None, "key1") is None

    def test_dict_no_expected_fields_rejected(self):
        assert _validate_structure({"foo": "bar"}, "key1") is None
        assert _validate_structure({}, "key1") is None

    def test_dict_with_one_expected_field_accepted(self):
        """At least one expected field is sufficient."""
        data = {"methods": ["FEM"], "extra": "value"}
        assert _validate_structure(data, "key1") == data

    def test_all_five_expected_fields_accepted(self):
        data = {
            "problem": "P",
            "methods": ["M"],
            "key_findings": ["K"],
            "limitations": ["L"],
            "keywords": ["W"],
        }
        assert _validate_structure(data, "key1") == data


class TestNormalizeStage:
    """Unit tests for _normalize_fields (Stage 3)."""

    def test_all_fields_present_no_normalization(self):
        data = {
            "problem": "P",
            "methods": ["M"],
            "key_findings": ["K"],
            "limitations": ["L"],
            "keywords": ["W"],
        }
        values, norm = _normalize_fields(data)
        assert values["problem"] == "P"
        assert values["methods"] == ["M"]
        assert norm == []

    def test_missing_fields_normalized(self):
        data = {"problem": "P"}
        values, norm = _normalize_fields(data)
        assert values["problem"] == "P"
        assert values["methods"] == []
        assert values["key_findings"] == []
        assert values["limitations"] == []
        assert values["keywords"] == []
        assert sorted(norm) == ["key_findings", "keywords", "limitations", "methods"]

    def test_none_problem_normalized_to_unknown(self):
        data = {"problem": None, "methods": []}
        values, norm = _normalize_fields(data)
        assert values["problem"] == "unknown"
        assert "problem" in norm

    def test_empty_string_problem_normalized_to_unknown(self):
        data = {"problem": "", "methods": []}
        values, norm = _normalize_fields(data)
        assert values["problem"] == "unknown"

    def test_non_string_problem_normalized_to_unknown(self):
        data = {"problem": 123, "methods": []}
        values, norm = _normalize_fields(data)
        assert values["problem"] == "unknown"

    def test_string_method_coerced_to_list(self):
        data = {"problem": "P", "methods": "single method"}
        values, _ = _normalize_fields(data)
        assert values["methods"] == ["single method"]


class TestStubCard:
    """Unit tests for _make_stub_card."""

    def test_stub_has_item_metadata(self):
        item = _make_item(citekey="zhao2020", title="Dynamic Fracture", year=2020)
        stub = _make_stub_card(item, "degraded")
        assert stub.citekey == "zhao2020"
        assert stub.title == "Dynamic Fracture"
        assert stub.year == 2020
        assert stub.text_quality == "degraded"
        assert stub.problem == "unknown"
        assert stub.methods == []

    def test_stub_preserves_all_item_fields(self):
        item = _make_item(
            doi="10.1234/test",
            venue="Nature",
            authors=["A, B", "C, D"],
        )
        stub = _make_stub_card(item, "good")
        assert stub.doi == "10.1234/test"
        assert stub.venue == "Nature"
        assert stub.authors == ["A, B", "C, D"]


class TestEndToEndParsing:
    """Integration tests for the full _parse_card_response pipeline."""

    def test_valid_payload_parses_correctly(self):
        payload = json.dumps(
            {
                "problem": "Crack propagation",
                "methods": ["Phase field", "FEM"],
                "key_findings": ["Model converges"],
                "limitations": ["2D only"],
                "keywords": ["fracture"],
            }
        )
        item = _make_item()
        card, norm = _parse_card_response(payload, item, "good")
        assert card.problem == "Crack propagation"
        assert card.methods == ["Phase field", "FEM"]
        assert card.key_findings == ["Model converges"]
        assert card.limitations == ["2D only"]
        assert card.keywords == ["fracture"]
        assert norm == []

    def test_metadata_from_item_not_payload(self):
        """Even if the LLM returns metadata fields, they are ignored."""
        payload = json.dumps(
            {
                "problem": "Test",
                "methods": [],
                "citekey": "wrong_key",
                "title": "Wrong Title",
                "year": 9999,
            }
        )
        item = _make_item(citekey="correct", title="Correct Title", year=2021)
        card, _ = _parse_card_response(payload, item, "good")
        assert card.citekey == "correct"
        assert card.title == "Correct Title"
        assert card.year == 2021

    def test_malformed_payload_returns_stub(self):
        """Passes JSON decode but fails validation -> stub."""
        payload = json.dumps({"unrelated": "data"})
        item = _make_item()
        card, norm = _parse_card_response(payload, item, "degraded")
        assert card.citekey == item.citekey
        assert card.problem == "unknown"
        assert card.methods == []
        assert card.text_quality == "degraded"
        assert norm == []

    def test_partial_payload_normalizes_missing(self):
        """Only 'problem' present -> other fields normalized."""
        payload = json.dumps({"problem": "Some problem"})
        item = _make_item()
        card, norm = _parse_card_response(payload, item, "good")
        assert card.problem == "Some problem"
        assert card.methods == []
        assert card.key_findings == []
        assert "methods" in norm
        assert "key_findings" in norm
