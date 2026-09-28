# REQUIREMENTS — obsidian-zsum

**Version:** 1.1  
**Status:** Draft  
**Scope:** Current desktop plugin scope. Items marked `[v2]` are explicitly deferred.

---

## 1. Overview

The plugin is a UI shell over the `zsum` CLI. Its job is to make the pipeline
state visible and operable from within Obsidian, without duplicating any pipeline
logic.

### 1.1 Actors

- **Primary user:** Researcher with a Zotero library, running `zsum` locally.
  Comfortable with Obsidian, does not want to use a terminal for routine runs.
- **Secondary users:** Students and colleagues of the primary user, less
  technically proficient. Must be able to trigger runs and read status without
  knowing what `uv` or `sqlite3` are.

### 1.2 Non-goals

- No web/cloud execution. Everything runs locally.
- No reimplementation of indexing, extraction, or LLM calls in TypeScript.
- No support for multiple simultaneous pipelines or vaults.
- No Zotero API integration (the CLI handles all Zotero access).

---

## 2. Functional Requirements

### 2.1 Plugin Settings

**REQ-S01** — The plugin SHALL provide a settings tab in Obsidian's Settings
panel containing the following fields:

| Field | Type | Default | Description |
|---|---|---|---|
| `configPath` | string (vault-relative path) | `zsum.config.yaml` | Path to the zsum YAML config |
| `pythonCmd` | string | `uv run zsum` | Command used to invoke the pipeline |
| `costPerMTokenIn` | number | `3.00` | USD per million input tokens |
| `costPerMTokenOut` | number | `15.00` | USD per million output tokens |
| `tokensPerCardIn` | number | `4000` | Estimated input tokens per paper card |
| `tokensPerCardOut` | number | `500` | Estimated output tokens per paper card |

**REQ-S02** — All plugin-local settings SHALL be persisted via Obsidian's
`plugin.saveData()` / `plugin.loadData()` API. The external zsum YAML file SHALL
remain the source of truth for pipeline configuration and SHALL be edited from
the main view's Config tab, not duplicated into plugin settings.

**REQ-S03** — The settings tab SHALL display a "Test command" button that runs
`zsum stats` and shows the raw output in a modal. This allows the user to verify
the Python environment is reachable before attempting a full run.

**REQ-S04** — `configPath` SHALL accept both vault-relative and absolute paths.
If the file does not exist at that path, the settings tab SHALL display a warning
inline (not a modal) and the main view SHALL render an empty state prompting the
user to fix the path.

---

### 2.2 Main View

**REQ-V01** — The plugin SHALL register a dedicated `ItemView` with ID
`zsum-view`, opened as a full workspace tab (not a sidebar leaf). The view SHALL
be opened via:
- A ribbon icon (📚) on the left ribbon
- The command palette entry "Zotero Summarizer: Open view"

**REQ-V02** — The view SHALL remain open across Obsidian restarts (persisted in
workspace layout).

**REQ-V03** — The view SHALL expose two top-level tabs:

| Tab | Description |
|---|---|
| Library | Global statistics, collection tree, paper list, and pipeline controls |
| Config | External YAML editor for the file referenced by `configPath` |

Within the **Library** tab, the layout SHALL still consist of four regions:

| Region | Position | Description |
|---|---|---|
| Status Bar | top | Global library statistics |
| Collection Tree | left, scrollable | Hierarchy of all collections |
| Paper List | right, scrollable | Papers in the selected collection |
| Pipeline Controls | bottom | Stage buttons, cost estimate, log output |

**REQ-V04** — The view SHALL respect Obsidian's active theme (light/dark) by
using CSS variables from the Obsidian theme layer (`--background-primary`,
`--text-normal`, etc.) rather than hardcoded colors.

---

### 2.3 Status Bar

**REQ-SB01** — The status bar SHALL display the following counts, read from
`cache/index.json` (see REQ-D01):

- Total collections
- Total papers
- Cards: cached count, pending count, degraded count
- Digests: up-to-date count, stale count

**REQ-SB02** — Counts for cached/pending/degraded SHALL use distinct color
accents (green / muted / amber) to allow at-a-glance health assessment.

**REQ-SB03** — The status bar SHALL show a "BBT live" indicator (pulsing dot)
when the BBT JSON path from `zsum.config.yaml` is readable and its `mtime` is
within the last 60 minutes. If stale or unreadable, the dot SHALL be amber with
tooltip "BBT JSON not updated recently".

**REQ-SB04** — The status bar SHALL refresh automatically after any pipeline run
completes, and on view open.

---

### 2.4 Collection Tree

**REQ-CT01** — The tree SHALL render all collections from `cache/index.json`,
preserving the parent/child hierarchy.

