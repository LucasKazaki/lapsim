"""Portable desktop entry point and an executable-level integration check."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import traceback


def _check_self_test_paths(report_path: Path, native_record_path: Path | None) -> None:
    if native_record_path is not None and (
        report_path.resolve() == native_record_path.resolve()
        or (report_path.exists() and report_path.samefile(native_record_path))
    ):
        raise ValueError("Self-test report must not overwrite its native record input")


def _check_native_record_viewer(root, native_record_path: Path | None = None) -> dict:
    """Exercise only the passive viewer, optionally against a supplied record."""
    from hashlib import sha256
    import time
    import tkinter as tk
    from .experiments.suspension_study import MAX_BYTES
    from .ui.native_record_viewer import NativeRecordViewer

    def bounded_bytes(path):
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Native self-test record exceeds the 8 MB limit")
        return raw

    viewer = NativeRecordViewer(root)
    try:
        root.update_idletasks()
        result = {
            "empty_viewer_widgets": viewer.window.winfo_exists() == 1,
            "saved_record": {"status": "not_requested"},
        }
        if native_record_path is None:
            return result
        before_stat = native_record_path.stat()
        before = bounded_bytes(native_record_path)
        expected = json.loads(before)
        if not viewer.load_path(native_record_path):
            raise RuntimeError("Native viewer did not accept the load request")
        deadline = time.monotonic() + 10
        while viewer.busy and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        if viewer.record is None or viewer.busy:
            raise RuntimeError(
                "Native saved-record workflow failed: " + viewer.status.get()
            )
        if any(
            viewer.record[key] != expected[key] for key in ("content_id", "receipt_id")
        ):
            raise RuntimeError("Native viewer changed saved record identity")
        samples = expected["payload"]["samples"]
        settle_s = expected["payload"]["scenario"]["settle_s"]
        settle_index = next(
            index
            for index, sample in enumerate(samples)
            if abs(sample["time_s"] - settle_s) <= 1e-9
        )
        selected = []
        for index in dict.fromkeys((0, settle_index, len(samples) - 1)):
            sample = samples[index]
            viewer.select(index)
            if viewer.selected_sample != sample:
                raise RuntimeError("Native viewer selected a different exported sample")
            if list(viewer.com_marker.get_xdata()) != [sample["position_m"][0]]:
                raise RuntimeError("Native viewer COM plot differs from saved sample")
            for kind, clock_key, force_key in (
                (
                    "Applied",
                    "applied_tire_force_source_time_s",
                    "applied_wheel_force_world_n",
                ),
                ("Computed", "tire_force_source_time_s", "wheel_force_world_n"),
            ):
                viewer.force_kind.set(kind)
                viewer.change_force()
                root.update()
                if not viewer.force_plot_available:
                    raise RuntimeError(
                        "Native self-test force channel could not be plotted"
                    )
                for wheel, marker in enumerate(viewer.force_markers):
                    clock = sample[clock_key]
                    if marker.get_visible() != (clock is not None):
                        raise RuntimeError("Native viewer fabricated a force timestamp")
                    if clock is not None and (
                        list(marker.get_xdata()) != [clock]
                        or list(marker.get_ydata()) != [sample[force_key][wheel][2]]
                    ):
                        raise RuntimeError(
                            "Native force plot differs from stored force/source clock"
                        )
            selected.append(
                {
                    "index": index,
                    "clocks": {
                        key: sample[key]
                        for key in (
                            "time_s",
                            "tire_force_source_time_s",
                            "tire_kinematics_source_time_s",
                            "applied_tire_force_source_time_s",
                            "applied_tire_force_geometry_time_s",
                        )
                    },
                    "completed_interval_command": sample["command"],
                }
            )
        details = viewer.inspect()
        if details is None or viewer.summary is None:
            raise RuntimeError(
                "Native viewer details or inspection summary are unavailable"
            )
        text = next(
            widget for widget in details.winfo_children() if isinstance(widget, tk.Text)
        )
        detail_value = json.loads(text.get("1.0", "end"))
        if (
            text.cget("state") != "disabled"
            or detail_value["selected_sample"] != samples[-1]
        ):
            raise RuntimeError(
                "Native viewer details are not the read-only selected sample"
            )
        details.destroy()
        after = bounded_bytes(native_record_path)
        after_stat = native_record_path.stat()
        if before != after or before_stat.st_mtime_ns != after_stat.st_mtime_ns:
            raise RuntimeError("Native viewer changed its input file")
        result["saved_record"] = {
            "status": "passed",
            "content_id": expected["content_id"],
            "receipt_id": expected["receipt_id"],
            "input_sha256": sha256(before).hexdigest(),
            "input_mtime_ns_before": before_stat.st_mtime_ns,
            "input_mtime_ns_after": after_stat.st_mtime_ns,
            "selected_samples": selected,
            "force_channels": ["Applied", "Computed"],
            "inspection_checks": viewer.summary["checks"],
            "scope": "saved telemetry only; no fresh native replay or physics",
        }
        return result
    finally:
        viewer.close()


def self_test(report_path: Path, *, native_record_path: Path | None = None) -> dict:
    _check_self_test_paths(report_path, native_record_path)
    from .ui._tk_runtime import configure_tk_libraries
    configure_tk_libraries()
    import tkinter as tk
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    from .resources import build_identity, documentation_root, repository_root
    from .ui.app import LapSimDesktop
    from .ui.dynamics_lab import DynamicsLab
    from .ui.basic_dynamics import BasicDynamicsLab
    from .experiments.basic_dynamics import decode_json, replay_bicycle_record
    from .experiments.control_study import replay_control_comparison
    from .experiments.component_study import replay_component_comparison
    from .ui.simulation import load_team_endurance_track, run_one_lap
    from .courses.spatial_track import SpatialTrack
    from .courses.track import Curve, Track
    from .events.endurance import EnduranceRunConfig
    from .experiments import LapRunSettings, RunRecord, capture_lap_run
    from .experiments.lap_replay import replay_lap_record
    from .profiles import build_vehicle
    from math import pi
    from tempfile import TemporaryDirectory
    import time

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
        native_viewer = _check_native_record_viewer(root, native_record_path)
        checks["native_record_viewer_widgets"] = native_viewer["empty_viewer_widgets"]
        if native_record_path is not None:
            checks["native_saved_record_workflow"] = native_viewer["saved_record"]["status"] == "passed"
        basic = BasicDynamicsLab(root)
        root.update_idletasks()
        checks["basic_bicycle_default"] = basic.model_id.get() == "dynamic_bicycle_v1"
        basic.inputs["duration"].set("0.2")
        basic.run_button.invoke()
        deadline = time.monotonic() + 30
        while basic.busy and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        if basic.record is None:
            raise RuntimeError("Basic bicycle desktop execution failed: " + basic.status.get())
        bicycle_record = basic.record
        checks["basic_bicycle_ui_run"] = (
            bicycle_record["scenario"]["model_id"] == "dynamic_bicycle_v1"
            and bicycle_record["scenario"]["controller_backend_id"] == "none_prescribed_force"
            and len(basic.path_axes.lines) == 1
        )
        basic.close()
        lab.control_study_button.invoke()
        control = lab.latest_control_study
        control.inputs["duration_s"].set(".1")
        control.run_button.invoke()
        deadline = time.monotonic() + 30
        while control.busy and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        if control.record is None:
            raise RuntimeError("Control study desktop execution failed: " + control.status.get())
        control_record = control.record
        checks["control_study_ui_run"] = (
            all(run["scenario"]["controller_backend_id"] == "python_reference"
                for run in control_record["runs"].values())
            and all(len(axis.lines) == 2 for axis in control.axes.flat)
        )
        control.close()
        lab.component_study_button.invoke()
        component = lab.latest_component_study
        component.run_button.invoke()
        root.update_idletasks()
        if component.record is None:
            raise RuntimeError("Component study failed: " + component.status.get())
        component_record = component.record
        checks["component_study_ui_run"] = (
            component_record["geometry_policy"] == "fixed_geometry"
            and all(len(axis.lines) == 2 for axis in component.axes)
            and replay_component_comparison(component_record)["runs_replayed"] == 2
        )
        with TemporaryDirectory(prefix="lapsim-component-") as component_directory:
            component_path = Path(component_directory) / "comparison.json"
            component.save_to(component_path)
            component.load_from(component_path)
            checks["component_study_saved_replay"] = (
                component.record == component_record and component.imported
                and component.run_button.instate(["disabled"])
            )
            component.new()
            component.inputs["outside_b"].set(".03")
            component.run_button.invoke()
            checks["component_geometry_recomputes_mass_inertia"] = (
                component.record is not None
                and component.record["geometry_policy"] == "manual_geometry_change"
                and component.record["runs"]["B"]["result"]["nominal"]["mass_kg"]
                > component_record["runs"]["B"]["result"]["nominal"]["mass_kg"]
            )
            component.inputs["force"].set("nan")
            component.run_button.invoke()
            checks["component_invalid_input_clears_result"] = component.record is None
        component.close()
        lab.close()
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
    if result.telemetry is None:
        raise RuntimeError("Completed self-test lap is missing telemetry")
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
        bicycle_path = Path(temporary) / "bicycle.json"
        bicycle_path.write_text(json.dumps(bicycle_record, allow_nan=False), encoding="utf-8")
        checks["basic_bicycle_record_replay"] = replay_bicycle_record(
            decode_json(bicycle_path.read_bytes())
        )["model_agreement"]
        control_path = Path(temporary) / "control.json"
        control_path.write_text(json.dumps(control_record, allow_nan=False), encoding="utf-8")
        checks["control_study_record_replay"] = replay_control_comparison(
            decode_json(control_path.read_bytes(), maximum_bytes=40_000_000)
        )["model_agreement"]
    report = {
        "status": "passed" if all(checks.values()) else "failed",
        "frozen": bool(getattr(sys, "frozen", False)), "checks": checks,
        "build": build_identity(), "course_cells": team_track.cell_count,
        "synthetic_lap_time_s": result.driving_time_s,
        "telemetry_samples": result.telemetry.sample_count,
        "replay": replay.to_dict(),
        "basic_bicycle": {"run_id": bicycle_record["run_id"],
                          "model_id": bicycle_record["scenario"]["model_id"],
                          "plant_ticks": bicycle_record["result"]["plant_ticks"]},
        "control_study": {"run_id": control_record["run_id"],
                          "runs_replayed": 2, "backend_id": "python_reference"},
        "component_study": {"run_id": component_record["run_id"],
                            "runs_replayed": 2, "backend_id": "analytic_python"},
        "native_record_viewer": native_viewer,
    }
    _check_self_test_paths(report_path, native_record_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[variable] = "1"
    parser = argparse.ArgumentParser(description="LapSim portable desktop simulator")
    parser.add_argument("--flow-map", action="store_true", help="Open the offline simulator map")
    parser.add_argument("--self-test", type=Path, metavar="REPORT.json", help="Check GUI, assets, simulation, save and replay")
    parser.add_argument("--self-test-native-record", type=Path, metavar="RECORD.json", help="With --self-test, also check a supplied saved native record without physics")
    args = parser.parse_args()
    if args.self_test_native_record is not None and args.self_test is None:
        parser.error("--self-test-native-record requires --self-test")
    if args.self_test_native_record is not None:
        try:
            _check_self_test_paths(args.self_test, args.self_test_native_record)
        except (OSError, ValueError) as error:
            parser.error(str(error))
    try:
        if args.self_test is not None:
            return 0 if self_test(args.self_test, native_record_path=args.self_test_native_record)["status"] == "passed" else 1
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
            try:
                _check_self_test_paths(args.self_test, args.self_test_native_record)
                args.self_test.parent.mkdir(parents=True, exist_ok=True)
                args.self_test.write_text(json.dumps({"status": "failed", "error": details}, indent=2), encoding="utf-8")
            except (OSError, ValueError) as error:
                if sys.stderr:
                    print("Self-test report was not written: " + str(error), file=sys.stderr)
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
