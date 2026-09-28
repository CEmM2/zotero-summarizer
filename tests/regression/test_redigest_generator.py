"""Tests for the redigest generator."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from zsum.config import CodexExecConfig, Config, LLMConfig, LLMProviderConfig, LLMRoutingConfig
from zsum.digests import generate_redigest
from zsum.llm import LLMResponse
from zsum.models import Collection, PaperCard
from zsum.prompts import load_prompt


class TestRedigestGenerator:
    """
    Tests for Add the redigest prompt and core refinement generator.
    Covers: 1, 2, 3, 4
    """

    @pytest.mark.integration
    def test_redigest_generator_returns_final_markdown_from_first_pass_digest(self):
        """
        Verifies: the redigest generator consumes a first-pass digest and returns final markdown.
        Covers: Redigest generation consumes the first-pass digest as input; redigest
        output is markdown intended for final publish use.
        Passes when: the refinement call accepts a first-pass digest payload and produces markdown
        suitable for publish without a structured-output detour.
        """
        col = Collection(key="COL1", name="Phase Field", path="Phase Field")
        cards = {
            "smith2017": PaperCard(
                citekey="smith2017",
                title="Phase Field Modeling",
                problem="Problem",
            )
        }
        config = Config(
            llm=LLMConfig(
                provider="anthropic",
                routing=LLMRoutingConfig(redigest="anthropic"),
                anthropic=LLMProviderConfig(model="claude-redigest", max_tokens_digest=777),
            )
        )
        response = LLMResponse(
            text="## Summary\nRefined digest with [[@smith2017]].\n",
            model="claude-redigest",
            input_tokens=120,
            output_tokens=45,
        )

        with patch("zsum.digests.complete_with_retry", return_value=response):
            digest = generate_redigest(
                col,
                "## Summary\nDraft digest with [[@smith2017]].",
                config,
                cards,
            )

        assert digest == "## Summary\nRefined digest with [[@smith2017]]."

    @pytest.mark.integration
    def test_redigest_generator_uses_redigest_route(self):
        """
        Verifies: redigest execution resolves through stage `redigest` instead of reusing the
        first-pass digest route.
        Covers: The generator does not depend on a global provider and uses the
        `redigest` route.
        Passes when: the refinement call selects the `redigest` provider/config path explicitly.
        """
        col = Collection(key="COL1", name="Phase Field", path="Phase Field")
        config = Config(
            llm=LLMConfig(
                provider="openai_compat",
                routing=LLMRoutingConfig(redigest="codex_exec", digests="openai_compat"),
                openai_compat=LLMProviderConfig(model="local-model", max_tokens_digest=333),
                codex_exec=CodexExecConfig(model="gpt-5.4", max_tokens_digest=654),
            )
        )
        response = LLMResponse(
            text="## Summary\nRefined digest.\n",
            model="gpt-5.4",
            input_tokens=100,
            output_tokens=30,
        )

        with patch("zsum.digests.complete_with_retry", return_value=response) as mock_complete:
            generate_redigest(col, "## Summary\nDraft digest.", config)

        assert mock_complete.call_args.kwargs["stage"] == "redigest"
        assert mock_complete.call_args.kwargs["max_tokens"] == 654

    @pytest.mark.integration
    def test_redigest_prompt_constrains_output_to_source_digest_and_context(self):
        """
        Verifies: the redigest prompt forbids invention beyond the supplied digest and collection
        context.
        Covers: The prompt explicitly discourages invention beyond the source digest
        and supplied context.
        Passes when: the prompt text clearly instructs the model to stay grounded in the provided
        digest/context and only refine style/structure.
        """
        prompt = load_prompt("collection_redigest.txt")

        assert "first-pass digest" in prompt
        assert "Do not invent claims" in prompt
        assert "Use only the supplied digest and explicitly provided collection context" in prompt
