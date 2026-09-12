#!/usr/bin/env bash
set -euo pipefail

install_url="https://raw.githubusercontent.com/SuperHelix77/HelixEngine/v0.1.0/scripts/install.sh"
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ -f "$script_dir/install.sh" ]; then
  exec "$script_dir/install.sh" "$@"
fi

command -v curl >/dev/null 2>&1 || {
  echo "update.sh: curl is required when the helper is not run from a checkout" >&2
  exit 2
}
curl -fsSL "$install_url" | bash -s -- "$@"
