"""Tests for Add regression coverage for mixed-library and legacy inputs."""

from __future__ import annotations

import json
import sqlite3

import pytest

from zsum.config import Config
from zsum.indexer import build_index


class TestMixedLibraryRegression:
    """
    Tests for Add regression coverage for mixed-library and legacy inputs.
    Covers: explicit regression coverage for multi-library duplicate
    itemIDs and the legacy single-library path.
    """

    @pytest.mark.regression
    def test_multi_library_duplicate_item_ids_remain_disambiguated(self, tmp_path):
        """
        Verifies: the mixed-library duplicate-itemID scenario is
        locked in as a regression case.
        Covers: There is an explicit regression test
        for multi-library duplicate itemIDs.
        Passes when: duplicate itemIDs across different libraries
        continue to resolve to distinct memberships.
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

    @pytest.mark.regression
    def test_legacy_single_library_membership_path_is_unchanged(
        self, sample_bbt_json, sample_zotero_sqlite, tmp_path
    ):
        """
        Verifies: the original single-library fixture still produces
        the same memberships.
        Covers: There is an explicit regression test
        for the legacy single-library path.
        Passes when: collection memberships are identical to the
        pre-libraryID baseline fixture.
        """
        config = Config(
            bbt_json=sample_bbt_json,
            zotero_sqlite=sample_zotero_sqlite,
            cache_dir=tmp_path / "cache",
        )
        index = build_index(config)

        assert index.collections["COL001"].item_citekeys == [
            "jones2019NoPdf",
            "smith2017PhaseField",
            "zhao2020CrackProp",
        ]
        assert index.collections["COL002"].item_citekeys == ["smith2017PhaseField"]
