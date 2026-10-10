# Verification and release acceptance

This guide separates automated software checks, packaged-app checks, and
physical validation. The [engineering handoff](engineering_handoff.md) preserves
dated historical evidence. Counts in that report belong to those runs; use a
fresh release report for the executable being shared.

## Established review evidence - 9 October 2026

The following checks were reported during this release review. Read the shared
release's XML, logs, and frozen self-test JSON alongside these summaries. The
complete-suite totals consolidate the initial module sweep and affected GUI
reruns; they are not a claim that the initial sweep had no skips.

| Check | Established result |
|---|---|
| Current source runtime self-test | All 10 checks passed: TkAgg canvas, desktop widgets, four-wheel lab widgets, bundled 1,978-cell course, course provenance, offline map, durable cached source/document links, synthetic lap, record round trip, and recorded-control replay |
| Current frozen runtime self-test | All 10 checks passed from an unrelated temporary directory with Python/Git absent from `PATH`, isolated user data, and optional external evidence absent; includes durable cached source/document links. Bundled course had 1,978 cells and the 32-cell synthetic lap completed in 8.1284262182 s with saved-record replay agreement |
| Consolidated complete suite | 64 modules; 749 test functions and 1,010 subtests, totaling 1,759 JUnit cases with no unresolved failure or skip after affected GUI reruns. The initial sweep had two Tcl startup skips; see the rerun explanation below |
| First combined suite (secondary baseline) | 730 passed, 1 skipped, 674 subtests; the skipped pose-preview case reported Tk `tcl_findLibrary`. Use the final isolated-module report for release totals |
| Packaging/source-profile/record regressions | 28 tests passed |
| Desktop lifecycle/saved-run regressions after cleanup fix | 8 tests passed with no native Tcl stderr; startup drains pending layout/theme work and destruction cancels queued Tcl callbacks, including TkAgg |
| Core physics regressions | 101 tests and 355 subtests passed |
| Event/dynamics/path-constraint regressions | 56 tests and 610 subtests passed |
| Equation-consistency operating-point sweep | 255 traversable cases passed across drive axle, speed, signed curvature, drive/coast/friction-brake/regen modes |
| Documentation link/reference audit | No missing non-map local Markdown targets; all 48 representative test-module references resolve |

In the operating-point sweep, maximum longitudinal force-balance residual was
`4.55e-13 N`, maximum battery `P - V I` residual was `1.46e-11 W`, tire combined
capacity stayed within bounds, telemetry remained finite, and normal loads
remained nonnegative. The audit fixed zero-power/depleted-battery stall torque
and the old lap solver's untraversable stopped-cell behavior. Battery validation
now rejects nonfinite values and non-integer cell counts. These are software,
equation, and input-boundary checks; they do not establish empirical prediction
quality. Consult the shared release's test logs and frozen self-test JSON for
its complete-suite totals, skipped cases, and final artifact results.

The initial 64-module sweep recorded 747 passed test functions, 1,010 subtests,
and two intermittent Tcl startup skips in course import and saved-run desktop
tests. The saved-run module then passed 7/7 without skips. A course-module retry
passed four cases but encountered a Tcl reinitialization failure in its restart
case; that exact case passed 1/1 in a fresh process. The entire course module
subsequently passed 5/5 with pytest's `--capture=sys`. Windows file-descriptor
capture was implicated in stale Tcl file channels; the release checker uses
Python stdout/stderr capture while preserving the process file descriptors.
The consolidated XML replaces affected case results and retains the original
and rerun logs. This documents the observed startup issue and its resolution
without calling the initial sweep an unskipped pass.

The application also drains initial layout/theme idle work after setting its
theme and cancels all pending Tcl `after` callbacks when the root is destroyed,
including Matplotlib's TkAgg callbacks. This closes the observed GUI cleanup
gap rather than relying only on test-runner capture settings.

## Reproduce the software checks

From the repository root after `setup_lapsim.cmd`:

```powershell
.\.venv\Scripts\python.exe scripts\check_desktop.py
New-Item -ItemType Directory -Force -Path work | Out-Null
.\.venv\Scripts\python.exe scripts\check_all.py 2>&1 | Tee-Object -FilePath work\test-suite.log
if ($LASTEXITCODE -ne 0) { throw "LapSim checks failed; review the report and log." }
```

The preflight verifies supported 64-bit Python, imports, the shipped course,
Tk initialization, and an actual Matplotlib TkAgg canvas. It does not run a lap.
The Python checker discovers each `tests/test_*.py` module and runs it in a fresh
process with restricted OpenBLAS/OMP/MKL workers, base Python Tcl/Tk paths,
and pytest `--capture=sys` for stable Tcl file channels on Windows.
It collects all module results
in `work/test-results.xml`; the command above also retains output in
`work/test-suite.log`. Failures or missing reports produce a nonzero exit.
The older `scripts/check_all.ps1` remains available; it configures base Python
Tcl/Tk paths and stops at the first failing module. Both avoid a shared Tk
interpreter and keep memory use bounded.

