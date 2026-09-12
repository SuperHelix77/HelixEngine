# Bound recording artifacts — development contract

The previous native recording pilot did not suppress any observation turns.
Native skill hydration changed the context after activation, so continuity
correctly rejected reuse. Separately, the model promised `observations.jsonl`;
capturing observations in Memory alone would not fulfill that artifact promise.
Neither failure licenses weakening continuity or final-answer requirements.

## Decision boundary

Helix can perform a transition only when a trusted caller has already declared
the operation, its authority, current dependencies, and absence of unresolved
semantic obligations. A matching envelope does not infer that declaration.
This is an explicit narrow contract, not an automatic general-purpose semantic
classifier. Normal requests, changed context/dependencies, unknown obligations,
or uncertain completion retain the model path.

Recording grants may additionally bind:

```json
{
  "materialization": {
    "path": "/absolute/project/observations.jsonl",
    "initial_sha256": "<CAS hash of exact existing bytes>",
    "initial_bytes": 0,
    "format": "exact-prompt-append-v1",
    "write_authority": "exclusive"
  }
}
```

The caller must actually possess exclusive write authority and select the file
and byte format. No filename or permission is extracted from model prose.
The file must already exist inside the project. Arming verifies its exact
initial contents; the target cannot also be an invariant dependency file.
This format appends the original UTF-8 prompt followed by one LF. It does not
canonicalize JSON or guarantee one physical line for multiline prompts.

## Completion and recovery

1. Validate current native identity, authentic transcript continuity, grant,
   captured prompt, sequence, and declared dependencies.
2. Commit the bounded recording to the existing exact-evidence ledger.
3. Reconstruct the expected artifact from its initial CAS bytes and verified
   recorded prompts. Publish only the expected byte transition, with exact
   readback and a receipt. Already matching bytes need no second append.
4. Revalidate declared dependencies. Publish the controller completion/outbox
   and release its fence only if the active grant and settings still match.
5. Only then return a suppression response.

The filesystem and two databases are **not one atomic transaction**. A failure
can leave a new file with an unpublished completion. The binding is quarantined,
the model path stays available, and a fixed recovery notice warns against
blindly repeating effects. Historical data remains evidence, not developer
instructions. No uncertain state is silently reset or retried.

File publication assumes cooperative/exclusive writer ownership; it is not a
security boundary against arbitrary writers ignoring locks. Unsupported
publication/durability primitives fail closed. Ordinary Engine functionality
and capture-only operation remain available on those platforms.

## Accounting and remaining gates

This deliberately reuses the existing verified history rather than creating a
second memory ledger. Full history reconstruction and file readback have bounded
but nonzero I/O and latency costs. Artifact receipt counters describe that local
operation, not complete filesystem/SQLite traffic or native model usage.

The independent capability preflight showed that the installed client can load
its plugin/skill inventory without starting a model turn. It did not establish
stable future context or automatic desktop startup readiness. Any later context
change must still invalidate the recording lease.

Before another native run: verify the artifact path offline, review failure and
restart behavior, prepare capabilities before the initial semantic turn, freeze
new caller/package bindings and a preregistration, and stop immediately on the
first unexpected route. The previous unpaired attempt and its costs remain
retained. No parity or savings claim follows from these offline tests.

## Verification

OBSERVED: 424 source tests passed locally, including 14 file-publication tests
and 12 real-core/controller integration cases. Independent review found a
replay-durability gap: matching bytes bypassed target-file fsync. A controller
test reproduced false suppression before the fix and passed afterward. Replay
now syncs the bound target and revalidates its identity, bytes, and parent.
Fault injection is not a physical power-loss certification.

OBSERVED: the freshly built wheel also passed all 424 tests from outside the
checkout, with the installed console entry point verified. Wheel SHA-256:
`ea8d857238b50939abc099ec97688c6e4a55ff69a72233b86a1b3c494fe73ca6`.
The first isolated-environment check stopped before tests because a deliberately
dependency-free installation lacked `certifi`; installing declared runtime and
test dependencies resolved that setup failure. Both local attempt logs remain
retained. No native benchmark was run for this change.

The earlier CI failure was a Windows installed-suite timeout. Its 2,049-row
recovery-limit fixture now uses one explicit SQLite transaction instead of
thousands of repeated initialization/commit cycles. The rejection assertion
and production integrity behavior remain unchanged. Cross-platform CI must
still verify this repair; local results do not establish Windows performance.
