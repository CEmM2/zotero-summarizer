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


class TestRedigestLibraryUi:
    def test_redigest_button_launches_redigest_cli_flow(self):
        run_view_model_test("library controls list every stage")

    def test_collection_refresh_queues_redigest_only_after_successful_digest(self):
        run_view_model_test("collection refresh queue runs digests before redigest")

    def test_selected_collection_header_shows_redigest_status_text(self):
        run_view_model_test("redigest status text maps directly from plugin index state")

    def test_collection_tree_keeps_single_digest_status_dot(self):
        view_source = (REPO_ROOT / "plugin_dev" / "src" / "view.ts").read_text(encoding="utf8")
        render_tree_source = view_source.split("private renderTree()", 1)[1].split(
            "private selectCollection",
            1,
        )[0]

        assert "col.digest_state" in render_tree_source
        assert "redigest_state" not in render_tree_source
