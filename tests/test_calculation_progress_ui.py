"""Desktop calculation progress reflects observed model work, not guesses."""

from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from lapsim.events.endurance import LapProgressSnapshot
from lapsim.solvers.path_constraints import PathConstraintProgressSnapshot
from lapsim.ui.app import LapSimDesktop


def _desktop() -> tuple[tk.Tk, LapSimDesktop]:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    return root, LapSimDesktop(root)


def _cell(app: LapSimDesktop, index: int) -> LapProgressSnapshot:
    return LapProgressSnapshot(
        lap_index=0,
        cell_index=index,
        cell_count=app.track.cell_count,
        elapsed_time_s=float(index + 1),
        lap_station_m=app.track.distance_m[index + 1],
        total_distance_m=app.track.distance_m[index + 1],
        speed_mps=5.0,
        lateral_acceleration_mps2=0.0,
    )


def test_centerline_bar_tracks_only_accepted_cells_and_resets_on_failure() -> None:
    root, app = _desktop()
    try:
        assert app._calculation_progress_mode == "idle"
        with patch("lapsim.ui.app.threading.Thread"):
            app._start_run()
        assert app._calculation_progress_mode == "indeterminate"
        assert "Preparing course" in app.calculation_progress_text.get()
        assert "progress unavailable" in app.calculation_progress_text.get()

        snapshot = _cell(app, 0)
        app._queue_live_progress("Prius", "Centerline model", app.track, snapshot)
        app._poll_live_progress()
        assert app._calculation_progress_mode == "determinate"
        assert app._calculation_progress_fraction == pytest.approx(
            1 / app.track.cell_count
        )
        assert f"1/{app.track.cell_count} cells" in app.calculation_progress_text.get()
        assert "Current pass" in app.calculation_progress_text.get()

        app._show_driver_preview_after_phase(
            app._driver_live_update_serial, "Prius", "Centerline model",
            phase_complete=False,
        )
        assert app._calculation_progress_mode == "indeterminate"
        assert "waiting for next accepted cell" in app.calculation_progress_text.get()

        app.result_queue.put(("single", None, RuntimeError("solver failed")))
        with patch("lapsim.ui.app.messagebox.showerror"):
            app._poll_result()
        assert app._calculation_progress_mode == "stopped"
        assert app._calculation_progress_after_id is None
        assert "Calculation stopped" in app.calculation_progress_text.get()
        app.inputs["road_grip_percent"].set("70")
        root.update_idletasks()
        assert app._calculation_progress_mode == "idle"
        assert "Inputs changed" in app.calculation_progress_text.get()
    finally:
        root.destroy()


def test_path_limit_progress_reports_measured_cells_without_claiming_convergence() -> None:
    root, app = _desktop()
    try:
        with patch("lapsim.ui.app.threading.Thread"):
            app._start_run()
        local = PathConstraintProgressSnapshot(
            phase="local_limits", completed_cells=30, cell_count=60,
            pass_number=None, maximum_passes=500,
        )
        app._queue_live_progress("Prius", "Centerline model", None, local)
        app._poll_live_progress()
        assert app._calculation_progress_mode == "determinate"
        assert app._calculation_progress_fraction == pytest.approx(0.5)
        assert "30/60 cells" in app.calculation_progress_text.get()
        assert "of this phase" in app.calculation_progress_text.get()
        assert "no vehicle pose" in app.driver_run_label.get()

        braking = PathConstraintProgressSnapshot(
            phase="cyclic_braking", completed_cells=60, cell_count=60,
            pass_number=2, maximum_passes=500,
        )
        app._queue_live_progress("Prius", "Centerline model", None, braking)
        app._poll_live_progress()
        assert app._calculation_progress_mode == "indeterminate"
        assert "pass 2" in app.calculation_progress_text.get()
        assert "convergence pending" in app.calculation_progress_text.get()
        assert "100%" not in app.calculation_progress_text.get()

        app._queue_live_progress("Prius", "Centerline model", app.track, _cell(app, 0))
        app._poll_live_progress()
        assert app._calculation_progress_mode == "determinate"
        assert "Current pass" in app.calculation_progress_text.get()

        app._queue_live_progress("Next car", "Centerline comparison", None, local)
        app._poll_live_progress()
        assert app.driver_playback is None
        assert all(value.get() == "—" for value in app.driver_values.values())
        assert all(value.get() == "—" for value in app.driver_decision_values.values())
        assert "no vehicle pose" in app.driver_run_label.get()
    finally:
        root.destroy()


def test_ai_and_comparison_bar_labels_each_current_pass() -> None:
    root, app = _desktop()
    try:
        app.driving_mode_var.set("AI racing line (experimental)")
        with patch("lapsim.ui.app.threading.Thread"):
            app._start_run()
        assert "Planning AI path" in app.calculation_progress_text.get()
        app._queue_live_progress("Prius", "Geometric centerline", app.track, _cell(app, 0))
        app._poll_live_progress()
        assert "Geometric centerline" in app.calculation_progress_text.get()
        app._queue_live_progress("Prius", "Full AI line", app.track, _cell(app, 1))
        app._poll_live_progress()
        assert "Full AI line" in app.calculation_progress_text.get()
        assert app._calculation_progress_fraction == pytest.approx(
            2 / app.track.cell_count
        )
        app._set_busy(False)

        with patch("lapsim.ui.app.threading.Thread"):
            app._start_comparison()
        assert "Preparing two cars" in app.calculation_progress_text.get()
        app._queue_live_progress("Car A", "Centerline comparison", app.track, _cell(app, 0))
        app._poll_live_progress()
        assert "Car A: Centerline comparison" in app.calculation_progress_text.get()
        app._queue_live_progress("Car B", "Centerline comparison", app.track, _cell(app, 0))
        app._poll_live_progress()
        assert "Car B: Centerline comparison" in app.calculation_progress_text.get()
    finally:
        root.destroy()


def test_bar_finishes_on_result_and_dark_mode_and_close_cancel_animation() -> None:
    root, app = _desktop()
    try:
        with patch("lapsim.ui.app.threading.Thread"):
            app._start_run()
        app.is_dark.set(True)
        app._apply_theme()
        assert app.calculation_progress_bar.cget("background") == "#000000"
        items = app.calculation_progress_bar.find_all()
        assert items
        assert app.calculation_progress_bar.itemcget(items[0], "fill") == "#ffffff"

        completed = SimpleNamespace(completed=True)
        app.result_queue.put((
            "single", ("Prius", 1.0, completed, "saved-run", app.track), None,
        ))
        with (
            patch.object(app, "_show_result"),
            patch.object(app, "_activate_driver_playback"),
        ):
            app._poll_result()
        assert app._calculation_progress_mode == "complete"
        assert app._calculation_progress_fraction == 1.0
        assert app.calculation_progress_text.get() == "Calculation finished"
        assert app._calculation_progress_after_id is None

        with patch("lapsim.ui.app.threading.Thread"):
            app._start_run()
        assert app._calculation_progress_after_id is not None
    finally:
        root.destroy()
    assert app._closed
    assert app._calculation_progress_after_id is None
