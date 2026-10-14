# LapSim team guide

LapSim estimates vehicle performance on a prescribed course and records the
inputs, solver geometry, controls, and telemetry behind each result. Use the
synthetic courses for a first demonstration. The shipped fused GNSS/IMU course
has a documented mismatch between plotted coordinates and physics curvature.
Its ordinary lap calculation can run, but the picture is not evidence that a
car followed that path or cleared cones.

## Run the shared Windows app

Download the team's `LapSim-Windows-x64.zip`, extract it, and double-click
`LapSim.exe`. This is a single-file Windows x64 application with Python,
Tkinter, Matplotlib, and mandatory course data bundled. Recipients do not
need to install Python. The first launch extracts its runtime into a temporary
folder and can take longer than later launches. Use a Windows x64 computer;
this build is not a macOS/Linux executable.

The shared ZIP also contains offline documentation, the expandable simulator
map, a source snapshot, and release test evidence. **Simulator map** in the
desktop header opens a durable local copy of the map and its source references.
You can also open `docs/simulator_flowchart/index.html` from the extracted ZIP.
Normal demonstrations work offline.

The executable is unsigned. Windows may identify an unfamiliar publisher or
show a reputation prompt. Confirm the download is the expected team artifact
and compare its published SHA-256 when available. Team IT may require an
approved or signed build; follow that process rather than disabling organization
protections.

See [release and rebuild instructions](release.md) for build identity,
distribution contents, verification, and frozen-runtime command options.

## Run from a source checkout

Use Windows with 64-bit Python 3.11 or newer, including Tkinter. Open the
repository folder and run `setup_lapsim.cmd` once, then `launch_lapsim.cmd`.
Setup needs internet access to install the dependencies. After installation,
the built-in courses and ordinary simulation run locally.

