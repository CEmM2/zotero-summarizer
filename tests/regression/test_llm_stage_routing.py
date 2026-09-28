"""Tests for per-stage LLM routing (cards/digests/redigest)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from tests.helpers import make_test_item as _make_item
from zsum.cards import generate_card
from zsum.config import CodexExecConfig, Config, LLMConfig, LLMProviderConfig, LLMRoutingConfig
from zsum.digests import generate_digest
from zsum.extractor import ExtractionResult
from zsum.llm import LLMResponse
from zsum.models import Collection, PaperCard


class TestLlmStageRouting:
    """
    Tests for Refactor LLM dispatch and generation callers to resolve provider by
    stage.
    Covers: 1, 2, 3
    """

    @pytest.mark.integration
    def test_cards_and_first_pass_digests_use_stage_specific_provider_config(self):
        """
        Verifies: cards resolve through stage `cards` and first-pass digests resolve through stage
        `digests` when one config routes them to different providers.
        Covers: Cards resolve provider/config through stage `cards`; first-pass
        digests resolve provider/config through stage `digests`; refactored dispatch still
        supports Anthropic, OpenAI-compatible, and Codex providers.
        Passes when: both code paths select the routed provider-specific config without reading a
        single global provider field.
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
        assert mock_card_complete.call_args.kwargs["max_tokens"] == 321
        assert mock_digest_complete.call_args.kwargs["stage"] == "digests"
        assert mock_digest_complete.call_args.kwargs["max_tokens"] == 654
        assert mock_digest_complete.call_args.kwargs["output_schema"]["type"] == "object"
