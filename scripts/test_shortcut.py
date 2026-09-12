#!/usr/bin/env python3
"""Inspect the platform desktop shortcut created by the installer."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys


def _desktop_dir() -> Path:
    if sys.platform.startswith("linux"):
        xdg = shutil.which("xdg-user-dir")
        if xdg:
            result = subprocess.run([xdg, "DESKTOP"], text=True, capture_output=True, check=False)
            if result.returncode == 0 and result.stdout.strip():
                return Path(result.stdout.strip())
    return Path.home() / "Desktop"


def _venv_python() -> Path:
    configured = os.environ.get("HELIXENGINE_VENV")
    venv = Path(configured).expanduser() if configured else Path.home() / ".helixengine-venv"
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _check_windows(expected: Path) -> None:
    script = r'''
$shell = New-Object -ComObject WScript.Shell
$desktop = $shell.SpecialFolders.Item("Desktop")
$link = Join-Path $desktop "Helix Engine.lnk"
if (-not (Test-Path -LiteralPath $link -PathType Leaf)) { throw "missing shortcut: $link" }
$shortcut = $shell.CreateShortcut($link)
if (-not ([StringComparer]::OrdinalIgnoreCase.Equals([string]$shortcut.TargetPath, [string]$env:HELIX_EXPECTED_TARGET))) { throw "target mismatch: $($shortcut.TargetPath)" }
if (([string]$shortcut.Arguments).Trim() -ne "-m helixengine serve --port 8769 --open") { throw "arguments mismatch: $($shortcut.Arguments)" }
Write-Output $link
'''
    environment = os.environ.copy()
    environment["HELIX_EXPECTED_TARGET"] = str(expected)
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        raise SystemExit("PowerShell is required to inspect the Windows .lnk shortcut")
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"Windows shortcut inspection failed:\n{result.stdout}\n{result.stderr}")
    print(result.stdout.strip())


def main() -> int:
    # Keep the venv path itself; venv Python is commonly a symlink on POSIX,
    # while the shortcut intentionally targets the venv path beside its
    # console script.
    expected = _venv_python().absolute()
    if os.name == "nt":
        _check_windows(expected)
        return 0

    desktop = _desktop_dir()
    if sys.platform == "darwin":
        shortcut = desktop / "Helix Engine.command"
    elif sys.platform.startswith("linux"):
        shortcut = desktop / "Helix Engine.desktop"
    else:
        raise SystemExit(f"unsupported platform for shortcut test: {sys.platform}")
    if not shortcut.is_file() or not os.access(shortcut, os.X_OK):
        raise SystemExit(f"missing or non-executable shortcut: {shortcut}")
    content = shortcut.read_text(encoding="utf-8")
    if "# Helix Engine generated shortcut v1" not in content:
        raise SystemExit(f"shortcut marker missing: {shortcut}")
    if str(expected) not in content or "-m helixengine serve --port 8769 --open" not in content:
        raise SystemExit(f"shortcut target or arguments missing: {shortcut}")
    print(shortcut)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
