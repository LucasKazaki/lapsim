"""Selected car profiles reach the optional AI model, record, and replay.

The compact course is an analytic test fixture. The TREV intake is a partial
working scenario, and the saved Prius values are deliberately user assumptions.
Neither case is a measured vehicle or surveyed course validation.
"""

from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from unittest.mock import patch

import pytest

from lapsim.experiments import RunRecord, replay_lap_record
from lapsim.profiles import build_vehicle, list_profiles
from lapsim.ui.app import LapSimDesktop
from lapsim.ui.course_catalog import COURSE_OPTIONS, course_source_metadata, load_course
from lapsim.ui.garage import ProfileStore
from lapsim.ui.presets import VehicleSetup


@pytest.mark.parametrize("kind", ("trev_source", "saved_prius"))
def test_selected_profile_ai_path_records_exact_vehicle_and_replays(
    tmp_path: Path, kind: str,
) -> None:
    available = {profile.profile_id for profile in list_profiles()}
    if kind == "trev_source" and "trev5_working_geometry" not in available:
        pytest.skip("Optional local ENME408 source bundle is unavailable")

    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    try:
        store = ProfileStore(tmp_path / "car_profiles.json")
        with patch("lapsim.ui.app.ProfileStore", return_value=store):
            app = LapSimDesktop(root)

        spec = COURSE_OPTIONS[1]
        track = load_course(spec.course_id)
        assert track.length_m < 200.0
        app._select_course(spec.label)
        assert json.loads(app.course_source_json) == course_source_metadata(spec, track)

        if kind == "trev_source":
            profile_id = "trev5_working_geometry"
            expected_vehicle, source_manifest = build_vehicle(profile_id)
            expected_mass_kg = expected_vehicle.mass_kg
            assert any(
                field.path == "mass_kg" and field.source_id and field.artifact_id
                for field in source_manifest.selected_fields
            )
            assert expected_mass_kg != VehicleSetup().mass_kg
        else:
            custom_setup = VehicleSetup(
                mass_kg=1510.0, peak_power_kw=125.0, tire_mu=0.82,
            )
            saved = store.save("Prius ballast assumption", custom_setup)
            app._refresh_profile_menus()
            profile_id = saved.profile_id
            expected_mass_kg = custom_setup.mass_kg
        app._select_profile(profile_id)
        assert app.profile_display_to_id[app.profile_var.get()] == profile_id

        app.inputs["solver_step_m"].set("2")
        app.driving_mode_var.set("AI racing line (experimental)")
        app._on_driving_mode_change()
        assert app._ai_mode_selected()

        run_dir = tmp_path / kind
        with patch("lapsim.ui.app.threading.Thread") as thread:
            app._start_run()
            assert app.run_in_progress
            assert thread.call_args.kwargs["target"].__name__ == "_calculate_ai_single"
            frozen_args = thread.call_args.kwargs["args"]
            assert frozen_args[0] == profile_id
            assert frozen_args[3] == 2.0
            assert frozen_args[5] == (3.0, 1.8, 0.2)
        with patch("lapsim.ui.app.default_run_directory", return_value=run_dir):
            app._calculate_ai_single(*frozen_args)

        kind_name, payload, error = app.result_queue.get_nowait()
        assert error is None, error
        assert kind_name == "ai_single"
        assert payload[1].completed
        assert payload[5].trials
        assert payload[2] is payload[5].selected_track
        app.result_queue.put((kind_name, payload, error))
        app._poll_result()
        root.update_idletasks()
        assert app.driver_playback is not None
        assert app.driver_playback.track is payload[2]
        assert app._displayed_run_records == (("AI result", payload[7]),)

        selected_path = run_dir / f"{payload[7]}.json"
        selected = RunRecord.load(selected_path).to_dict()
        config = selected["configuration"]
        planning = selected["settings"]["path_planning"]
        geometry = selected["settings"]["track"]["geometry"]
        assert config["selected_profile_id"] == profile_id
        assert config["effective_vehicle_config"]["fields"]["mass_kg"] == pytest.approx(
            expected_mass_kg
        )
        assert selected["settings"]["track"]["source_course"]["selected_course_id"] == spec.course_id
        assert planning["mode"] == "experimental_racing_line"
        assert planning["source_course_id"] == spec.course_id
        assert planning["synthetic_course"] is True
        assert planning["user_requested_maximum_cell_length_m"] == 2.0
        assert planning["actual_maximum_cell_length_m"] <= 2.0 + 1e-10
        assert planning["candidate_trials"]
        assert geometry["distance_m"] == pytest.approx(payload[2].distance_m)
        assert geometry["x_m"] == pytest.approx(payload[2].x_m)
        assert geometry["y_m"] == pytest.approx(payload[2].y_m)
        assert geometry["curvature_per_m"] == pytest.approx(payload[2].curvature_per_m)

        if kind == "trev_source":
            manifest = config["base_profile_manifest"]
            assert manifest["profile_id"] == profile_id
            mass_source = next(
                field for field in manifest["selected_fields"]
                if field["path"] == "mass_kg"
            )
            assert mass_source["source_id"] and mass_source["artifact_id"]
            assert "not confirmed as-built" in mass_source["evidence_status"]
            assert config["user_overrides"] is None
        else:
            assert config["base_profile_manifest"]["profile_id"] == "prius_2026_le"
            assert config["user_overrides"]["mass_kg"] == custom_setup.mass_kg
            assert config["user_overrides"]["peak_power_kw"] == custom_setup.peak_power_kw
            assert config["user_overrides"]["tire_mu"] == custom_setup.tire_mu
            assert config["effective_config_differs_from_base"] is True

        assert replay_lap_record(selected_path).model_agreement
    finally:
        root.destroy()
