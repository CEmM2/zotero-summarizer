"""Tests for the digests module."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from zsum.config import CodexExecConfig, Config, LLMConfig, LLMProviderConfig, LLMRoutingConfig
from zsum.digests import (
    _bottom_up_order,
    _build_digest_prompt,
    generate_digest,
    generate_digests_batch,
    generate_redigest,
)
from zsum.llm import LLMResponse
from zsum.models import Collection, Item, LibraryIndex, PaperCard


def _make_card(**overrides) -> PaperCard:
    defaults = dict(
        citekey="smith2017",
        title="Phase Field Modeling",
        authors=["Smith, John"],
        year=2017,
        venue="JMPS",
        problem="How cracks propagate.",
        methods=["Phase field", "FEM"],
        key_findings=["Converges to Griffith"],
        limitations=["2D only"],
        keywords=["phase-field", "fracture"],
    )
    defaults.update(overrides)
    return PaperCard(**defaults)


def _make_index() -> LibraryIndex:
    items = {
        "smith2017": Item(
            citekey="smith2017",
            zotero_key="A",
            item_id=1,
            title="Phase Field Modeling",
            authors=["Smith, John"],
            year=2017,
        ),
        "zhao2020": Item(
            citekey="zhao2020",
            zotero_key="B",
            item_id=2,
            title="Dynamic Fracture",
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
            child_keys=["COL2"],
        ),
        "COL2": Collection(
            key="COL2",
            name="Subcollection",
            parent_key="COL1",
            path="Phase Field / Subcollection",
            item_citekeys=["smith2017"],
            child_keys=[],
        ),
    }
    return LibraryIndex(items=items, collections=collections)


class TestBottomUpOrder:
    def test_children_before_parents(self):
        index = _make_index()
        order = _bottom_up_order(index)

        col2_pos = order.index("COL2")
        col1_pos = order.index("COL1")
        assert col2_pos < col1_pos

    def test_all_collections_included(self):
        index = _make_index()
        order = _bottom_up_order(index)
        assert set(order) == {"COL1", "COL2"}

    def test_single_collection(self):
        index = LibraryIndex(
            collections={
                "X": Collection(key="X", name="Solo", item_citekeys=["a"]),
            },
        )
        assert _bottom_up_order(index) == ["X"]

    def test_deep_hierarchy(self):
        index = LibraryIndex(
            collections={
                "A": Collection(key="A", name="Root", child_keys=["B"]),
                "B": Collection(key="B", name="Mid", parent_key="A", child_keys=["C"]),
                "C": Collection(key="C", name="Leaf", parent_key="B"),
            },
        )
        order = _bottom_up_order(index)
        assert order.index("C") < order.index("B") < order.index("A")


class TestBuildDigestPrompt:
    def test_includes_collection_info(self):
        col = Collection(
            key="COL1",
            name="Phase Field",
            path="Phase Field",
            item_citekeys=["smith2017"],
        )
        cards = {"smith2017": _make_card()}
        prompt = _build_digest_prompt(col, cards)

        assert "Phase Field" in prompt
        assert "Number of papers: 1" in prompt

    def test_includes_card_fields(self):
        col = Collection(key="X", name="Test", item_citekeys=["smith2017"])
        cards = {
            "smith2017": _make_card(
                problem="Crack propagation problem",
                methods=["FEM", "Phase field"],
                key_findings=["It works"],
            )
        }
        prompt = _build_digest_prompt(col, cards)

        assert "smith2017" in prompt
        assert "Crack propagation problem" in prompt
        assert "FEM" in prompt
        assert "It works" in prompt

    def test_multiple_cards_sorted(self):
        col = Collection(key="X", name="Test", item_citekeys=["b2020", "a2019"])
        cards = {
            "b2020": _make_card(citekey="b2020", title="Paper B"),
            "a2019": _make_card(citekey="a2019", title="Paper A"),
        }
        prompt = _build_digest_prompt(col, cards)

        pos_a = prompt.index("a2019")
        pos_b = prompt.index("b2020")
        assert pos_a < pos_b  # sorted alphabetically


class TestGenerateDigest:
    def test_codex_exec_renders_structured_markdown(self):
        col = Collection(
            key="COL1",
            name="Phase Field",
            path="Phase Field",
            item_citekeys=["smith2017"],
        )
        cards = {"smith2017": _make_card()}
        config = Config(
            llm=LLMConfig(
                provider="codex_exec",
                codex_exec=CodexExecConfig(model="gpt-5.4"),
            )
        )
        response = LLMResponse(
            text=json.dumps(
                {
                    "summary": "This collection studies fracture [[@smith2017]].",
                    "key_themes": ["Crack growth"],
                    "common_methods": ["Phase-field FEM"],
                    "gaps_and_limitations": ["Mostly 2D studies"],
                }
            ),
            model="gpt-5.4",
            input_tokens=100,
            output_tokens=40,
        )

        with patch("zsum.digests.complete_with_retry", return_value=response) as mock_complete:
            digest = generate_digest(col, cards, config)

        assert "## Summary" in digest
        assert "## Key Themes" in digest
        assert "- Crack growth" in digest
        assert "[[@smith2017]]" in digest
        assert mock_complete.call_args.kwargs["output_schema"]["type"] == "object"

    def test_codex_exec_rejects_uncited_summary(self):
        col = Collection(key="COL1", name="Phase Field", item_citekeys=["smith2017"])
        cards = {"smith2017": _make_card()}
        config = Config(
            llm=LLMConfig(
                provider="codex_exec",
                codex_exec=CodexExecConfig(model="gpt-5.4"),
            )
        )
        response = LLMResponse(
            text=json.dumps(
                {
                    "summary": "This collection studies fracture without citations.",
                    "key_themes": ["Crack growth"],
                    "common_methods": ["Phase-field FEM"],
                    "gaps_and_limitations": ["Mostly 2D studies"],
                }
            ),
            model="gpt-5.4",
            input_tokens=100,
            output_tokens=40,
        )

        with (
            patch("zsum.digests.complete_with_retry", return_value=response),
            pytest.raises(ValueError, match="citekey wikilinks"),
        ):
            generate_digest(col, cards, config)


class TestGenerateRedigest:
    def test_returns_final_markdown(self):
        col = Collection(
            key="COL1",
            name="Phase Field",
            path="Phase Field",
            item_citekeys=["smith2017"],
        )
        cards = {"smith2017": _make_card()}
        config = Config(
            llm=LLMConfig(
                provider="anthropic",
                routing=LLMRoutingConfig(redigest="anthropic"),
                anthropic=LLMProviderConfig(model="claude-redigest", max_tokens_digest=777),
            )
        )
        response = LLMResponse(
            text="## Summary\nRefined digest with [[@smith2017]].\n",
            model="claude-redigest",
            input_tokens=120,
            output_tokens=45,
        )

        with patch("zsum.digests.complete_with_retry", return_value=response) as mock_complete:
            digest = generate_redigest(
                col,
                "## Summary\nDraft digest with [[@smith2017]].",
                config,
                cards,
            )

        assert digest == "## Summary\nRefined digest with [[@smith2017]]."
        assert "Draft digest with [[@smith2017]]." in mock_complete.call_args.args[1]
        assert mock_complete.call_args.kwargs["stage"] == "redigest"
        assert mock_complete.call_args.kwargs["max_tokens"] == 777


class TestGenerateDigestsBatch:
    def test_caches_digest_to_file(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / "digests").mkdir()

        index = _make_index()
        cards = {
            "smith2017": _make_card(),
            "zhao2020": _make_card(citekey="zhao2020", title="Dynamic Fracture"),
        }
        config = Config(cache_dir=cache_dir)

        with patch("zsum.digests.generate_digest") as mock_gen:
            mock_gen.return_value = "This is a test digest."
            digests = generate_digests_batch(index, cards, config, cache_dir)

        assert "COL1" in digests
        assert (cache_dir / "digests" / "COL1.md").exists()
        assert (cache_dir / "digests" / "COL1.md").read_text() == "This is a test digest."

    def test_skips_unchanged_membership(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        cards_dir = cache_dir / "cards"
        digests_dir = cache_dir / "digests"
        cards_dir.mkdir()
        digests_dir.mkdir()

        # Write existing membership and digest
        membership = {"COL2": ["smith2017"]}
        (cache_dir / "membership.json").write_text(json.dumps(membership))
        (digests_dir / "COL2.md").write_text("Existing digest.")

        # Write card file and its hashes so content-hash check passes
        card_data = _make_card().model_dump()
        (cards_dir / "smith2017.json").write_text(json.dumps(card_data))

        from zsum.cache import save_digest_hashes

        save_digest_hashes("COL2", ["smith2017"], cards_dir, digests_dir)

        index = LibraryIndex(
            collections={
                "COL2": Collection(
                    key="COL2",
                    name="Sub",
                    item_citekeys=["smith2017"],
                ),
            },
        )
        cards = {"smith2017": _make_card()}
        config = Config(cache_dir=cache_dir)

        with patch("zsum.digests.generate_digest") as mock_gen:
            digests = generate_digests_batch(index, cards, config, cache_dir)

        mock_gen.assert_not_called()
        assert digests["COL2"] == "Existing digest."

    def test_regenerates_on_membership_change(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / "digests").mkdir()

        # Old membership had only smith2017
        membership = {"COL1": ["smith2017"]}
        (cache_dir / "membership.json").write_text(json.dumps(membership))
        (cache_dir / "digests" / "COL1.md").write_text("Old digest.")

        # New membership adds zhao2020
        index = LibraryIndex(
            collections={
                "COL1": Collection(
                    key="COL1",
                    name="Phase Field",
                    item_citekeys=["smith2017", "zhao2020"],
                ),
            },
        )
        cards = {
            "smith2017": _make_card(),
            "zhao2020": _make_card(citekey="zhao2020"),
        }
        config = Config(cache_dir=cache_dir)

        with patch("zsum.digests.generate_digest") as mock_gen:
            mock_gen.return_value = "Updated digest."
            digests = generate_digests_batch(index, cards, config, cache_dir)

        mock_gen.assert_called_once()
        assert digests["COL1"] == "Updated digest."

    def test_skips_collection_with_no_cards(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / "digests").mkdir()

        index = LibraryIndex(
            collections={
                "COL1": Collection(
                    key="COL1",
                    name="Empty",
                    item_citekeys=["missing_paper"],
                ),
            },
        )
        config = Config(cache_dir=cache_dir)

        with patch("zsum.digests.generate_digest") as mock_gen:
            digests = generate_digests_batch(index, {}, config, cache_dir)

        mock_gen.assert_not_called()
        assert "COL1" not in digests


class TestCardFreshnessCheck:
    def test_regenerates_when_card_content_changed(self, tmp_path):
        """When a card's content hash differs from saved hash, regenerate."""
        cache_dir = tmp_path / "cache"
        cards_dir = cache_dir / "cards"
        digests_dir = cache_dir / "digests"
        cards_dir.mkdir(parents=True)
        digests_dir.mkdir(parents=True)

        card_data = {
            "citekey": "smith2017",
            "title": "Test",
            "problem": "old problem",
            "methods": [],
            "key_findings": [],
            "limitations": [],
            "keywords": [],
            "text_quality": "good",
            "authors": [],
            "year": 2017,
            "venue": "",
            "doi": "",
        }
        card_file = cards_dir / "smith2017.json"
        card_file.write_text(json.dumps(card_data))

        digest_file = digests_dir / "COL1.md"
        digest_file.write_text("old digest")

        # Save hashes for original content
        from zsum.cache import save_digest_hashes, save_membership

        save_digest_hashes("COL1", ["smith2017"], cards_dir, digests_dir)

        # Update card content
        card_data["problem"] = "new problem"
        card_file.write_text(json.dumps(card_data))

        idx = LibraryIndex(
            items={
                "smith2017": Item(
                    citekey="smith2017",
                    zotero_key="A",
                    item_id=1,
                    title="Test",
                )
            },
            collections={
                "COL1": Collection(
                    key="COL1",
                    name="Test Col",
                    item_citekeys=["smith2017"],
                )
            },
        )
        save_membership(idx, cache_dir)

        cards = {"smith2017": PaperCard(citekey="smith2017", title="Test", problem="new problem")}

        with patch("zsum.digests.generate_digest") as mock_gen:
            mock_gen.return_value = "new digest content"
            result = generate_digests_batch(idx, cards, Config(), cache_dir)

        mock_gen.assert_called_once()
        assert result["COL1"] == "new digest content"

    def test_uses_cache_when_card_content_unchanged(self, tmp_path):
        """When card content hashes match, use cached digest."""
        cache_dir = tmp_path / "cache"
        cards_dir = cache_dir / "cards"
        digests_dir = cache_dir / "digests"
        cards_dir.mkdir(parents=True)
        digests_dir.mkdir(parents=True)

        card_data = {
            "citekey": "smith2017",
            "title": "Test",
            "problem": "test problem",
            "methods": [],
            "key_findings": [],
            "limitations": [],
            "keywords": [],
            "text_quality": "good",
            "authors": [],
            "year": 2017,
            "venue": "",
            "doi": "",
        }
        (cards_dir / "smith2017.json").write_text(json.dumps(card_data))
        (digests_dir / "COL1.md").write_text("cached digest")

        from zsum.cache import save_digest_hashes, save_membership

        save_digest_hashes("COL1", ["smith2017"], cards_dir, digests_dir)

        idx = LibraryIndex(
            items={
                "smith2017": Item(
                    citekey="smith2017",
                    zotero_key="A",
                    item_id=1,
                    title="Test",
                )
            },
            collections={
                "COL1": Collection(
                    key="COL1",
                    name="Test Col",
                    item_citekeys=["smith2017"],
                )
            },
        )
        save_membership(idx, cache_dir)

        cards = {"smith2017": PaperCard(citekey="smith2017", title="Test", problem="test problem")}

        with patch("zsum.digests.generate_digest") as mock_gen:
            result = generate_digests_batch(idx, cards, Config(), cache_dir)

        mock_gen.assert_not_called()
        assert result["COL1"] == "cached digest"
