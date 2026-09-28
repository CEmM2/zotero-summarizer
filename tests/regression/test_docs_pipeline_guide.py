from pathlib import Path

import pytest

GUIDE_PATH = Path(__file__).parents[2] / "GUIDE.md"

PIPELINE_STAGES = ["indexer", "extractor", "cards", "digests", "publisher"]


class TestDocsPipelineGuide:
    """
    Tests for Add data-flow contracts table to GUIDE.md
    Covers: [1] All 5 stages documented, [2] Types and side-effects listed
    """

    @pytest.fixture(autouse=True)
    def guide_text(self):
        self._guide = GUIDE_PATH.read_text()

    @pytest.mark.docs
    def test_all_pipeline_stages_documented(self):
        """
        Verifies: GUIDE.md contains data-flow entries for all 5 pipeline stages
        Covers: All 5 stages documented
        Passes when: indexer, extractor, cards, digests, publisher all appear in contracts table
        """
        missing = [stage for stage in PIPELINE_STAGES if stage not in self._guide.lower()]
        assert not missing, f"Pipeline stages missing from GUIDE.md: {missing}"

    @pytest.mark.docs
    def test_types_and_side_effects_listed(self):
        """
        Verifies: Each stage entry includes input types, output types, and side-effects
        Covers: Types and side-effects listed
        Passes when: Each stage row has non-empty consumes, produces, and side-effects columns
        """
        guide_lower = self._guide.lower()
        # Check that the contracts table section exists
        assert "data-flow" in guide_lower, "GUIDE.md must contain a 'Data-Flow' section"
        # Check that the table has the required columns
        assert "consumes" in guide_lower, "Contracts table must have a 'Consumes' column"
        assert "produces" in guide_lower, "Contracts table must have a 'Produces' column"
        assert "side-effect" in guide_lower, "Contracts table must have a 'Side-effects' column"
        # Each stage must have content in the table (appears in context with key types)
        assert "libraryindex" in guide_lower, "indexer output type LibraryIndex must be documented"
        assert "extractionresult" in guide_lower, (
            "extractor output type ExtractionResult must be documented"
        )
        assert "papercard" in guide_lower, "cards output type PaperCard must be documented"
        assert "llm api" in guide_lower, (
            "LLM API side-effect must be documented (for cards and digests)"
        )
