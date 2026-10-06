"""Ten-state, four-wheel planar dynamics for bounded control experiments.

The state and force balances follow the independent-wheel model reviewed in
the supplied ENME408 EV simulation report (sections 5-7). Parameters here are
explicit synthetic inputs; this module does not claim a calibrated team car.
It deliberately does not use the quasi-static lap solver's rotating-mass
correction because four wheel angular speeds are integrated as states.
The regularized tire law is intended for forward driving; reverse handling is
qualitative and has not been validated against tire measurements.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, ceil, cos, hypot, isfinite, pi, sin
from typing import Sequence

from .conditions import DEFAULT_PLANAR_ENVIRONMENT, PlanarEnvironment


WHEEL_NAMES = ("front_left", "front_right", "rear_left", "rear_right")
WheelValues = tuple[float, float, float, float]
ZERO_WHEELS: WheelValues = (0.0, 0.0, 0.0, 0.0)
MAX_INTERNAL_SUBSTEPS = 100_000
MAX_RUN_STEPS = 100_000
STIFFNESS_STEP_SAFETY_FACTOR = 0.8


def _four_finite(values: WheelValues, name: str) -> None:
    if len(values) != 4 or not all(isfinite(value) for value in values):
        raise ValueError(f"{name} must contain four finite values in FL, FR, RL, RR order")


@dataclass(frozen=True, slots=True)
class PlanarVehicleConfig:
    """Explicit parameters for a synthetic planar car and identical tires.

    Axle distances are positive distances from the CG. Left is positive body Y,
    heading and yaw are positive counterclockwise. Tire stiffnesses refer to
    force per unit regularized slip ratio and force per radian, respectively.
    """

    mass_kg: float
    yaw_inertia_kgm2: float
    cg_to_front_axle_m: float
    cg_to_rear_axle_m: float
    front_track_m: float
    rear_track_m: float
    wheel_radius_m: float
    wheel_inertia_kgm2: float
    tire_mu: float
    longitudinal_stiffness_n_per_slip: float
    cornering_stiffness_n_per_rad: float
    low_speed_regularization_mps: float = 0.5
    gravity_mps2: float = 9.80665
    maximum_integration_step_s: float = 0.002

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if self.maximum_integration_step_s > 0.01:
            raise ValueError("maximum_integration_step_s cannot exceed 0.01 s")

    @property
    def wheel_positions_m(self) -> tuple[tuple[float, float], ...]:
        return (
            (self.cg_to_front_axle_m, self.front_track_m / 2.0),
            (self.cg_to_front_axle_m, -self.front_track_m / 2.0),
            (-self.cg_to_rear_axle_m, self.rear_track_m / 2.0),
            (-self.cg_to_rear_axle_m, -self.rear_track_m / 2.0),
        )

    @property
    def static_normal_loads_n(self) -> WheelValues:
        wheelbase_m = self.cg_to_front_axle_m + self.cg_to_rear_axle_m
        front_each_n = (
            self.mass_kg * self.gravity_mps2 * self.cg_to_rear_axle_m
            / (2.0 * wheelbase_m)
        )
        rear_each_n = (
            self.mass_kg * self.gravity_mps2 * self.cg_to_front_axle_m
            / (2.0 * wheelbase_m)
        )
        return (front_each_n, front_each_n, rear_each_n, rear_each_n)

    @property
    def integration_step_limit_s(self) -> float:
        """Bound explicit RK4 by the fastest low-speed small-slip mode.

        Linearizing four equal tire contacts around rolling gives an angular
        slip eigenvalue of approximately Cκ/v_floor*(R²/J + 4/m). A step of
        0.8/|eigenvalue| stays inside RK4 stability and leaves headroom for
        accuracy; the user-supplied maximum may impose a smaller step.
        """

        slip_rate_per_s = (
            self.longitudinal_stiffness_n_per_slip
            / self.low_speed_regularization_mps
            * (
                self.wheel_radius_m**2 / self.wheel_inertia_kgm2
                + 4.0 / self.mass_kg
            )
        )
        if not isfinite(slip_rate_per_s) or slip_rate_per_s <= 0.0:
            raise ValueError("tire stiffness produces an invalid integration rate")
        return min(
            self.maximum_integration_step_s,
            STIFFNESS_STEP_SAFETY_FACTOR / slip_rate_per_s,
        )


@dataclass(frozen=True, slots=True)
class PlanarState:
    """X, Y, yaw, body u/v, yaw rate, and FL/FR/RL/RR wheel speeds."""

    x_m: float = 0.0
    y_m: float = 0.0
    heading_rad: float = 0.0
    u_mps: float = 0.0
    v_mps: float = 0.0
    yaw_rate_rad_s: float = 0.0
    wheel_speeds_rad_s: WheelValues = ZERO_WHEELS

    def __post_init__(self) -> None:
        if not all(
            isfinite(value)
            for value in (
                self.x_m,
                self.y_m,
                self.heading_rad,
                self.u_mps,
                self.v_mps,
                self.yaw_rate_rad_s,
            )
        ):
            raise ValueError("planar state must be finite")
        _four_finite(self.wheel_speeds_rad_s, "wheel_speeds_rad_s")


@dataclass(frozen=True, slots=True)
class PlanarControls:
    """Independent wheel requests and optional externally supplied loads.

    Drive torque is signed, with negative values representing generating or
    reverse torque. Friction brake torque is a nonnegative magnitude opposing
    wheel rotation. Normal loads default to static axle loads; zero load gives
    a free-spinning wheel with zero tire force.
    """

    steering_angles_rad: WheelValues = ZERO_WHEELS
    drive_torques_nm: WheelValues = ZERO_WHEELS
    brake_torques_nm: WheelValues = ZERO_WHEELS
    normal_loads_n: WheelValues | None = None
    external_force_x_n: float = 0.0
    external_force_y_n: float = 0.0
    external_yaw_moment_nm: float = 0.0

    def __post_init__(self) -> None:
        _four_finite(self.steering_angles_rad, "steering_angles_rad")
        _four_finite(self.drive_torques_nm, "drive_torques_nm")
        _four_finite(self.brake_torques_nm, "brake_torques_nm")
        if any(abs(angle) >= pi / 2 for angle in self.steering_angles_rad):
            raise ValueError("steering angles must lie strictly within +/- pi/2")
        if any(torque < 0.0 for torque in self.brake_torques_nm):
            raise ValueError("brake_torques_nm cannot be negative")
        if self.normal_loads_n is not None:
            _four_finite(self.normal_loads_n, "normal_loads_n")
            if any(load < 0.0 for load in self.normal_loads_n):
                raise ValueError("normal_loads_n cannot be negative")
        if not all(
            isfinite(value)
            for value in (
                self.external_force_x_n,
                self.external_force_y_n,
                self.external_yaw_moment_nm,
            )
        ):
            raise ValueError("external body loads must be finite")


@dataclass(frozen=True, slots=True)
class PlanarWheel:
    """One contact patch's local motion, forces, and applied brake torque."""

    normal_load_n: float
    local_velocity_x_mps: float
    local_velocity_y_mps: float
    slip_ratio: float
    slip_angle_rad: float
    local_force_x_n: float
    local_force_y_n: float
    body_force_x_n: float
    body_force_y_n: float
    applied_brake_torque_nm: float
    friction_limit_n: float
    world_contact_x_m: float
    world_contact_y_m: float
    road_material_id: str
    road_friction_multiplier: float
    road_valid: bool

    @property
    def in_contact(self) -> bool:
        return self.normal_load_n > 0.0

    @property
    def force_magnitude_n(self) -> float:
        return hypot(self.local_force_x_n, self.local_force_y_n)

    @property
    def force_utilization(self) -> float:
        return (
            self.force_magnitude_n / self.friction_limit_n
            if self.friction_limit_n > 0.0
            else 0.0
        )


