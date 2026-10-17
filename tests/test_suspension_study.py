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
        self.observations = []

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
        self.observations.append(self.steps)
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
    "settle_s,maneuver_s,logging_period_s",
    [
        # 2,001 regular exports plus the forced settling boundary.
        (1.0005, 0.9995, 0.001),
        # 2,000 regular exports plus both distinct forced boundaries.
        (1.0005, 0.999, 0.001),
        # The same 2,002-export overrun with a three-plant-tick log period.
        (1.0, 1.9995, 0.0015),
    ],
)
def test_sample_budget_rejects_forced_boundaries_beyond_2001(
    settle_s, maneuver_s, logging_period_s
):
    with pytest.raises(ValueError, match="sample budget"):
        SuspensionScenario(
            settle_s=settle_s,
            maneuver_s=maneuver_s,
            plant_step_s=0.0005,
            controller_period_s=0.001,
            logging_period_s=logging_period_s,
        )


@pytest.mark.parametrize(
    "settle_s,maneuver_s,logging_period_s,settle_tick,final_tick",
    [
        # All boundaries lie on the logging grid: 2,001 regular exports.
        (1.0, 1.0, 0.001, 2000, 4000),
        # 2,000 regular exports and only a forced final boundary.
        (1.0, 0.9995, 0.001, 2000, 3999),
        # 2,000 regular exports and only a forced settling boundary.
        (1.0, 1.9985, 0.0015, 2000, 5997),
        # 1,999 regular exports and both distinct forced boundaries.
        (1.0, 1.9975, 0.0015, 2000, 5995),
    ],
)
def test_exact_2001_sample_budget_accepts_regular_and_forced_boundaries(
    settle_s, maneuver_s, logging_period_s, settle_tick, final_tick
):
    scenario = SuspensionScenario(
        settle_s=settle_s,
        maneuver_s=maneuver_s,
        plant_step_s=0.0005,
        controller_period_s=0.001,
        logging_period_s=logging_period_s,
    )
    # ClockPlant verifies exported boundary behavior without native physics.
    result = run_study(scenario, plant_factory=ClockPlant)
    samples = result["payload"]["samples"]
    actual_ticks = [round(sample["time_s"] * 2000) for sample in samples]
    assert len(samples) == result["execution"]["logging_samples"] == 2001
    assert len(set(actual_ticks)) == 2001
    assert actual_ticks[0] == 0 and actual_ticks[-1] == final_tick
    assert settle_tick in actual_ticks


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
    assert results[0]["payload"]["metrics"] == results[1]["payload"]["metrics"]
    assert results[0]["payload"]["metrics"]["settle_samples"] == 1001
    assert [len(result["payload"]["samples"]) for result in results] == [111, 45]
    for plant in plants:
        assert [tick for tick in plant.observations if 1000 <= tick <= 2000] == list(
            range(1000, 2001)
        )


@pytest.mark.parametrize(
    "settings,trace_sha256",
    [
        (
            dict(settle_s=1.0, maneuver_s=0.1, plant_step_s=0.001, logging_period_s=0.01),
            "387f2b1786d65c02c06a08b6bcf37c9a51c423606f06e31bcf24570f05aed44a",
        ),
        (
            dict(settle_s=1.0, maneuver_s=0.1, plant_step_s=0.001, logging_period_s=0.025),
            "27a7a39a8e00e46f5cf1f5c3bf2ae6070f31635d660e1a6fd3e5974d3642e3eb",
        ),
        (
            dict(settle_s=1.003, maneuver_s=0.101, plant_step_s=0.001, logging_period_s=0.025),
            "58b1bb26f5e62749b327f8d374d40d628d81567db093de950b8dcd47a772d3bc",
        ),
        (
            dict(
                settle_s=1.0002,
                maneuver_s=0.1002,
                plant_step_s=0.0006,
                controller_period_s=0.0102,
                logging_period_s=0.024,
            ),
            "70c61bab00a8a506505045f91862767432aeb2fa140b04a7633625ed47794484",
        ),
    ],
)
def test_commands_and_exported_samples_match_pre_repair_frozen_trace(settings, trace_sha256):
    # Frozen from 135f6ed62a32e3e82f3bd3b82550f95359ec1cea before repair.
    # Covers every recorded field and command, not runtime/source identities.
    # ClockPlant is instrumentation, not native-physics acceptance evidence.
    result = run_study(SuspensionScenario(**settings), plant_factory=ClockPlant)
    trace = {key: result["payload"][key] for key in ("samples", "commands")}
    assert _content_id(trace) == trace_sha256


