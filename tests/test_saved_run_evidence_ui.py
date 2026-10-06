"""Saved-run evidence stays tied to the result currently shown in the desktop."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from lapsim.ui.app import LapSimDesktop, _linked_ai_run_references, _run_evidence_text


PRIMARY_ID = "a" * 64
BASELINE_ID = "b" * 64
TRIAL_ID = "c" * 64


def _desktop() -> tuple[tk.Tk, LapSimDesktop]:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    return root, LapSimDesktop(root)


def _record(run_id: str, profile: str, *, planning: dict | None = None) -> dict:
    settings = {
        "track": {
            "id": "synthetic_solver_path",
            "cell_count": 206,
            "source_course": {
                "selected_course_id": "synthetic_rounded_rectangle_v1",
                "source_kind": "synthetic",
                "boundary_status": "absent",
            },
        },
    }
    if planning is not None:
        settings["path_planning"] = planning
    return {
        "run_id": run_id,
        "configuration": {"selected_profile_label": profile},
        "evidence_level": "simulation_model_estimate",
        "settings": settings,
        "result": {"status": "completed"},
    }


def _details_text(root: tk.Tk) -> str:
    windows = [child for child in root.winfo_children() if isinstance(child, tk.Toplevel)]
    assert len(windows) == 1
    widgets = list(windows[0].winfo_children())
    for widget in widgets:
        widgets.extend(widget.winfo_children())
        if isinstance(widget, tk.Text):
            return widget.get("1.0", "end-1c")
    raise AssertionError("saved-run details window has no selectable text")


def test_evidence_summary_names_model_limits_and_source_assumptions() -> None:
    planning = {
        "mode": "experimental_racing_line",
        "corridor": {"source": "user-assumed uniform half-width; no surveyed boundaries"},
        "rank_status": "invalid_processed_baseline",
        "diagnostic_only": True,
    }
    summary = _run_evidence_text(
        "AI result", Path("C:/runs") / f"{PRIMARY_ID}.json",
        _record(PRIMARY_ID, "Prius benchmark", planning=planning),
    )
    assert PRIMARY_ID in summary
    assert "simulation model estimate" in summary
    assert "synthetic: yes" in summary
    assert "Source boundary status: absent" in summary
    assert "user-assumed uniform half-width" in summary
    assert "diagnostic only: yes" in summary

    measured_source = _record(PRIMARY_ID, "Imported car", planning=planning)
    measured_source["settings"]["track"]["source_course"].update({
        "source_kind": "measured",
        "boundary_status": "measured",
        "source_cell_corridor": {"status": "measured", "used_by_ai_planner": False},
    })
    measured_summary = _run_evidence_text("AI result", Path("C:/runs/record.json"), measured_source)
    assert "Source boundary status: measured" in measured_summary
    assert "Source corridor: measured; used by AI planner: no" in measured_summary
    assert "AI corridor: user-assumed uniform half-width" in measured_summary


def test_linked_ai_references_include_only_saved_trials() -> None:
    planning = {
        "baseline_record": {"run_id": BASELINE_ID},
        "candidate_trials": [
            {"offset_strength": 0.5, "run_id": TRIAL_ID},
            {"offset_strength": 1.0, "run_id": None},
        ],
    }
    assert _linked_ai_run_references(planning) == (
        ("Geometric baseline", BASELINE_ID), ("AI offset 0.5×", TRIAL_ID),
    )


def test_ai_details_show_full_primary_and_linked_records_then_invalidate(tmp_path: Path) -> None:
    root, app = _desktop()
    try:
        assert app.saved_runs_button is not None
        assert app.saved_runs_button.cget("state") == "disabled"
        app._open_saved_run_details()
        assert not any(isinstance(child, tk.Toplevel) for child in root.winfo_children())

        planning = {
            "mode": "experimental_racing_line",
            "rank_status": "invalid_processed_baseline",
            "diagnostic_only": True,
            "corridor": {"source": "user-assumed uniform half-width"},
            "baseline_record": {"run_id": BASELINE_ID},
            "candidate_trials": [{"offset_strength": 0.5, "run_id": TRIAL_ID}],
        }
        records = {
            PRIMARY_ID: _record(PRIMARY_ID, "Prius", planning=planning),
            BASELINE_ID: _record(BASELINE_ID, "Prius"),
            TRIAL_ID: _record(TRIAL_ID, "Prius"),
        }
        app._set_displayed_run_records((("AI result", PRIMARY_ID),))
        assert app.saved_runs_button.cget("state") == "normal"
        with (
            patch("lapsim.ui.app.default_run_directory", return_value=tmp_path),
            patch("lapsim.ui.app.RunRecord.load", side_effect=lambda path: SimpleNamespace(
                to_dict=lambda: records[path.stem],
            )),
        ):
            app._open_saved_run_details()
        details = _details_text(root)
        for run_id in (PRIMARY_ID, BASELINE_ID, TRIAL_ID):
            assert run_id in details
            assert str((tmp_path / f"{run_id}.json").resolve()) in details
        assert "Geometric baseline" in details
        assert "AI offset 0.5×" in details

        app.inputs["road_grip_percent"].set("90")
        root.update_idletasks()
        assert app._displayed_run_records == ()
        assert app.saved_runs_button.cget("state") == "disabled"
        assert not any(isinstance(child, tk.Toplevel) for child in root.winfo_children())
    finally:
        root.destroy()


def test_comparison_result_exposes_both_files(tmp_path: Path) -> None:
    root, app = _desktop()
    try:
        completed = SimpleNamespace(completed=True)
        app.result_queue.put((
            "comparison",
            (1.0, 0.8, (("Car A", completed), ("Car B", completed)),
             (BASELINE_ID, TRIAL_ID), app.track, 1.0),
            None,
        ))
        with (
            patch.object(app, "_show_result"),
            patch.object(app, "_set_driver_run"),
            patch.object(app, "_show_comparison"),
        ):
            app._poll_result()
        assert app._displayed_run_records == (
            ("Car A", BASELINE_ID), ("Car B", TRIAL_ID),
        )
        records = {
            BASELINE_ID: _record(BASELINE_ID, "Car A"),
            TRIAL_ID: _record(TRIAL_ID, "Car B"),
        }
        with (
            patch("lapsim.ui.app.default_run_directory", return_value=tmp_path),
            patch("lapsim.ui.app.RunRecord.load", side_effect=lambda path: SimpleNamespace(
                to_dict=lambda: records[path.stem],
            )),
        ):
            app._open_saved_run_details()
        details = _details_text(root)
        assert f"Car A\nRecord ID: {BASELINE_ID}" in details
        assert f"Car B\nRecord ID: {TRIAL_ID}" in details
    finally:
        root.destroy()


def test_saved_failed_lap_remains_inspectable_until_inputs_change() -> None:
    root, app = _desktop()
    try:
        failed = SimpleNamespace(completed=False, failure_reason="model stopped")
        app.result_queue.put((
            "single", ("Prius", 1.0, failed, PRIMARY_ID, app.track), None,
        ))
        with patch("lapsim.ui.app.messagebox.showerror"):
            app._poll_result()
        assert app._displayed_run_records == (("Lap result", PRIMARY_ID),)
        assert app.saved_runs_button is not None
        assert app.saved_runs_button.cget("state") == "normal"
        app.inputs["torque_request_percent"].set("75")
        root.update_idletasks()
        assert app._displayed_run_records == ()
        assert app.saved_runs_button.cget("state") == "disabled"
    finally:
        root.destroy()


def test_missing_saved_file_reports_error_in_details(tmp_path: Path) -> None:
    root, app = _desktop()
    try:
        app._set_displayed_run_records((("Lap result", PRIMARY_ID),))
        with (
            patch("lapsim.ui.app.default_run_directory", return_value=tmp_path),
            patch("lapsim.ui.app.RunRecord.load", side_effect=FileNotFoundError("file removed")),
        ):
            app._open_saved_run_details()
        details = _details_text(root)
        assert PRIMARY_ID in details
        assert "Could not read saved run: file removed" in details
    finally:
        root.destroy()