@dataclass(frozen=True, slots=True)
class PlanarDerivative:
    x_dot_mps: float
    y_dot_mps: float
    heading_dot_rad_s: float
    u_dot_mps2: float
    v_dot_mps2: float
    yaw_rate_dot_rad_s2: float
    wheel_accelerations_rad_s2: WheelValues


@dataclass(frozen=True, slots=True)
class PlanarEvaluation:
    """Instantaneous dynamics and mechanical-power accounting.

    The residual should be roundoff only: E_dot - actuator_power + contact
    dissipation - external_power = 0. Brake power is included in actuator
    power as a negative mechanical contribution.
    """

    derivative: PlanarDerivative
    wheels: tuple[PlanarWheel, PlanarWheel, PlanarWheel, PlanarWheel]
    total_body_force_x_n: float
    total_body_force_y_n: float
    total_yaw_moment_nm: float
    cg_longitudinal_acceleration_mps2: float
    cg_lateral_acceleration_mps2: float
    mechanical_energy_j: float
    mechanical_energy_rate_w: float
    drive_power_w: float
    brake_power_w: float
    external_power_w: float
    aero_power_w: float
    aero_body_force_x_n: float
    aero_body_force_y_n: float
    air_relative_body_x_mps: float
    air_relative_body_y_mps: float
    apparent_air_speed_mps: float
    road_valid: bool
    invalid_road_queries: int
    contact_dissipation_w: float
    energy_balance_residual_w: float


