"""Strict response contract at the parser boundary.

Validates that _parse_card_response rejects:
- Non-JSON text (decode failure)
- Valid JSON that is not a dict (array, string, number, bool, null)
- Dict missing all expected card fields
- Wrong field types (graceful handling)
"""

from __future__ import annotations

import json

from tests.helpers import make_test_item as _make_item
from zsum.cards import _parse_card_response


def _assert_stub(card, item, text_quality="good"):
    """Assert the card is a metadata-only stub with no LLM content."""
    assert card.citekey == item.citekey
    assert card.title == item.title
    assert card.authors == item.authors
    assert card.year == item.year
    assert card.venue == item.venue
    assert card.doi == item.doi
    assert card.text_quality == text_quality
    assert card.problem == "unknown"
    assert card.methods == []
    assert card.key_findings == []
    assert card.limitations == []
    assert card.keywords == []


class TestDecodeFailures:
    """Stage 1: text that cannot be JSON-parsed at all."""

    def test_plain_text_returns_stub(self):
        item = _make_item()
        card, norm = _parse_card_response("This is not JSON", item, "degraded")
        _assert_stub(card, item, "degraded")
        assert norm == []

    def test_empty_string_returns_stub(self):
        item = _make_item()
        card, norm = _parse_card_response("", item, "good")
        _assert_stub(card, item, "good")
        assert norm == []

    def test_truncated_json_returns_stub(self):
        item = _make_item()
        card, norm = _parse_card_response('{"problem": "test', item, "good")
        _assert_stub(card, item, "good")
        assert norm == []


class TestNonDictJsonReturnsStub:
    """Stage 2: valid JSON that is not a dict."""

    def test_json_array(self):
        item = _make_item()
        card, norm = _parse_card_response("[1, 2, 3]", item, "good")
        _assert_stub(card, item)
        assert norm == []

    def test_json_string(self):
        item = _make_item()
        card, norm = _parse_card_response('"hello"', item, "good")
        _assert_stub(card, item)
        assert norm == []

    def test_json_number(self):
        item = _make_item()
        card, norm = _parse_card_response("42", item, "good")
        _assert_stub(card, item)
        assert norm == []

    def test_json_boolean(self):
        item = _make_item()
        card, norm = _parse_card_response("true", item, "good")
        _assert_stub(card, item)
        assert norm == []

    def test_json_null(self):
        item = _make_item()
        card, norm = _parse_card_response("null", item, "good")
        _assert_stub(card, item)
        assert norm == []


class TestDictMissingExpectedFields:
    """Stage 2: valid dict but with none of the expected card fields."""

    def test_empty_dict(self):
        item = _make_item()
        card, norm = _parse_card_response("{}", item, "good")
        _assert_stub(card, item)
        assert norm == []

    def test_dict_unrelated_keys(self):
        payload = json.dumps({"foo": "bar", "baz": 42})
        item = _make_item()
        card, norm = _parse_card_response(payload, item, "good")
        _assert_stub(card, item)
        assert norm == []

    def test_dict_metadata_keys_only(self):
        """Keys matching Item fields but not LLM content fields."""
        payload = json.dumps({"citekey": "x", "title": "y", "year": 2020})
        item = _make_item()
        card, norm = _parse_card_response(payload, item, "good")
        _assert_stub(card, item)
        assert norm == []


class TestWrongFieldTypes:
    """Graceful handling when field types are unexpected."""

    def test_problem_as_integer(self):
        """Non-string problem is normalized to 'unknown'."""
        payload = json.dumps({"problem": 123, "methods": ["FEM"]})
        item = _make_item()
        card, norm = _parse_card_response(payload, item, "good")
        assert card.problem == "unknown"
        assert card.methods == ["FEM"]

    def test_problem_as_empty_string(self):
        payload = json.dumps({"problem": "", "methods": []})
        item = _make_item()
        card, _ = _parse_card_response(payload, item, "good")
        assert card.problem == "unknown"

    def test_problem_as_none(self):
        payload = json.dumps({"problem": None, "methods": []})
        item = _make_item()
        card, norm = _parse_card_response(payload, item, "good")
        assert card.problem == "unknown"
        assert "problem" in norm

    def test_methods_as_string_coerced(self):
        payload = json.dumps({"problem": "Test", "methods": "FEM"})
        item = _make_item()
        card, _ = _parse_card_response(payload, item, "good")
        assert card.methods == ["FEM"]

    def test_extra_keys_ignored(self):
        payload = json.dumps(
            {
                "problem": "Test problem",
                "methods": ["FEM"],
                "unexpected_key": "ignored",
            }
        )
        item = _make_item()
        card, _ = _parse_card_response(payload, item, "good")
        assert card.problem == "Test problem"
        assert card.methods == ["FEM"]
