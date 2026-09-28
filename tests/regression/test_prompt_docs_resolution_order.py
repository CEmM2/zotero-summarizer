"""Tests for Rewrite prompt resolution order in prompt docs.

Corrects the prompt resolution tier order in docs/guide/prompts.md to match
the actual 3-tier resolution implemented in zsum.prompts.load_prompt():
  1. Package data via importlib.resources (installed .txt files)
  2. CWD prompts/ directory (user override mechanism)
  3. Hardcoded fallback defaults

These tests verify that the documentation correctly describes all 3 tiers in the right order
and explains CWD as an override, not the primary path.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


class TestPromptDocsResolutionOrder:
    """
    Tests for Rewrite prompt resolution order in prompt docs
    Covers: [1, 2]
    """

    @pytest.fixture
    def prompts_guide_path(self) -> Path:
        """Locate the prompt customization guide."""
        # Start from the test file location and navigate to project root
        test_dir = Path(__file__).parent.parent.parent
        guide = test_dir / "docs" / "guide" / "prompts.md"
        assert guide.exists(), f"Prompt guide not found at {guide}"
        return guide

    @pytest.mark.regression
    def test_three_tiers_described_in_correct_order(self, prompts_guide_path: Path):
        """
        Verify that prompt docs describe all 3 prompt resolution tiers in the correct order:
          1. Package data (importlib.resources)
          2. CWD prompts/ directory
          3. Hardcoded fallback

        Anchored on the numbered-list markers `1.`, `2.`, `3.` so the check is robust to
        wording changes within each tier and to the appearance of the same keywords
        elsewhere in the section.
        """
        content = prompts_guide_path.read_text(encoding="utf-8")
        section_match = re.search(r"## Resolution Order.*?(?=\n## |\Z)", content, re.DOTALL)
        assert section_match, "Resolution Order section not found"
        prompt_section = section_match.group(0).lower()

        # Grab the first line of each numbered tier. Each must start at the beginning of
        # a line (after the section heading), be prefixed `1.` / `2.` / `3.`, and end at
        # the next newline.
        tier_lines = re.findall(r"^(\d)\.\s*(.*)$", prompt_section, flags=re.MULTILINE)
        numbered = {int(idx): body for idx, body in tier_lines}
        assert {1, 2, 3} <= set(numbered), (
            f"Expected enumerated tiers 1., 2., 3. in Customizing Prompts section; "
            f"found {sorted(numbered)}"
        )

        tier1, tier2, tier3 = numbered[1], numbered[2], numbered[3]
        assert "package" in tier1, f"Tier 1 should describe package data, got: {tier1!r}"
        assert "cwd" in tier2 or "prompts/" in tier2 or "current working directory" in tier2, (
            f"Tier 2 should describe CWD prompts/ directory, got: {tier2!r}"
        )
        assert "fallback" in tier3 or "built-in" in tier3, (
            f"Tier 3 should describe hardcoded fallback, got: {tier3!r}"
        )

    @pytest.mark.regression
    def test_cwd_described_as_override_mechanism(self, prompts_guide_path: Path):
        """
        Verify that prompt docs describe CWD prompts/ as an override mechanism,
        not the primary resolution path.

        Casing is normalized via a single `.lower()` call on the section text so the
        check does not depend on whether the docs say "CWD" or "cwd".
        """
        content = prompts_guide_path.read_text(encoding="utf-8")
        section_match = re.search(r"## Resolution Order.*?(?=\n## |\Z)", content, re.DOTALL)
        assert section_match, "Resolution Order section not found"
        prompt_section = section_match.group(0).lower()

        override_keywords = ("override", "custom", "customize", "user-provided", "copy")
        assert any(kw in prompt_section for kw in override_keywords), (
            f"CWD not described as override mechanism. Expected one of {override_keywords}"
        )

        # Verify that the word "primary" is attached to the *package data* tier, not CWD.
        tier_lines = dict(re.findall(r"^(\d)\.\s*(.*)$", prompt_section, flags=re.MULTILINE))
        assert "primary" not in tier_lines.get("2", ""), (
            "Tier 2 (CWD prompts/) should not be described as the primary path"
        )
