# Continuation, exact numerical replay and UI model — source-only tranche

Base: `a572ad16da5901f976e5ec4b8ff4ba3a2bc786b5`.
Scope: bounded E07 follow-on. **UNTESTED / UNBUILT / UNQUALIFIED.**

## Frozen behavior contract, before implementation

- Preserve v1 raw-journal origin and terminal rules. A continued raw store uses
  a fresh outer directory, a separate explicit ancestry artifact and an inner
  ordinary v1 journal rebuilt from the complete verified original prefix.
  No parent terminal is removed, no partial/orphan evidence is recovered, and
  global tick, segment, energy, work, context, controller and gate data are not
  reset. Copied history consumes the child's record/storage quotas too.
- Only `paused_budget` with at least one committed record and a running numeric
  checkpoint is proposed for continuation. This is a conservative NEW staging
  rule, not recovered original authority. Exact parent bundle, manifest,
  terminal, last storage receipt, checkpoint, historical owned-receipt bundle,
  fresh challenge and fresh input-bound dispatch request are bound together.
  A genuine external original provider must authenticate the entire history,
  explicitly admit continuation and own fresh allocation/cleanup. Missing or
  incomplete providers refuse before any numerical or storage side effect.
- Exact numerical replay starts by reconstructing the fresh stationary origin,
  then reruns every original requested chunk extent and compares whole raw
  chunks and linked checkpoints byte for byte. Output tick differences cannot
  substitute for originally requested ticks, particularly for invalid output.
  A versioned dispatch contract explicitly requires `progress_callback=None`;
  historical callback/unknown-request runs are not silently admitted to replay.
  No tolerance, endpoint-only equivalence or scientific requalification follows.
- Replay work belongs only inside a genuine freshly guarded owned worker with
  original receipt/cleanup admission. The worker helper is a library operation,
  not a launcher or a capability. A mismatch preserves the complete newly
  generated divergent chunk/checkpoint in its raw report; equal original bytes
  remain in the input bundle. Actual crash/exception evidence retention is still
  an external provider responsibility and must not be claimed from this source.
- The UI model reads exact pinned raw exports and distinguishes storage-chain
  consistency, numerical replay, execution admission and runtime availability.
  It cannot enable Run/Continue/Replay/Stop/Close from a local DTO or saved file.
  Stop-requested and cleanup-confirmed must remain distinct. The legacy web
  search/sweep backend is not used as a light-provider substitute.
- No real predicate, signer, crypto implementation, observer, guard, lease,
  watchdog, worker process or tool-receipt semantics are invented. No candidate
  execution, import, syntax check, test, simulation, inference, build, installation,
  push or publication is authorized in this tranche.

## Source investigation

The archive imports `lapsim.experiments.torque_light_demo` and calls
`residual_low_speed_regen` in `light_core_bridge.py`; `line_binding.py` imports
`producer_receipts`. Its source manifest also names `numeric_evidence`.
Tracked source and reachable Git object/path/history searches across the local
refs found no original definitions/files. The independent reviewer found the
same result. `research/light/README.md` explicitly describes unresolved receipt
dependencies and excludes machine-specific supervisors, process inventories,
resource/lease receipts and tool transcripts. Existing main-package process
controls are not evidence for the original light implementation.

Library content search returned no relevant source evidence; exact-title queries
for the three missing filenames returned no matches (index coverage is not proof
of global absence). Personal Context reported unavailable for this conversation.
No missing source was recovered, no remote machine was accessed and no gate was
cleared. The source/runtime observer, exact environment lock, original residual
predicate, authenticated producer evidence and genuine guard/receipt/cleanup
implementation remain external blockers.

Independent review evidence: v1 journal origins require tick=segment=0 and no
parent chunk; all terminal stores are immutable. Raw chunks omit the original
requested tick count, and callbacks can affect invalid status. The legacy web
server launches unrelated `controller_tournament`/`tournament_sweep` modules.

Inspected refs include `origin/review-166` at
`eda45185a4debeae7239dce906b72cfdf3909da9` and the source-audit ref at
`83eadd434156a217506ba3767302b08fef464ce6`. These are source artifacts,
not the original maintained checkout or runtime environment. A local reachable
object/path search returned only the new `guarded_dispatch.py` for the targeted
light guard/receipt names; path-history searches for the three missing files
returned none. This is a bounded local-source investigation, not proof that no
authorized copy exists elsewhere.

## Prepared implementation and review boundaries

- `dispatch_request.py` explicitly versions its staged schema to v2 and binds
  the fixed callback-free entrypoint. Its immutable tuple specification is
  converted to a fresh JSON object for staging/comparison. Old v1 requests remain
  preserved in previous artifacts; they are refused by this new exact-replay
  path. The numerical backend and raw checkpoint/chunk schemas are unchanged;
  loaded-source identity must nevertheless be observed afresh after any change.
