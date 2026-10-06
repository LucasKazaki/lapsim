"""End-to-end desktop wiring for the optional, assumed-corridor path mode."""

from __future__ import annotations

from dataclasses import replace
from math import pi
from pathlib import Path
import tkinter as tk
from unittest.mock import patch

import numpy as np
import pytest

from lapsim.experiments import RunRecord, replay_lap_record
from lapsim.events.endurance import LapProgressSnapshot
from lapsim.courses.spatial_track import SpatialTrack
from lapsim.ui.app import LapSimDesktop, _course_geometry_warning
from lapsim.ui.course_catalog import COURSE_OPTIONS, SYNTHETIC_DEMO_COURSE_ID
from lapsim.ui.presets import VehicleSetup


def test_course_warning_includes_arc_chord_mismatch_without_chord_excess() -> None:
    square = SpatialTrack(
        distance_m=(0.0, 10.0, 20.0, 30.0, 40.0),
        x_m=(0.0, 10.0, 10.0, 0.0, 0.0),
        y_m=(0.0, 0.0, 10.0, 10.0, 0.0),
        curvature_per_m=(pi / 20.0,) * 4,
    )
    audit = square.geometry_audit()
    assert audit.cells_with_chord_excess == 0
    warning = _course_geometry_warning(audit)
    assert warning is not None
    assert "prescribed arc chord length differs" in warning
    barely_over_threshold = replace(
        audit,
        maximum_arc_chord_mismatch_m=1.1e-6,
        curvature_integrated_closure_gap_m=0.0101,
    )
    precise_warning = _course_geometry_warning(barely_over_threshold)
    assert precise_warning is not None
    assert "1.1e-06 m" in precise_warning
    assert "0.0101 m" in precise_warning


def test_live_view_clears_old_numbers_and_distinguishes_empty_failure() -> None:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    try:
        app = LapSimDesktop(root)
        for value in app.driver_values.values():
            value.set("previous run")
        for value in app.output_values.values():
            value.configure(text="previous run")
        app.driver_progress_var.set(700.0)
        with patch("lapsim.ui.app.threading.Thread"):
            app._start_run()

        assert app._active_tab == "Driver view"
        assert app.driver_playback is None
        assert app.driver_progress_var.get() == 0.0
        assert all(value.get() == "—" for value in app.driver_values.values())
        assert all(value["text"] == "—" for value in app.output_values.values())
        app.result_queue.put(("single", None, RuntimeError("planning failed")))
        with patch("lapsim.ui.app.messagebox.showerror"):
            app._poll_result()
        assert app.driver_run_label.get() == (
            "No accepted model step · calculation ended"
        )

        with patch("lapsim.ui.app.threading.Thread"):
            app._start_run()
        station_m = app.track.distance_m[1]
        app._queue_live_progress(
            "Prius", "Centerline model", app.track,
            LapProgressSnapshot(
                lap_index=0, cell_index=0, cell_count=app.track.cell_count,
                elapsed_time_s=1.0, lap_station_m=station_m,
                total_distance_m=station_m, speed_mps=4.0,
                lateral_acceleration_mps2=0.0,
            ),
        )
        app._poll_live_progress()
        assert app.driver_values["speed"].get() == "14.4"
        app.result_queue.put(("single", None, RuntimeError("later failure")))
        with patch("lapsim.ui.app.messagebox.showerror"):
            app._poll_result()
        assert app.driver_run_label.get().startswith("Last accepted step · ")
        assert app.driver_values["speed"].get() == "14.4"
    finally:
        root.destroy()


