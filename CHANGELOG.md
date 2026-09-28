# Changelog

## [Unreleased]

### Added
- **`zsum setup-model` command**: one-command local LLM configuration for an existing Ollama install. Checks that Ollama is installed and running, pulls a model, writes `config.yaml` with the correct `openai_compat` settings, and verifies the model responds. Four size tiers (small/medium/large/xlarge) are defined in an external `model_tiers.yaml` data file — editable without touching code. Flags: `--size`, `--model` (any Ollama model), `--list`, `--dry-run`.
- **Native Codex CLI backend** (`llm.provider: codex_exec`): `zsum` can now use `codex exec` as an LLM provider for cards and digests. The backend shells out through the local Codex CLI, parses JSONL usage/final-message output, and supports configurable `binary`, `model`, `sandbox`, and token limits.
- **Schema-constrained Codex digests**: Codex-backed collection digests now use `codex exec --output-schema` plus a new structured prompt (`src/zsum/prompts/collection_digest_structured.txt`). `digests.py` validates the structured response and renders the canonical markdown headings itself, keeping digest layout stable.
- **Gemini CLI backend** (`llm.provider: gemini_cli`): `zsum` can now use the Gemini CLI (`gemini -p`) as an LLM provider for cards and digests, with Obsidian plugin config editing support.
- **Codex prompt-reviewer subagent**: added `.codex/agents/prompt-reviewer.md` as the Codex-side mirror of the existing Claude prompt-reviewer workflow for reviewing prompt-template changes.
- **MkDocs documentation site**: documentation now lives under the MkDocs tree with installation, command, provider, plugin, reference, and development pages.

### Changed
- **Cross-platform compatibility**: the Obsidian plugin now uses platform-aware process termination (no more `SIGTERM`/`SIGKILL` on Windows). The Python CLI was already cross-platform; `config.example.yaml` documents that `~/Zotero/` paths expand correctly on macOS, Linux, and Windows.
- **Publisher filename resolution**: Obsidian filename and wikilink resolution now lives in `zsum.publisher.resolver`, preserving existing naming behavior while exposing a reusable public surface for publisher-adjacent tools.
- **Config and docs**: `config.example.yaml`, `README.md`, `docs/getting-started/installation.md`, `docs/guide/providers.md`, and `docs/guide/commands.md` now document the `codex_exec` and `gemini_cli` providers, `setup-model` command, and structured digest behavior.

### Fixed
- **`zsum setup-model` config errors**: malformed or unreadable existing YAML now reports a Click error without a traceback and does not overwrite the config file.
- **Obsidian plugin tests**: plugin test scripts now include runner coverage, including platform-specific cancel signal behavior.

## [1.1.0] - 2026-04-20

### Added
- **Review paper detection** (`zsum reviews`): heuristic classifier flags review/survey/meta-analysis/tutorial papers at index time; the LLM can confirm or override during card generation. Reviews render in a dedicated `## Review Papers` section inside each collection note, carry a `paper_type` frontmatter field on paper notes, and show as a separate group with a badge in the Obsidian plugin.
- **Citation counts** (`zsum citations`): fetches citation counts from OpenAlex (primary, polite-pool with optional email) and Semantic Scholar (fallback). DOI-first lookup with conservative title+year+author fallback. Persisted to `cache/citations.json` with a configurable staleness threshold (default 30 days) and per-request rate-limit delay. Counts appear in paper-note frontmatter, a per-collection `## Most Cited Papers` section, and the plugin's paper list (sortable by citation count). Adds `httpx>=0.27` runtime dependency.
- **Collection Structure Advisory** (`zsum restructure`): single-LLM-call advisor that inspects the hierarchy and existing digests and produces a markdown advisory report proposing renames, splits, merges, new sub-collections, and flagging too-broad collections. Structure-only — never reassigns papers. Cached to `cache/restructure_advice.json` and `cache/restructure_report.md`. Exposed as a "Restructure" button in the Obsidian plugin.
- **One-shot installer** (`install.sh`): bash script that installs the CLI (`uv tool install -e .`), builds the Obsidian plugin (`npm ci && npm run build`), and copies `main.js`, `manifest.json`, and `styles.css` into `<vault>/.obsidian/plugins/obsidian-zsum/`. Accepts the vault path as a positional arg, `--vault`, or `VAULT_PATH` env var. Flags: `--cli-only`, `--plugin-only`, `--skip-deps`, `--skip-build`.

