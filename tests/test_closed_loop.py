"""Frozen TC scenario observations through the actual causal controller loop."""

from copy import deepcopy
from dataclasses import replace
import json

import pytest

from lapsim.dynamics.conditions import (
    PlanarEnvironment,
    PlanarRoad,
    RectangularGripPatch,
)
from lapsim.dynamics.planar import PlanarState
from lapsim.experiments.closed_loop import (
    ClosedLoopScenario,
    DriverPoint,
    replay_closed_loop,
    run_closed_loop,
)
from lapsim.experiments.dynamics_record import _content_id


def scenario(duration=200_000, speed=0, steer=0, **kwargs):
    return ClosedLoopScenario(
        duration_us=duration,
        initial_state=PlanarState(u_mps=speed, wheel_speeds_rad_s=(speed / 0.2,) * 4),
        driver=(
            DriverPoint(0, 0.2, steering_rad=steer),
            DriverPoint(duration, 0.8, steering_rad=steer),
        ),
        **kwargs,
    )


@pytest.mark.parametrize("field", ["x_m", "u_mps", "v_mps", "yaw_rate_rad_s"])
def test_scenario_rejects_boolean_initial_physics(field):
    with pytest.raises(ValueError, match="ordinary|boolean|finite"):
        replace(scenario(), initial_state=PlanarState(**{field: True}))


def test_scenario_rejects_boolean_wheel_or_road_physics():
    with pytest.raises(ValueError, match="ordinary|boolean|finite"):
        replace(scenario(), initial_state=PlanarState(wheel_speeds_rad_s=(False, 0, 0, 0)))
    with pytest.raises(ValueError, match="ordinary|boolean|finite"):
        scenario(environment=PlanarEnvironment(road=PlanarRoad(base_friction_multiplier=True)))


def test_tc_s01_launch_has_causal_snapshot_and_distinct_requested_guarded_actual_contact_stages():
    # Exercise an intentionally infeasible pedal envelope so the allocation
    # stage must differ from the aggregate request, even after slew settles.
    record = run_closed_loop(scenario(maximum_driver_request_nm=1000))
    result = record["result"]
    events = result["controller_events"]
    observations = result["observations"]
    assert result["controller_calls"] == 20 and result["plant_ticks"] == 200
    assert events[0]["snapshot"] is None
    assert not events[0]["core"]["command_allowed"]
    assert all(
        e["snapshot"] is None or e["snapshot"]["timestamp_us"] <= e["time_us"] - 10_000
        for e in events
    )
    assert result["final_state"]["plant"]["u_mps"] > 0
    assert events[-1]["requested_propulsive_nm"] > sum(
        events[-1]["core"]["guard"]["output_nm"]
    )
    assert (
        observations[-1]["actual_actuator"]["wheel_torques_nm"][2]
        != observations[-1]["limited_command_nm"][2]
    )
    achieved = observations[-1]["plant"]["wheels"][2]["local_force_x_n"]
    assert achieved != pytest.approx(
        observations[-1]["actual_actuator"]["wheel_torques_nm"][2] / 0.2, rel=1e-3
    )
    assert abs(result["energy_balance_residual_j"]) < 1e-5


def test_tc_s02_s03_mirrored_corner_exit_swaps_wheels_and_yaw_sign():
    left = run_closed_loop(scenario(speed=5, steer=0.06))["result"]
    right = run_closed_loop(scenario(speed=5, steer=-0.06))["result"]
    a = left["final_state"]["plant"]
    b = right["final_state"]["plant"]
    for key in ("x_m", "u_mps"):
        assert a[key] == pytest.approx(b[key], abs=1e-8)
    for key in ("y_m", "v_mps", "yaw_rate_rad_s", "heading_rad"):
        assert a[key] == pytest.approx(-b[key], abs=1e-8)
    assert a["wheel_speeds_rad_s"] == pytest.approx(
        [b["wheel_speeds_rad_s"][i] for i in (1, 0, 3, 2)], abs=1e-8
    )


