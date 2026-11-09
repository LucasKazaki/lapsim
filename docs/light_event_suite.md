# Nine-circuit nominal screen and separate skidpad field

This is a bounded E08 experiment-integration increment with E03 role/source
constraints. It does not complete native release or campaign qualification.

`lapsim.experiments.light_event_suite` stages all nine shipped circuit bundles
and the ordered skidpad in one fresh development workflow. It declares 36
fixed circuit cells, one per existing ordinary controller per course, followed
by the existing four-controller skidpad field. It performs no genetic search,
tuning, selection, ranking, winner declaration or official scoring.

The four ordinary controllers are `fixed`, `traction`, `yaw_pi`, `tire_reserve`.
The circuit cells use the explicit synthetic RWD profile and a fresh nominal
case per course: no patch/reverse/mirror, default nominal grip/SOC/voltage and
the source model's rolling 5 m/s initialization. Cases and profile match within
each course except controller selection. Conditions are not declared identical
across different events or across the portable AWD7 backend.

## Bounded smoke command

After installing the exact successor ordinary distribution:

```sh
<ordinary-python> -I -B -m lapsim.experiments.light_event_suite \
  --catalog-rollouts 1 --maximum-cell-seconds 0.1 \
  --skidpad-steps 2 --wall-seconds 30 \
  --entry-length-m 5 --exit-length-m 5 \
  --output <new-absolute-external-directory>
```

This deliberately small smoke does **not** complete the suite. It returns an
incomplete circuit diagnostic and a paused skidpad child, preserving the other
cells as unrun. Exit 3 means retained partial or failed development outcomes;
exit 0 requires every circuit cell and the skidpad field to complete their
model criteria. Invalid inputs or publication errors return exit 2.

The circuit budget is an explicit integer from 0 to 36 **whole rollout
reservations**. The skidpad budget is separately 0 to 40000 **plant-interval
reservations**, handled by its existing field. These are different units.
Zero allocations stage metadata without numerical work. At most 60 simulated
seconds per circuit attempt is supported here, on the 10 ms clock; long courses
may remain incomplete. There is no claim all nine courses can finish within
that horizon. The shared explicit wall allowance is at most 300 seconds.

The wall check is cooperative between circuit rollouts and skidpad chunks.
It cannot interrupt a closed-course lap or bound output finalization, and it
is not an OS deadline, resource lease or native allocation. Existing model work
caps remain in force. A whole circuit slot is persisted before dispatch and
never refunded, including failed, uncertain or wall-expired reservations.
Returned-call counts are separate from reservations. No automatic retries occur.
The dispatch fence is checked again after saved-request verification so slow
request I/O cannot start a new rollout after the wall allowance expires.

## Roles, raw outputs and continuation

All new cases are named `development_nominal:<course_id>`. The suite does not
read existing held-out results, invoke phase-selected held-out variants, mutate
controllers or select genetic parents. It makes no unseen-course claim: shared
library geometry does not establish a held-out allocation. Keep these fresh
nominal results separate from campaign holdout evidence and qualification.

The suite writes:

- `suite-binding.json`: the staged bundle hashes, source/runtime record and
  source-declared portable-policy audit.
- `catalog/requests/`: exact fixed case/controller/profile requests for all
  36 cells, including unrun ones.
- `catalog/raw/`: unchanged returned model JSON, including incomplete or failed
  records. The existing engineering-proxy diagnostic may appear inside a raw
  leaf; the suite neither uses nor promotes it into a score or winner.
- `checkpoint-*.json`: create-only outer bookkeeping snapshots before/after
  dispatch. A running/unreturned slot is uncertain, never a free retry.
- `skidpad/`: unchanged child field/checkpoint/result schemas when allocated.
- `suite-index.json`: all ten event groups and every circuit outcome, with raw
  byte pins, failures and unrun rows retained.

Closed-course `rollout()` does not expose a complete resumable mid-lap state.
Its returned record/telemetry and these outer checkpoints must not be used to
invent one. An unreturned exception retains an uncertain consumed slot and
stops subsequent work. Serialization/publication errors propagate and preserve
partial files. Native durability or cleanup is not claimed. Output is fresh
and create-only; suite resume arguments are unsupported.

The skidpad retains its real complete session checkpoints. Its child source,
runtime and course binding are checked against the outer snapshot; different
snapshots are rejected rather than rebound. Child checkpoints are data, not
original native continuation authority. Source/runtime drift before or after a
circuit call also stops the suite while retaining any returned raw record.

