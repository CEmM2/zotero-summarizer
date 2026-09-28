"""Tests for the config module."""

from __future__ import annotations

import yaml

from zsum.config import Config, load_config, validate_config


class TestLoadConfig:
    def test_loads_defaults_from_empty_yaml(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("")
        config = load_config(cfg_path)
        assert isinstance(config, Config)
        assert config.extraction.mode == "pages"

    def test_loads_custom_values(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(yaml.dump({"prompt_version": 42}))
        config = load_config(cfg_path)
        assert config.prompt_version == 42

    def test_unknown_keys_ignored_with_warning(self, tmp_path, caplog):
        import logging

        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(yaml.dump({"nonexistent_key": "value", "another_bad": 123}))
        with caplog.at_level(logging.WARNING):
            config = load_config(cfg_path)
        assert isinstance(config, Config)
        assert "Unknown config keys" in caplog.text

    def test_expands_tilde_in_paths(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(yaml.dump({"vault_output": "~/vault"}))
        config = load_config(cfg_path)
        assert "~" not in str(config.vault_output)

    def test_loads_codex_exec_config(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(
            yaml.dump(
                {
                    "llm": {
                        "provider": "codex_exec",
                        "codex_exec": {
                            "model": "gpt-5.4",
                            "binary": "custom-codex",
                            "sandbox": "read-only",
                        },
                    }
                }
            )
        )
        config = load_config(cfg_path)
        assert config.llm.provider == "codex_exec"
        assert config.llm.routing.cards == "codex_exec"
        assert config.llm.routing.digests == "codex_exec"
        assert config.llm.routing.redigest == "codex_exec"
        assert config.llm.codex_exec.binary == "custom-codex"

    def test_legacy_provider_populates_stage_routing(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(yaml.dump({"llm": {"provider": "openai_compat"}}))

        config = load_config(cfg_path)

        assert config.llm.provider_for_stage("cards") == "openai_compat"
        assert config.llm.provider_for_stage("digests") == "openai_compat"
        assert config.llm.provider_for_stage("redigest") == "openai_compat"

    def test_explicit_routing_overrides_legacy_provider(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(
            yaml.dump(
                {
                    "llm": {
                        "provider": "anthropic",
                        "routing": {
                            "cards": "openai_compat",
                            "digests": "anthropic",
                            "redigest": "codex_exec",
                        },
                    }
                }
            )
        )

        config = load_config(cfg_path)

        assert config.llm.provider == "anthropic"
        assert config.llm.provider_for_stage("cards") == "openai_compat"
        assert config.llm.provider_for_stage("digests") == "anthropic"
        assert config.llm.provider_for_stage("redigest") == "codex_exec"

    def test_unknown_llm_routing_keys_ignored_with_warning(self, tmp_path, caplog):
        import logging

        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(
            yaml.dump(
                {
                    "llm": {
                        "provider": "anthropic",
                        "routing": {
                            "cards": "anthropic",
                            "drafts": "openai_compat",
                        },
                    }
                }
            )
        )

        with caplog.at_level(logging.WARNING):
            config = load_config(cfg_path)

        assert config.llm.provider_for_stage("cards") == "anthropic"
        assert config.llm.provider_for_stage("digests") == "anthropic"
        assert "llm.routing" in caplog.text

    def test_codex_exec_model_is_optional_for_validation(self, tmp_path):
        bbt_path = tmp_path / "zot.json"
        sql_path = tmp_path / "zot.sqlite"
        bbt_path.write_text("{}")
        sql_path.write_text("")

        config = Config(bbt_json=bbt_path, zotero_sqlite=sql_path)
        config.llm.provider = "codex_exec"
        config.llm.routing.cards = "codex_exec"
        errors = validate_config(config, require_llm=True, llm_stages=("cards",))
        assert all("LLM model not set" not in err for err in errors)

    def test_stage_aware_validation_identifies_stage_and_provider(self, tmp_path):
        bbt_path = tmp_path / "zot.json"
        sql_path = tmp_path / "zot.sqlite"
        bbt_path.write_text("{}")
        sql_path.write_text("")

        config = Config(bbt_json=bbt_path, zotero_sqlite=sql_path)
        config.llm.routing.cards = "openai_compat"
        config.llm.routing.digests = "anthropic"
        config.llm.routing.redigest = "codex_exec"

        errors = validate_config(
            config,
            require_llm=True,
            llm_stages=("cards", "digests", "redigest"),
        )

        assert any("stage 'cards' using provider 'openai_compat'" in err for err in errors)
        assert any("stage 'digests' using provider 'anthropic'" in err for err in errors)

    def test_extraction_defaults_when_block_omitted(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("")
        config = load_config(cfg_path)
        assert config.extraction.mode == "pages"
        assert "abstract" in config.extraction.target_sections
        assert "introduction" in config.extraction.target_sections
        assert config.extraction.fuzzy_threshold == 80
        assert config.notebooklm.max_sources_per_notebook == 30
        assert config.notebooklm.query_timeout == 120.0
        assert config.notebooklm.upload_timeout == 600.0
        assert config.notebooklm.cleanup is False
        assert config.notebooklm.parse_locally is False
        assert config.notebooklm.profile == ""

    def test_extraction_target_sections_and_fuzzy_threshold_load_from_yaml(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(
            yaml.dump(
                {
                    "extraction": {
                        "mode": "sections",
                        "target_sections": ["abstract", "results"],
                        "fuzzy_threshold": 72,
                    }
                }
            )
        )
        config = load_config(cfg_path)
        assert config.extraction.mode == "sections"
        assert config.extraction.target_sections == ["abstract", "results"]
        assert config.extraction.fuzzy_threshold == 72

    def test_config_example_yaml_loads_with_documented_defaults(self, tmp_path):
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent
        config = load_config(repo_root / "config.example.yaml")
        assert config.extraction.mode == "pages"
        assert config.extraction.fuzzy_threshold == 80
        assert config.notebooklm.max_sources_per_notebook == 30
        assert config.notebooklm.query_timeout == 120.0
        assert config.notebooklm.upload_timeout == 600.0
        assert config.notebooklm.cleanup is False
        assert config.notebooklm.parse_locally is False
        assert config.notebooklm.profile == ""

    def test_loads_notebooklm_config_block(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(
            yaml.dump(
                {
                    "extraction": {"mode": "notebooklm"},
                    "notebooklm": {
                        "max_sources_per_notebook": 12,
                        "query_timeout": 45.0,
                        "upload_timeout": 90.0,
                        "cleanup": True,
                        "parse_locally": True,
                        "profile": "research",
                    },
                }
            )
        )

        config = load_config(cfg_path)

        assert config.extraction.mode == "notebooklm"
        assert config.notebooklm.max_sources_per_notebook == 12
        assert config.notebooklm.query_timeout == 45.0
        assert config.notebooklm.upload_timeout == 90.0
        assert config.notebooklm.cleanup is True
        assert config.notebooklm.parse_locally is True
        assert config.notebooklm.profile == "research"
