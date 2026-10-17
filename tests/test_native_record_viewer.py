"""Passive native-record selection, clock provenance and desktop lifecycle."""

import builtins
import json
import subprocess
import sys
import threading
import time
import tkinter as tk

import pytest

from lapsim.experiments import suspension_study as study
from lapsim.ui.dynamics_lab import DynamicsLab
from test_suspension_study import ClockPlant


@pytest.fixture
def root():
    window = tk.Tk()
    window.withdraw()
    yield window
    window.destroy()


@pytest.fixture(scope="module")
def saved_record():
    # Instrumentation, not native vehicle evidence. The extra settling sample
    # falls between logging times; source clocks deliberately have distinct ages.
    record = study.run_study(
        study.SuspensionScenario(
            settle_s=1, maneuver_s=0.1, plant_step_s=0.001, logging_period_s=0.03
        ),
        plant_factory=ClockPlant,
    )
    for sample in record["payload"]["samples"]:
        t = sample["time_s"]
        sample["position_m"] = [t, 2 * t, 1 + t / 10]
        sample["wheel_position_m"] = [
            [10 + wheel, t + 2 * wheel, 0.5] for wheel in range(4)
        ]
        sample["suspension_spring_length_m"] = [
            0.11 * (wheel + 1) + t / 1000 for wheel in range(4)
        ]
        for field, age in (
            ("tire_force_source_time_s", 0.0002),
            ("tire_kinematics_source_time_s", 0.0004),
            ("applied_tire_force_source_time_s", 0.0008),
        ):
            sample[field] = t - age if t else None
        sample["applied_tire_force_geometry_time_s"] = t - 0.0001 if t else 0
    record["content_id"] = study._content_id(record["payload"])
    record["receipt_id"] = study._content_id(
        {key: value for key, value in record.items() if key != "receipt_id"}
    )
    return record


@pytest.fixture
def saved(tmp_path, saved_record):
    path = tmp_path / "saved.json"
    path.write_text(json.dumps(saved_record), encoding="utf-8")
    return path


def wait(root, condition):
    until = time.monotonic() + 5
    while not condition():
        root.update()
        if time.monotonic() > until:
            pytest.fail("bounded desktop operation did not finish")
        time.sleep(0.01)
    root.update()


def make_viewer(root, saved):
    from lapsim.ui.native_record_viewer import NativeRecordViewer

    viewer = NativeRecordViewer(root)
    viewer.load_path(saved)
    wait(root, lambda: not viewer.busy)
    assert viewer.record is not None, viewer.status.get()
    return viewer


def test_recorded_model_claim_displays_actual_synthetic_profile():
    from lapsim.ui.native_record_viewer import recorded_model_claim

    record = {
        "payload": {
            "model": {"profile_id": "chrono10_synthetic_sedan_shafts_brakes_v1"}
        }
    }
    assert (
        recorded_model_claim(record)
        == "Recorded model claim: chrono10_synthetic_sedan_shafts_brakes_v1"
    )


@pytest.mark.parametrize(
    "model",
    (
        {},
        {"profile_id": None},
        {"profile_id": 4},
        {"profile_id": []},
        {"profile_id": ""},
    ),
)
def test_recorded_model_claim_missing_or_nonstring_is_not_recorded(model):
    from lapsim.ui.native_record_viewer import recorded_model_claim

    assert (
        recorded_model_claim({"payload": {"model": model}})
        == "Recorded model claim: not recorded"
    )


def test_recorded_model_claim_bounds_and_escapes_untrusted_text():
    from lapsim.ui.native_record_viewer import recorded_model_claim

    profile = "A\nB\rC\tD\x00E\x1bF\x7f\u2028\u202e"
    record = {"payload": {"model": {"profile_id": profile}}}
    assert (
        recorded_model_claim(record)
        == r"Recorded model claim: A\nB\rC\tD\u0000E\u001bF\u007f\u2028\u202e"
    )
    assert record["payload"]["model"]["profile_id"] == profile
    long_profile = "x" * 8_000_000
    record["payload"]["model"]["profile_id"] = long_profile
    display = recorded_model_claim(record)
    assert display == "Recorded model claim: " + "x" * 77 + "…"
    assert len(display) == 100
    assert record["payload"]["model"]["profile_id"] is long_profile


