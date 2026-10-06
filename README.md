# Formula SAE Event Simulator

Simulate endurance, acceleration, and skidpad from a distance-indexed controls
profile and track. Every event returns estimated points, timing, energy,
completion status, and aligned component telemetry through one result type.

The vehicle is composed from independently replaceable motor, inverter,
chain-drive, battery, aero, chassis, suspension, tire, and brake models. The
included implementations are intentionally simple baselines; their interfaces
are stable seams for higher-fidelity models.

`vehicle_model/vehicle.py` is the top-level coordinator. Component files are
organized by the `electrical`, `aero`, `powertrain`, and `mech` subteam
packages, while the root `vehicle_model` package continues to re-export the
main classes for concise imports.

## Documentation

- [Engineering handoff](docs/engineering_handoff.md): the complete software,
  math, GUI, data, verification, and model-limit walkthrough for a new lead.
- [Engineering handoff PDF](output/pdf/LapSim_Engineering_Handoff.pdf): a
  formatted copy of the same source report for review and sharing.
- [Architecture](docs/architecture.md): package boundaries, data flow, state,
  and parameter ownership.
- [Event simulation](docs/event_simulation.md): the shared profile/track API,
  points models, telemetry contract, and runnable analysis entry points.
- [Extending models](docs/extending_models.md): replace a component, add state,
  and run parameter sweeps.
- [Baseline parameters](docs/model_parameters.md): defaults and the power-flow
  convention.
- [Battery model](docs/battery_model.md): OCV lookup, SOC update, one-RC
  polarization, and voltage limits.
- [Battery voltage validation](docs/battery_voltage_validation.md):
  battery-only endurance fit and residuals.
- [One-RC battery validation](docs/battery_rc_validation.md): dynamic fit,
  chronological holdout, and transient plots.
- [First endurance-lap validation](docs/first_endurance_lap_validation.md):
  current-default recorded-control replay, graphs, and limitations.
- [Open-loop first-lap SOC validation](docs/first_lap_soc_validation.md):
  distance-indexed controls-plus-curvature replay and comparison with HVC SOC.
- [Endurance analysis](analysis/endurance/README.md): full-lap distance replay,
  drivetrain signals, acceleration, braking, and wheel slip.
- [Straight acceleration comparison](analysis/accel/README.md):
  corrected-IMU versus recorded-control replay on map-defined straights.
- [Endurance torque-profile optimizer](docs/endurance_optimizer.md): reusable
  track/vehicle architecture, Michigan 2026 scoring, sweeps, and limitations.
- [LapSim desktop app](docs/simulator_desktop.md): editable vehicle setup,
  top-down course navigation, optional path planning, driver playback, saved
  lap records, and comparison traces.
- [Versioned course bundles](docs/course_bundle_format.md): prepare coherent
  course CSVs, create portable revisions, import them in the desktop, and
  trace their source and solver geometry in saved runs.
- [Optional AI racer design and checks](docs/ai_racer_design.md): bounded path
  search, geometry assumptions, model comparison, and known limits.
- [Team demo brief](docs/team_demo_brief.md): a five-minute walkthrough,
  evidence to show, and measurements needed before car or course decisions.
- [Four-wheel dynamics](docs/four_wheel_dynamics.md): synthetic independent-wheel
  torque-allocation experiment, wind and local road grip, equations, and limits.
- [Source-backed vehicle profiles](docs/source_vehicle_profiles.md): local
  engineering registry, profile adapter, provenance, and headless commands.

## LapSim desktop app

On Windows, install **64-bit Python 3.11 or newer** with Tkinter, then from this
checkout run the one-time setup. It creates `.venv`, installs the required
packages, and checks that the app can import and load its bundled course:

```powershell
./setup_lapsim.cmd
./launch_lapsim.cmd
```

You can also double-click those two files in that order. For a terminal-only
setup without the batch file's final pause, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup_lapsim.ps1
.venv\Scripts\python.exe -m lapsim.ui
```

Run the complete repository checks with
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_all.ps1`.
The setup installs pytest; the checker runs every test file in small, separate
processes to fit a memory-limited Windows machine.