**REQ-CT02** — Each tree node SHALL display:
- A colored status dot indicating digest state:
  - **Green** — digest exists and membership is unchanged
  - **Amber** — digest exists but membership has changed since last generation
  - **Grey** — no digest exists
- The collection name
- Paper count (total items in that collection, not including subcollections)

**REQ-CT03** — Nodes with children SHALL be expandable/collapsible. State SHALL
be preserved within the session (not persisted across restarts).

**REQ-CT04** — Clicking a node SHALL load that collection's papers into the Paper
List panel. The selected node SHALL be visually highlighted.

**REQ-CT05** — A special root node "All Collections" SHALL appear at the top,
aggregating stats across all collections.

**REQ-CT06** — The tree SHALL include a legend below it explaining the three dot
colors.

---

### 2.5 Paper List

**REQ-PL01** — The paper list SHALL display all papers belonging to the currently
selected collection, as a scrollable table with the following columns:

| Column | Source | Notes |
|---|---|---|
| Status icon | `cache/index.json` | ✓ cached / ○ pending / ⚠ degraded / — no pdf |
| Citekey | `cache/index.json` | Monospace font; truncated if needed |
| Year | `cache/index.json` | |
| Venue | `cache/index.json` | Truncated if needed |
| Card badge | `cache/index.json` | Text label: "cached" / "pending" / "degraded" / "no pdf" |

**REQ-PL02** — The paper list header SHALL display the collection name, paper
count, and a summary of card states (e.g. "21 cached · 2 pending").

**REQ-PL03** — The paper list header SHALL include three action buttons:
- **Open note** (↗) — opens the collection's vault note in a new tab
- **Refresh final digest** (↺) — runs the queued collection refresh flow for this
  collection only (see REQ-P04)
- **Filter** (⊟) — `[v2]`

The selected collection header SHALL also surface `redigest ok`,
`redigest stale`, or `redigest missing` from plugin index data without adding a
second status dot to the collection tree.

**REQ-PL04** — Clicking a paper row SHALL open that paper's vault note
(`Papers/{citekey}.md`) in a floating popout window using
`app.workspace.openPopoutLeaf()`. If the note does not exist, it SHALL open in a
regular new tab instead, with no error modal.

**REQ-PL05** — The paper list SHALL show a sticky column header row.

---

### 2.6 Pipeline Controls

**REQ-P01** — The controls region SHALL contain the following stage buttons:

| Button | Command | Phase |
|---|---|---|
| Skeleton | `zsum skeleton` | A |
| Cards | `zsum cards` | B |
| Digests | `zsum digests` | B |
| Redigest | `zsum redigest` | B |
| Citations | `zsum citations` | A |
| Publish | `zsum publish` | A+B |
| Full Run | `zsum all` | A+B |
| Reviews | `zsum reviews` | A |
| Restructure | `zsum restructure` | B |
| Stats | `zsum stats` | A |

**REQ-P02** — Before running any LLM stage (Cards, Digests, Redigest, Full Run), the plugin
SHALL display a cost estimate in the controls header of the form:
`~$X.XX estimated · N cards pending`

The estimate SHALL be calculated as:
```
cost = pending_cards × (tokensPerCardIn × costPerMTokenIn / 1e6
                      + tokensPerCardOut × costPerMTokenOut / 1e6)
```
where all four variables come from plugin settings (REQ-S01).

**REQ-P03** — While a pipeline stage is running:
- The active button SHALL show a spinner and "Running…" label
- All other stage buttons SHALL be disabled
- A Cancel button SHALL appear that sends SIGTERM to the subprocess
- A progress bar SHALL animate at the top of the view (indeterminate)

**REQ-P04** — The collection refresh action on the Paper List (REQ-PL03) SHALL
queue `zsum digests --collection <collection_name>` and then
`zsum redigest --collection <collection_name>`. The redigest step SHALL run only
after the digest step completes successfully.

**REQ-P05** — Log output from the subprocess stdout SHALL be streamed line-by-line
into a log pane within the controls region. Each line SHALL be prefixed with a
timestamp (wall-clock HH:MM:SS). Lines containing `✓` SHALL be tinted green;
lines containing `⚠` amber; all others use the muted text color.

**REQ-P06** — The log pane SHALL auto-scroll to the latest line while running.
The user MAY scroll up to read earlier output; auto-scroll SHALL resume when the
user scrolls back to the bottom.

**REQ-P07** — On run completion (exit code 0), the plugin SHALL:
1. Refresh `cache/index.json` and update all UI regions
2. Log a final line: `[zsum] finished in Xs`

**REQ-P08** — On run failure (non-zero exit code), the plugin SHALL:
1. Log the final stderr output in red
2. Show an Obsidian `Notice` with the text "zsum failed — see log for details"
3. NOT show a blocking modal

