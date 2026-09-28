"""Tests for the indexer module."""

from __future__ import annotations

import json
import sqlite3

from zsum.cache import load_membership, save_membership
from zsum.config import Config
from zsum.indexer import build_index


class TestBuildIndex:
    """Test the full index building pipeline."""

    def test_loads_all_items(self, sample_bbt_json, sample_zotero_sqlite, tmp_path):
        config = Config(
            bbt_json=sample_bbt_json,
            zotero_sqlite=sample_zotero_sqlite,
            cache_dir=tmp_path / "cache",
        )
        index = build_index(config)
        assert len(index.items) == 3

    def test_item_metadata(self, sample_bbt_json, sample_zotero_sqlite, tmp_path):
        config = Config(
            bbt_json=sample_bbt_json,
            zotero_sqlite=sample_zotero_sqlite,
            cache_dir=tmp_path / "cache",
        )
        index = build_index(config)
        item = index.items["smith2017PhaseField"]

        assert item.citekey == "smith2017PhaseField"
        assert item.title == "Phase Field Modeling of Crack Propagation"
        assert item.year == 2017
        assert item.authors == ["Smith, John", "Doe, Alice"]
        assert item.doi == "10.1016/j.jmps.2017.01.001"
        assert "phase-field" in item.tags

    def test_pdf_resolution(self, sample_bbt_json, sample_zotero_sqlite, tmp_path):
        config = Config(
            bbt_json=sample_bbt_json,
            zotero_sqlite=sample_zotero_sqlite,
            cache_dir=tmp_path / "cache",
        )
        index = build_index(config)

        assert index.items["smith2017PhaseField"].has_pdf
        assert index.items["zhao2020CrackProp"].has_pdf
        assert not index.items["jones2019NoPdf"].has_pdf

    def test_collections_loaded(self, sample_bbt_json, sample_zotero_sqlite, tmp_path):
        config = Config(
            bbt_json=sample_bbt_json,
            zotero_sqlite=sample_zotero_sqlite,
            cache_dir=tmp_path / "cache",
        )
        index = build_index(config)

        assert "COL001" in index.collections
        assert "COL002" in index.collections
        assert index.collections["COL001"].name == "Phase Field Modeling"
        assert index.collections["COL002"].name == "Bismuth-Copper"

    def test_collection_hierarchy(self, sample_bbt_json, sample_zotero_sqlite, tmp_path):
        config = Config(
            bbt_json=sample_bbt_json,
            zotero_sqlite=sample_zotero_sqlite,
            cache_dir=tmp_path / "cache",
        )
        index = build_index(config)

        parent = index.collections["COL001"]
        child = index.collections["COL002"]

        assert parent.parent_key is None
        assert child.parent_key == "COL001"
        assert "COL002" in parent.child_keys
        assert child.path == "Phase Field Modeling / Bismuth-Copper"

    def test_collection_membership(self, sample_bbt_json, sample_zotero_sqlite, tmp_path):
        config = Config(
            bbt_json=sample_bbt_json,
            zotero_sqlite=sample_zotero_sqlite,
            cache_dir=tmp_path / "cache",
        )
        index = build_index(config)

        parent_items = index.collections["COL001"].item_citekeys
        child_items = index.collections["COL002"].item_citekeys

        assert "smith2017PhaseField" in parent_items
        assert "zhao2020CrackProp" in parent_items
        assert "jones2019NoPdf" in parent_items
        assert "smith2017PhaseField" in child_items

    def test_stats(self, sample_bbt_json, sample_zotero_sqlite, tmp_path):
        config = Config(
            bbt_json=sample_bbt_json,
            zotero_sqlite=sample_zotero_sqlite,
            cache_dir=tmp_path / "cache",
        )
        index = build_index(config)
        stats = index.stats

        assert stats["total_items"] == 3
        assert stats["with_pdf"] == 2
        assert stats["missing_pdf"] == 1
        assert stats["total_collections"] == 2

    def test_filter_collections(self, sample_bbt_json, sample_zotero_sqlite, tmp_path):
        config = Config(
            bbt_json=sample_bbt_json,
            zotero_sqlite=sample_zotero_sqlite,
            cache_dir=tmp_path / "cache",
            collections=["Phase Field Modeling"],
        )
        index = build_index(config)

        # Should include parent and its child
        assert "COL001" in index.collections
        assert "COL002" in index.collections

    def test_filter_collections_by_key(self, sample_bbt_json, sample_zotero_sqlite, tmp_path):
        """Filtering by collection key should work identically to name."""
        config = Config(
            bbt_json=sample_bbt_json,
            zotero_sqlite=sample_zotero_sqlite,
            cache_dir=tmp_path / "cache",
            collections=["COL001"],
        )
        index = build_index(config)

        # COL001 matched by key, COL002 included as its child
        assert "COL001" in index.collections
        assert "COL002" in index.collections

    def test_abstract_present(self, sample_bbt_json, sample_zotero_sqlite, tmp_path):
        config = Config(
            bbt_json=sample_bbt_json,
            zotero_sqlite=sample_zotero_sqlite,
            cache_dir=tmp_path / "cache",
        )
        index = build_index(config)
        item = index.items["jones2019NoPdf"]
        assert item.abstract == "This paper has no attachment."

    def test_library_id_loaded_when_present(self, sample_bbt_json, sample_zotero_sqlite, tmp_path):
        raw = json.loads(sample_bbt_json.read_text())
        raw["items"][0]["libraryID"] = 42
        sample_bbt_json.write_text(json.dumps(raw))

        config = Config(
            bbt_json=sample_bbt_json,
            zotero_sqlite=sample_zotero_sqlite,
            cache_dir=tmp_path / "cache",
        )
        index = build_index(config)

        assert index.items["smith2017PhaseField"].library_id == 42
        assert index.items["zhao2020CrackProp"].library_id is None


