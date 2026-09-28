# Installation

This guide walks you through setting up `zsum` from scratch.

## System Requirements

| Requirement | Details |
|---|---|
| **Python** | 3.11 or later |
| **uv** | Fast Python package manager ([install guide](https://docs.astral.sh/uv/getting-started/installation/)) |
| **Zotero** | Version 6 or 7 with [Better BibTeX](https://retorque.re/zotero-better-bibtex/) |
| **LLM Provider** | At least one — see [LLM Providers](../guide/providers.md) |
| **Network** | Optional — only needed for `zsum citations` |

## 1. Clone and Install

```bash
git clone https://github.com/CEmM2/zotero-summarizer.git
cd zotero-summarizer
uv sync
```

This installs all runtime and dev dependencies into an isolated virtual environment managed by `uv`. Runtime dependencies include `pymupdf`, `openai`, `pyyaml`, `click`, `pydantic`, and `httpx`.

### One-Shot Installer

If you want both the CLI and the Obsidian plugin installed in one command:

```bash
./install.sh /path/to/your/obsidian/vault
```

The script performs the global CLI install, builds the plugin, and copies the release files into your vault's plugin folder.

??? info "Installer flags"

    | Flag | Description |
    |---|---|
    | `--cli-only` | Skip the plugin step (no vault path required) |
    | `--plugin-only` | Skip the CLI step; still requires `--vault` |
    | `--skip-deps` | Skip `npm ci`/`npm install` before building |
    | `--skip-build` | Don't run `npm run build`; copy the committed `main.js` as-is |
    | `-h`, `--help` | Show help and exit |

### Global Install (Recommended)

Install `zsum` as a global command available from any directory:

```bash
uv tool install -e .
```

This adds `zsum` to `~/.local/bin/` (which `uv` adds to your PATH automatically). The `-e` (editable) flag means source code changes take effect immediately without reinstalling.

After global install, use `zsum` directly instead of `uv run zsum` throughout this guide.

### Verify

```bash
zsum --help
```

You should see a list of available commands.

## 2. Set Up Better BibTeX

Better BibTeX (BBT) provides the JSON export that `zsum` reads as its primary data source.

1. Install the [Better BibTeX plugin](https://retorque.re/zotero-better-bibtex/installation/) in Zotero
2. In Zotero: **File > Export Library**
3. Set format to **"Better BibTeX JSON"**
4. Check **"Keep updated"** so the export auto-syncs when your library changes
5. Save the `.json` file somewhere accessible — you'll point `bbt_json` at this path

!!! tip "Auto-sync"
    The "Keep updated" option means your BBT JSON file updates automatically whenever you modify your Zotero library. `zsum` reads this file at the start of every run, so new papers appear without any manual re-export.

## 3. Create Your Config File

```bash
cp config.example.yaml config.yaml
```

Set these three required paths:

```yaml
# Path to your BBT JSON export (from step 2)
bbt_json: ~/Zotero/zot.json

# Path to Zotero's SQLite database (used for collection hierarchy)
zotero_sqlite: ~/Zotero/zotero.sqlite

# Where to write the Obsidian vault
vault_output: ~/ObsidianVault/ZoteroSummaries
```

### Finding Your Zotero Paths

| OS | Typical Zotero data directory |
|---|---|
| macOS | `~/Zotero/` |
| Linux | `~/Zotero/` |
| Windows | `C:\Users\<you>\Zotero\` |

The SQLite database is always `zotero.sqlite` inside this directory.

### PDF Path Resolution

`zsum` reads PDF file paths from the BBT JSON export. Two modes:

- **Absolute paths** (default): works out of the box. Leave `zotero_pdf_base` empty.
- **Relative paths** (if you use ZotMoov or a shared PDF directory): set `zotero_pdf_base` to the directory containing your PDFs.

```yaml
# Only needed if BBT JSON contains relative PDF paths
zotero_pdf_base: /Volumes/Papers/Zotero
```

## 4. Configure Your LLM Provider

You need at least one LLM provider configured. See the full [LLM Providers & Routing](../guide/providers.md) page for all options.

=== "Local LLM (Quick Start)"

    The fastest way to get started — install and start [Ollama](https://ollama.com), then let `zsum` pull and configure a local model:

    ```bash
    zsum setup-model               # pulls qwen2.5:7b (~5GB RAM)
    zsum setup-model --size large  # for 16GB+ RAM machines
    zsum setup-model --list        # show all tiers
    ```

    This checks Ollama is installed and running, pulls the model, writes `config.yaml` with the correct settings, and verifies the model responds. If the existing config file is malformed or unreadable, the command reports the YAML/read error and leaves the file unchanged. See [CLI Commands](../guide/commands.md#zsum-setup-model) for all options.

    !!! note "Ollama required"
        If Ollama is not installed or the daemon is not running, `setup-model` prints the next step and exits without changing your config. Get Ollama from [ollama.com/download](https://ollama.com/download), then start it with `ollama serve` or the desktop app.

=== "Local LLM (Manual)"

    Start your local server (LM Studio, Ollama, vLLM, etc.), then configure:

    ```yaml
    llm:
      provider: openai_compat
      openai_compat:
        base_url: http://localhost:1234/v1
        model: your-model-name
        api_key: lm-studio
    ```

=== "Claude (Anthropic)"

    The `anthropic` provider shells out to the Claude Code CLI — no API key needed:

    ```bash
    claude auth  # authenticate once
    ```

    ```yaml
    llm:
      provider: anthropic
      anthropic:
        model: claude-sonnet-4-6
    ```

=== "Codex CLI"

    ```bash
    codex login  # authenticate once
    ```

    ```yaml
    llm:
      provider: codex_exec
      codex_exec:
        model: gpt-5.4
        binary: codex
        sandbox: read-only
    ```

=== "Gemini CLI"

    ```bash
    gemini auth  # authenticate once
    ```

    ```yaml
    llm:
      provider: gemini_cli
      gemini_cli:
        model: ""  # auto-selects
        binary: gemini
        approval_mode: yolo
    ```

## 5. Verify Your Setup

Run the skeleton command — it builds the vault structure without calling any LLM (no cost):

```bash
zsum skeleton
```

This will:

- Parse your BBT JSON and Zotero SQLite
- Report PDF extraction quality for each paper
- Write a metadata-only vault to `vault_output`

If it succeeds, your setup is complete.

## 6. Optional: Enable Citation Counts

```yaml
citations:
  enabled: true
  provider: openalex
  email: you@example.com  # recommended for OpenAlex polite pool
  max_age_days: 30
```

See [Citation Counts](../guide/citations.md) for full details.

## Troubleshooting

??? failure "Config not found: config.yaml"
    `zsum` looks for `config.yaml` in the current working directory. Either run from the project root, or specify the path:
    ```bash
    zsum --config /path/to/config.yaml skeleton
    ```

??? failure "Config error: bbt_json does not exist"
    Double-check the path in `config.yaml`. Use `~` for home directory — `zsum` expands it automatically.

??? failure "Config error: LLM model not set"
    The `cards`, `digests`, `redigest`, and `all` commands require an LLM model for most routed providers. Make sure the provider's `model` field is set. `codex_exec` and `gemini_cli` may leave `model` empty to use the CLI default.

??? failure "PyMuPDF installation issues"
    ```bash
    uv pip install pymupdf --force-reinstall
    ```
    On some platforms you may need system-level dependencies. See the [PyMuPDF docs](https://pymupdf.readthedocs.io/en/latest/installation.html).

??? failure "Local LLM connection refused"
    Ensure your LLM server is running and the `base_url` matches:
    ```bash
    curl http://localhost:1234/v1/models
    ```
