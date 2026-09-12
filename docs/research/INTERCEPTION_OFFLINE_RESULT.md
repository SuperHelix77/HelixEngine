# Installed Codex command rewrite: bounded offline result

The corrected probe on 2026-09-12 used `/Applications/ChatGPT.app/Contents/Resources/codex`, version 0.153.4, with an isolated Codex home and a local deterministic mock provider. The exact hook was reviewed and trusted using the supported `/hooks` UI. No trust record was forged and production config was not changed.

Observed: two mock requests, one PreToolUse/Bash event, one completed rewritten command, exit zero, preserved cwd/environment marker, original marker absent, and rewritten output in the next model-facing request. Decoding the native shell-escaped command display recovers the exact rewritten shell source. The initial raw substring assertion failed because it compared unescaped source to escaped display; offline adjudication resolves this without another execution.

The earlier probe was rejected: its mock repeatedly emitted the same tool call, producing 946 local requests before timeout while the untrusted hook never ran. Those attempts remain in the private research evidence. The corrected mock ends on request two and rejects a third.

This establishes a bounded parent CLI interception mechanism. It does not establish live desktop attachment, subagent interception, net token savings, capability parity or v0.2 release readiness. Next: one shared adapter and backend router, tested against actual desktop and child call receipts. All normal semantic/model execution remains available.

Native protocol contract: https://learn.chatgpt.com/docs/hooks

Permission caveat: the launch requested workspace-write / approvals never, but the emitted hook payload reports bypassPermissions. This probe does not establish restrictive-sandbox equivalence; that cell remains UNKNOWN. No permission configuration was changed to make the hook run.

## Compact delivery pair (2026-09-12)

OBSERVED, bounded installed-CLI/loopback component test: native next-request tool-output representation was 17,547 bytes; Helix was 2,448 bytes (86.05% reduction). Each arm completed one native command and two mock provider requests. Helix captured 54,000 exact stdout bytes and delivered a 1,766-byte packet. Independent nested request decoding matched the packet byte-for-byte exactly once. No hosted inference ran. Native token economics, semantic sufficiency, desktop coverage and child coverage do not follow from these bytes.

The original candidate failed to open its outside-workspace SQLite store under the native sandbox. It did not execute the requested command. The corrected component run used a workspace-local store; preparation failure now falls back to the original command under existing permissions. No permission expansion is installed.

Subsequent independent review found shell-comment parsing and post-execution publication failures. Comments now remain native. Archive/receipt/telemetry/packet failure injection preserves command status/output with exactly one execution. Packet failure emits raw captured bytes; missing publication is explicitly recorded/reported. The adapter preserves non-command hook input fields and handles SIGTERM through foreground capture cleanup. Native job-control/cancellation parity remains a separate gate.

The review's suggested removal of `permissionDecision: allow` was rejected: the official native hook protocol requires that field alongside `updatedInput`. This syntactic requirement does not establish approval parity. No PermissionRequest hook or escalation bypass is installed; approval behavior outside the tested policy remains unqualified.

Source: [OpenAI hook protocol](https://learn.chatgpt.com/docs/hooks). Private exact wire receipts remain in the local research fixture, not in the public package.

## Native child boundary

OBSERVED: the installed Codex CLI spawned one real child through its native collaboration tool against the loopback provider. Parent and child made two mock requests each; one child command executed through the same adapter. `SubagentStart`, `PreToolUse`, Engine execution and `SubagentStop` were captured. The child's next serialized request contained the exact 1,765-byte packet once; the 54,000-byte original was recovered exactly. No hosted model ran.

The first child probe stopped before command execution because its mock classifier relied on parent-style role prose absent in the child's request. The corrected classifier was tested against all captured requests offline and then used native request metadata. The failed attempt remains retained and charged as local test overhead.

Crucial attribution finding: child hook `session_id` names the **parent**, while `agent_id` names the **child**. Both match native request metadata. The adapter now normalizes `thread_id = agent_id or session_id`; adding parent and child counters by `session_id` alone would be wrong. This is native lineage/delivery evidence, not whole-tree usage reconciliation or desktop-session attachment.

Validation after publication-failure fixes: 30 targeted runtime, CLI, observer, server and interception checks passed. Full capability, native token savings, OS coverage, restricted approval behavior and desktop hot-reload remain unqualified. The isolated CLI trust review was performed through supported `/hooks`; no production configuration or trusted hash was forged.

## Current desktop activation gate

The project hook has been installed through supported native trust review, scoped to the current Helix parent session and native children only. Existing continuity/peer hooks and the release server were preserved. A subsequent ordinary `rg --count` in the already-running desktop turn produced no `CODEX_ROUTE` or `CODEX_EXECUTED` record. Therefore configuration/trust is demonstrated; **current desktop interception remains NOT OBSERVED**. Do not treat an isolated CLI receipt as a receipt from the live chat. The next resumed turn must repeat one minimal command and inspect exact origin attribution before claiming activation. No model-lane optimization or v0.2 promotion proceeds on assumed coverage.

The adapter now stays in the native POSIX process group; the standalone Engine retains its own default managed-group behavior. A subprocess integration check established unchanged stdin, environment value, cwd and the native caller process-group ID. This avoids isolating a command beyond Codex's group cancellation. Native cancellation/approval parity over all host variants is still not certified.

## Further attacks, ordered by evidence

| Priority | Mechanism | What must be measured before promotion |
|---|---|---|
| P0 | Compact delivery | Exact next-request bytes; passes scoped parent and child CLI probes |
| P1 | Parent/child coverage | Native lineage, child command receipts, per-thread usage deduplication; CLI lineage passes, live desktop coverage pending |
| P2 | Compact deterministic operations | Model-generated mechanics removed without suppressing novel probes or ordinary final answers; charge setup and interface overhead |
| P3 | Dependency-bound reuse | One authorized operation identity, complete relevant bindings, invalidation and replay; never cache arbitrary shell effects |
| P4 | Evidence on demand | Exact retrieval is already available; measure recovery turns and total bytes against actual native exposure |

The future semantic probe interface remains a hypothesis. No arbitrary result cache, new plan API, model restriction or semantic-call suppression was added during this delivery repair.
