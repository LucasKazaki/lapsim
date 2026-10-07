# Optional racing-line planner: implementation and evidence

**Audience:** Racing Terps vehicle and software leads.
**Date:** 6 October 2026.
**Status:** experimental, deterministic path planner; the original centerline lap remains the default.

## What is implemented

The desktop offers **Centerline (default)** and **AI racing line (experimental)**, plus an explicit **Course** choice. The default course is the fused team endurance recording; two separate analytic calculation courses provide a short AI demo and a longer endurance-style practice lap. A teammate can also import a versioned, coherent closed-course bundle without editing Python; see [Versioned course bundles](course_bundle_format.md). Importing leaves Centerline selected. The second driving mode is an offline minimum-curvature path planner with a bounded vehicle-model line-strength search, not machine learning or a closed-loop driving agent. It has access to the selected car model when comparing completed laps, and it uses the same lap physics for its processed geometric centerline and proposed paths. The default driving mode neither imports nor runs the optimizer. The planner does not steer a simulated vehicle, sense cones, react to another car, or learn from experience.

The engineering lap APIs accept an **absolute per-solver-cell grip tuple**
for a sensitivity experiment. Corner limits, cyclic braking ceilings, and
the corresponding cell force updates use the same cell value. The desktop
AI comparison can now additionally place one editable, **assumed world-fixed
low-grip rectangle** on a coherent closed course. It computes a fresh
schedule for each processed path from that path's curvature-integrated
nominal wheel-center geometry, then uses the existing per-cell lap solver.
The original minimum-curvature geometry solve is still grip-blind. Patch
mode can also generate one bounded, locally shifted detour from its processed
baseline. A low-cost grip-exposure score proposes the detour, while only its
modeled-path audit and full-model lap time can make it eligible to win.
Centerline and
two-car desktop runs retain uniform grip. Each completed scheduled AI trial
saves its own exact per-cell schedule in the additive v2 lap-record conditions
and is numerically replayable; this does not validate the assumed patch or
turn the separate WIP pose preview into a full-lap controller.

### Assumed patch to solver-cell calculation

The optional **AI trial surface** selector defaults to Uniform. In rectangle
mode the user enters world X/Y bounds and a positive grip percentage no
greater than the base percentage. The shipped fused GNSS/IMU course fails the
source arc-coherence gate, so this mode requires an analytic course or a
validated coherent imported course. The displayed top-down rectangle is an
input to the calculation, not a measured track feature. A finer course grid
still obeys the 5,000-cell cap.

For each modeled constant-curvature cell, the mapper starts from the same
initial heading policy as the continuous path-clearance audit. At distance
`s` from the cell entry, `psi(s)=psi_0+kappa*s`; the CG follows the exact
circular-arc displacement `s*sinc(kappa*s/2)` in direction
`psi_0+kappa*s/2`. A nominal wheel center is the CG plus longitudinal offset
`l*(cos(psi),sin(psi))` and lateral offset
`b*(-sin(psi),cos(psi))`. With wheelbase `L` and static front-weight fraction
`f`, the offsets are `l_front=L*(1-f)` and `l_rear=-L*f`; the left/right
offsets use half their axle track widths. These are geometric contact
locations only; the main lap still integrates no four-wheel pose or load on
separate road materials.

For one rectangle with factor `a` and the selected tire's uniform reference
factor `gamma`, the desktop's road base is `beta=1`. Its absolute solver input
is `q_i=gamma*min(beta,a)` when any nominal wheel-center curve may touch the
rectangle during cell `i`, and `q_i=gamma*beta` otherwise. The programmatic
mapper also accepts a different positive `beta`. The interval test uses
a bound on contact displacement, subdivides only near the rectangle, and
conservatively treats an unresolved possible touch within 0.01 m as contact.
It raises on its finite work limit instead of silently missing a patch.
All tire force capacity in a touched **whole cell** is reduced; this can
understate performance, and it is not independent-wheel surface physics.
The desktop offers one patch; the mapper supports up to 128 positive
low-grip rectangles and rejects unsupported bounded-road domains. Programmatic
multi-patch inputs must have pairwise disjoint rectangles: even a shared edge
is rejected because patch boundaries are inclusive. `PlanarRoad.query`
assigns an overlapping point to the first matching patch, whereas the mapper
uses the minimum touched factor for each whole solver cell. Rejecting overlaps
keeps those rules from silently disagreeing. The single-patch desktop input
is unaffected. The mapping version is
`integrated_arc_nominal_wheel_min_cell_v1`. Trial records retain the assumed
rectangle and mapping version as planning metadata, plus the exact absolute
schedule in `settings.conditions` and accepted grip telemetry. Replay uses
the frozen schedule rather than trying to reconstruct road geometry.

### Bounded grip-aware detour proposal

With one assumed rectangle and a passing processed-baseline path audit,
`optimization/grip_detour.py::propose_grip_detour` finds cyclic groups of
baseline cells where at least one nominal wheel center may touch lower grip.
It considers at most the two groups with greatest affected path length. If
there is no contact, if contact occupies the entire lap, or if the required
course/corridor alignment fails, it reports a reason and adds no lap trial.

For each group it tests left and right shifts of the processed baseline. The
shift has a flat section over the affected cells and lead-in/lead-out
shoulders of at least `max(12 m, 5 wheelbases, 6 baseline station spacings)`.
Each shoulder uses `S(u)=6u^5-15u^4+10u^3`, whose value and first two
derivatives join continuously at its endpoints. The periodic pulse thus
avoids a nominal curvature jump at the seam or shoulder endpoints. Its
amplitude is bounded by the entered usable scalar corridor at planner nodes,
source-width boundaries, and source-cell midpoints, by **3 m** absolute
offset, and by a further 0.9 factor; the tested fractions are **0.5, 0.75,
and 1.0** of that bounded amplitude. At most **2 contact groups × 2 sides ×
3 amplitudes = 12** geometries are constructed, on at most **5,000** cells.
The entire pulse must remain local, and undefined tangents, reversed local
travel, invalid path geometry, self-crossings, mapping failures, and cells
longer than the requested desktop maximum are screened out.

For each surviving geometry the existing world-road mapper is rerun along
that candidate's own prescribed curvature and nominal four wheel centers.
The screening proxy is
`E = sum_i cell_length_i * max(0, 1 - q_i/(gamma*beta))` in metres, where
`q_i` is the candidate's absolute per-cell grip and `gamma*beta` is its
uniform reference. A candidate must reduce `E` by at least **0.01 m** versus
the processed baseline; the least exposure wins the proposal screen, with
shorter path and smaller offset as deterministic tie-breakers. **Lower E is
not a faster modeled lap or a tire-force proof.** At most one proposed
detour proceeds to the same integrated-curvature scalar corridor/closure
audit and, if admitted, one extra speed-only seam probe plus final lap.
The original four-path budget is at most eight lap passes; patch mode can
reach **five paths and ten passes**. The best eligible candidate still needs
a completed, speed-closed lap and more than the provisional **0.05 s** gain
over the eligible processed baseline. Failed or untimed detours remain
explicit in the result and saved planning metadata. The path is an offline
proposal, not a learned driver, tracked pose, swept-body clearance proof, or
measured low-grip course.

