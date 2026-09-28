"""Tests for Add docstrings to public API functions.

Adds one-paragraph docstrings to 4 key public API functions and
one-liner docstrings to private helpers:
  - generate_card() in cards.py
  - generate_cards_batch() in cards.py
  - generate_digest() in digests.py
  - generate_digests_batch() in digests.py

These tests verify docstring presence and basic documentation completeness.
"""

from __future__ import annotations

import inspect

import pytest

from zsum.cards import generate_card, generate_cards_batch
from zsum.cli import _load_cfg, _setup_logging
from zsum.digests import generate_digest, generate_digests_batch
from zsum.models import Item, LibraryIndex


class TestPublicApiDocstrings:
    """
    Tests for Add docstrings to public API functions
    Covers: [1] 4 public functions have paragraph docstrings,
    [2] Private helpers have one-liners
    """

    @pytest.mark.docs
    def test_generate_card_has_docstring(self):
        """
        Verifies: generate_card function has a paragraph docstring
        Covers: 4 public functions have paragraph docstrings
        Passes when: generate_card.__doc__ is not None and len > 20
        """
        assert generate_card.__doc__ is not None, "generate_card has no docstring"
        assert len(generate_card.__doc__) > 20, "generate_card docstring is too short (< 20 chars)"

    @pytest.mark.docs
    def test_generate_cards_batch_has_docstring(self):
        """
        Verifies: generate_cards_batch function has a paragraph docstring
        Covers: 4 public functions have paragraph docstrings
        Passes when: generate_cards_batch.__doc__ is not None and len > 20
        """
        assert generate_cards_batch.__doc__ is not None, "generate_cards_batch has no docstring"
        assert len(generate_cards_batch.__doc__) > 20, (
            "generate_cards_batch docstring is too short (< 20 chars)"
        )

    @pytest.mark.docs
    def test_generate_digest_has_docstring(self):
        """
        Verifies: generate_digest function has a paragraph docstring
        Covers: 4 public functions have paragraph docstrings
        Passes when: generate_digest.__doc__ is not None and len > 20
        """
        assert generate_digest.__doc__ is not None, "generate_digest has no docstring"
        assert len(generate_digest.__doc__) > 20, (
            "generate_digest docstring is too short (< 20 chars)"
        )

    @pytest.mark.docs
    def test_generate_digests_batch_has_docstring(self):
        """
        Verifies: generate_digests_batch function has a paragraph docstring
        Covers: 4 public functions have paragraph docstrings
        Passes when: generate_digests_batch.__doc__ is not None and len > 20
        """
        assert generate_digests_batch.__doc__ is not None, "generate_digests_batch has no docstring"
        assert len(generate_digests_batch.__doc__) > 20, (
            "generate_digests_batch docstring is too short (< 20 chars)"
        )

    @pytest.mark.docs
    def test_cli_setup_logging_has_docstring(self):
        """
        Verifies: cli._setup_logging has a one-liner docstring.
        Covers: cli.py private helpers documented.
        """
        assert _setup_logging.__doc__ is not None, "cli._setup_logging has no docstring"
        assert len(_setup_logging.__doc__) > 20, (
            "cli._setup_logging docstring is too short (< 20 chars)"
        )

    @pytest.mark.docs
    def test_cli_load_cfg_has_docstring(self):
        """
        Verifies: cli._load_cfg has a one-liner docstring.
        Covers: cli.py private helpers documented.
        """
        assert _load_cfg.__doc__ is not None, "cli._load_cfg has no docstring"
        assert len(_load_cfg.__doc__) > 20, "cli._load_cfg docstring is too short (< 20 chars)"

    @pytest.mark.docs
    def test_models_item_has_pdf_has_docstring(self):
        """
        Verifies: models.Item.has_pdf has a docstring.
        Covers: models.py public members documented.
        """
        assert Item.has_pdf.__doc__ is not None, "Item.has_pdf has no docstring"
        assert len(Item.has_pdf.__doc__) > 20, "Item.has_pdf docstring is too short (< 20 chars)"

    @pytest.mark.docs
    def test_models_library_index_stats_has_docstring(self):
        """
        Verifies: models.LibraryIndex.stats has a docstring.
        Covers: models.py public members documented.
        """
        assert LibraryIndex.stats.__doc__ is not None, "LibraryIndex.stats has no docstring"
        assert len(LibraryIndex.stats.__doc__) > 20, (
            "LibraryIndex.stats docstring is too short (< 20 chars)"
        )

    @pytest.mark.docs
    def test_private_helpers_have_one_liner_docstrings(self):
        """
        Verifies: private helper functions have one-liner docstrings
        Covers: Private helpers have one-liners
        Passes when: all private helpers in cards.py and digests.py have docstrings
        """
        from zsum import cards, digests

        # Collect all private functions (start with _)
        private_funcs = [
            (name, func)
            for name, func in inspect.getmembers(cards, inspect.isfunction)
            if name.startswith("_") and not name.startswith("__")
        ] + [
            (name, func)
            for name, func in inspect.getmembers(digests, inspect.isfunction)
            if name.startswith("_") and not name.startswith("__")
        ]

        for name, func in private_funcs:
            assert func.__doc__ is not None, f"Private helper {name}() has no docstring"
            # Roughly verify it's a one-liner (one sentence, < 100 chars)
            assert len(func.__doc__) < 100, (
                f"Private helper {name}() docstring is too long (should be one-liner)"
            )
