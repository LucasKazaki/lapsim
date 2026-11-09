# Separate smoothed FSG candidate, portable dev31

`lapsim_light_course.fsg_smoothing.produce_fsg_smoothed_candidate` now constructs
and screens a separate development reference from the complete pinned FSG data.
Production, readback and evaluation use only the Python standard library. No
optimizer, extra physics engine, dependency install, model rollout, native
provider, gate/mission registration or original authentication is invoked.

## Fixed shared-control model

The original nine margin failures, four hard single-track proxy failures and
192 curvature jumps remain unchanged in the source and candidate evidence.
The archived 64-source-station pattern defines this new recipe. An initial
64/96-station SciPy investigation is retained as historical evidence: 64 passed
the sampled margin screen while 96 failed. The final producer uses neither
SciPy nor those independently rounded coefficient pieces. No held-out results,
policy results or optimization objective were used to select a trajectory.

Sample 64 equally spaced original source stations, using the existing saved
chord interpolation. The separate fit view closes its last point to its first;
the `3.0854550180035267e-12 m` adjustment is recorded, and source bytes remain
untouched. Solve the bounded cyclic interpolation system
`P[i-1] + 4 P[i] + P[i+1] = 6 source_node[i]`. Its fixed matrix is symmetric
positive definite with eigenvalues in [2,6]. The standard-library Gaussian
solve checks finite pivots, controls and interpolation residuals. Observed
maximum source-node residual is `1.464821375527116e-14 m`.

**One cyclic array of 64 controls defines the curve.** On interval i, normalized
local t uses P[i-1], P[i], P[i+1], P[i+2] with weights
`((1-t)^3, 3t^3-6t^2+4, -3t^3+3t^2+3t+1, t^3)/6`. The mathematical basis joins
position, first and second derivatives algebraically, including the seam.
Independent local coefficient overrides and a duplicated 65th control are
rejected. Rounded power coefficients are derived from those same controls for
the numerical interval screens; they do not define independent joining pieces.

This structural change addresses independent review's finding that tiny gaps
between separately stored cubic pieces can hide adjacent overlaps despite
positive tangent projections. The earlier independent-coefficient prototype
is preserved, has a different schema, and is not accepted by the new reader.
The new proposal schema is `lapsim.fsg-fixed-periodic-bspline-proposal.v1`;
the screened schema is `lapsim.fsg-fixed-periodic-bspline-candidate.v1`.

The evaluation parameter is **source-sample index 0–64**, not metres, time or
new-curve arc length. Source fitting stations in metres are separate provenance.
`candidate.evaluate(parameter, derivative=0)` evaluates the shared basis; third
derivatives at knots use the right-hand interval. This supplies geometry only.

## Continuous floating screens

Retain the synthetic body extents +/-1 m, width 1.4 m, safety/map/tracking
allowances 0.2/0.1/0.1 m, wheelbase 1.6 m and steering cap 0.4 rad. They are not
measurements or calibration for Lucas's RWD car. The fixed curvature margin is
`0.95*tan(0.4)/1.6 = 0.25103347362578354 /m`; it was not relaxed.

All interval recursion retains its original cubic-cell index and evaluates
both endpoints with that cell's polynomial. Curvature uses `(v x a)/|v|^3`,
not a unit-speed assumption. The complete-interval cubic bound passes in 140
intervals, with maximum `0.25083687223656603 /m`. Positive parameter-speed
bounds are established before accepting an interval.

The complete rectangle checker includes vertices, edge pairs and enclosed
boundary vertices. Midpoint clearance must exceed whole-interval displacement
`(Vmax + R*Amax/Vmin)*half_parameter_interval`. All 604 intervals pass; minimum
conservative slack is `0.0001945933265842248 m` **after 0.401000001 m declared
padding**. This lower bound is not a measured physical clearance.

Adaptive sampling proves a floating cubic-to-view error bound before topology
checks. Its maximum is `0.00015625413379316926 m`, below the retained 0.001 m
limit. The 4,096-cell view has chord length `306.2542287824437 m`; this is not
the source length or an exact new-curve arc length. Curvature previews are
cubic midpoint values, not claims that a polyline has bounded corner curvature.

Nonadjacent checks examine 11,253 pairs, using 4,951 bucket entries and 15,413
pair visits, with >0.002000001 m required separation. Both incident interval
tangent projections, including the seam, pass. Shared controls supply the C2
model; observed rounded-coefficient position/velocity/acceleration join residuals
remain explicit. These are **floating screens**, not rigorous roundoff or an
actual-vehicle simple-loop/trajectory certificate.

The within-cell steering-proxy spatial-gradient bound is `1.4113916211194508`
rad per metre of **new-curve arc length**. It is neither rad/s nor an exact
global machine-arithmetic rate proof. No speed law, steering-rate-in-time limit
or vehicle-following test is supplied.

## Readback, budgets and evidence

Complete raw source/frame/recipe projections use canonical-byte equality, and
the included frame must match its own declared digest. Boolean/numeric aliases
cannot change typed inputs while retaining old hashes. Readback derives all
coefficients from retained controls, reruns every screen and compares the whole
canonical artifact; a rehashed forged sample view is rejected. The raw fixture
is 414,997 bytes, SHA256
`d6cf0b81bd04edcb41f4cedc6c73720f6709e58dd81a06d8d5b245859470cdc8`.
This is local numerical consistency, not original producer/environment
authentication or cross-platform qualification.

One absolute cooperative window covers production, screening, serialization
and transport validation, with a final return fence. Each public window is
limited to 40 seconds; external test timeouts cover the whole command. Depth,
interval, sample and topology caps fail explicitly without coarsening or retry.
Rejected proposals retain their exact bytes. Clock-fixture tests are expressly
untrusted control-flow tests, not numerical or native deadline evidence.

Twenty new tests pass, covering the independent harmonic solve oracle, shared
basis/seam behavior, regularity, bounds/cap failures, typed identity aliases,
raw tampering, retained rejections, finalization fences and genuine fixture
readback. The first small-circle unit fixture was correctly refused because
the fixed sampling/error recipe required spacing below 0.05 m; the valid-case
fixture was enlarged, preserving production limits. Its failed log is retained.
The complete 159-case source suite passes in 42.816 s under a 50-second ceiling.
Installed acceptance and raw comparisons are recorded separately.

The candidate starts at the source builder seam, not a verified timing-gate
phase. Original mission, source/environment/producer admission, current guard,
ownership, allocation, output-retention and cleanup requirements remain open.
Existing FSI numerical-reference input rejects the new schema. No policy is
promoted, no all-course tournament or native run occurred, and no upload or
unchanged transport failure was retried. Prior releases, source data, ordinary
`.9` and all native admission protections remain unchanged.
