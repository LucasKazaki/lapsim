"""Constraint progress is exact observed work and does not alter physics."""

from __future__ import annotations

from math import pi

import pytest

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Track
from lapsim.solvers.path_constraints import (
    PathConstraintProgressSnapshot,
    PathConstraintSolver,
)
from lapsim.ui.simulation import (
    prepare_one_lap_constraints,
    run_one_lap,
    run_speed_periodic_lap,
)
from vehicle_model import Vehicle


def _track() -> SpatialTrack:
    return SpatialTrack.from_track(
        Track.from_segments([Curve(25.0, 2.0 * pi)]),
        maximum_cell_length_m=5.0,
    )


def _assert_solver_snapshots(
    snapshots: list[PathConstraintProgressSnapshot],
    track: SpatialTrack,
    maximum_passes: int = 500,
) -> None:
    assert snapshots
    assert all(snapshot.cell_count == track.cell_count for snapshot in snapshots)
    assert all(
        snapshot.maximum_passes == maximum_passes for snapshot in snapshots
    )
    assert snapshots[0].phase == "local_limits"
    assert snapshots[0].pass_number is None
    assert snapshots[0].completed_cells == 1
    assert any(
        snapshot.phase == "local_limits"
        and snapshot.completed_cells == track.cell_count
        for snapshot in snapshots
    )
    braking = [
        snapshot for snapshot in snapshots
        if snapshot.phase == "cyclic_braking"
    ]
    assert braking
    assert braking[0].pass_number == 1
    assert braking[0].completed_cells == 1
    pass_numbers = sorted({snapshot.pass_number for snapshot in braking})
    assert pass_numbers == list(range(1, pass_numbers[-1] + 1))
    for pass_number in pass_numbers:
        counts = [
            snapshot.completed_cells for snapshot in braking
            if snapshot.pass_number == pass_number
        ]
        assert counts == sorted(counts)
        assert counts[-1] == track.cell_count


def test_path_constraint_progress_matches_actual_cells_and_preserves_limits() -> None:
    track = _track()
    snapshots: list[PathConstraintProgressSnapshot] = []
    observed = PathConstraintSolver().solve(
        track, Vehicle(), progress_callback=snapshots.append,
    )
    reference = PathConstraintSolver().solve(track, Vehicle())

    _assert_solver_snapshots(snapshots, track)
    assert snapshots[-1].pass_number == observed.passes
    assert observed == reference


def test_scheduled_grip_callback_restores_vehicle_even_if_observer_fails() -> None:
    track = _track()
    vehicle = Vehicle()
    initial_grip = vehicle.tire.road_grip_multiplier
    schedule = (0.8,) * track.cell_count
    snapshots: list[PathConstraintProgressSnapshot] = []

    observed = PathConstraintSolver().solve(
        track, vehicle,
        cell_road_grip_multiplier=schedule,
        progress_callback=snapshots.append,
    )
    reference = PathConstraintSolver().solve(
        track, Vehicle(), cell_road_grip_multiplier=schedule,
    )
    _assert_solver_snapshots(snapshots, track)
    assert observed == reference
    assert vehicle.tire.road_grip_multiplier == initial_grip

    def fail(_: PathConstraintProgressSnapshot) -> None:
        raise RuntimeError("observer failed")

    with pytest.raises(RuntimeError, match="observer failed"):
        PathConstraintSolver().solve(
            track, vehicle,
            cell_road_grip_multiplier=schedule,
            progress_callback=fail,
        )
    assert vehicle.tire.road_grip_multiplier == initial_grip


def test_desktop_lap_has_constraint_then_accepted_cell_progress() -> None:
    track = _track()
    events: list[tuple[str, object]] = []
    observed = run_one_lap(
        Vehicle(), track, torque_request_fraction=0.8,
        constraint_progress_callback=lambda snapshot: events.append((
            "constraint", snapshot,
        )),
        progress_callback=lambda snapshot: events.append(("lap", snapshot)),
    )
    reference = run_one_lap(Vehicle(), track, torque_request_fraction=0.8)

    assert observed.completed and reference.completed
    assert events[0][0] == "constraint"
    assert events[-1][0] == "lap"
    assert len([event for event in events if event[0] == "lap"]) == track.cell_count
    assert observed.lap_times_s == reference.lap_times_s
    assert observed.pack_energy_kwh == reference.pack_energy_kwh
    assert observed.telemetry == reference.telemetry


def test_prepared_limits_do_not_emit_a_second_constraint_progress_stream() -> None:
    track = _track()
    vehicle = Vehicle()
    snapshots: list[PathConstraintProgressSnapshot] = []
    prepared = prepare_one_lap_constraints(
        vehicle, track, constraint_progress_callback=snapshots.append,
    )
    prepared_count = len(snapshots)
    assert prepared_count > 0

    result = run_one_lap(
        vehicle, track, torque_request_fraction=0.8,
        constraints=prepared, constraint_progress_callback=snapshots.append,
    )
    assert result.completed
    assert len(snapshots) == prepared_count


def test_speed_periodic_constraint_progress_precedes_final_lap_only() -> None:
    track = _track()
    constraint_snapshots: list[PathConstraintProgressSnapshot] = []
    lap_snapshots = []
    result = run_speed_periodic_lap(
        Vehicle(), track, torque_request_fraction=0.8,
        constraint_progress_callback=constraint_snapshots.append,
        progress_callback=lap_snapshots.append,
    )

    assert result.converged, result.failure_reason
    _assert_solver_snapshots(constraint_snapshots, track, maximum_passes=120)
    assert len(lap_snapshots) == track.cell_count
