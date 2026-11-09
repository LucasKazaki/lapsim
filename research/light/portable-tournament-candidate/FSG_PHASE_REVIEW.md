# FSG digital gate, phase view and margin audit, portable dev32

`lapsim_light_course.fsg_phase.construct_fsg_gate_phase` binds a separate,
immutable `FsgSmoothedPhaseView` to the unchanged complete smoothed reference
and exact source bundle/YAML. Complete base readback is required before gate
construction; a bare candidate DTO is not trusted. The base remains 414,997
bytes with SHA256
`d6cf0b81bd04edcb41f4cedc6c73720f6709e58dd81a06d8d5b245859470cdc8`.
No source, controls, fit, clearance, steering cap or native contract is changed.

## Supported source and exact digital predicates

The pinned YAML's `tk_device` endpoints are `(6,3)` and `(6,-3)`. They map
through the same FSG frame to approximately `(6.23693,2.84553)` and
`(5.73656,-3.13357)` metres. Direction uses the original ordered source chord's
crossing **sign only**, not its old curved-cell station/fraction. The source
front-wing pose remains uninterpreted metadata, not a vehicle CG/start state.
The segment's official timing and actual-car start conventions are unverified.

Convert the retained binary64 controls and mapped gate endpoints to exact
Fractions **before** forming differences or Bezier control combinations. On
each of 64 cubic cells, scalar Bernstein controls enclose
`f(P) = orientation * cross(B-A, P-A)` and `h(P) = dot(P-A, B-A)`.
Finite extent is strictly `0 < h < dot(B-A,B-A)`. Exact hulls exclude impossible
branches; strict derivative hulls plus opposite endpoint signs isolate one
transverse root. Other branches are subdivided or explicitly unresolved.

All finite-gate-potential branches are resolved before selecting exactly one
forward crossing. Tangencies, overlap, ambiguous finite endpoints and exhausted
node/depth limits fail. Exact shared knot/split roots are owned by their reduced
rational parameter; the periodic seam maps to zero. Only identical roots are
deduplicated. Two distinct roots separated by less than the bracket tolerance
remain distinct, as tested with rational roots `1/2 +/- 2^-40`.

The real FSG crossing is in cubic cell 1. Its exact digital root bracket is
`[2684496795/2147483648, 85903897441/68719476736]`, width `2^-36` in source-sample
index units. The representative is `1.2500662333404762`, with parameter radius
`7.275957614183426e-12`. At that representative the floating pose is approximately
`(5.98125593943,-0.209622303485) m`, with `2.93918e-11 m` plane residual.
The exact digital root is bracketed; its midpoint is **not an exact machine gate
pose**, survey result or official event phase.

Independent review found an edge case in the displayed radius: an exact deep
dyadic root can round when converted to a float. The new bound measures the
rounded representative's exact Fraction distance to both bracket endpoints and
rounds outward when needed. A failing-before/passing-after regression uses
global parameter `63.5 + 2^-48`; the actual FSG artifact is unchanged by this
repair. Numerators/denominators are canonical strings to preserve exact values.

## Geometry integration and event boundary

`view.evaluate(progress_index, derivative=0)` translates the unchanged shared
basis by the representative offset. Progress is bounded index 0–64, **not
metres, time or laps**. Both endpoints use the same saved offset directly,
avoiding `(offset+64)%64` cancellation. Derivatives remain in index units.
Controls and geometry bytes are not rotated, refitted or resampled.

`view.finite_segment_crossing(before_xy, after_xy)` uses exact digital signs
and finite extent to return an intersection fraction/point only. Reverse and
outside crossings return none; endpoint contact is unsupported. It does not
receive or generate time, battery energy, accepted physical state, winding or
departure history. A geometric hit or completed index interval is not a lap.

The old FSI `gate_ledger` requires its own origin/axis and continues to reject
this FSG gate. Existing numerical workers, requests and checkpoints remain
FSI-only. A future versioned consumer must pin **both base reference and phase
artifact identities**, establish progress/metric mapping, initialization,
departure/arming/winding/finish semantics and retain admitted physical state.
Old checkpoints cannot acquire a new starting phase merely because the base
curve hash is unchanged. This pass supplies no event receipt or Start route.

## Small steering-margin investigation

The old `0.25083687223656603 /m` certificate stopped refining once intervals
passed the unchanged `0.25103347362578354 /m` synthetic limit. It was not a close
estimate of the curve's maximum. A uniform finer partition can even have looser
raw bounds; completed inherited parent bounds must be retained.

The separate audit maintains a covering max-heap over all 64 cells. It refines
the largest upper bound, replaces a parent only after both children exist and
uses `min(valid inherited bound, new child bound)`. Observed point curvature is
a witness, never a replacement for a continuous bound. On cap exhaustion it
returns no partial success, leaving the original reference untouched.

In 216 nodes with 140 covering leaves, the refined floating upper bound is
`0.24284144974995692 /m`. The largest observed point is `0.24274145062548813 /m`;
their gap is below the fixed `0.0001 /m` target. With the same `1e-12 /m` guard,
the certificate headroom is **`0.008192023874826626 /m`**. This refines the
synthetic geometric certificate; it does not establish actual-car steering
headroom, time-rate limits or driver following. The original nine/four source
failures and 192 curvature jumps remain evidence.

## Evidence, identity and remaining requirements

The phase sidecar is 17,644 bytes, SHA256
`20c2f7d5102fd0bcd34058fc449f2b85679eda745a71c7f97d88c73d444294ab`.
It binds base/source/frame hashes, mapped segment, rational bracket, predicates,
covering intervals and explicit non-event scope. Transport checks reject
contradictory status/units/qualification labels; complete readback recomputes
everything and compares exact bytes. One original cooperative budget includes
base verification, all root/margin work, serialization and final transport.

Twenty-three new regressions pass, including nearby roots, knot/seam/split
ownership, tangent/overlap/finite endpoints, reverse/outside hits, exhausted
limits, deep representative rounding, full coverage, tampering/stale inputs,
phase endpoint equality, original FSI refusal and an explicitly untrusted late
clock fixture. The complete 182-case source suite passes in 42.482 s under a
60-second outer ceiling. The source construction probe took 4.169 s within its
40-second window. Installed acceptance is recorded separately.

Exact predicates apply to the serialized digital model only. Source transform,
survey, actual vehicle, original producer/environment authentication, Windows
and native execution remain unqualified. Base readback retains its local
numerical-consistency scope. Original ownership/activity/lease, finite allocation,
output retention and cleanup gates remain required. No native heavy job,
held-out result, award, publication or unchanged upload retry occurred. Prior
references/releases and the ordinary `.9` snapshot remain unchanged.