The equivalent developer commands, from the repository root, are:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup_lapsim.ps1
.\.venv\Scripts\python.exe -m lapsim.ui
```

The window starts at 1380 × 900 and permits resizing to 1080 × 720. The input
panel scrolls on smaller displays. Leave a calculation running while using the
plots; it computes in a worker thread.

## A repeatable first demonstration

1. Select **Prius benchmark**, **Synthetic loop · AI demo**, and
   **Centerline (default)**. Leave **Cell size (max)** at **1 m** and
   **Assumed road grip** at **100%**. Set driver request to **80% (enter 80)**.
2. Run one lap. Read the completion status before using time or energy. Show
   the calculation progress, Analysis plot, and Driver view playback. The
   ordinary Driver view maps model telemetry onto a reference course; it does
   not integrate planar vehicle pose.
3. Open **Saved run details**. Keep the full JSON record and record ID when
   sharing numbers. They identify the car inputs, source course, solver grid,
   starting speed, status, and aligned telemetry.
4. Select **AI racing line (experimental)** on the same synthetic course.
   Use **Compare path numbers** and inspect path audit and speed-seam status
   before reporting a gain. Show eligible baseline and candidate replays.
   A diagnostic or rejected path cannot support a ranked gain.
5. Open the [interactive simulator map](simulator_flowchart/index.html).
   Expand a subsystem, inspect its variables and equation details, and follow
   its source references. Read the [map controls](simulator_flowchart/README.md)
   for search, zoom, and maintenance.

For a five-minute presentation with deeper optional demonstrations, follow the
[team demo brief](team_demo_brief.md). Read actual current results from the app;
numbers in historical validation documents describe their stated configurations.

## Choose the calculation deliberately

| Route | What it calculates | How to interpret it |
|---|---|---|
| Desktop centerline | One distance-domain, rolling-start prescribed-path lap | Initial-condition model estimate; entry and exit speed may differ |
| Desktop two-car comparison | Two cars on the same selected course and one common feasible starting speed | A modeled comparison under matched run settings |
| Desktop AI racing line | Bounded offline geometry proposals, then laps with closed seam speed | Rank only complete, audited, eligible paths; corridor is an assumption |
| Four-wheel lab | A short synthetic time-domain maneuver with wheel-force and yaw dynamics | Torque-allocation sensitivity, separate from engineering lap time |
| Timed sessions · WIP | A bounded synthetic feedback-steering pose preview, normally 80 m | Synthetic trace; fixed 300 kg car, separate from the chosen lap profile |
| Python event API | Acceleration, skidpad, or endurance with a shared points/telemetry result | Read the selected event's rules, rollout, scoring, and completion contract |

The Prius is a simplified power-equivalent front-drive benchmark, not a hybrid
transaxle model. The repository baseline and optional TREV scenarios have their
own parameter provenance. TREV source profiles require the separate local
ENME408 evidence package; their absence does not prevent the ordinary demo.

## Configuration, units, and signs

Model API names carry their units. Most physical values are SI; hydraulic
brake pressure remains **psi**, motor speed telemetry uses **rpm**, and GUI
speed inputs and selected displays use **km/h**. Avoid copying displayed
numbers into differently named API fields without conversion.

| Quantity | API/model unit and convention | Desktop or record detail |
|---|---|---|
| Course station, X/Y, length, cell size | m | Station begins at zero and increases strictly |
| Course curvature | 1/m, signed | One value per cell; separate from tire slip ratio |
| Mass | kg | Total configured vehicle mass |
| Speed | m/s internally | `top_speed_kph` uses km/h; divide by 3.6 for m/s |
| Power | W internally | Editable `peak_power_kw` uses kW; multiply by 1000 |
| Energy | J internally or kWh in results | 1 kWh = 3,600,000 J; pack terminal energy |
| Torque | N m | `motor_torque_request_nm` is nonnegative propulsion |
| Brake pressure | psi | Nonnegative front/rear requests, bounded by brake model |
| Regenerative brake request | N | Nonnegative requested opposing force; use axle regen fields |
| Steering/heading | rad | Body axes forward/left/up; positive planar yaw is counterclockwise |
| Normal and tire forces | N | Wheel order: front-left, front-right, rear-left, rear-right |
| Tire friction/grip | Dimensionless | Desktop percent 100 means multiplier 1.0 |
| Driver request | API fraction [0, 1] | Desktop percent 80 means fraction 0.8 |
| SOC | Fraction [0, 1] | Positive battery terminal power means discharge |
| `CdA` | m² | Product of drag coefficient and reference area |
| Lift coefficient `Cl` | Dimensionless, signed | Negative values produce downforce in the lap aero model |

Controls are held over a spatial cell. The lap model solves
`v_next² = v² + 2 a Δs`, then obtains elapsed time from the cell's average speed
and evolves time-dependent battery/component state with that time. This is
different from the four-wheel model's time steps and RK4 pose integration.

Adjust parameters on the owning component, then call `vehicle.validate()`.
Create a fresh vehicle or reset it before an independent run. The public
`Vehicle` is mutable; do not reuse accumulated battery or tire state accidentally
for a comparison. The desktop's run and comparison helpers manage their reset
and matched-start behavior.

[Baseline parameters](model_parameters.md), [battery equations](battery_model.md),
[architecture](architecture.md), and the [engineering handoff](engineering_handoff.md)
give complete parameter ownership, force/power flow, equations, sign conventions,
and source assumptions.

## Courses and source data

Built-in synthetic courses are coherent analytic straight/circular paths. The
fused endurance CSV is a supplied recording with independent curvature and X/Y
reconstructions. No built-in course has surveyed boundaries.

Use **Import course…** for a versioned, coherent closed course JSON bundle.
Prepare it from a consistent CSV with `scripts/create_course_bundle.py`; follow
the [course-bundle format](course_bundle_format.md) for exact columns, hashing,
geometry gates, and versioning. A v2 bundle may preserve source-relative left
and right widths. The AI planner still uses its editable assumed uniform width
because its smoothed reference frame differs from the source widths' frame.

The desktop limits generated grids to 5,000 cells/points. Reduce requested
resolution only when needed: a smaller maximum cell size increases work.
Analytic refinement retains original source stations and endpoints. The
optional AI route builds its own processed grid. Record the actual individual
solver lengths rather than assuming that every cell equals the requested maximum.

Raw MF4 analysis needs the optional `mf4` dependency and the matching CAN/DBC
inputs. Those recordings and the local ENME408 evidence package are not required
for built-in demonstrations and are not automatically part of a shared app.

## Saved data and sharing a result

Windows user data lives outside the application directory:

| Location below `%LOCALAPPDATA%\LapSim` | Contents |
|---|---|
| `car_profiles.json` | Named user-created benchmark inputs |
| `courses` | Imported local course bundles |
| `runs` | Main-lap records, including completed AI trial records |
| `dynamics_runs` | Separate four-wheel A/B experiment records |
| `pose_runs` | Synthetic pose trace Save/Load files by default |
| `documentation\<source hash>` | Durable offline help/map/source cache for a portable build |
| `logs\desktop_startup.log` | Unexpected desktop startup traceback |

Use **Saved run details** to locate the precise main-lap files. For AI mode,
share the primary record and all linked trial records if teammates need to
compare paths. The content hash checks record integrity; it does not validate
the car or prove numerical replay agreement.

Completed v2 one-lap records can be checked from the source development setup:

```python
from lapsim.experiments.lap_replay import replay_lap_record