@dataclass(frozen=True, slots=True)
class PlanarRun:
    """Time-aligned trajectory and wheel diagnostics.

    ``times_s[i]`` and ``states[i]`` are state boundaries including the initial
    and final state. ``evaluations[i]`` contains the FL/FR/RL/RR wheel samples
    at ``states[i]``, before control interval ``i``; there is no final-point
    evaluation because no control is held beyond the last interval.
    """

    times_s: tuple[float, ...]
    states: tuple[PlanarState, ...]
    evaluations: tuple[PlanarEvaluation, ...]
    road_valid: bool = True
    invalid_road_queries: int = 0


def _wheel_world_position(
    state: PlanarState, position_x_m: float, position_y_m: float
) -> tuple[float, float]:
    heading_cosine = cos(state.heading_rad)
    heading_sine = sin(state.heading_rad)
    return (
        state.x_m + heading_cosine * position_x_m - heading_sine * position_y_m,
        state.y_m + heading_sine * position_x_m + heading_cosine * position_y_m,
    )


def _road_invalid_queries_at_state(
    config: PlanarVehicleConfig, state: PlanarState, environment: PlanarEnvironment
) -> int:
    return sum(
        not environment.road.query(*_wheel_world_position(state, x_m, y_m)).valid
        for x_m, y_m in config.wheel_positions_m
    )


