"""Index builder: reads BBT JSON + Zotero SQLite to produce a unified LibraryIndex."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import NamedTuple

from .classifier import classify_by_metadata
from .config import Config
from .models import Collection, Item, LibraryIndex

logger = logging.getLogger(__name__)


class ItemIdentity(NamedTuple):
    """Composite key for Zotero items: (library_id, item_id).

    Zotero's item_id is only unique within a library — a local library and a
    group library can both allocate the same integer. Pairing with library_id
    yields a globally stable identity for cross-library collection membership.
    """

    library_id: int
    item_id: int


def build_index(config: Config) -> LibraryIndex:
    """Main entry point. Build the full library index from BBT JSON + Zotero SQLite."""
    items = _load_bbt_items(config.bbt_json, config.zotero_pdf_base)
    collections, col_id_to_key = _load_collections(config.zotero_sqlite)
    _assign_items_to_collections(collections, items, config.zotero_sqlite, col_id_to_key)
    _build_collection_paths(collections)

    # Filter to requested collections if specified
    if config.collections:
        collections = _filter_collections(collections, config.collections)
        # Also trim items to only those referenced by the filtered collections
        referenced = {ck for col in collections.values() for ck in col.item_citekeys}
        items = {k: v for k, v in items.items() if k in referenced}

    # Build the final index keyed by citekey
    index = LibraryIndex(items=items, collections=collections)
    logger.info(
        "Index built: %d items (%d with PDF), %d collections",
        index.stats["total_items"],
        index.stats["with_pdf"],
        index.stats["total_collections"],
    )
    return index


# ---------------------------------------------------------------------------
# BBT JSON loading
# ---------------------------------------------------------------------------


def _load_bbt_items(bbt_path: Path, pdf_base_override: str) -> dict[str, Item]:
    """Load items from Better BibTeX JSON export."""
    with open(bbt_path) as f:
        data = json.load(f)

    # BBT JSON has a top-level "items" array and optional config fields
    raw_items = data if isinstance(data, list) else data.get("items", [])
    base_path = pdf_base_override or _detect_base_path(data)

    items: dict[str, Item] = {}
    skipped = 0

    for raw in raw_items:
        citekey = raw.get("citationKey", "")
        if not citekey:
            skipped += 1
            continue

        item = Item(
            citekey=citekey,
            zotero_key=raw.get("itemKey", raw.get("key", "")),
            library_id=raw.get("libraryID", None),
            item_id=raw.get("itemID", None),
            title=raw.get("title", ""),
            authors=_parse_authors(raw.get("creators", [])),
            year=_parse_year(raw.get("date", "")),
            venue=raw.get("publicationTitle", raw.get("proceedingsTitle", "")),
            doi=raw.get("DOI", ""),
            abstract=raw.get("abstractNote", ""),
            url=raw.get("url", ""),
            tags=[t["tag"] for t in raw.get("tags", []) if "tag" in t],
            pdf_path=_resolve_pdf(raw.get("attachments", []), base_path),
        )
        item.paper_type = classify_by_metadata(item)
        items[citekey] = item

    if skipped:
        logger.warning("Skipped %d items without citation keys", skipped)
    logger.info("Loaded %d items from BBT JSON", len(items))
    return items


def _detect_base_path(data: dict | list) -> str:
    """Try to extract baseAttachmentPath from BBT JSON config section."""
    if isinstance(data, dict):
        config = data.get("config", {})
        base: str = config.get("preferences", {}).get("baseAttachmentPath", "")
        if base:
            return base
    return ""


def _parse_authors(creators: list[dict]) -> list[str]:
    """Extract author names as 'Last, First' strings."""
    authors = []
    for c in creators:
        if c.get("creatorType") != "author":
            continue
        last = c.get("lastName", "")
        first = c.get("firstName", "")
        if last and first:
            authors.append(f"{last}, {first}")
        elif last:
            authors.append(last)
        elif c.get("name"):
            authors.append(c["name"])
    return authors


def _parse_year(date_str: str) -> int | None:
    """Extract a 4-digit year from a date string like '2020-09-01'."""
    if not date_str:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", date_str)
    return int(match.group()) if match else None


def _resolve_pdf(attachments: list[dict], base_path: str) -> Path | None:
    """Find the best PDF attachment path.

    Strategy:
    - Filter to PDF files only
    - Prefer larger files (heuristic for full text vs. supplementary)
    - Return the first/best match as an absolute Path
    """
    pdf_attachments = []
    for att in attachments:
        path_str = att.get("path", "")
        if not path_str:
            continue
        if not path_str.lower().endswith(".pdf"):
            continue
        pdf_attachments.append(path_str)

    if not pdf_attachments:
        return None

    # Resolve paths: if relative and we have a base, join them
    resolved = []
    for p in pdf_attachments:
        path = Path(p)
        if not path.is_absolute() and base_path:
            path = Path(base_path) / path
        resolved.append(path)

    # Prefer the largest existing file
    existing = [(p, p.stat().st_size) for p in resolved if p.exists()]
    if existing:
        existing.sort(key=lambda x: x[1], reverse=True)
        return existing[0][0]

    # If none exist on disk, return the first one anyway (for reporting)
    return resolved[0]


# ---------------------------------------------------------------------------
# Zotero SQLite: collections
# ---------------------------------------------------------------------------


def _load_collections(
    sqlite_path: Path,
) -> tuple[dict[str, Collection], dict[int, str]]:
    """Load collection tree from Zotero SQLite.

    Returns:
        A tuple of (collections dict keyed by collection key,
        id_to_key mapping from collectionID to collection key).
    """
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT collectionID, collectionName, parentCollectionID, key FROM collections"
        ).fetchall()
    finally:
        conn.close()

    # Build a mapping of collectionID -> parentCollectionID for path building
    id_to_key: dict[int, str] = {}
    collections: dict[str, Collection] = {}

    for row in rows:
        col_key = row["key"]
        id_to_key[row["collectionID"]] = col_key

    for row in rows:
        col_key = row["key"]
        parent_id = row["parentCollectionID"]
        parent_key = id_to_key.get(parent_id) if parent_id else None

        collections[col_key] = Collection(
            key=col_key,
            name=row["collectionName"],
            parent_key=parent_key,
        )

    # Set child_keys
    for col in collections.values():
        if col.parent_key and col.parent_key in collections:
            collections[col.parent_key].child_keys.append(col.key)

    logger.info("Loaded %d collections from Zotero SQLite", len(collections))
    return collections, id_to_key


def _assign_items_to_collections(
    collections: dict[str, Collection],
    items: dict[str, Item],
    sqlite_path: Path,
    col_id_to_key: dict[int, str],
) -> None:
    """Read collectionItems from SQLite and assign citekeys to collections."""
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = _load_collection_item_rows(conn)
    finally:
        conn.close()

    identity_to_citekey: dict[ItemIdentity, str] = {}
    item_id_candidates: dict[int, list[str]] = {}
    for item in items.values():
        if item.item_id is not None:
            item_id_candidates.setdefault(item.item_id, []).append(item.citekey)
            if item.library_id is not None:
                identity_to_citekey[ItemIdentity(item.library_id, item.item_id)] = item.citekey
        else:
            logger.warning(
                "Item '%s' has no item_id and will be excluded from collection assignment",
                item.citekey,
            )

    unique_item_id_matches = {
        item_id: citekeys[0]
        for item_id, citekeys in item_id_candidates.items()
        if len(citekeys) == 1
    }

    # Use sets for dedup, then convert to sorted lists
    col_items: dict[str, set[str]] = {k: set() for k in collections}
    for row in rows:
        col_key = col_id_to_key.get(row["collectionID"])
        citekey = _resolve_collection_item_citekey(
            row["itemID"],
            row["libraryID"],
            identity_to_citekey,
            unique_item_id_matches,
        )
        if col_key and citekey and col_key in collections:
            col_items[col_key].add(citekey)

    for col_key, citekeys in col_items.items():
        collections[col_key].item_citekeys = sorted(citekeys)


def _load_collection_item_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Load collection membership rows with library context when the DB exposes it."""
    collection_item_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(collectionItems)").fetchall()
    }
    if "libraryID" in collection_item_columns:
        return conn.execute(
            """
            SELECT collectionID, itemID, libraryID
            FROM collectionItems
            """
        ).fetchall()

    # Join with collections table to get the library context of the membership.
    # In Zotero, collections belong to a library, so this is the stable source
    # of truth—unlike items.itemID which is not globally unique across libraries.
    collection_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(collections)").fetchall()
    }
    if "libraryID" in collection_columns:
        return conn.execute(
            """
            SELECT DISTINCT ci.collectionID, ci.itemID, c.libraryID
            FROM collectionItems AS ci
            JOIN collections AS c
                ON ci.collectionID = c.collectionID
            """
        ).fetchall()

    return conn.execute(
        """
        SELECT collectionID, itemID, NULL AS libraryID
        FROM collectionItems
        """
    ).fetchall()


