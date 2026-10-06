"""Vehicle-dependent speed constraints on a prescribed spatial track."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import atan, isfinite

from scipy.optimize import brentq

from vehicle_model.aero import Aero
from vehicle_model.environment import (
    STANDARD_AIR_DENSITY_KGPM3,
    STANDARD_GRAVITY_MPS2,
)
from vehicle_model.mech.brakes import DEFAULT_MAXIMUM_BRAKE_PRESSURE_PSI
from vehicle_model.mech import Brakes, Chassis, Suspension, Tire
from vehicle_model.vehicle import Vehicle

from ..core.controls import Controls
from ..courses.spatial_track import SpatialTrack


class PathConstraintViolation(RuntimeError):
    """Raised when the vehicle cannot follow the prescribed path curvature."""


@dataclass(frozen=True, slots=True)
class PathSpeedConstraints:
    """Local corner limits and cyclic maximum-braking speed ceiling."""

    track: SpatialTrack
    local_corner_speed_mps: tuple[float, ...]
    braking_speed_ceiling_mps: tuple[float, ...]
    passes: int

    def __post_init__(self) -> None:
        expected = self.track.cell_count
        if len(self.local_corner_speed_mps) != expected:
            raise ValueError("Local limits must contain one value per track cell")
        if len(self.braking_speed_ceiling_mps) != expected:
            raise ValueError("Braking ceilings must contain one value per track cell")


class PathConstraintSolver:
    """Precompute torque-profile-independent path speed ceilings."""

    def __init__(
        self,
        *,
        convergence_tolerance_mps: float = 1e-5,
        maximum_passes: int = 500,
        maximum_entry_iterations: int = 40,
        steady_state_iterations: int = 50,
        gravity_mps2: float = STANDARD_GRAVITY_MPS2,
        air_density_kgpm3: float = STANDARD_AIR_DENSITY_KGPM3,
        maximum_brake_pressure_psi: float | None = DEFAULT_MAXIMUM_BRAKE_PRESSURE_PSI,
    ) -> None:
        if convergence_tolerance_mps <= 0:
            raise ValueError("convergence_tolerance_mps must be positive")
        if maximum_passes <= 0:
            raise ValueError("maximum_passes must be positive")
        if maximum_entry_iterations <= 0:
            raise ValueError("maximum_entry_iterations must be positive")
        if steady_state_iterations <= 0:
            raise ValueError("steady_state_iterations must be positive")
        if not isfinite(gravity_mps2) or gravity_mps2 <= 0.0:
            raise ValueError("gravity_mps2 must be finite and positive")
        if not isfinite(air_density_kgpm3) or air_density_kgpm3 <= 0.0:
            raise ValueError("air_density_kgpm3 must be finite and positive")
        if maximum_brake_pressure_psi is not None and (
            not isfinite(maximum_brake_pressure_psi)
            or maximum_brake_pressure_psi <= 0.0
        ):
            raise ValueError("maximum_brake_pressure_psi must be finite and positive")
        self.convergence_tolerance_mps = convergence_tolerance_mps
        self.maximum_passes = maximum_passes
        self.maximum_entry_iterations = maximum_entry_iterations
        self.steady_state_iterations = steady_state_iterations
        self.gravity_mps2 = gravity_mps2
        self.air_density_kgpm3 = air_density_kgpm3
        self.maximum_brake_pressure_psi = maximum_brake_pressure_psi

    def solve(self, track: SpatialTrack, vehicle: Vehicle) -> PathSpeedConstraints:
        """Calculate local lateral limits then a cyclic backward brake pass."""

        if not track.closed:
            raise ValueError(
                "The endurance path-constraint solver requires a closed track"
            )
        vehicle.validate()
        local_limits = [
            self.local_corner_speed_limit_mps(vehicle, curvature_per_m)
            for curvature_per_m in track.curvature_per_m
        ]
        ceilings = local_limits.copy()
        cell_lengths = track.cell_length_m

        for pass_number in range(1, self.maximum_passes + 1):
            largest_change_mps = 0.0
            for cell_index in range(track.cell_count - 1, -1, -1):
                next_index = (cell_index + 1) % track.cell_count
                reachable_speed_mps = self._maximum_entry_speed_mps(
                    vehicle=vehicle,
                    next_speed_mps=ceilings[next_index],
                    local_speed_limit_mps=local_limits[cell_index],
                    curvature_per_m=track.curvature_per_m[cell_index],
                    cell_length_m=cell_lengths[cell_index],
                )
                new_speed_mps = min(
                    ceilings[cell_index],
                    local_limits[cell_index],
                    reachable_speed_mps,
                )
                largest_change_mps = max(
                    largest_change_mps,
                    ceilings[cell_index] - new_speed_mps,
                )
                ceilings[cell_index] = new_speed_mps
            if largest_change_mps < self.convergence_tolerance_mps:
                return PathSpeedConstraints(
                    track=track,
                    local_corner_speed_mps=tuple(local_limits),
                    braking_speed_ceiling_mps=tuple(ceilings),
                    passes=pass_number,
                )

        raise RuntimeError(
            f"Cyclic braking ceiling did not converge after {self.maximum_passes} passes"
        )

    def _maximum_entry_speed_mps(
        self,
        *,
        vehicle: Vehicle,
        next_speed_mps: float,
        local_speed_limit_mps: float,
        curvature_per_m: float,
        cell_length_m: float,
    ) -> float:
        """Solve the variable-deceleration distance equation conservatively."""

        use_direct_force_balance = (
            type(vehicle.aero) is Aero
            and type(vehicle.brakes) is Brakes
            and type(vehicle.chassis) is Chassis
            and type(vehicle.suspension) is Suspension
            and type(vehicle.tire) is Tire
            and vehicle.tire.longitudinal_slip_relaxation_length_m == 0.0
        )
        if use_direct_force_balance:
            pressure_psi = (
                1.0e9
                if self.maximum_brake_pressure_psi is None
                else self.maximum_brake_pressure_psi
            )
            front_brake_request_n, rear_brake_request_n = (
                vehicle.brakes.axle_force_requests_from_pressures_n(
                    pressure_psi,
                    pressure_psi,
                    vehicle.tire.rolling_radius_m,
                )
            )

            def direct_braking_acceleration_mps2(entry_speed_mps: float) -> float:
                curvature_sign = 1.0 if curvature_per_m >= 0.0 else -1.0
                requested_lateral_force_n = (
                    vehicle.mass_kg
                    * entry_speed_mps**2
                    * abs(curvature_per_m)
                )

                def loads_and_capacity(
                    lateral_force_n: float,
                    assumed_acceleration_mps2: float,
                ):
                    lateral_acceleration_mps2 = (
                        curvature_sign * lateral_force_n / vehicle.mass_kg
                    )
                    aero_forces = vehicle.aero_forces_n(
                        entry_speed_mps,
                        lateral_acceleration_mps2,
                        self.air_density_kgpm3,
                        curvature_per_m=curvature_per_m,
                    )
                    normal_loads_n = vehicle.suspension.tire_normal_loads_n(
                        vehicle.mass_kg,
                        self.gravity_mps2,
                        aero_forces,
                        vehicle.chassis,
                        longitudinal_acceleration_mps2=assumed_acceleration_mps2,
                        lateral_acceleration_mps2=lateral_acceleration_mps2,
                    )
                    lateral_capacity_n = sum(
                        vehicle.tire.lateral_force_capacity_n(load_n)
                        for load_n in normal_loads_n.all_n
                    )
                    return normal_loads_n, lateral_capacity_n, aero_forces

                def acceleration_for_assumption(
                    assumed_acceleration_mps2: float,
                ) -> float:
                    normal_loads_n, lateral_capacity_n, aero_forces = (
                        loads_and_capacity(
                            requested_lateral_force_n,
                            assumed_acceleration_mps2,
                        )
                    )
                    lateral_force_n = min(
                        requested_lateral_force_n,
                        lateral_capacity_n,
                    )
                    if requested_lateral_force_n > lateral_capacity_n:
                        lateral_force_n = brentq(
                            lambda force_n: force_n
                            - loads_and_capacity(
                                force_n,
                                assumed_acceleration_mps2,
                            )[1],
                            0.0,
                            requested_lateral_force_n,
                            xtol=1e-8,
                        )
                        normal_loads_n, lateral_capacity_n, aero_forces = (
                            loads_and_capacity(
                                lateral_force_n,
                                assumed_acceleration_mps2,
                            )
                        )

                    tire_states = vehicle.tire.calculate_forces(
                        normal_loads_n,
                        curvature_sign * lateral_force_n,
                        0.0,
                        front_brake_request_n,
                        rear_brake_request_n,
                        max(entry_speed_mps, 0.1),
                        1.0,
                        drive_axle=vehicle.drivetrain.driven_axle,
                    )
                    cornering_drag_force_n = (
                        vehicle.cornering_drag_coefficient
                        * lateral_force_n**2
                        / (
                            vehicle.mass_kg * self.gravity_mps2
                            + aero_forces.downforce_n
                        )
                    )
                    rolling_force_n = vehicle.rolling_resistance_coefficient * (
                        vehicle.mass_kg * self.gravity_mps2
                        + aero_forces.downforce_n
                    )
                    resistance_force_n = (
                        aero_forces.drag_n
                        + rolling_force_n
                        + cornering_drag_force_n
                    )
                    return (
                        tire_states.longitudinal_force_n - resistance_force_n
                    ) / vehicle.effective_longitudinal_mass_kg

                return brentq(
                    lambda acceleration_mps2: (
                        acceleration_mps2
                        - acceleration_for_assumption(acceleration_mps2)
                    ),
                    -100.0,
                    100.0,
                    xtol=1e-8,
                )

        def residual(entry_speed_mps: float) -> float:
            if use_direct_force_balance:
                acceleration_mps2 = direct_braking_acceleration_mps2(
                    entry_speed_mps
                )
                final_speed_squared_mps2 = (
                    entry_speed_mps**2
                    + 2.0 * acceleration_mps2 * cell_length_m
                )
                if final_speed_squared_mps2 < -1e-9:
                    return -(next_speed_mps**2)
                return max(final_speed_squared_mps2, 0.0) - next_speed_mps**2

            candidate = deepcopy(vehicle)
            candidate.gravity_mps2 = self.gravity_mps2
            candidate.air_density_kgpm3 = self.air_density_kgpm3
            candidate.speed_mps = entry_speed_mps
            candidate.longitudinal_acceleration_mps2 = 0.0
            candidate.lateral_acceleration_mps2 = entry_speed_mps**2 * curvature_per_m
            pressure_psi = (
                1.0e9
                if self.maximum_brake_pressure_psi is None
                else self.maximum_brake_pressure_psi
            )
            maximum_braking = Controls(
                front_brake_pressure_psi=pressure_psi,
                rear_brake_pressure_psi=pressure_psi,
                steering_angle_rad=atan(
                    curvature_per_m * candidate.chassis.wheelbase_m
                ),
            )
            try:
                candidate.update_state(maximum_braking, cell_length_m)
            except ValueError as error:
                if "stops before the end of the cell" in str(error):
                    return -(next_speed_mps**2)
                raise
            return candidate.speed_mps**2 - next_speed_mps**2

        lower_speed_mps = min(next_speed_mps, local_speed_limit_mps)
        upper_speed_mps = local_speed_limit_mps
        if residual(upper_speed_mps) <= 0.0:
            return upper_speed_mps
        for _ in range(self.maximum_entry_iterations):
            candidate_speed_mps = 0.5 * (lower_speed_mps + upper_speed_mps)
            if residual(candidate_speed_mps) <= 0.0:
                lower_speed_mps = candidate_speed_mps
            else:
                upper_speed_mps = candidate_speed_mps
        return lower_speed_mps

    def local_corner_speed_limit_mps(
        self, vehicle: Vehicle, curvature_per_m: float
    ) -> float:
        """Return the steady lateral-capacity speed bound for one path cell.

        This is independent of driver controls. Callers must separately check
        any combined longitudinal/lateral tire-force limitation.
        """
        vehicle_speed_limit_mps = vehicle.drivetrain.vehicle_speed_limit_mps
        absolute_curvature_per_m = abs(curvature_per_m)
        if absolute_curvature_per_m <= 1e-15:
            return vehicle_speed_limit_mps

        lower_speed_mps = 0.0
        upper_speed_mps = vehicle_speed_limit_mps
        for _ in range(self.steady_state_iterations):
            candidate_speed_mps = 0.5 * (lower_speed_mps + upper_speed_mps)
            lateral_acceleration_mps2 = (
                candidate_speed_mps**2 * absolute_curvature_per_m
            )
            aero_forces = vehicle.aero_forces_n(
                candidate_speed_mps,
                lateral_acceleration_mps2,
                self.air_density_kgpm3,
                curvature_per_m=curvature_per_m,
            )
            tire_normal_loads = vehicle.suspension.tire_normal_loads_n(
                vehicle.mass_kg,
                self.gravity_mps2,
                aero_forces,
                vehicle.chassis,
                lateral_acceleration_mps2=lateral_acceleration_mps2,
            )
            available_lateral_force_n = sum(
                vehicle.tire.lateral_force_capacity_n(normal_load_n)
                for normal_load_n in tire_normal_loads.all_n
            )
            required_lateral_force_n = (
                vehicle.mass_kg * candidate_speed_mps**2 * absolute_curvature_per_m
            )
            if required_lateral_force_n <= available_lateral_force_n:
                lower_speed_mps = candidate_speed_mps
            else:
                upper_speed_mps = candidate_speed_mps
        return lower_speed_mps


__all__ = [
    "PathConstraintSolver",
    "PathConstraintViolation",
    "PathSpeedConstraints",
]
