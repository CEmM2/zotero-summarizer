"""Tests for the cache module."""

from __future__ import annotations

import json

from zsum.cache import (
    any_card_content_changed,
    card_content_hash,
    digest_content_hash,
    load_cached_cards,
    load_cached_digests,
    load_cached_redigests,
    load_effective_digests,
    load_membership,
    load_nlm_digest_keys,
    load_nlm_mappings,
    load_nlm_redigest_keys,
    load_redigest_metadata,
    redigest_state_for_collection,
    save_card,
    save_digest_hashes,
    save_membership,
    save_nlm_digest_keys,
    save_nlm_mappings,
    save_nlm_redigest_keys,
    save_plugin_index,
    save_redigest,
)
from zsum.config import Config, LLMConfig, LLMProviderConfig, LLMRoutingConfig
from zsum.models import Collection, Item, LibraryIndex, PaperCard


def _make_index() -> LibraryIndex:
    items = {
        "alpha": Item(citekey="alpha", zotero_key="A", item_id=1, title="Alpha"),
        "beta": Item(citekey="beta", zotero_key="B", item_id=2, title="Beta"),
    }
    collections = {
        "C1": Collection(
            key="C1",
            name="Col1",
            item_citekeys=["beta", "alpha"],
        ),
    }
    return LibraryIndex(items=items, collections=collections)


class TestSaveAndLoadMembership:
    def test_round_trip(self, tmp_path):
        idx = _make_index()
        save_membership(idx, tmp_path)
        loaded = load_membership(tmp_path)
        assert "C1" in loaded
        assert "alpha" in loaded["C1"]
        assert "beta" in loaded["C1"]

    def test_load_missing_returns_empty(self, tmp_path):
        loaded = load_membership(tmp_path / "nonexistent")
        assert loaded == {}

    def test_membership_is_sorted(self, tmp_path):
        idx = _make_index()
        save_membership(idx, tmp_path)
        loaded = load_membership(tmp_path)
        for citekeys in loaded.values():
            assert citekeys == sorted(citekeys)


class TestNotebookLmMappings:
    def test_round_trip(self, tmp_path):
        mappings = {
            "C1": [
                {
                    "collection_key": "C1",
                    "notebook_id": "nb-1",
                    "title": "Collection 1",
                    "purpose": "collection",
                    "part_index": 1,
                    "total_parts": 1,
                    "sources": [
                        {
                            "source_id": "src-1",
                            "title": "alpha",
                            "kind": "paper",
                            "citekey": "alpha",
                        }
                    ],
                }
            ]
        }

        save_nlm_mappings(mappings, tmp_path)

        loaded = load_nlm_mappings(tmp_path)
        assert loaded["C1"][0]["notebook_id"] == "nb-1"
        assert loaded["C1"][0]["sources"][0]["source_id"] == "src-1"

    def test_missing_cache_returns_empty(self, tmp_path):
        assert load_nlm_mappings(tmp_path) == {}


class TestNotebookLmDigestManifest:
    def test_round_trip(self, tmp_path):
        save_nlm_digest_keys({"C1", "C2"}, tmp_path)
        assert load_nlm_digest_keys(tmp_path) == {"C1", "C2"}

    def test_missing_cache_returns_empty(self, tmp_path):
        assert load_nlm_digest_keys(tmp_path) == set()


class TestNotebookLmRedigestManifest:
    def test_round_trip(self, tmp_path):
        save_nlm_redigest_keys({"C1", "C2"}, tmp_path)
        assert load_nlm_redigest_keys(tmp_path) == {"C1", "C2"}

    def test_missing_cache_returns_empty(self, tmp_path):
        assert load_nlm_redigest_keys(tmp_path) == set()


class TestSaveCard:
    def test_saves_json_with_meta(self, tmp_path):
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        card = PaperCard(citekey="smith2017", title="Test")
        config = Config(prompt_version=3)

        save_card(card, config, cards_dir)

        filepath = cards_dir / "smith2017.json"
        assert filepath.exists()
        data = json.loads(filepath.read_text())
        assert data["citekey"] == "smith2017"
        assert data["_meta"]["prompt_version"] == 3
        assert "generated_at" in data["_meta"]


