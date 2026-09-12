# Data privacy and telemetry limits

Helix Engine is a local application and observer with explicit control. Command arguments, working directories,
environment labels supplied by the caller, receipt identifiers, stdout,
stderr, hashes, timing, local state, and imported usage records are
operational data in the configured data directory.

The development Codex adapter can also capture bounded incoming user prompts
through its explicitly installed `UserPromptSubmit` hook. Exact prompt text is
kept in local Memory, while telemetry carries references and status. Capture alone
does not inject historical text or suppress inference. A separately armed
[recording grant](TRANSITION_GATE.md) can produce a mechanical stop notification
after its bound transition commits. See
[prompt capture](PROMPT_MEMORY.md) for limits and failure behavior.

The application does not send those records to a remote service as part of
local routing. Pricing is the one optional internet operation. It reads an
official pricing document only when a refresh is requested or due. The TLS
context preserves platform/default trust and environment behavior while
adding the certifi bundle. Pricing responses are parsed locally; certificate
verification remains enabled.

The HTTP interface binds to 127.0.0.1 and applies the contract's origin,
host, CSRF, body-size, and method checks for the explicit settings write. It
does not offer arbitrary command execution or arbitrary file reads. GET and
event-stream requests do not mutate settings.

Telemetry is bounded. Run rows expose observed command identity, state,
timestamps, separate stream byte counts, receipt paths, and reducer status
where measured. Missing values stay null or absent. Application logical
object and staging byte counts do not measure physical SSD traffic,
filesystem metadata, cache traffic, CPU, network traffic, or total cost.
Cross-stream ordering is not recorded.

Export is an explicit user action. Public evidence capsules are
hash-bound, read-only data with retained rejected outcomes and
qualification limits. They are not provider attestations, a research
ledger, or proof of model-wide parity. The package does not claim automatic
Codex interception or pre-inference interception. Only commands explicitly
routed through the Engine boundary are observed; the release does not cover
every workflow or source-output path.

The `run` operation manages a foreground process job. It is not a detached
daemon launcher. POSIX managed process groups receive cleanup after parent
observation. Windows is not a Job Object process sandbox, and unmanaged
background descendants may outlive the parent or keep output descriptors
open; captured streams are not guaranteed complete for those descendants.
