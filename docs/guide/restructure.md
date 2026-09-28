# Structure Advisory

`zsum restructure` generates an advisory report proposing structural changes to your Zotero collection hierarchy. It analyzes your collections and suggests renames, splits, merges, and new sub-collections.

!!! info "Advisory only"
    This command **never** modifies your Zotero library, reassigns papers, or mutates the library index. The output is purely informational.

## Usage

```bash
zsum restructure                              # print report to stdout
zsum restructure --output advisory.md         # write to file
zsum restructure --collection "Methods"       # limit to a subtree
```

## How It Works

1. Builds a tree representation of your collection hierarchy
2. Includes truncated digests (up to `restructure.max_digest_chars` per collection) as context
3. Makes a single LLM call with the `restructure.txt` prompt
4. Parses the response into structured suggestions
5. Renders a markdown advisory report

The advisor works best after running `zsum digests`, since collection digests provide rich context about each collection's contents. Without digests, it falls back to paper titles and keywords (and warns you).

## Configuration

```yaml
restructure:
  max_digest_chars: 2048  # max chars of each digest in the advisor prompt
```

## Output Format

The report includes:

- **Overall Assessment** — high-level evaluation of the hierarchy
- **Suggestions** — specific proposed changes, each with:
    - Type (rename, split, merge, new sub-collection, too-broad flag)
    - Target collection(s)
    - Proposed change
    - Rationale
- **Proposed Hierarchy** — a visual tree showing the suggested structure

## Cached Output

The report is cached to two files:

- `cache/restructure_advice.json` — structured data
- `cache/restructure_report.md` — rendered markdown

These are overwritten on each run. They are not cleared by `clear-cache` — delete them manually if needed.