class TestLoadCachedCards:
    def test_loads_valid_cards(self, tmp_path):
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        card_data = {"citekey": "test2020", "title": "Test Paper", "problem": "Testing"}
        (cards_dir / "test2020.json").write_text(json.dumps(card_data))

        cards = load_cached_cards(tmp_path)
        assert "test2020" in cards
        assert cards["test2020"].problem == "Testing"

    def test_strips_meta_field(self, tmp_path):
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        card_data = {
            "citekey": "test2020",
            "title": "Test",
            "_meta": {"model": "test", "prompt_version": 1},
        }
        (cards_dir / "test2020.json").write_text(json.dumps(card_data))

        cards = load_cached_cards(tmp_path)
        assert "test2020" in cards

    def test_empty_cache(self, tmp_path):
        cards = load_cached_cards(tmp_path)
        assert cards == {}


class TestLoadCachedDigests:
    def test_loads_digests(self, tmp_path):
        digests_dir = tmp_path / "digests"
        digests_dir.mkdir()
        (digests_dir / "COL1.md").write_text("Digest content here")

        digests = load_cached_digests(tmp_path)
        assert "COL1" in digests
        assert digests["COL1"] == "Digest content here"

    def test_empty_cache(self, tmp_path):
        digests = load_cached_digests(tmp_path)
        assert digests == {}


class TestRedigestCache:
    def _make_redigest_config(self) -> Config:
        return Config(
            llm=LLMConfig(
                provider="anthropic",
                routing=LLMRoutingConfig(redigest="anthropic"),
                anthropic=LLMProviderConfig(model="claude-redigest"),
            )
        )

    def test_save_redigest_persists_markdown_and_metadata(self, tmp_path):
        cache_dir = tmp_path / "cache"
        config = self._make_redigest_config()

        save_redigest("C1", "Refined digest", "Draft digest", cache_dir, config)

        assert (cache_dir / "redigests" / "C1.md").read_text(encoding="utf-8") == "Refined digest"
        metadata = load_redigest_metadata(cache_dir, "C1")
        assert metadata is not None
        assert metadata["provider"] == "anthropic"
        assert metadata["model"] == "claude-redigest"
        assert metadata["source_digest_hash"] == digest_content_hash("Draft digest")

    def test_loads_cached_redigests(self, tmp_path):
        cache_dir = tmp_path / "cache"
        config = self._make_redigest_config()

        save_redigest("C1", "Refined digest", "Draft digest", cache_dir, config)

        redigests = load_cached_redigests(cache_dir)
        assert redigests == {"C1": "Refined digest"}

    def test_redigest_state_ok_when_hash_matches(self, tmp_path):
        cache_dir = tmp_path / "cache"
        digests_dir = cache_dir / "digests"
        digests_dir.mkdir(parents=True)
        (digests_dir / "C1.md").write_text("Draft digest", encoding="utf-8")

        save_redigest(
            "C1", "Refined digest", "Draft digest", cache_dir, self._make_redigest_config()
        )

        assert redigest_state_for_collection("C1", cache_dir) == "ok"

    def test_redigest_state_stale_when_first_pass_changes(self, tmp_path):
        cache_dir = tmp_path / "cache"
        digests_dir = cache_dir / "digests"
        digests_dir.mkdir(parents=True)
        digest_path = digests_dir / "C1.md"
        digest_path.write_text("Draft digest", encoding="utf-8")

        save_redigest(
            "C1", "Refined digest", "Draft digest", cache_dir, self._make_redigest_config()
        )
        digest_path.write_text("Changed draft digest", encoding="utf-8")

        assert redigest_state_for_collection("C1", cache_dir) == "stale"

    def test_effective_digests_prefer_fresh_redigest_and_fallback_to_first_pass(self, tmp_path):
        cache_dir = tmp_path / "cache"
        digests_dir = cache_dir / "digests"
        digests_dir.mkdir(parents=True)

        (digests_dir / "C1.md").write_text("Draft digest 1", encoding="utf-8")
        (digests_dir / "C2.md").write_text("Draft digest 2", encoding="utf-8")

        config = self._make_redigest_config()
        save_redigest("C1", "Refined digest 1", "Draft digest 1", cache_dir, config)
        save_redigest("C2", "Refined digest 2", "Draft digest 2", cache_dir, config)
        (digests_dir / "C2.md").write_text("Changed draft digest 2", encoding="utf-8")

        effective = load_effective_digests(cache_dir)

        assert effective["C1"] == "Refined digest 1"
        assert effective["C2"] == "Changed draft digest 2"


