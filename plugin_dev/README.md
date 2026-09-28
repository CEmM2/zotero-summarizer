# obsidian-zsum

An Obsidian plugin that provides a graphical interface for the
[zotero-summarizer](../zotero-summarizer) CLI pipeline.

## What it does

`zotero-summarizer` (`zsum`) is a command-line tool that reads your Zotero
library, extracts text from linked PDFs, and uses an LLM to generate structured
paper summaries and collection digests, writing everything to an Obsidian vault.

This plugin surfaces the pipeline state **inside** that vault: you can see which
collections and papers have been processed, trigger pipeline stages, watch live
log output, and open paper notes — all without leaving Obsidian or touching a
terminal.

## What it does NOT do

- Re-implement any pipeline logic. All indexing, PDF extraction, LLM calls, and
  file writing remain in the Python CLI.
- Replace the CLI. Power users can still run `uv run zsum <stage>` directly; the
  plugin is an interface on top, not a replacement.
- Require an internet connection beyond what the pipeline itself needs.

## Requirements

| Dependency | Version | Notes |
|---|---|---|
| Obsidian | ≥ 1.4.0 | Uses `openPopoutLeaf` API |
| Node / Electron | bundled with Obsidian | No separate install |
| Python + uv | any recent | Must be in PATH or configured |
| zotero-summarizer | v1.x | Installed and configured separately |

## Installation

1. Install `zotero-summarizer` and verify `zsum stats` or `uv run zsum stats` works in a terminal.
2. Build the plugin and copy `main.js`, `manifest.json`, and `styles.css` to `<vault>/.obsidian/plugins/obsidian-zsum/`.
3. Enable the plugin in Obsidian → Settings → Community plugins.
4. Open plugin settings and set the config path to your `config.yaml` or `zsum.config.yaml`.
5. If you installed the CLI globally, set the Python command to `zsum`; otherwise keep `uv run zsum` and set the project root to this repo.
6. Open the Zotero Summarizer view via the ribbon icon or command palette.

## Repository layout

```
plugin_dev/
├── README.md                  ← this file
├── docs/
│   ├── REQUIREMENTS.md        ← what the plugin must do (user-facing)
│   └── TECHNICAL_SPEC.md      ← how it is built (developer-facing)
├── src/
│   ├── main.ts
│   ├── view.ts
│   ├── index-reader.ts
│   ├── config.ts
│   ├── runner.ts
│   ├── cost.ts
│   └── settings.ts
├── styles.css
├── manifest.json
└── package.json
```

## Development

```bash
cd plugin_dev
npm ci --no-audit --no-fund  # or: npm install --no-audit --no-fund
npm run dev          # watch mode, outputs plugin_dev/main.js
npm run build        # production build
```

Copy `main.js`, `manifest.json`, and `styles.css` to your plugin folder, then
reload Obsidian.

## Versioning

Follows the `zotero-summarizer` major version. Plugin v1.x targets CLI v1.x.
Breaking CLI changes (new cache format, new config keys) will bump the plugin
major version.
