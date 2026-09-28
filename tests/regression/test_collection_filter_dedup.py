"""Tests for mixed name/key filter list and deduplication.

Validates that ``_filter_collections`` correctly handles filter lists
containing both names and keys, and that the result is deduplicated
when the same collection is referenced by both its key and name.

Covers:
  AC-1: Mixed name+key filter list selects the union of matches
  AC-2: Same collection matched by both key and name is not duplicated
"""

from __future__ import annotations

import pytest

from zsum.indexer import _filter_collections
from zsum.models import Collection


def _make_tree() -> dict[str, Collection]:
    """Build a collection tree for dedup testing.

    Structure::

        COL1 (key="COL1", name="Physics")
        +-- COL1A (key="COL1A", name="Quantum")
        COL2 (key="COL2", name="Chemistry")
    """
    return {
        "COL1": Collection(
            key="COL1",
            name="Physics",
            child_keys=["COL1A"],
        ),
        "COL1A": Collection(
            key="COL1A",
            name="Quantum",
            parent_key="COL1",
        ),
        "COL2": Collection(
            key="COL2",
            name="Chemistry",
        ),
    }


class TestMixedFilterAndDedup:
    """Mixed name/key filter and deduplication."""

    @pytest.mark.unit
    def test_mixed_name_and_key(self):
        """AC-1: Filter with one name and one key selects both."""
        tree = _make_tree()
        result = _filter_collections(tree, ["Physics", "COL2"])
        # Physics (COL1) matched by name + its child COL1A
        assert "COL1" in result
        assert "COL1A" in result
        # Chemistry (COL2) matched by key
        assert "COL2" in result

    @pytest.mark.unit
    def test_dedup_same_collection_by_name_and_key(self):
        """AC-2: Same collection matched by name and key appears once."""
        tree = _make_tree()
        # "COL2" matches by key, "Chemistry" matches by name -> same collection
        result = _filter_collections(tree, ["COL2", "Chemistry"])
        assert "COL2" in result
        # The dict is keyed by collection key — duplicates are impossible
        # at the dict level, but verify the count is exactly 1 (not 3).
        assert len(result) == 1

    @pytest.mark.unit
    def test_dedup_parent_with_descendants(self):
        """AC-2: Matching parent by both name and key does not duplicate children."""
        tree = _make_tree()
        result = _filter_collections(tree, ["COL1", "Physics"])
        # Parent + child = 2, not 4
        assert set(result.keys()) == {"COL1", "COL1A"}

    @pytest.mark.unit
    def test_all_by_mixed_tokens(self):
        """AC-1: All collections selected via a mix of keys and names."""
        tree = _make_tree()
        result = _filter_collections(tree, ["COL1", "Chemistry"])
        assert set(result.keys()) == {"COL1", "COL1A", "COL2"}

    @pytest.mark.unit
    def test_key_equals_different_collections_name(self):
        """Edge case: a key string that also happens to be another
        collection's name should match both."""
        tree = {
            "Alpha": Collection(key="Alpha", name="First"),
            "Second": Collection(key="Second", name="Alpha"),
        }
        result = _filter_collections(tree, ["Alpha"])
        # "Alpha" matches key="Alpha" AND name="Alpha" (different collections)
        assert "Alpha" in result
        assert "Second" in result
