"""The optional pose preview stays separate from engineering lap results."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from unittest.mock import patch

import pytest

from lapsim.dynamics.conditions import PlanarEnvironment
from lapsim.dynamics.planar import PlanarState
from lapsim.courses.spatial_track import SpatialTrack
from lapsim.optimization.pose_driver import PoseDriverSample
from lapsim.ui.app import (
    LapSimDesktop, POSE_DRIVER_NOTE, POSE_SCENARIO_PATCH,
    POSE_SCENARIO_UNIFORM, REFERENCE_DRIVER_NOTE,
)
from lapsim.ui.course_catalog import (
    COURSE_OPTIONS, SYNTHETIC_DEMO_COURSE_ID, load_course,
)
from lapsim.ui.driver_view import DriverPlayback
from lapsim.ui.pose_driver_playback import PoseDriverLivePlayback, PoseDriverPlayback


def _desktop() -> tuple[tk.Tk, LapSimDesktop]:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    return root, LapSimDesktop(root)


def test_timed_session_controls_can_scroll_into_view_at_minimum_window() -> None:
    root, app = _desktop()
    try:
        root.geometry("1080x720")
        root.deiconify()
        app._switch_tab("Timed sessions · WIP")
        root.update()
        tab = app.tab_panels["Timed sessions · WIP"]
        canvas = next(child for child in tab.winfo_children()
                      if isinstance(child, tk.Canvas))
        canvas.yview_moveto(1.0)
        root.update()
        labels = [child for child in app._walk_widgets(tab)
                  if isinstance(child, tk.Label)]
        last_label = max(labels, key=lambda child: child.winfo_rooty())
        assert last_label.winfo_rooty() + last_label.winfo_height() <= (
            canvas.winfo_rooty() + canvas.winfo_height()
        )
    finally:
        root.destroy()


def _sampled_ai_path() -> SpatialTrack:
    return SpatialTrack(
        distance_m=(0.0, 30.0, 60.0, 90.0, 120.0),
        x_m=(0.0, 30.0, 30.0, 0.0, 0.0),
        y_m=(0.0, 0.0, 30.0, 30.0, 0.0),
        curvature_per_m=(0.0, 0.0, 0.0, 0.0),
        closed=True,
    )


def _offer_selected_ai_path(
    app: LapSimDesktop, *, rank_status: str = "candidate_selected",
    selected_mode: str = "candidate", audit_valid: bool = True,
) -> SpatialTrack:
    spec = next(option for option in COURSE_OPTIONS
                if option.course_id == SYNTHETIC_DEMO_COURSE_ID)
    app._select_course(spec.label)
    app.driving_mode_var.set("AI racing line (experimental)")
    app._on_driving_mode_change()
    app.root.update_idletasks()
    track = _sampled_ai_path()
    comparison = SimpleNamespace(
        rank_status=rank_status,
        selected_mode=selected_mode,
        baseline_time_s=20.0,
        candidate_time_s=19.0,
        candidate_run=SimpleNamespace(completed=True),
        candidate_path_audit=SimpleNamespace(valid=audit_valid),
        candidate_track=track,
    )
    app._path_comparison = (object(), comparison, (3.0, 1.8, 0.2))
    app._selected_path_track = track
    app._update_pose_ai_preview_availability()
    return track


def test_pose_button_runs_separate_worker_and_displays_model_only_result() -> None:
    root, app = _desktop()
    try:
        app.driver_playback = object()
        with patch("lapsim.ui.app.threading.Thread") as thread:
            app._start_pose_preview()
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()
        assert app.run_in_progress
        assert app.pose_preview_button.cget("state") == "disabled"
        assert app.pose_scenario_menu.cget("state") == "disabled"
        assert app.pose_offset_entry.cget("state") == "disabled"
        assert app.pose_save_button.cget("state") == "disabled"
        assert app.pose_load_button.cget("state") == "disabled"
        assert app.pose_offset_var.get() == "0.0"
        scenario, offset, pose_track, reference_geometry = thread.call_args.kwargs["args"]
        assert (scenario, offset) == (POSE_SCENARIO_UNIFORM, 0.0)
        assert reference_geometry == "coherent_arcs"
        assert pose_track == load_course(SYNTHETIC_DEMO_COURSE_ID)
        assert app.pose_scenario_var.get() == POSE_SCENARIO_UNIFORM
        assert app._displayed_run_records == ()
        assert app._active_tab == "Driver view"
        assert app.driver_playback is None
        assert "Synthetic pose model" in app.driver_run_label.get()
        assert POSE_SCENARIO_UNIFORM in app.driver_run_label.get()
        assert "initial offset +0.00 m" in app.driver_run_label.get()
        assert "effective pose grid" in app.driver_run_label.get()
        assert app.driver_play_button.cget("state") == "disabled"
        assert app.driver_heading_title_label.cget("text") == "VEHICLE HEADING (°)"

        track = load_course(SYNTHETIC_DEMO_COURSE_ID)
        sample = PoseDriverSample(1.25, 40.0, 0.3, 0.1, 0.8, 1.2)
        state = PlanarState(
            x_m=34.0, y_m=1.5, heading_rad=0.4,
            u_mps=5.0, yaw_rate_rad_s=0.2,
        )
        app.pose_progress_queue.put((track, sample, state))
        app._poll_pose_progress()
        assert "40.0/80 m" in app.calculation_progress_text.get()
        assert "initial offset +0.00 m" in app.calculation_progress_text.get()
        assert "1.25 s pose-model time" in app.calculation_progress_text.get()
        assert app._calculation_progress_fraction == pytest.approx(0.5)
        assert isinstance(app.driver_playback, PoseDriverLivePlayback)
        frame = app.driver_playback.frame_at(sample.time_s)
        assert (frame.x_m, frame.y_m, frame.course_heading_rad) == pytest.approx(
            (state.x_m, state.y_m, state.heading_rad)
        )
        assert frame.distance_m == pytest.approx(sample.progress_m)
        assert frame.speed_mps == pytest.approx(5.0)
        assert app.driver_values["time"].get() == "1.25 elapsed"
        assert app.driver_values["lateral"].get() == "—"
        assert app.driver_decision_values["path_speed_ceiling_mps"].get() == "—"
        assert app.driver_decision_values["battery_power_w"].get() == "+0.30"
        assert app.driver_canvas.find_withtag("driver_live_path")

        run = SimpleNamespace(
            completed=True,
            status="target_reached",
            samples=(SimpleNamespace(progress_m=80.2),),
            settings=SimpleNamespace(target_progress_m=80.0),
            elapsed_pose_model_time_s=14.75,
            maximum_absolute_cross_track_error_m=0.263,
            minimum_assumed_boundary_slack_m=1.611,
            states=(object(), object()),
        )
        app.result_queue.put(("pose_preview", run, None))
        with patch.object(app, "_activate_pose_preview") as activate:
            app._poll_result()
        activate.assert_called_once_with(run)
        assert not app.run_in_progress
        assert app.pose_preview_button.cget("state") == "normal"
        assert app.pose_offset_entry.cget("state") == "normal"
        assert app.pose_save_button.cget("state") == "normal"
        assert app.pose_load_button.cget("state") == "normal"
        assert "not an engineering lap time" in app.pose_preview_status.get()
        assert POSE_SCENARIO_UNIFORM in app.pose_preview_status.get()
        assert "initial offset +0.00 m" in app.pose_preview_status.get()
        assert app._displayed_run_records == ()
    finally:
        root.destroy()


@pytest.mark.parametrize(
    ("scenario", "expected_grip"),
    [(POSE_SCENARIO_UNIFORM, 1.0), (POSE_SCENARIO_PATCH, 0.3)],
)
def test_pose_scenario_passes_selected_road_to_worker(
    scenario: str, expected_grip: float,
) -> None:
    root, app = _desktop()
    try:
        with patch("lapsim.ui.app.run_pose_driver", return_value=object()) as driver:
            app._calculate_pose_preview(scenario, 0.75)
        environment = driver.call_args.kwargs["environment"]
        assert driver.call_args.kwargs["settings"].initial_lateral_offset_m == 0.75
        assert environment.road.query(40.0, 0.0).friction_multiplier == expected_grip
        assert environment.road.query(20.0, 0.0).friction_multiplier == 1.0
        if scenario == POSE_SCENARIO_PATCH:
            patch_region = environment.road.patches[0]
            assert (
                patch_region.x_min_m, patch_region.x_max_m,
                patch_region.y_min_m, patch_region.y_max_m,
            ) == (36.0, 55.0, -3.0, 16.0)
        assert app.result_queue.get_nowait()[0] == "pose_preview"
    finally:
        root.destroy()


def test_pose_preview_uses_finer_frozen_cell_grid() -> None:
    root, app = _desktop()
    try:
        source = load_course(SYNTHETIC_DEMO_COURSE_ID)
        app.inputs["solver_step_m"].set("0.25")
        with patch("lapsim.ui.app.threading.Thread") as thread:
            app._start_pose_preview()
        args = thread.call_args.kwargs["args"]
        grid = args[2]
        assert grid.cell_count > source.cell_count
        assert max(grid.cell_length_m) <= 0.25 + 1e-12
        assert "requested Cell size (max) 0.25 m" in app.pose_preview_status.get()
        assert f"effective pose grid {grid.cell_count:,} cells" in app.pose_preview_status.get()
        assert app.entry_by_key["solver_step_m"].cget("state") == "disabled"

        # The worker receives the grid frozen before a later input edit.
        app.inputs["solver_step_m"].set("1")
        with patch("lapsim.ui.app.run_pose_driver", return_value=object()) as driver:
            app._calculate_pose_preview(*args)
        assert driver.call_args.kwargs["track"] is grid
        assert app.result_queue.get_nowait()[0] == "pose_preview"
    finally:
        root.destroy()


def test_pose_preview_keeps_finer_source_for_coarse_request() -> None:
    root, app = _desktop()
    try:
        source = load_course(SYNTHETIC_DEMO_COURSE_ID)
        app.inputs["solver_step_m"].set("2")
        with patch("lapsim.ui.app.threading.Thread") as thread:
            app._start_pose_preview()
        grid = thread.call_args.kwargs["args"][2]
        assert grid == source
        assert "requested Cell size (max) 2 m" in app.pose_preview_status.get()
        assert f"max {max(source.cell_length_m):.3g} m" in app.pose_preview_status.get()
    finally:
        root.destroy()


def test_eligible_selected_ai_path_uses_frozen_sampled_reference() -> None:
    root, app = _desktop()
    try:
        selected = _offer_selected_ai_path(app)
        assert app.pose_ai_preview_button.cget("state") == "normal"
        assert "Eligible selected AI path ready" in app.pose_ai_availability.get()
        with patch("lapsim.ui.app.threading.Thread") as thread:
            app._start_pose_preview(use_selected_ai_path=True)
        args = thread.call_args.kwargs["args"]
        frozen = args[2]
        assert args[:2] == (POSE_SCENARIO_UNIFORM, 0.0)
        assert args[3] == "sampled_polyline"
        assert frozen.cell_count > selected.cell_count
        assert max(frozen.cell_length_m) <= 0.5 + 1e-12
        assert "eligible selected AI path (sampled polyline)" in app.driver_run_label.get()
        assert "separate synthetic car" in app.driver_note_var.get()
        assert app.pose_ai_preview_button.cget("state") == "disabled"

        # Editing the shared entry while the mocked worker is queued cannot
        # substitute a different path or resolution into that worker.
        app.inputs["solver_step_m"].set("0.25")
        with patch("lapsim.ui.app.run_pose_driver", return_value=object()) as driver:
            app._calculate_pose_preview(*args)
        assert driver.call_args.kwargs["track"] is frozen
        settings = driver.call_args.kwargs["settings"]
        assert settings.reference_geometry == "sampled_polyline"
        assert settings.target_progress_m == 80.0
        assert "vehicle_config" not in driver.call_args.kwargs
        assert app.result_queue.get_nowait()[0] == "pose_preview"
    finally:
        root.destroy()


@pytest.mark.parametrize(
    ("rank_status", "selected_mode", "audit_valid"),
    [
        ("candidate_not_faster", "centerline", True),
        ("invalid_candidate_path", "centerline", False),
        ("invalid_processed_baseline", "candidate", True),
    ],
)
def test_diagnostic_or_unselected_ai_paths_cannot_start_pose_preview(
    rank_status: str, selected_mode: str, audit_valid: bool,
) -> None:
    root, app = _desktop()
    try:
        _offer_selected_ai_path(
            app, rank_status=rank_status, selected_mode=selected_mode,
            audit_valid=audit_valid,
        )
        assert app.pose_ai_preview_button.cget("state") == "disabled"
        assert "diagnostic paths do not" in app.pose_ai_availability.get()
        with (
            patch("lapsim.ui.app.messagebox.showerror") as showerror,
            patch("lapsim.ui.app.threading.Thread") as thread,
        ):
            app._start_pose_preview(use_selected_ai_path=True)
        showerror.assert_called_once()
        thread.assert_not_called()
    finally:
        root.destroy()


def test_selected_ai_pose_button_retires_on_input_or_course_change() -> None:
    root, app = _desktop()
    try:
        _offer_selected_ai_path(app)
        assert app.pose_ai_preview_button.cget("state") == "normal"
        app.inputs["solver_step_m"].set("0.25")
        root.update_idletasks()
        assert app.pose_ai_preview_button.cget("state") == "disabled"
        assert app._path_comparison is None

        _offer_selected_ai_path(app)
        assert app.pose_ai_preview_button.cget("state") == "normal"
        app._select_course(COURSE_OPTIONS[0].label)
        assert app.pose_ai_preview_button.cget("state") == "disabled"
        assert "only on Synthetic loop" in app.pose_ai_availability.get()
    finally:
        root.destroy()


def test_selected_ai_pose_grid_obeys_5000_cell_cap() -> None:
    root, app = _desktop()
    try:
        app.inputs["solver_step_m"].set("0.01")
        with pytest.raises(ValueError, match="5,000-cell compute cap"):
            app._read_pose_grid(_sampled_ai_path())
    finally:
        root.destroy()


def test_pose_grid_label_is_retired_when_inputs_change() -> None:
    root, app = _desktop()
    try:
        with patch("lapsim.ui.app.threading.Thread"):
            app._start_pose_preview()
        assert "effective pose grid" in app._active_pose_description()
        app._set_busy(False)
        app.inputs["solver_step_m"].set("0.25")
        root.update_idletasks()
        assert "pose grid" not in app._active_pose_description()
    finally:
        root.destroy()


@pytest.mark.parametrize("value", ["", "bad", "nan", "inf", "0", "-1", "0.01"])
def test_pose_preview_rejects_invalid_or_excessive_cell_grid(value: str) -> None:
    root, app = _desktop()
    try:
        app.inputs["solver_step_m"].set(value)
        with (
            patch("lapsim.ui.app.messagebox.showerror") as showerror,
            patch("lapsim.ui.app.threading.Thread") as thread,
        ):
            app._start_pose_preview()
        showerror.assert_called_once()
        thread.assert_not_called()
        assert not app.run_in_progress
        assert app.entry_by_key["solver_step_m"].cget("state") == "normal"
        if value == "0.01":
            assert "5,000-cell compute cap" in showerror.call_args.args[1]
    finally:
        root.destroy()


def test_pose_scenario_change_clears_only_old_pose_playback() -> None:
    root, app = _desktop()
    try:
        reference_playback = object.__new__(DriverPlayback)
        app.driver_playback = reference_playback
        app.pose_scenario_var.set(POSE_SCENARIO_PATCH)
        assert app.driver_playback is reference_playback
        assert POSE_SCENARIO_PATCH in app.pose_preview_status.get()
        with patch("lapsim.ui.app.threading.Thread") as thread:
            app._start_pose_preview()
        assert thread.call_args.kwargs["args"][:2] == (POSE_SCENARIO_PATCH, 0.0)
        assert POSE_SCENARIO_PATCH in app.driver_run_label.get()
        assert app.pose_scenario_menu.cget("state") == "disabled"
        app.pose_scenario_var.set(POSE_SCENARIO_UNIFORM)
        assert app.pose_scenario_var.get() == POSE_SCENARIO_PATCH
        app._set_busy(False)
        app.driver_playback = object.__new__(PoseDriverPlayback)
        app.driver_play_button.configure(state="normal")
        app.driver_values["speed"].set("18.0")
        app.pose_scenario_var.set(POSE_SCENARIO_UNIFORM)
        assert app.driver_playback is None
        assert app.driver_play_button.cget("state") == "disabled"
        assert app.driver_values["speed"].get() == "—"
        assert POSE_SCENARIO_UNIFORM in app.pose_preview_status.get()
        assert "scenario changed" in app.driver_run_label.get()
        assert "pose grid" not in app._active_pose_description()
        tab = app.tab_panels["Timed sessions · WIP"]
        labels = [child.cget("text") for child in app._walk_widgets(tab)
                  if isinstance(child, tk.Label)]
        assert any("world x 36–55 m, y −3–16 m" in label for label in labels)
    finally:
        root.destroy()


def test_pose_playback_labels_separate_model_and_reference_mode_restores_note() -> None:
    root, app = _desktop()
    try:
        run = SimpleNamespace(
            status="target_reached",
            samples=(SimpleNamespace(progress_m=80.1),),
            settings=SimpleNamespace(
                target_progress_m=80.0, reference_geometry="sampled_polyline",
            ),
            elapsed_pose_model_time_s=14.75,
        )
        app._active_pose_reference_label = "recorded sampled polyline"
        fake_playback = object()
        with (
            patch("lapsim.ui.app.PoseDriverPlayback", return_value=fake_playback),
            patch.object(app, "_render_driver_frame"),
            patch.object(app, "_switch_tab"),
            patch.object(app, "_toggle_driver_playback"),
        ):
            app._activate_pose_preview(run)
        assert app.driver_playback is fake_playback
        assert POSE_DRIVER_NOTE in app.driver_note_var.get()
        assert app.driver_heading_title_label.cget("text") == "VEHICLE HEADING (°)"
        assert "recorded controls and tracking values" in app.driver_decision_title.get()
        assert "Synthetic pose model" in app.driver_run_label.get()
        assert "initial offset +0.00 m" in app.driver_run_label.get()
        assert "recorded sampled polyline" in app.driver_run_label.get()
        assert "separate synthetic car" in app.driver_note_var.get()
        assert "14.75 s pose-model time" in app.driver_run_label.get()
        assert app.driver_decision_title_labels[0].cget("text") == "STEER FRONT (°)"

        with (
            patch("lapsim.ui.app.DriverPlayback", return_value=object()),
            patch.object(app, "_render_driver_frame"),
        ):
            app._set_driver_run(
                "Prius", SimpleNamespace(telemetry={"recorded": True}),
            )
        assert app.driver_note_var.get() == REFERENCE_DRIVER_NOTE
        assert app.driver_heading_title_label.cget("text") == "MAP HEADING (°)"
        assert app.driver_decision_title_labels[0].cget("text") == "NEXT ENTRY (km/h)"
        assert "not a tracked vehicle pose" in app.driver_note_var.get()
    finally:
        root.destroy()


def test_pose_offset_freezes_at_start_and_only_clears_pose_playback() -> None:
    root, app = _desktop()
    try:
        reference_playback = object.__new__(DriverPlayback)
        app.driver_playback = reference_playback
        app.pose_offset_var.set("1.25")
        assert app.driver_playback is reference_playback
        assert "initial offset +1.25 m" in app.pose_preview_status.get()
        with patch("lapsim.ui.app.threading.Thread") as thread:
            app._start_pose_preview()
        assert thread.call_args.kwargs["args"][:2] == (POSE_SCENARIO_UNIFORM, 1.25)
        assert app.pose_offset_entry.cget("state") == "disabled"
        assert "initial offset +1.25 m" in app.driver_run_label.get()
        app.pose_offset_var.set("-0.5")
        assert app.pose_offset_var.get() == "1.25"
        app._set_busy(False)
        app.driver_playback = object.__new__(PoseDriverPlayback)
        app.driver_play_button.configure(state="normal")
        app.driver_values["speed"].set("5.0")
        app.pose_offset_var.set("-0.5")
        assert app.driver_playback is None
        assert app.driver_play_button.cget("state") == "disabled"
        assert app.driver_values["speed"].get() == "—"
        assert "initial offset -0.50 m" in app.pose_preview_status.get()
        assert "initial offset changed" in app.driver_run_label.get()
    finally:
        root.destroy()


@pytest.mark.parametrize("value", ["", "bad", "nan", "inf", "-inf", "1.90001", "-1.90001"])
def test_pose_offset_rejects_invalid_input_before_launch(value: str) -> None:
    root, app = _desktop()
    try:
        app.pose_offset_var.set(value)
        with (
            patch("lapsim.ui.app.messagebox.showerror") as showerror,
            patch("lapsim.ui.app.threading.Thread") as thread,
        ):
            app._start_pose_preview()
        showerror.assert_called_once()
        thread.assert_not_called()
        assert not app.run_in_progress
        assert app.pose_offset_entry.cget("state") == "normal"
    finally:
        root.destroy()


@pytest.mark.parametrize("value", ["1.9", "-1.9"])
def test_pose_offset_accepts_assumed_center_limit(value: str) -> None:
    root, app = _desktop()
    try:
        app.pose_offset_var.set(value)
        assert app._read_pose_offset_m() == float(value)
        with patch("lapsim.ui.app.threading.Thread") as thread:
            app._start_pose_preview()
        assert thread.call_args.kwargs["args"][:2] == (
            POSE_SCENARIO_UNIFORM, float(value),
        )
    finally:
        root.destroy()


def test_synthetic_trace_save_uses_frozen_run_and_reports_replay(tmp_path: Path) -> None:
    root, app = _desktop()
    try:
        run = object()
        app._latest_pose_run = run
        app._set_busy(False)
        assert app.pose_save_button.cget("state") == "normal"
        destination = tmp_path / "pose.json"
        with (
            patch("lapsim.ui.app.default_pose_run_directory", return_value=tmp_path),
            patch("lapsim.ui.app.filedialog.asksaveasfilename", return_value=str(destination)),
            patch("lapsim.ui.app.threading.Thread") as thread,
        ):
            app._save_pose_record()
        assert thread.call_args.kwargs["args"] == (run, destination)
        assert app.pose_save_button.cget("state") == "disabled"
        assert app.pose_load_button.cget("state") == "disabled"

        fake_record = SimpleNamespace(content_id="a" * 64, save=lambda path: None)
        with patch("lapsim.ui.app.PoseRunRecord.capture", return_value=fake_record) as capture:
            app._write_pose_record(run, destination)
        capture.assert_called_once_with(run)
        app._poll_result()
        assert not app.run_in_progress
        assert app.pose_save_button.cget("state") == "normal"
        assert "numerical replay passed" in app.pose_record_status.get()
        assert "pose.json" in app.pose_record_status.get()
    finally:
        root.destroy()


def test_synthetic_trace_load_checks_record_before_playback(tmp_path: Path) -> None:
    root, app = _desktop()
    try:
        destination = tmp_path / "pose.json"
        with (
            patch("lapsim.ui.app.default_pose_run_directory", return_value=tmp_path),
            patch("lapsim.ui.app.filedialog.askopenfilename", return_value=str(destination)),
            patch("lapsim.ui.app.threading.Thread") as thread,
        ):
            app._load_pose_record()
        assert thread.call_args.kwargs["args"] == (destination,)
        assert app.run_in_progress
        assert app.pose_load_button.cget("state") == "disabled"

        run = SimpleNamespace(
            environment=PlanarEnvironment(),
            settings=SimpleNamespace(
                initial_lateral_offset_m=0.75,
                reference_geometry="sampled_polyline",
            ),
            track=_sampled_ai_path(),
            samples=(SimpleNamespace(progress_m=80.1),),
            states=(object(), object()),
            status="target_reached",
            elapsed_pose_model_time_s=15.0,
        )
        record = SimpleNamespace(run=run, content_id="b" * 64)
        with patch("lapsim.ui.app.PoseRunRecord.load", return_value=record) as load:
            app._read_pose_record(destination)
        load.assert_called_once_with(destination)
        with patch.object(app, "_activate_pose_preview") as activate:
            app._poll_result()
        activate.assert_called_once_with(run)
        assert not app.run_in_progress
        assert app._latest_pose_run is run
        assert app._active_pose_offset_m == 0.75
        assert app.pose_save_button.cget("state") == "normal"
        assert "numerical replay passed" in app.pose_record_status.get()
        assert "recorded pose grid" in app.pose_preview_status.get()
        assert "recorded sampled polyline" in app.pose_preview_status.get()
        assert "pose-model time" in app.pose_preview_status.get()
        assert "requested Cell size" not in app.pose_preview_status.get()
    finally:
        root.destroy()


def test_zero_step_synthetic_trace_load_has_no_invented_motion(tmp_path: Path) -> None:
    root, app = _desktop()
    try:
        destination = tmp_path / "zero_step.json"
        run = SimpleNamespace(
            environment=PlanarEnvironment(),
            settings=SimpleNamespace(initial_lateral_offset_m=0.0),
            samples=(SimpleNamespace(progress_m=0.0),),
            states=(object(),),
            status="initial_road_out_of_domain",
            elapsed_pose_model_time_s=0.0,
        )
        record = SimpleNamespace(run=run, content_id="c" * 64)
        for value in app.driver_values.values():
            value.set("old lap")
        for value in app.driver_decision_values.values():
            value.set("old lap")
        with patch("lapsim.ui.app.PoseRunRecord.load", return_value=record):
            app._read_pose_record(destination)
        with patch.object(app, "_activate_pose_preview") as activate:
            app._poll_result()
        activate.assert_not_called()
        assert app._latest_pose_run is run
        assert app._active_tab == "Driver view"
        assert app.driver_playback is None
        assert app.driver_play_button.cget("state") == "disabled"
        assert "no driven step" in app.driver_run_label.get()
        assert all(value.get() == "—" for value in app.driver_values.values())
        assert all(value.get() == "—" for value in app.driver_decision_values.values())
    finally:
        root.destroy()


def test_cell_size_and_calculation_progress_are_visible_beside_run() -> None:
    root, app = _desktop()
    try:
        entry = app.entry_by_key["solver_step_m"]
        assert entry.winfo_manager() == "grid"
        assert entry.master.cget("text") == "Calculation settings"
        assert entry.master.master is app.run_button.master
        assert app.inputs["solver_step_m"].get() == "1.0"
        assert "Centerline grid:" in app.cell_count_text.get()

        app.inputs["solver_step_m"].set("2.0")
        assert app._read_run_settings()[1] == pytest.approx(2.0)
        assert "Centerline grid:" in app.cell_count_text.get()
        app.driving_mode_var.set("AI racing line (experimental)")
        app._on_driving_mode_change()
        assert "AI grid varies" in app.cell_count_text.get()
        app.driving_mode_var.set("Centerline (default)")
        app._on_driving_mode_change()
        assert "AI grid varies" not in app.cell_count_text.get()
        app.inputs["solver_step_m"].set("0")
        assert "valid size" in app.cell_count_text.get()
        app.inputs["solver_step_m"].set("1")
        app._select_course(COURSE_OPTIONS[1].label)
        app.inputs["solver_step_m"].set("0.041")
        assert "5,000-cell limit" in app.cell_count_text.get()
        with pytest.raises(ValueError, match="5000-cell compute cap"):
            app._read_run_settings()

        assert app.calculation_progress_bar.winfo_manager() == "grid"
        labels = [child.cget("text") for child in app.run_button.master.winfo_children()
                  if isinstance(child, tk.Label)]
        assert "Calculation progress" in labels
        app._set_calculation_progress("determinate", "Calculating cells", fraction=0.5)
        assert app._calculation_progress_fraction == pytest.approx(0.5)
        assert app.calculation_progress_bar.find_all()
    finally:
        root.destroy()
