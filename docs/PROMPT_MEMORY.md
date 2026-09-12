# Native prompt capture (development)

The shared Codex adapter now accepts `UserPromptSubmit` alongside its command
and child lifecycle events. Setup adds the event to the same managed hook;
existing three-event installations can be upgraded without duplicating their
groups. Native trust review and reload remain required. Setup does not alter
trust records or production model configuration.

When Engine is ON, a valid native submission of at most 64 KiB of UTF-8 is
stored in the existing project-scoped Memory/Store. The exact text, thread and
turn identities, byte count and hash are retained in one structured object.
Telemetry contains references and capture status, not the prompt text.
Root/child attribution follows native session and agent identities. Project
scope is logical filtering, not an access-control guarantee.

The hook returns no context and no stopping instruction. Native inference
continues normally. This is capture, not a semantic-transition gate or a token
saving mechanism. Archived user text is historical evidence, not a new source
of execution authority. It is never evaluated or promoted into instructions.

An identical native identity and payload is idempotent. Conflicting payloads,
missing identities, invalid encoding, oversized input and storage failures
cannot produce a successful capture receipt. The original native submission
continues; incomplete capture must not qualify that event for future inference
suppression. With Engine OFF, no prompt evidence is captured.

Exact retrieval uses the ordinary Memory record hash and project scope. It
does not depend on the model thread remaining alive. Records are local and
may contain sensitive user text; the configured data directory is part of the
user's local data custody boundary.

Validation: unit tests cover recovery, identity conflicts, idempotency,
Unicode/whitespace, child attribution, size limits and storage failure. An
auth-free installed Codex 0.153.4 app-server probe submitted a 60-byte prompt
through the actual adapter: one mock endpoint request, one capture, original
prompt present in the request, exact recovery by a fresh process. No hosted
model ran. Desktop rendering, semantic parity and economic savings are not
established by that probe.
