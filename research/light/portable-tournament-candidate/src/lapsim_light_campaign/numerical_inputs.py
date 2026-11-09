"""UNTESTED raw numerical inputs and mandatory external dependency interfaces.

Nothing here admits a producer bundle, qualifies an environment or authorizes
execution. Attribute/type matches cannot establish trusted adapter provenance.
"""
from dataclasses import dataclass
from abc import abstractmethod
from hashlib import sha256
from math import hypot, isfinite
from typing import Protocol

from lapsim_light_course.course import SourceCourse, SourceTrack, GEOMETRY_SHA256
from lapsim_light_guidance.driver import _validate_sampled_polyline

from .input_contracts import decode, digest, encode, exact, is_sha256, require

MAX_NATIVE_COURSE_JSON_BYTES = 2 * 1024 * 1024


def require_native_track(track):
    """Reject unknown/mutable nested inputs before invoking native track methods."""
    require(type(track) is SourceTrack, "Exact native SourceTrack required; no nested callback/protocol object")
    for name in ("distance_m", "x_m", "y_m", "curvature_per_m"):
        channel = getattr(track, name)
        require(type(channel) is tuple and 1 <= len(channel) <= 5001 and
                all(type(value) in (int, float) and isfinite(value) for value in channel),
                "Bounded immutable tuple of finite builtin track numbers required: " + name)
    require(track.closed is True and 8 <= len(track.curvature_per_m) <= 5000 and
            len(track.distance_m) == len(track.x_m) == len(track.y_m) == len(track.curvature_per_m) + 1,
            "Explicit closed native grid with exact channel inventory required")


def require_native_source_course(course):
    """Representation consistency only; existing content/authentication pins remain required."""
    require(type(course) is SourceCourse, "Exact native source-course DTO required")
    require_native_track(course.source_track)
    for raw in (course._metadata_json, course._frame_json):
        require(type(raw) is bytes and 0 < len(raw) <= MAX_NATIVE_COURSE_JSON_BYTES,
                "Immutable bounded source metadata/frame bytes required")
    require(all(is_sha256(getattr(course, name)) for name in
                ("bundle_raw_sha256", "cones_raw_sha256", "bundle_payload_sha256")) and
            all(type(value) is str and value in ("main_lf", "pr166_crlf") for value in
                (course.bundle_encoding, course.cones_encoding)),
            "Immutable source identity/encoding declarations required; declarations confer no authority")
    require(course.canonical_frame_artifact_sha256 is None or
            is_sha256(course.canonical_frame_artifact_sha256),
            "Canonical frame artifact pin must be absent or an exact SHA256")


REFERENCE_PARAMETERS={'stations':64,'maximum_iterations':48,'maximum_objective_calls':4096,
 'work_wall_s':60.,'solver_reserve_s':15.,'clearance_intervals':8192,'clearance_depth':10,
 'curvature_intervals':8192,'curvature_depth':10,'curvature_rounding_per_m':1e-12,
 'topology_max_pairs':200000,'topology_max_bucket_entries':100000,'topology_max_pair_visits':1000000,'topology_rounding_m':1e-9,
 'vehicle_width_m':1.4,'front_extent_m':1.,'rear_extent_m':1.,'safety_margin_m':.2,
 'map_uncertainty_m':.1,'tracking_allowance_m':.1,'polyline_error_m':.001,
 'wheelbase_m':1.6,'maximum_steering_rad':.4,'minimum_sample_spacing_m':.05,'maximum_sample_spacing_m':.1,
 'declared_input_scope':'Synthetic full rectangle/uncertainty assumptions;not measured team body or survey'}


class NumericalDependencyUnavailable(ValueError):
    pass


class SourceObserver(Protocol):
    implementation_sha256: str

    @abstractmethod
    def observe_source_identity(self) -> dict:
        """Actually observe the reviewed source/runtime closure through its owner."""
        raise NotImplementedError("Original reviewed source/runtime observer is unavailable")


class ResidualRegenRule(Protocol):
    implementation_sha256: str

    @abstractmethod
    def residual_low_speed_regen(self, u_mps, electrical) -> bool:
        """The unavailable original predicate, never an inferred approximation."""
        raise NotImplementedError("Original residual-regeneration predicate is unavailable")


@dataclass(frozen=True, slots=True)
class NumericalBindings:
    source_observer: object
    residual_regen_rule: object
    source_observer_sha256: str
    residual_regen_rule_sha256: str

    def require_available(self):
        for adapter, expected, method, placeholder in (
            (self.source_observer, self.source_observer_sha256, "observe_source_identity", SourceObserver.observe_source_identity),
            (self.residual_regen_rule, self.residual_regen_rule_sha256, "residual_low_speed_regen", ResidualRegenRule.residual_low_speed_regen),
        ):
            implementation = getattr(adapter, method, None)
            if (adapter is None or not callable(implementation) or
                    getattr(implementation, "__func__", implementation) is placeholder):
                raise NumericalDependencyUnavailable("Required external numerical dependency unavailable: " + method)
            require(is_sha256(expected) and getattr(adapter, "implementation_sha256", None) == expected,
                    "External numerical dependency differs from independently reviewed bootstrap")


