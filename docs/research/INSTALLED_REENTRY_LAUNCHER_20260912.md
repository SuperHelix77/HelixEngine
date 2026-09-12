# Installed exact-history launcher: offline qualification

OBSERVED: the installed reentry locator can invoke the existing exact Memory
replay operation through `python -I -m helixengine`. It no longer asks the model
to copy an import bootstrap and package search path. The operation arguments,
scope, recovery warnings, and historical-evidence authority remain unchanged.

Selection is limited to a package resolved beneath this interpreter's configured
purelib or platlib. Source, editable, user-site and custom-target locations keep
the original explicit-path bootstrap. No subprocess is added to select the
launcher. This relies on the same trusted interpreter/installation boundary;
`-I` excludes working-directory and PYTHONPATH shadows, not malicious interpreter
installations. No generic grant is activated, and no model effort or final-answer
contract changes.

## Why this slice

The preceding bounded Astra pair spent 202 output tokens in a segment that
selected a long Memory replay command. Offline substitution in that observed
command changes 474 UTF-8 bytes to 304, removing 170 bytes. This measures command
serialization only. Native input/output savings, whole-workflow economics and
model-wide parity for this variant remain UNKNOWN. No new hosted benchmark was
run for this change; the previous 65.83/50.27 pair remains unchanged.

A direct materialized-artifact shortcut is deferred. A stored receipt does not
establish that a mutable file is still authentic when the model reads it. That
path would require current history/authorization validation and a protected
retrieval boundary; exact Memory already provides the relevant checks.

## Validation

- Fresh installed wheel, outside the source checkout: 429 tests PASS in 15.75 s.
- Installed module launcher selected; hostile cwd/PYTHONPATH exact-recovery test
  ran and passed, with no dependency skip.
- Source-focused worker checks: 37 PASS, one subprocess check skipped because
  local isolated Python lacked certifi. The installed suite closes that gap.
- The initial fresh-environment test invocation found pytest missing and ran no
  tests. After explicitly installing test dependencies, the full suite passed.
- `git diff --check` passed.

The Windows 3.11 job for 9c5220b separately exposed a test race: the live-output
check saw RUNNING, then read an unfinished result dictionary after a three-second
join. The test now holds the child until observation, releases it explicitly,
and awaits its result with a bound, propagating worker failures. It still checks
real live bytes, successful completion and a separate actual timeout. Runtime
production behavior is unchanged. New Windows CI confirmation is pending.

## Evidence

Installed wheel SHA-256: `34afb42aa9404849d9ba0922ffd54785bffed5efb64b26d5132c8af44973772d`.

Observed original rollout SHA-256: `5aab76fd3bb6cb23e029c129c8cd6a1161cb6a7878b185fff439664dca4dd89e`.

Local installed-suite and serialization receipts are retained under the private
temporary validation directory. Neither these tests nor a shorter command imply
a universal capability guarantee or release-median qualification.
