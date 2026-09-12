# Optional project source context (development)

This unreleased option prepares a small, explicitly selected set of project
files through the existing Codex hook. It is off by default. It is not yet
qualified for native token savings or general capability parity.

After installing and reviewing the shared hook with the normal Codex trust
flow, select the files you want captured for this project:

```sh
helixengine codex install --project /path/to/project
helixengine codex source set --project /path/to/project solution.py test_solution.py settings.json
helixengine codex source status --project /path/to/project
```

Use the same `--data-dir` for setup and these commands if you selected a
nondefault Engine directory. Configuration is project-scoped and persists until
cleared. Keep that data directory outside the selected project. Configuring it
does not approve a hook, turn Engine on, or change any
model settings. Normal native hook trust remains required.

Managed native hook installation is currently qualified on POSIX only. Core
source-preparation tests on Windows do not establish a working Windows Codex
hook integration.

For ordinary user submissions and child startup, an enabled shared hook can
capture the configured files and offer quoted source evidence before inference.
Existing recording/recovery responses take priority. The source text is data;
comments or strings inside a file do not become instructions or approvals.
The model retains its ordinary tools, semantic decisions and final answer.

Only explicitly configured relative file paths are read. There is no recursive
repository scan, prompt-based file selection, memory summarizer or extra model
invocation. Captured bytes remain available in Engine's existing exact evidence
store. Each source object includes a recovery path and hash.

The packet has a bounded size. Missing, binary, oversized, unsafe or
changed-during-read input causes the whole optional packet to be withheld; the
ordinary native task remains available. Files are snapshots at capture time,
not a lock on future edits or proof of semantic correctness. A configuration
may need updating after a project is reorganized.

To stop source preparation while keeping Engine enabled:

```sh
helixengine codex source clear --project /path/to/project
```

The global Engine off switch also prevents this source preparation. Clearing
the configuration does not delete previously archived evidence.

Telemetry distinguishes a packet **offered by the hook** from bytes proven to
have reached an actual model request. File reads, archive work and packet size
are overhead, not savings. A smaller or earlier packet only saves model usage
if it displaces other paid work; any needed rereads and recovery must be counted.
