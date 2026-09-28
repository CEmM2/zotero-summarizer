"""Tests for the cards module."""

from __future__ import annotations

import json
from unittest.mock import patch

from tests.helpers import make_test_item as _make_item
from zsum.cache import extraction_signature, save_card
from zsum.cards import (
    _build_user_prompt,
    _ensure_list,
    _parse_card_response,
    generate_cards_batch,
)
from zsum.config import Config
from zsum.extractor import ExtractionResult
from zsum.models import PaperCard


def _make_extraction(**overrides) -> ExtractionResult:
    defaults = dict(
        citekey="smith2017",
        text="Some extracted text about fracture.",
        page_count=10,
        pages_used=[0, 1, 2, 8, 9],
        quality="good",
        extraction_method="pages",
    )
    defaults.update(overrides)
    return ExtractionResult(**defaults)


class TestParseCardResponse:
    def test_valid_json(self):
        response = json.dumps(
            {
                "problem": "How cracks propagate in brittle materials.",
                "methods": ["Phase field method", "FEM"],
                "key_findings": ["Model converges to Griffith"],
                "limitations": ["2D only"],
                "keywords": ["phase-field", "fracture"],
            }
        )
        card, _ = _parse_card_response(response, _make_item(), "good")

        assert card.citekey == "smith2017"
        assert card.problem == "How cracks propagate in brittle materials."
        assert card.methods == ["Phase field method", "FEM"]
        assert card.key_findings == ["Model converges to Griffith"]
        assert card.limitations == ["2D only"]
        assert card.text_quality == "good"

    def test_strips_markdown_fences(self):
        body = json.dumps(
            {
                "problem": "Test problem",
                "methods": [],
                "key_findings": [],
                "limitations": [],
                "keywords": [],
            }
        )
        response = f"```json\n{body}\n```"
        card, _ = _parse_card_response(response, _make_item(), "good")
        assert card.problem == "Test problem"

    def test_strips_fences_without_language(self):
        body = json.dumps(
            {
                "problem": "Test",
                "methods": [],
                "key_findings": [],
                "limitations": [],
                "keywords": [],
            }
        )
        response = f"```\n{body}\n```"
        card, _ = _parse_card_response(response, _make_item(), "good")
        assert card.problem == "Test"

    def test_invalid_json_returns_minimal_card(self):
        card, _ = _parse_card_response("This is not JSON at all", _make_item(), "degraded")

        assert card.citekey == "smith2017"
        assert card.title == "Phase Field Modeling"
        assert card.problem == "unknown"
        assert card.methods == []
        assert card.text_quality == "degraded"

    def test_partial_json_fills_defaults(self):
        response = json.dumps({"problem": "Some problem"})
        card, _ = _parse_card_response(response, _make_item(), "good")

        assert card.problem == "Some problem"
        assert card.methods == []
        assert card.key_findings == []
        assert card.keywords == []

    def test_metadata_comes_from_item_not_llm(self):
        response = json.dumps(
            {
                "problem": "Test",
                "methods": [],
                "key_findings": [],
                "limitations": [],
                "keywords": [],
            }
        )
        item = _make_item(citekey="zhao2020", title="Dynamic Fracture", year=2020)
        card, _ = _parse_card_response(response, item, "good")

        assert card.citekey == "zhao2020"
        assert card.title == "Dynamic Fracture"
        assert card.year == 2020

    def test_preserves_extraction_method(self):
        response = json.dumps(
            {
                "problem": "Test",
                "methods": [],
                "key_findings": [],
                "limitations": [],
                "keywords": [],
            }
        )
        card, _ = _parse_card_response(response, _make_item(), "good", "sections")

        assert card.extraction_method == "sections"

    def test_stub_card_preserves_extraction_method(self):
        card, _ = _parse_card_response(
            "This is not JSON at all",
            _make_item(),
            "degraded",
            "fallback_pages",
        )

        assert card.extraction_method == "fallback_pages"


class TestEnsureList:
    def test_list_passthrough(self):
        assert _ensure_list(["a", "b"]) == ["a", "b"]

    def test_string_wrapped(self):
        assert _ensure_list("single item") == ["single item"]

    def test_none_returns_empty(self):
        assert _ensure_list(None) == []

    def test_int_list_stringified(self):
        assert _ensure_list([1, 2, 3]) == ["1", "2", "3"]