@dataclass(frozen=True, slots=True)
class NumericalReference:
    """RAW reference transport, not an admitted line or an execution capability."""

    track: SourceTrack
    source_track: SourceTrack
    metadata_json: bytes
    artifact_raw: bytes

    @property
    def frame(self):
        return decode(self.metadata_json, 2 * 1024 * 1024)["frame"]

    @property
    def gate(self):
        return decode(self.metadata_json, 2 * 1024 * 1024)["gate"]

    @property
    def parameters(self):
        return decode(self.metadata_json, 2 * 1024 * 1024)["parameters"]

    @property
    def provenance(self):
        return decode(self.metadata_json, 2 * 1024 * 1024)["provenance"]

    def __getattr__(self, name):
        return getattr(self.track, name)


def raw_reference_inputs(artifact_raw, source_course, *, producer_audit_sha256,
                         reviewed_promotion_sha256):
    """Check numerical input consistency only; never authenticate producer claims.

    Real producer/optimization/continuous-clearance receipts are still required
    outside this constructor. An artifact's asserted screened status is not proof.
    """
    require_native_source_course(source_course)
    if source_course.canonical_frame_artifact_sha256 is not None:
        require(type(artifact_raw) is bytes and 0 < len(artifact_raw) <= 2 * 1024 * 1024 and
                sha256(artifact_raw).hexdigest() == source_course.canonical_frame_artifact_sha256,
                "Reference raw artifact differs from the canonical frame artifact pin")
    require(is_sha256(producer_audit_sha256) and
            is_sha256(reviewed_promotion_sha256), "Exact source inputs and external receipt pins required")
    value = decode(artifact_raw, 2 * 1024 * 1024)
    require(type(value) is dict and value.get("schema") == "ev.awd-fsi-frozen-racing-reference.v6" and
            value.get("status") == "GEOMETRY_SCREENED_DYNAMIC_REPLAY_UNRUN" and
            value.get("role") == "development" and value.get("heldout_used") is False and
            value.get("shared_across_techniques") is True, "Exact development reference input required")
    geometry = value["geometry"]
    exact(geometry, {"model", "closed", "distance_m", "x_m", "y_m", "curvature_per_m"}, "reference geometry")
    require(geometry["model"] == "sampled_polyline" and geometry["closed"] is True,
            "Sampled reference required; no source-arc fallback")
    channels = []
    for name in ("distance_m", "x_m", "y_m", "curvature_per_m"):
        values = geometry[name]
        require(type(values) is list and 1 <= len(values) <= 5001 and
                all(type(v) in (int, float) and isfinite(v) for v in values),
                "Bounded finite reference channels required")
        channels.append(tuple(values))
    track = SourceTrack(*channels, closed=True)
    require(8 <= track.cell_count <= 5000 and
            len(track.distance_m) == len(track.x_m) == len(track.y_m) == track.cell_count + 1 and
            track.distance_m[0] == track.x_m[0] == track.y_m[0] == 0. and
            all(b > a for a, b in zip(track.distance_m, track.distance_m[1:])) and
            0 < track.length_m <= 2200 and hypot(track.x_m[-1], track.y_m[-1]) <= 1e-8,
            "Reference shape, origin, station or closure differs")
    require(all(abs(hypot(b-a, d-c) - (s1-s0)) <= 1e-8 for a,b,c,d,s0,s1 in
                zip(track.x_m,track.x_m[1:],track.y_m,track.y_m[1:],track.distance_m,track.distance_m[1:])),
            "Reference must own chord stations; no inherited source distance")
    _validate_sampled_polyline(track)
    frame = source_course.frame_dict()
    require(value["source_geometry_sha256"] == GEOMETRY_SHA256 == digest(source_course.source_track.geometry_dict()) and
            value["source_bundle_payload_sha256"] == source_course.bundle_payload_sha256 and
            value["raw_boundary_sha256"] == source_course.cones_raw_sha256 and
            encode(value["frame"]) == encode(frame) and value["frame_sha256"] == digest(frame) and
            value["reference_geometry_sha256"] == digest(geometry),
            "Reference/source/frame identities differ")
    require(encode(value["parameters"]) == encode(REFERENCE_PARAMETERS), "Reference parameter recipe changed")
    expected_gate = {"origin_xy_m": [0.,0.], "forward_unit": [1.,0.], "finite_half_width_m": 3.,
                     "scope": "Source physical gate;not moved with reference distance"}
    require(encode(value["gate"]) == encode(expected_gate), "Original finite source gate required")
    provenance = {
        "artifact_sha256": sha256(artifact_raw).hexdigest(),
        "producer_audit_sha256": producer_audit_sha256,
        "reviewed_promotion_sha256": reviewed_promotion_sha256,
        "source_geometry_sha256": GEOMETRY_SHA256,
        "reference_geometry_sha256": value["reference_geometry_sha256"],
        "frame_sha256": digest(frame), "reference_length_m": track.length_m,
        "source_length_m": source_course.source_track.length_m, "reference_model": "sampled_polyline",
        "admission": "RAW_INPUT_CONSISTENCY_ONLY_NO_AUTHORITY",
    }
    metadata = {"frame": frame, "gate": expected_gate, "parameters": value["parameters"], "provenance": provenance}
    return NumericalReference(track, source_course.source_track, encode(metadata), artifact_raw)
