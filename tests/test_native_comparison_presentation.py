"""Pure saved-pair presentation and job ownership; no Tk root or physics."""

import builtins
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from queue import Queue
import subprocess
import threading
from types import SimpleNamespace

import pytest

from test_suspension_compare import canonical_world_si_claims, fixture_record, seal


def test_saved_pair_summary_uses_explicit_endpoint_and_receipt_scope():
    from lapsim.experiments.suspension_compare import compare_study_records
    from lapsim.ui.native_record_viewer import comparison_summary

    report = compare_study_records(
        canonical_world_si_claims(fixture_record()),
        canonical_world_si_claims(fixture_record(step=0.0005)),
        kind="plant-step",
    )
    text = comparison_summary(report)
    assert "Right - Left" in text
    assert "World-X velocity (m/s)" in text
    assert "Saved-fixture endpoint criterion: not applied" in text
    assert report["report_id"][:12] in text
    assert "not a complete environment" in text


def test_discarded_completion_releases_owner_without_publishing():
    from lapsim.ui.native_record_viewer import NativeRecordViewer

    viewer = object.__new__(NativeRecordViewer)
    viewer.closed = False
    viewer.busy = True
    viewer.active_job = 4
    viewer.generation = 5
    published = []
    viewer._sync_comparison_controls = lambda: None
    viewer._show_record = lambda *args: published.append("record")
    viewer._show_comparison = lambda *args: published.append("comparison")
    viewer._accept_result(4, "comparison", SimpleNamespace(), None)
    assert viewer.busy is False
    assert viewer.active_job is None
    assert published == []


def report_pair(*, kind="logging-period"):
    from lapsim.experiments.suspension_compare import compare_study_records

    left = fixture_record()
    right = (
        fixture_record(logging=0.05)
        if kind == "logging-period"
        else fixture_record(step=0.0005)
    )
    if kind == "plant-step":
        canonical_world_si_claims(left)
        canonical_world_si_claims(right)
    return left, right, compare_study_records(left, right, kind=kind)


def test_endpoint_rows_use_saved_right_minus_left_and_keep_actual_state_times():
    from lapsim.experiments.suspension_compare import compare_study_records
    from lapsim.ui.native_record_viewer import comparison_summary

    left, right, _ = report_pair(kind="plant-step")
    final = right["payload"]["samples"][-1]
    final["velocity_mps"][0] += 0.02
    final["position_m"][2] += 0.0002
    final["suspension_spring_length_m"][2] += 0.0003
    right["payload"]["metrics"]["final_speed_mps"] = final["velocity_mps"][0]
    right["payload"]["metrics"]["final_chassis_com_height_m"] = final["position_m"][2]
    seal(right)
    report = compare_study_records(left, right, kind="plant-step")
    text = comparison_summary(report)
    lines = text.splitlines()
    a, b = left["payload"]["samples"][-1], right["payload"]["samples"][-1]
    for label, x, y in (
        ("World-X velocity (m/s)", a["velocity_mps"][0], b["velocity_mps"][0]),
        ("Chassis COM height (m)", a["position_m"][2], b["position_m"][2]),
        *[
            (name + " spring length (m)", x, y)
            for name, x, y in zip(
                ("FL", "FR", "RL", "RR"),
                a["suspension_spring_length_m"],
                b["suspension_spring_length_m"],
                strict=True,
            )
        ],
    ):
        values = next(line for line in lines if line.startswith(label)).split()[-3:]
        assert list(map(float, values)) == pytest.approx([x, y, y - x])
    assert f"Left {a['time_s']!r} s; Right {b['time_s']!r} s" in text
    assert "Cached computed/applied forces retain their own origins" in text
    reverse = comparison_summary(compare_study_records(right, left, kind="plant-step"))
    value = next(
        line
        for line in reverse.splitlines()
        if line.startswith("World-X velocity (m/s)")
    )
    assert float(value.split()[-1]) == pytest.approx(-0.02)


def test_logging_counts_are_exact_and_shared_only():
    from lapsim.ui.native_record_viewer import comparison_summary

    left, right, report = report_pair()
    a = {sample["time_s"] for sample in left["payload"]["samples"]}
    b = {sample["time_s"] for sample in right["payload"]["samples"]}
    text = comparison_summary(report)
    assert f"Exact shared state timestamps: {len(a & b)}" in text
    assert f"Unmatched exports: Left {len(a - b)}; Right {len(b - a)}" in text
    assert "Shared observations match: yes" in text
    assert (
        "Shared-only agreement does not establish equality of unmatched exports" in text
    )
    assert "no interpolation or index alignment" in text
    assert "endpoint criterion" not in text


