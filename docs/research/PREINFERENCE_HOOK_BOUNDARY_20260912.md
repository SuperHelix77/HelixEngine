# Installed pre-inference hook boundary, 2026-09-12

**OBSERVED:** the installed Codex CLI can stop a user-turn submission before the model endpoint receives a request. This resolves a concrete integration uncertainty; it does not establish a general semantic classifier, production acknowledgement delivery, model capability parity, or native token savings. No hosted model was called.

## Current source and method

[Official hook documentation](https://learn.chatgpt.com/docs/hooks) describes UserPromptSubmit context and stopping responses. The inspected client was Codex 0.153.4. Local tests used a loopback SSE endpoint, separate HOME/CODEX_HOME per case, no authentication file or provider credentials, an isolated Git directory, unchanged production settings, and an explicitly reviewed local hook. The automation hook-trust flag was limited to those test invocations; sandbox and approval modes were not broadened.

| Hook result | Mock endpoint requests | Hook ran | CLI exit |
|---|---:|---|---:|
| Passthrough | 1 | yes | 0 |
| Fixed context only | 1 | yes | 0 |
| Block decision | 0 | yes | 0 |
| Continue false | 0 | yes | 0 |

The fixed context marker appeared in the serialized request. Stopping is therefore distinct from adding context: the former prevented the request; the latter did not. All test configurations remained byte-identical across execution.

A second test reused one actual native CLI thread across three separate processes. Endpoint calls were 1, 0, 1 for semantic sentinel, exact resolved sentinel, and subsequent semantic sentinel. The thread identity survived, and normal mock completion resumed. The hook was a literal sentinel match, not a claim to understand arbitrary user intent.

## Limits that affect production

1. **OBSERVED:** neither stopping form exposed the supplied stop text as a normal message in CLI JSON. This does not establish the desktop renderer's behavior. Suppressing a call without durable, visible completion delivery is not workflow parity.
2. **OBSERVED:** the stopped prompt was absent from the later serialized request. The test hook saved its input separately; Codex history alone is not sufficient exact recovery. Production must persist the original event before deciding to suppress inference.
3. **UNKNOWN:** direct desktop-window acknowledgement and parent/child coverage at this boundary. The tested path was the installed CLI.
4. **UNKNOWN:** economic savings with a real model, durable transition state, UI delivery and recovery overhead. Zero mock calls is a protocol result, not measured intelligence parity or included-plan quota saving.

## Smallest justified next slice

**HYPOTHESIS:** connect the shared Engine adapter to a caller-authorized, version-bound transition ledger through UserPromptSubmit. The model still handles every unresolved semantic event. Engine may suppress inference only for an exact event already covered by a current committed workflow, with all semantic obligations resolved and an explicit completion-delivery path.

Required inputs are workflow/thread/context-epoch identity, expected prior root, event identity and exact bytes, procedure/policy version, dependency bindings and the expected deterministic result. A text resemblance to ACK, a past successful receipt or a self-asserted PASS is insufficient authority. No arbitrary archived instruction becomes a new developer instruction.

Order: validate authority and bindings; preserve exact event; commit an idempotent deterministic transition and completion outbox; confirm the supported delivery boundary; then suppress the redundant request. An unknown or semantically unresolved event reaches the model. A stale/conflicting binding invalidates reuse; a storage or delivery failure must expose the unresolved state and must not silently lose the prompt or repeat an effect. Recovery must distinguish committed effects from unexecuted mechanics.

Before a native benchmark, falsify duplicate delivery, altered payload under reused identity, stale prior root, changed policy/dependency, crash before/after commit, missing acknowledgement, and the next semantic turn. Include a late-relevance query that requires exact retrieval of a previously suppressed event. Do not install a live suppressing hook from this protocol result alone.

## Rejected primary output attack

On the frozen installed Astra maintenance trace, total candidate output was 1,782 tokens and the additional-probe segment used 1,119. Even deleting that entire segment at zero cost leaves 663 tokens: only 54.37% saving against the 1,453-token native control. This deliberately generous fixed-trajectory bound does not justify a probe-helper-only route to 65%. Model-selected assertions and test fixtures cannot be discarded as scaffolding. A helper may still have bounded secondary value after its admission cost is measured.

The research worker's written report double-counted reasoning as additional to output. The adjudicated calculation above uses native output exactly once; reasoning is a reported subset. No inference was launched to retest that arithmetic.

## Evidence identities

- `probe.py`: `f20aa49929f3b8ad62e69bd11d9a938907393e0960c57dfa9769cdf7eaec4157`
- `RESULTS.json`: `a4cfa241af3d9fcb169320aaa53600e5d9435cebc7860eb394dd02f5b1b850cc`
- `continuation.py`: `d8c6ca119ae08939ce6d52e49578f47be1428b4db09b0b24b233dead66e19053`
- `continuation/RESULT.json`: `992df5218b05e067512dc77c1e2d37429e00a0657a17aa8d6058620d8e33fbb5`
- Codex binary SHA256: `87a08119b8effa519f0ecb552dc98043f58a8200bf2ec5da60f76890c33e9c3a`

Raw mock requests, CLI events and hook inputs remain in the private research directory. They are not shipped as release history.


## App-server transport and shared capture follow-up

**OBSERVED:** a separate auth-free native app-server stop probe delivered the
stop marker in live `hook/completed` warning/stop entries, with zero endpoint
requests. It did not persist that marker in `thread/read`. This narrows the
CLI-only uncertainty: live transport is available, but durable client delivery
and desktop rendering are still not verified. The reviewed local fixture was
trusted using `hooks/list` identities and the native configuration API in an
isolated Codex home; production trust settings remained untouched.

**OBSERVED:** the shared capture-only adapter then archived one actual native
submission while allowing exactly one mock endpoint request. The original
60-byte Unicode/whitespace prompt was present in the serialized request and
recovered byte-exactly from existing Memory by a fresh process. Capture supplies
no context and no block response. The archive stores the prompt once within its
structured source object; no redundant base64 copy is needed for exact UTF-8
recovery. These checks spent no hosted inference.

**CONDITIONAL:** capture is a prerequisite for a safe transition gate, not its
implementation. Explicit semantic authority, bound state, completion outbox,
duplicate/crash handling and confirmed delivery remain necessary before any
installed suppression policy can be qualified. No savings or capability claim
is promoted by this follow-up.

Follow-up evidence hashes:
- `appserver_delivery.py`: `8f6892c615355d1d7444d89a2e8fe9f1e5f351e0f302cacb49c4647732d7fb57`
- `appserver-delivery/RESULT.json`: `c5a7e4d1d4d2d0273fe5297d00cace56d03aae3a3d1326390b76434626a5d7b6`
- `appserver_capture.py`: `5d5394d0f75c6c9a9d4b2eeb8e1f420aa1445073abafd9a2ae8c4fcd3da04580`
- `appserver-capture/RESULT.json`: `0bc40791e3e9cdd2312847f2041b0925b32956e9367e556076bfc47da85f3eb0`
