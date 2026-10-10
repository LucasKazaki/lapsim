/* Entry points and orchestration */
(() => {
  "use strict";
  const {N,branches}=window.LAPSIM_FLOWCHART_BUILD;
  const input=(name,title,unit,type,description)=>Object.assign(
    N(`web-input-${name}`,title,"variable","implemented",description,{s:[["web/bridge.py","normalize_settings"]]}),
    {variable:{name,meaning:description,unit,type,unitEvidence:"Explicit browser JSON contract in web/bridge.py"}}
  );
  branches.push(
    N("entrypoints","Entry points and orchestration","entry","implemented","How a user or script enters the repository and which execution pipeline is selected.",{s:["src/lapsim/ui/app.py","src/lapsim/events/api.py"]},[
      N("browser-simulator","Browser simulator and team links","entry","implemented","Static web shell loads the existing Python model in a module worker. It computes one prescribed-path lap on the visitor's device.",{s:["web/index.html","web/app.js","web/worker.js","web/bridge.py","docs/web_simulator.md"]},[
        N("browser-inputs","Browser settings and individual variables","input","implemented","Finite settings are validated before vehicle construction or path solving. Unknown keys and oversized grids are rejected.",{s:[["web/bridge.py","normalize_settings"]]},[
          input("vehicleProfile","vehicleProfile","profile identifier","string","Selects a fresh built-in vehicle and its source manifest."),
          input("courseId","courseId","course identifier","string","Selects the stored or synthetic distance-indexed course."),
          input("torqueFraction","torqueFraction","dimensionless","number","Fraction 0–1 of the available driving-torque request; automatic braking remains the same controller."),
          input("brakePressurePsi","brakePressurePsi","psi","number","Maximum modeled axle hydraulic pressure, 10–500 psi. A configured cap, not pedal position or force bias."),
          input("gripMultiplier","gripMultiplier","dimensionless","number","Uniform road-grip sensitivity from 0.2 to 1.5; changes force caps."),
          input("regenEnabled","regenEnabled","boolean","boolean","Allows a regeneration request below SOC 1; actual recovery still requires battery/drivetrain acceptance. Both shipped browser packs have zero charge-power capacity."),
          input("maxCellLengthM","maxCellLengthM","m","number","Requested spatial grid step 0.5–10 m, further limited to 1200 actual cells."),
          input("initialSpeedMps","initialSpeedMps","m/s","number or null","Null uses the feasible automatic rolling start. An explicit value must remain within path constraints.")
        ]),
        N("browser-worker","Scientific runtime and cancellation","solver","implemented","Pinned Pyodide loads NumPy, SciPy and Matplotlib metadata, verifies archive SHA-256 and unpacks the exact Python source. Cancel terminates the worker; it does not wait for a queued message.",{s:["web/worker.js","scripts/build_web.py"]}),
        N("browser-physics","Solve constraints and traverse one lap","solver","implemented","Constructs the vehicle and course, applies real brake/grip settings, solves path constraints, then uses EnduranceSimulator with a constant periodic torque request.",{s:[["web/bridge.py","run_simulation"]],r:["distance-pipeline"]}),
        N("browser-record","Results, telemetry and evidence","data","implemented","Records aligned actual telemetry and effective vehicle/settings/runtime identity. Failed runs remain failed prefixes; completed laps can be compared. Downloaded JSON is the existing replayable run-record schema.",{s:["web/bridge.py","web/app.js","tests/test_web_bridge.py"],r:["run-records"]})
      ]),
      N("desktop-ui","LapSim desktop application","entry","implemented","Tk desktop shell that resolves inputs, launches bounded worker calculations, and displays results.",{i:["Selected course","Selected/effective vehicle","Road-grip and driver settings","Run mode"],o:["Run status","Plots and playback","Saved run records"],s:[["src/lapsim/ui/app.py","LapSimApplication"],"docs/simulator_desktop.md"]},[
        N("desktop-launch","Launch and environment checks","entry","implemented","Windows launchers validate Python, Tk, imports, and the bundled course before opening the GUI.",{s:["setup_lapsim.ps1","launch_lapsim.cmd"]}),
        N("desktop-input-freeze","Validate and freeze run inputs","solver","implemented","The UI parses controls, resolves a fresh vehicle, freezes the course/grid, and clears stale results before work starts.",{o:["Immutable calculation request","Independent vehicle copy"],s:["src/lapsim/ui/app.py","src/lapsim/ui/presets.py"]}),
        N("desktop-worker","Background calculation worker","solver","implemented","Long calculations execute outside the Tk event loop; progress reports observed work without inventing an overall ETA.",{s:[["src/lapsim/ui/app.py","calculation progress and worker callbacks"]]}),
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
