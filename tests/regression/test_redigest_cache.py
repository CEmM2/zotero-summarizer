"""Tests for redigest cache persistence and invalidation."""

from __future__ import annotations

from pathlib import Path

import pytest

from zsum.cache import (
    load_effective_digests,
    load_redigest_metadata,
    redigest_state_for_collection,
    save_redigest,
)
from zsum.config import Config, LLMConfig, LLMProviderConfig, LLMRoutingConfig


class TestRedigestCache:
    """
    Tests for Implement redigest cache metadata, staleness checks, and effective
    digest helpers.
    Covers: 1, 2, 3, 4
    """

    @pytest.mark.unit
    def test_matching_source_digest_hash_marks_redigest_fresh(self, tmp_path):
        """
        Verifies: a redigest with a matching source-digest hash is classified as fresh.
        Covers: Redigest freshness is determined from the current first-pass digest
        hash, not direct card inspection.
        Passes when: the freshness helper returns `ok` while the stored source-digest hash matches
        the current first-pass digest content.
        """
        digest_path = _write_digest(tmp_path, "C1", "Draft digest")

        save_redigest("C1", "Refined digest", digest_path.read_text(), tmp_path, _make_config())

        metadata = load_redigest_metadata(tmp_path, "C1")
        assert metadata is not None
        assert redigest_state_for_collection("C1", tmp_path) == "ok"

    @pytest.mark.unit
    def test_changed_first_pass_digest_marks_redigest_stale_without_card_hashes(self, tmp_path):
        """
        Verifies: changing only the first-pass digest content makes the redigest stale.
        Covers: Redigest freshness is determined from the current first-pass digest
        hash, not direct card inspection.
        Passes when: the staleness helper reports stale based solely on a digest-hash mismatch.
        """
        digest_path = _write_digest(tmp_path, "C1", "Draft digest")

        save_redigest("C1", "Refined digest", digest_path.read_text(), tmp_path, _make_config())
        digest_path.write_text("Changed draft digest", encoding="utf-8")

        assert redigest_state_for_collection("C1", tmp_path) == "stale"

    @pytest.mark.unit
    def test_effective_digests_prefer_fresh_redigest_and_fallback_to_first_pass(self, tmp_path):
        """
        Verifies: effective-digest loading prefers fresh redigests and falls back safely.
        Covers: Publish can retrieve a safe effective digest set with fallback
        behavior; the cache layout keeps first-pass and final-pass digests separate.
        Passes when: publish-facing helpers choose the redigest only when fresh and otherwise
        return the first-pass digest.
        """
        digest_path_c1 = _write_digest(tmp_path, "C1", "Draft digest 1")
        digest_path_c2 = _write_digest(tmp_path, "C2", "Draft digest 2")

        config = _make_config()
        save_redigest("C1", "Refined digest 1", digest_path_c1.read_text(), tmp_path, config)
        save_redigest("C2", "Refined digest 2", digest_path_c2.read_text(), tmp_path, config)
        digest_path_c2.write_text("Changed draft digest 2", encoding="utf-8")

        effective = load_effective_digests(tmp_path)

        assert effective["C1"] == "Refined digest 1"
        assert effective["C2"] == "Changed draft digest 2"


def _make_config() -> Config:
    return Config(
        llm=LLMConfig(
            provider="anthropic",
            routing=LLMRoutingConfig(redigest="anthropic"),
            anthropic=LLMProviderConfig(model="claude-redigest"),
        )
    )


def _write_digest(cache_dir: Path, col_key: str, content: str) -> Path:
    digests_dir = cache_dir / "digests"
    digests_dir.mkdir(parents=True, exist_ok=True)
    digest_path = digests_dir / f"{col_key}.md"
    digest_path.write_text(content, encoding="utf-8")
    return digest_path
