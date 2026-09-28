"""Tests for Config warning: include valid keys; module-level constant.

Covers:
- AC-1: Unknown key warning shows valid alternatives
- AC-2: _LLM_PROVIDER_FIELDS defined at module level
- AC-3: Existing config tests pass

Existing coverage (partial):
- test_MR_L2_T.py::test_unknown_key_in_anthropic_section_produces_warning: warning produced
  (no valid key check)
- test_config.py::test_unknown_keys_ignored_with_warning: top-level keys only
"""

import dataclasses
import logging

import pytest

from zsum.config import _LLM_PROVIDER_FIELDS, LLMProviderConfig, load_config


class TestConfigWarningValidKeys:
    """Tests for Config warning: valid keys; module-level constant."""

    @pytest.mark.unit
    def test_unknown_key_warning_includes_valid_keys(self, tmp_path, caplog):
        """
        Verifies: Unknown LLM provider key warning message includes valid alternatives.
        Covers: AC-1 (warning shows valid keys)
        Passes when: warning message contains at least 'model' and 'max_tokens_card'.
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

        # Config should still load successfully
        assert cfg.llm.anthropic.model == "claude-3-5-sonnet-20241022"

        # Warning should be present and mention the llm.anthropic section
        warning_messages = [r.message for r in caplog.records if "llm.anthropic" in r.message]
        assert warning_messages, "Expected a warning about unknown key in llm.anthropic"
        warning_text = warning_messages[0]

        # AC-1: warning must include valid keys hint
        assert "valid keys" in warning_text, (
            f"Expected 'valid keys' in warning, got: {warning_text!r}"
        )
        # At minimum, 'model' and 'max_tokens_card' must appear as valid key names
        assert "model" in warning_text, (
            f"Expected 'model' in valid keys hint, got: {warning_text!r}"
        )
        assert "max_tokens_card" in warning_text, (
            f"Expected 'max_tokens_card' in valid keys hint, got: {warning_text!r}"
        )

    @pytest.mark.unit
    def test_llm_provider_fields_module_constant(self):
        """
        Verifies: _LLM_PROVIDER_FIELDS is a frozenset at module level with correct fields.
        Covers: AC-2 (_LLM_PROVIDER_FIELDS defined at module level)
        Passes when: type is frozenset and contains all LLMProviderConfig field names.
        """
        # AC-2: must be a frozenset
        assert isinstance(_LLM_PROVIDER_FIELDS, frozenset), (
            f"Expected frozenset, got {type(_LLM_PROVIDER_FIELDS)}"
        )

        # Must contain exactly the field names of LLMProviderConfig
        expected = frozenset(f.name for f in dataclasses.fields(LLMProviderConfig))
        assert expected == _LLM_PROVIDER_FIELDS, (
            f"_LLM_PROVIDER_FIELDS {_LLM_PROVIDER_FIELDS!r} != expected {expected!r}"
        )

        # Spot-check the six known fields
        for field_name in (
            "model",
            "max_tokens_card",
            "max_tokens_digest",
            "api_key_env",
            "base_url",
            "api_key",
        ):
            assert field_name in _LLM_PROVIDER_FIELDS, (
                f"Expected '{field_name}' in _LLM_PROVIDER_FIELDS"
            )
