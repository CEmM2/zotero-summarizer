# TECHNICAL SPEC — obsidian-zsum

**Version:** 1.1  
**Status:** Draft  
**Depends on:** REQUIREMENTS.md v1.1

---

## 1. Technology Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language | TypeScript | Required by Obsidian plugin API |
| Build tool | esbuild (via Obsidian plugin template) | Standard for Obsidian plugins; fast |
| UI framework | Vanilla DOM | No React/Svelte. The view is simple enough; adding a framework increases bundle size and complexity for marginal gain |
| YAML parsing | `yaml` Document API | Preserves comments and unrelated keys while still allowing targeted field edits |
| CSS | Single `styles.css` using Obsidian CSS variables | Automatic light/dark theme support |
| Testing | Node test runner + targeted pytest wrappers + manual desktop smoke | Covers config/document and view-model contracts without adding a frontend framework |

---

## 2. File Structure

```
obsidian-zsum/
├── src/
│   ├── main.ts           # Plugin class, lifecycle, command/view registration
│   ├── view.ts           # ZsumView — full UI, DOM management
│   ├── view-model.ts     # Pure UI metadata helpers for tabs, config actions, and refresh queue
│   ├── index-reader.ts   # Reads + parses cache/index.json
│   ├── config.ts         # Comment-preserving YAML document service + runtime config reader
│   ├── runner.ts         # Spawns subprocess, streams stdout
│   ├── cost.ts           # Cost estimation pure functions
│   ├── settings.ts       # ZsumSettingsTab (Obsidian PluginSettingTab)
│   ├── config.test.mjs   # Config document service tests
│   └── view-model.test.mjs # View-model contract tests
├── styles.css
├── manifest.json
├── package.json
├── tsconfig.json
├── esbuild.config.mjs
└── docs/
    ├── REQUIREMENTS.md
    └── TECHNICAL_SPEC.md   ← this file
```

---

## 3. Module Specifications

### 3.1 `main.ts` — Plugin entry point

```typescript
export default class ZsumPlugin extends Plugin {
  settings: ZsumSettings;

  async onload(): Promise<void>
  async onunload(): Promise<void>
  async loadSettings(): Promise<void>
  async saveSettings(): Promise<void>
}
```

**onload responsibilities:**
1. Load settings via `loadSettings()`
2. Register `ZsumView` with `registerView(VIEW_TYPE_ZSUM, ...)`
3. Add ribbon icon; on click → `activateView()`
4. Register commands:
   - `zsum:open` — activate view
   - `zsum:run-all` — shortcut for Full Run (calls runner directly)
   - `zsum:refresh` — re-reads index.json, updates view
5. Register `ZsumSettingsTab`

**activateView():** Checks if a leaf with `VIEW_TYPE_ZSUM` already exists; if
so, reveals it. Otherwise creates a new tab leaf. Always sets the leaf active.

```typescript
export const VIEW_TYPE_ZSUM = 'zsum-view';
```

---

### 3.2 `settings.ts` — Settings schema and tab

```typescript
export interface ZsumSettings {
  configPath: string;         // vault-relative or absolute path to zsum.config.yaml
  pythonCmd: string;          // default: "uv run zsum"
  costPerMTokenIn: number;    // default: 3.00
  costPerMTokenOut: number;   // default: 15.00
  tokensPerCardIn: number;    // default: 4000
  tokensPerCardOut: number;   // default: 500
}

export const DEFAULT_SETTINGS: ZsumSettings = { ... };

export class ZsumSettingsTab extends PluginSettingTab {
  display(): void   // renders settings UI
}
```

**Settings tab layout:**

1. **Paths section**
   - `configPath` — text input + inline warning if file not found
   - `pythonCmd` — text input
   - "Test command" button → runs `<pythonCmd> stats`, shows output in a `new Modal`

2. **Cost estimation section**
   - `costPerMTokenIn` — number input (USD)
   - `costPerMTokenOut` — number input (USD)
   - `tokensPerCardIn` — number input
   - `tokensPerCardOut` — number input
   - Live preview: "Current estimate: $X.XX per card"

**Config path resolution** (used across modules, extracted to `config.ts`):

```typescript
function resolveConfigPath(configPath: string, vaultBasePath: string): string
// If configPath is absolute → return as-is
// If relative → join with vaultBasePath
```

---

### 3.3 `config.ts` — YAML document service + runtime reader

Owns the editable config schema, the comment-preserving YAML document service,
and the minimal runtime config needed by the rest of the plugin.