class TestCardContentHash:
    def test_deterministic(self, tmp_path):
        card_data = {"citekey": "test", "title": "Test", "problem": "A problem"}
        path = tmp_path / "test.json"
        path.write_text(json.dumps(card_data))
        assert card_content_hash(path) == card_content_hash(path)

    def test_ignores_meta(self, tmp_path):
        card_data = {"citekey": "test", "title": "Test"}
        path1 = tmp_path / "a.json"
        path1.write_text(json.dumps(card_data))

        card_data["_meta"] = {"model": "gpt-4", "generated_at": "2026-01-01"}
        path2 = tmp_path / "b.json"
        path2.write_text(json.dumps(card_data))

        assert card_content_hash(path1) == card_content_hash(path2)

    def test_different_content_different_hash(self, tmp_path):
        path1 = tmp_path / "a.json"
        path1.write_text(json.dumps({"citekey": "a", "title": "A"}))
        path2 = tmp_path / "b.json"
        path2.write_text(json.dumps({"citekey": "b", "title": "B"}))
        assert card_content_hash(path1) != card_content_hash(path2)


class TestSaveDigestHashes:
    def test_saves_hashes_file(self, tmp_path):
        cards_dir = tmp_path / "cards"
        digests_dir = tmp_path / "digests"
        cards_dir.mkdir()
        digests_dir.mkdir()

        card_data = {"citekey": "smith2017", "title": "Test"}
        (cards_dir / "smith2017.json").write_text(json.dumps(card_data))

        save_digest_hashes("COL1", ["smith2017"], cards_dir, digests_dir)

        hash_file = digests_dir / "COL1_hashes.json"
        assert hash_file.exists()
        hashes = json.loads(hash_file.read_text())
        assert "smith2017" in hashes
        assert len(hashes["smith2017"]) == 64  # SHA-256 hex


class TestAnyCardContentChanged:
    def test_no_hashes_file_returns_true(self, tmp_path):
        cards_dir = tmp_path / "cards"
        digests_dir = tmp_path / "digests"
        cards_dir.mkdir()
        digests_dir.mkdir()
        assert any_card_content_changed("COL1", ["smith2017"], cards_dir, digests_dir)

    def test_unchanged_content_returns_false(self, tmp_path):
        cards_dir = tmp_path / "cards"
        digests_dir = tmp_path / "digests"
        cards_dir.mkdir()
        digests_dir.mkdir()

        card_data = {"citekey": "smith2017", "title": "Test"}
        (cards_dir / "smith2017.json").write_text(json.dumps(card_data))
        save_digest_hashes("COL1", ["smith2017"], cards_dir, digests_dir)

        assert not any_card_content_changed("COL1", ["smith2017"], cards_dir, digests_dir)

    def test_changed_content_returns_true(self, tmp_path):
        cards_dir = tmp_path / "cards"
        digests_dir = tmp_path / "digests"
        cards_dir.mkdir()
        digests_dir.mkdir()

        card_data = {"citekey": "smith2017", "title": "Test"}
        (cards_dir / "smith2017.json").write_text(json.dumps(card_data))
        save_digest_hashes("COL1", ["smith2017"], cards_dir, digests_dir)

        # Modify the card
        card_data["title"] = "Changed Title"
        (cards_dir / "smith2017.json").write_text(json.dumps(card_data))

        assert any_card_content_changed("COL1", ["smith2017"], cards_dir, digests_dir)

    def test_new_citekey_returns_true(self, tmp_path):
        cards_dir = tmp_path / "cards"
        digests_dir = tmp_path / "digests"
        cards_dir.mkdir()
        digests_dir.mkdir()

        card_data = {"citekey": "smith2017", "title": "Test"}
        (cards_dir / "smith2017.json").write_text(json.dumps(card_data))
        save_digest_hashes("COL1", ["smith2017"], cards_dir, digests_dir)

        # Add a new card
        (cards_dir / "zhao2020.json").write_text(
            json.dumps({"citekey": "zhao2020", "title": "New"})
        )

        assert any_card_content_changed("COL1", ["smith2017", "zhao2020"], cards_dir, digests_dir)


