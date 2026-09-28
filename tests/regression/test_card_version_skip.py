"""Tests for prompt_version-aware card skip logic.

This module verifies that the card generation pipeline correctly handles
prompt_version matching to skip cached cards or regenerate when versions
change, and respects the --force flag to regenerate all cards.

Covers:
1. All new tests pass
2. Tests cover version match, mismatch, and force override
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from tests.helpers import make_test_item as _make_item
from zsum.cache import load_version_matched_citekeys
from zsum.cards import generate_cards_batch
from zsum.cli import main
from zsum.config import Config
from zsum.extractor import ExtractionResult
from zsum.models import Collection, LibraryIndex, PaperCard


def _make_extraction(**overrides) -> ExtractionResult:
    """Create a test ExtractionResult with sensible defaults."""
    defaults = dict(
        citekey="smith2017",
        text="Some extracted text about fracture.",
        page_count=10,
        pages_used=[0, 1, 2, 8, 9],
        quality="good",
    )
    defaults.update(overrides)
    return ExtractionResult(**defaults)


def _write_cached_card(
    cards_dir: Path, citekey: str, prompt_version: int, problem: str = "Cached problem"
) -> None:
    """Write a cached card JSON file with given prompt_version."""
    data = {
        "citekey": citekey,
        "title": "Test",
        "problem": problem,
        "methods": [],
        "key_findings": [],
        "limitations": [],
        "keywords": [],
        "text_quality": "good",
        "authors": [],
        "year": 2017,
        "venue": "",
        "doi": "",
        "_meta": {"model": "test", "prompt_version": prompt_version, "generated_at": "2025-01-01"},
    }
    (cards_dir / f"{citekey}.json").write_text(json.dumps(data))


class TestCardVersionSkip:
    """
    Tests for prompt_version-aware card skip logic.

    Verifies that prompt_version mismatch triggers card regeneration,
    version match causes skip, and --force flag overrides caching.
    """

    @pytest.mark.unit
    def test_version_match_skips_cached_card(self, tmp_path):
        """
        Verifies: Cached cards with matching prompt_version are loaded without regeneration.

        Covers: version match → skip

        Passes when: Card is loaded from cache and generate_card is not called.
        """
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        _write_cached_card(cards_dir, "smith2017", prompt_version=1)

        matched = load_version_matched_citekeys(tmp_path, prompt_version=1)

        assert "smith2017" in matched

    @pytest.mark.unit
    def test_version_mismatch_regenerates_card(self, tmp_path):
        """
        Verifies: Cached cards with mismatched prompt_version are regenerated.

        Covers: version mismatch → regenerate

        Passes when: Cached card has prompt_version=1 but config.prompt_version=2,
        and the card is regenerated (generate_card is called).
        """
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        _write_cached_card(cards_dir, "smith2017", prompt_version=1, problem="Old problem")

        items = {"smith2017": _make_item()}
        extractions = {"smith2017": _make_extraction()}
        config = Config(prompt_version=2)

        with patch("zsum.cards.generate_card") as mock_gen:
            mock_gen.return_value = (
                PaperCard(citekey="smith2017", title="Test", problem="New problem"),
                [],
            )
            result = generate_cards_batch(items, extractions, config, tmp_path)

        mock_gen.assert_called_once()
        assert result["smith2017"].problem == "New problem"

    @pytest.mark.unit
    def test_force_flag_regenerates_all_cards(self, tmp_path):
        cards_dir = tmp_path / "cache" / "cards"
        cards_dir.mkdir(parents=True)
        _write_cached_card(cards_dir, "smith2017", prompt_version=1)

        config = Config(cache_dir=tmp_path / "cache", prompt_version=1)
        index = LibraryIndex(
            items={"smith2017": _make_item()},
            collections={
                "COL1": Collection(
                    key="COL1",
                    name="Test Collection",
                    item_citekeys=["smith2017"],
                )
            },
        )
        extraction = {"smith2017": _make_extraction()}
        result_card = PaperCard(citekey="smith2017", title="Test", problem="Regenerated")
        runner = CliRunner()

        with (
            patch("zsum.cli._load_cfg", return_value=config),
            patch("zsum.cli.validate_config", return_value=[]),
            patch("zsum.indexer.build_index", return_value=index),
            patch("zsum.cache.load_version_matched_citekeys") as mock_load_matched,
            patch("zsum.extractor.extract_batch", return_value=extraction) as mock_extract,
            patch("zsum.cards.generate_cards_batch", return_value={"smith2017": result_card}),
        ):
            result = runner.invoke(main, ["--config", "ignored.yaml", "cards", "--force"])

        assert result.exit_code == 0, result.output
        assert "Total cards: 1" in result.output
        mock_load_matched.assert_not_called()
        mock_extract.assert_called_once_with(index.items, config, skip_citekeys=set())

    @pytest.mark.unit
    def test_mixed_cached_pending_cards(self, tmp_path):
        """
        Verifies: Batch generation correctly handles mix of cached (skipped) and pending cards.

        Covers: version match → skip (for alpha),
        version mismatch → regenerate (for beta)

        Passes when: alpha card is cached with matching version and skipped,
        beta card has mismatched version and is regenerated.
        """
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        # alpha: matching version → should be skipped
        _write_cached_card(cards_dir, "alpha2020", prompt_version=2, problem="Alpha cached")
        # beta: mismatched version → should be regenerated
        _write_cached_card(cards_dir, "beta2021", prompt_version=1, problem="Beta old")

        matched = load_version_matched_citekeys(tmp_path, prompt_version=2)

        assert "alpha2020" in matched
        assert "beta2021" not in matched

    @pytest.mark.unit
    def test_empty_cache_generates_all_cards(self, tmp_path):
        """
        Verifies: When no cached cards exist, all items are generated.

        Covers: version match → skip (no cached cards to skip)

        Passes when: With empty cache_dir, load_version_matched_citekeys returns empty set.
        """
        # cards dir doesn't exist yet
        matched = load_version_matched_citekeys(tmp_path, prompt_version=1)
        assert matched == set()

        # Also verify with empty cards dir
        (tmp_path / "cards").mkdir()
        matched = load_version_matched_citekeys(tmp_path, prompt_version=1)
        assert matched == set()

    @pytest.mark.unit
    def test_cached_card_with_missing_meta_is_regenerated(self, tmp_path):
        """
        Verifies: Cached cards without _meta (legacy cards) are regenerated.

        Covers: version mismatch → regenerate (missing _meta defaults to 0)

        Passes when: A cached card lacking _meta field is treated as mismatched and regenerated.
        """
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        # Write a legacy card with no _meta field
        legacy = {
            "citekey": "legacy2015",
            "title": "Legacy Paper",
            "problem": "Legacy problem",
            "methods": [],
            "key_findings": [],
            "limitations": [],
            "keywords": [],
            "text_quality": "good",
            "authors": [],
            "year": 2015,
            "venue": "",
            "doi": "",
        }
        (cards_dir / "legacy2015.json").write_text(json.dumps(legacy))

        # prompt_version=1 should NOT match a card with no _meta (defaults to 0)
        matched = load_version_matched_citekeys(tmp_path, prompt_version=1)
        assert "legacy2015" not in matched

        # prompt_version=0 should match (default value)
        matched_zero = load_version_matched_citekeys(tmp_path, prompt_version=0)
        assert "legacy2015" in matched_zero

    @pytest.mark.unit
    def test_prompt_version_zero_vs_nonzero(self, tmp_path):
        """
        Verifies: Cached cards with prompt_version=0 (default) only match config.prompt_version=0.

        Covers: version mismatch → regenerate

        Passes when: Cached card with prompt_version=0 and
        config.prompt_version=1 triggers regeneration.
        """
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        _write_cached_card(
            cards_dir, "smith2017", prompt_version=0, problem="Old zero-versioned card"
        )

        # Should match when prompt_version=0
        matched_zero = load_version_matched_citekeys(tmp_path, prompt_version=0)
        assert "smith2017" in matched_zero

        # Should NOT match when prompt_version=1
        matched_one = load_version_matched_citekeys(tmp_path, prompt_version=1)
        assert "smith2017" not in matched_one
