"""Desktop maneuver settings and paired-run invariants without a display."""

from dataclasses import replace
from math import radians
import queue

import pytest

from lapsim.dynamics import (
    PlanarEnvironment,
    PlanarRoad,
    PlanarVehicleConfig,
    RectangularGripPatch,
)
from lapsim.ui.dynamics_lab import (
    DynamicsLab,
    SYNTHETIC_CONFIG,
    ManeuverSettings,
    run_maneuver_pair,
)
from lapsim.experiments.dynamics_record import DynamicsComparisonRecord


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


def test_pair_uses_identical_wind_and_contact_patch_for_both_scenarios() -> None:
    settings = replace(
        example_settings(),
        environment=PlanarEnvironment(
            wind_world_x_mps=-5.0,
            drag_area_m2=0.8,
            road=PlanarRoad(patches=(
                RectangularGripPatch(-1.0, 1.0, -1.0, 0.0, 0.6),
            )),
        ),
    )
    first, second = run_maneuver_pair(settings)
    for run in (first, second):
        initial = run.evaluations[0]
        assert initial.apparent_air_speed_mps == pytest.approx(17.0)
        assert initial.aero_body_force_x_n < 0.0
        assert [wheel.road_friction_multiplier for wheel in initial.wheels] == [
            1.0, 0.6, 1.0, 0.6,
        ]
        assert run.road_valid
    assert first.evaluations[0].aero_body_force_x_n == second.evaluations[0].aero_body_force_x_n


def test_lab_worker_saves_exact_ab_conditions(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "lapsim.ui.dynamics_lab.default_dynamics_run_directory", lambda: tmp_path,
    )
    lab = DynamicsLab.__new__(DynamicsLab)
    lab.result_queue = queue.Queue()
    settings = example_settings()
    lab._calculate(settings)
    returned_settings, runs, record_id, error = lab.result_queue.get_nowait()
    assert error is None
    assert returned_settings == settings
    assert runs is not None
    record = DynamicsComparisonRecord.load(tmp_path / f"{record_id}.json")
    payload = record.to_dict()
    assert payload["inputs"]["environment"]["drag_area_m2"] == 0.0
    assert payload["runs"]["A"]["states"][-1]["yaw_rate_rad_s"] == pytest.approx(
        runs[0].states[-1].yaw_rate_rad_s,
    )
