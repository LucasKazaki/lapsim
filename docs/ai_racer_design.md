# Optional racing-line planner: implementation and evidence

**Audience:** Racing Terps vehicle and software leads.
**Date:** 6 October 2026.
**Status:** experimental, deterministic path planner; the original centerline lap remains the default.

## What is implemented

The desktop offers **Centerline (default)** and **AI racing line (experimental)**. The second option is an offline minimum-curvature path planner, not machine learning or a closed-loop driving agent. It has access to the selected car model when comparing completed laps, and it uses the same lap physics for its processed geometric centerline and proposed path. The default button neither imports nor runs the optimizer. The planner does not steer a simulated vehicle, sense cones, react to another car, or learn from experience.

The UI requires one assumed uniform half-width for both sides, plus vehicle width and safety margin. The planner API also accepts **different left and right clearances for every source cell**, with an explicit source label. Each side must be wider than half the vehicle width plus margin. In the shipped desktop course, no measured widths are available, so the entered numbers are a hypothetical corridor. The user-facing result states which completed path was selected, both available lap times, their difference, length, maximum lateral offset, assumed dimensions, and the discrepancy between source station length and processed x/y length. An invalid or slower candidate retains the geometric centerline. A candidate may be displayed if it finishes and its geometric baseline does not, but that is explicitly **not** called a time improvement.

## Why the shipped track needs an honest comparison

`analysis/data/track/gnss_imu_endurance_track.csv` contains 989 m of distance-indexed curvature for the current solver, but its separately fused x/y drawing does not form the same numerical path. A read-only audit of the committed file found about **1,012.35 m of x/y chord length**, 0.760 m endpoint mismatch, and about 6.09 rad accumulated heading change from x/y versus about 3.66 rad integral of the saved curvature. This is much larger than rounding noise. The track has no measured left/right cone boundary or width. Its metadata describes a fusion of registered schematic geometry and corrected IMU curvature, not a geometrically consistent surveyed corridor.

Consequently, AI mode rebuilds both a **geometric centerline baseline** and its candidate from the same x/y preparation method. It does not compare the source-curvature default lap time directly with a shifted x/y path: that would mix two different numerical tracks. A user-entered width here is an **assumed scenario**, not proof a line fits the real course. Track data reconciliation and surveyed widths are necessary before team setup decisions rely on an AI advantage.

## Exact method and compute budget

`RacingLinePlanner` in `src/lapsim/optimization/racing_line.py` proceeds as follows:

1. Require a closed `SpatialTrack` and an explicit `TrackCorridor`. Remove the source endpoint's closure error by a distance-proportional x/y correction, interpolate at an approximately **2 m** uniform source-station grid, then apply periodic Gaussian smoothing with default **0.8 m** scale. Both timing paths start from this identical processed x/y reference. The planner records closure error, maximum preparation shift, and processed versus source station length.
2. Compute a central-difference unit tangent and its left normal. Represent the lateral offset as a **periodic cubic B-spline with 24 control values** by default. The physical candidate point at sample `i` is `p_i = p_reference,i + offset_i normal_i`. The spline's local convex weights make smooth interpolation, but the code still checks corridor limits after optimization.
3. Recompute **every** candidate chord length, cumulative arc length, and signed three-point curvature from candidate x/y. At a vertex, the curvature estimate is `2 cross(e_previous,e_next) / (|e_previous| |e_next| |e_previous+e_next|)`; neighboring vertex estimates are averaged for each solver cell. Reject a zero-length/folded path, reversed local travel, or nonadjacent segment crossing. The baseline is computed by the same geometry function with all offsets zero. This discrete curvature is a defined numerical approximation, not a fitted tire or steering law.
4. Minimize the cheap geometry objective below with SciPy SLSQP, starting from zero offset. Its default maximum is **60 iterations** and the path grid is capped at **5,000 points**. The objective is multiplied by 10,000 internally to avoid absolute stopping tolerances declaring the very small curvature value unchanged. One geometry candidate emerges from this bounded solve; there is no random search or repeated physics evaluation inside SLSQP.

   ```text
   J = [sum_i (curvature_i^2 * cell_length_i) / path_length]
       + (0.01 m^-2) * (path_length / baseline_length - 1).
   usable_right = -(right_clearance - vehicle_width/2 - safety_margin)
   usable_left  =  (left_clearance  - vehicle_width/2 - safety_margin)
   usable_right <= offset(s) <= usable_left.
   ```

5. Constrain offset at all planner nodes and midpoints and at every original source-cell boundary and midpoint. A postcheck also solves the cubic polynomial's extrema within **each original source cell**, treating each cell's supplied width as constant. This verifies continuous **offset relative to the processed reference** under that piecewise-width model. It does **not** verify the swept body against surveyed pavement, cones, or unknown boundary shape between source stations.
6. Independently deep-copy the selected vehicle for a processed-centerline lap and, if a valid geometric candidate exists, one candidate lap through unchanged `run_one_lap`. At most **two full lap-model invocations** occur. Keep the candidate only when **both** laps complete and the candidate is faster. A nonconverged SLSQP result can still be retained if it is geometrically feasible and improves the stated objective; this is not a global optimum claim.

