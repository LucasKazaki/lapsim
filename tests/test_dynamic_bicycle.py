"""Frozen limiting cases for the six-state dynamic single-track plant."""

from dataclasses import replace
from math import hypot, pi

import pytest


from lapsim.dynamics.bicycle import (
    BicycleConfig,
    BicycleControls,
    BicycleState,
    evaluate_bicycle,
    integrate_bicycle,
)


def test_arbitrarily_large_integer_is_an_explicit_domain_error():
    with pytest.raises(ValueError, match="finite number"):
        BicycleConfig(mass_kg=10**500)


def advance(config, state, controls, duration, step=0.002):
    for _ in range(round(duration / step)):
        state = integrate_bicycle(config, state, controls, step)
    return state


def test_straight_propulsion_and_coast_have_analytic_solutions():
    config = BicycleConfig()
    state = advance(
        config, BicycleState(), BicycleControls(rear_force_request_n=300), 2
    )
    assert state.u_mps == pytest.approx(2, abs=1e-12)
    assert state.x_m == pytest.approx(2, abs=1e-12)
    assert state.y_m == state.v_mps == state.yaw_rate_rad_s == state.heading_rad == 0
    coast = advance(
        config, BicycleState(u_mps=5, heading_rad=pi / 2), BicycleControls(), 2
    )
    assert coast.y_m == pytest.approx(10, abs=1e-11)
    assert coast.x_m == pytest.approx(0, abs=1e-12)
    assert coast.u_mps == 5


def test_steering_at_rest_has_no_fictitious_lateral_force():
    config = BicycleConfig()
    state = BicycleState()
    controls = BicycleControls(steering_angle_rad=0.2)
    assert integrate_bicycle(config, state, controls, 0.1) == state
    evaluation = evaluate_bicycle(config, state, controls)
    assert evaluation.front_lateral_force_n == evaluation.rear_lateral_force_n == 0


def test_dynamic_yaw_and_lateral_velocity_are_states_not_a_kinematic_assignment():
    config = BicycleConfig()
    initial = BicycleState(u_mps=10)
    control = BicycleControls(steering_angle_rad=0.02)
    evaluation = evaluate_bicycle(config, initial, control)
    assert evaluation.derivative.yaw_rate_dot_rad_s2 > 0
    short = integrate_bicycle(config, initial, control, 0.0001)
    assert 0 < short.yaw_rate_rad_s < 10 * 0.02 / 1.6 / 10
    assert short.v_mps > 0


def test_mirrored_steering_mirrors_every_signed_lateral_state():
    config = BicycleConfig()
    left = advance(
        config,
        BicycleState(u_mps=8),
        BicycleControls(steering_angle_rad=0.04, rear_force_request_n=200),
        1,
    )
    right = advance(
        config,
        BicycleState(u_mps=8),
        BicycleControls(steering_angle_rad=-0.04, rear_force_request_n=200),
        1,
    )
    assert left.x_m == pytest.approx(right.x_m, abs=1e-12)
    assert left.u_mps == pytest.approx(right.u_mps, abs=1e-12)
    for name in ("y_m", "v_mps", "heading_rad", "yaw_rate_rad_s"):
        assert getattr(left, name) == pytest.approx(-getattr(right, name), abs=1e-12)


def test_neutral_steer_small_angle_constant_radius_limit():
    config = BicycleConfig()
    speed, delta = 10.0, 0.002
    rate = speed * delta / config.wheelbase_m
    lateral = config.cg_to_rear_axle_m * rate - (
        config.mass_kg
        * speed**2
        * rate
        * config.cg_to_front_axle_m
        / (config.wheelbase_m * config.rear_cornering_stiffness_n_per_rad)
    )
    state = advance(
        config,
        BicycleState(u_mps=speed, v_mps=lateral, yaw_rate_rad_s=rate),
        BicycleControls(steering_angle_rad=delta),
        2,
    )
    # Linear neutral-steer limit, not exact equality at finite slip/steering.
    assert state.yaw_rate_rad_s / state.u_mps == pytest.approx(
        delta / config.wheelbase_m, rel=3e-4
    )


