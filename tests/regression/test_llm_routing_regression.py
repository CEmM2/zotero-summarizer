"""Regression tests locking the LLM routing contract."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
import yaml

from tests.helpers import make_test_item as _make_item
from zsum.cards import generate_card
from zsum.config import (
    CodexExecConfig,
    Config,
    LLMConfig,
    LLMProviderConfig,
    LLMRoutingConfig,
    load_config,
    validate_config,
)
from zsum.digests import generate_digest
from zsum.extractor import ExtractionResult
from zsum.llm import LLMResponse
from zsum.models import Collection, PaperCard


class TestLlmRoutingRegression:
    """
    Tests for Add routing compatibility and stage-aware validation tests.
    Covers: 1, 2, 3, 4
    """

    @pytest.mark.regression
    def test_legacy_provider_and_explicit_routing_regressions_pass(self, tmp_path):
        """
        Verifies: legacy-provider configs still load and explicit routing overrides continue to
        pass after the routing refactor.
        Covers: The test suite proves old configs still work.
        Passes when: both legacy and routed config fixtures pass the updated config and LLM
        baseline checks.
        """
        bbt_path = tmp_path / "zot.json"
        sql_path = tmp_path / "zot.sqlite"
        bbt_path.write_text("{}")
        sql_path.write_text("")

        legacy_config = load_config(
            _write_config(
                tmp_path / "legacy.yaml",
                {
                    "bbt_json": str(bbt_path),
                    "zotero_sqlite": str(sql_path),
                    "llm": {
                        "provider": "openai_compat",
                        "openai_compat": {"model": "local-model"},
                    },
                },
            )
        )
        routed_config = load_config(
            _write_config(
                tmp_path / "routed.yaml",
                {
                    "bbt_json": str(bbt_path),
                    "zotero_sqlite": str(sql_path),
                    "llm": {
                        "provider": "anthropic",
                        "routing": {
                            "cards": "anthropic",
                            "digests": "openai_compat",
                            "redigest": "codex_exec",
                        },
                        "anthropic": {"model": "claude-sonnet"},
                        "openai_compat": {"model": "local-model"},
                        "codex_exec": {"model": "gpt-5.4"},
                    },
                },
            )
        )

        assert legacy_config.llm.provider_for_stage("cards") == "openai_compat"
        assert legacy_config.llm.provider_for_stage("digests") == "openai_compat"
        assert (
            validate_config(legacy_config, require_llm=True, llm_stages=("cards", "digests")) == []
        )
        assert routed_config.llm.provider_for_stage("cards") == "anthropic"
        assert routed_config.llm.provider_for_stage("digests") == "openai_compat"
        assert routed_config.llm.provider_for_stage("redigest") == "codex_exec"
        assert (
            validate_config(routed_config, require_llm=True, llm_stages=("cards", "digests")) == []
        )

    @pytest.mark.regression
    def test_divergent_cards_and_digests_routes_coexist(self):
        """
        Verifies: cards and first-pass digests can coexist with different routed providers in one
        config.
        Covers: The test suite proves divergent routes can coexist across stages.
        Passes when: the stage-specific dispatch path for each generator uses the intended routed
        provider without cross-talk.
        """
        config = Config(
            llm=LLMConfig(
                provider="anthropic",
                routing=LLMRoutingConfig(
                    cards="openai_compat",
                    digests="codex_exec",
                    redigest="anthropic",
                ),
                openai_compat=LLMProviderConfig(model="local-model", max_tokens_card=321),
                codex_exec=CodexExecConfig(model="gpt-5.4", max_tokens_digest=654),
            )
        )
        item = _make_item()
        extraction = ExtractionResult(
            citekey=item.citekey,
            text="Some extracted text about fracture.",
            page_count=10,
            pages_used=[0, 1, 2],
            quality="good",
        )
        cards = {
            item.citekey: PaperCard(
                citekey=item.citekey,
                title=item.title,
                authors=item.authors,
                year=item.year,
                venue=item.venue,
                doi=item.doi,
                problem="Problem",
                methods=["Method"],
                key_findings=["Finding"],
                limitations=["Limitation"],
                keywords=["keyword"],
                text_quality="good",
            )
        }
        collection = Collection(
            key="COL1",
            name="Phase Field",
            path="Phase Field",
            item_citekeys=[item.citekey],
        )

        with patch(
            "zsum.cards.complete_with_retry",
            return_value=LLMResponse(
                text=json.dumps(
                    {
                        "problem": "Problem",
                        "methods": ["Method"],
                        "key_findings": ["Finding"],
                        "limitations": ["Limitation"],
                        "keywords": ["keyword"],
                    }
                ),
                model="local-model",
                input_tokens=10,
                output_tokens=5,
            ),
        ) as mock_card_complete:
            generate_card(item, extraction, config)

        with patch(
            "zsum.digests.complete_with_retry",
            return_value=LLMResponse(
                text=json.dumps(
                    {
                        "summary": "This collection studies fracture [[@smith2017]].",
                        "key_themes": ["Theme"],
                        "common_methods": ["Method"],
                        "gaps_and_limitations": ["Gap"],
                    }
                ),
                model="gpt-5.4",
                input_tokens=12,
                output_tokens=6,
            ),
        ) as mock_digest_complete:
            generate_digest(collection, cards, config)

        assert mock_card_complete.call_args.kwargs["stage"] == "cards"
        assert mock_digest_complete.call_args.kwargs["stage"] == "digests"

    @pytest.mark.regression
    def test_stage_aware_validation_errors_identify_stage_and_provider(self, tmp_path):
        """
        Verifies: misconfigured routed providers produce validation failures that name the
        relevant stage/provider combination.
        Covers: Validation failures identify the misconfigured stage/provider
        combination; later work can rely on these tests to detect routing regressions immediately.
        Passes when: the failure message is specific enough to diagnose the routed stage and
        provider that is invalid.
        """
        bbt_path = tmp_path / "zot.json"
        sql_path = tmp_path / "zot.sqlite"
        bbt_path.write_text("{}")
        sql_path.write_text("")

        config = Config(
            bbt_json=bbt_path,
            zotero_sqlite=sql_path,
            llm=LLMConfig(
                provider="anthropic",
                routing=LLMRoutingConfig(
                    cards="openai_compat",
                    digests="anthropic",
                    redigest="codex_exec",
                ),
            ),
        )

        errors = validate_config(
            config,
            require_llm=True,
            llm_stages=("cards", "digests", "redigest"),
        )

        assert any("stage 'cards' using provider 'openai_compat'" in err for err in errors)
        assert any("stage 'digests' using provider 'anthropic'" in err for err in errors)
        assert all("redigest" not in err for err in errors)


def _write_config(path, payload):
    path.write_text(yaml.dump(payload), encoding="utf-8")
    return path