def evaluate_planar_dynamics(
    config: PlanarVehicleConfig,
    state: PlanarState,
    controls: PlanarControls,
    *,
    environment: PlanarEnvironment | None = None,
) -> PlanarEvaluation:
    """Evaluate local tire forces and the ten first-order state derivatives."""

    conditions = DEFAULT_PLANAR_ENVIRONMENT if environment is None else environment
    if not isinstance(conditions, PlanarEnvironment):
        raise TypeError("environment must be PlanarEnvironment or None")
    normal_loads_n = (
        config.static_normal_loads_n
        if controls.normal_loads_n is None
        else controls.normal_loads_n
    )
    wheels: list[PlanarWheel] = []
    wheel_accelerations: list[float] = []
    body_force_x_n = 0.0
    body_force_y_n = 0.0
    tire_yaw_moment_nm = 0.0
    contact_dissipation_w = 0.0
    drive_power_w = 0.0
    brake_power_w = 0.0
    invalid_road_queries = 0

    heading_cosine = cos(state.heading_rad)
    heading_sine = sin(state.heading_rad)
    wind_body_x_mps = (
        heading_cosine * conditions.wind_world_x_mps
        + heading_sine * conditions.wind_world_y_mps
    )
    wind_body_y_mps = (
        -heading_sine * conditions.wind_world_x_mps
        + heading_cosine * conditions.wind_world_y_mps
    )
    air_relative_body_x_mps = state.u_mps - wind_body_x_mps
    air_relative_body_y_mps = state.v_mps - wind_body_y_mps
    apparent_air_speed_mps = hypot(
        air_relative_body_x_mps, air_relative_body_y_mps
    )
    drag_scale = (
        -0.5
        * conditions.air_density_kgpm3
        * conditions.drag_area_m2
        * apparent_air_speed_mps
    )
    aero_body_force_x_n = drag_scale * air_relative_body_x_mps
    aero_body_force_y_n = drag_scale * air_relative_body_y_mps
    aero_power_w = (
        aero_body_force_x_n * state.u_mps
        + aero_body_force_y_n * state.v_mps
    )

    for index, (position_x_m, position_y_m) in enumerate(config.wheel_positions_m):
        world_contact_x_m = (
            state.x_m
            + heading_cosine * position_x_m
            - heading_sine * position_y_m
        )
        world_contact_y_m = (
            state.y_m
            + heading_sine * position_x_m
            + heading_cosine * position_y_m
        )
        road_sample = conditions.road.query(world_contact_x_m, world_contact_y_m)
        invalid_road_queries += not road_sample.valid
        steer_rad = controls.steering_angles_rad[index]
        c = cos(steer_rad)
        s = sin(steer_rad)
        body_velocity_x_mps = state.u_mps - state.yaw_rate_rad_s * position_y_m
        body_velocity_y_mps = state.v_mps + state.yaw_rate_rad_s * position_x_m
        local_velocity_x_mps = c * body_velocity_x_mps + s * body_velocity_y_mps
        local_velocity_y_mps = -s * body_velocity_x_mps + c * body_velocity_y_mps
        omega_rad_s = state.wheel_speeds_rad_s[index]
        wheel_surface_speed_mps = config.wheel_radius_m * omega_rad_s
        normal_load_n = normal_loads_n[index]

        if normal_load_n == 0.0:
            slip_ratio = 0.0
            slip_angle_rad = 0.0
            local_force_x_n = 0.0
            local_force_y_n = 0.0
        else:
            # At forward speed above the floor this is exactly the usual
            # kappa=(R*omega-Vx)/Vx. The floor regularizes launch and lock.
            reference_speed_mps = max(
                abs(local_velocity_x_mps), config.low_speed_regularization_mps
            )
            slip_ratio = (
                wheel_surface_speed_mps - local_velocity_x_mps
            ) / reference_speed_mps
            slip_angle_rad = atan2(local_velocity_y_mps, reference_speed_mps)
            requested_force_x_n = (
                config.longitudinal_stiffness_n_per_slip * slip_ratio
            )
            requested_force_y_n = (
                -config.cornering_stiffness_n_per_rad * slip_angle_rad
            )
            requested_magnitude_n = hypot(requested_force_x_n, requested_force_y_n)
            force_limit_n = (
                config.tire_mu * road_sample.friction_multiplier * normal_load_n
            )
            scale = (
                min(1.0, force_limit_n / requested_magnitude_n)
                if requested_magnitude_n > 0.0
                else 1.0
            )
            local_force_x_n = scale * requested_force_x_n
            local_force_y_n = scale * requested_force_y_n

        wheel_body_force_x_n = c * local_force_x_n - s * local_force_y_n
        wheel_body_force_y_n = s * local_force_x_n + c * local_force_y_n
        body_force_x_n += wheel_body_force_x_n
        body_force_y_n += wheel_body_force_y_n
        tire_yaw_moment_nm += (
            position_x_m * wheel_body_force_y_n
            - position_y_m * wheel_body_force_x_n
        )

        drive_torque_nm = controls.drive_torques_nm[index]
        brake_request_nm = controls.brake_torques_nm[index]
        torque_without_brake_nm = (
            drive_torque_nm - config.wheel_radius_m * local_force_x_n
        )
        if omega_rad_s > 0.0:
            applied_brake_torque_nm = -brake_request_nm
        elif omega_rad_s < 0.0:
            applied_brake_torque_nm = brake_request_nm
        elif torque_without_brake_nm > 0.0:
            applied_brake_torque_nm = -min(
                brake_request_nm, torque_without_brake_nm
            )
        else:
            applied_brake_torque_nm = min(
                brake_request_nm, -torque_without_brake_nm
            )
        wheel_accelerations.append(
            (torque_without_brake_nm + applied_brake_torque_nm)
            / config.wheel_inertia_kgm2
        )
        drive_power_w += drive_torque_nm * omega_rad_s
        brake_power_w += applied_brake_torque_nm * omega_rad_s
        contact_dissipation_w += (
            local_force_x_n * (wheel_surface_speed_mps - local_velocity_x_mps)
            - local_force_y_n * local_velocity_y_mps
        )
        wheels.append(
            PlanarWheel(
                normal_load_n=normal_load_n,
                local_velocity_x_mps=local_velocity_x_mps,
                local_velocity_y_mps=local_velocity_y_mps,
                slip_ratio=slip_ratio,
                slip_angle_rad=slip_angle_rad,
                local_force_x_n=local_force_x_n,
                local_force_y_n=local_force_y_n,
                body_force_x_n=wheel_body_force_x_n,
                body_force_y_n=wheel_body_force_y_n,
                applied_brake_torque_nm=applied_brake_torque_nm,
                friction_limit_n=(
                    config.tire_mu * road_sample.friction_multiplier * normal_load_n
                ),
                world_contact_x_m=world_contact_x_m,
                world_contact_y_m=world_contact_y_m,
                road_material_id=road_sample.material_id,
                road_friction_multiplier=road_sample.friction_multiplier,
                road_valid=road_sample.valid,
            )
        )

    total_body_force_x_n = (
        body_force_x_n + controls.external_force_x_n + aero_body_force_x_n
    )
    total_body_force_y_n = (
        body_force_y_n + controls.external_force_y_n + aero_body_force_y_n
    )
    total_yaw_moment_nm = tire_yaw_moment_nm + controls.external_yaw_moment_nm
    u_dot_mps2 = (
        state.yaw_rate_rad_s * state.v_mps
        + total_body_force_x_n / config.mass_kg
    )
    v_dot_mps2 = (
        -state.yaw_rate_rad_s * state.u_mps
        + total_body_force_y_n / config.mass_kg
    )
    yaw_rate_dot_rad_s2 = total_yaw_moment_nm / config.yaw_inertia_kgm2
    derivative = PlanarDerivative(
        x_dot_mps=(
            state.u_mps * cos(state.heading_rad)
            - state.v_mps * sin(state.heading_rad)
        ),
        y_dot_mps=(
            state.u_mps * sin(state.heading_rad)
            + state.v_mps * cos(state.heading_rad)
        ),
        heading_dot_rad_s=state.yaw_rate_rad_s,
        u_dot_mps2=u_dot_mps2,
        v_dot_mps2=v_dot_mps2,
        yaw_rate_dot_rad_s2=yaw_rate_dot_rad_s2,
        wheel_accelerations_rad_s2=tuple(wheel_accelerations),
    )
    mechanical_energy_j = (
        0.5 * config.mass_kg * (state.u_mps**2 + state.v_mps**2)
        + 0.5 * config.yaw_inertia_kgm2 * state.yaw_rate_rad_s**2
        + 0.5
        * config.wheel_inertia_kgm2
        * sum(omega**2 for omega in state.wheel_speeds_rad_s)
    )
    mechanical_energy_rate_w = (
        config.mass_kg * (
            state.u_mps * u_dot_mps2 + state.v_mps * v_dot_mps2
        )
        + config.yaw_inertia_kgm2
        * state.yaw_rate_rad_s
        * yaw_rate_dot_rad_s2
        + config.wheel_inertia_kgm2
        * sum(
            omega * omega_dot
            for omega, omega_dot in zip(
                state.wheel_speeds_rad_s, wheel_accelerations, strict=True
            )
        )
    )
    external_power_w = (
        state.u_mps * controls.external_force_x_n
        + state.v_mps * controls.external_force_y_n
        + state.yaw_rate_rad_s * controls.external_yaw_moment_nm
        + aero_power_w
    )
    energy_balance_residual_w = (
        mechanical_energy_rate_w
        - drive_power_w
        - brake_power_w
        + contact_dissipation_w
        - external_power_w
    )
    return PlanarEvaluation(
        derivative=derivative,
        wheels=tuple(wheels),
        total_body_force_x_n=total_body_force_x_n,
        total_body_force_y_n=total_body_force_y_n,
        total_yaw_moment_nm=total_yaw_moment_nm,
        cg_longitudinal_acceleration_mps2=total_body_force_x_n / config.mass_kg,
        cg_lateral_acceleration_mps2=total_body_force_y_n / config.mass_kg,
        mechanical_energy_j=mechanical_energy_j,
        mechanical_energy_rate_w=mechanical_energy_rate_w,
        drive_power_w=drive_power_w,
        brake_power_w=brake_power_w,
        external_power_w=external_power_w,
        aero_power_w=aero_power_w,
        aero_body_force_x_n=aero_body_force_x_n,
        aero_body_force_y_n=aero_body_force_y_n,
        air_relative_body_x_mps=air_relative_body_x_mps,
        air_relative_body_y_mps=air_relative_body_y_mps,
        apparent_air_speed_mps=apparent_air_speed_mps,
        road_valid=invalid_road_queries == 0,
        invalid_road_queries=invalid_road_queries,
        contact_dissipation_w=contact_dissipation_w,
        energy_balance_residual_w=energy_balance_residual_w,
    )


