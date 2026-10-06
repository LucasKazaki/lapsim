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

Driver request and solver cell length apply to every run. Invalid or
non-finite values are rejected before a run begins. The default solver cell
is 1 m; 0.5 m uses the source course's full station resolution. Coarser cells
run faster but can change the lap result because they smooth curvature over
longer distances.

The numeric outputs are lap time, peak speed, average speed, distance, net
equivalent-pack energy, and peak lateral acceleration in g. The trace selector
shows speed, longitudinal or lateral acceleration, drive or braking force,
driven tire slip, or battery power against distance or time. The top-down
course map stays fixed rather than moving with the car. In the map,
left-drag pans, the mouse wheel zooms around the cursor, and **Fit course**
restores the full view.

**Run comparison** simulates two selected saved/built-in profiles with the
same course, solver spacing, and driver request. The comparison window shows
both values and B-minus-A differences for each numeric output. The speed plot
uses solid and dashed black/white lines. Unsaved Prius edits are excluded from
comparison until saved as a named profile. Differences show model sensitivity
to selected inputs, not validated real-world performance.

Every lap run, including an interrupted run returned by the solver, saves a
content-identified JSON record under `%LOCALAPPDATA%\LapSim\runs`. The record
contains the selected profile manifest, effective car constructor inputs,
editable overrides, exact resampled-course hash, solver and controller
settings, result status, and aligned telemetry with units and validity flags.
The status line shows the start of the record ID; comparison shows both IDs.
Files stay on your computer and are not added to Git. A record is evidence of
what the model calculated, not evidence that the real vehicle was calibrated.

**Four-wheel lab** opens a separate top-down, time-domain experiment. It
compares two allocations of the same total requested wheel torque on one
synthetic car and shows paths, yaw rate, four wheel-slip traces, and wheel
forces at a movable time cursor. Its white/black desktop controls allow
editing mass, yaw inertia, geometry, tire coefficients, steer, and independent
wheel torques. The lab is for torque-allocation and equation checks. It has
no measured tire map, dynamic load transfer, motor/inverter/pack limits, or
team-car calibration, and its results must not be treated as lap times. See
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

The solver grid resamples curvature by a distance-weighted mean. This
preserves the integrated signed curvature over each solver cell and over the
lap; x/y coordinates are interpolated at cell boundaries. The grid spacing
still affects how the path model resolves short features, so compare 0.5 m and
1 m runs when numerical resolution matters. The Prius benchmark is for
software demonstration and input checking, not engineering sign-off.

The supplied ENME408 research report motivates a separate time-domain
four-wheel model rather than changing this prescribed-path solver into a
torque-vectoring claim. The lap and dynamics calculations currently answer
different questions; no motor or battery controller connects them yet.
