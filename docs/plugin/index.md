# Obsidian Plugin

The **Zotero Summarizer** Obsidian plugin (`obsidian-zsum`) provides a graphical interface for the `zsum` CLI pipeline directly inside your vault.

The plugin does **not** re-implement any pipeline logic. All indexing, PDF extraction, LLM calls, and file writing remain in the Python CLI. The plugin spawns `zsum` as a subprocess and reads its output.

## Features

- Browse collections and papers in a tree view
- Trigger pipeline stages with one click
- Watch live log output from the CLI
- Sort papers by year or citation count
- View review/survey paper classifications
- Edit `config.yaml` from within Obsidian
- Cost estimation before LLM stages

## Requirements

| Dependency | Version | Notes |
|---|---|---|
| Obsidian | >= 1.4.0 | Desktop only (uses Node `child_process`) |
| Python + uv | Any recent | Must be in PATH or configured in settings |
| zotero-summarizer | Installed | CLI must be functional (`zsum stats` should work) |

## Installation

### Fast Path: One-Shot Installer

```bash
./install.sh /path/to/your/obsidian/vault
```

This installs the CLI, builds the plugin, and copies the release files into your vault. Skip to step 5 below.
Because the installer puts `zsum` on your PATH with `uv tool install -e .`, set the plugin's
**Python command** to `zsum` if it is not already configured that way.

### Manual Installation

1. **Install the CLI** — follow the [Installation Guide](../getting-started/installation.md) and install globally with `uv tool install -e .`

2. **Build the plugin bundle**:

    ```bash
    cd plugin_dev
    npm ci --no-audit --no-fund  # or: npm install --no-audit --no-fund
    npm run build      # produces plugin_dev/main.js
    cd ..
    ```

3. **Create the plugin folder**:

    ```bash
    mkdir -p <vault>/.obsidian/plugins/obsidian-zsum
    ```

4. **Copy the three release files**:

    ```bash
    cp plugin_dev/main.js       <vault>/.obsidian/plugins/obsidian-zsum/
    cp plugin_dev/manifest.json <vault>/.obsidian/plugins/obsidian-zsum/
    cp plugin_dev/styles.css    <vault>/.obsidian/plugins/obsidian-zsum/
    ```

    !!! warning
        Only copy these three files. Do **not** copy the whole `plugin_dev/` folder.

5. **Enable the plugin** — in Obsidian, go to **Settings > Community plugins** and enable **Zotero Summarizer**

6. **Configure** — open **Settings > Zotero Summarizer** and set the path to your `config.yaml`

7. **Open the view** — click the book icon in the ribbon, or use the command palette: `Zotero Summarizer: Open view`

## Settings

| Setting | Default | Description |
|---|---|---|
| Config path | `zsum.config.yaml` | Path to your zsum YAML config (vault-relative or absolute). Set this to `config.yaml` or an absolute path if that is where you keep your config. |
| Python command | `uv run zsum` | Command to invoke the CLI. Use `zsum` after global install, or keep `uv run zsum` and set Project root to the repo. |
| Cost per M input tokens | 3.00 | USD per million input tokens (for cost estimation) |
| Cost per M output tokens | 15.00 | USD per million output tokens |
| Tokens per card (in) | 4000 | Estimated input tokens per paper card |
| Tokens per card (out) | 500 | Estimated output tokens per paper card |

Use the **Test command** button to verify the CLI is reachable from within Obsidian.

## Commands

The plugin registers three commands in the Obsidian command palette:

| Command | ID | Description |
|---|---|---|
| Open view | `zsum:open` | Opens or focuses the plugin view |
| Refresh | `zsum:refresh` | Reloads the index from `cache/index.json` |
| Run full pipeline | `zsum:run-all` | Triggers `zsum all` from the open view |

## Upgrading

To upgrade the plugin after pulling new code:

1. Run `uv sync` so the CLI picks up new dependencies
2. Rebuild: `cd plugin_dev && npm ci --no-audit --no-fund && npm run build`
3. Copy the refreshed `main.js`, `manifest.json`, and `styles.css` into the plugin folder
4. Toggle the plugin off and on in Obsidian settings

## Next

- [UI Walkthrough](ui.md) — detailed guide to the plugin interface
- [Troubleshooting](troubleshooting.md) — common issues and solutions