def _advance(state: PlanarState, derivative: PlanarDerivative, dt_s: float) -> PlanarState:
    return PlanarState(
        x_m=state.x_m + dt_s * derivative.x_dot_mps,
        y_m=state.y_m + dt_s * derivative.y_dot_mps,
        heading_rad=state.heading_rad + dt_s * derivative.heading_dot_rad_s,
        u_mps=state.u_mps + dt_s * derivative.u_dot_mps2,
        v_mps=state.v_mps + dt_s * derivative.v_dot_mps2,
        yaw_rate_rad_s=(
            state.yaw_rate_rad_s + dt_s * derivative.yaw_rate_dot_rad_s2
        ),
        wheel_speeds_rad_s=tuple(
            omega + dt_s * acceleration
            for omega, acceleration in zip(
                state.wheel_speeds_rad_s,
                derivative.wheel_accelerations_rad_s2,
                strict=True,
            )
        ),
    )


def _rk4_step(
    config: PlanarVehicleConfig,
    state: PlanarState,
    controls: PlanarControls,
    dt_s: float,
    environment: PlanarEnvironment,
) -> tuple[PlanarState, int]:
    first = evaluate_planar_dynamics(
        config, state, controls, environment=environment
    )
    k1 = first.derivative
    second = evaluate_planar_dynamics(
        config, _advance(state, k1, dt_s / 2.0), controls,
        environment=environment,
    )
    k2 = second.derivative
    third = evaluate_planar_dynamics(
        config, _advance(state, k2, dt_s / 2.0), controls,
        environment=environment,
    )
    k3 = third.derivative
    fourth = evaluate_planar_dynamics(
        config, _advance(state, k3, dt_s), controls,
        environment=environment,
    )
    k4 = fourth.derivative
    invalid_road_queries = sum(
        evaluation.invalid_road_queries
        for evaluation in (first, second, third, fourth)
    )
    factor = dt_s / 6.0
    final_state = PlanarState(
        x_m=state.x_m + factor * (
            k1.x_dot_mps + 2.0 * k2.x_dot_mps + 2.0 * k3.x_dot_mps + k4.x_dot_mps
        ),
        y_m=state.y_m + factor * (
            k1.y_dot_mps + 2.0 * k2.y_dot_mps + 2.0 * k3.y_dot_mps + k4.y_dot_mps
        ),
        heading_rad=state.heading_rad + factor * (
            k1.heading_dot_rad_s
            + 2.0 * k2.heading_dot_rad_s
            + 2.0 * k3.heading_dot_rad_s
            + k4.heading_dot_rad_s
        ),
        u_mps=state.u_mps + factor * (
            k1.u_dot_mps2 + 2.0 * k2.u_dot_mps2 + 2.0 * k3.u_dot_mps2 + k4.u_dot_mps2
        ),
        v_mps=state.v_mps + factor * (
            k1.v_dot_mps2 + 2.0 * k2.v_dot_mps2 + 2.0 * k3.v_dot_mps2 + k4.v_dot_mps2
        ),
        yaw_rate_rad_s=state.yaw_rate_rad_s + factor * (
            k1.yaw_rate_dot_rad_s2
            + 2.0 * k2.yaw_rate_dot_rad_s2
            + 2.0 * k3.yaw_rate_dot_rad_s2
            + k4.yaw_rate_dot_rad_s2
        ),
        wheel_speeds_rad_s=tuple(
            omega + factor * (a1 + 2.0 * a2 + 2.0 * a3 + a4)
            for omega, a1, a2, a3, a4 in zip(
                state.wheel_speeds_rad_s,
                k1.wheel_accelerations_rad_s2,
                k2.wheel_accelerations_rad_s2,
                k3.wheel_accelerations_rad_s2,
                k4.wheel_accelerations_rad_s2,
                strict=True,
            )
        ),
    )
    # Static friction brakes may hold a stopped wheel. Prevent a finite RK
    # step from numerically crossing zero and spinning it backward.
    wheel_speeds = list(final_state.wheel_speeds_rad_s)
    for index, (before, after) in enumerate(
        zip(state.wheel_speeds_rad_s, wheel_speeds, strict=True)
    ):
        if controls.brake_torques_nm[index] <= 0.0:
            continue
        drive_torque = controls.drive_torques_nm[index]
        initial_acceleration = k1.wheel_accelerations_rad_s2[index]
        forward_stop_within_step = (
            before > 0.0
            and initial_acceleration < 0.0
            and before <= -dt_s * initial_acceleration
        )
        reverse_stop_within_step = (
            before < 0.0
            and initial_acceleration > 0.0
            and -before <= dt_s * initial_acceleration
        )
        if (after < 0.0 or forward_stop_within_step) and before > 0.0 and drive_torque >= 0.0:
            wheel_speeds[index] = 0.0
        elif (after > 0.0 or reverse_stop_within_step) and before < 0.0 and drive_torque <= 0.0:
            wheel_speeds[index] = 0.0
    return PlanarState(
        x_m=final_state.x_m,
        y_m=final_state.y_m,
        heading_rad=final_state.heading_rad,
        u_mps=final_state.u_mps,
        v_mps=final_state.v_mps,
        yaw_rate_rad_s=final_state.yaw_rate_rad_s,
        wheel_speeds_rad_s=tuple(wheel_speeds),
    ), invalid_road_queries


