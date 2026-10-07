#!/usr/bin/env bash
# Removes the helix symlink and (if you ask) the hooks Helix added to ~/.claude/settings.json. Leaves this directory and your memory.db alone.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; PREFIX="${1:-$HOME/.local/bin}"
[ -L "$PREFIX/helix" ] && [ "$(readlink "$PREFIX/helix")" = "$HERE/helix" ] && { rm "$PREFIX/helix"; echo "removed $PREFIX/helix"; } || echo "no helix link at $PREFIX"
"$HERE/helix" lm-down 2>/dev/null || true
echo "To remove hooks you installed:  helix hooks uninstall   (restorable backups: ~/.claude/settings.json.bak-helix-*)"
echo "To delete everything: rm -rf $HERE   (this also deletes your local memory.db)"
