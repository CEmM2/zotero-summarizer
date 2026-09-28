"""Tests for Handle unknown keys in nested LLM config sections.

Ensures that unknown keys in anthropic or openai_compat config sections
produce a warning instead of raising TypeError, consistent with top-level
Config handling.
"""

from __future__ import annotations

import logging

import pytest

from zsum.config import load_config


class TestLlmConfigUnknownKeys:
    """
    Tests for Handle unknown keys in nested LLM config sections
    Covers: [1] Unknown keys produce warning, not TypeError
    """

    @pytest.mark.unit
    def test_unknown_key_in_anthropic_section_produces_warning(self, tmp_path, caplog):
        """
        Verifies: a typo key in llm.anthropic section produces a warning instead of TypeError
        Covers: Unknown keys produce warning, not TypeError
        Passes when: config loads successfully with a warning logged, no TypeError raised
        """
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "llm:\n"
            "  provider: anthropic\n"
            "  anthropic:\n"
            "    model: claude-3-5-sonnet-20241022\n"
            "    typo_key: should_be_ignored\n"
        )

        with caplog.at_level(logging.WARNING, logger="zsum.config"):
            cfg = load_config(config_file)

        # Should not raise — config loaded successfully
        assert cfg.llm.anthropic.model == "claude-3-5-sonnet-20241022"
        # Should have emitted a warning about the unknown key
        assert any("typo_key" in record.message for record in caplog.records)

    @pytest.mark.unit
    def test_unknown_key_in_openai_compat_section_produces_warning(self, tmp_path, caplog):
        """
        Verifies: a typo key in llm.openai_compat section produces a warning instead of TypeError
        Covers: Unknown keys produce warning, not TypeError
        Passes when: config loads successfully with a warning logged, no TypeError raised
        """
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "llm:\n"
            "  provider: openai_compat\n"
            "  openai_compat:\n"
            "    model: gpt-4o\n"
            "    unexpected_field: oops\n"
        )

        with caplog.at_level(logging.WARNING, logger="zsum.config"):
            cfg = load_config(config_file)

        # Should not raise — config loaded successfully
        assert cfg.llm.openai_compat.model == "gpt-4o"
        # Should have emitted a warning about the unknown key
        assert any("unexpected_field" in record.message for record in caplog.records)

    @pytest.mark.unit
    def test_valid_llm_config_keys_no_warning(self, tmp_path, caplog):
        """
        Verifies: valid LLM provider config keys produce no warning
        Covers: Normal config loading unaffected
        Passes when: config loads without any warnings about unknown keys in LLM sections
        """
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "llm:\n"
            "  provider: anthropic\n"
            "  anthropic:\n"
            "    model: claude-3-5-sonnet-20241022\n"
            "    max_tokens_card: 2048\n"
            "    max_tokens_digest: 4096\n"
            "    api_key_env: ANTHROPIC_API_KEY\n"
        )

        with caplog.at_level(logging.WARNING, logger="zsum.config"):
            cfg = load_config(config_file)

        # Should not raise — config loaded successfully
        assert cfg.llm.anthropic.model == "claude-3-5-sonnet-20241022"
        assert cfg.llm.anthropic.max_tokens_card == 2048
        # No warnings about unknown LLM keys
        llm_warnings = [r for r in caplog.records if "llm." in r.message and "ignored" in r.message]
        assert llm_warnings == []
