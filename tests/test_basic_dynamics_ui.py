"""Actual Tk session defaults, execution and stale-result ownership."""

import time
import tkinter as tk

from lapsim.ui.basic_dynamics import BasicDynamicsLab


def wait_for_result(root, lab):
    deadline = time.monotonic() + 10
    while lab.busy and time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)
    assert not lab.busy


def test_new_basic_session_selects_bicycle_runs_and_invalidates_changed_inputs():
    root = tk.Tk()
    root.withdraw()
    lab = BasicDynamicsLab(root)
    root.update_idletasks()
    try:
        assert lab.model_id.get() == "dynamic_bicycle_v1"
        assert str(lab.model_menu.cget("state")) == "readonly"
        lab.inputs["duration"].set("0.2")
        lab.run_button.invoke()
        wait_for_result(root, lab)
        assert lab.record is not None
        assert lab.record["scenario"]["model_id"] == "dynamic_bicycle_v1"
        assert (
            lab.record["scenario"]["controller_backend_id"] == "none_prescribed_force"
        )
        assert len(lab.path_axes.lines) == 1
        lab.inputs["steer"].set("-2")
        assert lab.record is None
        assert str(lab.save_button.cget("state")) == "disabled"
        assert not lab.path_axes.lines
    finally:
        lab.close()
        root.destroy()


def test_actual_save_load_replay_and_corrupt_file_rejection(tmp_path, monkeypatch):
    import lapsim.ui.basic_dynamics as ui
    from lapsim.experiments.basic_dynamics import decode_json, replay_bicycle_record

    root = tk.Tk()
    root.withdraw()
    lab = BasicDynamicsLab(root)
    root.update_idletasks()
    try:
        lab.inputs["duration"].set("0.2")
        lab.run_button.invoke()
        wait_for_result(root, lab)
        record_id = lab.record["run_id"]
        path = tmp_path / "bicycle run.json"
        monkeypatch.setattr(
            ui, "default_dynamics_run_directory", lambda: tmp_path / "dynamics"
        )
        monkeypatch.setattr(
            ui.filedialog, "asksaveasfilename", lambda **kwargs: str(path)
        )
        lab.save_button.invoke()
        assert replay_bicycle_record(decode_json(path.read_bytes()))["model_agreement"]
        lab.inputs["speed"].set("9")
        monkeypatch.setattr(
            ui.filedialog, "askopenfilename", lambda **kwargs: str(path)
        )
        lab.load_button.invoke()
        wait_for_result(root, lab)
        assert lab.record["run_id"] == record_id
        assert float(lab.inputs["speed"].get()) == 8
        path.write_text("{corrupt")
        lab.load_button.invoke()
        wait_for_result(root, lab)
        assert lab.record is None
        assert "failed" in lab.status.get()
        assert str(lab.save_button.cget("state")) == "disabled"
        lab.window.geometry("760x620")
        root.update_idletasks()
        assert lab.control_canvas.winfo_height() > 100
    finally:
        lab.close()
        root.destroy()


def test_changed_inputs_discard_old_worker_result():
    root = tk.Tk()
    root.withdraw()
    lab = BasicDynamicsLab(root)
    root.update_idletasks()
    try:
        revision = lab.input_revision
        lab.busy = True
        lab.inputs["force"].set("100")
        lab.results.put((revision, {"invalid_stale_result": True}, None))
        lab.window.after_cancel(lab.poll_id)
        lab._poll()
        assert lab.record is None
        assert not lab.busy
        assert "discarded" in lab.status.get()
    finally:
        lab.close()
        root.destroy()


def test_closing_session_cancels_canvas_owned_idle_draw():
    root = tk.Tk()
    root.withdraw()
    lab = BasicDynamicsLab(root)
    root.update_idletasks()
    try:
        lab._draw()
        pending = getattr(lab.canvas, "_idle_draw_id")
        assert pending is not None
        lab.close()
        assert pending not in root.tk.call("after", "info")
        root.update()
    finally:
        if not lab.closed:
            lab.close()
        root.destroy()
