"""Generated contract checks; independent of team-private vehicle parameters."""

from dataclasses import fields
import math

from hypothesis import given, settings, strategies as st
import pytest

from lapsim.core.controls import Controls
from lapsim.core.profiles import ConstantControlsProfile, PiecewiseLinearControlsProfile

settings.register_profile("quality", max_examples=200, derandomize=True, deadline=None)
settings.load_profile("quality")
NONNEGATIVE = st.floats(
    min_value=0, max_value=10000, allow_nan=False, allow_infinity=False
)
DISTANCE = st.floats(
    min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False
)


@given(distance=DISTANCE, torque=NONNEGATIVE)
def test_constant_profile_preserves_controls(distance, torque):
    controls = Controls(motor_torque_request_nm=torque)
    assert ConstantControlsProfile(controls).controls_at(distance) is controls


@given(lower=NONNEGATIVE, upper=NONNEGATIVE, fraction=st.floats(0, 1))
def test_drive_interpolation_is_finite_and_bounded(lower, upper, fraction):
    profile = PiecewiseLinearControlsProfile(
        (0.0, 100.0),
        (
            Controls(motor_torque_request_nm=lower),
            Controls(motor_torque_request_nm=upper),
        ),
    )
    result = profile.controls_at(100 * fraction)
    assert math.isfinite(result.motor_torque_request_nm)
    assert (
        min(lower, upper) - 1e-9
        <= result.motor_torque_request_nm
        <= max(lower, upper) + 1e-9
    )


@given(distance=st.floats(0, 1000), laps=st.integers(-10, 10))
def test_periodic_profile_repeats(distance, laps):
    profile = PiecewiseLinearControlsProfile(
        (0.0, 50.0),
        (Controls(motor_torque_request_nm=20), Controls(motor_torque_request_nm=80)),
        period_m=100,
    )
    assert profile.controls_at(distance).motor_torque_request_nm == pytest.approx(
        profile.controls_at(distance + laps * 100).motor_torque_request_nm, abs=1e-9
    )


@given(
    field=st.sampled_from([f.name for f in fields(Controls)]),
    invalid=st.sampled_from([float("nan"), float("inf"), -float("inf")]),
)
def test_nonfinite_controls_are_rejected(field, invalid):
    with pytest.raises(ValueError):
        Controls(**{field: invalid})


@given(
    torque=st.floats(1, 1000), regen=st.floats(1, 1000), fraction=st.floats(0.01, 0.99)
)
def test_accepted_profile_is_sampleable_across_drive_regen_transition(
    torque, regen, fraction
):
    # Reject an unsupported transition at construction, or return valid Controls.
    # Accepting a profile and crashing only when the solver samples it is unsafe.
    try:
        profile = PiecewiseLinearControlsProfile(
            (0.0, 100.0),
            (
                Controls(motor_torque_request_nm=torque),
                Controls(rear_regenerative_brake_force_request_n=regen),
            ),
        )
    except ValueError:
        return
    result = profile.controls_at(100 * fraction)
    assert not (
        result.motor_torque_request_nm > 0
        and result.rear_regenerative_brake_force_request_n > 0
    )


@pytest.mark.parametrize("axle", ["front", "rear"])
@pytest.mark.parametrize("reverse", [False, True])
def test_drive_regen_transition_is_rejected_at_construction(axle, reverse):
    controls = [
        Controls(motor_torque_request_nm=1),
        Controls(**{f"{axle}_regenerative_brake_force_request_n": 1}),
    ]
    if reverse:
        controls.reverse()
    with pytest.raises(ValueError, match="zero-demand knot"):
        PiecewiseLinearControlsProfile((0.0, 100.0), tuple(controls))


def test_periodic_drive_regen_seam_is_rejected():
    with pytest.raises(ValueError, match="zero-demand knot"):
        PiecewiseLinearControlsProfile(
            (0.0, 50.0, 100.0),
            (
                Controls(motor_torque_request_nm=1),
                Controls(),
                Controls(rear_regenerative_brake_force_request_n=1),
            ),
            period_m=150.0,
        )


@given(distance=st.floats(0, 100))
def test_explicit_coast_knot_makes_drive_regen_transition_sampleable(distance):
    profile = PiecewiseLinearControlsProfile(
        (0.0, 50.0, 100.0),
        (
            Controls(motor_torque_request_nm=20),
            Controls(),
            Controls(rear_regenerative_brake_force_request_n=100),
        ),
    )
    result = profile.controls_at(distance)
    assert not (
        result.motor_torque_request_nm > 0
        and result.rear_regenerative_brake_force_request_n > 0
    )


@given(soc=st.floats(0.1, 0.9), fraction=st.floats(0, 0.99))
def test_battery_current_satisfies_terminal_power_balance(soc, fraction):
    from vehicle_model.electrical.battery import OCVPackBattery

    battery = OCVPackBattery(initial_state_of_charge=soc)
    power = fraction * battery.discharge_power_limit_w
    current = battery.current_for_terminal_power_a(power)
    terminal = (
        battery.open_circuit_voltage_v - current * battery.internal_resistance_ohm
    )
    assert math.isfinite(current) and current >= 0
    assert current * terminal == pytest.approx(power, rel=1e-10, abs=1e-8)


@given(soc=st.floats(0, 1), dt=st.floats(1e-4, 10))
def test_zero_power_preserves_battery_charge(soc, dt):
    from vehicle_model.electrical.battery import OCVPackBattery

    battery = OCVPackBattery(initial_state_of_charge=soc)
    battery.update_state(0.0, dt)
    assert battery.current_a == 0.0
    assert battery.state_of_charge == soc


@given(load=st.floats(1, 5000), mu=st.floats(0.1, 2), utilization=st.floats(-2, 2))
def test_combined_tire_force_obeys_friction_budget(load, mu, utilization):
    from vehicle_model.mech.tire import Tire

    tire = Tire(constant_friction_coefficient=mu)
    available = tire.combined_longitudinal_force_capacity_n(
        load, utilization * mu * load
    )
    assert 0 <= available <= mu * load
    assert available == pytest.approx(
        mu * load * math.sqrt(max(0, 1 - min(abs(utilization), 1) ** 2)), abs=1e-8
    )
