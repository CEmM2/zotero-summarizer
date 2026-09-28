"""Tests for collection filter matches by name OR key.

Validates that ``_filter_collections`` matches filter tokens against
both ``Collection.key`` and ``Collection.name``, with descendants
included automatically.

Covers:
  AC-1: Name-based matching still works
  AC-2: Key-based matching works
  AC-3: Unmatched tokens are silently ignored (no error)
  AC-4: Descendants of matched collections are included
"""

from __future__ import annotations

import pytest

from zsum.indexer import _filter_collections
from zsum.models import Collection


def _make_tree() -> dict[str, Collection]:
    """Build a small collection tree for testing.

    Structure::

        ROOT (key="K_ROOT", name="Root")
        +-- CHILD_A (key="K_A", name="Alpha")
        |   +-- GRANDCHILD (key="K_GA", name="Gamma")
        +-- CHILD_B (key="K_B", name="Beta")
    """
    return {
        "K_ROOT": Collection(
            key="K_ROOT",
            name="Root",
            child_keys=["K_A", "K_B"],
        ),
        "K_A": Collection(
            key="K_A",
            name="Alpha",
            parent_key="K_ROOT",
            child_keys=["K_GA"],
        ),
        "K_GA": Collection(
            key="K_GA",
            name="Gamma",
            parent_key="K_A",
        ),
        "K_B": Collection(
            key="K_B",
            name="Beta",
            parent_key="K_ROOT",
        ),
    }


class TestFilterCollections:
    """Name match, key match, no-match, and descendant selection."""

    @pytest.mark.unit
    def test_name_match(self):
        """AC-1: Filtering by collection name returns that collection."""
        tree = _make_tree()
        result = _filter_collections(tree, ["Beta"])
        assert "K_B" in result
        assert result["K_B"].name == "Beta"

    @pytest.mark.unit
    def test_key_match(self):
        """AC-2: Filtering by collection key returns that collection."""
        tree = _make_tree()
        result = _filter_collections(tree, ["K_B"])
        assert "K_B" in result
        assert result["K_B"].name == "Beta"

    @pytest.mark.unit
    def test_no_match_returns_empty(self):
        """AC-3: Unmatched tokens produce an empty result."""
        tree = _make_tree()
        result = _filter_collections(tree, ["NoSuchName", "NO_KEY"])
        assert result == {}

    @pytest.mark.unit
    def test_descendants_included_via_name(self):
        """AC-4: Descendants are included when parent matched by name."""
        tree = _make_tree()
        result = _filter_collections(tree, ["Alpha"])
        assert "K_A" in result
        assert "K_GA" in result, "Grandchild must be included"

    @pytest.mark.unit
    def test_descendants_included_via_key(self):
        """AC-4: Descendants are included when parent matched by key."""
        tree = _make_tree()
        result = _filter_collections(tree, ["K_A"])
        assert "K_A" in result
        assert "K_GA" in result, "Grandchild must be included"

    @pytest.mark.unit
    def test_root_by_name_includes_full_subtree(self):
        """AC-4: Matching root by name includes the entire tree."""
        tree = _make_tree()
        result = _filter_collections(tree, ["Root"])
        assert set(result.keys()) == {"K_ROOT", "K_A", "K_GA", "K_B"}

    @pytest.mark.unit
    def test_root_by_key_includes_full_subtree(self):
        """AC-4: Matching root by key includes the entire tree."""
        tree = _make_tree()
        result = _filter_collections(tree, ["K_ROOT"])
        assert set(result.keys()) == {"K_ROOT", "K_A", "K_GA", "K_B"}
