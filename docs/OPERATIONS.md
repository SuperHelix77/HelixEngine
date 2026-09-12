# Operating the local application

The commands below follow `API_CONTRACT.md`. The global data-directory option
comes before the operation. If it is omitted, the application uses
`~/.helixengine` on Unix-like systems or the equivalent user-home directory
on Windows.

Use the interpreter-qualified form from the dedicated environment so the
operation does not depend on `PATH`:

    "$HOME/.helixengine-venv/bin/python" -m helixengine --help

On Windows PowerShell, the equivalent prefix is:

    & "$env:USERPROFILE\.helixengine-venv\Scripts\python.exe" -m helixengine --help

## Start the local server

Start the local observer with explicit control in the foreground:

    "$HOME/.helixengine-venv/bin/python" -m helixengine --data-dir PATH serve --port 8769

Request the browser to open after binding:

    "$HOME/.helixengine-venv/bin/python" -m helixengine --data-dir PATH serve --port 8769 --open

`serve` is a foreground process. It does not launch a detached daemon. The
server binds only to `127.0.0.1`; it does not expose arbitrary command
execution or arbitrary file reads. Routine rendering does not call a model.
The live state endpoint is `GET /api/release-state` and the event stream is
`GET /api/release-events`.

The local application is an observer with explicit control. `GET` requests
and event-stream reads do not mutate settings. `POST /api/settings` is the
explicit settings write and requires the contract's JSON body, exact same
origin, valid host, CSRF token, and current revision. A stale revision is
rejected instead of overwriting a newer setting.

If Helix already serves port 8769, leave that process running and use its
existing console. If another process occupies the port, the command reports
the bind failure without killing the occupant. Choose another explicit port
for a separate foreground server.

## Switch optimization routing

Inspect the current setting:

    "$HOME/.helixengine-venv/bin/python" -m helixengine --data-dir PATH status

Enable or disable routing for new commands:

    "$HOME/.helixengine-venv/bin/python" -m helixengine --data-dir PATH on
    "$HOME/.helixengine-venv/bin/python" -m helixengine --data-dir PATH off

Run the local integrity and storage checks:

    "$HOME/.helixengine-venv/bin/python" -m helixengine --data-dir PATH doctor

The switch applies to new routed commands. Active commands retain their
bound setting. OFF preserves exact native stdout, stderr, and exit status;
observation remains active.

## Route a command

The explicit command boundary is:

    "$HOME/.helixengine-venv/bin/python" -m helixengine --data-dir PATH run --kind generic --cwd PATH --timeout 60 -- COMMAND ARG...

The kind may be `generic`, `pytest`, or `compiler`. The command and arguments
are stored as operational metadata. A command failure is retained as
evidence. The reducer does not rerun a command when reduction fails.

`run` manages one explicitly requested foreground process job. It does not
launch detached daemons, background writers, or interactive terminal jobs.
On POSIX, the managed process group receives forced cleanup after parent
observation so the captured files can be finalized. On Windows, the release
does not claim a Job Object or process sandbox. Cleanup metadata is bounded
observation, and unmanaged background descendants may outlive the parent or
keep output descriptors open. Detached sessions and unmanaged descendants are
outside the complete captured-stream guarantee.

The result contains a receipt identifier. The receipt records separate
stdout and stderr objects, hashes, byte counts, exit status, timing, and the
limits that apply. Cross-stream ordering is unknown.

## Retrieve exact evidence

Retrieve a complete stream:

    "$HOME/.helixengine-venv/bin/python" -m helixengine --data-dir PATH retrieve RECEIPT --stream stdout

Retrieve a 1-based inclusive line range:

    "$HOME/.helixengine-venv/bin/python" -m helixengine --data-dir PATH retrieve RECEIPT --stream stderr --start 1 --end 40

The raw source is verified by hash before retrieval. Text is returned as
text; non-UTF-8 bytes are returned as base64. The projection is not the
source of truth. Keep the receipt and the returned hashes with any downstream
review.

## Import usage counters explicitly

Helix cannot see a provider's hidden context or billing counters. Obtain a
provider or caller receipt and include all required native counters. The
smallest valid JSON file is:

    {
      "model": "provider-model-id",
      "input_tokens": 0,
      "cached_input_tokens": 0,
      "cache_write_input_tokens": 0,
      "output_tokens": 0,
      "reasoning_output_tokens": 0
    }

Every field is required: `model` is a nonempty string and each counter is a
nonnegative integer. Cached input plus cache-write input cannot exceed input;
reasoning output cannot exceed output. Unknown counters remain unknown and
must not be replaced with zero. A `{"usage": {...}}` wrapper is accepted;
the model may also be supplied at the top level.

First run an explicitly routed command and retain its returned `run.id` (or
the `run` object from `run --json`). Then import the receipt:

    "$HOME/.helixengine-venv/bin/python" -m helixengine --data-dir PATH usage-import RUN_ID RECEIPT_JSON

The source JSON is retained and bound to its SHA-256. This is explicit
imported telemetry, not automatic provider attestation. It does not establish
included quota, billing, or total effective cost.

## Pricing and internet use

The pricing refresh is optional. When requested, it uses the official pricing
source with TLS verification. The certificate context preserves
platform/default trust and environment behavior while adding the certifi
bundle. If the source is unreachable, the certificate is invalid, or data is
stale, dollar estimates are suppressed. Never disable certificate
verification.

Update certifi in the selected environment:

    "$HOME/.helixengine-venv/bin/python" -m pip install --upgrade certifi

On Windows PowerShell:

    & "$env:USERPROFILE\.helixengine-venv\Scripts\python.exe" -m pip install --upgrade certifi

All command routing, receipt retrieval, switching, and local observation
continue offline after installation.
