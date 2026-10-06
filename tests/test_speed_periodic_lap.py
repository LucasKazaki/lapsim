"""Bounded, opt-in speed-only shooting for a closed desktop lap."""

from math import pi
from unittest.mock import patch

import pytest

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Track
from lapsim.events.endurance import EnduranceRunResult, LapProgressSnapshot
from lapsim.solvers.path_constraints import PathSpeedConstraints
from lapsim.ui.simulation import run_speed_periodic_lap
from vehicle_model import Vehicle


def _track() -> SpatialTrack:
    return SpatialTrack.from_track(
        Track.from_segments([Curve(25.0, 2.0 * pi)]),
        maximum_cell_length_m=5.0,
    )


def _fake_constraints(track: SpatialTrack) -> PathSpeedConstraints:
    return PathSpeedConstraints(
        track=track,
        local_corner_speed_mps=(10.0,) * track.cell_count,
        braking_speed_ceiling_mps=(10.0,) * track.cell_count,
        passes=1,
    )


def test_two_pass_shooting_reuses_initial_state_and_only_streams_final_pass() -> None:
    track = _track()
    original = Vehicle()
    original.battery.initial_state_of_charge = 0.8
    original.battery.reset_state()
    original_mass_kg = original.mass_kg
    observed = []
    calls = []
    exit_speeds_mps = (8.0, 8.0)

    def fake_run(self, trial, constraints, profile, config, *,
                 record_telemetry=False, progress_callback=None):
        del self, constraints, profile
        index = len(calls)
        calls.append((
            id(trial), trial.mass_kg, trial.battery.state_of_charge,
            config.starting_speed_mps, record_telemetry,
            progress_callback is not None,
        ))
        trial.speed_mps = exit_speeds_mps[index]
        trial.mass_kg += 100.0
        trial.battery.state_of_charge = 0.1
        if progress_callback is not None:
            progress_callback(LapProgressSnapshot(
                lap_index=0, cell_index=track.cell_count - 1,
                cell_count=track.cell_count, elapsed_time_s=12.0,
                lap_station_m=track.length_m,
                total_distance_m=track.length_m,
                speed_mps=trial.speed_mps,
                lateral_acceleration_mps2=0.0,
            ))
        return EnduranceRunResult(
            completed_laps=1, driving_time_s=12.0, lap_times_s=(12.0,),
            pack_energy_kwh=0.1, final_state_of_charge=0.1,
            failure_reason=None, telemetry=None,
            starting_speed_mps=config.starting_speed_mps,
            ending_speed_mps=trial.speed_mps,
        )

    with patch("lapsim.ui.simulation.PathConstraintSolver.solve",
               return_value=_fake_constraints(track)) as solve, patch(
        "lapsim.ui.simulation.EnduranceSimulator.run", new=fake_run,
    ):
        result = run_speed_periodic_lap(
            original, track, torque_request_fraction=0.8,
            progress_callback=observed.append,
        )

    assert solve.call_count == 1
    assert result.converged
    assert result.failure_reason is None
    assert result.passes == 2
    assert result.final_starting_speed_mps == 8.0
    assert result.speed_residual_mps == 0.0
    assert result.vehicle.speed_mps == 8.0
    assert len(observed) == 1
    assert [item[3:] for item in calls] == [
        (10.0, False, False), (8.0, True, True),
    ]
    assert calls[0][0] != calls[1][0]
    assert all(item[1] == original_mass_kg and item[2] == 0.8 for item in calls)
    assert original.mass_kg == original_mass_kg
    assert original.battery.state_of_charge == 0.8


