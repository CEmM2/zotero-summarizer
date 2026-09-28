# Developer Guide

Known caveats, design trade-offs, and things to watch when modifying `zsum`.

## Development Setup

```bash
git clone https://github.com/CEmM2/zotero-summarizer.git
cd zotero-summarizer
uv sync  # installs all deps including dev
```

### Running Tests

```bash
uv run pytest tests/ -v                                              # all tests
uv run pytest tests/test_indexer.py                                  # single module
uv run pytest tests/test_indexer.py::TestBuildIndex::test_loads_all_items  # single test
```

### Linting & Formatting

```bash
uv run ruff check src/ tests/    # lint
uv run ruff format src/ tests/   # format
uv run mypy src/                 # type check
```

### Code Style

- Python 3.11+, ruff with line-length 100, double quotes
- Ruff rules: `E`, `F`, `I` (isort), `UP` (pyupgrade), `B` (bugbear), `SIM` (simplify)
- Pydantic v2 for data models, Click for CLI
- mypy with `warn_return_any` (not strict mode)

## Data-Flow Contracts

Each pipeline stage has a defined contract. Use this table when adding or modifying a stage:

| Stage | Module | Consumes | Produces | Side-effects |
|---|---|---|---|---|
| **Indexer** | `indexer.py` | Config (BBT JSON, SQLite, filter, `zotero_pdf_base`) | `LibraryIndex` | Reads BBT JSON; opens Zotero SQLite read-only |
| **Extractor** | `extractor.py` | `dict[str, Item]`, Config, optional `skip_citekeys` | `dict[str, ExtractionResult]` | Reads PDF files via PyMuPDF |
| **Cards** | `cards.py` | Items, extractions, Config, `cache_dir` | `dict[str, PaperCard]` | LLM API calls; writes `cache/cards/*.json` |
| **Digests** | `digests.py` | `LibraryIndex`, cards, Config, `cache_dir` | `dict[str, str]` (markdown) | LLM API calls; writes digests + hashes |
| **Publisher** | `publisher/` | `LibraryIndex`, Config, optional cards/digests/citations | None | Writes Obsidian vault |
| **Classifier** | `classifier.py` | `Item` | `paper_type: str` | Pure, metadata-only |
| **Citations** | `citations.py` | Items, Config, `cache_dir` | `dict[str, CitationRecord]` | HTTP GETs; writes `cache/citations.json` |
| **Restructure** | `restructure.py` | `LibraryIndex`, digests, cards, Config | `StructureAdvice` + report | Single LLM call; writes cache files |

### Invariants

- A stage must not mutate its inputs; all outputs are new objects
- Side-effects (file I/O, LLM calls) must be documented in the module docstring
- New cache files must follow existing naming conventions (`cache/<subdir>/<key>.<ext>`)
- `Item.library_id` enables cross-library dedup — collection membership uses `(library_id, item_id)` when available
- Card parsing uses strict validation: non-dict JSON is rejected, metadata is always sourced from the local `Item`
- Review classification uses heuristic-then-LLM: `classify_by_metadata()` runs at index time, the card LLM may override
- Citation fetcher is advisory — network failures never break the pipeline
- Structure advisor is advisory-only — never writes back to Zotero

## Cache & Serialization

`save_card()` calls `PaperCard.model_dump()` and writes JSON. `load_cached_cards()` reconstructs via `PaperCard(**data)`.

!!! warning "Serialization constraint"
    Every field on `PaperCard` must be JSON-serializable. Adding a non-serializable field (e.g., `pathlib.Path`, `datetime`) will break caching. Use `model_dump()` exclusions or custom serializers if needed.

## Prompt Templates

Template variables in `prompts/paper_card.txt` and `prompts/collection_digest.txt` are injected at runtime by:

- `_build_user_prompt()` in `cards.py`
- `_build_digest_prompt()` in `digests.py`

!!! warning "No compile-time validation"
    Template placeholders are not validated. If you rename a variable in the prompt file, the code silently includes the literal placeholder text. Always update both the prompt file and the builder function together.

## Membership Sorting

`save_membership()` sorts citekeys with `sorted()` before writing. `digests.py` compares saved lists to current sorted lists. If the sort order ever changes (e.g., locale-aware collation), all digests will regenerate spuriously.

## `CardMeta` vs. `_meta` Dict

`CardMeta` is defined as a Pydantic model but is never instantiated at runtime. The `_meta` block is written as a raw dict and stripped when loading. The Pydantic model exists for documentation and potential future validation.

## Filename Collisions

`safe_filename()` in `publisher/resolver.py` replaces unsafe characters with `_`. Different names can collide (e.g., `"Test:Paper"` and `"Test|Paper"` both become `"Test_Paper"`). `FilenameTracker` detects collisions at write time and auto-numbers duplicates.

## Testing Gotchas

- `_write_config()` in `tests/test_cli.py` must include `llm.anthropic.model` for commands using `require_llm=True`
- `pytest.importorskip("fitz")` guards PDF tests — they silently skip if PyMuPDF is missing
- Mock `complete_with_retry` at the call site (e.g., `zsum.cards`), not at `zsum.llm`

## Building the Docs

```bash
uv run mkdocs serve     # local dev server at http://127.0.0.1:8000
uv run mkdocs build     # build static site to site/
```