def test_ai_path_keeps_invalid_model_trials_as_diagnostics(tmp_path: Path) -> None:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    try:
        app = LapSimDesktop(root)
        assert app.driving_mode_var.get() == "Centerline (default)"
        assert app.course_geometry_audit.cells_with_chord_excess == 1441
        assert app.course_geometry_audit.curvature_integrated_closure_gap_m == pytest.approx(
            542.633, abs=0.01
        )
        warning = [
            widget.cget("text")
            for widget in app._walk_widgets(root)
            if widget.winfo_class() == "Label"
            and "Course data mismatch" in widget.cget("text")
        ]
        assert len(warning) == 1
        assert "542.633 m" in warning[0]
        with patch("lapsim.ui.app.threading.Thread") as worker:
            app._start_run()
            assert worker.call_args.kwargs["target"].__name__ == "_calculate_single"
        app._set_busy(False)
        app.driving_mode_var.set("AI racing line (experimental)")
        app._on_driving_mode_change()
        with patch("lapsim.ui.app.threading.Thread") as worker:
            app._start_run()
            assert worker.call_args.kwargs["target"].__name__ == "_calculate_ai_single"
            assert worker.call_args.kwargs["args"][-1] == (2.0, 1.8, 0.2)
        app._set_busy(False)
        with patch("lapsim.ui.app.default_run_directory", return_value=tmp_path):
            app._calculate_ai_single(
                "prius_2026_le", "Prius geometry diagnostic", VehicleSetup(),
                1.0, 1.0, (2.0, 1.78308, 0.3),
            )
            kind, payload, error = app.result_queue.get_nowait()
            assert error is None, error
            assert kind == "ai_single"
            assert app.progress_queue.qsize() == 1
            app._set_busy(True)
            app._poll_live_progress()
            assert "Three-quarter AI line" in app.driver_run_label.get()
            app.result_queue.put((kind, payload, error))
            app._poll_result()
            root.update()

        plan, comparison = payload[4], payload[5]
        assert payload[3] == "no_comparable_path"
        assert comparison.rank_status == "invalid_processed_baseline"
        assert comparison.baseline_time_s is None
        assert comparison.candidate_time_s is None
        assert comparison.baseline_diagnostic_time_s == pytest.approx(87.618366, abs=0.001)
        assert comparison.candidate_diagnostic_time_s == pytest.approx(87.365597, abs=0.001)
        assert comparison.candidate_strength == 0.75
        assert comparison.baseline_path_audit is not None
        assert comparison.baseline_path_audit.maximum_corridor_excess_m > 0.09
        assert comparison.baseline_path_audit.seam_position_error_m > 0.75
        assert all(trial.lap_time_s is None for trial in comparison.trials)
        assert all(trial.diagnostic_lap_time_s is not None for trial in comparison.trials)
        assert app._last_result is None
        assert app._active_tab == "Driver view"
        assert app.driver_playback is not None
        assert app.ai_compare_button is not None
        assert app.ai_compare_button["state"] == "disabled"
        assert app.ai_output_values["baseline"]["text"].endswith("*")
        assert app.ai_output_values["candidate"]["text"].endswith("*")
        assert app.ai_output_values["difference"]["text"] == "—"
        assert "cannot be ranked" in app.ai_result_text.get()
        assert "sampled excess" in app.ai_result_text.get()
        assert "other states need not be periodic" in app.ai_result_text.get()
        assert app.driver_replay_var.get() == "Geometric centerline · diagnostic"
        assert app.driver_replay_menu is not None
        assert app.driver_replay_menu["state"] == "normal"
        before_windows = sum(isinstance(child, tk.Toplevel) for child in root.winfo_children())
        app._show_path_comparison()
        assert sum(isinstance(child, tk.Toplevel) for child in root.winfo_children()) == before_windows

        records = list(tmp_path.glob("*.json"))
        assert len(records) == 4
        selected_path = tmp_path / f"{payload[7]}.json"
        selected = RunRecord.load(selected_path).to_dict()
        planning = selected["settings"]["path_planning"]
        assert planning["mode"] == "experimental_racing_line"
        assert planning["algorithm"].endswith("v5_adaptive_strength")
        assert planning["selected_mode"] == "no_comparable_path"
        assert planning["diagnostic_only"] is True
        assert planning["rank_status"] == "invalid_processed_baseline"
        assert planning["comparison_is_valid"] is False
        assert planning["selection_margin_s"] == 0.05
        assert planning["baseline_lap_time_s"] is None
        assert planning["candidate_lap_time_s"] is None
        assert planning["baseline_diagnostic_lap_time_s"] == pytest.approx(
            comparison.baseline_diagnostic_time_s
        )
        assert planning["source_geometry_audit"]["curvature_integrated_closure_gap_m"] == pytest.approx(
            542.633, abs=0.01
        )
        assert planning["processed_baseline_geometry_audit"][
            "curvature_integrated_closure_gap_m"
        ] == pytest.approx(0.750897, abs=0.001)
        assert planning["baseline_sampled_path_audit"]["valid"] is False
        assert len(planning["candidate_trials"]) == 3
        assert all(trial["sampled_path_audit"]["valid"] is False
                   for trial in planning["candidate_trials"])
        assert planning["trial_record_manifest_version"] == 1
        assert planning["baseline_record"]["record_role"] == "selected_result"
        for trial, trial_row in zip(comparison.trials, planning["candidate_trials"], strict=True):
            assert trial_row["offset_strength"] == trial.strength
            assert trial_row["record_role"] in ("comparison_counterpart", "candidate_trial")
            trial_path = tmp_path / f"{trial_row['run_id']}.json"
            assert trial_path.exists()
            saved_trial = RunRecord.load(trial_path).to_dict()
            saved_planning = saved_trial["settings"]["path_planning"]
            assert saved_planning["comparison_rank_status"] == comparison.rank_status
            assert saved_planning["diagnostic_only"] is True
            assert saved_planning["comparable_with_baseline"] is False
            assert saved_trial["settings"]["track"]["length_m"] == pytest.approx(
                trial.track.length_m
            )
            assert replay_lap_record(trial_path).model_agreement
        assert selected["settings"]["track"]["length_m"] == pytest.approx(
            plan.baseline_track.length_m
        )
        assert abs(selected["result"]["seam_speed_delta_mps"]) <= 0.005
        counterpart_id = planning["comparison_counterpart_run_id"]
        assert counterpart_id and counterpart_id != payload[7]
        counterpart_path = tmp_path / f"{counterpart_id}.json"
        counterpart = RunRecord.load(counterpart_path).to_dict()
        counterpart_planning = counterpart["settings"]["path_planning"]
        assert counterpart_planning["comparison_role"] == "candidate_trial"
        assert counterpart_planning["rank_status"] == "invalid_processed_baseline"
        assert counterpart_planning["sampled_path_audit"]["valid"] is False
        assert counterpart["settings"]["track"]["length_m"] == pytest.approx(
            comparison.candidate_track.length_m
        )
        assert replay_lap_record(selected_path).model_agreement
        assert replay_lap_record(counterpart_path).model_agreement
        app._select_driver_replay("Best tested AI path · 0.75x offset · diagnostic")
        assert app.driver_playback is not None
        assert app.driver_playback.track.length_m == pytest.approx(
            comparison.candidate_track.length_m
        )
        app._select_driver_replay("AI offset 1x · diagnostic")
        assert app.driver_playback is not None
        assert app.driver_playback.track is comparison.trials[0].track
    finally:
        root.destroy()