def test_incompatibility_has_reasons_and_no_numerical_table():
    from lapsim.experiments.suspension_compare import compare_study_records
    from lapsim.ui.native_record_viewer import comparison_summary

    report = compare_study_records(
        fixture_record(), fixture_record(step=0.0005), kind="logging-period"
    )
    text = comparison_summary(report)
    assert "Recorded inputs are incompatible" in text
    assert "payload.scenario.plant_step_s differs" in text
    assert "No numerical result" in text
    assert "Right - Left" not in text
    assert "Shared observations match" not in text


@pytest.mark.parametrize("passed", (True, False))
def test_applied_criterion_label_is_explicitly_on_saved_claims(passed):
    from lapsim.ui.native_record_viewer import comparison_summary

    _, _, report = report_pair(kind="plant-step")
    # Presentation-only branch fixture; not a native criterion execution.
    report["result"]["criterion"] = {
        "status": "applied to recorded fixture claims",
        "passed": passed,
    }
    text = comparison_summary(report)
    assert (
        "Saved-fixture endpoint criterion: applied to recorded fixture claims · "
        + ("passed" if passed else "failed")
        in text
    )
    assert "not new native acceptance or a convergence proof" in text


def test_unavailable_sources_remain_inspectable_and_do_not_borrow_recipe_id(
    tmp_path, monkeypatch
):
    from lapsim.experiments import suspension_compare as comparison
    from lapsim.experiments import suspension_study as study
    from lapsim.ui.native_record_viewer import comparison_summary

    left, right, _ = report_pair(kind="plant-step")
    monkeypatch.setattr(
        comparison,
        "__file__",
        str(tmp_path / "missing/experiments/suspension_compare.py"),
    )

    def unavailable():
        raise OSError("not installed")

    monkeypatch.setattr(study, "_implementation_source", unavailable)
    report = comparison.compare_study_records(left, right, kind="plant-step")
    text = comparison_summary(report)
    assert "Compatible recorded inputs" in text
    assert "Comparison recipe: incomplete · ID unavailable" in text
    assert "Left: unavailable; current implementation files could not be read" in text
    assert "Saved-fixture endpoint criterion: not applied" in text


def test_visible_claims_are_bounded_and_control_characters_are_visible():
    from lapsim.ui.native_record_viewer import _bounded_claim

    text = _bounded_claim("right\n\u202e\t" + "x" * 8_000_000)
    assert len(text) <= 120
    assert "\\n\\u202e\\t" in text
    assert "\n" not in text and "\u202e" not in text
    assert text.endswith("…")


def worker_viewer():
    from lapsim.ui.native_record_viewer import NativeRecordViewer

    viewer = object.__new__(NativeRecordViewer)
    viewer.load_lock = threading.Lock()
    viewer.stopped = threading.Event()
    viewer.results = Queue(maxsize=1)
    return viewer


