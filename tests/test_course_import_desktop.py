"""Desktop import of a versioned, numerically coherent course bundle."""

from __future__ import annotations

from dataclasses import replace
from math import pi
from pathlib import Path
import tkinter as tk
from unittest.mock import patch

import pytest

from lapsim.courses.course_bundle import CourseBundle, course_geometry_sha256
from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Track
from lapsim.experiments import RunRecord, replay_lap_record
from lapsim.ui.app import LapSimDesktop
from lapsim.ui.course_catalog import (
    SYNTHETIC_DEMO_COURSE_ID, load_course, load_imported_course_catalog,
)
from lapsim.ui.presets import VehicleSetup


def _bundle() -> CourseBundle:
    track = SpatialTrack.from_track(
        Track.from_segments([Curve(radius_m=10.0, span_rad=2.0 * pi)]),
        maximum_cell_length_m=2.0,
    )
    return CourseBundle.from_dict({
        "schema_version": 1,
        "course_id": "practice_circle",
        "revision": "r1",
        "label": "Practice circle",
        "description": "Synthetic import exercise for course provenance.",
        "source_kind": "synthetic",
        "provenance": {
            "source_name": "Analytic circle",
            "source_sha256": None,
            "processing_method": "Exact circular arcs",
            "review_note": "No measured course or boundaries",
        },
        "coordinate_frame": {
            "type": "local_cartesian_right_handed_xy",
            "units": "m",
            "origin": "Start",
            "x_axis": "east",
            "y_axis": "north",
        },
        "travel_direction": "counterclockwise",
        "boundary_status": "absent",
        "ai_defaults": {
            "width_source": "assumed_uniform",
            "half_width_m": 2.5,
            "vehicle_width_m": 1.8,
            "safety_margin_m": 0.2,
        },
        "geometry": {
            "model": "piecewise_constant_curvature_arcs",
            "closed": True,
            "distance_m": list(track.distance_m),
            "x_m": list(track.x_m),
            "y_m": list(track.y_m),
            "curvature_per_m": list(track.curvature_per_m),
        },
        "geometry_sha256": course_geometry_sha256(track),
    })


def _rounded_rectangle_bundle() -> CourseBundle:
    """A coherent imported course that exercises nonzero AI offset trials."""

    track = load_course(SYNTHETIC_DEMO_COURSE_ID)
    manifest = _bundle().to_dict()
    manifest["course_id"] = "practice_rounded_rectangle"
    manifest["label"] = "Imported rounded rectangle"
    manifest["description"] = "Analytic closed import for optional AI integration."
    manifest["provenance"]["source_name"] = "Analytic rounded rectangle"
    manifest["ai_defaults"]["half_width_m"] = 3.0
    manifest["geometry"] = {
        "model": "piecewise_constant_curvature_arcs",
        "closed": True,
        "distance_m": list(track.distance_m),
        "x_m": list(track.x_m),
        "y_m": list(track.y_m),
        "curvature_per_m": list(track.curvature_per_m),
    }
    manifest["geometry_sha256"] = course_geometry_sha256(track)
    return CourseBundle.from_dict(manifest)