def test_dynamics_lab_exposes_native_open_without_crowding_header(root, monkeypatch):
    monkeypatch.setattr("tkinter.filedialog.askopenfilename", lambda **kwargs: "")
    lab = DynamicsLab(root)
    lab.window.geometry("1120x720")
    root.update()
    assert hasattr(lab, "native_record_button"), (
        "Four-wheel lab has no saved native result entry"
    )
    button = lab.native_record_button
    assert button.winfo_ismapped()
    assert (
        button.winfo_rootx() + button.winfo_width()
        <= lab.window.winfo_rootx() + lab.window.winfo_width()
    )
    button.invoke()
    assert lab.latest_native_record_viewer.window.winfo_exists()
    lab.close()


def test_saved_selection_uses_exact_sample_and_distinct_clocks(root, saved):
    viewer = make_viewer(root, saved)
    assert viewer.model_claim.get() == "Recorded model claim: not recorded"
    boundary = next(
        i
        for i, s in enumerate(viewer.record["payload"]["samples"])
        if abs(s["time_s"] - 1) < 1e-9
    )
    viewer.select(boundary)
    assert viewer.selected_sample["time_s"] == pytest.approx(1, abs=1e-12)
    assert "State 1.000000" in viewer.clocks.get()
    assert "0.999800" in viewer.clocks.get() and "0.999600" in viewer.clocks.get()
    assert "0.999200" in viewer.clocks.get() and "0.999900" in viewer.clocks.get()
    assert viewer.selected_sample["command"]["braking"] == 0.2
    assert "braking 0.2" in viewer.values.get()
    assert list(viewer.com_marker.get_xdata()) == pytest.approx([1])
    assert list(viewer.wheel_markers[2].get_xdata()) == [12]
    assert list(viewer.spring_markers[0].get_ydata()) == pytest.approx([0.111])
    assert list(viewer.force_markers[0].get_xdata()) == pytest.approx([0.9992])
    viewer.force_kind.set("Computed")
    viewer.change_force()
    assert list(viewer.force_markers[0].get_xdata()) == pytest.approx([0.9998])
    viewer.select(0)
    assert "unavailable" in viewer.clocks.get()
    assert not viewer.force_markers[0].get_visible()
    assert min(viewer.force_axes.lines[0].get_xdata()) > 0
    viewer.step(-1)
    assert viewer.index.get() == 0
    viewer.select(10**6)
    assert viewer.index.get() == len(viewer.record["payload"]["samples"]) - 1
    viewer.close()


def test_historical_mismatch_remains_viewable_and_explicit(
    root, tmp_path, saved_record
):
    record = json.loads(json.dumps(saved_record))
    record["payload"]["model"]["profile_id"] = "historical_clock_fixture_only"
    record["payload"]["source"]["files_sha256"]["suspension_study.py"] = "0" * 64
    record["content_id"] = study._content_id(record["payload"])
    record["receipt_id"] = study._content_id(
        {key: value for key, value in record.items() if key != "receipt_id"}
    )
    path = tmp_path / "historical.json"
    path.write_text(json.dumps(record))
    viewer = make_viewer(root, path)
    assert (
        viewer.model_claim.get()
        == "Recorded model claim: historical_clock_fixture_only"
    )
    assert "mismatch" in viewer.checks.get()
    assert "fresh native replay not run" in viewer.checks.get()
    viewer.close()


def test_completed_load_queued_before_close_is_discarded(root, saved):
    from lapsim.ui.native_record_viewer import NativeRecordViewer

    viewer = NativeRecordViewer(root)
    viewer.load_path(saved)
    viewer.worker.join(timeout=3)
    assert not viewer.results.empty()
    viewer.close()
    assert viewer.results.empty() and viewer.record is None
    root.update()


