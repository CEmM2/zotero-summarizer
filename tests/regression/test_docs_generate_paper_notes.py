from pathlib import Path

import pytest


class TestGeneratePaperNotesDocs:
    """
    Tests for Document generate_paper_notes option
    Covers: [1] Option documented with explanation of when to use it
    """

    @pytest.mark.docs
    def test_generate_paper_notes_documented_in_configuration_guide(self):
        """
        Verifies: configuration docs contain documentation for generate_paper_notes option
        Covers: Option documented with explanation of when to use it
        Passes when: The string 'generate_paper_notes' appears in configuration docs
        """
        config_guide = (
            Path(__file__).parent.parent.parent / "docs" / "getting-started" / "configuration.md"
        )
        assert config_guide.exists(), "docs/getting-started/configuration.md not found"
        content = config_guide.read_text()
        assert "generate_paper_notes" in content, (
            "generate_paper_notes option is not documented in configuration docs"
        )
        # Verify there's an explanation, not just a bare mention
        assert "false" in content or "False" in content, (
            "configuration docs should explain when to set generate_paper_notes to false"
        )
