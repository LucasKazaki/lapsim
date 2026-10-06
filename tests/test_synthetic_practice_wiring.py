"""Practice-course identity survives desktop selection and saved settings."""

from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from unittest.mock import patch

import pytest

from lapsim.courses.course_bundle import course_geometry_sha256
from lapsim.events.endurance import EnduranceRunConfig
from lapsim.experiments import LapRunSettings
from lapsim.ui.app import LapSimDesktop
from lapsim.ui.course_catalog import (
    COURSE_OPTIONS,
    DEFAULT_COURSE_ID,
    SYNTHETIC_FSAE_COURSE_ID,
    course_source_metadata,
    load_course,
    solver_track_for_course,
)


def test_practice_source_and_refined_grid_survive_run_settings_json() -> None:
    spec = COURSE_OPTIONS[2]
    source = load_course(SYNTHETIC_FSAE_COURSE_ID)
    solver = solver_track_for_course(SYNTHETIC_FSAE_COURSE_ID, source, 0.25)
    source_metadata = course_source_metadata(spec, source)

    settings = LapRunSettings.from_track(
        solver,
        track_id=spec.course_id,
        solver_step_m=0.25,
        solver_settings={"path_constraint": "practice_course_regression"},
        torque_request_fraction=0.8,
        endurance_config=EnduranceRunConfig(laps=1),
        source_course=source_metadata,
        path_planning={"synthetic_course": spec.synthetic},
    ).to_dict()

    saved_track = settings["track"]
    assert saved_track["id"] == SYNTHETIC_FSAE_COURSE_ID
    assert settings["path_planning"]["synthetic_course"] is True
    assert saved_track["source_course"]["source_kind"] == "synthetic"
    assert saved_track["source_course"]["boundary_status"] == "absent"
    assert saved_track["source_course"]["source_geometry_sha256"] == (
        course_geometry_sha256(source)
    )
    assert "D.12.2.2" in saved_track["source_course"]["design_reference"]
    assert saved_track["source_course"]["design_reference_url"].startswith(
        "https://www.fsaeonline.com/"
    )
    assert saved_track["geometry_sha256"] == course_geometry_sha256(solver)
    assert saved_track["geometry_sha256"] != course_geometry_sha256(source)
    assert saved_track["cell_count"] == solver.cell_count
    assert saved_track["geometry"] == {
        "closed": True,
        "distance_m": list(solver.distance_m),
        "x_m": list(solver.x_m),
        "y_m": list(solver.y_m),
        "curvature_per_m": list(solver.curvature_per_m),
    }


def test_practice_course_is_selectable_without_changing_default(
    tmp_path: Path,
) -> None:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    try:
        with patch("lapsim.ui.app.default_run_directory", return_value=tmp_path / "runs"):
            app = LapSimDesktop(root)
        assert app.course_spec.course_id == DEFAULT_COURSE_ID
        menu = app.course_menu.nametowidget(app.course_menu["menu"])
        labels = tuple(menu.entrycget(index, "label") for index in range(menu.index("end") + 1))
        assert labels[:3] == tuple(spec.label for spec in COURSE_OPTIONS)

        app._select_course(COURSE_OPTIONS[2].label)
        assert app.course_spec.course_id == SYNTHETIC_FSAE_COURSE_ID
        assert app.course_spec.synthetic
        assert app.driving_mode_var.get() == "Centerline (default)"
        assert app.track == load_course(SYNTHETIC_FSAE_COURSE_ID)
        assert json.loads(app.course_source_json)["source_geometry_sha256"] == (
            course_geometry_sha256(app.track)
        )
        assert (app.ai_half_width_var.get(), app.ai_vehicle_width_var.get(),
                app.ai_margin_var.get()) == ("3", "1.8", "0.2")

        app._select_course(COURSE_OPTIONS[0].label)
        assert app.course_spec.course_id == DEFAULT_COURSE_ID
    finally:
        root.destroy()