def test_one_physical_arrow_selects_one_exported_sample(root, saved):
    viewer = make_viewer(root, saved)
    viewer.select(10)
    viewer.slider.focus_force()
    root.update()
    assert viewer.slider.focus_get() is viewer.slider
    assert int(viewer.slider.cget("highlightthickness")) >= 1
    viewer.slider.event_generate("<Right>")
    root.update()
    assert viewer.index.get() == 11
    viewer.slider.event_generate("<Left>")
    root.update()
    assert viewer.index.get() == 10
    viewer.slider.event_generate("<Home>")
    root.update()
    assert viewer.index.get() == 0
    viewer.slider.event_generate("<End>")
    root.update()
    assert viewer.index.get() == len(viewer.record["payload"]["samples"]) - 1
    viewer.close()


def test_finite_extreme_force_channel_is_limited_without_deferred_tk_error(
    root, tmp_path, saved_record, monkeypatch
):
    record = json.loads(json.dumps(saved_record))
    for index, sample in enumerate(record["payload"]["samples"]):
        sample["heading_rad"] = 1e308
        for force in sample["wheel_force_world_n"]:
            force[2] = 1e308 if index % 2 else -1e308
    record["content_id"] = study._content_id(record["payload"])
    record["receipt_id"] = study._content_id(
        {key: value for key, value in record.items() if key != "receipt_id"}
    )
    study.validate_study_record(record)
    path = tmp_path / "finite-extreme.json"
    path.write_text(json.dumps(record))
    errors = []
    monkeypatch.setattr(
        root, "report_callback_exception", lambda *args: errors.append(args)
    )
    viewer = make_viewer(root, path)
    before = path.read_bytes()
    assert "heading 1e+308 rad" in viewer.values.get()
    assert "inf" not in viewer.values.get()
    viewer.force_kind.set("Computed")
    viewer.change_force()
    root.update()
    assert errors == []
    assert "force plot unavailable" in viewer.status.get()
    assert viewer.record == record
    assert viewer.details_button.cget("state") == "normal"
    viewer.force_kind.set("Applied")
    viewer.change_force()
    root.update()
    assert "force plot unavailable" not in viewer.status.get()
    assert path.read_bytes() == before
    viewer.close()


def test_finite_height_render_failure_clears_result_and_recovers(
    root, saved, tmp_path, saved_record, monkeypatch
):
    from lapsim.ui.native_record_viewer import NativeRecordViewer

    record = json.loads(json.dumps(saved_record))
    record["payload"]["model"]["profile_id"] = "incoming_finite_height_fixture"
    for sample in record["payload"]["samples"]:
        sample["position_m"][2] = 1e308
    record["content_id"] = study._content_id(record["payload"])
    record["receipt_id"] = study._content_id(
        {key: value for key, value in record.items() if key != "receipt_id"}
    )
    study.validate_study_record(record)
    path = tmp_path / "finite-height.json"
    path.write_text(json.dumps(record))
    errors = []
    monkeypatch.setattr(
        root, "report_callback_exception", lambda *args: errors.append(args)
    )
    viewer = NativeRecordViewer(root)
    viewer.load_path(path)
    wait(root, lambda: not viewer.busy)
    assert errors == []
    assert viewer.record is None
    assert viewer.model_claim.get() == "Recorded model claim: not recorded"
    assert "Open failed" in viewer.status.get()
    assert viewer.details_button.cget("state") == "disabled"
    viewer.load_path(saved)
    wait(root, lambda: not viewer.busy)
    assert viewer.record is not None
    assert viewer.model_claim.get() == "Recorded model claim: not recorded"
    viewer.close()