## Seven portable policy eligibility gaps

The ordinary index now pins public portable dev38, commit
`a84990be7bf121707abbd27eb4f06cf2b442131b`, manifest SHA256
`bb73c5513265748713e49bfabbc82466d9eb65d9513956b9cef120a3143ef847`.
All 14 declared source pins match the manifest and current checkout. Retained
273-case source and installed Linux evidence belongs to frozen dev38, whose
runtime/test bytes are unchanged; public metadata has a distinct identity.
It is not newly run native acceptance. The earlier 110-case component breakdown
and FSG preparation flags are explicitly historical dev28 data. Current source
availability separately includes the unqualified FSG development consumer,
checkpoint and short replay worker. Native registration and full-event
continuation qualification remain false.

This corrects the stale ordinary-descriptor finding in the portable README's
initial public-snapshot report. That pinned portable subtree remains unchanged;
the historical report is not a current ordinary-runtime admission result.
The ordinary command does not import that stack or offer a portable dispatch
route. Its recorded declarations are not a live capability/admission check;
runtime availability is explicitly unverified. Earlier `.8` indexes retain
dev27, `.7` retains dev26, and `.6`/`.5` retain dev25. Their bytes are unchanged.

Dev26 introduced two allocator API repairs and 16 component/domain tests. Those
checks remain in dev28's 110 source and installed cases. Seven matched rolling probes
have 20 one-ms intervals each; seven launch probes have one interval each, and
two additional intervals check work-counter parity. They use real synthetic AWD
components, with no authenticated course or original native provider. Their
coverage is recorded separately from the qualification gaps below. The ordinary
suite still cannot dispatch these policies, and none becomes eligible from
these fixed-control probes.

Dev27 adds 15 source-preparation cases and exact public FSG bundle/cone inputs.
`construct_fsg_course` now returns a distinct frozen source DTO with its complete
724-cell saved grid and locally reconstructed cone frame. The FSI LF/CRLF
construction outputs match the previous release on the same tested platform.
FSG still has no admissible driving reference or canonical producer frame,
and the existing numerical/reference consumers reject its type. The descriptor
records source preparation separately from course execution and eligibility.

Dev28 adds a separately typed, gate-aligned source-chord diagnostic with 17 new
tests. Its finite segment comes from the actual `tk_device` YAML endpoints
`(6,3)` and `(6,-3)`, transformed through FSG's own frame. The curved-cell arc
station is explicitly an estimate; timing/vehicle-start semantics remain
unverified. Subdividing chords does not improve their source-arc accuracy.
This diagnostic is incompatible with the existing FSI reference/gate consumers,
and no policy is promoted by it.

All seven implementations exist in that snapshot. Every registry entry declares
native qualification `UNRUN` and campaign eligibility false. Their domain is
four-independent AWD, regen OFF, FSI closed reference and one standing-start
lap, with 1 ms plant / 10 ms allocator / 50 ms driver. Ordinary RWD results and
held-out receipts cannot promote these policies.

| Exact portable policy ID | Qualification evidence still needed |
| --- | --- |
| `awd7-equal-off-v4` | Matched baseline trajectory, limits and accounting |
| `awd7-load-off-v4` | Nonuniform/dynamic load activation and zero-load rejection |
| `awd7-slip-off-v4` | Slip activation, shedding and low-speed behavior |
| `awd7-feedforward-off-v4` | Both steering signs/speeds and saturation effects |
| `awd7-yaw-pi-off-v4` | Error, windup/unwind and actuator-limit freeze |
| `awd7-yaw-slip-off-v4` | Simultaneous yaw/slip activation and conservative integral freeze |
| `awd7-eco-neutral-off-v4` | Feasibility/failure and surrogate intervention; no measured loss-map optimum |

Shared blockers remain actual canonical per-course source/frame/reference inputs
and reviewed FSI-constructor generalization; a portable open ordered-event
contract through driver/session/checkpoint/gates/chunks/replay; genuine native
worker registration, complete source/environment-v2 observations, authenticated
current inputs/authority and original finite ownership/cleanup; and fresh matched
seven-policy qualification evidence. The required original guard methods remain
`execute_owned_request` and `require_authenticated_owned_execution_and_cleanup`.
This suite supplies neither original provider implementation nor admission.
Original guards, earlier frozen release bytes and held-out records remain
unchanged; dev26 requires its newly reviewed source pins.

