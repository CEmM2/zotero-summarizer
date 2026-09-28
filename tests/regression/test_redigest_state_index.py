"""Tests for redigest state exposure in the plugin index."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from zsum.cache import save_digest_hashes, save_plugin_index, save_redigest
from zsum.config import Config, LLMConfig, LLMProviderConfig, LLMRoutingConfig
from zsum.models import Collection, Item, LibraryIndex


def _make_index(tmp_path: Path) -> LibraryIndex:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"fake")
    items = {
        "alpha2020": Item(
            citekey="alpha2020",
            zotero_key="A",
            title="Alpha",
            year=2020,
            venue="JMPS",
            pdf_path=pdf_path,
        ),
        "beta2021": Item(
            citekey="beta2021",
            zotero_key="B",
            title="Beta",
            year=2021,
            venue="",
            pdf_path=None,
        ),
    }
    collections = {
        "C1": Collection(
            key="C1",
            name="ColOne",
            path="ColOne",
            item_citekeys=["alpha2020", "beta2021"],
        ),
    }
    return LibraryIndex(items=items, collections=collections)


def _make_redigest_config() -> Config:
    return Config(
        llm=LLMConfig(
            provider="anthropic",
            routing=LLMRoutingConfig(redigest="anthropic"),
            anthropic=LLMProviderConfig(model="claude-redigest"),
        )
    )


class TestRedigestStateIndex:
    """
    Tests for Extend `cache/index.json` and plugin types with `redigest_state`.
    Covers: 1, 2, 3, 4
    """

    @pytest.mark.integration
    def test_plugin_index_reports_redigest_state_ok_for_fresh_redigest(self, tmp_path):
        """
        Verifies: a collection with a fresh redigest is marked `redigest_state: ok`.
        Covers: `redigest_state` is present in plugin index output with
        `ok | stale | missing` values.
        Passes when: the generated plugin index includes `redigest_state: ok` for a collection
        whose redigest hash matches the current first-pass digest.
        """
        idx = _make_index(tmp_path)
        cards_dir = tmp_path / "cards"
        digests_dir = tmp_path / "digests"
        cards_dir.mkdir()
        digests_dir.mkdir()
        (cards_dir / "alpha2020.json").write_text(
            json.dumps({"citekey": "alpha2020", "title": "Alpha"})
        )
        digest_text = "digest text"
        save_digest_hashes("C1", ["alpha2020"], cards_dir, digests_dir)
        (digests_dir / "C1.md").write_text(digest_text, encoding="utf-8")
        save_redigest("C1", "Refined digest", digest_text, tmp_path, _make_redigest_config())

        save_plugin_index(idx, tmp_path)

        data = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
        assert data["collections"]["C1"]["redigest_state"] == "ok"

    @pytest.mark.integration
    def test_plugin_index_reports_redigest_state_stale_when_digest_changes(self, tmp_path):
        """
        Verifies: a changed first-pass digest marks the redigest stale in the plugin index.
        Covers: `redigest_state` is present in plugin index output with
        `ok | stale | missing` values.
        Passes when: the next plugin-index write reports `redigest_state: stale` after the digest
        content changes.
        """
        idx = _make_index(tmp_path)
        cards_dir = tmp_path / "cards"
        digests_dir = tmp_path / "digests"
        cards_dir.mkdir()
        digests_dir.mkdir()
        (cards_dir / "alpha2020.json").write_text(
            json.dumps({"citekey": "alpha2020", "title": "Alpha"})
        )
        digest_path = digests_dir / "C1.md"
        digest_path.write_text("digest text", encoding="utf-8")
        save_digest_hashes("C1", ["alpha2020"], cards_dir, digests_dir)
        save_redigest("C1", "Refined digest", "digest text", tmp_path, _make_redigest_config())
        digest_path.write_text("changed digest text", encoding="utf-8")

        save_plugin_index(idx, tmp_path)

        data = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
        assert data["collections"]["C1"]["redigest_state"] == "stale"

    @pytest.mark.integration
    def test_plugin_index_reports_redigest_state_missing_without_changing_digest_state(
        self, tmp_path
    ):
        """
        Verifies: missing redigest output adds `redigest_state: missing` without redefining
        `digest_state`.
        Covers: `digest_state` semantics remain unchanged; `redigest_state` is
        present in plugin index output with `ok | stale | missing` values.
        Passes when: the collection record keeps the original first-pass `digest_state` meaning and
        adds `redigest_state: missing`.
        """
        idx = _make_index(tmp_path)
        cards_dir = tmp_path / "cards"
        digests_dir = tmp_path / "digests"
        cards_dir.mkdir()
        digests_dir.mkdir()
        (cards_dir / "alpha2020.json").write_text(
            json.dumps({"citekey": "alpha2020", "title": "Alpha"})
        )
        save_digest_hashes("C1", ["alpha2020"], cards_dir, digests_dir)
        (digests_dir / "C1.md").write_text("digest text", encoding="utf-8")

        save_plugin_index(idx, tmp_path)

        data = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
        assert data["collections"]["C1"]["digest_state"] == "ok"
        assert data["collections"]["C1"]["redigest_state"] == "missing"

    @pytest.mark.integration
    def test_plugin_bundle_builds_with_redigest_state_index_reader_changes(self):
        """
        Verifies: the plugin bundle still builds after the index-reader contract is extended.
        Covers: The plugin index reader accepts the extended collection shape without
        breaking existing fields; the plugin can surface redigest status without
        recomputing freshness client-side.
        Passes when: the plugin TypeScript build succeeds after adding `redigest_state` handling.
        """
        if shutil.which("npm") is None:
            pytest.skip("npm is not available")

        plugin_dir = Path(__file__).resolve().parents[2] / "plugin_dev"
        if not (plugin_dir / "node_modules").exists():
            pytest.skip("plugin_dev/node_modules not installed (run `npm ci` in plugin_dev)")
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=plugin_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
