"""Held-current interval bounds and atomic battery/vehicle rejection."""

import math
import pickle

import pytest

from lapsim import Controls
from vehicle_model import (
    Battery,
    BatteryModel,
    BatteryUpdatePreflight,
    OCVPackBattery,
    RCTheveninBattery,
    Vehicle,
)

PACKS = (OCVPackBattery, RCTheveninBattery)


def snapshot(value):
    return pickle.dumps(value, protocol=5)


def near_boundary(battery_type, charging):
    return battery_type(
        initial_state_of_charge=1.0 - 1e-6 if charging else 1e-6,
        max_charge_power_w=10000.0,
    )


@pytest.mark.parametrize("battery_type", PACKS)
@pytest.mark.parametrize("charging", (False, True))
def test_interval_cannot_remove_or_add_more_charge_than_available(
    battery_type, charging
):
    battery = near_boundary(battery_type, charging)
    before = snapshot(battery)
    with pytest.raises(ValueError, match="charge|capacity"):
        battery.update_state(-1000.0 if charging else 100.0, 1.0)
    assert snapshot(battery) == before


@pytest.mark.parametrize("battery_type", PACKS)
@pytest.mark.parametrize("charging", (False, True))
def test_exact_charge_boundary_remains_representable(battery_type, charging):
    battery = near_boundary(battery_type, charging)
    initial_soc = battery.state_of_charge
    power = -1000.0 if charging else 100.0
    current = battery.current_for_terminal_power_a(power)
    room_ah = (
        1.0 - initial_soc if charging else initial_soc
    ) * battery.pack_capacity_ah
    duration = room_ah * 3600.0 / abs(current)
    battery.update_state(power, duration)
    assert math.isclose(
        battery.state_of_charge, 1.0 if charging else 0.0, abs_tol=1e-18
    )
    assert math.isclose(abs(battery.net_charge_removed_ah), room_ah, rel_tol=2e-15)
    assert math.isclose(
        battery.current_power_w,
        battery.current_a * battery.terminal_voltage_v,
        rel_tol=1e-12,
    )


@pytest.mark.parametrize("battery_type", PACKS)
@pytest.mark.parametrize("charging", (False, True))
def test_real_excess_beyond_boundary_roundoff_is_rejected(battery_type, charging):
    battery = near_boundary(battery_type, charging)
    power = -1000.0 if charging else 100.0
    current = battery.current_for_terminal_power_a(power)
    room = (
        1.0 - battery.state_of_charge if charging else battery.state_of_charge
    ) * battery.pack_capacity_ah
    duration = room * 3600.0 / abs(current)
    for _ in range(128):
        duration = math.nextafter(duration, math.inf)
    before = snapshot(battery)
    with pytest.raises(ValueError, match="charge|capacity"):
        battery.update_state(power, duration)
    assert snapshot(battery) == before


@pytest.mark.parametrize("battery_type", PACKS)
def test_overflowing_interval_does_not_poison_operating_or_rc_state(battery_type):
    battery = battery_type(initial_state_of_charge=0.5)
    before = snapshot(battery)
    with pytest.raises(ValueError, match="charge|finite"):
        battery.update_state(50000.0, 1e308)
    assert snapshot(battery) == before


@pytest.mark.parametrize("battery_type", PACKS)
def test_vehicle_exhaustion_rejects_before_path_aero_and_component_commits(
    battery_type,
):
    vehicle = Vehicle(
        initial_speed_mps=5.0, battery=battery_type(initial_state_of_charge=1e-6)
    )
    before, telemetry = snapshot(vehicle), vehicle.telemetry_snapshot()
    with pytest.raises(ValueError, match="charge|capacity"):
        vehicle.update_state(Controls(motor_torque_request_nm=100.0), 0.5)
    assert snapshot(vehicle) == before
    assert vehicle.telemetry_snapshot() == telemetry


@pytest.mark.parametrize("battery_type", PACKS)
def test_vehicle_regeneration_overfill_is_also_atomic(battery_type):
    vehicle = Vehicle(
        initial_speed_mps=20.0,
        battery=battery_type(
            initial_state_of_charge=1.0 - 1e-6, max_charge_power_w=80000.0
        ),
    )
    before = snapshot(vehicle)
    with pytest.raises(ValueError, match="charge|capacity"):
        vehicle.update_state(
            Controls(rear_regenerative_brake_force_request_n=1000.0), 50.0
        )
    assert snapshot(vehicle) == before


