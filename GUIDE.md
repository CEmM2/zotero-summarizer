# zsum Developer Guide

Known caveats, design trade-offs, and things to watch when modifying `zsum`.

## Data-Flow Contracts

Each pipeline stage has a defined contract: what it consumes, what it produces, and what side-effects it performs. Use this table as the spec when adding or modifying a stage.

| Stage | Module | Consumes | Produces | Side-effects |
|-------|--------|----------|----------|--------------|
| **Indexer** | `indexer.py` | `Config` (BBT JSON path, SQLite path, collections filter, `zotero_pdf_base` for resolving relative PDF paths) | `LibraryIndex` (`items: dict[str, Item]`, `collections: dict[str, Collection]`) | Reads BBT JSON file; opens Zotero SQLite read-only |
| **Extractor** | `extractor.py` | `dict[str, Item]`, `Config` (page/char limits), optional `skip_citekeys: set[str]` | `dict[str, ExtractionResult]` (text, quality flag, page info); `extraction_report()` renders bounded 200-char text previews | Reads PDF files from disk via PyMuPDF |
| **Cards** | `cards.py` | `dict[str, Item]`, `dict[str, ExtractionResult]`, `Config`, `cache_dir: Path` | `dict[str, PaperCard]` (cached + newly generated); strict decode-validate-normalize pipeline rejects invalid LLM responses | LLM API calls; writes `cache/cards/{citekey}.json` |
| **Digests** | `digests.py` | `LibraryIndex`, `dict[str, PaperCard]`, `Config`, `cache_dir: Path` | `dict[str, str]` (collection\_key → markdown digest) | LLM API calls; writes `cache/digests/{col_key}.md` and `cache/digests/{col_key}_hashes.json`; reads `cache/membership.json` |
| **Publisher** | `publisher.py` | `LibraryIndex`, `Config`, optional `cards`, optional `digests`, optional `citations: dict[str, CitationRecord]` | None (void) | Writes Obsidian vault: `Collections/*.md`, `Papers/*.md`, `Library Index.md` |
| **Classifier** | `classifier.py` | `Item` | `paper_type: str` (one of research/review/survey/meta-analysis/tutorial) | Pure, metadata-only; runs during indexing |
| **Citations** | `citations.py` | `dict[str, Item]`, `Config`, `cache_dir` | `dict[str, CitationRecord]` | HTTP GETs to OpenAlex + Semantic Scholar (polite pool); writes `cache/citations.json`; respects `max_age_days` staleness |
| **Restructure** | `restructure.py` | `LibraryIndex`, `dict[str, str]` digests, optional cards, `Config` | `StructureAdvice` + rendered markdown report | Single LLM call; writes `cache/restructure_advice.json` and `cache/restructure_report.md`; never mutates collections |

**Invariants to maintain when adding a stage:**
- A stage must not mutate its inputs; all outputs are new objects.
- Side-effects (file I/O, LLM calls) must be documented here and in the module docstring.
- New cache files must follow the existing naming conventions (`cache/<subdir>/<key>.<ext>`).
- Item objects may carry an optional `library_id` loaded from BBT exports. Collection membership resolution prefers `(library_id, item_id)` when available, falling back to item-only matching.
- Card parsing uses strict validation: non-dict JSON payloads are rejected, dicts missing all expected fields (`problem`, `methods`, `key_findings`, `limitations`, `keywords`, `paper_type`) are rejected, and metadata (citekey, title, authors, year, venue, doi) is always sourced from the local Item.
- **Review classification is heuristic-then-LLM.** `classify_by_metadata()` runs at index time; the card LLM may override in `_normalize_fields()`. Fallback chain: LLM → heuristic → `"research"`. Known false-positive phrases (`peer review`, `code review`, `under review`) short-circuit to `"research"`.
- **Citation fetcher is advisory, not required.** All network failures are caught; disabled/offline runs must not break the pipeline. The cache (`cache/citations.json`) is the source of truth downstream — publisher and plugin_index read from it lazily.
- **Structure advisor is advisory-only.** `restructure.py` never writes back to Zotero, never mutates `LibraryIndex`, never reassigns papers. Report lives in `cache/restructure_advice.json` and `cache/restructure_report.md`.

## Cache & Serialization

`save_card()` calls `PaperCard.model_dump()` and writes JSON (`cache.py:49`).
`load_cached_cards()` reconstructs via `PaperCard(**data)` (`cache.py:70`).

**Caveat:** Every field on `PaperCard` must be JSON-serializable. Adding a
non-serializable field (e.g. `pathlib.Path`, `datetime`) will silently break
caching — `save_card` will raise, or `load_cached_cards` will fail to
reconstruct the object. If you need such a field, either exclude it from
`model_dump()` or add a custom serializer.

