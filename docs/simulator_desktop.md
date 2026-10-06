# LapSim desktop app

LapSim is a native Windows desktop application built with Tkinter and
Matplotlib. It calls the repository's existing vehicle, tire, path-constraint,
and endurance simulation code directly. The interface uses only black and
white, with a dark-mode switch that reverses those colors.

## Launch

From the repository folder, double-click `launch_lapsim.cmd`, or run:

```powershell
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m lapsim.ui
```

In VS Code, select **LapSim desktop app** from the Run and Debug menu. The
calculation runs in a worker thread so the window remains responsive.

## Inputs and outputs

The profile menu includes the Prius benchmark and unchanged repository model.
When the local ENME408 evidence package is present in Downloads, it also
offers two separate TREV5 working scenarios: geometry and geometry with the
source aero set. These are partial engineering scenarios, not released or
calibrated cars. The **Source data** button browses source values, units,
evidence, locators, model use, and caveats without changing the active car.

Prius profile inputs are editable: vehicle mass, power-equivalent limit,
wheelbase, tire radius, constant tire friction coefficient, drag area (`CdA`),
and speed limit. **Save current** creates another named local profile in
`%LOCALAPPDATA%\LapSim\car_profiles.json`; the file is outside the repository.
The repository and source-backed profiles are read-only so source values and
inherited model defaults remain distinguishable from edited assumptions.

Driver request applies to every run; the solver cell-length box applies to
standard centerline runs. AI mode builds its separate nominal 2 m geometric
grid. Invalid or non-finite values are rejected before a run begins. The default solver cell
is 1 m; 0.5 m uses the source course's full station resolution. Coarser cells
run faster but can change the lap result because they smooth curvature over
longer distances.

The numeric outputs are lap time, peak speed, average speed, distance, net
equivalent-pack energy, peak lateral acceleration in g, and lap entry/exit
speeds. The default centerline is a one-pass initial-condition lap: entry and
exit speeds may differ at the closed-course seam. Optional AI path timing
checks speed closure separately; neither mode establishes a full-state
steady endurance lap. The car and AI path comparison windows show the signed
seam-speed difference alongside their other numbers. The trace selector
shows speed, longitudinal or lateral acceleration, drive or braking force,
driven tire slip, or battery power against distance or time. The top-down
course map stays fixed rather than moving with the car. In the map,
left-drag pans, the mouse wheel zooms around the cursor, and **Fit course**
restores the full view.

The right side has **Analysis**, **Driver view**, and **Timed sessions · WIP**
tabs. Analysis remains the startup view. When a lap starts, the view first
labels path and speed-limit preparation; no motion is implied during that
prepass. As the physics solver accepts cells, Driver view shows its latest
elapsed time, station, speed, and lateral acceleration on a driver-centered
top-down **reference map**. The desktop keeps only the newest update and draws
at roughly 10 updates per second, so it does not slow the solver to real time.
AI mode labels geometric baseline, full line, and half line separately. Its
dry seam-speed probe sends no live updates; Driver view shows accepted cells
from the final recorded pass for each path.
Rejected cells are not shown as completed movement. After a completed lap,
the app starts a 1× replay with Play/Pause, Start, time scrub, playback rate,
and wheel zoom. **Replay lap** lets you switch between A and B after a
completed two-car comparison, or between completed geometric baseline and
best tested AI path runs, including runs labeled **diagnostic** after a failed
modeled-path audit. Each choice uses that run's
recorded telemetry and its own processed path where applicable. Switching
resets the playback cursor without rerunning physics; the menu is disabled
when only one completed run is available. The course rotates around a
fixed car marker. The replay uses
the solver's constant-acceleration cell relation between recorded exits.
The lap physics uses a separate curvature channel, so the displayed map
heading is not necessarily the model's integrated heading. This is a live
**accepted-step reference-path preview** followed by completed telemetry
playback, not vehicle line tracking, a first-person camera, or interactive
driving.

## Optional AI racing line

The **Driving path** menu defaults to **Centerline (default)**. This uses the
existing recorded curvature and runs no path search. Choose **AI racing line
(experimental)** to supply an *assumed* uniform half-width, vehicle width,
and safety margin. The app has no measured boundaries and does not infer
vehicle body width from the car profile. A deterministic, bounded planner
proposes one smooth lateral-offset line on a 2 m grid. It runs the same car and
torque request through a newly derived geometric centerline, the full-offset
candidate, and a validated half-offset path. For each path it makes one dry
seam-speed probe and one final recorded lap, starting each from the same fresh
initial car and pack state. The final pass starts at the probe's exit speed;
its finish-minus-start speed must be within **0.005 m/s**. This is at most six
full physics passes across three paths. Pack charge and other states need not
match at the seam. Evaluating both strengths can catch an interior line that
is faster than the full path in the modeled time calculation.

