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


class TestConfigWorkflow:
    def test_dirty_state_indicator_remains_until_save_or_revert(self):
        run_view_model_test(
            "dirty state badge and explicit save actions follow the workflow contract"
        )

    def test_parse_error_surfaces_inline_and_disables_save(self):
        run_view_model_test(
            "parse errors and missing files surface inline while save stays disabled"
        )

    def test_save_revert_and_reload_follow_explicit_save_workflow(self):
        run_view_model_test(
            "dirty state badge and explicit save actions follow the workflow contract"
        )

    def test_missing_config_file_warning_uses_resolved_path_preview(self):
        run_view_model_test(
            "parse errors and missing files surface inline while save stays disabled"
        )

    def test_success_notice_only_appears_after_completed_save(self):
        run_view_model_test("success feedback appears only when explicit save feedback is provided")