@pytest.mark.parametrize("steer", [0, .06])
def test_tc_s04_split_grip_strategy_uses_same_inputs_and_bounded_shared_power(steer):
    env = PlanarEnvironment(
        road=PlanarRoad(patches=(RectangularGripPatch(-100, 100, 0, 100, 0.2),))
    )
    base = scenario(duration=300_000, speed=3, steer=steer, environment=env)
    equal = run_closed_loop(base)
    traction = run_closed_loop(replace(base, strategy="traction_limited"))
    assert equal["scenario"]["driver"] == traction["scenario"]["driver"]
    assert equal["result"]["controller_calls"] == traction["result"]["controller_calls"]
    assert equal["result"]["final_state"] != traction["result"]["final_state"]
    for record in (equal, traction):
        for row in record["result"]["observations"]:
            assert abs(row["actual_actuator"]["pack_power_w"]) <= 25_000 + 1e-8
            assert row["actual_actuator"]["wheel_torques_nm"][:2] == (0, 0)


def test_tc_s05_actuator_loss_removes_actual_and_limited_authority_immediately():
    record = run_closed_loop(scenario(failed_rear_index=2, failure_time_us=100_000))
    for row in record["result"]["observations"]:
        if row["time_us"] >= 100_000:
            assert row["actual_actuator"]["wheel_torques_nm"][2] == 0
    for row in record["result"]["controller_events"]:
        if row["time_us"] >= 100_000:
            assert row["limited_command_nm"][2] == 0


def test_tc_s06_speed_cutoff_is_physical_even_before_sensor_feedback():
    record = run_closed_loop(scenario(speed=36))
    assert all(
        row["actual_actuator"]["wheel_torques_nm"] == (0,) * 4
        for row in record["result"]["observations"]
    )
    assert record["result"]["pack_draw_j"] == 0


def test_tc_s07_empty_full_regen_and_independent_friction_braking():
    empty = run_closed_loop(scenario(initial_soc=0))["result"]
    assert empty["final_state"]["pack_energy_j"] == 0
    assert empty["final_state"]["plant"]["u_mps"] == 0
    program = (
        DriverPoint(0, brake_fraction=0.2),
        DriverPoint(100_000, brake_fraction=0.2),
    )
    base = scenario(duration=100_000, speed=10)
    full = run_closed_loop(replace(base, initial_soc=1, driver=program))["result"]
    charge = run_closed_loop(replace(base, initial_soc=0.5, driver=program))["result"]
    assert full["pack_draw_j"] == 0 and charge["pack_draw_j"] < 0
    assert full["final_state"]["friction_brake_work_j"] < 0
    assert full["final_state"]["plant"]["u_mps"] < 10


def test_tc_s08_overlap_retains_raw_proposal_inhibits_and_requires_low_pedal_clear():
    program = (
        DriverPoint(0, 0.5),
        DriverPoint(60_000, 0.5, 0.2),
        DriverPoint(100_000, 0),
        DriverPoint(140_000, 0),
        DriverPoint(200_000, 0.5),
    )
    result = run_closed_loop(replace(scenario(), driver=program))["result"]
    tripped = [
        row
        for row in result["controller_events"]
        if row["core"]["guard"]["pedal_overlap_latched"]
    ]
    assert tripped and any(
        sum(row["core"]["allocator"]["wheel_torque_nm"]) > 0 for row in tripped
    )
    assert all(row["core"]["command_nm"] == [0, 0, 0, 0] for row in tripped)
    assert result["controller_events"][-1]["core"]["command_allowed"]


def test_tc_s08_stale_sensor_never_reuses_an_allowed_propulsive_command():
    result = run_closed_loop(scenario(dropped_sequences=tuple(range(3, 100))))["result"]
    stale = [row for row in result["controller_events"] if row["time_us"] >= 90_000]
    assert stale and all(not row["core"]["command_allowed"] for row in stale)
    assert all(row["core"]["allocator"]["fault"] == "stale_input" for row in stale)
    assert all(row["actual_actuator"]["wheel_torques_nm"] == (0.,)*4
               for row in result["observations"] if row["time_us"] >= 90_000)


