"""Versioned, immutable JSON evidence for a prescribed-path lap run.

The distance-domain solver estimates an achievable lap under its chosen path
and force-allocation assumptions.  A record preserves those assumptions and
the exact effective vehicle configuration without implying vehicle validation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from copy import deepcopy
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version as distribution_version
import json
from math import isfinite, isnan
from numbers import Real
import os
from pathlib import Path
import platform
from typing import Any, Mapping
from uuid import uuid4

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.events.endurance import EnduranceRunConfig, EnduranceRunResult
from lapsim.profiles import ResolvedManifest, snapshot_vehicle_config
from vehicle_model import Vehicle


RUN_RECORD_SCHEMA_VERSION = 2
_SUPPORTED_RUN_RECORD_SCHEMAS = frozenset((1, RUN_RECORD_SCHEMA_VERSION))
_RUNTIME_DEPENDENCIES = ("numpy", "scipy", "matplotlib")


def _canonical_json(value: Any) -> str:
    """Serialize only finite JSON values in a stable order."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256_json(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Nonfinite JSON constant is forbidden: {value}")


def _validated_mapping(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    if any(not isinstance(key, str) or not key for key in value):
        raise ValueError(f"{name} keys must be nonempty strings")
    try:
        return json.loads(_canonical_json(dict(value)))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain finite JSON values") from exc


def _road_grip_multiplier(value: Any) -> float:
    if (
        isinstance(value, bool) or not isinstance(value, Real)
        or not isfinite(value) or value <= 0.0
    ):
        raise ValueError("road_grip_multiplier must be finite and positive")
    return float(value)


def _saved_road_grip_multiplier(settings: Mapping[str, Any]) -> float:
    """Old v2 records without conditions use the original reference grip."""

    conditions = settings.get("conditions")
    if conditions is None:
        return 1.0
    if not isinstance(conditions, dict) or set(conditions) != {
        "road_grip_multiplier", "source"
    } or conditions.get("source") != "assumed_uniform_surface_sensitivity":
        raise ValueError("saved run conditions are invalid")
    return _road_grip_multiplier(conditions["road_grip_multiplier"])


def _runtime_identity() -> dict[str, Any]:
    """Record the interpreter, host, and installed numerical/plotting builds."""

    dependencies: dict[str, str] = {}
    for package in _RUNTIME_DEPENDENCIES:
        try:
            dependencies[package] = distribution_version(package)
        except PackageNotFoundError as exc:
            raise RuntimeError(f"required distribution {package!r} is unavailable") from exc
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
    }


def _validate_embedded_track(payload: Mapping[str, Any]) -> None:
    """Check v2's embedded solver grid independently of the record hash."""

    try:
        settings = payload["settings"]
        track = settings["track"]
        geometry = track["geometry"]
        if not isinstance(geometry, dict) or set(geometry) != {
            "closed", "distance_m", "x_m", "y_m", "curvature_per_m"
        }:
            raise ValueError("run-record track geometry has invalid channels")
        if not isinstance(geometry["closed"], bool):
            raise ValueError("run-record track geometry closed flag is invalid")
        for channel in ("distance_m", "x_m", "y_m", "curvature_per_m"):
            values = geometry[channel]
            if not isinstance(values, list) or any(
                isinstance(value, bool) or not isinstance(value, (int, float))
                or not isfinite(value) for value in values
            ):
                raise ValueError(f"run-record track geometry channel {channel} is invalid")
        solver_track = SpatialTrack(
            distance_m=tuple(geometry["distance_m"]),
            x_m=tuple(geometry["x_m"]),
            y_m=tuple(geometry["y_m"]),
            curvature_per_m=tuple(geometry["curvature_per_m"]),
            closed=geometry["closed"],
        )
        if (
            not isinstance(track["geometry_sha256"], str)
            or isinstance(track["cell_count"], bool)
            or not isinstance(track["cell_count"], int)
            or isinstance(track["length_m"], bool)
            or not isinstance(track["length_m"], (int, float))
            or not isfinite(track["length_m"])
            or not isinstance(track["closed"], bool)
        ):
            raise ValueError("run-record embedded track geometry metadata is invalid")
        if (
            track["geometry_sha256"] != _sha256_json(geometry)
            or track["cell_count"] != solver_track.cell_count
            or track["length_m"] != solver_track.length_m
            or track["closed"] is not solver_track.closed
        ):
            raise ValueError("run-record embedded track geometry does not match its hash or metadata")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("run-record embedded track geometry is missing or invalid") from exc


