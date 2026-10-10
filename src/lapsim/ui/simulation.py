"""Bridge the desktop controls into the existing endurance physics."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from math import ceil, isfinite
from numbers import Real
from pathlib import Path

import numpy as np

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.events.endurance import (
    EnduranceRunConfig,
    EnduranceRunResult,
    EnduranceSimulator,
    LapProgressSnapshot,
)
from lapsim.optimization.torque_profile import PeriodicPiecewiseLinearTorqueProfile
from lapsim.solvers.path_constraints import (
    PathConstraintProgressSnapshot,
    PathConstraintSolver,
    PathSpeedConstraints,
)
from vehicle_model import Vehicle
from vehicle_model.mech.tire import Tire


from lapsim.resources import repository_root

REPOSITORY_ROOT = repository_root()
ENDURANCE_TRACK_PATH = (
    REPOSITORY_ROOT / "analysis" / "data" / "track" / "gnss_imu_endurance_track.csv"
)


@dataclass(frozen=True, slots=True)
class SpeedPeriodicLapResult:
    """One-lap speed shooting result at a fixed initial vehicle/pack state.

    Only speed at the closed-course seam is tested for periodicity. Battery
    charge, temperatures, and other component states need not match there.
    ``vehicle`` is the independent copy advanced by the final pass.
    """

    run: EnduranceRunResult
    vehicle: Vehicle
    passes: int
    speed_tolerance_mps: float

    @property
    def final_starting_speed_mps(self) -> float | None:
        return self.run.starting_speed_mps

    @property
    def speed_residual_mps(self) -> float | None:
        return self.run.seam_speed_delta_mps

    @property
    def converged(self) -> bool:
        residual_mps = self.speed_residual_mps
        return residual_mps is not None and abs(residual_mps) <= self.speed_tolerance_mps

    @property
    def failure_reason(self) -> str | None:
        if self.run.failure_reason is not None:
            return self.run.failure_reason
        if not self.converged:
            residual_mps = self.speed_residual_mps
            if residual_mps is None:
                return "Speed-only seam convergence could not be checked"
            return (
                f"Speed-only lap seam did not converge after {self.passes} passes: "
                f"finish minus start speed {residual_mps:+.6f} m/s exceeds "
                f"{self.speed_tolerance_mps:.6f} m/s"
            )
        return None


@dataclass(frozen=True, slots=True)
class SpeedPeriodicPhaseSnapshot:
    """An observed lap-pass transition, without an estimated percent done."""

    phase: str
    pass_number: int
    maximum_passes: int


@dataclass(frozen=True, slots=True, eq=False)
class PreparedOneLapConstraints:
    """Path limits bound to the vehicle used to calculate them."""

    _vehicle: Vehicle
    _limits: PathSpeedConstraints
    _road_grip_multiplier: float

    @property
    def track(self) -> SpatialTrack:
        return self._limits.track

    @property
    def braking_speed_ceiling_mps(self) -> tuple[float, ...]:
        return self._limits.braking_speed_ceiling_mps


def load_team_endurance_track() -> SpatialTrack:
    """Load the fused, map-registered endurance lap shipped with the repo."""

    return SpatialTrack.from_csv(ENDURANCE_TRACK_PATH, closed=True)


def apply_uniform_road_grip(
    vehicle: Vehicle, road_grip_multiplier: float,
) -> None:
    """Set a uniform assumed road-grip scenario on one run vehicle.

    Build a fresh vehicle for each run before calling this helper. The source
    profile and its manifest stay at their selected reference tire fit.
    """

    if (
        isinstance(road_grip_multiplier, bool)
        or not isinstance(road_grip_multiplier, Real)
        or not isfinite(road_grip_multiplier)
        or road_grip_multiplier <= 0.0
    ):
        raise ValueError("road_grip_multiplier must be finite and positive")
    if not isinstance(vehicle, Vehicle) or not isinstance(vehicle.tire, Tire):
        raise TypeError("uniform road grip requires a Vehicle with the Tire model")
    vehicle.tire.road_grip_multiplier = float(road_grip_multiplier)
    vehicle.validate()


def resample_track(track: SpatialTrack, maximum_cell_length_m: float = 1.0) -> SpatialTrack:
    """Build a solver grid while preserving each cell's integrated curvature.

    The measured centerline remains in the course view. Each solver cell gets
    the distance-weighted mean curvature of the source cells it overlaps, so
    the signed curvature integral is preserved over the full lap. Coordinates
    are interpolated to the solver-cell boundaries.
    """

    if (
        isinstance(maximum_cell_length_m, bool)
        or not isinstance(maximum_cell_length_m, Real)
        or not isfinite(maximum_cell_length_m)
        or maximum_cell_length_m <= 0.0
    ):
        raise ValueError("maximum_cell_length_m must be finite and positive")
    requested_cells = track.length_m / maximum_cell_length_m
    if not isfinite(requested_cells) or requested_cells > 5000:
        raise ValueError("requested solver grid exceeds the 5000-cell compute cap")
    cell_count = ceil(requested_cells)
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


def prepare_one_lap_constraints(
    vehicle: Vehicle, track: SpatialTrack,
    *, cell_road_grip_multiplier: tuple[float, ...] | None = None,
    constraint_progress_callback: Callable[[PathConstraintProgressSnapshot], None] | None = None,
) -> PreparedOneLapConstraints:
    """Prepare the same path limits used by an ordinary desktop lap."""

    vehicle.reset_state()
    solver = PathConstraintSolver(**path_solver_settings(vehicle))
    solve_kwargs: dict[str, object] = {}
    if cell_road_grip_multiplier is not None:
        solve_kwargs["cell_road_grip_multiplier"] = cell_road_grip_multiplier
    if constraint_progress_callback is not None:
        solve_kwargs["progress_callback"] = constraint_progress_callback
    limits = solver.solve(track, vehicle, **solve_kwargs)
    return PreparedOneLapConstraints(
        vehicle,
        limits,
        vehicle.tire.road_grip_multiplier,
    )


def run_one_lap(
    vehicle: Vehicle,
    track: SpatialTrack,
    *,
    torque_request_fraction: float,
    constraints: PreparedOneLapConstraints | None = None,
    starting_speed_mps: float | None = None,
    progress_callback: Callable[[LapProgressSnapshot], None] | None = None,
    cell_road_grip_multiplier: tuple[float, ...] | None = None,
    constraint_progress_callback: Callable[[PathConstraintProgressSnapshot], None] | None = None,
) -> EnduranceRunResult:
    """Simulate one lap, optionally reusing path limits and an explicit start.

    Supplied limits must have been prepared for this vehicle and track.
    """

    knot_distance_m = (0.0, track.length_m * 0.5)
    profile = PeriodicPiecewiseLinearTorqueProfile(
        track_length_m=track.length_m,
        knot_distance_m=knot_distance_m,
        request_fraction_values=(torque_request_fraction,) * 2,
    )
    if constraints is None:
        prepare_kwargs: dict[str, object] = {}
        if cell_road_grip_multiplier is not None:
            prepare_kwargs["cell_road_grip_multiplier"] = cell_road_grip_multiplier
        if constraint_progress_callback is not None:
            prepare_kwargs["constraint_progress_callback"] = (
                constraint_progress_callback
            )
        selected_constraints = prepare_one_lap_constraints(
            vehicle, track, **prepare_kwargs,
        )._limits
    else:
        if not isinstance(constraints, PreparedOneLapConstraints):
            raise TypeError("constraints must be PreparedOneLapConstraints")
        if constraints._vehicle is not vehicle:
            raise ValueError("supplied path constraints belong to a different vehicle")
        if constraints.track != track:
            raise ValueError("supplied path constraints do not match the lap track")
        if constraints._road_grip_multiplier != vehicle.tire.road_grip_multiplier:
            raise ValueError("supplied path constraints use a different road grip")
        if (
            cell_road_grip_multiplier is not None
            and cell_road_grip_multiplier != constraints._limits.cell_road_grip_multiplier
        ):
            raise ValueError("supplied path constraints use a different cell road grip")
        vehicle.reset_state()
        selected_constraints = constraints._limits
    return EnduranceSimulator().run(
        vehicle,
        selected_constraints,
        profile,
        replace(
            endurance_run_config(vehicle),
            starting_speed_mps=starting_speed_mps,
        ),
        record_telemetry=True,
        progress_callback=progress_callback,
    )


def run_speed_periodic_lap(
    vehicle: Vehicle,
    track: SpatialTrack,
    *,
    torque_request_fraction: float,
    speed_tolerance_mps: float = 0.005,
    maximum_lap_passes: int = 2,
    progress_callback: Callable[[LapProgressSnapshot], None] | None = None,
    phase_progress_callback: Callable[[SpeedPeriodicPhaseSnapshot], None] | None = None,
    cell_road_grip_multiplier: tuple[float, ...] | None = None,
    constraint_progress_callback: Callable[[PathConstraintProgressSnapshot], None] | None = None,
) -> SpeedPeriodicLapResult:
    """Shoot for a closed-course seam speed with bounded full-model laps.

    This optional desktop helper keeps the ordinary one-lap behavior intact.
    Path constraints are solved once. Every pass starts from an independent
    copy of the same initial vehicle and pack state. Earlier passes have no
    telemetry or accepted-cell progress callbacks; an optional phase callback
    announces each unrecorded probe and the final pass. The default allows
    one probe plus one final pass. A third pass
    can be requested for an additional dry probe before the final pass.

    The returned ``converged`` flag is about speed alone. The final explicit
    start speed must be persisted with the run for faithful replay.
    """

    if not isfinite(speed_tolerance_mps) or speed_tolerance_mps <= 0.0:
        raise ValueError("speed_tolerance_mps must be finite and positive")
    if type(maximum_lap_passes) is not int or not 2 <= maximum_lap_passes <= 3:
        raise ValueError("maximum_lap_passes must be 2 or 3")
    if not track.closed:
        raise ValueError("speed-periodic lap requires a closed course")

    template_vehicle = deepcopy(vehicle)
    template_vehicle.reset_state()
    solver = PathConstraintSolver(**path_solver_settings(template_vehicle))
    solve_kwargs: dict[str, object] = {}
    if cell_road_grip_multiplier is not None:
        solve_kwargs["cell_road_grip_multiplier"] = cell_road_grip_multiplier
    if constraint_progress_callback is not None:
        solve_kwargs["progress_callback"] = constraint_progress_callback
    constraints = solver.solve(track, template_vehicle, **solve_kwargs)
    profile = PeriodicPiecewiseLinearTorqueProfile(
        track_length_m=track.length_m,
        knot_distance_m=(0.0, track.length_m * 0.5),
        request_fraction_values=(torque_request_fraction,) * 2,
    )
    start_speed_mps = constraints.braking_speed_ceiling_mps[0]
    simulator = EnduranceSimulator()
    for pass_number in range(1, maximum_lap_passes):
        if phase_progress_callback is not None:
            phase_progress_callback(SpeedPeriodicPhaseSnapshot(
                "speed_seam_probe", pass_number, maximum_lap_passes,
            ))
        probe_vehicle = deepcopy(template_vehicle)
        probe_result = simulator.run(
            probe_vehicle,
            constraints,
            profile,
            replace(
                endurance_run_config(probe_vehicle),
                starting_speed_mps=start_speed_mps,
            ),
        )
        if not probe_result.completed:
            return SpeedPeriodicLapResult(
                run=probe_result,
                vehicle=probe_vehicle,
                passes=pass_number,
                speed_tolerance_mps=speed_tolerance_mps,
            )
        start_speed_mps = probe_vehicle.speed_mps
        probe_residual_mps = probe_result.seam_speed_delta_mps
        if (
            probe_residual_mps is not None
            and abs(probe_residual_mps) <= speed_tolerance_mps
        ):
            break

    if phase_progress_callback is not None:
        phase_progress_callback(SpeedPeriodicPhaseSnapshot(
            "final_lap", pass_number + 1, maximum_lap_passes,
        ))
    final_vehicle = deepcopy(template_vehicle)
    final_result = simulator.run(
        final_vehicle,
        constraints,
        profile,
        replace(
            endurance_run_config(final_vehicle),
            starting_speed_mps=start_speed_mps,
        ),
        record_telemetry=True,
        progress_callback=progress_callback,
    )
    return SpeedPeriodicLapResult(
        run=final_result,
        vehicle=final_vehicle,
        passes=pass_number + 1,
        speed_tolerance_mps=speed_tolerance_mps,
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
