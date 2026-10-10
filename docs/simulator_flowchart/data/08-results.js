/* Results, telemetry, scoring, and replay */
(() => {
  "use strict";
  const {N,branches}=window.LAPSIM_FLOWCHART_BUILD;
  branches.push(
    N("outputs","Results, telemetry, scoring, and replay","output","implemented","How solver state becomes inspectable evidence and event-level decisions.",null,[
      N("telemetry","Namespaced aligned telemetry","output","implemented","Vehicle and every component append scalar channels to a shared snapshot; TelemetryRecorder aligns samples by accepted progress.",{o:["vehicle.*","controls.*","limits.*","battery.*","motor.*","tire.*","aero.*","brakes.*","suspension.*"],s:["src/lapsim/core/telemetry.py",["src/vehicle_model/vehicle.py","update_telemetry"]]}),
      N("endurance-result","EnduranceRunResult","output","implemented","",{o:["Completion/failure","Lap times","Driving time","Pack energy","SOC","Start/end speed","Accepted and failed-cell fields","Optional telemetry"],s:[["src/lapsim/events/endurance.py","EnduranceRunResult"]]}),
      N("event-result","Common EventResult","output","implemented","",{o:["Estimated points","Maximum points","Point breakdown","Scoring and elapsed time","Energy","Status","Telemetry"],s:[["src/lapsim/events/api.py","EventResult"],"docs/event_simulation.md"]}),
      N("run-records","Versioned saved run records","data","implemented","Persist effective vehicle, manifest, course/grid, settings, start state, status, and telemetry so results remain auditable.",{s:["src/lapsim/experiments/run_record.py","src/lapsim/experiments/lap_replay.py"]}),
      N("replay","Exact-path and control replay","validation","implemented","Reconstruct inputs and compare deterministic state/telemetry outputs; saved per-cell grip schedules are reapplied when present.",{s:["src/lapsim/data/replay.py","src/lapsim/experiments/lap_replay.py"]}),
      N("plots-playback","Desktop plots and Driver view","output","implemented","Course map, speed/forces/energy traces, selected-path evidence, and synchronized vehicle playback consume frozen run records.",{s:["src/lapsim/ui/driver_view.py","src/lapsim/solvers/plotting.py"]}),
      N("scoring","Event scoring","output","implemented","",{s:["src/lapsim/events/scoring.py"]},[
        N("timed-score","Acceleration/skidpad ratio score","equation","implemented","",{e:["R = [(T_max/T)^p - 1] / [(T_max/T_min)^p - 1]","points = P_min + (P_max-P_min)*R, clipped to event bounds","p=1 acceleration; p=2 skidpad"],s:[["src/lapsim/events/scoring.py","TimedEventScoring.score"]]}),
        N("endurance-score","Endurance time and lap points","equation","implemented","",{e:["lap_points = min(completed_laps+1 + 2 after driver-change threshold, 25)","time_points = P_end,max * [(T_max/T)-1]/[(T_max/T_min)-1] when fully eligible"],s:[["src/lapsim/events/scoring.py","FSAEEnduranceEfficiencyScoring.score"]]}),
        N("efficiency-score","Efficiency score","equation","implemented","",{e:["adjusted_energy_per_lap = energy_kWh*conversion/completed_laps","EF = (fastest_avg_lap/avg_lap)*(minimum_adjusted_energy/adjusted_energy)","efficiency_points = P_eff,max * clip((EF-EF_min)/(EF_max-EF_min),0,1)"],s:["src/lapsim/events/scoring.py"]})
      ])
    ])
  );
})();
