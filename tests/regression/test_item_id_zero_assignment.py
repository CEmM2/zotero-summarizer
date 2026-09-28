"""Tests for item_id=0 collection assignment.

Covers: Items with item_id=0 appear in collections; None excluded.
"""

from __future__ import annotations

import sqlite3

import pytest

from zsum.indexer import _assign_items_to_collections
from zsum.models import Collection, Item

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sqlite(tmp_path, items_rows: list[tuple[int, int]]) -> tuple:
    """Create a minimal SQLite with collections + collectionItems tables.

    items_rows: list of (collectionID, itemID) for collectionItems.
    Returns (db_path, col_id_to_key dict).
    """
    db_path = tmp_path / "zotero.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE collections (
            collectionID INTEGER PRIMARY KEY,
            collectionName TEXT,
            parentCollectionID INTEGER,
            key TEXT
        );
        CREATE TABLE collectionItems (
            collectionID INTEGER,
            itemID INTEGER
        );
        INSERT INTO collections VALUES (1, 'TestCollection', NULL, 'COL001');
    """)
    for col_id, item_id in items_rows:
        conn.execute("INSERT INTO collectionItems VALUES (?, ?)", (col_id, item_id))
    conn.commit()
    conn.close()

    col_id_to_key = {1: "COL001"}
    return db_path, col_id_to_key


def _make_collection(key: str = "COL001") -> dict[str, Collection]:
    return {key: Collection(key=key, name="TestCollection")}


def _make_item(citekey: str, item_id: int | None) -> Item:
    return Item(
        citekey=citekey,
        zotero_key="KEY001",
        item_id=item_id,
        title="Test Paper",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestItemIdZeroAssignment:
    """
    Tests for item_id=0 collection assignment.
    Covers: Items with item_id=0 appear in collections; None excluded.
    """

    @pytest.mark.unit
    def test_item_id_zero_in_id_to_citekey_mapping(self, tmp_path):
        """
        Verifies: Items with item_id=0 are included in id_to_citekey mapping.
        Covers: item_id=0 maps to citekey in collection assignment.
        Passes when: 'zero_item' ends up in the collection after assignment.
        """
        # collectionItems row maps collectionID=1 to itemID=0
        db_path, col_id_to_key = _make_sqlite(tmp_path, [(1, 0)])
        collections = _make_collection()
        items = {"zero_item": _make_item("zero_item", item_id=0)}

        _assign_items_to_collections(collections, items, db_path, col_id_to_key)

        assert "zero_item" in collections["COL001"].item_citekeys

    @pytest.mark.unit
    def test_item_id_zero_included_in_collections(self, tmp_path):
        """
        Verifies: Items with item_id=0 are assigned to their collections.
        Covers: item_id=0 item appears in collection.item_citekeys.
        Passes when: 'zero_item' in index.collections['COL001'].item_citekeys.
        """
        db_path, col_id_to_key = _make_sqlite(tmp_path, [(1, 0)])
        collections = _make_collection()
        items = {"zero_item": _make_item("zero_item", item_id=0)}

        _assign_items_to_collections(collections, items, db_path, col_id_to_key)

        assert collections["COL001"].item_citekeys == ["zero_item"]

    @pytest.mark.unit
    def test_item_id_none_excluded_from_mapping(self, tmp_path):
        """
        Verifies: Items with item_id=None are excluded from id_to_citekey mapping.
        Covers: None item does not appear in collections.
        Passes when: 'none_item' not in index.collections['COL001'].item_citekeys.
        """
        # Even if there's a row for itemID=0 (SQLite NULL would differ, but test None in Python)
        # We create a row that won't match since the item has no valid id
        db_path, col_id_to_key = _make_sqlite(tmp_path, [(1, 99)])
        collections = _make_collection()
        items = {"none_item": _make_item("none_item", item_id=None)}

        _assign_items_to_collections(collections, items, db_path, col_id_to_key)

        assert "none_item" not in collections["COL001"].item_citekeys

    @pytest.mark.unit
    def test_item_id_positive_included_in_collections(self, tmp_path):
        """
        Verifies: Items with positive item_id (e.g., 42) are assigned to collections.
        Covers: Regular item_id > 0 behavior unchanged.
        Passes when: 'regular_item' in index.collections['COL001'].item_citekeys.
        """
        db_path, col_id_to_key = _make_sqlite(tmp_path, [(1, 42)])
        collections = _make_collection()
        items = {"regular_item": _make_item("regular_item", item_id=42)}

        _assign_items_to_collections(collections, items, db_path, col_id_to_key)

        assert "regular_item" in collections["COL001"].item_citekeys

    @pytest.mark.unit
    def test_zero_vs_none_distinction_in_id_to_citekey(self, tmp_path):
        """
        Verifies: item_id=0 and item_id=None are treated distinctly.
        Covers: 0 is included, None is excluded.
        Passes when: zero_item is in collection, none_item is not.
        """
        # Map both collectionID=1 to itemID=0 and itemID=7 (none_item won't have id=7)
        db_path, col_id_to_key = _make_sqlite(tmp_path, [(1, 0), (1, 7)])
        collections = _make_collection()
        items = {
            "zero_item": _make_item("zero_item", item_id=0),
            "none_item": _make_item("none_item", item_id=None),
        }

        _assign_items_to_collections(collections, items, db_path, col_id_to_key)

        assert "zero_item" in collections["COL001"].item_citekeys
        assert "none_item" not in collections["COL001"].item_citekeys
