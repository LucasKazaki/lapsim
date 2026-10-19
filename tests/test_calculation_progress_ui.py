"""Desktop calculation progress reflects observed model work, not guesses."""

from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from lapsim.events.endurance import LapProgressSnapshot
from lapsim.solvers.path_constraints import PathConstraintProgressSnapshot
from lapsim.ui.app import LapSimDesktop
from lapsim.ui.simulation import SpeedPeriodicPhaseSnapshot


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


def test_ai_speed_seam_probe_clears_old_percent_and_has_no_fake_pose() -> None:
    root, app = _desktop()
    try:
        app.driving_mode_var.set("AI racing line (experimental)")
        with patch("lapsim.ui.app.threading.Thread"):
            app._start_run()
        app._queue_live_progress(
            "Prius", "Geometric centerline", app.track, _cell(app, 0),
        )
        app._poll_live_progress()
        assert app._calculation_progress_mode == "determinate"
        assert app.driver_playback is not None

        probe = SpeedPeriodicPhaseSnapshot("speed_seam_probe", 1, 2)
        app._queue_live_progress("Prius", "Full AI line", None, probe)
        app._poll_live_progress()
        assert app._calculation_progress_mode == "indeterminate"
        assert "Full AI line" in app.calculation_progress_text.get()
        assert "speed-seam probe pass 1" in app.calculation_progress_text.get()
        assert "cell progress unavailable" in app.calculation_progress_text.get()
        assert app.driver_playback is None
        assert "no vehicle pose" in app.driver_run_label.get()

        final = SpeedPeriodicPhaseSnapshot("final_lap", 2, 2)
        app._queue_live_progress("Prius", "Full AI line", None, final)
        app._poll_live_progress()
        assert app._calculation_progress_mode == "indeterminate"
        assert "final lap pass 2" in app.calculation_progress_text.get()
        assert "waiting for first accepted cell" in app.calculation_progress_text.get()
        app._queue_live_progress(
            "Prius", "Full AI line", app.track, _cell(app, 1),
        )
        app._poll_live_progress()
        assert app._calculation_progress_mode == "determinate"
        assert app._calculation_progress_fraction == pytest.approx(
            2 / app.track.cell_count
        )
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