class TestSavePluginIndex:
    def _make_index(self, tmp_path):
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"fake")
        items = {
            "alpha2020": Item(
                citekey="alpha2020",
                zotero_key="A",
                title="Alpha",
                year=2020,
                venue="JMPS",
                pdf_path=pdf_path,
            ),
            "beta2021": Item(
                citekey="beta2021", zotero_key="B", title="Beta", year=2021, venue="", pdf_path=None
            ),
        }
        collections = {
            "C1": Collection(
                key="C1", name="ColOne", path="ColOne", item_citekeys=["alpha2020", "beta2021"]
            ),
        }
        return LibraryIndex(items=items, collections=collections)

    def test_creates_index_json(self, tmp_path):
        idx = self._make_index(tmp_path)
        save_plugin_index(idx, tmp_path)
        assert (tmp_path / "index.json").exists()

    def test_structure(self, tmp_path):
        idx = self._make_index(tmp_path)
        save_plugin_index(idx, tmp_path)
        data = json.loads((tmp_path / "index.json").read_text())
        assert "generated_at" in data
        assert "collections" in data
        assert "items" in data

    def test_collection_fields(self, tmp_path):
        idx = self._make_index(tmp_path)
        save_plugin_index(idx, tmp_path)
        data = json.loads((tmp_path / "index.json").read_text())
        col = data["collections"]["C1"]
        assert col["name"] == "ColOne"
        assert col["parent"] is None
        assert col["item_count"] == 2
        assert col["digest_state"] == "missing"
        assert col["redigest_state"] == "missing"

    def _make_redigest_config(self) -> Config:
        return Config(
            llm=LLMConfig(
                provider="anthropic",
                routing=LLMRoutingConfig(redigest="anthropic"),
                anthropic=LLMProviderConfig(model="claude-redigest"),
            )
        )

    def test_digest_state_ok(self, tmp_path):
        idx = self._make_index(tmp_path)
        cards_dir = tmp_path / "cards"
        digests_dir = tmp_path / "digests"
        cards_dir.mkdir()
        digests_dir.mkdir()
        card_data = {"citekey": "alpha2020", "title": "Alpha"}
        (cards_dir / "alpha2020.json").write_text(json.dumps(card_data))
        save_digest_hashes("C1", ["alpha2020"], cards_dir, digests_dir)
        (digests_dir / "C1.md").write_text("digest text")
        save_plugin_index(idx, tmp_path)
        data = json.loads((tmp_path / "index.json").read_text())
        assert data["collections"]["C1"]["digest_state"] == "ok"

    def test_digest_state_stale(self, tmp_path):
        idx = self._make_index(tmp_path)
        cards_dir = tmp_path / "cards"
        digests_dir = tmp_path / "digests"
        cards_dir.mkdir()
        digests_dir.mkdir()
        card_path = cards_dir / "alpha2020.json"
        card_path.write_text(json.dumps({"citekey": "alpha2020", "title": "Alpha"}))
        save_digest_hashes("C1", ["alpha2020"], cards_dir, digests_dir)
        card_path.write_text(json.dumps({"citekey": "alpha2020", "title": "Changed"}))
        (digests_dir / "C1.md").write_text("stale digest")
        save_plugin_index(idx, tmp_path)
        data = json.loads((tmp_path / "index.json").read_text())
        assert data["collections"]["C1"]["digest_state"] == "stale"

    def test_redigest_state_ok(self, tmp_path):
        idx = self._make_index(tmp_path)
        cards_dir = tmp_path / "cards"
        digests_dir = tmp_path / "digests"
        cards_dir.mkdir()
        digests_dir.mkdir()
        card_data = {"citekey": "alpha2020", "title": "Alpha"}
        (cards_dir / "alpha2020.json").write_text(json.dumps(card_data))
        digest_text = "digest text"
        save_digest_hashes("C1", ["alpha2020"], cards_dir, digests_dir)
        (digests_dir / "C1.md").write_text(digest_text)
        save_redigest("C1", "Refined digest", digest_text, tmp_path, self._make_redigest_config())

        save_plugin_index(idx, tmp_path)

        data = json.loads((tmp_path / "index.json").read_text())
        assert data["collections"]["C1"]["digest_state"] == "ok"
        assert data["collections"]["C1"]["redigest_state"] == "ok"

    def test_redigest_state_stale_when_digest_changes(self, tmp_path):
        idx = self._make_index(tmp_path)
        cards_dir = tmp_path / "cards"
        digests_dir = tmp_path / "digests"
        cards_dir.mkdir()
        digests_dir.mkdir()
        card_data = {"citekey": "alpha2020", "title": "Alpha"}
        (cards_dir / "alpha2020.json").write_text(json.dumps(card_data))
        digest_path = digests_dir / "C1.md"
        digest_path.write_text("digest text")
        save_digest_hashes("C1", ["alpha2020"], cards_dir, digests_dir)
        save_redigest("C1", "Refined digest", "digest text", tmp_path, self._make_redigest_config())
        digest_path.write_text("changed digest text")

        save_plugin_index(idx, tmp_path)

        data = json.loads((tmp_path / "index.json").read_text())
        assert data["collections"]["C1"]["digest_state"] == "ok"
        assert data["collections"]["C1"]["redigest_state"] == "stale"

    def test_redigest_state_missing_without_changing_digest_state(self, tmp_path):
        idx = self._make_index(tmp_path)
        cards_dir = tmp_path / "cards"
        digests_dir = tmp_path / "digests"
        cards_dir.mkdir()
        digests_dir.mkdir()
        (cards_dir / "alpha2020.json").write_text(
            json.dumps({"citekey": "alpha2020", "title": "Alpha"})
        )
        save_digest_hashes("C1", ["alpha2020"], cards_dir, digests_dir)
        (digests_dir / "C1.md").write_text("digest text")

        save_plugin_index(idx, tmp_path)

        data = json.loads((tmp_path / "index.json").read_text())
        assert data["collections"]["C1"]["digest_state"] == "ok"
        assert data["collections"]["C1"]["redigest_state"] == "missing"

    def test_item_card_states(self, tmp_path):
        idx = self._make_index(tmp_path)
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        (cards_dir / "alpha2020.json").write_text(
            json.dumps({"citekey": "alpha2020", "title": "Alpha", "text_quality": "good"})
        )
        save_plugin_index(idx, tmp_path)
        data = json.loads((tmp_path / "index.json").read_text())
        assert data["items"]["alpha2020"]["card_state"] == "cached"
        assert data["items"]["beta2021"]["card_state"] == "no_pdf"

    def test_item_degraded_card_state(self, tmp_path):
        idx = self._make_index(tmp_path)
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        (cards_dir / "alpha2020.json").write_text(
            json.dumps({"citekey": "alpha2020", "title": "Alpha", "text_quality": "degraded"})
        )
        save_plugin_index(idx, tmp_path)
        data = json.loads((tmp_path / "index.json").read_text())
        assert data["items"]["alpha2020"]["card_state"] == "degraded"

    def test_item_pending_when_no_card_but_has_pdf(self, tmp_path):
        idx = self._make_index(tmp_path)
        save_plugin_index(idx, tmp_path)
        data = json.loads((tmp_path / "index.json").read_text())
        # alpha2020 has a PDF but no card cached
        assert data["items"]["alpha2020"]["card_state"] == "pending"

    def test_item_fallback_card_state_when_extraction_method_is_fallback_pages(self, tmp_path):
        idx = self._make_index(tmp_path)
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        (cards_dir / "alpha2020.json").write_text(
            json.dumps(
                {
                    "citekey": "alpha2020",
                    "title": "Alpha",
                    "text_quality": "good",
                    "extraction_method": "fallback_pages",
                }
            )
        )

        save_plugin_index(idx, tmp_path)

        data = json.loads((tmp_path / "index.json").read_text())
        assert data["items"]["alpha2020"]["card_state"] == "fallback"
        assert data["items"]["alpha2020"]["extraction_method"] == "fallback_pages"

    def test_item_fallback_state_overrides_degraded_text_quality(self, tmp_path):
        idx = self._make_index(tmp_path)
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        (cards_dir / "alpha2020.json").write_text(
            json.dumps(
                {
                    "citekey": "alpha2020",
                    "title": "Alpha",
                    "text_quality": "degraded",
                    "extraction_method": "fallback_pages",
                }
            )
        )

        save_plugin_index(idx, tmp_path)

        data = json.loads((tmp_path / "index.json").read_text())
        assert data["items"]["alpha2020"]["card_state"] == "fallback"

    def test_notebooklm_mode_keeps_fallback_pages_cards_visible(self, tmp_path):
        idx = self._make_index(tmp_path)
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        (cards_dir / "alpha2020.json").write_text(
            json.dumps(
                {
                    "citekey": "alpha2020",
                    "title": "Alpha",
                    "text_quality": "good",
                    "extraction_method": "fallback_pages",
                }
            )
        )

        config = Config()
        config.extraction.mode = "notebooklm"
        save_plugin_index(idx, tmp_path, config)

        data = json.loads((tmp_path / "index.json").read_text())
        assert data["items"]["alpha2020"]["card_state"] == "fallback"
        assert data["items"]["alpha2020"]["extraction_method"] == "fallback_pages"

    def test_item_includes_extraction_method_when_card_cached(self, tmp_path):
        idx = self._make_index(tmp_path)
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        (cards_dir / "alpha2020.json").write_text(
            json.dumps(
                {
                    "citekey": "alpha2020",
                    "title": "Alpha",
                    "text_quality": "good",
                    "extraction_method": "notebooklm",
                }
            )
        )

        save_plugin_index(idx, tmp_path)

        data = json.loads((tmp_path / "index.json").read_text())
        assert data["items"]["alpha2020"]["extraction_method"] == "notebooklm"

    def test_notebooklm_mode_ignores_local_mode_cards_for_digest_freshness(self, tmp_path):
        idx = self._make_index(tmp_path)
        cards_dir = tmp_path / "cards"
        digests_dir = tmp_path / "digests"
        cards_dir.mkdir()
        digests_dir.mkdir()

        alpha_path = cards_dir / "alpha2020.json"
        alpha_path.write_text(
            json.dumps(
                {
                    "citekey": "alpha2020",
                    "title": "Alpha",
                    "text_quality": "good",
                    "extraction_method": "notebooklm",
                }
            )
        )
        (cards_dir / "beta2021.json").write_text(
            json.dumps(
                {
                    "citekey": "beta2021",
                    "title": "Beta",
                    "text_quality": "good",
                    "extraction_method": "pages",
                }
            )
        )
        (digests_dir / "C1.md").write_text("NotebookLM digest", encoding="utf-8")
        (digests_dir / "C1_hashes.json").write_text(
            json.dumps({"alpha2020": card_content_hash(alpha_path)}),
            encoding="utf-8",
        )

        config = Config()
        config.extraction.mode = "notebooklm"
        save_nlm_digest_keys({"C1"}, tmp_path)
        save_plugin_index(idx, tmp_path, config)

        data = json.loads((tmp_path / "index.json").read_text())
        assert data["collections"]["C1"]["digest_state"] == "ok"
        assert data["items"]["beta2021"]["card_state"] == "no_pdf"

    def test_notebooklm_mode_allows_empty_digest_hash_sidecar(self, tmp_path):
        idx = self._make_index(tmp_path)
        digests_dir = tmp_path / "digests"
        digests_dir.mkdir()
        (digests_dir / "C1.md").write_text("NotebookLM digest", encoding="utf-8")
        (digests_dir / "C1_hashes.json").write_text("{}", encoding="utf-8")

        config = Config()
        config.extraction.mode = "notebooklm"
        save_nlm_digest_keys({"C1"}, tmp_path)
        save_plugin_index(idx, tmp_path, config)

        data = json.loads((tmp_path / "index.json").read_text())
        assert data["collections"]["C1"]["digest_state"] == "ok"

    def test_notebooklm_mode_hides_redigests_without_redigest_manifest(self, tmp_path):
        idx = self._make_index(tmp_path)
        digests_dir = tmp_path / "digests"
        redigests_dir = tmp_path / "redigests"
        digests_dir.mkdir()
        redigests_dir.mkdir()
        digest_text = "NotebookLM digest"
        (digests_dir / "C1.md").write_text(digest_text, encoding="utf-8")
        (digests_dir / "C1_hashes.json").write_text("{}", encoding="utf-8")
        save_redigest("C1", "Local redigest", digest_text, tmp_path, self._make_redigest_config())

        config = Config()
        config.extraction.mode = "notebooklm"
        save_plugin_index(idx, tmp_path, config)

        data = json.loads((tmp_path / "index.json").read_text())
        assert data["collections"]["C1"]["redigest_state"] == "missing"

    def test_notebooklm_mode_hides_digests_without_digest_manifest(self, tmp_path):
        idx = self._make_index(tmp_path)
        digests_dir = tmp_path / "digests"
        digests_dir.mkdir()
        (digests_dir / "C1.md").write_text("Local digest", encoding="utf-8")
        (digests_dir / "C1_hashes.json").write_text("{}", encoding="utf-8")

        config = Config()
        config.extraction.mode = "notebooklm"
        save_plugin_index(idx, tmp_path, config)

        data = json.loads((tmp_path / "index.json").read_text())
        assert data["collections"]["C1"]["digest_state"] == "missing"

    def test_notebooklm_mode_ignores_overwritten_local_card_for_digest_freshness(self, tmp_path):
        idx = self._make_index(tmp_path)
        cards_dir = tmp_path / "cards"
        digests_dir = tmp_path / "digests"
        cards_dir.mkdir()
        digests_dir.mkdir()

        alpha_path = cards_dir / "alpha2020.json"
        alpha_path.write_text(
            json.dumps(
                {
                    "citekey": "alpha2020",
                    "title": "Alpha",
                    "text_quality": "good",
                    "extraction_method": "notebooklm",
                }
            )
        )
        (digests_dir / "C1.md").write_text("NotebookLM digest", encoding="utf-8")
        (digests_dir / "C1_hashes.json").write_text(
            json.dumps({"alpha2020": card_content_hash(alpha_path)}),
            encoding="utf-8",
        )

        alpha_path.write_text(
            json.dumps(
                {
                    "citekey": "alpha2020",
                    "title": "Alpha (local overwrite)",
                    "text_quality": "good",
                    "extraction_method": "pages",
                }
            )
        )

        config = Config()
        config.extraction.mode = "notebooklm"
        save_nlm_digest_keys({"C1"}, tmp_path)
        save_plugin_index(idx, tmp_path, config)

        data = json.loads((tmp_path / "index.json").read_text())
        assert data["collections"]["C1"]["digest_state"] == "ok"

    def test_item_collections_membership(self, tmp_path):
        idx = self._make_index(tmp_path)
        save_plugin_index(idx, tmp_path)
        data = json.loads((tmp_path / "index.json").read_text())
        assert "C1" in data["items"]["alpha2020"]["collections"]
        assert "C1" in data["items"]["beta2021"]["collections"]