The launcher checks Python, Tk, app imports, and the bundled course before
opening a console-free window. A later startup error is shown in a message box
and saved under `%LOCALAPPDATA%\LapSim\logs\desktop_startup.log`. The app runs
from this source checkout because the default course is stored here; it is not
a standalone EXE. The app defaults
to the fused team endurance course and has an explicit **Course** menu for
synthetic rounded-rectangle and FSAE-style practice courses. **Import course…**
adds a validated, versioned course prepared from a coherent CSV and preserves
it in the local course catalog across launches; see the
[course-bundle guide](docs/course_bundle_format.md). It offers editable
2026 Prius LE benchmark inputs, saved
local car profiles, source-backed TREV5 working scenarios when the external
data package is present, and a two-car lap comparison with one feasible
rolling-start speed for both cars. The **Four-wheel lab**
opens a separate top-down torque-allocation comparison with individual wheel
slip and force displays. It exposes world-frame wind, air density, drag area,
base grip, and an optional fixed low-grip rectangle for paired sensitivity
studies. Completed and interrupted lap runs save local JSON records of inputs
and telemetry. The lap desktop also has an **Assumed road grip** input, default
100%, that uniformly scales the selected tire model's lateral and longitudinal
force capacities for a sensitivity run. It applies to centerline, AI, and
two-car comparisons and is saved with each run for replay. It is an assumed
uniform multiplier, not a measured wet/dry or local-surface model. Changing
run inputs clears the previous displayed result and playback. The centerline
solver defaults to a requested maximum 1 m step.
The fused course is resampled to that step; synthetic and imported coherent
courses retain their exact source arc cells when the request is at least as
large as their longest cell. For a finer request, the desktop strictly validates the source's
station, x/y, and constant-curvature geometry, then subdivides each source
cell into analytic straight or circular subarcs. Every original station and
endpoint remains on the solver grid. A 5,000-cell guard counts the resulting
subdivisions. This is a check of the numerical solver representation, not a
survey or evidence of measured course boundaries.
See the [desktop guide](docs/simulator_desktop.md) for data and model limits.

The **Driving path** control defaults to the ordinary centerline solver and
does no path optimization. Its optional **AI racing line (experimental)** mode
uses an assumed track half-width, vehicle width, and margin to propose one
smooth line and compare it with a geometric centerline using the same car and
physics solver. The baseline (strength 0), full offset (1), and
half offset (0.5) are checked first. A failed candidate clearance audit
skips its physics pass when the geometric baseline is valid. If all three
paths have eligible audits and times,
and half beats both endpoints by more than 0.05 s, a convex quadratic through
those times chooses the nearest safeguarded fourth strength from 0.25, 0.375,
0.625, 0.75, or 0.875. If full offset fails its path audit but eligible half
offset clearly beats the baseline, a short geometry-only search tries a stronger
fourth offset with at least 0.02 m of certified scalar clearance. In other
cases the fourth strength is 0.75. Each path admitted to physics receives one
dry speed-seam pass and one recorded pass, for at most eight lap-model passes
across four paths. A
completed lap is eligible for a path comparison only when its start
and finish speeds agree within 0.005 m/s and its integrated prescribed-curvature
path passes the declared clearance and position-closure checks. The audit
evaluates four positions per modeled cell plus every source corridor-cell
boundary and midpoint, then bounds lateral clearance between evaluations and
subdivides close intervals. An unresolved interval is ineligible. A shared
boundary uses the narrower adjacent width, including at the closed seam.
Allowable scalar corridor excess is 1e-8 m and the worst integrated-path, saved-path, and reference seam gap must be
at most 0.01 m. The certificate covers this continuous *normal-coordinate*
inequality under the supplied width model. It does not certify the swept
vehicle body, world-frame containment, or surveyed cone clearance.
For eligible paths, the app selects a candidate only when its gain over the
geometric baseline is strictly greater than 0.05 s. A smaller positive gain
is an unresolved numerical tie; the 0.05 s margin is a provisional selection
heuristic, not a proven error bound.

