# Configuration

`zsum` is configured via a YAML file (default: `config.yaml` in the current directory). This page documents every configuration option.

Use `--config <path>` on any command to specify an alternate config file location.

## Paths

```yaml
# Better BibTeX auto-updating JSON export (required)
bbt_json: ~/Zotero/zot.json

# Zotero SQLite database — read-only, for collection structure (required)
zotero_sqlite: ~/Zotero/zotero.sqlite

# Base path for linked PDFs (only if BBT JSON contains relative paths)
zotero_pdf_base: ""

# Output Obsidian vault directory
vault_output: ~/ObsidianVault/ZoteroSummaries

# Cache directory for paper cards, digests, and membership snapshots
cache_dir: ~/ObsidianVault/ZoteroSummaries/cache
```

All paths support `~` expansion. Relative paths are resolved relative to the config file's directory.

## Scope

```yaml
# Collections to process (by name as shown in Zotero)
# Empty list = process all collections
collections:
  - "Phase Field"
  - "Cohesive Zone"
```

Only listed collections and their subcollections will be processed. Leave empty or omit entirely to process your full library.

## Extraction

These settings control how much PDF text is sent to the LLM per paper:

```yaml
# Pages from the beginning (abstract, intro, methods)
max_first_pages: 3

# Pages from the end (conclusions, references)
max_last_pages: 3

# Cap on total characters sent to LLM (~4 chars = 1 token)
max_text_chars: 24000

# Below this = "degraded" quality flag
min_text_chars: 500

# Skip PDFs with more than this many pages (avoids books/proceedings)
max_pdf_pages: 130
```

Tuning tips:

- Increase `max_first_pages` / `max_last_pages` for longer papers or when summaries miss detail.
- Decrease `max_text_chars` to reduce token usage (and cost) per paper.

!!! tip
    Run `zsum extract` to preview extraction quality before spending on LLM calls.

## LLM

### Provider Selection

```yaml
llm:
  # Legacy fallback provider (used if routing is absent)
  provider: anthropic

  # Stage-specific routing (preferred)
  routing:
    cards: openai_compat     # per-paper summaries
    digests: openai_compat   # first-pass collection digests
    redigest: anthropic      # final digest refinement
```

If `llm.routing` is absent, the `llm.provider` value is used for all stages. See [LLM Providers & Routing](../guide/providers.md) for details.

### Anthropic (Claude Code CLI)

```yaml
llm:
  anthropic:
    model: claude-sonnet-4-6       # model name/alias
    binary: claude                  # path to claude CLI binary
    api_key_env: ANTHROPIC_API_KEY  # unused (retained for legacy compat)
    max_tokens_card: 4096           # max output tokens per card
    max_tokens_digest: 8192         # max output tokens per digest
```

### OpenAI-Compatible (Local LLMs)

```yaml
llm:
  openai_compat:
    base_url: http://localhost:1234/v1
    model: qwen/qwen3.6-35b-a3b
    api_key: lm-studio              # most local servers ignore this
    max_tokens_card: 4096
    max_tokens_digest: 8192
    enable_thinking: true           # for Qwen3/DeepSeek-R1 models
    structured_output: false        # JSON Schema via response_format API
    temperature: 0.25               # null = server default
    top_p: 0.95
    top_k: 0.6
    seed: 8
```

### Codex CLI

```yaml
llm:
  codex_exec:
    model: gpt-5.4         # optional; omit for CLI default
    binary: codex           # path to codex binary
    sandbox: read-only      # passed to codex exec
    max_tokens_card: 4096
    max_tokens_digest: 8192
```

### Gemini CLI

```yaml
llm:
  gemini_cli:
    model: ""               # optional; auto-selects when empty
    binary: gemini           # path to gemini binary
    approval_mode: yolo      # auto-approves (safe: no tools used)
    max_tokens_card: 4096
    max_tokens_digest: 8192
```

## Output

```yaml
# Generate individual paper notes in vault/Papers/
generate_paper_notes: true
```

Set to `false` to skip individual paper notes and only generate collection-level summaries.

## Versioning

```yaml
# Bump to invalidate all cached paper cards and force regeneration
prompt_version: 1
```

Changing this value forces all cards to regenerate on the next run, even if they are cached. Downstream digests will also regenerate because the card content hashes change.

## Citations

```yaml
citations:
  enabled: true                  # false to skip all network calls
  provider: openalex             # primary lookup provider
  fallback: semantic_scholar     # fallback if primary misses
  email: you@example.com         # for OpenAlex polite pool (recommended)
  api_key: ""                    # Semantic Scholar API key (optional)
  rate_limit_delay: 0.1          # seconds between HTTP requests
  max_age_days: 30               # refetch cached records older than this
  top_n: 10                      # default N for --top and Most Cited sections
  timeout_seconds: 10.0          # HTTP timeout per request
```

See [Citation Counts](../guide/citations.md) for usage details.

## Restructure

```yaml
restructure:
  max_digest_chars: 2048   # max chars of each digest included in advisor prompt
```

See [Structure Advisory](../guide/restructure.md) for usage details.

## Full Example

See [`config.example.yaml`](https://github.com/CEmM2/zotero-summarizer/blob/master/config.example.yaml) in the repository for a complete annotated config file.
