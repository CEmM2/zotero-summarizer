"""Tests for the structure advisor (advisory-only, single LLM call)."""

from __future__ import annotations

import pytest

from zsum.models import Collection, LibraryIndex, StructureAdvice
from zsum.restructure import (
    _build_restructure_prompt,
    _parse_advice_response,
    render_advice_report,
)

from .helpers import make_test_item


def _make_index(
    collections: list[tuple[str, str, str | None, list[str]]] | None = None,
) -> LibraryIndex:
    """Tiny fixture: list of (key, name, parent_key, citekeys)."""
    collections = collections or [
        ("A", "Methods", None, ["s17", "j18"]),
        ("B", "Applications", None, ["k19"]),
        ("A1", "Phase Field", "A", ["s17"]),
    ]
    idx = LibraryIndex()
    idx.items = {
        ck: make_test_item(citekey=ck) for ck in {c for col in collections for c in col[3]}
    }
    for key, name, parent, citekeys in collections:
        idx.collections[key] = Collection(
            key=key, name=name, parent_key=parent, path=name, item_citekeys=citekeys
        )
    # Children.
    for key, col in idx.collections.items():
        if col.parent_key and col.parent_key in idx.collections:
            idx.collections[col.parent_key].child_keys.append(key)
    # Paths.
    for col in idx.collections.values():
        if col.parent_key and col.parent_key in idx.collections:
            col.path = f"{idx.collections[col.parent_key].name} / {col.name}"
    return idx


@pytest.mark.unit
class TestPromptBuilder:
    def test_includes_tree_and_counts(self):
        idx = _make_index()
        digests = {"A": "Methods digest text", "B": "Applications digest text"}
        prompt = _build_restructure_prompt(idx, digests, cards={}, max_digest_chars=800)
        assert "Methods (2 papers)" in prompt
        assert "Applications (1 papers)" in prompt
        assert "Methods digest text" in prompt

    def test_truncates_long_digests(self):
        idx = _make_index()
        long_digest = "x" * 2000
        prompt = _build_restructure_prompt(
            idx, {"A": long_digest, "B": "", "A1": ""}, cards={}, max_digest_chars=200
        )
        # Ensure at most one copy of the truncated form, preceded by the ellipsis.
        assert "..." in prompt
        # Raw 2000-char string must not appear in full.
        assert long_digest not in prompt

    def test_fallback_to_titles_when_no_digest(self):
        idx = _make_index()
        prompt = _build_restructure_prompt(idx, digests={}, cards={}, max_digest_chars=800)
        assert "Sample papers" in prompt or "no digest" in prompt


@pytest.mark.unit
class TestJsonParser:
    def test_parses_clean_json(self):
        raw = """{
          "overall_assessment": "Looks OK",
          "suggestions": [
            {"type": "rename", "target": "A", "proposed": "A2", "rationale": "Clarity"}
          ],
          "proposed_hierarchy": {"Root": {"Child": {}}}
        }"""
        advice = _parse_advice_response(raw)
        assert advice.overall_assessment == "Looks OK"
        assert len(advice.suggestions) == 1
        assert advice.suggestions[0].type == "rename"
        assert advice.proposed_hierarchy == {"Root": {"Child": {}}}

    def test_strips_code_fences_and_think_blocks(self):
        raw = '<think>ponder</think>\n```json\n{"overall_assessment":"x"}\n```\n'
        advice = _parse_advice_response(raw)
        assert advice.overall_assessment == "x"

    def test_malformed_returns_empty_advice(self):
        advice = _parse_advice_response("not json at all")
        assert isinstance(advice, StructureAdvice)
        assert advice.overall_assessment == ""
        assert advice.suggestions == []

    def test_skips_bad_suggestion_entries(self):
        raw = '{"suggestions": [{"type": "rename", "rationale": "x"}, "junk", null]}'
        advice = _parse_advice_response(raw)
        assert len(advice.suggestions) == 1


@pytest.mark.unit
class TestReportRenderer:
    def test_includes_headings(self):
        idx = _make_index()
        advice = StructureAdvice(
            overall_assessment="All good",
            suggestions=[],
            proposed_hierarchy={"Methods": {}},
        )
        report = render_advice_report(advice, idx)
        assert "# Library Structure Advisory" in report
        assert "## Overall Assessment" in report
        assert "## Current Structure" in report
        assert "## Proposed Full Hierarchy" in report
        assert "advisory report" in report.lower()

    def test_renders_suggestions(self):
        idx = _make_index()
        advice = _parse_advice_response(
            '{"overall_assessment":"ok","suggestions":['
            '{"type":"merge","target":["A","B"],"proposed":"AB","rationale":"overlap"}'
            "]}"
        )
        report = render_advice_report(advice, idx)
        assert "Merge" in report
        assert "A, B" in report
        assert "overlap" in report
