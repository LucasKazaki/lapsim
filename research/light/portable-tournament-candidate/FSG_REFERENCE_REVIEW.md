# FSG sampled source-chord and gate diagnostic, dev28

`lapsim_light_course.fsg_reference.construct_fsg_source_chord_reference` builds
a separate `FsgSourceChordReference` from complete pinned FSG bundle/YAML bytes.
This is an explicit development geometry recipe, not a fallback racing line.
Its schema is `lapsim.fsg-source-chord-reference-candidate.v1`, status
`SOURCE_CHORD_DIAGNOSTIC_UNQUALIFIED`. Direct DTO construction validates bounded
canonical transport and declared scope; `verify_fsg_source_chord_reference`
rebuilds exact local source consistency. Neither operation authenticates a
producer or supplies native execution authority.

## Gate and phase

The public YAML actually contains `tk_device=[[6,3],[6,-3]]`. Its six-metre
segment is transformed through FSG's own SE2 frame. The separate starting-pose
triplet `[0,0,0]` is retained as uninterpreted front-wing metadata, never used as
a vehicle CG pose or confirmed yaw convention. Orange cones at x=4.7/7.3 and
y=+/-2.5 are not substituted for the timing segment. Official timing, survey
accuracy and vehicle-start semantics remain unverified.

The gate's normal is chosen from the ordered source chord at the unique finite
transversal crossing. Missing/multiple crossings, overlapping edges and vertex
touches are rejected. A true vertex side change is counted once. Independent
review found the original touch-counting defect; its failing regression and
repair are retained. `forward_crossing` returns only fraction/point diagnostics,
without time, battery state, lap completion or award.

The real crossing is in curved source cell 14: curvature
`-0.007541133083307749/m`, arc length `0.4467751757021672 m`. An initial exact
straight-cell assumption rejected it; that failure is retained. The implemented
chord recipe instead records station `5.986110824458535 m` as a linear arc-station
estimate at the chord fraction, explicitly not an analytic arc/gate intersection
and with no station-error bound. The builder seam is not the timing gate.
No old FSI origin/progress/finish rule is reused.

## Sampling and limits

Every distinct saved source vertex is preserved. A separate closed view replaces
the tiny source endpoint residual with exact closure, splits/rotates the loop at
the gate-chord intersection and subdivides chords by a declared maximum step.
Stations are cumulative Euclidean chord lengths; curvature follows the archived
producer's wrapped adjacent-heading change over mean adjacent chord length.
This does not create a smooth steering-qualified curve.

The 0.1 m diagnostic has 3,339 cells and chord length `306.4346565146983 m`, with
geometry SHA256 `2041ffb6b9cc7552780c751296c2268ce09b95200ae507c4c47cf3ad5f5a7069`.
The reported original-cell spatial estimate is `|K| ds^2/8` plus observed grid
and closure residuals, about `0.00775982345 m`. It is not a station bound or a
rigorous floating-point proof. Subdividing an existing chord does not reduce
that source-arc approximation error. The FSI producer's 0.001 m recipe and
clearance claims are not inherited.

At most 5,000 sample cells are counted before allocation; a tighter request that
exceeds the cap is rejected without coarsening. Coarse nonadjacent intersection
checks have a 300,000-pair limit. Degeneracy, foldback, nonfinite/duplicate JSON,
oversized/mutable transport, altered gate/phase/geometry and contradictory
qualification claims are refused. Source consistency readback is local to the
same numerical environment, not a canonical cross-platform producer artifact.

Seventeen new tests and the full 110-case source suite pass (5.321 s, zero
failures/errors/skips). The external runner uses a 20-second ceiling and retains
the complete candidate. Independent source review passed after the touch and
transport-bound repairs. Installed artifact results are recorded separately.
All model/clearance/optimization/authentication/roundoff qualification flags are
false, no held-out result is read, and all seven policies remain native `UNRUN`.
Existing `raw_reference_inputs`, numerical worker/bridge, gate ledger and
registry are unchanged and reject this incompatible candidate.

Remaining work is a versioned reference/mission contract with appropriate smooth
sampling, full rectangle/curvature/topology screens, genuine source/environment
and producer evidence, original admission/ownership/cleanup and fresh policy
qualification. This diagnostic does not unlock Start or native continuation.