def test_worker_is_passive_and_retains_complete_report_and_each_clock(
    tmp_path, monkeypatch
):
    from lapsim.experiments import suspension_study as study
    import tkinter as tk

    left, right, _ = report_pair(kind="plant-step")
    path = tmp_path / "right.json"
    path.write_text(json.dumps(right), encoding="utf-8")
    before = path.read_bytes(), path.stat().st_mtime_ns
    left_before = deepcopy(left)
    original_import = builtins.__import__

    def checked_import(name, *args, **kwargs):
        assert not name.startswith("pychrono") and "chrono_vehicle" not in name
        return original_import(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("Pure pair worker created a window, process, or physics run")

    monkeypatch.setattr(builtins, "__import__", checked_import)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(tk, "Tk", forbidden)
    monkeypatch.setattr(tk, "Toplevel", forbidden)
    for name in ("run_study", "replay_study", "_source", "_code_identity"):
        monkeypatch.setattr(study, name, forbidden)
    viewer = worker_viewer()
    viewer._load_comparison(left, path, "plant-step", 7)
    generation, kind, value, error = viewer.results.get_nowait()
    assert (generation, kind, error) == (7, "comparison", None)
    report, _, detail, identity = value
    assert json.loads(detail) == report
    assert right["content_id"][:12] in identity
    assert (
        right["receipt_id"]
        == report["inputs"]["right"]["inspection"]["saved_receipt_id"]
    )
    assert left == left_before
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    for role, record in (("left", left), ("right", right)):
        sample = record["payload"]["samples"][-1]
        context = report["result"]["final_observation_context"][role]
        assert context["clocks"] == {
            key: sample[key]
            for key in (
                "time_s",
                "tire_force_source_time_s",
                "tire_kinematics_source_time_s",
                "applied_tire_force_source_time_s",
                "applied_tire_force_geometry_time_s",
            )
        }
        assert context["completed_interval_command"] == sample["command"]
    assert (
        sha256(
            json.dumps(
                {key: value for key, value in report.items() if key != "receipt_id"},
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
        == report["receipt_id"]
    )


@pytest.mark.parametrize("job", ("record", "comparison"))
def test_worker_read_failure_is_queued_not_published_or_raised(tmp_path, job):
    viewer = worker_viewer()
    path = tmp_path / "bad.json"
    path.write_text("{invalid", encoding="utf-8")
    if job == "record":
        viewer._load(path, 3)
    else:
        viewer._load_comparison(fixture_record(), path, "logging-period", 3)
    generation, kind, value, error = viewer.results.get_nowait()
    assert (generation, kind, value) == (3, job, None)
    assert isinstance(error, str) and error


def test_empty_failure_message_clears_pair_instead_of_unpacking_missing_result():
    viewer = worker_viewer()
    viewer.comparison_window = object()
    viewer.comparison_right = Value("old right")
    viewer.comparison_report = {"old": "report"}
    viewer.comparison_json = "old report"
    shown = []
    viewer._set_comparison_text = shown.append
    viewer._show_comparison(None, "")
    assert viewer.comparison_report is viewer.comparison_json is None
    assert viewer.comparison_right.get() == "Right: record was not opened"
    assert "Comparison failed" in shown[0]


def test_stopped_viewer_discards_worker_result(tmp_path):
    viewer = worker_viewer()
    viewer.stopped.set()
    path = tmp_path / "right.json"
    path.write_text(json.dumps(fixture_record(logging=0.05)), encoding="utf-8")
    viewer._load_comparison(fixture_record(), path, "logging-period", 5)
    assert viewer.results.empty()


@pytest.mark.parametrize("failure", ("oversized", "overflow"))
def test_pair_worker_errors_keep_bounded_reader_and_finite_difference_policy(
    tmp_path, failure
):
    from lapsim.experiments import suspension_study as study

    left, right, _ = report_pair(kind="plant-step")
    path = tmp_path / "right.json"
    if failure == "oversized":
        path.write_bytes(b" " * (study.MAX_BYTES + 1))
    else:
        left["payload"]["samples"][-1]["position_m"][2] = 1e308
        right["payload"]["samples"][-1]["position_m"][2] = -1e308
        seal(left)
        seal(right)
        path.write_text(json.dumps(right), encoding="utf-8")
    viewer = worker_viewer()
    viewer._load_comparison(left, path, "plant-step", 8)
    generation, kind, value, error = viewer.results.get_nowait()
    assert (generation, kind, value) == (8, "comparison", None)
    assert ("exceeds" if failure == "oversized" else "overflow") in error


def test_busy_comparison_does_not_disable_primary_sample_inspection():
    viewer = worker_viewer()
    viewer.record = object()
    viewer.busy = True
    viewer.comparison_window = object()
    viewer.comparison_kind = Value("plant-step")
    viewer.comparison_report = None
    states = {}
    for name in (
        "open_button",
        "compare_button",
        "comparison_choose_button",
        "comparison_details_button",
    ):
        setattr(
            viewer,
            name,
            SimpleNamespace(
                configure=lambda *, state, key=name: states.update({key: state})
            ),
        )

    def forbidden(**kwargs):
        pytest.fail("Comparison disabled primary sample inspection")

    for name in (
        "details_button",
        "previous_button",
        "next_button",
        "slider",
        "force_menu",
    ):
        setattr(viewer, name, SimpleNamespace(configure=forbidden))
    viewer._sync_comparison_controls()
    assert states == {
        "open_button": "disabled",
        "compare_button": "normal",
        "comparison_choose_button": "disabled",
        "comparison_details_button": "disabled",
    }


def test_radio_arrows_are_local_wrap_and_return_break_without_extra_selection():
    viewer = worker_viewer()
    viewer.closed = False
    viewer.comparison_window = object()
    calls = []
    viewer.comparison_kind_buttons = [
        SimpleNamespace(
            focus_set=lambda at=index: calls.append((at, "focus")),
            invoke=lambda at=index: calls.append((at, "select")),
        )
        for index in range(2)
    ]
    assert viewer._comparison_kind_key(1, 1) == "break"
    assert calls == [(0, "focus"), (0, "select")]
    calls.clear()
    assert viewer._comparison_kind_key(0, -1) == "break"
    assert calls == [(1, "focus"), (1, "select")]


@pytest.mark.parametrize("kind", ("record", "comparison"))
def test_current_completion_releases_and_publishes_only_matching_owner(kind):
    viewer = worker_viewer()
    viewer.active_job = viewer.generation = 6
    viewer.busy = True
    published = []
    viewer._sync_comparison_controls = lambda: published.append("controls")
    viewer._show_record = lambda value, error: published.append(
        ("record", value, error)
    )
    viewer._show_comparison = lambda value, error: published.append(
        ("comparison", value, error)
    )
    viewer._accept_result(5, kind, "wrong owner", None)
    assert viewer.active_job == 6 and viewer.busy and published == []
    viewer._accept_result(6, kind, "current", None)
    assert viewer.active_job is None and not viewer.busy
    assert published == [(kind, "current", None), "controls"]


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_kind_reset_invalidates_publication_but_keeps_worker_owned():
    viewer = worker_viewer()
    viewer.generation = viewer.active_job = 7
    viewer.busy = True
    viewer.comparison_window = object()
    viewer.comparison_report = {"old": "result"}
    viewer.comparison_json = "old report"
    viewer.comparison_right = Value("old right identity")
    destroyed = []
    viewer.comparison_details_window = SimpleNamespace(
        destroy=lambda: destroyed.append(True)
    )
    viewer._set_comparison_text = lambda value: None
    viewer._sync_comparison_controls = lambda: None
    viewer._reset_comparison()
    assert viewer.generation == 8 and viewer.active_job == 7 and viewer.busy
    assert viewer.comparison_report is viewer.comparison_json is None
    assert viewer.comparison_right.get() == "Right: no record selected"
    assert destroyed == [True]
    viewer._show_comparison = lambda *args: pytest.fail("stale result published")
    viewer._accept_result(7, "comparison", "old", None)
    assert not viewer.busy and viewer.active_job is None


def test_close_invalidates_comparison_without_cancelling_other_ownership():
    viewer = worker_viewer()
    viewer.closed = False
    viewer.generation = viewer.active_job = 9
    viewer.busy = True
    destroyed = []
    viewer.comparison_window = SimpleNamespace(destroy=lambda: destroyed.append("pair"))
    viewer.comparison_details_window = SimpleNamespace(
        destroy=lambda: destroyed.append("details")
    )
    viewer.compare_button = SimpleNamespace(
        focus_force=lambda: destroyed.append("focus")
    )
    viewer.comparison_left = Value("old left identity")
    viewer.comparison_right = Value("old right identity")
    viewer.comparison_kind = Value("plant-step")
    viewer.comparison_report = {"old": "report"}
    viewer.comparison_json = "old report"
    viewer.close_comparison()
    assert (
        viewer.comparison_window
        is viewer.comparison_report
        is viewer.comparison_json
        is None
    )
    assert viewer.generation == 10 and viewer.active_job == 9 and viewer.busy
    assert viewer.comparison_left.get() == ""
    assert viewer.comparison_right.get() == "Right: no record selected"
    assert viewer.comparison_kind.get() == ""
    assert destroyed == ["details", "pair", "focus"]


@pytest.mark.parametrize(
    "busy,kind", ((True, "plant-step"), (False, ""), (False, "invented"))
)
def test_invalid_or_overlapping_request_keeps_old_result_without_starting(busy, kind):
    viewer = worker_viewer()
    viewer.closed = False
    viewer.busy = busy
    viewer.record = {"left": "snapshot"}
    viewer.comparison_window = object()
    viewer.comparison_kind = Value(kind)
    old = viewer.comparison_report = {"prior": "result"}
    assert viewer.compare_path(Path("never-opened.json")) is False
    assert viewer.comparison_report is old
