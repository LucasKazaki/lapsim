"""Versioned evidence for one synthetic, time-domain pose-driver experiment.

This format is separate from endurance lap records.  It freezes the exact
piecewise course, assumed road, synthetic vehicle, controller settings, held
inputs, state boundaries, and diagnostics. Loading checks numerical recorded-
control replay and every saved start-of-interval dynamics evaluation within
explicit small numerical tolerances. Schema v2 also checks that the declared
controller and settings issue the saved controls; legacy v1 records retain
recorded-control replay only. None of these checks validates a measured
vehicle, surface, cone boundary, or FSAE lap time.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version as distribution_version
import json
from math import cos, isclose, isfinite, sin
import os
from pathlib import Path
import platform
import subprocess
from typing import Any
from uuid import uuid4

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.dynamics.conditions import (
    PlanarEnvironment, PlanarRoad, RectangularGripPatch, RoadDomain,
)
from lapsim.dynamics.planar import (
    PlanarControls, PlanarState, PlanarVehicleConfig, evaluate_planar_dynamics,
)
from lapsim.optimization.pose_driver import (
    PoseControllerAgreementReport, PoseDriverRun, PoseDriverSample,
    PoseDriverSettings, PoseReplayReport, _reference_start_heading,
    _validate_sampled_polyline, check_pose_controller_agreement,
    replay_pose_driver,
)


POSE_RUN_RECORD_SCHEMA_VERSION = 2
POSE_CONTROLLER_ALGORITHM_ID = "synthetic_pose_preview_pure_pursuit_grip_edge_v2"
POSE_CONTROLLER_ALGORITHM_VERSION = 2
_LEGACY_POSE_CONTROLLER_ALGORITHM_ID = "synthetic_pose_preview_pure_pursuit_grip_edge_v1"
_RECORD_TYPE = "synthetic_pose_driver"
_MAX_RECORD_BYTES = 32 * 1024 * 1024
_MAX_GRIP_PATCHES = 128
# Numerical evaluations are recomputed on load. These are per-field tolerances
# for harmless floating-point drift across compatible runtimes; pose states
# and path diagnostics retain the separate PoseReplayTolerances gate.
_EVALUATION_REL_TOL = 1e-10
_EVALUATION_ABS_TOL = 1e-9
_SOURCE_FILES = (
    "optimization/pose_driver.py", "dynamics/planar.py",
    "dynamics/conditions.py", "courses/spatial_track.py",
    "experiments/pose_run_record.py",
)
_STATUSES = {
    "target_reached", "road_domain_invalid", "outside_assumed_corridor",
    "projection_lost", "maximum_control_steps", "maximum_simulated_time",
    "maximum_internal_substeps",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )


def _content_id(payload: dict[str, Any]) -> str:
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _file_json(value: Any) -> str:
    result = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if len(result.encode("utf-8")) > _MAX_RECORD_BYTES:
        raise ValueError("pose record exceeds the 32 MiB load cap")
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON constant is forbidden: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _source_identity() -> dict[str, Any]:
    from lapsim.resources import build_identity, repository_root

    identity = build_identity()
    root = repository_root()
    source_root = root / "src" / "lapsim"
    source_files_sha256: dict[str, str | None] = {}
    for name in _SOURCE_FILES:
        try:
            source_files_sha256[name] = sha256((source_root / name).read_bytes()).hexdigest()
        except OSError:
            source_files_sha256[name] = None
    if identity is not None:
        return {
            "code_commit": identity.get("code_commit"),
            "dirty_worktree": identity.get("dirty_worktree"),
            "source_files_sha256": source_files_sha256,
        }
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=root, check=True, capture_output=True, text=True, timeout=5,
        ).stdout.strip())
        return {
            "code_commit": commit, "dirty_worktree": dirty,
            "source_files_sha256": source_files_sha256,
        }
    except (OSError, subprocess.SubprocessError):
        return {
            "code_commit": None, "dirty_worktree": None,
            "source_files_sha256": source_files_sha256,
        }


def _runtime_identity() -> dict[str, Any]:
    dependencies: dict[str, str | None] = {}
    for package in ("numpy", "scipy"):
        try:
            dependencies[package] = distribution_version(package)
        except PackageNotFoundError:
            dependencies[package] = None
    return {
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        },
        "dependencies": dependencies,
        "source": _source_identity(),
    }


def _mapping(value: Any, names: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != names:
        raise ValueError(f"{label} has missing or unexpected fields")
    return value


def _dataclass_mapping(value: Any, kind: type, label: str) -> dict[str, Any]:
    return _mapping(value, {item.name for item in fields(kind)}, label)


def _number(value: Any, label: str) -> float:
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return value


def _number_list(value: Any, label: str, *, length: int | None = None) -> tuple[float, ...]:
    if not isinstance(value, list) or (length is not None and len(value) != length):
        raise ValueError(f"{label} has invalid length")
    return tuple(_number(item, label) for item in value)


def _parse_track(value: Any, reference_geometry: str) -> SpatialTrack:
    data = _dataclass_mapping(value, SpatialTrack, "pose track")
    if type(data["closed"]) is not bool or not data["closed"]:
        raise ValueError("pose track must be closed")
    if (not isinstance(data["distance_m"], list) or
            len(data["distance_m"]) > 100_001):
        raise ValueError("pose track exceeds the 100000-cell record cap")
    if (not isinstance(data["x_m"], list) or
            len(data["x_m"]) != len(data["distance_m"]) or
            not isinstance(data["y_m"], list) or
            len(data["y_m"]) != len(data["distance_m"]) or
            not isinstance(data["curvature_per_m"], list) or
            len(data["curvature_per_m"]) != len(data["distance_m"]) - 1):
        raise ValueError("pose track channels are not aligned")
    distance = _number_list(data["distance_m"], "track distance")
    track = SpatialTrack(
        distance_m=distance,
        x_m=_number_list(data["x_m"], "track x"),
        y_m=_number_list(data["y_m"], "track y"),
        curvature_per_m=_number_list(data["curvature_per_m"], "track curvature"),
        closed=data["closed"],
    )
    if reference_geometry == "sampled_polyline":
        _validate_sampled_polyline(track)
    else:
        track.validate_coherent_arcs()
    return track


def _parse_vehicle(value: Any) -> PlanarVehicleConfig:
    data = _dataclass_mapping(value, PlanarVehicleConfig, "pose vehicle")
    return PlanarVehicleConfig(**{
        name: _number(field_value, f"vehicle {name}")
        for name, field_value in data.items()
    })


def _parse_environment(value: Any) -> PlanarEnvironment:
    data = _dataclass_mapping(value, PlanarEnvironment, "pose environment")
    road_data = _dataclass_mapping(data["road"], PlanarRoad, "pose road")
    if not isinstance(road_data["base_material_id"], str):
        raise ValueError("road material must be text")
    patches_data = road_data["patches"]
    if not isinstance(patches_data, list) or len(patches_data) > _MAX_GRIP_PATCHES:
        raise ValueError("road patches must be a bounded list")
    patches = []
    for index, raw in enumerate(patches_data):
        patch = _dataclass_mapping(raw, RectangularGripPatch, f"road patch {index}")
        if not isinstance(patch["material_id"], str):
            raise ValueError("road patch material must be text")
        patches.append(RectangularGripPatch(**{
            key: value if key == "material_id" else _number(value, key)
            for key, value in patch.items()
        }))
    raw_domain = road_data["valid_domain"]
    domain = None
    if raw_domain is not None:
        bounds = _dataclass_mapping(raw_domain, RoadDomain, "road domain")
        domain = RoadDomain(**{
            key: _number(value, key) for key, value in bounds.items()
        })
    road = PlanarRoad(
        base_material_id=road_data["base_material_id"],
        base_friction_multiplier=_number(
            road_data["base_friction_multiplier"], "base road grip",
        ),
        patches=tuple(patches), valid_domain=domain,
    )
    return PlanarEnvironment(
        **{
            key: road if key == "road" else _number(value, key)
            for key, value in data.items()
        },
    )


def _parse_settings(value: Any, schema_version: int) -> PoseDriverSettings:
    expected = {item.name for item in fields(PoseDriverSettings)}
    if schema_version == 1:
        expected.remove("reference_geometry")
    data = _mapping(value, expected, "pose settings")
    parsed: dict[str, float | int | str] = {}
    for name, item in data.items():
        if name in ("maximum_control_steps", "maximum_internal_substeps"):
            if type(item) is not int:
                raise ValueError(f"{name} must be an integer")
            parsed[name] = item
        elif name == "reference_geometry":
            if type(item) is not str:
                raise ValueError("reference_geometry must be text")
            parsed[name] = item
        else:
            parsed[name] = _number(item, name)
    return PoseDriverSettings(**parsed)


def _parse_state(value: Any) -> PlanarState:
    data = _dataclass_mapping(value, PlanarState, "pose state")
    return PlanarState(**{
        key: _number_list(item, key, length=4) if key == "wheel_speeds_rad_s"
        else _number(item, key)
        for key, item in data.items()
    })


def _parse_control(value: Any) -> PlanarControls:
    data = _dataclass_mapping(value, PlanarControls, "pose control")
    parsed: dict[str, Any] = {}
    for key, item in data.items():
        if key in (
            "steering_angles_rad", "drive_torques_nm", "brake_torques_nm",
        ):
            parsed[key] = _number_list(item, key, length=4)
        elif key == "normal_loads_n":
            parsed[key] = None if item is None else _number_list(item, key, length=4)
        else:
            parsed[key] = _number(item, key)
    return PlanarControls(**parsed)


def _parse_sample(value: Any) -> PoseDriverSample:
    data = _dataclass_mapping(value, PoseDriverSample, "pose sample")
    if type(data["projection_valid"]) is not bool:
        raise ValueError("projection_valid must be boolean")
    valid = data["projection_valid"]
    slack = data["minimum_assumed_boundary_slack_m"]
    if valid:
        slack = _number(slack, "boundary slack")
    elif slack is None:
        slack = float("-inf")
    else:
        raise ValueError("invalid projection requires null boundary slack")
    return PoseDriverSample(
        **{
            key: valid if key == "projection_valid" else
            slack if key == "minimum_assumed_boundary_slack_m" else
            _number(item, key)
            for key, item in data.items()
        },
    )


def _saved_sample(sample: PoseDriverSample) -> dict[str, Any]:
    result = asdict(sample)
    if not sample.projection_valid:
        if sample.minimum_assumed_boundary_slack_m != float("-inf"):
            raise ValueError("invalid projection must have negative-infinite slack")
        result["minimum_assumed_boundary_slack_m"] = None
    return result


def _evaluation_agrees(recomputed: Any, saved: Any) -> bool:
    """Compare nested dynamics evaluations without weakening discrete fields."""

    if isinstance(recomputed, dict):
        return (
            isinstance(saved, dict) and set(recomputed) == set(saved) and
            all(_evaluation_agrees(value, saved[key])
                for key, value in recomputed.items())
        )
    if isinstance(recomputed, (tuple, list)):
        return (
            isinstance(saved, list) and len(recomputed) == len(saved) and
            all(_evaluation_agrees(first, second)
                for first, second in zip(recomputed, saved, strict=True))
        )
    if type(recomputed) is float:
        return (
            isfinite(recomputed) and type(saved) in (int, float) and
            isfinite(saved) and
            isclose(recomputed, saved,
                    rel_tol=_EVALUATION_REL_TOL,
                    abs_tol=_EVALUATION_ABS_TOL)
        )
    # Integers (such as invalid-road counts), booleans, material IDs, and
    # nullable fields must agree exactly and keep their JSON type.
    return type(saved) is type(recomputed) and saved == recomputed


def _expected_initial_state(
    track: SpatialTrack, config: PlanarVehicleConfig,
    settings: PoseDriverSettings,
) -> PlanarState:
    """Recompute the declared reference geometry's explicit start state."""

    start_heading = _reference_start_heading(track, settings)
    wheel_speed = settings.initial_speed_mps / config.wheel_radius_m
    return PlanarState(
        x_m=track.x_m[0] - sin(start_heading) * settings.initial_lateral_offset_m,
        y_m=track.y_m[0] + cos(start_heading) * settings.initial_lateral_offset_m,
        heading_rad=start_heading,
        u_mps=settings.initial_speed_mps,
        wheel_speeds_rad_s=(wheel_speed,) * 4,
    )


