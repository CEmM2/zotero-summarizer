# CLI Commands

All commands accept these global options:

| Option | Description |
|---|---|
| `--config <path>` | Path to config file (default: `config.yaml`) |
| `-v`, `--verbose` | Enable debug logging |

## Core Pipeline

### `zsum all`

Runs the full 6-stage pipeline: index, extract, cards, digests, redigest, publish.

```bash
zsum all
```

Output shows progress through each stage with timing:

```
1/6 Index...
  ✓ 127 items (98 PDF), 8 collections [0:01]
2/6 Extract...
  ✓ 85 extracted (72 good, 42 cached) [0:03]
3/6 Cards...
  ✓ 85/127 cards [1:12]
4/6 Digests...
  ✓ 8/8 digests [0:15]
5/6 Redigest...
  ✓ 8/8 redigests (5 generated, 3 cached, 0 skipped) [0:08]
6/6 Publish...
  ✓ Published to ~/vault [0:00]
Done! 85 cards, 8 digests, 8 redigests in 1:39
```

### `zsum skeleton`

Build the vault skeleton without calling any LLM. No cost.

```bash
zsum skeleton
```

Creates metadata-only notes in the vault and shows PDF extraction quality for each paper. Use this to verify your setup before spending on LLM calls.

### `zsum index`

Build the library index and print stats.

```bash
zsum index
```

```
Items: 127 (98 with PDF)
Collections: 8
  /Phase Field (23 papers)
  /Phase Field/Fracture (12 papers)
  /Cohesive Zone (18 papers)
```

### `zsum extract`

Dry-run showing PDF extraction quality and text previews.

```bash
zsum extract
```

### `zsum cards`

Generate per-paper structured summaries via LLM.

```bash
zsum cards          # incremental (skip cached)
zsum cards --force  # regenerate all cards
```

| Option | Description |
|---|---|
| `--force` | Regenerate all cards, ignoring cache |

### `zsum digests`

Generate first-pass collection digests.

```bash
zsum digests          # incremental
zsum digests --force  # clear and regenerate all
```

| Option | Description |
|---|---|
| `--force` | Delete all cached digest `.md` files and regenerate |

### `zsum redigest`

Refine first-pass digests into publish-ready digests.

```bash
zsum redigest                                # incremental
zsum redigest --collection "Phase Field"     # single collection
zsum redigest --force                        # force regeneration
```

| Option | Description |
|---|---|
| `--collection <name>` | Filter to a single collection (by name, key, or path) |
| `--force` | Regenerate even if redigest is fresh |

!!! warning
    If a collection is missing its first-pass digest, `redigest` will warn and skip it. Run `zsum digests` first.

### `zsum publish`

Write the Obsidian vault from cached data. No LLM calls.

```bash
zsum publish
```

## Enrichment

### `zsum citations`

Fetch citation counts from OpenAlex (primary) with Semantic Scholar fallback.

```bash
zsum citations                            # fetch missing/stale counts
zsum citations --refresh                  # force re-fetch everything
zsum citations --top 10                   # show top-N most-cited
zsum citations --collection "Batteries"   # restrict to one collection
```

| Option | Description |
|---|---|
| `--refresh` | Force re-fetch even if cached entries are fresh |
| `--top <N>` | Show only the top-N most-cited papers |
| `--collection <name>` | Restrict to a single collection subtree |

### `zsum reviews`

List papers classified as review, survey, or meta-analysis.

```bash
zsum reviews                              # all review papers
zsum reviews --collection "Phase Field"   # single collection
```

| Option | Description |
|---|---|
| `--collection <name>` | Filter to a single collection |

### `zsum restructure`

Generate an advisory report on collection hierarchy (never modifies your library).

```bash
zsum restructure                              # print to stdout
zsum restructure --output advisory.md         # write to file
zsum restructure --collection "Methods"       # limit to subtree
```

| Option | Description |
|---|---|
| `--output <path>` | Write the report to a file instead of stdout |
| `--collection <name>` | Restrict analysis to a collection subtree |

## Setup

### `zsum setup-model`

Check for [Ollama](https://ollama.com), pull a local model, and configure `zsum` to use it.
If Ollama is not installed, the command prints install instructions and exits without changing
your config.

```bash
zsum setup-model                   # pull medium tier (qwen2.5:7b)
zsum setup-model --size large      # for machines with 16GB+ RAM
zsum setup-model --size small      # for laptops with limited RAM
zsum setup-model --model llama3.2  # use any Ollama model name
zsum setup-model --list            # show available tiers
zsum setup-model --dry-run         # preview without changes
```

| Option | Description |
|---|---|
| `--size <tier>` | Model tier: `small`, `medium` (default), `large`, `xlarge` |
| `--model <name>` | Override with any Ollama model name |
| `--list` | Show available tiers and exit |
| `--dry-run` | Show what would happen without pulling or writing config |

Available tiers:

| Tier | Model | Params | RAM | Best for |
|---|---|---|---|---|
| `small` | `qwen2.5:1.5b` | ~1.5B | ~1GB | Laptops with limited RAM |
| `medium` | `qwen2.5:7b` | ~7B | ~5GB | Good balance for most machines |
| `large` | `qwen2.5:14b` | ~14B | ~9GB | Machines with 16GB+ RAM |
| `xlarge` | `qwen2.5:32b` | ~32B | ~20GB | Workstations with 32GB+ RAM |

!!! tip
    Tiers are defined in `src/zsum/model_tiers.yaml`. Edit that file to change models without touching code.

## Utility

### `zsum stats`

Show counts of items, collections, cached cards, and digests.

```bash
zsum stats
```

```
Items: 127 (98 PDF)
Collections: 8
Cards: 42 cached, 85 pending
Digests: 3 cached
```

### `zsum clear-cache`

Clear cached data.

```bash
zsum clear-cache --cards    # clear paper cards only
zsum clear-cache --digests  # clear digests only
zsum clear-cache --all      # clear everything
```

!!! note
    `clear-cache` does not remove `cache/redigests/`, `cache/citations.json`, or `cache/restructure_*`. Delete those manually for a complete reset.
