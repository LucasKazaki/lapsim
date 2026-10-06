"""The optional pose preview stays separate from engineering lap results."""

from __future__ import annotations

from types import SimpleNamespace
import tkinter as tk
from unittest.mock import patch

import pytest

from lapsim.ui.app import LapSimDesktop, POSE_DRIVER_NOTE, REFERENCE_DRIVER_NOTE


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
        with patch("lapsim.ui.app.threading.Thread") as thread:
            app._start_pose_preview()
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()
        assert app.run_in_progress
        assert app.pose_preview_button.cget("state") == "disabled"
        assert app._displayed_run_records == ()

        app.pose_progress_queue.put(SimpleNamespace(progress_m=40.0))
        app._poll_pose_progress()
        assert "40.0/80 m" in app.calculation_progress_text.get()
        assert app._calculation_progress_fraction == pytest.approx(0.5)

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
        assert app.driver_decision_title_labels[0].cget("text") == "NEXT ENTRY (km/h)"
        assert "not a tracked vehicle pose" in app.driver_note_var.get()
    finally:
        root.destroy()
