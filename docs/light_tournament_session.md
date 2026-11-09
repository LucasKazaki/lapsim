# Bounded light tournament session

The new `lapsim.tournament.session` module and `lapsim.tournament.ui.SessionPanel`
implement one first-policy/course chunk of the existing frozen seven-policy plan.
This initial flow displays one attempted cell and six unrun cells. It does not
reorder the plan, qualify a policy, award points or declare a field winner.
The portable dev38 subtree and its source manifest remain unchanged.

The UI entry is
`run_session_window(controller, initial_operation, *, continuation_source=None)`.
No runnable native command/factory is installed: that requires the original
Windows binding below. Ordinary four-controller/GUI startup is separate.

## Real source flow

`FreshOperation(plan_raw, plan_sha256, request_raw, request_sha256,
provider_sha256, output_root, limits, timeout_s)` binds one exact staged v2
request to the first frozen cell. `limits` is the existing `CampaignLimits`.
`FreshExecution(operation, *, provider, cancel_event)` retains the real
`CampaignProgram` before `run()` and supplies exactly one request, then EOF.
The native owner retains this execution object for `snapshot()` after failure;
failure never performs automatic recovery/finalization. Cancellation can return
no advanced output while preserving staged files.

`SessionOutput` contains the exact finalized RAW bundle, manifest and bundle pins,
recomputed seven-cell report, operation pin and output root. Its consistency check
preserves source/environment/car/course/policy/state identity, requested tick/work
bounds, journal quotas and original initial checkpoint. Only an advanced explicit
`paused_budget` / numerical `running` output is eligible for Continue.

`ContinuationOperation(previous_operation, predecessor, request_raw,
continuation_sha256, historical_owned_receipts_raw, provider_sha256, output_root,
timeout_s, maximum_records, maximum_bytes, sync_files)` requires a fresh original
outer continuation request and a disjoint new namespace. The controller refuses
used challenges, operations, namespaces and child lineages. Process-local replay
checks do not replace the original provider's persistent freshness authentication.

`ContinuationExecution(operation, *, provider, owned_admission_raw,
owned_admission_sha256, cancel_event)` runs **inside** independently authenticated
native writer admission. It copies and reads back the complete prefix/admission,
dispatches through `OriginalContinuationProvider`, retains returned packet bytes,
appends exactly one result, validates terminal/checkpoint readback, then writes
and reads back the export/report. The child's exact three-entry directory remains
`ancestry.json`, `owned-admission.bin`, `journal/`; packets/exports are outside it.
No partial namespace is retried. Predecessors remain immutable. RAW validation is
not numerical replay, signature authentication or execution permission.

## Exact native integration request

The existing native owner must supply a reviewed `NativeSessionHost` with:

```python
implementation_sha256: str
launch(operation: FreshOperation | ContinuationOperation) -> handle
require_authenticated_terminal(operation, update: HostUpdate) -> None

# Returned handle (bounded, nonblocking UI-thread calls):
operation_sha256: str
poll() -> HostUpdate | None
request_stop(reason: str) -> None  # user_stop / window_close / timeout
```

`HostUpdate(operation_sha256, sequence, phase, progress_ticks, outcome=None,
output=None, terminal_evidence_raw=b'', detail='')` uses phases `admitting`,
`running`, `finalizing`, `cleanup`, `terminal`. Progress is an actual observed
absolute numerical tick, bounded by the staged request. Terminal outcomes are
`returned`, `cancelled`, `timed_out`, `failed`. `returned` needs a real finalized
`SessionOutput`; failure/cancellation can retain partial files without one.
Terminal evidence must authenticate operation/source/environment/inputs, exact
output or quarantine, accounting, cancellation and owned cleanup. Hashes or local
flags are insufficient. The verifier raises on refusal; inherited placeholders
are rejected before launch.

The precise native process topology is still required: designate the process
holding the **existing** nonblocking FileLock and host writer context, the process
running `CampaignProgram` and the numerical leaf owner. `run_worker` already
acquires that lock; do not nest another `run_worker` acquisition.
`supervise_owned` does not itself acquire it and is not an alternate lease.
The child provider's verified cleanup can precede campaign host finalization;
the enclosing original host lease/deadline must remain valid through all writes,
readback and verification. Final UI cleanup verification follows empty Job,
signaled stable-process exit, joined watchdogs/observers/readers and proper handle
closure. Unproved cleanup invokes the native creator-fatal path inside the lease.
No Tk exception callback substitutes for creator exit.

`timeout_s` is a finite proposal, not an allocation. The native deadline starts
before launch and covers admission, request supply, execution, all output work,
verification and cleanup. Stop/Close/UI timeout only request cancellation and
keep polling. They never free the handle or enable Continue/Close based on time.
Actual authenticated failure/completion remains visible when a pending Stop races
it; Stop intent stays separately recorded and prevents automatic continuation.
Failed, cancelled, timed-out or unconfirmed launch states never silently resume.
Native original 10 GiB admission / 8 GiB running floors are unchanged.

## Package and verification boundary

The ordinary distribution revision is `0.1.0+light20261109.10`, separate from the
unchanged portable `0.0.0.dev38`. Python >=3.11; the new controller adds no third-party runtime dependency. Tk must
be present for the panel. The ordinary `python-lapsim` distribution has a new
`light-tournament` extra pinned to the separate existing
`lapsim-light-tournament-source-candidate==0.0.0.dev38` distribution. Install both
from the same checked-out source; that package is not asserted to exist on PyPI.
With the already approved interpreter/dependencies/build tools, the source recipe
is `python -m pip install --no-build-isolation ./research/light/portable-tournament-candidate '.[light-tournament]'`.
This is an installation recipe, not a launch or native qualification claim.
The native/launcher owners retain installer and original provider ownership.

Focused tests use actual CampaignProgram/RAW/continuation storage and explicitly
untrusted host/provider doubles. They do not run numerical physics, acquire a
lease, observe Windows resources or establish Job cleanup. Widget-double tests
exercise the actual callbacks/control state; they do not establish real Tk or
Windows UI acceptance. A direct cloud Tk creation attempt failed because this
executor has no DISPLAY. Native Start/Stop/timeout/cleanup/resume acceptance is
still required with fresh original admission and the reviewed native host.
