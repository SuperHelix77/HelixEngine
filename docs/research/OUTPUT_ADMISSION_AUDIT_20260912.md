# Output admission audit — 2026-09-12

## Verdict

OBSERVED: a smaller evidence packet can contain more tokenizer-proxy tokens than
the complete source. Engine now avoids small and marginal output reductions,
while retaining command execution, exact capture, exit status and telemetry.
This development change does not establish native-token savings or model parity.

## Offline evidence

The known repair from the rejected native coding pilot was replayed in a fresh
Git fixture. This reused answer is not independent capability evidence. Each
policy ran pytest, git diff and git status once; no new paid native benchmark
was launched.

| Measurement | Before | Admission guard |
|---|---:|---:|
| Raw Git diff bytes | 1,831 | 1,831 |
| Delivered Git diff bytes | 1,667 | 1,831 |
| Git diff o200k_base proxy tokens | 497 | 453 |
| Total raw bytes, three commands | 3,357 | 3,357 |
| Total delivered bytes | 3,193 | 3,357 |
| Object bytes read, including audit recovery | 19,151 | 10,535 |

The original diff is 453 proxy tokens: projection inflated it by 44 tokens
(9.7%) despite saving 164 bytes. Complete raw delivery removes this observed
inflation. The proxy is not a native billing receipt or proof of the hosted
model's tokenizer. Local object reads fell 45.0%; this is not a quota claim.

The before/after raw diff SHA-256 is identical:
`d062dcedd0c919c5642a9c63a05d4ff653b41602ce3d2fa2f9d2018c79dc144c`.

Evidence is retained in the local research workspace under
`research/interception-native-pilot-20260912/`:

- `CORRECTED_OUTPUT_AUDIT.json`
- `CORRECTED_OUTPUT_TOKEN_PROXY.json`
- `CORRECTED_OUTPUT_AUDIT_ADMISSION_V1.json`
- `corrected-output-evidence/` and `corrected-output-evidence-admission-v1/`
- `ADMISSION_WORKER_USAGE.json`

These local research artifacts are not bundled release data.

## Policy and validation

- Below 2,048 raw bytes: skip projection entirely and deliver exact raw streams.
- Otherwise, admit projection only when it saves at least 512 bytes and 20%.
- Marginal gain returns raw output with `BYPASSED_MARGINAL_GAIN` status.
- Existing failed-reducer fallback remains raw delivery without command rerun.
- Engine stays enabled. Model effort, tools and model-written final answers
  remain unchanged; this is one shared Runtime policy for parent and child use.

These thresholds are conservative byte heuristics, not fitted model-specific
economic guarantees. Admitted larger packets can still require exact retrieval.
No runtime tokenizer dependency or extra model call was introduced.

Validation: **212 tests passed in 12.02 seconds**, routed through Engine. New
cases cover exact binary stdout/stderr, nonzero exit, no small-output parsing,
both admission thresholds and admitted packet delivery. The identical offline
diff was recovered and compared after the change.

## Costs and deployment boundary

One bounded Luna High worker completed seven measured responses: 267,797 input
tokens (255,232 cached; 12,565 uncached), 3,882 output tokens including 2,602
reasoning tokens. These are research costs, not savings. Root costs remain
UNKNOWN because the session observer reports an oversized skipped history line.

The research HUD on port 8770 was restarted with the same task observer and
Engine enabled. The release HUD on 8769 was left unchanged. Native hook processes
load current source per invocation. This change does not suppress inference or
make session observation complete.

## Next gate

Do not rerun the small coding fixture merely to measure this fix: the corrected
trace has no substantial reducible output. Select a fresh, bounded workload with
material model-delivered tool output only after offline admission and exact
recovery checks. Measure cached and uncached native input, output, all agent
costs and normal-final behavior separately.

Historical Astra caller-prepared evidence and W50 state-transition wins require
caller lifecycle capabilities beyond tool interception. They cannot be credited
to this policy. Neither universal savings, 95/95, nor v0.2 release qualification
is established here.
