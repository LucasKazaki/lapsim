"""Checks for the independent-wheel planar force and energy balances."""

from __future__ import annotations

from math import cos, isclose, radians, sin

import pytest

from lapsim.dynamics import (
    PlanarControls,
    PlanarState,
    PlanarVehicleConfig,
    evaluate_planar_dynamics,
    run_planar_dynamics,
    step_planar_dynamics,
)


def synthetic_config() -> PlanarVehicleConfig:
    return PlanarVehicleConfig(
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


def rolling_state(speed_mps: float = 12.0) -> PlanarState:
    omega = speed_mps / synthetic_config().wheel_radius_m
    return PlanarState(
        u_mps=speed_mps,
        wheel_speeds_rad_s=(omega,) * 4,
    )


def test_static_loads_and_wheel_order() -> None:
    config = synthetic_config()
    loads = config.static_normal_loads_n
    assert loads == pytest.approx((735.49875,) * 4)
    assert sum(loads) == pytest.approx(config.mass_kg * config.gravity_mps2)
    assert config.wheel_positions_m == (
        (0.8, 0.6), (0.8, -0.6), (-0.8, 0.6), (-0.8, -0.6)
    )


def test_local_wheel_velocity_and_force_rotation() -> None:
    config = synthetic_config()
    steer = radians(8)
    state = PlanarState(
        u_mps=11.0,
        v_mps=0.6,
        yaw_rate_rad_s=0.4,
        wheel_speeds_rad_s=(60.0,) * 4,
    )
    controls = PlanarControls(steering_angles_rad=(steer, 0.0, 0.0, 0.0))
    evaluated = evaluate_planar_dynamics(config, state, controls)
    front_left = evaluated.wheels[0]
    body_vx = state.u_mps - state.yaw_rate_rad_s * 0.6
    body_vy = state.v_mps + state.yaw_rate_rad_s * 0.8
    assert front_left.local_velocity_x_mps == pytest.approx(
        cos(steer) * body_vx + sin(steer) * body_vy
    )
    assert front_left.local_velocity_y_mps == pytest.approx(
        -sin(steer) * body_vx + cos(steer) * body_vy
    )
    assert front_left.body_force_x_n == pytest.approx(
        cos(steer) * front_left.local_force_x_n
        - sin(steer) * front_left.local_force_y_n
    )
    assert front_left.body_force_y_n == pytest.approx(
        sin(steer) * front_left.local_force_x_n
        + cos(steer) * front_left.local_force_y_n
    )
    assert evaluated.cg_lateral_acceleration_mps2 == pytest.approx(
        evaluated.derivative.v_dot_mps2 + state.yaw_rate_rad_s * state.u_mps
    )


def test_combined_slip_respects_each_patch_limit() -> None:
    config = synthetic_config()
    state = PlanarState(
        u_mps=12.0,
        v_mps=3.0,
        wheel_speeds_rad_s=(120.0, 120.0, 120.0, 120.0),
    )
    evaluated = evaluate_planar_dynamics(config, state, PlanarControls())
    for wheel in evaluated.wheels:
        assert wheel.force_magnitude_n <= wheel.friction_limit_n + 1e-9
        assert wheel.force_utilization == pytest.approx(1.0)
    assert evaluated.contact_dissipation_w >= 0.0


def test_forward_slip_uses_vehicle_speed_above_regularization_floor() -> None:
    config = synthetic_config()
    state = PlanarState(
        u_mps=12.0,
        wheel_speeds_rad_s=(120.0,) * 4,
    )
    evaluated = evaluate_planar_dynamics(config, state, PlanarControls())
    assert evaluated.wheels[0].slip_ratio == pytest.approx(1.0)


def test_no_contact_wheel_free_spins_and_cannot_push_body() -> None:
    config = synthetic_config()
    controls = PlanarControls(
        drive_torques_nm=(30.0, 0.0, 0.0, 0.0),
        normal_loads_n=(0.0, 0.0, 0.0, 0.0),
    )
    evaluated = evaluate_planar_dynamics(config, PlanarState(), controls)
    assert all(not wheel.in_contact for wheel in evaluated.wheels)
    assert evaluated.total_body_force_x_n == 0.0
    assert evaluated.derivative.wheel_accelerations_rad_s2[0] == pytest.approx(
        30.0 / config.wheel_inertia_kgm2
    )
    final = step_planar_dynamics(config, PlanarState(), controls, 0.1)
    assert final.u_mps == 0.0
    assert final.wheel_speeds_rad_s[0] == pytest.approx(10.0)


def test_mechanical_power_identity_with_steer_and_external_loads() -> None:
    config = synthetic_config()
    state = PlanarState(
        u_mps=12.0,
        v_mps=-0.5,
        yaw_rate_rad_s=0.4,
        wheel_speeds_rad_s=(59.0, 65.0, 54.0, 68.0),
    )
    controls = PlanarControls(
        steering_angles_rad=(radians(5), radians(4), 0.0, 0.0),
        drive_torques_nm=(5.0, 10.0, 40.0, 70.0),
        brake_torques_nm=(0.0, 0.0, 0.0, 3.0),
        normal_loads_n=(500.0, 900.0, 600.0, 900.0),
        external_force_x_n=-120.0,
        external_force_y_n=15.0,
        external_yaw_moment_nm=4.0,
    )
    evaluated = evaluate_planar_dynamics(config, state, controls)
    assert evaluated.contact_dissipation_w >= 0.0
    assert evaluated.brake_power_w <= 0.0
    assert abs(evaluated.energy_balance_residual_w) < 1e-8
    assert evaluated.derivative.u_dot_mps2 - state.yaw_rate_rad_s * state.v_mps == pytest.approx(
        evaluated.total_body_force_x_n / config.mass_kg
    )
    assert evaluated.derivative.yaw_rate_dot_rad_s2 == pytest.approx(
        evaluated.total_yaw_moment_nm / config.yaw_inertia_kgm2
    )


def test_launch_coast_and_time_alignment() -> None:
    config = synthetic_config()
    launch = PlanarControls(drive_torques_nm=(40.0,) * 4)
    launched = run_planar_dynamics(
        config, PlanarState(), (launch,) * 50, 0.01
    )
    assert launched.states[-1].u_mps > 0.0
    assert launched.states[-1].x_m > 0.0
    assert len(launched.times_s) == len(launched.states) == 51
    assert len(launched.evaluations) == 50
    assert launched.times_s[0] == 0.0
    assert launched.times_s[-1] == pytest.approx(0.5)

    coasting = run_planar_dynamics(
        config, rolling_state(), (PlanarControls(),) * 100, 0.01
    )
    assert coasting.states[-1].u_mps == pytest.approx(12.0, abs=1e-8)
    assert coasting.states[-1].x_m == pytest.approx(12.0, abs=1e-8)
    assert coasting.states[-1].wheel_speeds_rad_s == pytest.approx((60.0,) * 4)
    assert isclose(
        coasting.evaluations[0].mechanical_energy_j,
        coasting.evaluations[-1].mechanical_energy_j,
        abs_tol=1e-8,
    )


def test_near_no_slip_acceleration_accounts_for_explicit_wheel_inertia_once() -> None:
    config = synthetic_config()
    drive_torque_nm = 40.0
    controls = PlanarControls(drive_torques_nm=(drive_torque_nm,) * 4)
    result = run_planar_dynamics(
        config, rolling_state(), (controls,) * 50, 0.01
    )
    evaluated = evaluate_planar_dynamics(config, result.states[-1], controls)
    expected_mps2 = (
        4.0 * drive_torque_nm / config.wheel_radius_m
        / (config.mass_kg + 4.0 * config.wheel_inertia_kgm2 / config.wheel_radius_m**2)
    )
    assert evaluated.derivative.u_dot_mps2 == pytest.approx(expected_mps2, rel=0.01)


def test_positive_front_steer_produces_left_yaw() -> None:
    config = synthetic_config()
    steer = radians(4)
    controls = PlanarControls(steering_angles_rad=(steer, steer, 0.0, 0.0))
    evaluated = evaluate_planar_dynamics(config, rolling_state(), controls)
    assert evaluated.total_body_force_y_n > 0.0
    assert evaluated.total_yaw_moment_nm > 0.0
    final = run_planar_dynamics(
        config, rolling_state(), (controls,) * 30, 0.01
    ).states[-1]
    assert final.heading_rad > 0.0
    assert final.y_m > 0.0
    assert final.yaw_rate_rad_s > 0.0


def test_more_right_rear_torque_produces_positive_yaw() -> None:
    config = synthetic_config()
    initial = rolling_state()
    equal = PlanarControls(drive_torques_nm=(0.0, 0.0, 100.0, 100.0))
    split = PlanarControls(drive_torques_nm=(0.0, 0.0, 90.0, 110.0))
    equal_result = run_planar_dynamics(config, initial, (equal,) * 20, 0.01)
    split_result = run_planar_dynamics(config, initial, (split,) * 20, 0.01)
    assert equal_result.states[-1].yaw_rate_rad_s == pytest.approx(0.0, abs=1e-10)
    assert split_result.states[-1].yaw_rate_rad_s > 0.0


def test_locked_brake_does_not_reverse_wheel() -> None:
    config = synthetic_config()
    full_brake = PlanarControls(brake_torques_nm=(400.0,) * 4)
    result = run_planar_dynamics(
        config, rolling_state(6.0), (full_brake,) * 30, 0.01
    )
    assert all(omega >= 0.0 for state in result.states for omega in state.wheel_speeds_rad_s)
    assert any(omega == 0.0 for omega in result.states[-1].wheel_speeds_rad_s)
    assert result.states[-1].u_mps >= 0.0


def test_timestep_sensitivity_for_steering_maneuver() -> None:
    config = synthetic_config()
    controls = PlanarControls(
        steering_angles_rad=(radians(3), radians(3), 0.0, 0.0),
        drive_torques_nm=(0.0, 0.0, 90.0, 100.0),
    )
    coarse = run_planar_dynamics(
        config, rolling_state(), (controls,) * 30, 0.01
    ).states[-1]
    fine = run_planar_dynamics(
        config, rolling_state(), (controls,) * 60, 0.005
    ).states[-1]
    assert coarse.x_m == pytest.approx(fine.x_m, abs=0.03)
    assert coarse.y_m == pytest.approx(fine.y_m, abs=0.03)
    assert coarse.heading_rad == pytest.approx(fine.heading_rad, abs=0.01)


def test_low_speed_stiffness_refinement_matches_small_step_reference() -> None:
    config = synthetic_config()
    assert config.integration_step_limit_s < config.maximum_integration_step_s
    initial = PlanarState(u_mps=0.1, wheel_speeds_rad_s=(0.5,) * 4)
    controls = PlanarControls(drive_torques_nm=(1.0,) * 4)
    coarse_output = run_planar_dynamics(
        config, initial, (controls,) * 20, 0.01
    ).states[-1]
    fine_reference = run_planar_dynamics(
        PlanarVehicleConfig(
            mass_kg=config.mass_kg,
            yaw_inertia_kgm2=config.yaw_inertia_kgm2,
            cg_to_front_axle_m=config.cg_to_front_axle_m,
            cg_to_rear_axle_m=config.cg_to_rear_axle_m,
            front_track_m=config.front_track_m,
            rear_track_m=config.rear_track_m,
            wheel_radius_m=config.wheel_radius_m,
            wheel_inertia_kgm2=config.wheel_inertia_kgm2,
            tire_mu=config.tire_mu,
            longitudinal_stiffness_n_per_slip=config.longitudinal_stiffness_n_per_slip,
            cornering_stiffness_n_per_rad=config.cornering_stiffness_n_per_rad,
            maximum_integration_step_s=0.0001,
        ),
        initial,
        (controls,) * 20,
        0.01,
    ).states[-1]
    assert coarse_output.u_mps == pytest.approx(fine_reference.u_mps, abs=1e-6)
    assert coarse_output.wheel_speeds_rad_s == pytest.approx(
        fine_reference.wheel_speeds_rad_s, abs=1e-6
    )


def test_invalid_physical_inputs_are_rejected() -> None:
    config = synthetic_config()
    with pytest.raises(ValueError):
        PlanarVehicleConfig(
            mass_kg=-1,
            yaw_inertia_kgm2=160,
            cg_to_front_axle_m=0.8,
            cg_to_rear_axle_m=0.8,
            front_track_m=1.2,
            rear_track_m=1.2,
            wheel_radius_m=0.2,
            wheel_inertia_kgm2=0.3,
            tire_mu=1.5,
            longitudinal_stiffness_n_per_slip=7000,
            cornering_stiffness_n_per_rad=8000,
        )
    with pytest.raises(ValueError):
        PlanarControls(brake_torques_nm=(-1.0, 0.0, 0.0, 0.0))
    with pytest.raises(ValueError):
        step_planar_dynamics(config, PlanarState(), PlanarControls(), 0.0)
    with pytest.raises(ValueError, match="too many internal"):
        step_planar_dynamics(config, PlanarState(), PlanarControls(), 1_000.0)
