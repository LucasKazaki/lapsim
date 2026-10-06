# Racing Terps LapSim: team demo brief

**Purpose:** show what the current desktop simulator calculates, what the optional racing-line mode changes, and which team measurements are still needed before using a result for a car or course decision.

## Five-minute walkthrough

1. Launch `launch_lapsim.cmd`, select the **Prius benchmark**, and leave **Centerline (default)** selected. Run one lap. The Driver view shows the latest accepted model step while the solve runs, then plays the completed result. Read the lap time, speed, energy, lateral acceleration, and entry/exit speed boxes; point out the saved run ID. Different seam speeds mean this is one initial-condition lap, not a periodic steady-state prediction.
2. Open **Source data / model notes** and the course warning. The shipped x/y drawing and the solver's saved curvature are separate, inconsistent channels. The current course also has no surveyed left/right widths.
3. Select **AI racing line (experimental)**. Enter an explicitly assumed corridor, vehicle width, and safety margin. The planner tests a full and half-strength smooth offset against a newly processed geometric centerline with the same car and physics. Each timed path closes its lap-seam speed within 0.005 m/s, using two bounded passes from the same initial car and pack state. Compare only the times shown together in the AI result box. The ordinary centerline lap uses different curvature and is not a fair time baseline for this mode.
4. Use **Run comparison** to run two car profiles at the same centerline settings. Read B-minus-A values and the saved IDs. The profiles can be edited and saved without source-code changes, but the source-backed Terps entries remain partial working scenarios.
5. Open **Timed sessions · WIP**. Explain that a versioned car and controller, live driving against a ghost, complete control capture, numerical replay agreement, and linked report are the next-stage contract; the tab deliberately cannot start a session yet.

## What the optional racer actually does

It is a deterministic, offline path planner. It minimizes a geometric curvature-and-length objective within entered clearances, rejects invalid paths, and checks up to three paths with at most two physics passes each. A time counts only when the modeled path completes and its seam speed converges; the car and pack state still change across the lap. It does not learn from laps, steer a simulated car, see cones, or respond to traffic. The default centerline calculation does not run the planner. The Driver view is a top-down **reference-path** display with model speed and lateral acceleration, not a measured vehicle pose or a first-person camera.

## Evidence to show, and how to phrase it

- Show a saved run's input profile, solver grid, actual lap start speed, course geometry, completion status, entry/exit speeds, telemetry, and content ID. Open the AI record's linked counterpart when comparing two paths. These establish what this version of the program calculated.
- Show the AI result's assumed corridor and separate processed-baseline/candidate times. A faster computed path under an assumed corridor is a model sensitivity result, not evidence it fits a competition course.
- Show the course geometry warning and the engineering handoff. The report gives the equations, Python data flow, test evidence, known mismatches, and unimplemented features.

## Data to request from the team

Ask for a surveyed centerline with left/right cone or pavement boundaries, a consistent distance/heading/curvature reconstruction, and the 2026–27 car's controlled revision of mass, wheelbase, track widths, tire force data, powertrain and battery limits, brake behavior, aero, and measured logs with stated test conditions. Those inputs matter more than a larger AI search or a learned driving policy at this stage.

**Full technical detail:** [Engineering handoff](engineering_handoff.md), [AI racer design](ai_racer_design.md), and [desktop guide](simulator_desktop.md).