## Acceptance scope, 2026-11-08

The frozen `.5` wheel, runtime commit `117399020e5143170c07bce5763b3198ce8b0b36`,
ran the smoke command from outside the checkout in a clean Linux/CPython 3.12.14
environment. Whole-process time was 5.211 s; the suite's own clock measured
2.081 s against its 30 s allowance. Exit 3 was expected and verified.

All ten event groups and 36 circuit requests were staged. Exactly one real
0.1 s circuit diagnostic returned `time_limit`; its raw record was retained,
and the other 35 circuit cells remained unrun. The real skidpad child consumed
two interval reservations, retained a running session checkpoint and left its
other three cells unrun. Source/runtime/course bindings and raw-file pins matched.
No winner, official score or portable eligibility was produced.

55 focused source tests passed, including failure publication, source drift,
changed result identity, child-binding rejection, predispatch wall expiry and
explicit unknown-state handling. Independent source and data reviews passed.
The [pinned smoke evidence](evidence/light-event-suite-smoke-20261108.json)
records the exact scope; it does not claim completion of all 40 numerical cells.
Windows, GUI, native admission, portable AWD7 qualification and full nine-course
trajectory coverage remain unverified. Post-test documents do not replace the
tested frozen wheel (SHA256
`15a7eb40a93bc69a72a6f35b61ec4c27302f1f89668a972aec2e299a80e933d5`).

### Repaired `.6` successor

The `.6` runtime at `c8c237674aad924152cdd4d6bfbef03be9785cd8` supersedes
`.5` for new integration. A regression first reproduced a late-dispatch gap:
reading and verifying a saved request could exhaust the wall allowance after
the earlier reservation check. The repaired code checks the deadline again
after that I/O and before the rollout. Expiry retains the charged reservation,
records a pause and dispatches no numerical work. Independent source review
confirmed this ordering. The allowance remains cooperative; it cannot preempt
a rollout already in progress or supply native containment.

The repaired source passed 56 focused tests (zero failed or skipped, 20.19 s).
A fresh isolated install of its frozen wheel then ran the same bounded smoke
from outside the checkout in 4.142 s, with expected exit 3. It retained one real
0.1 s `time_limit` record, 35 unrun circuit cells and two checkpointed skidpad
intervals. This was actual numerical work with the synthetic RWD profile; it
was not a full-field run, portable AWD7 qualification or Windows acceptance.
The [successor evidence](evidence/light-event-suite-smoke-r02-20261108.json)
pins the returned files. The `.6` wheel SHA256 is
`dd738857d756443fb765665c231a61eb2dd7d6db0a287205cb5fd789d8b675f4`.
Earlier releases and their evidence remain unchanged. Validation documents
added after the run do not rebuild or replace the tested wheel.

### Explicit `.7` policy snapshot update

The `.7` ordinary package updates only the data-only portable descriptor and
release metadata, preserving the `.6` numerical workflow source. The snapshot
audit now checks the raw manifest hash, distribution version and all six module
pins. Eligibility-invariant assertions run separately even when the optional
portable source tree is absent from an ordinary installation. Two focused
snapshot tests pass; the `.6` numerical acceptance above remains historical
evidence for that exact frozen release. Current `.7` installed staging acceptance
is recorded externally and must not be read as a repeated complete numerical
field, Windows test or native qualification.

### Explicit `.8` source-preparation snapshot

The `.8` ordinary package records dev27's FSG source preparation and checks ten
exact source/resource pins plus the complete raw manifest and version. Both
focused snapshot tests pass. Its numerical event runner remains unchanged from
`.6`; current installed acceptance is zero-budget request staging, recorded in
the release's external verification. The seven-policy numerical path remains
FSI-only and unqualified. Full FSG reference/mission integration, Windows/native
Start and a complete tournament are still separate requirements.

### Explicit `.9` diagnostic snapshot

The `.9` package pins dev28 and eleven source/resource files. Source-audit schema
v2 distinguishes the available chord/gate candidate from an unavailable
admissible driving reference; the numerical path remains disabled. Two focused
snapshot tests pass. Its event runner is unchanged from `.6`; current installed
acceptance is zero-budget staging, not a tournament or native Start.
