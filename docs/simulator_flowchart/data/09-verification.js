/* Verification, evidence, and model limits */
(() => {
  "use strict";
  const {N,branches}=window.LAPSIM_FLOWCHART_BUILD;
  branches.push(
    N("validation","Verification, evidence, and model limits","validation","implemented","The repository distinguishes software consistency from measured predictive validity.",null,[
      N("validation-tests","Automated regression and focused checks","validation","implemented","Unit, integration, replay, grid, path-audit, energy-residual, and desktop workflow tests guard the implemented contracts.",{s:["tests/"]}),
      N("validation-replays","Historical data replays","validation","implemented","Battery and first-lap studies test consistency with selected telemetry and calibration data; shared calibration data are not independent holdout validation.",{s:["docs/battery_voltage_validation.md","docs/battery_rc_validation.md","docs/first_endurance_lap_validation.md"]}),
      N("validation-synthetic","Analytic and synthetic checks","validation","implemented","Exact arc/straight courses, timestep comparisons, energy identities, and deterministic replays isolate numerical and sign errors.",{s:["tests/","docs/four_wheel_dynamics.md"]}),
      N("model-separation","Physics-family separation","limitation","limitation","Main lap wind/road/aero/tire equations are not automatically connected to the separate planar environment, and planar wheel dynamics do not determine endurance time.",{s:["docs/engineering_handoff.md"],r:["distance-pipeline","planar-model"]}),
      N("main-model-omissions","Main lap model omissions","limitation","limitation","",{a:["No lateral velocity or yaw inertia","No transient suspension/heave/pitch/roll damping","No surveyed track containment, elevation, banking, or roughness","No tire temperature/wear or full combined-slip Pacejka baseline","No motor/inverter/battery thermal derating or cooling model","Scalar aero without CFD ride-height/yaw maps","Quasi-static force evaluation per distance cell"],s:["docs/engineering_handoff.md","docs/model_parameters.md"]}),
      N("planar-omissions","Planar model omissions","limitation","limitation","",{a:["Synthetic vehicle and tire parameters","Static normal loads unless caller supplies them","No motor/battery/actuator envelope in base wheel torque requests","No vertical dynamics, real road survey, or production control timing","Open-loop lab maneuvers are not lap drivers"],s:["docs/four_wheel_dynamics.md"]}),
      N("evidence-gate","Evidence gate before team-car claims","validation","future","Promote assumptions only through reviewed adapters and validation cases; do not infer missing hardware from research prose.",{i:["Reviewed car mass/inertia/geometry","Measured tire/load-transfer data","Motor/inverter/battery maps and limits","Aero maps and track survey","Controller timing and telemetry"],s:["docs/engineering_handoff.md","docs/source_vehicle_profiles.md"]}),
      N("extension-seams","Future-proof replacement seams","optional","future","Protocols allow higher-fidelity battery, motor, inverter, chain drive, aero, chassis, suspension, tire, and brake implementations without rewriting the event boundary.",{s:["src/vehicle_model/interfaces.py","docs/extending_models.md"]})
    ])
  );
})();
