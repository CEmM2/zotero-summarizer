"""Regression tests for paper-list dash formatting."""

from __future__ import annotations

import pytest

from zsum.config import Config
from zsum.models import Collection, Item, LibraryIndex
from zsum.publisher import publish_vault


def _make_index() -> LibraryIndex:
    items = {
        "smith2017": Item(
            citekey="smith2017",
            zotero_key="AAA",
            item_id=1,
            title="Phase Field Modeling",
            authors=["Smith, John"],
            year=2017,
        ),
        "zhao2020": Item(
            citekey="zhao2020",
            zotero_key="BBB",
            item_id=2,
            title="Dynamic Crack Propagation",
            authors=["Zhao, Wei"],
            year=2020,
        ),
    }
    collections = {
        "COL1": Collection(
            key="COL1",
            name="Phase Field",
            parent_key=None,
            path="Phase Field",
            item_citekeys=["smith2017", "zhao2020"],
            child_keys=[],
        )
    }
    return LibraryIndex(items=items, collections=collections)


class TestPaperListFormatting:
    @pytest.mark.unit
    def test_paper_list_uses_em_dash(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(_make_index(), config)

        content = (vault / "Collections" / "Phase Field.md").read_text(encoding="utf-8")
        paper_list = content.split("## Papers in this Collection\n\n", 1)[1]

        lines = [line for line in paper_list.splitlines() if line.startswith("- [[@")]
        assert lines == [
            "- [[@smith2017]] — Smith, John (2017). Phase Field Modeling",
            "- [[@zhao2020]] — Zhao, Wei (2020). Dynamic Crack Propagation",
        ]
        assert " --- " not in paper_list
