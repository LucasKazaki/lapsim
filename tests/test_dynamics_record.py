"""Persistence and integrity checks for independent-wheel A/B records."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from importlib.metadata import version as distribution_version
import json
from math import pi
from pathlib import Path
import platform

import pytest

from lapsim.dynamics import (
    PlanarControls,
    PlanarEnvironment,
    PlanarRoad,
    PlanarState,
    PlanarVehicleConfig,
    RoadDomain,
    run_planar_dynamics,
)
from lapsim.experiments.dynamics_record import (
    DYNAMICS_RECORD_SCHEMA_VERSION,
    DynamicsComparisonRecord,
    capture_dynamics_comparison,
    default_dynamics_run_directory,
)


def _example(*, road: PlanarRoad | None = None):
    config = PlanarVehicleConfig(
        mass_kg=300.0,
        yaw_inertia_kgm2=160.0,
        cg_to_front_axle_m=0.8,
        cg_to_rear_axle_m=0.8,
        front_track_m=1.2,
        rear_track_m=1.2,
        wheel_radius_m=0.2,
        wheel_inertia_kgm2=0.3,
        tire_mu=1.5,
        longitudinal_stiffness_n_per_slip=7_000.0,
        cornering_stiffness_n_per_rad=8_000.0,
    )
    environment = PlanarEnvironment(road=road or PlanarRoad())
    initial = PlanarState(u_mps=5.0, wheel_speeds_rad_s=(25.0,) * 4)
    controls_a = (PlanarControls(drive_torques_nm=(0.0, 0.0, 10.0, 10.0)),) * 2
    controls_b = (PlanarControls(drive_torques_nm=(0.0, 0.0, 8.0, 12.0)),) * 2
    step = 0.01
    run_a = run_planar_dynamics(config, initial, controls_a, step, environment=environment)
    run_b = run_planar_dynamics(config, initial, controls_b, step, environment=environment)
    return dict(
        config=config, environment=environment, initial_state=initial,
        controls_a=controls_a, controls_b=controls_b, output_step_s=step,
        run_a=run_a, run_b=run_b, equal_total_required=True,
    )


def _write_rehashed(path: Path, payload: dict) -> None:
    contents = dict(payload)
    contents.pop("run_id", None)
    canonical = json.dumps(contents, sort_keys=True, separators=(",", ":"), allow_nan=False)
    contents["run_id"] = sha256(canonical.encode("utf-8")).hexdigest()
    path.write_text(json.dumps(contents, allow_nan=False), encoding="utf-8")


def test_record_is_deterministic_complete_and_round_trips(tmp_path: Path) -> None:
    example = _example()
    first = capture_dynamics_comparison(**example)
    second = capture_dynamics_comparison(**example)
    assert first.run_id == second.run_id
    payload = first.to_dict()
    assert payload["schema_version"] == DYNAMICS_RECORD_SCHEMA_VERSION
    assert payload["record_type"] == "four_wheel_ab_comparison"
    assert payload["inputs"]["vehicle_config"]["mass_kg"] == 300.0
    assert payload["inputs"]["environment"]["road"]["base_friction_multiplier"] == 1.0
    assert len(payload["inputs"]["controls"]["A"]) == 2
    assert payload["runs"]["A"]["times_s"] == [0.0, 0.01, 0.02]
    assert len(payload["runs"]["A"]["states"]) == 3
    assert len(payload["runs"]["A"]["evaluations"]) == 2
    assert len(payload["runs"]["B"]["evaluations"][0]["wheels"]) == 4
    assert payload["runs"]["B"]["evaluations"][0]["wheels"][0]["road_valid"]
    assert payload["runs"]["A"]["max_abs_equation_residuals"]["mechanical_power_w"] < 1e-8
    assert payload["validity"]["both_runs_within_declared_road_domain"]
    assert payload["runtime"]["python"]["version"] == platform.python_version()
    for package in ("numpy", "scipy", "matplotlib"):
        assert payload["runtime"]["dependencies"][package] == distribution_version(package)
    saved = first.save(tmp_path / "run.json")
    assert DynamicsComparisonRecord.load(saved).to_dict() == payload
    assert not list(tmp_path.glob("*.tmp"))


def test_equal_total_and_alignment_are_checked() -> None:
    example = _example()
    bad_commands = list(example["controls_b"])
    bad_commands[1] = replace(bad_commands[1], drive_torques_nm=(0.0, 0.0, 8.0, 13.0))
    with pytest.raises(ValueError, match="equal total wheel torque"):
        capture_dynamics_comparison(**(example | {"controls_b": tuple(bad_commands)}))
    with pytest.raises(ValueError, match="aligned"):
        capture_dynamics_comparison(**(
            example | {"initial_state": PlanarState()}
        ))


def test_outside_road_domain_remains_visible_and_unvalidated() -> None:
    narrow_road = PlanarRoad(valid_domain=RoadDomain(-0.5, 0.5, -0.5, 0.5))
    record = capture_dynamics_comparison(**_example(road=narrow_road))
    payload = record.to_dict()
    assert not payload["validity"]["both_runs_within_declared_road_domain"]
    assert payload["runs"]["A"]["invalid_road_queries"] > 0
    assert not payload["runs"]["A"]["evaluations"][0]["road_valid"]
    assert not payload["runs"]["A"]["evaluations"][0]["wheels"][0]["road_valid"]


def test_capture_rejects_outputs_from_different_inputs_and_false_road_summary() -> None:
    example = _example()
    with pytest.raises(ValueError, match="disagrees with its frozen inputs"):
        capture_dynamics_comparison(**(
            example | {"environment": PlanarEnvironment(drag_area_m2=10.0)}
        ))
    changed_controls = (
        replace(example["controls_a"][0], drive_torques_nm=(0.0, 0.0, 11.0, 9.0)),
        example["controls_a"][1],
    )
    with pytest.raises(ValueError, match="disagrees with its frozen inputs"):
        capture_dynamics_comparison(**(
            example | {"controls_a": changed_controls}
        ))
    outside = _example(road=PlanarRoad(
        valid_domain=RoadDomain(-0.5, 0.5, -0.5, 0.5),
    ))
    assert outside["run_a"].invalid_road_queries > 0
    forged_run = replace(outside["run_a"], road_valid=True, invalid_road_queries=0)
    with pytest.raises(ValueError, match="omits invalid road queries"):
        capture_dynamics_comparison(**(outside | {"run_a": forged_run}))


def test_rk_stage_only_road_violation_cannot_be_marked_valid(tmp_path: Path) -> None:
    config = replace(_example()["config"], tire_mu=1e-9)
    environment = PlanarEnvironment(
        road=PlanarRoad(valid_domain=RoadDomain(-0.9, 0.9, -0.7, 0.7)),
    )
    initial = PlanarState(yaw_rate_rad_s=2 * pi / 0.01)
    controls = (PlanarControls(),)
    run = run_planar_dynamics(
        config, initial, controls, 0.01, environment=environment,
    )
    assert run.evaluations[0].road_valid
    assert not run.road_valid
    inputs = dict(
        config=config, environment=environment, initial_state=initial,
        controls_a=controls, controls_b=controls, output_step_s=0.01,
        run_a=run, run_b=run, equal_total_required=True,
    )
    record = capture_dynamics_comparison(**inputs)
    forged_run = replace(run, road_valid=True, invalid_road_queries=0)
    with pytest.raises(ValueError, match="deterministic replay"):
        capture_dynamics_comparison(**(inputs | {"run_a": forged_run}))
    payload = record.to_dict()
    for label in ("A", "B"):
        payload["runs"][label]["road_valid"] = True
        payload["runs"][label]["invalid_road_queries"] = 0
    payload["validity"]["both_runs_within_declared_road_domain"] = True
    path = tmp_path / "forged.json"
    _write_rehashed(path, payload)
    with pytest.raises(ValueError, match="deterministic replay"):
        DynamicsComparisonRecord.load(path)


def test_load_detects_tampering_and_inconsistent_rehashed_payload(tmp_path: Path) -> None:
    record = capture_dynamics_comparison(**_example())
    path = record.save(tmp_path / "run.json")
    contents = json.loads(path.read_text(encoding="utf-8"))
    contents["runs"]["A"]["states"][1]["x_m"] += 1.0
    path.write_text(json.dumps(contents), encoding="utf-8")
    with pytest.raises(ValueError, match="content hash"):
        DynamicsComparisonRecord.load(path)
    contents = record.to_dict()
    contents["runs"]["B"]["times_s"][1] = 1.0
    _write_rehashed(path, contents)
    with pytest.raises(ValueError, match="inconsistent times"):
        DynamicsComparisonRecord.load(path)
    contents = record.to_dict()
    contents["runs"]["A"]["evaluations"][0]["total_body_force_x_n"] += 1.0
    _write_rehashed(path, contents)
    with pytest.raises(ValueError, match="disagrees with inputs|residuals disagree"):
        DynamicsComparisonRecord.load(path)
    contents = record.to_dict()
    contents["inputs"]["controls"]["B"][0]["drive_torques_nm"][3] += 1.0
    _write_rehashed(path, contents)
    with pytest.raises(ValueError, match="unequal A/B torque"):
        DynamicsComparisonRecord.load(path)
    contents = record.to_dict()
    contents["inputs"]["environment"]["drag_area_m2"] = 10.0
    _write_rehashed(path, contents)
    with pytest.raises(ValueError, match="disagrees with inputs"):
        DynamicsComparisonRecord.load(path)


def test_default_storage_is_outside_checkout() -> None:
    destination = default_dynamics_run_directory()
    assert destination.parts[-2:] == ("LapSim", "dynamics_runs")