def test_open_inspect_scrub_are_passive_and_preserve_input(root, saved, monkeypatch):
    before = saved.read_bytes()
    original_import = builtins.__import__

    def checked_import(name, *args, **kwargs):
        assert not name.startswith("pychrono") and "chrono_vehicle" not in name
        return original_import(name, *args, **kwargs)

    def unexpected(*args, **kwargs):
        pytest.fail("Passive viewer launched physics, planar reevaluation or a process")

    monkeypatch.setattr(builtins, "__import__", checked_import)
    monkeypatch.setattr(subprocess, "Popen", unexpected)
    monkeypatch.setattr(study, "run_study", unexpected)
    monkeypatch.setattr(study, "replay_study", unexpected)
    monkeypatch.setattr("lapsim.ui.dynamics_lab.evaluate_planar_dynamics", unexpected)
    viewer = make_viewer(root, saved)
    viewer.step(1)
    details = viewer.inspect()
    text = next(
        widget for widget in details.winfo_children() if isinstance(widget, tk.Text)
    )
    assert text.cget("state") == "disabled"
    value = json.loads(text.get("1.0", "end"))
    assert value["inspection"]["checks"]["fresh_native_replay"] == "not run"
    assert value["selected_sample"] == viewer.selected_sample
    assert saved.read_bytes() == before
    viewer.window.geometry("960x720")
    root.update()
    for widget in (
        viewer.open_button,
        viewer.details_button,
        viewer.previous_button,
        viewer.next_button,
        viewer.slider,
    ):
        assert widget.winfo_ismapped()
        assert (
            widget.winfo_rootx() + widget.winfo_width()
            <= viewer.window.winfo_rootx() + viewer.window.winfo_width()
        )
    viewer.close()


@pytest.mark.parametrize("failure", ("json", "plot"))
def test_bad_load_clears_old_result_and_fresh_load_recovers(
    root, saved, tmp_path, monkeypatch, failure
):
    prior = json.loads(saved.read_bytes())
    prior["payload"]["model"]["profile_id"] = "previous_record_fixture"
    prior["content_id"] = study._content_id(prior["payload"])
    prior["receipt_id"] = study._content_id(
        {key: value for key, value in prior.items() if key != "receipt_id"}
    )
    prior_path = tmp_path / "previous-profile.json"
    prior_path.write_text(json.dumps(prior))
    viewer = make_viewer(root, prior_path)
    assert viewer.model_claim.get() == "Recorded model claim: previous_record_fixture"
    bad = tmp_path / "invalid.json"
    bad.write_text("{invalid")
    renderer = viewer._draw_record
    if failure == "plot":

        def reject_plot():
            raise ValueError("stored channel range cannot be plotted")

        monkeypatch.setattr(viewer, "_draw_record", reject_plot)
    viewer.load_path(bad if failure == "json" else saved)
    assert viewer.record is None
    assert viewer.model_claim.get() == "Recorded model claim: not recorded"
    wait(root, lambda: not viewer.busy)
    assert "Open failed" in viewer.status.get()
    assert viewer.model_claim.get() == "Recorded model claim: not recorded"
    assert viewer.details_button.cget("state") == "disabled"
    monkeypatch.setattr(viewer, "_draw_record", renderer)
    viewer.load_path(saved)
    wait(root, lambda: not viewer.busy)
    assert viewer.record is not None
    assert viewer.model_claim.get() == "Recorded model claim: not recorded"
    viewer.close()


def test_close_during_single_load_discards_late_result(root, saved, monkeypatch):
    from lapsim.ui import native_record_viewer as module

    started, release = threading.Event(), threading.Event()
    reader = module.read_study_record

    def delayed(path):
        started.set()
        assert release.wait(3)
        return reader(path)

    monkeypatch.setattr(module, "read_study_record", delayed)
    viewer = module.NativeRecordViewer(root)
    viewer.load_path(saved)
    assert started.wait(1)
    assert viewer.load_path(saved) is False
    viewer.close()
    release.set()
    viewer.worker.join(timeout=3)
    assert not viewer.worker.is_alive()
    root.update()
    assert viewer.results.empty() and viewer.record is None