```typescript
export interface ZsumConfig {
  cache_dir: string;      // may be relative (to config file location) or absolute
  vault_output: string;   // path where vault notes are written
}

export class ZsumConfigDocumentService {
  static open(configPath: string, vaultBasePath: string): Promise<ZsumConfigDocumentService>
  getState(): ZsumConfigDocumentState
  updateField(path: ZsumEditableFieldPath, value: unknown): ZsumConfigDocumentState
  revert(): ZsumConfigDocumentState
  reloadFromDisk(): Promise<ZsumConfigDocumentState>
  save(): Promise<ZsumConfigDocumentState>
  readRuntimeConfig(): ZsumConfig | null
}

export async function readZsumConfig(
  configPath: string,
  vaultBasePath: string
): Promise<ZsumConfig | null>
// Returns null if file not found or unparseable.
// Resolves relative paths against the directory containing configPath.
```

Key behavior:

- Uses `yaml`'s parsed `Document` tree so comments and unknown keys survive save round-trips
- Buffers edits in memory until explicit `save()`
- Exposes validation errors, parse errors, dirty state, and resolved-path previews
- Writes via temp-file + atomic rename
- Keeps `readZsumConfig()` as a compatibility helper that reads through the service layer

---

### 3.4 `index-reader.ts` — cache/index.json reader

```typescript
export interface CollectionIndex {
  name: string;
  parent: string | null;
  path: string;
  item_count: number;
  digest_state: 'ok' | 'stale' | 'missing';
  redigest_state: 'ok' | 'stale' | 'missing';
}

export interface ItemIndex {
  citekey: string;
  year: number;
  venue: string;
  collections: string[];
  card_state: 'cached' | 'pending' | 'degraded' | 'no_pdf';
}

export interface ZsumIndex {
  generated_at: string;
  collections: Record<string, CollectionIndex>;
  items: Record<string, ItemIndex>;
}

export interface LibraryStats {
  total_collections: number;
  total_papers: number;
  cards_cached: number;
  cards_pending: number;
  cards_degraded: number;
  digests_ok: number;
  digests_stale: number;
  digests_missing: number;
}

export async function readIndex(
  cacheDir: string,
  vault: Vault
): Promise<ZsumIndex | null>
// Returns null if cache/index.json does not exist.

export function computeStats(index: ZsumIndex): LibraryStats

export function getCollectionPapers(
  index: ZsumIndex,
  collectionKey: string
): ItemIndex[]
// Returns papers belonging to the given collection key, sorted by year desc.
```

---

### 3.5 `cost.ts` — Cost estimation

Pure functions, no I/O.

```typescript
export interface CostEstimate {
  pending_cards: number;
  cost_usd: number;
  cost_display: string;   // e.g. "~$1.18"
}

export function estimateCost(
  pendingCards: number,
  settings: ZsumSettings
): CostEstimate

// Formula:
// per_card = (tokensPerCardIn * costPerMTokenIn / 1e6)
//          + (tokensPerCardOut * costPerMTokenOut / 1e6)
// total = pendingCards * per_card
// display = "~$" + total.toFixed(2)  (show "~$0.00" if zero)
```

---

### 3.6 `runner.ts` — Subprocess management

Uses Node's `child_process.spawn` (available in Obsidian's Electron environment).

```typescript
export type LogLine = {
  time: string;       // "HH:MM:SS"
  text: string;
  level: 'ok' | 'warn' | 'error' | 'info';
};

export type RunnerState = 'idle' | 'running' | 'done' | 'failed';

export type RunnerEventMap = {
  'log': LogLine;
  'state-change': RunnerState;
  'done': { exit_code: number; duration_ms: number };
};

export class ZsumRunner extends EventEmitter<RunnerEventMap> {
  get state(): RunnerState

  run(cmd: string, args: string[], cwd: string): void
  // Throws if already running.
  // Parses pythonCmd into cmd + base args, appends stage args.
  // e.g. pythonCmd="uv run zsum", stage="cards"
  //   → spawn("uv", ["run", "zsum", "cards"])

  cancel(): void
  // Sends SIGTERM. If process doesn't exit within 3s, sends SIGKILL.
}
```

**Log line classification:**

```
contains "✓"  → level: 'ok'
contains "⚠"  → level: 'warn'
starts with "Error" or stderr → level: 'error'
otherwise     → level: 'info'
```

**pythonCmd parsing:**

Split on whitespace. First token is the executable; remainder are prepended args.
This handles `uv run zsum`, `python -m zsum`, `/opt/homebrew/bin/uv run zsum`, etc.

```typescript
function parseCmd(pythonCmd: string, stageArgs: string[]): [string, string[]] {
  const parts = pythonCmd.trim().split(/\s+/);
  return [parts[0], [...parts.slice(1), ...stageArgs]];
}
```

**Stage args by button:**

