"""Explicit desktop course choices and their data provenance.

The shipped fused endurance course remains the default. Both optional analytic
courses are synthetic calculation examples, not surveyed Racing Terps courses
or sources of measured track boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import ceil, isfinite, pi
from numbers import Real
import os
from pathlib import Path

from lapsim.courses.course_bundle import CourseBundle, course_geometry_sha256
from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Straight, Track

from .simulation import ENDURANCE_TRACK_PATH, load_team_endurance_track, resample_track


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
SYNTHETIC_FSAE_COURSE_ID = "synthetic_fsae_endurance_style_v1"
IMPORTED_COURSE_PREFIX = "imported:"
MAX_SAVED_COURSE_FILES = 64

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
    CourseSpec(
        course_id=SYNTHETIC_FSAE_COURSE_ID,
        label="Synthetic FSAE-style · practice",
        description=(
            "Analytic 817.08 m closed practice lap inspired by the 2027 "
            "Formula SAE endurance layout guidance: 60 m and 45 m straights "
            "with alternating 15 m radius turns. The starting ±3.0 m AI "
            "half-width is a user-editable assumption. No surveyed course or "
            "cone boundaries, passing zones, official event layout, or claim "
            "of rule compliance."
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


def _synthetic_fsae_track(maximum_cell_length_m: float) -> SpatialTrack:
    # Four copies each turn 90 degrees; rotational symmetry closes the lap.
    # The left/right pair forms a chicane, followed by a quarter-turn left corner.
    # This is an analytic practice shape, not a competition course survey.
    motif = (
        Straight(60.0),
        Curve(radius_m=15.0, span_rad=pi / 6.0),
        Straight(45.0),
        Curve(radius_m=15.0, span_rad=-pi / 6.0),
        Straight(60.0),
        Curve(radius_m=15.0, span_rad=pi / 2.0),
    )
    return SpatialTrack.from_track(
        Track.from_segments(motif * 4),
        maximum_cell_length_m=maximum_cell_length_m,
        close_geometry=False,
    )


def load_course(course_id: str = DEFAULT_COURSE_ID) -> SpatialTrack:
    """Load one named course without silently substituting another source."""

    if course_id == DEFAULT_COURSE_ID:
        return load_team_endurance_track()
    if course_id == SYNTHETIC_DEMO_COURSE_ID:
        return _synthetic_demo_track(0.5)
    if course_id == SYNTHETIC_FSAE_COURSE_ID:
        return _synthetic_fsae_track(0.5)
    raise ValueError(f"Unknown course ID: {course_id!r}")


def imported_course_spec(bundle: CourseBundle) -> CourseSpec:
    """Expose one validated bundle revision as an explicit desktop choice."""

    return CourseSpec(
        course_id=f"{IMPORTED_COURSE_PREFIX}{bundle.catalog_id}",
        label=(
            f"Imported · {bundle.label[:42]} · {bundle.revision[:16]} · "
            f"{bundle.bundle_sha256[:8]}"
        ),
        description=(
            f"Imported {bundle.catalog_id}: {bundle.description} "
            "The solver x/y, distance, and curvature pass a numerical arc "
            "coherence check. No measured boundaries are included; AI widths "
            "remain user-editable assumptions, not surveyed track clearance."
        ),
        synthetic=bundle.synthetic,
        default_ai_half_width_m=bundle.default_ai_half_width_m,
        default_ai_vehicle_width_m=bundle.default_ai_vehicle_width_m,
        default_ai_margin_m=bundle.default_ai_margin_m,
    )


def load_imported_course_catalog(
    directory: Path,
) -> tuple[dict[str, CourseBundle], tuple[str, ...]]:
    """Reload bounded local course copies, rejecting bad or conflicting files."""

    if not directory.exists():
        return {}, ()
    try:
        with os.scandir(directory) as entries:
            paths = []
            for entry in entries:
                if not entry.name.lower().endswith(".json"):
                    continue
                paths.append(Path(entry.path))
                if len(paths) > MAX_SAVED_COURSE_FILES:
                    return {}, (
                        f"Saved course catalog exceeds {MAX_SAVED_COURSE_FILES} JSON files; "
                        "remove unused files before reopening it.",
                    )
    except OSError as error:
        return {}, (f"Saved course catalog could not be read: {error}",)
    bundles: dict[str, CourseBundle] = {}
    warnings: list[str] = []
    for path in sorted(paths):
        try:
            if path.is_symlink():
                raise ValueError("symbolic links are not supported")
            bundle = CourseBundle.load(path)
            if path.name != f"{bundle.bundle_sha256}.json":
                raise ValueError("filename does not match validated bundle hash")
            course_id = f"{IMPORTED_COURSE_PREFIX}{bundle.catalog_id}"
            existing = bundles.get(course_id)
            if existing is not None and existing.bundle_sha256 != bundle.bundle_sha256:
                raise ValueError("course ID/revision conflicts with another saved bundle")
            bundles[course_id] = bundle
        except (OSError, ValueError, TypeError) as error:
            warnings.append(f"{path.name}: {error}")
    return bundles, tuple(warnings)


def course_source_metadata(
    spec: CourseSpec, source_track: SpatialTrack, *,
    bundle: CourseBundle | None = None,
) -> dict[str, object]:
    """Freeze source identity separately from the eventual solver-grid hash."""

    geometry_hash = course_geometry_sha256(source_track)
    common: dict[str, object] = {
        "metadata_version": 1,
        "selected_course_id": spec.course_id,
        "source_geometry_sha256": geometry_hash,
        "source_geometry_hash_scope": (
            "canonical loaded closed/distance_m/x_m/y_m/curvature_per_m"
        ),
        "boundary_status": "absent",
    }
    if bundle is not None:
        if (
            spec.course_id != f"{IMPORTED_COURSE_PREFIX}{bundle.catalog_id}"
            or source_track != bundle.track
            or geometry_hash != bundle.geometry_sha256
        ):
            raise ValueError("Imported course does not match its validated bundle")
        manifest = bundle.to_dict()
        common.update({
            "source_kind": bundle.source_kind,
            "revision": bundle.revision,
            "bundle_id": bundle.catalog_id,
            "bundle_sha256": bundle.bundle_sha256,
            "bundle_hash_scope": "canonical validated v1 course-bundle manifest",
            "loaded_bundle_file_sha256": bundle.source_file_sha256,
            "declared_source_sha256": manifest["provenance"]["source_sha256"],
            "coordinate_frame": manifest["coordinate_frame"],
            "travel_direction": bundle.travel_direction,
        })
        return common
    if spec.course_id == DEFAULT_COURSE_ID:
        if source_track != load_team_endurance_track():
            raise ValueError("Fused course source does not match the catalog")
        sidecar = ENDURANCE_TRACK_PATH.with_suffix(".json")
        common.update({
            "source_kind": "recorded_fusion_unverified",
            "revision": "legacy_unversioned",
            "bundle_id": None,
            "bundle_sha256": None,
            "bundle_hash_scope": None,
            "source_artifact_sha256": {
                "fused_csv": sha256(ENDURANCE_TRACK_PATH.read_bytes()).hexdigest(),
                "fusion_metadata_json": sha256(sidecar.read_bytes()).hexdigest(),
            },
            "coordinate_frame": "legacy_map_registered_xy_unknown_origin",
        })
        return common
    if spec.course_id == SYNTHETIC_DEMO_COURSE_ID:
        if source_track != _synthetic_demo_track(0.5):
            raise ValueError("Synthetic course source does not match the catalog")
        common.update({
            "source_kind": "synthetic",
            "revision": "generator_v1",
            "bundle_id": None,
            "bundle_sha256": None,
            "bundle_hash_scope": None,
            "source_generator": "lapsim.ui.course_catalog._synthetic_demo_track",
            "coordinate_frame": "analytic_local_cartesian_xy_m",
        })
        return common
    if spec.course_id == SYNTHETIC_FSAE_COURSE_ID:
        if source_track != _synthetic_fsae_track(0.5):
            raise ValueError("Synthetic course source does not match the catalog")
        common.update({
            "source_kind": "synthetic",
            "revision": "generator_v1",
            "bundle_id": None,
            "bundle_sha256": None,
            "bundle_hash_scope": None,
            "source_generator": "lapsim.ui.course_catalog._synthetic_fsae_track",
            "coordinate_frame": "analytic_local_cartesian_xy_m",
            "design_reference": (
                "2027 Formula SAE Rules v1.0, D.12.2.2; layout inspiration only"
            ),
            "design_reference_url": (
                "https://www.fsaeonline.com/cdsweb/gen/DownloadDocument.aspx?"
                "DocumentID=da79bcb4-0935-4f7b-83d7-0dbb8ce68d38"
            ),
        })
        return common
    raise ValueError(f"Unknown course ID: {spec.course_id!r}")


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
    if course_id in (SYNTHETIC_DEMO_COURSE_ID, SYNTHETIC_FSAE_COURSE_ID):
        if source_track != load_course(course_id):
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
    if course_id.startswith(IMPORTED_COURSE_PREFIX) and len(course_id) > len(IMPORTED_COURSE_PREFIX):
        source_track.validate_coherent_arcs()
        # As with the synthetic course, preserve the imported source's exact
        # arc boundaries instead of averaging adjacent curvatures.
        return sum(
            ceil(length_m / maximum_cell_length_m)
            for length_m in source_track.cell_length_m
        )
    raise ValueError(f"Unknown course ID: {course_id!r}")


def solver_track_for_course(
    course_id: str, source_track: SpatialTrack, maximum_cell_length_m: float,
) -> SpatialTrack:
    """Retain exact coherent arcs; resample only the fused recorded course.

    A user step is a maximum, so a coherent source may stay finer.
    A finer requested step subdivides the verified analytic source arcs,
    preserving their stations and curvature instead of averaging across them.
    """

    if solver_cell_count_for_course(
        course_id, source_track, maximum_cell_length_m,
    ) > 5000:
        raise ValueError("requested solver grid exceeds the 5000-cell compute cap")
    if course_id in (SYNTHETIC_DEMO_COURSE_ID, SYNTHETIC_FSAE_COURSE_ID):
        source_track.validate_coherent_arcs()
        if maximum_cell_length_m >= max(source_track.cell_length_m) - 1e-10:
            return source_track
        return source_track.refine_arcs(maximum_cell_length_m)
    if course_id == DEFAULT_COURSE_ID:
        return resample_track(source_track, maximum_cell_length_m)
    if course_id.startswith(IMPORTED_COURSE_PREFIX) and len(course_id) > len(IMPORTED_COURSE_PREFIX):
        source_track.validate_coherent_arcs()
        if maximum_cell_length_m >= max(source_track.cell_length_m) - 1e-10:
            return source_track
        return source_track.refine_arcs(maximum_cell_length_m)
    raise ValueError(f"Unknown course ID: {course_id!r}")


__all__ = [
    "CourseSpec", "COURSE_OPTIONS", "DEFAULT_COURSE_ID", "IMPORTED_COURSE_PREFIX",
    "MAX_SAVED_COURSE_FILES", "load_imported_course_catalog",
    "SYNTHETIC_DEMO_COURSE_ID", "SYNTHETIC_FSAE_COURSE_ID",
    "load_course", "imported_course_spec",
    "course_source_metadata",
    "solver_cell_count_for_course",
    "solver_track_for_course",
]
