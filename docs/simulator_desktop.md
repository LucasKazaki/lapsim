# LapSim desktop app

LapSim is a native Windows desktop application built with Tkinter and
Matplotlib. It calls the repository's existing vehicle, tire, path-constraint,
and endurance simulation code directly. The interface uses only black and
white, with a dark-mode switch that reverses those colors.

## Launch

From a fresh Windows checkout, install **64-bit Python 3.11 or newer** with
Tkinter, then double-click `setup_lapsim.cmd`. It creates `.venv`, installs
LapSim in editable mode, and checks Python, Tk, desktop imports, and the default
course. Then double-click `launch_lapsim.cmd`. From PowerShell, the same steps
are:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup_lapsim.ps1
.venv\Scripts\python.exe -m lapsim.ui
```

The launcher checks the setup before opening a console-free window. If a later
startup error occurs, it shows a message and writes details to
`%LOCALAPPDATA%\LapSim\logs\desktop_startup.log`. In VS Code, run setup first,
then select **LapSim desktop app** from Run and Debug; the checked-in launch
configuration uses this checkout's `.venv`. The source checkout must remain
present because the default course is stored in its `analysis/data` folder.
The calculation runs in a worker thread so the window remains responsive.
To repeat the full software checks on Windows, run
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_all.ps1`
from this checkout after setup. It runs each test file in a separate process to
limit peak memory use.

## Inputs and outputs

