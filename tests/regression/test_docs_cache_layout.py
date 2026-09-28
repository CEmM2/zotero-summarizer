from pathlib import Path

import pytest

DOCS_PATH = Path(__file__).parents[2] / "docs" / "reference" / "cache-layout.md"


class TestDocsCacheLayout:
    """
    Tests for Add cache layout tree to docs
    Covers: [1] Complete cache layout documented,
    [2] Sidecar accumulation noted
    """

    @pytest.mark.docs
    def test_cache_layout_documented(self):
        """
        Verifies: docs contain the full cache directory layout tree
        Covers: Complete cache layout documented
        Passes when: A cache layout section exists with _hashes.json entries
        """
        content = DOCS_PATH.read_text()
        assert "_hashes.json" in content, "Cache layout must include _hashes.json sidecar files"
        assert "membership.json" in content, "Cache layout must include membership.json"
        assert "cache/" in content, "Cache layout tree must show the cache/ directory"
        assert "cards/" in content, "Cache layout tree must show the cards/ subdirectory"
        assert "digests/" in content, "Cache layout tree must show the digests/ subdirectory"

    @pytest.mark.docs
    def test_sidecar_accumulation_noted(self):
        """
        Verifies: docs mention that sidecar files accumulate for deleted collections
        Covers: Sidecar accumulation noted
        Passes when: The word 'accumulate' or equivalent appears near cache layout section
        """
        content = DOCS_PATH.read_text().lower()
        assert "accumulat" in content, (
            "Docs must note that sidecar files accumulate for deleted collections"
        )
        assert "deleted" in content, (
            "Docs must mention deleted collections in the context of sidecar accumulation"
        )
