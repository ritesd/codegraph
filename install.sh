#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
UV_BIN_DIR="${HOME}/.local/bin"
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m==>\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m==>\033[0m %s\n' "$*"; }

# ── 1. Ensure uv is installed ────────────────────────────────────────

if command -v uv &>/dev/null; then
    info "uv already installed: $(uv --version)"
else
    info "Installing uv …"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # The installer writes to ~/.local/bin or ~/.cargo/bin — source env
    if [ -f "${HOME}/.cargo/env" ]; then
        # shellcheck disable=SC1091
        source "${HOME}/.cargo/env"
    fi
    export PATH="${UV_BIN_DIR}:${HOME}/.cargo/bin:${PATH}"
    if ! command -v uv &>/dev/null; then
        warn "uv not found on PATH after install — check ~/.local/bin or ~/.cargo/bin"
        exit 1
    fi
    ok "uv installed: $(uv --version)"
fi

# ── 2. Install codegraph as a uv tool ────────────────────────────────

info "Installing codegraph via uv tool install …"
uv tool install "${SCRIPT_DIR}" --force
ok "codegraph installed"

# ── 3. Register PATH in shell rc files ────────────────────────────────

ensure_path_in_rc() {
    local rc="$1"
    if [ ! -f "$rc" ]; then
        return
    fi
    if grep -qF '.local/bin' "$rc" 2>/dev/null; then
        info "$rc already has .local/bin in PATH"
        return
    fi
    printf '\n# Added by codegraph install.sh\n%s\n' "$PATH_LINE" >> "$rc"
    ok "Appended PATH entry to $rc"
}

ensure_path_in_rc "${HOME}/.zshrc"
ensure_path_in_rc "${HOME}/.bashrc"

# ── 4. Verify ─────────────────────────────────────────────────────────

export PATH="${UV_BIN_DIR}:${PATH}"
if command -v codegraph &>/dev/null; then
    ok "Verification passed — codegraph is available:"
    codegraph --help 2>&1 | head -5
else
    warn "codegraph not found on PATH. Open a new terminal or run:"
    echo "  source ~/.zshrc   # or source ~/.bashrc"
fi
