"""Frozen signed conversion, shared pack bounds and current-at-stall checks."""

from dataclasses import replace
import math

import pytest

from lapsim.dynamics.actuation import ActuationConfig, constrain_actuation


def evaluate(
    config=None,
    torque=(0.0, 0.0, 100.0, 100.0),
    speeds=(10.0,) * 4,
    energy=9e6,
    interval=0.002,
    **kwargs,
):
    return constrain_actuation(
        config or ActuationConfig(), torque, speeds, energy, interval, **kwargs
    )


def test_signed_gear_motor_inverter_conversion_has_directional_efficiencies():
    config = replace(ActuationConfig(), equivalent_copper_resistance_ohm=0)
    efficiency = (
        config.gear_efficiency
        * config.motor_conversion_efficiency
        * config.inverter_efficiency
    )
    positive = evaluate(config)
    negative = evaluate(config, torque=(0, 0, -100, -100))
    assert positive.wheel_power_w == 2000
    assert positive.pack_power_w == pytest.approx(2000 / efficiency, rel=1e-12)
    assert negative.pack_power_w == pytest.approx(-2000 * efficiency, rel=1e-12)
    assert positive.conversion_loss_w >= 0
    assert negative.conversion_loss_w >= 0


def test_stall_retains_motor_current_limit_and_copper_power():
    config = ActuationConfig()
    value = evaluate(config, torque=(0, 0, 1e5, 1e5), speeds=(0,) * 4)
    assert value.motor_currents_a[2:] == pytest.approx((90, 90))
    assert value.wheel_power_w == 0
    assert value.pack_power_w == pytest.approx(2 * 90**2 * 0.02 / 0.97)
    assert value.conversion_loss_w == value.pack_power_w


def test_shared_bus_limits_sum_of_actuators_and_preserves_requested_split():
    config = replace(ActuationConfig(), pack_discharge_current_limit_a=2)
    value = evaluate(config, torque=(0, 0, 80, 160))
    assert value.pack_power_w <= 600
    assert value.pack_power_w == pytest.approx(600, rel=1e-12)
    assert value.wheel_torques_nm[3] == pytest.approx(2 * value.wheel_torques_nm[2])
    assert value.shared_power_scale < 1


def test_regeneration_shared_charge_current_and_full_empty_energy_boundaries():
    config = replace(ActuationConfig(), pack_charge_current_limit_a=1)
    regen = evaluate(config, torque=(0, 0, -200, -200), speeds=(30,) * 4)
    assert regen.pack_power_w == pytest.approx(-300, rel=1e-12)
    assert abs(regen.pack_current_a) <= 1
    assert evaluate(config, energy=0).wheel_torques_nm == (0,) * 4
    full = evaluate(config, torque=(0, 0, -100, -100), energy=config.pack_capacity_j)
    assert full.wheel_torques_nm == (0,) * 4
    near_empty = evaluate(config, energy=0.001)
    assert 0 <= near_empty.pack_power_w * 0.002 <= 0.001
    near_full = evaluate(
        config, torque=(0, 0, -100, -100), energy=config.pack_capacity_j - 0.001
    )
    assert -near_full.pack_power_w * 0.002 <= config.pack_capacity_j - (
        config.pack_capacity_j - 0.001
    )


def test_low_speed_regeneration_never_becomes_plug_braking_or_increases_on_scaling():
    config = replace(ActuationConfig(), pack_charge_power_limit_w=0.001)
    value = evaluate(config, torque=(0, 0, -200, -200), speeds=(0.001,) * 4)
    assert -0.001 <= value.pack_power_w <= 0
    assert value.conversion_loss_w >= 0
    assert (
        evaluate(config, torque=(0, 0, -100, -100), speeds=(0,) * 4).wheel_torques_nm
        == (0,) * 4
    )


def test_motor_speed_cutoff_and_availability_prevent_unavailable_torque():
    config = ActuationConfig()
    at_limit = evaluate(
        config, speeds=(config.motor_maximum_speed_rad_s / config.gear_ratio,) * 4
    )
    assert at_limit.wheel_torques_nm == (0,) * 4
    one = evaluate(config, available=(False, False, False, True))
    assert one.wheel_torques_nm == (0, 0, 0, 100)
    assert one.pack_power_w < evaluate(config).pack_power_w


@pytest.mark.parametrize(
    "kwargs",
    [
        {"torque": (1, 0, 0, 0)},
        {"speeds": (-1, 0, 0, 0)},
        {"energy": -1},
        {"energy": 18e6 + 1},
        {"interval": 0},
        {"torque": (0, 0, True, 0)},
        {"available": (False, False, 1, True)},
        {"speeds": (math.nan,) * 4},
    ],
)
def test_invalid_actuation_domain_is_explicit(kwargs):
    with pytest.raises(ValueError):
        evaluate(**kwargs)


def test_opposite_actuator_transients_still_obey_shared_signed_bus_limits():
    config = replace(
        ActuationConfig(), pack_charge_power_limit_w=10, pack_discharge_power_limit_w=10
    )
    value = evaluate(config, torque=(0, 0, -100, 150))
    assert -10 <= value.pack_power_w <= 10
    assert value.conversion_loss_w >= 0