The optional **Synthetic loop · AI demo** course is a 195.398224 m rounded rectangle:
two 40 m and two 20 m straights joined by four 12 m radius quarter-circle
arcs, stored in 0.5 m source cells. Its default AI inputs are an *assumed*
±3 m corridor, 1.8 m vehicle width, and 0.2 m safety margin. With the Prius
benchmark at model torque fraction 0.8 (enter 80 in the desktop's percent box)
and assumed road grip 100%, a current
speed-periodic model run gave
**16.949850 s** on the eligible geometric baseline, **15.691924 s** on an
eligible half-offset path, and **14.617662 s** on the selected 0.95-offset
path. The full-offset path failed clearance at an evaluated point by **0.040636 m**
and was skipped before the lap calculation; it has no modeled time or replay.
The fourth path passed its continuous scalar audit with a conservative
0.053396 m lower bound on modeled clearance and had a **2.331539 s** lead under
the 0.05 s rule. This is a synthetic software
demonstration, not a surveyed Formula SAE course or a validated team-car gain.

**Synthetic FSAE-style · practice** is a separate 817.079633 m analytic lap
inspired by the [2027 Formula SAE endurance layout guidance](https://www.fsaeonline.com/cdsweb/gen/DownloadDocument.aspx?DocumentID=da79bcb4-0935-4f7b-83d7-0dbb8ce68d38).
It repeats 60 m and 45 m straights with alternating 15 m radius bends, and
its exact straight/circular-arc source geometry closes without map correction.
The starting ±3 m AI half-width is an editable assumption. It has no surveyed
cones, measured boundaries, passing zones, or official event layout, and its
computed times are not competition predictions. The fused team recording
remains the startup course and **Centerline** remains the default driving path.
With the built-in Prius and 80% torque request on this analytic course, the
optional AI comparison selected a 0.975-offset path at **59.859115 s** against
its eligible processed baseline at **60.154777 s**. The **0.295661 s** modeled
lead is a software scenario result under the assumed corridor.

The default recorded course has no surveyed widths, and its x/y map does not agree
with its stored solver curvature. The Analysis tab reports 3.657937 rad of
prescribed turn versus 6.283185 rad of map winding, up to 0.235787 m
disagreement between individual solver arc-chord lengths and plotted map-chord lengths,
and a 542.633 m closure gap when the stored curvature is integrated from the
first map-chord heading.
The AI processed geometric baseline also has a 0.750897 m integrated closure
gap because its polygon chords and constant-curvature arcs disagree. On the
shipped course with an assumed ±2 m corridor, 1.78308 m car width, and 0.3 m
margin, completed Prius baseline and
offset laps currently fail the path audit; displayed starred times
are diagnostic only, the time difference is blank, and there is no selected
AI winner. Ordinary centerline remains the default driving mode; the new exit-force check also applies to its physics. AI-mode eligible times,
when available on a coherent course, should be compared only with the AI-mode
geometric baseline, not the ordinary centerline lap. The **Driver view** shows accepted solver-step progress on a reference
path, then plays back numeric telemetry against the exact solver-grid x/y saved with that run. Cell model boxes show each accepted cell's torque and brake requests, achieved forces, acceleration, signed battery power, and next-entry speed ceiling. This applies to ordinary centerline and car-comparison runs as well as AI paths; the separate top-down course plot continues to show the source map. The displayed position and map heading are not an integrated vehicle pose, and the fused course's x/y still disagrees with its physics curvature. Its **Replay
lap** menu switches between A and B after a two-car comparison, or among
the completed AI trials after an AI run, without running physics again.
A geometry-rejected trial has no replay. Each completed AI trial has a
content-identified local run record with its own telemetry and exact solver
geometry. The primary record links to the other trial IDs; its own selected
trial is identified as `selected_result`. Diagnostic runs remain available
for inspection but must not be ranked. Records identify the selected source
course by ID; AI metadata also marks a synthetic course explicitly and records
the fourth-strength policy and every tested `candidate_trials[].offset_strength`.
Read those values rather than assuming the fourth path always uses 0.75.
Candidate-only displays with a failed baseline are marked diagnostic. Completed v2 lap records
can be checked on demand with the programmatic `replay_lap_record()` API: it
reruns their recorded cell controls on the saved solver grid and reports
numerical agreement. The lap model also checks both requested and achieved
curvature against the prescribed cell curvature within a default 1e-9 1/m
tolerance before accepting a cell. This does not verify the plotted x/y path
or cone clearance. **Timed sessions · WIP** remains a disabled placeholder
for an interactive drive, ghost, complete session capture, and report workflow.

## Basic use

```python
from lapsim import (
    ConstantControlsProfile,
    Controls,
    SpatialTrack,
    simulate_acceleration,
)
from vehicle_model import Vehicle

track = SpatialTrack.from_cells(
    cell_length_m=(0.5,) * 150,
    curvature_per_m=(0.0,) * 150,
    closed=False,
)
profile = ConstantControlsProfile(
    Controls(motor_torque_request_nm=230.0)
)
result = simulate_acceleration(Vehicle(), track, profile)

print(result.estimated_points)
print(result.scoring_time_s)
print(result.telemetry["motor.speed_rpm"])
```

Swap in `simulate_skidpad` or `simulate_endurance` without changing the
profile, track, result, or telemetry concepts. The older speed-limit,
minimum-lap-time, and recorded-replay APIs remain available as lower-level
physics and validation tools.

Parameters live on the component that owns them:

```python
vehicle.drivetrain.motor.peak_power_w = 60_000.0
vehicle.drivetrain.inverter.efficiency = 0.96
vehicle.drivetrain.chain_drive.ratio = 4.1
vehicle.aero.frontal_area_m2 = 0.983996414
vehicle.aero.drag_coefficient = 1.6048838348
vehicle.aero.lift_coefficient = -2.4206997842
vehicle.validate()
```

The active-aero model has automatic straight-line deployment plus forced
positions for switching and fail-safe studies. The vehicle factory includes
the installed-system mass penalty:

```python
from vehicle_model import ActiveAero, Vehicle

vehicle = Vehicle.with_active_aero(
    active_aero_mass_penalty_lb=3.0,
    aero=ActiveAero(
        drag_reduction_fraction=0.30,
        downforce_reduction_fraction=0.30,
        straight_curvature_threshold_per_m=0.005,
    ),
)
vehicle.aero.set_deployment_mode("automatic")
# Alternatives: "low_drag" or "high_downforce".
```

To add a detailed model, supply an object implementing the corresponding
protocol in `vehicle_model.interfaces`. No solver changes are required while
the interface still describes the needed physics.

## Inferring delivered torque from an MF4 log

`scripts/infer_delivered_torque.py` decodes GNSS ground speed, fits a local
quadratic to calculate acceleration, and applies the inverse longitudinal
vehicle model:

```text
wheel force = effective mass * acceleration + drag + rolling resistance
motor torque = wheel force * tire radius / (ratio * differential efficiency)
```

Install the MF4 extra with Python 3.11-3.13, then supply the CAN database:

```powershell
python -m pip install -e ".[mf4]"
python scripts/infer_delivered_torque.py logs/6.24_accel.MF4 `
  --dbc path/to/can9-database.dbc `
  --feedback-dbc path/to/inverter.dbc `
  --hvc-dbc path/to/hvc.dbc `
  --start-s 1759.04515 --end-s 1763.04675 `
  --motor-power-limit-kw 70 `
  --output outputs/real_accel_validation/run13_inferred_torque.csv `
  --plot outputs/real_accel_validation/run13_inferred_torque.png `
  --motor-speed-derivative-plot `
    outputs/real_accel_validation/run13_motor_speed_derivative.png `
  --slip-comparison-plot `
    outputs/real_accel_validation/run13_slip_aware_torque_comparison.png
```

The CSV retains signed inverse-model torque and a propulsion-only version. A
negative signed value describes the wheel force required by the measured
deceleration; it is not proof that regenerative braking was active. It also
reports both wheel-equivalent torque reflected through the gear ratio and the
higher motor-shaft torque after correcting for post-motor differential loss.
The inference uses GNSS ground-speed acceleration and the simulator's no-slip
equivalent rotating mass. During wheelspin it does not include torque that goes
into accelerating the driven wheels relative to the vehicle, so it can
underestimate delivered motor torque.

When an HVC DBC is supplied, the slip-aware comparison also back-calculates
battery-terminal power from measured motor speed and inferred motor-shaft
torque. It divides motor mechanical power by the configured motor and inverter
efficiencies; differential loss is not applied again because it is already in
the motor-shaft torque inference. Measured battery power is calculated as
`HVC_Current_High_A * HVC_Batt_Voltage_V` so high-power operation does not
saturate the current measurement.

`SpeedLimitSolver` calculates unconstrained local speed ceilings, using the
vehicle's maximum speed wherever cornering does not impose a lower limit.
`LapTimeSolver` then performs the acceleration and braking passes from the
specified starting speed, integrates the resulting profile, and creates
telemetry.

## Distance-domain simulation

`Vehicle.update_state(controls, distance_step_m)` advances exactly one positive
spatial cell. It solves `v_next^2 = v^2 + 2*a*distance_step`, derives elapsed
time internally from cell-average speed, and passes that time to the battery,
drivetrain, brake, suspension, tire, and aero states. The tire model resolves
normal load, lateral force, drive/brake force, combined capacity, and slip at
each contact patch. Motor speed follows the average driven-tire surface speed,
and rotational inertia is retained as equivalent longitudinal mass.

Explicit control sequences can be run with the public `replay_controls()` API.
`RecordedLap` loads synchronized track and control data for validation.

Replay telemetry is a namespaced mapping populated by the vehicle and each
component:

```python
telemetry = replay_controls(vehicle, controls, distance_step_m=0.25)
speed_mps = telemetry["vehicle.speed_mps"]
traction_limited = telemetry["limits.traction_active"]
all_channels = telemetry.as_dict()
```

Higher-fidelity component models add signals through `update_telemetry()`;
the replay and recorder do not require a central schema change.

## First endurance-lap validation

Extract the first completed lap from the competition MF4, then replay its
distance-indexed controls through the current vehicle model:

```powershell
python scripts/extract_first_endurance_lap.py
$env:PYTHONPATH='src'
python scripts/validate_first_endurance_lap.py
```

The validation performs no parameter fitting and does not alter vehicle
defaults. It writes plots, telemetry, and metrics under
`outputs/endurance_validation/first_lap_soc_open_loop/`. The replay assumptions
are documented in `docs/first_lap_soc_validation.md`.

## Endurance torque optimization

The endurance solver optimizes a periodic normalized motor-torque request on
an injected spatial track, fresh vehicle factory, and scoring model. Run the
Michigan 2026 benchmark and its spatial-resolution verification with:

```powershell
$env:PYTHONPATH=(Resolve-Path src)
.\.venv\Scripts\python.exe scripts\optimize_mi6_endurance.py
.\.venv\Scripts\python.exe scripts\verify_endurance_profile.py
```

The implementation is grouped under `lapsim.courses`, `lapsim.solvers`,
`lapsim.events`, and `lapsim.optimization`. The root `lapsim` package is the
stable public facade; Michigan data remains confined to scoring presets and
analysis inputs.

## 75 m acceleration simulation

Run the standing-start, full-torque acceleration model in 0.5 m spatial
segments and export its complete telemetry, metrics, and dashboard with:

```powershell
.\.venv\Scripts\python.exe scripts\simulate_75m_acceleration.py
```

Use `--distance-m`, `--segment-length-m`, and `--output-dir` to change the
experiment without editing the script.
