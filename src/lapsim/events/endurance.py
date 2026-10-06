"""Stateful prescribed-path endurance simulation."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from math import atan, copysign, isfinite, sqrt

from scipy.optimize import brentq

from vehicle_model.mech.brakes import DEFAULT_MAXIMUM_BRAKE_PRESSURE_PSI
from vehicle_model.vehicle import Vehicle

from ..core.controls import Controls
from ..core.telemetry import JOULES_PER_KILOWATT_HOUR, Telemetry, TelemetryRecorder
from ..optimization.torque_profile import EnduranceControlProfile, TorqueProfile
from ..solvers.path_constraints import PathSpeedConstraints


@dataclass(frozen=True, slots=True)
class EnduranceRunConfig:
    """Event-independent run length and numerical behavior."""

    laps: int = 22
    starting_speed_mps: float | None = None
    maximum_driving_time_s: float = 3_600.0
    minimum_moving_speed_mps: float = 0.05
    path_speed_tolerance_mps: float = 0.01
    maximum_brake_pressure_psi: float | None = DEFAULT_MAXIMUM_BRAKE_PRESSURE_PSI
    regenerative_braking_soc_threshold: float | None = None
    path_curvature_tolerance_per_m: float = 1e-9

    def __post_init__(self) -> None:
        if self.laps <= 0:
            raise ValueError("laps must be positive")
        if self.starting_speed_mps is not None and (
            not isfinite(self.starting_speed_mps) or self.starting_speed_mps < 0.0
        ):
            raise ValueError("starting_speed_mps must be finite and nonnegative")
        if not isfinite(self.maximum_driving_time_s) or self.maximum_driving_time_s <= 0.0:
            raise ValueError("maximum_driving_time_s must be finite and positive")
        if not isfinite(self.minimum_moving_speed_mps) or self.minimum_moving_speed_mps <= 0.0:
            raise ValueError("minimum_moving_speed_mps must be finite and positive")
        if not isfinite(self.path_speed_tolerance_mps) or self.path_speed_tolerance_mps <= 0.0:
            raise ValueError("path_speed_tolerance_mps must be finite and positive")
        if (
            isinstance(self.path_curvature_tolerance_per_m, bool)
            or not isfinite(self.path_curvature_tolerance_per_m)
            or self.path_curvature_tolerance_per_m <= 0.0
        ):
            raise ValueError("path_curvature_tolerance_per_m must be finite and positive")
        if self.maximum_brake_pressure_psi is not None and (
            not isfinite(self.maximum_brake_pressure_psi)
            or self.maximum_brake_pressure_psi <= 0.0
        ):
            raise ValueError("maximum_brake_pressure_psi must be finite and positive")
        if self.regenerative_braking_soc_threshold is not None and (
            not isfinite(self.regenerative_braking_soc_threshold)
            or not 0.0 <= self.regenerative_braking_soc_threshold <= 1.0
        ):
            raise ValueError(
                "regenerative_braking_soc_threshold must be between zero and one"
            )


@dataclass(frozen=True, slots=True)
class EnduranceRunResult:
    """Performance summary with optional full component-owned telemetry.

    Failed-run time, speed, and SOC retain the attempted vehicle state for
    compatibility. ``accepted_*`` separately identify the last cell that
    passed the path and kinematic gates; failure indices are zero based.
    """

    completed_laps: int
    driving_time_s: float
    lap_times_s: tuple[float, ...]
    pack_energy_kwh: float
    final_state_of_charge: float
    failure_reason: str | None
    telemetry: Telemetry | None
    starting_speed_mps: float | None = None
    ending_speed_mps: float | None = None
    accepted_time_s: float | None = None
    accepted_distance_m: float | None = None
    accepted_speed_mps: float | None = None
    accepted_state_of_charge: float | None = None
    failed_lap_index: int | None = None
    failed_cell_index: int | None = None
    failed_cell_update_completed: bool | None = None

    @property
    def completed(self) -> bool:
        return self.failure_reason is None

    @property
    def seam_speed_delta_mps(self) -> float | None:
        """Finish minus start speed for a completed single-lap run, if known.

        A nonzero value means the lap's speed state is not periodic at the
        start/finish seam. No tolerance or correction is hidden in this value.
        """

        if (
            not self.completed
            or self.completed_laps != 1
            or self.starting_speed_mps is None
            or self.ending_speed_mps is None
        ):
            return None
        return self.ending_speed_mps - self.starting_speed_mps


@dataclass(frozen=True, slots=True)
class LapProgressSnapshot:
    """Accepted-cell state for an optional low-cost observer.

    Indices are zero based; ``lap_station_m`` is the cell exit on the current
    lap, while ``total_distance_m`` and ``elapsed_time_s`` include prior laps.
    The snapshot contains values only, so another thread can consume it
    without reading mutable vehicle or telemetry state.
    """

    lap_index: int
    cell_index: int
    cell_count: int
    elapsed_time_s: float
    lap_station_m: float
    total_distance_m: float
    speed_mps: float
    lateral_acceleration_mps2: float
    path_speed_ceiling_mps: float | None = None
    motor_torque_request_nm: float | None = None
    front_brake_pressure_psi: float | None = None
    rear_brake_pressure_psi: float | None = None
    drive_force_n: float | None = None
    friction_braking_force_n: float | None = None
    regenerative_braking_force_n: float | None = None
    longitudinal_acceleration_mps2: float | None = None
    battery_power_w: float | None = None


class EnduranceSimulator:
    """Apply supplied driver controls while preserving component state.

    A torque-only profile receives path-following steering plus a deterministic
    longitudinal controller.  The controller reduces requested drive torque,
    coasts, or requests friction braking as needed to reach the next cyclic
    path-speed ceiling.  A full control profile supplies motor, brake-pressure,
    regen, and steering commands directly. Both commanded and achieved
    curvature must follow the prescribed path, in addition to its speed
    constraints. This is not a check against plotted x/y or course boundaries.
    """

    @staticmethod
    def _path_resistance_and_lateral_force_n(
        vehicle: Vehicle,
        *,
        speed_mps: float,
        curvature_per_m: float,
    ) -> tuple[float, float]:
        """Return entry resistance and lateral force used by ``Vehicle``."""

        lateral_acceleration_mps2 = speed_mps**2 * curvature_per_m
        aero_forces = vehicle.aero_forces_n(
            speed_mps,
            lateral_acceleration_mps2,
            curvature_per_m=curvature_per_m,
        )
        rolling_force_n = vehicle.rolling_resistance_coefficient * (
            vehicle.mass_kg * vehicle.gravity_mps2 + aero_forces.downforce_n
        )
        tire_normal_loads = vehicle.suspension.tire_normal_loads_n(
            vehicle.mass_kg,
            vehicle.gravity_mps2,
            aero_forces,
            vehicle.chassis,
            longitudinal_acceleration_mps2=vehicle.longitudinal_acceleration_mps2,
            lateral_acceleration_mps2=lateral_acceleration_mps2,
        )
        lateral_capacity_n = sum(
            vehicle.tire.lateral_force_capacity_n(normal_load_n)
            for normal_load_n in tire_normal_loads.all_n
        )
        requested_lateral_force_n = (
            vehicle.mass_kg * speed_mps**2 * abs(curvature_per_m)
        )
        lateral_force_n = min(requested_lateral_force_n, lateral_capacity_n)
        total_normal_force_n = (
            vehicle.mass_kg * vehicle.gravity_mps2 + aero_forces.downforce_n
        )
        cornering_drag_force_n = (
            vehicle.cornering_drag_coefficient
            * lateral_force_n**2
            / total_normal_force_n
        )
        return (
            aero_forces.drag_n + rolling_force_n + cornering_drag_force_n,
            lateral_force_n,
        )

    @staticmethod
    def _brake_controls_for_target_force(
        vehicle: Vehicle,
        *,
        brake_force_request_n: float,
        target_acceleration_mps2: float,
        lateral_force_n: float,
        curvature_per_m: float,
        maximum_regenerative_brake_force_n: float = 0.0,
        maximum_brake_pressure_psi: float | None = None,
    ) -> tuple[float, float, float, float]:
        """Allocate friction and driven-axle regen within contact-patch grip."""

        lateral_acceleration_mps2 = (
            copysign(lateral_force_n, curvature_per_m) / vehicle.mass_kg
        )
        aero_forces = vehicle.aero_forces_n(
            vehicle.speed_mps,
            lateral_acceleration_mps2,
            curvature_per_m=curvature_per_m,
        )
        tire_normal_loads = vehicle.suspension.tire_normal_loads_n(
            vehicle.mass_kg,
            vehicle.gravity_mps2,
            aero_forces,
            vehicle.chassis,
            longitudinal_acceleration_mps2=target_acceleration_mps2,
            lateral_acceleration_mps2=lateral_acceleration_mps2,
        )
        tire_lateral_forces_n = vehicle.tire.lateral_forces_n(
            tire_normal_loads, lateral_force_n
        )
        tire_capacities_n = tuple(
            vehicle.tire.combined_longitudinal_force_capacity_n(load_n, lateral_n)
            for load_n, lateral_n in zip(
                tire_normal_loads.all_n,
                tire_lateral_forces_n.all_n,
                strict=True,
            )
        )
        # Axle requests are split equally left/right by the tire model. Use
        # the weaker contact patch so unused grip on the outside tire is not
        # silently transferred to the inside tire while cornering.
        front_capacity_n = 2.0 * min(tire_capacities_n[:2])
        rear_capacity_n = 2.0 * min(tire_capacities_n[2:])
        total_capacity_n = front_capacity_n + rear_capacity_n
        allocated_force_n = min(brake_force_request_n, total_capacity_n)
        tire_capacity_saturated = brake_force_request_n >= total_capacity_n - 1e-9
        driven_axle = vehicle.drivetrain.driven_axle
        if driven_axle == "front":
            front_regenerative_force_n = min(
                maximum_regenerative_brake_force_n,
                allocated_force_n,
                front_capacity_n,
            )
            rear_regenerative_force_n = 0.0
        elif driven_axle == "rear":
            front_regenerative_force_n = 0.0
            rear_regenerative_force_n = min(
                maximum_regenerative_brake_force_n,
                allocated_force_n,
                rear_capacity_n,
            )
        else:
            regenerative_force_n = min(
                maximum_regenerative_brake_force_n,
                allocated_force_n,
            )
            front_regenerative_force_n = (
                regenerative_force_n * front_capacity_n / total_capacity_n
                if total_capacity_n > 0.0
                else 0.0
            )
            rear_regenerative_force_n = (
                regenerative_force_n - front_regenerative_force_n
            )
        friction_force_n = (
            allocated_force_n
            - front_regenerative_force_n
            - rear_regenerative_force_n
        )
        front_friction_capacity_n = (
            front_capacity_n - front_regenerative_force_n
        )
        rear_friction_capacity_n = rear_capacity_n - rear_regenerative_force_n
        front_fraction = vehicle.brakes.front_brake_force_fraction
        front_force_n = min(
            friction_force_n * front_fraction,
            front_friction_capacity_n,
        )
        rear_force_n = min(
            friction_force_n * (1.0 - front_fraction),
            rear_friction_capacity_n,
        )
        remaining_force_n = friction_force_n - front_force_n - rear_force_n
        if remaining_force_n > 0.0:
            front_headroom_n = front_friction_capacity_n - front_force_n
            rear_headroom_n = rear_friction_capacity_n - rear_force_n
            total_headroom_n = front_headroom_n + rear_headroom_n
            if total_headroom_n > 0.0:
                front_addition_n = min(
                    remaining_force_n * front_headroom_n / total_headroom_n,
                    front_headroom_n,
                )
                front_force_n += front_addition_n
                rear_force_n += min(
                    remaining_force_n - front_addition_n,
                    rear_headroom_n,
                )
        front_pressure_psi, rear_pressure_psi = (
            vehicle.brakes.axle_pressures_for_force_requests_psi(
                max(front_force_n, 0.0),
                max(rear_force_n, 0.0),
                vehicle.tire.rolling_radius_m,
            )
        )
        pressure_limit_psi = min(
            vehicle.brakes.maximum_pressure_psi,
            maximum_brake_pressure_psi
            if maximum_brake_pressure_psi is not None
            else vehicle.brakes.maximum_pressure_psi,
        )
        if (
            tire_capacity_saturated
            or front_pressure_psi >= pressure_limit_psi - 1e-9
            or rear_pressure_psi >= pressure_limit_psi - 1e-9
        ):
            # The pressure inverse uses the target acceleration's estimated
            # tire loads. At the limit, the committed load-transfer fixed
            # point can provide slightly less force. The braking envelope
            # assumes both hydraulic actuators are available at full pressure,
            # so use that same bounded command when either axle saturates.
            # Contact-patch combined slip remains the physical force cap.
            front_pressure_psi = pressure_limit_psi
            rear_pressure_psi = pressure_limit_psi
        return (
            front_pressure_psi,
            rear_pressure_psi,
            front_regenerative_force_n,
            rear_regenerative_force_n,
        )

    def _torque_profile_controls(
        self,
        *,
        vehicle: Vehicle,
        request_fraction: float,
        curvature_per_m: float,
        cell_length_m: float,
        target_speed_mps: float,
        current_cell_corner_speed_mps: float,
        maximum_brake_pressure_psi: float | None,
        regenerative_braking_soc_threshold: float | None,
    ) -> tuple[Controls, float, bool, float, bool]:
        """Convert a torque profile into ceiling-following controls for one cell.

        Returns the controls, unconstrained profile torque, whether drive torque
        was reduced, the requested hydraulic brake force, and whether either
        hydraulic command was pressure limited.
        """

        initial_speed_mps = vehicle.speed_mps
        # The next-cell braking ceiling alone may permit acceleration beyond
        # the current curved cell's lateral limit before its exit. Both entry
        # and exit must satisfy the current cell's prescribed curvature.
        target_speed_mps = min(target_speed_mps, current_cell_corner_speed_mps)
        profile_torque_nm = request_fraction * (
            vehicle.drivetrain.motor.torque_limit_nm(
                vehicle.drivetrain.motor_speed_rpm(initial_speed_mps)
            )
        )
        target_acceleration_mps2 = (
            target_speed_mps**2 - initial_speed_mps**2
        ) / (2.0 * cell_length_m)
        resistance_force_n, lateral_force_n = (
            self._path_resistance_and_lateral_force_n(
                vehicle,
                speed_mps=initial_speed_mps,
                curvature_per_m=curvature_per_m,
            )
        )
        force_for_target_n = (
            vehicle.effective_longitudinal_mass_kg * target_acceleration_mps2
            + resistance_force_n
        )

        brake_force_request_n = max(-force_for_target_n, 0.0)
        brake_pressure_limited = False
        if brake_force_request_n > 0.0:
            motor_torque_request_nm = 0.0
            regen_enabled = (
                regenerative_braking_soc_threshold is not None
                and vehicle.battery.state_of_charge
                < regenerative_braking_soc_threshold
            )
            maximum_regenerative_brake_force_n = (
                vehicle.maximum_regenerative_brake_force_n(initial_speed_mps)
                if regen_enabled
                else 0.0
            )
            (
                front_pressure_psi,
                rear_pressure_psi,
                front_regenerative_brake_force_request_n,
                rear_regenerative_brake_force_request_n,
            ) = self._brake_controls_for_target_force(
                vehicle,
                brake_force_request_n=brake_force_request_n,
                target_acceleration_mps2=target_acceleration_mps2,
                lateral_force_n=lateral_force_n,
                curvature_per_m=curvature_per_m,
                maximum_regenerative_brake_force_n=(
                    maximum_regenerative_brake_force_n
                ),
                maximum_brake_pressure_psi=maximum_brake_pressure_psi,
            )
            pressure_limit_psi = min(
                vehicle.brakes.maximum_pressure_psi,
                maximum_brake_pressure_psi
                if maximum_brake_pressure_psi is not None
                else vehicle.brakes.maximum_pressure_psi,
            )
            brake_pressure_limited = (
                front_pressure_psi >= pressure_limit_psi - 1e-9
                or rear_pressure_psi >= pressure_limit_psi - 1e-9
            )
            if maximum_brake_pressure_psi is not None:
                brake_pressure_limited |= (
                    front_pressure_psi > maximum_brake_pressure_psi
                    or rear_pressure_psi > maximum_brake_pressure_psi
                )
                front_pressure_psi = min(
                    front_pressure_psi,
                    maximum_brake_pressure_psi,
                )
                rear_pressure_psi = min(
                    rear_pressure_psi,
                    maximum_brake_pressure_psi,
                )
        else:
            target_motor_torque_nm = (
                vehicle.drivetrain.motor_torque_for_wheel_force_nm(
                    max(force_for_target_n, 0.0)
                )
            )
            motor_torque_request_nm = min(
                profile_torque_nm,
                target_motor_torque_nm,
            )
            front_pressure_psi = 0.0
            rear_pressure_psi = 0.0
            front_regenerative_brake_force_request_n = 0.0
            rear_regenerative_brake_force_request_n = 0.0

        torque_limited = motor_torque_request_nm < profile_torque_nm - 1e-9
        return (
            Controls(
                motor_torque_request_nm=motor_torque_request_nm,
                front_brake_pressure_psi=front_pressure_psi,
                rear_brake_pressure_psi=rear_pressure_psi,
                front_regenerative_brake_force_request_n=(
                    front_regenerative_brake_force_request_n
                ),
                rear_regenerative_brake_force_request_n=(
                    rear_regenerative_brake_force_request_n
                ),
                steering_angle_rad=atan(
                    curvature_per_m * vehicle.chassis.wheelbase_m
                ),
            ),
            profile_torque_nm,
            torque_limited,
            brake_force_request_n,
            brake_pressure_limited,
        )

    @staticmethod
    def _exit_tire_force_tolerance_n(vehicle: Vehicle) -> float:
        """Allow small force-solve roundoff without hiding a grip deficit."""

        return max(1.0, 0.001 * vehicle.mass_kg * vehicle.gravity_mps2)

    def _cap_drive_for_exit_tire_capacity(
        self,
        *,
        vehicle: Vehicle,
        controls: Controls,
        cell_length_m: float,
        curvature_per_m: float,
    ) -> tuple[Controls, bool]:
        """Keep an automatic curved-cell request feasible at its exit speed.

        The force solve samples the cell entry. Preview only accelerating
        curved cells, then reduce the held motor request if its exit would
        exceed combined tire grip. The original vehicle is updated once with
        the chosen controls by ``run`` below.
        """

        if abs(curvature_per_m) <= 1e-15 or controls.motor_torque_request_nm <= 0.0:
            return controls, False

        original_torque_nm = controls.motor_torque_request_nm
        entry_resistance_n, _ = self._path_resistance_and_lateral_force_n(
            vehicle,
            speed_mps=vehicle.speed_mps,
            curvature_per_m=curvature_per_m,
        )

        def estimated_exit_margin_n(torque_nm: float) -> float:
            """Cheap upper-speed estimate before any full cell preview."""

            drive_request_n = vehicle.drivetrain.wheel_force_from_motor_torque_n(
                torque_nm
            )
            estimated_acceleration_mps2 = (
                drive_request_n - entry_resistance_n
            ) / vehicle.effective_longitudinal_mass_kg
            exit_speed_mps = sqrt(max(
                vehicle.speed_mps**2
                + 2.0 * estimated_acceleration_mps2 * cell_length_m,
                0.0,
            ))
            lateral_acceleration_mps2 = exit_speed_mps**2 * curvature_per_m
            aero_forces = vehicle.aero_forces_n(
                exit_speed_mps,
                lateral_acceleration_mps2,
                curvature_per_m=curvature_per_m,
            )
            required_lateral_n = (
                vehicle.mass_kg * abs(lateral_acceleration_mps2)
            )
            driven_axle = vehicle.drivetrain.driven_axle
            axle_indices = (
                (0, 1) if driven_axle == "front" else
                (2, 3) if driven_axle == "rear" else (0, 1, 2, 3)
            )
            margins_n = []
            entry_lateral_acceleration_mps2 = (
                vehicle.speed_mps**2 * curvature_per_m
            )
            entry_aero_forces = vehicle.aero_forces_n(
                vehicle.speed_mps,
                entry_lateral_acceleration_mps2,
                curvature_per_m=curvature_per_m,
            )
            for assumed_acceleration_mps2 in (
                0.0, estimated_acceleration_mps2
            ):
                entry_loads_n = vehicle.suspension.tire_normal_loads_n(
                    vehicle.mass_kg,
                    vehicle.gravity_mps2,
                    entry_aero_forces,
                    vehicle.chassis,
                    longitudinal_acceleration_mps2=assumed_acceleration_mps2,
                    lateral_acceleration_mps2=entry_lateral_acceleration_mps2,
                )
                entry_lateral_forces_n = vehicle.tire.lateral_forces_n(
                    entry_loads_n,
                    vehicle.mass_kg * entry_lateral_acceleration_mps2,
                )
                entry_longitudinal_capacities_n = tuple(
                    vehicle.tire.combined_longitudinal_force_capacity_n(
                        load_n, lateral_n,
                    )
                    for load_n, lateral_n in zip(
                        entry_loads_n.all_n,
                        entry_lateral_forces_n.all_n,
                        strict=True,
                    )
                )
                loads_n = vehicle.suspension.tire_normal_loads_n(
                    vehicle.mass_kg,
                    vehicle.gravity_mps2,
                    aero_forces,
                    vehicle.chassis,
                    longitudinal_acceleration_mps2=assumed_acceleration_mps2,
                    lateral_acceleration_mps2=lateral_acceleration_mps2,
                )
                lateral_capacity_n = sum(
                    vehicle.tire.lateral_force_capacity_n(load_n)
                    for load_n in loads_n.all_n
                )
                lateral_forces_n = vehicle.tire.lateral_forces_n(
                    loads_n,
                    vehicle.mass_kg * lateral_acceleration_mps2,
                )
                exit_longitudinal_capacities_n = tuple(
                    vehicle.tire.combined_longitudinal_force_capacity_n(
                        load_n, lateral_n,
                    )
                    for load_n, lateral_n in zip(
                        loads_n.all_n,
                        lateral_forces_n.all_n,
                        strict=True,
                    )
                )
                driven_entry_capacity_n = sum(
                    entry_longitudinal_capacities_n[index]
                    for index in axle_indices
                )
                if driven_entry_capacity_n > 0.0:
                    wheel_margins_n = (
                        exit_longitudinal_capacities_n[index]
                        - drive_request_n
                        * entry_longitudinal_capacities_n[index]
                        / driven_entry_capacity_n
                        for index in axle_indices
                    )
                    margins_n.append(min(
                        lateral_capacity_n - required_lateral_n,
                        *wheel_margins_n,
                    ))
                else:
                    margins_n.append(-drive_request_n)
            return min(margins_n)

        tolerance_n = self._exit_tire_force_tolerance_n(vehicle)
        estimate_buffer_n = max(4.0 * tolerance_n, 0.01 * vehicle.mass_kg * vehicle.gravity_mps2)
        try:
            requested_estimate_n = estimated_exit_margin_n(original_torque_nm)
        except (ValueError, OverflowError):
            # An upper-speed estimate can leave a component's supported
            # operating region even when the actual grip-limited step cannot.
            requested_estimate_n = float("-inf")
        if isfinite(requested_estimate_n) and requested_estimate_n >= estimate_buffer_n:
            return controls, False

        def preview_margin_n(torque_nm: float) -> float | None:
            candidate = deepcopy(vehicle)
            preview_controls = replace(controls, motor_torque_request_nm=torque_nm)
            try:
                candidate.update_state(preview_controls, cell_length_m)
                margin_n = candidate.exit_combined_tire_force_margin_n(
                    curvature_per_m
                )
            except ValueError:
                return None
            return margin_n if isfinite(margin_n) else None

        # The cheap estimate deliberately ignores entry tire and motor limits.
        # It may therefore warn about a request that the full vehicle model
        # finds feasible. Check that request before committing a lower torque.
        original_margin_n = preview_margin_n(original_torque_nm)
        if original_margin_n is not None and original_margin_n >= -tolerance_n:
            return controls, False

        try:
            estimated_coast_margin_n = estimated_exit_margin_n(0.0)
        except (ValueError, OverflowError):
            estimated_coast_margin_n = float("-inf")
        if isfinite(estimated_coast_margin_n) and estimated_coast_margin_n >= estimate_buffer_n:
            lower_torque_nm = 0.0
            upper_torque_nm = original_torque_nm
            for _ in range(15):
                candidate_torque_nm = 0.5 * (lower_torque_nm + upper_torque_nm)
                try:
                    candidate_margin_n = estimated_exit_margin_n(candidate_torque_nm)
                except (ValueError, OverflowError):
                    candidate_margin_n = float("-inf")
                if isfinite(candidate_margin_n) and candidate_margin_n >= estimate_buffer_n:
                    lower_torque_nm = candidate_torque_nm
                else:
                    upper_torque_nm = candidate_torque_nm
            controls = replace(
                controls, motor_torque_request_nm=lower_torque_nm
            )

        requested_torque_nm = controls.motor_torque_request_nm
        requested_margin_n = (
            original_margin_n
            if requested_torque_nm == original_torque_nm
            else preview_margin_n(requested_torque_nm)
        )
        if requested_margin_n is None or requested_margin_n >= -tolerance_n:
            return controls, requested_torque_nm < original_torque_nm - 1e-9

        coast_margin_n = preview_margin_n(0.0)
        if coast_margin_n is None or coast_margin_n < tolerance_n:
            # Even coasting needs another control action; the post-step gate
            # will keep this cell out of a completed result.
            return replace(controls, motor_torque_request_nm=0.0), True

        def margin_residual_n(torque_nm: float) -> float:
            margin_n = preview_margin_n(torque_nm)
            return margin_n - tolerance_n if margin_n is not None else -1e9

        root_torque_nm = brentq(
            margin_residual_n,
            0.0,
            requested_torque_nm,
            xtol=0.01,
            rtol=1e-4,
            maxiter=20,
        )
        # Stay on the known feasible side of the root. The final preview
        # catches a discontinuous motor or pack envelope before commitment.
        selected_torque_nm = max(
            root_torque_nm - max(0.05, 0.001 * requested_torque_nm),
            0.0,
        )
        selected_margin_n = preview_margin_n(selected_torque_nm)
        if selected_margin_n is None or selected_margin_n < -tolerance_n:
            lower_torque_nm = 0.0
            upper_torque_nm = selected_torque_nm
            for _ in range(8):
                candidate_torque_nm = 0.5 * (lower_torque_nm + upper_torque_nm)
                candidate_margin_n = preview_margin_n(candidate_torque_nm)
                if candidate_margin_n is not None and candidate_margin_n >= tolerance_n:
                    lower_torque_nm = candidate_torque_nm
                else:
                    upper_torque_nm = candidate_torque_nm
            selected_torque_nm = lower_torque_nm
        return replace(controls, motor_torque_request_nm=selected_torque_nm), True

    def run(
        self,
        vehicle: Vehicle,
        constraints: PathSpeedConstraints,
        profile: TorqueProfile | EnduranceControlProfile,
        config: EnduranceRunConfig,
        *,
        record_telemetry: bool = False,
        progress_callback: Callable[[LapProgressSnapshot], None] | None = None,
    ) -> EnduranceRunResult:
        track = constraints.track
        if not track.closed:
            raise ValueError("Endurance simulation requires a closed track")
        vehicle.validate()
        vehicle.reset_state()
        start_ceiling_mps = constraints.braking_speed_ceiling_mps[0]
        vehicle.speed_mps = (
            start_ceiling_mps
            if config.starting_speed_mps is None
            else config.starting_speed_mps
        )
        starting_speed_mps = vehicle.speed_mps
        accepted_time_s = vehicle.time_s
        accepted_distance_m = vehicle.distance_m
        accepted_speed_mps = vehicle.speed_mps
        accepted_state_of_charge = vehicle.battery.state_of_charge

        recorder = TelemetryRecorder() if record_telemetry else None
        energy_j = 0.0
        lap_times_s: list[float] = []
        completed_laps = 0
        failure_reason: str | None = None
        lap_start_time_s = 0.0
        cell_lengths_m = track.cell_length_m

        for lap_index in range(config.laps):
            for cell_index, cell_length_m in enumerate(cell_lengths_m):
                cell_update_completed = False
                next_cell_index = (cell_index + 1) % track.cell_count
                curvature_per_m = track.curvature_per_m[cell_index]
                target_speed_mps = constraints.braking_speed_ceiling_mps[
                    next_cell_index
                ]
                initial_speed_mps = vehicle.speed_mps
                if initial_speed_mps > (
                    constraints.local_corner_speed_mps[cell_index]
                    + config.path_speed_tolerance_mps
                ):
                    failure_reason = (
                        f"Car would spin out: supplied controls entered path cell "
                        f"{cell_index} on lap {lap_index + 1} above its local "
                        "corner-speed limit"
                    )
                    break
                if initial_speed_mps > (
                    constraints.braking_speed_ceiling_mps[cell_index]
                    + config.path_speed_tolerance_mps
                ):
                    failure_reason = (
                        "supplied controls entered a path cell above its braking "
                        "ceiling"
                    )
                    break

                lap_distance_m = track.cell_center_distance_m[cell_index]
                if isinstance(profile, EnduranceControlProfile):
                    controls = profile.controls_at(lap_distance_m)
                    if not isinstance(controls, Controls):
                        raise TypeError("controls_at must return Controls")
                    request_fraction = None
                    profile_torque_nm = None
                    path_torque_limited = False
                    path_brake_force_request_n = 0.0
                    path_brake_pressure_limited = False
                else:
                    request_fraction = profile.request_fraction(lap_distance_m)
                    (
                        controls,
                        profile_torque_nm,
                        path_torque_limited,
                        path_brake_force_request_n,
                        path_brake_pressure_limited,
                    ) = self._torque_profile_controls(
                        vehicle=vehicle,
                        request_fraction=request_fraction,
                        curvature_per_m=curvature_per_m,
                        cell_length_m=cell_length_m,
                        target_speed_mps=target_speed_mps,
                        current_cell_corner_speed_mps=(
                            constraints.local_corner_speed_mps[cell_index]
                        ),
                        maximum_brake_pressure_psi=(
                            config.maximum_brake_pressure_psi
                        ),
                        regenerative_braking_soc_threshold=(
                            config.regenerative_braking_soc_threshold
                        ),
                    )
                    controls, exit_tire_limited = (
                        self._cap_drive_for_exit_tire_capacity(
                            vehicle=vehicle,
                            controls=controls,
                            cell_length_m=cell_length_m,
                            curvature_per_m=curvature_per_m,
                        )
                    )
                    path_torque_limited |= exit_tire_limited
                time_before_step_s = vehicle.time_s
                try:
                    vehicle.update_state(controls, cell_length_m)
                except ValueError as error:
                    failure_reason = f"vehicle stalled on the endurance path: {error}"
                    break
                cell_update_completed = True
                timestep_s = vehicle.time_s - time_before_step_s
                if timestep_s <= 0.0:
                    failure_reason = "vehicle stalled on the endurance path"
                    break
                if (
                    abs(vehicle.requested_curvature_per_m - curvature_per_m)
                    > config.path_curvature_tolerance_per_m
                ):
                    failure_reason = (
                        "supplied steering did not follow prescribed path "
                        f"curvature at lap {lap_index + 1}, cell {cell_index}: "
                        f"requested {vehicle.requested_curvature_per_m:.8g} 1/m, "
                        f"path {curvature_per_m:.8g} 1/m"
                    )
                    break
                if (
                    abs(vehicle.curvature_per_m - curvature_per_m)
                    > config.path_curvature_tolerance_per_m
                ):
                    failure_reason = (
                        "vehicle could not achieve prescribed path curvature "
                        f"at lap {lap_index + 1}, cell {cell_index}: "
                        f"achieved {vehicle.curvature_per_m:.8g} 1/m, "
                        f"path {curvature_per_m:.8g} 1/m"
                    )
                    break
                if (
                    vehicle.speed_mps
                    > constraints.local_corner_speed_mps[cell_index]
                    + config.path_speed_tolerance_mps
                ):
                    failure_reason = (
                        "supplied controls exceeded the current cell corner-speed "
                        f"limit at lap {lap_index + 1}, cell {cell_index}: "
                        f"entered {initial_speed_mps:.6f} m/s, "
                        f"reached {vehicle.speed_mps:.6f} m/s, "
                        "limit "
                        f"{constraints.local_corner_speed_mps[cell_index]:.6f} m/s"
                    )
                    break
                if (
                    vehicle.speed_mps
                    > target_speed_mps + config.path_speed_tolerance_mps
                ):
                    failure_reason = (
                        "supplied controls exceeded the path ceiling "
                        f"at lap {lap_index + 1}, cell {cell_index}: "
                        f"entered {initial_speed_mps:.6f} m/s, "
                        f"reached {vehicle.speed_mps:.6f} m/s, "
                        f"ceiling {target_speed_mps:.6f} m/s; "
                        f"front pressure {controls.front_brake_pressure_psi:.2f} psi, "
                        f"rear pressure {controls.rear_brake_pressure_psi:.2f} psi"
                    )
                    break
                if abs(curvature_per_m) > 1e-15:
                    try:
                        exit_tire_margin_n = (
                            vehicle.exit_combined_tire_force_margin_n(curvature_per_m)
                        )
                    except ValueError as error:
                        failure_reason = (
                            "cannot evaluate combined tire force at the exit of "
                            f"lap {lap_index + 1}, cell {cell_index}: {error}"
                        )
                        break
                    if not isfinite(exit_tire_margin_n):
                        failure_reason = (
                            "nonfinite combined tire force at the exit of "
                            f"lap {lap_index + 1}, cell {cell_index}"
                        )
                        break
                    if exit_tire_margin_n < -self._exit_tire_force_tolerance_n(vehicle):
                        failure_reason = (
                            "supplied controls exceeded combined tire force at "
                            f"the exit of lap {lap_index + 1}, cell {cell_index}: "
                            f"force margin {exit_tire_margin_n:.6f} N"
                        )
                        break
                if vehicle.time_s > config.maximum_driving_time_s:
                    failure_reason = "maximum configured driving time exceeded"
                    break
                if vehicle.speed_mps < config.minimum_moving_speed_mps:
                    failure_reason = "vehicle stalled on the endurance path"
                    break
                energy_j += vehicle.battery.current_power_w * timestep_s
                if recorder is not None:
                    snapshot = vehicle.telemetry_snapshot()
                    snapshot.update(
                        {
                            "endurance.lap_index": float(lap_index),
                            "endurance.cell_index": float(cell_index),
                            "endurance.lap_distance_m": track.distance_m[
                                cell_index + 1
                            ],
                            "endurance.path_speed_ceiling_mps": target_speed_mps,
                            "energy.cumulative_net_j": energy_j,
                        }
                    )
                    if request_fraction is not None:
                        snapshot["endurance.torque_request_fraction"] = (
                            request_fraction
                        )
                        snapshot["endurance.profile_motor_torque_nm"] = (
                            profile_torque_nm
                        )
                        snapshot["endurance.path_torque_limited"] = float(
                            path_torque_limited
                        )
                        snapshot["endurance.path_brake_active"] = float(
                            path_brake_force_request_n > 0.0
                        )
                        snapshot["endurance.path_brake_force_request_n"] = (
                            path_brake_force_request_n
                        )
                        snapshot["endurance.path_brake_pressure_limited"] = float(
                            path_brake_pressure_limited
                        )
                    recorder.record(snapshot, timestep_s=timestep_s)
                accepted_time_s = vehicle.time_s
                accepted_distance_m = vehicle.distance_m
                accepted_speed_mps = vehicle.speed_mps
                accepted_state_of_charge = vehicle.battery.state_of_charge
                if progress_callback is not None:
                    progress_callback(LapProgressSnapshot(
                        lap_index=lap_index,
                        cell_index=cell_index,
                        cell_count=track.cell_count,
                        elapsed_time_s=vehicle.time_s,
                        lap_station_m=track.distance_m[cell_index + 1],
                        total_distance_m=vehicle.distance_m,
                        speed_mps=vehicle.speed_mps,
                        lateral_acceleration_mps2=(
                            vehicle.lateral_acceleration_mps2
                        ),
                        path_speed_ceiling_mps=target_speed_mps,
                        motor_torque_request_nm=controls.motor_torque_request_nm,
                        front_brake_pressure_psi=controls.front_brake_pressure_psi,
                        rear_brake_pressure_psi=controls.rear_brake_pressure_psi,
                        drive_force_n=vehicle.current_drive_force_n,
                        friction_braking_force_n=(
                            vehicle.current_friction_braking_force_n
                        ),
                        regenerative_braking_force_n=(
                            vehicle.current_regenerative_braking_force_n
                        ),
                        longitudinal_acceleration_mps2=(
                            vehicle.longitudinal_acceleration_mps2
                        ),
                        battery_power_w=vehicle.battery.current_power_w,
                    ))
                if vehicle.battery.state_of_charge <= 0.0:
                    failure_reason = "battery state of charge depleted"
                    break

            if failure_reason is not None:
                break
            completed_laps += 1
            lap_times_s.append(vehicle.time_s - lap_start_time_s)
            lap_start_time_s = vehicle.time_s

        telemetry = recorder.freeze() if recorder is not None else None
        return EnduranceRunResult(
            completed_laps=completed_laps,
            driving_time_s=vehicle.time_s,
            lap_times_s=tuple(lap_times_s),
            pack_energy_kwh=energy_j / JOULES_PER_KILOWATT_HOUR,
            final_state_of_charge=vehicle.battery.state_of_charge,
            failure_reason=failure_reason,
            telemetry=telemetry,
            starting_speed_mps=starting_speed_mps,
            ending_speed_mps=vehicle.speed_mps,
            accepted_time_s=accepted_time_s,
            accepted_distance_m=accepted_distance_m,
            accepted_speed_mps=accepted_speed_mps,
            accepted_state_of_charge=accepted_state_of_charge,
            failed_lap_index=lap_index if failure_reason is not None else None,
            failed_cell_index=cell_index if failure_reason is not None else None,
            failed_cell_update_completed=(
                cell_update_completed if failure_reason is not None else None
            ),
        )

__all__ = [
    "EnduranceRunConfig", "EnduranceRunResult", "EnduranceSimulator",
    "LapProgressSnapshot",
]