def _validate_runtime(value: Any) -> None:
    runtime = _mapping(
        value, {"python", "platform", "dependencies", "source"}, "runtime",
    )
    for key, names in (
        ("python", {"implementation", "version"}),
        ("platform", {"system", "release", "version", "machine"}),
        ("dependencies", {"numpy", "scipy"}),
        ("source", {"code_commit", "dirty_worktree", "source_files_sha256"}),
    ):
        data = _mapping(runtime[key], names, f"runtime {key}")
        for field_name, item in data.items():
            if key == "source" and field_name == "dirty_worktree":
                if item is not None and type(item) is not bool:
                    raise ValueError("dirty_worktree must be boolean or null")
            elif key == "source" and field_name == "source_files_sha256":
                if not isinstance(item, dict) or set(item) != set(_SOURCE_FILES):
                    raise ValueError("source file hashes must be recorded")
                for name, digest in item.items():
                    if not isinstance(name, str) or (
                        digest is not None and
                        (not isinstance(digest, str) or len(digest) != 64 or
                         any(char not in "0123456789abcdef" for char in digest))
                    ):
                        raise ValueError("source file hash entry is invalid")
            elif key == "source" and field_name == "code_commit":
                if item is not None and (
                    not isinstance(item, str) or len(item) != 40 or
                    any(char not in "0123456789abcdef" for char in item)
                ):
                    raise ValueError("code commit must be a Git SHA-1 or null")
            elif key in ("python", "platform") and (
                not isinstance(item, str) or not item
            ):
                raise ValueError(f"runtime {key}.{field_name} must be nonempty text")
            elif item is not None and not isinstance(item, str):
                raise ValueError(f"runtime {key}.{field_name} must be text or null")