def test_third_pass_reports_nonconvergence_without_claiming_periodicity() -> None:
    track = _track()
    speeds = iter((9.0, 8.0, 7.0))
    callbacks = []
    calls = []

    def fake_run(self, trial, constraints, profile, config, *,
                 record_telemetry=False, progress_callback=None):
        del self, constraints, profile
        trial.speed_mps = next(speeds)
        calls.append((config.starting_speed_mps, record_telemetry,
                      progress_callback is not None))
        if progress_callback is not None:
            progress_callback("final")
        return EnduranceRunResult(
            completed_laps=1, driving_time_s=10.0, lap_times_s=(10.0,),
            pack_energy_kwh=0.1, final_state_of_charge=0.8,
            failure_reason=None, telemetry=None,
            starting_speed_mps=config.starting_speed_mps,
            ending_speed_mps=trial.speed_mps,
        )

    with patch("lapsim.ui.simulation.PathConstraintSolver.solve",
               return_value=_fake_constraints(track)), patch(
        "lapsim.ui.simulation.EnduranceSimulator.run", new=fake_run,
    ):
        result = run_speed_periodic_lap(
            Vehicle(), track, torque_request_fraction=0.8,
            maximum_lap_passes=3, progress_callback=callbacks.append,
        )

    assert calls == [
        (10.0, False, False), (9.0, False, False), (8.0, True, True),
    ]
    assert callbacks == ["final"]
    assert result.passes == 3
    assert result.speed_residual_mps == -1.0
    assert not result.converged
    assert "did not converge" in result.failure_reason


def test_failed_probe_returns_failure_without_emitting_progress() -> None:
    track = _track()
    observed = []

    def failed_run(self, trial, constraints, profile, config, *,
                   record_telemetry=False, progress_callback=None):
        del self, trial, constraints, profile, record_telemetry, progress_callback
        return EnduranceRunResult(
            completed_laps=0, driving_time_s=0.1, lap_times_s=(),
            pack_energy_kwh=0.0, final_state_of_charge=1.0,
            failure_reason="vehicle stalled", telemetry=None,
            starting_speed_mps=config.starting_speed_mps,
            ending_speed_mps=0.0,
        )

    with patch("lapsim.ui.simulation.PathConstraintSolver.solve",
               return_value=_fake_constraints(track)), patch(
        "lapsim.ui.simulation.EnduranceSimulator.run", new=failed_run,
    ):
        result = run_speed_periodic_lap(
            Vehicle(), track, torque_request_fraction=0.8,
            progress_callback=observed.append,
        )

    assert result.passes == 1
    assert not result.converged
    assert result.failure_reason == "vehicle stalled"
    assert observed == []


def test_real_closed_circle_solves_once_and_records_speed_periodic_final_lap() -> None:
    track = _track()
    original = Vehicle()
    progress = []

    result = run_speed_periodic_lap(
        original, track, torque_request_fraction=0.8,
        progress_callback=progress.append,
    )

    assert result.converged, result.failure_reason
    assert result.passes == 2
    assert result.run.telemetry is not None
    assert len(result.run.telemetry["vehicle.speed_mps"]) == track.cell_count
    assert len(progress) == track.cell_count
    assert progress[-1].speed_mps == result.run.ending_speed_mps
    assert progress[-1].elapsed_time_s == result.run.driving_time_s
    assert result.vehicle.speed_mps == result.run.ending_speed_mps
    assert original.distance_m == 0.0


@pytest.mark.parametrize("tolerance", (0.0, -1.0, float("inf"), float("nan")))
def test_rejects_invalid_tolerance(tolerance: float) -> None:
    with pytest.raises(ValueError, match="speed_tolerance_mps"):
        run_speed_periodic_lap(
            Vehicle(), _track(), torque_request_fraction=0.8,
            speed_tolerance_mps=tolerance,
        )


@pytest.mark.parametrize("passes", (1, 4, 2.5, True))
def test_rejects_invalid_pass_cap(passes: object) -> None:
    with pytest.raises(ValueError, match="maximum_lap_passes"):
        run_speed_periodic_lap(
            Vehicle(), _track(), torque_request_fraction=0.8,
            maximum_lap_passes=passes,
        )


def test_rejects_open_course() -> None:
    open_track = SpatialTrack(
        distance_m=(0.0, 1.0), x_m=(0.0, 1.0), y_m=(0.0, 0.0),
        curvature_per_m=(0.0,), closed=False,
    )
    with pytest.raises(ValueError, match="closed course"):
        run_speed_periodic_lap(
            Vehicle(), open_track, torque_request_fraction=0.8,
        )
