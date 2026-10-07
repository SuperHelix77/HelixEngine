#!/usr/bin/env bash
# Removes the helix symlink and (if you ask) the hooks Helix added to ~/.claude/settings.json. Leaves this directory and your memory.db alone.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; PREFIX="${1:-$HOME/.local/bin}"
[ -L "$PREFIX/helix" ] && [ "$(readlink "$PREFIX/helix")" = "$HERE/helix" ] && { rm "$PREFIX/helix"; echo "removed $PREFIX/helix"; } || echo "no helix link at $PREFIX"
[ -L "$PREFIX/helix-grok" ] && [ "$(readlink "$PREFIX/helix-grok")" = "$HERE/helix" ] && { rm "$PREFIX/helix-grok"; echo "removed $PREFIX/helix-grok"; } || echo "no helix-grok link at $PREFIX"
"$HERE/helix" lm-down 2>/dev/null || true
echo "To remove Claude hooks you installed:  helix hooks uninstall   (restorable backups: ~/.claude/settings.json.bak-helix-*)"
echo "To remove Grok hooks you installed:    helix grok hooks uninstall   (backup beside ~/.grok/hooks/helix.json)"
echo "To delete everything: rm -rf $HERE   (this also deletes your local memory.db)"