def _run_from_payload(
    payload: dict[str, Any],
) -> tuple[PoseDriverRun, PoseReplayReport, PoseControllerAgreementReport | None]:
    _mapping(payload, {
        "schema_version", "record_type", "simulation_mode", "evidence_level",
        "controller", "runtime", "inputs", "trace", "validity",
    }, "pose record")
    if (type(payload["schema_version"]) is not int or
            payload["schema_version"] not in (1, POSE_RUN_RECORD_SCHEMA_VERSION) or
            payload["record_type"] != _RECORD_TYPE or
            payload["simulation_mode"] != "time_domain_four_wheel" or
            payload["evidence_level"] != "synthetic_model_estimate"):
        raise ValueError("unsupported pose-run record schema")
    controller = _mapping(
        payload["controller"], {"algorithm_id", "algorithm_version"},
        "controller identity",
    )
    expected_controller = (
        (_LEGACY_POSE_CONTROLLER_ALGORITHM_ID, 1)
        if payload["schema_version"] == 1 else
        (POSE_CONTROLLER_ALGORITHM_ID, POSE_CONTROLLER_ALGORITHM_VERSION)
    )
    if (type(controller["algorithm_version"]) is not int or
            (controller["algorithm_id"], controller["algorithm_version"]) != expected_controller):
        raise ValueError("unsupported pose-controller identity")
    _validate_runtime(payload["runtime"])
    validity = _mapping(
        payload["validity"], {"vehicle_validation", "road_data_status"},
        "pose validity",
    )
    if (validity["vehicle_validation"] != "not_established_by_this_run" or
            validity["road_data_status"] != "synthetic_user_defined_flat_road"):
        raise ValueError("unsupported pose validity claims")
    inputs = _mapping(
        payload["inputs"], {"track", "vehicle_config", "environment", "settings"},
        "pose inputs",
    )
    settings = _parse_settings(inputs["settings"], payload["schema_version"])
    track = _parse_track(inputs["track"], settings.reference_geometry)
    config = _parse_vehicle(inputs["vehicle_config"])
    environment = _parse_environment(inputs["environment"])
    if settings.target_progress_m > track.length_m:
        raise ValueError("target progress exceeds the saved course")
    trace = _mapping(payload["trace"], {
        "times_s", "states", "controls", "evaluations", "samples", "status",
        "internal_substeps", "road_valid",
    }, "pose trace")
    for key in ("states", "controls", "evaluations", "samples"):
        if not isinstance(trace[key], list):
            raise ValueError(f"{key} must be a list")
    if not isinstance(trace["times_s"], list):
        raise ValueError("pose times must be a list")
    control_count = len(trace["controls"])
    if (control_count > settings.maximum_control_steps or
            len(trace["states"]) != control_count + 1 or
            len(trace["times_s"]) != control_count + 1 or
            len(trace["samples"]) != control_count + 1 or
            len(trace["evaluations"]) != control_count):
        raise ValueError("pose trace channels are not aligned")
    times = _number_list(trace["times_s"], "pose times")
    if not times or times[0] != 0.0:
        raise ValueError("pose times must start at zero")
    controls = tuple(_parse_control(item) for item in trace["controls"])
    states = tuple(_parse_state(item) for item in trace["states"])
    samples = tuple(_parse_sample(item) for item in trace["samples"])
    if states[0] != _expected_initial_state(track, config, settings):
        raise ValueError("initial state disagrees with course and pose settings")
    if (len(states) != len(controls) + 1 or
            len(times) != len(states) or len(samples) != len(states) or
            len(trace["evaluations"]) != len(controls)):
        raise ValueError("pose trace channels are not aligned")
    if (any(abs(time - index * settings.output_step_s) > 1e-9
            for index, time in enumerate(times)) or
            any(abs(sample.time_s - time) > 1e-9
                for sample, time in zip(samples, times, strict=True))):
        raise ValueError("pose trace times disagree with output step")
    status = trace["status"]
    if not isinstance(status, str) or (
        status not in _STATUSES and not status.startswith("model_error: ")
    ):
        raise ValueError("unknown pose-run status")
    substeps = trace["internal_substeps"]
    if type(substeps) is not int or substeps < 0:
        raise ValueError("internal_substeps must be a nonnegative integer")
    if type(trace["road_valid"]) is not bool:
        raise ValueError("road_valid must be boolean")
    evaluations = []
    for index, (state, control, saved) in enumerate(zip(
        states[:-1], controls, trace["evaluations"], strict=True,
    )):
        evaluation = evaluate_planar_dynamics(
            config, state, control, environment=environment,
        )
        if not _evaluation_agrees(asdict(evaluation), saved):
            raise ValueError(f"pose evaluation {index} disagrees with saved inputs")
        evaluations.append(evaluation)
    run = PoseDriverRun(
        track=track, vehicle_config=config, environment=environment,
        settings=settings, times_s=times, states=states, controls=controls,
        evaluations=tuple(evaluations), samples=samples, status=status,
        internal_substeps=substeps, road_valid=trace["road_valid"],
    )
    report = replay_pose_driver(run)
    if not report.passed:
        raise ValueError("pose record disagrees with numerical recorded-control replay")
    controller_report = None
    if payload["schema_version"] == POSE_RUN_RECORD_SCHEMA_VERSION:
        controller_report = check_pose_controller_agreement(run)
        if not controller_report.passed:
            raise ValueError(
                "pose record controls disagree with declared controller "
                f"at step {controller_report.first_mismatch_step}"
            )
    # Legacy v1 records retain only their original recorded-control dynamics
    # replay gate; controller decisions are not retrospectively attested.
    return run, report, controller_report