### Changed
- **Models**: additive fields — `Item.paper_type`, `Item.is_review` (derived), `PaperCard.paper_type`. New models: `CitationRecord`, `StructureSuggestion`, `StructureAdvice`. Backward-compatible defaults; no prompt_version bump required.
- **Config**: new `citations` and `restructure` sections (both optional, sensible defaults). `config.example.yaml` documents all fields.
- **Plugin**: new "Citations" and "Restructure" stage buttons in the run panel; paper list gains a "Sort by citations" toggle, a Citations column, and a Review Papers group header.
- **Installation Guide** (`docs/getting-started/installation.md`): added `httpx` note, optional step for enabling citation lookups (OpenAlex polite pool), and verify-step mentions of the new no-cost commands.
- **User Guide** (`docs/guide/`): full sections for `zsum reviews`, `zsum citations`, and `zsum restructure`; full-pipeline-with-enrichment workflow; clarified that `clear-cache` does not touch citations/restructure caches.
- **Plugin Guide** (`docs/plugin/index.md`): updated button table, paper-list columns (Citations), Review Papers group, the sort toggle, and a rewritten Installation section that covers the build step, the three release files to copy (`main.js`, `manifest.json`, `styles.css`), and an explicit Upgrading-from-1.0.x subsection.
- **README**: short feature blurb at the top; enrichment commands listed in Usage; caching section covers citations and restructure.

## [1.0.1] - 2026-04-19

### Added
- **Global CLI install**: `zsum` can now be installed as a global tool via `uv tool install -e .`, making it available system-wide without `uv run` prefix. Editable mode means source changes take effect immediately.

### Changed
- **README**: added "Global Install" section under Setup, updated Usage examples to use `zsum` directly.
- **Installation Guide** (`docs/getting-started/installation.md`): added global install option alongside `uv run` instructions.
- **User Guide** (`docs/guide/commands.md`): updated all command examples to show `zsum` directly (without `uv run` prefix).
- **Plugin Guide** (`docs/plugin/index.md`): updated default Python command to `zsum` and added note about global install.

## [1.0.0] - 2026-04-16

First stable release — the CLI pipeline is feature-complete and now ships with an Obsidian plugin for graphical operation.

### Added
- **Obsidian plugin** (`obsidian-zsum`): TypeScript-based UI that surfaces the `zsum` pipeline inside Obsidian. Provides a status bar with library-wide counters, a collection tree with digest-state indicators, a paper list with card-state badges, and pipeline controls with live log output, cost estimation, and subprocess management. Desktop-only, requires Obsidian >= 1.4.0.
- **Plugin settings panel**: configurable paths (`config.yaml`, Python command), LLM cost parameters for per-card cost estimation, and a "Test command" button to verify the CLI is reachable.
- **Per-collection digest regeneration**: the plugin can trigger `zsum digests --collection <name>` from the paper list header.
- **Plugin documentation** (`docs/plugin/index.md`): installation walkthrough, settings reference, UI region descriptions, command palette entries, data flow, and troubleshooting.

### Changed
- **README**: added Obsidian Plugin section and Plugin Guide link to the documentation list.

## [0.1.2] - 2026-04-13

Close remaining gaps from the V1 spec, plus PR #48 review follow-ups.

### Added
- **Library-aware collection identity** (`indexer.py`): `collectionItems` rows are resolved via `(libraryID, itemID)` composite keys, preventing cross-library citekey collisions when a group library and local library share an `itemID`. Falls back to `collections.libraryID` when `collectionItems` lacks the column (real Zotero schema path).
- **Collection filter parity** (`indexer.py`): `_filter_collections()` now matches each token against both collection **keys** and **names**, with set-based dedup and recursive descendant inclusion. Regression test `test_filter_collections_by_key` covers the key-based path.
- **Strict paper card validation** (`cards.py`): three-stage parse pipeline (`_decode_response` → `_validate_structure` → `_normalize_fields`) rejects non-dict JSON and empty payloads before normalization. Metadata is always sourced from the local `Item`, never the LLM. New `_EXPECTED_LLM_FIELDS` frozenset enumerates the LLM's contract.
- **Extraction preview** (`extractor.py`): `extraction_report()` now includes a `## Text Previews` section with bounded 200-char excerpts per item (quality flag + first characters of extracted text). Transient only — no persistent cache files.
- **Regression tests** (`tests/regression/`): 85 new tests covering filter parity, card validation stages, preview bounds, and doc-critical contracts (CLI subcommand set, config fields, digest prompt `[[@` syntax, `TextQuality` enum).