- `guarded_dispatch.py` factors provider preflight, staged metadata validation,
  result byte bounds and post-cleanup metadata binding. It still imports no
  numerical module. Refactoring introduces no real provider or registration.
- `continuation.py` rebuilds its complete predecessor/inner-request binding
  whenever consumed. It permits proposals only from an advanced paused-budget
  store whose numeric tail is running and has remaining original mission/work/
  segment allowance. A genuine original provider must admit the full historical
  evidence and outer continuation request separately from fresh input claims.
  Returned data remains raw. The optional in-owned-worker copy helper writes a
  new directory exclusively; its nested v1 origin stays tick zero and copies all
  original raw chunks/checkpoints. Its ancestry and opaque admission bytes live
  outside that inner journal so v1 inventories remain unchanged. The same
  source/limits can yield the same inner manifest hash as the parent: the unique
  outer lineage/ancestry, not a v1 manifest alone, distinguishes the child.
  Consumers must authenticate that outer ancestry with the original provider.
  Never add the copied parent and child prefix together as new coverage.
- `numerical_replay.py` requires one complete canonical v2 original request per
  raw record, distinct challenges and a separate fresh origin input-review
  proposal. The latter's one-tick plan is only an input binding; it is NOT the
  full replay work permit. The outer replay request binds every original extent
  and a finite conservative sum of request/work ceilings. Only the genuine
  original provider may admit that outer operation and allocate its resources.
  The worker helper starts from newly initialized state and compares complete
  canonical output bytes. Mismatch reports retain generated raw origin or first
  divergent chunk/linked-checkpoint bytes. Metadata admission of such reports
  does not change historical validity or award points/credit.
- `ui_model.py` provides a passive, separately embeddable Tk frame/model. It
  clears old results before attempting a new load, retains raw scalar values,
  and never enables worker controls. Tk imports are deferred until explicit
  factory use. No app launcher, HTTP route, window, worker or mainloop is added.

All transport caps are explicit NEW interface bounds, not assertions about the
unavailable original formats. Opaque historical receipts are capped at 64 MiB,
original replay request bytes at 16 MiB total, replay proposals at 1 MiB and raw
reports at 3 MiB. Oversized data is refused, never truncated. The real owner must
retain original/partial/failing evidence durably. The source helper does not
establish exception/crash storage, actual lifecycle guards or power-loss safety.

## Remaining external and acceptance work

No original predicate, real producer verifier/bundle, loaded-source/runtime
observer, exact environment lock, supported guard APIs/receipts or genuine
chunk/continuation/replay provider was recovered or installed. Explicit outer
continuation/replay authentication and child-lineage admission must map to
those actual supported contracts. Direct helper/DTO construction cannot do so.
No automatic history migration, callback reconstruction or terminal revival is
supplied. Active UI progress/cancellation and cleanup-confirmed Stop/Close,
browser/desktop integration, matched laps and numerical/exception/crash/durability
qualification remain open. No existing restriction or earlier denial is cleared.

No candidate function, parser, state decoder, numeric bridge, replay helper,
signature adapter, provider callback, file-writing helper or Tk factory was
invoked. No candidate import, syntax check, test, simulation, inference, build or
installation ran. Source inspection cannot establish runtime correctness or
numerical parity. Independent source-review findings and final source hashes
will be recorded below before this tranche is committed.

## Final independent source review

The independent reviewer inspected the source investigation, continuation,
replay, v2 request/guard refactoring and passive UI source. No concrete defect
was identified in the final inspected changes. The reviewer confirmed:

- advanced paused-budget/running-only staging, complete child-prefix copying,
  actual journal interfaces, preserved cumulative state and parent immutability;
- original requested ticks and no-callback replay, first-divergence retention
  and exact prior/chunk/linked-checkpoint binding in mismatch-report admission;
- immutable v2 entrypoint declaration, consistent serialization/validation and
  provider-placeholder rejection before work;
- clear-before-load UI behavior, disabled controls and separate evidence scopes.

During own source review, child inspection/property access was reconciled with
the actual `journal_committed_tail` and `expected_manifest_sha256` APIs before
independent review. The entrypoint declaration was made immutable and divergent
reports were bound through the existing raw transition validator. No candidate
API was invoked to check these repairs. Source-manifest entries record exact
file byte counts, SHA-256 and Git blob identifiers, excluding the manifest itself.
Independent review is inspection only and establishes no numerical, parser,
storage, cryptographic, UI or guard-runtime acceptance.
