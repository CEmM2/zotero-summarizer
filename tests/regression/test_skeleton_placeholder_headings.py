"""Tests for Skeleton mode placeholder headings.

This module verifies that skeleton mode collection notes contain the three
required placeholder headings (Key Themes, Common Methods, Gaps and Limitations)
with pending notices, and that full mode notes are unaffected.

Covers:
1. Skeleton collection notes have 3 placeholder headings
2. Each heading has the correct pending notice text
3. Full mode (with digest) notes remain unaffected
"""

from __future__ import annotations

import pytest

from zsum.config import Config
from zsum.models import Collection, Item, LibraryIndex
from zsum.publisher import publish_vault


def _make_minimal_index() -> LibraryIndex:
    """Create a minimal test index with one collection and one item."""
    items = {
        "author2021": Item(
            citekey="author2021",
            zotero_key="Z1",
            item_id=1,
            title="A Test Paper",
            authors=["Author, A."],
            year=2021,
        ),
    }
    collections = {
        "COL1": Collection(
            key="COL1",
            name="Test Collection",
            parent_key=None,
            path="Test Collection",
            item_citekeys=["author2021"],
            child_keys=[],
        ),
    }
    return LibraryIndex(items=items, collections=collections)


class TestSkeletonPlaceholderHeadings:
    """
    Tests for Skeleton mode placeholder headings.

    Covers: Skeleton mode has Key Themes, Common Methods,
    Gaps and Limitations headings with pending notices.
    """

    @pytest.mark.unit
    def test_skeleton_collection_has_three_placeholder_headings(self, tmp_path):
        """
        Verifies: Skeleton collection note contains 3 required placeholder headings.

        Covers: skeleton note has 3 placeholder headings

        Passes when: Collection note in skeleton mode contains
        "## Key Themes", "## Common Methods", "## Gaps and Limitations".
        """
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(_make_minimal_index(), config)

        content = (vault / "Collections" / "Test Collection.md").read_text()
        assert "## Key Themes" in content
        assert "## Common Methods" in content
        assert "## Gaps and Limitations" in content

    @pytest.mark.unit
    def test_placeholder_headings_have_pending_notice(self, tmp_path):
        """
        Verifies: Each placeholder heading has correct pending notice text.

        Covers: pending notice text correct

        Passes when: Each of the 3 headings is followed by
        "*Pending — run `zsum digests` to generate.*"
        """
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(_make_minimal_index(), config)

        content = (vault / "Collections" / "Test Collection.md").read_text()

        # Verify the pending notice text appears after each heading
        for heading in ("## Key Themes", "## Common Methods", "## Gaps and Limitations"):
            heading_idx = content.index(heading)
            # The pending notice should appear somewhere after the heading
            after_heading = content[heading_idx:]
            assert "*Pending \u2014 run `zsum digests` to generate.*" in after_heading, (
                f"Pending notice not found after {heading!r}"
            )

    @pytest.mark.unit
    def test_full_mode_digest_note_unaffected(self, tmp_path):
        """
        Verifies: Full mode notes with digests do not get placeholder headings.

        Covers: full note unaffected

        Passes when: Collection note with a digest replaces the Summary
        section but does not include the 3 placeholder headings.
        """
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        digests = {"COL1": "This is the full digest content with real analysis."}
        publish_vault(_make_minimal_index(), config, digests=digests)

        content = (vault / "Collections" / "Test Collection.md").read_text()

        # Digest content should be present
        assert "This is the full digest content" in content
        # Summary pending notice should NOT be present
        assert "Summary pending" not in content
        # Placeholder headings should NOT be injected when digest is present
        assert "## Key Themes" not in content
        assert "## Common Methods" not in content
        assert "## Gaps and Limitations" not in content
