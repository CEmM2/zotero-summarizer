"""Fallback-chain propagation from extractor through plugin rendering.

Verifies end-to-end fallback chain through extractor, cache, and plugin layers.
Plugin tests run via subprocess to invoke npm test.
"""

import subprocess
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugin_dev"


class TestFallbackChainPropagation:
    """Tests for Fallback rendering in plugin."""

    @pytest.mark.regression
    def test_plugin_npm_test_full_suite_passes(self):
        """Verifies: Full plugin npm test suite passes including fallback cases."""
        result = subprocess.run(
            ["npm", "test"],
            cwd=PLUGIN_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"npm test failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        )

    @pytest.mark.regression
    def test_plugin_index_reader_tests_include_fallback(self):
        """Verifies: index-reader.test.mjs contains fallback state assertions."""
        test_file = PLUGIN_DIR / "src" / "index-reader.test.mjs"
        content = test_file.read_text()
        assert "fallback" in content, "index-reader tests should cover fallback state"
        assert "cards_fallback" in content, "index-reader tests should verify cards_fallback count"

    @pytest.mark.regression
    def test_plugin_fallback_css_classes_defined(self):
        """Verifies: styles.css defines zsum-fallback and zsum-badge-fallback."""
        styles = (PLUGIN_DIR / "styles.css").read_text()
        assert ".zsum-fallback" in styles
        assert ".zsum-badge-fallback" in styles
