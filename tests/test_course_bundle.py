"""Versioned course import contracts and numerical geometry gates."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from math import pi
from pathlib import Path

import pytest

from lapsim.courses.course_bundle import (
    COURSE_BUNDLE_SCHEMA_VERSION,
    MAX_BUNDLE_BYTES,
    CourseBundle,
    course_geometry_sha256,
)
from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Track


def _manifest(*, measured: bool = False) -> dict:
    track = SpatialTrack.from_track(
        Track.from_segments([Curve(radius_m=10.0, span_rad=2.0 * pi)]),
        maximum_cell_length_m=0.5,
    )
    return {
        "schema_version": COURSE_BUNDLE_SCHEMA_VERSION,
        "course_id": "team_test_loop",
        "revision": "r1",
        "label": "Test loop r1",
        "description": "A versioned local calculation course.",
        "source_kind": "measured" if measured else "synthetic",
        "provenance": {
            "source_name": "Synthetic circle generator" if not measured else "Survey export",
            "source_sha256": "0" * 64 if measured else None,
            "processing_method": "Exact circular arc discretization",
            "review_note": "Numerical geometry check only; no car validation.",
        },
        "coordinate_frame": {
            "type": "local_cartesian_right_handed_xy",
            "units": "m",
            "origin": "Start/finish survey origin",
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
            "closed": track.closed,
            "distance_m": list(track.distance_m),
            "x_m": list(track.x_m),
            "y_m": list(track.y_m),
            "curvature_per_m": list(track.curvature_per_m),
        },
        "geometry_sha256": course_geometry_sha256(track),
    }


def _refresh_geometry_hash(payload: dict) -> None:
    geometry = payload["geometry"]
    track = SpatialTrack(
        distance_m=tuple(geometry["distance_m"]),
        x_m=tuple(geometry["x_m"]),
        y_m=tuple(geometry["y_m"]),
        curvature_per_m=tuple(geometry["curvature_per_m"]),
        closed=geometry["closed"],
    )
    payload["geometry_sha256"] = course_geometry_sha256(track)


def test_course_bundle_roundtrip_hash_and_exact_arc_refinement(tmp_path: Path) -> None:
    bundle = CourseBundle.from_dict(_manifest())
    assert bundle.catalog_id == "team_test_loop@r1"
    assert bundle.synthetic
    assert bundle.boundary_status == "absent"
    assert bundle.source_file_sha256 is None
    assert bundle.bundle_sha256 == sha256(
        json.dumps(bundle.to_dict(), sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
    ).hexdigest()
    assert bundle.geometry_sha256 == course_geometry_sha256(bundle.track)
    assert bundle.solver_track(1.0) is bundle.track
    assert bundle.solver_cell_count(0.25) > bundle.track.cell_count
    refined = bundle.solver_track(0.25)
    assert refined.cell_count == bundle.solver_cell_count(0.25)
    assert max(refined.cell_length_m) <= 0.25 + 1e-12
    refined.validate_coherent_arcs()

    detached = bundle.to_dict()
    detached["geometry"]["x_m"][0] = 12345.0
    assert bundle.track.x_m[0] == 0.0
    path = bundle.save(tmp_path / "imported.json")
    loaded = CourseBundle.load(path)
    assert loaded.track == bundle.track
    assert loaded.bundle_sha256 == bundle.bundle_sha256
    assert loaded.source_file_sha256 == sha256(path.read_bytes()).hexdigest()


def test_formatting_changes_only_raw_file_hash(tmp_path: Path) -> None:
    manifest = _manifest()
    compact = tmp_path / "compact.json"
    pretty = tmp_path / "pretty.json"
    compact.write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")
    pretty.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    one, two = CourseBundle.load(compact), CourseBundle.load(pretty)
    assert one.bundle_sha256 == two.bundle_sha256
    assert one.source_file_sha256 != two.source_file_sha256


def test_measured_bundle_requires_source_digest_but_is_not_a_validation_claim() -> None:
    manifest = _manifest(measured=True)
    bundle = CourseBundle.from_dict(manifest)
    assert bundle.source_kind == "measured"
    assert not bundle.synthetic
    assert bundle.to_dict()["provenance"]["source_sha256"] == "0" * 64
    manifest["provenance"]["source_sha256"] = None
    with pytest.raises(ValueError, match="source SHA-256"):
        CourseBundle.from_dict(manifest)


def test_rejects_mismatched_hash_and_incoherent_arc_geometry() -> None:
    manifest = _manifest()
    manifest["geometry"]["x_m"][5] += 0.01
    with pytest.raises(ValueError, match="SHA-256"):
        CourseBundle.from_dict(manifest)
    _refresh_geometry_hash(manifest)
    with pytest.raises(ValueError, match="not coherent"):
        CourseBundle.from_dict(manifest)
    manifest = _manifest()
    manifest["geometry_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256"):
        CourseBundle.from_dict(manifest)


@pytest.mark.parametrize("mutation,expected", [
    (lambda m: m.update({"geometry_csv": "C:/external/track.csv"}), "exactly"),
    (lambda m: m["geometry"].update({"left_boundary_m": [1.0]}), "exactly"),
    (lambda m: m.update({"boundary_status": "surveyed"}), "boundary_status"),
    (lambda m: m["ai_defaults"].update({"width_source": "measured"}), "assumed_uniform"),
    (lambda m: m["coordinate_frame"].update({"units": "feet"}), "meters"),
    (lambda m: m.update({"travel_direction": "clockwise"}), "travel_direction disagrees"),
    (lambda m: m.update({"course_id": "../external"}), "path-free"),
    (lambda m: m["ai_defaults"].update({"half_width_m": 1.0}), "usable assumed corridor"),
    (lambda m: m["ai_defaults"].update({"vehicle_width_m": True}), "finite number"),
    (lambda m: m["coordinate_frame"].update({"y_axis": "east"}), "axes must be distinct"),
    (lambda m: m.update({"schema_version": 2}), "unsupported"),
])
def test_strict_schema_rejects_unsupported_claims(mutation, expected: str) -> None:
    manifest = _manifest()
    mutation(manifest)
    with pytest.raises(ValueError, match=expected):
        CourseBundle.from_dict(manifest)


def test_rejects_duplicate_json_keys_nonfinite_and_oversized_files(tmp_path: Path) -> None:
    source = tmp_path / "bad.json"
    source.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        CourseBundle.load(source)
    source.write_text('{"x":NaN}', encoding="utf-8")
    with pytest.raises(ValueError, match="nonfinite"):
        CourseBundle.load(source)
    source.write_bytes(b" " * (MAX_BUNDLE_BYTES + 1))
    with pytest.raises(ValueError, match="4 MiB"):
        CourseBundle.load(source)
    source.write_text("[" * 2000 + "0" + "]" * 2000, encoding="utf-8")
    with pytest.raises(ValueError, match="JSON nesting exceeds"):
        CourseBundle.load(source)


def test_oversized_json_integer_is_a_course_validation_error(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["ai_defaults"]["half_width_m"] = 10**400
    with pytest.raises(ValueError, match="ai_defaults.half_width_m must be a finite number"):
        CourseBundle.from_dict(manifest)

    source = tmp_path / "huge_integer.json"
    source.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="ai_defaults.half_width_m must be a finite number"):
        CourseBundle.load(source)


def test_refinement_respects_desktop_compute_cap() -> None:
    bundle = CourseBundle.from_dict(_manifest())
    assert bundle.solver_cell_count(0.02) > bundle.track.cell_count
    with pytest.raises(ValueError, match="5000-cell"):
        bundle.solver_track(0.005)
    with pytest.raises(ValueError, match="5000-cell"):
        bundle.solver_cell_count(1e-320)
    for bad_step in (True, 0.0, -1.0, float("nan")):
        with pytest.raises(ValueError):
            bundle.solver_cell_count(bad_step)


def test_source_geometry_and_metadata_cannot_mutate_loaded_bundle() -> None:
    manifest = _manifest()
    original = deepcopy(manifest)
    bundle = CourseBundle.from_dict(manifest)
    manifest["geometry"]["x_m"][0] = 100.0
    manifest["description"] = "changed"
    assert bundle.to_dict() == original
