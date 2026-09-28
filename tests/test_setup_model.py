"""Tests for the setup-model command (src/zsum/setup_model.py)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click import ClickException
from click.testing import CliRunner

from zsum.cli import main
from zsum.setup_model import (
    MODEL_TIERS,
    OLLAMA_API_KEY,
    OLLAMA_ENDPOINT,
    TIER_ORDER,
    _check_ollama_installed,
    _check_ollama_running,
    _update_config,
    run_setup_model,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _invoke(args: list[str], config_path: Path | None = None) -> object:
    runner = CliRunner()
    cfg = str(config_path) if config_path else "config.yaml"
    return runner.invoke(main, ["--config", cfg, *args])


# ---------------------------------------------------------------------------
# Unit: _check_ollama_installed
# ---------------------------------------------------------------------------


class TestCheckOllamaInstalled:
    def test_found(self):
        with patch("shutil.which", return_value="/usr/local/bin/ollama"):
            assert _check_ollama_installed() is True

    def test_not_found(self):
        with patch("shutil.which", return_value=None):
            assert _check_ollama_installed() is False


# ---------------------------------------------------------------------------
# Unit: _check_ollama_running
# ---------------------------------------------------------------------------


class TestCheckOllamaRunning:
    def test_running(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            assert _check_ollama_running() is True

    def test_not_running(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result):
            assert _check_ollama_running() is False

    def test_timeout(self):
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ollama", 5)):
            assert _check_ollama_running() is False

    def test_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert _check_ollama_running() is False


# ---------------------------------------------------------------------------
# Unit: _update_config
# ---------------------------------------------------------------------------


class TestUpdateConfig:
    def test_creates_new_config(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        _update_config(config_path, "qwen2.5:7b", dry_run=False)
        data = yaml.safe_load(config_path.read_text())
        assert data["llm"]["provider"] == "openai_compat"
        assert data["llm"]["openai_compat"]["model"] == "qwen2.5:7b"
        assert data["llm"]["openai_compat"]["base_url"] == OLLAMA_ENDPOINT
        assert data["llm"]["openai_compat"]["api_key"] == OLLAMA_API_KEY

    def test_updates_existing_config_preserves_other_keys(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("bbt_json: /some/path.json\ncache_dir: ./cache\n")
        _update_config(config_path, "qwen2.5:14b", dry_run=False)
        data = yaml.safe_load(config_path.read_text())
        assert data["bbt_json"] == "/some/path.json"
        assert data["llm"]["openai_compat"]["model"] == "qwen2.5:14b"

    def test_overwrites_existing_llm_section(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("llm:\n  provider: anthropic\n  anthropic:\n    model: old\n")
        _update_config(config_path, "qwen2.5:7b", dry_run=False)
        data = yaml.safe_load(config_path.read_text())
        assert data["llm"]["provider"] == "openai_compat"

    def test_routing_set_to_openai_compat(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        _update_config(config_path, "qwen2.5:7b", dry_run=False)
        data = yaml.safe_load(config_path.read_text())
        routing = data["llm"]["routing"]
        assert routing["cards"] == "openai_compat"
        assert routing["digests"] == "openai_compat"
        assert routing["redigest"] == "openai_compat"

    def test_dry_run_does_not_write(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        _update_config(config_path, "qwen2.5:7b", dry_run=True)
        assert not config_path.exists()

    def test_max_tokens_defaults_set(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        _update_config(config_path, "qwen2.5:7b", dry_run=False)
        data = yaml.safe_load(config_path.read_text())
        oc = data["llm"]["openai_compat"]
        assert oc["max_tokens_card"] == 4096
        assert oc["max_tokens_digest"] == 8192

    def test_malformed_existing_config_reports_click_error(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("llm:\n  routing: [oops\n", encoding="utf-8")

        with pytest.raises(ClickException) as exc_info:
            _update_config(config_path, "qwen2.5:7b", dry_run=False)

        assert f"Could not parse config file {config_path}" in exc_info.value.message
        assert config_path.read_text(encoding="utf-8") == "llm:\n  routing: [oops\n"


# ---------------------------------------------------------------------------
# Unit: run_setup_model (integration of logic without Click runner)
# ---------------------------------------------------------------------------


class TestRunSetupModel:
    def _patches(self, *, installed=True, running=True, pull_ok=True, verify_ok=True):
        return [
            patch("zsum.setup_model._check_ollama_installed", return_value=installed),
            patch("zsum.setup_model._check_ollama_running", return_value=running),
            patch("zsum.setup_model._pull_model", return_value=pull_ok),
            patch("zsum.setup_model._verify_model", return_value=verify_ok),
        ]

    def test_happy_path_writes_config(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        patches = self._patches()
        for p in patches:
            p.start()
        try:
            run_setup_model(
                size="medium",
                model=None,
                list_tiers=False,
                dry_run=False,
                config_path=config_path,
            )
        finally:
            for p in patches:
                p.stop()
        assert config_path.exists()
        data = yaml.safe_load(config_path.read_text())
        assert data["llm"]["openai_compat"]["model"] == MODEL_TIERS["medium"]["model"]

    def test_custom_model_overrides_size(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        patches = self._patches()
        for p in patches:
            p.start()
        try:
            run_setup_model(
                size="small",
                model="llama3.2",
                list_tiers=False,
                dry_run=False,
                config_path=config_path,
            )
        finally:
            for p in patches:
                p.stop()
        data = yaml.safe_load(config_path.read_text())
        assert data["llm"]["openai_compat"]["model"] == "llama3.2"

    def test_ollama_not_installed_exits(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        with (
            patch("zsum.setup_model._check_ollama_installed", return_value=False),
            pytest.raises(SystemExit) as exc_info,
        ):
            run_setup_model(
                size="medium",
                model=None,
                list_tiers=False,
                dry_run=False,
                config_path=config_path,
            )
        assert exc_info.value.code == 1

    def test_ollama_not_running_exits(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        with (
            patch("zsum.setup_model._check_ollama_installed", return_value=True),
            patch("zsum.setup_model._check_ollama_running", return_value=False),
            pytest.raises(SystemExit) as exc_info,
        ):
            run_setup_model(
                size="medium",
                model=None,
                list_tiers=False,
                dry_run=False,
                config_path=config_path,
            )
        assert exc_info.value.code == 1

    def test_pull_failure_exits(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        patches = self._patches(pull_ok=False)
        for p in patches:
            p.start()
        try:
            with pytest.raises(SystemExit) as exc_info:
                run_setup_model(
                    size="medium",
                    model=None,
                    list_tiers=False,
                    dry_run=False,
                    config_path=config_path,
                )
        finally:
            for p in patches:
                p.stop()
        assert exc_info.value.code == 1

    def test_verify_failure_warns_but_does_not_exit(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        patches = self._patches(verify_ok=False)
        for p in patches:
            p.start()
        try:
            run_setup_model(
                size="medium",
                model=None,
                list_tiers=False,
                dry_run=False,
                config_path=config_path,
            )
        finally:
            for p in patches:
                p.stop()
        assert config_path.exists()

    def test_dry_run_skips_daemon_check(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        with (
            patch("zsum.setup_model._check_ollama_installed", return_value=True),
            patch("zsum.setup_model._check_ollama_running") as mock_running,
            patch("zsum.setup_model._pull_model") as mock_pull,
            patch("zsum.setup_model._verify_model") as mock_verify,
        ):
            run_setup_model(
                size="medium",
                model=None,
                list_tiers=False,
                dry_run=True,
                config_path=config_path,
            )
            mock_running.assert_not_called()
            mock_pull.assert_not_called()
            mock_verify.assert_not_called()

    def test_dry_run_does_not_write_config(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        with (
            patch("zsum.setup_model._check_ollama_installed", return_value=True),
            patch("zsum.setup_model._check_ollama_running", return_value=True),
        ):
            run_setup_model(
                size="medium",
                model=None,
                list_tiers=False,
                dry_run=True,
                config_path=config_path,
            )
        assert not config_path.exists()

    def test_dry_run_malformed_existing_config_exits_cleanly(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("llm:\n  routing: [oops\n", encoding="utf-8")
        with (
            patch("zsum.setup_model._check_ollama_installed", return_value=True),
            pytest.raises(ClickException) as exc_info,
        ):
            run_setup_model(
                size="medium",
                model=None,
                list_tiers=False,
                dry_run=True,
                config_path=config_path,
            )
        assert f"Could not parse config file {config_path}" in exc_info.value.message

    def test_list_tiers_does_not_pull(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        with patch("zsum.setup_model._pull_model") as mock_pull:
            run_setup_model(
                size="medium",
                model=None,
                list_tiers=True,
                dry_run=False,
                config_path=config_path,
            )
            mock_pull.assert_not_called()


# ---------------------------------------------------------------------------
# CLI integration via Click CliRunner
# ---------------------------------------------------------------------------


class TestSetupModelCLI:
    def test_list_flag_exits_zero(self):
        result = _invoke(["setup-model", "--list"])
        assert result.exit_code == 0
        for tier in TIER_ORDER:
            assert tier in result.output

    def test_help_shows_options(self):
        result = _invoke(["setup-model", "--help"])
        assert result.exit_code == 0
        assert "--size" in result.output
        assert "--model" in result.output
        assert "--dry-run" in result.output
        assert "--list" in result.output

    def test_invalid_size_rejected(self):
        result = _invoke(["setup-model", "--size", "enormous"])
        assert result.exit_code != 0

    def test_dry_run_no_config(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        with patch("zsum.setup_model._check_ollama_installed", return_value=True):
            result = _invoke(["setup-model", "--dry-run"], config_path=config_path)
        assert result.exit_code == 0
        assert "dry-run" in result.output

    def test_all_tiers_appear_in_list(self):
        result = _invoke(["setup-model", "--list"])
        assert result.exit_code == 0
        for tier in MODEL_TIERS:
            assert tier in result.output

    def test_model_names_appear_in_list(self):
        result = _invoke(["setup-model", "--list"])
        assert result.exit_code == 0
        for info in MODEL_TIERS.values():
            assert info["model"] in result.output

    def test_ollama_not_installed_message(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        with patch("zsum.setup_model._check_ollama_installed", return_value=False):
            result = _invoke(["setup-model"], config_path=config_path)
        assert result.exit_code != 0

    def test_happy_path_cli(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        with (
            patch("zsum.setup_model._check_ollama_installed", return_value=True),
            patch("zsum.setup_model._check_ollama_running", return_value=True),
            patch("zsum.setup_model._pull_model", return_value=True),
            patch("zsum.setup_model._verify_model", return_value=True),
        ):
            result = _invoke(["setup-model", "--size", "small"], config_path=config_path)
        assert result.exit_code == 0
        assert config_path.exists()
        data = yaml.safe_load(config_path.read_text())
        assert data["llm"]["openai_compat"]["model"] == MODEL_TIERS["small"]["model"]

    def test_custom_model_cli(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        with (
            patch("zsum.setup_model._check_ollama_installed", return_value=True),
            patch("zsum.setup_model._check_ollama_running", return_value=True),
            patch("zsum.setup_model._pull_model", return_value=True),
            patch("zsum.setup_model._verify_model", return_value=True),
        ):
            result = _invoke(["setup-model", "--model", "mistral:7b"], config_path=config_path)
        assert result.exit_code == 0
        data = yaml.safe_load(config_path.read_text())
        assert data["llm"]["openai_compat"]["model"] == "mistral:7b"

    def test_dry_run_malformed_existing_config_has_no_traceback(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("llm:\n  routing: [oops\n", encoding="utf-8")
        with patch("zsum.setup_model._check_ollama_installed", return_value=True):
            result = _invoke(["setup-model", "--dry-run"], config_path=config_path)
        assert result.exit_code != 0
        assert "Could not parse config file" in result.output
        assert "Traceback" not in result.output
