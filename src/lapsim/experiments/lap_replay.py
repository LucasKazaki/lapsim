"""Check a saved one-lap model run against its recorded cell commands.

This is an explicit, potentially expensive engineering-model replay. It does
not verify the vehicle against measured data or implement a driving session.
"""

from __future__ import annotations

from bisect import bisect_right
from copy import deepcopy
from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from typing import Any, Mapping

from lapsim.core.controls import Controls
from lapsim.courses.spatial_track import SpatialTrack
from lapsim.events.endurance import EnduranceRunConfig, EnduranceSimulator
from lapsim.profiles import snapshot_vehicle_config
from lapsim.profiles.adapter import _code_identity
from lapsim.solvers.path_constraints import PathConstraintSolver
from vehicle_model import (
    ActiveAero, Aero, Battery, Brakes, ChainDrive, Chassis, Drivetrain,
    FinalDrive, Inverter, Motor,
    OCVPackBattery, Pacejka52UpcR20LateralModel,
    Pacejka52UpcR20LongitudinalModel, Pacejka61LateralModel,
    RCTheveninBattery, Suspension, Tire, Vehicle,
)

from .run_record import (
    RUN_RECORD_SCHEMA_VERSION, RunRecord, _runtime_identity,
    _saved_road_grip_multiplier,
)


_MODEL_CLASSES = {
    cls.__name__: cls for cls in (
        Vehicle, Tire, Drivetrain, Motor, Inverter, ChainDrive, Battery, Aero,
        ActiveAero, OCVPackBattery, RCTheveninBattery, Brakes, Chassis,
        Suspension, Pacejka61LateralModel, Pacejka52UpcR20LateralModel,
        Pacejka52UpcR20LongitudinalModel,
    )
}
# FinalDrive is the legacy public alias of ChainDrive. Fresh snapshots identify
# it as ChainDrive; keeping the alias explicit makes unsupported names obvious.
_MODEL_CLASSES["FinalDrive"] = FinalDrive
_CONTROL_FIELDS = tuple(field.name for field in fields(Controls))


def _digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _required_object(parent: Mapping[str, Any], key: str, label: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"saved {label} must be an object")
    return value


