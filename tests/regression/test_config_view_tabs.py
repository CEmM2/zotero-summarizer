from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO_ROOT / "plugin_dev"


def run_view_model_test(pattern: str) -> None:
    result = subprocess.run(
        [
            "node",
            "--experimental-strip-types",
            "--test",
            "src/view-model.test.mjs",
            "--test-name-pattern",
            pattern,
        ],
        cwd=PLUGIN_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"Node view-model test failed for pattern {pattern!r}\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


class TestConfigViewTabs:
    def test_view_tab_switching_preserves_library_and_config_surfaces(self):
        run_view_model_test("tabs expose library and config surfaces")

    def test_config_tab_renders_planned_sections_and_control_types(self):
        run_view_model_test("config view model renders planned sections and control types")
