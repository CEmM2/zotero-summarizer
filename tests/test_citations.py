"""Tests for the citations fetcher, cache, and CLI surface."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from zsum.cache import load_citations, save_citations
from zsum.citations import (
    fetch_citations_batch,
    is_stale,
    top_n_by_citations,
)
from zsum.config import CitationsConfig, Config
from zsum.models import CitationRecord

from .helpers import make_test_item


def _mock_transport(handler):
    return httpx.MockTransport(handler)


def _make_cfg(tmp_path, **citations_overrides):
    cfg = Config(cache_dir=tmp_path)
    cfg.citations = CitationsConfig(rate_limit_delay=0.0, **citations_overrides)
    return cfg


@pytest.mark.unit
class TestIsStale:
    def test_missing_timestamp_is_stale(self):
        rec = CitationRecord(citekey="x")
        assert is_stale(rec, 30) is True

    def test_recent_is_fresh(self):
        rec = CitationRecord(
            citekey="x", fetched_at=datetime.now(UTC).isoformat(), citation_count=5
        )
        assert is_stale(rec, 30) is False

    def test_old_is_stale(self):
        old = (datetime.now(UTC) - timedelta(days=45)).isoformat()
        rec = CitationRecord(citekey="x", fetched_at=old, citation_count=5)
        assert is_stale(rec, 30) is True

    def test_bogus_timestamp_is_stale(self):
        rec = CitationRecord(citekey="x", fetched_at="not-a-date")
        assert is_stale(rec, 30) is True


@pytest.mark.unit
class TestCacheRoundTrip:
    def test_save_then_load(self, tmp_path):
        rec = CitationRecord(
            citekey="smith2017",
            citation_count=42,
            source="openalex",
            fetched_at=datetime.now(UTC).isoformat(),
            external_id="https://openalex.org/W123",
        )
        save_citations({"smith2017": rec}, tmp_path)
        loaded = load_citations(tmp_path)
        assert "smith2017" in loaded
        assert loaded["smith2017"].citation_count == 42
        assert loaded["smith2017"].source == "openalex"

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_citations(tmp_path) == {}


@pytest.mark.unit
class TestFetchBatch:
    def test_disabled_skips_fetch(self, tmp_path):
        cfg = _make_cfg(tmp_path, enabled=False)
        item = make_test_item(doi="10.1000/a")
        records = fetch_citations_batch({"smith2017": item}, cfg, tmp_path)
        assert records == {}

    def test_openalex_doi_success(self, tmp_path):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            assert "openalex.org/works" in str(request.url)
            return httpx.Response(
                200,
                json={
                    "id": "https://openalex.org/W123",
                    "cited_by_count": 77,
                    "doi": "10.1000/a",
                },
            )

        client = httpx.Client(transport=_mock_transport(handler))
        cfg = _make_cfg(tmp_path)
        item = make_test_item(doi="10.1000/a")
        records = fetch_citations_batch({"smith2017": item}, cfg, tmp_path, client=client)
        assert records["smith2017"].citation_count == 77
        assert records["smith2017"].source == "openalex"
        # Persisted to disk.
        reloaded = load_citations(tmp_path)
        assert reloaded["smith2017"].citation_count == 77
        assert calls["n"] == 1

    def test_openalex_404_then_s2_fallback(self, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "openalex.org" in url:
                return httpx.Response(404, json={})
            if "semanticscholar.org" in url:
                return httpx.Response(
                    200,
                    json={"paperId": "abc", "citationCount": 12, "title": "x"},
                )
            return httpx.Response(500)

        client = httpx.Client(transport=_mock_transport(handler))
        cfg = _make_cfg(tmp_path, fallback="semantic_scholar")
        item = make_test_item(doi="10.1000/a", title="Zero Match", year=None, authors=[])
        records = fetch_citations_batch({"smith2017": item}, cfg, tmp_path, client=client)
        assert records["smith2017"].citation_count == 12
        assert records["smith2017"].source == "semantic_scholar"

    def test_network_error_no_crash(self, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("simulated offline", request=request)

        client = httpx.Client(transport=_mock_transport(handler))
        cfg = _make_cfg(tmp_path, fallback="")
        item = make_test_item(doi="10.1000/a")
        records = fetch_citations_batch({"smith2017": item}, cfg, tmp_path, client=client)
        # No record fetched but no exception either.
        assert records == {} or "smith2017" not in records

    def test_skips_fresh_entries(self, tmp_path):
        # Pre-seed a fresh cached record.
        fresh = CitationRecord(
            citekey="smith2017",
            citation_count=5,
            source="openalex",
            fetched_at=datetime.now(UTC).isoformat(),
        )
        save_citations({"smith2017": fresh}, tmp_path)

        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json={"id": "x", "cited_by_count": 999})

        client = httpx.Client(transport=_mock_transport(handler))
        cfg = _make_cfg(tmp_path, max_age_days=30)
        item = make_test_item(doi="10.1000/a")
        records = fetch_citations_batch({"smith2017": item}, cfg, tmp_path, client=client)
        # Fresh → no HTTP call; value unchanged.
        assert calls["n"] == 0
        assert records["smith2017"].citation_count == 5


@pytest.mark.unit
class TestTopN:
    def test_sorted_desc(self):
        recs = {
            "a": CitationRecord(citekey="a", citation_count=3),
            "b": CitationRecord(citekey="b", citation_count=10),
            "c": CitationRecord(citekey="c", citation_count=1),
            "d": CitationRecord(citekey="d", citation_count=None),
        }
        result = top_n_by_citations(recs, ["a", "b", "c", "d"], 2)
        assert result == [("b", 10), ("a", 3)]
