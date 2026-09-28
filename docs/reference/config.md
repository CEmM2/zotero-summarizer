# Configuration Reference

All configuration dataclasses are defined in `src/zsum/config.py`.

## Config

Top-level application configuration.

| Field | Type | Default | Description |
|---|---|---|---|
| `bbt_json` | `Path` | `~/Zotero/zot.json` | Path to BBT JSON export |
| `zotero_sqlite` | `Path` | `~/Zotero/zotero.sqlite` | Path to Zotero SQLite database |
| `zotero_pdf_base` | `str` | `""` | Base path for resolving relative PDF paths |
| `vault_output` | `Path` | `./vault` | Output Obsidian vault directory |
| `cache_dir` | `Path` | `./cache` | Cache directory for cards, digests, membership |
| `collections` | `list[str]` | `[]` | Collection names to process (empty = all) |
| `max_first_pages` | `int` | `3` | Pages to extract from PDF start |
| `max_last_pages` | `int` | `2` | Pages to extract from PDF end |
| `max_text_chars` | `int` | `24000` | Max characters sent to LLM per paper |
| `min_text_chars` | `int` | `500` | Below this = "degraded" quality flag |
| `max_pdf_pages` | `int \| None` | `None` | Skip PDFs with more pages than this |
| `llm` | `LLMConfig` | — | LLM configuration (see below) |
| `generate_paper_notes` | `bool` | `True` | Write individual paper notes |
| `prompt_version` | `int` | `1` | Bump to invalidate all cached cards |
| `citations` | `CitationsConfig` | — | Citation fetcher settings |
| `restructure` | `RestructureConfig` | — | Structure advisor settings |

Path fields support `~` expansion. Relative paths are resolved relative to the config file's directory.

## LLMConfig

LLM configuration with provider selection and routing.

| Field | Type | Default | Description |
|---|---|---|---|
| `provider` | `str` | `"anthropic"` | Legacy fallback provider |
| `routing` | `LLMRoutingConfig` | — | Stage-specific routing |
| `anthropic` | `LLMProviderConfig` | — | Anthropic provider settings |
| `openai_compat` | `LLMProviderConfig` | — | OpenAI-compatible provider settings |
| `codex_exec` | `CodexExecConfig` | — | Codex CLI settings |
| `gemini_cli` | `GeminiCliConfig` | — | Gemini CLI settings |

**Methods:**

| Method | Description |
|---|---|
| `provider_for_stage(stage)` | Return the routed provider name for a stage |
| `config_for_stage(stage)` | Return the provider config object for a stage |
| `config_for_provider(provider)` | Return the config object for a provider name |

## LLMRoutingConfig

Stage-specific provider routing.

| Field | Type | Default | Description |
|---|---|---|---|
| `cards` | `str` | `"anthropic"` | Provider for paper card generation |
| `digests` | `str` | `"anthropic"` | Provider for first-pass digests |
| `redigest` | `str` | `"anthropic"` | Provider for digest refinement |

## LLMProviderConfig

Settings for the `anthropic` and `openai_compat` providers.

| Field | Type | Default | Description |
|---|---|---|---|
| `model` | `str` | `""` | Model name or alias |
| `max_tokens_card` | `int` | `1024` | Max output tokens per card |
| `max_tokens_digest` | `int` | `2048` | Max output tokens per digest |
| `api_key_env` | `str` | `"ANTHROPIC_API_KEY"` | Env var for API key (unused for CLI mode) |
| `binary` | `str` | `"claude"` | Path to the claude CLI binary |
| `base_url` | `str` | `http://localhost:1234/v1` | OpenAI-compatible server URL |
| `api_key` | `str` | `"lm-studio"` | API key for OpenAI-compatible server |
| `enable_thinking` | `bool \| None` | `None` | Extended thinking for Qwen3/DeepSeek-R1 |
| `structured_output` | `bool` | `False` | JSON Schema via response_format API |
| `temperature` | `float \| None` | `None` | Sampling temperature |
| `top_p` | `float \| None` | `None` | Top-p sampling |
| `top_k` | `float \| None` | `None` | Top-k sampling |
| `seed` | `int \| None` | `None` | Random seed for reproducibility |

## CodexExecConfig

Settings for the Codex CLI provider.

| Field | Type | Default | Description |
|---|---|---|---|
| `model` | `str` | `""` | Model name (empty = CLI default) |
| `max_tokens_card` | `int` | `1024` | Max output tokens per card |
| `max_tokens_digest` | `int` | `2048` | Max output tokens per digest |
| `binary` | `str` | `"codex"` | Path to codex binary |
| `sandbox` | `str` | `"read-only"` | Sandbox mode passed to `codex exec` |

## GeminiCliConfig

Settings for the Gemini CLI provider.

| Field | Type | Default | Description |
|---|---|---|---|
| `model` | `str` | `""` | Model name (empty = auto-select) |
| `max_tokens_card` | `int` | `1024` | Max output tokens per card |
| `max_tokens_digest` | `int` | `2048` | Max output tokens per digest |
| `binary` | `str` | `"gemini"` | Path to gemini binary |
| `approval_mode` | `str` | `"yolo"` | Approval mode for gemini CLI |

## CitationsConfig

Citation fetcher settings.

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | `bool` | `True` | Enable/disable citation lookups |
| `provider` | `str` | `"openalex"` | Primary citation provider |
| `fallback` | `str` | `"semantic_scholar"` | Fallback provider ("" to disable) |
| `email` | `str` | `""` | Email for OpenAlex polite pool |
| `api_key` | `str` | `""` | Semantic Scholar API key |
| `rate_limit_delay` | `float` | `0.1` | Seconds between HTTP requests |
| `max_age_days` | `int` | `30` | Refetch cache entries older than this |
| `top_n` | `int` | `10` | Default N for `--top` and Most Cited sections |
| `timeout_seconds` | `float` | `10.0` | HTTP timeout per request |

## RestructureConfig

Structure advisor settings.

| Field | Type | Default | Description |
|---|---|---|---|
| `max_digest_chars` | `int` | `800` | Max chars of each digest in advisor prompt |

## Validation

`validate_config()` checks for common problems:

- BBT JSON file must exist
- Zotero SQLite file must exist
- For LLM stages: the routed provider's model must be set (except for `codex_exec` and `gemini_cli` with empty model)

Returns a list of error messages (empty = valid).

## Loading

`load_config(path)` loads a YAML file and returns a `Config` object:

- Expands `~` in path fields
- Resolves relative paths against the config file's directory
- Warns about unknown config keys (does not error)
- Hydrates `LLMRoutingConfig` defaults from the legacy `provider` field