@dataclass(frozen=True, slots=True)
class LapRunSettings:
    """Exact course and run inputs, frozen before simulation begins.

    ``solver_settings`` must contain the actual path-constraint settings, not
    just the requested grid spacing.  The course hash includes every point
    and cell curvature in the solver's resampled track.
    """

    _json: str

    @classmethod
    def from_track(
        cls,
        track: SpatialTrack,
        *,
        track_id: str,
        solver_step_m: float,
        solver_settings: Mapping[str, Any],
        torque_request_fraction: float,
        endurance_config: EnduranceRunConfig,
        road_grip_multiplier: float = 1.0,
        profile_id: str | None = None,
        profile_label: str | None = None,
        path_planning: Mapping[str, Any] | None = None,
        source_course: Mapping[str, Any] | None = None,
    ) -> LapRunSettings:
        if not isinstance(track_id, str) or not track_id.strip():
            raise ValueError("track_id must be a nonempty string")
        if not track.closed:
            raise ValueError("a one-lap endurance record requires a closed course")
        if not isfinite(solver_step_m) or solver_step_m <= 0.0:
            raise ValueError("solver_step_m must be finite and positive")
        if not isfinite(torque_request_fraction) or not 0.0 <= torque_request_fraction <= 1.0:
            raise ValueError("torque_request_fraction must be finite and in [0, 1]")
        selected_road_grip = _road_grip_multiplier(road_grip_multiplier)
        if not isinstance(endurance_config, EnduranceRunConfig) or endurance_config.laps != 1:
            raise ValueError("endurance_config must describe exactly one lap")
        if profile_id is not None and (not isinstance(profile_id, str) or not profile_id.strip()):
            raise ValueError("profile_id must be a nonempty string when supplied")
        if profile_label is not None and (not isinstance(profile_label, str) or not profile_label.strip()):
            raise ValueError("profile_label must be a nonempty string when supplied")
        solver = _validated_mapping(solver_settings, "solver_settings")
        if not solver:
            raise ValueError("solver_settings cannot be empty")
        geometry = {
            "closed": track.closed,
            "distance_m": track.distance_m,
            "x_m": track.x_m,
            "y_m": track.y_m,
            "curvature_per_m": track.curvature_per_m,
        }
        payload = {
            "track": {
                "id": track_id,
                "geometry_sha256": _sha256_json(geometry),
                "geometry": geometry,
                "length_m": track.length_m,
                "cell_count": track.cell_count,
                "closed": track.closed,
            },
            "solver": {
                "requested_maximum_cell_length_m": solver_step_m,
                "path_constraint_settings": solver,
            },
            "driver": {"torque_request_fraction": torque_request_fraction},
            "conditions": {
                "road_grip_multiplier": selected_road_grip,
                "source": "assumed_uniform_surface_sensitivity",
            },
            "endurance_config": asdict(endurance_config),
            "profile_id": profile_id,
            "profile_label": profile_label,
        }
        if source_course is not None:
            source = _validated_mapping(source_course, "source_course")
            if not source:
                raise ValueError("source_course cannot be empty")
            payload["track"]["source_course"] = source
        if path_planning is not None:
            planning = _validated_mapping(path_planning, "path_planning")
            if not planning:
                raise ValueError("path_planning cannot be empty")
            payload["path_planning"] = planning
        return cls(_canonical_json(payload))

    def to_dict(self) -> dict[str, Any]:
        """Return a detached copy; callers cannot mutate saved settings."""

        return json.loads(self._json)


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Immutable-by-value run payload with a content-derived identifier."""

    run_id: str
    _payload_json: str

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self._payload_json)
        payload["run_id"] = self.run_id
        return payload

    def save(self, path: str | Path) -> Path:
        """Atomically export a complete JSON record and return its path."""

        destination = Path(path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f"{destination.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(self.to_dict(), indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    @classmethod
    def load(cls, path: str | Path) -> RunRecord:
        """Read a saved record and reject corruption or unsupported schemas."""

        with Path(path).open("r", encoding="utf-8") as stream:
            payload = json.load(stream, parse_constant=_reject_json_constant)
        if (
            not isinstance(payload, dict)
            or type(payload.get("schema_version")) is not int
            or payload["schema_version"] not in _SUPPORTED_RUN_RECORD_SCHEMAS
        ):
            raise ValueError("unsupported run-record schema")
        run_id = payload.pop("run_id", None)
        if not isinstance(run_id, str) or run_id != _sha256_json(payload):
            raise ValueError("run-record content hash does not match")
        if payload["schema_version"] == RUN_RECORD_SCHEMA_VERSION:
            _validate_embedded_track(payload)
        return cls(run_id=run_id, _payload_json=_canonical_json(payload))


_UNIT_SUFFIXES = (
    ("_nm_per_psi", "N*m/psi"),
    ("_nm_per_deg", "N*m/deg"),
    ("_nm_per_rad", "N*m/rad"),
    ("_rad_s2", "rad/s^2"),
    ("_rad_s", "rad/s"),
    ("_kgpm3", "kg/m^3"),
    ("_mps2", "m/s^2"),
    ("_per_m", "1/m"),
    ("_kwh", "kWh"),
    ("_kgm2", "kg*m^2"),
    ("_percent", "%"),
    ("_ratio", "1"),
    ("_fraction", "1"),
    ("_coefficient", "1"),
    ("_multiplier", "1"),
    ("_utilization", "1"),
    ("_mps", "m/s"),
    ("_rpm", "rev/min"),
    ("_rad", "rad"),
    ("_deg", "deg"),
    ("_psi", "psi"),
    ("_ohm", "ohm"),
    ("_m2", "m^2"),
    ("_nm", "N*m"),
    ("_kg", "kg"),
    ("_ms", "ms"),
    ("_hz", "Hz"),
    ("_ah", "Ah"),
    ("_pa", "Pa"),
    ("_a", "A"),
    ("_v", "V"),
    ("_w", "W"),
    ("_j", "J"),
    ("_n", "N"),
    ("_s", "s"),
    ("_m", "m"),
)


def _channel_unit(name: str) -> str | None:
    if name in {
        "battery.state_of_charge", "chain_drive.ratio", "chain_drive.efficiency",
        "aero.downforce_retention_at_roll_limit", "aero.active_aero.enabled",
    }:
        return "1"
    if name.endswith(("_active", "_limited", "_enabled", ".enabled", ".efficiency")):
        return "1"
    if name.endswith(("_index", "_count")):
        return "count"
    for suffix, unit in _UNIT_SUFFIXES:
        if name.endswith(suffix):
            return unit
    return None


def _channel_origin(name: str) -> str:
    prefix = name.split(".", 1)[0]
    if prefix == "controls":
        return "driver_command"
    if prefix == "endurance":
        return "distance_solver"
    if prefix == "energy":
        return "derived_accounting"
    if prefix == "limits":
        return "model_constraint"
    return "simulated_model"


def _trace_payload(result: EnduranceRunResult) -> dict[str, Any]:
    telemetry = result.telemetry
    if telemetry is None or telemetry.sample_count == 0:
        return {
            "sample_count": 0,
            "sample_time_s": [],
            "sample_distance_m": [],
            "channels": {},
            "status": "not_recorded" if telemetry is None else "empty",
        }
    sample_count = telemetry.sample_count
    for required in ("vehicle.time_s", "vehicle.distance_m"):
        if required not in telemetry:
            raise ValueError(f"telemetry is missing required alignment channel {required}")
    aligned: dict[str, list[float]] = {}
    for name in ("vehicle.time_s", "vehicle.distance_m"):
        values = [float(value) for value in telemetry[name]]
        if len(values) != sample_count or not all(isfinite(value) for value in values):
            raise ValueError(f"telemetry alignment channel {name} must be finite")
        if values[0] < 0.0 or any(next_value < value for value, next_value in zip(values, values[1:])):
            raise ValueError(f"telemetry alignment channel {name} must be nondecreasing and nonnegative")
        aligned[name] = values
    if any(next_value <= value for value, next_value in zip(aligned["vehicle.time_s"], aligned["vehicle.time_s"][1:])):
        raise ValueError("telemetry time must increase at every sample")

    channels: dict[str, Any] = {}
    for name in sorted(telemetry):
        values: list[float | None] = []
        for raw_value in telemetry[name]:
            value = float(raw_value)
            if isfinite(value):
                values.append(value)
            elif isnan(value):
                values.append(None)  # TelemetryRecorder's missing-channel marker.
            else:
                raise ValueError(f"telemetry channel {name} contains infinity")
        valid_count = sum(value is not None for value in values)
        channels[name] = {
            "unit": _channel_unit(name),
            "origin": _channel_origin(name),
            "validity": "complete" if valid_count == sample_count else "missing_samples",
            "valid_sample_count": valid_count,
            "values": values,
        }
    return {
        "sample_count": sample_count,
        "sample_time_s": aligned["vehicle.time_s"],
        "sample_distance_m": aligned["vehicle.distance_m"],
        "channels": channels,
        "status": "recorded",
    }


def _result_payload(result: EnduranceRunResult) -> dict[str, Any]:
    if result.completed_laps not in (0, 1) or len(result.lap_times_s) != result.completed_laps:
        raise ValueError("the run result must contain at most one completed lap")
    scalars = (result.driving_time_s, result.pack_energy_kwh, result.final_state_of_charge)
    if any(not isfinite(value) for value in scalars) or result.driving_time_s < 0.0:
        raise ValueError("run summary contains invalid numeric values")
    if not 0.0 <= result.final_state_of_charge <= 1.0:
        raise ValueError("final_state_of_charge must be in [0, 1]")
    if any(not isfinite(value) or value <= 0.0 for value in result.lap_times_s):
        raise ValueError("lap_times_s must contain finite positive times")
    if result.completed and result.completed_laps != 1:
        raise ValueError("a successful one-lap result must complete one lap")
    if result.failure_reason is not None and not result.failure_reason.strip():
        raise ValueError("failure_reason must be nonempty when present")
    summary = {
        "status": "completed" if result.completed else "failed",
        "termination_reason": "completed" if result.completed else result.failure_reason,
        "completed_laps": result.completed_laps,
        "driving_time_s": result.driving_time_s,
        "lap_times_s": list(result.lap_times_s),
        "pack_energy_kwh": result.pack_energy_kwh,
        "final_state_of_charge": result.final_state_of_charge,
    }
    for name in ("starting_speed_mps", "ending_speed_mps"):
        value = getattr(result, name)
        if value is not None:
            if not isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and nonnegative")
            summary[name] = value
    accepted_names = (
        "accepted_time_s", "accepted_distance_m", "accepted_speed_mps",
        "accepted_state_of_charge",
    )
    accepted_values = tuple(getattr(result, name, None) for name in accepted_names)
    if any(value is None for value in accepted_values):
        if not all(value is None for value in accepted_values):
            raise ValueError("accepted-prefix values must be supplied together")
    else:
        for name, value in zip(accepted_names, accepted_values, strict=True):
            if isinstance(value, bool) or not isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and nonnegative")
            summary[name] = value
        if summary["accepted_state_of_charge"] > 1.0:
            raise ValueError("accepted_state_of_charge must be in [0, 1]")
        if summary["accepted_time_s"] > result.driving_time_s + 1e-9:
            raise ValueError("accepted_time_s cannot exceed driving_time_s")
        if result.completed:
            if abs(summary["accepted_time_s"] - result.driving_time_s) > 1e-8:
                raise ValueError("completed accepted_time_s must equal driving_time_s")
            if (
                result.ending_speed_mps is not None
                and abs(summary["accepted_speed_mps"] - result.ending_speed_mps) > 1e-8
            ):
                raise ValueError("completed accepted_speed_mps must equal ending_speed_mps")
            if abs(
                summary["accepted_state_of_charge"] - result.final_state_of_charge
            ) > 1e-8:
                raise ValueError(
                    "completed accepted_state_of_charge must equal final_state_of_charge"
                )
    failed_lap = getattr(result, "failed_lap_index", None)
    failed_cell = getattr(result, "failed_cell_index", None)
    failed_update = getattr(result, "failed_cell_update_completed", None)
    failure_fields = (failed_lap, failed_cell, failed_update)
    if any(value is None for value in failure_fields):
        if not all(value is None for value in failure_fields):
            raise ValueError("failure location and update status must be supplied together")
    elif result.completed:
        raise ValueError("completed result cannot contain failure location")
    if failed_lap is not None:
        for name, value in (("failed_lap_index", failed_lap),
                            ("failed_cell_index", failed_cell)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
            summary[name] = value
    if failed_update is not None:
        if not isinstance(failed_update, bool):
            raise ValueError("failed_cell_update_completed must be a boolean")
        summary["failed_cell_update_completed"] = failed_update
    if result.seam_speed_delta_mps is not None:
        summary["seam_speed_delta_mps"] = result.seam_speed_delta_mps
    return summary


def capture_lap_run(
    result: EnduranceRunResult,
    manifest: ResolvedManifest,
    settings: LapRunSettings,
    *,
    actual_vehicle: Vehicle,
    user_overrides: Mapping[str, Any] | None = None,
) -> RunRecord:
    """Freeze a one-lap result, provenance, effective car, and sampled traces.

    For an edited profile, pass the full editable setup as ``user_overrides``.
    The base manifest remains labeled as the original selected profile while
    the effective constructor-field snapshot records what the solver used.
    """

    if not isinstance(result, EnduranceRunResult):
        raise TypeError("result must be EnduranceRunResult")
    if not isinstance(manifest, ResolvedManifest):
        raise TypeError("manifest must be ResolvedManifest")
    if not isinstance(settings, LapRunSettings):
        raise TypeError("settings must be LapRunSettings")
    if not isinstance(actual_vehicle, Vehicle):
        raise TypeError("actual_vehicle must be Vehicle")
    overrides = None if user_overrides is None else _validated_mapping(user_overrides, "user_overrides")
    if overrides == {}:
        raise ValueError("user_overrides must contain the edited setup when supplied")
    base_manifest = manifest.to_dict()
    effective_vehicle = snapshot_vehicle_config(actual_vehicle)
    base_config = base_manifest["model_config"]
    run_settings = settings.to_dict()
    road_grip_multiplier = _saved_road_grip_multiplier(run_settings)
    try:
        tire_fields = effective_vehicle["fields"]["tire"]["fields"]
        base_tire_fields = base_config["fields"]["tire"]["fields"]
        if tire_fields["road_grip_multiplier"] != road_grip_multiplier:
            raise ValueError("effective vehicle road grip disagrees with run settings")
        base_grip = base_tire_fields["road_grip_multiplier"]
    except (KeyError, TypeError) as exc:
        raise ValueError("vehicle snapshot has no road-grip setting") from exc
    config_changed = _canonical_json(base_config) != _canonical_json(effective_vehicle)
    effective_without_run_condition = deepcopy(effective_vehicle)
    effective_without_run_condition["fields"]["tire"]["fields"][
        "road_grip_multiplier"
    ] = base_grip
    profile_fields_changed = (
        _canonical_json(base_config)
        != _canonical_json(effective_without_run_condition)
    )
    if profile_fields_changed and overrides is None:
        raise ValueError("actual vehicle differs from base manifest; supply user_overrides")
    summary = _result_payload(result)
    telemetry = _trace_payload(result)
    if telemetry["sample_count"] and "accepted_time_s" in summary:
        for field_name, samples_name in (
            ("accepted_time_s", "sample_time_s"),
            ("accepted_distance_m", "sample_distance_m"),
        ):
            if abs(summary[field_name] - telemetry[samples_name][-1]) > 1e-8:
                raise ValueError(
                    f"{field_name} must match the last accepted telemetry sample"
                )
        for field_name, channel_name in (
            ("accepted_speed_mps", "vehicle.speed_mps"),
            ("accepted_state_of_charge", "battery.state_of_charge"),
        ):
            channel = telemetry["channels"].get(channel_name)
            if (
                channel is not None and channel["values"][-1] is not None
                and abs(summary[field_name] - channel["values"][-1]) > 1e-8
            ):
                raise ValueError(
                    f"{field_name} must match the last accepted telemetry sample"
                )
    warnings = list(manifest.limitations)
    if manifest.code_commit is None:
        warnings.append("Source commit was unavailable for this run.")
    if manifest.dirty_worktree:
        warnings.append("The source checkout had uncommitted changes; the commit alone cannot reproduce it.")
    if telemetry["sample_count"] == 0:
        warnings.append("No synchronized telemetry samples were recorded.")
    if (
        result.failure_reason is not None
        and summary.get("accepted_time_s") is not None
        and result.driving_time_s > summary["accepted_time_s"] + 1e-9
    ):
        warnings.append(
            "The failed cell advanced the vehicle before rejection; result "
            "time, speed, and SOC describe that attempt, while accepted-prefix "
            "fields and telemetry describe only checked cells."
        )
    if any(channel["unit"] is None for channel in telemetry["channels"].values()):
        warnings.append("Some telemetry channels have unspecified units.")
    payload = {
        "schema_version": RUN_RECORD_SCHEMA_VERSION,
        "simulation_mode": "prescribed_path_distance_domain",
        "evidence_level": "simulation_model_estimate",
        "runtime": _runtime_identity(),
        "model_assumptions": [
            "prescribed_course_path",
            "distance_domain_speed_envelope",
            "capacity_based_tire_force_allocation",
        ],
        "configuration": {
            "base_profile_manifest": base_manifest,
            "selected_profile_id": run_settings["profile_id"] or manifest.profile_id,
            "selected_profile_label": run_settings["profile_label"] or manifest.profile_name,
            "user_overrides": overrides,
            "effective_vehicle_config": effective_vehicle,
            "effective_vehicle_config_sha256": _sha256_json(effective_vehicle),
            "effective_config_differs_from_base": config_changed,
            "profile_fields_differ_from_base": profile_fields_changed,
        },
        "settings": run_settings,
        "result": summary,
        "telemetry": telemetry,
        "validity": {
            "vehicle_validation": "not_established_by_this_run",
            "warnings": warnings,
        },
    }
    _validate_embedded_track(payload)
    return RunRecord(run_id=_sha256_json(payload), _payload_json=_canonical_json(payload))


def default_run_directory() -> Path:
    """Return a per-user storage location outside the source checkout."""

    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "LapSim" / "runs"


__all__ = [
    "RUN_RECORD_SCHEMA_VERSION",
    "LapRunSettings",
    "RunRecord",
    "capture_lap_run",
    "default_run_directory",
]
