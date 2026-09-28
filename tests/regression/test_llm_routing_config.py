"""Tests for stage-specific LLM provider routing configuration."""

from __future__ import annotations

import logging

import pytest
import yaml

from zsum.config import load_config, validate_config


class TestLlmRoutingConfig:
    """
    Tests for Extend `LLMConfig` with stage routing and legacy fallback loading.
    Covers: 1, 2, 3, 4
    """

    @pytest.mark.unit
    def test_legacy_llm_provider_only_populates_stage_routing_defaults(self, tmp_path):
        """
        Verifies: configs with only `llm.provider` hydrate routing defaults for cards, digests,
        and redigest.
        Covers: Configs that only define `llm.provider` still load without
        modification; loaded config objects expose explicit routing values for cards, digests,
        and redigest.
        Passes when: loading a legacy config preserves behavior and all stage routes inherit the
        legacy provider.
        """
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump({"llm": {"provider": "openai_compat"}}), encoding="utf-8")

        config = load_config(config_path)

        assert config.llm.provider == "openai_compat"
        assert config.llm.provider_for_stage("cards") == "openai_compat"
        assert config.llm.provider_for_stage("digests") == "openai_compat"
        assert config.llm.provider_for_stage("redigest") == "openai_compat"

    @pytest.mark.unit
    def test_explicit_llm_routing_overrides_legacy_provider(self, tmp_path):
        """
        Verifies: an explicit `llm.routing` block overrides the legacy provider field per stage.
        Covers: Loaded config objects expose explicit routing values for cards,
        digests, and redigest.
        Passes when: routed stage values win over the legacy provider and remain accessible on the
        loaded config object.
        """
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "llm": {
                        "provider": "anthropic",
                        "routing": {
                            "cards": "codex_exec",
                            "digests": "openai_compat",
                            "redigest": "anthropic",
                        },
                    }
                }
            ),
            encoding="utf-8",
        )

        config = load_config(config_path)

        assert config.llm.provider == "anthropic"
        assert config.llm.provider_for_stage("cards") == "codex_exec"
        assert config.llm.provider_for_stage("digests") == "openai_compat"
        assert config.llm.provider_for_stage("redigest") == "anthropic"

    @pytest.mark.unit
    def test_stage_aware_validation_requires_models_for_anthropic_and_openai_compat(self, tmp_path):
        """
        Verifies: stage-aware validation still rejects missing models for Anthropic and
        OpenAI-compatible routes while keeping Codex model optional.
        Covers: Codex model remains optional while stage-aware validation still
        rejects missing models for Anthropic and OpenAI-compatible stages.
        Passes when: validation failures identify missing routed models without flagging an empty
        Codex model.
        """
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "llm": {
                        "provider": "codex_exec",
                        "routing": {
                            "cards": "anthropic",
                            "digests": "openai_compat",
                            "redigest": "codex_exec",
                        },
                        "anthropic": {"model": ""},
                        "openai_compat": {"model": ""},
                        "codex_exec": {"model": ""},
                    }
                }
            ),
            encoding="utf-8",
        )

        config = load_config(config_path)
        errors = validate_config(
            config,
            require_llm=True,
            llm_stages=("cards", "digests", "redigest"),
        )

        assert any("stage 'cards' using provider 'anthropic'" in err for err in errors)
        assert any("stage 'digests' using provider 'openai_compat'" in err for err in errors)
        assert all("redigest" not in err for err in errors)

    @pytest.mark.unit
    def test_unknown_llm_routing_keys_warn_and_are_ignored(self, tmp_path, caplog):
        """
        Verifies: unknown keys under `llm.routing` warn but do not break config loading.
        Covers: Unknown keys under `llm.routing` are ignored with a warning instead
        of breaking load.
        Passes when: the config loads successfully, the warning is emitted, and only supported
        routing keys are retained.
        """
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "llm": {
                        "provider": "anthropic",
                        "routing": {
                            "cards": "openai_compat",
                            "drafts": "codex_exec",
                        },
                    }
                }
            ),
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING):
            config = load_config(config_path)

        assert config.llm.provider_for_stage("cards") == "openai_compat"
        assert config.llm.provider_for_stage("digests") == "anthropic"
        assert config.llm.provider_for_stage("redigest") == "anthropic"
        assert "Unknown config keys in llm.routing ignored" in caplog.text