## Cache Invalidation

The pipeline uses a layered invalidation chain. Understanding the chain helps
predict when cached artifacts will be regenerated.

### Invalidation chain (in order)

1. **`prompt_version` → card regeneration.** `generate_cards_batch()` in
   `cards.py` loads a cached card only when its `_meta.prompt_version` matches
   the current config value. A mismatch means the card is treated as uncached
   and the LLM is called again. Bump `prompt_version` in `config.yaml` to force
   all cards to regenerate after changing a prompt template.

2. **Card content → card hash.** `card_content_hash()` in `cache.py` computes
   a SHA-256 digest of all card fields *excluding* `_meta`, using
   `json.dumps(data, sort_keys=True)` for a stable canonical form. Any change
   to a card's content fields produces a new hash.

3. **Card hash change → digest invalidation.** `any_card_content_changed()` in
   `cache.py` compares each card's current hash against the values saved in
   `{col_key}_hashes.json`. If any hash differs, the corresponding digest is
   considered stale and will be regenerated.

4. **Membership change → digest invalidation.** `generate_digests_batch()` in
   `digests.py` also compares the current sorted citekey list against the saved
   membership snapshot. Any addition or removal of items in a collection
   triggers regeneration even if no card content changed. (Reordering cannot
   trigger regeneration because the snapshot is always sorted before comparison.)

5. **`--force` bypasses all checks.** Both `cards` and `digests` subcommands
   accept `--force`, but their behaviour differs (see below).

### `--force` behavior: cards vs. digests

| | `cards --force` | `digests --force` |
|---|---|---|
| What is deleted | Nothing; items are simply not skipped | All `*.md` files in `cache/digests/` |
| What is regenerated | All cards — re-extracted from PDFs and re-sent to the LLM | All digests — re-synthesized from **existing** cards (no LLM call for cards) |
| Hash sidecar files (`*_hashes.json`) | Overwritten as new cards are saved | **Not** deleted; only `clear-cache --digests` or `clear-cache --all` removes them |

**Key difference:** `cards --force` is a full re-run of extraction + LLM for
every paper. `digests --force` only re-runs the digest synthesis step — it
reuses whatever card content is already cached. Use `digests --force` when you
want fresh collection summaries without re-spending card generation budget.

**Note on hash sidecar accumulation:** `{col_key}_hashes.json` files are never
deleted by `--force`. If a collection is removed from the library, its sidecar
file remains in `cache/digests/`. Run `clear-cache --digests` or
`clear-cache --all` to clean them up.

## Prompt Templates

Template variables in `prompts/paper_card.txt` and `prompts/collection_digest.txt`
are injected at runtime by:

- `_build_user_prompt()` in `cards.py:89`
- `_build_digest_prompt()` in `digests.py:110`

There is **no compile-time validation** that template placeholders match the
code. If you rename or remove a variable in the prompt file, the code will
silently produce a prompt with the literal placeholder text. Always update both
the prompt file and the corresponding builder function together.

## LLM Client Lifecycle

`llm.py` caches clients at module level (`_anthropic_client`, `_openai_client`).
This is safe for the CLI, which uses a single config per run.

If you reuse `zsum` as a library and switch configs between calls, the cached
client will still point to the original provider/key. Call `_reset_clients()`
between config changes. See `llm.py:15-26`.

## Membership Sorting

`save_membership()` sorts citekeys with Python's default `sorted()` before
writing (`cache.py:25`). On the next run, `digests.py` compares the saved list
to the current sorted list to detect membership changes.

If the sort order ever changes (e.g. locale-aware collation), **all digests will
regenerate** because the saved and current lists won't match even if membership
is unchanged. A future version may switch to set-based comparison to avoid this.

## `CardMeta` vs. `_meta` Dict

`CardMeta` is defined as a Pydantic model in `models.py`, but it is **never instantiated
at runtime**. The metadata stored alongside each cached card is written as a raw `_meta`
dict in `cache.py:save_card()` (keys: `model`, `prompt_version`, `generated_at`). When
loading, `_meta` is stripped before reconstructing the `PaperCard` object. The Pydantic
model exists for documentation and potential future validation, but current code bypasses it.

## Filename Collisions

`_safe_filename()` in `publisher.py` replaces unsafe characters with `_`. Two
different names can normalize to the same filename (e.g. `"Test:Paper"` and
`"Test|Paper"` both become `"Test_Paper"`).

The publisher uses a `_FilenameTracker` to detect collisions at write time. When
a collision occurs, it auto-numbers the duplicate (`Test_Paper_2.md`) and logs a
warning. After all notes are written, a summary of any collisions is logged.
