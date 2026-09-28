#!/usr/bin/env bash
# install.sh — one-shot installer for the zsum CLI and the Obsidian plugin.
#
# Usage:
#   ./install.sh <vault-path>
#   ./install.sh --vault <vault-path>
#   VAULT_PATH=/path/to/vault ./install.sh
#   ./install.sh --cli-only
#   ./install.sh --plugin-only --vault <vault-path>
#
# Flags:
#   -v, --vault <path>   Obsidian vault root (the folder containing .obsidian/).
#   --cli-only           Skip plugin install.
#   --plugin-only        Skip CLI install (requires --vault).
#   --skip-deps          Skip `npm install` before building the plugin.
#   --skip-build         Skip `npm run build`; copy the committed main.js as-is.
#   -h, --help           Show this help and exit.
#
# Exits non-zero on any failure. Safe to re-run.

set -euo pipefail

# ---------------------------------------------------------------------------
# Paths + colors
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_SRC="$SCRIPT_DIR/plugin_dev"
PLUGIN_ID="obsidian-zsum"
RELEASE_FILES=(main.js manifest.json styles.css)

if [[ -t 1 ]]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'
  C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
  C_RED=$'\033[31m'; C_BLUE=$'\033[34m'
else
  C_RESET=''; C_BOLD=''; C_GREEN=''; C_YELLOW=''; C_RED=''; C_BLUE=''
fi

log()  { printf '%s[zsum-install]%s %s\n' "$C_BLUE" "$C_RESET" "$*"; }
ok()   { printf '%s[zsum-install]%s %s%s%s\n' "$C_BLUE" "$C_RESET" "$C_GREEN" "$*" "$C_RESET"; }
warn() { printf '%s[zsum-install]%s %s%s%s\n' "$C_BLUE" "$C_RESET" "$C_YELLOW" "$*" "$C_RESET" >&2; }
die()  { printf '%s[zsum-install]%s %serror:%s %s\n' "$C_BLUE" "$C_RESET" "$C_RED" "$C_RESET" "$*" >&2; exit 1; }

usage() { sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

VAULT_PATH="${VAULT_PATH:-}"
DO_CLI=1
DO_PLUGIN=1
DO_NPM_INSTALL=1
DO_NPM_BUILD=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    -v|--vault)
      [[ $# -lt 2 ]] && die "--vault requires a path argument"
      VAULT_PATH="$2"; shift 2
      ;;
    --cli-only)    DO_PLUGIN=0; shift ;;
    --plugin-only) DO_CLI=0; shift ;;
    --skip-deps)   DO_NPM_INSTALL=0; shift ;;
    --skip-build)  DO_NPM_BUILD=0; shift ;;
    -h|--help)     usage; exit 0 ;;
    -*)            die "unknown flag: $1" ;;
    *)
      if [[ -z "$VAULT_PATH" ]]; then
        VAULT_PATH="$1"; shift
      else
        die "unexpected positional argument: $1"
      fi
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------

require_bin() { command -v "$1" >/dev/null 2>&1 || die "missing required command: $1 — $2"; }

if [[ $DO_CLI -eq 1 ]]; then
  require_bin uv "install from https://docs.astral.sh/uv/getting-started/installation/"
fi

if [[ $DO_PLUGIN -eq 1 ]]; then
  [[ -z "$VAULT_PATH" ]] && { usage; die "vault path is required for plugin install (pass it as an arg, --vault, or VAULT_PATH env)"; }
  if [[ $DO_NPM_BUILD -eq 1 ]]; then
    require_bin npm "install Node.js (which bundles npm) from https://nodejs.org/"
  fi
fi

# Resolve vault path early so errors surface before we start installing.
if [[ $DO_PLUGIN -eq 1 ]]; then
  # Expand ~ manually — `eval echo` is unsafe on paths with spaces.
  if [[ "$VAULT_PATH" == "~"* ]]; then
    VAULT_PATH="${HOME}${VAULT_PATH:1}"
  fi
  [[ -d "$VAULT_PATH" ]] || die "vault path does not exist or is not a directory: $VAULT_PATH"
  [[ -d "$VAULT_PATH/.obsidian" ]] || warn "$VAULT_PATH has no .obsidian/ folder — is this really an Obsidian vault? Proceeding anyway."
fi

cd "$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# CLI install
# ---------------------------------------------------------------------------

install_cli() {
  log "Installing zsum CLI via 'uv tool install -e .'"
  uv tool install -e . --force
  # Sanity: zsum should be on PATH now (uv adds ~/.local/bin).
  if command -v zsum >/dev/null 2>&1; then
    ok "CLI installed: $(command -v zsum)"
  else
    warn "zsum is installed but not on PATH. Make sure ~/.local/bin is in your PATH."
    warn "Run:  export PATH=\"\$HOME/.local/bin:\$PATH\"  (add to your shell rc file to persist)."
  fi
}

# ---------------------------------------------------------------------------
# Plugin install
# ---------------------------------------------------------------------------

install_plugin() {
  [[ -d "$PLUGIN_SRC" ]] || die "plugin source not found at $PLUGIN_SRC"

  if [[ $DO_NPM_BUILD -eq 1 ]]; then
    log "Building plugin bundle"
    (
      cd "$PLUGIN_SRC"
      if [[ $DO_NPM_INSTALL -eq 1 ]]; then
        if [[ -f package-lock.json ]]; then
          npm ci --no-audit --no-fund || npm install --no-audit --no-fund
        else
          npm install --no-audit --no-fund
        fi
      fi
      npm run build
    )
  else
    log "Skipping plugin build (--skip-build); expecting committed main.js to be current"
  fi

  for f in "${RELEASE_FILES[@]}"; do
    [[ -f "$PLUGIN_SRC/$f" ]] || die "expected plugin file missing: $PLUGIN_SRC/$f (did the build fail?)"
  done

  local dest="$VAULT_PATH/.obsidian/plugins/$PLUGIN_ID"
  mkdir -p "$dest"

  log "Installing plugin files to $dest"
  for f in "${RELEASE_FILES[@]}"; do
    cp "$PLUGIN_SRC/$f" "$dest/$f"
  done
  ok "Plugin files copied: ${RELEASE_FILES[*]}"
}

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

[[ $DO_CLI -eq 1 ]]    && install_cli
[[ $DO_PLUGIN -eq 1 ]] && install_plugin

ok "Done."
if [[ $DO_PLUGIN -eq 1 ]]; then
  cat <<EOF

Next steps:
  1. Open Obsidian with the vault at:
       $VAULT_PATH
  2. Go to Settings -> Community plugins.
  3. If this is a fresh install, enable "Zotero Summarizer".
     If you upgraded, toggle it off and on so the new main.js is picked up.
  4. In the plugin settings, point 'Config path' to your zsum.config.yaml.
  5. Click the book icon in the ribbon (or run the 'Zotero Summarizer: Open view' command).

EOF
fi
