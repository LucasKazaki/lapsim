# Racing Terps LapSim: team demo brief

**Purpose:** show what the current desktop simulator calculates, what the optional racing-line mode changes, and which team measurements are still needed before using a result for a car or course decision.

For the shared Windows x64 build, extract `LapSim-Windows-x64.zip` and run
`LapSim.exe`; Python installation is unnecessary. For a fresh source clone,
run `setup_lapsim.cmd` once, then `launch_lapsim.cmd`. See the
[team guide](team_guide.md) for startup, units, troubleshooting, and saved evidence.

## Five-minute walkthrough

1. Launch `launch_lapsim.cmd` with the **Prius benchmark**, **Fused GNSS/IMU · default**, and **Centerline (default)**. Run one lap. Show the live accepted-cell display, then scrub the Driver view and read the time, speed, energy, and entry/exit speeds. Different entry and exit speeds mean this is one initial-condition lap. Open **Saved run details** beside **Run one lap** to show the full record ID, file, profile, course source, and model-estimate label.
2. Open **Model notes** and show the warning above the Analysis course plot. The fused recording's x/y map and solver curvature disagree, and it has no surveyed left/right boundaries. If the optional ENME408 intake package is installed, **Source data** shows the partial team inputs; a fresh clone does not include that package.
3. Choose **Synthetic loop · AI demo**. Leave **Cell size (max)** at **1 m**, set Prius driver request to **80% (enter 80)** and **Assumed road grip** to **100%**, select **AI racing line (experimental)**, and run. The current synthetic example compares a **17.009 s** processed baseline with a **14.638 s** selected path, a **2.371 s modeled lead** under an *assumed* ±3 m corridor. Show **Compare path numbers**, replay the completed paths, and open **Saved run details** to inspect the primary record and linked trials. The calculation bar shows the current model pass, not an overall AI percentage. These are software-example times, not Racing Terps performance.
4. Close with the missing inputs: a coherent surveyed course and boundaries, a controlled 2026–27 car configuration, and measured logs under stated conditions. Until then, use the outputs to inspect model behavior and sensitivity.

In **Compare path numbers**, point out the separate rolling start and finish
speeds for the processed centerline and AI candidate. Speed-seam shooting can
choose different starts for those paths. The paths use the same effective
vehicle configuration, initial pack state, and driver request, but their
rolling speeds may differ. The lap-time difference compares path-specific
speed-closed model laps; it is not a same-start or validated race result.

### Optional follow-ups

- On the eligible uniform-road synthetic AI result, click **Check finer grid
  (optional)**. The same fixed baseline/candidate paths and frozen car are
  rerun once at finer spacing; the current example's modeled difference
  changes from about **−2.371 s** to **−2.352 s** while retaining its sign and
  0.05 s selection-margin crossing. The original-grid path remains displayed.
  Other AI trials are not rerun, so this stable fixed-pair result does not
  confirm the best-trial ordering.
  If either check changes on a different run, the main result says
  **grid-sensitive; ranking unresolved** while its original-grid numbers and
  saved records remain available. **Saved run details** labels the saved rank
  as an original-grid decision; the optional check is not stored in that run
  record, so reopening it later does not recover the warning. This is one
  numerical sensitivity check, not convergence or boundary validation.
  While unresolved, **Preview selected AI path (80 m)** is disabled until a
  completed stable check or a new eligible AI run. An existing synthetic pose
  trace and any saved file remain available; an already displayed selected-path
  trace gets an original-grid uncertainty qualifier. A separately loaded file
  retains its generic recorded-sampled label.
- Return to **Fused GNSS/IMU · default** in AI mode at 1 m, 100% Prius driver request, assumed half-width 2.0 m, vehicle width 1.78308 m, safety margin 0.3 m, and 100% assumed road grip. Read the *current* diagnostic status from the run: the processed baseline fails the path audit, completed times are starred diagnostics, **Compare path numbers** is disabled, and no AI winner is selected. **Saved run details** exposes the primary and linked trial files; Driver view can replay completed diagnostics. Changing course clears the previous result and evidence button.
- Switch back to **Centerline (default)** and use **Run comparison** for two saved or built-in profiles. Read B-minus-A values and the shared rolling start, then open **Saved run details** for both full record IDs and files. Peak speed includes that rolling start as well as recorded cell exits; a decelerating first cell cannot make the displayed peak lower than the shared start. Each car has one initial-condition lap; the source-backed TREV entries are partial working scenarios.
- Open **Timed sessions · WIP** and, if time permits, run its **80 m synthetic pose preview**. After an eligible synthetic AI result, its second button can preview that selected polygon with the separate synthetic car. Driver view then plays actual modeled x/y and heading, with boxes for steering, wheel torque, tracking error, sampled grip, and assumed clearance. On replay, controls hold over their recorded intervals; **GRIP SAMPLE (×)** reads the latest pose sample, including the terminal sample, without another physics step. Its duration is pose-model time, not the endurance lap time. A saved v2 pose trace checks both recorded-input dynamics replay and whether the declared controller issued its controls; a zero-step trace has no controller choices to check. The tab cannot start a full timed session or ghost yet.