def _step_planar_with_status(
    config: PlanarVehicleConfig,
    state: PlanarState,
    controls: PlanarControls,
    dt_s: float,
    environment: PlanarEnvironment,
) -> tuple[PlanarState, int]:
    if not isfinite(dt_s) or dt_s <= 0.0:
        raise ValueError("dt_s must be finite and positive")
    substep_count = ceil(dt_s / config.integration_step_limit_s)
    if substep_count > MAX_INTERNAL_SUBSTEPS:
        raise ValueError("dt_s requests too many internal integration steps")
    substep_s = dt_s / substep_count
    result = state
    invalid_road_queries = 0
    for _ in range(substep_count):
        result, invalid_in_substep = _rk4_step(
            config, result, controls, substep_s, environment
        )
        invalid_road_queries += invalid_in_substep
    return result, invalid_road_queries


def step_planar_dynamics(
    config: PlanarVehicleConfig,
    state: PlanarState,
    controls: PlanarControls,
    dt_s: float,
    *,
    environment: PlanarEnvironment | None = None,
) -> PlanarState:
    """Advance one hold, rejecting any out-of-domain RK force evaluation."""

    conditions = DEFAULT_PLANAR_ENVIRONMENT if environment is None else environment
    if not isinstance(conditions, PlanarEnvironment):
        raise TypeError("environment must be PlanarEnvironment or None")
    result, invalid_road_queries = _step_planar_with_status(
        config, state, controls, dt_s, conditions
    )
    invalid_road_queries += _road_invalid_queries_at_state(
        config, result, conditions
    )
    if invalid_road_queries:
        raise ValueError(
            f"road query left the valid domain ({invalid_road_queries} invalid queries)"
        )
    return result


