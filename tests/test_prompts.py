"""Tests for the prompts module."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from zsum.prompts import load_prompt


class TestLoadPromptDefaults:
    def test_loads_paper_card_default(self):
        result = load_prompt("paper_card.txt")
        assert result
        assert "JSON" in result

    def test_loads_digest_default(self):
        result = load_prompt("collection_digest.txt")
        assert result
        assert "digest" in result.lower()

    def test_loads_structured_digest_default(self):
        result = load_prompt("collection_digest_structured.txt")
        assert result
        assert "structured content" in result.lower()

    def test_missing_prompt_raises(self):
        with pytest.raises(FileNotFoundError, match="nonexistent.txt"):
            load_prompt("nonexistent.txt")


class TestLoadPromptCwdOverride:
    def test_cwd_override(self, tmp_path, monkeypatch):
        """CWD prompts/ (tier 2) is used when package data (tier 1) is unavailable."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "paper_card.txt").write_text("custom prompt content")
        monkeypatch.chdir(tmp_path)

        # Disable tier 1 so tier 2 (CWD) is reached
        with patch("zsum.prompts.pkg_resources.files", side_effect=ModuleNotFoundError):
            result = load_prompt("paper_card.txt")
        assert result == "custom prompt content"


class TestZsumPromptDirEnvVar:
    """Tier 0: the ZSUM_PROMPT_DIR env-var overlay.

    The env var must override every other tier — including the
    package-data (tier 1) one — when it is set and the file exists.
    When unset or when the file is absent inside the dir, behaviour is
    strictly additive: every existing tier falls through unchanged.
    """

    def test_zsum_prompt_dir_env_var_takes_priority(self, tmp_path, monkeypatch):
        # Stage an overlay prompt under ZSUM_PROMPT_DIR.
        overlay = tmp_path / "overlay_prompts"
        overlay.mkdir()
        (overlay / "paper_card.txt").write_text("OVERLAY")
        monkeypatch.setenv("ZSUM_PROMPT_DIR", str(overlay))

        # Even with package data + CWD-prompts available, the overlay wins.
        result = load_prompt("paper_card.txt")
        assert result == "OVERLAY"

    def test_zsum_falls_back_when_env_dir_missing_file(self, tmp_path, monkeypatch):
        # ZSUM_PROMPT_DIR is set but the file is not inside it.
        overlay = tmp_path / "empty_overlay"
        overlay.mkdir()
        monkeypatch.setenv("ZSUM_PROMPT_DIR", str(overlay))

        # Package data tier 1 still provides paper_card.txt.
        result = load_prompt("paper_card.txt")
        assert result
        assert "OVERLAY" not in result  # came from tier 1 or 3, not tier 0

    def test_zsum_unset_env_dir_is_no_op(self, tmp_path, monkeypatch):
        """When ZSUM_PROMPT_DIR is unset the existing 3-tier chain is unchanged."""
        monkeypatch.delenv("ZSUM_PROMPT_DIR", raising=False)
        # Tier 1 should still serve the default paper card.
        result = load_prompt("paper_card.txt")
        assert result
        assert "JSON" in result  # baseline assertion from existing tests
