"""Clock/record contracts independent of the optional native engine."""

import sys
from dataclasses import asdict, replace

import pytest

from lapsim.dynamics.native_plant import (
    AxleCommand,
    PlantCapabilities,
    PlantObservation,
)
from lapsim.experiments.dynamics_record import _content_id
from lapsim.experiments.suspension_study import (
    StudyCancelled,
    SuspensionScenario,
    _compare,
    replay_study,
    run_study,
)


class ClockPlant:
    """An instrumented clock, not a physics surrogate or native acceptance test."""

    capabilities = PlantCapabilities(
        "clock_fixture", "none", "CPU", "fixture", "none", "none"
    )

    def __init__(self):
        self.time = 0.0
        self.command = AxleCommand()
        self.applied = AxleCommand()
        self.closed = False
        self.steps = 0
        self.commands = []

    def reset(self):
        self.time = 0.0

    def set_command(self, command):
        self.command = command
        self.commands.append((self.time, command))

    def advance(self, step):
        self.time += step
        self.steps += 1
        self.applied = self.command

    def observe(self):
        return PlantObservation(
            time_s=self.time,
            tire_force_source_time_s=None,
            tire_kinematics_source_time_s=None,
            applied_tire_force_source_time_s=None,
            applied_tire_force_geometry_time_s=self.time,
            position_m=(self.time, 0.0, 1.0),
            velocity_mps=(1.0, 0.0, 0.0),
            cardan_xyz_rad=(0.0,) * 3,
            heading_rad=0.0,
            angular_velocity_rad_s=(0.0,) * 3,
            mass_kg=1.0,
            wheel_position_m=((0.0,) * 3,) * 4,
            wheel_omega_rad_s=(0.0,) * 4,
            native_axle_shaft_omega_rad_s=(0.0,) * 4,
            wheel_force_world_n=((0.0, 0.0, 9.81 / 4),) * 4,
            applied_wheel_force_world_n=((0.0, 0.0, 9.81 / 4),) * 4,
            tire_slip_ratio=(0.0,) * 4,
            tire_slip_angle_rad=(0.0,) * 4,
            suspension_spring_length_m=(0.5,) * 4,
            suspension_spring_force_n=(0.0,) * 4,
            suspension_damper_force_n=(0.0,) * 4,
            driveline_wheel_torque_nm=(0.0,) * 4,
            command=self.applied,
        )

    def provenance(self):
        return {"fixture": "clock only"}

    def close(self):
        self.closed = True


@pytest.mark.parametrize(
    "field,value",
    [
        ("plant_step_s", True),
        ("plant_step_s", 0.0),
        ("plant_step_s", float("nan")),
        ("plant_step_s", 0.003),
        ("controller_period_s", 0.01025),
        ("logging_period_s", 0.0005),
        ("settle_s", float("inf")),
        ("scenario_id", "team_car"),
        ("driveshaft_torque_nm", -1),
        ("steering", 1.0),
    ],
)
def test_scenario_rejects_invalid_or_unbounded_work(field, value):
    with pytest.raises(ValueError):
        SuspensionScenario(**{field: value})


@pytest.mark.parametrize(
    "field,value",
    [("braking", True), ("steering", float("nan")), ("driveshaft_torque_nm", 401)],
)
def test_command_rejects_invalid_authority(field, value):
    with pytest.raises(ValueError):
        AxleCommand(**{field: value})


def test_integer_clock_and_prior_interval_command_are_recorded():
    plant = ClockPlant()
    scenario = SuspensionScenario(
        settle_s=1.0, maneuver_s=0.1, settle_braking=0.2, plant_step_s=0.001
    )
    result = run_study(scenario, plant_factory=lambda: plant)
    assert plant.closed
    assert plant.steps == 1100
    assert len(plant.commands) == 110
    assert len(result["payload"]["samples"]) == 56
    samples = result["payload"]["samples"]
    assert samples[0]["command"]["braking"] == 0.0  # no completed interval yet
    assert samples[1]["command"]["braking"] == 0.2
    # The state at the ramp's first tick was produced by the settling command.
    assert samples[50]["time_s"] == pytest.approx(1.0)
    assert samples[50]["command"]["braking"] == 0.2
    assert result["execution"]["controller_calls"] == 110


def test_observation_rate_does_not_change_clock_or_command_calls():
    scenario = SuspensionScenario(settle_s=1.0, maneuver_s=0.1)
    plants = [ClockPlant(), ClockPlant()]
    results = [
        run_study(
            replace(scenario, logging_period_s=period),
            plant_factory=lambda plant=plant: plant,
        )
        for plant, period in zip(plants, (0.01, 0.025))
    ]
    assert plants[0].commands == plants[1].commands
    assert plants[0].steps == plants[1].steps
    assert results[0]["payload"]["samples"][-1] == results[1]["payload"]["samples"][-1]


