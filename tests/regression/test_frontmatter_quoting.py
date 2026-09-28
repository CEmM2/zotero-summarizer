"""Tests for YAML frontmatter quoting.

Ensures that special characters in paper metadata (venue, title, keywords) are
properly quoted in YAML frontmatter to avoid parsing errors.
"""

from __future__ import annotations

import pytest
import yaml

from zsum.config import Config
from zsum.models import Collection, Item, LibraryIndex, PaperCard
from zsum.publisher import publish_vault


def _make_index_with_item(item: Item) -> LibraryIndex:
    """Wrap a single item in a minimal LibraryIndex with one collection."""
    return LibraryIndex(
        items={item.citekey: item},
        collections={
            "COL1": Collection(
                key="COL1",
                name="Test Collection",
                parent_key=None,
                path="Test Collection",
                item_citekeys=[item.citekey],
                child_keys=[],
            )
        },
    )


def _extract_frontmatter(content: str) -> dict:
    """Extract and parse the YAML frontmatter block from a note."""
    # Frontmatter is between the first and second '---' lines
    lines = content.splitlines()
    assert lines[0] == "---", f"Expected frontmatter start, got: {lines[0]!r}"
    end = lines.index("---", 1)
    fm_text = "\n".join(lines[1:end])
    return yaml.safe_load(fm_text)


class TestFrontmatterQuoting:
    @pytest.mark.unit
    def test_colon_in_venue(self, tmp_path):
        item = Item(
            citekey="nano2024",
            zotero_key="N1",
            item_id=1,
            title="Nanostructures",
            authors=["Lee, James"],
            year=2024,
            venue="Nature: Nanotechnology",
        )
        vault = tmp_path / "vault"
        config = Config(vault_output=vault, generate_paper_notes=True)
        publish_vault(_make_index_with_item(item), config)

        content = (vault / "Papers" / "@nano2024.md").read_text()

        # The raw line must be explicitly quoted
        assert 'venue: "Nature: Nanotechnology"' in content

        # The frontmatter must parse correctly via YAML
        fm = _extract_frontmatter(content)
        assert fm["venue"] == "Nature: Nanotechnology"

    @pytest.mark.unit
    def test_quotes_in_title(self, tmp_path):
        item = Item(
            citekey="quote2024",
            zotero_key="Q1",
            item_id=2,
            title="Paper With Quotes",
            authors=["Smith, Bob"],
            year=2024,
            venue='He said "hello"',
        )
        vault = tmp_path / "vault"
        config = Config(vault_output=vault, generate_paper_notes=True)
        publish_vault(_make_index_with_item(item), config)

        content = (vault / "Papers" / "@quote2024.md").read_text()

        # The venue line must escape the embedded double quotes
        assert 'venue: "He said \\"hello\\""' in content

        # The frontmatter must parse correctly via YAML and round-trip the value
        fm = _extract_frontmatter(content)
        assert fm["venue"] == 'He said "hello"'

    @pytest.mark.unit
    def test_brackets_in_keywords(self, tmp_path):
        item = Item(
            citekey="bracket2024",
            zotero_key="B1",
            item_id=3,
            title="Meta Study",
            authors=["Wang, Li"],
            year=2024,
        )
        card = PaperCard(
            citekey="bracket2024",
            title="Meta Study",
            problem="Systematic review of methods.",
            keywords=["[meta-analysis]", "review"],
        )
        vault = tmp_path / "vault"
        config = Config(vault_output=vault, generate_paper_notes=True)
        publish_vault(_make_index_with_item(item), config, cards={"bracket2024": card})

        content = (vault / "Papers" / "@bracket2024.md").read_text()

        # The bracketed keyword must be double-quoted in the list
        assert '  - "[meta-analysis]"' in content

        # The frontmatter must parse correctly via YAML
        fm = _extract_frontmatter(content)
        assert "[meta-analysis]" in fm["keywords"]
