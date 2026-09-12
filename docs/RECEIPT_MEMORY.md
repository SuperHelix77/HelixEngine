# Automatic receipt memory

With Engine ON, completed routed commands now add small historical observations
to the existing memory index. This uses the same evidence store as output
reduction. Raw stdout/stderr are captured once; memory stores references to that
receipt, bounded command metadata, exit status and known producer identities.
Failed commands are evidence too. OFF retains command observation and exact raw
delivery but does not automatically index those executions.

No model is invoked to index a receipt. There is no additional summarization
agent, automatic command reuse or context injection in this component. It does
not establish RTK/Claude-Mem feature parity or model-token savings.

Inspect indexing and recover a bounded backlog:

```sh
helixengine memory status
helixengine memory sync --limit 16
```

Both use the selected `--data-dir`. Sync consumes at most 64 completed events
per call and never executes commands. The normal completion path consumes up to
16. Identical replay is idempotent. A crash after the memory commit but before
the cursor commit replays the record safely. Missing/corrupt receipts and
conflicting records stop ingestion at that event; the durable status exposes
the gap. Fix the underlying evidence/index problem before syncing again.

Command output and exit status survive an indexing failure. There is no retry of
the command to repair memory or telemetry. If the completion event itself could
not be published, retained raw evidence may need explicit reconciliation; a
zero backlog is not proof that every historical execution was observed.

Project scope uses the recorded hook project directory where present; otherwise
it uses execution cwd. Producing thread and parent/child identities stay
separate. Local CLI runs without native identity use `engine-local`. Project
scope is logical filtering, not filesystem access control. Observations are
historical data, never current approval, instructions or semantic correctness.

Use the existing `memory search`, `timeline` and `retrieve` commands to navigate
the index. The observation's receipt hash works with `helixengine retrieve` for
exact original streams. Exact retrieval verifies stream bytes; ingestion verifies
receipt metadata and its binding to the completion event without rereading large
streams. It does not independently authenticate the mutable event database or
prove that deleted events are absent.

The HUD exposes backlog, gaps, last batch duration and indexed bytes. API field
`receipt_memory.last_batch` includes logical evidence-store I/O. SQLite traffic,
physical I/O and provider token savings are not inferred from these counters.
Existing full-index integrity checks remain unchanged. Automatic restoration,
semantic decision ingestion and dependency-qualified procedure reuse are separate
work, not silently enabled by receipt indexing.
