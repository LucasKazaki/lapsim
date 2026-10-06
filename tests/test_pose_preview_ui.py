"""The optional pose preview stays separate from engineering lap results."""

from __future__ import annotations

from types import SimpleNamespace
import tkinter as tk
from unittest.mock import patch

import pytest

from lapsim.dynamics.planar import PlanarState
from lapsim.optimization.pose_driver import PoseDriverSample
from lapsim.ui.app import LapSimDesktop, POSE_DRIVER_NOTE, REFERENCE_DRIVER_NOTE
from lapsim.ui.course_catalog import (
    COURSE_OPTIONS, SYNTHETIC_DEMO_COURSE_ID, load_course,
)
from lapsim.ui.pose_driver_playback import PoseDriverLivePlayback


def _desktop() -> tuple[tk.Tk, LapSimDesktop]:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    return root, LapSimDesktop(root)


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
        assert app._displayed_run_records == ()
        assert app._active_tab == "Driver view"
        assert app.driver_playback is None
        assert "Synthetic pose model" in app.driver_run_label.get()
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
        assert "not an engineering lap time" in app.pose_preview_status.get()
        assert app._displayed_run_records == ()
    finally:
        root.destroy()


def test_pose_playback_labels_separate_model_and_reference_mode_restores_note() -> None:
    root, app = _desktop()
    try:
        run = SimpleNamespace(
            status="target_reached",
            samples=(SimpleNamespace(progress_m=80.1),),
            settings=SimpleNamespace(target_progress_m=80.0),
        )
        fake_playback = object()
        with (
            patch("lapsim.ui.app.PoseDriverPlayback", return_value=fake_playback),
            patch.object(app, "_render_driver_frame"),
            patch.object(app, "_switch_tab"),
            patch.object(app, "_toggle_driver_playback"),
        ):
            app._activate_pose_preview(run)
        assert app.driver_playback is fake_playback
        assert app.driver_note_var.get() == POSE_DRIVER_NOTE
        assert app.driver_heading_title_label.cget("text") == "VEHICLE HEADING (°)"
        assert "recorded controls and tracking values" in app.driver_decision_title.get()
        assert "Synthetic pose model" in app.driver_run_label.get()
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
