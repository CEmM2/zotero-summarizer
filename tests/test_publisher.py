"""Tests for the publisher module."""

from __future__ import annotations

import json

from zsum.cache import load_cached_cards, load_effective_digests, save_redigest
from zsum.config import Config, LLMConfig, LLMProviderConfig, LLMRoutingConfig
from zsum.models import Collection, Item, LibraryIndex, PaperCard
from zsum.publisher import _FilenameTracker, _safe_filename, _yaml_quote, publish_vault


def _make_test_index() -> LibraryIndex:
    """Create a small test index."""
    items = {
        "smith2017": Item(
            citekey="smith2017",
            zotero_key="AAA",
            item_id=1,
            title="Phase Field Modeling",
            authors=["Smith, John", "Doe, Alice"],
            year=2017,
            venue="JMPS",
            doi="10.1000/test",
            abstract="A phase field model.",
            tags=["phase-field", "fracture"],
        ),
        "zhao2020": Item(
            citekey="zhao2020",
            zotero_key="BBB",
            item_id=2,
            title="Dynamic Crack Propagation",
            authors=["Zhao, Wei"],
            year=2020,
            venue="EFM",
            doi="10.1000/test2",
            abstract="Dynamic fracture study.",
            tags=["dynamic", "brittle"],
        ),
    }
    collections = {
        "COL1": Collection(
            key="COL1",
            name="Phase Field",
            parent_key=None,
            path="Phase Field",
            item_citekeys=["smith2017", "zhao2020"],
            child_keys=["COL2"],
        ),
        "COL2": Collection(
            key="COL2",
            name="Subcollection A",
            parent_key="COL1",
            path="Phase Field / Subcollection A",
            item_citekeys=["smith2017"],
            child_keys=[],
        ),
    }
    return LibraryIndex(items=items, collections=collections)


