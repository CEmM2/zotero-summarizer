# Quick Start

Get `zsum` running in 5 minutes. This page assumes you already have Zotero with Better BibTeX set up and a BBT JSON export file.

## Install

```bash
git clone https://github.com/CEmM2/zotero-summarizer.git
cd zotero-summarizer
uv sync
uv tool install -e .  # makes `zsum` available globally
```

## Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your paths:

```yaml
bbt_json: ~/Zotero/zot.json
zotero_sqlite: ~/Zotero/zotero.sqlite
vault_output: ~/ObsidianVault/ZoteroSummaries
cache_dir: ~/ObsidianVault/ZoteroSummaries/cache
```

Then set up your LLM. The quickest path is to install and start Ollama, then let `zsum`
pull a model and write the local provider config:

```bash
zsum setup-model            # pulls a local model and writes config
```

Or configure manually for a cloud provider:

```yaml
llm:
  provider: anthropic
  anthropic:
    model: claude-sonnet-4-6
```

## Preview (Free)

Build the vault skeleton without any LLM calls:

```bash
zsum skeleton
```

This verifies your setup and shows the extraction quality for each paper.

## Check Stats

```bash
zsum stats
```

```
Items: 127 (98 PDF)
Collections: 8
Cards: 0 cached, 127 pending
Digests: 0 cached
```

## Generate Everything

```bash
zsum all
```

This runs the full 6-stage pipeline:

```
1/6 Index...
2/6 Extract...
3/6 Cards...
4/6 Digests...
5/6 Redigest...
6/6 Publish...
Done! 42 cards, 5 digests, 5 redigests in 1m23s
```

## Open in Obsidian

Open the `vault_output` directory in Obsidian. Start with `Library Index.md` to navigate your collections and papers.

## Optional: Enrichment

After the initial run, add citation counts and structural analysis:

```bash
zsum citations                          # fetch citation counts
zsum publish                            # re-publish with citation data
zsum restructure --output advisory.md   # structural review
```

## What's Next

- [Pipeline Overview](../guide/pipeline.md) — understand each stage
- [CLI Commands](../guide/commands.md) — full command reference
- [Configuration](configuration.md) — all config options
- [Obsidian Plugin](../plugin/index.md) — graphical interface