For a focused regression while developing:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -rs tests\test_lap_replay.py
```

GUI tests require a usable Tk display. Several optional source-profile tests
require the local ENME408 evidence package. Report skipped tests and their
reasons explicitly. A suite that skips display tests cannot establish that the
desktop works. A missing optional evidence package is different from a missing
mandatory shipped course.

## What the existing tests cover

| Area | Representative test modules | Evidence provided |
|---|---|---|
| Components and interfaces | `test_aero`, `test_ocv_pack_battery`, `test_drivetrain`, `test_tire`, `test_suspension`, `test_brakes`, `test_component_extensibility` | Equations, limiting cases, validation, component replacement |
| Cell integration and physics gates | `test_state_update`, `test_spatial`, `test_corner_cell_exit`, `test_prescribed_path_corner_exit`, `test_brake_ceiling_guard` | Accepted-step force/speed behavior, corner-capacity exits, braking guards |
| Course geometry | `test_track`, `test_spatial_track`, `test_track_refinement`, `test_course_bundle`, `test_course_catalog`, `test_create_course_bundle` | Arc/grid consistency, subdivisions, hashes, schema and invalid-data rejection |
| Limits, progress and laps | `test_path_constraint_convergence`, `test_constraint_progress`, `test_solver_integration`, `test_speed_periodic_lap`, `test_speed_periodic_progress` | Cyclic braking, bounds, closed speed seams, accepted-cell progress |
| Events and scoring | `test_events`, `test_endurance_simulator`, `test_endurance_scoring`, `test_endurance_optimizer`, `test_torque_profile` | Shared event contract, completion/points behavior, optimization bookkeeping |
| AI paths and local grip | `test_racing_line`, `test_ai_desktop`, `test_ai_grid_stability`, `test_grip_detour`, `test_road_grip_schedule`, `test_cell_road_grip` | Geometry eligibility, bounded trials, grid-sensitivity policy and grip mapping |
| Records and replay | `test_run_record`, `test_lap_replay`, `test_pose_run_record`, `test_dynamics_record` | Alignment, hash/schema checks, tamper rejection and numerical replay |
| Desktop state and playback | `test_desktop_simulation`, `test_driver_view`, `test_saved_run_evidence_ui`, `test_calculation_progress_ui`, `test_tk_lifecycle` | Input invalidation, displayed values, callback cleanup, accepted-step alignment |
| Separate pose physics | `test_planar_dynamics`, `test_planar_conditions`, `test_pose_driver`, `test_pose_preview_ui`, `test_pose_status_ui` | Force/power identities, RK4 scenarios, feedback preview, replay and stop reporting |

Tests are focused regression evidence, not exhaustive exploration of every
possible input or proof that no bugs remain. New fixes should add a regression
at the actual behavioral boundary, rather than a test that repeats implementation.

## Manual desktop smoke checks

Record pass/fail and observed status for the release being shared:

1. Launch with no source checkout or Python installation required by the
   portable build, from a working directory unrelated to the app folder.
   Confirm the default course loads and the window/canvas renders.
2. Run the synthetic-loop centerline demo with Prius, driver request 80%,
   grip 100%, and 1 m maximum cell size. Confirm a completed result, plots,
   live progress, Driver view playback, and a saved run record.
3. Change a run input. Confirm the old result and playback clear. Enter one
   invalid value and verify the UI explains it without retaining a misleading
   old result; restore a valid value and rerun.
4. Run a two-car comparison. Confirm both cars use one common feasible start
   speed, separate records, and the correct replay selection and course label.
5. On the synthetic loop, run optional AI mode. Inspect each trial's audit,
   speed seam, eligibility, chosen strategy, linked records, and replay.
   Rejected geometry should have no physics replay; diagnostic time must be
   labeled. Exercise the finer-grid check and its sensitivity warning if shown.
6. Exercise the assumed low-grip rectangle on a coherent synthetic course.
   Confirm the rectangle appears, each trial saves its own schedule, and the
   fused recording refuses a feature requiring coherent geometry.
7. Open the Four-wheel lab and run an A/B maneuver. Read its separate
   synthetic label and save evidence. Open the WIP pose preview; run, replay,
   save, and load a synthetic trace.
8. Import a prepared coherent course bundle, restart, and confirm it remains
   in the catalog. Verify a malformed bundle is rejected with an explanation.
9. Save a user profile, restart, and confirm the saved input values persist.
   Preserve existing user data throughout upgrades.
10. Open the interactive map from the shared package. Expand subsystem
    branches to variable/equation leaves; exercise search, pan/zoom, collapse,
    and any supplied source links from their shipped location.
11. Close the desktop during/after calculation and close plot/detail windows.
    Confirm no abandoned process or callback exception remains.

Use the automated GUI tests for the covered transitions and perform the
packaged smoke checks on the actual artifact. A source checkout passing tests
does not establish that a frozen executable includes its course, Tcl/Tk,
Matplotlib data, source references, or local documentation.

## Reproducible release evidence

Keep these together when creating a release:

- Source repository URL, checked-out commit, and uncommitted-change status.
- Build date, target OS/architecture, Python and dependency versions, packaging
  tool version, and exact build command.
- Complete-suite totals, failures, skips with reasons, preflight result, and
  manual packaged smoke results.
- Hashes of distributed artifacts and a manifest of the included files.
- Representative saved runs, their profile/course IDs, exact settings, and
  numerical replay result when applicable.
- Known limitations and any tests blocked by unavailable external evidence.

Use an isolated temporary Windows user-data directory for automated smoke
checks, so the release test cannot overwrite teammate profiles or runs. Build
from a controlled dependency environment and retain its dependency lock/snapshot.
After source changes, rebuild and test the final artifact. Publish counts for
the final tested build rather than an earlier successful revision.

## Model-validation boundary

Equation identities, deterministic replay, and synthetic sensitivities check
the implemented model. Historical fitted-lap replay checks consistency with
its calibration data. A team-car prediction needs independent held-out
measurements with stated course geometry, vehicle configuration, tires,
weather, synchronized channels, and uncertainty. Current software checks
cannot turn assumed widths/grip, inherited defaults, or an inconsistent
recorded course into measured evidence.

Before using a result for a car decision, review both the saved run's validity
warnings and the handoff's evidence levels. Reduce spatial/time steps and
compare decision-relevant quantities when numerical sensitivity matters.
An optional pairwise finer-grid check is one sensitivity observation, not
convergence of the full AI search or validation against the real car.
