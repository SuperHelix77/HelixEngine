#!/usr/bin/env bash
set -euo pipefail

home_dir="${HOME:-}"
[ -n "$home_dir" ] || { echo "uninstall.sh: HOME is required" >&2; exit 2; }
venv_path="${HELIXENGINE_VENV:-$home_dir/.helixengine-venv}"
venv_python="$venv_path/bin/python"

if [ ! -x "$venv_python" ]; then
  echo "uninstall.sh: Helix Engine venv not found: $venv_path" >&2
  echo "User data was not touched." >&2
  exit 2
fi

"$venv_python" -m pip uninstall --yes helixengine

remove_owned() {
  local target="$1"
  local marker="$2"
  if [ -f "$target" ] && grep -Fqx "$marker" "$target" >/dev/null 2>&1; then
    rm "$target"
    echo "Removed $target"
  fi
}

remove_owned "$home_dir/Desktop/Helix Engine.command" "# Helix Engine generated shortcut v1"
desktop_dir=""
if command -v xdg-user-dir >/dev/null 2>&1; then
  desktop_dir="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
fi
[ -n "$desktop_dir" ] || desktop_dir="$home_dir/Desktop"
remove_owned "$desktop_dir/Helix Engine.desktop" "# Helix Engine generated shortcut v1"

echo "Package removed from $venv_path; the virtual environment and $home_dir/.helixengine user data were preserved."
