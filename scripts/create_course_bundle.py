"""Convert a coherent SpatialTrack CSV into a portable v1 CourseBundle.

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
arc geometry. This tool validates that geometry; it does not fit arcs, survey
cones, or certify that a self-declared measured source is accurate.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import os
from pathlib import Path
from typing import Sequence

# Course conversion is small and should not allocate a large BLAS worker pool.
# Set these before importing the LapSim package and its numerical dependencies.
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

from lapsim.courses.course_bundle import (
    COURSE_BUNDLE_SCHEMA_VERSION,
    MAX_BUNDLE_BYTES,
    CourseBundle,
    course_geometry_sha256,
)
from lapsim.courses.spatial_track import SpatialTrack


def _read_bounded_csv(source: Path) -> bytes:
    with source.open("rb") as stream:
        data = stream.read(MAX_BUNDLE_BYTES + 1)
    if len(data) > MAX_BUNDLE_BYTES:
        raise ValueError("source CSV exceeds the 4 MiB input cap")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("source CSV must be UTF-8") from exc
    return data


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
) -> CourseBundle:
    """Create one immutable revision from a bounded, coherent source CSV."""

    source = Path(input_csv).expanduser().resolve()
    destination = Path(output_json).expanduser().resolve()
    if source == destination:
        raise ValueError("input CSV and output bundle must be different files")
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
    bundle = CourseBundle.from_dict({
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
    })
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
            "Boundaries are absent and all AI widths are assumed scenario values. "
            "The raw input CSV SHA-256 is saved as provenance."
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
