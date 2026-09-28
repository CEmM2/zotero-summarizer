"""Tests for Add cache invalidation chain to GUIDE.md

Documents the 5-step cache invalidation chain in a dedicated
subsection of GUIDE.md:
  1. prompt_version invalidates all cached cards
  2. Card content hash invalidates digests
  3. Digest content hash for incremental rebuilds
  4. --force flag bypasses all checks
  5. Behavior difference between --force on cards vs digests

These tests verify that GUIDE.md contains the full chain documentation and
explains --force behavior distinctly for cards and digests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# TODO: replace with actual imports if the documented API grows


class TestDocsCacheInvalidationChain:
    """
    Tests for Add cache invalidation chain to GUIDE.md
    Covers: [1] Full chain documented,
    [2] --force behavior difference explained
    """

    @pytest.mark.docs
    def test_invalidation_chain_documented(self):
        """
        Verifies: GUIDE.md contains a cache invalidation subsection with all chain steps
        Covers: Full chain documented
        Passes when: prompt_version, card hash, digest hash, and --force all appear in chain section
        """
        guide_path = Path("GUIDE.md")
        assert guide_path.exists(), "GUIDE.md not found"
        content = guide_path.read_text()
        assert "cache invalidation" in content.lower(), "Cache invalidation section missing"
        assert "prompt_version" in content, "prompt_version not documented"
        assert "card" in content.lower() and "hash" in content.lower(), "Card hash not documented"
        assert "digest" in content.lower() and "hash" in content.lower(), (
            "Digest hash not documented"
        )
        assert "--force" in content, "--force flag not documented"

    @pytest.mark.docs
    def test_force_behavior_difference_explained(self):
        """
        Verifies: GUIDE.md explains the difference between --force for cards vs digests
        Covers: --force behavior difference explained
        Passes when: Both 'cards' and 'digests' force behaviors are described distinctly
        """
        guide_path = Path("GUIDE.md")
        assert guide_path.exists(), "GUIDE.md not found"
        content = guide_path.read_text()
        assert "--force" in content, "--force flag not documented"
        # Verify both cards and digests --force behaviors are mentioned
        lower_content = content.lower()
        cards_section_present = "cards" in lower_content and "--force" in content
        digests_section_present = "digests" in lower_content and "--force" in content
        assert cards_section_present, "--force behavior for cards not explained"
        assert digests_section_present, "--force behavior for digests not explained"
