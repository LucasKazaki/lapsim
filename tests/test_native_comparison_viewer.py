"""Actual Tk saved-pair workflow contracts; run only with allocated GUI ownership."""

import builtins
import json
import subprocess
import threading
import time
import tkinter as tk
from hashlib import sha256

import pytest

from lapsim.experiments import suspension_study as study
from lapsim.ui.native_record_viewer import NativeRecordViewer
from test_suspension_compare import fixture_record


@pytest.fixture
def root():
    window = tk.Tk()
    window.withdraw()
    yield window
    window.destroy()


@pytest.fixture
def saved(tmp_path):
    paths = {}
    for name, record in (
        ("left", fixture_record()),
        ("plant", fixture_record(step=0.0005)),
        ("logging", fixture_record(logging=0.05)),
    ):
        # GUI-only synthetic observations declare their world/SI plotting claims;
        # these analytic values remain a no-physics fixture, not native evidence.
        record["payload"]["frame"] = (
            "right-handed world X initially forward, Y left, Z up; chassis COM"
        )
        record["payload"]["units"] = (
            "SI; steering request normalized, tire slip ratio dimensionless"
        )
        record["content_id"] = sha256(
            json.dumps(
                record["payload"], sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ).hexdigest()
        record["receipt_id"] = sha256(
            json.dumps(
                {key: value for key, value in record.items() if key != "receipt_id"},
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps(record), encoding="utf-8")
        paths[name] = path
    return paths


def wait(root, condition):
    deadline = time.monotonic() + 5
    while not condition():
        root.update()
        if time.monotonic() > deadline:
            pytest.fail("bounded saved-pair desktop operation did not finish")
        time.sleep(0.01)
    root.update()


def viewer_with_left(root, saved, *, dark=False):
    viewer = NativeRecordViewer(root, dark=dark)
    assert viewer.compare_button.cget("state") == "disabled"
    assert viewer.load_path(saved["left"])
    wait(root, lambda: not viewer.busy)
    assert viewer.record is not None
    assert viewer.compare_button.cget("state") == "normal"
    viewer.compare_button.invoke()
    assert viewer.comparison_window.winfo_exists()
    return viewer


def choose_kind(viewer, kind):
    viewer.comparison_kind_buttons[0 if kind == "plant-step" else 1].invoke()


def open_pair(root, viewer, path, kind):
    choose_kind(viewer, kind)
    assert viewer.compare_path(path)
    wait(root, lambda: not viewer.busy)
    assert viewer.comparison_report is not None


def test_explicit_kind_required_and_second_picker_cancel_is_unchanged(
    root, saved, monkeypatch
):
    viewer = viewer_with_left(root, saved)
    assert viewer.comparison_kind.get() == ""
    assert viewer.comparison_choose_button.cget("state") == "disabled"
    assert viewer.compare_path(saved["logging"]) is False
    open_pair(root, viewer, saved["logging"], "logging-period")
    prior = viewer.comparison_report
    monkeypatch.setattr("tkinter.filedialog.askopenfilename", lambda **kwargs: "")
    viewer.comparison_choose_button.invoke()
    assert viewer.comparison_report is prior
    viewer.close()


@pytest.mark.parametrize(
    "kind,name", (("plant-step", "plant"), ("logging-period", "logging"))
)
def test_normal_picker_flow_details_passivity_and_input_identity(
    root, saved, monkeypatch, kind, name
):
    before = {
        key: (path.read_bytes(), path.stat().st_mtime_ns) for key, path in saved.items()
    }
    original_import = builtins.__import__

    def checked_import(module, *args, **kwargs):
        assert not module.startswith("pychrono") and "chrono_vehicle" not in module
        return original_import(module, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("Saved-pair desktop review launched physics, replay or a process")

    monkeypatch.setattr(builtins, "__import__", checked_import)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    for field in ("run_study", "replay_study", "_source", "_code_identity"):
        monkeypatch.setattr(study, field, forbidden)
    viewer = viewer_with_left(root, saved)
    left = viewer.record
    viewer.select(2)
    selected = viewer.selected_sample
    choose_kind(viewer, kind)
    monkeypatch.setattr(
        "tkinter.filedialog.askopenfilename", lambda **kwargs: str(saved[name])
    )
    viewer.comparison_choose_button.invoke()
    wait(root, lambda: not viewer.busy)
    report = viewer.comparison_report
    assert report["comparison_kind"] == kind and report["status"] == "compared"
    assert viewer.record is left and viewer.selected_sample is selected
    assert viewer.comparison_text.cget("state") == "disabled"
    assert report["report_id"][:12] in viewer.comparison_text.get("1.0", "end")
    details = viewer.inspect_comparison()
    text = next(
        child for child in details.winfo_children() if isinstance(child, tk.Text)
    )
    assert text.cget("state") == "disabled"
    assert json.loads(text.get("1.0", "end")) == report
    assert viewer.comparison_window.grab_current() is None
    assert {
        key: (path.read_bytes(), path.stat().st_mtime_ns) for key, path in saved.items()
    } == before
    viewer.close()


def test_failure_kind_change_and_primary_reload_clear_old_pair_and_details(
    root, saved, tmp_path
):
    viewer = viewer_with_left(root, saved)
    open_pair(root, viewer, saved["logging"], "logging-period")
    details = viewer.inspect_comparison()
    old_left = viewer.record
    bad = tmp_path / "invalid.json"
    bad.write_text("{bad", encoding="utf-8")
    assert viewer.compare_path(bad)
    assert viewer.comparison_report is viewer.comparison_json is None
    assert not details.winfo_exists()
    wait(root, lambda: not viewer.busy)
    assert "Comparison failed" in viewer.comparison_text.get("1.0", "end")
    assert viewer.comparison_report is None and viewer.record is old_left
    assert viewer.comparison_details_button.cget("state") == "disabled"
    assert viewer.compare_path(saved["logging"])
    wait(root, lambda: not viewer.busy)
    assert viewer.comparison_report is not None
    details = viewer.inspect_comparison()
    choose_kind(viewer, "plant-step")
    assert viewer.comparison_report is viewer.comparison_json is None
    assert viewer.comparison_right.get() == "Right: no record selected"
    assert not details.winfo_exists()
    assert viewer.compare_path(saved["plant"])
    wait(root, lambda: not viewer.busy)
    details = viewer.inspect_comparison()
    assert viewer.load_path(saved["left"])
    assert viewer.comparison_window is viewer.comparison_report is None
    assert not details.winfo_exists()
    wait(root, lambda: not viewer.busy)
    viewer.open_comparison()
    assert viewer.comparison_kind.get() == "" and viewer.comparison_report is None
    viewer.close()


@pytest.mark.parametrize("condition", ("incompatible", "unavailable"))
def test_inspectable_claim_statuses_are_reports_and_not_load_failures(
    root, saved, tmp_path, monkeypatch, condition
):
    from lapsim.experiments import suspension_compare as comparison

    viewer = viewer_with_left(root, saved)
    if condition == "unavailable":
        monkeypatch.setattr(
            comparison,
            "__file__",
            str(tmp_path / "absent/experiments/suspension_compare.py"),
        )

        def unavailable():
            raise OSError("source unavailable in this runtime")

        monkeypatch.setattr(study, "_implementation_source", unavailable)
    kind = "logging-period" if condition == "incompatible" else "plant-step"
    open_pair(root, viewer, saved["plant"], kind)
    assert viewer.comparison_details_button.cget("state") == "normal"
    text = viewer.comparison_text.get("1.0", "end")
    if condition == "incompatible":
        assert viewer.comparison_report["status"] == "incompatible"
        assert "No numerical result" in text
    else:
        assert viewer.comparison_report["status"] == "compared"
        assert "Comparison recipe: incomplete · ID unavailable" in text
        assert "Saved-fixture endpoint criterion: not applied" in text
    assert "Comparison failed" not in text
    viewer.close()


@pytest.mark.parametrize("invalidate", ("close", "kind"))
def test_late_completion_is_discarded_but_owner_released_and_primary_scrubbing_works(
    root, saved, monkeypatch, invalidate
):
    from lapsim.ui import native_record_viewer as module

    viewer = viewer_with_left(root, saved)
    choose_kind(viewer, "plant-step")
    started, release = threading.Event(), threading.Event()
    reader = module.read_study_record

    def delayed(path):
        if path == saved["plant"]:
            started.set()
            assert release.wait(3)
        return reader(path)

    monkeypatch.setattr(module, "read_study_record", delayed)
    assert viewer.compare_path(saved["plant"])
    assert started.wait(1)
    owner = viewer.active_job
    viewer.step(1)
    assert viewer.index.get() == 1
    viewer.force_kind.set("Computed")
    viewer.change_force()
    assert viewer.compare_path(saved["logging"]) is False
    assert viewer.load_path(saved["left"]) is False
    if invalidate == "close":
        viewer.close_comparison()
        viewer.open_comparison()
    choose_kind(viewer, "logging-period")
    assert viewer.busy and viewer.active_job == owner
    assert viewer.comparison_report is None
    release.set()
    wait(root, lambda: not viewer.busy)
    assert viewer.active_job is None and viewer.comparison_report is None
    assert viewer.comparison_details_button.cget("state") == "disabled"
    assert viewer.comparison_choose_button.cget("state") == "normal"
    assert viewer.compare_path(saved["logging"])
    wait(root, lambda: not viewer.busy)
    assert viewer.comparison_report["comparison_kind"] == "logging-period"
    viewer.close()


def test_parent_close_discards_pending_pair_and_callbacks(root, saved, monkeypatch):
    from lapsim.ui import native_record_viewer as module

    viewer = viewer_with_left(root, saved)
    choose_kind(viewer, "logging-period")
    started, release = threading.Event(), threading.Event()
    reader = module.read_study_record

    def delayed(path):
        started.set()
        assert release.wait(3)
        return reader(path)

    monkeypatch.setattr(module, "read_study_record", delayed)
    assert viewer.compare_path(saved["logging"])
    assert started.wait(1)
    viewer.close()
    release.set()
    viewer.worker.join(timeout=3)
    root.update()
    assert not viewer.worker.is_alive()
    assert viewer.results.empty()
    assert viewer.record is viewer.comparison_window is viewer.comparison_report is None


def test_kind_arrows_wrap_once_clear_old_report_and_preserve_native_space_tab(
    root, saved
):
    viewer = viewer_with_left(root, saved)
    open_pair(root, viewer, saved["plant"], "plant-step")
    details = viewer.inspect_comparison()
    selected = viewer.selected_sample
    first, second = viewer.comparison_kind_buttons
    wait(root, lambda: details.winfo_viewable() and first.winfo_viewable())
    first.focus_force()
    root.update()
    wait(root, lambda: first.focus_get() is first)
    assert first.focus_get() is first
    first.event_generate("<Right>")
    root.update()
    assert viewer.comparison_kind.get() == "logging-period"
    assert first.focus_get() is second
    assert viewer.comparison_report is None and not details.winfo_exists()
    second.event_generate("<Right>")
    root.update()
    assert viewer.comparison_kind.get() == "plant-step" and first.focus_get() is first
    first.event_generate("<Left>")
    root.update()
    assert (
        viewer.comparison_kind.get() == "logging-period" and first.focus_get() is second
    )
    second.event_generate("<Up>")
    root.update()
    assert viewer.comparison_kind.get() == "plant-step"
    first.event_generate("<Down>")
    root.update()
    assert viewer.comparison_kind.get() == "logging-period"
    first.focus_force()
    wait(root, lambda: first.focus_get() is first)
    assert first.focus_get() is first
    first.event_generate("<space>")
    root.update()
    assert viewer.comparison_kind.get() == "plant-step"
    first.event_generate("<Tab>")
    root.update()
    focus = first.focus_get()
    assert focus is not None and focus.winfo_toplevel() is viewer.comparison_window
    focus.event_generate("<Shift-Tab>")
    root.update()
    assert (
        first.focus_get() is not None
        and first.focus_get().winfo_toplevel() is viewer.comparison_window
    )
    assert viewer.selected_sample is selected
    viewer.close()


@pytest.mark.parametrize("dark", (False, True))
@pytest.mark.parametrize("size", ("960x720", "1180x840"))
def test_actions_resize_and_escape_keeps_primary_keyboard_cursor(
    root, saved, dark, size
):
    viewer = viewer_with_left(root, saved, dark=dark)
    viewer.window.geometry(size)
    root.update()
    for button in (
        viewer.open_button,
        viewer.details_button,
        viewer.compare_button,
        viewer.force_menu,
    ):
        assert button.winfo_ismapped()
        assert (
            button.winfo_rootx() + button.winfo_width()
            <= viewer.window.winfo_rootx() + viewer.window.winfo_width()
        )
    pair = viewer.comparison_window
    pair.geometry("720x520")
    root.update()
    for button in (
        *viewer.comparison_kind_buttons,
        viewer.comparison_choose_button,
        viewer.comparison_details_button,
    ):
        assert button.winfo_ismapped()
        assert (
            button.winfo_rootx() + button.winfo_width()
            <= pair.winfo_rootx() + pair.winfo_width()
        )
    pair.focus_force()
    pair.event_generate("<Escape>")
    root.update()
    assert viewer.comparison_window is None and viewer.window.winfo_exists()
    assert viewer.compare_button.focus_get() is viewer.compare_button
    viewer.slider.focus_force()
    viewer.slider.event_generate("<Right>")
    root.update()
    assert viewer.index.get() == 1
    viewer.close()
