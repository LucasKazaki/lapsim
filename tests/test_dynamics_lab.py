"""Desktop maneuver settings and paired-run invariants without a display."""

from dataclasses import replace
from math import radians

import pytest

from lapsim.dynamics import PlanarVehicleConfig
from lapsim.ui.dynamics_lab import (
    SYNTHETIC_CONFIG,
    ManeuverSettings,
    run_maneuver_pair,
)


def example_settings() -> ManeuverSettings:
    return ManeuverSettings(
        config=PlanarVehicleConfig(**SYNTHETIC_CONFIG),
        initial_speed_mps=12.0,
        steering_angle_rad=radians(1.0),
        duration_s=1.0,
        output_step_s=0.01,
        torque_a_nm=(0.0, 0.0, 120.0, 120.0),
        torque_b_nm=(0.0, 0.0, 110.0, 130.0),
    )


def test_default_pair_uses_same_total_request_and_initial_state() -> None:
    settings = example_settings()
    assert sum(settings.torque_a_nm) == sum(settings.torque_b_nm)
    first, second = run_maneuver_pair(settings)
    assert first.times_s == second.times_s
    assert first.states[0] == second.states[0]
    assert len(first.states) == settings.step_count + 1
    assert second.states[-1].yaw_rate_rad_s > first.states[-1].yaw_rate_rad_s


def test_zero_step_maneuver_and_unequal_request_are_rejected() -> None:
    settings = example_settings()
    with pytest.raises(ValueError, match="1 to 2000 steps"):
        replace(settings, duration_s=1e-12)
    with pytest.raises(ValueError, match="equal total wheel torque"):
        replace(settings, torque_b_nm=(0.0, 0.0, 110.0, 131.0))


def test_unknown_scenario_is_rejected() -> None:
    with pytest.raises(ValueError, match="A or B"):
        example_settings().controls("C")