def test_imported_course_runs_and_saves_source_identity(tmp_path: Path) -> None:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    try:
        app = LapSimDesktop(root)
        app._last_result = object()
        source_file = _bundle().save(tmp_path / "practice.json")
        expected = CourseBundle.load(source_file)
        run_dir = tmp_path / "runs"
        with patch("lapsim.ui.app.default_run_directory", return_value=run_dir):
            app._import_course_bundle(source_file)
            assert app.course_spec.course_id == "imported:practice_circle@r1"
            assert app._last_result is None
            assert app.track == expected.track
            assert app.course_var.get().startswith("Imported · Practice circle")
            assert "No measured boundaries" in app._course_notice_text()
            assert (run_dir.parent / "courses" / f"{expected.bundle_sha256}.json").exists()
            assert app._read_run_settings()[1] > 0.0

            app._calculate_single(
                "prius_2026_le", "Prius imported circle",
                VehicleSetup(torque_request_fraction=0.8), 1.0, 0.8,
            )
            kind, payload, error = app.result_queue.get_nowait()
            assert error is None, error
            assert kind == "single"
            assert payload[2].completed

        record_path = run_dir / f"{payload[3]}.json"
        record = RunRecord.load(record_path).to_dict()
        source = record["settings"]["track"]["source_course"]
        assert source["selected_course_id"] == "imported:practice_circle@r1"
        assert source["revision"] == "r1"
        assert source["bundle_sha256"] == expected.bundle_sha256
        assert source["source_geometry_sha256"] == expected.geometry_sha256
        assert source["boundary_status"] == "absent"
        assert record["settings"]["track"]["geometry_sha256"] != expected.geometry_sha256
        assert replay_lap_record(record_path).model_agreement

        changed = expected.to_dict()
        changed["description"] = "Different content under the same revision"
        changed_file = CourseBundle.from_dict(changed).save(tmp_path / "changed.json")
        with patch("lapsim.ui.app.default_run_directory", return_value=run_dir):
            with pytest.raises(ValueError, match="new revision"):
                app._import_course_bundle(changed_file)
    finally:
        root.destroy()


def test_imported_coherent_course_ai_trials_save_and_replay(
    tmp_path: Path,
) -> None:
    bundle = _rounded_rectangle_bundle()
    source_file = bundle.save(tmp_path / "source.json")
    run_dir = tmp_path / "runs"
    with patch("lapsim.ui.app.default_run_directory", return_value=run_dir):
        try:
            root = tk.Tk()
        except tk.TclError as error:
            pytest.skip(f"Tk display unavailable: {error}")
        root.withdraw()
        try:
            app = LapSimDesktop(root)
            app._import_course_bundle(source_file)
            assert app.driving_mode_var.get() == "Centerline (default)"
            assert app.track == bundle.track
            app._calculate_ai_single(
                "prius_2026_le", "Prius imported AI exercise",
                VehicleSetup(torque_request_fraction=0.8), 1.0, 0.8,
                (3.0, 1.8, 0.2),
            )
            kind, payload, error = app.result_queue.get_nowait()
            assert error is None, error
            assert kind == "ai_single"
            comparison = payload[5]
            assert comparison.rank_status == "candidate_selected"
            assert len(comparison.trials) == 3
            completed_trials = [
                trial for trial in comparison.trials
                if trial.run is not None and trial.run.completed
            ]
            skipped_trials = [
                trial for trial in comparison.trials if trial.run is None
            ]
            assert len(completed_trials) == 2
            assert len(skipped_trials) == 1
            assert skipped_trials[0].path_audit is not None
            assert not skipped_trials[0].path_audit.valid
            app._set_busy(True)
            app.result_queue.put((kind, payload, error))
            app._poll_result()
            assert app.driver_replay_menu is not None
            assert app.driver_replay_menu["state"] == "normal"

            primary_path = run_dir / f"{payload[7]}.json"
            primary = RunRecord.load(primary_path).to_dict()
            planning = primary["settings"]["path_planning"]
            source = primary["settings"]["track"]["source_course"]
            assert planning["trial_record_manifest_version"] == 1
            assert planning["selected_mode"] == "candidate"
            assert len(planning["candidate_trials"]) == 3
            assert source["selected_course_id"] == (
                "imported:practice_rounded_rectangle@r1"
            )
            assert source["bundle_sha256"] == bundle.bundle_sha256
            assert source["source_geometry_sha256"] == bundle.geometry_sha256
            assert len(list(run_dir.glob("*.json"))) == 3
            assert planning["baseline_record"]["run_id"] is not None
            assert sum(row["record_role"] == "selected_result"
                       for row in planning["candidate_trials"]) == 1
            for path in run_dir.glob("*.json"):
                record = RunRecord.load(path).to_dict()
                assert record["settings"]["track"]["source_course"] == source
                assert replay_lap_record(path).model_agreement
            for row in planning["candidate_trials"]:
                if row["record_role"] == "no_run":
                    assert row["run_id"] is None
                    assert row["model_run_completed"] is None
                    assert "Model run skipped" in row["error"]
                elif row["record_role"] != "selected_result":
                    assert (run_dir / f"{row['run_id']}.json").exists()
        finally:
            root.destroy()


