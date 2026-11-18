"""Tests for the public built-in prompt API (zsum.resources)."""

from __future__ import annotations

import hashlib
import importlib.resources as pkg_resources

import pytest

from zsum import resources
from zsum.resources import (
    RESOURCE_SCHEMA_VERSION,
    BuiltinPrompt,
    get_builtin_prompt,
    iter_builtin_prompts,
)

# Slots a downstream consumer depends on. Removing or renaming one is a
# breaking change for those consumers, so it must fail here first.
REQUIRED_SLOTS = {
    "paper_card",
    "collection_digest",
    "collection_digest_structured",
    "collection_redigest",
    "restructure",
}


def _shipped_txt_names() -> set[str]:
    root = pkg_resources.files("zsum") / "prompts"
    return {e.name for e in root.iterdir() if e.is_file() and e.name.endswith(".txt")}


class TestIterBuiltinPrompts:
    def test_yields_every_shipped_template(self):
        names = {p.filename for p in iter_builtin_prompts()}
        assert names == _shipped_txt_names()

    def test_required_slots_present(self):
        slots = {p.slot for p in iter_builtin_prompts()}
        assert slots >= REQUIRED_SLOTS

    def test_sorted_and_deterministic(self):
        first = [p.slot for p in iter_builtin_prompts()]
        second = [p.slot for p in iter_builtin_prompts()]
        assert first == sorted(first)
        assert first == second

    def test_record_fields(self):
        for p in iter_builtin_prompts():
            assert isinstance(p, BuiltinPrompt)
            assert p.filename == f"{p.slot}.txt"
            assert p.content
            expected = hashlib.sha256(p.content.encode("utf-8")).hexdigest()
            assert p.content_hash == f"sha256:{expected}"
            assert p.schema_version == RESOURCE_SCHEMA_VERSION == 1
            assert p.package_version

    def test_content_matches_package_file(self):
        root = pkg_resources.files("zsum") / "prompts"
        for p in iter_builtin_prompts():
            assert p.content == (root / p.filename).read_text(encoding="utf-8")

    def test_records_are_immutable(self):
        p = next(iter(iter_builtin_prompts()))
        with pytest.raises(AttributeError):
            p.content = "changed"  # type: ignore[misc]

    def test_ignores_prompt_dir_overlay(self, tmp_path, monkeypatch):
        (tmp_path / "paper_card.txt").write_text("overlay")
        monkeypatch.setenv("ZSUM_PROMPT_DIR", str(tmp_path))
        assert get_builtin_prompt("paper_card").content != "overlay"

    def test_ignores_cwd_prompts(self, tmp_path, monkeypatch):
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "paper_card.txt").write_text("cwd")
        (tmp_path / "prompts" / "extra_only_here.txt").write_text("cwd")
        monkeypatch.chdir(tmp_path)
        assert get_builtin_prompt("paper_card").content != "cwd"
        assert "extra_only_here" not in {p.slot for p in iter_builtin_prompts()}

    def test_package_version_unknown_without_metadata(self, monkeypatch):
        def _missing(_name: str) -> str:
            raise resources.PackageNotFoundError

        monkeypatch.setattr(resources, "_dist_version", _missing)
        assert {p.package_version for p in iter_builtin_prompts()} == {"unknown"}


class TestGetBuiltinPrompt:
    def test_returns_matching_record(self):
        p = get_builtin_prompt("paper_card")
        assert p.filename == "paper_card.txt"
        assert "JSON" in p.content

    def test_unknown_slot_raises_key_error(self):
        with pytest.raises(KeyError, match="nope"):
            get_builtin_prompt("nope")