class TestDeduplication:
    """Test that duplicate collectionItems rows do not produce duplicate citekeys."""

    def test_no_duplicate_citekeys(self, sample_bbt_json, tmp_path):
        """Duplicate collectionItems rows should not produce duplicate citekeys."""
        db_path = tmp_path / "zotero_dup.sqlite"
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE collections (
                collectionID INTEGER PRIMARY KEY,
                collectionName TEXT,
                parentCollectionID INTEGER,
                key TEXT
            );
            CREATE TABLE collectionItems (
                collectionID INTEGER, itemID INTEGER
            );
            INSERT INTO collections
                VALUES (1, 'Test Col', NULL, 'COL001');
            INSERT INTO collectionItems VALUES (1, 101);
            INSERT INTO collectionItems VALUES (1, 101);
            INSERT INTO collectionItems VALUES (1, 102);
        """)
        conn.commit()
        conn.close()

        config = Config(
            bbt_json=sample_bbt_json,
            zotero_sqlite=db_path,
            cache_dir=tmp_path / "cache",
        )
        index = build_index(config)
        citekeys = index.collections["COL001"].item_citekeys
        assert len(citekeys) == len(set(citekeys)), f"Duplicate citekeys found: {citekeys}"


class TestMultiLibraryMembership:
    """Test library-aware collection assignment when itemIDs collide across libraries."""

    def test_duplicate_item_ids_in_different_libraries_do_not_collide(self, tmp_path):
        bbt_path = tmp_path / "multi_library.json"
        bbt_path.write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "key": "AAAA1111",
                            "itemKey": "AAAA1111",
                            "itemID": 101,
                            "libraryID": 1,
                            "itemType": "journalArticle",
                            "citationKey": "smith2017Local",
                            "title": "Local Library Paper",
                            "date": "2017",
                            "publicationTitle": "JMPS",
                            "DOI": "",
                            "abstractNote": "",
                            "url": "",
                            "creators": [],
                            "tags": [],
                            "attachments": [],
                        },
                        {
                            "key": "BBBB2222",
                            "itemKey": "BBBB2222",
                            "itemID": 101,
                            "libraryID": 2,
                            "itemType": "journalArticle",
                            "citationKey": "smith2017Group",
                            "title": "Group Library Paper",
                            "date": "2017",
                            "publicationTitle": "JMPS",
                            "DOI": "",
                            "abstractNote": "",
                            "url": "",
                            "creators": [],
                            "tags": [],
                            "attachments": [],
                        },
                    ]
                }
            )
        )

        db_path = tmp_path / "multi_library.sqlite"
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
                itemID INTEGER,
                libraryID INTEGER
            );
            INSERT INTO collections VALUES (1, 'Local Library', NULL, 'COL001');
            INSERT INTO collections VALUES (2, 'Group Library', NULL, 'COL002');
            INSERT INTO collectionItems VALUES (1, 101, 1);
            INSERT INTO collectionItems VALUES (2, 101, 2);
        """)
        conn.commit()
        conn.close()

        config = Config(
            bbt_json=bbt_path,
            zotero_sqlite=db_path,
            cache_dir=tmp_path / "cache",
        )
        index = build_index(config)

        assert index.collections["COL001"].item_citekeys == ["smith2017Local"]
        assert index.collections["COL002"].item_citekeys == ["smith2017Group"]

    def test_collections_table_fallback_resolves_library_context(self, tmp_path):
        """When collectionItems lacks libraryID, library context is recovered
        from the collections table (the real Zotero schema path)."""
        bbt_path = tmp_path / "real_schema.json"
        bbt_path.write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "key": "AAAA1111",
                            "itemKey": "AAAA1111",
                            "itemID": 101,
                            "libraryID": 1,
                            "itemType": "journalArticle",
                            "citationKey": "smith2017Local",
                            "title": "Local Library Paper",
                            "date": "2017",
                            "publicationTitle": "JMPS",
                            "DOI": "",
                            "abstractNote": "",
                            "url": "",
                            "creators": [],
                            "tags": [],
                            "attachments": [],
                        },
                        {
                            "key": "BBBB2222",
                            "itemKey": "BBBB2222",
                            "itemID": 101,
                            "libraryID": 2,
                            "itemType": "journalArticle",
                            "citationKey": "smith2017Group",
                            "title": "Group Library Paper",
                            "date": "2017",
                            "publicationTitle": "JMPS",
                            "DOI": "",
                            "abstractNote": "",
                            "url": "",
                            "creators": [],
                            "tags": [],
                            "attachments": [],
                        },
                    ]
                }
            )
        )

        db_path = tmp_path / "real_schema.sqlite"
        conn = sqlite3.connect(db_path)
        # Real Zotero schema: collectionItems has NO libraryID column,
        # but collections table carries libraryID for each collection.
        conn.executescript("""
            CREATE TABLE collections (
                collectionID INTEGER PRIMARY KEY,
                collectionName TEXT,
                parentCollectionID INTEGER,
                libraryID INTEGER,
                key TEXT
            );
            CREATE TABLE collectionItems (
                collectionID INTEGER,
                itemID INTEGER
            );
            INSERT INTO collections VALUES (1, 'Local Coll', NULL, 1, 'COL001');
            INSERT INTO collections VALUES (2, 'Group Coll', NULL, 2, 'COL002');
            INSERT INTO collectionItems VALUES (1, 101);
            INSERT INTO collectionItems VALUES (2, 101);
        """)
        conn.commit()
        conn.close()

        config = Config(
            bbt_json=bbt_path,
            zotero_sqlite=db_path,
            cache_dir=tmp_path / "cache",
        )
        index = build_index(config)

        assert index.collections["COL001"].item_citekeys == ["smith2017Local"]
        assert index.collections["COL002"].item_citekeys == ["smith2017Group"]


class TestMembership:
    """Test membership snapshot save/load for change detection."""

    def test_save_and_load(self, sample_bbt_json, sample_zotero_sqlite, tmp_path):
        config = Config(
            bbt_json=sample_bbt_json,
            zotero_sqlite=sample_zotero_sqlite,
            cache_dir=tmp_path / "cache",
        )
        index = build_index(config)
        cache_dir = tmp_path / "cache"

        save_membership(index, cache_dir)

        loaded = load_membership(cache_dir)
        assert "COL001" in loaded
        assert "smith2017PhaseField" in loaded["COL001"]

    def test_load_missing_returns_empty(self, tmp_path):
        loaded = load_membership(tmp_path / "nonexistent")
        assert loaded == {}

    def test_membership_is_sorted(self, sample_bbt_json, sample_zotero_sqlite, tmp_path):
        config = Config(
            bbt_json=sample_bbt_json,
            zotero_sqlite=sample_zotero_sqlite,
            cache_dir=tmp_path / "cache",
        )
        index = build_index(config)
        cache_dir = tmp_path / "cache"

        save_membership(index, cache_dir)

        loaded = load_membership(cache_dir)
        for citekeys in loaded.values():
            assert citekeys == sorted(citekeys)
