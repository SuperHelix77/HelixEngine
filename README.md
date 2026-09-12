# Helix Engine

Start with the pinned [Helix Engine v0.1.0 GitHub release page](https://github.com/SuperHelix77/HelixEngine/releases/tag/v0.1.0). The wheel URL used by the one-command installers is:

    https://github.com/SuperHelix77/HelixEngine/releases/download/v0.1.0/helixengine-0.1.0-py3-none-any.whl

Helix Engine is a local Python application for explicit command routing,
lossless stdout and stderr retention, bounded projections, and public
evidence capsules. The local server is an observer with explicit control:
settings writes are available through the guarded settings operation, while
GET and event-stream reads do not mutate settings.

The runtime requires Python 3.11 or newer and has one runtime dependency:
certifi, at version 2024.2.2 or newer without an upper pin. The rest of the
runtime uses the Python standard library. Certifi supports certificate trust
for optional official pricing refreshes; command execution and local
evidence work offline after installation.

The CLI, local HTTP server, renderer, and routine telemetry do not invoke a
model. A user explicitly routes a command with the `run` subcommand. The
package does not claim automatic interception of arbitrary Codex activity or
pre-inference interception.

## Install from GitHub

Install Python 3.11 or newer from [python.org/downloads](https://www.python.org/downloads/).
The supported one-command installers create a dedicated per-user virtual
environment and a desktop shortcut. They do not install into global
site-packages, edit a Codex configuration, or require administrator access.
The default install is online so pip can resolve the pinned release and
certifi.

On Linux or macOS:

    curl -fsSL https://raw.githubusercontent.com/SuperHelix77/HelixEngine/v0.1.0/scripts/install.sh | bash

On Windows PowerShell:

    irm https://raw.githubusercontent.com/SuperHelix77/HelixEngine/v0.1.0/scripts/install.ps1 | iex

The installers use `~/.helixengine-venv` on Linux/macOS and
`%USERPROFILE%\.helixengine-venv` on Windows. They create `Helix Engine.command`
on the macOS Desktop, `Helix Engine.desktop` on the Linux Desktop, or
`Helix Engine.lnk` in the actual Windows Desktop folder, including OneDrive
Desktop locations.

For a step-by-step manual installation on Linux or macOS, first create the
same dedicated environment and then install the exact wheel URL:

    python3 --version
    python3 -m venv "$HOME/.helixengine-venv"
    "$HOME/.helixengine-venv/bin/python" -m pip install --upgrade "https://github.com/SuperHelix77/HelixEngine/releases/download/v0.1.0/helixengine-0.1.0-py3-none-any.whl"
    "$HOME/.helixengine-venv/bin/python" -m helixengine --help

For Windows PowerShell:

    py -3 --version
    py -3 -m venv "$env:USERPROFILE\.helixengine-venv"
    & "$env:USERPROFILE\.helixengine-venv\Scripts\python.exe" -m pip install --upgrade "https://github.com/SuperHelix77/HelixEngine/releases/download/v0.1.0/helixengine-0.1.0-py3-none-any.whl"
    & "$env:USERPROFILE\.helixengine-venv\Scripts\python.exe" -m helixengine --help

The full console paths are `$HOME/.helixengine-venv/bin/helixengine` and
`%USERPROFILE%\.helixengine-venv\Scripts\helixengine.exe`. Use the
interpreter-qualified `python -m helixengine` form when the console directory
is not on `PATH`.

For an explicit offline installation, download the Helix Engine wheel and a
compatible `certifi` wheel into one local wheelhouse. Then use the local
wheel with the no-index option:

    "$HOME/.helixengine-venv/bin/python" -m pip install --no-index --find-links /path/to/wheelhouse --upgrade /path/to/wheelhouse/helixengine-0.1.0-py3-none-any.whl

    & "$env:USERPROFILE\.helixengine-venv\Scripts\python.exe" -m pip install --no-index --find-links C:\path\to\wheelhouse --upgrade C:\path\to\wheelhouse\helixengine-0.1.0-py3-none-any.whl

The repository helpers accept an explicit local wheel and make the same
choice:

    bash scripts/install.sh --wheel /path/to/helixengine-0.1.0-py3-none-any.whl
    bash scripts/install.sh --offline /path/to/wheelhouse/helixengine-0.1.0-py3-none-any.whl

    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -WheelPath C:\path\to\helixengine-0.1.0-py3-none-any.whl
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -Offline -WheelPath C:\path\to\wheelhouse\helixengine-0.1.0-py3-none-any.whl

`--offline` is explicit and requires the certifi wheel in the same directory.
`--no-shortcut` suppresses desktop launcher creation. `HELIXENGINE_VENV`
selects another per-user environment and `PYTHON_BIN` selects the Python used
to create it.

## Update and uninstall

An update reuses the dedicated virtual environment, refreshes the package,
and refreshes the generated shortcut. On Linux/macOS:

    bash scripts/update.sh --wheel /path/to/new/helixengine-0.1.0-py3-none-any.whl

On Windows PowerShell:

    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\update.ps1 -WheelPath C:\path\to\new\helixengine-0.1.0-py3-none-any.whl

The update and uninstall helpers preserve the virtual environment and all
user data. The default data directory is `~/.helixengine` on Linux/macOS or
`%USERPROFILE%\.helixengine` on Windows. Uninstall removes the package and a
shortcut generated by Helix Engine when it still points to Helix Engine; it
does not remove a user-edited shortcut, the virtual environment, receipts,
telemetry, or evidence objects.

    bash scripts/uninstall.sh
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\uninstall.ps1

The equivalent direct uninstall commands remain interpreter-qualified:

    "$HOME/.helixengine-venv/bin/python" -m pip uninstall --yes helixengine
    & "$env:USERPROFILE\.helixengine-venv\Scripts\python.exe" -m pip uninstall --yes helixengine

## Launch and operate

The desktop launchers run the server in the foreground with:

    python -m helixengine serve --port 8769 --open

Use the full interpreter path when starting it from a terminal:

    "$HOME/.helixengine-venv/bin/python" -m helixengine serve --port 8769 --open
    & "$env:USERPROFILE\.helixengine-venv\Scripts\python.exe" -m helixengine serve --port 8769 --open

The launcher does not create a detached daemon or kill an occupied port. If
Helix already serves port 8769, keep that process and use its existing local
console. An unrelated process occupying the port is left untouched; choose a
different explicit `--port` for a separate foreground server.

The fixed application contract is documented in `API_CONTRACT.md`. The
complete ON/OFF switch, command routing, exact receipt retrieval, explicit
usage import, and doctor commands are in [docs/OPERATIONS.md](docs/OPERATIONS.md).
The optional manual Codex bridge is documented in
[integrations/codex/README.md](integrations/codex/README.md); it does not edit
production Codex configuration.

`run` manages one explicitly requested foreground process job. It is not a
detached daemon launcher. On POSIX, the managed foreground process group is
cleaned after parent observation so captured files can be finalized. On
Windows, the release does not claim a Job Object or process sandbox; cleanup
metadata is bounded observation, and unmanaged background descendants can
outlive the parent or keep output descriptors open. Detached sessions,
background writers, and daemons are outside the captured-stream guarantee.

## Explicit usage import

Helix cannot discover a provider's hidden context or billing counters. To
import native counters, create a JSON receipt from the provider or caller and
include every required field. The smallest valid JSON object is:

    {
      "model": "provider-model-id",
      "input_tokens": 0,
      "cached_input_tokens": 0,
      "cache_write_input_tokens": 0,
      "output_tokens": 0,
      "reasoning_output_tokens": 0
    }

Use measured nonnegative integers. Cached input plus cache-write input must be
no greater than input, and reasoning output must be no greater than output.
Unknown counters are not converted to zero; do not import until the provider
receipt supplies the required values. A `{"usage": {...}}` wrapper is also
accepted, and a top-level `model` is copied into that usage object.

After a routed command returns its run identifier, import the receipt with:

    "$HOME/.helixengine-venv/bin/python" -m helixengine --data-dir ~/.helixengine usage-import RUN_ID RECEIPT_JSON

The source JSON is retained and hash-bound. The import is explicit telemetry,
not automatic provider attestation, included quota, or total effective cost.

## Evidence and limits

ON applies to new routed commands. Active commands retain the setting bound
when they started. OFF preserves exact native stdout, stderr, and exit
status while observation remains active. If reduction fails, the command is
not rerun. Raw streams remain separate, and cross-stream ordering is
unknown.

Receipts preserve exact raw streams and hashes. Projections are typed,
bounded, and explicitly partial; retrieve the receipt when exact evidence is
needed. Fields that were not measured remain absent or null. Logical
application byte counts do not measure physical SSD traffic, metadata, cache
traffic, CPU, network traffic, or full effective cost.

With Engine ON, completed routed commands also index small historical receipt
references in the shared memory store, without copying or summarizing raw logs.
Use `helixengine memory status` to inspect backlog/gaps and
`helixengine memory sync --limit 16` for bounded recovery without command
execution. See [automatic receipt memory](docs/RECEIPT_MEMORY.md) for attribution,
failure behavior and the limits of this integration.

An attached native research session also follows discovered child usage receipts
through the same observer parser. See [parent and child accounting](docs/CHILD_USAGE.md)
for scope, native registry compatibility, deduplication and explicit coverage gaps.

Optional [visible-statement memory](docs/STATEMENT_MEMORY.md) preserves exact
assistant commentary/final messages from an explicitly attached research session
and its verified children. It requires a project opt-in and follows the Engine
switch. It does not capture reasoning or invoke a memory model.

The bundled `release_evidence` directory contains hash-bound public capsules
and their qualification limits. It is not a research ledger, provider
attestation, or proof of model-wide parity. This release only observes
commands explicitly routed through its boundary; it does not cover every
workflow or source-output path. No research ledger, private raw logs, or
developer-specific absolute paths are included in release artifacts.

## Pricing and privacy

Internet access is optional after installation and only supports the official
pricing refresh. If pricing is unavailable or stale, dollar estimates are
withheld. Pricing uses TLS certificate verification while preserving the
platform/default trust and environment behavior and adding the certifi bundle.
Never disable TLS verification. Update the certificate bundle in the Helix
Engine environment with:

    "$HOME/.helixengine-venv/bin/python" -m pip install --upgrade certifi
    & "$env:USERPROFILE\.helixengine-venv\Scripts\python.exe" -m pip install --upgrade certifi

Command arguments, working directories, receipts, and local state are private
operational data. Export is an explicit user action. Local HTTP requests are
restricted by the application contract and do not expose arbitrary command
execution or file reads. Settings writes require the contract's explicit
same-origin, host, CSRF, and revision checks.

See [docs/PRIVACY.md](docs/PRIVACY.md) and [docs/RECOVERY.md](docs/RECOVERY.md).

## Source and license status

The source is available for authorized publication. The source repository
currently has no selected license. This package makes no license grant and
does not assert third-party rights.
