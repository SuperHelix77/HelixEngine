# Installation, update, and removal

Use Python 3.11 or newer from [python.org/downloads](https://www.python.org/downloads/).
The release page is [Helix Engine v0.1.0 on GitHub](https://github.com/SuperHelix77/HelixEngine/releases/tag/v0.1.0),
and the pinned wheel is:

    https://github.com/SuperHelix77/HelixEngine/releases/download/v0.1.0/helixengine-0.1.0-py3-none-any.whl

Helix Engine installs into a dedicated per-user virtual environment. It does
not use `pip --user`, modify global site-packages, edit a Codex configuration,
or require administrator privileges. The installed runtime is standard
library based apart from certifi, which is used for verified TLS certificate
trust when the optional pricing refresh is requested.

## One-command online installation

On Linux or macOS, run the pinned installer directly from GitHub:

    curl -fsSL https://raw.githubusercontent.com/SuperHelix77/HelixEngine/v0.1.0/scripts/install.sh | bash

The script is pipe-safe and creates `~/.helixengine-venv`. It downloads the
pinned wheel through pip, resolves certifi online, and creates an executable
`Helix Engine.command` on `~/Desktop` on macOS or `Helix Engine.desktop` in
the directory returned by `xdg-user-dir DESKTOP` on Linux. If that command is
unavailable, it uses `~/Desktop`.

On Windows PowerShell, run:

    irm https://raw.githubusercontent.com/SuperHelix77/HelixEngine/v0.1.0/scripts/install.ps1 | iex

The script is safe through `Invoke-Expression`, uses
`%USERPROFILE%\.helixengine-venv`, and creates `Helix Engine.lnk` in the
actual Windows Desktop folder returned by `WScript.Shell`, including a
OneDrive Desktop location. The shortcut target is the venv's
`Scripts\python.exe` with `-m helixengine serve --port 8769 --open`.

The desktop command starts the local server as a foreground process. It does
not create a detached daemon or kill an occupied port. An existing Helix
server remains in place; an unrelated process using port 8769 is left alone.

## Manual Linux or macOS steps

Create the per-user environment, install the exact wheel, and use the
interpreter-qualified command so `PATH` is not required:

    python3 --version
    python3 -m venv "$HOME/.helixengine-venv"
    "$HOME/.helixengine-venv/bin/python" -m pip install --upgrade "https://github.com/SuperHelix77/HelixEngine/releases/download/v0.1.0/helixengine-0.1.0-py3-none-any.whl"
    "$HOME/.helixengine-venv/bin/python" -m helixengine --help

The full console path is `$HOME/.helixengine-venv/bin/helixengine`.

## Manual Windows steps

In PowerShell:

    py -3.11 --version
    py -3.11 -m venv "$env:USERPROFILE\.helixengine-venv"
    & "$env:USERPROFILE\.helixengine-venv\Scripts\python.exe" -m pip install --upgrade "https://github.com/SuperHelix77/HelixEngine/releases/download/v0.1.0/helixengine-0.1.0-py3-none-any.whl"
    & "$env:USERPROFILE\.helixengine-venv\Scripts\python.exe" -m helixengine --help

The full console path is `%USERPROFILE%\.helixengine-venv\Scripts\helixengine.exe`.

## Local and offline installation

Passing a wheel is an explicit local installation. It still permits pip to
resolve certifi online unless `--offline` is supplied:

    bash scripts/install.sh --wheel /path/to/helixengine-0.1.0-py3-none-any.whl

    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -WheelPath C:\path\to\helixengine-0.1.0-py3-none-any.whl

For offline operation, put the Helix Engine wheel and a compatible certifi
wheel in the same wheelhouse:

    bash scripts/install.sh --offline /path/to/wheelhouse/helixengine-0.1.0-py3-none-any.whl

    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -Offline -WheelPath C:\path\to\wheelhouse\helixengine-0.1.0-py3-none-any.whl

`--offline` passes `--no-index` and `--find-links` to pip. `--no-shortcut`
suppresses launcher creation. Set `HELIXENGINE_VENV` to choose another
per-user location and `PYTHON_BIN` to choose the interpreter used to create
the environment.

## Update

### Development v0.2: connect a Codex project

This command is in the development source, **not the published v0.1 wheel**.
After installing a development build on macOS/Linux, configure an explicit
project with the interpreter from the Helix environment:

    "$HOME/.helixengine-venv/bin/python" -m helixengine codex install --project "/path/to/project"

It merges one shared adapter into that project's `.codex/hooks.json` for
`PreToolUse`, `SubagentStart` and `SubagentStop`. Existing unrelated hooks and
configuration remain intact. Repeated installation is idempotent; changed
managed entries cause an error instead of being overwritten. An existing hook
file is backed up before modification.

Review the changed hooks using Codex's supported `/hooks` interface. A running
desktop session may need to be restarted before it loads them. Configuration
presence is not proof of activation: confirm attributed `CODEX_ROUTE` and
`CODEX_EXECUTED` events in the selected Engine data directory. The installer
does not write trusted hashes, change model settings, or grant permissions.
The [native hooks contract](https://learn.chatgpt.com/docs/hooks) governs review
and lifecycle behavior.

Use the same `--data-dir` when installing, inspecting or removing a custom-data
integration:

    "$HOME/.helixengine-venv/bin/python" -m helixengine --data-dir "$HOME/.helixengine" codex status --project "/path/to/project"
    "$HOME/.helixengine-venv/bin/python" -m helixengine --data-dir "$HOME/.helixengine" codex remove --project "/path/to/project"

Remove project hooks before uninstalling the package. Removal preserves other
hooks and retained Engine evidence. The existing Engine on/off switch controls
new routed commands without requiring hook removal.

Native Windows hook setup remains unqualified and is rejected explicitly;
Windows can still install the Engine and use explicit command routing. The
adapter currently admits tested foreground POSIX command forms. Interactive,
unsupported or ambiguous forms retain native execution. It does not suppress
model inference, replace final answers, or establish whole-session savings.

### Update the installed Engine

An update installs a newer local wheel into the existing dedicated venv and
refreshes a shortcut generated by Helix Engine:

    bash scripts/update.sh --wheel /path/to/new/helixengine-0.1.0-py3-none-any.whl

    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\update.ps1 -WheelPath C:\path\to\new\helixengine-0.1.0-py3-none-any.whl

The generated shortcut is replaced only when it still has the Helix marker on
Unix-like systems or still targets the Helix venv and arguments on Windows.
An existing user-edited shortcut is backed up before replacement.

## Uninstall

Uninstall removes the package and an owned desktop shortcut while preserving
the venv and data:

    bash scripts/uninstall.sh

    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\uninstall.ps1

The default data directory is `~/.helixengine` on Linux/macOS or
`%USERPROFILE%\.helixengine` on Windows. Receipts, telemetry, evidence
objects, and custom `--data-dir` locations are never deleted by uninstall.
Inspect and back up that data before removing it manually.
