# Finite campaign execution program

Base: `cf9942a01bab62c254f3571ee19014ae1a182afa`. Frozen E05 behavior before
implementation. This tranche permits bounded metadata/storage integration tests;
it does not authorise native processes, resource/lease probes, simulations,
fabricated production receipts, transfers or installation.

Implement a real fresh-field run loop around the existing coordinator: obtain a
canonical v2 request for its exact current checkpoint, dispatch through the real
required OriginalGuardProvider, retain returned bytes, append adopted packets
to the actual RawJournal and verify readback before another request. Close and
export actual journals, preserve a finalized field packet archive, and invoke
the existing seven-policy reducer. Keep missing/failed slots, all raw values and
all source/context/parent/request bounds; never retry/reset/revive a terminal.

The installed library Start interface takes a native-supplied provider, request
source, output namespace, explicit finite caps and cancellation Event. It does
not discover/import a native factory or register a shell command that pretends
to have one. Request supply is data, not authority: existing staged validation
and real execution/cleanup admission remain mandatory. A blocking request source
has no Python timeout substitute; native finite deadlines must enclose it.

The native bootstrap must supply genuine writer/path exclusion and finite
finalization windows with ordering compatible with its chunk provider's lease.
The source program acquires no lease. Provider cleanup grants no continuing
host writer scope. A guessed outer lease could deadlock a native implementation;
the native owner must establish the actual lifecycle before calling Start.
Any provider/control exception propagates without further file finalization.
Already written evidence and the coordinator's in-memory returned packets remain;
output that never returned remains the original provider's retention duty.

Pre-reserve complete bounded packet/journal growth, a final archive, actual
raw exports and reports before dispatch. Journal source byte caps stay <=63 MiB
for the existing <=64 MiB export path. These are file-byte/proposal bounds, not
actual disk-block/RSS observations or an allocation. Partial/uncertain writes
are retained and halt execution; no automatic inspect-and-reappend recovery.

Cancellation is checked between chunks and before dispatch. Active Stop remains
the native provider's duty; no local flag means a worker exited or cleanup was
proved. Normal local budget/feed exhaustion may close an advanced running store
as paused_budget, with no continuation authority. Real outer continuation still
requires original history/admission and a fresh child namespace/provider.

Bounded tests must exercise the real orchestration/storage/reduction code with
explicitly UNTRUSTED metadata fixtures and guard/request doubles. They establish
neither numerical correctness nor original admission/containment/cleanup. Never
promote those fixtures or receipts into production artifacts or readiness claims.

## Implemented handoff

Public installed-library source interface: `campaign.start_tournament(plan_raw,
expected_plan_sha256=..., expected_provider_sha256=..., provider=...,
request_source=..., output_root=..., limits=CampaignLimits(...), cancel_event=None)`.
For failure snapshots, retain `CampaignProgram` and invoke `run()` once, then
read `snapshot()` after return/raise. Reentry is refused. Native registration and
the one-command shell bootstrap are not supplied by a default provider.

The request source signature is `(policy_id, checkpoint_raw, *, requested_ticks,
remaining_requested_wall_time_ms) -> canonical v2 request bytes | None`. None
means no further request is available. It must use actual admission inputs,
fresh challenge/time and the existing construction/authentication path, not test
fixtures. The provider is exactly the existing two-method OriginalGuardProvider:
`execute_owned_request` and `require_authenticated_owned_execution_and_cleanup`.
It must dispatch the real fixed chunk_worker numerical family and retain outputs
that fail before return. No source hash/DTO or request-source callback supplies
that provenance or original execution authority.

CampaignLimits has eight explicit fields: chunk_ticks, summed requested-wall-time
cap, retained-history payload cap, journal record cap, journal byte cap, archive
byte cap, aggregate campaign file-byte cap and sync_files. Bounds are enforced
before output creation/dispatch/finalization. Actual time/RSS/free-space probes,
resource admission and watchdog enforcement remain native. The native writer
window must cover root creation, source callback, dispatch, post-cleanup writes
and finalization with compatible lease ordering. No outer lease is guessed here.

Successful storage writes create plan.json/run.json; packets/SEQUENCE contains
the exact request, chunk, checkpoint and original opaque receipts plus a local
packet file index. cells/POLICY is a real v1 RawJournal; exports/POLICY.json is an
actual pinned RawCellExport; field-packets/ is the finalized data-only archive;
results.json is the existing raw field report; outcome.json records the local
status and content pins, never original cleanup/admission. A normal advanced
running stop can produce paused_budget. Resume requires that pinned export,
actual authenticated history, a fresh request/lineage/admission and the existing
OriginalContinuationProvider; this Start never reopens a terminal or refunds caps.

Provider/control or storage exceptions cause no subsequent file finalization,
preserve partials and propagate unchanged. snapshot() separates accepted in-memory
state from successfully read-back persisted checkpoint pins. Active Stop has no
new API here: native termination/empty-job/watchdog/cleanup proof remain required.

## Verification and independent review

Two reviewers found three concrete issues in the first implementation: insufficient
initial/final byte-cap reservation, cancellation during staging still allowing a
new dispatch, and missing packet-parent directory sync. All are repaired and
confirmed by follow-up source inspection. The parent sync test checks wiring;
actual filesystem flushing and power-loss behavior remain unqualified.