The **Course** menu starts at **Fused GNSS/IMU · default**, the shipped team
endurance recording. **Synthetic loop · AI demo** selects a separate
195.398224 m rounded rectangle made from two 40 m and two 20 m straights and
four 12 m radius quarter-circle arcs, stored in at most 0.5 m source cells.
**Synthetic FSAE-style · practice** selects a separate analytic 817.079633 m
loop with 60 m and 45 m straights and alternating 15 m radius bends. Its
general scale and turn variety are inspired by [2027 Formula SAE Rules v1.0,
D.12.2.2](https://www.fsaeonline.com/cdsweb/gen/DownloadDocument.aspx?DocumentID=da79bcb4-0935-4f7b-83d7-0dbb8ce68d38).
Changing courses clears previous output boxes and Driver view replays so
results from different tracks are not mistaken for a matched comparison.
Course selection does not change the driving mode: **Centerline (default)**
continues to run without the AI planner. Both synthetic courses are calculation
examples. The practice loop is not an official layout or a rule-compliance
claim; it has no surveyed centerline, cones, widths, or passing zones. All
three built-in course choices lack surveyed left/right boundaries.

**Import course…** accepts a versioned, internally coherent closed course
bundle. Its source arcs are validated before selection, and its local copy
reappears in the menu after restarting the desktop. Schema v1 has no boundary
widths. Schema v2 can carry one left and right width per original source cell,
with declared status, source file hash, processing note, and a hash tied to the
validated source geometry. These are distances along that source path's normals,
not world-frame edge coordinates or a swept-car clearance certificate. The AI
planner changes the reference path by smoothing and resampling, so the desktop
does not feed v2 source widths into it until a frame transformation is checked.
The starting AI width remains an editable uniform assumption, even when an
import declares measured source-relative widths. See
[Versioned course bundles](course_bundle_format.md) for source preparation,
metadata, and numerical gates.

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

Driver request applies to every run. **Cell size (max)** is an editable
upper bound for the generated physics cells in centerline, two-car comparison,
and optional AI runs. It sits in the fixed **Calculation settings** panel beside
Run, with a live centerline solver-cell count or invalid-size hint. AI mode
notes that its separate path grid count is determined during planning. The
desktop starts at 1 m. AI builds a separate x/y-derived path grid and adds samples until its processed baseline and full
offset meet that bound; fractional offsets then fit it too. A smaller request
can increase planning and lap time, and a request needing more than 5,000
points is refused. The saved grid's individual lengths are authoritative.
**Assumed road grip** defaults to 100% and uniformly multiplies the selected
tire model's longitudinal and lateral force capacities. It applies to ordinary
laps, AI trials, and both cars in a profile comparison. A value below 100%
is a sensitivity scenario; it is not a calibrated wet-road model, a local
surface map, or a claim about actual course conditions. Each saved lap records
the multiplier alongside the effective tire configuration. The engineering
replay checker restores both; older v2 records without this condition use
the original 100% grip. Editing a run input or changing the selected profile
clears displayed outputs and playback so prior numbers cannot be read as the
new setup.
For Python-only studies, the path-constraint and one-lap APIs also accept an
immutable tuple of **absolute** tire-grip multipliers with exactly one
positive finite value per solver cell. The local corner-speed calculation,
cyclic braking-envelope pass, and that cell's force update all use its value,
and the car's configured tire multiplier is restored afterward. Omitting the
tuple preserves the uniform baseline. The desktop does not expose this
schedule, draw a local main-lap grip map, or save such a schedule in a lap
record; its percentage box remains uniform for centerline, AI, and A/B.
A scheduled API run needs a future record/replay schema extension before it
can be shared as a checked v2 lap record.
Invalid or non-finite values are rejected before a run begins, and requests
producing more than 5,000 actual cells are refused. For either synthetic course,
the guard counts subdivisions of each original straight or arc cell. The fused
course is resampled at the requested
maximum, which may average
curvature across original cell boundaries and change lap time. The synthetic
courses keep their exact generated straight/circular-arc cells (at most 0.5 m)
for any request at least as large as its longest source cell. An imported
coherent course follows the same retain-or-subdivide policy. A finer request
first strictly validates the source station, x/y, and constant-curvature
geometry, then subdivides each original cell into analytic straight or
circular subarcs. It keeps every source station and endpoint, without
averaging curvature or interpolating interior x/y along the old chord. A
coarser request therefore does not reduce a coherent source's solver-cell
count. Imported courses have the same 5,000-cell guard. This gate checks a
numerical solver representation; it does not establish
a surveyed track or measured left/right boundaries.
The separate WIP pose preview instead retains or analytically refines its
coherent course to at most 0.5 m cells; it does not read the main-lap
**Cell size (max)** box.

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

The fixed **Calculate** strip remains visible when the input panel scrolls.
Its labeled monochrome **Calculation progress** bar animates during path
planning, AI dry passes, and waits without accepted cells. During path-speed
preparation it fills by **local corner-limit cells processed**. The following
cyclic braking sweeps show a pass number and processed-cell count, while the
bar stays indeterminate because the number of passes needed for convergence
is unknown. During a recorded physics pass it fills from that pass's
accepted-cell index and labels the active car/path and cell count. A
percentage describes **its named phase or current recorded pass only**; it
is never an overall percentage or ETA. AI can run several passes and return
to preparation. Completion, failure, or changed inputs update the bar's
label and state.

The right side has **Analysis**, **Driver view**, and **Timed sessions · WIP**
tabs. Analysis remains the startup view. When a lap starts, Driver view first
fits a static, labeled source-course map with its start marked while path and
speed-limit preparation runs. AI dry seam-speed passes also return to this
static preview after the preceding trial finishes; a pause of more than half
a second between accepted cells does the same. The last accepted numeric
values remain visible. No vehicle pose or motion
is implied during those periods. As the physics solver accepts cells, Driver
view switches to the active trial's exact solver-grid path and shows its latest
elapsed time, station, speed, and lateral acceleration on a driver-centered
top-down view of that run's **solver-grid reference x/y**. The desktop keeps only the newest update and draws
at roughly 10 updates per second, so it does not slow the solver to real time.
AI mode labels geometric baseline, full, half, and its fourth line separately;
that fourth line is labeled three-quarter on fallback or car-adaptive when a
different strength is selected. Its
dry seam-speed probe sends no live updates; Driver view shows accepted cells
from the final recorded pass for each path.
Rejected cells are not shown as completed movement. After a completed lap,
the app starts a 1× replay with Play/Pause, Start, time scrub, playback rate,
and wheel zoom. **Replay lap** lets you switch between A and B after a
completed two-car comparison, or among completed AI trials. A candidate
rejected by the modeled-path audit when the processed baseline is valid has no
model run or replay. Completed runs that failed the modeled-path audit because
the baseline is invalid are labeled **diagnostic**. Each choice uses that run's
recorded telemetry and exact saved solver-grid x/y. This includes ordinary
centerline laps and both cars in a profile comparison, so completed playback
uses the same reference geometry as live progress. Switching
resets the playback cursor without rerunning physics; the menu is disabled
when only one completed run is available. The course rotates around a
fixed car marker. The replay uses
the solver's constant-acceleration cell relation between recorded exits.
For a solver-cell-aligned run, the lateral acceleration number holds that
cell's solved value until the next cell. Legacy traces without this alignment
keep the prior linear display interpolation.
The simple **cell model values** boxes show the accepted cell's motor torque
request, front/rear hydraulic pressure requests, achieved drive/friction/regen
forces, longitudinal acceleration, and signed terminal battery power. The
**next-entry ceiling** is the braking speed limit at the next cell entrance,
not the full controller target or a guarantee of the shown exit speed. During
live solving the boxes show the last accepted cell; completed playback holds
the active cell's saved values and switches at cell boundaries. Missing or
unaligned legacy channels show a dash rather than an invented number. Positive
battery kW denotes discharge; negative denotes charge.
The Analysis tab's course plot continues to show the selected source map;
resampling can make its x/y differ from the saved solver grid. The lap physics
uses a separate curvature channel, so the displayed map heading is not
necessarily the model's integrated heading, especially on the inconsistent
fused course. This is a live
**accepted-step reference-path preview** followed by completed telemetry
playback, not vehicle line tracking, a first-person camera, or interactive
driving.

## Optional AI racing line

The **Driving path** menu defaults to **Centerline (default)**. This uses the
selected course's original curvature and runs no path search. Choose **AI racing line
(experimental)** to supply an *assumed* uniform half-width, vehicle width,
and safety margin. On either synthetic course, the boxes initially show an
*assumed* ±3 m half-width, 1.8 m vehicle width, and 0.2 m safety margin;
switching back restores the default recorded course's scenario inputs. The
AI mode has no verified boundary transform from any imported source widths
and does not infer vehicle body width from the car profile. A deterministic,
bounded planner
proposes one smooth lateral-offset line on a separate grid, using nominal 2 m samples only when the requested maximum allows it; it increases samples until generated cells meet the bound. It runs the same car and
torque request through a newly derived geometric centerline, then checks
full- and half-offset candidates. When the centerline audit is valid, a
candidate failing its path audit is skipped before physics. If all three paths have eligible audits and times,
and half beats both endpoints by more than **0.05 s**, a convex quadratic
through their times estimates an interior best strength. The fourth path uses
the nearest safeguarded choice from **0.25, 0.375, 0.625, 0.75, 0.875**;
if full offset fails its path audit while eligible half offset clearly
beats the baseline, a short geometry-only screen instead tries stronger
offsets and requires at least **0.02 m** of certified scalar clearance beyond the
entered vehicle width and margin. Other cases fall back to **0.75**. This is a bounded probe for the selected
car, not a learned or closed-loop controller. For each path admitted to physics it makes one dry seam-speed probe and one
final recorded lap, starting each from the same fresh
initial car and pack state. The final pass starts at the probe's exit speed;
its finish-minus-start speed must be within **0.005 m/s**. This is at most eight
full physics passes across four paths. Pack charge and other states need not
match at the seam. The fourth path has the same modeled-path and speed-seam
eligibility requirements as every other path.

Before a time can be compared, the app integrates each solver path's saved
constant-curvature cells and evaluates **four positions per modeled cell**, plus
every source-corridor cell boundary and midpoint, against the declared usable
corridor around the processed geometric baseline. It then bounds the change
in lateral normal-coordinate offset between evaluations using each modeled
arc's curvature, the linearly interpolated reference and normal, and an
adaptive interval subdivision. Intervals that cannot be certified within
the bounded work budget make the time ineligible. Shared width boundaries use
the narrower adjacent width, including where the first and last cells meet.
The scalar corridor excess allowance is **1e-8 m**. The integrated path and
both saved polygon endpoints must close within **0.01 m**. A certified minimum slack is a
conservative lower bound for this continuous scalar inequality under the
supplied piecewise-width model. It is not a swept-body, world-frame
containment, or surveyed cone-clearance certificate. If the processed baseline
fails, all completed times in that run
are **diagnostic only**. The left panel adds `*` to those times, leaves their
difference blank, disables **Compare path numbers**, and states the excess and
seam gap. Driver view still offers diagnostic replay, and linked JSON records
retain the completed runs. There is no selected AI winner for that case.

When the geometric baseline and a candidate pass the modeled-path audit and speed-seam check, the app
selects the best tested candidate only if its gain is strictly greater than
**0.05 s**. A smaller positive gain is an unresolved numerical tie and leaves
the eligible geometric baseline selected. The margin is a provisional
selection heuristic, not a proven numerical error bound. Eligible comparisons
show their signed difference and allow **Compare path numbers** for time,
distance, speed, equivalent energy, and lateral acceleration. That window
names the selected course, as does the two-car comparison window, so an open
comparison retains its source label after the main course selection changes.
A failed run returned by the solver is saved for diagnosis. Its record labels
the last checked cell's time, distance, speed, and SOC separately from the
vehicle state after an attempted rejected cell; partial times cannot be ranked.

The optional AI worker uses the car selected in **Vehicle profile**. A
desktop-level regression selects the partial source-backed TREV working
profile when its local source bundle is available, and a separately saved
Prius with explicit user overrides on the analytic demo course. It checks
that each selected setup and the exact
computed path appear in the saved result and that the recorded cell controls
replay with numerical agreement. This checks the app's profile-to-result
flow; it does not validate either car's real lap time.

This AI mode rebuilds arc length and curvature from the selected course's x/y
geometry. On the default fused course, ordinary centerline mode uses its
separate recorded curvature channel. On that default course those channels
disagree materially: 1,441 map chords exceed their
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

An earlier unconstrained nominal-2 m API run on the fused course used assumed
±2 m width, Prius torque request 100% (model fraction 1.0), 1.78308 m car
width, and 0.3 m margin. Its baseline/full/half/three-quarter laps completed
in **88.2468936756/88.0083862976/88.0305817762/87.9983373607 s** under
the current exit-force check, but all four were starred diagnostics:
observed usable-corridor excess is **0.095506/0.908195/0.501981/0.705117 m** and the
position seam misses by roughly **0.75–0.77 m**. No AI path is selected from
those runs. These are historical grid-specific numbers, not timing predictions
for the desktop's new 1 m AI default. Ordinary centerline remains the default
driving mode; the exit-force check applies to it too.
The failed baseline audit makes the fourth strength fall back to 0.75 in this
example; its completed time remains diagnostic.

For a controlled AI demonstration, choose **Synthetic loop · AI demo**, the
Prius benchmark, desktop torque request **80% (enter 80; model fraction 0.8)**, and its initial assumed ±3 m
half-width, 1.8 m vehicle width, and 0.2 m margin. Leave assumed uniform road
grip at **100%** and **Cell size (max)** at its initial **1 m** for the stated
numbers. The current speed-periodic model comparison produced an eligible
**17.0090108038 s** geometric baseline,
**15.7317585066 s** half-offset, and **14.6378307024 s** 0.975-offset
candidate. Those three continuous scalar audits passed; the full-offset
path failed at an evaluated point by **0.0026717805 m** and was skipped before
physics. It therefore has no time, saved run, or replay. The 0.975 path has a
conservative certified clearance lower bound of **0.0445441230 m** and was
selected on a **2.3711801014 s** modeled lead. These are synthetic model
numbers, not surveyed-course or team-car performance. An on-demand fixed-path
`SpatialTrack.refine(1.0)` probe made before the continuous certificate and
exit-speed combined-grip gate gave
**16.882064565 s** baseline,
**15.000468902 s** old 0.75 offset, and **14.551839123 s** selected 0.95
offset; all completed and closed speed. The 0.95 line retained about
**0.449 s** over the old fallback, but refined path clearance was not re-audited.
This is a timing-sensitivity probe, not a new eligible comparison or proof of
grid convergence.

On **Synthetic FSAE-style · practice** at the same assumed ±3 m width, Prius
80% torque request, and initial **1 m** cell limit, the current comparison
uses **829** processed cells. Its eligible processed baseline took
**60.3626147273 s** and the selected full-offset path **60.0387107423 s**,
a **0.3239039850 s** modeled lead. All four tested paths passed the scalar
clearance audit; the selected path's conservative minimum assumed clearance
was **0.1173201189 m**. These are software scenario numbers for an analytic
practice shape, not a surveyed event course or calibrated vehicle.

The primary AI run record includes every tested offset strength and its
reported eligible or diagnostic result and audit status. It stores its own
exact solver geometry and telemetry, including the explicit starting speed of
its final pass. Its `settings.path_planning.algorithm` ends in `v7_continuous_scalar_clearance`;
`fourth_strength_policy` names the bounded quadratic, clearance screen, and 0.75 fallback.
Read `candidate_trials[].offset_strength`, path audit, and eligible versus
diagnostic time for the actual fourth probe; its position in the trial list
does not imply a fixed 0.75 strength or an eligible result. Every completed
AI trial has its own content-identified record with exact solver geometry,
recorded telemetry, and final-pass start speed. The primary record's
`baseline_record` and `candidate_trials[]` entries identify the selected
record as `selected_result` and link other saved runs by `run_id`. The
existing `comparison_counterpart_run_id` still points to the comparison
counterpart. At most four path records are saved per AI comparison. A geometry-screened
trial has its audit and skip reason in the primary record but no model run ID;
an interrupted extra trial likewise keeps its error summary without a
replayable record.
For an audit-failed default course, the primary record is flagged diagnostic,
and no record represents a selected winner. A candidate-only display after
the baseline fails is also marked `diagnostic_only`, even if that candidate
itself completed. Each record identifies the selected source course by ID;
AI path-planning metadata additionally saves the source label, description,
synthetic flag, and exact source-geometry hash. These records do not provide a
full ghost/session replay.

The **Timed sessions · WIP** tab has an enabled **Run 80 m synthetic pose
preview** button, **Save last synthetic trace…** and **Load synthetic
trace…** controls, a **Road condition** selector, and an **Initial lateral
offset (m)** box; **Start timed session**
remains disabled. **Uniform base grip (1.0×)** is the initial choice. **Assumed
bend patch (0.3×)** adds one world-fixed rectangle on the first synthetic
bend, x 36–55 m and y −3–16 m, with a local friction multiplier of 0.3. The
offset defaults to zero; positive starts left of travel and negative right.
The box accepts finite values through the nominal **±1.9 m** CG allowance
under the assumed width. This is an input bound, not a promise that the whole
car starts inside the corridor: at **−1.9 m** on the curved synthetic start,
the sampled axle-span rectangle is outside and the model stops before issuing
controls. The preview runs the separate time-domain four-wheel car on the coherent
synthetic loop using rear-axle pure-pursuit steering, a bounded future
curvature/road-grip speed target, and bounded drive/brake requests. The
controller samples reference-path grip ahead of the car so it can request
braking before the assumed patch. It also reduces that prior target as the
sampled assumed body-corner slack and predicted outward motion approach the
edge. The edge rule is a conservative speed response; the focused offset
cases also completed without it, so these runs do not establish improved
clearance. Both choices are synthetic sensitivity scenarios; neither is a
measured dry/wet tire or road map. The chosen scenario and starting offset
are frozen for the worker and identified in its live status and replay.
Changing either while idle clears only an old pose preview, not an ordinary
lap replay. The pose preview is limited by
target progress, simulated time, control-step count, and internal integration
steps. A supplied coherent course with cells longer than 0.5 m is validated
and split into analytic straight/circular subarcs before driving, with a
100,000-cell refinement cap; the shipped 0.5 m source grid is retained. The
local projection considers cells overlapping the station window, including
overlapping lap copies across the seam, and clips the station to that window.
These are numerical geometry repairs, not continuous road-edge checks; the
controller still uses short x/y chords. It opens Driver view immediately
and shows the latest simulated planar x/y and heading while solving, then
plays the complete trace. This differs
from mapping station onto reference x/y as ordinary lap playback does. The
display labels its time as **pose-model time** and identifies the synthetic
four-wheel experiment; it does not show an endurance-model lap time, energy,
or battery result. During the live calculation it shows speed, progress,
tracking error, local grip, assumed footprint slack, and yaw rate; controls
and lateral acceleration display dashes until completed replay. Its replay
number boxes then show recorded steering, rear-wheel drive, and front-wheel brake
requests too. The default ±3 m corridor, 1.8 m vehicle width, and 0.2 m
margin are assumptions. The sampled body-rectangle check covers the span
between axle lines under that corridor, with no surveyed boundary, overhang,
or between-sample swept-area certificate. The future-speed calculation is a
planning heuristic, not a tire-force or clearance certificate. This WIP
preview always uses the fixed 300 kg synthetic four-wheel car and does not
use the selected Prius/TREV profile or feed the default centerline lap. A full
interactive session, ghost,
Terps vehicle/controller, and linked comparison report remain future work.
The saved synthetic pose trace is a versioned short experiment, distinct
from a complete session or the standalone main-lap record replay below.

After a preview, **Save last synthetic trace…** checks and writes the frozen
run to a separate JSON file; the default folder is
`%LOCALAPPDATA%\LapSim\pose_runs` on Windows. **Load synthetic trace…**
checks a selected file in a worker and plays its recorded pose in Driver view
when it has driven steps. A zero-step stop is still a valid record and loads
with an explicit no-driven-step status. The schema-v1 file keeps the exact
processed course, synthetic car, road and patches, controller settings,
control/time/state history, pre-step force evaluations, pose samples,
termination status, and source/runtime identity. Capture computes a
SHA-256 content ID; load checks it. Both check the saved evaluations against
current model equations and run recorded-control numerical replay.
Evaluation floats allow `1e-9` absolute or `1e-10` relative drift, while
field names, array lengths, and discrete values must match exactly; pose
states have separate replay tolerances. A
matching hash alone does not prove
the simulated dynamics agree, and replay does not validate a measured car.

**Run comparison** simulates two selected saved/built-in profiles with the
same selected centerline course, solver spacing, driver request, and rolling
start speed. It prepares both cars' speed limits and uses the lower first-cell
braking ceiling as a feasible start for both. Each car then runs one recorded
lap; the saved records include that explicit common speed for replay. The
comparison window shows the selected course, shared start, both values, and
B-minus-A differences for each numeric output. Their finish speeds may differ,
so these remain one-pass initial-condition laps. The speed plot
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

For the result currently displayed, **Saved run details** opens a read-only,
selectable-text evidence window. It gives full record IDs and file paths,
profile and result status, source course and boundary status, solver path and
cell count, and AI assumption/ranking status when applicable. It includes both
cars after a comparison and follows the primary AI record's available trial
links. The window reports a missing or invalid linked file instead of treating
the link as a completed record. This viewer loads saved model records; it does
not rerun the lap or establish vehicle validation.

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

The synthetic pose preview retains each issued control and resulting planar
state in its `PoseDriverRun`, which can also be saved through
`PoseRunRecord.capture(run).save(path)` and reconstructed with
`PoseRunRecord.load(path)`. For engineering checks,
`replay_pose_driver(run, tolerances=PoseReplayTolerances())` reintegrates the
saved controls with the same four-wheel configuration and environment. Its
default absolute tolerances are **1e-8 m** for position, **1e-8 rad** for
heading, **1e-8 m/s** for body velocity, **1e-8 rad/s** for yaw rate, and
**1e-8 rad/s** for wheel speed. It also recomputes the recorded sample times,
path progress, cross-track and heading errors, local grip, assumed footprint
slack, projection validity, and stop status under explicit tolerances, and
checks road-validity agreement. This is numerical replay of a short synthetic
maneuver, distinct from the saved
v2 endurance-lap record replay and from a persistent full-session record.
The programmatic replay starts from the trace's recorded initial planar
state; the **pose record loader** additionally checks that the initial state
matches its saved course and offset settings. Neither establishes measured
corridor clearance.

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

The fused course's default solver grid resamples curvature by a
distance-weighted mean. This
preserves integrated signed curvature over the lap; x/y coordinates are
interpolated at the new cell boundaries. A new global grid can average across
old curvature discontinuities, changing the squared-curvature demand used by
the tire model. For a diagnostic refinement of an existing `SpatialTrack`, the
programmatic `track.refine(maximum_cell_length_m)` instead splits each original
cell, retains every old boundary and its piecewise-constant curvature, and
interpolates interior x/y points along the old chord. It preserves track
length, each original cell's signed turn, and its length-weighted squared
curvature, with a 100,000-cell safety cap. This chord-linear QA method remains
unchanged; it does not perform either synthetic course's analytic subarc
subdivision or certify geometric consistency. It does not change the desktop's
default grid or repair an inconsistent source map. Grid spacing still affects
the speed-envelope and cell integration, so resolution checks remain
necessary. The Prius benchmark is for software demonstration and input
checking, not engineering sign-off.

The supplied ENME408 research report motivates a separate time-domain
four-wheel model rather than changing this prescribed-path solver into a
torque-vectoring claim. The lap and dynamics calculations currently answer
different questions; no motor or battery controller connects them yet.
