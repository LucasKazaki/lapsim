"""Construct pinned FSI/FSG source inputs without importing the simulator.

Source preparation only. This module neither admits nor supplies a racing line.
All resource acquisition and all runtime authorization belong to the caller.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from math import hypot, isfinite

from . import _fsi_geometry as geometry


CONTRACT = "lapsim.light-fsi-source-course.v1"
COURSE_ID = "amz_fssim_fsi_approx"
GEOMETRY_SHA256 = "4d0404480da3f1035a4a22f6d94ae6870278d010ca8b215f0160b8263156210d"
CONE_LF_SHA256 = "7e0cfd65403406e3d6cf0e12aeeb605efb0163b35f3b6312250f871f0ee85134"
BUNDLE_LF_SHA256 = "443abe03651008cfb2452dd36a2360f5e2695f6af5ef1d2f468f31297b36a976"
# These are reviewed encodings of one input, not caller-configurable trust pins.
_BUNDLE_ENCODINGS = (
    (58174, BUNDLE_LF_SHA256, "main_lf"),
    (60423, "46ce29a898f4491d3dc6456f42325769474fa7790ce4227a86a8ab537dcc373e", "pr166_crlf"),
)
_CONE_ENCODINGS = (
    (7377, CONE_LF_SHA256, "main_lf"),
    (7708, "a70ef6bc168801e1b985964e13c2ffbf4a540007ffc9bf84b23434b1a682c4a2", "pr166_crlf"),
)
FSG_COURSE_ID = "amz_fssim_fsg_approx"
FSG_GEOMETRY_SHA256 = "0863d0fe882a9e7d756e35b211ee510e829f1dde3384ec85d26d4737e748c0ee"
FSG_CONE_LF_SHA256 = "7b3351cd9db27912131b9f5de427861061e2144ed6795498fe980adcd905c30d"
FSG_BUNDLE_LF_SHA256 = "c6e4c47a3a4e5aa6efd3c1e4b93d332dc9cd1796f8ae88d02d4a970f6e6525af"


@dataclass(frozen=True, slots=True)
class _SourcePins:
    course_id: str
    geometry_sha256: str
    cones_lf_sha256: str
    bundle_lf_sha256: str
    bundle_encodings: tuple
    cone_encodings: tuple
    length_m: float
    label: str


_FSI = _SourcePins(COURSE_ID, GEOMETRY_SHA256, CONE_LF_SHA256, BUNDLE_LF_SHA256,
    _BUNDLE_ENCODINGS, _CONE_ENCODINGS, 216.14860023596088, "FSI")
_FSG = _SourcePins(FSG_COURSE_ID, FSG_GEOMETRY_SHA256, FSG_CONE_LF_SHA256,
    FSG_BUNDLE_LF_SHA256, ((76673, FSG_BUNDLE_LF_SHA256, "main_lf"),),
    ((8710, FSG_CONE_LF_SHA256, "main_lf"),), 306.45041872992834, "FSG")
_TOP_KEYS = frozenset((
    "schema_version", "course_id", "revision", "label", "description",
    "source_kind", "provenance", "coordinate_frame", "travel_direction",
    "boundary_status", "ai_defaults", "geometry", "geometry_sha256",
))
_GEOMETRY_KEYS = frozenset((
    "model", "closed", "distance_m", "x_m", "y_m", "curvature_per_m",
))
_PROVENANCE_KEYS = frozenset((
    "source_name", "source_sha256", "processing_method", "review_note",
))
_FRAME_KEYS = frozenset(("type", "units", "origin", "x_axis", "y_axis"))
_AI_KEYS = frozenset(("width_source", "half_width_m", "vehicle_width_m", "safety_margin_m"))
_CONE_FRAME_KEYS = frozenset((
    "schema", "raw_sha256", "LF_sha256", "source_geometry_sha256",
    "source_origin_m", "source_heading_rad", "source_to_course_SE2",
    "left_xy_m", "right_xy_m", "maximum_grid_xy_error_m",
    "maximum_grid_station_error_m", "maximum_grid_curvature_error_per_m",
    "confidence", "runtime_or_corridor_admission",
))
_SE2_KEYS = frozenset(("translation_x_m", "translation_y_m", "rotation_rad", "scale"))
MAX_REFERENCE_BYTES = 2 * 1024 * 1024


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _exact_keys(value, keys, name):
    _require(type(value) is dict and value.keys() == keys, f"Unexpected {name} fields")


def _pinned_bytes(raw, encodings, lf_sha256, name):
    _require(type(raw) is bytes, f"{name} must be immutable bytes")
    _require(len(raw) in tuple(row[0] for row in encodings), f"Unsupported {name} byte count")
    raw_sha256 = sha256(raw).hexdigest()
    encoding = next((label for size, digest, label in encodings
                     if len(raw) == size and raw_sha256 == digest), None)
    _require(encoding is not None, f"{name} is outside the fixed source identities")
    _require(sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == lf_sha256,
             f"{name} LF identity differs")
    return raw_sha256, encoding


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate source-course JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"Nonfinite source-course JSON constant: {value}")


def _channel(value, name):
    _require(type(value) is list and 1 <= len(value) <= 5001, f"Bounded {name} array required")
    _require(all(type(number) in (int, float) and isfinite(number) for number in value),
             f"Finite nonboolean {name} values required")
    # Keep parsed numbers unchanged: converting int/float spelling changes the
    # canonical geometry identity. The exact pinned source contains SI floats.
    return tuple(value)


@dataclass(frozen=True, slots=True)
class SourceTrack:
    """Immutable source arc grid; never an authenticated driving reference."""

    distance_m: tuple[float, ...]
    x_m: tuple[float, ...]
    y_m: tuple[float, ...]
    curvature_per_m: tuple[float, ...]
    closed: bool

    @property
    def cell_count(self):
        return len(self.curvature_per_m)

    @property
    def length_m(self):
        return self.distance_m[-1]

    @property
    def cell_length_m(self):
        return tuple(b - a for a, b in zip(self.distance_m, self.distance_m[1:]))

    @property
    def cell_center_distance_m(self):
        return tuple(.5 * (a + b) for a, b in zip(self.distance_m, self.distance_m[1:]))

    def geometry_dict(self):
        """Return fresh channels with the original geometry digest semantics."""
        return {"closed": self.closed, "distance_m": list(self.distance_m),
                "x_m": list(self.x_m), "y_m": list(self.y_m),
                "curvature_per_m": list(self.curvature_per_m)}


@dataclass(frozen=True, slots=True)
class SourceCourse:
    """Constructed input with explicit uncertainty and no admission authority.

    Frozen byte projections preserve all metadata/frame fields while callers
    receive fresh dictionaries. Constructing this DTO directly confers no trust;
    a future consumer must independently bind this module and its source pins.
    """

    source_track: SourceTrack
    bundle_raw_sha256: str
    cones_raw_sha256: str
    bundle_encoding: str
    cones_encoding: str
    bundle_payload_sha256: str
    _metadata_json: bytes
    _frame_json: bytes
    canonical_frame_artifact_sha256: str | None = None

    @property
    def contract(self):
        return CONTRACT

    @property
    def status(self):
        return "SOURCE_INPUT_ONLY_UNQUALIFIED"

    @property
    def course_id(self):
        return COURSE_ID

    @property
    def geometry_sha256(self):
        return GEOMETRY_SHA256

    def metadata_dict(self):
        """Fresh bundle metadata, including provenance and assumed widths."""
        return json.loads(self._metadata_json)

    def frame_dict(self):
        """Fresh cone frame: local source-only or exact pinned artifact values.

        Artifact diagnostics remain saved producer claims, not measurements of
        the current reconstruction. Neither construction supplies admission.
        """
        return json.loads(self._frame_json)


@dataclass(frozen=True, slots=True)
class FsgSourceCourse(SourceCourse):
    """Separate unqualified DTO; existing exact-FSI consumers reject this type.

    This carries local source/frame screens, never an authenticated driving line.
    Its identity cannot be selected through an FSI constructor or reference.
    """

    @property
    def contract(self):
        return "lapsim.light-fsg-source-course.v1"

    @property
    def course_id(self):
        return FSG_COURSE_ID

    @property
    def geometry_sha256(self):
        return FSG_GEOMETRY_SHA256


def construct_fsi_course(bundle_raw: bytes, cones_raw: bytes) -> SourceCourse:
    """Retain the existing fixed FSI input/DTO and reconstruction semantics."""
    return _construct_source_course(bundle_raw, cones_raw, _FSI)


def construct_fsg_course(bundle_raw: bytes, cones_raw: bytes) -> FsgSourceCourse:
    """Construct the exact LF FSG source grid and local cone-frame diagnostics.

    No driving reference is generated or substituted. This new type is not
    accepted by the FSI numerical/reference/worker path or seven-policy plan.
    """
    return _construct_source_course(bundle_raw, cones_raw, _FSG)


def _construct_source_course(bundle_raw, cones_raw, spec):
    """Check fixed bytes, preserve the source grid, and reconstruct its frame.

    Raises ValueError on unsupported inputs or unresolved geometric screens.
    No I/O, optimization, path substitution or admission occurs here. In
    particular, source_track must not fill an unavailable racing-line input.
    """
    _require(spec is _FSI or spec is _FSG, "Fixed reviewed source selection required")
    bundle_sha, bundle_encoding = _pinned_bytes(
        bundle_raw, spec.bundle_encodings, spec.bundle_lf_sha256, spec.label+" bundle")
    cones_sha, cones_encoding = _pinned_bytes(
        cones_raw, spec.cone_encodings, spec.cones_lf_sha256, spec.label+" cones")
    bundle = json.loads(bundle_raw, object_pairs_hook=_unique, parse_constant=_reject_constant)
    _exact_keys(bundle, _TOP_KEYS, "bundle")
    _require(type(bundle["schema_version"]) is int and bundle["schema_version"] == 1 and
             bundle["course_id"] == spec.course_id and bundle["revision"] == "v1" and
             bundle["geometry_sha256"] == spec.geometry_sha256,
             "Pinned "+spec.label+" course identity differs")
    _exact_keys(bundle["coordinate_frame"], _FRAME_KEYS, "coordinate frame")
    _require(bundle["coordinate_frame"]["type"] == "local_cartesian_right_handed_xy" and
             bundle["coordinate_frame"]["units"] == "m" and
             bundle["coordinate_frame"]["x_axis"] == "initial outgoing tangent" and
             bundle["coordinate_frame"]["y_axis"] == "local left",
             "Pinned SI frame differs")
    _exact_keys(bundle["provenance"], _PROVENANCE_KEYS, "provenance")
    _require(bundle["provenance"]["source_sha256"] == spec.cones_lf_sha256 and
             bundle["source_kind"] == "synthetic" and
             bundle["travel_direction"] == "clockwise" and bundle["boundary_status"] == "absent",
             "Source provenance/direction/uncertainty differs")
    _exact_keys(bundle["ai_defaults"], _AI_KEYS, "AI assumptions")
    _require(bundle["ai_defaults"] == {"width_source": "assumed_uniform", "half_width_m": 3.0,
                                     "vehicle_width_m": 1.4, "safety_margin_m": .2},
             "Pinned corridor assumptions differ")

    channels = bundle["geometry"]
    _exact_keys(channels, _GEOMETRY_KEYS, "geometry")
    _require(channels["model"] == "piecewise_constant_curvature_arcs" and
             channels["closed"] is True, "Closed source arc geometry required")
    track = SourceTrack(*(_channel(channels[name], name) for name in
                          ("distance_m", "x_m", "y_m", "curvature_per_m")), closed=True)
    _require(8 <= track.cell_count <= 5000 and
             len(track.distance_m) == len(track.x_m) == len(track.y_m) == track.cell_count + 1,
             "Source channel lengths differ")
    _require(track.distance_m[0] == 0.0 and track.x_m[0] == track.y_m[0] == 0.0 and
             all(b > a for a, b in zip(track.distance_m, track.distance_m[1:])) and
             abs(track.length_m - spec.length_m) <= 1e-9 and
             hypot(track.x_m[-1], track.y_m[-1]) <= 1e-7,
             "Source stations, seam or length differ")
    _require(geometry.digest(track.geometry_dict()) == spec.geometry_sha256,
             "Source geometry digest differs")

    # This replays only the archived course-construction arithmetic when called
    # by a future authorized consumer; it is never called at module import.
    frame = (geometry.reconstruct_frame(cones_raw, track.geometry_dict()) if spec is _FSI else
             geometry.reconstruct_fsg_frame(cones_raw, track.geometry_dict()))
    _require(frame["raw_sha256"] == cones_sha and frame["LF_sha256"] == spec.cones_lf_sha256 and
             frame["source_geometry_sha256"] == spec.geometry_sha256 and
             frame["runtime_or_corridor_admission"] is False,
             "Reconstructed frame identity differs")
    metadata = {name: value for name, value in bundle.items() if name != "geometry"}
    source_type = SourceCourse if spec is _FSI else FsgSourceCourse
    return source_type(
        source_track=track, bundle_raw_sha256=bundle_sha, cones_raw_sha256=cones_sha,
        bundle_encoding=bundle_encoding, cones_encoding=cones_encoding,
        bundle_payload_sha256=geometry.digest(bundle),
        _metadata_json=geometry.canonical(metadata).encode("utf-8"),
        _frame_json=geometry.canonical(frame).encode("utf-8"),
    )


def construct_fsi_course_from_reference(
    bundle_raw: bytes, cones_raw: bytes, line_artifact_raw: bytes, *,
    expected_line_artifact_sha256: str,
) -> SourceCourse:
    """Bind the complete saved reference frame without platform regeneration.

    This is input consistency, not authentication. The expected raw artifact pin
    must be inherited from the original reviewed native request/admission path.
    The caller still supplies the complete original artifact to the numerical
    reference/bridge, whose exact frame and source checks remain mandatory.

    The existing source constructor runs unchanged for local geometric screens.
    Its floating frame/diagnostics are check results only; they never overwrite
    the complete canonical frame retained in the pinned artifact. No additional
    tolerance-based identity comparison or fallback frame is introduced.
    """
    _require(type(line_artifact_raw) is bytes and
             0 < len(line_artifact_raw) <= MAX_REFERENCE_BYTES,
             "Bounded immutable complete reference artifact bytes required")
    _require(type(expected_line_artifact_sha256) is str and
             len(expected_line_artifact_sha256) == 64 and
             all(c in "0123456789abcdef" for c in expected_line_artifact_sha256) and
             sha256(line_artifact_raw).hexdigest() == expected_line_artifact_sha256,
             "Reference raw artifact identity differs from the explicit request pin")
    value = json.loads(line_artifact_raw, object_pairs_hook=_unique,
                       parse_constant=_reject_constant)
    # parse_constant rejects NaN/Infinity tokens, but not numeric overflow 1e999.
    # Check the complete object, including fields outside the frame projection.
    _require(len(geometry.canonical(value).encode("utf-8")) <= MAX_REFERENCE_BYTES,
             "Canonical reference artifact exceeds its transport bound")
    _require(type(value) is dict and
             value.get("schema") == "ev.awd-fsi-frozen-racing-reference.v6" and
             value.get("status") == "GEOMETRY_SCREENED_DYNAMIC_REPLAY_UNRUN" and
             value.get("role") == "development" and value.get("heldout_used") is False and
             value.get("shared_across_techniques") is True and
             value.get("minimum_time_proven") is False,
             "Exact development reference artifact required; no qualified-line claim")
    frame = value.get("frame")
    _exact_keys(frame, _CONE_FRAME_KEYS, "saved cone frame")
    _exact_keys(frame["source_to_course_SE2"], _SE2_KEYS, "saved SE2")
    finite = lambda n: type(n) in (int, float) and isfinite(n)
    se2 = frame["source_to_course_SE2"]
    _require(frame["schema"] == "ev.fsi-cone-frame.v1" and
             frame["confidence"] == "APPROXIMATE_SIMULATOR_CONES_NOT_SURVEY" and
             frame["runtime_or_corridor_admission"] is False and
             type(frame["source_origin_m"]) is list and len(frame["source_origin_m"]) == 2 and
             all(finite(n) for n in frame["source_origin_m"]) and
             finite(frame["source_heading_rad"]) and all(finite(n) for n in se2.values()) and
             se2["scale"] == 1. and se2["rotation_rad"] == -frame["source_heading_rad"],
             "Saved frame schema, finite rigid transform or unqualified status differs")
    for name in ("left_xy_m", "right_xy_m"):
        _require(type(frame[name]) is list and all(type(p) is list for p in frame[name]),
                 "Saved cone coordinate arrays required")
        geometry.checked_polygon(frame[name])
    # These bounds apply to the saved producer's reconstruction claims, as in
    # the original builder. They are NOT tolerances for frame/hash equality.
    for name, bound in (("maximum_grid_xy_error_m", 1e-7),
                        ("maximum_grid_station_error_m", 1e-7),
                        ("maximum_grid_curvature_error_per_m", 1e-9)):
        _require(finite(frame[name]) and 0 <= frame[name] <= bound,
                 "Saved source-grid diagnostic claim is outside the original screen")

    local = construct_fsi_course(bundle_raw, cones_raw)
    _require(value.get("source_geometry_sha256") == frame["source_geometry_sha256"] == GEOMETRY_SHA256 and
             value.get("source_bundle_payload_sha256") == local.bundle_payload_sha256 and
             value.get("raw_boundary_sha256") == frame["raw_sha256"] == local.cones_raw_sha256 and
             frame["LF_sha256"] == CONE_LF_SHA256 and
             value.get("frame_sha256") == geometry.digest(frame),
             "Saved reference frame/source/encoding identities differ")
    return replace(local, _frame_json=geometry.canonical(frame).encode("utf-8"),
                   canonical_frame_artifact_sha256=expected_line_artifact_sha256)
