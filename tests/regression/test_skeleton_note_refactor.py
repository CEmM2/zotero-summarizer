"""Regression tests for the skeleton-note refactor and CLI preview wiring."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

from zsum.cli import main
from zsum.config import Config
from zsum.models import Collection, Item, LibraryIndex
from zsum.publisher import publish_vault


def _make_minimal_index() -> LibraryIndex:
    item = Item(
        citekey="author2021",
        zotero_key="Z1",
        item_id=1,
        title="A Test Paper",
        authors=["Author, A."],
        year=2021,
    )
    collection = Collection(
        key="COL1",
        name="Test Collection",
        parent_key=None,
        path="Test Collection",
        item_citekeys=["author2021"],
        child_keys=[],
    )
    return LibraryIndex(items={"author2021": item}, collections={"COL1": collection})


class TestSkeletonNoteRefactor:
    @pytest.mark.regression
    def test_skeleton_output_unchanged(self, tmp_path):
        vault = tmp_path / "vault"
        config = Config(vault_output=vault)
        publish_vault(_make_minimal_index(), config)

        content = (vault / "Collections" / "Test Collection.md").read_text(encoding="utf-8")
        expected = "\n".join(
            [
                "---",
                'type: "collection"',
                f'created: "{date.today().isoformat()}"',
                "paper_count: 1",
                "---",
                "",
                "# Test Collection",
                "",
                "> Parent: [[Library Index]]",
                "",
                "## Summary",
                "",
                "*Summary pending — run `zsum digests` to generate.*",
                "",
                "## Key Themes",
                "",
                "*Pending — run `zsum digests` to generate.*",
                "",
                "## Common Methods",
                "",
                "*Pending — run `zsum digests` to generate.*",
                "",
                "## Gaps and Limitations",
                "",
                "*Pending — run `zsum digests` to generate.*",
                "",
                "## Papers in this Collection",
                "",
                "- [[@author2021]] — Author, A. (2021). A Test Paper",
                "",
            ]
        )

        assert content == expected


def _write_config(tmp_path: Path, bbt_json: Path, zotero_sqlite: Path) -> Path:
    """Write a minimal config.yaml for CLI tests."""
    cache_dir = tmp_path / "cache"
    vault_dir = tmp_path / "vault"
    cache_dir.mkdir(parents=True, exist_ok=True)
    vault_dir.mkdir(parents=True, exist_ok=True)

    config_content = (
        f"bbt_json: {bbt_json}\n"
        f"zotero_sqlite: {zotero_sqlite}\n"
        f"cache_dir: {cache_dir}\n"
        f"vault_output: {vault_dir}\n"
        f"generate_paper_notes: false\n"
        "llm:\n"
        "  provider: anthropic\n"
        "  anthropic:\n"
        "    model: test-model\n"
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(config_content)
    return config_path


class TestCLIPreviewWiring:
    """CLI wiring: extract and skeleton commands include preview text."""

    @pytest.mark.unit
    def test_extract_output_includes_preview_text(
        self, tmp_path, sample_bbt_json, sample_zotero_sqlite
    ):
        config_path = _write_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        runner = CliRunner()
        result = runner.invoke(main, ["--config", str(config_path), "extract"])
        assert result.exit_code == 0, f"Command failed:\n{result.output}"
        assert "## Text Previews" in result.output

    @pytest.mark.unit
    def test_skeleton_output_includes_preview_text(
        self, tmp_path, sample_bbt_json, sample_zotero_sqlite
    ):
        config_path = _write_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        vault_dir = tmp_path / "vault"
        runner = CliRunner()
        result = runner.invoke(main, ["--config", str(config_path), "skeleton"])
        assert result.exit_code == 0, f"Command failed:\n{result.output}"
        assert "## Text Previews" in result.output
        # Skeleton must still write vault files
        assert (vault_dir / "Library Index.md").exists()

    @pytest.mark.unit
    def test_no_new_cache_files_from_extract(self, tmp_path, sample_bbt_json, sample_zotero_sqlite):
        config_path = _write_config(tmp_path, sample_bbt_json, sample_zotero_sqlite)
        cache_dir = tmp_path / "cache"
        runner = CliRunner()
        # Snapshot cache contents before extract
        before = set(cache_dir.rglob("*"))
        result = runner.invoke(main, ["--config", str(config_path), "extract"])
        assert result.exit_code == 0, f"Command failed:\n{result.output}"
        after = set(cache_dir.rglob("*"))
        # Extract should not create any new cache files
        new_files = after - before
        assert not new_files, f"Unexpected new cache files: {new_files}"
