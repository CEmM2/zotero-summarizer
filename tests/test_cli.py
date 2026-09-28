"""Tests for the CLI entry point (cli.py) using Click's CliRunner."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from click.testing import CliRunner

from zsum.cache import save_nlm_digest_keys, save_nlm_mappings, save_redigest
from zsum.cli import main
from zsum.config import load_config
from zsum.models import PaperCard
from zsum.nlm_pipeline import NLMBatchResult, NLMNotebookMapping, NLMSourceMapping


def _write_config(tmp_path: Path, bbt_json: Path, zotero_sqlite: Path) -> Path:
    """Write a minimal config.yaml to tmp_path and return its path."""
    cache_dir = tmp_path / "cache"
    vault_dir = tmp_path / "vault"
    cache_dir.mkdir(parents=True, exist_ok=True)
    vault_dir.mkdir(parents=True, exist_ok=True)

    config_content = (
        f"bbt_json: {bbt_json}\n"
        f"zotero_sqlite: {zotero_sqlite}\n"
        f"cache_dir: {cache_dir}\n"
        f"vault_output: {vault_dir}\n"
        f"generate_paper_notes: false\n"
        "llm:\n"
        "  provider: anthropic\n"
        "  anthropic:\n"
        "    model: test-model\n"
    )

    config_path = tmp_path / "config.yaml"
    config_path.write_text(config_content)
    return config_path


def _write_notebooklm_config(
    tmp_path: Path,
    bbt_json: Path,
    zotero_sqlite: Path,
    *,
    parse_locally: bool = False,
    include_llm_model: bool = True,
) -> Path:
    """Write a config.yaml with extraction.mode=notebooklm."""
    cache_dir = tmp_path / "cache"
    vault_dir = tmp_path / "vault"
    cache_dir.mkdir(parents=True, exist_ok=True)
    vault_dir.mkdir(parents=True, exist_ok=True)

    model_value = "test-model" if include_llm_model else ""
    config_content = (
        f"bbt_json: {bbt_json}\n"
        f"zotero_sqlite: {zotero_sqlite}\n"
        f"cache_dir: {cache_dir}\n"
        f"vault_output: {vault_dir}\n"
        f"generate_paper_notes: false\n"
        "llm:\n"
        "  provider: anthropic\n"
        "  anthropic:\n"
        f"    model: {json.dumps(model_value)}\n"
        "extraction:\n"
        "  mode: notebooklm\n"
        "notebooklm:\n"
        f"  parse_locally: {'true' if parse_locally else 'false'}\n"
    )

    config_path = tmp_path / "config.yaml"
    config_path.write_text(config_content)
    return config_path


class TestHelpCommand:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "zsum" in result.output

    def test_nlm_help_lists_subcommands(self):
        runner = CliRunner()
        result = runner.invoke(main, ["nlm", "--help"])
        assert result.exit_code == 0
        for command_name in ["upload", "cards", "digests", "all", "status", "cleanup"]:
            assert command_name in result.output


class TestMissingConfig:
    def test_missing_config_exits(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--config", "/nonexistent/config.yaml", "index"])
        assert result.exit_code != 0


class TestConfigValidation:
    def test_bad_bbt_path_exits_with_message(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "bbt_json: /nonexistent/zot.json\nzotero_sqlite: /nonexistent/zotero.sqlite\n"
        )
        runner = CliRunner()
        result = runner.invoke(main, ["--config", str(config_path), "index"])
        assert result.exit_code != 0
        assert "BBT JSON not found" in result.output

    def test_missing_llm_model_blocks_cards(self, tmp_path, sample_bbt_json, sample_zotero_sqlite):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            f"bbt_json: {sample_bbt_json}\n"
            f"zotero_sqlite: {sample_zotero_sqlite}\n"
            f"cache_dir: {tmp_path / 'cache'}\n"
            f"vault_output: {tmp_path / 'vault'}\n"
            "llm:\n"
            "  provider: anthropic\n"
            "  anthropic:\n"
            '    model: ""\n'
        )
        runner = CliRunner()
        result = runner.invoke(main, ["--config", str(config_path), "cards"])
        assert result.exit_code != 0
        assert "LLM model not set" in result.output

    def test_missing_llm_model_allows_skeleton(
        self, tmp_path, sample_bbt_json, sample_zotero_sqlite
    ):
        config_path = _write_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        runner = CliRunner()
        result = runner.invoke(main, ["--config", str(config_path), "skeleton"])
        assert result.exit_code == 0


class TestIndexCommand:
    def test_index_command(self, tmp_path, sample_bbt_json, sample_zotero_sqlite):
        config_path = _write_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        runner = CliRunner()
        result = runner.invoke(main, ["--config", str(config_path), "index"])
        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        assert "Items:" in result.output


class TestStatsCommand:
    def test_stats_command(self, tmp_path, sample_bbt_json, sample_zotero_sqlite):
        config_path = _write_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        runner = CliRunner()
        result = runner.invoke(main, ["--config", str(config_path), "stats"])
        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        assert "Items:" in result.output
        assert "Collections:" in result.output


class TestSkeletonCommand:
    def test_skeleton_command(self, tmp_path, sample_bbt_json, sample_zotero_sqlite):
        config_path = _write_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        vault_dir = tmp_path / "vault"
        runner = CliRunner()
        result = runner.invoke(main, ["--config", str(config_path), "skeleton"])
        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        assert (vault_dir / "Library Index.md").exists()

    def test_skeleton_creates_collection_notes(
        self, tmp_path, sample_bbt_json, sample_zotero_sqlite
    ):
        config_path = _write_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        vault_dir = tmp_path / "vault"
        runner = CliRunner()
        result = runner.invoke(main, ["--config", str(config_path), "skeleton"])
        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        collections_dir = vault_dir / "Collections"
        assert collections_dir.exists()
        md_files = list(collections_dir.glob("*.md"))
        assert len(md_files) >= 1, "skeleton should create collection markdown files"


class TestStatsOutputContent:
    def test_stats_includes_cards_and_digests(
        self, tmp_path, sample_bbt_json, sample_zotero_sqlite
    ):
        config_path = _write_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        runner = CliRunner()
        result = runner.invoke(main, ["--config", str(config_path), "stats"])
        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        assert "Cards:" in result.output
        assert "Digests:" in result.output


class TestExtractCommand:
    def test_extract_reports_quality(self, tmp_path, sample_bbt_json, sample_zotero_sqlite):
        config_path = _write_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        runner = CliRunner()
        result = runner.invoke(main, ["--config", str(config_path), "extract"])
        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        # extraction_report includes quality breakdown
        assert "Total items:" in result.output or "No PDF:" in result.output


class TestClearCacheCommand:
    def test_clear_cache_removes_cards(self, tmp_path, sample_bbt_json, sample_zotero_sqlite):
        config_path = _write_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        cache_dir = tmp_path / "cache"
        cards_dir = cache_dir / "cards"
        cards_dir.mkdir(parents=True, exist_ok=True)
        # Create a fake cached card
        (cards_dir / "fake.json").write_text(json.dumps({"citekey": "fake", "title": "Fake"}))
        assert len(list(cards_dir.glob("*.json"))) == 1

        runner = CliRunner()
        result = runner.invoke(main, ["--config", str(config_path), "clear-cache", "--cards"])
        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        assert "Cleared" in result.output
        assert len(list(cards_dir.glob("*.json"))) == 0


def _mock_llm_card_response(*args, **kwargs):
    """Return a mock LLMResponse with a valid JSON card."""
    from zsum.llm import LLMResponse

    card_json = json.dumps(
        {
            "problem": "Test problem",
            "methods": ["Method A"],
            "key_findings": ["Finding 1"],
            "limitations": ["Limitation 1"],
            "keywords": ["test"],
        }
    )
    return LLMResponse(text=card_json, model="mock", input_tokens=100, output_tokens=50)


def _mock_llm_digest_response(*args, **kwargs):
    """Return a mock LLMResponse with a digest."""
    from zsum.llm import LLMResponse

    return LLMResponse(
        text="# Collection Digest\n\nThis is a test digest.",
        model="mock",
        input_tokens=200,
        output_tokens=100,
    )


def _mock_llm_redigest_response(*args, **kwargs):
    """Return a mock LLMResponse with a final redigest."""
    from zsum.llm import LLMResponse

    return LLMResponse(
        text="## Summary\n\nThis is a refined digest.",
        model="mock",
        input_tokens=120,
        output_tokens=60,
    )


def _mock_stage_llm_response(*args, **kwargs):
    """Dispatch stage-aware mock responses for cards, digests, and redigests."""
    stage = kwargs.get("stage")
    if stage == "cards":
        return _mock_llm_card_response(*args, **kwargs)
    if stage == "digests":
        return _mock_llm_digest_response(*args, **kwargs)
    if stage == "redigest":
        return _mock_llm_redigest_response(*args, **kwargs)
    raise AssertionError(f"Unexpected LLM stage: {stage!r}")


class TestRedigestCommand:
    def test_redigest_collection_filter_refines_only_matching_collection(
        self,
        tmp_path,
        sample_bbt_json,
        sample_zotero_sqlite,
    ):
        config_path = _write_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        cache_dir = tmp_path / "cache"
        digests_dir = cache_dir / "digests"
        digests_dir.mkdir(parents=True, exist_ok=True)
        (digests_dir / "COL001.md").write_text("Draft digest for root", encoding="utf-8")
        (digests_dir / "COL002.md").write_text("Draft digest for child", encoding="utf-8")

        runner = CliRunner()
        with patch(
            "zsum.digests.generate_redigest",
            return_value="## Summary\n\nThis is a refined digest.",
        ) as mock_redigest:
            result = runner.invoke(
                main,
                [
                    "--config",
                    str(config_path),
                    "redigest",
                    "--collection",
                    "Phase Field Modeling",
                ],
            )

        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        assert (cache_dir / "redigests" / "COL001.md").exists()
        assert not (cache_dir / "redigests" / "COL002.md").exists()
        assert mock_redigest.call_count == 1

    def test_redigest_force_reruns_fresh_and_stale_outputs(
        self,
        tmp_path,
        sample_bbt_json,
        sample_zotero_sqlite,
    ):
        config_path = _write_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        cache_dir = tmp_path / "cache"
        digests_dir = cache_dir / "digests"
        digests_dir.mkdir(parents=True, exist_ok=True)
        (digests_dir / "COL001.md").write_text("Draft digest for root", encoding="utf-8")
        child_digest_path = digests_dir / "COL002.md"
        child_digest_path.write_text("Draft digest for child", encoding="utf-8")

        config = load_config(config_path)
        save_redigest("COL001", "Old refined root", "Draft digest for root", cache_dir, config)
        save_redigest("COL002", "Old refined child", "Draft digest for child", cache_dir, config)
        child_digest_path.write_text("Changed draft digest for child", encoding="utf-8")

        runner = CliRunner()
        with patch(
            "zsum.digests.generate_redigest",
            return_value="## Summary\n\nRefined digest.",
        ) as mock_redigest:
            result = runner.invoke(main, ["--config", str(config_path), "redigest", "--force"])

        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        assert mock_redigest.call_count == 2
        assert "2 generated" in result.output
        assert (
            (cache_dir / "redigests" / "COL001.md")
            .read_text(encoding="utf-8")
            .startswith("## Summary")
        )
        assert (
            (cache_dir / "redigests" / "COL002.md")
            .read_text(encoding="utf-8")
            .startswith("## Summary")
        )
        assert "Refined digest" in (cache_dir / "redigests" / "COL001.md").read_text(
            encoding="utf-8"
        )
        assert "Refined digest" in (cache_dir / "redigests" / "COL002.md").read_text(
            encoding="utf-8"
        )

    def test_redigest_warns_when_first_pass_digest_is_missing(
        self,
        tmp_path,
        sample_bbt_json,
        sample_zotero_sqlite,
    ):
        config_path = _write_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        cache_dir = tmp_path / "cache"
        digests_dir = cache_dir / "digests"
        digests_dir.mkdir(parents=True, exist_ok=True)
        (digests_dir / "COL001.md").write_text("Draft digest for root", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--config", str(config_path), "redigest", "--collection", "Bismuth-Copper"],
        )

        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        assert "Warning: no first-pass digest for 'Bismuth-Copper'" in result.output
        assert not (cache_dir / "redigests" / "COL002.md").exists()


class TestAllCommand:
    def test_all_command_runs_full_pipeline(
        self,
        tmp_path,
        sample_bbt_json,
        sample_zotero_sqlite,
    ):
        config_path = _write_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        runner = CliRunner()

        # Patch at the call sites (cards.py / digests.py / restructure.py do
        # `from .llm import complete_with_retry`, which copies the reference
        # into their own module namespace). Patching `zsum.llm.complete_with_retry`
        # alone misses these importers if they were imported before the patch
        # took effect — which happens any time test_cards.py runs first in the
        # same pytest session.
        with (
            patch("zsum.cards.complete_with_retry", side_effect=_mock_stage_llm_response),
            patch("zsum.digests.complete_with_retry", side_effect=_mock_stage_llm_response),
            patch("zsum.restructure.complete_with_retry", side_effect=_mock_stage_llm_response),
        ):
            result = runner.invoke(main, ["--config", str(config_path), "all"])

        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        # Verify pipeline stages ran
        assert "1/6 Index" in result.output
        assert "5/6 Redigest" in result.output
        assert "6/6 Publish" in result.output
        assert result.output.index("5/6 Redigest") < result.output.index("6/6 Publish")
        # Verify output reports card/digest counts
        assert "cards" in result.output.lower()
        assert "digests" in result.output.lower()
        assert "redigests" in result.output.lower()

    def test_all_command_routes_notebooklm_mode_through_nlm_pipeline(
        self,
        tmp_path,
        sample_bbt_json,
        sample_zotero_sqlite,
    ):
        config_path = _write_notebooklm_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        runner = CliRunner()

        with (
            patch("zsum.cli._run_nlm_all_stage", return_value=NLMBatchResult()) as mock_nlm_all,
            patch(
                "zsum.digests.generate_redigests_batch",
                return_value=SimpleNamespace(
                    redigests={},
                    generated=0,
                    cached=0,
                    failed=0,
                    missing_first_pass=[],
                ),
            ) as mock_redigest,
            patch("zsum.publisher.publish_vault") as mock_publish,
        ):
            result = runner.invoke(main, ["--config", str(config_path), "all"])

        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        assert "2/4 NotebookLM" in result.output
        mock_nlm_all.assert_called_once()
        mock_redigest.assert_called_once()
        mock_publish.assert_called_once()


class TestNotebookLmCommandRouting:
    def test_nlm_all_does_not_require_local_llm_when_parse_locally_false(
        self,
        tmp_path,
        sample_bbt_json,
        sample_zotero_sqlite,
    ):
        config_path = _write_notebooklm_config(
            tmp_path,
            sample_bbt_json,
            sample_zotero_sqlite,
            include_llm_model=False,
            parse_locally=False,
        )
        runner = CliRunner()

        with patch("zsum.cli._run_nlm_all_stage", return_value=NLMBatchResult()):
            result = runner.invoke(main, ["--config", str(config_path), "nlm", "all"])

        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        assert "NotebookLM complete" in result.output

    def test_cards_command_routes_to_notebooklm_stage_when_mode_selected(
        self,
        tmp_path,
        sample_bbt_json,
        sample_zotero_sqlite,
    ):
        config_path = _write_notebooklm_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        runner = CliRunner()

        with (
            patch("zsum.cli._run_nlm_cards_stage", return_value={}) as mock_nlm_cards,
            patch("zsum.cards.generate_cards_batch") as mock_generate_cards,
        ):
            result = runner.invoke(main, ["--config", str(config_path), "cards"])

        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        mock_nlm_cards.assert_called_once()
        mock_generate_cards.assert_not_called()

    def test_digests_command_routes_to_notebooklm_stage_when_mode_selected(
        self,
        tmp_path,
        sample_bbt_json,
        sample_zotero_sqlite,
    ):
        config_path = _write_notebooklm_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        runner = CliRunner()

        with (
            patch("zsum.cli._run_nlm_digests_stage", return_value={}) as mock_nlm_digests,
            patch("zsum.digests.generate_digests_batch") as mock_generate_digests,
        ):
            result = runner.invoke(main, ["--config", str(config_path), "digests"])

        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        mock_nlm_digests.assert_called_once()
        mock_generate_digests.assert_not_called()

    def test_nlm_status_reports_cached_mapping_counts(
        self,
        tmp_path,
        sample_bbt_json,
        sample_zotero_sqlite,
    ):
        config_path = _write_notebooklm_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        save_nlm_mappings(
            {
                "COL002": [
                    {
                        "collection_key": "COL002",
                        "notebook_id": "nb-1",
                        "title": "Bismuth-Copper",
                        "purpose": "collection",
                        "part_index": 1,
                        "total_parts": 1,
                        "sources": [
                            {
                                "source_id": "src-1",
                                "title": "smith2017PhaseField",
                                "kind": "paper",
                                "citekey": "smith2017PhaseField",
                            }
                        ],
                    }
                ]
            },
            tmp_path / "cache",
        )
        runner = CliRunner()

        result = runner.invoke(main, ["--config", str(config_path), "nlm", "status"])

        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        assert "NotebookLM collections: 1" in result.output
        assert "NotebookLM notebooks: 1" in result.output
        assert "NotebookLM sources: 1" in result.output

    def test_nlm_cleanup_deletes_cached_mapping_state(
        self,
        tmp_path,
        sample_bbt_json,
        sample_zotero_sqlite,
    ):
        config_path = _write_notebooklm_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        save_nlm_mappings(
            {
                "COL002": [
                    {
                        "collection_key": "COL002",
                        "notebook_id": "nb-1",
                        "title": "Bismuth-Copper",
                        "purpose": "collection",
                        "part_index": 1,
                        "total_parts": 1,
                        "sources": [],
                    }
                ]
            },
            tmp_path / "cache",
        )
        runner = CliRunner()

        with patch("zsum.nlm_pipeline.cleanup_notebooks") as mock_cleanup:
            result = runner.invoke(main, ["--config", str(config_path), "nlm", "cleanup"])

        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        mock_cleanup.assert_called_once()
        assert not (tmp_path / "cache" / "nlm_notebooks.json").exists()

    def test_cards_command_ignores_cached_non_notebooklm_cards(
        self,
        tmp_path,
        sample_bbt_json,
        sample_zotero_sqlite,
    ):
        config_path = _write_notebooklm_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        cache_dir = tmp_path / "cache"
        cards_dir = cache_dir / "cards"
        cards_dir.mkdir(parents=True, exist_ok=True)
        (cards_dir / "smith2017PhaseField.json").write_text(
            json.dumps(
                {
                    "citekey": "smith2017PhaseField",
                    "title": "Phase Field Modeling of Crack Propagation",
                    "problem": "Local cached card",
                    "extraction_method": "pages",
                    "_meta": {"prompt_version": 1},
                }
            )
        )
        save_nlm_mappings(
            {
                "COL002": [
                    {
                        "collection_key": "COL002",
                        "notebook_id": "nb-1",
                        "title": "Bismuth-Copper",
                        "purpose": "collection",
                        "part_index": 1,
                        "total_parts": 1,
                        "sources": [
                            {
                                "source_id": "src-1",
                                "title": "smith2017PhaseField",
                                "kind": "paper",
                                "citekey": "smith2017PhaseField",
                            }
                        ],
                    }
                ]
            },
            cache_dir,
        )
        runner = CliRunner()
        notebooklm_card = PaperCard(
            citekey="smith2017PhaseField",
            title="Phase Field Modeling of Crack Propagation",
            problem="NotebookLM card",
            extraction_method="notebooklm",
        )

        with patch(
            "zsum.nlm_pipeline.query_paper_card", return_value=notebooklm_card
        ) as mock_query:
            result = runner.invoke(
                main,
                [
                    "--config",
                    str(config_path),
                    "nlm",
                    "cards",
                    "--collection",
                    "Bismuth-Copper",
                ],
            )

        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        mock_query.assert_called_once()
        cached = json.loads((cards_dir / "smith2017PhaseField.json").read_text(encoding="utf-8"))
        assert cached["problem"] == "NotebookLM card"
        assert cached["extraction_method"] == "notebooklm"

    def test_digests_command_regenerates_over_cached_local_digest(
        self,
        tmp_path,
        sample_bbt_json,
        sample_zotero_sqlite,
    ):
        config_path = _write_notebooklm_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        cards_dir = tmp_path / "cache" / "cards"
        digests_dir = tmp_path / "cache" / "digests"
        cards_dir.mkdir(parents=True, exist_ok=True)
        digests_dir.mkdir(parents=True, exist_ok=True)
        (cards_dir / "smith2017PhaseField.json").write_text(
            json.dumps(
                {
                    "citekey": "smith2017PhaseField",
                    "title": "Phase Field Modeling of Crack Propagation",
                    "problem": "Local cached card",
                    "extraction_method": "pages",
                    "_meta": {"prompt_version": 1},
                }
            ),
            encoding="utf-8",
        )
        (digests_dir / "COL002.md").write_text("Local cached digest", encoding="utf-8")
        runner = CliRunner()
        notebook = NLMNotebookMapping(
            collection_key="COL002",
            notebook_id="nb-1",
            title="Bismuth-Copper",
            purpose="collection",
            part_index=1,
            total_parts=1,
            sources=[
                NLMSourceMapping(
                    source_id="src-1",
                    title="smith2017PhaseField",
                    kind="paper",
                    citekey="smith2017PhaseField",
                )
            ],
        )
        with (
            patch("zsum.nlm_pipeline.create_collection_notebooks", return_value=[notebook]),
            patch(
                "zsum.nlm_pipeline.query_collection_digest",
                return_value="NotebookLM regenerated digest",
            ) as mock_query,
        ):
            result = runner.invoke(
                main,
                [
                    "--config",
                    str(config_path),
                    "nlm",
                    "digests",
                    "--collection",
                    "Bismuth-Copper",
                ],
            )

        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        mock_query.assert_called_once()
        assert (digests_dir / "COL002.md").read_text(
            encoding="utf-8"
        ) == "NotebookLM regenerated digest"
        assert json.loads((digests_dir / "COL002_hashes.json").read_text(encoding="utf-8")) == {}

    def test_publish_in_notebooklm_mode_uses_only_manifested_digests(
        self,
        tmp_path,
        sample_bbt_json,
        sample_zotero_sqlite,
    ):
        config_path = _write_notebooklm_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        cards_dir = tmp_path / "cache" / "cards"
        digests_dir = tmp_path / "cache" / "digests"
        cards_dir.mkdir(parents=True, exist_ok=True)
        digests_dir.mkdir(parents=True, exist_ok=True)
        (cards_dir / "smith2017PhaseField.json").write_text(
            json.dumps(
                {
                    "citekey": "smith2017PhaseField",
                    "title": "Phase Field Modeling of Crack Propagation",
                    "problem": "NotebookLM card",
                    "extraction_method": "notebooklm",
                    "_meta": {"prompt_version": 1},
                }
            ),
            encoding="utf-8",
        )
        (cards_dir / "zhao2020CrackProp.json").write_text(
            json.dumps(
                {
                    "citekey": "zhao2020CrackProp",
                    "title": "Dynamic Crack Propagation in Brittle Materials",
                    "problem": "NotebookLM card outside manifested scope",
                    "extraction_method": "notebooklm",
                    "_meta": {"prompt_version": 1},
                }
            ),
            encoding="utf-8",
        )
        (digests_dir / "COL001.md").write_text("Local digest", encoding="utf-8")
        (digests_dir / "COL002.md").write_text("NotebookLM digest", encoding="utf-8")
        save_nlm_digest_keys({"COL002"}, tmp_path / "cache")
        save_redigest(
            "COL002",
            "Local redigest that should be ignored",
            "NotebookLM digest",
            tmp_path / "cache",
            load_config(config_path),
        )
        runner = CliRunner()

        with patch("zsum.publisher.publish_vault") as mock_publish:
            result = runner.invoke(main, ["--config", str(config_path), "publish"])

        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        assert mock_publish.call_args.kwargs["digests"] == {"COL002": "NotebookLM digest"}
        assert set(mock_publish.call_args.kwargs["cards"]) == {"smith2017PhaseField"}

    def test_publish_in_notebooklm_mode_includes_fallback_cards(
        self,
        tmp_path,
        sample_bbt_json,
        sample_zotero_sqlite,
    ):
        config_path = _write_notebooklm_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        cards_dir = tmp_path / "cache" / "cards"
        digests_dir = tmp_path / "cache" / "digests"
        cards_dir.mkdir(parents=True, exist_ok=True)
        digests_dir.mkdir(parents=True, exist_ok=True)
        (cards_dir / "smith2017PhaseField.json").write_text(
            json.dumps(
                {
                    "citekey": "smith2017PhaseField",
                    "title": "Phase Field Modeling of Crack Propagation",
                    "problem": "Fallback-generated card",
                    "extraction_method": "fallback_pages",
                    "_meta": {"prompt_version": 1},
                }
            ),
            encoding="utf-8",
        )
        (digests_dir / "COL002.md").write_text("NotebookLM digest", encoding="utf-8")
        save_nlm_digest_keys({"COL002"}, tmp_path / "cache")
        runner = CliRunner()

        with patch("zsum.publisher.publish_vault") as mock_publish:
            result = runner.invoke(main, ["--config", str(config_path), "publish"])

        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        assert set(mock_publish.call_args.kwargs["cards"]) == {"smith2017PhaseField"}


class TestNotebookLmFallback:
    def test_generate_nlm_fallback_cards_tags_extraction_method_and_persists(
        self, tmp_path, sample_bbt_json, sample_zotero_sqlite
    ):
        from zsum.cli import _generate_nlm_fallback_cards
        from zsum.extractor import ExtractionResult
        from zsum.indexer import build_index

        config_path = _write_notebooklm_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        cfg = load_config(config_path)
        idx = build_index(cfg)
        target_citekey = next(iter(idx.items))

        captured: dict[str, ExtractionResult] = {}

        def _fake_extract_batch(items_subset, _cfg):
            for ck, item in items_subset.items():
                captured[ck] = ExtractionResult(
                    citekey=ck,
                    text=f"fake text for {item.title}",
                    page_count=5,
                    pages_used=[0, 4],
                    quality="good",
                    warnings=[],
                    extraction_method="pages",
                )
            return captured

        def _fake_generate_cards_batch(items_subset, extractions, _cfg, _cache_dir):
            assert all(ext.extraction_method == "fallback_pages" for ext in extractions.values()), (
                "Fallback path must override extraction_method before card generation"
            )
            return {
                ck: PaperCard(
                    citekey=ck,
                    title=items_subset[ck].title,
                    problem="Fallback",
                    extraction_method=extractions[ck].extraction_method,
                )
                for ck in items_subset
            }

        with (
            patch("zsum.extractor.extract_batch", _fake_extract_batch),
            patch("zsum.cards.generate_cards_batch", _fake_generate_cards_batch),
        ):
            cards = _generate_nlm_fallback_cards([target_citekey], idx, cfg)

        assert target_citekey in cards
        assert cards[target_citekey].extraction_method == "fallback_pages"

    def test_generate_nlm_fallback_cards_skips_when_local_llm_unconfigured(
        self, tmp_path, sample_bbt_json, sample_zotero_sqlite
    ):
        from zsum.cli import _generate_nlm_fallback_cards
        from zsum.indexer import build_index

        config_path = _write_notebooklm_config(
            tmp_path,
            sample_bbt_json,
            sample_zotero_sqlite,
            include_llm_model=False,
        )
        cfg = load_config(config_path)
        idx = build_index(cfg)
        target_citekey = next(iter(idx.items))

        with (
            patch("zsum.extractor.extract_batch") as mock_extract,
            patch("zsum.cards.generate_cards_batch") as mock_cards,
        ):
            cards = _generate_nlm_fallback_cards([target_citekey], idx, cfg)

        assert cards == {}
        mock_extract.assert_not_called()
        mock_cards.assert_not_called()