def test_car_comparison_records_share_the_selected_source(tmp_path: Path) -> None:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    try:
        app = LapSimDesktop(root)
        app._select_course(app.course_options[1].label)
        setup_a = VehicleSetup(torque_request_fraction=0.8)
        setup_b = replace(setup_a, mass_kg=setup_a.mass_kg + 25.0)
        with patch("lapsim.ui.app.default_run_directory", return_value=tmp_path):
            app._calculate_comparison((
                ("user:car_a", "Car A", setup_a),
                ("user:car_b", "Car B", setup_b),
            ), 5.0, 0.8)
        kind, payload, error = app.result_queue.get_nowait()
        assert error is None, error
        assert kind == "comparison"
        source_a = RunRecord.load(tmp_path / f"{payload[3][0]}.json").to_dict()[
            "settings"
        ]["track"]["source_course"]
        source_b = RunRecord.load(tmp_path / f"{payload[3][1]}.json").to_dict()[
            "settings"
        ]["track"]["source_course"]
        assert source_a == source_b
        assert source_a["selected_course_id"] == app.course_spec.course_id
        assert source_a["source_kind"] == "synthetic"
    finally:
        root.destroy()


def test_imported_course_survives_restart_and_rejects_revision_reuse(
    tmp_path: Path,
) -> None:
    source_file = _bundle().save(tmp_path / "source.json")
    run_dir = tmp_path / "local" / "runs"
    with patch("lapsim.ui.app.default_run_directory", return_value=run_dir):
        first_root = tk.Tk()
        first_root.withdraw()
        try:
            first = LapSimDesktop(first_root)
            first._import_course_bundle(source_file)
            selected_id = first.course_spec.course_id
            bundle_hash = first.imported_courses[selected_id].bundle_sha256
        finally:
            first_root.destroy()

        second_root = tk.Tk()
        second_root.withdraw()
        try:
            second = LapSimDesktop(second_root)
            assert second.course_spec.course_id != selected_id
            assert selected_id in second.imported_courses
            assert second.imported_courses[selected_id].bundle_sha256 == bundle_hash
            second._select_course(next(
                option.label for option in second.course_options
                if option.course_id == selected_id
            ))
            assert second.course_spec.course_id == selected_id
            changed = _bundle().to_dict()
            changed["description"] = "Different content under the same revision"
            changed_file = CourseBundle.from_dict(changed).save(
                tmp_path / "changed-revision.json"
            )
            with pytest.raises(ValueError, match="new revision"):
                second._import_course_bundle(changed_file)
        finally:
            second_root.destroy()


def test_saved_catalog_skips_tampered_and_conflicting_files(tmp_path: Path) -> None:
    bundle = _bundle()
    bundle.save(tmp_path / f"{bundle.bundle_sha256}.json")
    (tmp_path / ("0" * 64 + ".json")).write_text("{}", encoding="utf-8")
    changed = bundle.to_dict()
    changed["description"] = "Conflicting same ID and revision"
    conflict = CourseBundle.from_dict(changed)
    conflict.save(tmp_path / f"{conflict.bundle_sha256}.json")
    catalog, warnings = load_imported_course_catalog(tmp_path)
    assert catalog[f"imported:{bundle.catalog_id}"].bundle_sha256 in {
        bundle.bundle_sha256, conflict.bundle_sha256,
    }
    assert any("conflicts" in warning for warning in warnings)

    saved = tmp_path / f"{bundle.bundle_sha256}.json"
    saved.write_text("{}", encoding="utf-8")
    catalog, warnings = load_imported_course_catalog(tmp_path)
    assert not catalog or catalog[f"imported:{bundle.catalog_id}"].bundle_sha256 == conflict.bundle_sha256
    assert any("bundle" in warning for warning in warnings)
