"""A selected road-aware detour is displayed, saved, and replayable."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from unittest.mock import patch

import pytest

from lapsim.dynamics.conditions import PlanarRoad, RectangularGripPatch
from lapsim.experiments import RunRecord, replay_lap_record
from lapsim.ui.app import LapSimDesktop
from lapsim.ui.course_catalog import COURSE_OPTIONS, SYNTHETIC_DEMO_COURSE_ID
from lapsim.ui.presets import VehicleSetup


def test_selected_detour_has_exact_saved_strategy_and_replays(
    tmp_path: Path,
) -> None:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    try:
        app = LapSimDesktop(root)
        synthetic = next(
            spec for spec in COURSE_OPTIONS
            if spec.course_id == SYNTHETIC_DEMO_COURSE_ID
        )
        app._select_course(synthetic.label)
        road = PlanarRoad(patches=(
            RectangularGripPatch(52.0, 57.0, 14.0, 16.0, 0.01),
        ))
        with patch("lapsim.ui.app.default_run_directory", return_value=tmp_path):
            app._calculate_ai_single(
                "prius_2026_le", "Prius detour sensitivity",
                VehicleSetup(torque_request_fraction=0.8), 1.0, 0.8,
                (3.0, 1.8, 0.2), road=road,
            )
            kind, payload, error = app.result_queue.get_nowait()
            assert error is None, error
            assert kind == "ai_single"
            comparison = payload[5]
            assert comparison.selected_mode == "candidate"
            assert comparison.candidate_strategy == "grip_detour"
            assert comparison.candidate_strength is None
            assert comparison.trials[-1].strategy == "grip_detour"
            assert comparison.trials[-1].lap_time_s == comparison.candidate_time_s

            app._set_busy(True)
            app.result_queue.put((kind, payload, None))
            app._poll_result()
            root.update()
            assert "Faster grip-aware detour selected" in app.ai_result_text.get()

        selected_path = tmp_path / f"{payload[7]}.json"
        selected = RunRecord.load(selected_path).to_dict()
        planning = selected["settings"]["path_planning"]
        assert planning["selected_strategy"] == "grip_detour"
        assert planning["selected_offset_strength"] is None
        assert planning["candidate_trials"][-1]["strategy"] == "grip_detour"
        assert planning["candidate_trials"][-1]["record_role"] == "selected_result"
        assert planning["grip_detour_search"]["status"] == "timed"
        assert replay_lap_record(selected_path).model_agreement
    finally:
        root.destroy()