Before a time can be compared, the app integrates each solver path's saved
constant-curvature cells and samples **four positions per cell** against the
declared usable corridor around the processed geometric baseline. Sampled
clearance may exceed the usable corridor by no more than **1e-8 m**, and the
integrated end position must close within **0.01 m**. The check is deliberately
conservative and does not certify the continuous swept body or real cone
clearance. If the processed baseline fails, all completed times in that run
are **diagnostic only**. The left panel adds `*` to those times, leaves their
difference blank, disables **Compare path numbers**, and states the excess and
seam gap. Driver view still offers diagnostic replay, and linked JSON records
retain the completed runs. There is no selected AI winner for that case.

When both paths pass the modeled-path audit and speed-seam check, the app
selects the best tested candidate only if its gain is strictly greater than
**0.05 s**. A smaller positive gain is an unresolved numerical tie and leaves
the eligible geometric baseline selected. The margin is a provisional
selection heuristic, not a proven numerical error bound. Eligible comparisons
show their signed difference and allow **Compare path numbers** for time,
distance, speed, equivalent energy, and lateral acceleration. A failed run
returned by the solver is saved for diagnosis.

This AI mode rebuilds arc length and curvature from the x/y map. The ordinary
centerline mode uses the separate recorded curvature channel. On the packaged
course those channels disagree materially: 1,441 map chords exceed their
station intervals, individual prescribed arc-chord lengths differ from plotted
map-chord lengths by up to **0.235787 m**, stored curvature sums to **3.657937 rad** of
turn versus **6.283185 rad** of map winding, and constant-curvature integration
from the first map-chord heading leaves a **542.633 m** closure gap. The processed AI
baseline polygon closes in x/y but has a **0.750897 m** integrated arc closure
gap. The Analysis tab shows the source warning. Even two x/y-derived AI-mode
times may be ranked only if their modeled-path audits pass; they must not be
compared directly with the ordinary source-curvature lap. The map is not a surveyed corridor, the planner does
not steer a closed-loop car, and the vehicle model has simplified tire and
controller physics. See [AI racer design and checks](ai_racer_design.md) for
the objective, validation checks, and local benchmark results.

For the shipped assumed ±2 m Prius case, baseline/full/half laps complete in
**87.618366/87.377773/87.403816 s**, but all three are starred diagnostics:
sampled usable-corridor excess is **0.095506/0.908195/0.501981 m** and the
position seam misses by roughly **0.75–0.77 m**. No AI path is selected from
those runs. This does not change the ordinary centerline calculation.

The primary AI run record includes every tested offset strength and its
reported eligible or diagnostic result, audit status, and exact saved solver
geometry and telemetry, including the explicit starting speed of its final
pass. When a second physics trial returned a run, the app also saves one
linked counterpart with its own geometry and telemetry; the primary record
names its ID and role. A third trial may have only its summary saved. For an
audit-failed shipped course, the primary record is flagged diagnostic, and
neither record represents a selected winner. These records do not provide a
full ghost/session replay.

The Timed sessions tab is explicitly a design placeholder for a future
versioned Terps vehicle/controller, timed drive, ghost, full session capture,
and comparison report. A standalone, programmatic lap-record replay check
exists as described below, but it is not a timed session or a tab workflow.
The tab's Start button is disabled.

**Run comparison** simulates two selected saved/built-in profiles with the
same standard centerline course, solver spacing, and driver request. The
comparison window shows
both values and B-minus-A differences for each numeric output. The speed plot
uses solid and dashed black/white lines. Unsaved Prius edits are excluded from
comparison until saved as a named profile. Differences show model sensitivity
to selected inputs, not validated real-world performance.

Every lap run, including an interrupted run returned by the solver, saves a
content-identified JSON record under `%LOCALAPPDATA%\LapSim\runs`. The record
contains the selected profile manifest, effective car constructor inputs,
editable overrides, exact resampled-course geometry and hash, solver and controller
settings, result status, and aligned telemetry with units and validity flags.
The status line shows the start of the record ID; comparison shows both IDs.
Files stay on your computer and are not added to Git. A record is evidence of
what the model calculated, not evidence that the real vehicle was calibrated.

For a **completed v2 one-lap** record, an engineer can check the saved cell
commands against the current model without opening the GUI:

```python
from lapsim.experiments import (
    LapReplayTolerances, default_run_directory, replay_lap_record,
)

path = default_run_directory() / "<run_id>.json"
report = replay_lap_record(path, tolerances=LapReplayTolerances())
print(report.model_agreement, report.mismatch_reasons)
print(report.provenance_warnings)
for metric in report.metrics:
    print(metric.name, metric.maximum_absolute_error, metric.tolerance, metric.passed)
```

