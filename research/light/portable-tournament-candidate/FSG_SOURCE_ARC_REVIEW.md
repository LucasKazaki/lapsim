# FSG source-arc pose and steering-proxy diagnostic, portable dev30

`lapsim_light_course.fsg_source_arcs.screen_fsg_source_arcs` takes the complete
pinned FSG bundle/YAML and explicit body, uncertainty and steering-recipe inputs.
It adds continuous **source-arc pose** geometry screening without modifying the
saved source, chord reference, guidance, worker, mission or admission interfaces.
It returns `lapsim.fsg-source-arc-pose-proxy-diagnostic.v1`, always unqualified.

The archived synthetic assumptions are front/rear extents 1 m, width 1.4 m,
safety margin 0.2 m, map uncertainty 0.1 m, tracking allowance 0.1 m, wheelbase
1.6 m, steering cap 0.4 rad and curvature margin fraction 0.95. The fixture's
driver cap and two 0.8 m axle offsets support those declared numbers; they are
not measured dimensions, calibration or a steering model for Lucas's RWD car.
The reference anchor is not established as a CG or rear-axle path, and parallel
front-wheel steering is not the single-track geometric proxy used here.

## Global heading and body transfer

The source model is piecewise constant-curvature arcs. Initial heading zero is
supported by its initial-outgoing-tangent coordinate frame and original builder.
For each saved arc length `ds` and curvature `k`, integrate the full global pose
using `ds*sinc(k*ds/2)` at the midpoint heading. Carry XY and unwrapped heading
across all 724 cells; never reanchor to saved cell endpoints. Compare **every**
saved endpoint with this independent global reconstruction. The maximum observed
position discrepancy is `5.145708854543081e-12 m`, below the existing source-grid
screen's `1e-7 m` tolerance.

The signed turn is `-6.283185307179537 rad`; wrapped seam-heading error is about
`4.885e-14 rad`. The unsnapped terminal XY is approximately
`(-1.98308e-12, -6.21738e-13) m`, a `2.07826e-12 m` position gap. These floating
checks do not prove exact periodic closure. The last clearance parent chord ends
at the first saved source point, and its actual endpoint discrepancy is included.

Reuse the existing full-rectangle translation screen on all 724 original parent
chords and the exact same approximate cone frame/body/padding. This is separate
from the earlier gate-split 725-chord diagnostic. Retain the inherited spatial
arc allowance in padding, even though the following transfer includes position
error again. This conservative extra reservation is neither refunded nor used
as a rigorous error proof.

For each arc and its same-fraction saved chord point:

```
position_bound = abs(k)*ds**2/8 + max(analytic_endpoint_to_parent_errors)
beta = abs(remainder(analytic_mid_heading - chord_heading, 2*pi)) + abs(k)*ds/2
rotation_bound = 2*body_radius*sin(min(beta, pi)/2)
pose_transfer_bound = position_bound + rotation_bound
```

The first term is the unit-speed arc's vector linear-interpolation bound plus
actual endpoint discrepancies. The second covers every rectangle point at its
arc tangent orientation. A positional grid tolerance is never substituted for
an angular bound. The whole-cell heading span is not wrapped. The global minimum
completed parent-translation slack minus the largest cell transfer bound must
be strictly positive; incomplete/failed parent clearance cannot transfer.

Here the parent slack is `0.20654201849530202 m`, the largest transfer bound is
`0.0871846434113781 m` at cell 445, and the conservative arc-pose clearance lower
bound is **`0.11935737508392391 m`**. This supports only the modeled continuous
arc body family against approximate cone-centre polylines in floating arithmetic.
It is not measured-car clearance, rigorous roundoff certification, or a claim
that the current chord-interpolating guidance follows these arc tangents.
Static vertex rotations from the previous diagnostic are not treated as a drive.

## Steering failures remain

The archived recipe uses `0.95*tan(0.4)/1.6`, not `tan(0.95*0.4)/1.6`:

- Margin curvature limit: `0.25103347362578354 /m`.
- Maximum saved magnitude: `0.2728963069136036 /m`.
- Margin failures: cells 442–445 and 447–451, covering `4.138154033063898 m`.
- Cells 442–445 also exceed the unmargined `tan(0.4)/1.6` limit.
- Maximum `abs(atan(1.6*k))`: `0.41168341485150256 rad`, a **single-track proxy**.
- All 192 source curvature jumps, including the seam, remain recorded.

Clear body geometry does not erase these proxy failures. No steering-rate or
drivability qualification follows from piecewise curvature jumps. No radii,
coordinates, caps, margin fractions or failure statuses are silently adjusted.
Inputs and derived curvature limits must be finite and strictly positive;
independent review found accepted subnormal inputs could otherwise overflow a
limit to infinity or underflow it to zero. The two failing cases are preserved
and now rejected before comparisons/reporting.

## Evidence and remaining dependencies

Twelve new cases cover stable signed/near-zero-curvature poses, globally carried
heading, independent analytic circle/body-corner counterchecks, interior-grid
tampering, invalid inputs and derived limits, curvature margin placement, signed
amplitude failures, seam jumps, transfer refusal and the complete real FSG input.
The full 139-case source suite passes in 21.380 s under a 45-second outer limit.
Installed package acceptance and raw per-cell evidence are recorded separately.
Two independent source reviews checked the geometry/proxy boundaries; the
derived-limit repair has a failing-before/passing-after regression.

Remaining work includes a separately generated and screened reference satisfying
its declared curvature/steering contract, continuous steering/rate and actual
vehicle trajectory checks, an exact reviewed arc/gate/phase/mission convention,
and genuine original source/environment/producer admission plus native worker,
ownership, deadline, output retention and cleanup. This module supplies none of
those authorities. It uses no held-out results, registers no provider or Start,
and leaves all existing native/policy eligibility gates unchanged. Prior releases
and the ordinary `.9` snapshot remain frozen. No native job or delivery retry is
part of this pass.
