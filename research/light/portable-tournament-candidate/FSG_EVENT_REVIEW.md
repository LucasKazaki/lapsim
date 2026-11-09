# FSG development numerical consumer, portable dev33

`lapsim_light_campaign.fsg_event` adds a distinct versioned numerical component.
It constructs a metric course from complete smoothed-reference/phase/source
readback and advances the real fixed-clock driver, seven-policy allocator and
coupled planar/electrical/load/thermal/DRS plant. It does not register a native
worker, authenticate inputs or provide a checkpoint restore/Start route.

## Metric initialization and identity

`FsgNumericalCourse(phase_raw, reference_raw, bundle_raw, cones_raw,
work_wall_s=40.)` uses one absolute cooperative geometry budget for base/phase
readback, projections and serialization. It retains the original 4096-cell
sampled metric and parameter table without resampling, rotation or curve refit.
The original 414,997-byte reference and 17,644-byte phase inputs stay unchanged.
Their hashes, exact source/frame/geometry identities and metric table hash are
bound into a new `lapsim.fsg-development-metric-course.v1` record.

The initial CG is explicitly synthetic: the analytic phase representative point
and tangent, not the source front-wing pose or a measured vehicle start.
Parameter-to-chord interpolation supplies a local-search seed only. Actual
initial projections supply separate reference and source station offsets R0/S0.
Absolute unwrapped metre stations R/S remain in memory; reported gate-relative
progress is R-R0/S-S0. This avoids the old FSI zero-seed discontinuity at FSG's
roughly six-metre source offset. Phase index is never substituted for metres.
The guidance target is explicitly R0 plus reference length. That target is not
the finish test. Chord/source stations are approximate metrics, not exact new
curve arclength or physical distance travelled.

## Real numerical behavior and event boundary

`FsgDevelopmentConsumer(course, policy_id=..., residual_regen_rule=...,
residual_regen_rule_sha256=..., maximum_ticks=..., maximum_work=...)` constructs
the retained synthetic standing fixture: zero vehicle/wheel speeds, 9 MJ pack,
70 C tires and unchanged physical/model settings. All seven OFF policy IDs use
matched initial state and conditions. No actual-car or regenerative qualification
is inherited. A missing/placeholder/wrong-pinned residual-predicate input fails
closed. A method/hash match is consistency only; the production bootstrap must
supply the real original implementation and independent authentication.

`advance(ticks=..., work_wall_s=..., maximum_new_work=...)` returns a distinct raw
interval. Limits are at most 1000 ticks/50,000 new numerical work units per call,
a positive cooperative window at most 10 seconds and explicit global tick/work
caps. Driver/allocator/brake clocks remain 50/10/1 plant ticks; physical ticks are
1 ms. Existing controller, allocator, brake-blend and `plant_tick.advance_tick`
functions own those calculations. Actual request/proposal/limit/intervention
fields and controller memory are preserved; existing energy is never reset or
clipped. Verified body parameters and an owned frame copy are cached once,
without reparsing the complete reference artifact for each physical tick.

Each prospective interval checks projection continuity and full Euclidean
residual, gate-relative one-lap domain, forward speed/wheels, road/slip/combined
force, pack domain, original-predicate result, OFF actual-power/torque domain,
full synthetic body clearance, mechanical energy and component clocks. These
are development checks, not original ownership/resource/admission safeguards.
The synthetic body is checked for every candidate tick; continuous swept
trajectory, actual car, survey and roundoff qualification remain absent.

Startup is unarmed. The small representative gate residual cannot turn its first
forward crossing into a lap. Departure requires an accepted forward-side state
and positive reference/source progress. Arming requires both net windings; finish
requires a previously armed state, directed finite CG-gate crossing and both
current gate-relative stations near one complete circuit. Reverse finite hits,
ambiguous finite endpoints, projection jumps and incomplete windings are refused.
Reference distance alone cannot finish a lap. Existing FSI workers and receipts
are unchanged and do not accept this new event family.

A finish uses the same actual XY intersection fraction to interpolate time and
pack energy between accepted 1 ms endpoints. The full post-tick state and memory
are retained unchanged, with no reset/backstep. Status is `development_completed`,
never native qualification or an award. Pure event-arithmetic test inputs are
explicitly fabricated and are not completed numerical laps.

## Failure, cancellation, work and retained bytes

The consumer owns one immutable accepted boundary record. Snapshot serialization
acquires the same nonblocking lock as advancement. A complete candidate record is
published in one pointer operation; an interrupted publication restores the
complete old boundary, while retaining the attempted work and rejected trial.
A refused call after a terminal result leaves that result unchanged.

Returned plant work is charged before post-validation. If an attempted plant call
throws without trustworthy counters, the retained total is explicitly a lower
bound. Unexpected exceptions seal the event invalid, retain available evidence
and propagate; a failed cell cannot silently retry. Value/domain rejections keep
the last accepted state plus a separate uncommitted provisional state/memory.
Time/work limits and cancellation do not create a finish. Cancellation is
cooperative at tick boundaries: an in-flight tick may commit before the next
boundary observes the request.

Deadline fences cover initial snapshot work, new plant work, post-step/event
commit and final interval serialization. A late finalization returns no success:
`FsgDevelopmentDeadlineExceeded.raw_interval` retains staged bytes as quarantined
data, the consumer becomes terminal `wall_limit`, and any candidate finish is
kept only as failed-finalization evidence. No second serialization is attempted
after that deadline. These Python fences cannot interrupt a blocked dependency
or replace an original enclosing OS deadline/watchdog and cleanup proof.

`snapshot()` is raw data only, not an authenticated checkpoint, durable archive,
continuation permit or restoration API. Unreturned output retention and process
cleanup remain the original provider's responsibility. There is no automatic
retry, extra lap, hidden budget extension or permissive native fallback.

## Tests and remaining work

Twenty-two new focused cases cover initialization/units, matched seven-policy
20 ms real-plant probes, fixed-clock split-call parity, timing/work/cancellation,
retained trials, unexpected exceptions, snapshot locking, late control/post-step/
serialization fences, whole-record interrupted publication, immutable terminal
refusal, finite directed finish and independent windings. The positive plant
probes use an explicitly UNTRUSTED residual-predicate double. They execute the
real numerical components but do not test the unavailable original predicate,
source/environment observation, native guard, Windows or a full FSG lap.
Injected exceptions/clocks and fabricated gate/terminal fixtures retain their
separate roles in the source and test evidence.

The complete source/installed acceptance and exact artifacts are recorded
externally against the final committed source. No held-out result is loaded.
Native FSG worker/request/continuation registration, independent source/environment/
line authentication, original admission/lease/deadline/output-retention/cleanup,
actual-car/driver and complete trajectory qualification remain separate gates.
The supported Library preparation failure was not retried; all artifacts remain
producer-local. Earlier releases and ordinary `.9` pins remain unchanged.