class TestBuildUserPrompt:
    def test_includes_metadata(self):
        item = _make_item()
        extraction = _make_extraction()
        prompt = _build_user_prompt(item, extraction)

        assert "smith2017" in prompt
        assert "Phase Field Modeling" in prompt
        assert "Smith, John" in prompt
        assert "2017" in prompt
        assert "JMPS" in prompt

    def test_includes_extracted_text(self):
        extraction = _make_extraction(text="Fracture mechanics content here.")
        prompt = _build_user_prompt(_make_item(), extraction)

        assert "--- EXTRACTED TEXT ---" in prompt
        assert "Fracture mechanics content here." in prompt

    def test_abstract_fallback_when_no_text(self):
        extraction = _make_extraction(text="")
        item = _make_item(abstract="This is the abstract.")
        prompt = _build_user_prompt(item, extraction)

        assert "--- ABSTRACT ONLY ---" in prompt
        assert "This is the abstract." in prompt

    def test_no_text_no_abstract(self):
        extraction = _make_extraction(text="")
        item = _make_item(abstract="")
        prompt = _build_user_prompt(item, extraction)

        assert "--- NO TEXT AVAILABLE ---" in prompt

    def test_includes_quality_info(self):
        extraction = _make_extraction(quality="degraded", page_count=20, pages_used=[0, 1])
        prompt = _build_user_prompt(_make_item(), extraction)

        assert "degraded" in prompt
        assert "2 of 20" in prompt

    def test_includes_extraction_method(self):
        extraction = _make_extraction(extraction_method="sections")
        prompt = _build_user_prompt(_make_item(), extraction)

        assert "Extraction method: sections" in prompt


class TestSaveCard:
    def test_saves_json_with_meta(self, tmp_path):
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        card = PaperCard(citekey="smith2017", title="Test")
        config = Config(prompt_version=3)

        save_card(card, config, cards_dir)

        filepath = cards_dir / "smith2017.json"
        assert filepath.exists()
        data = json.loads(filepath.read_text())
        assert data["citekey"] == "smith2017"
        assert data["_meta"]["prompt_version"] == 3
        assert "generated_at" in data["_meta"]


class TestGenerateCardsBatch:
    def test_skips_cached_cards_with_matching_version(self, tmp_path):
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        cached = {
            "citekey": "smith2017",
            "title": "Test",
            "problem": "Cached problem",
            "methods": [],
            "key_findings": [],
            "limitations": [],
            "keywords": [],
            "text_quality": "good",
            "authors": [],
            "year": 2017,
            "venue": "",
            "doi": "",
            "_meta": {
                "model": "test",
                "prompt_version": 1,
                "extraction_signature": extraction_signature(Config()),
                "generated_at": "2025-01-01",
            },
        }
        (cards_dir / "smith2017.json").write_text(json.dumps(cached))

        items = {"smith2017": _make_item()}
        extractions = {"smith2017": _make_extraction()}
        config = Config(prompt_version=1)

        result = generate_cards_batch(items, extractions, config, tmp_path)
        assert result["smith2017"].problem == "Cached problem"

    def test_regenerates_on_version_bump(self, tmp_path):
        cards_dir = tmp_path / "cards"
        cards_dir.mkdir()
        cached = {
            "citekey": "smith2017",
            "title": "Test",
            "problem": "Old",
            "methods": [],
            "key_findings": [],
            "limitations": [],
            "keywords": [],
            "text_quality": "good",
            "authors": [],
            "year": 2017,
            "venue": "",
            "doi": "",
            "_meta": {
                "model": "test",
                "prompt_version": 1,
                "extraction_signature": extraction_signature(Config()),
                "generated_at": "2025-01-01",
            },
        }
        (cards_dir / "smith2017.json").write_text(json.dumps(cached))

        items = {"smith2017": _make_item()}
        extractions = {"smith2017": _make_extraction()}
        config = Config(prompt_version=2)

        with patch("zsum.cards.generate_card") as mock_gen:
            mock_gen.return_value = (
                PaperCard(citekey="smith2017", title="Test", problem="New"),
                [],
            )
            result = generate_cards_batch(items, extractions, config, tmp_path)

        assert result["smith2017"].problem == "New"
        mock_gen.assert_called_once()