The ordinary source-curvature lap at 2 m spacing used 495 cells and took about **5.1 s wall time** for a 78.778 s completed Prius benchmark lap on this computer (6 October 2026). The AI grid is generated separately from x/y and may have a different path length and maximum cell size; the GUI's solver-step box applies to the **default** mode. The wall time is a local benchmark, not a guaranteed runtime elsewhere. For a synthetic rounded rectangle and the built-in Prius at a fixed 0.8 torque fraction, a focused software check observed **16.77 s** on the processed baseline and **14.23 s** on the candidate. On the shipped course with a *user-assumed* ±2 m corridor, a 1.78308 m Prius width, and a 0.3 m margin, the processed geometric baseline completed in **87.168 s** and the candidate in **86.984 s**. Wider assumed ±3 m and ±5 m cases produced slower candidates that fell back to the geometric baseline. These results establish that the selection gate can find and reject candidate paths in modeled scenarios, not that the line is fastest possible or improves an on-track car. The 78.778 s ordinary source-curvature lap is **not comparable** with the 87.168 s x/y-derived baseline as a racing-line gain.

The objective is minimum **mean squared curvature with a length penalty**, not minimum lap time. The curvature term has units `m^-2`; therefore the coefficient of relative length is a numerical weight with units `m^-2`. Its geometry does not use car mass, drive layout, aero, tire map, or battery while optimizing. Those enter only during the final two lap solves. Consequently the proposal can be slower for another car or condition and the time comparison is the required selection gate. The main lap model currently assumes flat, uniform, still-air conditions; this feature cannot adapt to weather, surface patches, grade, tire temperature, or traffic that the lap model does not represent.

## Driver view and future timed-session tab

The implemented **Driver view** plays a completed lap's telemetry against the selected **reference path** in a top-down, car-fixed viewport. It shows time, distance, speed, lateral acceleration, and map heading in simple number boxes; controls include play/pause, start, time scrub, playback rate, and wheel zoom. The triangular vehicle marker stays fixed while the path rotates with its map tangent. Default runs use the source x/y map; AI runs use the exact selected processed path. The position and heading are interpolated from the displayed x/y map by solved distance, while speed and lateral acceleration come from the physics telemetry. The main solver integrates prescribed curvature and does not guarantee that its internally integrated x/y coincides with the separately fused plotted centerline. Thus this is **reference-path playback**, not the simulated vehicle pose, actual steering behavior, a true first-person camera, or collision detection.

The separate **Timed sessions · WIP** tab states a future contract: select a versioned Terps vehicle and controller, run a timed session against a ghost, save full controls/states/environment, generate a comparison report, and replay through the engineering model with stated tolerances. It currently contains a scope description and unavailable/disabled controls. Current lap records and four-wheel records provide pieces of the evidence architecture, but they do not form that end-to-end workflow.

AI runs save the selected solver path's exact geometry in the normal content-hashed lap record. Optional `settings.path_planning` also stores the source-geometry hash, assumed corridor and vehicle clearance, planner version/settings, the two lap times or failures, selection status, path lengths, actual maximum generated cell length, geometry discrepancy, constraint violation, and compute timings. The existing `settings.solver.requested_maximum_cell_length_m` field receives that actual maximum for these generated paths; the nominal 2 m planning grid is recorded separately. This is enough to audit the scenario's declared inputs and result. The record does not embed the unsaved baseline telemetry as a linked comparison, and a source hash is not a survey certificate.

## Acceptance and iteration checks

| Check | Required evidence |
|---|---|
| Default unaffected | Centerline remains selected after launch and does not call optimizer code |
| Geometric validity | Continuous spline offset respects piecewise supplied widths after vehicle width/margin; closed path has finite positive cells, periodic geometry, no detected self-crossing |
| Fair A/B | Geometric centerline and AI path share the same source x/y preparation, car, controller request, and solver settings |
| Robust selection | Only completed valid laps can win; failure or no improvement returns baseline with an explanation |
| Bounded cost | SLSQP iteration cap, 5,000-point path cap, and at most two full solver calls; report elapsed wall time |
| Traceability | Record selected path geometry, source hash, corridor assumptions, planner settings/version, selected profile and effective car, and run ID |
| Car adaptability | Repeat on built-in and saved profiles without assuming one motor topology; reject unsupported or failing profile scenarios explicitly |
| Presentation | Show a simple top-down line/driver preview, numbers, and explicit “synthetic corridor” labeling |

Further development should be driven by failed checks and team data. Measured track boundaries, cone positions, tire limits, and synchronized vehicle logs are higher priority than a more complex learned policy. When those arrive, a closed-loop controller can be compared against this simple planner without changing the default engineering baseline.

## Primary references used for the design

- [TUM FTM global racetrajectory optimization](https://github.com/TUMFTM/global_racetrajectory_optimization) separates shortest-path, minimum-curvature, and full minimum-time approaches and requires explicit track boundaries. Minimum curvature is a useful inexpensive proxy, not a promise of minimum lap time.
- [TUM FTM trajectory planning helpers](https://github.com/TUMFTM/trajectory_planning_helpers) documents the boundary/corridor geometry and splined racing-line preparation used in that research software. We use the ideas, not its LGPL-3.0 implementation code.
- [TORCS robot tutorial: driving on a track](https://torcs.sourceforge.net/api/robot_tutorial_chapter_4.html) illustrates the game-bot separation of target line, lookahead steering, speed feedback, and edge checks; it warns that cutting across corners can make a nominally faster lap invalid.
- [TORCS robot tutorial: speed control](https://torcs.sourceforge.net/api/robot_tutorial_chapter_3.html) shows curvature-limited target speed and backward braking logic, which are conceptually similar to LapSim's existing path speed envelope.
