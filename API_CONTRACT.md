# Helix Engine v0.1 application contract

This is the integration contract for the standalone local application. No model invocation is performed by its CLI, HTTP server, renderer, or routine telemetry.

## CLI

`helixengine --data-dir PATH serve --port 8769 [--open]`

`helixengine --data-dir PATH on|off|status|doctor`

`helixengine --data-dir PATH run [--kind generic|pytest|compiler] [--cwd PATH] [--timeout SECONDS] -- COMMAND ARG...`

`helixengine --data-dir PATH retrieve RECEIPT --stream stdout|stderr [--start INTEGER] [--end INTEGER]`

`helixengine --data-dir PATH usage-import RUN_ID RECEIPT_JSON`

Global default data directory is `~/.helixengine`. The optimization switch affects new routed commands. Active commands retain their bound setting. OFF preserves exact native stdout/stderr and exit status; observation remains active. No automatic interception of arbitrary Codex activity is claimed. No command reruns on reducer failure. Small outputs bypass reduction when a compact packet costs more bytes. Raw streams remain separate and exact; cross-stream ordering is unknown.

## HTTP

Bind only 127.0.0.1. No arbitrary command execution or file reads via HTTP. No `/research` route or research ledger assets.

`GET /api/release-state` returns:

```
{
  "schema": "helix.app.v1", "app_version": "0.1.0", "observed_at": 0,
  "settings": {"enabled": true, "revision": 0}, "csrf_token": "random-per-server",
  "runs": [], "events": [], "usages": [], "total_runs": 0, "run_view_limit": 100,
  "storage": {"bytes": null, "objects": null},
  "release": {"lanes": [], "problems": [], "model_wide_parity": false, "release_medians": null},
  "pricing": {"fresh": false, "rates": null, "checked_at": null, "expires_at": null}
}
```

`GET /api/release-events` streams these snapshots as SSE `data` messages, updating about once per second. Append-only event records have id, at (Unix seconds), kind, run. Run rows contain id, argv array, cwd, state (STARTING/RUNNING/COMPLETED/FAILED), enabled, started (Unix), stdout_bytes, stderr_bytes; completed rows also include visible_bytes, elapsed_seconds, exit_code, receipt path, reducer_status. Fields not measured must remain null/absent, never inferred from byte proxies.

`POST /api/settings` accepts `{ "enabled": false, "revision": 0 }` with `Content-Type: application/json`, exact same Origin, valid Host and `X-Helix-CSRF` matching the snapshot token. Return updated settings with 200; stale revision 409; malformed input 400; bad origin/token 403. Never mutate on GET. Restrict body size. No permissive CORS.

Pricing comes from the existing official-source parser, refreshes at most every 120 seconds, and expires after 300. Unavailable/stale prices suppress dollar estimates. Dollar values describe token tariff equivalents, not included quota or total effective cost. Usages are explicitly imported receipt counters, not automatic provider attestation. Public paired evidence capsules remain read-only and retain rejected outcomes and qualification limits.

The export omits the CSRF token. Local command arguments and paths are private operational data; export requires an explicit user action. Routine rendering never calls a model.
