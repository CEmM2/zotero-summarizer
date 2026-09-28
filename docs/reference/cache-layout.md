# Cache Layout

All cached data lives under `cache_dir` (default: `./cache`). This page documents every file the pipeline reads and writes.

## Directory Structure

```
cache/
├── membership.json              # Collection → citekey membership snapshot
├── index.json                   # Plugin index (collection + paper metadata)
├── citations.json               # Citation count cache
├── restructure_advice.json      # Structure advisor output (structured)
├── restructure_report.md        # Structure advisor output (rendered markdown)
├── cards/
│   ├── {citekey}.json          # Per-paper card with _meta block
│   └── ...
├── digests/
│   ├── {col_key}.md            # First-pass collection digest
│   ├── {col_key}_hashes.json   # SHA-256 hashes of cards used in the digest
│   └── ...
└── redigests/
    ├── {col_key}.md            # Final publish-ready collection digest
    ├── {col_key}.json          # Source-digest hash + provider metadata
    └── ...
```

## File Details

### `membership.json`

Written by `save_membership()`, read by `load_membership()`.

Maps each collection key to a sorted list of citekeys. Used to detect membership changes between runs.

```json
{
  "ABC123": ["smith2017", "zhao2020", "jones2019"],
  "DEF456": ["wang2021", "liu2022"]
}
```

### `index.json`

Written by `save_plugin_index()`, read by the Obsidian plugin.

Contains collection and paper metadata for the plugin UI, including redigest state and citation counts.

### `citations.json`

Written by `fetch_citations_batch()`, read by `load_citations()`.

Maps citekeys to `CitationRecord` objects:

```json
{
  "smith2017": {
    "citekey": "smith2017",
    "citation_count": 3847,
    "source": "openalex",
    "fetched_at": "2026-04-20T10:30:00Z",
    "external_id": "W123456789"
  }
}
```

### `cards/{citekey}.json`

Written by `save_card()`, read by `load_cached_cards()`.

Structured JSON summary for a single paper, plus a `_meta` block:

```json
{
  "citekey": "smith2017",
  "title": "Phase field modeling of crack propagation",
  "authors": ["Smith, J.", "Doe, A."],
  "year": 2017,
  "problem": "...",
  "methods": ["..."],
  "key_findings": ["..."],
  "limitations": ["..."],
  "keywords": ["phase field", "fracture"],
  "text_quality": "good",
  "paper_type": "research",
  "_meta": {
    "model": "claude-sonnet-4-6",
    "prompt_version": 1,
    "generated_at": "2026-04-20T10:00:00Z"
  }
}
```

The `_meta` block is stripped when loading — it is not part of the `PaperCard` model.

**Invalidation:** Cards are skipped (not regenerated) when their `_meta.prompt_version` matches the current config value. Change `prompt_version` to force regeneration.

### `digests/{col_key}.md`

Written by `generate_digests_batch()`, read by `load_cached_digests()`.

Rendered markdown digest for a collection. Contains sections like Summary, Key Themes, Common Methods, and Gaps.

### `digests/{col_key}_hashes.json`

Written by `save_digest_hashes()`, read by `any_card_content_changed()`.

SHA-256 content hashes of each card that contributed to the digest:

```json
{
  "smith2017": "a1b2c3d4e5...",
  "zhao2020": "f6g7h8i9j0..."
}
```

If any hash differs on the next run, the digest is considered stale.

!!! note "Accumulation"
    Hash sidecar files are not removed when a collection is deleted from Zotero. Run `clear-cache --digests` to clean them up.

### `redigests/{col_key}.md`

Written by `save_redigest()`, read by `load_cached_redigests()`.

The final publish-ready digest. The publisher prefers this over the first-pass digest.

### `redigests/{col_key}.json`

Sidecar metadata for the redigest:

```json
{
  "source_digest_hash": "sha256...",
  "provider": "anthropic",
  "model": "claude-sonnet-4-6",
  "generated_at": "2026-04-20T11:00:00Z"
}
```

Used to detect whether the redigest is still fresh (i.e., the underlying first-pass digest hasn't changed).

### `restructure_advice.json`

Structured output from `advise_structure()`. Contains the overall assessment, suggestions, and proposed hierarchy.

### `restructure_report.md`

Rendered markdown report from `render_advice_report()`. Human-readable version of the advisory.

## Cache Operations

| Operation | Effect |
|---|---|
| `clear-cache --cards` | Deletes all `cards/*.json`, recreates empty directory |
| `clear-cache --digests` | Deletes all `digests/*.md` and `digests/*.json`, recreates empty directory |
| `clear-cache --all` | Both of the above |

!!! warning
    `clear-cache` does **not** remove `redigests/`, `citations.json`, `restructure_*`, `index.json`, or `membership.json`. Delete these manually for a full reset.
