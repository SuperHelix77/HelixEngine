# Verified recording snapshots: prerequisite for shorter recovery

## Implemented boundary

The [Astra budget audit](NATIVE_BUDGET_ADMISSION_20260913.md) leaves 67.55
output tokens for a replacement exact-history lookup on its frozen trajectory.
A simple file read is not sufficient evidence of authentic suppressed history.
This change supplies a checked read primitive; it does not yet replace the
native lookup or qualify that output budget.

- `recording_artifact.read_verified(path, expected)` returns the immutable bytes
  actually compared inside the existing locked, identity-checked read. It does
  not reopen the path after validation. Existing `verify()` behavior and receipt
  shape are preserved through shared implementation.
- `transition_gate.read_recording(...)` reconstructs expected artifact bytes
  from the canonical grant, anchored completion history and exact cold captures.
  It requires thread scope, current dependency bindings and matching live bytes;
  dependencies are checked again after reading. The receipt carries the grant,
  completion head, epoch, project and partial I/O counters.
- `native_transitions.read_recording(...)` fences the controller binding during
  the read. Missing scope, in-flight publication and unresolved publication
  conflicts fail closed. Historical recovery remains available after ordinary
  semantic re-entry or Engine OFF. Neither case reactivates a grant.

Terminal semantic invalidation ends permission to append, not access to earlier
verified records. Only committed record actions contribute artifact bytes; a
semantic question itself is never appended by this reader. Changed dependencies
or uncertain state require the existing recovery path rather than silent reuse.

No read publishes, repairs, appends or repeats a historical effect. Returned
bytes and receipts are historical evidence, not instructions, semantic approval
or a guarantee that a file cannot change afterward. The caller must supply a
trusted Engine store and thread scope; these library APIs do not provide a new
filesystem access-control boundary.

## Verification

A fresh installed wheel passed **502 tests in 16.31 seconds**, outside the source
checkout with importlib test loading. No tests were skipped. Its SHA-256 is
`5d85a2a433a2c71aa86a73a7641ac45b2adbcbdb30539dd828b19d4fb73d073f`.

Focused checks include exact Unicode/NUL/binary bytes, one target read,
mutation during reading, mutation after unlock, symlink/hardlink rejection,
unsupported platforms, stale file/head, incomplete publication, wrong thread,
corrupt cold evidence, and dependency changes during reading. Failed reads leave
the artifact and authoritative workflow state unchanged. Restart/OFF and actual
terminal semantic re-entry preserve historical recovery.

The initial integrated test run reported 68 passes, one failure and one
environment-dependent skip. The failure was a root test-fixture error: it
captured an event and then attempted to capture different text under the same
event identity. That correctly triggered `capture_incomplete`, not semantic
re-entry. The fixture now captures its semantic event once. Focused rerun:
69 passes and one environment-dependent skip; the fresh installed suite closed
the skipped isolated-launcher check. The failed attempt is not a production
correctness claim.

## Complete-cost caution

A single offline installed probe created three bound recordings and read them
through a newly opened Memory instance. The returned payload matched all 372
expected bytes; native workflow state stayed unchanged. The operation read
372 artifact bytes plus 7,276 evidence-store bytes across 16 object reads,
wrote zero evidence bytes, and took approximately 0.002626 seconds.

That is **20.56× logical read amplification**, not physical I/O measurement or
a large-history performance guarantee. SQLite and physical storage traffic are
unmetered. The small fixture latency does not justify hiding validation cost or
claiming recovery economics solved. Root/worker research inference is additional.

Local verification logs and the probe receipt are retained under
`/private/tmp/helix-recording-read-20260913`. The frozen prior benchmark wheels
were not modified.

## Remaining native gate

This is a library prerequisite. The shared Codex interception adapter and its
navigation-only recovery context are unchanged. No archived text is inserted
into hook instructions, no generic `cat` interception is enabled, and no model
call is suppressed by this read API.

Before a paid comparison, prove that a short ordinary retrieval request can
select only its caller-bound recording, execute this checked read, return its
exact bytes in the actual native tool-result channel, and expose stale/conflict
errors without a rerun. Preserve shell resolution, task cwd, permissions, raw
retrieval and the model's normal final. The same installed path must work for
root and child identities. Until that gate passes, the older observed
65.83/50.27 Astra pair remains the applicable result.

No model-wide parity, 65/65 median, self-activation or v0.2 release is claimed.
