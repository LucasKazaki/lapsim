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

The fixed native-host constructor is now:

```python
prepare_session_execution(
    operation, *, provider, cancel_event,
    owned_admission_raw=None, owned_admission_sha256=None,
)
```

Import it from `lapsim.tournament.session`. It returns the actual `FreshExecution`
or `ContinuationExecution`, preserves the supplied provider/Event, and never runs,
acquires a lock, enters a native context or authenticates admission. Fresh calls
reject continuation admission arguments. Continuation calls require the original
owner's already authenticated complete admission bytes and exact pin. Both
original continuation methods and the reviewed implementation pin are checked
before output creation, again at run entry, and at the original dispatch boundary.
An incomplete provider therefore cannot create a new prefix before being refused.
The host retains the returned object before calling `run()` inside its existing
original writer/lease/deadline allocation. `FreshExecution.snapshot()` is readable
after return/failure; `ContinuationExecution.phase` identifies its last stage.
Neither is a recovery or cleanup receipt. No native control exception is caught
by this factory.
The Event is local to the host executing the campaign. If UI and host are separate
processes, the native handle's existing owned Stop relay must set that Event and
also enforce active-leaf cancellation through the original supervisor. A Python
thread Event is not a cross-process transport or an active-leaf watchdog.

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
output=None, terminal_evidence_raw=b'', detail='',
paused_continuation_eligible=False)` uses phases `admitting`,
`running`, `finalizing`, `cleanup`, `terminal`. Progress is an actual observed
absolute numerical tick, bounded by the staged request. Terminal outcomes are
`returned`, `cancelled`, `timed_out`, `failed`. `returned` needs a real finalized
`SessionOutput`; failure/cancellation can retain partial files without one.
Terminal evidence must authenticate operation/source/environment/inputs, exact
output or quarantine, accounting, cancellation and owned cleanup. Hashes or local
flags are insufficient. The verifier raises on refusal; inherited placeholders
are rejected before launch.

The additive `paused_continuation_eligible` field is an exact boolean, defaulting
to **False**. It can be True only on a `returned` terminal with an advanced
paused-budget/running output. The real native verifier must bind this exact
claim to the exact paused predecessor and genuinely admitted historical lineage;
cleanup alone, local hashes or RAW consistency do not establish it. The controller
commits eligibility only after that verifier accepts the exact update. Older
bindings that omit the field can show the paused result and close after cleanup,
but cannot enable Continue. Each new Start resets eligibility. A True claim is
eligibility to **propose** a continuation: it never replaces the original provider's
fresh challenge/current-input/lineage/lease/resource/deadline admission for it.
The native adapter's reviewed implementation pin must cover this updated verifier
contract. An older generic verifier is not assumed to authenticate the new True
claim just because its method signature still accepts `HostUpdate`. The status
panel explains when paused continuation eligibility is not verified.
The separate ordinary package/commit and its actual loaded session/UI/host source
must also be pinned and observed in the native outer integration. The unchanged
portable dev38 source manifest covers that numerical subtree; it is not a source
identity for these new lifecycle modules or an environment observation.

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

For immediate native implementation, the only required source-side factory is
`prepare_session_execution` above. The Windows owner must identify the existing
FileLock holder and its lifetime, the CampaignProgram host and leaf process/Job
identities, and the path from handle Stop to the genuine owner/watchdog. Its
terminal evidence must cover stable-process exit, the actual empty-Job check,
joined readers/observers/watchdogs, handle closure and final output verification
before releasing UI cleanup state. An admission/GO failure is a failure terminal
only after its actual cleanup is authenticated; an exception with uncertain
creation stays blocked. A prior ordinary GUI containment failure neither supplies
these tournament receipts nor identifies its own cause.

`timeout_s` is a finite proposal, not an allocation. The native deadline starts
before launch and covers admission, request supply, execution, all output work,
verification and cleanup. Stop/Close/UI timeout only request cancellation and
keep polling. They never free the handle or enable Continue/Close based on time.
Actual authenticated failure/completion remains visible when a pending Stop races
it; Stop intent stays separately recorded and prevents automatic continuation.
Failed, cancelled, timed-out or unconfirmed launch states never silently resume.
Native original 10 GiB admission / 8 GiB running floors are unchanged.

## Package and verification boundary

The ordinary distribution revision is `0.1.0+light20261109.11`, separate from the
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
