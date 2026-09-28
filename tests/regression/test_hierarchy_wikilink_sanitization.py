"""Tests for sanitized wikilinks in collection hierarchy."""

from __future__ import annotations

import pytest

from zsum.config import Config
from zsum.models import Collection, Item, LibraryIndex
from zsum.publisher import publish_vault


class TestHierarchyWikilinkSanitization:
    @pytest.mark.unit
    def test_wikilink_sanitized_colon_in_name(self, tmp_path):
        # Collection "Methods: 2024" (parent) with child "Sub"
        items = {
            "paper1": Item(
                citekey="paper1",
                zotero_key="A",
                item_id=1,
                title="Test Paper",
                authors=["Author"],
                year=2020,
            ),
        }
        collections = {
            "PAR": Collection(
                key="PAR",
                name="Methods: 2024",
                parent_key=None,
                path="Methods: 2024",
                item_citekeys=["paper1"],
                child_keys=["CHI"],
            ),
            "CHI": Collection(
                key="CHI",
                name="Sub",
                parent_key="PAR",
                path="Methods: 2024 / Sub",
                item_citekeys=["paper1"],
                child_keys=[],
            ),
        }
        index = LibraryIndex(items=items, collections=collections)
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(index, config)

        col_dir = vault / "Collections"

        # Child note should use sanitized parent name in wikilink
        child_content = (col_dir / "Sub.md").read_text()
        assert "[[Methods_ 2024]]" in child_content
        assert "[[Methods: 2024]]" not in child_content

        # Parent note's subcollections wikilink should be unchanged (child name is normal)
        parent_content = (col_dir / "Methods_ 2024.md").read_text()
        assert "[[Sub]]" in parent_content

        # Library Index should use sanitized parent name
        index_content = (vault / "Library Index.md").read_text()
        assert "[[Methods_ 2024]]" in index_content
        assert "[[Methods: 2024]]" not in index_content

    @pytest.mark.unit
    def test_wikilink_sanitized_slash_in_name(self, tmp_path):
        # Collection "A/B" as child of "Root"
        items = {
            "paper1": Item(
                citekey="paper1",
                zotero_key="A",
                item_id=1,
                title="Test Paper",
                authors=["Author"],
                year=2020,
            ),
        }
        collections = {
            "ROOT": Collection(
                key="ROOT",
                name="Root",
                parent_key=None,
                path="Root",
                item_citekeys=["paper1"],
                child_keys=["SLASH"],
            ),
            "SLASH": Collection(
                key="SLASH",
                name="A/B",
                parent_key="ROOT",
                path="Root / A/B",
                item_citekeys=["paper1"],
                child_keys=[],
            ),
        }
        index = LibraryIndex(items=items, collections=collections)
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(index, config)

        col_dir = vault / "Collections"

        # Parent "Root" note should use sanitized child name in subcollections link
        parent_content = (col_dir / "Root.md").read_text()
        assert "[[A_B]]" in parent_content
        assert "[[A/B]]" not in parent_content

        # Child "A/B" note should use unsanitized parent name (Root is normal)
        child_content = (col_dir / "A_B.md").read_text()
        assert "[[Root]]" in child_content

        # Library Index should use sanitized child name
        index_content = (vault / "Library Index.md").read_text()
        assert "[[A_B]]" in index_content
        assert "[[A/B]]" not in index_content

    @pytest.mark.unit
    def test_wikilink_normal_name_unchanged(self, tmp_path):
        # Collections "Alpha" and "Beta" (no special chars)
        items = {
            "paper1": Item(
                citekey="paper1",
                zotero_key="A",
                item_id=1,
                title="Test Paper",
                authors=["Author"],
                year=2020,
            ),
        }
        collections = {
            "ALPHA": Collection(
                key="ALPHA",
                name="Alpha",
                parent_key=None,
                path="Alpha",
                item_citekeys=["paper1"],
                child_keys=["BETA"],
            ),
            "BETA": Collection(
                key="BETA",
                name="Beta",
                parent_key="ALPHA",
                path="Alpha / Beta",
                item_citekeys=["paper1"],
                child_keys=[],
            ),
        }
        index = LibraryIndex(items=items, collections=collections)
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(index, config)

        col_dir = vault / "Collections"

        # Files should be named as-is
        assert (col_dir / "Alpha.md").exists()
        assert (col_dir / "Beta.md").exists()

        # Parent "Alpha" note should have unchanged subcollections link
        alpha_content = (col_dir / "Alpha.md").read_text()
        assert "[[Beta]]" in alpha_content

        # Child "Beta" note should have unchanged parent link
        beta_content = (col_dir / "Beta.md").read_text()
        assert "[[Alpha]]" in beta_content

        # Library Index should use unchanged names
        index_content = (vault / "Library Index.md").read_text()
        assert "[[Alpha]]" in index_content
        assert "[[Beta]]" in index_content