@pytest.mark.parametrize("alias_kind", ("exact", "hardlink"))
def test_self_test_report_alias_rejected_before_ui_or_writes(
    saved, tmp_path, monkeypatch, alias_kind
):
    from lapsim import desktop

    report = saved if alias_kind == "exact" else tmp_path / "report.json"
    if alias_kind == "hardlink":
        report.hardlink_to(saved)
    before, mtime = saved.read_bytes(), saved.stat().st_mtime_ns
    monkeypatch.setattr(
        desktop,
        "_check_native_record_viewer",
        lambda *args: pytest.fail("alias reached GUI"),
    )
    with pytest.raises(ValueError, match="must not overwrite"):
        desktop.self_test(report, native_record_path=saved)
    monkeypatch.setattr(
        sys,
        "argv",
        ["lapsim", "--self-test", str(report), "--self-test-native-record", str(saved)],
    )
    with pytest.raises(SystemExit) as error:
        desktop.main()
    assert error.value.code == 2
    assert saved.read_bytes() == before and saved.stat().st_mtime_ns == mtime


def test_native_self_test_flag_requires_report_and_dispatches(
    saved, tmp_path, monkeypatch
):
    from lapsim import desktop

    monkeypatch.setattr(
        sys, "argv", ["lapsim", "--self-test-native-record", str(saved)]
    )
    with pytest.raises(SystemExit) as error:
        desktop.main()
    assert error.value.code == 2
    report = tmp_path / "qa.json"
    calls = []

    def fake_self_test(path, *, native_record_path=None):
        calls.append((path, native_record_path))
        return {"status": "passed"}

    monkeypatch.setattr(desktop, "self_test", fake_self_test)
    monkeypatch.setattr(
        sys,
        "argv",
        ["lapsim", "--self-test", str(report), "--self-test-native-record", str(saved)],
    )
    assert desktop.main() == 0
    assert calls == [(report, saved)]


def test_failure_report_rechecks_new_hardlink_alias(saved, tmp_path, monkeypatch):
    from lapsim import desktop

    report = tmp_path / "qa.json"
    before, mtime = saved.read_bytes(), saved.stat().st_mtime_ns

    def fail_after_alias(path, *, native_record_path=None):
        path.hardlink_to(native_record_path)
        raise RuntimeError("workflow failed after another actor created report alias")

    monkeypatch.setattr(desktop, "self_test", fail_after_alias)
    monkeypatch.setattr(
        sys,
        "argv",
        ["lapsim", "--self-test", str(report), "--self-test-native-record", str(saved)],
    )
    assert desktop.main() == 1
    assert saved.read_bytes() == before and saved.stat().st_mtime_ns == mtime


def test_passive_viewer_self_test_reports_optional_scope(root, saved, monkeypatch):
    from lapsim import desktop

    def unexpected(*args, **kwargs):
        pytest.fail("Saved-record QA launched physics or a process")

    monkeypatch.setattr(subprocess, "Popen", unexpected)
    monkeypatch.setattr(study, "run_study", unexpected)
    monkeypatch.setattr(study, "replay_study", unexpected)
    empty = desktop._check_native_record_viewer(root)
    assert empty == {
        "empty_viewer_widgets": True,
        "saved_record": {"status": "not_requested"},
    }
    result = desktop._check_native_record_viewer(root, saved)["saved_record"]
    raw = json.loads(saved.read_bytes())
    assert result["status"] == "passed"
    assert (result["content_id"], result["receipt_id"]) == (
        raw["content_id"],
        raw["receipt_id"],
    )
    assert result["selected_samples"][0]["clocks"]["tire_force_source_time_s"] is None
    assert result["selected_samples"][1]["completed_interval_command"]["braking"] == 0.2
    assert result["force_channels"] == ["Applied", "Computed"]
    assert result["input_mtime_ns_before"] == result["input_mtime_ns_after"]