The checker verifies the record ID and embedded model/track data, restores
allowlisted vehicle constructor inputs, solves the saved path constraints,
and feeds each saved accepted-cell control command back through the endurance
model. It checks completed status and cell count, lap and total time, entry
and exit speed, net pack energy, final SOC, and aligned time, station, speed,
path-ceiling, and control traces. The default absolute limits are 0.01 s for
time, 0.01 m/s for speed, 0.00001 kWh for energy, 0.00001 SOC, and 1e-8 m
for station; recorded control channels must match exactly. The report separates
numerical agreement from source commit, dirty-worktree, Python, platform,
and dependency-version warnings. This check requires the installed model code
and supports neither older v1 records nor incomplete laps. Agreement means
the current code reproduced the saved model outputs, even for a diagnostic
AI run whose path audit failed. For a record
made with explicit controls, the event checks speed ceilings and both the
steering-requested and tire-achieved curvature against the prescribed cell
curvature. `EnduranceRunConfig.path_curvature_tolerance_per_m` defaults to
**1e-9 1/m**; a direct zero-steer circular lap fails this check. The replay
uses the same event gate. This cell check does not establish that integrated
x/y followed the plotted course or that the car stayed clear of boundaries.
The replay is not validation against a measured car or a complete
ghost/session workflow.

**Four-wheel lab** opens a separate top-down, time-domain experiment. It
compares two allocations of the same total requested wheel torque on one
synthetic car and shows paths, yaw rate, four wheel-slip traces, and wheel
forces at a movable time cursor. Its white/black desktop controls allow
editing mass, yaw inertia, geometry, tire coefficients, steer, independent
wheel torques, world-frame wind, air density, synthetic drag area, base road
grip, and an optional rectangular lower-grip patch. It displays apparent airspeed,
aero force, and per-wheel grip multiplier. Each A/B experiment saves one
linked JSON record under `%LOCALAPPDATA%\LapSim\dynamics_runs`, including exact
inputs, trajectories, wheel forces, and equation residuals. Road coverage is
shown as assumed unless a validity domain is supplied through the Python API.
The lab is for torque-allocation and equation checks. It has no measured tire
map, dynamic load transfer, motor/inverter/pack limits, or team-car calibration,
and its results must not be treated as lap times. See
[Four-wheel dynamics](four_wheel_dynamics.md) for the equations and checks.

The team course file is a 989 m fused GNSS/corrected-IMU recording registered
to an earlier official centerline. It is not a surveyed ground-truth path or a
confirmed 2026–27 competition layout. Its source stores centerline geometry,
not course-width measurements.

## Model assumptions

The initial vehicle is a 2026 Toyota Prius LE FWD benchmark. Published Toyota
values seed its combined-system power rating, curb mass, overall dimensions,
wheelbase, and tire size. Since Toyota does not publish a single motor torque
curve for the hybrid system, the benchmark converts net system power into an
idealized one-motor FWD power envelope. This is not a calibrated Prius hybrid
model. The battery, tire grip, drag area, and some chassis values are modeling
assumptions; pack energy is therefore an equivalent-model output.

The core drivetrain supports front, rear, or all driven tires. The Prius
benchmark uses front drive. The source-backed TREV5 scenarios apply reviewed
mass/geometry inputs and optional aero inputs on a fresh repository vehicle;
other tire, motor, battery, and controls settings remain inherited model
assumptions. A future 2026–27 car needs its own confirmed configuration. Do
not infer its motor count or electrical layout from these partial scenarios.

## Numerical method

For every distance cell, the existing vehicle model solves the longitudinal
force balance including aero drag, rolling resistance, tire force limits, and
equivalent rotating mass. Cell time is calculated from constant-acceleration
kinematics. The path solver first finds tire-limited corner speeds, then
performs cyclic backward braking passes. The endurance controller reduces
drive torque or brakes to stay below those path-speed ceilings.

The default solver grid resamples curvature by a distance-weighted mean. This
preserves integrated signed curvature over the lap; x/y coordinates are
interpolated at the new cell boundaries. A new global grid can average across
old curvature discontinuities, changing the squared-curvature demand used by
the tire model. For a diagnostic refinement of an existing `SpatialTrack`, the
programmatic `track.refine(maximum_cell_length_m)` instead splits each original
cell, retains every old boundary and its piecewise-constant curvature, and
interpolates interior x/y points along the old chord. It preserves track
length, each original cell's signed turn, and its length-weighted squared
curvature, with a 100,000-cell safety cap. It does not change the desktop's
default grid or repair an inconsistent source map. Grid spacing still affects
the speed-envelope and cell integration, so resolution checks remain
necessary. The Prius benchmark is for software demonstration and input
checking, not engineering sign-off.

The supplied ENME408 research report motivates a separate time-domain
four-wheel model rather than changing this prescribed-path solver into a
torque-vectoring claim. The lap and dynamics calculations currently answer
different questions; no motor or battery controller connects them yet.
