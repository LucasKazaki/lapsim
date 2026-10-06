"""Bridge the desktop controls into the existing endurance physics."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.events.endurance import (
    EnduranceRunConfig,
    EnduranceRunResult,
    EnduranceSimulator,
)
from lapsim.optimization.torque_profile import PeriodicPiecewiseLinearTorqueProfile
from lapsim.solvers.path_constraints import PathConstraintSolver
from vehicle_model import Vehicle


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ENDURANCE_TRACK_PATH = (
    REPOSITORY_ROOT / "analysis" / "data" / "track" / "gnss_imu_endurance_track.csv"
)


def load_team_endurance_track() -> SpatialTrack:
    """Load the fused, map-registered endurance lap shipped with the repo."""

    return SpatialTrack.from_csv(ENDURANCE_TRACK_PATH, closed=True)


def resample_track(track: SpatialTrack, maximum_cell_length_m: float = 1.0) -> SpatialTrack:
    """Build a solver grid while preserving each cell's integrated curvature.

    The measured centerline remains in the course view. Each solver cell gets
    the distance-weighted mean curvature of the source cells it overlaps, so
    the signed curvature integral is preserved over the full lap. Coordinates
    are interpolated to the solver-cell boundaries.
    """

    if maximum_cell_length_m <= 0.0:
        raise ValueError("maximum_cell_length_m must be positive")
    cell_count = int(np.ceil(track.length_m / maximum_cell_length_m))
    distances = [
        min(index * maximum_cell_length_m, track.length_m)
        for index in range(cell_count + 1)
    ]
    source_distance = np.asarray(track.distance_m, dtype=float)
    source_curvature = np.asarray(track.curvature_per_m, dtype=float)
    averaged_curvature: list[float] = []
    for lower_m, upper_m in zip(distances, distances[1:]):
        source_index = max(
            0,
            int(np.searchsorted(source_distance, lower_m, side="right") - 1),
        )
        weighted_curvature = 0.0
        while source_index < track.cell_count and source_distance[source_index] < upper_m:
            overlap_m = max(
                0.0,
                min(upper_m, source_distance[source_index + 1])
                - max(lower_m, source_distance[source_index]),
            )
            weighted_curvature += source_curvature[source_index] * overlap_m
            source_index += 1
        averaged_curvature.append(weighted_curvature / (upper_m - lower_m))
    return SpatialTrack(
        distance_m=tuple(distances),
        x_m=tuple(np.interp(distances, source_distance, track.x_m)),
        y_m=tuple(np.interp(distances, source_distance, track.y_m)),
        curvature_per_m=tuple(averaged_curvature),
        closed=track.closed,
    )


def run_one_lap(
    vehicle: Vehicle,
    track: SpatialTrack,
    *,
    torque_request_fraction: float,
) -> EnduranceRunResult:
    """Simulate one lap with path constraints and the brake controller."""

    knot_distance_m = (0.0, track.length_m * 0.5)
    profile = PeriodicPiecewiseLinearTorqueProfile(
        track_length_m=track.length_m,
        knot_distance_m=knot_distance_m,
        request_fraction_values=(torque_request_fraction,) * 2,
    )
    vehicle.reset_state()
    constraints = PathConstraintSolver(
        **path_solver_settings(vehicle),
    ).solve(track, vehicle)
    return EnduranceSimulator().run(
        vehicle,
        constraints,
        profile,
        endurance_run_config(vehicle),
        record_telemetry=True,
    )


def path_solver_settings(vehicle: Vehicle) -> dict[str, float | int]:
    """Settings used by the desktop path solver and saved run records."""

    return dict(
        convergence_tolerance_mps=0.005,
        maximum_passes=120,
        maximum_entry_iterations=20,
        steady_state_iterations=24,
        gravity_mps2=vehicle.gravity_mps2,
        air_density_kgpm3=vehicle.air_density_kgpm3,
        maximum_brake_pressure_psi=vehicle.brakes.maximum_pressure_psi,
    )


def endurance_run_config(vehicle: Vehicle) -> EnduranceRunConfig:
    """Configuration used by the desktop endurance controller."""

    return EnduranceRunConfig(
        laps=1,
        path_speed_tolerance_mps=0.06,
        maximum_brake_pressure_psi=vehicle.brakes.maximum_pressure_psi,
    )
