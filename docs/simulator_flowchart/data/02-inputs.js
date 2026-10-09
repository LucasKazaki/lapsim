/* Inputs, configuration, and provenance */
(() => {
  "use strict";
  const {N,branches}=window.LAPSIM_FLOWCHART_BUILD;
  branches.push(
    N("inputs","Inputs, configuration, and provenance","input","implemented","Everything frozen before a run: car, course, controls, conditions, numerical settings, and source evidence.",null,[
      N("vehicle-resolution","Resolve the effective vehicle","input","implemented","A selected profile and allowed overrides are adapted into a fresh Vehicle plus a manifest of used, inherited, and unused fields.",{o:["Vehicle instance","ResolvedManifest","Explicit inherited assumptions"],s:["src/lapsim/profiles/registry.py","src/lapsim/profiles/adapter.py"]},[
        N("profile-registry","Profile registry","data","implemented","Enumerates built-in vehicles and optional locally reviewed TREV source bundles.",{s:["src/lapsim/profiles/registry.py"]}),
        N("profile-adapter","Allowlisted profile adapter","solver","implemented","Maps supported source fields and units into component constructors; missing values remain defaults or unknowns.",{s:["src/lapsim/profiles/adapter.py"]}),
        N("garage-overrides","Local garage overrides","input","optional","Small editable convenience layer for a limited set of vehicle fields; it is not a complete calibration manager.",{s:["src/lapsim/ui/garage.py"]}),
        N("vehicle-manifest","Resolved source manifest","data","implemented","Records source identity, accepted values, defaults, and unused fields so a saved result can be traced to its effective inputs.",{s:[["src/lapsim/profiles/adapter.py","ResolvedManifest"]]})
      ]),
      N("course-inputs","Course and solver geometry","input","implemented","SpatialTrack supplies monotonically increasing station, cell curvature, optional x/y boundaries, and closed/open topology.",{s:[["src/lapsim/courses/spatial_track.py","SpatialTrack"]]},[
        N("course-fused","Bundled fused endurance recording","data","implemented","Default desktop course loaded from the repository's fused GNSS/IMU-derived centerline input.",{s:["analysis/data/track/gnss_imu_endurance_track.csv"]}),
        N("course-synthetic","Analytic synthetic courses","data","assumption","Exact straight/arc practice loops support deterministic software checks; they are not surveyed competition layouts.",{s:["src/lapsim/courses/track.py","src/lapsim/ui/course_catalog.py"]}),
        N("course-bundle","Versioned imported course bundle","data","optional","Validated bundle metadata can retain coherent geometry, hashes, provenance, and source-relative widths.",{s:["src/lapsim/courses/course_bundle.py","docs/course_bundle_format.md"]}),
        N("course-resample","Build the solver grid","solver","implemented","Measured tracks are resampled with distance-weighted curvature; coherent analytic cells are preserved or exactly subdivided.",{i:["Source SpatialTrack","Maximum cell length"],o:["Solver SpatialTrack with <= 5000 cells"],e:["kappa_new = sum(kappa_source * overlap_length) / new_cell_length","Integral preservation: sum(kappa_new * ds_new) = sum(kappa_source * ds_source)"],s:[["src/lapsim/ui/simulation.py","resample_track"],"src/lapsim/courses/spatial.py"]})
      ]),
      N("controls-inputs","Driver and actuator requests","input","implemented","Controls are distance-indexed in the main model and time-indexed in the planar model.",null,[
        N("controls-struct","Main-model Controls","input","implemented","",{i:["Motor torque request (N m)","Front/rear hydraulic pressure (psi)","Front/rear regenerative force request (N)","Steering angle (rad)"],s:[["src/lapsim/core/controls.py","Controls"]]}),
        N("controls-profiles","Distance-indexed controls profiles","input","implemented","Constant and piecewise-linear profiles provide controls_at(distance_m).",{s:["src/lapsim/core/profiles.py"]}),
        N("torque-profile","Normalized periodic torque profile","input","implemented","Offline endurance controller converts a 0-1 torque fraction into feasible drive, coast, friction-brake, and optional regen commands.",{s:["src/lapsim/optimization/torque_profile.py"]}),
        N("planar-controls-input","PlanarControls","input","experimental","",{i:["Four steering angles","Four drive torques","Four brake torques","Optional normal loads","External body loads"],s:[["src/lapsim/dynamics/planar.py","PlanarControls"]]})
      ]),
      N("condition-inputs","Road and environment assumptions","input","implemented","",null,[
        N("uniform-grip","Uniform tire-grip multiplier","input","assumption","Scales lateral and longitudinal tire capacity for an entire main-model run.",{e:["mu_effective(Fz) = grip_multiplier * mu_selected_tire(Fz)"],s:[["src/lapsim/ui/simulation.py","apply_uniform_road_grip"],"src/vehicle_model/mech/tire.py"]}),
        N("cell-grip","Per-cell absolute grip schedule","input","optional","One positive multiplier per solver cell, used consistently for local limits, braking ceilings, and cell physics.",{s:["src/lapsim/solvers/path_constraints.py","src/lapsim/events/endurance.py"]}),
        N("world-patch-input","Assumed world-fixed grip rectangle","input","experimental","Optional AI-path sensitivity input mapped separately onto each candidate path's nominal wheel contacts.",{s:["src/lapsim/optimization/road_grip_schedule.py"],r:["road-grip-map"]}),
        N("planar-environment-input","PlanarEnvironment and PlanarRoad","input","experimental","",{i:["World-frame wind","Air density","CdA","Base pavement","Grip patches","Optional validity domain"],s:["src/lapsim/dynamics/conditions.py"]})
      ]),
      N("numerical-inputs","Numerical configuration and guards","input","implemented","Cell count, tolerances, pass caps, time caps, and pressure limits bound computation and define acceptance gates.",{s:[["src/lapsim/ui/simulation.py","path_solver_settings"],["src/lapsim/events/endurance.py","EnduranceRunConfig"]]})
    ])
  );
})();
