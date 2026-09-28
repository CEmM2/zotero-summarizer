"""Tests for Plugin index-reader.ts update.

Verifies TypeScript type definitions by reading the source file and checking
that the expected type structure exists.
"""

from pathlib import Path

import pytest

PLUGIN_SRC = Path(__file__).resolve().parents[2] / "plugin_dev" / "src"
INDEX_READER = PLUGIN_SRC / "index-reader.ts"


class TestPluginIndexReaderContract:
    """Tests for Plugin index-reader.ts update. AC covered: [1,2,3,4]."""

    @pytest.mark.unit
    def test_card_state_includes_fallback(self):
        """Verifies: card_state union type includes 'fallback'."""
        content = INDEX_READER.read_text()
        assert '"fallback"' in content
        line = next(ln for ln in content.splitlines() if "card_state" in ln and "fallback" in ln)
        assert "|" in line, "card_state should be a union type"

    @pytest.mark.unit
    def test_extraction_method_is_optional(self):
        """Verifies: extraction_method field is optional string in ItemIndex."""
        content = INDEX_READER.read_text()
        assert "extraction_method?" in content
        line = next(ln for ln in content.splitlines() if "extraction_method?" in ln)
        assert "string" in line

    @pytest.mark.unit
    def test_existing_card_states_valid(self):
        """Verifies: Existing card_state values remain valid."""
        content = INDEX_READER.read_text()
        card_state_line = next(
            ln for ln in content.splitlines() if "card_state" in ln and '"cached"' in ln
        )
        for state in ("cached", "pending", "degraded", "no_pdf", "fallback"):
            assert f'"{state}"' in card_state_line, f"Missing state: {state}"

    @pytest.mark.unit
    def test_typescript_compilation(self):
        """Verifies: TypeScript compilation completes without errors."""
        import subprocess

        result = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=PLUGIN_SRC.parent,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"tsc failed:\n{result.stdout}\n{result.stderr}"
