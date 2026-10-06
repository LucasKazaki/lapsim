"""Portable, versioned course geometry for the desktop lap model.

Version 1 accepts only a closed, coherent constant-curvature-arc solver path.
Its AI width is explicitly a scenario assumption. Version 2 can additionally
store source-cell left/right normal-coordinate widths tied to that validated
source geometry. Those widths are not world-frame boundaries or a swept-car
clearance certificate, and cannot be passed to a planner that changes the
reference path without a checked frame transformation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from hashlib import sha256
import json
from math import ceil, fsum, isfinite, pi
from numbers import Real
import os
from pathlib import Path
import re
from typing import Any, Mapping
from uuid import uuid4

from .spatial_track import SpatialTrack


COURSE_BUNDLE_SCHEMA_VERSION = 1
COURSE_BUNDLE_CORRIDOR_SCHEMA_VERSION = 2
MAX_BUNDLE_BYTES = 4 * 1024 * 1024
MAX_BUNDLE_CELLS = 5000
_ID_PATTERN = re.compile(r"[a-z][a-z0-9_-]{2,63}\Z")
_REVISION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_TOP_KEYS = frozenset((
    "schema_version", "course_id", "revision", "label", "description",
    "source_kind", "provenance", "coordinate_frame", "travel_direction",
    "boundary_status", "ai_defaults", "geometry", "geometry_sha256",
))
_TOP_KEYS_V2 = _TOP_KEYS | frozenset(("corridor",))
_GEOMETRY_KEYS = frozenset((
    "model", "closed", "distance_m", "x_m", "y_m", "curvature_per_m",
))
_FRAME_KEYS = frozenset(("type", "units", "origin", "x_axis", "y_axis"))
_PROVENANCE_KEYS = frozenset((
    "source_name", "source_sha256", "processing_method", "review_note",
))
_AI_KEYS = frozenset((
    "width_source", "half_width_m", "vehicle_width_m", "safety_margin_m",
))
_CORRIDOR_KEYS = frozenset((
    "model", "reference_geometry_sha256", "status", "left_width_m",
    "right_width_m", "provenance", "corridor_sha256",
))
_CORRIDOR_MODEL = "left_right_normal_offsets_from_source_geometry"
_CORRIDOR_BOUNDARY_STATUS = {
    "assumed": "source_normal_offsets_assumed",
    "measured": "source_normal_offsets_measured",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256_json(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate course-bundle key: {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_json(value: str) -> None:
    raise ValueError(f"nonfinite course-bundle JSON value: {value}")


def _exact_keys(value: Any, keys: frozenset[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or value.keys() != keys:
        raise ValueError(f"{name} must have exactly: {', '.join(sorted(keys))}")
    return value


def _text(value: Any, name: str, *, limit: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be nonempty text of at most {limit} characters")
    return value.strip()


def _finite_number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    if positive and number <= 0.0:
        raise ValueError(f"{name} must be positive")
    return number


def _geometry_dict(track: SpatialTrack) -> dict[str, Any]:
    return {
        "closed": track.closed,
        "distance_m": track.distance_m,
        "x_m": track.x_m,
        "y_m": track.y_m,
        "curvature_per_m": track.curvature_per_m,
    }


def course_geometry_sha256(track: SpatialTrack) -> str:
    """Hash the normalized solver channels, independent of JSON whitespace."""

    return _sha256_json(_geometry_dict(track))


@dataclass(frozen=True, slots=True)
class SourceCellCorridor:
    """Declared widths in normal coordinates of the bundle's source geometry.

    The arrays contain one width per source cell and exclude the repeated
    closure point. They do not describe world-frame edges, cones, or the
    planner's separately smoothed reference path.
    """

    reference_geometry_sha256: str
    status: str
    left_width_m: tuple[float, ...]
    right_width_m: tuple[float, ...]
    source_name: str
    source_sha256: str
    processing_method: str
    review_note: str
    corridor_sha256: str


@dataclass(frozen=True, slots=True)
class CourseBundle:
    """Validated one-file course revision with immutable solver geometry."""

    course_id: str
    revision: str
    label: str
    description: str
    source_kind: str
    travel_direction: str
    boundary_status: str
    default_ai_half_width_m: float
    default_ai_vehicle_width_m: float
    default_ai_margin_m: float
    track: SpatialTrack
    geometry_sha256: str
    bundle_sha256: str
    schema_version: int = COURSE_BUNDLE_SCHEMA_VERSION
    source_cell_corridor: SourceCellCorridor | None = None
    source_file_sha256: str | None = None
    _manifest_json: str = field(default="", repr=False, compare=False)

    @property
    def catalog_id(self) -> str:
        """Unique UI and run-record key for a course revision."""

        return f"{self.course_id}@{self.revision}"

    @property
    def synthetic(self) -> bool:
        return self.source_kind == "synthetic"

    def to_dict(self) -> dict[str, Any]:
        """Return a detached copy of the canonical validated manifest."""

        return json.loads(self._manifest_json)

    def save(self, path: str | Path) -> Path:
        """Atomically save a portable copy without referring to the source path."""

        destination = Path(path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f"{destination.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(self.to_dict(), indent=2, ensure_ascii=False, allow_nan=False)
                + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    def solver_cell_count(self, maximum_cell_length_m: float) -> int:
        """Count exact source-arc subdivisions before allocating a solver grid."""

        step = _finite_number(
            maximum_cell_length_m, "maximum_cell_length_m", positive=True,
        )
        count = 0
        for length_m in self.track.cell_length_m:
            ratio = length_m / step
            if not isfinite(ratio) or ratio > MAX_BUNDLE_CELLS - count:
                raise ValueError("requested solver grid exceeds the 5000-cell compute cap")
            count += ceil(ratio)
        return count

    def solver_track(self, maximum_cell_length_m: float) -> SpatialTrack:
        """Keep verified exact arcs at coarse steps; split them at finer steps."""

        count = self.solver_cell_count(maximum_cell_length_m)
        if count == self.track.cell_count:
            return self.track
        return self.track.refine_arcs(maximum_cell_length_m)

    @classmethod
    def load(cls, path: str | Path) -> CourseBundle:
        """Read a bounded UTF-8 JSON file; no external asset paths are followed."""

        source = Path(path)
        with source.open("rb") as stream:
            data = stream.read(MAX_BUNDLE_BYTES + 1)
        if len(data) > MAX_BUNDLE_BYTES:
            raise ValueError("course bundle exceeds the 4 MiB input cap")
        try:
            payload = json.loads(
                data.decode("utf-8"),
                object_pairs_hook=_object_without_duplicate_keys,
                parse_constant=_reject_nonfinite_json,
            )
        except RecursionError as exc:
            raise ValueError("course bundle JSON nesting exceeds the parser limit") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("course bundle must be UTF-8 JSON") from exc
        bundle = cls.from_dict(payload)
        return cls(
            course_id=bundle.course_id,
            revision=bundle.revision,
            label=bundle.label,
            description=bundle.description,
            source_kind=bundle.source_kind,
            travel_direction=bundle.travel_direction,
            boundary_status=bundle.boundary_status,
            default_ai_half_width_m=bundle.default_ai_half_width_m,
            default_ai_vehicle_width_m=bundle.default_ai_vehicle_width_m,
            default_ai_margin_m=bundle.default_ai_margin_m,
            track=bundle.track,
            geometry_sha256=bundle.geometry_sha256,
            bundle_sha256=bundle.bundle_sha256,
            schema_version=bundle.schema_version,
            source_cell_corridor=bundle.source_cell_corridor,
            source_file_sha256=sha256(data).hexdigest(),
            _manifest_json=bundle._manifest_json,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CourseBundle:
        """Validate all versioned claims before a course becomes runnable."""

        if (
            type(payload) is dict
            and type(payload.get("schema_version")) is int
            and payload["schema_version"] == COURSE_BUNDLE_CORRIDOR_SCHEMA_VERSION
        ):
            return cls._from_v2_dict(payload)

        manifest = _exact_keys(payload, _TOP_KEYS, "course bundle")
        if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
            raise ValueError("unsupported course-bundle schema version")
        course_id = _text(manifest["course_id"], "course_id", limit=64)
        revision = _text(manifest["revision"], "revision", limit=64)
        if _ID_PATTERN.fullmatch(course_id) is None:
            raise ValueError("course_id must be a lowercase, path-free identifier")
        if _REVISION_PATTERN.fullmatch(revision) is None:
            raise ValueError("revision must be a path-free identifier")
        label = _text(manifest["label"], "label", limit=120)
        description = _text(manifest["description"], "description")
        source_kind = manifest["source_kind"]
        if source_kind not in ("synthetic", "measured"):
            raise ValueError("source_kind must be synthetic or measured")
        provenance = _exact_keys(manifest["provenance"], _PROVENANCE_KEYS, "provenance")
        source_name = _text(provenance["source_name"], "provenance.source_name")
        processing_method = _text(
            provenance["processing_method"], "provenance.processing_method",
        )
        review_note = _text(provenance["review_note"], "provenance.review_note")
        source_sha = provenance["source_sha256"]
        if source_sha is not None and (
            not isinstance(source_sha, str) or _SHA256_PATTERN.fullmatch(source_sha) is None
        ):
            raise ValueError("provenance.source_sha256 must be a lowercase SHA-256 or null")
        if source_kind == "measured" and source_sha is None:
            raise ValueError("measured courses require a source SHA-256")
        frame = _exact_keys(manifest["coordinate_frame"], _FRAME_KEYS, "coordinate_frame")
        if frame["type"] != "local_cartesian_right_handed_xy" or frame["units"] != "m":
            raise ValueError("coordinate_frame must use right-handed local x/y in meters")
        origin = _text(frame["origin"], "coordinate_frame.origin")
        x_axis = _text(frame["x_axis"], "coordinate_frame.x_axis")
        y_axis = _text(frame["y_axis"], "coordinate_frame.y_axis")
        if x_axis.casefold() == y_axis.casefold():
            raise ValueError("coordinate_frame axes must be distinct")
        travel_direction = manifest["travel_direction"]
        if travel_direction not in ("clockwise", "counterclockwise"):
            raise ValueError("travel_direction must be clockwise or counterclockwise")
        if manifest["boundary_status"] != "absent":
            raise ValueError("v1 has no surveyed-boundary frame; boundary_status must be absent")
        ai = _exact_keys(manifest["ai_defaults"], _AI_KEYS, "ai_defaults")
        if ai["width_source"] != "assumed_uniform":
            raise ValueError("v1 AI widths must be marked assumed_uniform")
        half_width = _finite_number(ai["half_width_m"], "ai_defaults.half_width_m", positive=True)
        vehicle_width = _finite_number(
            ai["vehicle_width_m"], "ai_defaults.vehicle_width_m", positive=True,
        )
        margin = _finite_number(ai["safety_margin_m"], "ai_defaults.safety_margin_m")
        if margin < 0.0 or half_width <= 0.5 * vehicle_width + margin:
            raise ValueError("AI defaults leave no usable assumed corridor")
        geometry = _exact_keys(manifest["geometry"], _GEOMETRY_KEYS, "geometry")
        if geometry["model"] != "piecewise_constant_curvature_arcs":
            raise ValueError("geometry.model must be piecewise_constant_curvature_arcs")
        if geometry["closed"] is not True:
            raise ValueError("course-bundle geometry must be closed")
        channels: dict[str, tuple[float, ...]] = {}
        for name in ("distance_m", "x_m", "y_m", "curvature_per_m"):
            values = geometry[name]
            if type(values) not in (list, tuple) or len(values) > MAX_BUNDLE_CELLS + 1:
                raise ValueError(f"geometry.{name} exceeds the cell cap or is not an array")
            channels[name] = tuple(
                _finite_number(value, f"geometry.{name}[{index}]")
                for index, value in enumerate(values)
            )
        if not 4 <= len(channels["curvature_per_m"]) <= MAX_BUNDLE_CELLS:
            raise ValueError("course bundle needs 4 through 5000 cells")
        track = SpatialTrack(**channels, closed=True)
        geometry_sha = course_geometry_sha256(track)
        if (
            not isinstance(manifest["geometry_sha256"], str)
            or manifest["geometry_sha256"] != geometry_sha
        ):
            raise ValueError("course geometry SHA-256 does not match its channels")
        try:
            track.validate_coherent_arcs()
        except ValueError as exc:
            raise ValueError(f"course geometry is not coherent: {exc}") from exc
        expected_turn = 2.0 * pi if travel_direction == "counterclockwise" else -2.0 * pi
        actual_turn = fsum(
            curvature * length_m
            for curvature, length_m in zip(
                track.curvature_per_m, track.cell_length_m, strict=True,
            )
        )
        if abs(actual_turn - expected_turn) > 1e-6:
            raise ValueError("travel_direction disagrees with the signed single-lap turn")
        normalized = {
            "schema_version": COURSE_BUNDLE_SCHEMA_VERSION,
            "course_id": course_id,
            "revision": revision,
            "label": label,
            "description": description,
            "source_kind": source_kind,
            "provenance": {
                "source_name": source_name,
                "source_sha256": source_sha,
                "processing_method": processing_method,
                "review_note": review_note,
            },
            "coordinate_frame": {
                "type": frame["type"],
                "units": frame["units"],
                "origin": origin,
                "x_axis": x_axis,
                "y_axis": y_axis,
            },
            "travel_direction": travel_direction,
            "boundary_status": "absent",
            "ai_defaults": {
                "width_source": "assumed_uniform",
                "half_width_m": half_width,
                "vehicle_width_m": vehicle_width,
                "safety_margin_m": margin,
            },
            "geometry": {"model": geometry["model"], **_geometry_dict(track)},
            "geometry_sha256": geometry_sha,
        }
        manifest_json = _canonical_json(normalized)
        return cls(
            course_id=course_id,
            revision=revision,
            label=label,
            description=description,
            source_kind=source_kind,
            travel_direction=travel_direction,
            boundary_status="absent",
            default_ai_half_width_m=half_width,
            default_ai_vehicle_width_m=vehicle_width,
            default_ai_margin_m=margin,
            track=track,
            geometry_sha256=geometry_sha,
            bundle_sha256=sha256(manifest_json.encode("utf-8")).hexdigest(),
            _manifest_json=manifest_json,
        )

    @classmethod
    def _from_v2_dict(cls, payload: dict[str, Any]) -> CourseBundle:
        """Validate source-relative widths without asserting planner-frame safety."""

        manifest = _exact_keys(payload, _TOP_KEYS_V2, "course bundle")
        # Reuse the unchanged v1 geometry and metadata contract. A v2 bundle
        # keeps v1 AI defaults as a separately identified uniform assumption;
        # the source-cell corridor below is never substituted for those fields.
        v1_manifest = {key: value for key, value in manifest.items() if key != "corridor"}
        v1_manifest["schema_version"] = COURSE_BUNDLE_SCHEMA_VERSION
        v1_manifest["boundary_status"] = "absent"
        base = cls.from_dict(v1_manifest)

        raw_corridor = _exact_keys(manifest["corridor"], _CORRIDOR_KEYS, "corridor")
        if raw_corridor["model"] != _CORRIDOR_MODEL:
            raise ValueError(f"corridor.model must be {_CORRIDOR_MODEL}")
        if raw_corridor["reference_geometry_sha256"] != base.geometry_sha256:
            raise ValueError("corridor.reference_geometry_sha256 must match validated source geometry")
        status = raw_corridor["status"]
        if not isinstance(status, str) or status not in _CORRIDOR_BOUNDARY_STATUS:
            raise ValueError("corridor.status must be assumed or measured")
        if manifest["boundary_status"] != _CORRIDOR_BOUNDARY_STATUS[status]:
            raise ValueError("boundary_status disagrees with corridor.status")
        if status == "measured" and base.source_kind != "measured":
            raise ValueError("measured corridor requires a measured source course")

        provenance = _exact_keys(
            raw_corridor["provenance"], _PROVENANCE_KEYS, "corridor.provenance",
        )
        source_name = _text(provenance["source_name"], "corridor.provenance.source_name")
        source_sha = provenance["source_sha256"]
        if not isinstance(source_sha, str) or _SHA256_PATTERN.fullmatch(source_sha) is None:
            raise ValueError("corridor.provenance.source_sha256 must be a lowercase SHA-256")
        processing_method = _text(
            provenance["processing_method"], "corridor.provenance.processing_method",
        )
        review_note = _text(provenance["review_note"], "corridor.provenance.review_note")

        widths: dict[str, tuple[float, ...]] = {}
        for side in ("left", "right"):
            key = f"{side}_width_m"
            values = raw_corridor[key]
            if type(values) not in (list, tuple) or len(values) != base.track.cell_count:
                raise ValueError(f"corridor.{key} must have exactly {base.track.cell_count} source-cell values")
            widths[key] = tuple(
                _finite_number(value, f"corridor.{key}[{index}]", positive=True)
                for index, value in enumerate(values)
            )

        normalized_corridor = {
            "model": _CORRIDOR_MODEL,
            "reference_geometry_sha256": base.geometry_sha256,
            "status": status,
            "left_width_m": widths["left_width_m"],
            "right_width_m": widths["right_width_m"],
            "provenance": {
                "source_name": source_name,
                "source_sha256": source_sha,
                "processing_method": processing_method,
                "review_note": review_note,
            },
        }
        corridor_sha = _sha256_json(normalized_corridor)
        if raw_corridor["corridor_sha256"] != corridor_sha:
            raise ValueError("corridor SHA-256 does not match its normalized channels and provenance")
        normalized = base.to_dict()
        normalized["schema_version"] = COURSE_BUNDLE_CORRIDOR_SCHEMA_VERSION
        normalized["boundary_status"] = _CORRIDOR_BOUNDARY_STATUS[status]
        normalized["corridor"] = {**normalized_corridor, "corridor_sha256": corridor_sha}
        manifest_json = _canonical_json(normalized)
        if len(manifest_json.encode("utf-8")) > MAX_BUNDLE_BYTES:
            raise ValueError("course bundle exceeds the 4 MiB input cap")
        source_cell_corridor = SourceCellCorridor(
            reference_geometry_sha256=base.geometry_sha256,
            status=status,
            left_width_m=widths["left_width_m"],
            right_width_m=widths["right_width_m"],
            source_name=source_name,
            source_sha256=source_sha,
            processing_method=processing_method,
            review_note=review_note,
            corridor_sha256=corridor_sha,
        )
        return replace(
            base,
            schema_version=COURSE_BUNDLE_CORRIDOR_SCHEMA_VERSION,
            boundary_status=_CORRIDOR_BOUNDARY_STATUS[status],
            source_cell_corridor=source_cell_corridor,
            bundle_sha256=sha256(manifest_json.encode("utf-8")).hexdigest(),
            _manifest_json=manifest_json,
        )


__all__ = [
    "COURSE_BUNDLE_SCHEMA_VERSION", "COURSE_BUNDLE_CORRIDOR_SCHEMA_VERSION",
    "MAX_BUNDLE_BYTES", "MAX_BUNDLE_CELLS", "CourseBundle",
    "SourceCellCorridor", "course_geometry_sha256",
]