class TestPublishSkeleton:
    def test_creates_vault_structure(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault, generate_paper_notes=True)
        publish_vault(_make_test_index(), config)

        assert (vault / "Library Index.md").exists()
        assert (vault / "Collections" / "Phase Field.md").exists()
        assert (vault / "Collections" / "Subcollection A.md").exists()
        assert (vault / "Papers" / "@smith2017.md").exists()
        assert (vault / "Papers" / "@zhao2020.md").exists()

    def test_skeleton_paper_has_pending(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault, generate_paper_notes=True)
        publish_vault(_make_test_index(), config)

        content = (vault / "Papers" / "@smith2017.md").read_text()
        assert "Pending" in content
        assert "type: paper" in content
        assert 'citekey: "smith2017"' in content

    def test_skeleton_collection_has_pending(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(_make_test_index(), config)

        content = (vault / "Collections" / "Phase Field.md").read_text()
        assert "Summary pending" in content
        assert 'type: "collection"' in content

    def test_collection_hierarchy_links(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(_make_test_index(), config)

        parent = (vault / "Collections" / "Phase Field.md").read_text()
        child = (vault / "Collections" / "Subcollection A.md").read_text()

        assert "[[Library Index]]" in parent
        assert "[[Subcollection A]]" in parent
        assert "[[Phase Field]]" in child

    def test_index_note_stats(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(_make_test_index(), config)

        content = (vault / "Library Index.md").read_text()
        assert "**Papers:** 2" in content
        assert "**Collections:** 2" in content
        assert "[[Phase Field]]" in content

    def test_paper_note_heading_includes_citekey(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault, generate_paper_notes=True)
        publish_vault(_make_test_index(), config)

        content = (vault / "Papers" / "@smith2017.md").read_text()
        assert "# smith2017 \u2014 Phase Field Modeling" in content

    def test_no_paper_notes_when_disabled(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault, generate_paper_notes=False)
        publish_vault(_make_test_index(), config)
        assert not (vault / "Papers").exists()

    def test_collection_note_pending_uses_em_dash(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(_make_test_index(), config)
        content = (vault / "Collections" / "Phase Field.md").read_text()
        assert "Summary pending \u2014" in content  # em dash in pending message
        assert "Summary pending ---" not in content  # no triple hyphen in pending

    def test_collection_paper_list_uses_em_dash(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(_make_test_index(), config)

        content = (vault / "Collections" / "Phase Field.md").read_text()
        paper_list = content.split("## Papers in this Collection\n\n", 1)[1]
        assert "- [[@smith2017]] \u2014 Smith, John (2017). Phase Field Modeling" in paper_list
        assert "- [[@zhao2020]] \u2014 Zhao, Wei (2020). Dynamic Crack Propagation" in paper_list
        assert " --- " not in paper_list

    def test_paper_note_pending_uses_em_dash(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault, generate_paper_notes=True)
        publish_vault(_make_test_index(), config)
        content = (vault / "Papers" / "@smith2017.md").read_text()
        # Paper note body should use em dash in pending messages
        body = content.split("---\n\n", 1)[-1]
        if "Pending" in body and "run" in body:
            assert "\u2014" in body


class TestPublishWithCards:
    def test_cards_populate_paper_notes(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault, generate_paper_notes=True)
        cards = {
            "smith2017": PaperCard(
                citekey="smith2017",
                title="Phase Field Modeling",
                problem="How to model crack propagation with phase fields.",
                methods=["Phase field method", "FEM discretization"],
                key_findings=["Converges to Griffith solution"],
                limitations=["2D only"],
                keywords=["phase-field", "fracture"],
            ),
        }

        publish_vault(_make_test_index(), config, cards=cards)

        content = (vault / "Papers" / "@smith2017.md").read_text()
        assert "How to model crack propagation" in content
        assert "Phase field method" in content
        assert "Converges to Griffith" in content
        assert "2D only" in content

    def test_cards_in_collection_paper_list(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        cards = {
            "smith2017": PaperCard(
                citekey="smith2017",
                title="Phase Field Modeling",
                problem="Modeling crack propagation.",
            ),
        }

        publish_vault(_make_test_index(), config, cards=cards)

        content = (vault / "Collections" / "Phase Field.md").read_text()
        assert "Modeling crack propagation" in content


class TestPublishWithDigests:
    def test_digest_replaces_pending(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        digests = {"COL1": "This collection covers phase field modeling approaches."}

        publish_vault(_make_test_index(), config, digests=digests)

        content = (vault / "Collections" / "Phase Field.md").read_text()
        assert "phase field modeling approaches" in content
        assert "Summary pending" not in content

    def test_effective_digests_prefer_fresh_redigest_and_fallback_to_first_pass(self, tmp_path):
        vault = tmp_path / "vault"
        cache_dir = tmp_path / "cache"
        digests_dir = cache_dir / "digests"
        digests_dir.mkdir(parents=True, exist_ok=True)
        root_digest = "Draft digest for root collection."
        child_digest = "Draft digest for child collection."
        (digests_dir / "COL1.md").write_text(root_digest, encoding="utf-8")
        child_digest_path = digests_dir / "COL2.md"
        child_digest_path.write_text(child_digest, encoding="utf-8")
        config = Config(
            vault_output=vault,
            llm=LLMConfig(
                provider="anthropic",
                routing=LLMRoutingConfig(redigest="anthropic"),
                anthropic=LLMProviderConfig(model="claude-redigest"),
            ),
        )
        save_redigest("COL1", "## Summary\n\nRefined root digest.", root_digest, cache_dir, config)
        save_redigest(
            "COL2", "## Summary\n\nOld refined child digest.", child_digest, cache_dir, config
        )
        child_digest_path.write_text("Changed child digest.", encoding="utf-8")

        publish_vault(_make_test_index(), config, digests=load_effective_digests(cache_dir))

        root_content = (vault / "Collections" / "Phase Field.md").read_text()
        child_content = (vault / "Collections" / "Subcollection A.md").read_text()
        assert "Refined root digest" in root_content
        assert "Changed child digest" in child_content
        assert "Old refined child digest" not in child_content


class TestYamlQuote:
    def test_normal_value(self):
        assert _yaml_quote("hello") == '"hello"'

    def test_value_with_colon(self):
        result = _yaml_quote("Nature: Nano")
        assert result == '"Nature: Nano"'

    def test_value_with_double_quote(self):
        result = _yaml_quote('say "hello"')
        assert result == '"say \\"hello\\""'

    def test_value_with_brackets(self):
        result = _yaml_quote("[special]")
        assert result == '"[special]"'

    def test_value_with_backslash(self):
        result = _yaml_quote("path\\to\\file")
        assert result == '"path\\\\to\\\\file"'

    def test_empty_string(self):
        assert _yaml_quote("") == '""'

    def test_value_with_newline(self):
        assert _yaml_quote("line1\nline2") == '"line1\\nline2"'

    def test_value_with_tab(self):
        assert _yaml_quote("tab\there") == '"tab\\there"'

    def test_value_with_hash(self):
        assert _yaml_quote("#comment") == '"#comment"'

    def test_value_with_exclamation(self):
        assert _yaml_quote("!tag") == '"!tag"'

    def test_value_with_ampersand(self):
        assert _yaml_quote("&anchor") == '"&anchor"'

    def test_value_with_asterisk(self):
        assert _yaml_quote("*alias") == '"*alias"'


class TestFrontmatterQuoting:
    """Verify that special characters in metadata don't corrupt YAML frontmatter."""

    def _make_special_index(self) -> LibraryIndex:
        items = {
            "colon2024": Item(
                citekey="colon2024",
                zotero_key="X1",
                item_id=10,
                title="Paper: A Special Title",
                authors=["O'Brien, Pat", 'Smith, "Bob"'],
                year=2024,
                venue="Nature: Nano",
                doi="10.1000/test:special",
                abstract="Abstract.",
                tags=["nano[tech]", "key: value"],
            ),
        }
        collections = {
            "COL1": Collection(
                key="COL1",
                name="Special Chars",
                parent_key=None,
                path="Special Chars",
                item_citekeys=["colon2024"],
                child_keys=[],
            ),
        }
        return LibraryIndex(items=items, collections=collections)

    def test_venue_with_colon_is_quoted(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault, generate_paper_notes=True)
        publish_vault(self._make_special_index(), config)
        content = (vault / "Papers" / "@colon2024.md").read_text()
        assert 'venue: "Nature: Nano"' in content

    def test_doi_with_colon_is_quoted(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault, generate_paper_notes=True)
        publish_vault(self._make_special_index(), config)
        content = (vault / "Papers" / "@colon2024.md").read_text()
        assert 'doi: "10.1000/test:special"' in content

    def test_author_with_quotes_is_escaped(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault, generate_paper_notes=True)
        publish_vault(self._make_special_index(), config)
        content = (vault / "Papers" / "@colon2024.md").read_text()
        assert '  - "Smith, \\"Bob\\""' in content

    def test_tag_with_brackets_is_quoted(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault, generate_paper_notes=True)
        publish_vault(self._make_special_index(), config)
        content = (vault / "Papers" / "@colon2024.md").read_text()
        assert '  - "nano[tech]"' in content

    def test_tag_with_colon_is_quoted(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault, generate_paper_notes=True)
        publish_vault(self._make_special_index(), config)
        content = (vault / "Papers" / "@colon2024.md").read_text()
        assert '  - "key: value"' in content

    def test_citekey_is_quoted(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault, generate_paper_notes=True)
        publish_vault(self._make_special_index(), config)
        content = (vault / "Papers" / "@colon2024.md").read_text()
        assert 'citekey: "colon2024"' in content


class TestSafeFilename:
    def test_normal_name(self):
        assert _safe_filename("Phase Field") == "Phase Field"

    def test_special_chars(self):
        result = _safe_filename('Test: A/B "paper"')
        assert ":" not in result
        assert "/" not in result

    def test_dots_stripped(self):
        result = _safe_filename("...test...")
        assert not result.startswith(".")
        assert not result.endswith(".")

    def test_empty_string_raises(self):
        import pytest

        with pytest.raises(ValueError):
            _safe_filename("")

    def test_whitespace_only_raises(self):
        import pytest

        with pytest.raises(ValueError):
            _safe_filename("   ")


class TestLoadCachedCards:
    def test_loads_valid_cards(self, tmp_path):
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        card_data = {"citekey": "test2020", "title": "Test Paper", "problem": "Testing"}
        (cards_dir / "test2020.json").write_text(json.dumps(card_data))

        cards = load_cached_cards(tmp_path)
        assert "test2020" in cards
        assert cards["test2020"].problem == "Testing"

    def test_empty_cache(self, tmp_path):
        cards = load_cached_cards(tmp_path)
        assert cards == {}


class TestFilenameTracker:
    def test_filename_collision_auto_numbers(self):
        tracker = _FilenameTracker()
        # "Test:Paper" and "Test|Paper" both normalize to "Test_Paper"
        first = tracker.resolve("Test:Paper")
        second = tracker.resolve("Test|Paper")
        assert first == "Test_Paper"
        assert second == "Test_Paper_2"

    def test_no_collision_no_suffix(self):
        tracker = _FilenameTracker()
        assert tracker.resolve("Alpha") == "Alpha"
        assert tracker.resolve("Beta") == "Beta"

    def test_resolve_idempotent(self):
        """Calling resolve() twice for the same name returns the same safe name."""
        tracker = _FilenameTracker()
        first = tracker.resolve("My: Collection")
        second = tracker.resolve("My: Collection")
        assert first == second == "My_ Collection"

    def test_get_safe_name_after_resolve(self):
        """get_safe_name() returns the same result as resolve() for a registered name."""
        tracker = _FilenameTracker()
        safe = tracker.resolve("Data: 2024")
        assert tracker.get_safe_name("Data: 2024") == safe == "Data_ 2024"

    def test_get_safe_name_raises_for_unregistered(self):
        """get_safe_name() raises KeyError for names not registered via resolve()."""
        import pytest

        tracker = _FilenameTracker()
        # Never called resolve() for this name
        with pytest.raises(KeyError, match="Unregistered: Name"):
            tracker.get_safe_name("Unregistered: Name")

    def test_get_safe_name_collision_uses_numbered_name(self):
        """get_safe_name() returns the numbered variant for a colliding name."""
        tracker = _FilenameTracker()
        tracker.resolve("A:B")  # resolves to "A_B"
        tracker.resolve("A|B")  # collides, resolves to "A_B_2"
        assert tracker.get_safe_name("A:B") == "A_B"
        assert tracker.get_safe_name("A|B") == "A_B_2"

    def test_collision_in_publish_vault(self, tmp_path):
        """Two collections with colliding names produce separate files."""
        items = {
            "paper1": Item(
                citekey="paper1",
                zotero_key="A",
                item_id=1,
                title="Paper One",
                authors=["Author"],
                year=2020,
            ),
        }
        collections = {
            "C1": Collection(
                key="C1",
                name="Test:Collection",
                parent_key=None,
                path="Test:Collection",
                item_citekeys=["paper1"],
                child_keys=[],
            ),
            "C2": Collection(
                key="C2",
                name="Test|Collection",
                parent_key=None,
                path="Test|Collection",
                item_citekeys=["paper1"],
                child_keys=[],
            ),
        }
        index = LibraryIndex(items=items, collections=collections)
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(index, config)

        col_dir = vault / "Collections"
        assert (col_dir / "Test_Collection.md").exists()
        assert (col_dir / "Test_Collection_2.md").exists()


class TestSanitizedWikilinks:
    """Verify wikilinks use sanitized filenames, not raw collection names."""

    def _make_special_collection_index(self) -> LibraryIndex:
        """Index with a parent/child pair where names contain special characters."""
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
                name="Sub/Section",
                parent_key="PAR",
                path="Methods: 2024 / Sub/Section",
                item_citekeys=["paper1"],
                child_keys=[],
            ),
        }
        return LibraryIndex(items=items, collections=collections)

    def test_collection_files_use_sanitized_names(self, tmp_path):
        """Files are written using sanitized names (colons/slashes replaced)."""
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(self._make_special_collection_index(), config)

        col_dir = vault / "Collections"
        assert (col_dir / "Methods_ 2024.md").exists()
        assert (col_dir / "Sub_Section.md").exists()

    def test_parent_wikilink_in_child_uses_sanitized_name(self, tmp_path):
        """Child note's Parent wikilink uses the sanitized parent filename."""
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(self._make_special_collection_index(), config)

        child_content = (vault / "Collections" / "Sub_Section.md").read_text()
        # Should link to the sanitized filename, not the raw "Methods: 2024"
        assert "[[Methods_ 2024]]" in child_content
        assert "[[Methods: 2024]]" not in child_content

    def test_child_wikilink_in_parent_uses_sanitized_name(self, tmp_path):
        """Parent note's Subcollections wikilink uses the sanitized child filename."""
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(self._make_special_collection_index(), config)

        parent_content = (vault / "Collections" / "Methods_ 2024.md").read_text()
        # Should link to the sanitized filename, not the raw "Sub/Section"
        assert "[[Sub_Section]]" in parent_content
        assert "[[Sub/Section]]" not in parent_content

    def test_index_wikilinks_use_sanitized_names(self, tmp_path):
        """Library Index wikilinks use sanitized collection filenames."""
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(self._make_special_collection_index(), config)

        index_content = (vault / "Library Index.md").read_text()
        # Root collection link should be sanitized
        assert "[[Methods_ 2024]]" in index_content
        assert "[[Methods: 2024]]" not in index_content
        # Child collection link should also be sanitized
        assert "[[Sub_Section]]" in index_content
        assert "[[Sub/Section]]" not in index_content