### Changed
- **Spec alignment** (`dev/specs/Zotero_Collection_Summarizer_SpecsV1.md`): corrected module names (`card_generator.py` → `cards.py`, `digest_generator.py` → `digests.py`), documented `library_id` composite key fallback, added validation and preview notes.
- **README** (`README.md`) and `config.example.yaml`: `extract` subcommand now documents text previews; collections filter comment reads "names or keys".
- **GUIDE** (`GUIDE.md`): Data-Flow Contracts table extended with library_id invariant, strict card validation rule, and preview-is-transient note. Invariants section updated with the new validation rules.

### Fixed
- **PR #48 review** (`1beefa5`): addressed all 6 review findings — 1 HIGH-priority finding from Gemini (cross-library `itemID` collision in `_load_collection_item_rows` fallback JOIN) and 5 Copilot nits (unused imports, stale docstrings, test determinism).

### Commits
- `6ed4db5` feat(phase-2): collection filter parity — support name and key matching
- `8f809e3` feat(phase-3): strict paper card validation — reject malformed payloads
- `cf1686e` feat(phase-4): extraction preview — bounded text excerpts in Phase A output
- `4611cfa` docs(phase-5): align spec, README, GUIDE with shipped V1 + regression tests
- `1beefa5` fix(review): address PR #48 review feedback

## [0.1.1] - 2026-03-04

Post-review fixes from PR #1 diff review.

### Added
- `CHANGELOG.md` for tracking project changes.
- mypy step in CI workflow (`.github/workflows/ci.yml`).
- CLI tests: `all` command pipeline, `stats` card/digest output, `skeleton` collection notes, `extract` quality report, `clear-cache` removal.
- Cache tests for content-hash functions (`card_content_hash`, `save_digest_hashes`, `any_card_content_changed`).

### Changed
- Replaced mtime-based digest invalidation (`any_card_newer_than_digest`) with SHA-256 content-hash comparison (`any_card_content_changed`). Stores `{col_key}_hashes.json` sidecar files alongside digests.

### Fixed
- mypy `no-any-return` errors in `cache.py` and `indexer.py`.
- Added mypy overrides for untyped `yaml` and `fitz` imports.

## [0.1.0] - 2026-03-04

Initial release (R0 milestone).

### Added
- **CLI** (`zsum`): Click-based CLI with subcommands `index`, `extract`, `cards`, `digests`, `publish`, `skeleton`, `all`, `stats`, `clear-cache`.
- **Indexer**: Parses Better BibTeX JSON exports and Zotero SQLite for items, collections, and hierarchy.
- **Extractor**: PyMuPDF-based PDF text extraction (first N + last N pages) with quality flagging (good/degraded/no_pdf).
- **LLM abstraction**: Provider-agnostic `complete()` supporting Anthropic SDK and OpenAI-compatible endpoints (LM Studio, Ollama).
- **Paper cards**: Per-paper structured JSON summaries via LLM, cached by citekey + prompt_version.
- **Collection digests**: Per-collection markdown digests via LLM, processed bottom-up. Invalidated on membership or card content changes.
- **Publisher**: Writes Obsidian vault with `Collections/` and `Papers/` directories, frontmatter, wikilinks, and `_index.md`.
- **Two-phase publishing**: `skeleton` (no LLM cost) and `all` (full pipeline).
- **Incremental caching**: Cards and digests cached in `cache/` directory.
- **CI**: GitHub Actions workflow with ruff lint/format, mypy type checking, and pytest.
- **Tests**: Unit tests for indexer, extractor, cards, digests, cache, CLI, and publisher.
- **Type annotations**: Full type annotations across all modules, checked with mypy.