report = replay_lap_record(r"C:\path\to\saved-run.json")
print(report.to_dict())
assert report.model_agreement
```

Replay uses the saved solver grid, controls, effective vehicle configuration,
and per-cell grip values when present. `model_agreement` is separate from source
and runtime provenance warnings. Interrupted laps and legacy records without a
complete v2 accepted-cell trace cannot use this replay checker. Synthetic pose
traces have their own Save/Load and controller/dynamics replay gates.

## Physical and numerical limits

The main lap follows prescribed curvature and uses quasi-static load transfer,
low-order tire/aero models, and the configured powertrain/battery assumptions.
It does not integrate a driver's independent X/Y/yaw trajectory, survey cones,
or prove a swept-body clearance. The optional scalar corridor certificate is
relative to the supplied/assumed path-width model. One rectangular low-grip
patch in AI mode conservatively lowers whole-cell tire capacity when any mapped
nominal wheel contact touches it; this is distinct from per-wheel pose physics.

Several baseline parameters were fitted using the same historical endurance
lap used for replay. Agreement there is calibration consistency, not held-out
prediction accuracy. Thermal derating, tire temperature/wear, full transient
suspension, detailed CFD maps, and a complete validated team-car controller
remain outside the current model. A passing software suite does not establish
real-car predictive accuracy. See the handoff's evidence-level table and
[verification guide](verification.md) before presenting claims.

## Troubleshooting

| Symptom | Action |
|---|---|
| Source setup cannot find Python | Install 64-bit Python 3.11+ with Tcl/Tk; rerun setup |
| Source `.venv` is unsupported or incomplete | Rename that folder for recovery, then rerun setup |
| Tk startup or canvas failure | Run `scripts/check_desktop.py` with the checkout's Python; inspect the startup log |
| No TREV source profiles | Install the separate evidence package in its documented location; use a built-in profile meanwhile |
| Invalid or slow cell-size request | Use a finite positive maximum, begin at 1 m, and stay under the grid cap |
| AI result is diagnostic or no gain selected | Inspect path audit, closure, and baseline status; demonstrate the coherent synthetic course |
| Import fails | Check bundle schema, coherent arcs, monotonic station, revision, and source hashes |
| No numerical replay agreement | Read metric differences and provenance warnings; use the same release/model and exact saved record |
| User profile file is malformed | Back up `car_profiles.json`, then move it aside and restart; do not overwrite needed inputs |
| A calculation fails | Preserve its saved record and error, with last accepted distance/cell and settings; failed attempted state may be ahead of telemetry |

When reporting a bug, provide the release/build identity, Windows version,
course ID/revision, car profile, all changed settings, expected versus observed
behavior, error/log, and the relevant saved records. Include a minimal repeatable
sequence rather than only a screenshot.

## Developer orientation

`lapsim` owns courses, controls, events, solvers, optimization, UI, profiles, and
records. `vehicle_model` owns replaceable component physics and mutable state.
The desktop calls `ui/simulation.py`, `PathConstraintSolver`, and
`EnduranceSimulator`; the generic event/scoring facade and older lap-time tools
are distinct entry points. `analysis/` contains historical studies and data
preparation, not the desktop's main runtime.

Start with [architecture](architecture.md) and [extending models](extending_models.md).
Keep force evaluation deterministic, preserve units and component ownership,
avoid counting rotational inertia twice, and version record-format changes.
Follow [verification](verification.md) for software and release checks.

For the complete isolated-module sweep, run
`.venv\Scripts\python.exe scripts\check_all.py`; it writes
`work/test-results.xml`. The verification guide also shows how to retain
`work/test-suite.log` and distinguish the final release report from an earlier
combined-suite baseline.
