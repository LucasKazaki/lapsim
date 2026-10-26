"""Pure augmented RK4: existing planar physics plus actuator and energy states."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil, isfinite

from .actuation import ActuationConfig, constrain_actuation, four_numbers, SINGLE_MOTOR_RWD_TOPOLOGY_ID, SPOOL_RWD_TOPOLOGY_ID
from .bicycle import _finite
from .planar import (
    PlanarControls,
    PlanarEnvironment,
    PlanarState,
    PlanarVehicleConfig,
    evaluate_planar_dynamics,
)

BRAKE_STOP_SPEED_RAD_S = 1e-9
MAX_POWERED_WORK = 50_000
MAX_ALLOCATED_POWERED_WORK = 200_000


class _BrakeStopTrial(Exception):
    """An unaccepted numerical stage crossed a friction-braked wheel stop."""


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
    wheel_stop_dissipation_j: float = 0.0
    integration_substeps: int = 0
    integration_trials: int = 0
    wheel_stop_events: int = 0

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
            "wheel_stop_dissipation_j",
        ):
            _finite(getattr(self, name), name)
        for name in ("integration_substeps", "integration_trials", "wheel_stop_events"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError("integration counters must be nonnegative integers")
        if self.wheel_stop_dissipation_j < 0:
            raise ValueError("wheel-stop dissipation cannot be negative")


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


def _couple_locked_rear(config, state, physical, drive_nm, brakes_nm, radii_m):
    """Ideal rigid shaft; reaction is internal and does zero total shaft work."""
    omega = state.plant.wheel_speeds_rad_s
    if omega[2] != omega[3]:
        raise ValueError('locked axle requires equal rear angular velocity')
    free = physical.derivative.wheel_accelerations_rad_s2
    wheels = list(physical.wheels)
    moments = [config.wheel_inertia_kgm2 * free[i] for i in (2,3)]
    net_shaft_moment = sum(moments)
    if omega[2] == 0:
        # Static friction acts on the shaft, not on two independently stopped
        # wheels. One rear brake can hold the motor's entire shared moment.
        unbraked = [drive_nm[i]-radii_m[i]*wheels[i].local_force_x_n for i in (2,3)]
        capacity = brakes_nm[2]+brakes_nm[3]
        applied = -max(-capacity,min(capacity,sum(unbraked)))
        # Solve the scalar shaft balance before redistributing it. Summing
        # individually cancelled wheel moments can invent a tiny negative
        # acceleration at an exactly held zero-speed shaft, defeating stops.
        net_shaft_moment = sum(unbraked)+applied
        for index,i in enumerate((2,3)):
            brake = applied*brakes_nm[i]/capacity if capacity else 0.
            moments[index] = unbraked[index]+brake
            wheels[i] = replace(wheels[i],applied_brake_torque_nm=brake)
    common = net_shaft_moment/(2*config.wheel_inertia_kgm2)
    reaction = config.wheel_inertia_kgm2*common-moments[0]
    derivative = replace(physical.derivative,wheel_accelerations_rad_s2=(*free[:2],common,common))
    return replace(physical,derivative=derivative,wheels=tuple(wheels),
                   axle_constraint_reactions_nm=(0.,0.,reaction,-reaction))


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
    *, wheel_radii_m=None,
):
    if actuation.topology_id in (SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID):
        command = four_numbers(command_nm, "single-motor command")
        if command[0] != 0 or command[1] != 0 or command[2] != command[3]:
            raise ValueError("single-motor command requires zero front and equal rear torques")
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
            wheel_radii_m=wheel_radii_m,
        ),
        environment=environment,
    )
    if actuation.topology_id == SPOOL_RWD_TOPOLOGY_ID:
        physical = _couple_locked_rear(config,state,physical,electrical.wheel_torques_nm,
                                      brakes,wheel_radii_m or (config.wheel_radius_m,)*4)
    d = physical.derivative
    contact_force = sum(w.body_force_x_n for w in physical.wheels)
    # Two equal half-axle memory channels represent one actuator. Their summed
    # slew budget must equal the declared axle budget, not two motor budgets.
    slew = actuation.actuator_slew_nm_per_s / (2 if actuation.topology_id in (SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID) else 1)
    memory_rate = tuple(
        max(
            -slew,
            min(
                slew,
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
    maximum_work: int = MAX_POWERED_WORK,
    wheel_radii_m=None,
) -> PoweredState:
    """One held-command interval. No controller, sensor or random state exists here."""
    command_nm = four_numbers(command_nm, "command")
    steering = four_numbers(steering, "steering")
    brakes = four_numbers(brakes, "brakes")
    _finite(timestep_s, "timestep_s")
    _finite(driver_proxy_n, "driver_proxy_n")
    if type(maximum_work) is not int or not 1 <= maximum_work <= MAX_ALLOCATED_POWERED_WORK:
        raise ValueError("powered work allocation must be an integer in [1, 200000]")
    if timestep_s <= 0 or timestep_s > 0.01:
        raise ValueError("powered plant step must be in (0, 0.01] s")
    # Radius affects the fast slip mode. A mismatch must not silently retain
    # a less conservative step than the largest declared contact radius.
    if wheel_radii_m is not None:
        PlanarControls(wheel_radii_m=wheel_radii_m)
    step_config = replace(config,wheel_radius_m=max(wheel_radii_m)) if wheel_radii_m else config
    limit = min(step_config.integration_step_limit_s, actuation.actuator_time_constant_s / 4)
    count = ceil(timestep_s / limit)
    if count > 50_000:
        raise ValueError("powered integration exceeds the work budget")
    h = timestep_s / count
    conditions = environment or PlanarEnvironment()
    trials = state.integration_trials
    for _ in range(count):
        remaining = h
        while remaining > 0:
            rate = evaluate_powered(
                config,
                actuation,
                state,
                command_nm,
                steering,
                brakes,
                available,
                remaining,
                conditions,
                driver_proxy_n,
                wheel_radii_m=wheel_radii_m,
            )[0]
            stops = [
                i
                for i, omega in enumerate(state.plant.wheel_speeds_rad_s)
                if 0 < omega <= BRAKE_STOP_SPEED_RAD_S
                and brakes[i] > 0
                and rate[6 + i] < 0
            ]
            if actuation.topology_id == SPOOL_RWD_TOPOLOGY_ID and any(i in stops for i in (2,3)):
                stops = sorted(set(stops) | {2,3})
            if stops:
                wheels = list(state.plant.wheel_speeds_rad_s)
                loss = (
                    0.5 * config.wheel_inertia_kgm2 * sum(wheels[i] ** 2 for i in stops)
                )
                for i in stops:
                    wheels[i] = 0.0
                state = replace(
                    state,
                    plant=replace(
                        state.plant,
                        wheel_speeds_rad_s=four_numbers(wheels, "stopped wheels"),
                    ),
                    wheel_stop_dissipation_j=state.wheel_stop_dissipation_j + loss,
                    wheel_stop_events=state.wheel_stop_events + len(stops),
                )
                if trials + state.wheel_stop_events > maximum_work:
                    raise ValueError(
                        "powered integration exceeds the actual work budget"
                    )
                continue
            trial_h = min(
                [remaining]
                + [
                    0.25 * omega / -rate[6 + i]
                    for i, omega in enumerate(state.plant.wheel_speeds_rad_s)
                    if omega > 0 and brakes[i] > 0 and rate[6 + i] < 0
                ]
            )
            while True:
                trials += 1
                if trials + state.wheel_stop_events > maximum_work:
                    raise ValueError(
                        "powered integration exceeds the actual work budget"
                    )
                try:
                    candidate = _rk_trial(
                        config,
                        actuation,
                        state,
                        command_nm,
                        steering,
                        brakes,
                        available,
                        trial_h,
                        conditions,
                        driver_proxy_n,
                        wheel_radii_m,
                    )
                    break
                except _BrakeStopTrial:
                    trial_h /= 2
                    if remaining - trial_h == remaining:
                        raise ValueError(
                            "brake stop exceeds the supported temporal resolution"
                        ) from None
            state = replace(
                candidate,
                integration_substeps=state.integration_substeps + 1,
                integration_trials=trials,
                wheel_stop_events=state.wheel_stop_events,
                wheel_stop_dissipation_j=state.wheel_stop_dissipation_j,
            )
            remaining -= trial_h
            if not 0 <= state.pack_energy_j <= actuation.pack_capacity_j:
                raise ValueError(
                    "pack energy crossed its physical bounds; integration rejected"
                )
    return state


def _rk_trial(
    config,
    actuation,
    state,
    command,
    steering,
    brakes,
    available,
    h,
    environment,
    driver_proxy_n,
    wheel_radii_m=None,
):
    value = _vector(state)

    def check_wheels(values):
        for i, omega in enumerate(values[6:10]):
            if omega < 0:
                if brakes[i] > 0 or (actuation.topology_id == SPOOL_RWD_TOPOLOGY_ID and i in (2,3) and (brakes[2]>0 or brakes[3]>0)):
                    raise _BrakeStopTrial()
                raise ValueError("reverse wheel motion is outside the powered domain")

    def derivative(values):
        check_wheels(values)
        return evaluate_powered(
            config,
            actuation,
            _state(values),
            command,
            steering,
            brakes,
            available,
            h,
            environment,
            driver_proxy_n,
            wheel_radii_m=wheel_radii_m,
        )[0]

    def shifted(rate, scale):
        return tuple(x + scale * dx for x, dx in zip(value, rate, strict=True))

    k1 = derivative(value)
    k2 = derivative(shifted(k1, h / 2))
    k3 = derivative(shifted(k2, h / 2))
    k4 = derivative(shifted(k3, h))
    final = tuple(
        x + h / 6 * (a + 2 * b + 2 * c + d)
        for x, a, b, c, d in zip(value, k1, k2, k3, k4, strict=True)
    )
    check_wheels(final)
    return _state(final)


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
        + final.wheel_stop_dissipation_j
        - initial.wheel_stop_dissipation_j
        - (final.friction_brake_work_j - initial.friction_brake_work_j)
        - (final.external_work_j - initial.external_work_j)
    )