def test_synthetic_course_switch_and_eligible_ai_demo(tmp_path: Path) -> None:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    try:
        app = LapSimDesktop(root)
        app._last_result = object()
        app.output_values["lap_time"].configure(text="old course")
        app._select_course(COURSE_OPTIONS[1].label)
        assert app.course_spec.course_id == SYNTHETIC_DEMO_COURSE_ID
        assert app.track.length_m == pytest.approx(195.398223686, abs=1e-6)
        assert app.driving_mode_var.get() == "Centerline (default)"
        assert app._last_result is None
        assert app.output_values["lap_time"]["text"] == "—"
        assert "Synthetic closed calculation course" in app.course_warning_label.cget("text")
        assert "Course data mismatch" not in app.course_warning_label.cget("text")
        assert (app.ai_half_width_var.get(), app.ai_vehicle_width_var.get(),
                app.ai_margin_var.get()) == ("3", "1.8", "0.2")
        assert "Synthetic" in app.footer_label.cget("text")
        app.inputs["solver_step_m"].set("0.0391")
        with pytest.raises(ValueError, match="5000-cell compute cap"):
            app._read_run_settings()
        app.inputs["solver_step_m"].set("1")
        app._set_busy(True)
        assert app.course_menu["state"] == "disabled"
        app._select_course(COURSE_OPTIONS[0].label)
        assert app.course_spec.course_id == SYNTHETIC_DEMO_COURSE_ID
        app._set_busy(False)

        app.driving_mode_var.set("AI racing line (experimental)")
        app._on_driving_mode_change()
        with patch("lapsim.ui.app.default_run_directory", return_value=tmp_path):
            app._calculate_ai_single(
                "prius_2026_le", "Prius synthetic AI demo",
                VehicleSetup(torque_request_fraction=0.8), 1.0, 0.8,
                (3.0, 1.8, 0.2),
            )
            kind, payload, error = app.result_queue.get_nowait()
            assert error is None, error
            assert kind == "ai_single"
            app._set_busy(True)
            app.result_queue.put((kind, payload, error))
            app._poll_result()
            root.update()

        plan, comparison = payload[4], payload[5]
        assert payload[3] == "candidate"
        assert comparison.rank_status == "candidate_selected"
        assert comparison.candidate_strength == 0.75
        assert comparison.baseline_time_s == pytest.approx(16.885573, abs=0.002)
        assert comparison.candidate_time_s == pytest.approx(15.007724, abs=0.002)
        assert comparison.baseline_path_audit is not None
        assert comparison.baseline_path_audit.valid
        assert comparison.candidate_path_audit is not None
        assert comparison.candidate_path_audit.valid
        assert app._last_result is comparison.candidate_run
        assert app.ai_compare_button is not None
        assert app.ai_compare_button["state"] == "normal"
        assert app.ai_output_values["difference"]["text"].startswith("-")
        assert app.ai_result_text.get().startswith("SYNTHETIC AI DEMO.")
        assert "Faster AI path selected" in app.ai_result_text.get()
        assert "default lap uses different source curvature" not in app.ai_result_text.get()
        assert app.driver_playback is not None
        assert app.driver_playback.track is comparison.candidate_track
        assert app.driver_replay_menu is not None
        assert app.driver_replay_menu["state"] == "normal"
        app._select_driver_replay("AI offset 0.5x")
        assert app.driver_playback is not None
        assert app.driver_playback.track is comparison.trials[1].track
        assert "Synthetic loop" in app.course_ax.get_title(loc="left")

        records = list(tmp_path.glob("*.json"))
        assert len(records) == 4
        primary_path = tmp_path / f"{payload[7]}.json"
        primary = RunRecord.load(primary_path).to_dict()
        planning = primary["settings"]["path_planning"]
        assert primary["settings"]["track"]["id"].startswith(
            SYNTHETIC_DEMO_COURSE_ID
        )
        assert planning["source_course_id"] == SYNTHETIC_DEMO_COURSE_ID
        assert planning["synthetic_course"] is True
        assert planning["algorithm"].endswith("v5_adaptive_strength")
        assert planning["fourth_strength_policy"] == (
            "eligible_quadratic_grid_v1_fallback_0.75"
        )
        counterpart_id = planning["comparison_counterpart_run_id"]
        counterpart = RunRecord.load(tmp_path / f"{counterpart_id}.json").to_dict()
        counterpart_planning = counterpart["settings"]["path_planning"]
        assert counterpart_planning["algorithm"] == planning["algorithm"]
        assert counterpart_planning["fourth_strength_policy"] == (
            planning["fourth_strength_policy"]
        )
        assert planning["comparison_is_valid"] is True
        assert planning["diagnostic_only"] is False
        assert planning["selected_mode"] == "candidate"
        assert planning["selected_offset_strength"] == 0.75
        assert planning["trial_record_manifest_version"] == 1
        assert planning["baseline_record"]["run_id"] == counterpart_id
        assert planning["baseline_record"]["record_role"] == "comparison_counterpart"
        for trial, trial_row in zip(comparison.trials, planning["candidate_trials"], strict=True):
            assert trial_row["offset_strength"] == trial.strength
            if trial.run is comparison.candidate_run:
                assert trial_row["record_role"] == "selected_result"
                assert trial_row["run_id"] is None
                continue
            assert trial_row["record_role"] == "candidate_trial"
            trial_path = tmp_path / f"{trial_row['run_id']}.json"
            assert trial_path.exists()
            saved_trial = RunRecord.load(trial_path).to_dict()
            saved_planning = saved_trial["settings"]["path_planning"]
            assert saved_planning["comparison_rank_status"] == comparison.rank_status
            assert saved_planning["diagnostic_only"] == (trial.lap_time_s is None)
            assert saved_planning["comparable_with_baseline"] == (
                trial.lap_time_s is not None
            )
            assert saved_trial["settings"]["track"]["length_m"] == pytest.approx(
                trial.track.length_m
            )
            assert replay_lap_record(trial_path).model_agreement
        assert planning["processed_baseline_geometry_audit"][
            "curvature_integrated_closure_gap_m"
        ] < 0.01
        assert replay_lap_record(primary_path).model_agreement
        assert plan.baseline_track.length_m > comparison.candidate_track.length_m
        app._show_path_comparison()
        popup = next(child for child in root.winfo_children() if isinstance(child, tk.Toplevel))
        popup_text = " ".join(
            child.cget("text") for child in app._walk_widgets(popup)
            if child.winfo_class() == "Label"
        )
        assert "Course: Synthetic loop · AI demo" in popup_text
        assert "synthetic course demonstrates" in popup_text
        assert "source x/y map and recorded curvature disagree" not in popup_text

        # An interrupted extra trial retains its failure summary, while the
        # completed baseline and other offsets still have linked records.
        from lapsim.optimization import racing_line

        real_compare = racing_line.compare_lines_with_lap_model

        def interrupted_full_trial(*args, **kwargs):
            modeled = real_compare(*args, **kwargs)
            full = modeled.trials[0]
            assert full.run is not None
            interrupted = replace(
                full,
                run=replace(
                    full.run, completed_laps=0,
                    failure_reason="Synthetic interrupted probe",
                ),
                diagnostic_lap_time_s=None,
                error="Synthetic interrupted probe",
            )
            return replace(modeled, trials=(interrupted, *modeled.trials[1:]))

        incomplete_dir = tmp_path / "incomplete_trial"
        with patch.object(
            racing_line, "compare_lines_with_lap_model",
            side_effect=interrupted_full_trial,
        ), patch("lapsim.ui.app.default_run_directory", return_value=incomplete_dir):
            app._calculate_ai_single(
                "prius_2026_le", "Prius synthetic incomplete trial",
                VehicleSetup(torque_request_fraction=0.8), 1.0, 0.8,
                (3.0, 1.8, 0.2),
            )
            interrupted_kind, interrupted_payload, interrupted_error = (
                app.result_queue.get_nowait()
            )
        assert interrupted_kind == "ai_single"
        assert interrupted_error is None
        assert len(list(incomplete_dir.glob("*.json"))) == 3
        interrupted_primary = RunRecord.load(
            incomplete_dir / f"{interrupted_payload[7]}.json"
        ).to_dict()
        interrupted_planning = interrupted_primary["settings"]["path_planning"]
        assert interrupted_planning["candidate_trials"][0]["run_id"] is None
        assert interrupted_planning["candidate_trials"][0]["record_role"] == (
            "unsaved_incomplete"
        )
        assert interrupted_planning["candidate_trials"][0]["model_run_completed"] is False
        assert (incomplete_dir / f"{interrupted_planning['baseline_record']['run_id']}.json").exists()
        assert (incomplete_dir / f"{interrupted_planning['candidate_trials'][1]['run_id']}.json").exists()
        app._select_course(COURSE_OPTIONS[0].label)
        assert app.course_spec.course_id != SYNTHETIC_DEMO_COURSE_ID
        assert "Course: Synthetic loop · AI demo" in " ".join(
            child.cget("text") for child in app._walk_widgets(popup)
            if child.winfo_class() == "Label"
        )
    finally:
        root.destroy()