| Button | stageArgs |
|---|---|
| Skeleton | `["skeleton"]` |
| Cards | `["cards"]` |
| Digests | `["digests"]` |
| Redigest | `["redigest"]` |
| Citations | `["citations"]` |
| Publish | `["publish"]` |
| Full Run | `["all"]` |
| Reviews | `["reviews"]` |
| Restructure | `["restructure"]` |
| Stats | `["stats"]` |
| Refresh final digest (collection) | queue `["digests", "--collection", collectionName]` then `["redigest", "--collection", collectionName]` |

---

### 3.7 `view.ts` — ZsumView

```typescript
export class ZsumView extends ItemView {
  private index: ZsumIndex | null = null;
  private selectedCollectionKey: string = 'root';
  private runner: ZsumRunner;
  private logLines: LogLine[] = [];
  private userScrolledUp: boolean = false;
  private activeTab: 'library' | 'config';
  private configService: ZsumConfigDocumentService | null = null;

  getViewType(): string           // returns VIEW_TYPE_ZSUM
  getDisplayText(): string        // returns "Zotero Summarizer"
  getIcon(): string               // returns "book-open" (Lucide icon)

  async onOpen(): Promise<void>
  async onClose(): Promise<void>

  private async loadIndex(): Promise<void>
  private render(): void          // full re-render; called after index load
  private renderTabs(): void
  private renderStatusBar(): void
  private renderTree(): void
  private renderPaperList(collectionKey: string): void
  private renderControls(): void
  private renderConfigPanel(): void
  private appendLogLine(line: LogLine): void
  private selectCollection(key: string): void
  private openPaperNote(citekey: string): Promise<void>
  private openCollectionNote(collectionKey: string): Promise<void>
  private runStage(stageArgs: string[]): void
  private cancelRun(): void
  private updateRunState(state: RunnerState): void
}
```

**Rendering strategy:**

The view uses direct DOM manipulation (no virtual DOM). `render()` clears and
rebuilds the active tab surface on index/config load. Partial updates are used for:
- `appendLogLine()` — appends a single `<div>` to the log pane
- `updateRunState()` — updates button states and progress bar visibility
- `renderStatusBar()` / `renderPaperList()` — called independently after
  collection selection changes
- `renderConfigPanel()` — re-renders the schema-driven config surface after
  config-state changes

This avoids full re-renders during a running pipeline.

**DOM structure:**

```
div.zsum-view
├── div.zsum-status-bar
├── div.zsum-progress-bar [hidden when idle]
├── div.zsum-content
│   ├── div.zsum-tree-panel
│   │   ├── div.zsum-panel-header
│   │   ├── div.zsum-tree-scroll
│   │   │   └── div.zsum-tree-item[data-key="..."] × N
│   │   └── div.zsum-legend
│   └── div.zsum-papers-panel
│       ├── div.zsum-papers-header
│       ├── div.zsum-col-header
│       └── div.zsum-papers-scroll
│           └── div.zsum-paper-row[data-citekey="..."] × N
└── div.zsum-controls
    ├── div.zsum-controls-header
    └── div.zsum-controls-body
        ├── div.zsum-buttons
        └── div.zsum-log
```

**openPaperNote implementation:**

```typescript
private async openPaperNote(citekey: string): Promise<void> {
  const notePath = `Papers/${citekey}.md`;
  const file = this.app.vault.getAbstractFileByPath(notePath);

  if (file instanceof TFile) {
    // Open in popout window
    const leaf = this.app.workspace.openPopoutLeaf();
    await leaf.openFile(file);
  } else {
    // Note doesn't exist yet — open a new tab with a notice
    const leaf = this.app.workspace.getLeaf('tab');
    new Notice(`Note not found: ${notePath}. Run "Publish" to generate notes.`);
  }
}
```

**Auto-scroll logic:**

```typescript
// In appendLogLine:
const atBottom = logEl.scrollHeight - logEl.scrollTop <= logEl.clientHeight + 20;
if (!this.userScrolledUp || atBottom) {
  logEl.scrollTop = logEl.scrollHeight;
  this.userScrolledUp = false;
}

// On scroll event:
logEl.addEventListener('scroll', () => {
  const atBottom = logEl.scrollHeight - logEl.scrollTop <= logEl.clientHeight + 20;
  this.userScrolledUp = !atBottom;
});
```

---

## 4. CSS Architecture

All styles live in `styles.css`. Class names use the `zsum-` prefix to avoid
conflicts with Obsidian or other plugins.

**Theme integration — use only Obsidian variables:**

