"""Tests for Narrow except Exception; log missing citekey.

Covers:
- AC-1: Only expected exceptions (json.JSONDecodeError, KeyError, ValueError, OSError) are caught
- AC-2: Unexpected exceptions propagate without being caught
- AC-3: Missing/falsy citekey in version-matched card triggers warning log

Existing coverage: None for iter_version_matched_cards.
"""

import json
import logging
from unittest.mock import patch

import pytest

from zsum.cache import iter_version_matched_cards


class TestCardParseErrorHandling:
    """Tests for Narrow except Exception; log missing citekey."""

    @pytest.mark.unit
    def test_json_decode_error_caught(self, tmp_path, caplog):
        """
        Verifies: json.JSONDecodeError from malformed card file is caught, iteration continues.
        Covers: AC-1 (only expected exceptions caught)
        Passes when: malformed JSON card is skipped with warning, valid cards still yielded.
        """
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()

        # Write a malformed JSON file
        bad = cards_dir / "bad.json"
        bad.write_text("{ not valid json }", encoding="utf-8")

        # Write a valid card that matches the prompt version
        good = cards_dir / "good.json"
        good.write_text(
            json.dumps({"citekey": "smith2020", "_meta": {"prompt_version": 1}}),
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING, logger="zsum.cache"):
            results = list(iter_version_matched_cards(cards_dir, prompt_version=1))

        # The bad file is skipped with a warning
        assert any("bad.json" in msg for msg in caplog.messages), "Expected warning about bad.json"
        # The good card is still yielded
        assert len(results) == 1
        assert results[0][1]["citekey"] == "smith2020"

    @pytest.mark.unit
    def test_oserror_caught(self, tmp_path, caplog):
        """
        Verifies: OSError during card file read is caught, iteration continues.
        Covers: AC-1 (only expected exceptions caught)
        Passes when: OSError is logged and skipped, other cards still yielded.
        """
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()

        # Create two valid card files on disk
        card1 = cards_dir / "card1.json"
        card1.write_text(
            json.dumps({"citekey": "jones2021", "_meta": {"prompt_version": 2}}),
            encoding="utf-8",
        )
        card2 = cards_dir / "card2.json"
        card2.write_text(
            json.dumps({"citekey": "doe2022", "_meta": {"prompt_version": 2}}),
            encoding="utf-8",
        )

        original_read_text = card1.__class__.read_text

        def patched_read_text(self, *args, **kwargs):
            if self.name == "card1.json":
                raise OSError("simulated permission error")
            return original_read_text(self, *args, **kwargs)

        with (
            caplog.at_level(logging.WARNING, logger="zsum.cache"),
            patch.object(type(card1), "read_text", patched_read_text),
        ):
            results = list(iter_version_matched_cards(cards_dir, prompt_version=2))

        # The OSError card is skipped with a warning
        assert any("card1.json" in msg for msg in caplog.messages), (
            "Expected warning about card1.json"
        )
        # The other card is still yielded
        assert len(results) == 1
        assert results[0][1]["citekey"] == "doe2022"

    @pytest.mark.unit
    def test_unexpected_exception_propagates(self, tmp_path):
        """
        Verifies: Exceptions not in the narrowed set (e.g. RuntimeError) propagate out.
        Covers: AC-2 (unexpected exceptions propagate)
        Passes when: iter_version_matched_cards raises the unexpected exception.
        """
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()

        card = cards_dir / "card.json"
        card.write_text(
            json.dumps({"citekey": "test2023", "_meta": {"prompt_version": 1}}),
            encoding="utf-8",
        )

        def raise_runtime(*args, **kwargs):
            raise RuntimeError("unexpected internal error")

        with (
            patch.object(type(card), "read_text", raise_runtime),
            pytest.raises(RuntimeError, match="unexpected internal error"),
        ):
            list(iter_version_matched_cards(cards_dir, prompt_version=1))

    @pytest.mark.unit
    def test_missing_citekey_logs_warning(self, tmp_path, caplog):
        """
        Verifies: Version-matched card with missing/falsy citekey triggers warning.
        Covers: AC-3 (missing citekey logs a warning)
        Passes when: warning logged containing 'citekey' for card with citekey=None or "".
        """
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()

        # Card with empty citekey
        empty_key = cards_dir / "empty_key.json"
        empty_key.write_text(
            json.dumps({"citekey": "", "_meta": {"prompt_version": 3}}),
            encoding="utf-8",
        )

        # Card with null citekey
        null_key = cards_dir / "null_key.json"
        null_key.write_text(
            json.dumps({"citekey": None, "_meta": {"prompt_version": 3}}),
            encoding="utf-8",
        )

        # Card with missing citekey field entirely
        no_key = cards_dir / "no_key.json"
        no_key.write_text(
            json.dumps({"_meta": {"prompt_version": 3}}),
            encoding="utf-8",
        )

        # Control card with a valid citekey — should NOT trigger a warning
        valid = cards_dir / "valid.json"
        valid.write_text(
            json.dumps({"citekey": "brown2024", "_meta": {"prompt_version": 3}}),
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING, logger="zsum.cache"):
            results = list(iter_version_matched_cards(cards_dir, prompt_version=3))

        # All four files are yielded (none raise parse errors)
        assert len(results) == 4

        # Warnings logged for the three falsy-citekey cards
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_messages) == 3, (
            f"Expected 3 citekey warnings, got {len(warning_messages)}: {warning_messages}"
        )
        for msg in warning_messages:
            assert "citekey" in msg, f"Warning should mention 'citekey': {msg}"

        # Valid card must NOT have triggered a warning
        assert not any("brown2024" in m for m in caplog.messages)