@pytest.mark.parametrize("logging_period_s", (0.01, 0.025))
@pytest.mark.parametrize("excursion", ("vertical_speed", "vertical_force", "left_right_load"))
def test_settle_gate_rejects_excursion_between_exported_samples(
    logging_period_s, excursion
):
    class ExcursionPlant(ClockPlant):
        def observe(self):
            sample = super().observe()
            if self.steps == 751:
                if excursion == "vertical_speed":
                    sample = replace(sample, velocity_mps=(1.0, 0.0, 0.02))
                elif excursion == "vertical_force":
                    sample = replace(
                        sample,
                        applied_wheel_force_world_n=((0.0, 0.0, 9.81 * 1.02 / 4),) * 4,
                    )
                else:
                    forces = list(sample.applied_wheel_force_world_n)
                    # Equal/opposite changes keep total vertical force correct.
                    forces[0] = (0.0, 0.0, 9.81 / 4 + 9.81 * 0.005)
                    forces[1] = (0.0, 0.0, 9.81 / 4 - 9.81 * 0.005)
                    sample = replace(sample, applied_wheel_force_world_n=tuple(forces))
            return sample

    plant = ExcursionPlant()
    scenario = SuspensionScenario(
        settle_s=1.0,
        maneuver_s=0.1,
        plant_step_s=0.001,
        logging_period_s=logging_period_s,
    )
    with pytest.raises(RuntimeError, match="not settled"):
        run_study(scenario, plant_factory=lambda: plant)
    assert plant.closed
    assert plant.steps == 1000
    assert all(command.braking == 0.2 for _, command in plant.commands)


@pytest.mark.parametrize("excursion_tick", (500, 1000))
def test_settle_window_includes_both_plant_boundary_endpoints(excursion_tick):
    class ExcursionPlant(ClockPlant):
        def observe(self):
            sample = super().observe()
            if self.steps == excursion_tick:
                return replace(sample, velocity_mps=(1.0, 0.0, 0.02))
            return sample

    plant = ExcursionPlant()
    with pytest.raises(RuntimeError, match="not settled"):
        run_study(
            SuspensionScenario(settle_s=1.0, maneuver_s=0.1, plant_step_s=0.001),
            plant_factory=lambda: plant,
        )
    assert plant.closed and plant.steps == 1000


@pytest.mark.parametrize("excursion_tick", (490, 1010))
def test_settle_gate_does_not_include_observations_outside_its_window(excursion_tick):
    class OutsideExcursion(ClockPlant):
        def observe(self):
            sample = super().observe()
            if self.steps == excursion_tick:
                return replace(sample, velocity_mps=(1.0, 0.0, 0.02))
            return sample

    result = run_study(
        SuspensionScenario(
            settle_s=1.0, maneuver_s=0.1, plant_step_s=0.001, logging_period_s=0.01
        ),
        plant_factory=OutsideExcursion,
    )
    assert result["payload"]["metrics"]["settle_acceptance"]["passed"]
    assert result["payload"]["metrics"]["settle_max_vertical_speed_mps"] == 0.0
    assert any(sample["velocity_mps"][2] == 0.02 for sample in result["payload"]["samples"])


def test_settle_summary_retains_a_valid_peak_not_present_in_exported_samples():
    class SubLimitPeak(ClockPlant):
        def observe(self):
            sample = super().observe()
            if self.steps == 751:
                return replace(sample, velocity_mps=(1.0, 0.0, 0.0095))
            return sample

    result = run_study(
        SuspensionScenario(settle_s=1.0, maneuver_s=0.1, plant_step_s=0.001),
        plant_factory=SubLimitPeak,
    )
    payload = result["payload"]
    assert payload["metrics"]["settle_max_vertical_speed_mps"] == 0.0095
    assert payload["metrics"]["settle_samples"] == 501
    assert all(sample["velocity_mps"][2] == 0.0 for sample in payload["samples"])


def test_settle_sampling_scope_reports_the_actual_grid_when_window_edge_is_off_grid():
    result = run_study(
        SuspensionScenario(
            settle_s=1.0002,
            maneuver_s=0.1002,
            plant_step_s=0.0006,
            controller_period_s=0.0102,
            logging_period_s=0.024,
        ),
        plant_factory=ClockPlant,
    )
    metrics = result["payload"]["metrics"]
    assert metrics["settle_window_s"] == pytest.approx([0.5002, 1.0002])
    assert metrics["settle_samples"] == 834
    assert metrics["settle_sampling"]["period_s"] == 0.0006
    assert metrics["settle_sampling"]["first_time_s"] == pytest.approx(0.5004)
    assert metrics["settle_sampling"]["last_time_s"] == pytest.approx(1.0002)
    assert metrics["settle_sampling"]["force_channel"] == "applied_wheel_force_world_n"


@pytest.mark.parametrize("failure", ("clock", "nonfinite"))
def test_unlogged_settling_observations_are_validated_and_close_on_error(failure):
    class InvalidObservation(ClockPlant):
        def observe(self):
            sample = super().observe()
            if self.steps == 751:
                if failure == "clock":
                    return replace(sample, time_s=99.0)
                return replace(sample, velocity_mps=(1.0, 0.0, float("nan")))
            return sample

    plant = InvalidObservation()
    expected = RuntimeError if failure == "clock" else ValueError
    with pytest.raises(expected):
        run_study(
            SuspensionScenario(settle_s=1.0, maneuver_s=0.1, plant_step_s=0.001),
            plant_factory=lambda: plant,
        )
    assert plant.closed and plant.steps == 751


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
