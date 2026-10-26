"""Pure synthetic wheel-actuation and constant-voltage pack constraints.

Wheel contact forces belong to the planar plant. This module converts and
limits applied torque/power; it never advances wheel or battery state.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite

from .bicycle import _finite

TOPOLOGY_ID = "synthetic_independent_rear_rwd_v1"
AWD_TOPOLOGY_ID = "synthetic_independent_four_awd_v1"
SINGLE_MOTOR_RWD_TOPOLOGY_ID = "synthetic_single_motor_open_diff_rwd_v1"
SPOOL_RWD_TOPOLOGY_ID = "synthetic_single_motor_locked_axle_rwd_v1"


def four_numbers(values: object, name: str) -> tuple[float, float, float, float]:
    if not isinstance(values, (tuple, list)) or len(values) != 4:
        raise ValueError(f"{name} must contain FL, FR, RL, RR values")
    for value in values:
        _finite(value, name)
    return float(values[0]), float(values[1]), float(values[2]), float(values[3])


@dataclass(frozen=True, slots=True)
class ActuationConfig:
    topology_id: str = TOPOLOGY_ID
    gear_ratio: float = 4.0
    gear_efficiency: float = 0.96
    motor_conversion_efficiency: float = 0.95
    inverter_efficiency: float = 0.97
    torque_constant_nm_per_a: float = 0.8
    motor_current_limit_a: float = 100.0
    inverter_current_limit_a: float = 90.0
    motor_peak_torque_nm: float = 80.0
    motor_base_speed_rad_s: float = 250.0
    motor_maximum_speed_rad_s: float = 700.0
    equivalent_copper_resistance_ohm: float = 0.02
    pack_voltage_v: float = 300.0
    pack_capacity_j: float = 18_000_000.0
    pack_discharge_current_limit_a: float = 100.0
    pack_charge_current_limit_a: float = 40.0
    pack_discharge_power_limit_w: float = 25_000.0
    pack_charge_power_limit_w: float = 8_000.0
    actuator_time_constant_s: float = 0.025
    actuator_slew_nm_per_s: float = 8_000.0

    def __post_init__(self) -> None:
        if self.topology_id not in (TOPOLOGY_ID, AWD_TOPOLOGY_ID, SINGLE_MOTOR_RWD_TOPOLOGY_ID, SPOOL_RWD_TOPOLOGY_ID):
            raise ValueError("unsupported actuator topology")
        for name in self.__dataclass_fields__:
            if name == "topology_id":
                continue
            value = getattr(self, name)
            _finite(value, name)
            if value < 0 or (value == 0 and name != "equivalent_copper_resistance_ohm"):
                raise ValueError(
                    f"{name} must be positive (copper resistance may be zero)"
                )
        for name in (
            "gear_efficiency",
            "motor_conversion_efficiency",
            "inverter_efficiency",
        ):
            if getattr(self, name) > 1:
                raise ValueError(f"{name} must not exceed one")
        if self.motor_base_speed_rad_s >= self.motor_maximum_speed_rad_s:
            raise ValueError("base motor speed must be below maximum speed")
        derived = (
            self.gear_ratio * self.motor_peak_torque_nm / self.gear_efficiency,
            self.pack_voltage_v * self.pack_discharge_current_limit_a,
            self.pack_voltage_v * self.pack_charge_current_limit_a,
            self.motor_current_limit_a
            * self.motor_current_limit_a
            * self.equivalent_copper_resistance_ohm,
            min(self.motor_current_limit_a, self.inverter_current_limit_a)
            * self.torque_constant_nm_per_a,
        )
        if not all(isfinite(value) for value in derived):
            raise ValueError(
                "actuation configuration exceeds the finite numerical domain"
            )


@dataclass(frozen=True, slots=True)
class ActuationEvaluation:
    wheel_torques_nm: tuple[float, float, float, float]
    motor_torques_nm: tuple[float, float, float, float]
    motor_currents_a: tuple[float, float, float, float]
    motor_speeds_rad_s: tuple[float, float, float, float]
    wheel_power_w: float
    pack_power_w: float
    pack_current_a: float
    conversion_loss_w: float
    constraints: tuple[str, ...]
    shared_power_scale: float


def _electrical(config: ActuationConfig, torque: tuple, speeds: tuple) -> tuple:
    motor_torques, currents, bus_powers = [], [], []
    wheel_power = 0.0
    for effort, omega in zip(torque, speeds, strict=True):
        power = effort * omega
        wheel_power += power
        if effort >= 0:
            motor_torque = effort / (config.gear_ratio * config.gear_efficiency)
        else:
            motor_torque = effort * config.gear_efficiency / config.gear_ratio
        current = motor_torque / config.torque_constant_nm_per_a
        mechanical = motor_torque * config.gear_ratio * omega
        dc = (
            mechanical / config.motor_conversion_efficiency
            if mechanical >= 0
            else mechanical * config.motor_conversion_efficiency
        )
        dc += current * current * config.equivalent_copper_resistance_ohm
        bus = (
            dc / config.inverter_efficiency
            if dc >= 0
            else dc * config.inverter_efficiency
        )
        motor_torques.append(motor_torque)
        currents.append(current)
        bus_powers.append(bus)
        if not all(
            isfinite(value)
            for value in (power, motor_torque, current, mechanical, dc, bus)
        ):
            raise ValueError(
                "electrical conversion exceeds the finite numerical domain"
            )
    return tuple(motor_torques), tuple(currents), sum(bus_powers), wheel_power


def constrain_actuation(
    config: ActuationConfig,
    requested_wheel_torques_nm: tuple,
    wheel_speeds_rad_s: tuple,
    energy_j: float,
    interval_s: float,
    available: tuple[bool, bool, bool, bool] = (False, False, True, True),
) -> ActuationEvaluation:
    """Return physically feasible applied torque before the plant/energy update.

    Pack power is positive for discharge. Shared scaling preserves the
    proposed rear split. Opposite signs during an actuator transient are
    allowed; common scaling is conservative rather than an optimal allocator.
    All values are synthetic.
    """
    if not isinstance(config, ActuationConfig):
        raise TypeError("expected ActuationConfig")
    requested = four_numbers(requested_wheel_torques_nm, "wheel torque")
    speeds = four_numbers(wheel_speeds_rad_s, "wheel speed")
    if config.topology_id != AWD_TOPOLOGY_ID and (requested[0] != 0 or requested[1] != 0):
        raise ValueError("front drive torque is unavailable in the RWD topology")
    if any(value < 0 for value in speeds):
        raise ValueError("negative wheel speed is outside this actuation domain")
    if (
        not isinstance(available, (tuple, list))
        or len(available) != 4
        or any(type(v) is not bool for v in available)
    ):
        raise ValueError("availability must contain four booleans")
    if config.topology_id != AWD_TOPOLOGY_ID and (available[0] or available[1]):
        raise ValueError("front actuators are unavailable in the RWD topology")
    _finite(energy_j, "pack energy")
    _finite(interval_s, "interval_s")
    if interval_s <= 0 or not 0 <= energy_j <= config.pack_capacity_j:
        raise ValueError("invalid pack energy or positive integration interval")
    if config.topology_id == SPOOL_RWD_TOPOLOGY_ID:
        if speeds[2] != speeds[3]:
            raise ValueError('locked axle requires equal rear angular velocity; no hidden state projection')
        # The electrical converter is one common motor. Mechanical reaction
        # torque and shaft-speed coupling belong to the powered plant.
        return _single_motor_open_diff(config, requested, speeds, energy_j, interval_s, available)
    if config.topology_id == SINGLE_MOTOR_RWD_TOPOLOGY_ID:
        return _single_motor_open_diff(config, requested, speeds, energy_j, interval_s, available)
    reasons = []
    limited = []
    current_torque = (
        min(config.motor_current_limit_a, config.inverter_current_limit_a)
        * config.torque_constant_nm_per_a
    )
    for index, (request, omega) in enumerate(zip(requested, speeds, strict=True)):
        motor_speed = config.gear_ratio * omega
        if not isfinite(motor_speed):
            raise ValueError("motor speed exceeds the finite numerical domain")
        motor_cap = min(config.motor_peak_torque_nm, current_torque)
        if motor_speed > config.motor_base_speed_rad_s:
            motor_cap = min(
                motor_cap,
                config.motor_peak_torque_nm
                * config.motor_base_speed_rad_s
                / motor_speed,
            )
        if motor_speed >= config.motor_maximum_speed_rad_s:
            motor_cap = 0.0
        if not available[index]:
            motor_cap = 0.0
        cap = (
            motor_cap
            * config.gear_ratio
            * (config.gear_efficiency if request >= 0 else 1 / config.gear_efficiency)
        )
        if request < 0:
            # P_motor_dc(t) = -a*t + b*t². Restrict t <= a/(2b)
            # so reducing regeneration cannot increase its charging power.
            resistance = config.equivalent_copper_resistance_ohm
            regen_current_cap = (
                motor_speed
                * config.torque_constant_nm_per_a
                * config.motor_conversion_efficiency
                / (2 * resistance)
                if resistance
                else float("inf")
            )
            cap = min(
                cap,
                regen_current_cap
                * config.torque_constant_nm_per_a
                * config.gear_ratio
                / config.gear_efficiency,
            )
            if omega == 0:
                cap = 0.0
        applied = min(abs(request), cap) * (-1 if request < 0 else 1)
        if applied != request:
            reasons.append(f"wheel_{index}_motor_current_speed_availability")
        limited.append(applied)
    torque = tuple(limited)
    upper = min(
        config.pack_discharge_power_limit_w,
        config.pack_voltage_v * config.pack_discharge_current_limit_a,
        energy_j / interval_s,
    )
    lower = -min(
        config.pack_charge_power_limit_w,
        config.pack_voltage_v * config.pack_charge_current_limit_a,
        (config.pack_capacity_j - energy_j) / interval_s,
    )
    _, _, power, _ = _electrical(config, torque, speeds)
    scale = 1.0
    if not lower <= power <= upper:
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2
            _, _, candidate, _ = _electrical(
                config, tuple(mid * value for value in torque), speeds
            )
            if lower <= candidate <= upper:
                lo = mid
            else:
                hi = mid
        scale = lo
        torque = tuple(scale * value for value in torque)
        reasons.append("shared_pack_power_current_interval_energy")
    motor_torques, currents, power, wheel_power = _electrical(config, torque, speeds)
    loss = power - wheel_power
    if not all(
        isfinite(value)
        for value in (*torque, *motor_torques, *currents, power, wheel_power, loss)
    ):
        raise ValueError("actuator evaluation exceeds the finite numerical domain")
    return ActuationEvaluation(
        torque,
        motor_torques,
        currents,
        four_numbers(
            tuple(config.gear_ratio * value for value in speeds), "motor speeds"
        ),
        wheel_power,
        power,
        power / config.pack_voltage_v,
        loss,
        tuple(reasons),
        scale,
    )


def _single_motor_open_diff(config, requested, speeds, energy_j, interval_s, available):
    """One reflected axle actuator and a lossless symmetric open differential.

    Equal output torques and carrier speed = mean wheel speed preserve power
    for unequal wheel speeds. The existing motor/pack solver runs exactly once.
    Motor arrays use slot RL for the sole drive unit, RR is zero; wheel arrays
    remain FL/FR/RL/RR. No differential friction, preload or motor inertia is
    modeled. This is a synthetic topology, not a selected team differential.
    """
    if requested[2] != requested[3]:
        raise ValueError("single-motor open differential requires equal rear wheel torque commands")
    speed = speeds[2]/2 + speeds[3]/2
    axle = requested[2] + requested[3]
    motor = constrain_actuation(
        replace(config, topology_id=TOPOLOGY_ID), (0, 0, axle, 0), (0, 0, speed, 0),
        energy_j, interval_s, (False, False, available[2] and available[3], False),
    )
    half = motor.wheel_torques_nm[2]/2
    reasons = tuple("single_motor_current_speed_availability" if r.startswith("wheel_2_") else r
                    for r in motor.constraints)
    return replace(motor, wheel_torques_nm=(0.0, 0.0, half, half), constraints=reasons)
