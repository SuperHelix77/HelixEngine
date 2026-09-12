# Native edit batching and the remaining source boundary

## Windows read-consistency correction

Windows Python 3.13 CI rejected stable rewritten source before reading it.
The diagnostic at commit `341af49` recorded equal device, inode, mode, link
count, size, modification time and birthtime, but unequal `st_ctime_ns`:
path lookup reported creation time `1789249628564080500`, while the open
descriptor reported change time `1789249628580347000`.
[Diagnostic CI](https://github.com/SuperHelix77/HelixEngine/actions/runs/34720860503).

This matches CPython's distinct path and descriptor implementations:
[path stat](https://github.com/python/cpython/blob/v3.13.0/Modules/posixmodule.c#L2160-L2203),
[descriptor stat](https://github.com/python/cpython/blob/v3.13.0/Python/fileutils.c#L1111-L1288).
The correction uses birthtime for Windows cross-API comparisons when available,
while comparing descriptor before/after stamps with their full change time.
Path before/after and whole-set consistency fences remain in place. A synthetic
cross-API discrepancy succeeds; a descriptor change-time-only mutation still
rejects the packet. These are capture-time consistency checks, not a filesystem
transaction or a guarantee against a malicious writer restoring metadata.

This compatibility repair does not qualify native source delivery, capability
parity, or token savings. Self-activation remains gated on those separate checks.

## Observed execution result

The local installed-client probe replaced a generated Python file-write and
subprocess wrapper with ordinary `tools.apply_patch` and `tools.exec_command`
in one `functions.exec` batch. The latter invokes the installed `helixengine`
console from its interpreter's PATH. Engine remains ON and owns test execution;
native tools own the patch. No model effort or final-answer schema was changed.

The valid repair's actual tool text fell from 3,040 to 1,582 UTF-8 bytes
(47.96%). The solution itself remained 1,088 bytes. This is observed tool
serialization, **not native output-token savings**. A preliminary 1,427-byte
estimate omitted some actual runtime arguments; use 1,582 for the tested path.

Two deterministic loopback cases passed: the valid repair executed once and
returned test exit 0; the defective repair executed once and returned test exit
1. Both retained ordinary final-message transport. The finals and repairs were
scripted by the local mock, so this establishes neither Sol reasoning nor
normal-final semantic parity. Each case had two local provider requests and
one Engine execution. No hosted inference was used.

The separate finite oracle accepted the valid source (735 graphs, 16 invalid
inputs, 751 nonmutation checks) and rejected the defective source. Protected
test/settings files stayed unchanged. Small/marginal output reductions bypassed
while Engine remained enabled.

## Stale-patch falsifier

A deliberate missing-preimage patch stopped the native batch. The next request
contained `apply_patch verification failed`; there were **zero Engine runs**
and all initial task files were unchanged. The original success-oriented
harness reports missing test markers for this case. Root adjudication treats
that retained failure as the expected stop-on-failure observation, not a passing
success-harness run. The mock final was changed to withhold completion.

This checks a stale textual patch context. It does not establish transactionality
across arbitrary multi-file patches or protect against all concurrent writers.

## Source-preparation correction

Root inspection of decoded first-request content found none of the three exact
project files in either case. The task prompt named the files; the scripted
provider already knew the repair. That distinction was not explicit enough in
the preceding report and is now corrected there.

A Luna explorer correctly located exact native prompt capture through
`UserPromptSubmit`, but concluded that this sufficed for source preparation.
Root inspection of `prompt_memory.py` rejected that conclusion: capturing prompt
bytes does not read or deliver the mentioned project files. The module itself
explicitly describes storage-only behavior. Its passing capture tests are not
file-preparation tests.

A further local wire check appended a native `mention` input for each project
file. Neither exact file contents nor the supplied absolute file paths appeared
in the observed first requests. Do not infer file expansion from the existence
of a generic mention schema. The current official documentation describes
mentions for apps and separately documents client-supplied tool output and
history injection; it does not establish an existing desktop source bridge.
[App-server documentation](https://learn.chatgpt.com/docs/app-server).

## Next implementation boundary

The bounded candidate is an explicit, project-scoped source opt-in through the
existing shared hook. Installed Engine captures a configured finite file set,
archives exact bytes, and offers a bounded quoted source packet before native
inference. It does not guess file permissions or source selection from prompt
text, execute source instructions, or replace the model's final answer. Missing,
changed-during-read, binary or oversized input returns no packet and leaves the
ordinary tool path available. Recording/recovery context retains priority.

This is intended to remove a measured discovery/read context cycle, not add a
memory agent. Configuration, reads, archives, packet size, native delivery,
retrievals and any additional model work must all be charged. It stays opt-in
pending installed delivery and a fresh paired economic/capability gate. Do not
launch a hosted comparison merely because the earlier scripted repair passed.

## Implemented preparation slice

The development branch now exposes `codex source set|status|clear --project`
through the installed CLI. The same shared hook offers configured evidence for
ordinary root submissions and child startup, with independent child attribution.
There is no additional interceptor, model call, task-text file selector or
second archive. Default behavior is unconfigured; Engine OFF prevents reading.
Source configuration lives outside the selected project. Exact CAS object
paths make recovery possible without inspecting Engine implementation code.

The full-set before/after stat fence rejects ordinary read-time changes.
It is not a lease or a concurrency-proof filesystem snapshot after return.
Read and serialized-context budgets are enforced separately. JSON source
strings remain untrusted data. Preparation failures preserve the ordinary
native task, and do not misclassify successful prompt capture as failed.

Root and independent review found and fixed path normalization, bounded CLI
errors, FIFO-open blocking, aggregate read growth, cross-file mutation,
Windows binary-read flags and oversize configuration publication. The first
installed suite passed 455 checks but preceded the last two review fixes;
the next wheel passed 456 locally but failed Windows Python 3.13 CI.
After the timestamp correction above, the fresh installed wheel passed
**458 tests in 15.82 seconds**. All seven jobs in
[CI for `d401289`](https://github.com/SuperHelix77/HelixEngine/actions/runs/34721171108)
passed, including Windows, Linux and macOS on Python 3.11/3.13 and browser smoke.
This qualifies the tested platform behavior, not native Windows hook installation.

Direct invocation of the installed hook command passed root/child exact-content,
new-source-version, old-object recovery, missing-file fallback, Engine OFF and
clear-configuration checks. Three files contained 677 source bytes; the offered
JSON packet was **1,821 bytes**. Initial preparation reported 3.24 ms and 677
object bytes written; repeated child preparation reported 9.83 ms, 677 object
bytes read and zero new object bytes written. These are local observations,
not stable latency predictions or full effective-cost accounting. In particular,
`archive_bytes` is logical archived input; `store_io` records the measured
object traffic, including deduplicated writes.

That smoke invoked the installed hook command directly and did not prove native
dispatch. The subsequent native-client experiment below closes that delivery
gap for the tested isolated root-session path. Runtime telemetry still says
`hook_response_not_wire_verified`: an individual hook response cannot infer
whether its caller subsequently serialized it successfully.
Native economics, semantic parity, live desktop/root attachment and self-activation
remain unqualified. No production source opt-in or root model setting changed.

## Native-client source delivery

Using the installed Codex 0.153.4 client, the root reviewed the four shared hook
definitions through the normal CLI `/hooks` UI in an isolated home/project.
Native `hooks/list` then reported all four enabled and trusted. No trust hashes
were hand-written, no managed-policy override was introduced, and no hook-trust
bypass flag was used. This is test-project approval, not approval or attachment
of the current desktop conversation.

A Luna worker ran three fresh native threads against an auth-free loopback
Responses mock. Each sent exactly one provider request and received one scripted
ordinary final message. The submitted 93-byte user prompt remained unchanged.

| Case | Exact source in first request | Packet bytes | Request bytes |
|---|---:|---:|---:|
| Configured source V1 | 3 files, 677 bytes | 1,818 | 49,736 |
| Source V2 after changing `solution.py` | 3 files, 700 bytes | 1,843 | 49,763 |
| Engine OFF | No source packet | 0 | 47,694 |

The root independently decoded the stored requests, checked the developer
message's quoted-evidence wrapper, and verified every source byte/hash against
the archived objects. Both old and new source versions remain recoverable.
The runner sent only the user prompt through `turn/start`; it did not inject
the expected packet itself. The configured native hook supplied it.

These are serialized byte counts, not token or monetary savings. The candidate
adds source context; savings require that a real model then avoids more expensive
rediscovery while preserving its investigation and normal final answer. Quoted
data in developer transport is not itself proof of semantic resistance to source
instructions. Subagent source delivery through the actual native creation path
also remains a separate gate.

The original probe used an uninstrumented `elapsed_seconds: 0` placeholder.
Root audit rejects it as a timing observation: elapsed time is **UNKNOWN**.
The original receipt and executed harness are retained; the future harness now
uses null. No hosted model calls or authorization headers were used. Parent and
worker research inference is still research overhead, not zero-cost work.

Exact artifacts: `research/source-hook-native-wire-20260913/RESULT.json`,
`ROOT_AUDIT.json`, `NATIVE_REVIEW.json`, and each case's raw `request.json`.
V1 request SHA-256:
`a3802870b0be0bd39ae1cbbd4abcc52371004ba52c6ca374312d58c2c5fa78c4`.
V2 request SHA-256:
`1ebaebf3a5770af2011b0586eabf54829ec63dd2b4ddd3779926379ffcc2b72f`.
OFF request SHA-256:
`7e5a075f4ebefe75b23302f46f53b86e05d16ced7934ebf527b4614ebaaf70b7`.

## Ordinary unittest routing gap

The installed transfer probe previously used an explicit `helixengine run`
command. Inspection of the shared router found that ordinary
`python -m unittest` and `python3 -m unittest` were not admitted, although
the existing generic reducer already preserved unittest counts and failure IDs.
The router now admits these commands without changing their arguments, using
the same execution, fallback, exact capture and delivery boundary as other
supported command families. Arbitrary Python scripts and interactive Python
remain outside this admission rule.

Focused tests executed ordinary rewritten unittest commands once for each of
parent/child and success/failure cases. They checked exit status, counts,
diagnostic text and producing-thread identity. This is an adapter integration
check, not a native model-request or savings result. The separate source-wire
probe retains its earlier frozen installed wheel so the two changes cannot be
silently conflated.
The fresh installed wheel passed 462 tests in 16.09 seconds locally; its SHA-256
is `6d9eaef44371632e442e1b8435e36a8a5faaaf9e79e86890f88d85f2d54afacd`.
All seven [CI jobs for `ce9c711`](https://github.com/SuperHelix77/HelixEngine/actions/runs/34721825673)
passed. Native unittest interception/delivery must still be checked before
crediting this route in a real model comparison.

## Evidence

- Native edit-batch PROBE SHA-256:
  `80d30648eb7e53439c52cba5932917153e6b10c2bf256f8ff99d73a13d4a2732`.
- Independent oracle SHA-256:
  `6c080fb574d44a54d911ca69b86d5687634bba7c78a8853ece0b8901d8d3de6e`.
- File-mention valid-case first request SHA-256:
  `4b49c25a7972deb6fe1b4124730560edce8e9f8565b368441aa7913ddc234a52`.
- Source-context wheel before the Windows timestamp correction (not cross-platform qualified):
  `ff2ad6b0c5f684b20439161bcfd01e7de07525d34a63fdad198cd5999ae801c0`.
- Installed wheel after the timestamp correction:
  `50b03cf74dd97023a6bebfb1eb3f26fee80ce656af2302612140454aaa9b09a6`.
- Installed hook smoke RESULT SHA-256:
  `0664437e6d07c7c394b41fd60022be2d5e02ddeca23639ac285fb4df94d57484`.

Exact local artifacts are retained in the dated `sol-native-edit-batch`,
`sol-native-edit-stale`, and `sol-native-file-mention` research directories.
No model median is qualified and no v0.2 release is claimed.