@pytest.mark.parametrize("battery_type", PACKS)
@pytest.mark.parametrize("charging", (False, True))
def test_valid_intervals_keep_current_energy_and_coulomb_accounting(
    battery_type, charging
):
    battery = battery_type(initial_state_of_charge=0.5, max_charge_power_w=10000.0)
    initial_soc = battery.state_of_charge
    power, duration = (-1000.0 if charging else 1000.0), 0.2
    battery.update_state(power, duration)
    delta = battery.current_a * duration / 3600.0
    assert battery.net_charge_removed_ah == delta
    assert battery.coulomb_throughput_ah == abs(delta)
    assert battery.state_of_charge == initial_soc - delta / battery.pack_capacity_ah
    assert math.isclose(
        power * duration,
        battery.current_a * battery.terminal_voltage_v * duration,
        rel_tol=1e-12,
    )


def test_ideal_battery_keeps_its_explicit_infinite_charge_model():
    battery = Battery()
    battery.update_state(1000.0, 1e100)
    assert battery.current_power_w == 1000.0


@pytest.mark.parametrize("battery_type", (Battery, *PACKS))
def test_builtin_preflight_is_pure_for_accepted_and_rejected_intervals(battery_type):
    battery = battery_type()
    assert isinstance(battery, BatteryUpdatePreflight)
    before = snapshot(battery)
    battery.validate_state_update(1000.0, 0.2)
    assert snapshot(battery) == before
    with pytest.raises(ValueError):
        battery.validate_state_update(1e100, 0.2)
    assert snapshot(battery) == before


class LegacyBattery:
    """Existing structural replacement without the new optional capability."""

    def __init__(self):
        self.source = Battery()

    @property
    def current_power_w(self):
        return self.source.current_power_w

    @property
    def discharge_power_limit_w(self):
        return self.source.discharge_power_limit_w

    @property
    def charge_power_limit_w(self):
        return self.source.charge_power_limit_w

    def validate(self):
        self.source.validate()

    def reset_state(self):
        self.source.reset_state()

    def update_telemetry(self, telemetry):
        self.source.update_telemetry(telemetry)

    def limit_discharge_power_w(self, request):
        return self.source.limit_discharge_power_w(request)

    def limit_charge_power_w(self, request):
        return self.source.limit_charge_power_w(request)

    def update_state(self, power, duration):
        self.source.update_state(power, duration)


def test_legacy_battery_protocol_replacement_still_runs():
    battery = LegacyBattery()
    assert isinstance(battery, BatteryModel)
    assert not isinstance(battery, BatteryUpdatePreflight)
    vehicle = Vehicle(battery=battery, initial_speed_mps=5.0)
    vehicle.update_state(Controls(motor_torque_request_nm=100.0), 0.5)
    assert vehicle.distance_m == 0.5
    assert battery.current_power_w > 0.0


class RefusingBattery(Battery):
    def validate_state_update(self, power_w, timestep_s):
        raise ValueError("test pure preflight refusal")


def test_optional_preflight_refusal_precedes_all_builtin_commits():
    vehicle = Vehicle(battery=RefusingBattery(), initial_speed_mps=5.0)
    before = snapshot(vehicle)
    with pytest.raises(ValueError, match="test pure preflight"):
        vehicle.update_state(Controls(motor_torque_request_nm=100.0), 0.5)
    assert snapshot(vehicle) == before


@pytest.mark.parametrize("battery_type", PACKS)
def test_rejection_restores_prior_nonzero_suspension_trial_cache(battery_type):
    vehicle = Vehicle(
        initial_speed_mps=5.0, battery=battery_type(initial_state_of_charge=0.5)
    )
    vehicle.update_state(Controls(steering_angle_rad=0.05), 0.01)
    vehicle.battery.state_of_charge = 1e-6
    before = snapshot(vehicle)
    with pytest.raises(ValueError, match="charge|capacity"):
        vehicle.update_state(
            Controls(motor_torque_request_nm=100.0, steering_angle_rad=0.1), 0.5
        )
    assert snapshot(vehicle) == before