def _resolve_collection_item_citekey(
    item_id: int,
    library_id: int | None,
    identity_to_citekey: dict[ItemIdentity, str],
    unique_item_id_matches: dict[int, str],
) -> str | None:
    """Resolve membership rows to citekeys without reintroducing mixed-library collisions."""
    if library_id is not None:
        citekey = identity_to_citekey.get(ItemIdentity(library_id, item_id))
        if citekey is not None:
            return citekey

    return unique_item_id_matches.get(item_id)


def _build_collection_paths(collections: dict[str, Collection]) -> None:
    """Build human-readable hierarchical paths like 'Parent / Child / Grandchild'."""

    def _get_path(col_key: str) -> str:
        col = collections[col_key]
        if col.parent_key and col.parent_key in collections:
            return _get_path(col.parent_key) + " / " + col.name
        return col.name

    for key in collections:
        collections[key].path = _get_path(key)


def _filter_collections(
    collections: dict[str, Collection],
    requested: list[str],
) -> dict[str, Collection]:
    """Filter to only the requested collections. Include children.

    Each token in *requested* is matched against both collection
    keys and collection names (exact match). A collection is
    included if its ``key`` or ``name`` equals any token.
    Descendants of every matched collection are included
    automatically. The result is deduplicated — a collection
    matched by both its key and name appears only once.
    """
    requested_set = set(requested)

    # Build a reverse lookup: name -> list of keys (names may not be unique)
    name_to_keys: dict[str, list[str]] = {}
    for key, col in collections.items():
        name_to_keys.setdefault(col.name, []).append(key)

    # Find matching collection keys (by key OR by name)
    matched_keys: set[str] = set()
    for token in requested_set:
        # Match by collection key
        if token in collections:
            matched_keys.add(token)
            _collect_descendants(collections, token, matched_keys)
        # Match by collection name
        for key in name_to_keys.get(token, []):
            if key not in matched_keys:
                matched_keys.add(key)
                _collect_descendants(collections, key, matched_keys)

    filtered = {k: v for k, v in collections.items() if k in matched_keys}
    logger.info(
        "Filtered to %d collections (from %d filter tokens)",
        len(filtered),
        len(requested),
    )
    return filtered


def _collect_descendants(
    collections: dict[str, Collection],
    key: str,
    result: set[str],
) -> None:
    """Recursively collect all descendant collection keys."""
    for child_key in collections[key].child_keys:
        result.add(child_key)
        _collect_descendants(collections, child_key, result)
