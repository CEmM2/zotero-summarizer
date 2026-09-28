# Workflows

Common usage patterns for `zsum`.

## First Run

```bash
zsum setup-model   # pull and configure a local Ollama model (optional)
zsum skeleton      # verify setup, check extraction quality (free)
zsum stats         # see how many papers will be processed
zsum all           # generate everything
```

## After Adding Papers to Zotero

1. Re-export your library from Zotero (or let "Keep updated" handle it)
2. Run `zsum all` — only new papers will be processed

The incremental cache means existing cards and digests are preserved. Only new papers get LLM calls, and digests regenerate only for collections with membership changes.

## After Changing Prompts

1. Edit the prompt template in `./prompts/`
2. Bump `prompt_version` in `config.yaml`
3. Run each stage:

```bash
zsum cards          # regenerate paper cards
zsum digests        # regenerate collection digests
zsum redigest       # regenerate final digests
zsum publish        # update the vault
```

## Switching LLM Providers

Change `llm.routing` in `config.yaml` and update the provider-specific sections.

- **Quick switch to Ollama**: run `zsum setup-model --size <tier>` to pull a model and update config
- **Moving only the refinement step**: update `llm.routing.redigest` and run `zsum redigest`
- **Changing cards or digests**: consider bumping `prompt_version` or running with `--force`

## Full Pipeline with Enrichment

The `all` command runs the core 6-stage pipeline but does **not** include `citations` or `restructure`. For a full enriched run:

```bash
zsum all                                 # core pipeline
zsum citations                           # fetch citation counts
zsum publish                             # re-publish with citation data
zsum restructure --output advisory.md    # optional structural review
```

!!! note
    Running `zsum publish` after `citations` is necessary because the publisher reads `cache/citations.json` at publish time.

## Selective Regeneration

When you only need to refresh specific collections:

```bash
# Regenerate digests for a single collection
zsum digests --force
zsum redigest --collection "Phase Field"
zsum publish
```

## Cost-Conscious Workflow

Minimize LLM spend by checking stats first:

```bash
zsum stats                  # check how many are pending
zsum extract                # preview extraction quality
zsum cards                  # incremental — only pending papers
zsum digests                # only stale/new digests
zsum redigest               # only stale/new redigests
zsum publish
```

## Mixed-Provider Workflow

Use a local model for bulk work and a cloud model for refinement:

```yaml
llm:
  routing:
    cards: openai_compat       # fast local model
    digests: openai_compat     # same local model
    redigest: anthropic        # stronger cloud model for final polish
```

```bash
# Start local LLM server first
zsum cards                     # uses local model
zsum digests                   # uses local model
zsum redigest                  # uses Claude for final refinement
zsum publish
```
