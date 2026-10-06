"""Optional per-cell tire grip stays aligned across path limits and laps."""

from dataclasses import FrozenInstanceError
from math import pi

import pytest

from lapsim.core.controls import Controls
from lapsim.core.profiles import ConstantControlsProfile
from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Track
from lapsim.events.endurance import EnduranceRunConfig, EnduranceSimulator
from lapsim.solvers.path_constraints import PathConstraintSolver, PathSpeedConstraints
from lapsim.ui.simulation import (
    prepare_one_lap_constraints,
    run_one_lap,
    run_speed_periodic_lap,
)
from vehicle_model import Vehicle


def _circle() -> SpatialTrack:
    return SpatialTrack.from_track(
        Track.from_segments([Curve(25.0, 2.0 * pi)]),
        maximum_cell_length_m=5.0,
    )


def _patch(track: SpatialTrack) -> tuple[float, ...]:
    return tuple(
        0.7 if 8 <= index < 12 else 1.0
        for index in range(track.cell_count)
    )


@pytest.mark.parametrize(
    "values",
    (
        (1.0, 1.0, 1.0),
        [1.0, 1.0, 1.0, 1.0],
        (1.0, 1.0, True, 1.0),
        (1.0, 1.0, 0.0, 1.0),
        (1.0, 1.0, -0.1, 1.0),
        (1.0, 1.0, float("nan"), 1.0),
        (1.0, 1.0, float("inf"), 1.0),
    ),
)
def test_cell_grip_schedule_requires_immutable_positive_values(values: object) -> None:
    track = SpatialTrack.from_cells(
        cell_length_m=(1.0,) * 4,
        curvature_per_m=(0.01,) * 4,
    )
    with pytest.raises(ValueError, match="cell road grip"):
        PathConstraintSolver().solve(
            track, Vehicle(), cell_road_grip_multiplier=values,
        )
    with pytest.raises(ValueError, match="cell road grip"):
        PathSpeedConstraints(
            track=track,
            local_corner_speed_mps=(10.0,) * track.cell_count,
            braking_speed_ceiling_mps=(10.0,) * track.cell_count,
            passes=1,
            cell_road_grip_multiplier=values,
        )


def test_solver_uses_each_cell_grip_for_corner_and_backward_seam() -> None:
    track = SpatialTrack.from_cells(
        cell_length_m=(1.0,) * 4,
        curvature_per_m=(0.01, 0.015, 0.02, 0.025),
    )
    schedule = (1.0, 0.9, 0.8, 0.7)
    solver = PathConstraintSolver()
    observed_corners: list[tuple[float, float]] = []
    observed_braking: list[tuple[float, float]] = []
    corner_limit = solver.local_corner_speed_limit_mps

    def corner_spy(vehicle: Vehicle, curvature_per_m: float) -> float:
        observed_corners.append(
            (curvature_per_m, vehicle.tire.road_grip_multiplier)
        )
        return corner_limit(vehicle, curvature_per_m)

    def braking_spy(*, vehicle: Vehicle, curvature_per_m: float,
                    local_speed_limit_mps: float, **_unused: object) -> float:
        observed_braking.append(
            (curvature_per_m, vehicle.tire.road_grip_multiplier)
        )
        return local_speed_limit_mps

    solver.local_corner_speed_limit_mps = corner_spy
    solver._maximum_entry_speed_mps = braking_spy
    vehicle = Vehicle()
    base_grip = vehicle.tire.road_grip_multiplier
    constraints = solver.solve(
        track, vehicle, cell_road_grip_multiplier=schedule,
    )

    expected = list(zip(track.curvature_per_m, schedule, strict=True))
    assert observed_corners == expected
    assert observed_braking[:track.cell_count] == list(reversed(expected))
    assert observed_braking[-1] == expected[-1]  # cyclic seam recheck
    assert vehicle.tire.road_grip_multiplier == base_grip
    assert constraints.cell_road_grip_multiplier is schedule
    with pytest.raises(FrozenInstanceError):
        constraints.cell_road_grip_multiplier = None


def test_lower_grip_reduces_corner_and_upstream_braking_ceiling() -> None:
    track = _circle()
    solver = PathConstraintSolver()
    uniform = solver.solve(track, Vehicle())
    schedule = tuple(
        0.55 if index == 0 else 1.0
        for index in range(track.cell_count)
    )
    scheduled = solver.solve(
        track, Vehicle(), cell_road_grip_multiplier=schedule,
    )

    assert scheduled.local_corner_speed_mps[0] < uniform.local_corner_speed_mps[0]
    assert (
        scheduled.braking_speed_ceiling_mps[-1]
        < uniform.braking_speed_ceiling_mps[-1]
    )