@pytest.mark.parametrize(
    ("mode", "target_name"),
    (
        ("Centerline (default)", "_calculate_single"),
        ("AI racing line (experimental)", "_calculate_ai_single"),
    ),
    ids=("centerline", "ai"),
)
def test_ordinary_run_recovers_when_thread_start_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    target_name: str,
) -> None:
    """A controlled pre-launch fault; no model worker or numerical run occurs."""
    from pathlib import Path
    import sys
    import threading
    from typing import Any

    from lapsim.experiments import default_run_directory
    import lapsim.ui.app as app_module

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    root, app = _desktop()
    owner = threading.get_ident()
    failure_text = "can't start new thread: controlled ordinary Run probe"
    attempts: list[dict[str, Any]] = []
    callback_errors: list[str] = []
    dialogs: list[tuple[str, str, int, str]] = []
    run_attempted = False
    deadline_reached = False
    thread_type = threading.Thread
    original_start = threading.Thread.start

    def no_launch_proven() -> bool:
        return bool(attempts) and all(
            item["real_thread"]
            and item["ident"] is None
            and not item["is_alive"]
            and not item["original_delegated"]
            for item in attempts
        )

    def deny_app_worker_start(thread: threading.Thread) -> None:
        target = getattr(thread, "_target", None)
        selected = getattr(target, "__self__", None) is app
        name = getattr(target, "__name__", None)
        del target
        if selected:
            attempts.append(
                {
                    "target": name,
                    "real_thread": type(thread) is thread_type,
                    "ident": thread.ident,
                    "is_alive": thread.is_alive(),
                    "original_delegated": False,
                }
            )
            # The actual constructor ran; this branch never calls original_start.
            raise RuntimeError(failure_text)
        return original_start(thread)

    def observe_callback_error(
        exception_type: type[BaseException],
        error: BaseException,
        _trace: Any,
    ) -> None:
        callback_errors.append(f"{exception_type.__name__}: {error}")

    def observe_error(title: str, message: str, **_kwargs: Any) -> None:
        caller = sys._getframe(1)
        try:
            caller_name = caller.f_code.co_name
        finally:
            del caller
        # Test-only modal observation. No frame, exception or Tk object is stored.
        dialogs.append((title, str(message), threading.get_ident(), caller_name))

    def observe_terminal() -> None:
        if no_launch_proven() and (not app.run_in_progress or callback_errors):
            root.quit()
        else:
            root.after(10, observe_terminal)

    def deadline() -> None:
        nonlocal deadline_reached
        deadline_reached = True
        # Never interpret an empty attempt list as proof of no started worker.
        if no_launch_proven():
            root.quit()

    def storage_snapshot() -> dict[str, tuple[bytes, int]]:
        return {
            str(path.relative_to(tmp_path)): (
                path.read_bytes(),
                path.stat().st_mtime_ns,
            )
            for directory in (tmp_path / "local", tmp_path / "xdg")
            for path in directory.rglob("*")
            if path.is_file()
        }

    try:
        app.driving_mode_var.set(mode)
        app._on_driving_mode_change()
        input_states = {
            key: str(entry.cget("state")) for key, entry in app.entry_by_key.items()
        }
        run_directory = default_run_directory()
        assert run_directory.resolve().is_relative_to(tmp_path.resolve())
        assert not list(run_directory.glob("*.json"))
        assert app.profile_store.path.resolve().is_relative_to(tmp_path.resolve())
        assert app_module.__file__ is not None
        source_root = Path(app_module.__file__).resolve().parents[3]
        source_files = (
            Path(app_module.__file__),
            source_root / "analysis/data/track/gnss_imu_endurance_track.csv",
            source_root / "analysis/data/track/gnss_imu_endurance_track.json",
        )
        source_before = {
            path: (path.read_bytes(), path.stat().st_mtime_ns) for path in source_files
        }
        storage_before = storage_snapshot()
        monkeypatch.setattr(root, "report_callback_exception", observe_callback_error)
        monkeypatch.setattr(app_module.messagebox, "showerror", observe_error)
        monkeypatch.setattr(threading.Thread, "start", deny_app_worker_start)
        root.after(1000, deadline)
        root.after(0, observe_terminal)
        run_attempted = True
        app.run_button.invoke()
        assert no_launch_proven(), "No-worker ownership needs an observed denied start"
        root.mainloop()

        assert not deadline_reached, (
            "Scheduled error recovery did not finish within 1 s"
        )
        assert not callback_errors, callback_errors
        assert attempts == [
            {
                "target": target_name,
                "real_thread": True,
                "ident": None,
                "is_alive": False,
                "original_delegated": False,
            }
        ]
        assert dialogs == [
            ("Lap calculation failed", failure_text, owner, "_poll_result")
        ]
        assert not app.run_in_progress
        assert app.run_button.cget("state") == "normal"
        assert {
            key: str(entry.cget("state")) for key, entry in app.entry_by_key.items()
        } == input_states
        for key in ("solver_step_m", "torque_request_percent", "road_grip_percent"):
            assert app.entry_by_key[key].cget("state") == "normal"
        assert app.course_menu.cget("state") == "normal"
        assert app.profile_menu.cget("state") == "normal"
        assert app._calculation_progress_mode == "stopped"
        assert app._calculation_progress_fraction != 1.0
        assert app._calculation_progress_after_id is None
        assert app.status_text.get() == f"Calculation failed: {failure_text}"
        assert app._active_run_input_signature is None
        assert app._last_result is None and app.driver_playback is None
        assert app._displayed_run_records == () and app._driver_replay_runs == {}
        assert app.saved_runs_button is not None
        assert app.saved_runs_button.cget("state") == "disabled"
        assert not list(run_directory.glob("*.json"))
        assert storage_snapshot() == storage_before
        assert {
            path: (path.read_bytes(), path.stat().st_mtime_ns) for path in source_files
        } == source_before
    finally:
        # The injected pre-delegation failure proves ownership, unlike no entry.
        assert not run_attempted or no_launch_proven(), (
            "Do not destroy Tk without no-launch proof"
        )
        root.destroy()
