# Plugin Troubleshooting

Common issues and solutions for the Obsidian plugin.

## "Config file not found"

The config path in plugin settings does not resolve to an existing file.

**Fix:** Check the path in **Settings > Zotero Summarizer**. Use a vault-relative path (e.g., `zsum.config.yaml` if at the vault root) or an absolute path.

## "No index found"

The CLI has not been run yet — no `cache/index.json` exists.

**Fix:** Click **Skeleton** or **Full Run** to generate the initial index.

## Test Command Fails

Obsidian may not inherit your shell's PATH.

**Fixes:**

- Set the Python command to the full path: `/Users/you/.local/bin/zsum`
- Or: `/Users/you/.cargo/bin/uv run zsum`
- Verify that `zsum stats` works in a terminal from the vault directory

## "Note is outside the vault"

The `vault_output` path in your config points outside your Obsidian vault.

**Fix:** Set `vault_output` to a subdirectory within your vault.

## Regenerate Digest Fails

The per-collection refresh runs both `digests --collection` and `redigest --collection`.

**Fix:** If you see errors about unknown subcommands, update the CLI with `uv sync`.

## Config Tab Shows Parse Error

The plugin won't overwrite malformed YAML.

**Fix:** Fix the file in the Config tab or on disk, then click **Reload from disk**.

## Limitations

- **Desktop only** — uses Node's `child_process`, not available on mobile
- **No paper list search/filtering** — planned for a future version
- **No per-paper card preview** — cards are viewable only as generated notes
- **No cost history** — cost estimates are session-only
- **Windows** — process cancellation uses Windows-safe termination, but PATH and shell startup can still differ from macOS/Linux
