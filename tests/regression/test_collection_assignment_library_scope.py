"""Tests for Update collection assignment to match on (library_id, item_id)."""

from __future__ import annotations

import json
import sqlite3

import pytest

from zsum.config import Config
from zsum.indexer import build_index


class TestCollectionAssignmentLibraryScope:
    """
    Tests for Update collection assignment to match on (library_id, item_id).
    Covers: collection assignment no longer relies on itemID alone
    when library identity is available; two items sharing an itemID in different libraries
    do not collide during membership assignment.
    """

    @pytest.mark.integration
    def test_duplicate_item_ids_in_different_libraries_do_not_collide(self, tmp_path):
        """
        Verifies: collection assignment uses a library-safe identity
        when duplicate itemIDs exist.
        Covers: Two items sharing an itemID in different
        libraries do not collide during membership assignment.
        Passes when: each library-specific item is assigned only to
        its intended collection membership.
        """
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
