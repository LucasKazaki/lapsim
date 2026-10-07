"""Projection-loss status text distinguishes confirmed station from pose."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tkinter as tk

import pytest

import lapsim.optimization.pose_driver as pose_driver
from lapsim.optimization.pose_driver import PoseDriverSettings, run_pose_driver
from lapsim.ui.app import LapSimDesktop


def _desktop() -> tuple[tk.Tk, LapSimDesktop]:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    return root, LapSimDesktop(root)


def _projection_lost_run(monkeypatch):
    original = pose_driver._project_local
    calls = 0

    def lose_after_first_step(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 7:
            raise ValueError("projection unavailable")
        return original(*args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(pose_driver, "_project_local", lose_after_first_step)
        run = run_pose_driver()
    assert run.status == "projection_lost"
    assert not run.samples[-1].projection_valid
    assert run.minimum_assumed_boundary_slack_m == float("-inf")
    return run


@pytest.mark.parametrize("loaded", [False, True])
def test_projection_loss_status_labels_last_confirmed_station(
    monkeypatch, loaded: bool,
) -> None:
    run = _projection_lost_run(monkeypatch)
    root, app = _desktop()
    try:
        if loaded:
            record = SimpleNamespace(
                run=run, content_id="f" * 64, controller_report=None,
            )
            app.result_queue.put((
                "pose_record_loaded", (Path("projection-lost.json"), record), None,
            ))
        else:
            app.result_queue.put(("pose_preview", run, None))
        app._poll_result()

        status = app.pose_preview_status.get()
        assert "projection_lost: last confirmed progress 0.0 m in" in status
        assert "last confirmed progress 0.0 m / 80 m" in app.driver_run_label.get()
        if loaded:
            assert "Recorded" in status
        else:
            assert "assumed footprint slack unavailable after projection loss" in status
            assert "-inf m" not in status
    finally:
        root.destroy()


def test_valid_pose_status_keeps_numeric_station_and_slack() -> None:
    run = run_pose_driver(settings=PoseDriverSettings(target_progress_m=0.1))
    assert run.completed
    root, app = _desktop()
    try:
        app.result_queue.put(("pose_preview", run, None))
        app._poll_result()
        status = app.pose_preview_status.get()
        assert f"{run.samples[-1].progress_m:.1f} m in" in status
        assert (
            f"minimum assumed footprint slack "
            f"{run.minimum_assumed_boundary_slack_m:.2f} m"
        ) in status
        assert "last confirmed progress" not in status
        assert "last confirmed progress" not in app.driver_run_label.get()
    finally:
        root.destroy()
