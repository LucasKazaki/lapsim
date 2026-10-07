"""Saved lap commands can be checked against the distance-domain model."""

from __future__ import annotations

from dataclasses import asdict, replace
from hashlib import sha256
import json
from math import pi
from pathlib import Path

import pytest

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Track
from lapsim.dynamics.conditions import PlanarRoad, RectangularGripPatch
from lapsim.experiments import (
    LapRunSettings, RunRecord, capture_lap_run, replay_lap_record,
)
from lapsim.profiles import build_vehicle
from lapsim.optimization.road_grip_schedule import (
    ROAD_GRIP_SCHEDULE_MAPPING_VERSION, world_patch_grip_schedule,
)
from lapsim.ui.simulation import (
    apply_uniform_road_grip, endurance_run_config, path_solver_settings, run_one_lap,
    run_speed_periodic_lap,
)


@pytest.fixture(scope="module")
def saved_laps(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    directory = tmp_path_factory.mktemp("lap_replay")
    track = SpatialTrack.from_track(
        Track.from_segments([Curve(25.0, 2.0 * pi)]),
        maximum_cell_length_m=5.0,
    )
    paths: dict[str, Path] = {}
    for profile_id in ("prius_2026_le", "repository_baseline"):
        vehicle, manifest = build_vehicle(profile_id)
        if profile_id == "prius_2026_le":
            periodic = run_speed_periodic_lap(
                vehicle, track, torque_request_fraction=0.8,
            )
            assert periodic.converged
            result = periodic.run
            config = replace(
                endurance_run_config(vehicle),
                starting_speed_mps=result.starting_speed_mps,
            )
            planning = {
                "mode": "experimental_racing_line",
                "lap_start_policy": "speed_only_periodic_fixed_initial_vehicle_state",
                "speed_seam_tolerance_mps": 0.005,
            }
        else:
            result = run_one_lap(vehicle, track, torque_request_fraction=0.8)
            config = endurance_run_config(vehicle)
            planning = None
        assert result.completed
        settings = LapRunSettings.from_track(
            track, track_id="short_closed_circle", solver_step_m=5.0,
            solver_settings=path_solver_settings(vehicle),
            torque_request_fraction=0.8,
            endurance_config=config,
            profile_id=profile_id, profile_label=profile_id,
            path_planning=planning,
        )
        record = capture_lap_run(result, manifest, settings, actual_vehicle=vehicle)
        paths[profile_id] = record.save(directory / f"{profile_id}.json")
    return paths


def _mutated_record(source: Path, target: Path, mutate) -> Path:
    payload = RunRecord.load(source).to_dict()
    mutate(payload)
    payload.pop("run_id")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    payload["run_id"] = sha256(canonical.encode("utf-8")).hexdigest()
    target.write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
    return target


def test_periodic_prius_record_replays_saved_cell_commands(saved_laps: dict[str, Path]) -> None:
    path = saved_laps["prius_2026_le"]
    record = RunRecord.load(path).to_dict()
    assert record["settings"]["endurance_config"]["starting_speed_mps"] == pytest.approx(
        record["result"]["starting_speed_mps"]
    )
    report = replay_lap_record(path)
    assert report.model_agreement
    assert report.replay_completed
    assert report.recorded_sample_count == report.replayed_sample_count
    assert report.recorded_sample_count == record["settings"]["track"]["cell_count"]
    assert all(metric.passed for metric in report.metrics)
    assert max(metric.maximum_absolute_error for metric in report.metrics) < 1e-9
    assert report.to_dict()["run_id"] == record["run_id"]


def test_plain_centerline_record_replays_without_explicit_start_speed(saved_laps: dict[str, Path]) -> None:
    path = saved_laps["repository_baseline"]
    record = RunRecord.load(path).to_dict()
    assert record["settings"]["endurance_config"]["starting_speed_mps"] is None
    report = replay_lap_record(path)
    assert report.model_agreement
    assert report.replayed_sample_count == report.recorded_sample_count


def test_assumed_grip_record_replays_with_same_profile_and_condition(tmp_path: Path) -> None:
    track = SpatialTrack.from_track(
        Track.from_segments([Curve(25.0, 2.0 * pi)]),
        maximum_cell_length_m=5.0,
    )
    vehicle, manifest = build_vehicle("repository_baseline")
    apply_uniform_road_grip(vehicle, 0.7)
    run = run_one_lap(vehicle, track, torque_request_fraction=0.8)
    assert run.completed, run.failure_reason
    settings = LapRunSettings.from_track(
        track, track_id="grip_sensitivity_circle", solver_step_m=5.0,
        solver_settings=path_solver_settings(vehicle),
        torque_request_fraction=0.8,
        endurance_config=endurance_run_config(vehicle),
        road_grip_multiplier=0.7,
        profile_id="repository_baseline",
    )
    path = capture_lap_run(
        run, manifest, settings, actual_vehicle=vehicle,
    ).save(tmp_path / "grip.json")
    payload = RunRecord.load(path).to_dict()
    assert payload["settings"]["conditions"]["road_grip_multiplier"] == 0.7
    assert payload["configuration"]["base_profile_manifest"]["model_config"]["fields"]["tire"]["fields"]["road_grip_multiplier"] == 1.0
    assert replay_lap_record(path).model_agreement


def test_world_patch_record_checks_geometry_and_grip_after_rehash(
    tmp_path: Path,
) -> None:
    track = SpatialTrack.from_track(
        Track.from_segments([Curve(25.0, 2.0 * pi)]),
        maximum_cell_length_m=5.0,
    )
    vehicle, manifest = build_vehicle("repository_baseline")
    road = PlanarRoad(patches=(RectangularGripPatch(
        -100.0, 100.0, -100.0, 100.0, 0.7,
    ),))
    schedule = world_patch_grip_schedule(track, vehicle, road)
    assert set(schedule) == {0.7}
    run = run_one_lap(
        vehicle, track, torque_request_fraction=0.8,
        cell_road_grip_multiplier=schedule,
    )
    assert run.completed, run.failure_reason
    settings = LapRunSettings.from_track(
        track, track_id="assumed_patch_circle", solver_step_m=5.0,
        solver_settings=path_solver_settings(vehicle),
        torque_request_fraction=0.8,
        endurance_config=endurance_run_config(vehicle),
        cell_road_grip_multiplier=schedule,
        path_planning={"road_condition": {
            "mode": "assumed_world_fixed_low_grip_rectangle",
            "mapping_version": ROAD_GRIP_SCHEDULE_MAPPING_VERSION,
            "base_material_id": road.base_material_id,
            "base_friction_multiplier": road.base_friction_multiplier,
            "patches": [asdict(patch) for patch in road.patches],
            "policy": "minimum_nominal_wheel_contact_grip_for_whole_cell",
            "contact_resolution_m": 0.01,
            "measured": False,
        }},
    )
    path = capture_lap_run(
        run, manifest, settings, actual_vehicle=vehicle,
    ).save(tmp_path / "world_patch.json")
    assert replay_lap_record(path).model_agreement

    changed_rectangle = _mutated_record(
        path, tmp_path / "changed_rectangle.json",
        lambda payload: payload["settings"]["path_planning"]["road_condition"]
        ["patches"][0].update(friction_multiplier=0.8),
    )
    with pytest.raises(ValueError, match="does not reproduce cell grip schedule"):
        replay_lap_record(changed_rectangle)

    overlapping_rectangle = _mutated_record(
        path, tmp_path / "overlapping_rectangle.json",
        lambda payload: payload["settings"]["path_planning"]["road_condition"]
        ["patches"].append(dict(
            payload["settings"]["path_planning"]["road_condition"]["patches"][0],
            friction_multiplier=0.3,
        )),
    )
    with pytest.raises(ValueError, match="overlapping patches"):
        replay_lap_record(overlapping_rectangle)

    claimed_uniform = _mutated_record(
        path, tmp_path / "claimed_uniform.json",
        lambda payload: (
            payload["settings"].update(conditions={
                "road_grip_multiplier": 1.0,
                "source": "assumed_uniform_surface_sensitivity",
            }),
            payload["settings"]["path_planning"].update(
                road_condition={"mode": "assumed_uniform_surface"},
            ),
        ),
    )
    with pytest.raises(ValueError, match="saved tire grip telemetry disagrees"):
        replay_lap_record(claimed_uniform)


@pytest.mark.parametrize("periodic", [False, True])
def test_cell_grip_record_replays_exact_saved_schedule(
    tmp_path: Path, periodic: bool,
) -> None:
    track = SpatialTrack.from_track(
        Track.from_segments([Curve(25.0, 2.0 * pi)]),
        maximum_cell_length_m=5.0,
    )
    schedule = tuple(0.7 if 8 <= i < 12 else 1.0 for i in range(track.cell_count))
    vehicle, manifest = build_vehicle("repository_baseline")
    if periodic:
        periodic_result = run_speed_periodic_lap(
            vehicle, track, torque_request_fraction=0.8,
            cell_road_grip_multiplier=schedule,
        )
        assert periodic_result.converged, periodic_result.failure_reason
        run = periodic_result.run
        actual_vehicle = periodic_result.vehicle
        config = replace(
            endurance_run_config(actual_vehicle),
            starting_speed_mps=run.starting_speed_mps,
        )
        planning = {
            "mode": "experimental_racing_line",
            "lap_start_policy": "speed_only_periodic_fixed_initial_vehicle_state",
        }
    else:
        run = run_one_lap(
            vehicle, track, torque_request_fraction=0.8,
            cell_road_grip_multiplier=schedule,
        )
        actual_vehicle = vehicle
        config = endurance_run_config(vehicle)
        planning = None
    assert run.completed, run.failure_reason
    assert run.telemetry is not None
    assert run.telemetry["tire.road_grip_multiplier"] == schedule
    assert actual_vehicle.tire.road_grip_multiplier == 1.0
    settings = LapRunSettings.from_track(
        track, track_id="cell_grip_circle", solver_step_m=5.0,
        solver_settings=path_solver_settings(actual_vehicle),
        torque_request_fraction=0.8, endurance_config=config,
        cell_road_grip_multiplier=schedule,
        path_planning=planning,
    )
    path = capture_lap_run(
        run, manifest, settings, actual_vehicle=actual_vehicle,
    ).save(tmp_path / "cell_grip.json")
    payload = RunRecord.load(path).to_dict()
    assert payload["schema_version"] == 2
    assert payload["settings"]["conditions"] == {
        "road_grip_multiplier": 1.0,
        "source": "assumed_cellwise_surface_sensitivity",
        "cell_road_grip_multiplier": list(schedule),
    }
    report = replay_lap_record(path)
    assert report.model_agreement, report.mismatch_reasons
    assert report.replay_completed
    assert any(
        metric.name == "tire.road_grip_multiplier"
        and metric.passed and metric.maximum_absolute_error == 0.0
        for metric in report.metrics
    )


def test_cell_grip_capture_rejects_settings_that_differ_from_run() -> None:
    track = SpatialTrack.from_track(
        Track.from_segments([Curve(25.0, 2.0 * pi)]),
        maximum_cell_length_m=5.0,
    )
    vehicle, manifest = build_vehicle("repository_baseline")
    run = run_one_lap(vehicle, track, torque_request_fraction=0.8)
    assert run.completed
    schedule = tuple(0.7 if i == 8 else 1.0 for i in range(track.cell_count))
    settings = LapRunSettings.from_track(
        track, track_id="cell_grip_circle", solver_step_m=5.0,
        solver_settings=path_solver_settings(vehicle),
        torque_request_fraction=0.8,
        endurance_config=endurance_run_config(vehicle),
        cell_road_grip_multiplier=schedule,
    )
    with pytest.raises(ValueError, match="saved tire grip telemetry disagrees"):
        capture_lap_run(run, manifest, settings, actual_vehicle=vehicle)


@pytest.mark.parametrize("mutation", [
    lambda conditions: conditions["cell_road_grip_multiplier"].pop(),
    lambda conditions: conditions["cell_road_grip_multiplier"].__setitem__(0, False),
    lambda conditions: conditions["cell_road_grip_multiplier"].__setitem__(0, 0.0),
    lambda conditions: conditions.__setitem__("source", "unknown"),
    lambda conditions: conditions.__setitem__("cell_road_grip_multiplier", None),
])
def test_rehashed_malformed_cell_grip_is_rejected_on_load(
    saved_laps: dict[str, Path], tmp_path: Path, mutation,
) -> None:
    def alter(payload: dict) -> None:
        count = payload["settings"]["track"]["cell_count"]
        conditions = payload["settings"]["conditions"]
        conditions["source"] = "assumed_cellwise_surface_sensitivity"
        conditions["cell_road_grip_multiplier"] = [1.0] * count
        mutation(conditions)

    path = _mutated_record(
        saved_laps["repository_baseline"], tmp_path / "bad_cell_grip.json", alter,
    )
    with pytest.raises(ValueError, match="cell road grip|saved run conditions"):
        RunRecord.load(path)


def test_rehashed_valid_cell_grip_conflicting_with_trace_is_rejected_before_replay(
    saved_laps: dict[str, Path], tmp_path: Path,
) -> None:
    def add_schedule(payload: dict) -> None:
        count = payload["settings"]["track"]["cell_count"]
        conditions = payload["settings"]["conditions"]
        conditions["source"] = "assumed_cellwise_surface_sensitivity"
        conditions["cell_road_grip_multiplier"] = [1.0] * count
        conditions["cell_road_grip_multiplier"][8] = 0.7

    path = _mutated_record(
        saved_laps["repository_baseline"], tmp_path / "false_cell_grip.json", add_schedule,
    )
    assert RunRecord.load(path).to_dict()["settings"]["conditions"][
        "cell_road_grip_multiplier"
    ][8] == 0.7
    with pytest.raises(ValueError, match="saved tire grip telemetry disagrees"):
        replay_lap_record(path)


def test_old_v2_tire_snapshot_replays_with_original_default_grip(
    saved_laps: dict[str, Path], tmp_path: Path,
) -> None:
    def remove_new_field(payload: dict) -> None:
        configuration = payload["configuration"]
        configuration["effective_vehicle_config"]["fields"]["tire"]["fields"].pop(
            "road_grip_multiplier"
        )
        configuration["base_profile_manifest"]["model_config"]["fields"]["tire"]["fields"].pop(
            "road_grip_multiplier"
        )
        payload["settings"].pop("conditions")
        snapshot = configuration["effective_vehicle_config"]
        configuration["effective_vehicle_config_sha256"] = sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()

    path = _mutated_record(
        saved_laps["prius_2026_le"], tmp_path / "prior_v2.json", remove_new_field,
    )
    assert replay_lap_record(path).model_agreement


def test_replay_rejects_condition_snapshot_mismatch(
    saved_laps: dict[str, Path], tmp_path: Path,
) -> None:
    path = _mutated_record(
        saved_laps["prius_2026_le"], tmp_path / "mismatch.json",
        lambda payload: payload["settings"]["conditions"].__setitem__(
            "road_grip_multiplier", 0.7,
        ),
    )
    with pytest.raises(ValueError, match="road-grip setting disagrees"):
        replay_lap_record(path)


def test_replay_rejects_explicit_null_conditions_in_new_record(
    saved_laps: dict[str, Path], tmp_path: Path,
) -> None:
    path = _mutated_record(
        saved_laps["prius_2026_le"], tmp_path / "null_conditions.json",
        lambda payload: payload["settings"].__setitem__("conditions", None),
    )
    with pytest.raises(ValueError, match="saved run conditions are invalid"):
        replay_lap_record(path)


@pytest.mark.parametrize("field", [
    "controls.steering_angle_rad", "controls.front_brake_pressure_psi",
    "controls.rear_brake_pressure_psi",
    "controls.motor_torque_request_nm",
    "controls.front_regenerative_brake_force_request_n",
    "controls.rear_regenerative_brake_force_request_n",
])
def test_missing_recorded_command_is_rejected(
    saved_laps: dict[str, Path], tmp_path: Path, field: str,
) -> None:
    path = _mutated_record(
        saved_laps["prius_2026_le"], tmp_path / "missing.json",
        lambda payload: payload["telemetry"]["channels"].pop(field),
    )
    with pytest.raises(ValueError, match="complete controls"):
        replay_lap_record(path)


def test_misaligned_cell_distance_is_rejected(saved_laps: dict[str, Path], tmp_path: Path) -> None:
    path = _mutated_record(
        saved_laps["prius_2026_le"], tmp_path / "misaligned.json",
        lambda payload: payload["telemetry"]["sample_distance_m"].__setitem__(1, 99.0),
    )
    with pytest.raises(ValueError, match="do not align with cells"):
        replay_lap_record(path)


def test_unknown_snapshot_class_is_rejected(saved_laps: dict[str, Path], tmp_path: Path) -> None:
    def mutate(payload: dict) -> None:
        snapshot = payload["configuration"]["effective_vehicle_config"]
        snapshot["fields"]["aero"]["class"] = "ExternalAero"
        canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
        payload["configuration"]["effective_vehicle_config_sha256"] = sha256(
            canonical.encode("utf-8")
        ).hexdigest()

    path = _mutated_record(saved_laps["prius_2026_le"], tmp_path / "unknown.json", mutate)
    with pytest.raises(ValueError, match="unsupported model class"):
        replay_lap_record(path)


def test_failed_and_v1_records_are_not_command_replayable(
    saved_laps: dict[str, Path], tmp_path: Path,
) -> None:
    def make_failed(payload: dict) -> None:
        payload["result"]["status"] = "failed"
        payload["result"]["completed_laps"] = 0

    failed = _mutated_record(saved_laps["prius_2026_le"], tmp_path / "failed.json", make_failed)
    with pytest.raises(ValueError, match="only completed"):
        replay_lap_record(failed)

    def make_v1(payload: dict) -> None:
        payload["schema_version"] = 1
        payload["settings"]["track"].pop("geometry")

    legacy = _mutated_record(saved_laps["prius_2026_le"], tmp_path / "legacy.json", make_v1)
    with pytest.raises(ValueError, match="only v2"):
        replay_lap_record(legacy)


def test_numerical_disagreement_is_reported_separately_from_provenance(
    saved_laps: dict[str, Path], tmp_path: Path,
) -> None:
    def mutate(payload: dict) -> None:
        payload["result"]["driving_time_s"] += 0.1
        payload["configuration"]["base_profile_manifest"]["code_commit"] = "0" * 40

    path = _mutated_record(saved_laps["prius_2026_le"], tmp_path / "bad_result.json", mutate)
    report = replay_lap_record(path)
    assert not report.model_agreement
    assert report.replay_completed
    assert any(metric.name == "driving_time_s" and not metric.passed for metric in report.metrics)
    assert any("commit differs" in warning for warning in report.provenance_warnings)


def test_changed_recorded_commands_fail_numerical_agreement(
    saved_laps: dict[str, Path], tmp_path: Path,
) -> None:
    def mutate(payload: dict) -> None:
        channel = payload["telemetry"]["channels"]["controls.motor_torque_request_nm"]
        channel["values"] = [0.0] * len(channel["values"])

    path = _mutated_record(
        saved_laps["prius_2026_le"], tmp_path / "changed_controls.json", mutate,
    )
    report = replay_lap_record(path)
    assert not report.model_agreement
    assert report.mismatch_reasons


def test_off_path_recorded_steering_fails_model_replay(
    saved_laps: dict[str, Path], tmp_path: Path,
) -> None:
    def mutate(payload: dict) -> None:
        payload["telemetry"]["channels"]["controls.steering_angle_rad"]["values"][0] = 0.0

    path = _mutated_record(
        saved_laps["prius_2026_le"], tmp_path / "off_path_steering.json", mutate,
    )
    report = replay_lap_record(path)
    assert not report.model_agreement
    assert not report.replay_completed
    assert report.replayed_sample_count == 0
    assert any("did not complete" in reason for reason in report.mismatch_reasons)


def test_first_cell_model_failure_returns_a_structured_mismatch(
    saved_laps: dict[str, Path], tmp_path: Path,
) -> None:
    def mutate(payload: dict) -> None:
        channels = payload["telemetry"]["channels"]
        # The Prius model drives the front axle; a rear regen command makes
        # its first model step fail before any telemetry can be accepted.
        channels["controls.motor_torque_request_nm"]["values"][0] = 0.0
        channels["controls.rear_regenerative_brake_force_request_n"]["values"][0] = 1.0

    path = _mutated_record(
        saved_laps["prius_2026_le"], tmp_path / "first_cell_failure.json", mutate,
    )
    report = replay_lap_record(path)
    assert not report.model_agreement
    assert not report.replay_completed
    assert report.replayed_sample_count == 0
    assert any("did not complete" in reason for reason in report.mismatch_reasons)


def test_speed_periodic_record_requires_its_explicit_start(
    saved_laps: dict[str, Path], tmp_path: Path,
) -> None:
    path = _mutated_record(
        saved_laps["prius_2026_le"], tmp_path / "no_start.json",
        lambda payload: payload["settings"]["endurance_config"].__setitem__(
            "starting_speed_mps", None,
        ),
    )
    with pytest.raises(ValueError, match="explicit start speed"):
        replay_lap_record(path)


@pytest.mark.parametrize(("missing_path", "message"), [
    (("result",), "saved result must be an object"),
    (("configuration",), "saved configuration must be an object"),
    (("configuration", "effective_vehicle_config"), "effective vehicle configuration"),
    (("configuration", "base_profile_manifest"), "base profile manifest"),
    (("telemetry",), "saved telemetry must be an object"),
    (("settings", "solver"), "saved solver must be an object"),
    (("settings", "solver", "path_constraint_settings"), "path constraint settings"),
    (("settings", "endurance_config"), "endurance configuration"),
    (("runtime",), "saved runtime must be an object"),
    (("result", "driving_time_s"), "missing driving_time_s"),
    (("result", "pack_energy_kwh"), "missing pack_energy_kwh"),
    (("result", "final_state_of_charge"), "missing final_state_of_charge"),
])
def test_rehashed_record_with_missing_replay_field_has_clear_error(
    saved_laps: dict[str, Path], tmp_path: Path,
    missing_path: tuple[str, ...], message: str,
) -> None:
    def mutate(payload: dict) -> None:
        parent = payload
        for part in missing_path[:-1]:
            parent = parent[part]
        parent.pop(missing_path[-1])

    path = _mutated_record(
        saved_laps["prius_2026_le"], tmp_path / "missing_replay_field.json", mutate,
    )
    with pytest.raises(ValueError, match=message):
        replay_lap_record(path)


@pytest.mark.parametrize(("field_path", "replacement", "message"), [
    (("result", "lap_times_s"), [], "exactly one lap time"),
    (("result", "driving_time_s"), "invalid", "driving_time_s must be a finite number"),
    (("settings", "path_planning"), None, "path planning settings"),
    (("settings", "endurance_config"), None, "endurance configuration"),
    (("settings", "solver", "path_constraint_settings"), None, "path constraint settings"),
])
def test_rehashed_record_with_malformed_replay_field_has_clear_error(
    saved_laps: dict[str, Path], tmp_path: Path,
    field_path: tuple[str, ...], replacement: object, message: str,
) -> None:
    def mutate(payload: dict) -> None:
        parent = payload
        for part in field_path[:-1]:
            parent = parent[part]
        parent[field_path[-1]] = replacement

    path = _mutated_record(
        saved_laps["prius_2026_le"], tmp_path / "bad_replay_field.json", mutate,
    )
    with pytest.raises(ValueError, match=message):
        replay_lap_record(path)
