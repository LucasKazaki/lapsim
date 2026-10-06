"""End-to-end desktop wiring for the optional, assumed-corridor path mode."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from unittest.mock import patch

import pytest

from lapsim.experiments import RunRecord
from lapsim.ui.app import LapSimDesktop
from lapsim.ui.presets import VehicleSetup


def test_ai_path_can_run_display_compare_and_save(tmp_path: Path) -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display unavailable")
    root.withdraw()
    try:
        app = LapSimDesktop(root)
        assert app.driving_mode_var.get() == "Centerline (default)"
        with patch("lapsim.ui.app.threading.Thread") as worker:
            app._start_run()
            assert worker.call_args.kwargs["target"].__name__ == "_calculate_single"
            worker.return_value.start.assert_called_once()
        app._set_busy(False)
        app.driving_mode_var.set("AI racing line (experimental)")
        app._on_driving_mode_change()
        with patch("lapsim.ui.app.threading.Thread") as worker:
            app._start_run()
            assert worker.call_args.kwargs["target"].__name__ == "_calculate_ai_single"
            assert worker.call_args.kwargs["args"][-1] == (2.0, 1.8, 0.2)
        app._set_busy(False)
        with patch("lapsim.ui.app.default_run_directory", return_value=tmp_path):
            app._calculate_ai_single(
                "prius_2026_le", "Prius integration test", VehicleSetup(),
                1.0, 1.0, (2.0, 1.78308, 0.3),
            )
            kind, payload, error = app.result_queue.get_nowait()
            assert error is None, error
            assert kind == "ai_single"
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
        assert "different source curvature" in app.ai_result_text.get()
        records = list(tmp_path.glob("*.json"))
        assert len(records) == 1
        record = RunRecord.load(records[0]).to_dict()
        assert record["settings"]["path_planning"]["mode"] == "experimental_racing_line"
        assert record["settings"]["track"]["length_m"] == pytest.approx(
            app.driver_playback.track.length_m
        )
        app._show_path_comparison()
        root.update()
        assert any(isinstance(child, tk.Toplevel) for child in root.winfo_children())
    finally:
        root.destroy()
