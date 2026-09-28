"""Tests for the redigest CLI command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from zsum.cache import save_redigest
from zsum.cli import main
from zsum.config import load_config


def _write_config(tmp_path: Path, bbt_json: Path, zotero_sqlite: Path) -> Path:
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
    config_path.write_text(config_content, encoding="utf-8")
    return config_path


def _mock_llm_card_response(*args, **kwargs):
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
    from zsum.llm import LLMResponse

    return LLMResponse(
        text="# Collection Digest\n\nThis is a test digest.",
        model="mock",
        input_tokens=200,
        output_tokens=100,
    )


def _mock_llm_redigest_response(*args, **kwargs):
    from zsum.llm import LLMResponse

    return LLMResponse(
        text="## Summary\n\nThis is a refined digest.",
        model="mock",
        input_tokens=120,
        output_tokens=60,
    )


def _mock_stage_llm_response(*args, **kwargs):
    stage = kwargs.get("stage")
    if stage == "cards":
        return _mock_llm_card_response(*args, **kwargs)
    if stage == "digests":
        return _mock_llm_digest_response(*args, **kwargs)
    if stage == "redigest":
        return _mock_llm_redigest_response(*args, **kwargs)
    raise AssertionError(f"Unexpected LLM stage: {stage!r}")


class TestRedigestCli:
    """
    Tests for Add `zsum redigest` and integrate redigest into `all` and publish flow.
    Covers: 1, 2, 3, 4
    """

    @pytest.mark.integration
    def test_redigest_collection_filter_refines_only_matching_collection(
        self,
        tmp_path,
        sample_bbt_json,
        sample_zotero_sqlite,
    ):
        """
        Verifies: `zsum redigest --collection <name>` refines only the targeted collection.
        Covers: `zsum redigest` works at whole-library scope and filtered collection
        scope.
        Passes when: the command refines the matching collection and leaves non-targeted digests
        untouched.
        """
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

    @pytest.mark.integration
    def test_redigest_force_reruns_fresh_and_stale_outputs(
        self,
        tmp_path,
        sample_bbt_json,
        sample_zotero_sqlite,
    ):
        """
        Verifies: `--force` reruns redigest even when an output is already fresh.
        Covers: `zsum redigest` works at whole-library scope and filtered collection
        scope.
        Passes when: the command reruns both stale and currently fresh redigests under `--force`.
        """
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
            side_effect=[
                "## Summary\n\nRefined root digest.",
                "## Summary\n\nRefined child digest.",
            ],
        ) as mock_redigest:
            result = runner.invoke(main, ["--config", str(config_path), "redigest", "--force"])

        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        assert mock_redigest.call_count == 2
        assert "2 generated" in result.output

    @pytest.mark.integration
    def test_all_pipeline_includes_redigest_before_publish(
        self,
        tmp_path,
        sample_bbt_json,
        sample_zotero_sqlite,
    ):
        """
        Verifies: the full pipeline inserts redigest before publish while keeping numbered stage
        logs stable.
        Covers: `zsum all` runs the redigest stage before publish; CLI output
        preserves the numbered-stage format expected by the plugin progress strip.
        Passes when: `zsum all` shows redigest between first-pass digests and publish with the
        expected numbered output.
        """
        config_path = _write_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        runner = CliRunner()

        with patch("zsum.llm.complete_with_retry", side_effect=_mock_stage_llm_response):
            result = runner.invoke(main, ["--config", str(config_path), "all"])

        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        assert "4/6 Digests" in result.output
        assert "5/6 Redigest" in result.output
        assert "6/6 Publish" in result.output
        assert result.output.index("5/6 Redigest") < result.output.index("6/6 Publish")

    @pytest.mark.integration
    def test_publish_prefers_fresh_redigest_and_falls_back_when_stale_or_missing(
        self,
        tmp_path,
        sample_bbt_json,
        sample_zotero_sqlite,
    ):
        """
        Verifies: publish consumes fresh redigests and falls back safely when they are stale or
        missing.
        Covers: Publish prefers fresh redigest output and safely falls back to the
        first-pass digest when necessary.
        Passes when: publish writes the refined digest only when fresh and otherwise uses the
        first-pass digest without error.
        """
        config_path = _write_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        cache_dir = tmp_path / "cache"
        digests_dir = cache_dir / "digests"
        digests_dir.mkdir(parents=True, exist_ok=True)
        root_digest = "Draft digest for root collection."
        child_digest = "Draft digest for child collection."
        (digests_dir / "COL001.md").write_text(root_digest, encoding="utf-8")
        child_digest_path = digests_dir / "COL002.md"
        child_digest_path.write_text(child_digest, encoding="utf-8")
        config = load_config(config_path)
        save_redigest(
            "COL001", "## Summary\n\nRefined root digest.", root_digest, cache_dir, config
        )
        save_redigest(
            "COL002", "## Summary\n\nOld refined child digest.", child_digest, cache_dir, config
        )
        child_digest_path.write_text("Changed child digest.", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(main, ["--config", str(config_path), "publish"])

        assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
        root_note = (tmp_path / "vault" / "Collections" / "Phase Field Modeling.md").read_text(
            encoding="utf-8"
        )
        child_note = (tmp_path / "vault" / "Collections" / "Bismuth-Copper.md").read_text(
            encoding="utf-8"
        )
        assert "Refined root digest" in root_note
        assert "Changed child digest" in child_note
        assert "Old refined child digest" not in child_note
