"""Course choice provenance and geometry, without desktop UI dependencies."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
from math import pi

import pytest

from lapsim.courses.course_bundle import CourseBundle, course_geometry_sha256
from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Track
from lapsim.ui.course_catalog import (
    COURSE_OPTIONS,
    DEFAULT_COURSE_ID,
    IMPORTED_COURSE_PREFIX,
    SYNTHETIC_DEMO_COURSE_ID,
    SYNTHETIC_FSAE_COURSE_ID,
    course_source_metadata,
    imported_course_spec,
    load_course,
    solver_cell_count_for_course,
    solver_track_for_course,
)


def test_course_options_keep_fused_source_as_explicit_default() -> None:
    assert tuple(option.course_id for option in COURSE_OPTIONS) == (
        DEFAULT_COURSE_ID, SYNTHETIC_DEMO_COURSE_ID,
        SYNTHETIC_FSAE_COURSE_ID,
    )
    assert len({option.label for option in COURSE_OPTIONS}) == len(COURSE_OPTIONS)
    source, demo, practice = COURSE_OPTIONS
    assert not source.synthetic
    assert "GNSS/IMU" in source.label
    assert "not one geometrically consistent path" in source.description
    assert "No surveyed boundaries" in source.description
    assert demo.synthetic
    assert "Synthetic" in demo.label
    assert "assumed demonstration corridor" in demo.description
    assert "not a surveyed Racing Terps boundary" in demo.description
    assert (source.default_ai_half_width_m, source.default_ai_vehicle_width_m,
            source.default_ai_margin_m) == (2.0, 1.8, 0.2)
    assert (demo.default_ai_half_width_m, demo.default_ai_vehicle_width_m,
            demo.default_ai_margin_m) == (3.0, 1.8, 0.2)
    assert practice.synthetic
    assert "Synthetic FSAE-style" in practice.label
    assert "user-editable assumption" in practice.description
    assert "No surveyed course or cone boundaries" in practice.description
    assert "or claim of rule compliance" in practice.description
    assert (practice.default_ai_half_width_m,
            practice.default_ai_vehicle_width_m,
            practice.default_ai_margin_m) == (3.0, 1.8, 0.2)
    with pytest.raises(FrozenInstanceError):
        demo.label = "Measured course"  # type: ignore[misc]


def test_default_loader_returns_shipped_fused_course() -> None:
    default = load_course()
    explicit = load_course(DEFAULT_COURSE_ID)
    assert default.closed
    assert default.cell_count == 1978
    assert default.length_m == pytest.approx(989.0)
    assert default == explicit


def test_synthetic_demo_is_closed_coherent_segment_course() -> None:
    track = load_course(SYNTHETIC_DEMO_COURSE_ID)
    assert track.closed
    assert track.length_m == pytest.approx(120.0 + 24.0 * pi)
    assert max(track.cell_length_m) <= 0.5 + 1e-12
    assert track.x_m[-1] == pytest.approx(track.x_m[0], abs=1e-9)
    assert track.y_m[-1] == pytest.approx(track.y_m[0], abs=1e-9)
    assert set(round(value, 12) for value in track.curvature_per_m) == {
        0.0, round(1.0 / 12.0, 12),
    }
    audit = track.geometry_audit()
    assert audit.curvature_integrated_closure_gap_m < 1e-7
    assert audit.maximum_arc_chord_mismatch_m < 1e-7


def test_fsae_style_practice_course_is_analytic_closed_and_bidirectional() -> None:
    track = load_course(SYNTHETIC_FSAE_COURSE_ID)
    assert track.closed
    assert track.length_m == pytest.approx(660.0 + 50.0 * pi)
    assert track.cell_count == 1640
    assert max(track.cell_length_m) <= 0.5 + 1e-12
    assert set(round(value, 12) for value in track.curvature_per_m) == {
        0.0, round(1.0 / 15.0, 12), round(-1.0 / 15.0, 12),
    }
    track.validate_coherent_arcs()
    audit = track.geometry_audit()
    assert audit.endpoint_separation_m < 1e-7
    assert audit.curvature_signed_turn_rad == pytest.approx(2.0 * pi)
    assert audit.curvature_integrated_closure_gap_m < 1e-7
    assert audit.maximum_arc_chord_mismatch_m < 1e-7


def test_unknown_course_id_is_not_silently_replaced() -> None:
    with pytest.raises(ValueError, match="Unknown course ID"):
        load_course("made-up-course")


@pytest.mark.parametrize("course_id", [
    SYNTHETIC_DEMO_COURSE_ID, SYNTHETIC_FSAE_COURSE_ID,
])
@pytest.mark.parametrize("requested_maximum_m", [0.25, 0.5, 5.0, 10.0])
def test_synthetic_solver_grid_keeps_exact_arcs(
    course_id: str, requested_maximum_m: float,
) -> None:
    source = load_course(course_id)
    solver = solver_track_for_course(
        course_id, source, requested_maximum_m,
    )
    assert max(solver.cell_length_m) <= min(requested_maximum_m, 0.5) + 1e-12
    assert solver.cell_count == solver_cell_count_for_course(
        course_id, source, requested_maximum_m,
    )
    assert solver.geometry_audit().curvature_integrated_closure_gap_m < 1e-7
    assert solver.geometry_audit().maximum_arc_chord_mismatch_m < 1e-7
    if requested_maximum_m >= 0.5:
        assert solver is source
    else:
        assert solver.cell_count > source.cell_count
        solver_by_station = {
            station: (x_m, y_m)
            for station, x_m, y_m in zip(
                solver.distance_m, solver.x_m, solver.y_m, strict=True,
            )
        }
        assert all(
            solver_by_station[station] == pytest.approx((x_m, y_m))
            for station, x_m, y_m in zip(
                source.distance_m, source.x_m, source.y_m, strict=True,
            )
        )


def test_fused_solver_grid_still_uses_recorded_curvature() -> None:
    source = load_course()
    solver = solver_track_for_course(DEFAULT_COURSE_ID, source, 1.0)
    assert solver.cell_count == 989
    assert solver.geometry_audit().curvature_signed_turn_rad == pytest.approx(
        source.geometry_audit().curvature_signed_turn_rad
    )


def test_synthetic_solver_route_rejects_mislabeled_source() -> None:
    fused = load_course(DEFAULT_COURSE_ID)
    with pytest.raises(ValueError, match="does not match the catalog"):
        solver_track_for_course(SYNTHETIC_DEMO_COURSE_ID, fused, 1.0)
    coherent_circle = SpatialTrack.from_track(
        Track.from_segments([Curve(10.0, 2.0 * pi)]),
        maximum_cell_length_m=0.5,
    )
    coherent_circle.validate_coherent_arcs()
    with pytest.raises(ValueError, match="does not match the catalog"):
        solver_track_for_course(SYNTHETIC_DEMO_COURSE_ID, coherent_circle, 0.25)
    with pytest.raises(ValueError, match="does not match the catalog"):
        solver_track_for_course(SYNTHETIC_FSAE_COURSE_ID, coherent_circle, 0.25)
    with pytest.raises(ValueError, match="does not match the catalog"):
        solver_track_for_course(DEFAULT_COURSE_ID, coherent_circle, 1.0)


@pytest.mark.parametrize("bad_step", [True, 0.0, -1.0, float("nan"), 1e-6])
def test_solver_grid_rejects_invalid_or_excessive_work(bad_step: float) -> None:
    source = load_course(SYNTHETIC_DEMO_COURSE_ID)
    with pytest.raises(ValueError):
        solver_track_for_course(SYNTHETIC_DEMO_COURSE_ID, source, bad_step)


@pytest.mark.parametrize("course_id,maximum_m,expected_cells", [
    (SYNTHETIC_DEMO_COURSE_ID, 0.0391, 5096),
    (SYNTHETIC_FSAE_COURSE_ID, 0.165, 6240),
])
def test_synthetic_source_cell_subdivision_cannot_bypass_compute_cap(
    course_id: str, maximum_m: float, expected_cells: int,
) -> None:
    source = load_course(course_id)
    assert source.length_m / maximum_m < 5000
    assert solver_cell_count_for_course(
        course_id, source, maximum_m,
    ) == expected_cells
    with pytest.raises(ValueError, match="5000-cell compute cap"):
        solver_track_for_course(course_id, source, maximum_m)


def test_imported_course_uses_coherent_arc_refinement_only() -> None:
    imported_id = f"{IMPORTED_COURSE_PREFIX}practice_loop@r1"
    source = SpatialTrack.from_track(
        Track.from_segments([Curve(10.0, 2.0 * pi)]),
        maximum_cell_length_m=1.0,
    )
    refined = solver_track_for_course(imported_id, source, 0.4)
    assert refined.cell_count == solver_cell_count_for_course(
        imported_id, source, 0.4,
    )
    assert max(refined.cell_length_m) <= 0.4 + 1e-12
    refined.validate_coherent_arcs()
    assert solver_track_for_course(imported_id, source, 2.0) is source
    with pytest.raises(ValueError, match="closed endpoint mismatch"):
        solver_track_for_course(imported_id, load_course(), 1.0)


def test_source_metadata_separates_import_bundle_and_solver_geometry() -> None:
    fused_spec, demo_spec, practice_spec = COURSE_OPTIONS
    fused = course_source_metadata(fused_spec, load_course())
    assert fused["revision"] == "legacy_unversioned"
    assert fused["bundle_sha256"] is None
    assert fused["source_artifact_sha256"]["fused_csv"]
    assert fused["source_geometry_sha256"] == course_geometry_sha256(load_course())
    demo = course_source_metadata(demo_spec, load_course(SYNTHETIC_DEMO_COURSE_ID))
    assert demo["source_kind"] == "synthetic"
    assert demo["boundary_status"] == "absent"
    practice = course_source_metadata(
        practice_spec, load_course(SYNTHETIC_FSAE_COURSE_ID),
    )
    assert practice["source_kind"] == "synthetic"
    assert practice["boundary_status"] == "absent"
    assert practice["source_generator"].endswith("_synthetic_fsae_track")
    assert "layout inspiration only" in practice["design_reference"]
    assert practice["source_geometry_sha256"] == course_geometry_sha256(
        load_course(SYNTHETIC_FSAE_COURSE_ID)
    )

    track = SpatialTrack.from_track(
        Track.from_segments([Curve(10.0, 2.0 * pi)]),
        maximum_cell_length_m=0.5,
    )
    bundle = CourseBundle.from_dict({
        "schema_version": 1,
        "course_id": "practice_loop",
        "revision": "r1",
        "label": "Practice loop",
        "description": "Analytic import example",
        "source_kind": "synthetic",
        "provenance": {
            "source_name": "Analytic circle",
            "source_sha256": None,
            "processing_method": "Exact circular arcs",
            "review_note": "No measured cone boundaries",
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
    spec = imported_course_spec(bundle)
    assert spec.course_id == f"{IMPORTED_COURSE_PREFIX}{bundle.catalog_id}"
    assert "No measured boundaries" in spec.description
    metadata = course_source_metadata(spec, bundle.track, bundle=bundle)
    assert metadata["bundle_sha256"] == bundle.bundle_sha256
    assert metadata["source_geometry_sha256"] == bundle.geometry_sha256
    assert metadata["boundary_status"] == "absent"
    with pytest.raises(ValueError, match="does not match"):
        course_source_metadata(spec, load_course(), bundle=bundle)

    v2_manifest = bundle.to_dict()
    v2_manifest["schema_version"] = 2
    v2_manifest["boundary_status"] = "source_normal_offsets_assumed"
    corridor = {
        "model": "left_right_normal_offsets_from_source_geometry",
        "reference_geometry_sha256": bundle.geometry_sha256,
        "status": "assumed",
        "left_width_m": [2.5] * bundle.track.cell_count,
        "right_width_m": [2.75] * bundle.track.cell_count,
        "provenance": {
            "source_name": "Scenario width table",
            "source_sha256": "a" * 64,
            "processing_method": "Offsets from source-cell normals",
            "review_note": "Not a surveyed boundary or swept-car clearance proof",
        },
    }
    corridor["corridor_sha256"] = sha256(
        json.dumps(corridor, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    v2_manifest["corridor"] = corridor
    v2_bundle = CourseBundle.from_dict(v2_manifest)
    v2_spec = imported_course_spec(v2_bundle)
    assert "source-relative" in v2_spec.description
    assert "uniform assumed corridor" in v2_spec.description
    v2_metadata = course_source_metadata(v2_spec, v2_bundle.track, bundle=v2_bundle)
    assert v2_metadata["metadata_version"] == 2
    assert v2_metadata["boundary_status"] == "source_normal_offsets_assumed"
    assert v2_metadata["source_cell_corridor"]["corridor_sha256"] == (
        v2_bundle.source_cell_corridor.corridor_sha256
    )
    assert v2_metadata["source_cell_corridor"]["used_by_ai_planner"] is False