def test_tc_s08_invalid_driver_sample_inhibits_actual_torque_after_its_arrival():
    base = scenario()
    program = (DriverPoint(0, .5), DriverPoint(50_000, .5, valid=False),
               DriverPoint(200_000, .5, valid=False))
    result = run_closed_loop(replace(base, driver=program))["result"]
    late = [e for e in result["controller_events"] if e["time_us"] >= 60_000]
    assert late and all(not e["core"]["command_allowed"] for e in late)
    assert all(row["actual_actuator"]["wheel_torques_nm"] == (0.,)*4
               for row in result["observations"] if row["time_us"] >= 60_000)


def test_tc_s09_delay_duplicate_order_and_restart_preserve_causality():
    result = run_closed_loop(
        scenario(
            sensor_delay_us=0,
            duplicate_sequences=(2,),
            extra_delays_us=((0, 30_000), (4, 80_000)),
            restart_times_us=(80_000,),
        )
    )["result"]
    reasons = {
        row["reason"] for row in result["sensor_arrivals"] if not row["accepted"]
    }
    assert "out_of_order_or_duplicate" in reasons and "wrong_epoch" in reasons
    assert all(
        row["source_us"] <= row["arrival_us"] for row in result["sensor_arrivals"]
    )
    restarted = [
        row for row in result["controller_events"] if row["time_us"] == 80_000
    ][0]
    assert restarted["core"]["restart_requested"]
    assert restarted["core"]["fault"]["generation"] == 1


def test_tc_s10_refinement_changes_plant_step_without_changing_control_clock():
    base = scenario(speed=5)
    coarse = run_closed_loop(base)["result"]
    fine = run_closed_loop(replace(base, plant_step_us=500))["result"]
    assert coarse["controller_calls"] == fine["controller_calls"] == 20
    assert coarse["plant_ticks"] == 200 and fine["plant_ticks"] == 400
    assert coarse["final_state"]["plant"]["u_mps"] == pytest.approx(
        fine["final_state"]["plant"]["u_mps"], abs=1e-5
    )


def test_tc_s10_controller_period_sweep_is_separate_sampling_sensitivity():
    base = scenario()
    fast = run_closed_loop(base)["result"]
    slow = run_closed_loop(replace(base, controller_period_us=20_000))["result"]
    assert fast["plant_ticks"] == slow["plant_ticks"] == 200
    assert fast["controller_calls"] == 20 and slow["controller_calls"] == 10
    assert [e["time_us"] for e in slow["controller_events"]] == list(range(0, 200_000, 20_000))
    assert fast["final_state"]["plant"]["u_mps"] != pytest.approx(
        slow["final_state"]["plant"]["u_mps"], abs=1e-8
    )


def test_tc_s11_logging_rate_changes_neither_controller_events_nor_plant():
    base = scenario()
    first = run_closed_loop(base)["result"]
    second = run_closed_loop(replace(base, logging_period_us=40_000))["result"]
    for key in (
        "controller_events",
        "sensor_arrivals",
        "final_state",
        "pack_draw_j",
        "energy_balance_residual_j",
    ):
        assert first[key] == second[key]
    assert first["observations"][::2] == second["observations"]


def test_versioned_record_round_trip_replay_and_forged_output_rejection():
    record = run_closed_loop(scenario(duration=100_000))
    decoded = json.loads(json.dumps(record))
    assert ClosedLoopScenario.from_dict(decoded["scenario"]) == scenario(
        duration=100_000
    )
    assert replay_closed_loop(decoded)["model_agreement"]
    broken = deepcopy(decoded)
    broken["result"]["final_state"]["plant"]["u_mps"] += 1
    broken["run_id"] = _content_id({k: v for k, v in broken.items() if k != "run_id"})
    with pytest.raises(ValueError, match="replay numeric"):
        replay_closed_loop(broken)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"plant_step_us": True},
        {"controller_period_us": 7500},
        {"controller_backend_id": "fake_native"},
        {"initial_soc": 2},
        {"extra_delays_us": ((0, -1),)},
        {"restart_times_us": (1,)},
        {"failed_rear_index": 0},
    ],
)
def test_unknown_identity_invalid_clock_and_fault_injections_fail_before_execution(
    kwargs,
):
    with pytest.raises(ValueError):
        scenario(**kwargs)
