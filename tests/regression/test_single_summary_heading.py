"""Tests for single Summary heading.

Ensures that collection notes contain exactly one ## Summary heading, even when
digests already contain a ## Summary prefix. This prevents duplicate headings
in the final Obsidian output.
"""

from __future__ import annotations

import pytest

from zsum.config import Config
from zsum.models import Collection, Item, LibraryIndex
from zsum.publisher import publish_vault


def _make_index() -> LibraryIndex:
    """Create a minimal LibraryIndex with one collection and one item."""
    item = Item(
        citekey="smith2024",
        zotero_key="ABCD1234",
        item_id=1,
        title="A Test Paper",
        authors=["Smith, J."],
        year=2024,
    )
    col = Collection(
        key="COL1",
        name="Test Collection",
        item_citekeys=["smith2024"],
    )
    return LibraryIndex(items={"smith2024": item}, collections={"COL1": col})


def _make_config(tmp_path) -> Config:
    """Create a Config pointing vault output at a temp directory."""
    config = Config()
    config.vault_output = tmp_path / "vault"
    config.generate_paper_notes = False
    return config


def _read_collection_note(tmp_path) -> str:
    """Read the generated collection note content."""
    note_path = tmp_path / "vault" / "Collections" / "Test Collection.md"
    return note_path.read_text(encoding="utf-8")


class TestSingleSummaryHeading:
    @pytest.mark.unit
    def test_digest_with_summary_heading(self, tmp_path):
        index = _make_index()
        config = _make_config(tmp_path)

        publish_vault(
            index,
            config,
            digests={"COL1": "## Summary\n\nThis is the digest content."},
        )

        content = _read_collection_note(tmp_path)
        summary_count = content.count("## Summary")
        assert summary_count == 1, (
            f"Expected exactly 1 '## Summary' heading, found {summary_count}.\n\n{content}"
        )
        assert "This is the digest content." in content

    @pytest.mark.unit
    def test_digest_without_summary_heading(self, tmp_path):
        index = _make_index()
        config = _make_config(tmp_path)

        publish_vault(
            index,
            config,
            digests={"COL1": "This is raw digest without heading."},
        )

        content = _read_collection_note(tmp_path)
        assert "This is raw digest without heading." in content
        # Publisher always prepends ## Summary
        assert "## Summary" in content, (
            f"Expected '## Summary' heading to be present even when digest has none.\n\n{content}"
        )

    @pytest.mark.unit
    def test_no_digest_shows_summary_heading(self, tmp_path):
        index = _make_index()
        config = _make_config(tmp_path)

        publish_vault(index, config)

        content = _read_collection_note(tmp_path)
        summary_count = content.count("## Summary")
        assert summary_count == 1, (
            f"Expected exactly 1 '## Summary' heading, found {summary_count}.\n\n{content}"
        )
        assert "Summary pending" in content
