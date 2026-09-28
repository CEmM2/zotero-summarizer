"""Tests for paper-type classification heuristics."""

from __future__ import annotations

import pytest

from zsum.classifier import classify_by_metadata, normalize_paper_type
from zsum.models import PaperCard

from .helpers import make_test_item


@pytest.mark.unit
class TestClassifyByMetadata:
    def test_default_is_research(self):
        item = make_test_item(title="Phase Field Modeling of Grain Growth", venue="JMPS")
        assert classify_by_metadata(item) == "research"

    def test_review_title(self):
        item = make_test_item(title="A Comprehensive Review of Phase-Field Methods")
        assert classify_by_metadata(item) == "review"

    def test_survey_title(self):
        item = make_test_item(title="Survey of Machine Learning for Materials Science")
        assert classify_by_metadata(item) == "survey"

    def test_meta_analysis_title(self):
        item = make_test_item(title="Meta-analysis of Fracture Toughness Measurements")
        assert classify_by_metadata(item) == "meta-analysis"

    def test_tutorial_title(self):
        item = make_test_item(title="A Tutorial on Finite Element Methods")
        assert classify_by_metadata(item) == "tutorial"

    def test_systematic_review(self):
        item = make_test_item(title="Systematic Review of Battery Failure Modes")
        assert classify_by_metadata(item) == "review"

    def test_recent_advances(self):
        item = make_test_item(title="Recent Advances in Ceramic Processing")
        assert classify_by_metadata(item) == "review"

    def test_review_venue(self):
        item = make_test_item(
            title="Mechanics of Crystal Plasticity",
            venue="Annual Review of Materials Research",
        )
        assert classify_by_metadata(item) == "review"

    def test_progress_in_venue(self):
        item = make_test_item(
            title="Dislocation Dynamics",
            venue="Progress in Materials Science",
        )
        assert classify_by_metadata(item) == "review"

    def test_review_tag(self):
        item = make_test_item(title="Crystal Plasticity", tags=["Review", "mechanics"])
        assert classify_by_metadata(item) == "review"

    def test_survey_tag(self):
        item = make_test_item(title="Ceramics", tags=["survey"])
        assert classify_by_metadata(item) == "survey"

    def test_false_positive_peer_review(self):
        item = make_test_item(title="Peer Review of Machine Learning Models")
        assert classify_by_metadata(item) == "research"

    def test_false_positive_code_review(self):
        item = make_test_item(title="Code Review Practices at Google")
        assert classify_by_metadata(item) == "research"

    def test_empty_metadata(self):
        item = make_test_item(title="", venue="", tags=[])
        assert classify_by_metadata(item) == "research"


@pytest.mark.unit
class TestNormalizePaperType:
    def test_valid_value(self):
        assert normalize_paper_type("review") == "review"

    def test_case_insensitive(self):
        assert normalize_paper_type("Review") == "review"

    def test_unknown_falls_back(self):
        assert normalize_paper_type("opinion", fallback="research") == "research"

    def test_none_falls_back(self):
        assert normalize_paper_type(None, fallback="survey") == "survey"

    def test_invalid_fallback_goes_to_research(self):
        assert normalize_paper_type(None, fallback="nonsense") == "research"


@pytest.mark.unit
class TestItemPaperTypeFallback:
    def test_default_paper_type(self):
        item = make_test_item()
        assert item.paper_type == "research"
        assert item.is_review is False

    def test_is_review_true_for_review(self):
        item = make_test_item(paper_type="review")
        assert item.is_review is True

    def test_is_review_true_for_survey(self):
        item = make_test_item(paper_type="survey")
        assert item.is_review is True

    def test_is_review_false_for_tutorial(self):
        item = make_test_item(paper_type="tutorial")
        assert item.is_review is False


@pytest.mark.regression
class TestPaperCardBackwardCompat:
    def test_missing_paper_type_defaults_to_research(self):
        card = PaperCard(citekey="x", title="Foo")
        assert card.paper_type == "research"
        assert card.is_review is False

    def test_old_cache_dict_loads(self):
        legacy = {
            "citekey": "x",
            "title": "Foo",
            "problem": "p",
            "methods": [],
            "key_findings": [],
            "limitations": [],
            "keywords": [],
        }
        card = PaperCard(**legacy)
        assert card.paper_type == "research"
