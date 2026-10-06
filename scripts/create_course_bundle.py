"""Convert a coherent SpatialTrack CSV into a portable CourseBundle.

Run from an installed LapSim environment, for example::

    python scripts/create_course_bundle.py course.csv course_r1.json \
      --course-id terps_endurance --revision r1 --label "Terps endurance r1" \
      --description "Reviewed course model" --source-kind measured \
      --source-name "Survey export 2027-03-15" \
      --processing-method "Documented coherent-arc fit" \
      --review-note "Geometry reviewed; car model not validated" \
      --frame-origin "start/finish survey marker" \
      --frame-x-axis east --frame-y-axis north \
      --travel-direction counterclockwise

The source CSV must already contain model-ready, closed piecewise circular
arc geometry. An optional source-cell corridor CSV produces a v2 bundle.
This tool validates alignment; it does not fit arcs, survey cones, or certify
that a self-declared measured source or corridor is accurate.
"""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import io
import json
from math import isfinite
import os
from pathlib import Path
from typing import Sequence

# Course conversion is small and should not allocate a large BLAS worker pool.
# Set these before importing the LapSim package and its numerical dependencies.
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

from lapsim.courses.course_bundle import (
    COURSE_BUNDLE_CORRIDOR_SCHEMA_VERSION,
    COURSE_BUNDLE_SCHEMA_VERSION,
    MAX_BUNDLE_BYTES,
    CourseBundle,
    course_geometry_sha256,
)
from lapsim.courses.spatial_track import SpatialTrack


_CORRIDOR_COLUMNS = ("distance_m", "left_width_m", "right_width_m")
_CORRIDOR_STATION_TOLERANCE_M = 1e-9


def _read_bounded_csv(source: Path, *, label: str = "source CSV") -> bytes:
    with source.open("rb") as stream:
        data = stream.read(MAX_BUNDLE_BYTES + 1)
    if len(data) > MAX_BUNDLE_BYTES:
        raise ValueError(f"{label} exceeds the 4 MiB input cap")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be UTF-8") from exc
    return data


def _source_cell_corridor(
    source: Path, source_stations_m: tuple[float, ...],
) -> tuple[list[float], list[float], str]:
    """Read exact CSV bytes and align one width row to each source cell."""

    raw_csv = _read_bounded_csv(source, label="corridor CSV")
    raw_digest = sha256(raw_csv).hexdigest()
    left_width_m: list[float] = []
    right_width_m: list[float] = []
    seen_stations: set[float] = set()
    previous_station_m: float | None = None
    try:
        rows = csv.reader(io.StringIO(raw_csv.decode("utf-8"), newline=""), strict=True)
        if tuple(next(rows, ())) != _CORRIDOR_COLUMNS:
            raise ValueError(
                "corridor CSV header must be exactly distance_m,left_width_m,right_width_m"
            )
        for index, row in enumerate(rows):
            if index >= len(source_stations_m):
                raise ValueError("corridor CSV must have exactly one row per source cell")
            if len(row) != 3:
                raise ValueError(f"corridor CSV row {index + 2} must have exactly three fields")
            try:
                station_m, left_m, right_m = (float(value) for value in row)
            except ValueError as exc:
                raise ValueError(
                    f"corridor CSV row {index + 2} has a missing or malformed number"
                ) from exc
            if not all(isfinite(value) for value in (station_m, left_m, right_m)):
                raise ValueError(f"corridor CSV row {index + 2} must contain finite numbers")
            if station_m in seen_stations:
                raise ValueError(f"corridor CSV row {index + 2} duplicates a station")
            seen_stations.add(station_m)
            if previous_station_m is not None and station_m <= previous_station_m:
                raise ValueError(f"corridor CSV row {index + 2} stations must increase")
            previous_station_m = station_m
            if abs(station_m - source_stations_m[index]) > _CORRIDOR_STATION_TOLERANCE_M:
                raise ValueError(
                    f"corridor CSV row {index + 2} station does not match source cell "
                    f"{index} within {_CORRIDOR_STATION_TOLERANCE_M:g} m"
                )
            if left_m <= 0.0 or right_m <= 0.0:
                raise ValueError(f"corridor CSV row {index + 2} widths must be positive")
            left_width_m.append(left_m)
            right_width_m.append(right_m)
    except csv.Error as exc:
        raise ValueError("corridor CSV is malformed") from exc
    if len(left_width_m) != len(source_stations_m):
        raise ValueError("corridor CSV must have exactly one row per source cell")
    if sha256(_read_bounded_csv(source, label="corridor CSV")).hexdigest() != raw_digest:
        raise ValueError("corridor CSV changed during conversion")
    return left_width_m, right_width_m, raw_digest


