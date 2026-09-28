"""Tests for regression tests locking the filter contract.

These tests lock the public contract of ``_filter_collections`` so
that future changes cannot silently alter its matching semantics.

Contract:
  1. A filter token matches if it equals a collection's key OR name.
  2. Matching is exact (case-sensitive, no substring/glob).
  3. Descendants of every matched collection are always included.
  4. The result is deduplicated by collection key.
  5. An empty filter list returns an empty dict.
  6. Unrecognized tokens are silently ignored.
"""

from __future__ import annotations

import pytest

from zsum.indexer import _filter_collections
from zsum.models import Collection


def _make_tree() -> dict[str, Collection]:
    """Standard test tree.

    Structure::

        TOP (key="TOP", name="TopLevel")
        +-- MID (key="MID", name="Middle")
        |   +-- LEAF (key="LEAF", name="Leaf")
        SOLO (key="SOLO", name="Standalone")
    """
    return {
        "TOP": Collection(
            key="TOP",
            name="TopLevel",
            child_keys=["MID"],
        ),
        "MID": Collection(
            key="MID",
            name="Middle",
            parent_key="TOP",
            child_keys=["LEAF"],
        ),
        "LEAF": Collection(
            key="LEAF",
            name="Leaf",
            parent_key="MID",
        ),
        "SOLO": Collection(
            key="SOLO",
            name="Standalone",
        ),
    }


class TestFilterContractRegression:
    """Regression tests locking the filter contract."""

    # ---- Contract 1: key OR name matching ----

    @pytest.mark.unit
    def test_contract_name_match(self):
        """Contract-1: token matching by name selects the collection."""
        tree = _make_tree()
        result = _filter_collections(tree, ["Standalone"])
        assert "SOLO" in result

    @pytest.mark.unit
    def test_contract_key_match(self):
        """Contract-1: token matching by key selects the collection."""
        tree = _make_tree()
        result = _filter_collections(tree, ["SOLO"])
        assert "SOLO" in result

    # ---- Contract 2: exact match only ----

    @pytest.mark.unit
    def test_contract_case_sensitive(self):
        """Contract-2: matching is case-sensitive."""
        tree = _make_tree()
        assert _filter_collections(tree, ["standalone"]) == {}
        assert _filter_collections(tree, ["solo"]) == {}

    @pytest.mark.unit
    def test_contract_no_substring_match(self):
        """Contract-2: substrings do not match."""
        tree = _make_tree()
        assert _filter_collections(tree, ["Stand"]) == {}
        assert _filter_collections(tree, ["SOL"]) == {}

    # ---- Contract 3: descendants included ----

    @pytest.mark.unit
    def test_contract_descendants_of_name_match(self):
        """Contract-3: descendants included when parent matched by name."""
        tree = _make_tree()
        result = _filter_collections(tree, ["TopLevel"])
        assert set(result.keys()) == {"TOP", "MID", "LEAF"}

    @pytest.mark.unit
    def test_contract_descendants_of_key_match(self):
        """Contract-3: descendants included when parent matched by key."""
        tree = _make_tree()
        result = _filter_collections(tree, ["TOP"])
        assert set(result.keys()) == {"TOP", "MID", "LEAF"}

    # ---- Contract 4: deduplication ----

    @pytest.mark.unit
    def test_contract_dedup_by_key(self):
        """Contract-4: same collection matched twice produces single entry."""
        tree = _make_tree()
        result = _filter_collections(tree, ["SOLO", "Standalone"])
        assert len(result) == 1
        assert "SOLO" in result

    # ---- Contract 5: empty filter ----

    @pytest.mark.unit
    def test_contract_empty_filter_returns_empty(self):
        """Contract-5: an empty filter list returns an empty dict."""
        tree = _make_tree()
        result = _filter_collections(tree, [])
        assert result == {}

    # ---- Contract 6: unrecognized tokens ----

    @pytest.mark.unit
    def test_contract_unknown_tokens_ignored(self):
        """Contract-6: unknown tokens are silently ignored."""
        tree = _make_tree()
        result = _filter_collections(tree, ["NoSuchThing"])
        assert result == {}

    @pytest.mark.unit
    def test_contract_mix_valid_and_unknown(self):
        """Contract-6: valid tokens match even alongside unknowns."""
        tree = _make_tree()
        result = _filter_collections(tree, ["BOGUS", "Standalone", "NOPE"])
        assert set(result.keys()) == {"SOLO"}
