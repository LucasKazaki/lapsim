# LapSim engineering handoff

**Scope:** current desktop application, its source and portable Windows launch paths, distance-domain lap model and separate time-domain four-wheel experiments, input data, and the code and checks needed to maintain them.
**Audience:** software lead and vehicle engineers.
**Status:** implementation description, not vehicle certification or a claim of predictive accuracy.
**Source basis:** this repository; the supplied *EV Vehicle Simulation and Torque Control* research report (Report I); and the supplied *EV Vehicle Simulation II: Aerodynamics, CFD, Track Conditions, and Secondary Effects* (Report II, 5 October 2026). Report II's proposals are treated as design evidence, not as proof that a feature exists or that its example values describe the team car.

## 1. Read this first

LapSim has **two physics families**. The main desktop's default route estimates one rolling-start lap along a prescribed centerline; its start and finish speeds are recorded and need not match at the closed-course seam. Its optional AI path comparison uses extra passes to close seam **speed** for each tested path. Both routes advance from one distance cell to the next with the repository's vehicle, powertrain, battery, brake, aero, tire, and quasi-static suspension models. Their outputs are model estimates for the selected car and course. The separate time-domain four-wheel model integrates world position, body velocity, yaw, and four wheel speeds. The Four-wheel lab uses it for a short, synthetic, open-loop torque-allocation comparison. The optional WIP pose preview uses it with feedback steering over 80 m of a synthetic loop. Neither time-domain route is an endurance-lap solver or uses the selected Prius or TREV car profile.

That distinction is the most important interface contract in the project. A lap-time difference is not proof that the time-domain torque controller will be faster; a yaw difference in the lab is not a lap-time prediction. Neither mode currently has a calibrated 2026-27 car. The built-in Prius uses an equivalent electric power source to exercise the software, not a Toyota hybrid transaxle model. Optional TREV working profiles use partial local evidence and retain inherited defaults for missing subsystems.

The work informed by Report II adds explicit air-relative wind and per-wheel road-grip conditions to the four-wheel experiment. The **core API's** zero-drag, still-air, base-grip default recovers the pre-extension model; the desktop deliberately starts with a synthetic nonzero drag-area input. Full six-component CFD maps, ride-height feedback, vertical road/contact dynamics, and temperature-dependent limits remain future work because the required car, tire, CFD, road, and thermal data are not in this repository. Section 17 lists the exact data needed to advance those models.

An optional **experimental racing-line planner** now proposes one smooth path within an explicitly supplied corridor and computes model laps for it and a processed geometric centerline. Each prescribed curvature path must pass a continuous scalar normal-coordinate clearance check and a position-closure check before either time can be ranked. The default fused course fails this gate, so its completed AI-mode times are **diagnostics, not a selected racing-line gain**. A separate synthetic rounded rectangle passes the software gates and demonstrates an eligible modeled selection under assumed widths; it is not a surveyed event track. The ordinary centerline remains the default driving mode and does not run optimization. The planner is deterministic offline geometry optimization. Ordinary lap Driver view playback maps solved telemetry to reference x/y; the separate WIP pose preview plays the four-wheel model's simulated x/y and heading with its own label. Section 8.4 gives the planner math, Sections 9 and 10.2 describe those displays and pose experiment, and `docs/ai_racer_design.md` records their research and evidence limits.

### 1.1 Evidence levels

| Level | What it establishes here | What it does not establish |
|---|---|---|
| Equation and unit checks | Signs, conservation identities, limiting cases, numerical behavior of implemented equations | Parameters of the real car |
| Synthetic scenario check | Software responds to controlled changes in torque, wind, or grip | A measured lap-time or controller gain |
| Historical replay or fitted parameter | Agreement or disagreement with the recorded conditions and channels used | Independent prediction when parameters were tuned on the same run |
| Team-car validation | Would require held-out, synchronized measurements with configuration and uncertainty | Not currently available for the complete 2026-27 simulator |

The older report's 44 reference checks belong to its separate source package. They were **not** tests of this repository. The repository's current checks are identified in Section 16.

<!-- PDF_PAGE_BREAK -->

## 2. Run the code and locate the outputs

For recipients, extract `LapSim-Windows-x64.zip` and double-click `LapSim.exe`.
The single-file Windows x64 build includes the Python runtime and mandatory
course data. Its header **Simulator map** opens a durable offline map with
source references. The ZIP also provides documentation, source snapshot, and
test evidence. Follow [the team guide](team_guide.md) and
[release instructions](release.md) for distribution details and frozen checks.

The developer launch uses the repository checkout on Windows:

```powershell
cd C:\path\to\lapsim
.\setup_lapsim.cmd
.\launch_lapsim.cmd
```

The setup command finds 64-bit Python 3.11+, creates or reuses `.venv`, installs the project, and checks imports, the default course, Tk, and an actual TkAgg plot canvas. The launcher repeats that preflight, then starts a console-free window; an unexpected startup exception opens an error dialog and writes `%LOCALAPPDATA%\LapSim\logs\desktop_startup.log`. The direct `.venv\Scripts\python.exe -m lapsim.ui` route and `.vscode/launch.json` use the same checkout. Launch paths restrict numerical libraries to one worker thread. Source runs resolve Tcl/Tk scripts from the base Python installation when available; frozen runs use the packaged runtime. The application is native Tkinter with embedded Matplotlib. The default fused course is `analysis/data/track/gnss_imu_endurance_track.csv` relative to the resource root. `lapsim.resources.repository_root()` selects the source checkout or frozen `bundle` tree, so portable execution does not depend on a repository folder or current working directory.

Run the repository checks with:

```powershell
.venv\Scripts\python.exe scripts\check_all.py
```

The Python checker discovers every `test_*.py` file, runs each file in a fresh process, and sets one numerical-library thread plus base Python Tcl/Tk paths. It writes the aggregate `work/test-results.xml`; the verification guide shows how to retain `work/test-suite.log`. The older PowerShell checker remains available. These settings limit memory demand and isolate Tk interpreter state; they are not physics parameters. Setup installs pytest through the `dev` extra. A passing suite establishes the stated software checks, not full vehicle accuracy.

The [verification guide](verification.md) records coverage and release checks.
Use the final executable's self-test and release evidence for current counts;
the dated results in Section 16 preserve earlier source-test history.

This Markdown file is the editable report source. With ReportLab installed in a documentation Python environment, `python docs/render_engineering_handoff_pdf.py` regenerates `output/pdf/LapSim_Engineering_Handoff.pdf`; ReportLab is not required by the simulator itself.

Local user profiles are saved in `%LOCALAPPDATA%\LapSim\car_profiles.json`. Completed and interrupted main-lap runs are saved in `%LOCALAPPDATA%\LapSim\runs`; four-wheel A/B runs are saved in `%LOCALAPPDATA%\LapSim\dynamics_runs`. The separately saved synthetic pose traces default to `%LOCALAPPDATA%\LapSim\pose_runs`. These files are outside Git; do not confuse them with the built-in or reviewed-source profiles. The status bar shows a shortened record ID for saved lap and A/B runs; the WIP pose tab shows its own shortened content ID after Save or Load. Record contents are described in Section 14.

<!-- PDF_PAGE_BREAK -->

## 3. Repository architecture and execution boundaries

```text
src/lapsim/ui/__main__.py
  -> ui/app.py: Tk controls, worker thread, plots, profile comparison,
                 optional racing-line workflow, driver playback, WIP tab
      -> ui/garage.py and profiles/adapter.py: car construction and provenance
      -> ui/simulation.py: course load/resample and default run_one_lap
      -> optimization/racing_line.py: optional processed x/y baseline,
                                       full, half, bounded fourth path; up to eight passes
          -> optimization/grip_detour.py: optional fifth patch-mode trial;
                                          at most ten total passes
          -> optimization/road_grip_schedule.py: path-specific nominal
                                                 wheel-contact grip map
          -> solvers/path_constraints.py: cyclic speed ceilings
          -> events/endurance.py: driver requests, braking, cell advance
              -> vehicle_model/vehicle.py: component coordination
                  -> tire, suspension, aero, brake, drivetrain, battery
      -> experiments/run_record.py: settings, results, aligned telemetry
      -> ui/driver_view.py: time/distance interpolation onto reference x/y
      -> optimization/pose_driver.py: bounded pure-pursuit synthetic pose preview
          -> dynamics/planar.py: separate time-domain four-wheel model
      -> ui/pose_driver_playback.py: actual simulated pose in Driver view
      -> experiments/pose_run_record.py: separate synthetic trace Save/Load and replay gate

  -> ui/dynamics_lab.py: separate short maneuver and A/B displays
      -> dynamics/planar.py: time-domain four-wheel forces and RK4
      -> dynamics/conditions.py: deterministic wind and road queries
```

The environment is a pure model queried during integration, not a GUI animation. `vehicle_model/interfaces.py` defines replaceable component contracts. `lapsim` owns courses, solvers, controls, events, optimization, telemetry, profiles, and experiment records. The `analysis/` tree contains source data, historical studies, preparation scripts, and archived material; its scripts do not run every time the desktop app starts.

`events/api.py::simulate_endurance` is a separate generic event/scoring interface. `solvers/speed_limit.py` and `solvers/lap_time.py` are other solver utilities. The desktop's actual one-lap route is `ui/simulation.py::run_one_lap` through `PathConstraintSolver` and `EnduranceSimulator`. Do not use a result from one API as if it documented the assumptions of another.

The generic prescribed-path scoring route now precomputes each cell's steady lateral-capacity speed with `PathConstraintSolver.local_corner_speed_limit_mps` and checks both entry and exit speed. A coarse curved cell can otherwise start with zero lateral force, gain speed during the cell, and receive skidpad points despite exiting above corner capacity. An excess beyond the 0.01 m/s numerical gate fails the event with its lap and cell identified and awards no points. This endpoint guard does not turn the cell-level force approximation into continuous tire-force or path-pose integration.

### 3.1 State ownership and side effects

The main `Vehicle` is mutable. `run_one_lap` resets it before a run. Component `update_state` methods commit accepted cell results; telemetry is recorded after accepted cells. The time-domain lab uses immutable state and control values for force evaluations. Its Runge-Kutta stages may call a force function repeatedly, so road and wind queries must be pure: an internal substep must not draw a new random weather value, heat a tire, drain a battery, or change a controller command. Report II Section 12 explicitly distinguishes force evaluation from committed state evolution.

The GUI is not the solver's clock. Lap work runs on a worker thread and returns results through a Tk queue. The four-wheel lab also computes away from the Tk event loop. Redrawing a plot or moving the time cursor must not change a run's physics or data.

## 4. Frames, signs, units, and terms

| Symbol or channel | Meaning | Positive direction / units |
|---|---|---|
| `s`, `distance_m` | Distance along prescribed lap path | Increasing, m |
| `X,Y` | World-plane position in the four-wheel lab | World x/y, m |
| Body `x,y,z` | Vehicle axes | Forward, left, up |
| `psi`, `r` | Heading and yaw rate | Counterclockwise about +z, rad and rad/s |
| `u,v` | Body center-of-gravity velocity | Forward and left, m/s |
| `kappa` | Path curvature or wheel longitudinal slip, as named by context | Path: 1/m; tire slip: dimensionless |
| `Fx,Fy,Fz` | Tire force | Forward, left, upward reaction, N |
| `omega` | Wheel angular speed | Forward rolling positive, rad/s |
| `Tdrive,Tbrake` | Signed wheel drive and applied friction-brake torques | N m; brake torque opposes spin |
| `Ppack` | Battery terminal power in lap mode | Positive discharge, negative charge, W |
| `rho` | Air density | kg/m^3 |
| `w` | Air velocity in world frame | m/s; distinct from car ground velocity |

The four-wheel wheel order is **front-left, front-right, rear-left, rear-right**. Wheel body offsets use +y for the left side. A stronger right-rear forward tire force creates positive yaw because `Mz = x Fy - y Fx` and the right wheel has negative `y`. The lap solver uses a prescribed scalar path curvature; it does not integrate yaw dynamics with those independent wheel forces.

All public physics inputs are SI except fields that explicitly say `rpm`, `psi`, `kWh`, `deg`, or `km/h`. A dimensionless tire friction coefficient is not a force. The visible GUI converts speed from m/s to km/h, acceleration to `g` with 9.80665 m/s^2, forces to kN in traces, and battery power to kW. Those are display conversions; the core models use SI. The report's equations below use ASCII variable names so the exact code convention is clear.

## 5. Data path and provenance

### 5.1 Course input

`analysis/data/track/gnss_imu_endurance_track.csv` is the desktop's shipped 989 m course. The accompanying JSON says it is a spatial fusion of GNSS position, corrected IMU lateral acceleration, and an earlier schematic/registered centerline; it is not a surveyed current Formula SAE course. The metadata records 0.5 m source spacing, 1,979 points, a 0.76 m closure error, and limitations on map alignment and low-speed curvature. Some historical absolute file paths in that JSON describe the original preparation workstation; they are provenance strings, not valid paths on this computer.

