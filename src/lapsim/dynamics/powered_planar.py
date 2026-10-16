"""Pure augmented RK4: existing planar physics plus actuator and energy states."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite

from .actuation import ActuationConfig, constrain_actuation, four_numbers
from .bicycle import _finite
from .planar import (
    PlanarControls,
    PlanarEnvironment,
    PlanarState,
    PlanarVehicleConfig,
    evaluate_planar_dynamics,
)


@dataclass(frozen=True, slots=True)
class PoweredState:
    plant: PlanarState
    actuator_memory_nm: tuple[float, float, float, float]
    pack_energy_j: float
    wheel_work_j: float = 0.0
    conversion_loss_j: float = 0.0
    contact_dissipation_j: float = 0.0
    friction_brake_work_j: float = 0.0
    external_work_j: float = 0.0
    driver_proxy_impulse_ns: float = 0.0
    tire_longitudinal_impulse_ns: float = 0.0
    absolute_contact_force_error_ns: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.plant, PlanarState):
            raise TypeError("powered state requires a PlanarState")
        four_numbers(self.actuator_memory_nm, "actuator memory")
        for name in (
            "pack_energy_j",
            "wheel_work_j",
            "conversion_loss_j",
            "contact_dissipation_j",
            "friction_brake_work_j",
            "external_work_j",
            "driver_proxy_impulse_ns",
            "tire_longitudinal_impulse_ns",
            "absolute_contact_force_error_ns",
        ):
            _finite(getattr(self, name), name)


def _vector(state: PoweredState) -> tuple:
    p = state.plant
    return (
        p.x_m,
        p.y_m,
        p.heading_rad,
        p.u_mps,
        p.v_mps,
        p.yaw_rate_rad_s,
        *p.wheel_speeds_rad_s,
        *state.actuator_memory_nm,
        state.pack_energy_j,
        state.wheel_work_j,
        state.conversion_loss_j,
        state.contact_dissipation_j,
        state.friction_brake_work_j,
        state.external_work_j,
        state.driver_proxy_impulse_ns,
        state.tire_longitudinal_impulse_ns,
        state.absolute_contact_force_error_ns,
    )


def _state(values: tuple) -> PoweredState:
    return PoweredState(
        PlanarState(
            values[0],
            values[1],
            values[2],
            values[3],
            values[4],
            values[5],
            four_numbers(values[6:10], "wheel speeds"),
        ),
        four_numbers(values[10:14], "actuator memory"),
        pack_energy_j=values[14],
        wheel_work_j=values[15],
        conversion_loss_j=values[16],
        contact_dissipation_j=values[17],
        friction_brake_work_j=values[18],
        external_work_j=values[19],
        driver_proxy_impulse_ns=values[20],
        tire_longitudinal_impulse_ns=values[21],
        absolute_contact_force_error_ns=values[22],
    )


def evaluate_powered(
    config: PlanarVehicleConfig,
    actuation: ActuationConfig,
    state: PoweredState,
    command_nm: tuple,
    steering: tuple,
    brakes: tuple,
    available: tuple,
    horizon_s: float,
    environment: PlanarEnvironment,
    driver_proxy_n: float = 0.0,
):
    electrical = constrain_actuation(
        actuation,
        state.actuator_memory_nm,
        state.plant.wheel_speeds_rad_s,
        state.pack_energy_j,
        horizon_s,
        available,
    )
    physical = evaluate_planar_dynamics(
        config,
        state.plant,
        PlanarControls(
            steering_angles_rad=steering,
            drive_torques_nm=electrical.wheel_torques_nm,
            brake_torques_nm=brakes,
        ),
        environment=environment,
    )
    d = physical.derivative
    contact_force = sum(w.body_force_x_n for w in physical.wheels)
    memory_rate = tuple(
        max(
            -actuation.actuator_slew_nm_per_s,
            min(
                actuation.actuator_slew_nm_per_s,
                (command - value) / actuation.actuator_time_constant_s,
            ),
        )
        for command, value in zip(command_nm, state.actuator_memory_nm, strict=True)
    )
    derivative = (
        d.x_dot_mps,
        d.y_dot_mps,
        d.heading_dot_rad_s,
        d.u_dot_mps2,
        d.v_dot_mps2,
        d.yaw_rate_dot_rad_s2,
        *d.wheel_accelerations_rad_s2,
        *memory_rate,
        -electrical.pack_power_w,
        electrical.wheel_power_w,
        electrical.conversion_loss_w,
        physical.contact_dissipation_w,
        physical.brake_power_w,
        physical.external_power_w,
        driver_proxy_n,
        contact_force,
        abs(driver_proxy_n - contact_force),
    )
    if not all(isfinite(value) for value in derivative):
        raise ValueError("powered derivative exceeds the finite numerical domain")
    return derivative, physical, electrical


def advance_powered(
    config: PlanarVehicleConfig,
    actuation: ActuationConfig,
    state: PoweredState,
    command_nm: tuple,
    steering: tuple,
    brakes: tuple,
    available: tuple,
    timestep_s: float,
    environment: PlanarEnvironment | None = None,
    *,
    driver_proxy_n: float = 0.0,
) -> PoweredState:
    """One held-command interval. No controller, sensor or random state exists here."""
    command_nm = four_numbers(command_nm, "command")
    steering = four_numbers(steering, "steering")
    brakes = four_numbers(brakes, "brakes")
    _finite(timestep_s, "timestep_s")
    _finite(driver_proxy_n, "driver_proxy_n")
    if timestep_s <= 0 or timestep_s > 0.01:
        raise ValueError("powered plant step must be in (0, 0.01] s")
    limit = min(config.integration_step_limit_s, actuation.actuator_time_constant_s / 4)
    count = ceil(timestep_s / limit)
    if count > 50_000:
        raise ValueError("powered integration exceeds the work budget")
    h = timestep_s / count
    conditions = environment or PlanarEnvironment()
    for _ in range(count):
        value = _vector(state)

        def derivative(values):
            return evaluate_powered(
                config,
                actuation,
                _state(values),
                command_nm,
                steering,
                brakes,
                available,
                h,
                conditions,
                driver_proxy_n,
            )[0]

        def shifted(rate, scale, base=value):
            return tuple(x + scale * dx for x, dx in zip(base, rate, strict=True))

        k1 = derivative(value)
        k2 = derivative(shifted(k1, h / 2))
        k3 = derivative(shifted(k2, h / 2))
        k4 = derivative(shifted(k3, h))
        state = _state(
            tuple(
                x + h / 6 * (a + 2 * b + 2 * c + d)
                for x, a, b, c, d in zip(value, k1, k2, k3, k4, strict=True)
            )
        )
        if not 0 <= state.pack_energy_j <= actuation.pack_capacity_j:
            raise ValueError(
                "pack energy crossed its physical bounds; integration rejected"
            )
    return state


def energy_residual_j(
    config: PlanarVehicleConfig, initial: PoweredState, final: PoweredState
) -> float:
    def mechanical(state):
        p = state.plant
        return (
            0.5 * config.mass_kg * (p.u_mps * p.u_mps + p.v_mps * p.v_mps)
            + 0.5 * config.yaw_inertia_kgm2 * p.yaw_rate_rad_s * p.yaw_rate_rad_s
            + 0.5 * config.wheel_inertia_kgm2 * sum(w * w for w in p.wheel_speeds_rad_s)
        )

    return (
        mechanical(final)
        - mechanical(initial)
        + final.pack_energy_j
        - initial.pack_energy_j
        + final.conversion_loss_j
        - initial.conversion_loss_j
        + final.contact_dissipation_j
        - initial.contact_dissipation_j
        - (final.friction_brake_work_j - initial.friction_brake_work_j)
        - (final.external_work_j - initial.external_work_j)
    )
