"""End-to-end desktop wiring for the optional, assumed-corridor path mode."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from unittest.mock import patch

import pytest

from lapsim.experiments import RunRecord
from lapsim.events.endurance import LapProgressSnapshot
from lapsim.ui.app import LapSimDesktop
from lapsim.ui.presets import VehicleSetup


def test_live_view_clears_old_numbers_and_distinguishes_empty_failure() -> None:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    try:
        app = LapSimDesktop(root)
        for value in app.driver_values.values():
            value.set("previous run")
        for value in app.output_values.values():
            value.configure(text="previous run")
        app.driver_progress_var.set(700.0)
        with patch("lapsim.ui.app.threading.Thread"):
            app._start_run()

        assert app._active_tab == "Driver view"
        assert app.driver_playback is None
        assert app.driver_progress_var.get() == 0.0
        assert all(value.get() == "—" for value in app.driver_values.values())
        assert all(value["text"] == "—" for value in app.output_values.values())
        app.result_queue.put(("single", None, RuntimeError("planning failed")))
        with patch("lapsim.ui.app.messagebox.showerror"):
            app._poll_result()
        assert app.driver_run_label.get() == (
            "No accepted model step · calculation ended"
        )

        with patch("lapsim.ui.app.threading.Thread"):
            app._start_run()
        station_m = app.track.distance_m[1]
        app._queue_live_progress(
            "Prius", "Centerline model", app.track,
            LapProgressSnapshot(
                lap_index=0, cell_index=0, cell_count=app.track.cell_count,
                elapsed_time_s=1.0, lap_station_m=station_m,
                total_distance_m=station_m, speed_mps=4.0,
                lateral_acceleration_mps2=0.0,
            ),
        )
        app._poll_live_progress()
        assert app.driver_values["speed"].get() == "14.4"
        app.result_queue.put(("single", None, RuntimeError("later failure")))
        with patch("lapsim.ui.app.messagebox.showerror"):
            app._poll_result()
        assert app.driver_run_label.get().startswith("Last accepted step · ")
        assert app.driver_values["speed"].get() == "14.4"
    finally:
        root.destroy()


def test_ai_path_can_run_display_compare_and_save(tmp_path: Path) -> None:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    try:
        app = LapSimDesktop(root)
        assert app.driving_mode_var.get() == "Centerline (default)"
        assert app.course_geometry_audit.cells_with_chord_excess > 0
        assert any(
            widget.winfo_class() == "Label"
            and "Course data mismatch" in widget.cget("text")
            for widget in app._walk_widgets(root)
        )
        with patch("lapsim.ui.app.threading.Thread") as worker:
            app._start_run()
            assert worker.call_args.kwargs["target"].__name__ == "_calculate_single"
            worker.return_value.start.assert_called_once()
        for cell in range(3):
            app._queue_live_progress(
                "Prius live test", "Centerline model", app.track,
                LapProgressSnapshot(
                    lap_index=0, cell_index=cell, cell_count=app.track.cell_count,
                    elapsed_time_s=float(cell + 1),
                    lap_station_m=float((cell + 1) * 10),
                    total_distance_m=float((cell + 1) * 10),
                    speed_mps=10.0, lateral_acceleration_mps2=0.0,
                ),
            )
        assert app.progress_queue.qsize() == 1
        app._poll_live_progress()
        assert app._active_tab == "Driver view"
        assert app.driver_playback is not None
        assert app.driver_playback.frame_at(3.0).distance_m == pytest.approx(30.0)
        assert "accepted cell 3/" in app.driver_run_label.get()
        assert app.driver_play_button["state"] == "disabled"
        app._set_busy(False)
        app.driving_mode_var.set("AI racing line (experimental)")
        app._on_driving_mode_change()
        with patch("lapsim.ui.app.threading.Thread") as worker:
            app._start_run()
            assert worker.call_args.kwargs["target"].__name__ == "_calculate_ai_single"
            assert worker.call_args.kwargs["args"][-1] == (2.0, 1.8, 0.2)
            assert "Evaluating geometric centerline" in app.ai_result_text.get()
        app._set_busy(False)
        with patch("lapsim.ui.app.default_run_directory", return_value=tmp_path):
            app._calculate_ai_single(
                "prius_2026_le", "Prius integration test", VehicleSetup(),
                1.0, 1.0, (2.0, 1.78308, 0.3),
            )
            kind, payload, error = app.result_queue.get_nowait()
            assert error is None, error
            assert kind == "ai_single"
            assert app.progress_queue.qsize() == 1
            app._set_busy(True)
            app._poll_live_progress()
            assert "Half AI line" in app.driver_run_label.get()
            assert app.driver_playback is not None
            assert app.driver_playback.frame_at(
                app.driver_playback.duration_s
            ).distance_m == pytest.approx(app.driver_playback.track.length_m)
            app.result_queue.put((kind, payload, error))
            app._poll_result()
            root.update()

        assert app._last_result is not None and app._last_result.completed
        assert app._active_tab == "Driver view"
        assert app.driver_playback is not None
        assert app.driver_playback.track.length_m > 1000.0
        assert app.ai_compare_button is not None
        assert app.ai_compare_button["state"] == "normal"
        assert app.ai_output_values["baseline"]["text"] != "—"
        assert app.ai_output_values["candidate"]["text"] != "—"
        assert app.output_values["entry_speed"]["text"] != "—"
        assert app.output_values["exit_speed"]["text"] != "—"
        assert "different source curvature" in app.ai_result_text.get()
        records = list(tmp_path.glob("*.json"))
        assert len(records) == 1
        record = RunRecord.load(records[0]).to_dict()
        assert record["result"]["seam_speed_delta_mps"] == pytest.approx(
            record["result"]["ending_speed_mps"]
            - record["result"]["starting_speed_mps"]
        )
        planning = record["settings"]["path_planning"]
        assert planning["mode"] == "experimental_racing_line"
        assert planning["algorithm"].endswith("v3_winding_three_trial")
        assert len(planning["candidate_trials"]) == 2
        assert planning["corridor_fold_ratio_max"] < 0.98
        assert planning["candidate_trials"][0]["offset_strength"] == 1.0
        assert planning["candidate_length_m"] == pytest.approx(
            payload[5].candidate_track.length_m
        )
        assert record["settings"]["track"]["length_m"] == pytest.approx(
            app.driver_playback.track.length_m
        )
        app._show_path_comparison()
        root.update()
        assert any(isinstance(child, tk.Toplevel) for child in root.winfo_children())

        # A wider assumed corridor makes the full proposal slower for this
        # fixed benchmark. Exercise the conditional half-offset path through
        # the actual desktop record and driver-view wiring.
        with patch("lapsim.ui.app.default_run_directory", return_value=tmp_path):
            app._calculate_ai_single(
                "prius_2026_le", "Prius half-offset test", VehicleSetup(),
                1.0, 1.0, (3.0, 1.78308, 0.3),
            )
            kind, half_payload, error = app.result_queue.get_nowait()
            assert error is None, error
            assert kind == "ai_single"
            assert half_payload[3] == "candidate"
            assert half_payload[5].candidate_strength == 0.5
            assert half_payload[2] is half_payload[5].candidate_track
            app.result_queue.put((kind, half_payload, error))
            app._poll_result()
            root.update()

        half_record = RunRecord.load(
            tmp_path / f"{half_payload[7]}.json"
        ).to_dict()
        half_planning = half_record["settings"]["path_planning"]
        assert half_planning["selected_offset_strength"] == 0.5
        assert [trial["offset_strength"] for trial in half_planning["candidate_trials"]] == [
            1.0, 0.5,
        ]
        assert half_record["settings"]["track"]["length_m"] == pytest.approx(
            half_payload[5].candidate_track.length_m
        )
        assert app.driver_playback.track.length_m == pytest.approx(
            half_payload[5].candidate_track.length_m
        )
    finally:
        root.destroy()
