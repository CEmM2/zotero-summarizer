"""Tests for Extend item identity model to carry library identity."""

from __future__ import annotations

import json

import pytest

from tests.helpers import make_test_item
from zsum.config import Config
from zsum.indexer import build_index


class TestLibraryIdentityModel:
    """
    Tests for Extend item identity model to carry library identity.
    Covers: Item objects can carry a library_id value without
    breaking existing call sites; BBT records with libraryID populate library_id in
    the in-memory model; BBT records without libraryID still load successfully using
    the legacy path.
    """

    @pytest.mark.unit
    def test_load_item_with_library_id_preserves_identity(
        self, sample_bbt_json, sample_zotero_sqlite, tmp_path
    ):
        """
        Verifies: BBT-backed item loading preserves library identity
        when libraryID exists.
        Covers: BBT records with libraryID populate
        library_id in the in-memory model.
        Passes when: a loaded Item exposes the expected library_id.
        """
        raw = json.loads(sample_bbt_json.read_text())
        raw["items"][0]["libraryID"] = 9
        sample_bbt_json.write_text(json.dumps(raw))

        config = Config(
            bbt_json=sample_bbt_json,
            zotero_sqlite=sample_zotero_sqlite,
            cache_dir=tmp_path / "cache",
        )
        index = build_index(config)

        assert index.items["smith2017PhaseField"].library_id == 9

    @pytest.mark.unit
    def test_load_item_without_library_id_uses_legacy_path(
        self, sample_bbt_json, sample_zotero_sqlite, tmp_path
    ):
        """
        Verifies: item loading remains backward-compatible when
        libraryID is absent.
        Covers: BBT records without libraryID still load
        successfully using the legacy path.
        Passes when: an Item loads successfully and preserves existing
        metadata without requiring library_id.
        """
        config = Config(
            bbt_json=sample_bbt_json,
            zotero_sqlite=sample_zotero_sqlite,
            cache_dir=tmp_path / "cache",
        )
        index = build_index(config)

        item = index.items["smith2017PhaseField"]
        assert item.library_id is None
        assert item.item_id == 101
        assert item.title == "Phase Field Modeling of Crack Propagation"

    @pytest.mark.unit
    def test_test_helper_remains_compatible_after_library_id_addition(self):
        """
        Verifies: shared test helpers and existing Item construction
        paths still work after adding library_id.
        Covers: Item objects can carry a library_id value
        without breaking existing call sites.
        Passes when: helper-created Items remain valid both with and
        without an explicit library_id.
        """
        default_item = make_test_item()
        library_item = make_test_item(library_id=4)

        assert default_item.library_id is None
        assert library_item.library_id == 4
