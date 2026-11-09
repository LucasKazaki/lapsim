# FSG approximate-cone route/body diagnostic, portable dev29

`lapsim_light_course.fsg_clearance.screen_fsg_source_chord_reference` verifies
the complete dev28 source-chord reference against the pinned bundle/YAML, then
screens its unchanged parent chords and a declared rectangle. All six body and
uncertainty inputs are required. This pass uses the archived **synthetic**
front/rear extents of 1 m, width 1.4 m, safety margin 0.2 m, map uncertainty
0.1 m and tracking allowance 0.1 m. They are not measured car dimensions or a
qualified profile projection. No new physics model or optimized line is added.

The boundaries are the two source cone-centre polygons transformed by FSG's
existing frame. Their simplicity, nonintersection and strict nesting are checked.
They are approximate simulator geometry, not surveyed road edges or cone-base
clearance. Orange start cones and `tk_device` retain their previous interpretations.
No official event, timing, start-pose or physical-gate semantics are established.

## Whole route and rectangle screens

The 3,339 verified sample cells subdivide exactly the same 725 saved parent
chords after the existing gate split. Every sample is checked against its own
parent segment; the maximum observed floating residual is about `7.07e-15 m`,
below the separately declared `1e-9 m` numerical allowance. This is neither a
new fitted/downsampled path nor an independent rigorous rounding proof.
Rectangle and yaw results explicitly use **parent-chord headings**, not small
floating differences in the subdivided segment headings.

Every parent chord is compared with all 182 cone-boundary edges: 131,950 pairs,
against a 300,000-pair cap. Whole-segment distances and interior membership
avoid accepting endpoints that hide a crossing through an inner island. The
original reference constructor's topology checks remain unchanged.

A disk with radius `hypot(max(front, rear), width/2)` encloses the rectangle
at every heading. Its swept capsule is a conservative sufficient screen for
all chord positions and junction orientations. This bound fails here: the
minimum centreline/boundary distance is `1.3143018429459727 m`, the body radius
is `1.2206555615733703 m` and total scalar padding is `0.4077598244506709 m`.
The resulting disk slack is `-0.31411354307806844 m`. This does **not** prove
an aligned rectangle collides.

Separately, for every chord a midpoint rectangle with front/rear extents enlarged
by half its length covers the complete fixed-heading translation. The reused
full-footprint routine checks corners, all edge pairs and boundary vertices
inside the rectangle. The minimum padded translation slack is
`0.20654201849530202 m`; corner-only or edge-only acceptance is not used.

At every junction, including the seam, the diagnostic specifies the shortest
incoming-to-outgoing **static yaw family at the exact parent vertex**. For a
yaw interval `[a,b]` of width at most pi, each rectangle point moves at most
`2 R sin(abs(b-a)/4)` from its midpoint-yaw position. Midpoint footprint slack
must strictly exceed this displacement. Otherwise the interval is bisected,
or explicitly fails/unresolves on a sampled pose violation, ambiguity near a
half-turn, depth 10, or the shared 8,192-interval cap. Unchecked joins never pass.
All 725 real joins clear in 725 intervals, with a minimum certified floating
slack bound of `0.16723594090121338 m`. This is a static geometric pose
family, **not a feasible in-place vehicle turn or a smooth steering trajectory**.

The inherited `0.007759823450670832 m` arc-to-chord spatial estimate is included
in padding and remains an estimate. It supplies no arc-heading, gate-phase or
station-error proof. These screens do not qualify the original continuous arcs.

## Evidence and boundary

Seventeen new cases cover analytic capsule distances, whole-chord crossings,
outside/contact rejection, disjoint/crossing boundaries, inner-island enclosure
with clear corners/edges, conservative disk failure, midpoint yaw violation
despite clear endpoints, adaptive interval bounds and exhaustion, half-turn
ambiguity, source tampering and the real FSG inputs. The complete 127-case
source suite passes in 18.544 s under a 35-second outer limit. Raw geometry,
all 725 join records and prior unrefined/unresolved evidence are retained
externally. Installed artifact acceptance is recorded separately.

Independent review prompted a more discriminating enclosure regression and an
explicit parent-heading scope. The midpoint rotation bound is distinct from
the archived smooth-cubic derivative bound, which cannot span chord joins.
No admission/provider/worker/gate-ledger code changes. The existing reference
still declares `vehicle_clearance_screened=False`; this separate diagnostic
does not rewrite its bytes, producer chain or qualification. All original
native requirements remain. No held-out data, native job, winner, upload or
transfer retry is part of this pass. The ordinary `.9` release remains pinned
to portable dev28; this separate portable dev29 needs its own manifest identity.
