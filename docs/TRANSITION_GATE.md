# Bounded recording transitions (development)

Helix can decide that a model call is unnecessary when the next action follows
mechanically from an explicitly armed recording contract. It does not decide
that arbitrary prose is unimportant, or infer permission from words like ACK.

The current action is **record exact data and issue a mechanical notification**.
It performs no shell commands, edits, approvals or semantic decisions. Ordinary
model-written final answers remain on the native path.

## Admission contract

An explicit caller arms a grant bound to a project, native thread, epoch,
authorization evidence and declared file dependencies. The grant requires an
explicit empty list of unresolved obligations. This declaration must represent
the actual user-authorized workflow; an empty list and an evidence hash are not
proof that the caller interpreted the task correctly.

Two exclusive modes are supported: exact expected steps, or a recording lease
for previously unknown observations. A lease accepts only a strict JSON envelope
with `schema: "helix.observation.v1"`, the current `epoch`, the next integer
`sequence`, and a string `payload`. The envelope is a data-ingestion protocol.
Instructions quoted inside payload remain historical data. Ordinary requests,
extra fields, duplicate keys, wrong sequence or changed epoch cannot silently
be classified as observations.

Exact native capture must succeed before transition acceptance. Grants and
records use the existing evidence store and completion chain. Identical native
delivery can replay; conflicting bytes cannot. A new semantic prompt invalidates
the lease. Historical records, dependency hashes and the externally retained
completion head are checked before accepting subsequent data.

## Native binding

`helixengine transition arm grant.json` stores a grant without activating a
native hook. Explicit `--activate-native --transcript PATH` also binds the
shared hook to a completed native semantic-turn checkpoint. `transition status
THREAD_ID` inspects the binding; `transition deactivate THREAD_ID` removes its
eligibility. Hook setup/trust is a separate prerequisite. None of these commands
changes a model's reasoning effort or installs a second interception pattern.

The native checker requires the unchanged transcript prefix and the observed
stopped-turn sequence through the current turn's start/context fence. Missing
hook work, compaction, changed model/instructions/context, prefix mutation or
rollback cannot silently preserve eligibility. An ON/OFF settings revision also
invalidates the binding. Missing proof expands to native inference.

Completion records and external heads are durable; a notification being prepared
or returned is not proof that a desktop client displayed or acknowledged it.
An uncertain cross-database commit must be quarantined rather than silently
resetting a head or repeating execution. The local owner remains part of the
trust boundary; this is not protection against coherent rewriting of all
trusted state by a hostile host.

## Costs and qualification

The current limits are 256 events and a 4 MiB native transcript snapshot. Exact
capture accepts at most 64 KiB of UTF-8 prompt, including envelope overhead.
Full-prefix and prior-record validation may repeat reads; these costs must be
included rather than described as constant-time operation. The gate is a bounded
development implementation, not a general-purpose semantic classifier.

Offline hostile tests and auth-free native protocol probes precede hosted
benchmarks. They cannot establish model intelligence parity, full desktop
coverage, seven-task median savings or included-plan quota ratios. A candidate
must still pass the normal-answer capability and economic gates before release.