The UI requires one assumed uniform half-width for both sides, plus vehicle width and safety margin. The planner API also accepts **different left and right clearances for every source cell**, with an explicit source label. Each side must be wider than half the vehicle width plus margin. Neither built-in course nor v1 imported bundles include measured widths, so the entered numbers are hypothetical corridors. The user-facing result reports the modeled-path audit, including continuous scalar clearance certification before ranking any completed times. When the processed baseline audit fails, completed laps remain starred diagnostics, the time difference is blank, and no AI winner is selected. When that baseline is valid, a candidate failing its modeled-path audit is recorded as a skipped geometry trial without spending a lap-model pass or creating a replay. If both paths pass, an invalid, slower, or insufficiently faster candidate retains the geometric centerline. A candidate may be displayed if it finishes and its eligible geometric baseline does not, but that is explicitly **not** called a time improvement; its primary run record is also marked `diagnostic_only`.

Course-bundle schema v2 can retain left and right widths **per original source
cell**, tied to that validated source geometry by hashes and accompanied by
independent width provenance and an assumed/measured declaration. They are
normal-coordinate offsets from the *source* reference. The offline planner
prepares a different smoothed reference, so its current desktop route does
not substitute v2 widths for the editable assumed uniform corridor. A checked
source-to-processed frame transformation, boundary uncertainty, and swept-body
check are required before those widths can support an AI clearance claim.
This keeps the course metadata available for review without silently changing
the existing AI comparison. [TUM FTM's trajectory format](https://github.com/TUMFTM/global_racetrajectory_optimization/blob/master/Readme.md)
also defines track widths relative to a named reference line and its normals;
the reference line is therefore part of the meaning of each width.

## Why the default recorded track needs an honest comparison

`analysis/data/track/gnss_imu_endurance_track.csv` contains 989 m of distance-indexed curvature for the current solver, but its separately fused x/y drawing does not form the same numerical path. The repeatable `SpatialTrack.geometry_audit()` reports **1,012.35 m of x/y chord length**, 0.760 m endpoint mismatch, and **1,441 of 1,978 map chords longer than their assigned station distance**, with 45.23 m total positive excess. Any one such chord is impossible for a path of its assigned length. The largest absolute difference between a prescribed constant-curvature arc's chord **length** and its plotted map-cell chord length is **0.235787 m**; this local check detects defects that can cancel in whole-lap turn and closure totals, although it does not check chord direction. The stored curvature integrates to **3.657937 rad** of signed turn versus **6.283185 rad** of x/y winding. Integrating the stored constant-curvature cells from the first plotted chord heading leaves a **542.633 m** position-closure gap. These are geometry diagnostics, not a simulated vehicle pose. The Analysis tab visibly warns about the mismatch. The track has no measured left/right cone boundary or width. Its metadata describes a fusion of registered schematic geometry and corrected IMU curvature, not a geometrically consistent surveyed corridor.

Consequently, AI mode rebuilds both a **geometric centerline baseline** and its candidate from the same x/y preparation method. It does not compare the source-curvature default lap time directly with a shifted x/y path: that would mix two different numerical tracks. The processed baseline's x/y polygon is closed, but its chord lengths and assigned constant-curvature arcs differ; `geometry_audit()` reports a **0.750897 m** curvature-integrated closure gap. A user-entered width here is an **assumed scenario**, not proof a line fits the real course. Track data reconciliation and surveyed widths are necessary before team setup decisions rely on an AI advantage.

## Optional synthetic courses and current eligible comparisons

For ordinary centerline runs, `solver_track_for_course` keeps the synthetic
course's original straight and circular-arc cells when the requested maximum
step is at least its longest source cell (about 0.5 m). For a finer request,
strict validation first checks that the source stations, x/y endpoints, and
constant-curvature arcs agree; each source cell is then subdivided into
analytic straight or circular subarcs while retaining its original stations
and endpoints. A coarser request does not reduce the source cell count.
The fused recording still uses generic distance resampling. Requests implying
more than 5,000 generated centerline cells are rejected to bound desktop work;
the synthetic guard sums the subdivisions of its original source cells. This
gate establishes consistency of a numerical solver representation, not a
surveyed course or measured boundaries. The AI planner uses its own geometric
grid and compute cap.

`src/lapsim/ui/course_catalog.py` defines three built-in course IDs. `team_endurance_fused_gnss_imu` is the **Fused GNSS/IMU · default** startup choice and loads the recorded/fused track above. `synthetic_rounded_rectangle_v1` is a separate **Synthetic loop · AI demo** choice: two 40 m and two 20 m straights joined by four 12 m radius quarter-circle arcs. Its length is **195.398224 m** and its source cells are at most **0.5 m**. `synthetic_fsae_endurance_style_v1` is **Synthetic FSAE-style · practice**: an analytic **817.079633 m** closed loop with alternating 15 m radius bends and 60 m/45 m straights. Its general scale and turn variety draw on [2027 Formula SAE Rules v1.0, D.12.2.2](https://www.fsaeonline.com/cdsweb/gen/DownloadDocument.aspx?DocumentID=da79bcb4-0935-4f7b-83d7-0dbb8ce68d38). It has no official event layout, surveyed centerline or cone boundaries, measured widths, or passing zones; its initial ±3 m corridor is only an editable assumption. Both synthetic source grids use at most 0.5 m cells with coherent straight/circular arcs. The course menu also lists validated imported revisions saved locally across launches. The choice changes the input track for a subsequent centerline, car comparison, or optional AI run; it does not turn on AI automatically. Switching courses clears displayed runs so results from different courses are not implicitly compared.

A geometry probe on the practice course with its starting assumed **±3 m** half-width, **1.8 m** vehicle width, **0.2 m** margin, and initial **Cell size (max) of 1 m** found a coherent, non-self-intersecting source: endpoint mismatch about **3.3e-12 m**, integrated-arc closure gap about **8.6e-12 m**, and maximum source arc-chord mismatch about **5.5e-14 m**. The planner built **829** processed cells with a maximum full-path cell of **0.98907 m**. An exact final-station normalization removes a one-ulp seam mismatch before the unchanged continuous scalar clearance audit; all four tested paths then certified. With the built-in Prius at **80%** desktop torque request, the speed-periodic processed baseline completed in **60.3626147273 s**, half offset **60.1875429499 s**, fourth 0.75 offset **60.1144353996 s**, and the selected full offset **60.0387107423 s**. The full path had a conservative **0.1173201189 m** minimum assumed-corridor slack and a **0.3239039850 s** modeled lead over its own processed baseline. Planning took about **0.67 s** and the bounded comparison about **38.3 s** on this computer. These are controlled software results under hypothetical widths and Prius parameters, not measured cone clearance or a predicted Racing Terps advantage.

On the shipped fused course, an **earlier unconstrained nominal-2 m API benchmark** used **±2 m** assumed half-width, **1.78308 m** vehicle width, **0.3 m** margin, and full torque request. Under the current exit-grip physics but before the desktop cell-length bound, its processed baseline/full/half/0.75 diagnostic laps completed in **88.2468936756/88.0083862976/88.0305817762/87.9983373607 s**. Every path was ineligible because modeled-path geometry failed the corridor/closure audit. These are not timing predictions for the new 1 m desktop default. The default centerline uses different source curvature and is not a timing baseline for them.

The short synthetic demo initially fills the AI boxes with an *assumed* uniform **±3 m** half-width, **1.8 m** vehicle width, and **0.2 m** margin; these remain editable. With the built-in Prius at desktop torque request **80% (enter 80; model fraction 0.8)** and initial **Cell size (max) of 1 m**, the speed-periodic comparison produced an eligible geometric baseline of **17.0090108038 s**, an eligible half-offset of **15.7317585066 s**, and an eligible **0.975-offset** of **14.6378307024 s**. The 0.975 path was selected (`candidate_selected`) with a **2.3711801014 s** modeled lead. Its generated cell lengths stayed below the requested maximum. The automatic driver checks exit-speed combined tire grip as well as the path gates. This is evidence that optional selection can pass its numerical gates on a controlled shape, not a surveyed Formula SAE circuit, measured corridor, calibrated Prius, or predicted Racing Terps advantage. Do not compare its time to the 989 m recorded course.

The full-offset short-demo path exceeded the assumed corridor by **0.0026717805 m** under the 1 m setting, so the model run is skipped and it has no current time, saved run, or replay. The selected 0.975 path has a conservative continuous scalar clearance lower bound of **0.0445441230 m**. An earlier implementation spent a diagnostic lap on an invalid full path and reported **14.4579210447 s**; that was a different grid and force policy and was never an eligible comparison. The prior nominal-2 m example selected a 0.95 path; its numbers are historical for the desktop after the new cell-length control.

At otherwise identical **70% assumed uniform road grip** and the same 1 m limit, the short synthetic Prius comparison remained `candidate_selected`, now at 0.975 strength: eligible baseline **19.8711951482 s**, half offset **18.4359730524 s**, and selected offset **17.1829034123 s**. This shows a tire-capacity sensitivity in the bounded comparison; it is not a calibrated wet-track result.

Before the grip-detour proposal was added, an optional assumed rectangle
**X 36–55 m, Y −3–16 m at 30% of the 100% base** on the same short-course
Prius setup produced an eligible processed
baseline **20.3465718414 s** and selected 0.975 path **17.7554567737 s**.
The rectangle mapped to **32** baseline cells and **33** selected-path cells,
showing that one road location is evaluated separately on each modeled path.
The full-strength geometry still failed the assumed corridor audit and did
not receive a lap time. These are software-model sensitivities under an
invented surface condition under the earlier four-path comparison; they are
not a current five-path detour result or evidence of a general avoidance policy.

For one historical on-demand resolution probe before the exit-speed combined-grip gate, `SpatialTrack.refine(1.0)` preserved the **fixed baseline, old 0.75 fallback, and selected 0.95-offset** cells and curvature boundaries while splitting longer cells. Their refined two-pass laps completed and closed speed: baseline **16.882064565 s**, 0.75 offset **15.000468902 s**, and 0.95 offset **14.551839123 s**. The refined 0.95 numerical lead over 0.75 was about **0.448630 s**. The refined paths' sampled clearance was **not re-audited**, so this probe measures timing sensitivity of fixed paths under an earlier cell-force policy, not renewed eligibility at the refined resolution or formal convergence. Neither this calculation nor the synthetic source establishes real cone clearance.

Both ordinary and AI records identify the selected course by ID and freeze its source metadata separately from the generated solver grid. Imported runs carry the course revision, source geometry hash, canonical bundle hash, and declared source hash; built-ins have no bundle hash. AI records also include source-course label/description, a synthetic flag, and path audits. A candidate-only display after the geometric baseline fails does not establish a comparable gain and is flagged `diagnostic_only` in its primary record.

Both the car and eligible path comparison windows display the selected course
label. The label remains attached to an open comparison when the main course
selection changes.

## Exact method and compute budget

`RacingLinePlanner` in `src/lapsim/optimization/racing_line.py` proceeds as follows:

1. Require a closed `SpatialTrack` and an explicit `TrackCorridor`. Remove the source endpoint's closure error by a distance-proportional x/y correction, interpolate with periodic cubic splines at a nominal **2 m** uniform source-station grid, then apply periodic Gaussian smoothing with default **0.8 m** scale. The desktop's **Cell size (max)** can make the grid finer, and planning repeats at larger sample counts until the generated cells meet that limit or a compute bound stops it. Both timing paths start from the same processed x/y reference. The planner records closure error, maximum preparation shift, and processed versus source station length.
2. Compute a central-difference unit tangent and its left normal. Represent the lateral offset as a **periodic cubic B-spline with 24 control values** by default. The physical candidate point at sample `i` is `p_i = p_reference,i + offset_i normal_i`. The spline's local convex weights make smooth interpolation, but the code still checks corridor limits after optimization.
3. Recompute **every** candidate chord length, cumulative arc length, and signed cell curvature from candidate x/y. For edge vectors `e`, vertex turn `θ_i = atan2(cross(e_{i-1},e_i), dot(e_{i-1},e_i))`; cell curvature is `κ_i = (θ_i + θ_{i+1})/(2 Δs_i)` for candidate chord length `Δs_i`. Consequently `Σ κ_i Δs_i = Σ θ_i`, the polygon's signed heading change, including at the lap seam. That turn identity does **not** make the constant-curvature arc traversed by the lap model meet each saved chord endpoint. Reject a zero-length/folded path, reversed local travel, or nonadjacent segment crossing. The baseline is computed by the same geometry function with all offsets zero. This discrete curvature is a defined numerical approximation, not a fitted tire or steering law.
4. Minimize the cheap geometry objective below with SciPy SLSQP, starting from zero offset. Its default maximum is **60 iterations** and the path grid is capped at **5,000 points**. The objective is multiplied by 10,000 internally to avoid absolute stopping tolerances declaring the very small curvature value unchanged. One geometry candidate emerges from this bounded solve; there is no random search or repeated physics evaluation inside SLSQP.

   ```text
   J = [sum_i (curvature_i^2 * cell_length_i) / path_length]
       + (0.01 m^-2) * (path_length / baseline_length - 1).
   usable_right = -(right_clearance - vehicle_width/2 - safety_margin)
   usable_left  =  (left_clearance  - vehicle_width/2 - safety_margin)
   usable_right <= offset(s) <= usable_left.
   ```

5. Before optimization, reject a corridor whose usable inside offset reaches 98% of a local estimated bend radius at planner nodes or source-cell centers. This guards the normal-coordinate map's tangential Jacobian `1 − κ d` from folding inside the declared corridor. Constrain offset at all planner nodes and midpoints and at every original source-cell boundary and midpoint. A postcheck also solves the cubic polynomial's extrema within **each original source cell**, treating each cell's supplied width as constant. This verifies continuous **offset relative to the processed reference** under that piecewise-width model. It does **not** verify the swept body against surveyed pavement, cones, or unknown boundary shape between source stations.
6. Audit each proposed modeled path before the vehicle lap. When the processed centerline is valid, skip physics for a candidate that already fails clearance or position closure, retaining its trial strength, geometry, audit, and reason. When the processed centerline fails, run the paths as diagnostic-only probes so the team can inspect the inconsistent source case. Independently deep-copy the selected vehicle for each path admitted to the lap model: processed centerline (strength 0), full offset (1), half offset (0.5), and a possible fourth strength. If all three paths have passing modeled-path audits and eligible times, and the half time beats both endpoint times by more than **0.05 s**, fit a convex quadratic through those three times. Use the nearest safeguarded fourth strength from **0.25, 0.375, 0.625, 0.75, 0.875** to its interior minimum. If full fails its modeled-path audit while eligible half beats the baseline by more than the selection margin, screen **0.975, 0.95, 0.9, 0.875, 0.75, 0.625** in descending order with geometry and the same continuous scalar audit. The first audit-valid path with at least **0.02 m additional certified scalar slack** becomes the fourth model trial. Otherwise use **0.75** as fallback. This is a selection buffer beyond the entered width and margin, not measured clearance or a continuous swept-body certificate. Intermediate paths rebuild chord lengths and curvature and check direction and self-intersection; convex offset scaling retains the previously checked lateral bounds. Each admitted physics trial solves path constraints once, makes one dry lap pass to estimate the closed-course seam speed, then makes one recorded lap from a fresh copy of the same initial vehicle and pack state with that explicit start speed. Only the final pass emits Driver view progress and telemetry. Thus the original four-path comparison uses at most **eight full lap-model passes** and fewer when a candidate is screened out. With one assumed rectangle and a valid processed baseline, a lower-exposure detour may add one further audited path and at most two more passes, for **five paths and ten passes** total; ordinary centerline mode still uses one pass. This is a bounded car-specific probe, not machine learning or closed-loop pose control.
7. Before calling a completed time eligible, integrate each path's prescribed constant-curvature cells from the processed path's first point and inferred initial heading. First sample four quarter-cell positions per modeled cell plus every source-corridor boundary and midpoint. Shared boundaries use the narrower neighboring width, including the closed seam. Then certify the *continuous scalar normal-coordinate clearance* of the represented arc between those stations using a conservative second-derivative bound on lateral coordinate `g=(P_arc-R_linear) dot normalize(N_linear)`. For an interval of fractional span `h`, the interpolation error is at most `B h²/8`, where `B` bounds `|g''|` from cell length, curvature, reference-chord length, normal variation, and minimum blended-normal norm. Bisect when this bound cannot establish the supplied piecewise-width limits; reject any interval that remains unresolved at the depth/work cap. Require observed excess at most **1e-8 m** and the worst integrated-path, modeled-polygon, or reference-polygon seam gap at most **0.01 m**. `minimum_corridor_slack_m` is a conservative lower bound for certified paths; the audit reports certification status and unresolved intervals. A completed lap also needs absolute finish-minus-start **speed** at most **0.005 m/s**. A screened candidate has no completed time, record, or Driver view replay; its trial row retains the failed path audit. If the processed baseline fails, neither baseline nor candidate has an eligible comparison time, even if the car completed both; those completed times remain diagnostic. This is a certificate of a stated **scalar normal-coordinate condition** for the represented path and assumed widths. It is not a swept-vehicle, surveyed-boundary, real cone, or pose-tracking certificate.
8. Only when the baseline and a tested nonzero path have eligible times is the best eligible candidate selected for a modeled gain strictly greater than **0.05 s**. The quadratic or clearance screen chooses only where to make the fourth model trial; that trial still needs its own path audit, completed lap, and speed-seam check. A positive gain at or below that provisional margin is an unresolved numerical tie: the baseline stays selected, while the candidate time, replay, and linked run record remain available. The margin is a heuristic informed by observed grid sensitivity, **not** a proven discretization error bound. A nonconverged SLSQP result can still be retained if it is geometrically feasible and improves the stated objective; this is not a global optimum claim.

The shared lap physics now checks combined tire-force capacity at **each curved cell exit** using its exit speed and the held solved drive/brake forces. A full-control profile that exceeds that capacity fails visibly. The automatic torque-profile driver makes a cheap capacity estimate and previews near-limit commands on a car copy, reducing requested torque when necessary; the committed cell still receives an independent force-margin check. This fixes a software counterexample where a coarse circular cell finished at its pure lateral speed ceiling while retaining drive force that the exit tire could not supply. An earlier unconstrained nominal-2 m short Prius AI comparison took **about 2.5 s wall time including planning** at 100% grip and **3.03 s** at 70% in one local measurement; those are not latency estimates for the desktop's 1 m AI grid. This gate improves consistency of the stated cell model; it is not continuous-time tire-force integration or real-car calibration.

The following are **historical one-pass benchmarks from before speed-only seam shooting, the current-cell corner-speed guard, and the exit-speed combined-grip gate**, not current desktop AI times. The ordinary source-curvature lap at 2 m spacing used 495 cells and took about **5.1 s wall time** for a 78.778 s completed Prius benchmark lap on this computer (6 October 2026); the default mode remains one-pass, but the comparable **requested 2 m step** benchmark is now 79.4064453081 s under the updated guard. The desktop initially requests **1 m**. The AI grid is generated separately from x/y and can have a different path length. The GUI's **Cell size (max)** request now bounds generated physics cells for centerline laps, two-car comparisons, and optional AI paths; the historical examples in this paragraph predate its application to AI. After the periodic geometry and winding-curvature correction, a synthetic rounded rectangle and the built-in Prius at torque request 0.8 took **16.784 s** on the processed baseline, **14.267 s** on the full line, and **15.479 s** on the half line. On the shipped course at torque request 1.0, with a *user-assumed* ±2 m corridor, a 1.78308 m vehicle width, and a 0.3 m margin, the Prius processed baseline completed in **87.364 s**; full and half lines took **87.155 s** and **87.162 s**, so full was selected under that earlier policy. At assumed ±2.5 m, full took **87.238 s** and already beat the **87.364 s** baseline, but half took **87.144 s** and was better still. At assumed ±3 m, full took **87.342 s** and half **87.156 s**, so half was selected. With the TREV5 working profile at assumed ±2 m, 1.8 m vehicle width and 0.2 m margin, the baseline was **61.923 s**; full and half took **61.956 s** and **61.925 s**, so baseline remained selected. The earlier three Prius physics passes took about **11.2 s wall time** together; the original four-path AI method can use up to eight passes, and optional patch mode can use ten, so that timing is not its runtime estimate. These historical results show model-sensitive line ranking under the old start policy and corner guard, not a measured track benefit or a current AI selection. The 78.778 s ordinary source-curvature lap is **not comparable** with the 87.364 s x/y-derived baseline as a racing-line gain.

The following completed-lap timings used **speed-only seam shooting** and the current-cell corner-speed guard, but were recorded **before the sampled modeled-path audit and exit-speed combined-grip gate were added**. They are historical diagnostics, not eligible AI racing-line comparisons under the current policy. At assumed ±2 m and torque request 1.0, the Prius geometric baseline took **87.618366 s**, full offset **87.377773 s**, and half offset **87.403816 s**; the old policy selected full on its **0.240593 s** numerical lead. At assumed ±2.5 m, the baseline was again **87.618366 s**, full **87.441030 s**, and half **87.375223 s**; the old policy selected half on a **0.243143 s** numerical lead. The TREV5 working-profile case at assumed ±2 m gave **62.100664 s** baseline, **62.112456 s** full, and **62.091354 s** half. Its **0.009310 s** half-line numerical lead was below the provisional 0.05 s margin. All these tested paths closed seam speed under the 0.005 m/s rule, which alone no longer makes a time eligible. On this computer the three cases took about **11.0 s**, **11.1 s**, and **23.5 s** wall time, respectively, with about **0.7 s** planner work; runtime varies by machine and scenario. These are modeled calculations on assumed corridors, not validation against a surveyed track or team-car laps.

In an earlier unconstrained nominal-2 m API benchmark under the modeled-path geometry audit, the shipped assumed **±2 m Prius** scenario used torque fraction **1.0** (enter 100% in the desktop), a **1.78308 m vehicle width and 0.3 m margin**; these differ from the desktop's initial 1.8 m and 0.2 m fields. Before the exit-speed combined-grip gate, its baseline, full, half, and three-quarter lines completed at **87.618366/87.377773/87.403816/87.3655968872 s**, but all four are **diagnostic and ineligible**. Their sampled usable-corridor excesses are **0.095506/0.908195/0.501981/0.705117 m**, respectively; integrated seam gaps are roughly **0.75–0.77 m**, far above the 0.01 m limit. The failed baseline audit makes the fourth probe fall back to 0.75. Under the current exit-force physics on that same old grid, baseline/full/half/three-quarter diagnostic times were **88.2468936756/88.0083862976/88.0305817762/87.9983373607 s**; none was eligible. They are not the new 1 m desktop-default timings. The comparison rank is `invalid_processed_baseline`: there is **no selected AI winner** and no reported time gain. The desktop marks completed times with `*`, leaves their difference blank, disables **Compare path numbers**, and retains diagnostic Driver view replays and linked run records. The ordinary source-curvature centerline mode remains separate; its modeled time changed with the exit-grip gate. No real surveyed boundary is available for either path.

The earlier **TREV5 working geometry** case at the same assumed ±2 m width (1.8 m vehicle width, 0.2 m margin, torque fraction 1.0) likewise ranked `invalid_processed_baseline`: baseline/full/half/three-quarter completed in **62.1006641048/62.1124557233/62.0913539700/62.0959759770 s**, but each time is diagnostic and ineligible. Full/half/three-quarter sampled excesses were **0.908612549/0.456447888/0.682565568 m**, and seam gaps **0.771628008/0.761433514/0.766570964 m**; the baseline also fails the audit, so the fourth probe falls back to 0.75. The half-strength diagnostic run has the lowest modeled time, but is not a line-selection result. This four-path comparison took about **30.14 s** on this machine.

An earlier on-demand grid check, also before the modeled-path audit, held the generated assumed ±2 m paths fixed and used boundary-preserving `SpatialTrack.refine(1.0)` to split cells without averaging neighboring curvature. The original paths had 495 cells and maximum cell lengths of **2.873–3.368 m**; the refined paths had **1,335–1,344 cells**. Prius full offset retained a numerical lead: **0.240593 s** on the original grid and **0.236265 s** on the refined grid. TREV half offset had a **0.009310 s** numerical lead on the original grid, but the refined baseline beat half by **0.001388 s**. All refined paths completed and closed speed at the seam. TREV's old numerical ranking was grid sensitive; none of these figures establishes eligibility under the new path audit. The refined two-pass trials took about **9.5 s** per Prius path and **20 s** per TREV path on this computer, so this check stays outside default operation. Earlier global-grid resampling also reversed TREV's ranking but averaged across curvature boundaries. Neither check is a formal convergence study or measured validation.

The objective is minimum **mean squared curvature with a length penalty**, not minimum lap time. The curvature term has units `m^-2`; therefore the coefficient of relative length is a numerical weight with units `m^-2`. Its geometry does not use car mass, drive layout, aero, tire map, or battery while optimizing. Those enter during the bounded full-model comparison, which can choose full, half, or the tested fourth offset (0.75 on fallback), an optional patch-mode grip detour, or the geometric centerline for that car and torque request **only after the modeled-path audit passes**. A failed geometric offset path is not timed when the baseline is valid; an independently proposed detour may still be audited and timed. This is coarse vehicle adaptation, not continuous minimum-time optimization. The main lap model assumes a flat, still-air path and uses the user-assumed base grip factor for both longitudinal and lateral tire capacity in the prepass and cell model. Uniform mode applies it to every cell. Optional rectangle mode creates a path-specific, world-fixed low-grip schedule before each trial, so the full-model trial selection can respond to one local surface assumption. The original minimum-curvature proposal does not use the patch, while the separate bounded detour proposal can shift around its nominal wheel contacts, and the model still cannot represent grade, main-lap wind, tire temperature, or traffic.

An offline **one-pass** strength probe illustrates the numerical-resolution limit of choosing a line from very small time gaps. On the assumed ±2 m Prius case, strength 0.75 beat strength 1.0 on an approximately 2 m solver grid (**87.130291 s** versus **87.155418 s**), but their order reversed on an approximately 1 m grid (**86.841115 s** versus **86.806429 s**). A TREV probe similarly reversed strength 0.25 versus baseline. These are model/grid sensitivity checks under the earlier start policy, not current AI times or measured-car validation. The current bounded policy tests 0, 1, and 0.5 first; its one fourth strength comes from an eligible quadratic, an audit-screened stronger path after an invalid full path, or the 0.75 fallback. It still cannot resolve hundredth-second gains without a resolution study. The current 1 m synthetic 0.975 selection has a much larger lead, while the older assumed fused-course strength probe remains a caution about small numerical differences.

The dry pass starts at the cyclic braking ceiling; its exit speed seeds the recorded pass for that same path. Each pass begins with a fresh copy of the initial car and pack, so charge and other internal states are **not** made periodic. The recorded pass must close speed within 0.005 m/s **and** pass the continuous scalar modeled-path audit to receive an eligible comparison time. Every completed AI trial record saves its actual explicit starting speed, entry/exit speeds, and seam-speed difference, including when its time is only diagnostic. A historical, pre-exit-grip ordinary-centerline Prius audit at 0.8 torque request started at 13.2725 m/s and finished at 9.4656 m/s; it was a one-pass initial-condition result. Speed-only closure is a limited numerical boundary condition, not a full-state steady endurance lap or evidence that a real car would hold this line.

An **in-memory biarc prototype** was explored as a way to make every constant-curvature solver arc connect the intended x/y endpoints. It achieved position coherence to roughly **1e-9 m**, but took **2.2–2.5×** the current runtime and shifted modeled times by **5–7 s** because it introduced curvature spikes. It was deferred and is **not merged or used by the simulator**. A replacement path representation needs coherent x/y, curvature, station length, and smooth enough curvature for stable physics before its time rankings can be trusted.

A separate unmerged **one-circular-arc-per-edge** experiment used an odd 991-cell path and closed its integrated geometry to about **2e-11 m**. Its larger peak absolute curvature and adjacent curvature jumps shifted one-pass model times by **5–7 s**, reversed a TREV numerical ranking, and used about **2.5×** the compute. Exact position closure alone therefore did not make it a suitable course repair. It needs course review, curvature regularity and resolution checks, and independent vehicle validation before any competition-line claim.

## Driver view and timed-session boundary

The implemented **Driver view** displays accepted physics-cell progress during a solve and then plays the completed lap's telemetry against a **reference path** in a top-down, car-fixed viewport. An optional immutable `LapProgressSnapshot` is emitted only after a cell passes the solver checks; it carries elapsed time, station, speed, lateral acceleration, and cell indices. The desktop coalesces intermediate events in a one-slot queue and sends at most about 10 updates per second to Tk. During path preparation, dry speed passes, or a pause after accepted cells, it shows a static labeled source-course map with the start marked and an explicit **NO VEHICLE POSE** label. Accepted-cell values remain in their boxes but no moving pose is inferred in those gaps. It labels baseline/full/half and fourth AI trial phases separately, using three-quarter for the 0.75 fallback and car-adaptive otherwise; an optional fifth patch-mode phase is labeled grip-aware detour. If a run stops, the last accepted step stays identified as such. During accepted physics progress, the triangular marker stays fixed while the path rotates with its map tangent. Ordinary centerline laps and A/B car comparisons use the exact solver-grid x/y saved with their runs, matching live progress; each AI trial uses its own processed solver path. The separate Analysis course plot continues to show source x/y. Completed-run replay offers play/pause, start, time scrub, playback rate, and wheel zoom. The **Replay lap** menu switches among every completed geometric baseline, full, half, fourth, and optional grip-detour AI trial, including audit-failed diagnostic runs labeled as such, using each run's exact processed track and saved telemetry without rerunning physics. It also switches A/B laps after a two-car comparison. The menu is disabled when only one completed lap is available. Recorded cell exit time, distance, and speed are interpolated with the solver's constant-acceleration relation, reconstructing the initially unrecorded entry speed; inconsistent imported telemetry falls back to linear distance interpolation. Map positions and heading come from the displayed solver-grid x/y, while speed and lateral acceleration come from physics. The main solver integrates prescribed curvature and does not guarantee that its internally integrated x/y coincides with the separately fused plotted centerline. This is a **live accepted-step reference-path preview and completed-lap playback**, not the simulated vehicle pose, actual steering behavior, a true first-person camera, or collision detection.

The fixed **Calculation progress** strip reports actual processed cells in
the local corner-limit preparation phase and accepted cells in the current
recorded lap. It names the cyclic braking pass and its processed cells but
remains indeterminate until convergence; dry seam-speed probes and path
planning likewise have no reliable total-work percentage. These counters
do not estimate total AI completion time, and no vehicle pose is shown while
the path-speed limits are being prepared.

The Driver view's monochrome **cell model values** boxes expose accepted
torque and brake requests, achieved drive/friction/regen forces, longitudinal
acceleration, signed battery power, and the next-entry braking ceiling for
either driving mode. Live boxes show the last accepted cell; completed replay
holds the active cell's saved values and does not add solver passes. Missing
or unaligned legacy channels show a dash. The ceiling alone is not the
controller's full speed target; the current-cell corner limit also applies.

The separate **Timed sessions · WIP** tab offers a short synthetic pose preview
described below and can save/load that short trace with numerical replay.
Its future contract still calls for a versioned Terps vehicle and controller,
a timed session against a ghost, **complete-session** controls/states/environment
capture, a comparison report, and replay through the engineering model with
declared tolerances. The programmatic `replay_lap_record` checker reproduces a
completed v2 one-lap record's accepted-cell commands on its saved solver grid;
it is separate from this preview and from a full session workflow. The lap
event requires both steering-requested and tire-achieved curvature to match
the prescribed cell curvature within `EnduranceRunConfig.path_curvature_tolerance_per_m`
(default **1e-9 1/m**) before accepting a cell. This scalar gate cannot show
that the integrated pose followed the displayed x/y or cleared cones.

AI runs save the primary displayed run's exact solver geometry and full result telemetry in a content-hashed lap record. Its optional `settings.path_planning` also stores source and processed geometry audits, assumed corridor and vehicle clearance, continuous scalar path audit and eligibility status, eligible versus diagnostic times, planner version/settings, the `periodic_cubic_minimum_curvature_slsqp_v7_continuous_scalar_clearance` algorithm ID and `fourth_strength_policy`, each evaluated candidate strategy/nullable strength/time/error, path lengths, actual maximum generated cell length, and compute timings. The existing `settings.solver.requested_maximum_cell_length_m` field now receives the user request for these generated paths; `path_planning` separately records the actual maximum generated cell, nominal planning setting, and effective sample count/spacing. Every completed trial record also retains its own requested and measured maximum. Every path that completes a model lap has its own content-identified record with exact solver geometry, telemetry, and explicit final-pass start speed, for at most four path records without a patch or five when one detour reaches the model. A candidate screened out before physics remains in the trial manifest with `record_role=no_run`, no run ID or time, and its failed audit and skip reason. The primary record's `baseline_record` and `candidate_trials[]` identify its own path by `record_role=selected_result` and link the other saved paths by `run_id`; the existing `comparison_counterpart_run_id` remains available. Linked trial records contain only their own planning/audit metadata, so content-derived IDs do not refer back to the primary ID. An extra trial interrupted before completing keeps its summary without a replayable record. On an audit-failed shipped course, no record is a selected racing-line winner: the primary record is flagged diagnostic, though completed runs can be replayed for investigation. Read `candidate_trials[].strategy`, nullable `offset_strength`, audit, and eligible or diagnostic time to distinguish the fourth geometric strength from an optional `grip_detour` trial. The detour's strength is null, and trial order does not imply a fixed 0.75 or an eligible gain. Each completed v2 file with complete accepted-cell controls can be checked independently by `lapsim.experiments.replay_lap_record`; it compares selected summary and trace outputs with declared tolerances and reports source/runtime provenance separately. A file hash checks integrity, not model agreement or path feasibility. There is no one-click engineering replay or ghost/session workflow. A source hash is not a survey certificate.

For numerical QA, `SpatialTrack.refine(maximum_cell_length_m)` subdivides the already generated solver cells while retaining their original boundaries and piecewise-constant curvatures. It preserves each source cell's signed turn and length-weighted squared curvature, unlike global distance resampling that can average across curvature changes. It is an on-demand diagnostic tool with a 100,000-cell cap, not a new default for the AI planner or desktop solver. Results still need a resolution study; retained curvature does not eliminate speed-envelope and integration discretization error.
Its interior x/y points are interpolated along each old chord; this unchanged
QA method neither performs analytic subarc subdivision nor certifies that x/y,
stations, and curvature agree.

`diagnose_paired_grid_stability` in `optimization/grid_stability.py` packages
a bounded, opt-in paired timing check for already eligible baseline and
candidate paths. It preflights each refined grid against 5,000 cells, reruns
the same selected car and start policy on both fixed paths, and reports whether
the candidate-minus-baseline sign or 0.05 s margin crossing changes. The
desktop's **Check finer grid (optional)** action uses the frozen effective
pre-run car and enables for two eligible completed paths on either uniform
road or the assumed rectangular-patch setting; its worker can add at most
four lap-model passes. For a patch trial, the checker maps the same world-fixed
rectangle independently onto each refined baseline and candidate path. It
freezes each original path's modeled entry heading when refining, because
interpolated x/y chords can otherwise change the mapper's automatic heading
choice. A failed refined road mapping returns a non-completed diagnostic.
When a completed report finds either a sign change or a crossing of the
provisional 0.05 s selection margin, the main AI headline and status mark the
modeled ranking **grid-sensitive; unresolved**. The original-grid path,
numbers, and saved trial records remain in place; a stable report leaves the
headline unchanged, and stale or non-completed reports do not add this warning.
The API's separate explicit per-cell grip mode repeats each original cell's
value through its subdivisions; that is **not** world-fixed remapping. The API
rejects combining explicit per-cell tuples with a world-fixed road. The
check reports sensitivity without changing the selection, re-auditing
corridor clearance, proving convergence, or validating the assumed road.
Ordinary centerline and AI runs incur no finer-grid work.

## Bounded synthetic pose-aware driver experiment

`src/lapsim/optimization/pose_driver.py::run_pose_driver` runs the coherent
rounded rectangle through the **separate time-domain four-wheel model**, with
actual planar x/y, heading, body velocity, yaw rate, and four wheel speeds.
The WIP tab can launch an **80 m** preview with either uniform assumed base
grip or an assumed **0.3×** rectangular road-grip patch at synthetic world
`x=36..55 m`, `y=-3..16 m`. The selected scenario stays visible during the
calculation and replay. Driver view uses the simulated x/y and heading in
both phases. Neither setting represents a measured dry or wet surface. This
controller does not steer the distance-domain endurance car, use the selected
Prius/TREV profile, or produce an engineering lap time or battery energy. Its
model-time duration is one finite synthetic maneuver, not a closed lap.
In completed replay, steering and torque/brake commands are held from their
recorded control interval. The box labeled **GRIP SAMPLE (×)** uses the latest
recorded pose sample, including the final sample after the last control.
Interpolated display geometry and this sampled grip add no physics step.

When a pose run stops with `road_domain_invalid`, its local-grip value may be
the base-road diagnostic fallback for a query outside the declared road
domain; the Driver view and status warn that it is not valid road data.

At each **0.05 s** control step, a local projection first finds the CG's
station and sampled corridor slack, then finds the rear axle's station for
pure-pursuit steering. With body speed `speed = sqrt(u² + v_body²)`, the
lookahead distance is `min(30 m, half the track length,
2.5 m + (0.45 s) speed)`; the target is that distance ahead
along the reference. For target bearing error `alpha`, wheelbase `L`, and
rear-axle-to-target straight-line distance `D` (floored at **0.5 m**), the
implemented kinematic steering command is
`delta = atan2(2 L sin(alpha), D)`, clipped to **±0.30 rad**. The speed target
is the lesser of **5.5 m/s** and every preview sample's allowed speed. The
controller samples path curvature and the environment's road multiplier at
the nominal path CG and four wheel centers ahead for at most **60 m**, half a
lap, and **121 points**. For each sample at distance `d`, it computes
`v_corner² = min(4 m/s², 0.35 mu min(grip_now, grip_at_d) g) /
max(|kappa_at_d|, 1e-9 1/m)`. It limits deceleration to
`a_brake = min(0.20 mu min_grip_ahead g,
4 T_brake,max / (mass wheel_radius))` and sets
`v_allowed(d) = sqrt(v_corner² + 2 a_brake max(d - margin, 0))`, with
`margin = 1 m + (0.45 s) speed + front_axle_distance`. Proportional requests
drive both rear wheels or brake all four. This is a bounded control heuristic:
its nominal future wheel positions can differ from the later driven path, and
it neither proves friction-circle feasibility nor detects a patch narrower
than the sampling. The lower-grip case asks for braking before its first
low-grip wheel contact in the regression scenario.
The steering geometry follows [Coulter's pure-pursuit derivation](https://publications.ri.cmu.edu/implementation-of-the-pure-pursuit-path-tracking-algorithm).
The [TORCS steering tutorial](https://torcs.sourceforge.net/api/robot_tutorial_chapter_4.html)
likewise distinguishes distance measured along the reference from the direct
vehicle-to-target vector. Its [speed-control chapter](https://torcs.sourceforge.net/api/robot_tutorial_chapter_3.html)
motivates checking future bend speeds against available braking distance.
This is a basic feedback experiment, not a learned
driver or an implementation of those projects' complete controller stacks.

After the future bend/grip target, an assumed-edge rule can only lower that
target. Let `s` be the current minimum projected slack of the four sampled
axle-span body corners inside the assumed corridor. It subtracts **0.5 s**
times outward CG lateral speed relative to the reference tangent, plus a
conservative yaw-rate/body-corner contribution, and clamps the predicted
slack at zero. It blends between `min(prior target, 2.0 m/s)` at zero predicted
slack and the prior target at **0.8 m** predicted slack using the square root
of the slack fraction. This speed response is specific to LapSim. The
[TORCS steering tutorial](https://torcs.sourceforge.net/api/robot_tutorial_chapter_4.html)
motivates checking car corners and reducing speed near a road edge, but it
uses its own edge rule and warns that current corner samples do not prove
swept clearance. LapSim's corridor is an assumed reference-path width, not
TORCS road-edge data or measured Racing Terps cones.

The WIP tab's **Initial lateral offset (m)** starts the car at
`(x_ref,y_ref) + e_0 (-sin(psi_0), cos(psi_0))`; positive `e_0` is left of
travel, negative is right, and the default is zero. The input accepts finite
values within the nominal **±1.9 m** CG allowance and is frozen for the
worker; changing it while idle clears an old pose preview only. The actual
four-corner footprint check remains authoritative: a nominally accepted
**−1.9 m** start on this curved synthetic start is already outside the
sampled assumed corridor and stops before a control step. The edge rule is a
slowdown heuristic, not a geometric steering or safety certificate. In the
focused synthetic runs, starts at **±1.8 m** reached 80 m on both uniform and
patch roads with positive sampled slack and replay agreement. The same
starts without the edge cap also completed and had the same minimum sampled
slack, which occurred initially; the cap's observed effect was more braking
and longer model time, not a demonstrated safety gain. One deliberately long
**3.0 s** lookahead regression with a **+1.8 m** start and extended
**25 s / 500-control-step / 80,000-substep** budget is a bounded
counterexample: the nominal edge rule reached 80 m with positive sampled
slack, while a virtually inactive edge rule left the assumed corridor near
40.64 m. Both traces replayed numerically. This demonstrates an effect in
one synthetic setting, not a general prevention of road exits.

Default limits are **80 m** target progress, **20 s** simulated time,
**400** control steps, and **60,000** internal integration substeps. The
assumed ±3 m corridor, 1.8 m vehicle width, and 0.2 m margin give a
**1.9 m** nominal CG offset allowance. The run checks a projected rectangle
between the axle lines at each output sample and stops if its assumed
boundary slack turns negative or the declared road domain is invalid. That
sampled geometry excludes overhangs and does not certify the swept body
between samples or clearance to measured cones. The recorded `PoseDriverRun`
holds the issued controls, time grid, planar states, evaluations, and status
in memory. `replay_pose_driver` reintegrates those controls and compares every
saved state using `PoseReplayTolerances`: **1e-8 m** position, **1e-8 rad**
heading, **1e-8 m/s** body velocity, **1e-8 rad/s** yaw rate and wheel speed.
It also recomputes pose-sample time, station, tracking error, grip, assumed
footprint slack, projection validity, road validity, and stop status. This
checks numerical reproduction of a
synthetic trace; it is not a full session, ghost, or vehicle validation.

The projection scans **cells whose station intervals overlap** the local
window rather than only cells whose midpoints fall inside it. It considers
the overlapping closed-lap copies needed at the seam and clips the
projected point to the window, so a long cell or the seam does not
disappear from the search.
By default, a coherent source with cells longer than **0.5 m** is
validated and analytically subdivided with `SpatialTrack.refine_arcs(0.5)`;
this keeps source boundaries and exact straight/circular-arc geometry under
the **100,000-cell** refinement cap. The desktop pose preview also reads
**Cell size (max)** from Calculate: finer requests analytically subdivide
the shipped 0.5 m source before the worker starts, while coarser requests
retain the finer source. The requested and effective grid are displayed,
and the desktop refuses more than 5,000 pose cells. The controller still
projects to short **x/y chords** and checks
the axle-span body corners only at output samples; this is not continuous
geometry or swept-body clearance. An explicit `sampled_polyline` reference
mode can instead follow the AI planner's closed x/y polygon. It validates
nondegenerate chord/station geometry, subdivides long chords without
changing their source vertices, and estimates bend severity from chord
headings one fixed metric interval before and after each speed-preview
station. The fixed window avoids changing its corner estimate merely by
inserting collinear solver cells. This mode is a separate
synthetic pose experiment; it does not make the main distance-domain AI lap
a tracked car trajectory or a measured-corridor result.

The WIP desktop keeps the coherent 80 m pose preview as its default. After
the synthetic demo course produces an eligible, faster selected AI candidate,
an additional button can drive that exact selected polygon for 80 m with
the separate synthetic four-wheel car. An audit-failed, unranked, or slower
candidate does not unlock it. The path is frozen and subdivided to the
smaller of the entered Cell size (max) and 0.5 m under a 5,000-cell UI cap;
the saved pose trace records its sampled-polyline mode. The selected
Prius/TREV vehicle does not become the pose car, and the WIP road scenario
is independent of any main AI trial grip schedule. A planner-produced
206-cell synthetic candidate reached 80.1475 m in 14.75 s of pose-model
time with 0.17404 m maximum absolute tracking error and 1.70328 m minimum
sampled assumed footprint slack. Recorded-control replay and schema-v2
save/load passed. These are synthetic tracking diagnostics, not a measured
racing-line gain or full Formula SAE lap.

`PoseRunRecord.capture(run)` writes a separate **schema-v2 synthetic pose
record** through `save(path)`; `PoseRunRecord.load(path)` reconstructs and
checks it. It freezes the exact processed track, reference-geometry mode,
synthetic car, road and
patches, settings and controller identity, held controls, every boundary
time/state, pre-step dynamics evaluations, pose samples, status, and runtime
and source identity. A SHA-256 content ID detects content changes unless
the ID is recalculated; load also rejects unknown fields, malformed or
oversized JSON, misaligned traces, inconsistent starting pose, changed
evaluations, and numerical recorded-control replay mismatches.
Schema-v2 capture/load also reconstructs each controller decision from the
saved pose, settings, reference, and road. A record whose controls disagree
with that declared controller is rejected even when its recorded-control
dynamics replay still passes. `controller_report` exposes the number of
commands checked and maximum steering and torque differences; it is `None`
for legacy schema-v1 records, which retain their original dynamics-only gate.
No controller choice is attested for a zero-control stop.
Recomputed evaluation floats
allow at most `1e-9` absolute or `1e-10` relative difference through the
standard closeness rule; evaluation field names, array lengths, material
IDs, and other discrete values must match exactly. Pose states and path
diagnostics keep their separate `PoseReplayTolerances` gate. A stopped
trace with zero controls is valid if its initial status and samples agree.
Earlier schema-v1 coherent-arc records remain loadable with the original
controller identity and default mode. The WIP tab's
**Save last synthetic trace…** and **Load synthetic trace…** controls do this
work in a worker and show loaded trace playback. This archive is isolated
from v2 endurance-lap records and cannot be ranked as a full timed session
against a ghost. Source fingerprints are provenance metadata; loading does
not require the installed code to match them byte for byte, so the numerical
replay result should be reviewed alongside that identity.

## Acceptance and iteration checks

| Check | Required evidence |
|---|---|
| Default unaffected | Centerline remains selected after launch and does not call optimizer code |
| Source-width frame | V2 source-cell widths and provenance remain tied to source geometry; planner uses the explicit assumed corridor until a checked frame transformation exists |
| Geometric validity | Continuous spline offset respects piecewise supplied widths after vehicle width/margin; closed path has finite positive cells, periodic geometry, no detected self-crossing |
| Modeled-path validity | Initial quarter-cell/source-boundary samples and bounded interval checks certify continuous scalar normal-coordinate clearance to 1e-8 m for the represented curvature path; unresolved bounds fail, and the integrated path and both saved polygon endpoints must close within 0.01 m. This is not swept-body certification |
| Fair A/B | Eligible geometric centerline and AI path share source x/y preparation, car, controller request, one declared world-road scenario, and solver settings; a local rectangle is remapped to each path's own modeled geometry |
| Robust selection | Only completed, speed-closed, modeled-path-audited laps can win; a failed candidate audit skips physics when the baseline is valid, invalid completed runs remain diagnostic, and eligible gain must exceed 0.05 s |
| Bounded cost | SLSQP iteration cap and 5,000-point path cap; four ordinary AI paths use at most eight full lap passes, while one assumed patch can add up to 12 cheap detour geometries and one two-pass lap trial, for five paths and ten passes total; report elapsed wall time |
| Traceability | Record selected path geometry, source hash, corridor assumptions, planner settings/version, selected profile and effective car, and run ID |
| Car adaptability | Repeat on built-in and saved profiles without assuming one motor topology; reject unsupported or failing profile scenarios explicitly |
| Presentation | Show a simple top-down line/driver preview, numbers, and explicit “synthetic corridor” labeling |
| Pose preview | Bound work and progress, show simulated pose with a separate model/time label, compare replayed states within stated tolerances, and retain the WIP session boundary |
| Synthetic trace archive | Freeze exact pose inputs, controls, states, evaluations, status, and code identity in a content-identified schema; reject corrupted or numerically inconsistent records, including zero-step stops |

The end-to-end profile check in `tests/test_ai_profile_e2e.py` selects the
partial source-backed TREV working profile (when its local source bundle is
available) and, separately, a locally saved Prius with user overrides. It
starts the desktop's optional AI worker on the analytic demo course, inspects
the selected effective vehicle and exact solver path in each saved JSON,
shows that path in Driver view, and checks recorded-control model replay.
This checks profile-to-result wiring and reproducibility, not real-car lap
accuracy or a measured course.

Further development should be driven by failed checks and team data. Measured track boundaries, cone positions, tire limits, and synchronized vehicle logs are higher priority than a more complex learned policy. A future team-car closed-loop controller can then be compared against this simple planner without changing the default engineering baseline; the bounded synthetic pose preview is an isolated first step.

## Primary references used for the design

- [TUM FTM global racetrajectory optimization](https://github.com/TUMFTM/global_racetrajectory_optimization/blob/master/Readme.md) separates shortest-path, minimum-curvature, and full minimum-time approaches and represents track widths relative to a reference line and normals. Minimum curvature is a useful inexpensive proxy, not a promise of minimum lap time.
- [TUM FTM variable-friction minimum-time implementation](https://github.com/TUMFTM/global_racetrajectory_optimization/blob/master/opt_mintime_traj/Readme.md) shows why wheel-specific friction can change the optimal line; its double-track, nonlinear collocation/IPOPT solve is outside this desktop's compute and data budget. LapSim's scalar exposure screen is an approximation, not that optimizer.
- [Kapania, Subosits, and Gerdes, *A Sequential Two-Step Algorithm for Fast Generation of Vehicle Racing Trajectories*](https://ddl.stanford.edu/sites/g/files/sbiybj25996/files/media/file/2015_dscc_kapania_sequential_2step_0.pdf) alternates a friction-limited speed pass with a bounded path update and checks the resulting lap time. Its simplified vehicle model and no-global-optimum result limit transfer to a Formula SAE car.
- [Jain and Morari, *Computing the racing line using Bayesian optimization*](https://arxiv.org/abs/2002.04794) uses sparse lateral offsets and actual fixed-path lap-time scoring. LapSim borrows the sparse-proposal/score separation, but its bounded detour is deterministic and has no Gaussian-process search; that paper's experiments used miniature cars.
- [Coulter, *Implementation of the Pure Pursuit Path Tracking Algorithm* (CMU-RI-TR-92-01, 1992)](https://publications.ri.cmu.edu/implementation-of-the-pure-pursuit-path-tracking-algorithm) gives the geometric basis for the short pose-driver steering preview.
- [Xue, Yue, and Dolan, *Spline-Based Minimum-Curvature Trajectory Optimization for Autonomous Racing* (2023)](https://arxiv.org/abs/2309.09186) motivates low-dimensional spline geometry when detailed vehicle and track dynamics data are limited. LapSim implements its own planner; its bounded car-specific timing trials are an extension here, not a reproduction or validation of that paper.
- [TUM FTM trajectory planning helpers](https://github.com/TUMFTM/trajectory_planning_helpers) documents the boundary/corridor geometry and splined racing-line preparation used in that research software. We use the ideas, not its LGPL-3.0 implementation code.
- [TORCS robot tutorial: driving on a track](https://torcs.sourceforge.net/api/robot_tutorial_chapter_4.html) illustrates the game-bot separation of target line, lookahead steering, speed feedback, and edge checks; it warns that cutting across corners can make a nominally faster lap invalid.
- [TORCS robot tutorial: speed control](https://torcs.sourceforge.net/api/robot_tutorial_chapter_3.html) shows curvature-limited target speed and backward braking logic, which are conceptually similar to LapSim's existing path speed envelope.
