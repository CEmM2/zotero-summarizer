"""Citation-count fetcher: OpenAlex primary, Semantic Scholar fallback.

The module is intentionally self-contained so offline / disabled runs never
raise. On any network error the item is simply skipped and its existing cache
entry (if any) is preserved.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from .config import Config
from .models import CitationRecord, Item

logger = logging.getLogger(__name__)

_OPENALEX_BASE = "https://api.openalex.org"
_S2_BASE = "https://api.semanticscholar.org/graph/v1"


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------


def is_stale(record: CitationRecord, max_age_days: int) -> bool:
    """Return True if the record is older than ``max_age_days`` or has no timestamp."""
    if not record.fetched_at:
        return True
    try:
        when = datetime.fromisoformat(record.fetched_at)
    except ValueError:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return datetime.now(UTC) - when > timedelta(days=max_age_days)


# ---------------------------------------------------------------------------
# OpenAlex client
# ---------------------------------------------------------------------------


def _doi_url(doi: str) -> str:
    doi = doi.strip().lstrip("/")
    if doi.lower().startswith("https://doi.org/"):
        return doi
    if doi.lower().startswith("doi:"):
        doi = doi[4:]
    return f"https://doi.org/{doi}"


def _openalex_headers(email: str) -> dict[str, str]:
    # Polite-pool identification — OpenAlex recommends including mailto.
    ua = "zotero-summarizer/1.0"
    if email:
        ua += f" (mailto:{email})"
    return {"User-Agent": ua}


def _first_openalex_author_surname(item: Item) -> str:
    if not item.authors:
        return ""
    first = item.authors[0]
    surname = first.split(",")[0] if "," in first else first.split()[-1]
    return re.sub(r"[^a-z]", "", surname.lower())


def _openalex_work_to_record(
    citekey: str, data: dict[str, Any], item: Item, source: str = "openalex"
) -> CitationRecord | None:
    """Convert an OpenAlex work payload to a ``CitationRecord``; return None if invalid."""
    count = data.get("cited_by_count")
    if not isinstance(count, int):
        return None
    external_id = data.get("id") or data.get("doi") or item.doi or ""
    return CitationRecord(
        citekey=citekey,
        citation_count=count,
        source=source,
        fetched_at=datetime.now(UTC).isoformat(),
        external_id=str(external_id),
    )


def _fetch_openalex(item: Item, client: httpx.Client, email: str) -> CitationRecord | None:
    headers = _openalex_headers(email)
    params: dict[str, Any] = {}
    if email:
        params["mailto"] = email

    # Step 1: DOI lookup (OpenAlex accepts "doi:10.x/y" as an ID).
    if item.doi:
        try:
            url = f"{_OPENALEX_BASE}/works/{_doi_url(item.doi)}"
            resp = client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                return _openalex_work_to_record(item.citekey, resp.json(), item)
        except httpx.HTTPError as e:
            logger.debug("OpenAlex DOI lookup failed for %s: %s", item.citekey, e)

    # Step 2: Title + year + author fallback. Only accept if author and year match.
    if item.title and item.year:
        try:
            search_params = {
                **params,
                "search": item.title,
                "filter": f"publication_year:{item.year}",
                "per-page": 5,
            }
            resp = client.get(f"{_OPENALEX_BASE}/works", headers=headers, params=search_params)
            if resp.status_code == 200:
                works = resp.json().get("results", [])
                target_surname = _first_openalex_author_surname(item)
                for work in works:
                    if work.get("publication_year") != item.year:
                        continue
                    authorships = work.get("authorships") or []
                    names = " ".join(
                        (a.get("author") or {}).get("display_name", "") for a in authorships
                    ).lower()
                    if not target_surname or target_surname in re.sub(r"[^a-z ]", "", names):
                        return _openalex_work_to_record(item.citekey, work, item)
        except httpx.HTTPError as e:
            logger.debug("OpenAlex title lookup failed for %s: %s", item.citekey, e)

    return None


# ---------------------------------------------------------------------------
# Semantic Scholar fallback
# ---------------------------------------------------------------------------


def _fetch_semantic_scholar(
    item: Item, client: httpx.Client, api_key: str
) -> CitationRecord | None:
    headers = {"User-Agent": "zotero-summarizer/1.0"}
    if api_key:
        headers["x-api-key"] = api_key
    fields = "citationCount,externalIds,title,year"

    if item.doi:
        try:
            resp = client.get(
                f"{_S2_BASE}/paper/DOI:{item.doi}",
                headers=headers,
                params={"fields": fields},
            )
            if resp.status_code == 200:
                data = resp.json()
                count = data.get("citationCount")
                if isinstance(count, int):
                    return CitationRecord(
                        citekey=item.citekey,
                        citation_count=count,
                        source="semantic_scholar",
                        fetched_at=datetime.now(UTC).isoformat(),
                        external_id=data.get("paperId") or item.doi,
                    )
        except httpx.HTTPError as e:
            logger.debug("Semantic Scholar lookup failed for %s: %s", item.citekey, e)

    return None


# ---------------------------------------------------------------------------
# Batch entry point
# ---------------------------------------------------------------------------


def fetch_citations_batch(
    items: dict[str, Item],
    config: Config,
    cache_dir: Path,
    *,
    client: httpx.Client | None = None,
    refresh: bool = False,
) -> dict[str, CitationRecord]:
    """Fetch citation counts for all items, returning a ``{citekey: CitationRecord}`` map.

    Reads any existing records from ``cache/citations.json`` and only fetches
    those that are missing or stale. When ``refresh=True``, all items are
    refreshed regardless of staleness. A single ``httpx.Client`` is reused for
    the whole batch unless one is passed in (tests).
    """
    from .cache import load_citations, save_citations

    cfg = config.citations
    if not cfg.enabled:
        logger.info("Citations disabled; skipping fetch")
        return load_citations(cache_dir)

    cached = load_citations(cache_dir)
    pending: list[Item] = []
    for ck, item in items.items():
        rec = cached.get(ck)
        if refresh or rec is None or is_stale(rec, cfg.max_age_days):
            pending.append(item)

    if not pending:
        logger.info("Citations: all %d records fresh", len(cached))
        return cached

    logger.info("Citations: fetching %d / %d items", len(pending), len(items))

    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=cfg.timeout_seconds)

    try:
        fetched = 0
        for item in pending:
            record = _fetch_openalex(item, client, cfg.email)
            if record is None and cfg.fallback == "semantic_scholar":
                record = _fetch_semantic_scholar(item, client, cfg.api_key)
            if record is not None:
                cached[item.citekey] = record
                fetched += 1
            if cfg.rate_limit_delay > 0:
                time.sleep(cfg.rate_limit_delay)
    except Exception as e:
        # Never break the pipeline — always save what we have.
        logger.warning("Citation fetch aborted after partial progress: %s", e)
    finally:
        if owns_client:
            client.close()

    save_citations(cached, cache_dir)
    logger.info("Citations: fetched %d new, %d total cached", fetched, len(cached))
    return cached


def top_n_by_citations(
    records: dict[str, CitationRecord], citekeys: list[str], n: int
) -> list[tuple[str, int]]:
    """Return ``[(citekey, count), ...]`` sorted by count desc, truncated to ``n``."""
    pairs: list[tuple[str, int]] = []
    for ck in citekeys:
        rec = records.get(ck)
        if rec and rec.citation_count is not None:
            pairs.append((ck, rec.citation_count))
    pairs.sort(key=lambda t: t[1], reverse=True)
    return pairs[:n]