def test_synthetic_centerline_run_records_selected_course(tmp_path: Path) -> None:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    try:
        app = LapSimDesktop(root)
        app._select_course(COURSE_OPTIONS[1].label)
        assert app.driving_mode_var.get() == "Centerline (default)"
        with patch("lapsim.ui.app.default_run_directory", return_value=tmp_path):
            app._calculate_single(
                "prius_2026_le", "Prius synthetic centerline",
                VehicleSetup(torque_request_fraction=0.8), 5.0, 0.8,
            )
        kind, payload, error = app.result_queue.get_nowait()
        assert error is None, error
        assert kind == "single"
        assert payload[2].completed
        record = RunRecord.load(tmp_path / f"{payload[3]}.json").to_dict()
        assert record["settings"]["track"]["id"] == SYNTHETIC_DEMO_COURSE_ID
        assert record["settings"].get("path_planning") is None
        assert record["settings"]["solver"]["requested_maximum_cell_length_m"] == 5.0
        geometry = record["settings"]["track"]["geometry"]
        saved_track = SpatialTrack(
            distance_m=tuple(geometry["distance_m"]),
            x_m=tuple(geometry["x_m"]),
            y_m=tuple(geometry["y_m"]),
            curvature_per_m=tuple(geometry["curvature_per_m"]),
            closed=geometry["closed"],
        )
        assert saved_track.cell_count == app.track.cell_count
        assert saved_track.geometry_audit().curvature_integrated_closure_gap_m < 1e-7
        app._show_comparison(
            (("Car A", payload[2]), ("Car B", payload[2])),
            5.0, 0.8, (payload[3], payload[3]),
        )
        popup = next(child for child in root.winfo_children() if isinstance(child, tk.Toplevel))
        popup_text = " ".join(
            child.cget("text") for child in app._walk_widgets(popup)
            if child.winfo_class() == "Label"
        )
        assert "Course: Synthetic loop · AI demo" in popup_text
        assert "synthetic course model comparisons" in popup_text
        app._select_course(COURSE_OPTIONS[0].label)
        assert "Course: Synthetic loop · AI demo" in " ".join(
            child.cget("text") for child in app._walk_widgets(popup)
            if child.winfo_class() == "Label"
        )
    finally:
        root.destroy()


