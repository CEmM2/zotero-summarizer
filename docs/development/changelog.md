# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added
- **`zsum setup-model` command**: one-command local LLM configuration for an existing [Ollama](https://ollama.com) install. Checks that Ollama is installed and running, pulls a model, writes `config.yaml`, and verifies the model responds. Four size tiers (small/medium/large/xlarge) defined in an external `model_tiers.yaml` — editable without touching code. Flags: `--size`, `--model`, `--list`, `--dry-run`.
- **Native Codex CLI backend** (`llm.provider: codex_exec`): `zsum` can now use `codex exec` as an LLM provider for cards and digests. The backend shells out through the local Codex CLI, parses JSONL usage/final-message output, and supports configurable `binary`, `model`, `sandbox`, and token limits.
- **Schema-constrained Codex digests**: Codex-backed collection digests now use `codex exec --output-schema` plus a new structured prompt (`src/zsum/prompts/collection_digest_structured.txt`). `digests.py` validates the structured response and renders the canonical markdown headings itself, keeping digest layout stable.
- **Gemini CLI backend** (`llm.provider: gemini_cli`): `zsum` can now use the Gemini CLI (`gemini -p`) as an LLM provider for cards and digests.
- **MkDocs documentation**: Full documentation site using MkDocs with Material theme.

### Changed
- **Cross-platform compatibility**: Obsidian plugin uses platform-aware process termination (Windows support). Python CLI confirmed cross-platform. `config.example.yaml` documents path expansion on all OSes.
- **Publisher filename resolution**: Obsidian filename and wikilink resolution now lives in `zsum.publisher.resolver`, preserving existing naming behavior while exposing a reusable public surface for publisher-adjacent tools.
- **Config and docs**: `config.example.yaml`, `README.md`, `docs/getting-started/installation.md`, `docs/guide/providers.md`, and `docs/guide/commands.md` now document the `codex_exec` and `gemini_cli` providers and the `setup-model` command.

### Fixed
- **`zsum setup-model` config errors**: malformed or unreadable existing YAML now reports a Click error without a traceback and does not overwrite the config file.
- **Obsidian plugin tests**: plugin test scripts now include runner coverage, including platform-specific cancel signal behavior.

## [1.1.0] - 2026-04-20

### Added
- **Review paper detection** (`zsum reviews`): heuristic classifier flags review/survey/meta-analysis/tutorial papers at index time; the LLM can confirm or override during card generation.
- **Citation counts** (`zsum citations`): fetches citation counts from OpenAlex (primary) and Semantic Scholar (fallback). DOI-first lookup with conservative title+year+author fallback. Adds `httpx>=0.27` runtime dependency.
- **Collection Structure Advisory** (`zsum restructure`): single-LLM-call advisor that produces a markdown advisory report proposing renames, splits, merges, and new sub-collections.
- **One-shot installer** (`install.sh`): bash script that installs the CLI and the Obsidian plugin.

### Changed
- **Models**: `Item.paper_type`, `Item.is_review`, `PaperCard.paper_type`. New models: `CitationRecord`, `StructureSuggestion`, `StructureAdvice`.
- **Config**: new `citations` and `restructure` sections.
- **Plugin**: new Citations and Restructure stage buttons; paper list gains citation sort toggle and Review Papers group.

## [1.0.1] - 2026-04-19

### Added
- **Global CLI install**: `zsum` can be installed as a global tool via `uv tool install -e .`.

## [1.0.0] - 2026-04-16

First stable release with full CLI pipeline and Obsidian plugin.

### Added
- **Obsidian plugin** (`obsidian-zsum`): TypeScript-based UI with status bar, collection tree, paper list, and pipeline controls.
- **Plugin settings panel**: configurable paths, cost parameters, and test button.
- **Per-collection digest regeneration** from the plugin UI.

## [0.1.2] - 2026-04-13

### Added
- **Library-aware collection identity**: composite `(libraryID, itemID)` keys prevent cross-library collisions.
- **Collection filter parity**: matching by both keys and names.
- **Strict paper card validation**: three-stage parse pipeline.
- **Extraction preview**: bounded 200-char text excerpts.
- **Plan regression tests**: 85 new tests.

## [0.1.1] - 2026-03-04

### Added
- `CHANGELOG.md`, mypy CI step, CLI tests, cache tests.

### Changed
- SHA-256 content-hash comparison replaces mtime-based digest invalidation.

## [0.1.0] - 2026-03-04

Initial release (R0 milestone).

### Added
- CLI with all core subcommands.
- Indexer, Extractor, LLM abstraction, Paper cards, Collection digests, Publisher.
- Two-phase publishing, incremental caching, CI, tests, type annotations.