def test_cancel_closes_plant_and_returns_no_record():
    plant = ClockPlant()
    with pytest.raises(StudyCancelled, match="tick 7"):
        run_study(
            SuspensionScenario(),
            cancel=lambda: plant.steps >= 7,
            plant_factory=lambda: plant,
        )
    assert plant.closed
    assert plant.steps == 7


def test_pre_cancel_never_constructs_optional_backend():
    def unexpected():
        pytest.fail("cancelled study initialized the backend")

    with pytest.raises(StudyCancelled, match="before initialization"):
        run_study(SuspensionScenario(), cancel=lambda: True, plant_factory=unexpected)


def test_bad_clock_closes_backend():
    class WrongClock(ClockPlant):
        def observe(self):
            return replace(super().observe(), time_s=99)

    plant = WrongClock()
    with pytest.raises(RuntimeError, match="clock diverged"):
        run_study(SuspensionScenario(), plant_factory=lambda: plant)
    assert plant.closed


def test_nonfinite_solver_output_closes_backend():
    class Nonfinite(ClockPlant):
        def observe(self):
            return replace(super().observe(), position_m=(float("nan"), 0.0, 0.0))

    plant = Nonfinite()
    with pytest.raises(ValueError):
        run_study(SuspensionScenario(), plant_factory=lambda: plant)
    assert plant.closed


def test_missing_native_backend_is_actionable_and_never_falls_back(monkeypatch):
    from lapsim.dynamics.chrono_vehicle import ChronoVehiclePlant

    monkeypatch.setitem(sys.modules, "pychrono", None)
    with pytest.raises(RuntimeError, match="no fast-model fallback"):
        ChronoVehiclePlant()


def test_forged_record_rejected_before_backend_construction():
    result = run_study(
        SuspensionScenario(settle_s=1.0, maneuver_s=0.1), plant_factory=ClockPlant
    )
    result["payload"]["samples"][-1]["position_m"] = [1e6, 0, 0]
    with pytest.raises(ValueError, match="receipt hash"):
        replay_study(result)


def test_replay_comparison_rejects_added_fields_and_nonfinite_values():
    with pytest.raises(ValueError):
        _compare({"a": [0.0]}, {"a": [0.0], "b": True})
    with pytest.raises(ValueError):
        _compare(float("nan"), float("nan"))
    _compare(
        asdict(AxleCommand()),
        {"driveshaft_torque_nm": 0.0, "steering": 0.0, "braking": 0.0},
    )


def _reseal(record):
    record["content_id"] = _content_id(record["payload"])
    record["receipt_id"] = _content_id(
        {key: value for key, value in record.items() if key != "receipt_id"}
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("gpu_physics", True),
        ("device", "CUDA"),
        ("controller_calls", 1),
        ("plant_steps", 1),
        ("logging_samples", 0),
        ("process_cpu_s", -1),
        ("total_wall_s", 10**1000),
        ("process_lifetime_peak_working_set_bytes", True),
    ],
)
def test_resealed_false_execution_claim_rejected_before_native_work(field, value):
    record = run_study(
        SuspensionScenario(settle_s=1.0, maneuver_s=0.1), plant_factory=ClockPlant
    )
    record["execution"][field] = value
    _reseal(record)
    with pytest.raises(ValueError, match="[Ee]xecution|measurement|working-set"):
        replay_study(record)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(extra=None),
        lambda payload: payload.update(source=None),
        lambda payload: payload["source"].update(code_commit=123),
        lambda payload: payload["source"].update(dirty_worktree="false"),
    ],
)
def test_resealed_malformed_shape_rejected_cleanly(mutate):
    record = run_study(
        SuspensionScenario(settle_s=1.0, maneuver_s=0.1), plant_factory=ClockPlant
    )
    mutate(record["payload"])
    _reseal(record)
    with pytest.raises(ValueError):
        replay_study(record)


def test_wrong_scenario_type_does_not_initialize_backend():
    def unexpected():
        pytest.fail("invalid scenario initialized native resources")

    with pytest.raises(TypeError, match="SuspensionScenario"):
        run_study({}, plant_factory=unexpected)


def test_replay_numeric_comparison_reports_huge_integer_cleanly():
    with pytest.raises(ValueError, match="Replay differs"):
        _compare(10**1000, 1.0)