def _restore_config(value: Any) -> Any:
    """Decode only known model dataclasses; never import a class from JSON."""

    if isinstance(value, list):
        return [_restore_config(item) for item in value]
    if isinstance(value, dict):
        if "class" in value or "fields" in value:
            if set(value) != {"class", "fields"} or not isinstance(value["fields"], dict):
                raise ValueError("malformed model constructor snapshot")
            name = value["class"]
            if not isinstance(name, str) or name not in _MODEL_CLASSES:
                raise ValueError(f"unsupported model class in snapshot: {name!r}")
            cls = _MODEL_CLASSES[name]
            expected = {
                field.name for field in fields(cls)
                if field.init and not (cls is Drivetrain and field.name == "tire")
            }
            # A v2 run saved before uniform road-grip scenarios has the same
            # tire constructor snapshot except for this new defaulted field.
            legacy_tire = (
                cls is Tire
                and set(value["fields"]) == expected - {"road_grip_multiplier"}
            )
            if set(value["fields"]) != expected and not legacy_tire:
                raise ValueError(f"constructor fields do not match {name}")
            try:
                return cls(**{
                    key: _restore_config(item)
                    for key, item in value["fields"].items()
                })
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"could not restore model class {name}: {exc}") from exc
        return {key: _restore_config(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and isfinite(value):
        return value
    raise ValueError("model constructor snapshot contains an unsupported value")


def _normalized_vehicle_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Add only the new 1.0 tire default for an intact older v2 snapshot."""

    normalized = deepcopy(snapshot)
    tire = normalized.get("fields", {}).get("tire")
    if (
        isinstance(tire, dict) and tire.get("class") == "Tire"
        and isinstance(tire.get("fields"), dict)
    ):
        tire["fields"].setdefault("road_grip_multiplier", 1.0)
    return normalized


@dataclass(frozen=True, slots=True)
class LapReplayTolerances:
    """Absolute agreement thresholds in the units named by each field."""

    time_s: float = 0.01
    speed_mps: float = 0.01
    energy_kwh: float = 0.00001
    state_of_charge: float = 0.00001
    distance_m: float = 0.00000001

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0.0:
                raise ValueError(f"{field.name} tolerance must be finite and nonnegative")


@dataclass(frozen=True, slots=True)
class LapReplayMetric:
    name: str
    maximum_absolute_error: float | None
    tolerance: float
    passed: bool


@dataclass(frozen=True, slots=True)
class LapReplayReport:
    """Numerical agreement is separate from source and runtime provenance."""

    run_id: str
    model_agreement: bool
    replay_completed: bool
    recorded_sample_count: int
    replayed_sample_count: int
    metrics: tuple[LapReplayMetric, ...]
    mismatch_reasons: tuple[str, ...]
    provenance_warnings: tuple[str, ...]

    @property
    def source_runtime_match(self) -> bool:
        return not self.provenance_warnings

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _RecordedCellControls:
    def __init__(self, track: SpatialTrack, commands: tuple[Controls, ...]) -> None:
        self.track = track
        self.commands = commands

    def controls_at(self, distance_m: float) -> Controls:
        index = bisect_right(self.track.distance_m, distance_m) - 1
        if not 0 <= index < len(self.commands):
            raise ValueError("recorded controls queried outside the saved lap")
        return self.commands[index]


def _recorded_controls(payload: Mapping[str, Any], track: SpatialTrack) -> tuple[Controls, ...]:
    trace = _required_object(payload, "telemetry", "telemetry")
    count = track.cell_count
    if trace.get("status") != "recorded" or trace.get("sample_count") != count:
        raise ValueError("a complete accepted-cell trace is required for lap replay")
    channels = trace.get("channels")
    sample_time = trace.get("sample_time_s")
    sample_distance = trace.get("sample_distance_m")
    if not isinstance(channels, dict) or not isinstance(sample_time, list) or not isinstance(sample_distance, list) or len(sample_time) != count or len(sample_distance) != count:
        raise ValueError("saved lap telemetry is not aligned with the solver grid")
    previous_time = 0.0
    for index, (time, distance) in enumerate(zip(sample_time, sample_distance, strict=True)):
        time_s = _finite_number(time, "sample time")
        distance_m = _finite_number(distance, "sample distance")
        if time_s <= previous_time or abs(distance_m - track.distance_m[index + 1]) > 1e-8:
            raise ValueError("saved lap sample times or distances do not align with cells")
        previous_time = time_s
    required = (
        *(f"controls.{name}" for name in _CONTROL_FIELDS),
        "endurance.cell_index", "endurance.lap_index",
        "endurance.path_speed_ceiling_mps", "vehicle.speed_mps",
    )
    for name in required:
        channel = channels.get(name)
        if not isinstance(channel, dict) or channel.get("validity") != "complete" or channel.get("valid_sample_count") != count or not isinstance(channel.get("values"), list) or len(channel["values"]) != count:
            raise ValueError(f"saved lap telemetry is missing a complete {name} channel")
        for value in channel["values"]:
            _finite_number(value, name)
    if any(channels["endurance.cell_index"]["values"][index] != index or channels["endurance.lap_index"]["values"][index] != 0 for index in range(count)):
        raise ValueError("saved lap cell and lap indices are not aligned")
    for name, samples in (("vehicle.time_s", sample_time), ("vehicle.distance_m", sample_distance)):
        channel = channels.get(name)
        if not isinstance(channel, dict) or channel.get("values") != samples:
            raise ValueError(f"saved {name} does not match the sample alignment axis")
    return tuple(
        Controls(**{
            field: channels[f"controls.{field}"]["values"][index]
            for field in _CONTROL_FIELDS
        })
        for index in range(count)
    )


def _provenance_warnings(payload: Mapping[str, Any]) -> tuple[str, ...]:
    warnings: list[str] = []
    configuration = _required_object(payload, "configuration", "configuration")
    source = _required_object(configuration, "base_profile_manifest", "base profile manifest")
    recorded_commit = source.get("code_commit")
    recorded_dirty = source.get("dirty_worktree")
    current_commit, current_dirty = _code_identity()
    if recorded_commit is None or current_commit is None:
        warnings.append("Source commit is unavailable for the saved run or current checkout.")
    elif recorded_commit != current_commit:
        warnings.append("Current source commit differs from the saved run.")
    if recorded_dirty is not False:
        warnings.append("The saved run used uncommitted or unknown source changes.")
    if current_dirty is not False:
        warnings.append("The current checkout has uncommitted or unknown source changes.")
    recorded_runtime = _required_object(payload, "runtime", "runtime")
    current_runtime = _runtime_identity()
    for key in ("python", "platform", "dependencies"):
        if recorded_runtime.get(key) != current_runtime[key]:
            warnings.append(f"Current {key} differs from the saved run.")
    return tuple(warnings)


def _metric(name: str, expected: float, actual: float, tolerance: float) -> LapReplayMetric:
    error = abs(expected - actual)
    return LapReplayMetric(name, error, tolerance, error <= tolerance)


def _trace_metric(name: str, expected: list[float], actual: tuple[float, ...], tolerance: float) -> LapReplayMetric:
    if len(expected) != len(actual):
        return LapReplayMetric(name, None, tolerance, False)
    error = max((abs(saved - observed) for saved, observed in zip(expected, actual, strict=True)), default=0.0)
    return LapReplayMetric(name, error, tolerance, error <= tolerance)


def replay_lap_record(
    path: str | Path, *, tolerances: LapReplayTolerances | None = None,
) -> LapReplayReport:
    """Replay one completed v2 lap's recorded controls through the model.

    Model agreement compares saved and replayed numerical results only. Even
    exact agreement does not validate a car or a track against measurements.
    """

    record = RunRecord.load(path)
    payload = record.to_dict()
    if payload["schema_version"] != RUN_RECORD_SCHEMA_VERSION:
        raise ValueError("only v2 records with an embedded solver grid can be replayed")
    if payload.get("simulation_mode") != "prescribed_path_distance_domain":
        raise ValueError("unsupported lap simulation mode")
    saved_result = _required_object(payload, "result", "result")
    if saved_result.get("status") != "completed" or saved_result.get("completed_laps") != 1:
        raise ValueError("only completed one-lap records can replay recorded controls")
    selected_tolerances = tolerances or LapReplayTolerances()
    if not isinstance(selected_tolerances, LapReplayTolerances):
        raise TypeError("tolerances must be LapReplayTolerances")

    configuration = _required_object(payload, "configuration", "configuration")
    snapshot = _required_object(
        configuration, "effective_vehicle_config", "effective vehicle configuration",
    )
    if _digest(snapshot) != configuration.get("effective_vehicle_config_sha256"):
        raise ValueError("effective vehicle snapshot hash does not match")
    vehicle = _restore_config(snapshot)
    if (
        type(vehicle) is not Vehicle
        or _digest(snapshot_vehicle_config(vehicle))
        != _digest(_normalized_vehicle_snapshot(snapshot))
    ):
        raise ValueError("effective vehicle snapshot cannot be restored exactly")

    settings = _required_object(payload, "settings", "settings")
    if vehicle.tire.road_grip_multiplier != _saved_road_grip_multiplier(settings):
        raise ValueError("saved road-grip setting disagrees with vehicle snapshot")
    geometry = _required_object(
        _required_object(settings, "track", "track"), "geometry", "track geometry",
    )
    track = SpatialTrack(
        distance_m=tuple(geometry["distance_m"]),
        x_m=tuple(geometry["x_m"]),
        y_m=tuple(geometry["y_m"]),
        curvature_per_m=tuple(geometry["curvature_per_m"]),
        closed=geometry["closed"],
    )
    if not track.closed:
        raise ValueError("lap replay requires a closed solver track")
    commands = _recorded_controls(payload, track)
    solver_settings = _required_object(
        _required_object(settings, "solver", "solver"),
        "path_constraint_settings", "path constraint settings",
    )
    run_settings = _required_object(settings, "endurance_config", "endurance configuration")
    try:
        config = EnduranceRunConfig(**run_settings)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"saved endurance configuration is invalid: {exc}") from exc
    if config.laps != 1:
        raise ValueError("saved endurance configuration must describe one lap")
    path_planning = settings.get("path_planning", {})
    if not isinstance(path_planning, dict):
        raise ValueError("saved path planning settings must be an object")
    if (
        path_planning.get("lap_start_policy")
        == "speed_only_periodic_fixed_initial_vehicle_state"
        and config.starting_speed_mps is None
    ):
        raise ValueError("saved speed-periodic lap is missing its explicit start speed")
    if "starting_speed_mps" not in saved_result or "ending_speed_mps" not in saved_result:
        raise ValueError("saved lap has no measured entry and exit speeds")
    if (
        not isinstance(saved_result.get("lap_times_s"), list)
        or len(saved_result["lap_times_s"]) != 1
    ):
        raise ValueError("saved completed lap must have exactly one lap time")
    for name in (
        "driving_time_s", "starting_speed_mps", "ending_speed_mps",
        "pack_energy_kwh", "final_state_of_charge",
    ):
        if name not in saved_result:
            raise ValueError(f"saved lap result is missing {name}")
        _finite_number(saved_result[name], f"saved {name}")
    _finite_number(saved_result["lap_times_s"][0], "saved lap time")
    if config.starting_speed_mps is not None and abs(
        config.starting_speed_mps
        - _finite_number(saved_result["starting_speed_mps"], "recorded starting speed")
    ) > 1e-9:
        raise ValueError("explicit lap start speed disagrees with the saved result")
    provenance_warnings = _provenance_warnings(payload)
    try:
        solver = PathConstraintSolver(**solver_settings)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"saved path constraint settings are invalid: {exc}") from exc
    try:
        vehicle.reset_state()
        constraints = solver.solve(track, vehicle)
        replayed = EnduranceSimulator().run(
            vehicle, constraints, _RecordedCellControls(track, commands),
            config, record_telemetry=True,
        )
    except (ValueError, TypeError, RuntimeError, ArithmeticError, OverflowError) as exc:
        return LapReplayReport(
            run_id=record.run_id, model_agreement=False,
            replay_completed=False, recorded_sample_count=track.cell_count,
            replayed_sample_count=0, metrics=(),
            mismatch_reasons=(f"Replay model raised {type(exc).__name__}: {exc}",),
            provenance_warnings=provenance_warnings,
        )

    reasons: list[str] = []
    replayed_count = replayed.telemetry.sample_count if replayed.telemetry else 0
    if not replayed.completed or replayed.completed_laps != 1:
        reasons.append(f"Replay did not complete one lap: {replayed.failure_reason}")
    if replayed_count != track.cell_count:
        reasons.append("Replay accepted-cell count differs from the saved grid")
    metric_specs = (
        ("driving_time_s", saved_result["driving_time_s"], replayed.driving_time_s, selected_tolerances.time_s),
        ("lap_time_s", saved_result["lap_times_s"][0], replayed.lap_times_s[0] if replayed.lap_times_s else replayed.driving_time_s, selected_tolerances.time_s),
        ("starting_speed_mps", saved_result["starting_speed_mps"], replayed.starting_speed_mps, selected_tolerances.speed_mps),
        ("ending_speed_mps", saved_result["ending_speed_mps"], replayed.ending_speed_mps, selected_tolerances.speed_mps),
        ("pack_energy_kwh", saved_result["pack_energy_kwh"], replayed.pack_energy_kwh, selected_tolerances.energy_kwh),
        ("final_state_of_charge", saved_result["final_state_of_charge"], replayed.final_state_of_charge, selected_tolerances.state_of_charge),
    )
    metrics = [
        _metric(name, _finite_number(expected, name), _finite_number(actual, name), tolerance)
        for name, expected, actual, tolerance in metric_specs
    ]
    saved_trace = payload["telemetry"]
    replayed_trace = replayed.telemetry
    if replayed_trace is not None and replayed_count:
        for name, expected, actual, tolerance in (
            ("sample_time_s", saved_trace["sample_time_s"], replayed_trace["vehicle.time_s"], selected_tolerances.time_s),
            ("sample_distance_m", saved_trace["sample_distance_m"], replayed_trace["vehicle.distance_m"], selected_tolerances.distance_m),
            ("speed_trace_mps", saved_trace["channels"]["vehicle.speed_mps"]["values"], replayed_trace["vehicle.speed_mps"], selected_tolerances.speed_mps),
            ("path_speed_ceiling_mps", saved_trace["channels"]["endurance.path_speed_ceiling_mps"]["values"], replayed_trace["endurance.path_speed_ceiling_mps"], selected_tolerances.speed_mps),
        ):
            metrics.append(_trace_metric(name, expected, actual, tolerance))
        for field in _CONTROL_FIELDS:
            name = f"controls.{field}"
            metrics.append(_trace_metric(
                name, saved_trace["channels"][name]["values"],
                replayed_trace[name], 0.0,
            ))
    else:
        reasons.append("Replay produced no accepted-cell telemetry")
    if any(not metric.passed for metric in metrics):
        reasons.append("One or more model outputs exceeded the declared tolerance")
    return LapReplayReport(
        run_id=record.run_id,
        model_agreement=not reasons,
        replay_completed=replayed.completed and replayed.completed_laps == 1,
        recorded_sample_count=track.cell_count,
        replayed_sample_count=replayed_count,
        metrics=tuple(metrics), mismatch_reasons=tuple(reasons),
        provenance_warnings=provenance_warnings,
    )


__all__ = [
    "LapReplayMetric", "LapReplayReport", "LapReplayTolerances",
    "replay_lap_record",
]
