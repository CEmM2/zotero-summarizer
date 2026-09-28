"""Tests for Eliminate get_safe_name() fallback.

Covers:
- AC-1: get_safe_name either removed or raises on unregistered names
- AC-2: All existing tests pass
- AC-3: Collision-prone names still get numbered suffixes

Existing coverage (tests/test_publisher.py::TestFilenameTracker):
- test_filename_collision_auto_numbers: collision detection (COVERED)
- test_resolve_idempotent: resolve() idempotency (COVERED)
- test_get_safe_name_after_resolve: cached result after resolve (COVERED)
- test_collision_in_publish_vault: integration collision test (COVERED)
"""

import pytest

from zsum.config import Config
from zsum.models import Collection, Item, LibraryIndex
from zsum.publisher import _FilenameTracker, publish_vault


class TestSafeNameFallback:
    """Tests for Eliminate get_safe_name() fallback."""

    @pytest.mark.unit
    def test_unregistered_name_raises_after_refactor(self):
        """
        Verifies: get_safe_name raises KeyError for names not registered via resolve().
        Covers: AC-1 (get_safe_name raises on unregistered names)
        Passes when: tracker.get_safe_name("never_registered") raises KeyError.
        """
        tracker = _FilenameTracker()
        with pytest.raises(KeyError):
            tracker.get_safe_name("never_registered")

    @pytest.mark.unit
    def test_collection_notes_use_resolve_path(self, tmp_path):
        """
        Verifies: _write_collection_note uses resolve() for parent/child names (not fallback).
        Covers: AC-1 (no fallback path), AC-3 (collision numbering works)
        Passes when: collection notes with colliding names produce correctly numbered wikilinks.
        """
        # Two collections whose names collide after safe-filename conversion:
        # "Parent:Alpha" and "Parent|Alpha" both map to "Parent_Alpha"
        items = {
            "p1": Item(
                citekey="p1",
                zotero_key="K1",
                item_id=1,
                title="Paper One",
                authors=["Author A"],
                year=2021,
            ),
        }
        collections = {
            "col1": Collection(
                key="col1",
                name="Parent:Alpha",
                parent_key=None,
                path="Parent:Alpha",
                item_citekeys=["p1"],
                child_keys=["col2"],
            ),
            "col2": Collection(
                key="col2",
                name="Parent|Alpha",
                parent_key="col1",
                path="Parent:Alpha/Parent|Alpha",
                item_citekeys=["p1"],
                child_keys=[],
            ),
        }
        index = LibraryIndex(items=items, collections=collections)
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(index, config)

        col_dir = vault / "Collections"
        # First name gets "Parent_Alpha", second gets "Parent_Alpha_2"
        assert (col_dir / "Parent_Alpha.md").exists(), "First collection file should exist"
        assert (col_dir / "Parent_Alpha_2.md").exists(), (
            "Colliding collection file should be numbered"
        )

        # Child note should reference parent by resolved (collision-safe) name
        child_content = (col_dir / "Parent_Alpha_2.md").read_text(encoding="utf-8")
        assert "[[Parent_Alpha]]" in child_content, "Parent wikilink should use resolved name"

        # Parent note should reference child by resolved (numbered) name
        parent_content = (col_dir / "Parent_Alpha.md").read_text(encoding="utf-8")
        assert "[[Parent_Alpha_2]]" in parent_content, "Child wikilink should use numbered name"

    @pytest.mark.unit
    def test_index_tree_uses_resolve_path(self, tmp_path):
        """
        Verifies: _write_collection_tree uses resolve() for all collection names.
        Covers: AC-1 (no fallback path)
        Passes when: index MOC wikilinks use pre-registered names with collision suffixes.
        """
        # Two root collections whose names collide
        items = {
            "p1": Item(
                citekey="p1",
                zotero_key="K1",
                item_id=1,
                title="Paper One",
                authors=["Author A"],
                year=2021,
            ),
        }
        collections = {
            "root1": Collection(
                key="root1",
                name="Topic:A",
                parent_key=None,
                path="Topic:A",
                item_citekeys=["p1"],
                child_keys=[],
            ),
            "root2": Collection(
                key="root2",
                name="Topic|A",
                parent_key=None,
                path="Topic|A",
                item_citekeys=["p1"],
                child_keys=[],
            ),
        }
        index = LibraryIndex(items=items, collections=collections)
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(index, config)

        index_content = (vault / "Library Index.md").read_text(encoding="utf-8")
        # Both collections should appear in the index MOC with their resolved names
        assert "[[Topic_A]]" in index_content, "First collection should appear as Topic_A"
        assert "[[Topic_A_2]]" in index_content, (
            "Second (colliding) collection should appear as Topic_A_2"
        )