---

### 2.7 Config Tab

**REQ-C01** — The Config tab SHALL edit the external YAML file referenced by
`configPath`.

**REQ-C02** — The Config tab SHALL group fields by section:
- Paths
- Scope
- Extraction
- LLM Routing
- LLM Anthropic
- LLM OpenAI Compatible
- LLM Codex Exec
- Output
- Versioning
- Citations
- Restructure

**REQ-C03** — Finite option sets SHALL use dropdown controls. This includes the
provider selectors for `llm.routing.cards`, `llm.routing.digests`, and
`llm.routing.redigest`.

**REQ-C04** — `llm.openai_compat.model` SHALL remain a free-text input so the
user can type an arbitrary model name exposed by their server.

**REQ-C05** — The Config tab SHALL expose explicit `Save`, `Revert`, and
`Reload from disk` actions. Edits SHALL remain buffered in memory until the user
clicks `Save`.

**REQ-C06** — The Config tab SHALL surface dirty state, validation errors,
missing-file warnings, and YAML parse errors inline. Save SHALL be disabled
while parse or validation errors are present.

**REQ-C07** — Saving SHALL preserve comments and unrelated YAML keys instead of
rewriting the entire file from a lossy object dump.

---

### 2.8 Data Freshness

**REQ-DF01** — The plugin SHALL read `cache/index.json` on:
- View open
- After any pipeline run completes (REQ-P07)
- On the `zsum:refresh` command (palette entry "Zotero Summarizer: Refresh")

**REQ-DF02** — The plugin SHALL NOT poll `cache/index.json` on a timer. Reads are
event-driven only.

**REQ-DF03** — The plugin SHALL NOT watch the filesystem for changes (no
`vault.on('modify', ...)` loop). This avoids performance issues with large caches.

---

## 3. Data Requirements

**REQ-D01** — The `zsum index` stage SHALL write a file `cache/index.json` with
the following schema. This is a **new output** from the CLI, not currently in
the v1 spec — it must be added.

```jsonc
{
  "generated_at": "2025-03-15T14:03:22Z",    // ISO 8601
  "collections": {
    "COL_KEY_1": {
      "name": "Phase Field Modeling",
      "parent": null,                          // null = root
      "path": "Phase Field Modeling",
      "item_count": 89,
      "digest_state": "ok | stale | missing", // ok = exists + membership unchanged
      "redigest_state": "ok | stale | missing"
    }
  },
  "items": {
    "smith2017PhaseField": {
      "citekey": "smith2017PhaseField",
      "year": 2017,
      "venue": "JMPS",
      "collections": ["COL_KEY_1", "COL_KEY_2"],
      "card_state": "cached | pending | degraded | no_pdf"
    }
  }
}
```

**REQ-D02** — `cache/index.json` SHALL be regenerated every time `zsum index`
runs (which is the first stage of every pipeline invocation). The plugin treats
it as a read-only snapshot.

**REQ-D03** — The plugin SHALL NOT read or write any other cache files directly
(`cards/`, `digests/`, `redigests/`, `membership.json`). All library status
comes from `cache/index.json`.

**REQ-D04** — The plugin SHALL read the configured zsum YAML file to extract
`cache_dir` and `vault_output`, so it knows where to look for `index.json` and
where collection/paper notes are written.

**REQ-D05** — When the user edits config through the Config tab, the plugin
SHALL write changes back to that YAML file while preserving comments and
unrelated keys.

---

## 4. Out of Scope for v1

The following are explicitly deferred to v2:

| Feature | Reason |
|---|---|
| Filter / search in paper list | Low priority for solo use |
| Per-paper card preview pane | Opening the vault note covers this use case |
| Thematic clustering view | Depends on v2 CLI feature |
| Cost history / run log persistence | Nice to have, not needed for core workflow |
| Multi-vault support | Single-vault assumption simplifies everything |
| Windows support | Primary user is on macOS/Linux; `SIGTERM` and path handling untested on Windows |

---

## 5. Open Questions

| # | Question | Status |
|---|---|---|
| OQ-1 | Should the plugin write `cache/index.json` itself as a fallback if the CLI hasn't been run yet, or just show an empty state? | **Decision: empty state with instructions.** Do not generate partial data. |
| OQ-2 | `openPopoutLeaf` availability — is it stable in Obsidian ≥ 1.4.0? | Needs verification against Obsidian API changelog. |
| OQ-3 | Should the per-collection refresh flow target names or internal keys? | Decision: use collection names in plugin commands; CLI handles name/key matching. |
| OQ-4 | What happens if `uv` is not in PATH on macOS (e.g. installed via Homebrew, not in login shell PATH)? | REQ-S03 "Test command" button surfaces this; document workaround in README. |
