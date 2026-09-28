"""Tests for force-flag behavior and preview output contract."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from zsum.cli import main
from zsum.config import Config
from zsum.extractor import ExtractionResult, extraction_report
from zsum.models import Collection, Item, LibraryIndex, PaperCard


def _make_item(pdf_path: Path | None = None) -> Item:
    return Item(
        citekey="smith2017",
        zotero_key="AAA",
        item_id=1,
        title="Phase Field Modeling",
        authors=["Smith, John"],
        year=2017,
        pdf_path=pdf_path,
    )


def _make_index(item: Item | None = None) -> LibraryIndex:
    item = item or _make_item()
    return LibraryIndex(
        items={item.citekey: item},
        collections={
            "COL1": Collection(
                key="COL1",
                name="Test Collection",
                item_citekeys=[item.citekey],
            )
        },
    )


def _make_extraction(citekey: str = "smith2017") -> ExtractionResult:
    return ExtractionResult(
        citekey=citekey,
        text="Some extracted text about fracture.",
        page_count=10,
        pages_used=[0, 1],
        quality="good",
    )


def _write_cached_card(cards_dir: Path, citekey: str, prompt_version: int) -> None:
    data = {
        "citekey": citekey,
        "title": "Cached",
        "problem": "Cached problem",
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
    (cards_dir / f"{citekey}.json").write_text(json.dumps(data), encoding="utf-8")


class TestForceFlag:
    @pytest.mark.unit
    def test_cards_force_passes_empty_skip_set(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cards_dir = cache_dir / "cards"
        cards_dir.mkdir(parents=True)
        _write_cached_card(cards_dir, "smith2017", prompt_version=1)

        config = Config(cache_dir=cache_dir, prompt_version=1)
        index = _make_index()
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
    def test_digests_force_clears_markdown_cache_but_preserves_hashes(self, tmp_path):
        cache_dir = tmp_path / "cache"
        digests_dir = cache_dir / "digests"
        digests_dir.mkdir(parents=True)
        (digests_dir / "COL1.md").write_text("cached digest", encoding="utf-8")
        (digests_dir / "COL1.json").write_text('{"hash": "abc"}', encoding="utf-8")

        config = Config(cache_dir=cache_dir)
        index = _make_index()
        runner = CliRunner()

        with (
            patch("zsum.cli._load_cfg", return_value=config),
            patch("zsum.cli.validate_config", return_value=[]),
            patch("zsum.indexer.build_index", return_value=index),
            patch("zsum.cache.load_cached_cards", return_value={}),
            patch(
                "zsum.digests.generate_digests_batch", return_value={"COL1": "digest"}
            ) as mock_gen,
        ):
            result = runner.invoke(main, ["--config", "ignored.yaml", "digests", "--force"])

        assert result.exit_code == 0, result.output
        assert "Total digests: 1" in result.output
        assert not (digests_dir / "COL1.md").exists()
        assert (digests_dir / "COL1.json").exists()
        mock_gen.assert_called_once()


class TestPreviewOutputContract:
    """Preview output contract: report includes preview sections,
    no persistent files created."""

    @pytest.mark.unit
    def test_report_includes_preview_section_with_citekey_and_excerpt(self):
        results = {
            "alpha2020": ExtractionResult(
                citekey="alpha2020",
                text="This is the extracted text about fracture mechanics.",
                page_count=5,
                pages_used=[0, 1],
                quality="good",
            ),
        }
        report = extraction_report(results)
        assert "## Text Previews" in report
        assert "**alpha2020**" in report
        assert "fracture mechanics" in report

    @pytest.mark.unit
    def test_report_includes_multiple_previews(self):
        results = {
            "aaa2020": ExtractionResult(
                citekey="aaa2020",
                text="First paper text.",
                page_count=5,
                pages_used=[0],
                quality="good",
            ),
            "bbb2021": ExtractionResult(
                citekey="bbb2021",
                text="Second paper text.",
                page_count=3,
                pages_used=[0],
                quality="degraded",
                warnings=["Short text"],
            ),
        }
        report = extraction_report(results)
        assert "**aaa2020**" in report
        assert "**bbb2021**" in report
        assert "First paper text" in report
        assert "Second paper text" in report

    @pytest.mark.unit
    def test_no_persistent_files_created(self, tmp_path):
        """extraction_report produces only a string, no files."""
        results = {
            "test2020": ExtractionResult(
                citekey="test2020",
                text="Some text here.",
                page_count=5,
                pages_used=[0],
                quality="good",
            ),
        }
        before = set(tmp_path.rglob("*"))
        _ = extraction_report(results)
        after = set(tmp_path.rglob("*"))
        assert before == after, "extraction_report should not create any files"