`src/lapsim/ui/course_catalog.py` gives the desktop an explicit **Course** selector. `team_endurance_fused_gnss_imu` is the startup **Fused GNSS/IMU · default** choice and loads that CSV. `synthetic_rounded_rectangle_v1` is **Synthetic loop · AI demo**, a generated 195.398224 m rounded rectangle made from two 40 m and two 20 m straights and four radius-12 m quarter-circle arcs. `synthetic_fsae_endurance_style_v1` is the separate **Synthetic FSAE-style · practice** course: an 817.079633 m analytic loop repeating 60 m and 45 m straights, alternating signed turns, and 15 m radius bends. Its motif repeats four times with net turn `2π`; source distance, x/y, and circular-arc curvature close to numerical precision. Both synthetic sources have cells at most 0.5 m long. The practice course uses [2027 Formula SAE Rules v1.0, D.12.2.2](https://www.fsaeonline.com/cdsweb/gen/DownloadDocument.aspx?DocumentID=da79bcb4-0935-4f7b-83d7-0dbb8ce68d38) as dimensional inspiration, not as a specification of an actual event layout. Neither analytic course has measured cone positions or boundary widths, passing zones, or a surveyed Racing Terps centerline. Switching courses clears displayed results and replays; it does not switch the default **Centerline** driving mode to AI. Both synthetic choices initially supply editable *assumed* ±3 m AI half-width, 1.8 m vehicle width, and 0.2 m margin. These are scenario inputs, not sourced course data.

`courses/course_bundle.py::CourseBundle` adds a versioned import path for a
team-prepared course. The user selects a UTF-8 JSON file with **Import
course…**; the desktop validates and copies it to
`%LOCALAPPDATA%\LapSim\courses\<bundle_sha256>.json`, then reloads up to 64
saved JSON bundles at startup. A bad file is skipped with a warning. A
`course_id@revision` collision with different manifest content in this local
catalog is rejected; teams still need revision governance across computers.
The bundled `scripts/create_course_bundle.py` converts a coherent
`SpatialTrack` CSV to this format without source-code edits and hashes the
exact CSV bytes. The converter checks that output does not already exist
before saving and does not derive
curvature from raw survey points. `docs/course_bundle_format.md` defines
every field and gives a working command.

V1 is deliberately narrow: 4–5,000 cells, at most 4 MiB of JSON, a declared
right-handed local x/y frame in metres, one signed ±2π lap, and piecewise constant
curvature arcs whose stations/endpoints and closed heading agree within the
numeric geometry gate. That gate uses **1e-6 m** per-cell and cumulative
position tolerance, **1e-6 rad** heading-seam tolerance, and **1e-6 rad**
agreement with the declared signed ±2π turn. Frame handedness, origin, and axis descriptions are
provenance declarations; the loader cannot compare them with a survey. It
rejects duplicate JSON keys, nonfinite channels,
wrong hashes, and malformed geometry. `source_kind=measured` is a **declaration
with a source hash**, not independent survey verification. V1 requires
`boundary_status=absent` and `ai_defaults.width_source=assumed_uniform`:
neither the importer nor the AI planner can call its width a measured cone
corridor. The inconsistent shipped fused recording fails this strict import
contract and remains available only as its explicitly identified legacy
built-in course.

Schema **v2** keeps that same coherent source-arc contract and adds a
`corridor` with one positive left and right width per original source cell.
Its `reference_geometry_sha256` must match the validated source geometry;
`corridor_sha256` covers normalized widths and separate width provenance
(`source_name`, source SHA-256, processing method, review note). The declared
`status` is `assumed` or `measured`; measured status requires a measured
source-kind declaration. Widths are finite positive source data, independent
of the default AI vehicle width and margin. The loader preserves them as normal-coordinate
offsets from the **source** reference, not world-frame boundary coordinates
or a swept-body certificate. The imported course description and saved run
source metadata expose their status and hashes; run metadata marks
`source_cell_corridor.used_by_ai_planner=false`. The planner's processed
reference is smoothed and resampled, so its desktop route continues to use
the editable `ai_defaults` uniform assumption until a source-to-processed
width transformation is checked. A declaration of measured widths is not
independent survey verification. [TUM FTM's trajectory format](https://github.com/TUMFTM/global_racetrajectory_optimization/blob/master/Readme.md)
also defines left/right widths with respect to an explicit reference line
and normal vectors, illustrating why changing that line changes the width
coordinate frame.

`SpatialTrack` reads point arrays `distance_m`, `x_m`, `y_m` and one curvature value per cell. It checks finite values, channel lengths, and strictly increasing distance. It does **not** prove that the plotted x/y geometry exactly matches the cell curvature, that a closed flag closes the coordinates perfectly, or that the car remains within cones. The path solver consumes distance, cell length, and curvature. The plotted map consumes x/y. `Vehicle.update_state` separately integrates its achieved x/y/heading; the desktop does not overlay this path or check track width.

This difference is material to the optional planner. `SpatialTrack.geometry_audit()` now exposes a repeatable check: the shipped CSV has **989 m** of source station distance versus about **1,012.35 m** of accumulated x/y chords, about **0.760 m** endpoint gap, and **1,441 of 1,978 individual x/y chords longer than their assigned station intervals**, totaling 45.23 m of positive excess. A path segment cannot have a chord longer than its own travel distance. The largest absolute difference between a prescribed constant-curvature arc's chord **length** and its plotted map-cell chord length is **0.235787 m**; this local diagnostic can expose defects that cancel in whole-lap turn and closure totals, although it does not check chord direction. The saved curvature integrates to **3.657937 rad** signed turn versus **6.283185 rad** of x/y winding. Starting at the first plotted chord tangent and integrating each constant-curvature cell as an arc leaves a **542.633 m** position-closure gap. This is a source-geometry diagnostic, not an integrated vehicle-lap pose. The Analysis tab displays a warning; the data channels are separately fused estimates rather than one self-consistent path. The experimental mode generates both its baseline and proposed line from the same prepared x/y geometry and recomputes curvature for both. However, even the processed baseline's closed polygon has a **0.750897 m** curvature-integrated closure gap because chord lengths and assigned arcs differ. Its time comparison is *not* relative to the ordinary 989 m source-curvature lap. The source metadata provides no surveyed left/right boundary, so a width entered in the desktop is a scenario assumption.

`ui/course_catalog.py::solver_track_for_course` chooses the standard centerline solver grid. For the fused recorded course it calls `ui/simulation.py::resample_track`, which creates cells at the requested maximum length. For source cells overlapping a new cell `[a,b]`, it computes

```text
kappa_new = sum(kappa_old_i * overlap_length_i) / (b - a).
```

This conserves integrated signed curvature over the resampled path. It linearly interpolates x/y at the new distance boundaries. A new global grid can nevertheless average across original curvature changes, altering `sum(kappa_i^2 delta_s_i)` and the tire demand at a given speed. Coarsening the fused course removes short curvature variation and can change lap time.

Both synthetic courses follow a different branch: for a requested maximum at least as large as the longest original cell (about 0.5 m), `solver_track_for_course` retains the generated source cells, so a 1 m or coarser request does **not** reduce their cell count or distort the exact circular arcs. For a finer request, it strictly validates agreement among the source stations, x/y endpoints, and prescribed constant-curvature cells, then subdivides each original cell into analytic straight or circular subarcs. Every source station and endpoint remains in the finer solver grid; interior x/y points follow the subarc rather than the old chord. The desktop exposes **Cell size (max)** and defaults to a **requested maximum** 1 m step. Each synthetic ID also requires its exact catalog-generated source. The geometry gate checks analytic endpoints cell by cell and the integrated closed heading; polygon chord winding is not an acceptance condition, since coarse valid arcs can alias it. For a valid coarse arc whose signed chord projection is negative, the gate compares the absolute chord length and adjusts the recovered entry heading by π; the same convention is used for patch mapping and path audits. This validation is a numerical solver-representation gate, not a survey or evidence of measured track boundaries.

Imported bundles take the same retain-or-analytic-subdivide branch. Their
source geometry is checked when loaded and again before refinement; a coarser
request keeps every original arc, and a finer request counts and splits each
source cell without averaging adjacent curvature. The GUI's 5,000-cell
compute cap applies to the resulting grid. The source bundle hash and solver
grid hash are separate because subdivision changes the latter.

`solver_cell_count_for_course` predicts the grid before allocation; the desktop rejects requests for more than **5,000 actual generated centerline cells**. For the fused recording that count is `ceil(course length / requested step)`. For a finer synthetic request it sums `ceil(source cell length / requested step)` over every original source cell; when the source grid is retained, its existing cell count is used. A quick total-length check rejects obviously excessive requests first; the desktop checks the returned per-cell count as the final guard. The direct fused `resample_track` helper also rejects nonnumeric, nonfinite, nonpositive, and over-cap requests before allocation. The AI planner has its own 5,000-point grid limit and applies the same user-requested maximum to its generated physics cells. Cell length is a physical/numerical modeling choice, not a plot-resolution option.

`SpatialTrack.refine(maximum_cell_length_m)` is a separate, unchanged on-demand resolution check. It subdivides each existing cell at most to the requested length while retaining every original station boundary, endpoint x/y, and piecewise-constant curvature. New x/y points lie on the old chord; this is **not** the synthetic course's analytic subarc subdivision. Thus each original cell keeps its length, signed turn `kappa_i delta_s_i`, and squared-curvature integral `kappa_i^2 delta_s_i`; splitting a cell does not average it with its neighbors. It rejects a nonfinite or nonpositive step and grids exceeding 100,000 cells. This QA method does **not** change the desktop's default discretization, certify geometric consistency, or repair an inconsistent source map. Speed-envelope and vehicle integration error can still change with cell size, so compare results rather than assuming convergence.

### 5.2 Car profiles and actual model values

`profiles/adapter.py::build_vehicle` constructs a **fresh** vehicle and a manifest. `repository_baseline` uses repository defaults. `prius_2026_le` uses `ui/presets.py::make_prius_benchmark` and an idealized one-motor, front-drive power envelope based on published combined power. The Prius's mass and wheelbase are published benchmark specifications; its effective motor curve, pack, grip, and several aero/chassis inputs are assumptions. The saved-user profile mechanism (`ui/garage.py`) copies only seven editable Prius-equivalent fields: mass, peak-equivalent power, wheelbase, tire radius, tire friction, drag area, and speed limit. It is not a general editor for every Python model parameter.

The built-in Prius starter values are `1404.78 kg` converted from `3097 lb`, `144.67 kW` converted from `194 hp` combined power, `2.7508 m` wheelbase converted from `108.3 in`, and `0.3329 m` **nominal geometric** radius from tire designation `195/60R17`. Those four conversions are drawn from the manufacturer-specification block in `ui/presets.py`; geometric radius is not a measured loaded rolling radius. The editable starting assumptions are tire `mu=0.95`, `CdA=0.59 m^2`, and top-speed cap `180 km/h`. The constructed equivalent has a front driven axle, a four-knot idealized motor curve with a 4200 rpm knee and 10000 rpm maximum, unit motor/inverter/chain efficiencies, no charge-power allowance, zero aero lift, 60% static front weight, `0.53 m` CG height, `1.56/1.58 m` front/rear tracks, rolling-resistance coefficient `0.012`, and cornering-drag coefficient `0.025`. These are **software-model assumptions**, not a claim to reproduce a Toyota hybrid's mechanical or electrical architecture. Exact constructed values and overrides are frozen in each lap record.

Optional TREV5 working profiles require the reviewed ENME408 data package in Downloads. `profiles/registry.py` validates the package and `profiles/adapter.py` promotes only allowlisted, unit-compatible fields. The manifest separates selected source values, inherited model defaults, unused records, conversion details, source locations, artifact hashes, and limitations. A source browser can inspect records without silently applying them. These profiles are partial working scenarios; neither motor count nor 2026-27 electrical topology should be inferred from a label.

The effective vehicle snapshot in each saved lap record is the **constructed car used by that run**, not merely the chosen base profile. Editable overrides are recorded separately. This matters because a user can select Prius, change a number, run once, and leave the named profile unchanged.

### 5.3 Missing physical data

The shipped course has no track width, elevation, bank, crest radius, local surface material, wetness, roughness, road temperature, or measured wind. The main lap mode therefore assumes a flat, still-air path with its configured constant density and a user-entered base road-grip factor (100% by default). Experimental AI mode can additionally use one user-assumed world-fixed lower-grip rectangle on a coherent closed course. The shipped fused course is not coherent enough to place that rectangle reliably; its patch option is rejected. Neither the AI rectangle nor a road patch drawn in the separate four-wheel lab is reconstructed from a survey. No rain graphic is treated as tire physics.

## 6. Main lap mode: aero, suspension, and tire capacity

The lap model is quasi-static within each spatial cell. It does not solve a Navier-Stokes fluid field, suspension differential equations, or four independent wheel angular speeds. Its components provide algebraic forces to the path solver and the vehicle's cell update.

### 6.1 Aerodynamic forces

`vehicle_model/aero/model.py::Aero.forces_n` computes dynamic pressure `q = 0.5 rho v^2`, positive drag `D = q Cd A`, and signed downforce `Ddown = -q Cl A f_roll`. `Cl < 0` means downforce under this model's convention. The front share is `p Ddown`; the rear gets `(1-p) Ddown`. The roll factor is

```text
f_roll = 1 - min(abs(roll)/roll_limit, 1) * (1 - retention_at_limit).
```

At and above the default one-degree roll limit, the default retains 50% of the zero-roll downforce. This is a configured approximation, not a measured ride-height/attitude map. `Vehicle.aero_forces_n` obtains a quasi-static body-roll estimate from suspension before calling `Aero.forces_n`. The optional `ActiveAero` subclass selects a two-position low-drag state from absolute path curvature and scales drag and downforce independently; it has no actuator delay or rule-eligibility determination. The desktop's default Prius uses its own estimated `CdA`, not the baseline aero package's coefficient table.

This lap calculation currently uses **ground speed as airspeed** and a fixed air density. It does not include crosswind side force, aero yaw/pitch moments, or the wind-aware model in the separate lab. Its baseline coefficient and reference area values are listed in `docs/model_parameters.md`. The active ratio `abs(Cl)/Cd` must be computed from those actual coefficients; a historical unused ratio constant was removed because it disagreed with them.

The total normal reaction used by resistance and tire calculations is approximately `m g + Ddown` on the flat path. A positive-lift configuration that removes all reaction or makes either axle's base reaction negative is now rejected as outside this constrained-contact model. It is not silently turned into extra tire grip or a negative denominator. The code still cannot simulate flight, porpoising, or a crest.

### 6.2 Quasi-static suspension loads

`vehicle_model/mech/suspension.py::tire_normal_loads_n` starts from static axle weights and adds the configured front/rear aero downforce. Longitudinal load transfer is proportional to `m ax hCG / L`, moving load rearward under forward acceleration. Lateral transfer uses `Fy = m ay`, front/rear roll-axis heights, track widths, total elastic roll stiffness, and the configured front load-transfer distribution. It estimates body roll for the aero multiplier. Wheel loads are clipped at wheel lift only within its algebraic model; it has no heave, pitch, roll, damper, unsprung-mass, or contact-trajectory states. Do not add a second independent load-transfer correction around this component.

More specifically, its quasi-static roll angle is `phi = m ay max(hCG - h_roll_axis_at_CG,0) / K_roll`. Geometric roll moments act through front/rear roll-axis heights; elastic roll moment is distributed according to a front stiffness fraction chosen to approximate the configured front lateral-load-transfer fraction within `[0,1]`. Each axle's lateral transfer is its geometric plus elastic moment divided by that axle's track, then limited so no algebraic wheel load is negative. The exact stiffness-fraction solve is in `suspension.py::tire_normal_loads_n` and is included in the effective vehicle snapshot; it is an equilibrium allocation, not a transient suspension response.

Report II gives a more complete flat-road pitch balance including aerodynamic pitch moment and longitudinal ground force. The present model is **not** an exact solution of that general balance: it has no aerodynamic pitch moment, wind, grade, or transient pitch angular momentum. Its outputs are suitable for model sensitivity and force-budget checks under the stated flat, quasi-static assumptions.

### 6.3 Tire law and combined force

`vehicle_model/mech/tire.py::Tire` is the default main-lap tire. It interpolates a load-sensitive `mu(Fz)` table over its configured range and clamps beyond the table. Pure lateral and longitudinal capacities are `mu_lat(Fz) max(Fz,0)` and `mu_long(Fz) max(Fz,0)`. It distributes a requested total lateral force across wheels in proportion to capacity. Its remaining longitudinal limit under lateral force is a friction-circle-style capacity:

```text
Fx_remaining = Fx_pure * sqrt(max(0, 1 - (Fy / Fy_pure)^2)).
```

Drive demand is allocated only to configured driven wheels; braking requests are distributed by axle and constrained at each contact patch. The default main-lap tire does not integrate each wheel's `J d(omega)/dt`. It infers a longitudinal slip estimate from force/capacity, with a configured peak-slip ratio and optional distance relaxation. Tire saturation and the path speed ceiling are therefore not a substitute for a measured force-versus-slip-and-temperature map.

The distance-domain force solve evaluates lateral demand at **cell-entry** speed while holding its solved longitudinal force across the cell. A curved cell can accelerate enough that its **exit** lateral demand and held drive/brake force no longer fit together under the same tire law. Before accepting a curved cell, `Vehicle.exit_combined_tire_force_margin_n(kappa)` recomputes exit aero load and quasi-static wheel normal loads using `v_exit`, `a_y,exit = v_exit^2 kappa`, and the solved cell `a_x`. It allocates required exit lateral force by the tire's capacity fractions and computes the lesser of the total lateral margin and each tire's remaining longitudinal capacity minus its held drive-plus-brake force:

```text
M_lat = sum_i Fy_pure_i(v_exit) - m abs(v_exit^2 kappa)
M_x,i = Fx_remaining_i(v_exit) - (Fx_drive_i + Fx_brake_i)
M_exit = min(M_lat, M_x,front_left, M_x,front_right, M_x,rear_left, M_x,rear_right).
```

An exit deficit below `-max(1 N, 0.001 m g)` rejects the attempted cell before its energy, telemetry, and Driver progress enter the accepted prefix. This tolerance covers small force-solve roundoff; it is not a tire uncertainty bound. For the automatic torque-profile driver, an inexpensive entry/exit capacity estimate screens most cells. Near a possible limit, a copy of the car first previews the **original requested command**; a conservative screen alone cannot cut torque that the full vehicle model finds feasible. Only if that preview lacks exit grip does a bounded torque search reduce the request before the independent post-step gate checks the committed cell. Explicit control profiles are not silently rewritten: an over-demanded exit is reported as a failed lap. A four-cell 10 m radius, constant-grip circle exposed the old flaw: a completed lap could exit a cell at its pure lateral speed ceiling while still claiming hundreds of newtons of drive where the exit tire had about one newton of combined capacity. The corrected automatic and explicit-control circle regressions cover that case, including a 64-cell resolution. The gate checks **cell endpoints** under this quasi-static tire law; it does not prove continuous in-cell force feasibility, swept-body clearance, measured tire grip, or a full vehicle trajectory.

The desktop road-grip entry supplies a positive base factor `gamma` to every tire on a run. With the same normal load, `Fy_capacity(gamma) = gamma Fy_capacity(1)` and `Fx_capacity(gamma) = gamma Fx_capacity(1)`; the remaining combined-force limit is then recomputed from those scaled capacities. The factor also scales optional pure Pacejka forces when that tire class is selected. The path-speed/braking prepass and the accepted-cell vehicle solve use the same effective tire, and every A/B or AI trial starts from its own car copy with the same entered base factor. Centerline and A/B keep that factor uniform. Optional AI rectangle mode replaces it per trial cell by the absolute schedule described in Section 8.4. These are sensitivity inputs, not calibrated wet tires, grade, temperature, or measured friction. At `gamma=1` with no patch the original main-lap tire law is unchanged.

Optional Pacejka classes and a public UPC `.tir` file exist in `vehicle_model/mech/pacejka.py` and `data/tires`. They are **not** silently enabled by the desktop. The imported file's pure lateral information and its longitudinal/combined-slip provenance differ; see `docs/model_parameters.md` before using them as a measured complete tire model.

## 7. Main lap mode: powertrain, brakes, and battery

### 7.1 Propulsion and equivalent rotating mass

The baseline power chain is DC pack terminal -> inverter -> motor shaft -> chain/final drive -> driven tires. `motor.py` interpolates peak torque against RPM and limits shaft power and maximum RPM. `drivetrain.py` uses a nominal no-slip conversion from ground speed through the tire rolling radius and gear ratio for its envelope; cell force/power checks can then use inferred driven-wheel surface speed from tire slip:

```text
omega_wheel = v / R; omega_motor = gear_ratio * omega_wheel;
Fx_wheel = Tmotor * gear_ratio * eta_chain / R.
```

The available motor torque also depends on pack discharge power, inverter and motor efficiencies, and motor power limit. `vehicle_model/vehicle.py` can further reduce demand when the driven wheel surface speed would violate the motor envelope or configured vehicle speed cap. The default efficiencies are constants, so there is no torque-versus-temperature derating or detailed inverter loss map. The `continuous` motor curves are available as references/telemetry; the one-lap event does not thermally integrate continuous rating usage.

Main-lap wheel, shaft, and rotor inertias are **reflected into an equivalent longitudinal mass** `m_eff = m + J_ref/R^2`, where `J_ref = (J_motor_rotor + J_chain_input) ratio^2 + J_chain_output + J_driven_wheels`. This belongs only to the distance-domain car, which does not integrate wheel speed as independent state. The four-wheel time-domain model instead integrates four `J d(omega)/dt` equations and must not also add the same wheel inertia to `m`. This separation prevents double counting.

The built-in repository defaults include parameters that were fit to the historical endurance run: rolling radius, motor efficiency, and chain efficiency. Agreement with that same run is in-sample consistency. It cannot by itself validate a prediction for a future car, another tire, or another track.

### 7.2 Hydraulic braking and regenerative allocation

`vehicle_model/mech/brakes.py` converts independent front/rear pressure requests, after its configured deadband/map, to axle torque and then force through rolling radius; both pressures have a 300 psi baseline ceiling. Tire force is the final cap. The endurance automatic path controller asks for enough negative force to reach the next speed ceiling and distributes friction brake requests across the two axles and their left/right tires. The pressure inverse is an actuator request, not a guarantee that the path is feasible.

`Vehicle.maximum_regenerative_brake_force_n` limits a requested regen magnitude by motor speed/torque, drivetrain efficiency, and pack charge power. `Vehicle.update_state` checks driven-axle topology, and `Tire.calculate_forces` then limits the combined regen and friction-brake request by contact grip. `EnduranceSimulator` enables automatic regen only if a non-null SOC threshold is configured and SOC is below that threshold. The desktop `EnduranceRunConfig` does **not** set this threshold, and the baseline/Prius default pack charge-power cap is zero. Thus a visible regenerative-braking trace may correctly stay at zero. Friction-brake heat is not modeled, and regenerative energy is signed battery power rather than disc heating.

### 7.3 RC battery and energy sign

The repository default is a one-RC Thevenin pack in `vehicle_model/electrical/battery.py`; the Prius benchmark creates an `OCVPackBattery` equivalent. Both use pack open-circuit voltage versus SOC and a terminal resistance. For the RC variant, with positive current discharging:

```text
V_source = OCV(SOC) - V_polarization;
V_terminal = V_source - I R0;
P_terminal = V_terminal I;
I = 2 P_terminal / (V_source + sqrt(V_source^2 - 4 R0 P_terminal));
SOC_next = clip(SOC - I dt / (3600 capacity_Ah), 0, 1);
V_polarization,next = exp(-dt/(R1 C1)) V_polarization
                     + R1 (1 - exp(-dt/(R1 C1))) I.
```

The low-current quadratic root avoids cancellation near zero power. Pack limits also bound terminal voltage, discharge/charge power, SOC, and the quadratic branch. A positive `battery.power_w` means discharge; negative means charging. The event's displayed **net energy** integrates signed terminal power over accepted cells and converts joules to kWh. The telemetry recorder also has a separate cumulative **positive-discharge** energy channel; these must not be interchanged. The pack has no cell temperature, cooling, aging, or measured Prius hybrid energy flow. `docs/battery_model.md` and `docs/battery_rc_validation.md` describe the model and the limited historical voltage holdout.

## 8. Main lap mode: speed ceiling, controller, and cell update

### 8.1 Precompute the path speed envelope

`ui/simulation.py` builds a constant-fraction, two-knot periodic torque profile; both knots have the same requested fraction, so this desktop input is a constant normalized driver demand. It creates `PathConstraintSolver` with explicit tolerance/pass/iteration settings from `path_solver_settings`. At each curvature cell the solver bisects speed between zero and the configured maximum until required lateral force `m v^2 abs(kappa)` fits the sum of quasi-static tire lateral capacities. The local limit is then passed through cyclic backward braking passes, using the next cell's speed and available braking force to bound each entry speed. Conceptually:

```text
v_entry^2 + 2 a_brake(v_entry, kappa, car) delta_s <= v_next^2, with signed a_brake < 0.
```

The implemented braking acceleration is nonlinear in speed and load transfer, so the solver evaluates force balance and bisects rather than assuming one constant deceleration for the entire lap. It iterates around the closed path until its configured convergence tolerance or pass bound is reached. The tolerance must be finite and positive. A descending pass uses the prior cell-zero ceiling for the closing cell, so the solver independently rechecks that cyclic seam against the newly updated cell-zero ceiling and refuses to return if the gap exceeds 1e-6 m/s, even with a loose requested tolerance. It continues sweeping or raises at the pass bound. `PathSpeedConstraints` stores local corner limits and braking ceilings for every cell. A nonzero speed ceiling is a model output, not a safety guarantee for a real car.

The Python API accepts `cell_road_grip_multiplier=(q_0,...,q_{N-1})`
in `PathConstraintSolver.solve`, `prepare_one_lap_constraints`,
`run_one_lap`, and `run_speed_periodic_lap`, where `N` is the exact solver
track's cell count. This immutable tuple contains **absolute** tire-model
`road_grip_multiplier` values, not factors multiplied by the vehicle's
existing grip. Each value must be finite and positive. For cell `i`, the
solver sets the tire's grip to `q_i` for its local corner calculation and
backward brake-entry calculation; `EnduranceSimulator` uses the same `q_i`
before its cell entry gates and force update. Both components restore the
vehicle's configured multiplier afterward, including after an exception.
Passing no tuple follows the unchanged uniform-grip arithmetic. Prepared
limits retain the schedule and cannot be paired with a different supplied
schedule. The tuple is a station-indexed scalar capacity input. The desktop
can now generate one such tuple **separately for every optional AI trial**
from an assumed world-coordinate rectangle and nominal wheel-center paths;
Section 8.4 gives that mapping. Ordinary centerline and two-car modes still
use uniform grip. `LapRunSettings.from_track` can freeze a scheduled API or
desktop run in a v2 record with exact grid order, and `replay_lap_record`
reapplies and checks the saved grip channel. The saved tuple is sufficient
to replay the model; a patch-mode AI record also saves its rectangle and
mapping version so the checker can independently regenerate the tuple.

### 8.2 Driver/controller action

`events/endurance.py::EnduranceSimulator.run` resets the vehicle and, unless an explicit start speed was supplied, begins at the **first cyclic braking ceiling**. This is a rolling-start, single initial-condition lap, not a standing-start acceleration event or a converged periodic flying lap. The cyclic ceiling guarantees braking feasibility, not that the car can accelerate back to its entry speed at the seam. The result records actual entry and exit speeds and exposes finish-minus-start speed for a completed single lap. Before each cell it checks entry against local and braking ceilings. The automatic torque-profile controller converts driver fraction to requested motor torque, computes the force needed to reach the next ceiling, and chooses one of drive, coast/torque reduction, or hydraulic braking (with optional configured regen). Steering is chosen from the prescribed curvature with `delta = atan(kappa L)`. A full `EnduranceControlProfile` can instead supply explicit torque, pressure, regen, and steering; that path is checked against speed and curvature constraints rather than silently repaired. `Vehicle.update_state` derives requested curvature from steering and may reduce achieved curvature when lateral tire force saturates. After each model step, the event requires **both** requested and achieved curvature to differ from the prescribed cell curvature by no more than `EnduranceRunConfig.path_curvature_tolerance_per_m` (**1e-9 1/m** by default) before accepting the cell. Thus a direct zero-steer run on a circular path fails. This checks a scalar curvature for each cell, not whether the integrated x/y pose follows the plotted course or remains within cones. The automatic baseline and AI laps request the prescribed curvature, but they also lack a closed-loop pose and boundary check.

The ordinary single-car lap uses that first cyclic ceiling. The two-car A/B workflow instead computes one common feasible rolling start from both cars' first ceilings, then supplies it explicitly to each event; Section 9 gives the formula and record contract. Neither route requires the exit speed to equal its entry speed.

The automatic driver targets the smaller of the **next cell's braking ceiling** and the **current cell's local corner-speed ceiling**:

```text
v_target = min(v_braking,next, v_corner,current).
```

The current-cell cap matters when a corner is followed by a straighter cell: following only the next ceiling could accelerate above the corner limit before leaving the curved cell. After the model step, the event checks the requested and achieved cell curvature as above, then `v_exit <= v_corner,current + epsilon` and `v_exit <= v_braking,next + epsilon`, with `epsilon = config.path_speed_tolerance_mps` (**0.01 m/s** by default). These checks apply to supplied explicit controls as well as automatic control. The event records telemetry and progress only for an accepted cell. Because the prescribed curvature and longitudinal acceleration are constant over a cell, bounding its entry and exit speeds bounds the modeled speed between them. The cell model still evaluates forces at a representative operating point and has no transient tire/path tracking; these are consistency guards within that approximation, not real-world cornering validation.

The automatic brake allocator inverts an estimated axle-force request into pressures. When either axle reaches the effective configured pressure cap, the controller now commands both axles at that cap, matching the full-pressure premise of the backward braking envelope. The committed vehicle load-transfer solve can otherwise deliver slightly less force than the inverse estimate; small deficits accumulated into an apparent ceiling failure in one TREV5 working scenario. The tire combined-slip model still caps contact-patch force, and pressure never exceeds the configured or physical limit. This is a conservative simulation guard, not a calibrated brake-bias or ABS controller; a prospective pressure solve against the actual vehicle step remains future work.

If the vehicle exceeds a ceiling, stops, exceeds time, depletes SOC, or cannot traverse a cell, `EnduranceRunResult` carries a failure reason and completed-lap count. A failed comparison is not ranked as a valid lap. The desktop saves its record for diagnosis. `Vehicle.update_state` can advance a cell before a post-step rejection, so the failed result's existing terminal time/speed/SOC may describe that attempted cell. The added `accepted_*` fields identify the checked prefix that agrees with energy, telemetry, and Driver progress. A cell that completes physically and depletes SOC at its endpoint is included in those checked outputs before the run stops. Section 14.1 gives the exact saved fields and remaining rollback limitation.

The separate legacy `solvers/lap_time.py::LapTimeSolver` forward acceleration pass now also caps a cell's exit speed by both the current and next `SpeedLimitMap` limits, as well as reachable speed. This applies the same current-cell corner principle to that lower-level speed-profile API; it does not turn its profile into an `EnduranceSimulator` lap or add path-pose validation.

### 8.3 Advance the vehicle by one distance cell

`Vehicle.update_state(controls, delta_s)` obtains tire, brake, motor, aero, and suspension forces and solves a longitudinal force-balance fixed point. Required lateral force is `m v_entry^2 abs(kappa_request)`. If tire capacity is lower, a root solve reduces achieved lateral force and therefore effective curvature. Resistance is

```text
F_resist = D_aero + Crr (m g + Ddown)
         + Ccorner Fy^2 / (m g + Ddown).
a_x = (Fx_tire - F_resist) / m_eff.
```

The normal-load guard rejects unsupported negative reaction before the denominator is used. The cell kinematics assume constant longitudinal acceleration at the cell entry operating point:

```text
v_exit^2 = v_entry^2 + 2 a_x delta_s;
dt = 2 delta_s / (v_entry + v_exit).
```

Time and force are coupled because optional tire slip relaxation may depend on `dt`. The code iterates to a relative time tolerance and refuses a cell it cannot traverse. It then commits component states using the converged `dt`, integrates effective heading by `delta_heading = kappa_effective delta_s`, and adds the corresponding circular-arc x/y increment. This is a spatial, quasi-static approximation. It does not integrate lateral velocity, yaw inertia, road banking, or track containment.

### 8.4 Optional experimental racing-line planning

`src/lapsim/optimization/racing_line.py` prepares a **new path input** for the shared lap model. It does not change the force, power, braking, or battery equations in Sections 6-8. The desktop imports this module only after **AI racing line (experimental)** is selected. Ordinary **Centerline (default)** calls `solver_track_for_course` and `run_one_lap` on the selected course's original distance/curvature channel and pays no optimization cost. That grid helper resamples the fused recording or preserves and analytically subdivides either synthetic course's existing straight/arc cells as described in Section 5.1. The startup course is the fused team recording; either synthetic course is selected separately. The AI route requires the user to enter assumed half-width, vehicle width, and safety margin. Its programmatic `TrackCorridor` supports separate left/right width for *each source cell*, plus a required source description; the current desktop supplies equal uniform assumed widths. The clearances must exceed `vehicle_width/2 + margin` on both sides. These values define a center-of-car offset envelope, not an observed edge of pavement. Bundle v2 source-cell widths are not passed to this planner because it shifts and smooths the reference path without a verified source-to-processed width transformation.

For a closed source course with length `L_source`, the planner removes the x/y endpoint mismatch linearly over source distance, interpolates x/y with a periodic cubic spline onto `N = max(ceil(L_source/2 m), 4 K, 32)` periodic samples by default (`K=24` controls), and applies wrapped Gaussian smoothing with a `0.8 m` scale. In desktop AI mode, the requested maximum cell length first reduces the nominal sampling interval when needed. Since offset geometry can lengthen an individual chord, the planner then rebuilds at larger sample counts until both generated endpoint paths have actual cell lengths at or below the request. Chord length is convex in offset strength, so bounding strength 0 and 1 also bounds the intermediate 0.5 and fourth strengths. Planning stops with an explicit error at the 5,000-point cap or after eight bounded attempts; smaller cells increase compute cost and can change the optimized line and modeled time. Periodic cubic interpolation avoids artificial corners when the source and planner station grids differ; it does not repair an inconsistent source map. The planner records closure error, maximum preparation shift, and processed path length difference. The processed zero-offset line is the **geometric baseline**; the ordinary source-curvature line is not a valid A/B baseline for a shifted x/y candidate. The planner refuses more than 5,000 samples, an open course, self-intersecting processed baseline, undefined tangent, degenerate cell, or unusable corridor.

At each processed sample, a central-difference tangent defines the unit left normal `n_i`. A periodic uniform cubic B-spline basis `B_ij` maps the `K` controls `c_j` to lateral offset `d_i = sum_j B_ij c_j`; candidate sample positions are `p_i = p_base,i + d_i n_i`. Because the basis is periodic, its offset and first derivatives meet at the lap seam. The algorithm computes candidate chord lengths `ell_i = |p_(i+1)-p_i|`, cumulative solver station `s_(i+1)=s_i+ell_i`, and signed heading turn `theta_i` from the incoming and outgoing chord vectors `a` and `b` at each vertex:

```text
theta_i = atan2(cross(a,b), dot(a,b));
kappa_cell,i = (theta_i + theta_(i+1)) / (2 ell_i);
sum_i (kappa_cell,i ell_i) = sum_i theta_i = 2 pi * winding_number;
J(c) = sum_i [kappa_cell,i^2 ell_i] / sum_i ell_i
       + lambda (sum_i ell_i / L_baseline - 1), lambda = 0.01 m^-2.
```

The discrete curvature is a centered allocation of polygon heading turn to neighboring solver cells. Its integral matches the polygon's signed winding exactly, but the local value remains a numerical approximation for the speed-envelope solver. **Matching total turn does not make a constant-curvature arc at the assigned cell length reach the polygon chord endpoint.** It is recomputed for **both** geometric baseline and proposed path, never copied from the original source curvature. The first term of `J` has units `m^-2`; the length-penalty coefficient therefore also has units `m^-2`, since the relative-length term is dimensionless. `J` favors lower average squared curvature with a weighted length penalty. It is **not** lap time, and it does not use car mass, power, grip, or aero while solving. SciPy SLSQP starts from all-zero offset, uses finite-difference objective derivatives, and is capped at 60 iterations by default. The numeric objective is multiplied by 10,000 for the optimizer's absolute tolerances; reported objective values remain unscaled. This is one local candidate, not a global racing-line optimum or a trained policy.

The linear optimizer constraints evaluate the spline at planner nodes and midpoints and at every original source-cell boundary and midpoint. Bounds at shared boundaries use the narrower adjacent width, including the closed seam's first and last cells. A postcheck analytically finds the cubic offset extrema *within each source cell* against its piecewise constant left/right widths. Before planning, a normal-coordinate fold guard rejects a supplied inside clearance whose local curvature-times-offset reaches `0.98`, since the offset strip approaches its local bend radius and cannot support a meaningful corridor claim. The candidate must have violation no more than `1e-6 m`, forward local motion relative to the processed baseline, finite positive chord lengths, and no nonadjacent segment intersection. The latter check operates on the discretized polygon. Width certification at this stage is for the mathematical **offset polygon relative to the processed reference and supplied cell widths**, not the arc path actually implied by the lap model.

The `CurvaturePathAudit` separately integrates each saved constant-curvature cell from the processed path's first x/y point and inferred initial heading. An initial screen checks four quarter-cell positions per modeled cell, every source-corridor cell boundary, and every source-corridor cell midpoint. A source boundary uses the narrower adjacent width, including the closed seam. This inexpensive screen reports observed excess early; passing it alone is insufficient for eligibility.

For the continuous check, use fraction `f` within modeled cell `i`. `P_i(f)` is its exact straight or circular arc, `R_i(f)` is linear interpolation of the processed reference endpoints, and `N_i(f)` linearly blends the endpoint unit normals. The declared scalar lateral coordinate is `g_i(f) = (P_i(f) - R_i(f)) dot [N_i(f)/|N_i(f)|]`. Intervals are split at every modeled-cell and supplied source-width boundary, so each interval has one pair of width limits. For an interval of fractional span `h`, let `D=P-R`, `q_min=min|N|`, `u=|N'|`, `r=|R'|`, cell length `ell`, and prescribed curvature `kappa`. An upper bound used by the code is:

```text
D_max = max(|D(left)|, |D(right)|) + (ell + r) h/2
B = ell^2 |kappa| + 2(ell + r)u/q_min + 3 D_max u^2/q_min^2
|g(f) - linear_interpolation(g(left),g(right))| <= B h^2/8.
```

This follows by differentiating `g=D dot n`, bounding `|D''|`, `|D'|`, `|n'|`, and `|n''|`, then applying the linear-interpolation remainder bound. The implementation finds `q_min` over the interval, bisects intervals whose bound does not establish clearance, and has finite depth and work caps. An unresolved interval, undefined normal, observed excess above **1e-8 m**, or any of the integrated path, modeled polygon, or reference polygon endpoints farther than **0.01 m** from its start makes the audit ineligible. `minimum_corridor_slack_m` is a conservative lower bound for a certified path, not merely the smallest sample. The fourth-trial search requires at least **0.02 m** of this certified additional slack beyond the entered width and safety margin. `continuous_clearance_certified`, `unresolved_clearance_intervals`, and `clearance_status` expose why the check passed or failed.

The certificate applies to this **scalar normal-coordinate corridor around the processed reference**, with piecewise declared source widths and the represented curvature arc. It does not certify the swept body in world coordinates, collision-free passage between cones, a measured track boundary, or physical pose tracking. The original shipped processed baseline fails, so a completed physics run can have time and telemetry while being ineligible for an AI line ranking.

`compare_lines_with_lap_model` audits modeled-path clearance before a candidate lap. If the processed baseline is valid, an invalid candidate retains its geometry, audit, and skip reason but has no lap time, saved run, or replay. If the baseline itself is invalid, the solver still records diagnostic laps to expose the source-course mismatch. It copies the selected vehicle separately for the geometric centerline and every candidate admitted to physics, preventing one lap's battery or chassis state from contaminating another. All admitted paths use the same torque fraction and cell physics. It first tests geometric baseline strength 0, full offset 1, and half offset 0.5. If all three audits and times are eligible and half beats both endpoints by more than 0.05 s, a convex quadratic through their times chooses one safeguarded fourth strength from {0.25, 0.375, 0.625, 0.75, 0.875}. If full fails its modeled-path audit while eligible half beats baseline by more than the selection margin, a geometry-only preflight checks {0.975, 0.95, 0.9, 0.875, 0.75, 0.625} in descending order. The first valid path with at least 0.02 m additional certified scalar slack gets the fourth model trial. Otherwise the fourth strength is 0.75. The quadratic and clearance screen choose only where to run that trial; neither establishes its eligible time. Convex offset scaling preserves the supplied lateral bounds for the proposed **polygon**, while each intermediate path rebuilds station and curvature and checks direction and nonadjacent crossings.

The desktop calls the speed-only seam helper for at most four original paths that pass the preflight or are retained as diagnostics after a failed baseline. With one assumed low-grip rectangle and a valid processed baseline, a separate bounded detour proposer may add one fifth audited path. The comparison solves path constraints once per admitted path, starts a dry probe at the cyclic braking ceiling, then makes a recorded pass at that probe's exit speed. Each pass uses a fresh copy of the same effective vehicle configuration and initial pack state at that path's solved rolling start speed; only the final pass emits progress and telemetry. At most **eight complete lap-model passes** occur without a patch, or **ten** when the optional detour receives one two-pass trial. A comparison time requires a completed final pass with `abs(finish_speed - start_speed) <= 0.005 m/s` **and** a passing modeled-path audit. Speed closure with a fixed initial pack state is **not** periodic battery charge or full-state convergence. Completed but ineligible times remain diagnostic with their run and track. If the processed baseline audit fails, status is `invalid_processed_baseline` and no path can win. Each completed AI path record saves its explicit start speed. An eligible candidate wins only if its gain over eligible baseline is **strictly greater than 0.05 s**. A smaller positive gain is `unresolved_close_gain`: the baseline stays selected and the candidate remains inspectable. The 0.05 s margin is a provisional heuristic based on observed grid sensitivity, **not** a certified error bound. A finer-grid study is needed to rank close paths. If only a candidate has an eligible time for a reason other than failed baseline path audit, it may be displayed without claiming a gain. An optimizer stop without success can still supply a geometrically feasible candidate; a lower geometry objective `J` can still lose the car-dependent time comparison. This is a coarse car-dependent line-strength search plus an optional local grip-detour proposal, not arbitrary-path minimum-time optimization. The separate four-wheel lab still has its own wind/road/pose model; it does not feed this geometric planner. The main-lap AI comparison can now map an assumed world-fixed lower-grip rectangle to each path's solver cells before scoring it.

`optimization/road_grip_schedule.py::world_patch_grip_schedule` performs that optional mapping. The UI accepts a positive patch factor `a` no greater than one, finite world-coordinate X/Y bounds with positive spans, and a coherent closed source course. For every **trial path independently**, it integrates the prescribed constant-curvature cells from the same initial-heading rule as `CurvaturePathAudit`. At distance `s` in a cell, heading is `psi(s)=psi_entry+kappa*s`; CG displacement is `s*sinc(kappa*s/2)` along heading `psi_entry+kappa*s/2`. A nominal wheel center is the CG plus longitudinal offset `l*(cos psi,sin psi)` and lateral offset `b*(-sin psi,cos psi)`. With wheelbase `L` and static front fraction `f`, `l_front=L*(1-f)`, `l_rear=-L*f`, and `b` is plus/minus half that axle's track width. This geometry is a **contact-location sensitivity**, not independently simulated wheel force, suspension, slip, or pose tracking.

The mapper conservatively detects intersection between each nominal wheel-center curve and each world rectangle. A midpoint derivative bound excludes separated intervals; intervals near an edge are bisected, and possible contact unresolved within 0.01 m is treated as contact. A fixed 2,000,000-interval budget raises rather than returning a silently incomplete map. The entire cell receives the **minimum touched** factor: `q_i=gamma*min(beta,a)` for a touched cell, `q_i=gamma*beta` otherwise, where `gamma` is the selected car's reference tire multiplier, `beta` is `PlanarRoad.base_friction_multiplier` (one in the desktop), and `a` is a touched patch's factor. These `q_i` are the absolute inputs to Section 8.1's solver and event. For this map only positive grip reductions are supported; the UI allows one rectangle, while the mapper caps its programmatic input at 128 and rejects bounded road-validity domains. Programmatic rectangles must also be pairwise disjoint, including their inclusive boundaries. `PlanarRoad.query` assigns an overlap to the first matching patch, while the mapper lowers a whole cell to its minimum touched factor; rejecting overlapping rectangles avoids inconsistent interpretations. A lower factor for the whole cell can overstate the effect of a small patch. It does not derive actual wet grip or four contact-specific limits. The mapping version is `integrated_arc_nominal_wheel_min_cell_v1`; each saved AI trial stores its own exact tuple and planning metadata. `replay_lap_record` checks both the recorded grip trace and regeneration of the tuple from the saved rectangle and effective vehicle. This checks **internal numerical provenance**, not whether the patch existed on a real course.

For disjoint programmatic patches, the general cell rule is
`q_i = gamma * min(beta, a_1, ..., a_n)`, where the `a_j` are factors of
patches touched in cell `i` (or only `beta` when none are touched).
Several separate patches can affect one coarse cell, so this is a conservative
cell capacity, not a claim that any single wheel position has both materials.
The mapping version remains `v1` because supported disjoint inputs produce the
same tuples. A previously saved overlapping-patch claim now fails replay with
an explicit mapping error instead of being treated as agreement with the
first-match road model.

`optimization/grip_detour.py::propose_grip_detour` is a second, optional
geometric proposal for **one assumed rectangle**. It runs only after the
processed baseline passes the same modeled-path audit used for ranking. The
road mapper identifies cyclic groups of baseline cells whose nominal wheel
centers contact lower grip; no group, a whole-lap group, an unaligned plan,
or a mapping failure returns a stated reason and adds no trial. The proposer
examines at most the two longest contact groups, both left/right sides, and
three fractions (0.5, 0.75, 1.0) of the available offset per side. Thus it
constructs at most **12 geometries**, with at most **5,000 baseline cells**.
Each shift has a plateau over affected cells and periodic lead-in/lead-out
shoulders at least `max(12 m, 5 wheelbases, 6 grid spacings)` long. Their
quintic `S(u)=6u^5-15u^4+10u^3` has zero first and second derivatives at
the joins, giving a C2 nominal offset. Amplitude is capped at **3 m**, at
90% of the usable scalar corridor ratio checked at planner/source stations,
and by the requested maximum cell length after rebuilding geometry. Undefined
normals, reversed travel, invalid geometry, and polygon self-crossings are
screened out. The remaining candidates each get a fresh path-specific wheel
grip schedule.

The cheap screen minimizes weighted low-grip exposure
`E=sum_i ell_i max(0,1-q_i/(gamma beta))` metres, where `ell_i` is the
candidate cell length, `q_i` its absolute mapped grip, and `gamma beta` the
uniform reference. At least **0.01 m** exposure reduction is required;
candidate length and offset magnitude break ties deterministically. This
quantity is neither lap time nor a friction-circle capacity proof. The
single proposed detour still faces the complete integrated-curvature scalar
corridor/closure audit, then the ordinary speed-only seam and full-model
timing if admitted. It can be selected only by a completed eligible lap more
than **0.05 s** faster than the eligible processed baseline. A faster full,
half, or fourth offset can beat it; the patch does not force avoidance. The
run record stores `candidate_trials[].strategy="grip_detour"` with null
`offset_strength`, its exact per-cell schedule, and
`grip_detour_search` status, exposure and work counts. This deterministic
offline proposal is not learned from laps, a swept-body or pose-tracking
guarantee, or a measured-road model.

`optimization/grid_stability.py::diagnose_paired_grid_stability` is an on-demand timing sensitivity check for two already eligible paths. It preserves the original cell boundaries and curvature, halves the smaller maximum cell length by default, preflights each refined grid against a 5,000-cell cap, and reruns the same start policy with independent car copies. It reports original/refined candidate-minus-baseline time, sign stability, and whether the 0.05 s selection-margin crossing is stable. Its API defaults to a **one-pass** lap, matching `compare_lines_with_lap_model`; callers using speed-periodic original times must explicitly request `speed_periodic=True` for the check. On an unchanged synthetic grid, the two start policies differed by about **0.449 s** in a focused probe, so mixing them would confound the grid comparison. The desktop passes `speed_periodic=True` explicitly for both its original comparison and optional check. Its **Check finer grid (optional)** action uses the effective pre-run car frozen by the AI worker and offers this check when both path audits and completed times are eligible on uniform road or the assumed rectangular-patch setting. For a patch, it maps the same world-fixed rectangle independently onto each refined path, freezing that path's original modeled entry heading because chord interpolation can otherwise change the mapper's automatic heading choice. A completed report changing either the sign or the provisional 0.05 s margin crossing marks the main AI headline and status **grid-sensitive; ranking unresolved**. The same qualification appears in the path-comparison and saved-evidence windows, including windows already open, and beside the ordinary AI replay selector; those remain explicitly original-grid views. The original-grid path and numbers remain displayed, and saved trial records stay available; no path is reselected or record rewritten. A later completed stable report clears the qualification. Stale inputs clear the displayed result; failed or non-completed retries do not establish a stable ranking. A failed refined road mapping yields an explicit non-completed diagnostic. The API's separate explicit per-cell grip-tuple mode repeats each original cell's value over its subdivisions; that mode **does not** remap a world rectangle. The check does not rerun the corridor audit, validate the road assumption, or promote a path. It can add four full lap-model passes and is outside the desktop's default calculation.

The finer-grid report compares only the original selected candidate with the
baseline. Its 0.05 s crossing is a threshold check for that fixed pair; other
AI trials and any runner-up are not rerun. A stable pairwise check therefore
does not confirm the best-path ordering across all original trials.
When a completed check makes the selected AI rank unresolved, the WIP
selected-path synthetic pose preview is disabled until a completed stable
check or a new eligible AI run. An already generated trace and any saved file
remain available. An already displayed selected-path trace receives an
original-grid uncertainty qualifier without changing recorded state or
controls; a separately loaded file retains its generic recorded-sampled
label because the archive does not attest a current AI ranking.

A popup showing an older result keeps its grid-sensitive caveat beside its
frozen numbers after current inputs invalidate that result; newly opened
popups use the new result's state. This prevents old original-grid figures
from silently losing their uncertainty label.

An unmerged **in-memory biarc prototype** explored connecting the intended x/y endpoints with curvature-consistent arc segments. It reduced geometric mismatch to roughly **1e-9 m**, but took **2.2–2.5×** as long and changed modeled lap times by **5–7 s** because of curvature spikes. A separate unmerged one-circular-arc-per-edge experiment used an odd **991-cell** path and closed its integrated geometry to about **2e-11 m**, but increased peak absolute curvature and adjacent curvature jumps. Its one-pass times shifted by **5–7 s**, one TREV numerical ranking reversed, and compute rose about **2.5×**. Exact position closure alone does not establish physical or numerical validity. Neither prototype is used by the simulator; any replacement needs consistent geometry, controlled curvature, course review, and independent resolution and vehicle checks.

Research basis: [TUM FTM's variable-friction minimum-time implementation](https://github.com/TUMFTM/global_racetrajectory_optimization/blob/master/opt_mintime_traj/Readme.md) shows that spatial friction can change the preferred line but needs nonlinear optimization and wheel/tire data. [Kapania, Subosits, and Gerdes](https://ddl.stanford.edu/sites/g/files/sbiybj25996/files/media/file/2015_dscc_kapania_sequential_2step_0.pdf) motivate alternating friction-limited speed evaluation and path updates, while [Jain and Morari](https://arxiv.org/abs/2002.04794) motivate sparse lateral candidate parameterization and fixed-path lap-time scoring. LapSim implements its own bounded deterministic approximation, not those solvers or their performance guarantees. `docs/ai_racer_design.md` has further source links and geometry checks.

## 9. What the main GUI displays

| View/control | Source and meaning |
|---|---|
| Course | Explicit fused GNSS/IMU default, synthetic AI demo, synthetic FSAE-style practice course, or validated versioned import; changes input course and clears prior results/replay without enabling AI |
| Car profile / editable boxes | Fresh vehicle from `build_vehicle` or editable Prius-equivalent `VehicleSetup`; seven car fields editable on Prius and saved copies |
| Assumed road grip | Positive base tire-capacity factor in percent, default 100%; remains uniform for centerline and both car profiles, and is the base for AI trials |
| AI trial surface | Uniform by default; optional editable world X/Y rectangle with lower grip as a percent of base on a coherent closed source course. Each AI path gets a separately mapped absolute cell schedule, saved and checked on replay |
| Driver request | Constant fraction, 0-100%, of motor torque-curve request before vehicle/path limits |
| Cell size (max) | Fixed Calculation settings entry beside Run; user-requested upper bound on generated main-lap physics cell length in metres, with a centerline solver-cell count or invalid-size hint. AI mode says its separate grid varies until planning. Fused centerline source is resampled, coherent synthetic/imported source arcs remain finer or are analytically subdivided, and optional AI rebuilds its separate geometric grid until generated path cells meet the bound. The WIP pose preview reads the same entry at start and freezes a separate coherent synthetic grid: requests finer than its 0.5 m source analytically subdivide it, coarser requests keep the source. It labels requested and effective resolution and enforces a 5,000-cell UI cap |
| Driving path | Centerline is default; experimental AI requires assumed corridor half-width, vehicle width, and safety margin |
| Run one lap | Worker executes one rolling-start prescribed-path lap in default mode; AI mode plans one geometry candidate and tests full, half, and one bounded fourth offset against its processed centerline |
| Calculation progress bar | Labeled fixed monochrome strip: local corner-limit cells and current recorded-lap accepted cells have measured within-phase fractions; cyclic braking names its pass and processed cells while remaining indeterminate until convergence; planning, explicitly labeled speed-seam probes, and the transition to the final lap remain indeterminate; complete/stopped state at result |
| Compare car profiles | Two saved/built-in profiles run against the same course, step, driver fraction, and feasible rolling-start speed; B-minus-A numbers and separate finish/seam speeds are model differences |
| Eight boxes | Lap time, peak speed from the rolling start and recorded cell exits, average speed (`course_length/time`), course distance, signed net pack-model energy, peak `abs(lateral acceleration)/g`, and entry/exit speeds |
| AI result boxes | Eligible baseline/candidate times and signed difference when both audits pass; completed audit-failed times carry `*`, difference is blank, Compare path numbers is disabled, and text gives observed excess, certification status, and seam gap |
| Check finer grid (optional) | Enabled for two eligible completed AI paths on uniform road or the assumed rectangle. A worker reruns the same fixed paths with the frozen effective car and driver request on a finer grid, up to 5,000 cells per path and four additional speed-seam lap passes. For patch trials it remaps the world-fixed rectangle separately on each refined path using that path's original modeled entry heading. It reports original/refined signed time differences, sign and the fixed pair's 0.05 s selection-threshold crossing; other AI trials are not rerun. A completed sign or threshold-crossing change flags the main result, path comparison, saved-evidence window, and AI replay context as grid-sensitive/unresolved while leaving the original-grid path, numbers, and records intact. A stable pairwise check does not confirm global trial ordering, convergence, renewed clearance, or measured-road validity |
| Trace selector | Speed, acceleration, drive/braking forces, inferred driven slip, or battery power from named telemetry channels, against time or distance |
| Course map | Selected source x/y reference, fixed top-down; mouse drag pans and wheel zooms; a selected AI rectangle is outlined in black/white. The fused course displays its geometry warning while the synthetic choices are labeled as assumed examples |
| Driver view tab | Static labeled source-course preview while preparing; latest accepted physics cell on the exact trial grid during a solve; then timed top-down replay on each run's saved solver-grid x/y with fixed car marker, play/pause, scrub, rate, wheel zoom, cell control/force number boxes, and a Replay lap menu for completed comparisons; the separately labeled synthetic pose preview uses simulated x/y and heading |
| Timed sessions · WIP tab | Optional bounded 80 m synthetic four-wheel pose preview on the coherent demo centerline, plus a selected eligible AI candidate path preview on that same demo using an explicit sampled-polyline reference. Both use a separate synthetic car, uniform base grip or a labeled assumed 0.3× first-bend patch, and a signed initial offset inside a nominal ±1.9 m input bound. Save/Load persists and numerically checks only this separate synthetic trace; the versioned team controller, ghost, full session capture, and comparison workflow remain unavailable |
| Saved run details | Read-only text window for the currently displayed lap or A/B result: full content IDs and files, profile, result, source/boundary status, solver path, AI original-grid rank/assumptions, and available linked AI trial records. Optional finer-grid findings are not in the saved lap record |
| Source data / model notes | Inspect reviewed records, origins, model use, and caveats; inspection does not change the active vehicle |
| Dark mode | Reverses white/black Tk and Matplotlib surfaces; it does not change a simulation parameter |

The GUI deliberately keeps numeric output boxes and simple monochrome traces.
The calculation bar shows a measured fraction **within** local corner-limit
preparation or the current recorded lap's accepted cells. Its cyclic braking
label reports pass number and processed cells, but remains indeterminate
because convergence can take an unknown number of passes up to the solver
cap. Planning, speed-only dry passes, and saving likewise have no reliable
overall work count. The bar names the active car/path as accepted cells
arrive and is never an overall AI completion percentage or ETA. Starting a
new lap or car comparison clears the prior numeric result and Analysis
trace immediately, so a failed replacement calculation cannot leave an old
trace next to empty boxes. Car and path comparison windows name the selected
course, and that label remains visible if the main window later switches
courses. A solid line means A/current run and a dashed line means B in
comparisons. Do not infer measurement uncertainty from line thickness, and
do not interpret a visually overlapping trace as an identical force or
energy history. For exact values and full channels use the saved JSON record.

For A/B, `prepare_one_lap_constraints` solves each car's limits once on the same grid. Its wrapper binds the limits to that vehicle; reuse with another car or track is rejected. The app starts both at `min(ceiling_A[0], ceiling_B[0])` m/s. Keep each car's setup unchanged between limit preparation and running.

Both cars then complete one recorded pass with that explicit rolling start and the same constant driver torque fraction. The constraints are reused instead of solved again; the extra shared-start selection adds no lap-model pass. Both records freeze the same start speed in their endurance settings, so `replay_lap_record()` can reproduce each saved command trace. Each car still has its own tire/powertrain limits, battery state, achieved finish speed, and nonperiodic speed seam. The B-minus-A lap difference is a same-start **model sensitivity comparison**, not a steady-state race prediction or validation against either car.

`ui/comparison.py::summarize_lap` computes displayed peak speed from the
rolling start **and** every recorded accepted-cell exit. Telemetry starts
after the first cell, so a car that slows through its opening cell could
otherwise report a peak below the shared start speed shown in the A/B popup.
For a complete synthetic two-cell example starting at **20 m/s** with
recorded exits **10 and 8 m/s**, the corrected peak is **72 km/h** rather
than **36 km/h**. Legacy records without a start speed retain the exit-only
summary. This is a peak of the modeled boundary samples, not an independent
continuous-speed measurement.

**Compare path numbers** shows each AI path's rolling start speed, finish speed, and finish-minus-start seam speed beside its lap metrics. Speed-seam shooting solves the rolling start independently for the processed baseline and candidate. The paths use the same effective vehicle configuration, initial pack state, and driver torque request, but their rolling start speeds may differ. The displayed AI lap-time difference compares those two path-specific speed-closed model laps; it is not a same-start experiment or a validated race-time advantage.

### 9.1 Live accepted-step view and completed playback

The separate synthetic pose preview starts a size-one queue of the newest
accepted `(PoseDriverSample, PlanarState)` pair. It opens Driver view before
the first step, draws simulated planar x/y and heading against the assumed
reference course, and replaces the live frame with completed replay. The
worker does not call Tk. Live control requests and lateral acceleration are
unavailable in that callback and display dashes. The WIP **Road condition**
selector defaults to **Uniform base grip (1.0×)**. Its other option, **Assumed
bend patch (0.3×)**, freezes an environment with one world-fixed x 36–55 m,
y −3–16 m rectangle on the first synthetic bend. It is not measured dry or
wet-road data. The adjacent **Initial lateral offset (m)** input defaults to
zero and is signed along the start path's left normal: positive starts left
of travel. The worker receives both selected values before starting; live
status, replay, and result text identify them. Changing either while idle
clears an old pose preview and its boxes, without discarding an ordinary lap
replay. Neither can be changed during the calculation. The nominal ±1.9 m
input range is derived from the assumed half-width, car width, and margin;
the sampled body footprint can still start outside the curved corridor.
An additional **Preview selected AI path (80 m)** button is enabled only
after the synthetic demo's optional AI comparison selects a faster eligible
candidate with passing modeled-path audit and completed baseline/candidate
times. The worker freezes that selected polygon and refines its chords to
the smaller of the entered cell-size maximum and 0.5 m, under a 5,000-cell
desktop cap. It sets `reference_geometry="sampled_polyline"`; the ordinary
pose preview retains strict coherent arcs. Changing the source course or a
run input retires the selected path button. The displayed pose and time use
the separate synthetic car and WIP road scenario, which need not match the
selected Prius/TREV car or optional AI trial's road schedule. A loaded
polyline trace is labeled as a recorded sampled reference without asserting
the provenance of an absent AI comparison.
An unresolved finer-grid selected-path ranking disables a new selected-path
preview while leaving an already displayed selected-path synthetic trace
available with an original-grid uncertainty label. A separately loaded
sampled-path record does not claim the current AI ranking.
After a run, **Save last synthetic trace…** captures its complete bounded
trace in a separate schema-v2 JSON file; **Load synthetic trace…** validates
and replays it in Driver view on the UI worker. A zero-step stop loads with
its status and no invented playback motion. The initial save directory is
`%LOCALAPPDATA%\LapSim\pose_runs` on Windows. The UI disables these actions
during calculation and does not change an ordinary lap record or selected
car profile. Section 14.4 gives the exact archive and check contract.

`EnduranceSimulator.run` accepts an optional `progress_callback`. After a cell passes the path, speed, traversal, time, and stall checks, it emits an immutable `LapProgressSnapshot` with zero-based lap/cell indices, cell count, elapsed model time, current-lap station, total model distance, speed, and lateral acceleration. A cell rejected by those checks emits no snapshot. A cell that reaches zero pack SOC at its endpoint is present in both telemetry and progress before the event stops with a depletion failure. `ui/simulation.py::run_one_lap` forwards the callback, and `compare_lines_with_lap_model` adds the phase (`baseline`, `full`, `half`, `three_quarter` fallback, or `adaptive` fourth) and exact trial track for AI runs. The normal core API pays only a conditional branch when no observer is supplied; callback tests compare observed values with recorded telemetry and unchanged final lap time/energy.

Before any vehicle cell is accepted, `PathConstraintSolver.solve` can emit
`PathConstraintProgressSnapshot(phase, completed_cells, cell_count,
pass_number, maximum_passes)` through an optional observer. It reports
completed local corner-limit cells and cells in each descending cyclic
braking sweep at a bounded stride. `prepare_one_lap_constraints`,
`run_one_lap`, `run_speed_periodic_lap`, and the AI trial comparison forward
that observer to the desktop; their physics result is unchanged without one.
The UI coalesces these messages, shows an exact local-limit phase fraction,
and reports each cyclic braking pass without treating the configured maximum
pass count as a convergence percentage. Driver view remains a static map
with **NO VEHICLE POSE** during these callbacks.

The snapshot also copies the accepted cell's next-entry braking ceiling,
motor torque request, front/rear brake pressure requests, achieved drive,
friction-brake, and regenerative-brake forces, longitudinal acceleration,
and signed pack-terminal power. It reads already solved scalar state; it
does not evaluate forces or rerun the vehicle. The progress regression
compares all nine values with same-cell saved telemetry and checks that
attaching the observer does not change lap time or energy.

The desktop's worker throttles **accepted-lap snapshots** to at most about
one update every 0.1 s of computation, plus the phase's final accepted cell.
The path-constraint observer instead emits up to about 100 snapshots per
local-limit stage and per braking pass; these are not time-throttled. Both
types enter the same one-slot queue, and the Tk thread consumes only the
latest event rather than reading mutable vehicle state. Before a recorded
physics pass emits an accepted cell, Driver view fits a **static
source-course preview** with the start marked and an explicit **NO VEHICLE
POSE** label. It returns to that static preview after a completed AI trial
or a half-second pause without an accepted cell, retaining the last accepted
numeric values. During an active solve it shows the accepted endpoint on
that trial's **exact solver-grid reference x/y path**, its modeled speed and
lateral acceleration, and a station-based progress bar. A serial guard
prevents old preview timers from replacing a newer trial or completed
replay. Replay buttons and scrubbing stay disabled until a completed run
arrives. A stopped run leaves the last accepted step visibly labeled. The
display runs at computation speed; it does not pause the solver to animate a
real-time driver.

`ui/driver_view.py::DriverPlayback` requires four equal-length, finite, synchronized telemetry arrays: `vehicle.time_s`, `vehicle.distance_m`, `vehicle.speed_mps`, and `vehicle.lateral_acceleration_mps2`. It rejects nonincreasing time, decreasing distance, negative speed, and a station beyond the displayed path. Endurance telemetry begins after an accepted cell, so playback prepends a time-zero display frame at station zero when necessary. Its initial speed is recovered from the first cell's distance, exit speed, and elapsed time. Given a requested display time within a consistent cell, it interpolates speed and station with the same constant-acceleration relation as `Vehicle.update_state`; inconsistent imported cells use linear station interpolation instead. Solver-aligned lateral acceleration holds the **active cell's** solved value because the core produces one force result per accepted cell. Legacy traces without that alignment retain linear display interpolation. It then interpolates x/y by station on the run's solver-grid reference path and computes a displayed heading from nearby path points. The canvas transforms a short path segment into the car-fixed view; its sampling includes the car station and visible ends of an open course, so a coarse spacing cannot leave the marker detached from the line. The triangle stays fixed while the map line rotates. The GUI uses wall-clock time only to advance the display cursor, with selectable 0.25× to 4× speed. Playback can be scrubbed and zoomed without rerunning physics. After a completed A/B car comparison, **Replay lap** selects either recorded profile and its shared saved solver grid. After completed AI trials, it selects among the geometric baseline and whichever offset trials actually ran, each paired with its exact processed path; an audit-failed run is explicitly labeled **diagnostic** in the menu. Switching resets playback to the beginning, retains the previous play/pause state, and makes no new solver call. The selector is disabled if fewer than two completed runs are available.

The monochrome **cell model values** panel has these exact sources and display
conversions. Each quantity belongs to the accepted cell; it is a command or
achieved model value as labeled, not a measured driver action. The next-entry
ceiling is `constraints.braking_speed_ceiling_mps[next_cell_index]`, recorded
under `endurance.path_speed_ceiling_mps`; the torque/brake controller also
checks the current cell's local corner limit, so this one ceiling is not the
whole target-speed rule.

| Box | Saved telemetry channel | Display conversion |
|---|---|---|
| Next-entry ceiling | `endurance.path_speed_ceiling_mps` | m/s × 3.6 → km/h |
| Motor request | `controls.motor_torque_request_nm` | N·m unchanged |
| Front brake / rear brake | `controls.front_brake_pressure_psi` / `controls.rear_brake_pressure_psi` | psi unchanged; requested pressures |
| Drive force | `vehicle.drive_force_n` | N ÷ 1,000 → kN; achieved |
| Friction brake | `vehicle.friction_braking_force_n` | N ÷ 1,000 → kN; achieved magnitude |
| Regen brake | `vehicle.regenerative_braking_force_n` | N ÷ 1,000 → kN; achieved magnitude |
| Longitudinal | `vehicle.longitudinal_acceleration_mps2` | m/s² ÷ 9.80665 → signed g |
| Net battery | `battery.power_w` | W ÷ 1,000 → signed kW; positive discharge, negative charge |

For replay, `DriverPlayback` uses an active-cell zero-order hold on those
optional channels **only when** saved station, time, and speed match the
solver's cell grid and constant-acceleration distance relation. At an exact
interior cell boundary it switches to the next cell; at the final endpoint
it holds the last. Missing, nonfinite, wrong-length, or physically invalid
optional channels display `—` independently; unaligned legacy traces show
`—` for all cell decisions. Live progress instead shows the latest accepted
snapshot directly, since a one-snapshot preview does not contain the
prefix of earlier cells needed for playback alignment. Tk may coalesce
intermediate updates, but no extra physics pass is performed.

For a centerline lap, including either car in a profile comparison, the displayed path is the exact centerline solver-grid x/y frozen in the saved run; for an AI trial it is that trial's processed solver path. Live progress and completed replay therefore interpolate the same per-run reference geometry. The separate Analysis course plot still shows the source x/y, which can differ after solver resampling. None of these **lap views** is the integrated `Vehicle` x/y/heading state. In particular, the fused default track's x/y and curvature disagree numerically even on the saved grid. The lap view is a useful time/station and speed preview but does **not** show steering error, tire path tracking, cone proximity, a true driver's camera, or interactive driving. The desktop switches to this tab when a lap calculation starts and shows a static labeled source-course map with the start marked and **NO VEHICLE POSE** until an accepted cell arrives. A pause between accepted cells returns to that preview; completed laps start replay. The optional WIP pose preview instead plays the separate four-wheel model's actual simulated x/y and heading with an explicit synthetic model-time label. It does not validate the lap solver's reference-path playback. A full timed session remains unavailable until a versioned controller contract, complete input/state/environment capture, replay tolerance policy, and linked comparison report exist.

During the pose preview, the nine decision boxes change labels. Live updates
show reference cross-track error (m), heading error (degrees), sampled local
road-grip multiplier, assumed axle-span footprint slack (m), and yaw rate
(degrees/s); the four control boxes and lateral acceleration display dashes
because that callback does not supply them. Completed replay additionally
shows recorded front steering request (degrees), rear drive request per wheel
(N·m), and FL/FR brake requests (N·m). Controls are held over each 0.05 s
output interval. The pose Driver view's lateral-acceleration box holds the
recorded **pre-step force evaluation** throughout that active interval and
switches to the next evaluation at the next boundary; it is not a continuous
force sample. Geometric diagnostics and yaw rate are interpolated between
recorded states for replay display only. Switching back to a lap restores the
endurance-model box labels and telemetry. The pose boxes do not imply motor,
pack, or hydraulic brake hardware modeling.

If the pose status is `road_domain_invalid`, a local-grip sample may contain
the base-road diagnostic fallback from a query outside the declared road
domain. The desktop warns in the status and Driver view that this displayed
number is not valid road data; it must not be read as measured grip or as
coverage of the missing domain.

## 10. Four-wheel lab: state, control, tire, and motion equations

`src/lapsim/dynamics/planar.py` is a separate **ten-state** ordinary differential equation model. Its state is `(X,Y,psi,u,v,r,omega_FL,omega_FR,omega_RL,omega_RR)`: three planar pose values, three body motion values, and four wheel speeds. `PlanarControls` holds four steering angles, four signed drive torques, four nonnegative friction-brake torque requests, optional four normal-load overrides, and optional external body force/yaw moment. The desktop holds these controls constant throughout each A or B run; it sets equal left/right front steering and zero rear steering. An external controller can provide a different sequence to `run_planar_dynamics`. The GUI does not simulate a motor, inverter, pack, torque delivery latency, or controller feedback in this mode. A negative drive torque is a signed generating/reverse mechanical request, not an automatically constrained battery-regeneration command.

The lab's default synthetic vehicle uses `m=300 kg`, `Iz=160 kg m^2`, `a=b=0.8 m`, `tf=tr=1.2 m`, `R=0.2 m`, wheel `J=0.3 kg m^2`, `mu=1.5`, `Ck=7000 N/slip`, and `Ca=8000 N/rad`. Its default 1 s maneuver starts at `12 m/s`, front steer `1 degree`, output step `0.01 s`, and rear requests A `(120,120) N m`, B `(110,130) N m`; front torques are zero. These numbers are **test scenario inputs**, not a Prius or TREV calibration. They are visible and editable in the lab. `PlanarVehicleConfig` also holds gravity `9.80665 m/s^2`, regularization floor `0.5 m/s`, and maximum internal step `0.002 s` unless code changes them.

For front axle distance `a`, rear distance `b`, and front/rear tracks `tf,tr`, wheel body positions are `(a,+tf/2)`, `(a,-tf/2)`, `(-b,+tr/2)`, and `(-b,-tr/2)` in FL, FR, RL, RR order. With no override, static loads are `Fz_FL=Fz_FR=mg b/[2(a+b)]` and `Fz_RL=Fz_RR=mg a/[2(a+b)]`. They do **not** change with acceleration, grade, bank, aero, or a grip patch. Passing `controls.normal_loads_n` is a prescribed load experiment; it is not suspension physics. A zero-load wheel produces zero tire force but its spin equation still evolves.

At wheel center `(x_i,y_i)` and steering angle `delta_i`, the code computes contact velocity in the body frame and rotates it into that wheel's frame:

```text
Vxb = u - r y_i;                 Vyb = v + r x_i
Vxi = cos(delta_i) Vxb + sin(delta_i) Vyb
Vyi = -sin(delta_i) Vxb + cos(delta_i) Vyb
vref = max(abs(Vxi), v_floor)
slip_i = (R omega_i - Vxi) / vref
alpha_i = atan2(Vyi, vref)
Fx_raw_i = Ck slip_i;           Fy_raw_i = -Ca alpha_i
Fcap_i = mu * road_multiplier_i * Fz_i
scale_i = min(1, Fcap_i / hypot(Fx_raw_i,Fy_raw_i))
Fx_i = scale_i Fx_raw_i;        Fy_i = scale_i Fy_raw_i
```

When the raw force magnitude is zero, `scale_i=1`. The common scale is a circular **combined** force cap, so large requested longitudinal force reduces the achieved lateral force and vice versa. `v_floor` is 0.5 m/s in the lab's default synthetic car, preventing division by zero during launch or wheel lock. It changes the low-speed law; it is not a tire measurement. Reverse behavior is qualitative. The grip multiplier changes **only** the force cap; it does not change stiffness, contact load, wheel radius, or the slip formula. A measured tire lookup would need load, slip, camber, road condition, and temperature data with units and validity ranges.

The achieved wheel force is rotated back to body axes. The net yaw moment is `sum(x_i Fyb_i - y_i Fxb_i) + M_external`, with positive yaw counterclockwise. A larger forward force at the right rear has a positive yaw contribution. The state derivatives are:

```text
Xdot = u cos(psi) - v sin(psi);  Ydot = u sin(psi) + v cos(psi)
psidot = r
udot = r v + (sum Fxb_i + Fx_external + Fx_aero)/m
vdot = -r u + (sum Fyb_i + Fy_external + Fy_aero)/m
rdot = (sum(x_i Fyb_i - y_i Fxb_i) + M_external)/Iz
J omega_dot_i = Tdrive_i + Tbrake_applied_i - R Fx_i.
```

Brake torque opposes actual wheel spin. At exactly zero spin it is capped to prevent a requested friction brake from creating wheel rotation in the opposite direction; integration also handles an incipient zero crossing. These brake rules are in the derivative/integrator, not a hydraulic pressure or ABS model. Unlike the main lap, the four wheel inertias are explicit energy and dynamic states, so they are **not** reflected into the body mass.

### 10.1 Power identity and integration

Every force evaluation computes `E = 0.5m(u^2+v^2) + 0.5Iz r^2 + 0.5J sum(omega_i^2)`. Mechanical drive and brake powers are `sum(Tdrive_i omega_i)` and `sum(Tbrake_applied_i omega_i)`. Contact dissipation is `sum[Fx_i(R omega_i - Vxi) - Fy_i Vyi]`. External power is `Fx_external u + Fy_external v + M_external r + Fx_aero u + Fy_aero v`. The diagnostic is:

```text
power_residual = E_dot - P_drive - P_brake
                 + P_contact_dissipation - P_external.
```

It should be at roundoff for a force evaluation, including the added aero work. This identity checks sign and accounting consistency at an instant. It does not prove that an RK4 trajectory conserves energy exactly, that every requested torque is hardware-feasible, or that the tire parameters are real. The code records the diagnostic in `PlanarEvaluation` and shows it at the GUI cursor.

`run_planar_dynamics` uses classical fourth-order Runge-Kutta with held controls/environment over an output interval, splitting that interval into smaller internal steps. The cap is `min(user_max_step, 0.8/lambda)`, where `lambda=(Ck/v_floor)(R^2/J+4/m)` approximates the fastest small-slip mode. The synthetic config's explicit maximum is 0.002 s; stiffness may force smaller substeps. The public run stores `N+1` boundary times/states and `N` pre-control interval evaluations. There is no final-point evaluation because no control interval follows the final state; the GUI computes one only for display with the last held control. A single-step API raises on an invalid road query; the batch runner returns a flagged run. The output count and internal substep count have explicit upper bounds in code. The integration is deterministic for identical input values and code, apart from ordinary floating-point/runtime variation.

### 10.2 Bounded pose-aware preview on the synthetic loop

`optimization/pose_driver.py::run_pose_driver` couples this **same separate
four-wheel model** to a simple feedback controller targeting **80 m** of
progress on the coherent synthetic rounded rectangle. The WIP tab can show
its actual planar x/y and heading through `ui/pose_driver_playback.py`; the
playback labels elapsed time as **pose-model time** and has no battery or
endurance-lap result. The car is the explicit 300 kg synthetic planar
configuration from Section 10, independent of the active Prius/TREV profile.
During completed replay, the steering and torque/brake boxes hold the issued
control for its recorded interval. **GRIP SAMPLE (×)** reads the latest
recorded pose sample, including the final sample at the terminal time; the
display does not perform another force or road-physics step.
Tracking error, heading error, and assumed boundary slack are interpolated
only while both adjacent pose samples have a valid local path projection.
At an exact valid sample boundary the display uses that recorded sample;
after projection is lost these three boxes show an unavailable dash instead
of stale geometry or a fabricated number. Held commands, grip, yaw rate,
and the simulated x/y pose remain visible. This presentation rule does not
alter the recorded state, controller, or physics integration.
If terminal projection is lost, the pose summary labels distance as the
**last confirmed station** and reports assumed footprint slack as unavailable.
The Driver view's **STATION** box shows an unavailable dash through the
failed interval and at its terminal sample rather than presenting that stale
station as the current pose projection. Live invalid samples also mask their
tracking, heading-error, and assumed-slack boxes. The retained numeric
station remains internal to viewport sampling; actual pose, speed, and
recorded controls remain visible. The prior station is not a projection of
the final simulated pose.

The path is a reference for steering; the state evolves from the four-wheel
forces and yaw equations above. This gives a controlled pose experiment,
not a calibrated Formula SAE lap or complete driving session.

By default, `run_pose_driver` first validates that the supplied closed
course has coherent constant-curvature straight/circular-arc geometry. If
any source cell is longer than **0.5 m**, it uses
`SpatialTrack.refine_arcs(0.5)` to integrate analytic subarc x/y points,
retain every source station and curvature, and keep each resulting cell at
most 0.5 m long under the **100,000-cell** refinement cap. The shipped
synthetic course already has 0.5 m cells and is retained unchanged. The
control loop's `_path_point` still interpolates the resulting short x/y
**chords**, so refinement reduces a coarse-turn chord error without
substituting continuous-arc projection or proving physical path clearance.

An explicit `PoseDriverSettings(reference_geometry="sampled_polyline")`
allows the same bounded pose controller to follow an AI planner's sampled
x/y reference. This mode checks a closed, finite, nondegenerate polygon,
its station/chord agreement and adjacent-cell reversals, then uses
`SpatialTrack.refine(0.5)` to split chords while retaining the source
vertices. Its start heading is the first chord heading rather than an
analytic arc-entry heading. At each speed-preview station `s`, let
`h=min(0.5 m,L_track/8)`, `P-=P(s-h)`, `P0=P(s)`, and `P+=P(s+h)` on the
interpolated polygon. The bend proxy is
`max(|kappa_saved_cell|, |wrap(angle(P+-P0)-angle(P0-P-))|/h)`.
If either preview chord is degenerate, the controller asks for a slow
preview instead of trusting an undefined heading. Using a **fixed metric
span** prevents merely splitting an unchanged polygon into shorter cells
from doubling its bend estimate. This only chooses a speed target under an
explicit smoothing heuristic; a polygon vertex has no finite point
curvature. The option does not certify
self-intersection, a swept car footprint, measured cone clearance, or
agreement between the main lap's prescribed curvature and the driven pose.
The default strict arc mode and centerline lap calculation remain unchanged.

For local pose projection, `_project_local` visits each cell whose **station
interval overlaps** `[s_previous-window,s_previous+window]`, rather than
filtering by cell midpoint. It includes overlapping copies at the closed
lap seam and clips each candidate's projected fraction to that station
window. A bounded full-track branch covers windows of at least half a lap.
This prevents a long cell crossing the window or seam from being silently
omitted; it does not disambiguate self-intersecting roads or certify a
surveyed corridor. The controller projects the CG to calculate progress,
cross-track error, and assumed body-corner slack, then projects the
**rear axle** into a local 12 m station window,
then looks `ell = min(30 m, track_length/2,
2.5 m + (0.45 s) sqrt(u² + v²))` ahead along the reference.
For bearing error `alpha` from the vehicle heading to the target, wheelbase
`L`, and direct rear-axle-to-target distance `D` (floored at **0.5 m**), it
requests `delta = atan2(2 L sin(alpha), D)`, clipped to **±0.30 rad**. The
rear-axle geometry follows
[Coulter's pure-pursuit report](https://publications.ri.cmu.edu/implementation-of-the-pure-pursuit-path-tracking-algorithm);
the [TORCS steering tutorial](https://torcs.sourceforge.net/api/robot_tutorial_chapter_4.html)
also distinguishes lookahead station distance from the direct target vector.

Speed control samples a **future reference-path envelope** at `n+1` evenly
spaced stations, where `H=min(60 m, track_length/2)` and
`n=max(2, min(120, ceil(H/0.5 m)))`. Thus the nominal interval is at most
0.5 m and work stays bounded even with extreme finite driver settings. At
each station it linearly interpolates the source x/y chord, uses that chord's
tangent for a nominal heading, and queries the declared road at that nominal
center and four nominal wheel centers. `q_j` is the minimum friction
multiplier among those five queries; an invalid query contributes zero to
the preview. The **current** grip `q_now` is independently the minimum road
multiplier at the actual simulated CG and four actual wheel centers. Future
wheel locations lie on the reference tangent, not on a predicted vehicle
trajectory. Sampling can miss a narrower road feature and does not check a
swept footprint.

For preview distance `d_j`, source-cell curvature `kappa_j`, vehicle base
tire coefficient `mu`, mass `m`, wheel radius `R`, maximum per-wheel brake
request `T_b=80 N m`, and `q_min=min(q_now,q_0,...,q_n)`, the controller uses:

```text
a_brake = min(0.20 mu q_min g, 4 T_b/(m R))
a_lat,j = min(4 m/s², 0.35 mu min(q_now,q_j) g)
v_corner,j² = a_lat,j / max(abs(kappa_j), 1e-9 1/m)
d_margin = 1 m + (0.45 s) speed + front_axle_distance
v_allowed,j = sqrt(v_corner,j² + 2 a_brake max(0,d_j-d_margin))
v_target = min(5.5 m/s, v_allowed,0, ..., v_allowed,n)
```

The brake expression reserves much of estimated friction and respects a
separate straight-line wheel-torque upper bound. The margin reserves
distance for response and front-axle arrival. Both constants are controller
assumptions, not measured response or a proof that the tire can attain the
target under simultaneous steering. The forward speed envelope is motivated
by the [TORCS speed-control tutorial](https://torcs.sourceforge.net/api/robot_tutorial_chapter_3.html),
which also uses bend targets and a distance-to-bend braking allowance; the
coefficients here are specific software heuristics. A single lowest future
grip value limits `a_brake` across the entire preview, intentionally
conservative for an upcoming patch. The controller requests up to **80 N·m**
drive on each rear wheel at gain **40 N·m/(m/s)** when `v_target > speed`, or
up to **80 N·m** brake on each wheel at gain **35 N·m/(m/s)** otherwise.
These gains do not guarantee exact tracking of the target. Neither source
calibrates this car or establishes tire-force feasibility.

The **Initial lateral offset (m)** setting uses `e_0=0` by default. The
initial CG position is `(X_ref-e_0 sin(psi_0),
Y_ref+e_0 cos(psi_0))`, so positive is left of travel. A finite input with
`|e_0| <= 3.0 - 1.8/2 - 0.2 = 1.9 m` passes the nominal CG-offset input
check. This is not the four-corner footprint check: the body can overlap the
assumed corridor at a curved start even when the CG offset is admissible.
The initial footprint is checked before issuing any control. In the
regression's **−1.9 m** case it is already outside and the run records
`outside_assumed_corridor` with zero controls.

The controller then applies a separate assumed-edge speed rule to the
future bend/grip target `v_prior`. Let `S` be the current smallest projected
slack from the four axle-span body corners. With path-tangent heading
`psi_ref`, CG cross-track error `e`, body velocities `(u,v)`, yaw rate `r`,
front/rear CG-to-axle distances `l_f,l_r`, and assumed body width `w`:

```text
v_lat = u sin(psi-psi_ref) + v cos(psi-psi_ref)
v_out_cg = abs(v_lat)                    when abs(e) <= 1e-9 m
           max(0,sign(e)*v_lat)          otherwise
v_out = v_out_cg + abs(r) hypot(max(l_f,l_r), w/2)
S_pred = max(0, S - (0.5 s)*v_out)
f = sqrt(min(1, S_pred/(0.8 m)))
v_low = min(v_prior, 2.0 m/s)
v_final = v_low + f*(v_prior-v_low)
```

The yaw term bounds a sampled body corner's contribution to lateral
motion; it is not an integrated future body path. At or beyond zero
predicted slack, the target is at most 2.0 m/s; at 0.8 m or more, the edge
rule leaves the previous target unchanged. The rule cannot raise a lower
bend/grip target and does not alter the pure-pursuit steering target. The
[TORCS steering tutorial](https://torcs.sourceforge.net/api/robot_tutorial_chapter_4.html)
motivates minimum four-corner clearance and reducing a previous speed
target near an edge, while warning that sampled corners do not certify the
swept path. LapSim's square-root blend and short outward-motion estimate
are its own heuristic, applied to assumed corridor geometry rather than
measured road edges. The requested speed can still differ from achieved
speed because force, grip, and control gains are modeled separately.

Default bounds are **0.05 s** per control step, **20 s** modeled time,
**400** control steps, and **60,000** internal substeps. The assumed corridor
is ±3 m with 1.8 m body width and 0.2 m margin. At each output sample, the
model projects the four corners of an axle-span body rectangle and stops on
negative assumed boundary slack or invalid declared road coverage. This
omits overhangs and does not certify between-sample swept clearance or real
cones. `PoseDriverRun` keeps time, issued controls, full planar boundary
states, force evaluations, projection samples, and termination status in
memory. `replay_pose_driver(run, tolerances=PoseReplayTolerances())`
reintegrates those controls and compares every recorded state at default
absolute limits **1e-8 m** position, **1e-8 rad** heading, **1e-8 m/s** body
velocity, and **1e-8 rad/s** yaw rate and wheel speed, plus road-validity
agreement. It recomputes every sample's time, station, cross-track and heading
errors, local grip, assumed footprint slack, and projection-valid flag from
replayed states and declared course/environment. Default sample tolerances are
**1e-9 s** time, **1e-8 m** station/cross-track/slack, **1e-8 rad** heading
error, and **1e-10** grip multiplier. Projection validity and derived stop
status must agree exactly. These are numerical replay tolerances for the short
synthetic trace, not measured tracking accuracy or a full-session record.
`replay_pose_driver` starts from the recorded initial `PlanarState`; when
loading a saved pose record, the record parser separately checks that this
initial state matches the exact saved track and offset setting. Neither
operation verifies the assumed corridor against an external survey.

## 11. Report II upgrade: wind and road conditions

`src/lapsim/dynamics/conditions.py` defines immutable `PlanarEnvironment`, `PlanarRoad`, `RectangularGripPatch`, and optional `RoadDomain`. Wind is a **world-frame vector** `(wx,wy)`. For heading `psi`, the derivative first rotates it into the body frame, then subtracts it from ground velocity:

```text
w_body = R(psi)^T w_world
U_body = (u,v) - w_body;       Vair = hypot(Ux,Uy)
F_aero_body = -0.5 rho CdA Vair U_body
P_aero = F_aero_body dot (u,v).
```

The final line uses **ground** velocity for the vehicle's mechanical power balance. Replacing it with `F dot U` would account for a different energy transfer involving moving air. A headwind raises apparent speed and drag; a tailwind faster than the car can make the modeled aero force accelerate the car. `CdA` is a single, isotropic, synthetic drag area placed at the center of gravity. A crosswind therefore produces a lateral component under this simple vector drag law, but the code does **not** claim a measured side-force coefficient, aero yaw moment, downforce, front/rear balance, CFD map, or ride-height coupling. `drag_area_m2=0` disables aero exactly and is the core API's backward-compatible default. The GUI starts with a clearly synthetic `CdA=0.8 m^2`, zero wind, and `rho=1.225 kg/m^3`; those values are study inputs, not team-car data.

For each wheel center, the code evaluates world position `(X+cos(psi)x_i-sin(psi)y_i, Y+sin(psi)x_i+cos(psi)y_i)` and queries the road there. The base material is `reference_pavement` with multiplier 1. A finite rectangular patch can assign a different nonnegative multiplier and material identifier. Patches are world-fixed, inclusive of their boundaries, and searched in tuple order; the first matching patch owns an overlap. The Four-wheel lab GUI can turn on one assumed low-grip rectangle and shows its top-down outline. It passes the **same** environment object to A and B. The separate WIP pose preview offers its own fixed first-bend rectangle, as described in Sections 9 and 10.2; its road scenario is not the lab's editable A/B setting. Neither patch is part of the shipped endurance course.

`RoadDomain` is a programmatic optional rectangle representing where road data are supported. If a wheel query leaves it, the road uses the base grip **as a diagnostic fallback** and sets `valid=False`; the result must not be ranked as a validated comparison. The batch run's `road_valid` flag aggregates all wheel force evaluations, including intermediate RK4 stages and the final state. `invalid_road_queries` counts invalid wheel-force queries, including repeated substep evaluations; it is neither elapsed time nor a count of unique places. The GUI reads the run-level flag, labels the result `INVALID ROAD DOMAIN`, and withholds the B-minus-A ranking. The GUI currently does not expose a domain editor; an API caller can supply one.

### 11.1 What Report II does and does not authorize

Report II is a design and verification source, not a command to copy its synthetic values into the team car. Its first defensible change is to keep the lap solver's established flat baseline while adding explicit air-relative wind and road contact queries to the independent-wheel lab. The report recommends a progression from scalar coefficients and flat road through measured six-component aero maps, surveyed elevation/bank/curvature, dynamic suspension/contact, and conservative thermal states. This implementation stops at the first environment layer because no reviewed team CFD map, ride-height schedule, tire/road friction map, elevation/bank survey, cell thermal characterization, or cooling test is available here.

The main distance-domain lap still uses ground speed as airspeed, a constant
density, scalar drag/downforce, and flat-road forces. Its **desktop** input is
one assumed uniform grip factor. The Python-only per-cell schedule in Section
8.1 changes the tire's scalar capacity by solver station, but does not query
world-fixed wheel contacts or model the rectangular road patch. The new
`PlanarEnvironment` is **not** passed into `run_one_lap`,
`PathConstraintSolver`, or `Vehicle.update_state`. Neither the lab's
wind/patch nor the WIP pose preview's patch changes a main-lap desktop time;
the separate main-lap Assumed road grip (%) input does. Connecting a
world-fixed condition safely requires a path-referenced world wind field,
force/moment allocation without double counting, a contact-point road query
compatible with the lap model, and new regression/validation cases. Sections
16-17 define the evidence gate for that work.

## 12. Four-wheel GUI inputs and outputs

`ui/dynamics_lab.py::ManeuverSettings` freezes a car config, initial speed, steering, duration, output step, four A torques, four B torques, equal-total requirement, and one shared environment. It validates finite values, speed 0-40 m/s, steer within 30 degrees, duration `(0,10]` s, output step 0.002-0.1 s, integral 1-2000 output steps, and per-wheel torque magnitude <=500 N m. Equal total torque is on by default so an A/B yaw comparison isolates left/right allocation more clearly; it is a **sum of torque requests**, not a guarantee of equal electrical power or equal tire force. `run_maneuver_pair` gives A and B identical initial state, front steer, duration, output times, synthetic car, and environment. Initial wheel speeds are `u0/R`.

The side panel exposes the car's mass, yaw inertia, geometry, wheel radius/inertia, tire `mu`, and two stiffnesses. Each entry is an explicit synthetic parameter. World X/Y wind, air density, drag area, base grip scale, and optional patch rectangle/grip scale appear in simple number boxes. A/B wheel torques appear in a four-row table. The plots show top-down paths, yaw-rate histories, four wheel-slip histories for the selected car, and a body-frame wheel diagram. The time slider changes only inspection. Numeric boxes show time, body forward/lateral speed, heading, yaw rate, yaw moment, peak tire use, instantaneous power residual, apparent airspeed, aero body X/Y forces, and whole-run road coverage. The coverage box says `ASSUMED` when no validity domain was supplied; otherwise it reflects the entire run, not only the cursor sample. The wheel diagram shows each tire's slip, local longitudinal/lateral force, normal load, and road grip multiplier. Dark mode reverses black/white surfaces; it never changes physics.

The path is a computed open-loop **maneuver trajectory**, not the 989 m Formula SAE course. The main app's top-down course is a reference map. Neither view uses 3D animation, elevation, or moving-camera effects. A/B final yaw differences are reported only for domain-valid runs and must be interpreted as sensitivity of this synthetic model, not a control-system lap-time gain. The selected scenario and time cursor choose an evaluation already generated from the frozen settings; editing a text box does not retroactively change a displayed run until `Compare A and B` is pressed.

## 13. Profile, source-data, and model audit trail

The profile selector's name is a label; the **effective constructed vehicle** is the physics input. `profiles/registry.py` identifies built-ins and optional locally reviewed TREV source bundles. `profiles/adapter.py` maps allowlisted source values into a fresh `Vehicle`, records inherited defaults and unused fields, and returns a `ResolvedManifest`. The local editable garage in `ui/garage.py` is a small seven-field Prius-equivalent convenience layer. It should not be mistaken for a full calibration manager. A software lead can trace a lap number by reading, in order, the selected profile and overrides, the resolved manifest, the run-level uniform grip setting, the actual effective vehicle snapshot, the resampled track grid, solver settings, controller fraction, result status, and telemetry channels in its saved record.

Data and code are separated deliberately. The shipped course CSV and its metadata are historical inputs; `docs/model_parameters.md` and validation notes describe where baseline values came from; the two ENME408 PDFs are research/design evidence; local Downloads source bundles remain optional and are never silently invented. A source value is only promoted when adapter logic accepts its field and units. A missing 2026-27 parameter remains an inherited assumption or an explicit unknown. The code does not infer a two-motor topology, battery thermal parameters, CFD coefficients, tire temperature law, track bank, or road friction from the research prose.

The important reproducibility distinction is **model input versus measured evidence**. A JSON record's hashed model configuration and track grid are enough to inspect what that software run attempted. They are not a signed calibration certificate, a raw log archive, or proof that the course and car matched an event. The detailed run-record schema and replay gaps are in Section 14.

## 14. Saved records: exact schema, integrity, and replay limits

### 14.1 Main-lap record (`experiments/run_record.py`)

For a v2 imported course, `settings.track.source_course.metadata_version=2`
and `boundary_status` identify the declared source-width revision. Its
`source_cell_corridor` summary stores status, source-geometry and corridor
hashes, width source name/hash, and `used_by_ai_planner=false` with the
frame-transformation reason. The full per-cell width arrays remain in the
validated local course bundle, while the lap record freezes source identity
and the actual solver grid. Review the corresponding bundle when a
width-by-cell audit is needed. A measured declaration and matching hash are
provenance, not proof of surveyed edge accuracy or AI path clearance.

`LapRunSettings.from_track` freezes the **resampled solver grid**, not just a filename: `closed`, all distance/X/Y/curvature values, and a SHA-256 of canonical JSON for that geometry. It also saves course ID, length, cell count, requested maximum step, path-constraint settings, constant driver torque fraction, base road-grip factor and source, one-lap event settings, and selected profile identifiers. An additive v2 `settings.conditions` variant stores an optional **absolute per-cell grip tuple** with `source=assumed_cellwise_surface_sensitivity`; uniform records keep their previous two-key conditions shape. The tuple has exactly the embedded grid's cell count, finite positive non-Boolean values, and no implicit multiplication by the base factor. This is an additive v2 contract: external readers that assumed every v2 condition was uniform must handle or explicitly reject the new source value. The course ID distinguishes ordinary fused-team runs (`team_endurance_fused_gnss_imu`) from the short synthetic demo (`synthetic_rounded_rectangle_v1`) and longer practice course (`synthetic_fsae_endurance_style_v1`) rather than silently treating them as the same input. `capture_lap_run` combines these settings with the source-aware profile manifest, editable overrides, full effective `Vehicle` constructor-field snapshot and its hash, result status/reason/time/pack energy/final SOC, and synchronized post-cell telemetry. Completed scheduled captures require one grip sample per cell matching the tuple exactly; failed runs check their accepted prefix. Each telemetry channel has values, unit when identified, origin category, sample count, and missing-sample status; a missing numeric sample is JSON `null`, not an undocumented zero. The record carries Python implementation/version, operating-system descriptors, and installed NumPy/SciPy/Matplotlib versions. `schema_version=2` embeds the grid; the loader accepts the older v1 format too.

Desktop records also freeze `settings.track.source_course`, independent of
`settings.track.geometry_sha256`. It records selected course ID and source
geometry hash for every ordinary, A/B, and AI trial. A versioned import adds
`revision`, `bundle_id`, canonical manifest `bundle_sha256`, declared raw
source hash, coordinate-frame declaration, boundary status, and the exact
loaded bundle-file hash. A local reserialization may change that last raw
file hash while preserving the canonical manifest hash. Built-in legacy and
synthetic courses instead record their respective source CSV/sidecar hashes
or generator revision and use `null` for bundle hash. These are frozen
provenance claims and integrity links, not proof of survey accuracy. The
source hash and solver-grid hash can legitimately differ after arc
subdivision or legacy resampling.

For an AI-mode desktop run, `settings.path_planning` records `algorithm=periodic_cubic_minimum_curvature_slsqp_v7_continuous_scalar_clearance`, `fourth_strength_policy=eligible_quadratic_or_certified_clearance_probe_v3_fallback_0.75`, `rank_status`, eligible versus diagnostic times, the modeled-path audits, and whether the primary record is diagnostic only. It also stores the source-course ID, label, description, and `synthetic_course` flag; source, processed-baseline, and selected-solver geometry audits; a SHA-256 of the **source** geometry; user-requested maximum cell length; nominal and actual planner spacing/sample count plus controls/smoothing/iteration cap/length penalty; the assumed corridor source and dimensions; each tested candidate strategy/nullable offset strength/path length/time/error; best candidate and selected strategy, with null offset strength for a grip detour; maximum offset and constraint violation; maximum normal-coordinate fold ratio; source closure/preparation discrepancy; and measured planner/lap-comparison compute time. The speed-only seam policy, 0.005 m/s tolerance, and two-pass limit per trial are explicit. The embedded `settings.track.geometry` is the **primary displayed solver path** and its hash, so a reviewer can inspect exactly what the saved lap used. The saved endurance settings contain the final pass's explicit starting speed; the `result` includes actual entry speed, exit speed, and finish-minus-start seam-speed difference. A default run has no `path_planning` field. Optional planning metadata is validated as canonical finite JSON at record construction, and the record's content ID covers it. The AI workflow saves the primary displayed run and every other completed trial, for at most four path records without a patch or five when one detour reaches the model. A candidate screened out before physics remains in the trial manifest with `record_role=no_run`, no run ID or modeled time, and its failed audit and skip reason. Each completed trial file contains its own exact solver geometry, full result, aligned telemetry, and explicit final-pass start speed. The primary file's `comparison_counterpart_run_id` and `comparison_counterpart_role` still identify the comparison counterpart when one exists. Its `record_role` is `selected_result` for the displayed result even when `diagnostic_only=true` and **no racing-line winner was selected**. That diagnostic flag also applies when a candidate completed but the eligible geometric baseline failed; showing that candidate is not an A/B time gain. Other linked files have `record_role=comparison_counterpart` or `candidate_trial`; their `comparison_role`, `strategy`, and nullable `offset_strength` identify the geometric baseline, offset trial, or grip detour. The primary file also has a compact `baseline_record` and `candidate_trials[]` manifest: saved trials have `run_id` links, while the path in the primary file has `record_role=selected_result` and no self-referential ID. Incomplete or geometry-screened extra trials keep their summaries without a replayable file. Read `settings.path_planning.candidate_trials[].strategy` and nullable `offset_strength` with each modeled-path audit and eligible or diagnostic time, plus `selected_strategy`, nullable `selected_offset_strength`, and `rank_status`. A `grip_detour` trial has null strength; the fourth offset's position does not imply strength 0.75 or a valid gain. The primary manifest links the available path records, but there is no interactive ghost/session workflow. Re-running the planner requires the source file identified by the hash, equivalent environment/code, and the original vehicle inputs. An individual completed record can be checked through the programmatic model replay in Section 14.2, but stored diagnostic times must not be ranked as racing-line gains.

For AI-generated geometry, `path_planning.user_requested_maximum_cell_length_m` records the editable bound and `path_planning.actual_maximum_cell_length_m` records the measured largest cell of the selected path. The older `path_planning.user_requested_centerline_step_m` key is retained for record compatibility and now has the same value even when AI mode is selected. The solver field `requested_maximum_cell_length_m` holds the same user request. `path_planning.planner_sample_spacing_m` records the nominal planning setting, while the actual sample count and spacing record any automatic grid increase. The exact embedded cell distances, not these scalars, are the authoritative solver input.

The effective vehicle snapshot includes the run-level grip factor. `effective_config_differs_from_base` reports a literal snapshot difference, so it is true when only grip changes; `profile_fields_differ_from_base` excludes that run condition and identifies an actual profile-field difference. The grip assumption remains explicit in `settings.conditions`.

The complete payload is serialized as stable, finite canonical JSON and SHA-256 is its content-derived `run_id`. `RunRecord.save` writes a temporary file and atomically replaces `%LOCALAPPDATA%\LapSim\runs\<run_id>.json`. `RunRecord.load` checks the ID and, for v2, validates embedded geometry, metadata, and geometry hash. Equal content under the same runtime/source identity gets the same name and overwrites that same content; the ID is not a per-attempt timestamp. A failed event result is saved when it reaches capture, but an exception before capture/save leaves no record. The GUI's A/B lap comparison creates two individual run files, not a third linked comparison manifest. Keep the two full IDs together when reviewing a comparison.

For a failed lap, the existing `result.driving_time_s`, `ending_speed_mps`, and `final_state_of_charge` remain the **attempted vehicle state** at termination. A path/time/stall rejection may happen after `Vehicle.update_state` has advanced a cell, while net energy, telemetry, and Driver progress contain only the checked prefix. New `accepted_time_s`, `accepted_distance_m`, `accepted_speed_mps`, and `accepted_state_of_charge` identify that prefix even when telemetry was disabled. `failed_lap_index` and `failed_cell_index` locate the failing cell with zero-based indices; `failed_cell_update_completed` says whether `Vehicle.update_state` returned successfully. A false value can mean an entry-gate rejection or an update exception that partially changed component state. All seven fields are optional additions to the existing v2 result; older manually constructed results and records may lack them. Capture validates a supplied prefix against the last saved telemetry sample and adds a warning when the attempted time is ahead of it. This is **transparent failure accounting**, not a rollback: the caller's vehicle can still contain the attempted component state. A zero-SOC endpoint passes the physical-cell checks, so it is included consistently in energy, telemetry, and progress before the run reports battery depletion.

The embedded grid makes the solver input auditable even if the checkout course file later changes. It does not embed raw GNSS/IMU logs, original fusion scripts, or a signed track survey. The manifest records Git commit and dirty-worktree flag; it does not store the uncommitted patch, so a dirty run cannot be exactly reproduced from the commit alone. Dependency versions are selected key packages, not a complete lockfile or BLAS build. The replay checker below restores only its allowlisted built-in model classes; the snapshot is not a universal constructor for external components. A content hash detects accidental mutation but does not authenticate who supplied the data or prove model agreement.

The AI trial manifest has `trial_record_manifest_version=1` within the existing v2 lap-record schema. Each linked `run_id` is a content hash, but loading the primary file does not load every linked file or make the group an atomic archive. Resolve each saved ID to its own JSON file and load it independently when auditing all paths.

An auxiliary AI path record identifies its own `eligible_lap_time_s`, `diagnostic_lap_time_s`, `trial_error`, modeled-path audit, and `diagnostic_only` status. Its `comparison_rank_status` is the **overall** four-path decision, or five-path decision when an assumed patch yields a detour trial, not that file's individual result. `comparable_with_baseline` is false when the geometric baseline lacks an eligible time, even if this individual candidate completed. The Driver view's best-path replay label includes the selected offset strength or grip-detour strategy; a baseline-failed candidate and every other ineligible path are labeled diagnostic. These fields prevent a standalone trial file or replay choice from being mistaken for a ranked winner.

### 14.2 Programmatic one-lap model replay (`experiments/lap_replay.py`)

`replay_lap_record(path, tolerances=LapReplayTolerances())` accepts one completed, one-lap **v2** JSON record with a complete accepted-cell trace, including any completed AI trial flagged diagnostic. `RunRecord.load` first checks its content ID and embedded track hash. The checker validates the effective vehicle snapshot hash, checks that its base tire grip matches `settings.conditions.road_grip_multiplier`, and reconstructs only known model dataclasses from an explicit class allowlist; it does not dynamically import class names from JSON. Older intact v2 records without `settings.conditions` or the new tire field replay at the original factor 1.0; their saved content hash is checked before this narrow compatibility default is applied. It restores the exact saved solver grid, path-constraint settings, optional absolute per-cell grip schedule, endurance settings (including an AI final pass's explicit start speed), and six per-cell controls: steering angle, front/rear brake pressure, motor torque request, and front/rear regenerative brake-force request. Scheduled records require a complete grip trace equal to the saved tuple. If a desktop AI record claims a world rectangle, replay independently remaps that rectangle with the frozen car and solver track and rejects a tuple that does not match. It requires one accepted sample per grid cell, ordered by increasing time and aligned with the saved cell and lap indices and station boundaries. It then resolves the path constraints and replays those controls through `EnduranceSimulator` in the installed code. This is a replay of the saved modeled lap, not a rerun of AI geometry optimization, continuous scalar corridor eligibility, or a driver's steering policy.

The `LapReplayReport` separately states `model_agreement`, completion, saved/replayed sample counts, named per-output maximum absolute errors and limits, `mismatch_reasons`, and `provenance_warnings`. It checks summary driving/lap time, start/end speed, net pack energy and final SOC; the aligned sample time, station, speed, and next path-speed ceiling traces; and exact agreement of the six recorded control traces and any available tire-grip trace. Default absolute limits are **0.01 s** for time, **0.01 m/s** for speed, **1e-5 kWh** for energy, **1e-5** for SOC, and **1e-8 m** for station; control and grip traces use zero tolerance. The limits can be supplied explicitly with `LapReplayTolerances`; they measure numerical agreement, not prediction accuracy. The checker does not compare every component telemetry channel. An incomplete/misaligned record, malformed explicit grip conditions, unsupported model snapshot, missing explicit AI start speed, or v1 schema is rejected; a modeled rerun that stops or disagrees returns a structured failed report. It compares saved/current source commit, dirty flags, Python/platform, and selected dependency versions as provenance warnings independently of numerical agreement. Exact agreement on a dirty checkout is still numerically possible, while a clean but different code version can disagree. This operation requires a Python environment with the model and may take a full lap solve; the desktop has no replay-check button.

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

The file hash checks that the loaded JSON has not changed since it was named; it is **not** this replay check. A successful command replay confirms selected numerical outputs of the saved **model** run and reruns the event's requested/achieved curvature gate. It does not prove that the integrated vehicle x/y followed the separately plotted course or stayed within surveyed boundaries. Neither this API nor the Driver view's visual telemetry playback proves agreement with an instrumented vehicle or implements the full Timed sessions workflow.

### 14.3 Four-wheel A/B record (`experiments/dynamics_record.py`)

`capture_dynamics_comparison` takes the exact `PlanarVehicleConfig`, `PlanarEnvironment` (including wind, density, CdA, base road, domain, and ordered patches), initial state, every A/B control step, output step, and both `PlanarRun` objects. It checks both runs share the initial state/time grid, that equal-total torque holds at each step if requested, and then **replays both runs** under those frozen inputs before accepting their trajectories or RK-stage road status. The record stores **every** boundary time/state, every pre-step wheel/force/energy evaluation, per-sample body longitudinal/lateral force residuals, yaw-moment residuals, power residuals and their maxima, road-validity flags and invalid-query counts. It identifies the FL/FR/RL/RR wheel order, Python/platform/dependency versions, source commit/dirty flag, and synthetic evidence status. `DynamicsComparisonRecord.load` checks its content ID, alignment/time grid, torque condition, equation residual summaries, and deterministic replay against the saved input. Both A and B are in one linked file at `%LOCALAPPDATA%\LapSim\dynamics_runs\<run_id>.json`. The UI saves it before displaying a completed comparison and shows the shortened ID.

The lab record supports inspection and programmatic replay from exact inputs, but there is no one-click replay button yet. Its power/force residuals are evaluated from the saved numerical derivatives and forces; they do not compare a simulated maneuver with instrumented car measurements. The road-valid flag reports that the **solver found** every queried contact inside the declared domain; capture and load rerun the integrator to check this, including RK4 stages. The file still stores only their aggregate invalid-query count, not every intermediate contact coordinate. If no domain exists, coverage is an unbounded synthetic assumption, which the GUI calls `ASSUMED`; it is not a claim of road survey coverage. A/B record capture identifies a dirty worktree but does not archive the uncommitted source patch. Because load uses the installed model code for replay, a future change to physics or integration may reject a historically valid record until an explicit schema/model-version migration or archived-code replay is provided.

### 14.4 Synthetic pose trace record (`experiments/pose_run_record.py`)

`PoseRunRecord` is a **separate schema-v2** archive for one short synthetic
time-domain pose experiment; it is not a v2 endurance-lap record. The WIP
tab's **Save last synthetic trace…** invokes `PoseRunRecord.capture(run)`
then an atomic JSON `save(path)` in a worker. **Load synthetic trace…**
invokes `PoseRunRecord.load(path)` in a worker and displays the checked
result in Driver view. These controls do not enable **Start timed session**
or create a ghost or comparison report.

New files store `schema_version=2`, `record_type=synthetic_pose_driver`,
`simulation_mode=time_domain_four_wheel`, and the versioned pure-pursuit/
grip/edge controller identity. `inputs` contains the **exact processed
track** (stations, x/y, curvature, closure), `PlanarVehicleConfig`,
`PlanarEnvironment` (wind, road, ordered patches and optional domain), and
all `PoseDriverSettings`, including the explicit reference-geometry mode,
initial lateral offset, and compute bounds. Schema-v1 arc-only records
remain loadable with their original controller identity and an implied
`coherent_arcs` mode. `trace` contains every output time, planar boundary state, held
control, pre-step `PlanarEvaluation`, derived `PoseDriverSample`, final
status, internal-substep count, and road-valid flag. `runtime` identifies
Python/platform, NumPy/SciPy versions, Git commit and dirty state when
available, and SHA-256 fingerprints of the five source modules used by
this model/record. `validity` expressly labels the run as a synthetic model
estimate with unestablished vehicle validation and user-defined flat road.

`content_id` hashes the canonical payload, excluding the ID itself; it is
an integrity identifier, **not** a signature or independent evidence of
physical correctness. The loader rejects duplicate JSON keys, nonfinite
JSON constants, unknown/missing schema fields, unsupported controller IDs,
misaligned trace arrays, a file over **32 MiB**, more than **100,000** track
cells, more than **128** road patches, and geometry that fails the saved
mode's arc or sampled-polyline gate. It
reconstructs the initial pose from the saved track and offset setting,
checks times/step budgets and every saved pre-step dynamics evaluation
against the current equations. Finite evaluation floats use
`abs(saved-recomputed) <= max(1e-9, 1e-10 max(abs(saved),abs(recomputed)))`;
the parser still requires **exact field names, array lengths, material
IDs, booleans, integers, and nullable values**. The loaded typed run holds
recomputed evaluations when harmless float drift is accepted, while the
JSON payload retains its saved values. The loader then reintegrates each
held control with `replay_pose_driver` under the separate state/path
tolerances in Section 10.2. That report checks whether saved inputs reproduce
saved states and diagnostics; it does not by itself show that the declared
controller would have chosen those inputs. For schema v2, capture and load
also recompute every controller decision from the saved pre-step pose, prior
path projection, footprint slack, settings, and road. Steering and wheel
torques must agree within **1e-9 rad** and **1e-7 N·m**, respectively;
auxiliary control fields agree exactly. `controller_report` exposes pass/fail,
checked-control count, maximum errors, and first mismatch step. A changed
cruise target that leaves recorded-control dynamics replay intact now fails
this controller gate. Schema-v1 records retain only their original dynamics
replay and expose `controller_report=None`, rather than claiming retrospective
controller agreement. A zero-control
initial road-domain/corridor stop can be saved and loaded when its saved
status and sample agree; its controller check covers zero decisions and it
must not be shown as driven motion. Capture
performs the same numerical check before writing. Source fingerprints are
retained for review rather than required to match the installed files;
historical records can fail numerical replay after model changes until a
version-aware migration or archived-code replay exists.

```python
from lapsim.experiments.pose_run_record import PoseRunRecord

record = PoseRunRecord.capture(run)
path = record.save("synthetic_pose_trace.json")
checked = PoseRunRecord.load(path)
print(checked.content_id, checked.replay_report.passed,
      checked.controller_report.passed if checked.controller_report else None)
```

### 14.5 Practical record inspection

The desktop's **Saved run details** button opens a read-only text viewer for
the currently displayed lap or A/B comparison. It loads each named run by
its full content ID and file path, reports the profile, result status, source
course and boundary status, solver path and cell count, and AI assumption and
rank status where present. The AI rank is explicitly labeled as the saved
**original-grid** decision. An optional finer-grid finding can qualify the
current desktop view, but it is not stored in that immutable lap record and
will not reappear merely by reopening the JSON after a restart. For a primary
AI result it follows available baseline and candidate trial IDs, showing a
load error if a linked file is
missing or invalid. The viewer does not rerun physics, certify boundaries,
or turn a diagnostic trial into a ranked path. The separate WIP pose Save/Load
controls use Section 14.4's synthetic pose schema, not this v2 lap-record
viewer, and supply no complete session archive.

Read the JSON in this order: `schema_version` and `simulation_mode`; `runtime` and source identity; `configuration`/`inputs`; `settings` and solver grid or time step; `result`/`runs`; `validity`; then telemetry/evaluations. A run is usable for a model comparison only if its event succeeded, its selected inputs match the intended comparison, its declared validity checks pass, and its assumed parameters are appropriate for the engineering question. Never rank a failed lap or a road-out-of-domain maneuver by its partial elapsed time or final yaw alone. Preserve the full JSON alongside any plot shared with the team.

## 15. How Python modules and the desktop interact

| Responsibility | Main source | Contract / important side effect |
|---|---|---|
| Desktop entry and main widgets | `src/lapsim/ui/__main__.py`, `ui/app.py` | Tk event loop; validates form inputs; dispatches worker; renders results on GUI thread |
| Four-wheel widgets | `ui/dynamics_lab.py` | Freezes `ManeuverSettings`, runs matched A/B in worker, saves one record, draws top-down/force views |
| Shipped course and gridding | `ui/simulation.py`, `courses/spatial_track.py` | Reads source CSV and creates path cells; on-demand `SpatialTrack.refine` preserves existing cell boundaries for resolution checks |
| Optional path proposal and A/B timing | `optimization/racing_line.py`, `optimization/grip_detour.py`, `optimization/road_grip_schedule.py` | Builds processed geometric baseline and bounded full/half/fourth-offset candidates; optional one-patch mode screens at most 12 local detour geometries and can add one fifth full-model trial. Each path's nominal wheel contacts get their own scalar grip schedule. Integrated curvature paths need continuous scalar normal-coordinate clearance and position closure before ranking. At most eight lap-model passes without a patch or ten with one patch in the desktop speed-seam policy |
| Optional fixed-path resolution diagnostic | `optimization/grid_stability.py`, `ui/app.py` | On request, reruns the eligible selected-candidate/baseline pair on one finer grid with the frozen car and no path reselection; patch mode remaps the same world rectangle on each refined path with its original modeled entry heading. Caps each path at 5,000 cells and reports pairwise sign/threshold sensitivity; runner-up ordering, convergence, and road validity remain unchecked |
| Car selection and local saved profiles | `profiles/registry.py`, `profiles/adapter.py`, `ui/garage.py` | Constructs fresh `Vehicle` and provenance; seven editable garage fields |
| Spatial speed constraints | `solvers/path_constraints.py` | Computes local tire-limited and cyclic braking entry ceilings; optional absolute per-cell grip tuple and within-phase progress snapshots |
| One-lap event | `events/endurance.py` | Starts a rolling initial-condition lap, applies driver/automatic brake actions, calls cell update, records accepted telemetry and seam speeds; uses any saved constraint's per-cell grip schedule and restores configured grip afterward |
| Main vehicle assembly | `vehicle_model/vehicle.py` | Couples aero, suspension, tire, drivetrain, brake, battery and commits state after solving a cell |
| Four-wheel derivative and integrator | `dynamics/planar.py` | Pure force/derivative evaluation; bounded RK4 time integration; no lap score |
| Wind/road scenario | `dynamics/conditions.py` | Deterministic world wind and world-fixed contact-patch query; no update side effect |
| WIP pose driver and playback | `optimization/pose_driver.py`, `ui/pose_driver_playback.py`, `ui/app.py` | Validates/refines coherent long arcs by default; opt-in sampled-polyline mode accepts checked AI x/y references. Both project overlapping station cells/lap copies, run a bounded synthetic four-wheel control loop, and stream simulated pose to Driver view without changing a main-lap record |
| Synthetic pose evidence | `experiments/pose_run_record.py` | Saves/loads a separate schema-v2 exact synthetic trace with geometry mode, source identity, content hash, evaluations, numerical recorded-control replay, and declared-controller agreement; zero-step stops carry no controller decision, and v1 arc traces retain dynamics-only replay |
| Main-lap evidence | `experiments/run_record.py` | Content-hashed v2 record with exact solver grid and effective vehicle snapshot |
| One-lap model replay | `experiments/lap_replay.py` | Reconstructs an allowlisted vehicle and saved grid; reruns accepted-cell controls and reports numeric differences separately from provenance |
| Driver view and progress | `events/endurance.py`, `ui/driver_view.py`, `ui/app.py` | Emits immutable accepted-cell snapshots; maps live endpoints and completed telemetry to each run's saved solver-grid reference x/y; switches among already solved comparison laps without changing physics |
| Four-wheel evidence | `experiments/dynamics_record.py` | Linked A/B content-hashed input/trajectory/force record |

An implementation change should begin with the **contract** between these modules. For example, adding measured wind to the lap solver is more than another GUI box: the track needs an orientation/world frame, the path solver must use air-relative forces at its speed-ceiling probes, `Vehicle.update_state` must use the same force without double counting, the record must store the wind field and its frame, and analytical baseline/headwind/crosswind checks must pass. Likewise, adding dynamic ride height requires new continuous states/contact geometry in the time-domain model or a defined equilibrium map in the distance-domain one; a plotted height slider alone would have no physical effect.

### 15.1 What to change for a new car profile

Create a reviewed parameter table with unit, source, date, vehicle configuration, operating range, and uncertainty. Add an allowlisted adapter mapping, then inspect the resolved manifest and effective `Vehicle` snapshot. Confirm motor count/topology, wheel radii, torque/RPM/power envelope, cell/pack limit behavior, mass/CG/inertia, aero convention, tire load/slip data, braking/regen boundaries, and track condition separately. Do not fill missing fields with a plausible number without labeling it an assumption. The garage's seven boxes are useful for an initial sensitivity run, not enough to assert a 2026-27 calibration. Re-run the baseline unit/equation checks and held-out data comparison after any physical parameter update.

### 15.2 What to change for a new track

Supply a source-controlled or recorded course with monotone distance, x/y, signed curvature, closure decision, units, and derivation metadata. `resample_track` can create solver cells, but a new course should be checked for geometric closure, map/curvature agreement, and cone/path width. A legitimate Report II road extension additionally needs elevation, grade, bank, crest curvature, surface material/condition, and validity coverage referenced to a shared world frame. Compute gravity along and normal to the road consistently: grade changes required climbing work and normal force; bank changes lateral tire demand; a crest can unload contact. Those are **not** currently in the lap model. A local wetness or grip multiplier without a surface measurement should stay a sensitivity scenario.

For the current desktop import path, derive a coherent closed constant-curvature
solver course first, export the four-column `SpatialTrack` CSV, and run
`scripts/create_course_bundle.py` with source, frame, revision, processing,
and review declarations. The converter and importer enforce internal geometry,
hash, size, and signed-turn gates; they do not fit raw measurements or accept
measured boundary widths. Select its JSON through **Import course…**. Keep the
source CSV and preparation method with the generated bundle and run record.
Changing any manifest content requires a new revision, and a complete
source/solver geometry plus measured-boundary review is still needed before
interpreting path clearance physically. See `docs/course_bundle_format.md`.

### 15.3 Numerical and code-review guardrails

Keep derivative evaluations pure during RK4 and commit thermal, charge, wear, or weather-state evolution only after an accepted step. Keep one definition for each force and sign; aero loads must enter both force balance and power/accounting exactly once. Define whether a coefficient maps body velocity, air-relative velocity, or wheel-contact velocity. If adding pitch/yaw aero moments, verify moment reference points and equilibrium; if adding rotating states, remove any equivalent-mass term representing the same inertia. Preserve dimensional units at API boundaries. Version every new record field/schema and add a migration or explicit rejection path. The deterministic baseline and limiting-case checks in Section 16 are the minimum regression gate.

## 16. Checks performed, interpretation, and known discrepancies

### 16.1 Current release-review evidence - 9 October 2026

The current source runtime self-test passed all ten checks, including the full desktop
and TkAgg canvas, separate four-wheel lab, shipped 1,978-cell course/provenance,
offline map and durable cached source/document links, synthetic lap,
saved record round trip, and recorded-control
numerical replay. Focused
packaging/source-profile/record regressions passed **28 tests**. The physics
audit passed **101 core tests with 355 subtests**, plus **56 event/dynamics/
path-constraint tests with 610 subtests**. A separate **255-case** operating-point
sweep covered front/rear/all drive, speeds 0-40 m/s, signed curvature, and
drive/coast/friction-brake/regen requests; maximum longitudinal force-balance
residual was **4.55e-13 N** and maximum pack `P - V I` residual **1.46e-11 W**.
Telemetry was finite, normal loads nonnegative, and no accepted tire force
exceeded combined capacity.

The current frozen executable also passed all ten runtime checks from an
unrelated temporary directory with Python/Git absent from `PATH`, isolated
user data, and no optional source evidence. Its 32-cell synthetic circle lap
completed in **8.1284262182 s** and its record replay agreed. The consolidated
**64-module** suite records **749 test functions and 1,010 subtests**, or
**1,759 JUnit cases**, with no unresolved failure or skip after affected GUI
reruns. The initial sweep had two intermittent Tcl startup skips. The
saved-run module then passed 7/7; the course module retry passed four cases but
hit a Tcl reinitialization failure in its restart case, which passed 1/1 in a
fresh process. The full course module subsequently passed 5/5 using pytest
`--capture=sys`; the release checker preserves process file descriptors while
capturing Python stdout/stderr to avoid stale Tcl file channels. The original
and rerun logs remain part of the evidence; the initial sweep was not an
unskipped pass. A first combined run with **730
passed, 1 skipped, and 674 subtests** is a secondary baseline. Use the packaged
`work/test-results.xml` and `work/test-suite.log` for release totals and its
frozen self-test JSON for the executable result. The locked Windows x64 build
was tested with Python **3.12.2**.

The audit corrected a zero-power/depleted-pack stall-torque loophole and made
the older lap solver reject an untraversable stopped cell. Battery configuration
and update inputs now reject NaN/infinity and non-integer pack cell counts.
Desktop startup drains pending layout/theme idle work; destruction cancels
all queued Tcl callbacks, including TkAgg. Lifecycle/saved-run regressions
passed 8/8 without native Tcl stderr after that fix. These checks establish
implemented behavior, not vehicle calibration. See [verification](verification.md)
and [release instructions](release.md).

### 16.2 Historical source checks and numerical investigations

The dated checks and scenario values below preserve earlier investigations.
They are not freshly measured release benchmarks or proof that the final EXE
passed. Their configurations and stated policy changes govern interpretation.

Coarse prescribed-path skidpad regressions require a radius-5 m circle split into one or four cells to reject acceleration beyond its modeled corner limit, while an ordinary within-limit skidpad still scores. A newer circle regression checks the combined longitudinal/lateral force margin at every accepted exit on both 4-cell and 64-cell grids; an explicit 50 N·m request that passes the pure lateral speed ceiling but lacks about 102 N of exit grip must fail. The legacy unconstrained nominal-2 m AI API regression requires a 0.95-strength continuous scalar-audit pass and a completed **14.617662 s** Prius trial under the current exit-grip physics; new maximum-cell tests check a distinct finer-grid desktop scenario. An earlier fixed-path 1 m probe retained roughly 0.449 s over the old 0.75 fallback under the prior cell-force policy. The Windows preflight also draws a TkAgg canvas and checks the shipped course before launch. On a separate synthetic radius-25 m circle with the repository-baseline car and torque request 0.8, an **earlier pre-exit-grip** sensitivity run changed assumed uniform road grip from 100% to 70%, reduced the path-entry ceiling from **19.827545 to 16.555945 m/s**, and increased the completed lap from **8.073551 to 9.637759 s**. Those lap times are historical; the prepass and lap both respond to the same grip factor, but this is not a calibrated wet-track prediction.

On 6 October 2026, the checked-in `scripts/check_all.ps1` completed all **60 repository test files** in isolated one-module pytest processes with no failures. One pose GUI case was skipped during that sweep when Windows intermittently failed to read an existing Tcl/Tk support file; that exact case then passed in a fresh process (**1/1**). The full desktop AI module passed **18/18**, and the desktop startup check passed. Splitting the files avoided this workstation's Windows commit-memory limit; each process used one OpenBLAS, OMP, and MKL thread and explicit Tcl/Tk library paths. The Driver view checks compare every live accepted-cell value with same-cell telemetry, verify replay's active-cell boundary timing and independent missing-channel handling, and confirm the desktop numbers and unit conversions. New desktop tests also start a new run with an old Analysis trace visible, then fail the new calculation and verify the old plot and result references remain cleared. Failed-run checks cover rejection before a cell update, rejection after the first and a later attempted update, last accepted telemetry alignment, complete-run equality, record serialization and contradictions, and consistent battery-depletion progress. A/B tests use cars with markedly different independent first-cell ceilings, require one common start and one preparation per car, replay both saved records, inspect live/replay/popup behavior, and reject a different vehicle or track when reusing limits. The new cyclic-braking regression reproduces a four-cell closing-straight case: with a loose tolerance, the prior one-pass 43.112 m/s closing-cell ceiling exceeded its 23.254 m/s braking-feasible entry; the corrected solver continues its sweep or raises at the pass bound. It also rejects nonfinite tolerance settings. At the declared minimum **1080 × 720** window, the decision grid requests **620 px** inside a **660 px** panel and the course canvas remains **264 px** high. Course checks include exact catalog-source identity for both synthetic IDs, analytic per-cell endpoint and closed-heading validation, original-station-preserving subarcs, and a valid coarse two-semicircle loop whose polygon chord winding aliases the true turn. They also cover bounded versioned JSON and CSV loading, duplicate/nonfinite/malformed input rejection, source and manifest hashes, local catalog reload and revision conflicts, imported centerline and AI runs, linked trial records, and model replay of those records. These are numerical and software checks, not a track survey or measured-boundary validation.

A later 6 October sweep after the pose-grid, selected-path, and WIP scrolling changes again completed all **60 test files** without failures. The focused pose UI module passed **36/36**, and `scripts/check_desktop.py` passed its Python, TkAgg, app-import, and default-course preflight. These runs verify reproducibility under the checked-in model and this workstation; they do not calibrate its physical predictions.

After the optional finer-grid desktop action and schema-v2 controller gate,
another 6 October run of `scripts/check_all.ps1` completed all **60 test
files** without failures. The AI desktop module passed **24/24**, including
one real synthetic Prius Tk-to-worker finer-grid run and a pending-input
invalidation race check. Focused pose checks passed **37/37** UI cases,
**9/9** record cases, and **46/46** driver cases in fresh processes. The
desktop startup preflight passed. A combined pose UI/record invocation had
one intermittent Windows Tk skip; the affected UI module passed in the
fresh run just noted. These tests check implementation and replay behavior,
not track survey, tire calibration, or real-car lap accuracy.

After patch-mode finer-grid remapping and the pose road-domain display warning,
`scripts/check_all.ps1` again passed all **60 test files** in isolated
processes on 6 October 2026. The AI desktop module passed **25/25**, including
an unmocked synthetic Prius patch run followed by the optional refined-grid
worker; the paired-grid module passed **12/12**, and the pose UI module passed
**39/39**. `scripts/check_desktop.py` passed its startup preflight. Focused
checks additionally cover a narrow world rectangle at a refined-cell boundary,
the original modeled entry heading, road-mapping failure before physics, a
frozen patch passed to the desktop worker, and both driven and zero-step
invalid-road pose traces. These checks establish deterministic behavior of
the current software model; they do not calibrate the car, surface, or course.

Additional focused regression cases now cover a completed grid-check sign
reversal, a margin-only crossing, stable and stale reports, unchanged original
path/numbers/records, a terminal grip sample after a patch crossing with the
last control held, and rejected overlapping or edge-touching programmatic
patches alongside disjoint-patch mapping. The dated full-suite counts above
predate these cases. A fresh 6 October 2026 `scripts/check_all.ps1` sweep then
passed all **60 test files**. The AI desktop module passed **31/31**, the pose
driver **47/47**, pose UI **39/39**, road mapper **19/19**, and lap replay
**47/47**; `scripts/check_desktop.py` passed. These cases check display,
archive, and mapping consistency, not numerical convergence or measured grip.

A subsequent 6 October 2026 sweep again passed all **60 test files** after
making the optional grid check's callable default match the one-pass
comparison policy, extending its sensitivity warning to already-open
comparison/evidence windows and AI replay context, and correcting pose
tracking displays when projection is lost. The AI desktop module passed
**34/34**, paired-grid checks **14/14**, and pose-driver checks **47/47**;
`scripts/check_desktop.py` passed. Focused UI regressions confirm that
same-input failed or non-completed grid retries preserve a previous warning,
a completed stable check removes it, and stale inputs clear the current view
while an older popup retains its warning next to frozen numbers. These checks
establish policy dispatch and display behavior, not full numerical
convergence, physical tracking, or a validated competition racing line.

After retaining warnings in older popups, a second isolated sweep finished
all **60 test files** without failures; desktop startup passed. Two Tk tests
skipped on intermittent Windows `init.tcl` read errors: an AI patch-worker
case and a progress UI case. Fresh isolated reruns passed the skipped AI
test **1/1** and the full progress UI module **5/5**. In that sweep, AI desktop
was **33 passed, 1 skipped**, paired-grid **14/14**, and pose-driver **47/47**.
These checks do not establish real-car accuracy.

The next 6 October 2026 isolated sweep passed all **61 test files** with no
failures or skips after qualifying the pairwise grid result, gating the WIP
selected-path pose preview on an unresolved grid finding, and correcting
projection-loss summaries. AI desktop passed **35/35**, pose-preview UI
**40/40**, the new pose-status UI **3/3**, paired-grid **14/14**, and
pose-driver **47/47**; desktop startup preflight passed. In the synthetic
projection-loss reproduction, the final pose moved about **0.226 m** in X
while its last confirmed path station stayed at **0.0 m** and the footprint
slack sentinel was negative infinity. The UI now labels that station as
last confirmed and the slack as unavailable. This verifies reporting and
software consistency, not pose tracking on a measured course.

On 7 October 2026, another isolated `scripts/check_all.ps1` sweep completed
all **61 test files** without failures after exposing path-specific rolling
start and finish speeds in the AI comparison and correcting the synthetic
Driver view's held pre-step lateral-acceleration display. One unrelated AI
Tk case skipped during that sweep when Windows intermittently could not read
an existing `init.tcl`; its exact case passed **1/1** in a fresh process, and
the entire AI desktop module had separately passed **36/36**. The pose-driver
module passed **48/48**, and `scripts/check_desktop.py` passed its startup
preflight. The new UI regressions check separately solved baseline/candidate
start speeds and interval-boundary lateral values. These are display and
software checks; they do not change or validate the physical vehicle model.

A later 7 October 2026 sweep passed all **61 test files** after correcting
three reporting issues: the synthetic Driver view now masks its STATION box
when local projection is lost, saved AI evidence labels its rank as an
original-grid decision and discloses that optional finer-grid findings are
not in the run record, and displayed peak speed includes the rolling start
as well as accepted-cell exits. The first sweep exposed three outdated AI
desktop assertions expecting the former evidence label; after updating that
test expectation, the full sweep had no failures. One AI Tk case skipped
intermittently on an `init.tcl` read error and its entire three-case
parameterization passed **3/3** in a fresh process. Focused checks passed
**52/52** across pose driver/status, **7/7** saved-evidence UI, and **3/3**
profile/summary cases; `scripts/check_desktop.py` passed. In the synthetic
projection-loss reproduction, the pose advanced about **0.226 m** while
the retained station stayed at **0.0 m**; the STATION box now displays an
unavailable dash during the failed interval and at the terminal sample.
These are reporting and model-summary checks, not physical validation.

The cell-length regressions verify that the planner bounds generated baseline and candidate physics cells, tries the allowed 5,000-point grid before rejecting a tight request, and handles a one-ulp final-station discrepancy on the FSAE-style practice course without relaxing its clearance checks. A desktop regression changes the visible cell-size entry from 2 m to 1 m and confirms that the actual model grid and requested maximum passed to record capture change. The WIP pose UI checks its finer/coarser effective grid, 5,000-cell rejection, selected-path eligibility gate, frozen worker path, live pose-model labels, saved-record mode, and scrolling access to status at the 1080 × 720 window minimum. Desktop progress regressions verify current-pass accepted-cell fractions, explicit speed-seam probe and final-lap transitions without a fabricated percentage, indeterminate preparation and gap states, completion/failure reset, dark-mode contrast, and cancellation of pending animation callbacks at window close. Detour regressions check bounded construction, lower wheel-contact exposure, corridor refusal, full-model selection, slower-detour rejection, exact saved strategy, and replay agreement.

Further focused tests exercise the **absolute per-cell grip** tuple:
shape/finite-value rejection, cell-specific corner and cyclic braking
limits, lower-grip upstream response, reuse with matching prepared limits,
conflicting-schedule rejection, telemetry per cell, unchanged uniform
baseline, and restoration of the vehicle's configured grip after success,
failed events, and exceptions. Constraint-progress checks cover the
local-limit completed-cell counts, cyclic pass numbers/cells without an
invented convergence percentage, and forwarding through the desktop's
lap/AI paths. The world-road mapper tests include a narrow rectangle between
cell samples, both sides of a closed seam, a front wheel entering before the
CG, path-specific translated geometry, coherent versus plotted-arc position,
unsupported road settings, and a near-5,000-cell compute case. Desktop
integration tests save and replay each scheduled AI trial; replay tests reject
a rehashed rectangle that no longer regenerates the tuple and a rehashed
uniform claim contradicted by recorded tire grip. The optional paired-grid
diagnostic has focused pass/failure, sign, margin, cap, and subdivision
checks. These are software checks of assumed scalar tire capacity, not
evidence for a measured wet patch.

The pose projection checks use long coherent cells overlapping a narrow
station window, clipping at the requested window, both closed-lap copies
of a major arc, analytic refinement of coarse arcs to at most 0.5 m,
retained source stations, default fine-grid identity, the 100,000-cell
cap, and recorded-control replay after refinement. Pose-record checks
round-trip exact uniform and assumed-patch inputs, evaluations, and
playback; accept a zero-step invalid-road stop; reject changed hashes,
rehashed but numerically inconsistent states/controls/evaluations,
unsupported schema, malformed alignment, duplicate/nonfinite JSON, and
oversized files. A bounded float perturbation in a saved evaluation passes
the explicit `1e-9` absolute/`1e-10` relative check; a larger perturbation
or changed road-material ID fails. Desktop Save/Load checks use the frozen
run and verify load before playback. A dedicated zero-step UI check confirms
that a loaded stopped trace has no playback motion and clears stale lap
numbers instead of inventing a driven step.
These establish archive integrity and current-model numerical reproduction,
not physical model validity or a complete session.

The v2 bundle and converter checks cover source-cell width lengths, station
alignment, narrow positive widths independent of car size, declared provenance,
both canonical and raw-file hashes, malformed or duplicate CSV rows, and
round-trip import. The pose-driver checks cover an 80 m synthetic bend,
low-grip command response from the same initial pose, braking before first
contact with the assumed patch, bounded preview under extreme finite
lookahead settings, zero-length-chord rejection, local-projection agreement
around the closed seam, finite work and road limits, projection failure
alignment, recorded-control numerical replay,
tampered pose samples and stop status, and driver-view use of the actual
simulated pose and control boxes. WIP tab tests check default/selected road
conditions, disabled scenario changes while running, a frozen worker
scenario, and clearing only pose replay on a later selector change. Saved-run UI
checks show full content IDs and paths for one lap, AI-linked trials, and A/B
records, then clear stale evidence after input changes. These do not establish
measured course width, driver quality, or real-car agreement.

New focused pose checks place the synthetic car at both **+1.5 m** and
**−1.5 m** along the start path's left normal and check the first control's
braking request, step bound, and in-memory replay. Full **±1.8 m** starts on
both uniform and assumed-patch roads reach the 80 m target with positive
sampled slack and replay agreement. Separate fixed-state checks require an
outward lateral velocity to request more braking than an inward one near
either side of the assumed corridor, and require the future patch to lower
the target at the same current pose. Invalid nonfinite/out-of-range inputs
are rejected. UI checks verify that offset and scenario are frozen while the
worker runs and that changing either while idle clears only pose playback.
An accepted nominal **−1.9 m** input on the curved start produces negative
four-corner slack and zero controls, demonstrating why input range and
actual footprint validity are separate. In an exploratory comparison with
the edge cap bypassed, the same ±1.8 m starts also finished with the same
minimum sampled slack at time zero; the new cap slowed those model runs by
about half a second. This confirms a conservative braking response in these
cases, not improved clearance or prevention of an exit.

One harder, deliberately configured regression tests the edge rule at a
**+1.8 m** start with `lookahead_seconds=3.0` instead of the default 0.45.
The experiment extends the finite budget to **25 s**, **500** controls, and
**80,000** integration substeps. With the nominal edge rule, it reached
**80.19 m** in **20.20 s** of pose-model time and retained **+0.04884 m**
minimum sampled assumed slack. With the rule made effectively inactive by
setting its slack threshold and outward-prediction time to `1e-6` each, it
stopped outside the assumed corridor at **40.64 m** with **−0.01351 m**
minimum sampled slack. Both recorded traces passed numerical replay. This
shows one reproducible controller tradeoff on an analytic road; it does not
prove the rule prevents exits on other tracks, offsets, grips, or lookaheads.

The new opt-in sampled-polyline checks retain strict arc-mode rejection of
an AI polygon unless its geometry mode is explicitly changed. They reject
open endpoints, zero chords, mismatched stations, and local reversals; a
driven polygon trace passes state/sample replay and the schema-v2 record
round trip, while a changed geometry-mode field fails loading. A constructed
schema-v1 coherent-arc record still loads with numerical replay. In one
on-demand synthetic demo probe, the planner produced a **206-cell** sampled
candidate at a requested **1 m** maximum. The separate pose controller
reached **80.1475 m** in **14.75 s** of pose-model time with **295** control
steps and **38,055** internal substeps. Wall time was **3.744 s** on this
computer; maximum absolute reference tracking error was **0.17404 m** and
minimum *assumed sampled* footprint slack was **1.70328 m**. Numerical
replay and a saved schema-v2 round trip passed. These numbers describe a
synthetic car following a planner-produced polygon; they are not an
eligible engineering lap-time comparison or measured boundary clearance.
In an unmocked desktop-to-worker exercise, the synthetic demo Prius AI
comparison selected a **206-cell** candidate after its processed geometric
baseline and candidate modeled **17.009011 s** and **14.637831 s**,
respectively. The WIP button froze that selected polygon as **412** pose
cells; the synthetic car reached **80.147 m** in **14.75 s** of pose-model
time, and its recorded controls passed numerical replay and schema-v2
capture/load. The two AI values are full prescribed-path model laps; the
14.75 s value is a separate 80 m driven pose duration, so subtracting them
would be meaningless. The test establishes UI wiring and replay, not a
validated Racing Terps path or car.
The first polygon-corner speed proxy divided heading turn by the adjacent
**solver** cell lengths; splitting an identical sampled polygon from 0.5 m
to 0.25 m doubled its peak estimated bend from about **0.142** to
**0.284 1/m** and changed the 80 m pose duration from **14.75** to
**16.70 s**. That was a numerical grid artifact, not a changed driving
line. The fixed **0.5 m physical preview span** described above removes
that specific artifact: for the same polygon, its active 8 m/s bend-speed
target differed by at most **1.2e-12 m/s** across those subdivisions, and
both 80 m runs ended on the same **14.75 s** control step. This is a focused
resolution check on fixed x/y geometry, not a formal convergence study of
the four-wheel integrator or the main lap solver.
An exploratory full coherent-course pose run reached one **195.4 m** lap
after **35.85 s** of model time, using **92,493** of the allowed **100,000**
substeps, and also replayed. Its small remaining compute headroom supports
retaining the 80 m WIP preview as the desktop default rather than promising
an arbitrary full-session finish.

The stronger schema-v2 pose-record check was exercised on an ordinary
**295-control**, **14.75 s** model-time, 80 m trace: recorded-control dynamics
replay and declared-controller agreement both passed for all controls.
Changing only the recorded cruise-speed setting to **2 m/s** left dynamics
replay passing, since the same saved commands still produce the saved states,
but made the reconstructed first controller command disagree (at least
**40 N·m** drive and **80 N·m** brake difference). Schema-v2 capture and
load now reject that contradiction. A constructed v1 record with the same
changed setting still loads with `controller_report=None`, explicitly
retaining its older dynamics-only meaning. The controller check adds work
only to explicit pose-trace save/load; on one local default 80 m trace,
driving took about **4.18 s** wall time and checked capture took about
**6.57 s** wall time. These are workstation timings, not a prediction of
other hardware.

`tests/test_ai_profile_e2e.py` now exercises the optional AI route from the
desktop's selected profile through its worker, recorded result, Driver view,
and `replay_lap_record`. On the compact analytic synthetic course, one case
chooses the partial source-backed `trev5_working_geometry` intake when its
local source bundle is available; another saves and chooses a Prius setup
with explicit 1,510 kg mass, 125 kW peak power, and `mu=0.82` overrides.
The test checks the frozen profile ID and requested 2 m maximum cell length,
the effective vehicle configuration and source or override provenance in the
JSON, the exact selected solver-grid distance/x/y/curvature arrays, and replay
agreement. It verifies wiring and record reproducibility for two kinds of
profiles. The TREV intake is a partial working scenario and the Prius edits
are user assumptions; neither test establishes measured vehicle behavior or
track-boundary safety.

In the fixed synthetic x 36–55 m, y −3–16 m, 0.3× first-bend scenario, the
updated pose controller first requested braking at **29.726 m** of projected
progress, while the first actual wheel contact with the lower-grip patch was
at **35.244 m**: a **5.518 m** sampled lead. It reached the 80 m target with
**1.673 m** minimum assumed footprint slack and passed recorded-control
replay. The uniform and patch previews took **8.48 s combined wall time** on
this workstation in one fresh run, versus about **9.3 s** combined before the
lookahead/index change. These are implementation checks on one synthetic
course and assumed patch; they neither calibrate grip nor prove safe braking
or swept clearance under arbitrary conditions.

The repository tests exercise constructors, component limits, path constraints, endurance events, desktop settings, record integrity, and the four-wheel equations. The environment checks cover backward-compatible zero-drag/still-air behavior, headwind/tailwind/crosswind signs and power, rotated world wind, road queries after heading rotation, malformed inputs, deterministic repeated runs, and road-domain violations that occur **only inside RK4 stages**. The four-wheel lab checks that A/B share initial conditions and the same wind/patch, and that its worker saves a linked record. The record checks cover content hashes, geometry/input alignment, schema compatibility, tamper rejection, grip-condition/snapshot agreement, older v2 default-grip replay, and residual summaries. Additional desktop checks cover shared grip in AI and car A/B runs, the visible 1080×720 grip control, and clearing old result/replay displays when defining inputs change. The aero/suspension guards reject unsupported loss of normal reaction. Course-catalog checks cover source identity, synthetic and imported arc geometry at several requested steps, exact per-source-cell grid limits, fused-grid behavior, and invalid grid requests; desktop checks cover course-switch clearing, saved course IDs, import persistence, and comparison provenance. The exact command, result, and Git commit should be logged together for a later design review.

Focused planner regression checks exercise explicit corridor requirements, x/y-derived rather than copied curvature, exact chord/station reconstruction, periodic geometry and winding, deterministic bounded iteration, variable widths, narrow 0.5 m source cells, self-crossing and folded-corridor rejection, full/half/adaptive-fourth-offset trials and fallback, failure handling, and candidate selection with the full lap model. The narrow-cell QA case permits only about ±0.01 m offset; its reported candidate offset was about −0.00916 m with zero computed bound violation. A historical **one-pass** synthetic rounded-rectangle case with the built-in Prius at fixed 0.8 torque fraction gave a 16.784 s processed baseline and 14.267 s full-offset candidate; those are not current AI desktop times. A sampled circle regression checks near-uniform curvature and exact integrated turn of `2π` after resampling. Separate `SpatialTrack.geometry_audit()` tests catch map chords longer than their station cells and accept shorter geometric chords around curves; new tests cover source turn mismatch, curvature-integrated closure, and individual arc-chord mismatch when whole-lap totals happen to agree. `SpatialTrack.refine` tests retain original station/curvature boundaries, signed turn, and squared-curvature integral while bounding pathological grid size. New planner tests check continuous scalar modeled-path clearance and closure, including a between-sample violation, near-coincident source-width boundary, unresolved zero-slack tangency, and an open map mislabeled closed, preserve completed but ineligible diagnostics, and prohibit ranking when the processed baseline fails. Driver-view checks include constant-acceleration interpolation, inconsistent legacy fallback, closed-course seam wrapping, and switching already solved A/B and AI paths, including diagnostic replays. Progress callback tests compare snapshots against telemetry, verify unchanged lap time/energy, suppress rejected-cell updates, and exercise phase/track forwarding and desktop queue coalescing. Lap replay tests cover completed centerline and speed-periodic records, changed commands/results, missing channels, misaligned samples, unsupported model snapshots, off-path steering, and incomplete or legacy records. Current-cell corner-exit tests exercise automatic capping, preservation of feasible front-drive torque, exit-speed combined-grip checks on coarse and fine circle grids, and explicit-control rejection; new practice-course wiring checks verify catalog metadata, solver grids, saved run IDs, and desktop selection, while Tk lifecycle tests verify pending timers are canceled when a window closes; curvature-gate tests reject direct zero-steer circular driving, lateral-force saturation, and a small persistent steering bias. These tests establish model/software behavior, not surveyed Formula SAE feasibility.

Additional targeted regressions place a narrow source corridor cell entirely between prior quarter-cell audit samples and require the updated audit to reject the modeled arc. They check that the closed seam applies the narrower of the first and last supplied widths, that the synthetic grid cap counts generated cells per segment, and that every available runnable profile can enter the same optional AI comparison path without a profile-specific planner branch. These checks establish implementation behavior on synthetic inputs; they do not validate a measured boundary or any vehicle dynamics.

The following **historical speed-only seam shooting** calculations used torque fraction 1.0, the same effective vehicle configuration and initial pack state per pass, with a path-specific rolling start, one dry plus one recorded pass per path, and a 0.005 m/s speed residual tolerance. They were benchmarked **before the continuous scalar modeled-path and exit-speed combined-grip gates**; they are not current model timings or eligible racing-line comparisons. With the built-in Prius and a **user-assumed** ±2 m half-width, 1.78308 m car width, and 0.3 m margin, the processed x/y geometric baseline was **1,011.080 m** long after at most **0.769 m** preparation shift, versus 989 m of source stations. Baseline/full/half completed at **87.618366/87.377773/87.403816 s** under that earlier policy, which selected full on its **0.240593 s** numerical lead. At assumed ±2.5 m, baseline/full/half completed at **87.618366/87.441030/87.375223 s**; that policy selected half on a **0.243143 s** numerical lead. These prior selection labels are historical, not current audit eligibility. An ordinary 2 m source-curvature Prius run then completed in about **78.787 s**, but its 989 m station path is different geometry and uses the default one-pass start policy. It must **not** be subtracted from an AI time as a racing-line gain. Earlier one-pass AI times of 87.364 s baseline and 87.155 s full Prius ±2 m predate speed-only seam shooting and the current-cell corner-speed guard. The team's widths, car limits, and track conditions are not established by these scenarios.

An **earlier unconstrained nominal-2 m API benchmark** on the fused course rejected all four assumed ±2 m Prius geometries at desktop-equivalent torque entry **100%** (model fraction **1.0**) under **1.78308 m** vehicle width and **0.3 m** margin. Baseline/full/half/three-quarter usable-corridor excess was **0.095506/0.908195/0.501981/0.705117 m**, with integrated position-seam gaps about **0.75–0.77 m**. Before the exit-speed combined-grip gate, those paths took **87.618366/87.377773/87.403816/87.3655968872 s**; under the current force gate on that same old grid they took **88.2468936756/88.0083862976/88.0305817762/87.9983373607 s**. All times are diagnostic and ineligible. The failed baseline geometry made the fourth strength fall back to 0.75; `rank_status=invalid_processed_baseline`, eligible time fields were null, and no AI winner or gain was selected. These numbers are **not** the current desktop default after the editable 1 m cell-length bound. Its fused source remains geometrically inconsistent; current completed diagnostic trials must be read from the run, not compared with the ordinary source-curvature centerline.

With the desktop **Cell size (max) = 1 m**, a fresh fused-course Prius diagnostic with the same assumed ±2 m corridor, 1.78308 m vehicle width, 0.3 m margin, and 100% torque request built **1,719** processed cells. Its processed baseline had **zero corridor excess** but a **0.065374 m** integrated position-closure error, above the 0.01 m limit. The full-offset path had **0.077436 m** observed corridor excess. Baseline and full-offset model laps completed in **90.001421 s** and **89.678997 s**, respectively; both are diagnostics, and `rank_status=invalid_processed_baseline` still prohibits a ranked gain. The fallback fourth trial remained 0.75, while the full offset was the fastest completed *diagnostic* path. These numbers describe the generated one-meter grid and assumed corridor, not validated track geometry.

The **earlier TREV5 working geometry** run with an assumed ±2 m half-width, 1.8 m width, 0.2 m margin, and torque fraction 1.0 also had `rank_status=invalid_processed_baseline`. Before the exit-speed combined-grip gate, its baseline/full/half/three-quarter completed diagnostic times were **62.1006641048/62.1124557233/62.0913539700/62.0959759770 s**. Sampled usable-corridor excess for full/half/three-quarter was **0.908612549/0.456447888/0.682565568 m**, and their integrated position-seam gaps were **0.771628008/0.761433514/0.766570964 m**; the baseline itself also fails the audit, so the fourth strength falls back to 0.75. The half-strength number was the fastest historical diagnostic, but no path was eligible for selection. That earlier four-path comparison took about **30.14 s** on this machine, not a current latency estimate.

The optional **synthetic rounded-rectangle course** provides a controlled software example. Its ID is `synthetic_rounded_rectangle_v1`, length **195.398224 m**, generated source-cell limit **0.5 m**, and four radius-12 m quarter-circle arcs joined by two 40 m and two 20 m straights. The desktop initially sets **Cell size (max) = 1 m** and supplies *assumed* **±3 m** AI half-width, **1.8 m** vehicle width, and **0.2 m** margin. With the built-in Prius and **80%** desktop torque request, the current speed-periodic processed baseline completed in **17.0090108038 s**, the half-offset path in **15.7317585066 s**, and the selected **0.975-offset** path in **14.6378307024 s**. All three passed their continuous scalar audits and exit-speed combined-grip gate. The full offset failed the assumed corridor by **0.0026717805 m**, so its model lap was skipped. The selected path had a certified lower-bound clearance of **0.0445441230 m** and a **2.3711801014 s** modeled lead. The planner built **206** cells, with selected maximum **0.986678 m**; planning and comparison took about **0.19 s** and **5.4 s** respectively on this computer. This is an eligible numerical selection on an analytic shape, not a validated Formula SAE course, Toyota hybrid prediction, or Racing Terps performance gain.

An optional paired fixed-path grid probe on that same uniform-road Prius
example refined the already selected **206/206-cell** baseline/candidate
paths to **412/542 cells**, without replanning or changing the car. The
refined baseline and candidate completed in **16.9769654766 s** and
**14.6253179480 s**. The candidate-minus-baseline difference changed from
**−2.3711801014 s** to **−2.3516475286 s**; its sign and 0.05 s
selection-margin crossing both remained stable in this one probe. The
approximately **0.01953 s** change shows that cell spacing affects the
reported gain. Because this held the original paths fixed, did not renew
their corridor audit, and sampled only one finer grid, it is a sensitivity
observation, not a convergence certificate or validation against cones.

A fresh optional paired probe with the same synthetic course and Prius at
**80%** driver request used the assumed world rectangle X **36–55 m**, Y
**−3–16 m**, at **0.3×** base grip. The original eligible fixed-path
**206/206-cell** baseline/candidate completed in **20.3465718414 s** and
**17.7554582838 s**. The diagnostic mapped that same world-fixed rectangle
separately onto the **412/542-cell** refined paths with each original path's
modeled entry heading retained; the refined times were **20.3100544665 s**
and **17.6978407275 s**. The candidate-minus-baseline difference changed
from **−2.5911135576 s** to **−2.6122137390 s**; both its sign and the
**0.05 s** selection-margin decision remained stable. This optional check
took about **15.1 s** on this computer, beyond the ordinary AI calculation.
It is one synthetic fixed-path sensitivity observation. It neither proves
grid convergence nor re-audits corridor clearance, and the assumed rectangle
is not a surveyed road condition.

Before the grip-detour proposal was added, a separate **assumed local-surface**
run on that same car, course, cell-size request, and corridor used one
world-fixed rectangle at X **36–55 m**,
Y **−3–16 m**, **30%** of base grip produced a processed-baseline time of
**20.3465718414 s** and selected 0.975-offset time of **17.7554567737 s**.
The mapper marked **32** baseline and **33** selected-path cells at reduced
grip, rather than copying one station-indexed map between paths. This is
evidence that the patch input reached the earlier four-path full-model trial
comparison and was represented differently on different geometries. It is
not a current fifth-trial outcome, measured road data, an optimal avoidance
trajectory, or proof of grid convergence.

A newer short-synthetic-loop software case with the built-in Prius, **1 m**
requested cell limit, assumed **±3 m** half-width, and a deliberately severe
world rectangle at X **52–57 m**, Y **14–16 m**, with **1% of base grip**
selected a grip detour after its full-model trial. Eligible times were
**24.3665982656 s** for the processed baseline, **22.1246941307 s** for the
geometric half offset, and **17.5060905004 s** for the detour; the full
geometric offset failed clearance. The desktop integration check saved and
numerically replayed the selected detour record. This shows that local grip
can alter the selected modeled path when the patch, path audit, and full lap
solver are all active. The extreme assumed patch and synthetic course do not
establish measured grip, a calibrated Prius, reliable lap-time benefit, or
Formula SAE cone clearance.

The longer **synthetic FSAE-style practice course** provides a second controlled comparison. With the same assumed **±3 m** half-width, **1.8 m** car width, **0.2 m** margin, built-in Prius, **80%** torque request, and desktop-default **1 m** cell-length limit, the planner built **829** processed cells; the full-offset maximum was **0.989068 m**. The speed-periodic processed baseline completed in **60.3626147273 s**, the half offset in **60.1875429499 s**, the fourth 0.75 offset in **60.1144353996 s**, and the selected full offset in **60.0387107423 s**. All four passed continuous scalar clearance and closure audits after exact final-station normalization removed a one-ulp seam difference; no audit bound was relaxed. The selected path's conservative minimum assumed-corridor slack was **0.1173201189 m**, and its modeled lead over its own processed baseline was **0.3239039850 s**. Planning took about **0.67 s** and the four-path comparison about **38.3 s** on this computer. This is a software scenario under hypothetical widths and Prius parameters, not a measured Formula SAE advantage or validated vehicle lap.

An earlier on-demand fixed-path resolution probe, **before the exit-speed combined-grip gate**, used `SpatialTrack.refine(1.0)` on that synthetic baseline, old 0.75 fallback, and selected 0.95-offset path, preserving original cell boundaries and curvatures. Their historical refined two-pass laps completed and closed speed: baseline **16.882064565 s**, 0.75 offset **15.000468902 s**, and 0.95 offset **14.551839123 s**. The selected path then retained about **0.448630 s** over the old fallback. Refined path clearance was **not re-audited**, so the probe supports only a timing-sensitivity observation on fixed paths under an older force policy, not renewed path eligibility or formal grid convergence. The recorded default course's failed geometry gate remains unresolved.

At otherwise identical **70% assumed uniform road grip** and **1 m** cell limit, the short synthetic Prius comparison remained `candidate_selected` at 0.975 strength: eligible baseline **19.8711951482 s**, half offset **18.4359730524 s**, and selected offset **17.1829034123 s**. The bounded comparison took about **8.2 s** on this computer. This is a tire-capacity sensitivity in the model, not a calibrated wet-track result.

An earlier on-demand speed-periodic resolution check held each generated assumed ±2 m path fixed and used `SpatialTrack.refine(1.0)` to split existing cells **without averaging curvature across their original boundaries**. The original paths had 495 cells each and maximum cell lengths of **2.873–3.368 m**. Refined paths had **1,335–1,344 cells**. Prius baseline/full/half times were **87.567225/87.330961/87.356931 s**; the full path retained a **0.236265 s** numerical lead versus **0.240593 s** on the original grid. TREV baseline/full/half times were **62.013863/62.049208/62.015252 s**; baseline beat half by **0.001388 s**, reversing the original-grid **0.009310 s** half-offset lead. All six refined laps completed and closed seam speed, but no sampled modeled-path clearance/closure audit was applied to those prior trials. A two-pass refined Prius trial took about **9.5 s** and a TREV trial about **20 s** on this machine; this diagnostic is deliberately outside the default run path. Earlier global-grid resampling also reversed TREV's numerical order but averaged across curvature changes. Neither check is a formal convergence study or measured validation, and none establishes current path eligibility.

An earlier offline **one-pass** resolution probe held the geometric paths fixed while resampling their solver cells from roughly 2 m to 1 m. In the assumed ±2 m Prius scenario, a 0.75-strength offset beat the full offset by **0.025 s** on the coarse grid, then lost by **0.035 s** on the finer grid. A TREV5 0.25-strength offset similarly changed rank against its geometric baseline. These small differences are below the demonstrated grid sensitivity. The current policy tests 0, 1, and 0.5 first, then makes one fourth trial chosen by eligible quadratic, clearance screen after an invalid full path, or 0.75 fallback. Neither the ordinary four-path budget nor the optional fifth patch-mode trial makes hundredth-second gains robust without a resolution study. This is a numerical sensitivity check under the earlier start policy, not track validation or a formal convergence study.

An earlier independent seam audit used the unprocessed **989 m, 1,978-cell** shipped centerline, the default Prius benchmark, a 0.8 torque request, and no start-speed override. Before the exit-speed combined-grip gate, it calculated **79.161 s**, starting at the braking ceiling of **13.2725 m/s** and finishing at **9.4656 m/s**: finish minus start was **−3.8069 m/s** at the same closed-course seam. These are historical results; the seam mismatch illustrates the one-pass initial-condition definition, not a claim that the real car loses that speed on every lap. A current Prius benchmark with a **requested 2 m solver step** completed in **79.4064453081 s** under the new gate; the desktop initially requests **1 m**. The benchmark still uses a one-pass start policy rather than a periodic speed state. Optional AI timing uses the bounded speed-only seam check above; it does not make the changing pack and other component states periodic. Neither route is a verified steady-state lap prediction, and different paths, seams, or start policies could affect ranking.

These are software and equation checks. For an actual car model, additional independent evidence is needed: measured acceleration/coast/braking on specified surface, wheel torque/RPM and pack voltage/current, synchronized yaw/IMU/GNSS, tire force/slip/load and temperature, measured aero balance or CFD with a declared coordinate convention and validation, and surveyed course/ambient conditions. Fit one subset of runs, then test on held-out days, speeds, steering maneuvers, and tracks. Report time error, speed/yaw residuals, energy error, constraint violations, and parameter uncertainty separately. A single matched lap time can hide compensating wrong drag, grip, power, and brake models.

Existing historical material is useful but limited. `docs/model_parameters.md` states that rolling radius, motor efficiency, and chain efficiency were fitted to the same endurance data used for a historical comparison, so that agreement is **in-sample**. `docs/first_lap_soc_validation.md` records 39.07 s simulated versus 69.49 s measured for one first-lap comparison and 13.28 m/s speed RMSE; some discussion there predates later brake logic and should be rechecked before quoting it as current behavior. `docs/real_accel_validation_report.md` documents a rear-wheel-derived acceleration target and explains why it is not a clean independent gate. `docs/battery_rc_validation.md` gives a limited chronological voltage holdout for one historical pack log (about 2.669 V RMSE over its final 35%). None of these constitute a complete 2026-27 Formula SAE vehicle validation, a tire thermal calibration, or a Report II CFD proof.

Important current bounds and gaps:

| Boundary | Consequence for interpretation |
|---|---|
| Main lap follows prescribed curvature and no cone/width rule | A fast time is not proof of a feasible driven line |
| Explicit-control lap checks requested and achieved curvature, but not x/y path or boundaries | Passing the scalar curvature gate and recorded-control replay does not prove the car followed the displayed map or cleared cones |
| AI polygon offset check uses a declared synthetic corridor relative to processed x/y | It verifies the proposed spline offset under supplied widths, not the arc path implied by curvature |
| AI continuous scalar modeled-path check requires clearance and position closure | Initial samples plus bounded interval checks cover each represented curvature arc against supplied normal-coordinate widths; unresolved intervals fail. It does not certify swept-body or surveyed cone clearance, and the shipped paths fail |
| Imported v2 widths are source-relative | Provenance and hashes preserve per-cell data, but the AI planner does not use them until its changed reference frame has a verified width transformation |
| AI objective is local mean-curvature optimization plus bounded line-strength trials; patch mode can propose a separate local detour | Up to eight full-model passes without a patch or ten with one patch. Reduced wheel-contact grip exposure only screens detour geometry; path audit and full-model lap time decide eligibility. Invalid candidates skip physics when the baseline is valid. No path is selectable when the processed baseline fails its modeled-path audit |
| Source x/y and curvature disagree | Stored turn is 3.657937 rad versus 6.283185 rad map winding; default and AI paths cannot be compared for a racing-line gain |
| Default lap speed need not close at the course seam | The default starts at a cyclic braking ceiling for one pass; AI trials separately require speed closure within 0.005 m/s, but no route enforces periodic charge or other full state |
| Main-lap Driver view maps solved station onto reference x/y | The lap marker is not the dynamically integrated vehicle pose; the separate WIP pose preview displays a four-wheel model state on a synthetic course |
| Synthetic pose preview has sampled assumed-corridor checks and edge slowdown | Its 80 m model duration is not an endurance lap time; a nominally valid initial offset may already be outside at a curve, and the speed cap plus axle-span sample/replay checks do not establish swept cone clearance, safer driving, or a full session |
| Main lap uses flat, still air and a base grip factor; optional AI rectangle trials use per-cell absolute schedules | The entered factor scales tire capacity; each optional AI path maps its own assumed world rectangle to nominal wheel-contact cells. Ordinary centerline and A/B remain uniform. The separate lab wind model does not enter main-lap time |
| Main tire is capacity-based with inferred slip | A uniform or per-cell grip value changes its capacity but supplies no measured tire/road calibration, independent wheel transient, or temperature prediction |
| Lab uses static Fz and synthetic linear/circular tire | It demonstrates yaw/force coupling, not a calibrated car |
| Lab aero is vector drag at CG, no downforce/moments | Crosswind sensitivity is qualitative without measured coefficients |
| Lab road patch changes grip cap only | No roughness, rolling resistance, puddling, hydroplaning, or surface heat |
| No thermal states in either current route | Continuous torque, brake temperature, tire fade, and pack derating cannot be predicted |
| Main event can update a cell before rejecting its path/time/stall result | Failed records distinguish attempted vehicle time/speed/SOC from the last checked prefix; caller vehicle remains attempted, so neither is an eligible lap time |
| Windows x64 one-file EXE and controlled build dependency snapshot | Recipients can run without Python; other platforms and organization signing need separate release work. Final packaged checks are distinct from source tests |

## 17. Prioritized engineering work and acceptance evidence

1. **Freeze the 2026-27 car evidence.** Collect a versioned, reviewed configuration: mass/CG/inertias, wheelbase/tracks/radii, drive topology and torque limits, pack/thermal data, brake/regen limits, tire map, and aero coordinate convention. Keep source, units, validity range, and uncertainty per field. Promote only verified values into adapters; keep unknowns explicit.
2. **Establish held-out baseline validation.** Instrument a known dry, flat maneuver and course section. Align times and frames; compare speed, yaw, wheel speeds/torques, pack voltage/current, and brake response with error and uncertainty. Require zero-weather/constant-surface regression before each environmental change.
3. **Repair and survey the course before ranking real racing lines.** Survey both cone boundaries in one world frame with station, closure, and uncertainty. Reconcile 989 m station/curvature with roughly 1,012 m x/y using retained raw data and versioned processing. Require consistent x/y, cell lengths, curvature arcs, and position seam without damaging curvature spikes. Transform V2 source-relative widths into the smoothed AI frame with checked uncertainty. Retain the synthetic loop's assumed-corridor gate as a software check, then verify the full swept vehicle against surveyed boundaries. Arc prototypes remain research evidence; default fused-course AI times remain diagnostic until repair.
4. **Extend wind and aero only with reviewed maps.** A first lap wind extension needs a world-referenced course and measured/declared wind. A full six-component CFD or wind-tunnel map needs force/moment reference, yaw sign, ride height/roll/pitch axes, interpolation bounds, and crosswind benchmarks. Avoid applying both scalar drag/downforce and the same map forces.
5. **Add surveyed road geometry and contact states.** Elevation/grade, bank, crest, material, and patch coverage must be sampled at actual wheel contacts. Check analytically that still-flat results recover baseline; constant grade gives longitudinal gravity force `mg sin(theta)`, elevation work `mg delta_h`, and normal component `mg cos(theta)`; symmetric bank changes lateral demand with correct sign; crest unloading cannot produce negative contact loads. Track width and cone feasibility require a path model, not a display outline.
6. **Add conservative thermal states only with calorimetry and cooling evidence.** Tire/brake/motor/inverter/pack temperatures need explicit heat capacities, generated heat, conductive/convective/radiative flows, ambient or coolant boundaries, and state-dependent limits. Internal heat exchanges must cancel in the whole-system balance. Slip and brake work must be assigned once, without double counting pack discharge. A derivative call must not change temperature or SOC.
7. **Build complete timed sessions from the bounded pose experiment.** The 80 m synthetic preview now exercises feedback steering, planar pose, assumed-corridor samples, and a separate versioned trace archive with numerical replay. That archive contains only one synthetic maneuver; it does not connect to a versioned Terps vehicle/controller, interactive driver, ghost, or session comparison. Extend the lap cell-curvature gate to a checked integrated pose against one consistent course map and surveyed boundaries before calling an explicit-controls run a driven lap. A ghost is only a time/station comparison until both tracked poses are verified. Define complete-session controls/states/environment and validity capture, channel tolerances, and a comparison manifest linking both run IDs, source hashes, and software versions. Keep full-session controls unavailable until that workflow is testable.
8. **Maintain reproducible distribution and extend replay.** Preserve artifact hashes, source changes, complete-suite/skip logs, and packaged smoke evidence for every revision of the controlled Windows x64 build; add signing or other platforms when required. Extend one-lap replay into a version-aware comparison gate. Capture dirty patches or require clean source, add a standalone A/B comparison manifest, and document schema migrations and machine-independent tolerances. Four-wheel A/B and synthetic pose records replay frozen inputs under the installed model; complete timed-session replay remains future work.

Report II provides **test design**, not acceptance evidence. Each upgrade needs equation/unit checks, limiting-case regressions, controlled synthetic sensitivities with monotonic expectations where applicable, and independent measured holdouts before being described as predictive. Label displayed results as model estimates and retain their exact records with engineering decisions.