def create_course_bundle(
    input_csv: str | Path,
    output_json: str | Path,
    *,
    course_id: str,
    revision: str,
    label: str,
    description: str,
    source_kind: str,
    source_name: str,
    processing_method: str,
    review_note: str,
    frame_origin: str,
    frame_x_axis: str,
    frame_y_axis: str,
    travel_direction: str,
    ai_half_width_m: float = 2.0,
    ai_vehicle_width_m: float = 1.8,
    ai_safety_margin_m: float = 0.2,
    corridor_csv: str | Path | None = None,
    corridor_status: str | None = None,
    corridor_source_name: str | None = None,
    corridor_processing_method: str | None = None,
    corridor_review_note: str | None = None,
) -> CourseBundle:
    """Create one immutable revision from a bounded, coherent source CSV."""

    source = Path(input_csv).expanduser().resolve()
    destination = Path(output_json).expanduser().resolve()
    corridor_fields = (
        corridor_status, corridor_source_name, corridor_processing_method,
        corridor_review_note,
    )
    if corridor_csv is None and any(value is not None for value in corridor_fields):
        raise ValueError("corridor metadata requires --corridor-csv")
    if corridor_csv is not None and any(value is None for value in corridor_fields):
        raise ValueError(
            "--corridor-csv requires status, source name, processing method, and review note"
        )
    corridor_source = Path(corridor_csv).expanduser().resolve() if corridor_csv is not None else None
    if source == destination:
        raise ValueError("input CSV and output bundle must be different files")
    if corridor_source == destination:
        raise ValueError("corridor CSV and output bundle must be different files")
    if destination.exists():
        raise ValueError(f"output bundle already exists: {destination}")
    raw_csv = _read_bounded_csv(source)
    raw_digest = sha256(raw_csv).hexdigest()
    try:
        track = SpatialTrack.from_csv(source, closed=True)
    except (TypeError, AttributeError) as exc:
        raise ValueError("source CSV contains missing or malformed track fields") from exc
    # A changed input could otherwise yield a digest from different geometry.
    if sha256(_read_bounded_csv(source)).hexdigest() != raw_digest:
        raise ValueError("source CSV changed during conversion")
    geometry = {
        "model": "piecewise_constant_curvature_arcs",
        "closed": track.closed,
        "distance_m": list(track.distance_m),
        "x_m": list(track.x_m),
        "y_m": list(track.y_m),
        "curvature_per_m": list(track.curvature_per_m),
    }
    manifest = {
        "schema_version": COURSE_BUNDLE_SCHEMA_VERSION,
        "course_id": course_id,
        "revision": revision,
        "label": label,
        "description": description,
        "source_kind": source_kind,
        "provenance": {
            "source_name": source_name,
            "source_sha256": raw_digest,
            "processing_method": processing_method,
            "review_note": review_note,
        },
        "coordinate_frame": {
            "type": "local_cartesian_right_handed_xy",
            "units": "m",
            "origin": frame_origin,
            "x_axis": frame_x_axis,
            "y_axis": frame_y_axis,
        },
        "travel_direction": travel_direction,
        "boundary_status": "absent",
        "ai_defaults": {
            "width_source": "assumed_uniform",
            "half_width_m": ai_half_width_m,
            "vehicle_width_m": ai_vehicle_width_m,
            "safety_margin_m": ai_safety_margin_m,
        },
        "geometry": geometry,
        "geometry_sha256": course_geometry_sha256(track),
    }
    if corridor_source is None:
        bundle = CourseBundle.from_dict(manifest)
    else:
        # Validate the source geometry before accepting station-relative widths.
        base = CourseBundle.from_dict(manifest)
        left_width_m, right_width_m, corridor_digest = _source_cell_corridor(
            corridor_source, base.track.distance_m[:-1],
        )
        corridor = {
            "model": "left_right_normal_offsets_from_source_geometry",
            "reference_geometry_sha256": base.geometry_sha256,
            "status": corridor_status,
            "left_width_m": left_width_m,
            "right_width_m": right_width_m,
            "provenance": {
                "source_name": corridor_source_name,
                "source_sha256": corridor_digest,
                "processing_method": corridor_processing_method,
                "review_note": corridor_review_note,
            },
        }
        corridor["corridor_sha256"] = sha256(
            json.dumps(corridor, sort_keys=True, separators=(",", ":"), allow_nan=False)
            .encode("utf-8")
        ).hexdigest()
        manifest["schema_version"] = COURSE_BUNDLE_CORRIDOR_SCHEMA_VERSION
        manifest["boundary_status"] = f"source_normal_offsets_{corridor_status}"
        manifest["corridor"] = corridor
        bundle = CourseBundle.from_dict(manifest)
    bundle.save(destination)
    saved = CourseBundle.load(destination)
    if saved.bundle_sha256 != bundle.bundle_sha256:
        raise RuntimeError("saved course bundle failed the content-hash round trip")
    return saved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a closed, coherent SpatialTrack CSV into a versioned "
            "LapSim CourseBundle JSON. The CSV must already contain exact "
            "constant-curvature solver arcs; this command does not derive "
            "curvature from raw survey points."
        ),
        epilog=(
            "V1 uses right-handed local Cartesian x/y coordinates in meters. "
            "Travel direction is checked against the path's signed 2*pi turn. "
            "With --corridor-csv, v2 adds source-relative cell widths; AI still "
            "uses uniform assumed scenario widths. Exact source CSV byte "
            "SHA-256 values are saved as provenance."
        ),
    )
    parser.add_argument("input_csv", type=Path, help="UTF-8 SpatialTrack CSV with distance_m, x_m, y_m and per-cell curvature_per_m")
    parser.add_argument("output_json", type=Path, help="new versioned JSON file; existing files are never replaced")
    parser.add_argument("--course-id", required=True, help="stable lowercase ID, such as terps_endurance")
    parser.add_argument("--revision", required=True, help="immutable revision ID, such as r1 or 2027-03-15-r1")
    parser.add_argument("--label", required=True, help="short course name shown in the desktop menu")
    parser.add_argument("--description", required=True, help="plain-language course scope and limitations")
    parser.add_argument("--source-kind", choices=("synthetic", "measured"), required=True, help="declared source type; measured is a provenance claim, not independent survey validation")
    parser.add_argument("--source-name", required=True, help="name/revision of the raw source data, not a file path reference")
    parser.add_argument("--processing-method", required=True, help="how model-ready constant-curvature arcs were produced")
    parser.add_argument("--review-note", required=True, help="review status and remaining uncertainty")
    parser.add_argument("--frame-origin", required=True, help="physical or synthetic local x/y origin")
    parser.add_argument("--frame-x-axis", required=True, help="positive x-axis direction in a right-handed meter frame")
    parser.add_argument("--frame-y-axis", required=True, help="positive y-axis direction in a right-handed meter frame")
    parser.add_argument("--travel-direction", choices=("clockwise", "counterclockwise"), required=True, help="direction around the single closed lap in this x/y frame")
    parser.add_argument("--ai-half-width-m", type=float, default=2.0, help="assumed uniform half-width in meters (default: 2.0); not surveyed clearance")
    parser.add_argument("--ai-vehicle-width-m", type=float, default=1.8, help="assumed vehicle width in meters (default: 1.8)")
    parser.add_argument("--ai-safety-margin-m", type=float, default=0.2, help="assumed side margin in meters (default: 0.2)")
    parser.add_argument("--corridor-csv", type=Path, help="opt in to v2 with one UTF-8 width row per source cell, excluding the closure row")
    parser.add_argument("--corridor-status", choices=("assumed", "measured"), help="declared source-relative width status; measured requires --source-kind measured")
    parser.add_argument("--corridor-source-name", help="name/revision of the width source data")
    parser.add_argument("--corridor-processing-method", help="how widths were measured or assumed at source cell starts")
    parser.add_argument("--corridor-review-note", help="width review status and remaining uncertainty")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        bundle = create_course_bundle(
            args.input_csv, args.output_json,
            course_id=args.course_id,
            revision=args.revision,
            label=args.label,
            description=args.description,
            source_kind=args.source_kind,
            source_name=args.source_name,
            processing_method=args.processing_method,
            review_note=args.review_note,
            frame_origin=args.frame_origin,
            frame_x_axis=args.frame_x_axis,
            frame_y_axis=args.frame_y_axis,
            travel_direction=args.travel_direction,
            ai_half_width_m=args.ai_half_width_m,
            ai_vehicle_width_m=args.ai_vehicle_width_m,
            ai_safety_margin_m=args.ai_safety_margin_m,
            corridor_csv=args.corridor_csv,
            corridor_status=args.corridor_status,
            corridor_source_name=args.corridor_source_name,
            corridor_processing_method=args.corridor_processing_method,
            corridor_review_note=args.corridor_review_note,
        )
    except (OSError, TypeError, ValueError) as exc:
        parser.exit(2, f"course bundle not created: {exc}\n")
    print(
        f"Saved {bundle.catalog_id}: {bundle.track.cell_count} cells, "
        f"bundle SHA-256 {bundle.bundle_sha256}, "
        f"source CSV SHA-256 {bundle.to_dict()['provenance']['source_sha256']}\n"
        f"{Path(args.output_json).expanduser().resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
