"""The cell exit must respect the curvature still active in that cell."""

from __future__ import annotations

from math import atan

import pytest

from lapsim.core.controls import Controls
from lapsim.core.profiles import ConstantControlsProfile
from lapsim.courses.spatial_track import SpatialTrack
from lapsim.events.endurance import EnduranceRunConfig, EnduranceSimulator
from lapsim.optimization.torque_profile import PeriodicPiecewiseLinearTorqueProfile
from lapsim.profiles import build_vehicle, default_bundle_dir
from lapsim.solvers.path_constraints import PathConstraintSolver
from vehicle_model import Vehicle


def _corner_then_straight() -> SpatialTrack:
    # A short closed model fixture: the solver consumes the prescribed cell
    # curvature and station distance, not an inferred x/y steering path.
    return SpatialTrack(
        distance_m=(0.0, 5.0, 10.0),
        x_m=(0.0, 5.0, 0.0),
        y_m=(0.0, 0.0, 0.0),
        curvature_per_m=(0.1, 0.0),
        closed=True,
    )


@pytest.mark.parametrize("profile_id", ["prius_2026_le", "trev5_working_geometry"])
def test_automatic_driver_caps_current_corner_exit(profile_id: str) -> None:
    if profile_id.startswith("trev5_") and default_bundle_dir() is None:
        pytest.skip("optional ENME408 local evidence bundle is unavailable")
    track = _corner_then_straight()
    vehicle, _ = build_vehicle(profile_id)
    constraints = PathConstraintSolver().solve(track, vehicle)
    current_corner_limit = constraints.local_corner_speed_mps[0]
    assert constraints.braking_speed_ceiling_mps[1] > current_corner_limit
    profile = PeriodicPiecewiseLinearTorqueProfile(
        track_length_m=track.length_m,
        knot_distance_m=(0.0, 5.0),
        request_fraction_values=(1.0, 1.0),
    )
    result = EnduranceSimulator().run(
        vehicle,
        constraints,
        profile,
        EnduranceRunConfig(
            laps=1,
            starting_speed_mps=current_corner_limit - 0.2,
        ),
        record_telemetry=True,
    )

    assert result.completed, result.failure_reason
    assert result.telemetry is not None
    assert result.telemetry.sample_count == track.cell_count
    assert result.telemetry.speed_mps[0] <= current_corner_limit + 0.01
    assert result.telemetry.speed_mps[0] == pytest.approx(current_corner_limit, abs=1e-6)


def test_supplied_controls_reject_current_corner_exit_overspeed() -> None:
    track = _corner_then_straight()
    vehicle = Vehicle()
    constraints = PathConstraintSolver().solve(track, vehicle)
    current_corner_limit = constraints.local_corner_speed_mps[0]
    assert constraints.braking_speed_ceiling_mps[1] > current_corner_limit
    profile = ConstantControlsProfile(
        Controls(
            motor_torque_request_nm=1000.0,
            steering_angle_rad=atan(0.1 * vehicle.chassis.wheelbase_m),
        )
    )
    progress = []
    result = EnduranceSimulator().run(
        vehicle,
        constraints,
        profile,
        EnduranceRunConfig(
            laps=1,
            starting_speed_mps=current_corner_limit - 0.2,
        ),
        record_telemetry=True,
        progress_callback=progress.append,
    )

    assert not result.completed
    assert result.failure_reason is not None
    assert "current cell corner-speed limit" in result.failure_reason
    assert result.ending_speed_mps is not None
    assert result.ending_speed_mps > current_corner_limit + 0.01
    assert result.ending_speed_mps < constraints.braking_speed_ceiling_mps[1]
    assert result.telemetry is not None
    assert result.telemetry.sample_count == 0
    assert progress == []