During that pose replay, the lateral-acceleration box holds the recorded
pre-step force evaluation until the next control boundary. It is an interval
display value, not a continuous force or acceleration sample.

If terminal path projection is lost, the pose summary gives the last confirmed
station and marks assumed footprint slack unavailable. The Driver view's
**STATION** box shows an unavailable dash while projection is lost; actual
pose and recorded controls remain visible.

If a pose trace stops with `road_domain_invalid`, its local-grip box may show
the base-road diagnostic fallback outside the declared road domain. Read the
status warning; that number is not valid road data.

For a longer course demonstration, select **Synthetic FSAE-style · practice**
and run a fresh centerline lap or an experimental AI comparison. This is an
analytic **817.079633 m** closed loop with 60 m and 45 m straights, alternating
left/right bends, and 15 m radius corners. Its design is inspired by the
[2027 Formula SAE endurance layout guidance, D.12.2.2](https://www.fsaeonline.com/cdsweb/gen/DownloadDocument.aspx?DocumentID=da79bcb4-0935-4f7b-83d7-0dbb8ce68d38).
Read its result from the current run; the rounded-rectangle times in step 3
belong only to **Synthetic loop · AI demo**. The practice course has no
surveyed centerline, cones, measured boundary widths, or passing zones. Its
starting ±3 m AI half-width is an editable assumption. With the built-in
Prius at 80% torque request and the initial 1 m cell limit, the optional
speed-periodic comparison gives an eligible **60.362615 s** processed baseline
and selects the full-offset path at **60.038711 s**. All four tested paths
pass the assumed-corridor audit. Neither this shape nor its model lap is a claim
of rule compliance or competition performance.

If there is time, return to **Synthetic loop · AI demo** and repeat a run at assumed
road grip **80%**. The setting uniformly scales the selected tire model's
force capacities, so describe the difference as a model sensitivity to one
assumption. Restore **100%** before citing the benchmark above. The multiplier
is saved with the run and restored by the engineering replay checker; it is
not measured surface grip, weather, or a spatial patch. Editing it clears the
old on-screen result and replay before another run.

For a local-condition demonstration on the **synthetic loop**, select
**One rectangular low-grip patch (assumed)** under **AI trial surface**.
The starting boxes describe world X **36–55 m**, Y **−3–16 m**, at **30% of
base grip**. Run AI again; the top-down map outlines the rectangle, while
each modeled path gets a separately mapped cell-grip schedule. A completed
trial's JSON retains its own schedule and rectangle version, and the replay
checker regenerates that mapping before checking lap numbers. This is a
controlled software sensitivity, not observed pavement. The optional racer
can now screen a small set of smooth left/right detours near baseline wheel
contacts and, if one lowers weighted low-grip exposure, add **one** fifth
full-model trial. Read the current result's **Grip detour** status, compare
the detour's eligible time with baseline and other paths, and inspect
`settings.path_planning.grip_detour_search` plus the linked trial record.
Do not promise an avoidance gain: a candidate can fail clearance, fail the
lap, or lose on time. This is a deterministic offline proposal, not learning
from driven laps or proof of cone clearance.

If both patch-mode paths are eligible and complete, **Check finer grid
(optional)** remaps the same world-fixed rectangle independently onto each
refined fixed path, retaining each original path's modeled entry heading. In
one synthetic Prius probe, the candidate-minus-centerline difference moved
from about **−2.591 s** to **−2.612 s**; the sign and 0.05 s selection-margin
decision stayed the same. The selected line does not change. This is one
numerical sensitivity observation, not convergence, surveyed road validity,
renewed clearance proof, or a check of other AI trials and their ordering.
If a completed check reverses the sign or crosses the 0.05 s margin, describe
the modeled ranking as **grid-sensitive and unresolved**. The displayed
original-grid path, numbers, and saved records stay in place. The path
comparison, saved-evidence window, and ordinary AI replay context also show
the warning, even if their windows were already open. A failed retry does not
settle the ranking; only a completed stable check removes the warning. An
older popup keeps its caveat with its frozen numbers after inputs change.

The car and path comparison popups display the selected course label; an open
popup retains that label if the main course choice changes.

## What the optional racer actually does

The **AI racing line** mode is a deterministic, offline path planner. It minimizes a geometric curvature-and-length objective within entered clearances, rejects invalid paths, and checks up to four ordinary paths with at most two physics passes each; one assumed rectangle may add a fifth grip detour and two more passes. After baseline, full, and half, it fits one convex quadratic only if all three audits and times are eligible and half beats both endpoints by more than 0.05 s. When full fails its audit but eligible half clearly wins, it screens stronger offsets using geometry and requires 0.02 m of certified scalar clearance before spending the fourth physics trial. An invalid candidate path is skipped before physics when the processed baseline is valid. Other cases use the 0.75 fallback. This is bounded car-specific probing, not learning. A patch detour must lower a cheap wheel-contact exposure score before its own geometry audit and full lap trial; only the latter can establish an eligible time gain. An **eligible comparison time** requires a completed lap, a closed speed seam, and a certified continuous normal-coordinate clearance inequality plus position closure. At the initial 1 m cell limit, the optional short synthetic loop has eligible baseline, half, and 0.975 paths; the default fused course's assumed-corridor paths fail despite completed model laps. The scalar certificate follows the supplied piecewise-width model; it is not a swept-body, world-frame containment, or surveyed cone-clearance certificate. The car and pack state still change across the lap. The offline planner does not steer a simulated car, learn from laps, see cones, or respond to traffic. The default centerline calculation does not run the planner. Ordinary Driver view playback is a top-down **reference-path** display with model speed and lateral acceleration. The separate pose preview does steer a synthetic four-wheel model from its actual state, but has no measured vehicle pose, surveyed cones, or endurance lap result.

## Evidence to show, and how to phrase it

- Use **Saved run details** to locate the primary JSON and, for AI mode, every linked saved trial. Each file contains its exact input profile, source-course ID and synthetic flag where applicable, solver grid, start speed, completion status, telemetry, and full content ID. `selected_result` names the primary AI file; `baseline_record` and `candidate_trials[].run_id` link the others. A record hash identifies content but does not prove model agreement. For an engineer's follow-up, `replay_lap_record()` checks a completed v2 record's saved cell controls against the current model and reports numerical differences separately from source and runtime warnings.
- Read AI eligibility from the current result and record: the assumed corridor, observed excess, certified clearance bound when available, speed seam, and `settings.path_planning.candidate_trials[].strategy` and its nullable `offset_strength` (null for a grip detour). A completed diagnostic time is replayable but cannot be ranked. On the short synthetic loop, the selected 0.975-offset path's **2.3711801014 s** modeled lead demonstrates ranking on an analytic example; full offset fails the assumed corridor by **0.0026717805 m** and has no modeled time. The engineering handoff retains historical fused-course benchmarks, which are not current live outputs or eligible racing-line results. The model's curvature check does not establish x/y map following or cone clearance.
- Show the course geometry warning and the engineering handoff. The report gives the equations, Python data flow, test evidence, known mismatches, and unimplemented features.
- Show **Import course…** as the team-data entry point. A coherent, closed,
  versioned course bundle is validated and saved in the local catalog; the
  importer refuses to re-label the inconsistent fused recording as a coherent
  new course. V1 has no surveyed boundary; v2 can retain source-relative
  boundary widths and their evidence. The AI planner still uses its separate,
  editable assumed corridor while reference-frame handling is incomplete.
  **Saved run details** distinguishes source boundary status from the AI
  corridor and shows whether the source widths were used. Saved runs separate
  source bundle/geometry hashes from the solver-grid hash; see the
  [bundle format](course_bundle_format.md).
- If showing a failed run record, read its `accepted_*` fields alongside the
  attempted terminal state and failed lap/cell index. The attempted state can
  be one rejected cell ahead of saved telemetry and is not a lap result.

## Data to request from the team

Ask for a surveyed centerline with left/right cone or pavement boundaries, a consistent distance/heading/curvature reconstruction, and the 2026–27 car's controlled revision of mass, wheelbase, track widths, tire force data, powertrain and battery limits, brake behavior, aero, and measured logs with stated test conditions. Those inputs matter more than a larger AI search or a learned driving policy at this stage.

**Full technical detail:** [Engineering handoff](engineering_handoff.md), [AI racer design](ai_racer_design.md), [desktop guide](simulator_desktop.md), and [course-bundle format](course_bundle_format.md).
