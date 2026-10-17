"""Actual native study entry, execution, cancellation and checked save/load."""

import time
import tkinter as tk
from threading import Event

import pytest

from lapsim.ui.control_lab import ControlLab
from lapsim.ui.dynamics_lab import DynamicsLab


def wait(root, lab):
    deadline = time.monotonic() + 20
    while lab.busy and time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)
    assert not lab.busy, lab.status.get()


def test_actual_four_wheel_entry_runs_matched_study_and_invalidates_inputs():
    root = tk.Tk()
    root.withdraw()
    manual = DynamicsLab(root, dark=False)
    root.update_idletasks()
    try:
        manual.control_study_button.invoke()
        lab = manual.latest_control_study
        root.update_idletasks()
        assert isinstance(lab, ControlLab)
        lab.inputs["duration_s"].set(".1")
        lab.run_button.invoke()
        wait(root, lab)
        assert lab.record is not None, lab.status.get()
        assert (
            lab.record["runs"]["A"]["scenario"]["controller_backend_id"]
            == "python_reference"
        )
        assert all(len(axis.lines) == 2 for axis in lab.axes.flat)
        lab.inputs["speed_mps"].set("2")
        assert lab.record is None and str(lab.save_button.cget("state")) == "disabled"
        assert not any(axis.lines for axis in lab.axes.flat)
        lab.close()
        root.update()
    finally:
        root.destroy()


def test_save_load_checked_replay_and_explicit_new_preset(tmp_path, monkeypatch):
    import lapsim.ui.control_lab as ui

    root = tk.Tk()
    root.withdraw()
    lab = ControlLab(root)
    root.update_idletasks()
    try:
        lab.inputs["duration_s"].set(".1")
        lab.run()
        wait(root, lab)
        identity = lab.record["run_id"]
        path = tmp_path / "control study.json"
        monkeypatch.setattr(
            ui, "default_dynamics_run_directory", lambda: tmp_path / "dynamics"
        )
        monkeypatch.setattr(
            ui.filedialog, "asksaveasfilename", lambda **kwargs: str(path)
        )
        monkeypatch.setattr(
            ui.filedialog, "askopenfilename", lambda **kwargs: str(path)
        )
        lab.save()
        assert path.is_file()
        lab.load()
        wait(root, lab)
        assert lab.record["run_id"] == identity and lab.imported
        assert str(lab.run_button.cget("state")) == "disabled"
        assert all(str(field.cget("state")) == "disabled" for field in lab.fields)
        lab.new_button.invoke()
        assert lab.record is None
        assert str(lab.run_button.cget("state")) == "normal"
        path.write_text("{corrupt")
        lab.load()
        wait(root, lab)
        assert lab.record is None and "failed" in lab.status.get().lower()
    finally:
        lab.close()
        root.update()
        root.destroy()


def test_cancel_study_produces_no_exportable_partial_record_and_closes_cleanly():
    root = tk.Tk()
    root.withdraw()
    lab = ControlLab(root, dark=True)
    root.update_idletasks()
    try:
        lab.inputs["duration_s"].set("2")
        lab.run()
        lab.cancel_button.invoke()
        wait(root, lab)
        assert lab.record is None
        assert "cancelled" in lab.status.get().lower()
        lab._draw()
        pending = lab.canvas._idle_draw_id
        lab.close()
        assert pending not in root.tk.call("after", "info")
        root.update()
    finally:
        if not lab.closed:
            lab.close()
        root.destroy()


@pytest.mark.parametrize("previously_imported", (False, True))
def test_cancel_import_interrupts_real_replay_and_allows_fresh_load_and_run(
    tmp_path, monkeypatch, previously_imported
):
    import json

    from lapsim.experiments import closed_loop, control_study
    from lapsim.ui import control_lab as ui

    comparison = control_study.run_control_comparison(
        control_study.study_scenario(dict(control_study.DEFAULT_REQUEST, duration_s=0.1))
    )
    source = tmp_path / "saved comparison.json"
    source.write_text(json.dumps(comparison), encoding="utf-8")
    before = source.read_bytes()
    root = tk.Tk()
    root.withdraw()
    lab = ControlLab(root)
    root.update_idletasks()
    entered = Event()
    release = Event()
    steps = 0
    original = closed_loop.advance_powered

    def pause_first_advance(*args, **kwargs):
        nonlocal steps
        steps += 1
        if steps == 1:
            entered.set()
            assert release.wait(timeout=5)
        return original(*args, **kwargs)

    monkeypatch.setattr(ui.filedialog, "askopenfilename", lambda **kwargs: str(source))
    try:
        if previously_imported:
            lab.load_button.invoke()
            wait(root, lab)
            assert lab.record is not None and lab.imported
        monkeypatch.setattr(closed_loop, "advance_powered", pause_first_advance)
        lab.load_button.invoke()
        assert entered.wait(timeout=5), lab.status.get()
        lab.cancel_button.invoke()
        release.set()
        wait(root, lab)
        assert steps == 1
        assert lab.record is None and not lab.imported
        assert "cancelled" in lab.status.get().lower()
        assert "failed" not in lab.status.get().lower()
        assert str(lab.save_button.cget("state")) == "disabled"
        assert str(lab.inspect_button.cget("state")) == "disabled"
        assert all(str(field.cget("state")) != "disabled" for field in lab.fields)
        assert not any(axis.lines for axis in lab.axes.flat)
        assert source.read_bytes() == before
        monkeypatch.setattr(closed_loop, "advance_powered", original)
        lab.load_button.invoke()
        wait(root, lab)
        assert lab.imported and lab.record["run_id"] == comparison["run_id"]
        lab.new_button.invoke()
        lab.inputs["duration_s"].set(".1")
        lab.run_button.invoke()
        wait(root, lab)
        assert lab.record is not None and not lab.imported
    finally:
        release.set()
        lab.close()
        root.update()
        root.destroy()


def test_cancel_after_import_worker_finishes_discards_queued_result(
    tmp_path, monkeypatch
):
    import json

    from lapsim.experiments import control_study
    from lapsim.ui import control_lab as ui

    comparison = control_study.run_control_comparison(
        control_study.study_scenario(dict(control_study.DEFAULT_REQUEST, duration_s=0.1))
    )
    source = tmp_path / "saved comparison.json"
    source.write_text(json.dumps(comparison), encoding="utf-8")
    root = tk.Tk()
    root.withdraw()
    lab = ControlLab(root)
    root.update_idletasks()
    monkeypatch.setattr(ui.filedialog, "askopenfilename", lambda **kwargs: str(source))
    try:
        lab.load_button.invoke()
        deadline = time.monotonic() + 5
        while lab.results.empty() and time.monotonic() < deadline:
            # Hold UI delivery so cancellation races with a completed worker.
            time.sleep(0.01)
        assert not lab.results.empty()
        lab.cancel_button.invoke()
        wait(root, lab)
        assert lab.record is None and not lab.imported
        assert "cancelled" in lab.status.get().lower()
        assert str(lab.save_button.cget("state")) == "disabled"
        assert not any(axis.lines for axis in lab.axes.flat)
    finally:
        lab.close()
        root.update()
        root.destroy()
