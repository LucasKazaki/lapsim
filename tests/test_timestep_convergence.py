"""Physical consistency checks for a formerly oscillating spatial cell."""

from math import isfinite
from dataclasses import replace

import pytest

from lapsim import Controls
from vehicle_model import Vehicle
from vehicle_model.mech.tire import Tire, TIRE_POSITIONS


@pytest.mark.parametrize("torque_nm", (100.0, 1.0e6))
@pytest.mark.parametrize("relaxation_m", (0.0, 1.0))
def test_near_rpm_limit_cell_has_one_consistent_elapsed_time(
    torque_nm: float, relaxation_m: float
) -> None:
    vehicle = Vehicle(initial_speed_mps=42.5)
    vehicle.tire.longitudinal_slip_relaxation_length_m = relaxation_m
    distance_m = 50.0

    vehicle.update_state(Controls(motor_torque_request_nm=torque_nm), distance_m)

    assert vehicle.distance_m == distance_m
    assert vehicle.time_s == pytest.approx(
        2 * distance_m / (vehicle.initial_speed_mps + vehicle.speed_mps),
        rel=1e-10,
    )
    assert vehicle.speed_mps**2 == pytest.approx(
        vehicle.initial_speed_mps**2
        + 2 * vehicle.longitudinal_acceleration_mps2 * distance_m,
        rel=1e-10,
    )
    assert all(isfinite(value) for value in vehicle.telemetry_snapshot().values())
    force_n = (
        vehicle.current_drive_force_n
        - vehicle.current_friction_braking_force_n
        - vehicle.current_regenerative_braking_force_n
        - vehicle.current_resistance_force_n
    )
    assert (
        vehicle.effective_longitudinal_mass_kg * vehicle.longitudinal_acceleration_mps2
        == pytest.approx(force_n, abs=1e-5)
    )
    assert vehicle.battery.current_power_w == pytest.approx(
        vehicle.battery.current_a * vehicle.battery.terminal_voltage_v,
        abs=1e-5,
    )


def test_timestep_bracket_must_contain_a_physical_root_not_just_a_jump() -> None:
    class DiscontinuousTire(Tire):
        """Synthetic cutoff with no consistent cell time; not a tire calibration."""

        def calculate_forces(self, *args, **kwargs):
            states = super().calculate_forces(*args, **kwargs)
            if states.vehicle_speed_mps < 6.0:
                return states
            return replace(
                states,
                **{
                    name: replace(
                        state,
                        drive_force_n=0.0,
                        slip_ratio=0.0,
                        wheel_surface_speed_mps=states.vehicle_speed_mps,
                    )
                    for name, state in zip(TIRE_POSITIONS, states.all, strict=True)
                },
            )

    vehicle = Vehicle(initial_speed_mps=5.0, tire=DiscontinuousTire())
    before = vehicle.telemetry_snapshot()
    with pytest.raises(RuntimeError, match="internal timestep"):
        vehicle.update_state(Controls(motor_torque_request_nm=100.0), 5.0)
    assert vehicle.telemetry_snapshot() == before
