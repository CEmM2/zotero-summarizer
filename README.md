# zotero-summarizer

Generate AI-powered summaries of your Zotero library collections as an Obsidian vault.

**What it does** — For each paper: extracts PDF text, produces a structured LLM summary
(problem, methods, findings, limitations, keywords). For each collection: synthesizes a
digest from its paper cards. Publishes everything as an interlinked Obsidian vault. Also
detects review/survey papers, fetches citation counts from OpenAlex/Semantic Scholar,
and can generate an advisory report on your collection hierarchy.

## Prerequisites

1. **Zotero** with the [Better BibTeX](https://retorque.re/zotero-better-bibtex/) plugin installed
2. **Python 3.11+** and [uv](https://docs.astral.sh/uv/)
3. One LLM backend:
   - **Quick start**: install and start [Ollama](https://ollama.com), then run `zsum setup-model` to pull and configure a local model
   - the **Claude Code CLI** (`claude auth`) — used by the `anthropic` provider
   - a local OpenAI-compatible server (LM Studio, Ollama, etc.)
   - the **Codex CLI** (`codex login`)
   - the **Gemini CLI** (`gemini auth`) — used by the `gemini_cli` provider

### Better BibTeX Setup

1. Install the Better BibTeX plugin in Zotero
2. In Zotero: File → Export Library → Format: "Better BibTeX JSON"
3. Check "Keep updated" to auto-sync on library changes
4. Save the `.json` file to a known path (this is your `bbt_json` path in config)

### PDF Path Resolution

`zsum` reads PDF file paths from the BBT JSON export. Two modes:

- **Absolute paths** (default for most setups): works out of the box, leave `zotero_pdf_base` empty
- **Relative paths** (e.g., when using ZotMoov with a shared PDF directory): set `zotero_pdf_base` in config to the directory containing your PDFs

## Setup

```bash
uv sync
cp config.example.yaml config.yaml
```

### One-Shot Installer (Recommended)

The repo ships an `install.sh` that installs the CLI **and** the Obsidian plugin in a
single command. Pass it the path to your Obsidian vault:

```bash
./install.sh /path/to/your/obsidian/vault
```

The script runs `uv tool install -e .` to put `zsum` on your PATH, builds the plugin
(`npm ci` when possible, otherwise `npm install`, then `npm run build` inside `plugin_dev/`), and copies `main.js`,
`manifest.json`, and `styles.css` into `<vault>/.obsidian/plugins/obsidian-zsum/`. See
`./install.sh --help` for flags (`--cli-only`, `--plugin-only`, `--skip-build`).

### Manual: CLI Only

If you prefer to install just the CLI:

```bash
uv tool install -e .
```

This adds `zsum` to your PATH (via `~/.local/bin/`). The `-e` (editable) flag means source changes take effect immediately without reinstalling. After this, you can use `zsum` directly instead of `uv run zsum`.

Edit `config.yaml` with your paths:

```yaml
# Required: path to your BBT JSON export
bbt_json: ~/Zotero/zot.json

# Required: path to Zotero's SQLite database
zotero_sqlite: ~/Zotero/zotero.sqlite

# Required for LLM commands: set your provider and model
llm:
  provider: anthropic
  anthropic:
    model: claude-sonnet-4-5-20250514
```

The `anthropic` provider shells out to the Claude Code CLI (`claude -p`), so no
API key is required — install Claude Code and authenticate once:

```bash
claude auth
```

The `binary:` field under `llm.anthropic` lets you point at a non-default `claude`
executable; `model:` accepts any alias the CLI accepts (e.g. `sonnet`, `opus`, or
a full version string).

For a zero-hassle local LLM setup, install and start Ollama first, then run
`zsum setup-model` — it checks Ollama, pulls a model, and writes the config for you. If
Ollama is missing or not running, it prints the next step and exits without changing your
config:

```bash
zsum setup-model               # pulls a medium-size model (qwen2.5:7b)
zsum setup-model --size large  # for machines with 16GB+ RAM
zsum setup-model --list        # show available tiers
zsum setup-model --model llama3.2  # use any Ollama model
```

Alternatively, set `provider: openai_compat` and configure the `openai_compat` section manually.

For Ollama, the manual config is:

```yaml
llm:
  routing:
    cards: openai_compat
    digests: openai_compat
    redigest: openai_compat
  openai_compat:
    base_url: http://localhost:11434/v1
    model: llama3.2
    api_key: ollama
    max_tokens_card: 4096
    max_tokens_digest: 8192
```

If using Codex CLI, set `provider: codex_exec` and configure the `codex_exec` section.
For digests, `zsum` uses Codex's `--output-schema` support to request structured sections and
then renders the final markdown itself.

If using Gemini CLI, set `provider: gemini_cli` and configure the `gemini_cli` section
(`model:`, `binary:`, `approval_mode:`). Gemini has no `--system-prompt` or `--json-schema`
flags, so system + user prompts are combined and structured-output schemas are inlined into
the prompt rather than enforced by the CLI.

See `config.example.yaml` for all options.

## Usage

If you installed globally (see above), use `zsum` directly. Otherwise prefix with `uv run`.

```bash
# Phase A: build vault skeleton (no LLM, no cost)
zsum skeleton

# Check your library index
zsum index

# Phase B: generate summaries
zsum cards      # per-paper structured summaries via LLM
zsum digests    # per-collection synthesis via LLM
zsum publish    # write Obsidian vault from cache

# Or run the full pipeline in one go
zsum all

# Enrichment commands
zsum reviews                         # list review/survey/meta-analysis papers
zsum citations                       # fetch citation counts (OpenAlex + S2 fallback)
zsum citations --top 10              # show top-N most-cited papers
zsum restructure                     # generate advisory report on collection hierarchy
zsum restructure --output report.md  # write report to file

# Setup
zsum setup-model       # pull an Ollama model + configure zsum

# Utilities
zsum stats             # show cache/progress counts
zsum extract           # dry-run: show PDF extraction quality + text previews
zsum clear-cache --all # clear cached cards and digests
```

## Obsidian Plugin

An Obsidian plugin (`obsidian-zsum`) provides a graphical interface for the
pipeline inside your vault — browse collections and papers, trigger stages
(including `Citations` and `Restructure`), sort by citation count, watch live
log output, and open generated notes without leaving Obsidian.

See the **[Plugin Guide](docs/plugin/index.md)** for installation and usage.

## Output

The vault is written to `vault_output` (default: `./vault`) with this structure:

```
vault/
├── Library Index.md          # Map of contents with stats
├── Collections/
│   ├── Phase Field.md        # Collection note with digest + paper links
│   └── Subcollection A.md
└── Papers/
    ├── smith2017.md           # Paper note with structured summary
    └── zhao2020.md
```

Notes use Obsidian wikilinks (`[[...]]`) for cross-referencing.

## Caching

Cards and digests are cached in `cache_dir`. On subsequent runs:

- **Cards**: only new/uncached papers are processed
- **Digests**: regenerated when collection membership or card content changes
- **Citations**: refetched only when older than `citations.max_age_days` (default 30)
- **Restructure**: runs on demand; last advisory is kept at `cache/restructure_report.md`
- **Prompt version**: bump `prompt_version` in config to force card regeneration
- Use `--force` flag on `cards`/`digests` commands, or `--refresh` on `citations`, to bypass cache
- **Extraction settings**: cards record an extraction signature (PDF backend, mode, page/section limits); changing any of these regenerates affected cards automatically

## PDF backends & licensing

zotero-summarizer is MIT-licensed, and the default installation stays MIT-clean:
PDFs are read with [pdfminer.six](https://github.com/pdfminer/pdfminer.six) (MIT)
and [pypdf](https://github.com/py-pdf/pypdf) (BSD-3). No copyleft dependencies
are installed or imported by default.

An optional [PyMuPDF](https://pymupdf.readthedocs.io/) backend is available for
users who prefer its extraction quality. PyMuPDF is licensed under the
**AGPL-3.0** (or a commercial license from Artifex) — installing the extra means
your combined installation is subject to those terms:

```bash
uv tool install --reinstall "zotero-summarizer[pymupdf]"
```

Select the backend in `config.yaml`:

```yaml
extraction:
  backend: pdfminer   # default, permissive; or "pymupdf" (requires the extra)
```

or per-invocation with `zsum --pdf-backend pymupdf ...`. Switching backends
automatically invalidates cached paper cards (extraction output differs between
engines).

## Documentation

- **[Installation Guide](docs/getting-started/installation.md)** — Detailed setup from scratch (Zotero, BBT, LLM providers, troubleshooting)
- **[User Guide](docs/guide/commands.md)** — CLI commands, workflows, caching, prompt customization
- **[Plugin Guide](docs/plugin/index.md)** — Obsidian plugin installation, settings, and UI walkthrough
- **[Architecture & Reference](docs/reference/architecture.md)** — Internal architecture, data models, config reference
- **[Developer Guide](docs/development/developer-guide.md)** — Caveats, invariants, and notes for contributors

Build and serve the full docs locally with `uv run mkdocs serve`.
