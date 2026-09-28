# LLM Providers & Routing

`zsum` supports four LLM providers and lets you route different pipeline stages to different providers.

## Supported Providers

| Provider | Config key | Auth | Notes |
|---|---|---|---|
| **Claude** (Anthropic) | `anthropic` | Claude Code CLI (`claude auth`) | Shells out to `claude -p` |
| **Local LLM** | `openai_compat` | Varies | LM Studio, Ollama, mlx-lm, vLLM |
| **Codex CLI** | `codex_exec` | Codex CLI (`codex login`) | Uses `codex exec` subprocess |
| **Gemini CLI** | `gemini_cli` | Gemini CLI (`gemini auth`) | Uses `gemini -p` subprocess |

## Stage Routing

`llm.routing` lets you choose a separate provider for each pipeline stage:

```yaml
llm:
  routing:
    cards: openai_compat     # per-paper summaries
    digests: openai_compat   # first-pass collection digests
    redigest: anthropic      # final digest refinement
```

This is the primary configuration surface. The legacy `llm.provider` field is only used when `llm.routing` is absent.

### Why Route Stages Separately?

A common pattern is to use a fast local model for bulk card and digest generation, then route the final `redigest` stage to a stronger cloud model:

```yaml
llm:
  routing:
    cards: openai_compat       # fast local model for bulk work
    digests: openai_compat     # same local model
    redigest: codex_exec       # stronger model for final polish
  openai_compat:
    base_url: http://localhost:1234/v1
    model: Qwen2.5-32B-Instruct
    api_key: lm-studio
  codex_exec:
    model: gpt-5.4
    binary: codex
    sandbox: read-only
```

This minimizes cloud API costs while ensuring high-quality final output.

## Provider Configuration

### Anthropic (Claude Code CLI)

The `anthropic` provider shells out to the Claude Code CLI (`claude -p`). No API key is needed — authenticate once with `claude auth`.

```yaml
llm:
  anthropic:
    model: claude-sonnet-4-6       # model name or alias
    binary: claude                  # path to claude binary
    max_tokens_card: 4096
    max_tokens_digest: 8192
```

The `binary` field lets you point at a non-default `claude` executable. The `model` field accepts any alias the CLI accepts (e.g., `sonnet`, `opus`, or a full version string).

### OpenAI-Compatible (Local LLMs)

Works with any server that exposes the OpenAI chat completions API.

!!! tip "Quick start with Ollama"
    Install and start Ollama, then run `zsum setup-model` to pull a model and configure everything. See [setup-model](commands.md#zsum-setup-model) for details.

Manual Ollama configuration uses the same `openai_compat` provider as other local OpenAI-compatible servers:

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

```yaml
llm:
  openai_compat:
    base_url: http://localhost:1234/v1
    model: your-model-name
    api_key: lm-studio
    max_tokens_card: 4096
    max_tokens_digest: 8192
    enable_thinking: true       # for Qwen3/DeepSeek-R1 models
    structured_output: false    # JSON Schema via response_format
    temperature: 0.25
    top_p: 0.95
    top_k: 0.6
    seed: 8
```

Common server URLs:

| Server | Default URL |
|---|---|
| LM Studio | `http://localhost:1234/v1` |
| Ollama | `http://localhost:11434/v1` |
| mlx-lm | `http://localhost:8080/v1` |
| vLLM | `http://localhost:8000/v1` |

#### Extended Thinking

Set `enable_thinking: true` for models that support extended thinking (Qwen3, DeepSeek-R1). When `false`, thinking is explicitly disabled via `extra_body`. Leave as `null` (or omit) to let the server decide.

#### Structured Output

Set `structured_output: true` to use JSON Schema validation via the OpenAI `response_format` API. Requires a compatible server (LM Studio, vLLM). When enabled, cards and digests get schema-validated JSON instead of prompt-engineered freeform output.

### Codex CLI

Uses the Codex CLI as a subprocess.

```yaml
llm:
  codex_exec:
    model: gpt-5.4
    binary: codex
    sandbox: read-only
    max_tokens_card: 4096
    max_tokens_digest: 8192
```

For collection digests, `zsum` uses Codex's `--output-schema` support and renders the final markdown itself, keeping digest layout stable.

### Gemini CLI

Uses the Gemini CLI (`gemini -p`) as a subprocess.

```yaml
llm:
  gemini_cli:
    model: ""                # optional; auto-selects when empty
    binary: gemini
    approval_mode: yolo      # auto-approves (safe: no tools used)
    max_tokens_card: 4096
    max_tokens_digest: 8192
```

Gemini CLI has no `--system-prompt` or `--json-schema` flags, so system and user prompts are combined and structured-output schemas are inlined into the prompt.

## Legacy Configuration

Older configs that define only `llm.provider` without `llm.routing` still work. The single provider is used for all three stages:

```yaml
llm:
  provider: anthropic  # used for cards, digests, and redigest
  anthropic:
    model: claude-sonnet-4-6
```

## Token Limits

Each provider config includes two token limit fields:

| Field | Default | Description |
|---|---|---|
| `max_tokens_card` | 1024 | Max output tokens for each paper card |
| `max_tokens_digest` | 2048 | Max output tokens for each collection digest |

Increase for more detailed output; decrease to save cost.