def test_force_rotation_balances_and_common_friction_circle():
    config = BicycleConfig()
    state = BicycleState(u_mps=8, v_mps=-0.3, yaw_rate_rad_s=0.1)
    control = BicycleControls(
        steering_angle_rad=0.15, front_force_request_n=5000, rear_force_request_n=5000
    )
    result = evaluate_bicycle(config, state, control)
    d = result.derivative
    assert config.mass_kg * (
        d.u_dot_mps2 - state.yaw_rate_rad_s * state.v_mps
    ) == pytest.approx(result.total_force_x_n)
    assert config.mass_kg * (
        d.v_dot_mps2 + state.yaw_rate_rad_s * state.u_mps
    ) == pytest.approx(result.total_force_y_n)
    assert config.yaw_inertia_kgm2 * d.yaw_rate_dot_rad_s2 == pytest.approx(
        result.yaw_moment_nm
    )
    assert result.front_force_x_body_n != result.front_longitudinal_force_n
    for fx, fy, load in (
        (
            result.front_longitudinal_force_n,
            result.front_lateral_force_n,
            config.static_axle_loads_n[0],
        ),
        (
            result.rear_longitudinal_force_n,
            result.rear_lateral_force_n,
            config.static_axle_loads_n[1],
        ),
    ):
        assert hypot(fx, fy) == pytest.approx(
            config.friction_coefficient * load, rel=1e-12
        )
    assert result.front_limited and result.rear_limited


@pytest.mark.parametrize("loads,mu", [((0.0, 0.0), 1.2), (None, 0.0)])
def test_zero_load_or_grip_cannot_generate_contact_force(loads, mu):
    result = evaluate_bicycle(
        replace(BicycleConfig(), friction_coefficient=mu),
        BicycleState(u_mps=4, v_mps=0.5),
        BicycleControls(
            steering_angle_rad=0.1, rear_force_request_n=1000, normal_loads_n=loads
        ),
    )
    assert result.total_force_x_n == result.total_force_y_n == result.yaw_moment_nm == 0


def test_low_speed_floor_is_continuous_and_forward_ramp_crosses_it():
    config = BicycleConfig()
    control = BicycleControls(steering_angle_rad=0.02, rear_force_request_n=60)
    low = evaluate_bicycle(config, BicycleState(u_mps=0.5 - 1e-8, v_mps=0.01), control)
    high = evaluate_bicycle(config, BicycleState(u_mps=0.5 + 1e-8, v_mps=0.01), control)
    assert low.total_force_y_n == pytest.approx(high.total_force_y_n, abs=1e-3)
    state = advance(config, BicycleState(), control, 4)
    assert state.u_mps > config.low_speed_regularization_mps
    assert abs(state.yaw_rate_rad_s) < 0.1


@pytest.mark.parametrize(
    "name,value",
    [
        ("mass_kg", True),
        ("mass_kg", 0),
        ("mass_kg", float("nan")),
        ("yaw_inertia_kgm2", -1),
        ("cg_to_front_axle_m", float("inf")),
        ("friction_coefficient", -0.1),
        ("low_speed_regularization_mps", 0),
    ],
)
def test_invalid_config_is_rejected(name, value):
    with pytest.raises(ValueError):
        replace(BicycleConfig(), **{name: value})


@pytest.mark.parametrize(
    "values",
    [
        {"steering_angle_rad": pi / 2},
        {"front_force_request_n": True},
        {"rear_force_request_n": float("inf")},
        {"normal_loads_n": (1, -1)},
    ],
)
def test_invalid_controls_are_rejected(values):
    with pytest.raises(ValueError):
        BicycleControls(**values)


def test_reverse_and_excessive_integration_work_are_explicit_failures():
    with pytest.raises(ValueError, match="reverse"):
        BicycleState(u_mps=-1)
    with pytest.raises(ValueError, match="work budget"):
        integrate_bicycle(BicycleConfig(), BicycleState(), BicycleControls(), 1000)
    with pytest.raises(ValueError):
        integrate_bicycle(BicycleConfig(), BicycleState(), BicycleControls(), 0)


def test_smooth_maneuver_refines_in_rk4_accuracy_region():
    config = replace(
        BicycleConfig(),
        front_cornering_stiffness_n_per_rad=2000,
        rear_cornering_stiffness_n_per_rad=2000,
        maximum_integration_step_s=0.004,
    )
    initial = BicycleState(u_mps=5)
    control = BicycleControls(steering_angle_rad=0.02, rear_force_request_n=200)
    reference = advance(config, initial, control, 0.2, 0.00025)
    errors = []
    for step in (0.004, 0.002, 0.001):
        actual = advance(config, initial, control, 0.2, step)
        errors.append(
            max(
                abs(getattr(actual, name) - getattr(reference, name))
                for name in initial.__dataclass_fields__
            )
        )
    assert errors[1] < errors[0] / 8
    assert errors[2] < errors[1] / 8
