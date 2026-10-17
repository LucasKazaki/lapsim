"""Actual native acceptance checks. Run explicitly inside the pinned Chrono environment.

No skips, mocks, rendering, or alternative physics backend are used here.
"""

import json
from dataclasses import asdict, replace
from pathlib import Path
from uuid import uuid4

import pytest

from lapsim.dynamics.chrono_vehicle import ChronoVehiclePlant
from lapsim.experiments.record_io import write_text_atomic
from lapsim.experiments.suspension_study import (
    StudyCancelled,
    SuspensionScenario,
    replay_study,
    run_study,
)


@pytest.fixture(scope="module")
def native_records():
    folder = Path("work/detailed-study/native-checks") / uuid4().hex
    folder.mkdir(parents=True, exist_ok=True)
    write_text_atomic(
        Path("work/detailed-study/latest-native-attempt.json"),
        json.dumps({"directory": folder.as_posix()}),
    )
    records = {}
    cases = {
        "settle": SuspensionScenario(scenario_id="settle"),
        "drive": SuspensionScenario(),
        "drive_half_step": SuspensionScenario(plant_step_s=0.00025),
        "drive_sparse_log": SuspensionScenario(logging_period_s=0.05),
        "steer_left": SuspensionScenario(scenario_id="steer"),
        "steer_right": SuspensionScenario(scenario_id="steer", steering=-0.06),
    }
    for name, scenario in cases.items():
        if (Path("work/detailed-study/STOP")).exists():
            raise StudyCancelled("Local coordinator stop marker is present")
        record = run_study(
            scenario, cancel=lambda: Path("work/detailed-study/STOP").exists()
        )
        write_text_atomic(
            folder / (name + ".json"), json.dumps(record, allow_nan=False)
        )
        records[name] = record
    return records


def test_gravity_equilibrium_and_static_left_right_symmetry(native_records):
    metrics = native_records["settle"]["payload"]["metrics"]
    assert metrics["settle_max_vertical_force_relative_error"] < 0.01
    assert metrics["settle_max_left_right_load_relative_difference"] < 0.01
    assert metrics["settle_max_vertical_speed_mps"] < 0.01
    assert metrics["settle_acceptance"]["passed"]


def test_positive_rear_drive_has_correct_authority_and_forward_response(native_records):
    drive = native_records["drive"]["payload"]
    settle = native_records["settle"]["payload"]
    final = drive["samples"][-1]
    assert final["velocity_mps"][0] > 0.4
    assert abs(settle["samples"][-1]["velocity_mps"][0]) < 0.01
    assert final["driveline_wheel_torque_nm"][:2] == (0.0, 0.0)
    assert all(torque > 0 for torque in final["driveline_wheel_torque_nm"][2:])
    assert all(omega > 0 for omega in final["wheel_omega_rad_s"])
    assert all(omega < 0 for omega in final["native_axle_shaft_omega_rad_s"])
    assert final["command"]["driveshaft_torque_nm"] == 40.0
    assert all(
        0 <= event["request"]["driveshaft_torque_nm"] <= 40
        for event in drive["commands"]
    )


def test_steering_sign_and_mirrored_yaw_response(native_records):
    left = native_records["steer_left"]["payload"]["metrics"]["final_heading_rad"]
    right = native_records["steer_right"]["payload"]["metrics"]["final_heading_rad"]
    assert left > 0
    assert right < 0
    assert left == pytest.approx(-right, rel=0.02, abs=1e-4)


def test_timestep_refinement_changes_small_physical_quantities_by_less_than_one_percent(
    native_records,
):
    coarse = native_records["drive"]["payload"]["samples"][-1]
    fine = native_records["drive_half_step"]["payload"]["samples"][-1]
    assert coarse["velocity_mps"][0] == pytest.approx(fine["velocity_mps"][0], rel=0.01)
    assert coarse["position_m"][2] == pytest.approx(fine["position_m"][2], abs=0.001)
    for left, right in zip(
        coarse["suspension_spring_length_m"], fine["suspension_spring_length_m"]
    ):
        assert left == pytest.approx(right, abs=0.001)


def test_logging_is_side_effect_free_and_does_not_change_the_physical_trace(
    native_records,
):
    dense = native_records["drive"]["payload"]
    sparse = native_records["drive_sparse_log"]["payload"]
    assert dense["commands"] == sparse["commands"]
    assert dense["samples"][-1] == sparse["samples"][-1]
    assert dense["metrics"] == sparse["metrics"]
    assert dense["metrics"]["settle_samples"] == 1001
    shared = {round(sample["time_s"], 8): sample for sample in dense["samples"]}
    for sample in sparse["samples"]:
        key = round(sample["time_s"], 8)
        if key in shared:
            assert sample == shared[key]


def test_force_and_tire_kinematics_timestamps_expose_cached_coupling(native_records):
    samples = native_records["drive"]["payload"]["samples"]
    assert samples[0]["tire_force_source_time_s"] is None
    assert samples[0]["applied_tire_force_source_time_s"] is None
    for sample in samples[1:]:
        assert sample["time_s"] - sample["tire_force_source_time_s"] == pytest.approx(
            0.0005
        )
        assert sample["time_s"] - sample[
            "applied_tire_force_geometry_time_s"
        ] == pytest.approx(0.0005)
        assert sample["time_s"] - sample[
            "applied_tire_force_source_time_s"
        ] == pytest.approx(0.001)
        assert (
            sample["tire_kinematics_source_time_s"]
            == sample["tire_force_source_time_s"]
        )


def test_reset_is_repeatable_and_observe_does_not_advance():
    plant = ChronoVehiclePlant()
    try:
        initial = asdict(plant.observe())
        assert asdict(plant.observe()) == initial
        for _ in range(10):
            plant.advance(0.001)
        plant.reset()
        assert asdict(plant.observe()) == initial
    finally:
        plant.close()


def test_native_tire_clock_matches_each_actual_plant_interval():
    plant = ChronoVehiclePlant()
    try:
        for step in (0.0005, 0.00025, 0.00075):
            plant.advance(step)
            # This reads the actual native tire setting used by its Dahl ODE,
            # independently of the public Advance argument or runner clock.
            assert all(tire.GetStepsize() == step for tire in plant._tires)
        assert plant.observe().time_s == pytest.approx(0.0015)
    finally:
        plant.close()


def test_native_record_replays_through_same_engine(native_records):
    record = native_records["drive"]
    replayed = replay_study(json.loads(json.dumps(record)))
    assert replayed["payload"]["model"] == record["payload"]["model"]
    assert replayed["execution"]["device"] == "CPU"
    assert replayed["execution"]["gpu_physics"] is False


def test_actual_cancel_cleans_up_and_does_not_poison_next_native_initialization():
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls > 8

    with pytest.raises(StudyCancelled):
        run_study(SuspensionScenario(), cancel=cancel)
    plant = ChronoVehiclePlant()
    try:
        assert plant.observe().time_s == 0.0
    finally:
        plant.close()


def test_insufficient_settle_is_rejected_before_maneuver():
    with pytest.raises(RuntimeError, match="not settled"):
        run_study(replace(SuspensionScenario(), settle_s=1.0))
