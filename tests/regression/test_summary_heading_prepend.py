"""Tests for Strip-then-prepend Summary heading.

Covers:
- AC-1: Digest with ## Summary -> single heading in output
- AC-2: Digest without ## Summary -> heading still present
- AC-3: Digest with # Summary (wrong level) -> corrected to ##

Existing coverage (partial):
- test_single_summary_heading.py::test_digest_with_summary_heading: validates count=1 (PARTIAL)
- test_single_summary_heading.py::test_digest_without_summary_heading: asserts
  OPPOSITE behavior (CONFLICTING)

Note: test_single_summary_heading.py::test_digest_without_summary_heading asserts
the complementary behavior ('## Summary' NOT in content).
"""

import pytest

from zsum.config import Config
from zsum.models import Collection, Item, LibraryIndex
from zsum.publisher import publish_vault


def _make_index() -> LibraryIndex:
    item = Item(
        citekey="jones2023",
        zotero_key="ZZZZ0001",
        item_id=1,
        title="Test Paper",
        authors=["Jones, A."],
        year=2023,
    )
    col = Collection(
        key="COL1",
        name="Test Collection",
        item_citekeys=["jones2023"],
    )
    return LibraryIndex(items={"jones2023": item}, collections={"COL1": col})


def _make_config(tmp_path) -> Config:
    config = Config()
    config.vault_output = tmp_path / "vault"
    config.generate_paper_notes = False
    return config


def _read_collection_note(tmp_path) -> str:
    note_path = tmp_path / "vault" / "Collections" / "Test Collection.md"
    return note_path.read_text(encoding="utf-8")


class TestSummaryHeadingPrepend:
    """Tests for Strip-then-prepend Summary heading."""

    @pytest.mark.unit
    def test_digest_with_heading_no_duplicate(self, tmp_path):
        """
        Verifies: Digest containing '## Summary' has heading stripped before prepending.
        Covers: AC-1 (single heading in output)
        Passes when: collection note contains exactly one '## Summary' heading.
        """
        index = _make_index()
        config = _make_config(tmp_path)

        publish_vault(
            index,
            config,
            digests={"COL1": "## Summary\n\nContent here"},
        )

        content = _read_collection_note(tmp_path)
        count = content.count("## Summary")
        assert count == 1, f"Expected exactly 1 '## Summary', found {count}.\n\n{content}"
        assert "Content here" in content

    @pytest.mark.unit
    def test_digest_without_heading_gets_heading_added(self, tmp_path):
        """
        Verifies: Digest without any Summary heading gets '## Summary' prepended.
        Covers: AC-2 (heading still present)
        Passes when: collection note contains '## Summary' followed by digest content.
        """
        index = _make_index()
        config = _make_config(tmp_path)

        publish_vault(
            index,
            config,
            digests={"COL1": "Content without heading"},
        )

        content = _read_collection_note(tmp_path)
        assert "## Summary" in content, f"Expected '## Summary' heading to be added.\n\n{content}"
        assert "Content without heading" in content
        # Verify heading appears before the content
        assert content.index("## Summary") < content.index("Content without heading")

    @pytest.mark.unit
    def test_digest_wrong_heading_level_corrected(self, tmp_path):
        """
        Verifies: Digest with '# Summary' (h1) is corrected to '## Summary' (h2).
        Covers: AC-3 (wrong level corrected)
        Passes when: output has '## Summary' and no '# Summary' (bare h1).
        """
        index = _make_index()
        config = _make_config(tmp_path)

        publish_vault(
            index,
            config,
            digests={"COL1": "# Summary\n\nContent"},
        )

        content = _read_collection_note(tmp_path)
        assert "## Summary" in content, f"Expected '## Summary' heading.\n\n{content}"
        assert "Content" in content
        # No bare h1 "# Summary" line should remain (h1 is only the collection title)
        lines = content.splitlines()
        bare_h1_summary = [ln for ln in lines if ln.strip() == "# Summary"]
        assert not bare_h1_summary, (
            f"Found bare '# Summary' h1 line(s) — should be corrected to ##.\n\n{content}"
        )