def test_solver_restores_reference_grip_if_cell_prepass_raises() -> None:
    track = _circle()
    vehicle = Vehicle()
    vehicle.tire.road_grip_multiplier = 0.85
    solver = PathConstraintSolver()
    seen = 0

    def fail_after_first_cell(_vehicle: Vehicle, _curvature: float) -> float:
        nonlocal seen
        seen += 1
        if seen == 2:
            raise RuntimeError("corner prepass stopped")
        return 10.0

    solver.local_corner_speed_limit_mps = fail_after_first_cell
    with pytest.raises(RuntimeError, match="corner prepass stopped"):
        solver.solve(
            track, vehicle, cell_road_grip_multiplier=_patch(track),
        )
    assert vehicle.tire.road_grip_multiplier == 0.85


def test_scheduled_lap_records_grip_and_restores_vehicle() -> None:
    track = _circle()
    schedule = _patch(track)
    vehicle = Vehicle()
    reference_grip = vehicle.tire.road_grip_multiplier
    result = run_one_lap(
        vehicle, track, torque_request_fraction=0.8,
        cell_road_grip_multiplier=schedule,
    )

    assert result.completed, result.failure_reason
    assert result.telemetry is not None
    assert result.telemetry["tire.road_grip_multiplier"] == schedule
    assert vehicle.tire.road_grip_multiplier == reference_grip
    assert vehicle.drivetrain.tire is vehicle.tire
    dry = run_one_lap(Vehicle(), track, torque_request_fraction=0.8)
    assert result.driving_time_s > dry.driving_time_s


def test_uniform_default_matches_explicit_unit_schedule_exactly() -> None:
    track = _circle()
    default = run_one_lap(Vehicle(), track, torque_request_fraction=0.8)
    scheduled = run_one_lap(
        Vehicle(), track, torque_request_fraction=0.8,
        cell_road_grip_multiplier=(1.0,) * track.cell_count,
    )

    assert default.completed and scheduled.completed
    assert default.driving_time_s == scheduled.driving_time_s
    assert default.pack_energy_kwh == scheduled.pack_energy_kwh
    assert default.telemetry is not None and scheduled.telemetry is not None
    assert default.telemetry.as_dict() == scheduled.telemetry.as_dict()


def test_prepared_schedule_is_reused_and_conflicting_schedule_rejected() -> None:
    track = _circle()
    schedule = _patch(track)
    vehicle = Vehicle()
    prepared = prepare_one_lap_constraints(
        vehicle, track, cell_road_grip_multiplier=schedule,
    )
    assert prepared._limits.cell_road_grip_multiplier == schedule
    with pytest.raises(ValueError, match="different cell road grip"):
        run_one_lap(
            vehicle, track, torque_request_fraction=0.8,
            constraints=prepared,
            cell_road_grip_multiplier=(1.0,) * track.cell_count,
        )
    result = run_one_lap(
        vehicle, track, torque_request_fraction=0.8, constraints=prepared,
    )
    assert result.completed, result.failure_reason
    assert result.telemetry is not None
    assert result.telemetry["tire.road_grip_multiplier"] == schedule


def test_scheduled_grip_restored_after_failed_run_and_exception() -> None:
    track = _circle()
    schedule = _patch(track)
    vehicle = Vehicle()
    vehicle.tire.road_grip_multiplier = 0.85
    constraints = PathConstraintSolver().solve(
        track, vehicle, cell_road_grip_multiplier=schedule,
    )
    failure = EnduranceSimulator().run(
        vehicle, constraints,
        ConstantControlsProfile(Controls(steering_angle_rad=0.0)),
        EnduranceRunConfig(laps=1, starting_speed_mps=5.0),
    )
    assert not failure.completed
    assert failure.failed_cell_index == 0
    assert vehicle.tire.road_grip_multiplier == 0.85

    class RaisingControls:
        def controls_at(self, distance_m: float) -> Controls:
            raise RuntimeError(f"controls failed at {distance_m}")

    with pytest.raises(RuntimeError, match="controls failed"):
        EnduranceSimulator().run(
            vehicle, constraints, RaisingControls(),
            EnduranceRunConfig(laps=1, starting_speed_mps=5.0),
        )
    assert vehicle.tire.road_grip_multiplier == 0.85


def test_speed_periodic_passes_use_one_frozen_schedule_and_restore_cars() -> None:
    track = _circle()
    schedule = _patch(track)
    source = Vehicle()
    source.tire.road_grip_multiplier = 0.95
    result = run_speed_periodic_lap(
        source, track, torque_request_fraction=0.8,
        cell_road_grip_multiplier=schedule,
    )

    assert result.converged, result.failure_reason
    assert result.passes == 2
    assert result.run.telemetry is not None
    assert result.run.telemetry["tire.road_grip_multiplier"] == schedule
    assert source.tire.road_grip_multiplier == 0.95
    assert result.vehicle.tire.road_grip_multiplier == 0.95
