# Prompt Customization

`zsum` uses prompt templates to instruct the LLM. You can customize these templates to change the style, format, or content of generated summaries.

## Template Files

| Template | Used by | Purpose |
|---|---|---|
| `paper_card.txt` | `zsum cards` | Defines the JSON schema and instructions for per-paper summaries |
| `collection_digest.txt` | `zsum digests` | First-pass format for collection-level synthesis |
| `collection_digest_structured.txt` | `zsum digests` (codex_exec) | Structured digest schema for Codex CLI |
| `collection_redigest.txt` | `zsum redigest` | Refinement prompt for turning first-pass digests into final form |
| `restructure.txt` | `zsum restructure` | Advisory report on collection hierarchy |

## Resolution Order

Templates are resolved through a 3-tier lookup:

1. **Package data** — the `.txt` files shipped with the package (via `importlib.resources`). This is the default.
2. **CWD `prompts/` directory** — if you place a template in `./prompts/`, it overrides the package default for that template only.
3. **Hardcoded fallback** — a minimal built-in default compiled into the source code, used only if the package data is somehow unavailable.

## Customizing Templates

Copy the package templates into a local `prompts/` directory and edit:

```bash
mkdir -p prompts
cp src/zsum/prompts/paper_card.txt prompts/
cp src/zsum/prompts/collection_digest.txt prompts/
cp src/zsum/prompts/collection_redigest.txt prompts/
```

Edit the copies in `./prompts/`. `zsum` will automatically pick up the local versions.

!!! important "Bump prompt_version after changes"
    After modifying templates, bump `prompt_version` in `config.yaml` so cached cards regenerate with the new prompt:
    ```yaml
    prompt_version: 2  # was 1
    ```

## Paper Card Schema

The `paper_card.txt` template instructs the LLM to return JSON matching this schema:

```json
{
  "problem": "1-3 sentences describing the research question or gap",
  "methods": ["concise bullet point", "..."],
  "key_findings": ["concise bullet point", "..."],
  "limitations": ["concise bullet point", "..."],
  "keywords": ["keyword", "..."]
}
```

The `paper_type` field is handled separately by the classifier and normalization pipeline — it does not appear in the prompt schema.

## Digest Format

The `collection_digest.txt` template instructs the LLM to produce markdown with these sections:

- **Summary** — 1-3 paragraphs synthesizing the collection, citing papers by citekey
- **Key Themes** — bullet points identifying major research themes
- **Common Methods** — shared methodologies across papers
- **Gaps and Limitations** — what is missing or limited

## Template Variables

Template variables are injected at runtime by the builder functions in `cards.py` and `digests.py`. The available variables depend on the template:

- **Paper card**: paper metadata (title, authors, year, venue, DOI, abstract) and extracted PDF text
- **Collection digest**: collection name, path, paper cards for all member papers
- **Redigest**: collection metadata, the first-pass digest markdown, and an optional compact grounding list

!!! warning "No compile-time validation"
    Template placeholders are not validated at build time. If you rename or remove a variable in the prompt file, the code will silently include the literal placeholder text. Always test after making template changes.

## Tips

- Keep prompts concise — verbose instructions tend to produce worse results than clear, specific ones
- Use `zsum cards --force` to test card prompt changes on a few papers
- Use `zsum digests --force` to test digest prompt changes
- The `--verbose` flag shows the full LLM request/response for debugging
- Structured output (`structured_output: true` for `openai_compat`) bypasses prompt-based JSON formatting in favor of schema-validated output
