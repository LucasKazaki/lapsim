"""Explicit desktop course choices and their data provenance.

The shipped fused endurance course remains the default. The optional rounded
rectangle is a synthetic calculation example, not a surveyed Racing Terps
course or a source of measured track boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite, pi
from numbers import Real

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Straight, Track

from .simulation import load_team_endurance_track, resample_track


@dataclass(frozen=True, slots=True)
class CourseSpec:
    """Immutable display metadata and starting AI corridor assumptions."""

    course_id: str
    label: str
    description: str
    synthetic: bool
    default_ai_half_width_m: float
    default_ai_vehicle_width_m: float
    default_ai_margin_m: float


DEFAULT_COURSE_ID = "team_endurance_fused_gnss_imu"
SYNTHETIC_DEMO_COURSE_ID = "synthetic_rounded_rectangle_v1"

COURSE_OPTIONS: tuple[CourseSpec, ...] = (
    CourseSpec(
        course_id=DEFAULT_COURSE_ID,
        label="Fused GNSS/IMU · default",
        description=(
            "Shipped 989 m distance-indexed endurance data. Its fused x/y map "
            "and curvature are not one geometrically consistent path. No "
            "surveyed boundaries are included; the ±2.0 m AI half-width is "
            "only a user-editable scenario assumption."
        ),
        synthetic=False,
        default_ai_half_width_m=2.0,
        default_ai_vehicle_width_m=1.8,
        default_ai_margin_m=0.2,
    ),
    CourseSpec(
        course_id=SYNTHETIC_DEMO_COURSE_ID,
        label="Synthetic loop · AI demo",
        description=(
            "Synthetic closed calculation course: two 40 m and two 20 m "
            "straights joined by four 12 m radius quarter-circle arcs. "
            "The starting ±3.0 m AI half-width is a user-editable assumed "
            "demonstration corridor, not a surveyed Racing Terps boundary or "
            "Formula SAE event map."
        ),
        synthetic=True,
        default_ai_half_width_m=3.0,
        default_ai_vehicle_width_m=1.8,
        default_ai_margin_m=0.2,
    ),
)


def _synthetic_demo_track(maximum_cell_length_m: float) -> SpatialTrack:
    segments = []
    for straight_length_m in (40.0, 20.0, 40.0, 20.0):
        segments.extend((
            Straight(straight_length_m),
            Curve(radius_m=12.0, span_rad=pi / 2.0),
        ))
    return SpatialTrack.from_track(
        Track.from_segments(segments),
        maximum_cell_length_m=maximum_cell_length_m,
    )


def load_course(course_id: str = DEFAULT_COURSE_ID) -> SpatialTrack:
    """Load one named course without silently substituting another source."""

    if course_id == DEFAULT_COURSE_ID:
        return load_team_endurance_track()
    if course_id == SYNTHETIC_DEMO_COURSE_ID:
        return _synthetic_demo_track(0.5)
    raise ValueError(f"Unknown course ID: {course_id!r}")


def solver_cell_count_for_course(
    course_id: str, source_track: SpatialTrack, maximum_cell_length_m: float,
) -> int:
    """Count the cells a requested maximum step would actually produce."""

    if (
        isinstance(maximum_cell_length_m, bool)
        or not isinstance(maximum_cell_length_m, Real)
        or not isfinite(maximum_cell_length_m)
        or maximum_cell_length_m <= 0.0
    ):
        raise ValueError("maximum_cell_length_m must be finite and positive")
    if source_track.length_m / maximum_cell_length_m > 5000:
        raise ValueError("requested solver grid exceeds the 5000-cell compute cap")
    if course_id == SYNTHETIC_DEMO_COURSE_ID:
        if source_track != _synthetic_demo_track(0.5):
            raise ValueError("Synthetic course source does not match the catalog")
        if maximum_cell_length_m >= max(source_track.cell_length_m) - 1e-10:
            return source_track.cell_count
        # Refinement keeps the source's analytic straight/arc boundaries.
        # Count their subdivisions, rather than rebuilding larger segments
        # with a different rounding of their cell boundaries.
        return sum(
            ceil(length_m / maximum_cell_length_m)
            for length_m in source_track.cell_length_m
        )
    if course_id == DEFAULT_COURSE_ID:
        if source_track != load_team_endurance_track():
            raise ValueError("Fused course source does not match the catalog")
        return ceil(source_track.length_m / maximum_cell_length_m)
    raise ValueError(f"Unknown course ID: {course_id!r}")


def solver_track_for_course(
    course_id: str, source_track: SpatialTrack, maximum_cell_length_m: float,
) -> SpatialTrack:
    """Retain exact synthetic arcs; resample only the fused recorded course.

    A user step is a maximum, so the 0.5 m synthetic source may stay finer.
    A finer requested step subdivides the verified analytic source arcs,
    preserving their stations and curvature instead of averaging across them.
    """

    if solver_cell_count_for_course(
        course_id, source_track, maximum_cell_length_m,
    ) > 5000:
        raise ValueError("requested solver grid exceeds the 5000-cell compute cap")
    if course_id == SYNTHETIC_DEMO_COURSE_ID:
        source_track.validate_coherent_arcs()
        if maximum_cell_length_m >= max(source_track.cell_length_m) - 1e-10:
            return source_track
        return source_track.refine_arcs(maximum_cell_length_m)
    if course_id == DEFAULT_COURSE_ID:
        return resample_track(source_track, maximum_cell_length_m)
    raise ValueError(f"Unknown course ID: {course_id!r}")


__all__ = [
    "CourseSpec", "COURSE_OPTIONS", "DEFAULT_COURSE_ID",
    "SYNTHETIC_DEMO_COURSE_ID", "load_course", "solver_cell_count_for_course",
    "solver_track_for_course",
]