Executed bounded check (isolated Python, no installs or native/model jobs):
`python3 -I -S -B -c` adding only this candidate's src/ and tests/ directories,
then `unittest.defaultTestLoader.loadTestsFromName("test_campaign")` with
TextTestRunner. Final result: **14 tests passed, exit 0, 2.174 seconds**. The
earlier nine-case pass was superseded by the focused regressions. All generated
test data lived in temporary UNTRUSTED directories and was removed by the tests.
No test is production evidence, a qualified policy or an authenticated lap.

## Fixed worker input construction

The dev22 `worker_inputs.construct_worker_bridge` supplies the missing fixed
constructor chain: actual `construct_fsi_course`, `raw_reference_inputs`,
`construct_standing_fixture`, then `NumericalBridge`. It takes request/checkpoint
bytes and expected request pin; exact baseline, course-bundle, cone and line bytes;
the independent cone, producer-audit, promotion and source-manifest pins; and real
native `NumericalBindings`. No payload names an import or callable. All raw inputs
are bounded immutable bytes, and parent source/adapter and reference-review pins
must match before any geometric construction. Original line/producer/environment
authentication remains mandatory outside these raw consistency constructors.

Inside the already admitted owned worker, the native bootstrap retains a
`create_chunk_worker(...)` program, constructs this bridge from its admitted
inputs, then invokes `program.execute(bridge=bridge)`. It captures `snapshot()`
after return/failure under original retention and cleanup controls. This source
adds no OS bootstrap, replacement lease, receipt signer or production registration.
Constructor frame/reference arithmetic belongs inside the finite worker deadline;
it must not run inside the post-cleanup receipt authentication callback.

One independent finding was repaired: producer-audit and promotion pins now match
the exact parent's reference provenance before construction. The existing worker
resume would also reject a changed context before stepping. The new early check
does not replace that full resume validation.

Final combined check: **23 tests passed, exit 0, 1.916 seconds** using the same
isolated unittest runner with `test_campaign` and `test_worker_inputs`. The nine
new cases cover bounded raw input/source/adapter/parent-review preflight, fixed
constructor wiring and unchanged owner-control exception propagation. Successful
constructor wiring uses explicit doubles; no real line, observer, residual rule,
numerical step or native process was exercised. The earlier 22-case pass was
superseded by the parent-review-pin regression.

## Dev36 campaign Stop, publication and recovery checks

The dev36 source repair checks the cancellation Event immediately after request
supply, before interpreting None as feed exhaustion. At the local finalization
boundary it freezes one cancellation value. A Stop already observed is sticky;
a newly observed Stop replaces only feed/budget pause, never an actual completed
or failed numerical terminal. The active journal therefore closes cancelled
instead of paused_budget when Stop caused or coincided with the pause.

outcome.json, CampaignResult and the post-run snapshot use that exact frozen
value. snapshot()['cancel_requested'] is None until the finalization boundary,
then a bool describing Stop observed before local finalization. It is not a live
Event view, proof that a native worker stopped, or a cleanup receipt. Later Event
changes cannot rewrite the saved/returned outcome. Exceptions before that
boundary preserve None and their original identity, without new file writes.

The evidence CLI now checks the actual write count before reporting a complete
output digest/size. A short write fails with exit2, leaves the partial exclusive
file intact, prints no success summary and refuses overwrite on another call.
An interrupted write retains partials and reports exit130. These commands never
start or stop a native worker.

Twenty-six focused cases passed in4.597seconds, including12new cases (seven
campaign and five CLI). The first corrected25case red run reproduced five
failures and three missing-snapshot-field errors in4.700seconds. One subsequent
new recovery fixture incorrectly assumed the raw journal manifest had an envelope;
that test-only assumption was corrected to digest its actual body, then all26
cases passed. All intermediate red/green logs are retained outside the source.

The actual partial-receipt case retains orphan objects and the returned packet,
observes zero committed journal records despite one accepted in-memory tick,
and refuses reappend, same-program restart and a fresh program on the same root.
File bytes remain unchanged after refusal. A cancelled export is rejected by the
existing continuation precondition before fresh staged-request validation; it
cannot be revived as a budget pause. No recovery implementation or admission
contract was relaxed. Independent recovery inspection found no additional defect
in field archive finalization, journal reconciliation or child continuation.

Two independent static reviews passed the runtime changes and final test bytes.
All new provider/request/receipt fixtures are explicitly UNTRUSTED storage/control
doubles. No numerical trajectory, native receipt, Windows directory flushing,
active process Stop, lease, resource probe, cleanup or full tournament was tested
by these new cases. Existing numerical tests retain their prior separate scope.

The convenience start_tournament wrapper still propagates exceptions without a
failed-program handle. A genuine native bootstrap requiring failure snapshots
must retain CampaignProgram before invoking run(), then snapshot after return or
raise under its original evidence-retention controls. Partial storage is never
authority to retry, reconcile or resume. Native writer exclusion, finite deadline,
original guards/admission and cleanup are unchanged and still required.

Full source and clean-installed acceptance results, commands and exact package
identities are external records bound to the final commit and source manifest.
The frozen dev35 bundle remains unchanged. No native or launcher-owned file,
private source, transfer path, permission setting or published repository changed.