def test_completed_fused_centerline_playback_uses_saved_solver_grid(
    tmp_path: Path,
) -> None:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    try:
        app = LapSimDesktop(root)
        with patch("lapsim.ui.app.default_run_directory", return_value=tmp_path):
            app._calculate_single(
                "prius_2026_le", "Prius fused centerline",
                VehicleSetup(torque_request_fraction=0.8), 5.0, 0.8,
            )
        kind, payload, error = app.result_queue.get_nowait()
        assert error is None, error
        assert kind == "single"
        assert payload[2].completed
        solver_track = payload[4]
        assert solver_track is not app.track
        assert solver_track.cell_count == 198
        record = RunRecord.load(tmp_path / f"{payload[3]}.json").to_dict()
        geometry = record["settings"]["track"]["geometry"]
        assert geometry["x_m"] == pytest.approx(solver_track.x_m)
        assert geometry["y_m"] == pytest.approx(solver_track.y_m)

        app.result_queue.put((kind, payload, None))
        app._poll_result()
        app._pause_driver_playback()
        assert app.driver_playback is not None
        assert app.driver_playback.track is solver_track
        stations = np.asarray(app.track.distance_m)
        solver_x = np.interp(stations, solver_track.distance_m, solver_track.x_m)
        solver_y = np.interp(stations, solver_track.distance_m, solver_track.y_m)
        map_delta = np.hypot(
            solver_x - np.asarray(app.track.x_m),
            solver_y - np.asarray(app.track.y_m),
        )
        index = int(np.argmax(map_delta))
        assert map_delta[index] > 1.0
        assert app.driver_playback.point_at(float(stations[index])) == pytest.approx(
            (solver_x[index], solver_y[index])
        )
    finally:
        root.destroy()