def run_planar_dynamics(
    config: PlanarVehicleConfig,
    initial_state: PlanarState,
    controls: Sequence[PlanarControls],
    dt_s: float,
    *,
    environment: PlanarEnvironment | None = None,
) -> PlanarRun:
    """Run held controls and retain invalid road-query status from RK stages."""

    conditions = DEFAULT_PLANAR_ENVIRONMENT if environment is None else environment
    if not isinstance(conditions, PlanarEnvironment):
        raise TypeError("environment must be PlanarEnvironment or None")
    if not isfinite(dt_s) or dt_s <= 0.0:
        raise ValueError("dt_s must be finite and positive")
    if len(controls) > MAX_RUN_STEPS:
        raise ValueError("controls sequence is too long")
    if len(controls) * ceil(dt_s / config.integration_step_limit_s) > MAX_INTERNAL_SUBSTEPS:
        raise ValueError("run requests too many internal integration steps")
    states = [initial_state]
    evaluations: list[PlanarEvaluation] = []
    invalid_road_queries = 0
    for command in controls:
        evaluation = evaluate_planar_dynamics(
            config, states[-1], command, environment=conditions
        )
        evaluations.append(evaluation)
        invalid_road_queries += evaluation.invalid_road_queries
        next_state, invalid_in_substeps = _step_planar_with_status(
            config, states[-1], command, dt_s, conditions
        )
        invalid_road_queries += invalid_in_substeps
        states.append(next_state)
    invalid_road_queries += _road_invalid_queries_at_state(
        config, states[-1], conditions
    )
    return PlanarRun(
        times_s=tuple(index * dt_s for index in range(len(states))),
        states=tuple(states),
        evaluations=tuple(evaluations),
        road_valid=invalid_road_queries == 0,
        invalid_road_queries=invalid_road_queries,
    )


