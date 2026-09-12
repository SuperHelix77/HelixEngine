#!/usr/bin/env bash
set -euo pipefail

# This file is intentionally independent of its own location.  The supported
# one-command install pipes it directly from GitHub into bash.
release_wheel_url="https://github.com/SuperHelix77/HelixEngine/releases/download/v0.1.0/helixengine-0.1.0-py3-none-any.whl"
home_dir="${HOME:-}"
if [ -z "$home_dir" ]; then
  echo "HOME is required for a per-user Helix Engine installation." >&2
  exit 2
fi

venv_path="${HELIXENGINE_VENV:-$home_dir/.helixengine-venv}"
python_bin="${PYTHON_BIN:-python3}"
offline=0
no_shortcut=0
wheel_path=""

usage() {
  cat <<'EOF'
Usage: install.sh [OPTIONS] [WHEEL]

Install Helix Engine into a dedicated per-user virtual environment.

With no wheel argument, the pinned GitHub release wheel is downloaded by pip.
Pass a local wheel for a local install.  Add --offline to forbid indexes and
resolve certifi only from the local wheel's directory.

Options:
  --offline             Require a local wheel and use no package index.
  --wheel PATH          Install this local wheel.
  --venv PATH           Override ~/.helixengine-venv for this invocation.
  --no-shortcut         Do not create or update the desktop launcher.
  -h, --help            Show this help.

Environment:
  PYTHON_BIN             Python 3.11+ used to create the virtual environment.
  HELIXENGINE_VENV       Per-user virtual environment path.
EOF
}

die() {
  echo "install.sh: $*" >&2
  exit 2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --offline)
      offline=1
      shift
      ;;
    --offline=*)
      offline=1
      wheel_path="${1#*=}"
      shift
      ;;
    --wheel)
      [ "$#" -ge 2 ] || die "--wheel requires a path"
      wheel_path="$2"
      shift 2
      ;;
    --venv)
      [ "$#" -ge 2 ] || die "--venv requires a path"
      venv_path="$2"
      shift 2
      ;;
    --no-shortcut)
      no_shortcut=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      [ "$#" -le 1 ] || die "only one wheel path may be supplied"
      if [ "$#" -eq 1 ]; then
        [ -z "$wheel_path" ] || die "a wheel path was supplied twice"
        wheel_path="$1"
      fi
      shift || true
      ;;
    -*)
      die "unknown option: $1"
      ;;
    *)
      [ -z "$wheel_path" ] || die "a wheel path was supplied twice"
      wheel_path="$1"
      shift
      ;;
  esac
done

[ "$offline" -eq 0 ] || [ -n "$wheel_path" ] || die "--offline requires a local wheel"

if ! command -v "$python_bin" >/dev/null 2>&1 && [ ! -x "$python_bin" ]; then
  die "Python executable not found: $python_bin"
fi

if [ -n "$wheel_path" ]; then
  [ -f "$wheel_path" ] || die "wheel does not exist: $wheel_path"
  wheel_path="$(CDPATH= cd -- "$(dirname -- "$wheel_path")" && pwd)/$(basename -- "$wheel_path")"
fi

venv_python="$venv_path/bin/python"
if [ ! -x "$venv_python" ]; then
  if [ -e "$venv_path" ] && [ ! -d "$venv_path" ]; then
    die "virtual-environment path is not a directory: $venv_path"
  fi
  mkdir -p "$(dirname -- "$venv_path")"
  "$python_bin" -m venv "$venv_path"
fi
[ -x "$venv_python" ] || die "virtual environment has no executable: $venv_python"

if [ "$offline" -eq 1 ]; then
  wheel_dir="$(dirname -- "$wheel_path")"
  "$venv_python" -m pip install --no-index --find-links "$wheel_dir" --upgrade "$wheel_path"
elif [ -n "$wheel_path" ]; then
  # A local wheel is explicit, but its runtime dependency may still be
  # resolved online unless --offline was requested.
  "$venv_python" -m pip install --upgrade "$wheel_path"
else
  "$venv_python" -m pip install --upgrade "$release_wheel_url"
fi

shell_quote() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//\$/\\\$}"
  value="${value//\`/\\\`}"
  printf '%s' "$value"
}

backup_unowned() {
  local target="$1"
  local marker="$2"
  local stamp backup index
  [ -e "$target" ] || return 0
  [ -f "$target" ] || die "desktop shortcut path is not a regular file: $target"
  grep -Fqx "$marker" "$target" >/dev/null 2>&1 && return 0
  stamp="$(date +%Y%m%d%H%M%S)"
  backup="${target}.backup-${stamp}"
  index=0
  while [ -e "$backup" ]; do
    index=$((index + 1))
    backup="${target}.backup-${stamp}-${index}"
  done
  mv "$target" "$backup"
  echo "Preserved existing desktop shortcut as $backup"
}

create_mac_shortcut() {
  local desktop target escaped
  desktop="$home_dir/Desktop"
  mkdir -p "$desktop"
  target="$desktop/Helix Engine.command"
  backup_unowned "$target" "# Helix Engine generated shortcut v1"
  escaped="$(shell_quote "$venv_python")"
  {
    printf '%s\n' '#!/bin/sh' '# Helix Engine generated shortcut v1'
    printf '%s\n' '# The server stays in the foreground; an occupied port is never killed.'
    printf 'exec "%s" -m helixengine serve --port 8769 --open\n' "$escaped"
  } > "$target"
  chmod +x "$target"
  echo "Created $target"
}

create_linux_shortcut() {
  local desktop target escaped
  desktop=""
  if command -v xdg-user-dir >/dev/null 2>&1; then
    desktop="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
  fi
  [ -n "$desktop" ] || desktop="$home_dir/Desktop"
  mkdir -p "$desktop"
  target="$desktop/Helix Engine.desktop"
  backup_unowned "$target" "# Helix Engine generated shortcut v1"
  escaped="$(shell_quote "$venv_python")"
  {
    printf '%s\n' '# Helix Engine generated shortcut v1' '[Desktop Entry]'
    printf '%s\n' 'Type=Application' 'Version=1.0' 'Name=Helix Engine'
    printf '%s\n' 'Comment=Launch the local Helix Engine console'
    printf 'Exec="%s" -m helixengine serve --port 8769 --open\n' "$escaped"
    printf '%s\n' 'Terminal=true' 'Categories=Development;'
  } > "$target"
  chmod +x "$target"
  echo "Created $target"
}

if [ "$no_shortcut" -eq 0 ]; then
  case "$(uname -s)" in
    Darwin) create_mac_shortcut ;;
    Linux) create_linux_shortcut ;;
    *) echo "No desktop shortcut implementation for $(uname -s); installation is complete." ;;
  esac
fi

echo "Installed helixengine 0.1.0 in $venv_path"
echo "Run: $venv_python -m helixengine --help"