@dataclass(frozen=True, slots=True)
class PoseRunRecord:
    """Content-identified JSON record and its verified typed pose run.

    ``replay_report`` checks saved-control dynamics. ``controller_report``
    separately checks declared-controller decisions for schema v2 and is
    ``None`` for legacy v1 records that never carried this attestation.
    """

    content_id: str
    _payload_json: str = field(repr=False)
    _run: PoseDriverRun = field(repr=False, compare=False)
    replay_report: PoseReplayReport = field(repr=False, compare=False)
    controller_report: PoseControllerAgreementReport | None = field(
        repr=False, compare=False,
    )

    @property
    def run(self) -> PoseDriverRun:
        """The trace with dynamics evaluations recomputed and checked on load."""

        return self._run

    def replay(self) -> PoseReplayReport:
        """Check saved controls against the current numerical model again."""

        return replay_pose_driver(self._run)

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self._payload_json)
        payload["content_id"] = self.content_id
        return payload

    def save(self, path: str | Path) -> Path:
        """Write a strict JSON record atomically, outside or inside a checkout."""

        serialized = _file_json(self.to_dict())
        destination = Path(path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f"{destination.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(serialized, encoding="utf-8")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    @classmethod
    def capture(cls, run: PoseDriverRun) -> PoseRunRecord:
        """Freeze and validate one completed or interrupted synthetic run."""

        if not isinstance(run, PoseDriverRun):
            raise TypeError("run must be PoseDriverRun")
        if len(run.evaluations) != len(run.controls):
            raise ValueError("pose evaluations must align with controls")
        payload = {
            "schema_version": POSE_RUN_RECORD_SCHEMA_VERSION,
            "record_type": _RECORD_TYPE,
            "simulation_mode": "time_domain_four_wheel",
            "evidence_level": "synthetic_model_estimate",
            "controller": {
                "algorithm_id": POSE_CONTROLLER_ALGORITHM_ID,
                "algorithm_version": POSE_CONTROLLER_ALGORITHM_VERSION,
            },
            "runtime": _runtime_identity(),
            "inputs": {
                "track": asdict(run.track),
                "vehicle_config": asdict(run.vehicle_config),
                "environment": asdict(run.environment),
                "settings": asdict(run.settings),
            },
            "trace": {
                "times_s": list(run.times_s),
                "states": [asdict(state) for state in run.states],
                "controls": [asdict(control) for control in run.controls],
                "evaluations": [asdict(item) for item in run.evaluations],
                "samples": [_saved_sample(item) for item in run.samples],
                "status": run.status,
                "internal_substeps": run.internal_substeps,
                "road_valid": run.road_valid,
            },
            "validity": {
                "vehicle_validation": "not_established_by_this_run",
                "road_data_status": "synthetic_user_defined_flat_road",
            },
        }
        # asdict retains tuples in memory; validate the exact JSON shape the
        # loader will see after its list conversion and strict finite check.
        canonical = _canonical_json(payload)
        payload = json.loads(canonical)
        typed, report, controller_report = _run_from_payload(payload)
        content_id = _content_id(payload)
        _file_json({**payload, "content_id": content_id})
        return cls(content_id, canonical, typed, report, controller_report)

    @classmethod
    def load(cls, path: str | Path) -> PoseRunRecord:
        """Reject damaged, unsupported, or numerically inconsistent records.

        A permitted large file can still take noticeable time: every control
        hold is reintegrated within the saved substep limit. Desktop callers
        should load it in a worker and show progress as indeterminate.
        """

        source = Path(path)
        if source.stat().st_size > _MAX_RECORD_BYTES:
            raise ValueError("pose record exceeds the 32 MiB load cap")
        with source.open("r", encoding="utf-8") as stream:
            payload = json.load(
                stream, parse_constant=_reject_json_constant,
                object_pairs_hook=_reject_duplicate_keys,
            )
        if not isinstance(payload, dict):
            raise ValueError("pose record must be a JSON object")
        content_id = payload.pop("content_id", None)
        if not isinstance(content_id, str) or content_id != _content_id(payload):
            raise ValueError("pose-record content hash does not match")
        try:
            typed, report, controller_report = _run_from_payload(payload)
        except (KeyError, TypeError, IndexError, OverflowError) as error:
            raise ValueError("pose record has missing or invalid fields") from error
        return cls(content_id, _canonical_json(payload), typed, report,
                   controller_report)


def default_pose_run_directory() -> Path:
    """Store user pose experiments separately from engineering lap records."""

    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "LapSim" / "pose_runs"


__all__ = [
    "POSE_RUN_RECORD_SCHEMA_VERSION", "POSE_CONTROLLER_ALGORITHM_ID",
    "POSE_CONTROLLER_ALGORITHM_VERSION", "PoseRunRecord",
    "default_pose_run_directory",
]