```css
.zsum-view {
  background: var(--background-primary);
  color: var(--text-normal);
  font-family: var(--font-interface);
}

.zsum-panel-header {
  background: var(--background-secondary);
  border-bottom: 1px solid var(--background-modifier-border);
  color: var(--text-muted);
}

.zsum-tree-item:hover {
  background: var(--background-modifier-hover);
}

.zsum-tree-item.is-selected {
  background: var(--background-modifier-active-hover);
}
```

**Status dot colors — use semantic CSS variables, not hardcoded hex:**

```css
.zsum-dot-ok      { background: var(--color-green); }
.zsum-dot-stale   { background: var(--color-yellow); }
.zsum-dot-missing { background: var(--background-modifier-border); }
```

**Monospace elements (citekeys, log, stats):**

```css
.zsum-citekey, .zsum-log-line, .zsum-stat-val {
  font-family: var(--font-monospace);
  font-size: var(--font-smaller);
}
```

---

## 5. manifest.json

```json
{
  "id": "obsidian-zsum",
  "name": "Zotero Summarizer",
  "version": "1.0.0",
  "minAppVersion": "1.4.0",
  "description": "UI for the zotero-summarizer pipeline",
  "author": "",
  "authorUrl": "",
  "isDesktopOnly": true
}
```

`isDesktopOnly: true` — the plugin spawns subprocesses and reads the filesystem
outside the vault. It cannot work in Obsidian Mobile.

---

## 6. Error States

| Condition | UI behavior |
|---|---|
| `zsum.config.yaml` not found | View shows empty state: "Config file not found. Check plugin settings." |
| YAML parse error in config | Config tab shows inline parse error and disables save until reload after fix |
| `cache/index.json` not found | View shows empty state: "No index found. Run 'Skeleton' or 'Full Run' to get started." |
| `cache/index.json` parse error | Notice: "Failed to read index — file may be corrupt. Try re-running zsum index." |
| subprocess not found (ENOENT) | Log line in red: "Command not found: <cmd>. Check Python command in settings." + Notice |
| subprocess exits non-zero | Log final stderr in red + Notice (REQ-P08) |
| `openPopoutLeaf` not available | Graceful fallback to regular tab (no error shown) |

---

## 7. CLI Coordination (changes required in zotero-summarizer)

The following changes to the Python CLI are required before this plugin can be
fully functional. They should be tracked as issues in the `zotero-summarizer` repo.

| Change | Requirement | Notes |
|---|---|---|
| Write `cache/index.json` in `indexer.py` | REQ-D01 | New file; schema defined in REQUIREMENTS §3 |
| Add `--collection <name>` flag to `zsum digests` | REQ-P04 | Implemented; collection refresh uses this as step 1 |
| Add `zsum redigest` plus `--collection <name>` | REQ-P04 | Implemented; collection refresh uses this as step 2 |
| Add `redigest_state` to `cache/index.json` | REQ-D01 | Implemented for selected-collection status text |
| Ensure `zsum` exits with non-zero code on failure | REQ-P08 | Currently may swallow exceptions |

---

## 8. Build and Release

```json
// package.json (key fields)
{
  "scripts": {
    "dev": "node esbuild.config.mjs",
    "build": "tsc --noEmit --skipLibCheck && node esbuild.config.mjs production",
    "test:config": "node --experimental-strip-types --test src/config.test.mjs",
    "test:view": "node --experimental-strip-types --test src/view-model.test.mjs"
  },
  "dependencies": {
    "yaml": "^2.x"
  },
  "devDependencies": {
    "@types/node": "^16.0.0",
    "obsidian": "latest",
    "typescript": "^5.0.0",
    "esbuild": "0.17.3"
  }
}
```

**Release checklist:**
1. Bump version in `manifest.json` and `package.json`
2. `npm run build` — verify no TypeScript errors
3. Copy `main.js`, `manifest.json`, `styles.css` to vault plugin folder
4. Smoke test: open view, run skeleton, check tree populates
5. Tag release in git

---

## 9. Known Constraints and Risks

| Risk | Severity | Mitigation |
|---|---|---|
| `openPopoutLeaf` API is undocumented / may change | Medium | Wrap in try/catch with fallback to regular tab (implemented in spec §3.7) |
| `child_process` unavailable in future Obsidian sandbox | Low | `isDesktopOnly: true` buys time; monitor Obsidian release notes |
| Large `cache/index.json` (1000+ papers) parse time | Low | JSON.parse of a ~200KB file is <10ms; no concern |
| `uv` not in PATH on macOS (GUI app shell) | High | "Test command" button in settings exposes this immediately; document fix |
| Manual Obsidian desktop smoke test is still required after code changes | High | Keep `npm run build`, `npm run test:config`, and `npm run test:view` green, then do a real vault smoke test before release |
