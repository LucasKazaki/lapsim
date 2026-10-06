"""The cell exit must respect the curvature still active in that cell."""

from __future__ import annotations

from copy import deepcopy
from math import atan, pi

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
    # The combined-force guard now leaves room for propulsion at the exit.
    assert result.telemetry.speed_mps[0] < current_corner_limit - 1e-3


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


def _constant_grip_circle(cell_count: int = 4) -> tuple[SpatialTrack, Vehicle]:
    radius_m = 10.0
    track = SpatialTrack.from_cells(
        cell_length_m=(2.0 * pi * radius_m / cell_count,) * cell_count,
        curvature_per_m=(1.0 / radius_m,) * cell_count,
    )
    vehicle = Vehicle(initial_speed_mps=5.0)
    vehicle.tire.constant_friction_coefficient = 1.0
    vehicle.aero.drag_area_m2 = 0.0
    vehicle.aero.downforce_area_m2 = 0.0
    vehicle.cornering_drag_coefficient = 0.0
    return track, vehicle


@pytest.mark.parametrize("cell_count", (4, 64))
def test_automatic_circle_lap_respects_combined_grip_at_every_exit(
    cell_count: int,
) -> None:
    track, vehicle = _constant_grip_circle(cell_count)
    constraints = PathConstraintSolver().solve(track, vehicle)
    profile = PeriodicPiecewiseLinearTorqueProfile(
        track_length_m=track.length_m,
        knot_distance_m=(0.0, 0.5 * track.length_m),
        request_fraction_values=(1.0, 1.0),
    )
    exit_margins_n = []
    result = EnduranceSimulator().run(
        vehicle,
        constraints,
        profile,
        EnduranceRunConfig(laps=1, starting_speed_mps=5.0),
        progress_callback=lambda snapshot: exit_margins_n.append(
            vehicle.exit_combined_tire_force_margin_n(
                track.curvature_per_m[snapshot.cell_index]
            )
        ),
    )

    assert result.completed, result.failure_reason
    assert len(exit_margins_n) == track.cell_count
    assert min(exit_margins_n) >= 0.0


def test_supplied_controls_reject_exit_combined_grip_below_corner_limit() -> None:
    track, vehicle = _constant_grip_circle()
    constraints = PathConstraintSolver().solve(track, vehicle)
    profile = ConstantControlsProfile(
        Controls(
            motor_torque_request_nm=50.0,
            steering_angle_rad=atan(0.1 * vehicle.chassis.wheelbase_m),
        )
    )
    result = EnduranceSimulator().run(
        vehicle,
        constraints,
        profile,
        EnduranceRunConfig(laps=1, starting_speed_mps=5.0),
        record_telemetry=True,
    )

    assert not result.completed
    assert "exceeded combined tire force" in result.failure_reason
    assert result.failed_cell_index == 0
    assert vehicle.speed_mps < constraints.local_corner_speed_mps[0]
    assert result.telemetry is not None
    assert result.telemetry.sample_count == 0


def test_automatic_exit_guard_keeps_feasible_front_drive_request() -> None:
    vehicle = Vehicle(initial_speed_mps=4.0)
    vehicle.drivetrain.driven_axle = "front"
    vehicle.aero.downforce_area_m2 = 5.0
    curvature_per_m = 0.02
    controls = Controls(
        motor_torque_request_nm=250.0,
        steering_angle_rad=atan(
            curvature_per_m * vehicle.chassis.wheelbase_m
        ),
    )
    simulator = EnduranceSimulator()
    preview = deepcopy(vehicle)
    preview.update_state(controls, 3.0)
    assert preview.exit_combined_tire_force_margin_n(curvature_per_m) >= 0.0

    selected_controls, exit_tire_limited = (
        simulator._cap_drive_for_exit_tire_capacity(
            vehicle=vehicle,
            controls=controls,
            cell_length_m=3.0,
            curvature_per_m=curvature_per_m,
        )
    )

    assert selected_controls == controls
    assert not exit_tire_limited