class PlanarSimulator:
    """Small stateful wrapper for repeated time-domain control steps."""

    def __init__(
        self,
        config: PlanarVehicleConfig,
        initial_state: PlanarState | None = None,
        *,
        environment: PlanarEnvironment | None = None,
    ) -> None:
        self.config = config
        self.state = PlanarState() if initial_state is None else initial_state
        self.environment = (
            DEFAULT_PLANAR_ENVIRONMENT if environment is None else environment
        )
        if not isinstance(self.environment, PlanarEnvironment):
            raise TypeError("environment must be PlanarEnvironment or None")
        self.time_s = 0.0
        self.road_valid = True
        self.invalid_road_queries = 0

    def step(self, controls: PlanarControls, dt_s: float) -> PlanarEvaluation:
        evaluation = evaluate_planar_dynamics(
            self.config, self.state, controls, environment=self.environment
        )
        next_state, invalid_in_substeps = _step_planar_with_status(
            self.config, self.state, controls, dt_s, self.environment
        )
        invalid_in_final_state = _road_invalid_queries_at_state(
            self.config, next_state, self.environment
        )
        self.invalid_road_queries += (
            evaluation.invalid_road_queries
            + invalid_in_substeps
            + invalid_in_final_state
        )
        self.road_valid = self.invalid_road_queries == 0
        self.state = next_state
        self.time_s += dt_s
        return evaluation
