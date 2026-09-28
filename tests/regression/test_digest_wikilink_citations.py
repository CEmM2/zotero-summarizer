"""Tests for wikilink citation format in digest output.

Ensures that the digest generation system requests and produces [[@citekey]]
wikilink citations instead of the legacy (citekey) parenthetical format.
"""

from __future__ import annotations

import pytest

from zsum.prompts import load_prompt


class TestDigestWikilinkCitations:
    """
    Tests for wikilink citation format in digest output
    Covers: prompt wording for [[@citekey]] citations
    """

    @pytest.mark.unit
    def test_prompt_contains_wikilink_format(self):
        """
        Verifies: digest prompt instructs LLM to use [[@citekey]] format
        Covers: prompt contains [[@citekey]]
        Passes when: the system prompt or user prompt for digest generation
                     includes guidance on using [[@citekey]] wikilink syntax
        """
        prompt = load_prompt("collection_digest.txt")
        assert "[[@" in prompt, "Prompt must contain the wikilink prefix '[[@'"
        # The prompt should include at least one concrete wikilink example
        import re

        assert re.search(r"\[\[@\w+\]\]", prompt), (
            "Prompt must contain at least one [[@citekey]] wikilink example"
        )

    @pytest.mark.unit
    def test_prompt_excludes_parenthetical_format(self):
        """
        Verifies: digest prompt does NOT request parenthetical (citekey) format
        Covers: no parenthetical format in prompt
        Passes when: the prompt does not instruct the LLM to use (citekey) or
                     (citekey1; citekey2) citation styles
        """
        prompt = load_prompt("collection_digest.txt")
        assert "(smith2017PhaseField; zhao2020CrackProp)" not in prompt, (
            "Prompt must not contain the legacy parenthetical example "
            "'(smith2017PhaseField; zhao2020CrackProp)'"
        )
        assert "using citekeys in parentheses" not in prompt, (
            "Prompt must not instruct LLM to use citekeys in parentheses"
        )
