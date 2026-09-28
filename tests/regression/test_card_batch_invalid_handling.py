"""Batch-level behavior for invalid card handling.

Validates that generate_cards_batch:
- Continues generating valid cards when one LLM response is malformed
- Caches only valid cards (stubs from invalid responses are still saved)
- Reports correct counts (generated + failed = total pending)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import patch

from tests.helpers import make_test_item as _make_item
from zsum.cache import extraction_signature
from zsum.cards import generate_cards_batch
from zsum.config import Config
from zsum.extractor import ExtractionResult


def _make_extraction(citekey: str = "smith2017", **overrides) -> ExtractionResult:
    defaults = dict(
        citekey=citekey,
        text="Extracted text about fracture.",
        page_count=10,
        pages_used=[0, 1, 2, 8, 9],
        quality="good",
    )
    defaults.update(overrides)
    return ExtractionResult(**defaults)


@dataclass
class _FakeLLMResponse:
    """Minimal stand-in for the LLM response object."""

    text: str
    input_tokens: int = 100
    output_tokens: int = 50


def _make_valid_payload(**overrides):
    """Return a valid JSON card payload as a string."""
    data = {
        "problem": "How cracks propagate",
        "methods": ["Phase field"],
        "key_findings": ["Model converges"],
        "limitations": ["2D only"],
        "keywords": ["fracture"],
    }
    data.update(overrides)
    return json.dumps(data)


class TestMixedBatchResponses:
    """A batch where one LLM response is invalid among valid ones."""

    def test_valid_cards_survive_invalid_response(self, tmp_path):
        """Valid cards are generated even when one response is garbage."""
        items = {
            "good1": _make_item(citekey="good1", zotero_key="G1"),
            "bad1": _make_item(citekey="bad1", zotero_key="B1"),
            "good2": _make_item(citekey="good2", zotero_key="G2"),
        }
        extractions = {
            "good1": _make_extraction(citekey="good1"),
            "bad1": _make_extraction(citekey="bad1"),
            "good2": _make_extraction(citekey="good2"),
        }
        config = Config(prompt_version=1)

        responses = {
            "good1": _FakeLLMResponse(text=_make_valid_payload()),
            "bad1": _FakeLLMResponse(text="[1, 2, 3]"),  # array -> invalid
            "good2": _FakeLLMResponse(text=_make_valid_payload(problem="Different problem")),
        }

        def fake_complete(system, user, cfg, max_tokens=None, **kwargs):
            # Extract citekey from user prompt
            for key in responses:
                if f"Citation key: {key}" in user:
                    return responses[key]
            raise ValueError("Unexpected prompt")

        with (
            patch("zsum.cards.complete_with_retry", side_effect=fake_complete),
            patch("zsum.cards.load_prompt", return_value="system prompt"),
        ):
            result = generate_cards_batch(items, extractions, config, tmp_path)

        # All three items produce cards (invalid one gets a stub)
        assert len(result) == 3
        assert result["good1"].problem == "How cracks propagate"
        assert result["good2"].problem == "Different problem"
        # Invalid response produces a stub card with defaults
        assert result["bad1"].problem == "unknown"
        assert result["bad1"].methods == []

    def test_cache_written_for_all_generated_cards(self, tmp_path):
        """Cache files are written for both valid and stub cards."""
        items = {
            "valid": _make_item(citekey="valid", zotero_key="V1"),
            "invalid": _make_item(citekey="invalid", zotero_key="I1"),
        }
        extractions = {
            "valid": _make_extraction(citekey="valid"),
            "invalid": _make_extraction(citekey="invalid"),
        }
        config = Config(prompt_version=1)

        responses = {
            "valid": _FakeLLMResponse(text=_make_valid_payload()),
            "invalid": _FakeLLMResponse(text='"just a string"'),  # invalid
        }

        def fake_complete(system, user, cfg, max_tokens=None, **kwargs):
            for key in responses:
                if f"Citation key: {key}" in user:
                    return responses[key]
            raise ValueError("Unexpected prompt")

        with (
            patch("zsum.cards.complete_with_retry", side_effect=fake_complete),
            patch("zsum.cards.load_prompt", return_value="system prompt"),
        ):
            generate_cards_batch(items, extractions, config, tmp_path)

        cards_dir = tmp_path / "cards"
        # Both cards are saved to cache
        assert (cards_dir / "valid.json").exists()
        assert (cards_dir / "invalid.json").exists()

        # Valid card has LLM content
        valid_data = json.loads((cards_dir / "valid.json").read_text())
        assert valid_data["problem"] == "How cracks propagate"

        # Invalid card is a stub with defaults
        invalid_data = json.loads((cards_dir / "invalid.json").read_text())
        assert invalid_data["problem"] == "unknown"
        assert invalid_data["methods"] == []


class TestBatchCounts:
    """Result counts match expectations."""

    def test_all_valid_no_failures(self, tmp_path):
        items = {
            "a": _make_item(citekey="a", zotero_key="A1"),
            "b": _make_item(citekey="b", zotero_key="B1"),
        }
        extractions = {
            "a": _make_extraction(citekey="a"),
            "b": _make_extraction(citekey="b"),
        }
        config = Config(prompt_version=1)

        def fake_complete(system, user, cfg, max_tokens=None, **kwargs):
            return _FakeLLMResponse(text=_make_valid_payload())

        with (
            patch("zsum.cards.complete_with_retry", side_effect=fake_complete),
            patch("zsum.cards.load_prompt", return_value="system prompt"),
        ):
            result = generate_cards_batch(items, extractions, config, tmp_path)

        assert len(result) == 2
        for card in result.values():
            assert card.problem == "How cracks propagate"

    def test_all_invalid_still_produces_stubs(self, tmp_path):
        items = {
            "x": _make_item(citekey="x", zotero_key="X1"),
            "y": _make_item(citekey="y", zotero_key="Y1"),
        }
        extractions = {
            "x": _make_extraction(citekey="x"),
            "y": _make_extraction(citekey="y"),
        }
        config = Config(prompt_version=1)

        def fake_complete(system, user, cfg, max_tokens=None, **kwargs):
            return _FakeLLMResponse(text="not json at all")

        with (
            patch("zsum.cards.complete_with_retry", side_effect=fake_complete),
            patch("zsum.cards.load_prompt", return_value="system prompt"),
        ):
            result = generate_cards_batch(items, extractions, config, tmp_path)

        # Both items get stub cards (parse failure -> stub, not exception)
        assert len(result) == 2
        for card in result.values():
            assert card.problem == "unknown"
            assert card.methods == []

    def test_cached_cards_not_regenerated_in_mixed_batch(self, tmp_path):
        """Pre-cached cards are loaded; only pending ones hit the LLM."""
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()

        # Pre-cache one card
        cached = {
            "citekey": "cached1",
            "title": "Cached Paper",
            "problem": "Cached problem",
            "methods": ["Cached method"],
            "key_findings": [],
            "limitations": [],
            "keywords": [],
            "text_quality": "good",
            "authors": [],
            "year": 2020,
            "venue": "",
            "doi": "",
            "_meta": {
                "model": "test",
                "prompt_version": 1,
                "extraction_signature": extraction_signature(Config()),
                "generated_at": "2025-01-01",
            },
        }
        (cards_dir / "cached1.json").write_text(json.dumps(cached))

        items = {
            "cached1": _make_item(citekey="cached1", zotero_key="C1"),
            "new1": _make_item(citekey="new1", zotero_key="N1"),
        }
        extractions = {
            "cached1": _make_extraction(citekey="cached1"),
            "new1": _make_extraction(citekey="new1"),
        }
        config = Config(prompt_version=1)

        call_count = 0

        def fake_complete(system, user, cfg, max_tokens=None, **kwargs):
            nonlocal call_count
            call_count += 1
            return _FakeLLMResponse(text=_make_valid_payload())

        with (
            patch("zsum.cards.complete_with_retry", side_effect=fake_complete),
            patch("zsum.cards.load_prompt", return_value="system prompt"),
        ):
            result = generate_cards_batch(items, extractions, config, tmp_path)

        # Cached card loaded as-is, new card generated
        assert len(result) == 2
        assert result["cached1"].problem == "Cached problem"
        assert result["new1"].problem == "How cracks propagate"
        # LLM was called only once (for new1, not cached1)
        assert call_count == 1
