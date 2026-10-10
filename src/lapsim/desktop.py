"""Portable desktop entry point and an executable-level integration check."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import traceback


def self_test(report_path: Path) -> dict:
    from .ui._tk_runtime import configure_tk_libraries
    configure_tk_libraries()
    import tkinter as tk
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    from .resources import build_identity, documentation_root, repository_root
    from .ui.app import LapSimDesktop
    from .ui.dynamics_lab import DynamicsLab
    from .ui.simulation import load_team_endurance_track, run_one_lap
    from .courses.spatial_track import SpatialTrack
    from .courses.track import Curve, Track
    from .events.endurance import EnduranceRunConfig
    from .experiments import LapRunSettings, RunRecord, capture_lap_run
    from .experiments.lap_replay import replay_lap_record
    from .profiles import build_vehicle
    from math import pi
    from tempfile import TemporaryDirectory

    checks = {}
    root = tk.Tk()
    root.withdraw()
    try:
        canvas = FigureCanvasTkAgg(Figure(figsize=(2, 1.5)), master=root)
        canvas.draw()
        canvas.get_tk_widget().destroy()
        checks["tkagg_canvas"] = True
        app = LapSimDesktop(root)
        root.update_idletasks()
        checks["desktop_widgets"] = not app._closed
        lab = DynamicsLab(root, dark=False)
        root.update_idletasks()
        checks["four_wheel_lab_widgets"] = True
        # Child widgets are destroyed by root, allowing their lifecycle hooks to run.
    finally:
        root.destroy()
    team_track = load_team_endurance_track()
    checks["bundled_course"] = team_track.cell_count > 0
    checks["bundled_course_provenance"] = (
        repository_root() / "analysis/data/track/gnss_imu_endurance_track.json"
    ).is_file()
    checks["offline_map"] = (repository_root() / "docs/simulator_flowchart/index.html").is_file()
    offline = documentation_root()
    checks["offline_source_links"] = all((offline / name).is_file() for name in (
        "launch_lapsim.cmd", "setup_lapsim.ps1", "packaging/LapSim.spec",
        "src/vehicle_model/vehicle.py", "output/pdf/LapSim_Engineering_Handoff.pdf",
    ))
    track = SpatialTrack.from_track(
        Track.from_segments([Curve(25.0, 2.0 * pi)]), maximum_cell_length_m=5.0,
    )
    vehicle, manifest = build_vehicle("repository_baseline")
    result = run_one_lap(vehicle, track, torque_request_fraction=0.8)
    if not result.completed:
        raise RuntimeError(result.failure_reason)
    checks["synthetic_lap"] = True
    settings = LapRunSettings.from_track(
        track, track_id="portable_self_test", solver_step_m=5.0,
        solver_settings={"convergence_tolerance_mps": 0.005, "maximum_passes": 120},
        torque_request_fraction=0.8, endurance_config=EnduranceRunConfig(laps=1),
        profile_id="repository_baseline", profile_label="Portable integration check",
    )
    with TemporaryDirectory(prefix="lapsim-check-") as temporary:
        record_path = Path(temporary) / "lap.json"
        record = capture_lap_run(result, manifest, settings, actual_vehicle=vehicle)
        record.save(record_path)
        checks["record_round_trip"] = RunRecord.load(record_path).run_id == record.run_id
        replay = replay_lap_record(record_path)
        checks["recorded_control_replay"] = replay.model_agreement and replay.replay_completed
        if not checks["recorded_control_replay"]:
            raise RuntimeError(str(replay.mismatch_reasons))
    report = {
        "status": "passed" if all(checks.values()) else "failed",
        "frozen": bool(getattr(sys, "frozen", False)), "checks": checks,
        "build": build_identity(), "course_cells": team_track.cell_count,
        "synthetic_lap_time_s": result.driving_time_s,
        "telemetry_samples": result.telemetry.sample_count,
        "replay": replay.to_dict(),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[variable] = "1"
    parser = argparse.ArgumentParser(description="LapSim portable desktop simulator")
    parser.add_argument("--flow-map", action="store_true", help="Open the offline simulator map")
    parser.add_argument("--self-test", type=Path, metavar="REPORT.json", help="Check GUI, assets, simulation, save and replay")
    args = parser.parse_args()
    try:
        if args.self_test is not None:
            return 0 if self_test(args.self_test)["status"] == "passed" else 1
        if args.flow_map:
            from .resources import open_simulator_map
            return 0 if open_simulator_map() else 1
        from .ui._tk_runtime import configure_tk_libraries
        configure_tk_libraries()
        from .ui.app import main as start_app
        start_app()
        return 0
    except Exception:
        details = traceback.format_exc()
        if args.self_test is not None:
            args.self_test.parent.mkdir(parents=True, exist_ok=True)
            args.self_test.write_text(json.dumps({"status": "failed", "error": details}, indent=2), encoding="utf-8")
        else:
            base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".lapsim")
            log = base / "LapSim/logs/desktop_startup.log"
            try:
                log.parent.mkdir(parents=True, exist_ok=True)
                log.write_text(details, encoding="utf-8")
                message = f"LapSim could not start. Details were saved to:\n{log}"
            except OSError:
                message = details[-1800:]
            if sys.platform == "win32":
                from ctypes import windll
                windll.user32.MessageBoxW(None, message, "LapSim startup error", 0x10)
            elif sys.stderr:
                print(details, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
