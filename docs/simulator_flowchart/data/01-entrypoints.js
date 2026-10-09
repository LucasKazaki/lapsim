/* Entry points and orchestration */
(() => {
  "use strict";
  const {N,branches}=window.LAPSIM_FLOWCHART_BUILD;
  branches.push(
    N("entrypoints","Entry points and orchestration","entry","implemented","How a user or script enters the repository and which execution pipeline is selected.",{s:["src/lapsim/ui/app.py","src/lapsim/events/api.py"]},[
      N("desktop-ui","LapSim desktop application","entry","implemented","Tk desktop shell that resolves inputs, launches bounded worker calculations, and displays results.",{i:["Selected course","Selected/effective vehicle","Road-grip and driver settings","Run mode"],o:["Run status","Plots and playback","Saved run records"],s:[["src/lapsim/ui/app.py","LapSimApplication"],"docs/simulator_desktop.md"]},[
        N("desktop-launch","Launch and environment checks","entry","implemented","Windows launchers validate Python, Tk, imports, and the bundled course before opening the GUI.",{s:["setup_lapsim.ps1","launch_lapsim.cmd"]}),
        N("desktop-input-freeze","Validate and freeze run inputs","solver","implemented","The UI parses controls, resolves a fresh vehicle, freezes the course/grid, and clears stale results before work starts.",{o:["Immutable calculation request","Independent vehicle copy"],s:["src/lapsim/ui/app.py","src/lapsim/ui/presets.py"]}),
        N("desktop-worker","Background calculation worker","solver","implemented","Long calculations execute outside the Tk event loop; progress reports observed work without inventing an overall ETA.",{s:["src/lapsim/ui/app.py","src/lapsim/ui/calculation_progress.py"]}),
        N("desktop-centerline","Centerline lap mode","entry","implemented","Uses the selected course curvature directly, solves path constraints, then runs the distance-domain lap model.",{s:[["src/lapsim/ui/simulation.py","run_one_lap"]],r:["distance-pipeline"]}),
        N("desktop-compare","Two-car comparison","optional","optional","Runs frozen vehicles on the same course, driver request, and feasible rolling-start convention for an A/B comparison.",{s:["src/lapsim/ui/comparison.py","src/lapsim/ui/app.py"]}),
        N("desktop-ai-mode","AI racing-line mode","experimental","experimental","Builds bounded candidate paths, audits them, and times admitted paths with the same lap physics.",{s:["src/lapsim/optimization/racing_line.py"],r:["racing-line"]}),
        N("desktop-four-wheel","Four-wheel dynamics lab","experimental","experimental","Runs paired short time-domain maneuvers with independent wheel torques, wind, and local road grip.",{s:["src/lapsim/ui/dynamics_lab.py"],r:["planar-model"]}),
        N("desktop-pose-preview","WIP pose-driver preview","experimental","experimental","Uses the separate planar model and a simple closed-loop driver to test short synthetic path-following traces.",{s:["src/lapsim/ui/pose_driver_playback.py","src/lapsim/optimization/pose_driver.py"],r:["pose-driver"]})
      ]),
      N("programmatic-api","Programmatic event API","entry","implemented","Shared Python boundary for endurance, acceleration, and skidpad studies.",{i:["Vehicle","SpatialTrack","ControlsProfile or torque profile"],o:["EventResult with points, time, energy, status, telemetry"],s:["src/lapsim/events/api.py","docs/event_simulation.md"]},[
        N("api-controls-profile","ControlsProfile contract","input","implemented","Any object implementing controls_at(distance_m) -> Controls can drive the generic event simulators.",{s:[["src/lapsim/core/profiles.py","ControlsProfile"]]}),
        N("api-endurance","simulate_endurance","entry","implemented","Generic endurance wrapper that returns the common EventResult boundary.",{s:[["src/lapsim/events/api.py","simulate_endurance"]]}),
        N("api-acceleration","simulate_acceleration","entry","implemented","Runs an open straight course, including an optional rollout distance before the scoring line.",{s:[["src/lapsim/events/api.py","simulate_acceleration"]]}),
        N("api-skidpad","simulate_skidpad","entry","implemented","Runs the prescribed skidpad path and applies timed-event scoring to the selected laps.",{s:[["src/lapsim/events/api.py","simulate_skidpad"]]})
      ]),
      N("analysis-entrypoints","Analysis scripts and focused studies","entry","implemented","Repository scripts run event studies, validation replays, sweeps, and report generation using the same model APIs.",{s:["analysis/events/","analysis/endurance/","analysis/accel/"]})
    ])
  );
})();
