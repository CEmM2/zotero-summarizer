"""Tests for Log warning for item_id=None items excluded from collections.

Covers: Items with item_id=None trigger a logger.warning that includes the citekey.
Implementation target: src/zsum/indexer.py — _assign_items_to_collections
"""

from __future__ import annotations

import logging
import sqlite3

import pytest

from zsum.indexer import _assign_items_to_collections
from zsum.models import Collection, Item


def _make_sqlite(tmp_path, items_rows: list[tuple[int, int]]):
    """Create a minimal SQLite with collections + collectionItems tables."""
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


class TestItemIdNoneWarning:
    """
    Tests for Log warning for item_id=None items excluded from collections.
    Covers: AC-1, AC-2
    """

    @pytest.mark.unit
    def test_item_id_none_logs_warning_with_citekey(self, tmp_path, caplog):
        """
        Verifies: items with item_id=None trigger a logger.warning that includes the citekey.
        Covers: AC-1 (warning logged), AC-2 (citekey in message).
        Passes when: caplog captures a WARNING record whose message contains the citekey.
        """
        db_path, col_id_to_key = _make_sqlite(tmp_path, [(1, 99)])
        collections = _make_collection()
        items = {"smith2024": _make_item("smith2024", item_id=None)}

        with caplog.at_level(logging.WARNING, logger="zsum.indexer"):
            _assign_items_to_collections(collections, items, db_path, col_id_to_key)

        # AC-1: a WARNING record was emitted
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) >= 1, f"Expected at least one WARNING log, got: {caplog.text}"

        # AC-2: the citekey appears in at least one warning message
        assert any("smith2024" in r.getMessage() for r in warning_records), (
            "Expected 'smith2024' in warning message, got: "
            f"{[r.getMessage() for r in warning_records]}"
        )

    @pytest.mark.unit
    def test_item_id_none_warning_emitted_once_per_item(self, tmp_path, caplog):
        """
        Verifies: Each item with item_id=None emits exactly one warning.
        Passes when: Two None-id items each produce exactly one warning
        with their respective citekeys.
        """
        db_path, col_id_to_key = _make_sqlite(tmp_path, [])
        collections = _make_collection()
        items = {
            "alpha2020": _make_item("alpha2020", item_id=None),
            "beta2021": _make_item("beta2021", item_id=None),
        }

        with caplog.at_level(logging.WARNING, logger="zsum.indexer"):
            _assign_items_to_collections(collections, items, db_path, col_id_to_key)

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        messages = [r.getMessage() for r in warning_records]

        assert any("alpha2020" in m for m in messages), (
            f"Expected warning for 'alpha2020', got: {messages}"
        )
        assert any("beta2021" in m for m in messages), (
            f"Expected warning for 'beta2021', got: {messages}"
        )

    @pytest.mark.unit
    def test_item_with_valid_item_id_does_not_log_warning(self, tmp_path, caplog):
        """
        Verifies: Items with a valid item_id (not None) do not produce warnings.
        Passes when: No WARNING is emitted for an item with item_id=42.
        """
        db_path, col_id_to_key = _make_sqlite(tmp_path, [(1, 42)])
        collections = _make_collection()
        items = {"jones2019": _make_item("jones2019", item_id=42)}

        with caplog.at_level(logging.WARNING, logger="zsum.indexer"):
            _assign_items_to_collections(collections, items, db_path, col_id_to_key)

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) == 0, (
            f"Unexpected warnings for valid item_id: {[r.getMessage() for r in warning_records]}"
        )
