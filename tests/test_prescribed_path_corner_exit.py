"""Coarse timed-event cells cannot bypass lateral corner capacity."""

from math import pi

import pytest

from lapsim import (
    ConstantControlsProfile,
    Controls,
    SkidpadConfig,
    SpatialTrack,
    simulate_skidpad,
)
from lapsim.courses.track import Curve, Track
from lapsim.solvers.path_constraints import PathConstraintSolver
from vehicle_model import Vehicle


def _circle(radius_m: float, maximum_cell_length_m: float) -> SpatialTrack:
    return SpatialTrack.from_track(
        Track.from_segments([Curve(radius_m, 2.0 * pi)]),
        maximum_cell_length_m=maximum_cell_length_m,
    )


@pytest.mark.parametrize("maximum_cell_length_m, expected_cells", [(40.0, 1), (10.0, 4)])
def test_standing_start_coarse_circle_cannot_score_above_corner_limit(
    maximum_cell_length_m: float,
    expected_cells: int,
) -> None:
    track = _circle(5.0, maximum_cell_length_m)
    assert track.cell_count == expected_cells
    vehicle = Vehicle()
    corner_limit_mps = PathConstraintSolver().local_corner_speed_limit_mps(
        vehicle, 1.0 / 5.0,
    )

    result = simulate_skidpad(
        vehicle,
        track,
        ConstantControlsProfile(Controls(motor_torque_request_nm=230.0)),
        config=SkidpadConfig(
            warmup_laps=0,
            scored_laps=1,
            starting_speed_mps=0.0,
        ),
    )

    assert vehicle.speed_mps > corner_limit_mps + 0.01
    assert not result.completed
    assert result.estimated_points == 0.0
    assert result.scoring_time_s is None
    assert result.completed_laps == 0
    assert result.failure_reason is not None
    assert "exited prescribed path above corner-speed limit" in result.failure_reason
    assert "lap 1, cell 0" in result.failure_reason


def test_within_corner_capacity_still_scores_skidpad() -> None:
    track = _circle(25.0, 5.0)
    result = simulate_skidpad(
        Vehicle(),
        track,
        ConstantControlsProfile(Controls(motor_torque_request_nm=5.0)),
        config=SkidpadConfig(
            warmup_laps=1,
            scored_laps=1,
            starting_speed_mps=5.0,
        ),
    )

    assert result.completed, result.failure_reason
    assert result.completed_laps == 2
    assert result.scoring_time_s == result.lap_times_s[-1]
    assert result.estimated_points > 0.0
