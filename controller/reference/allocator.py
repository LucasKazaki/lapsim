from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from math import isfinite
from typing import Iterable
from torque_numeric import wheel_total

WHEEL_COUNT = 4
SUPPORTED_TORQUE_UNIT = "N*m"
MAX_OFFLINE_REPLAY_STEPS = 4096


@dataclass(frozen=True)
class AllocationInput:
    """One synthetic control-cycle input for the reference allocator."""

    now_ms: int
    input_timestamp_ms: int
    request_nm: float
    wheel_limits_nm: tuple[float, float, float, float]
    wheel_enabled: tuple[bool, bool, bool, bool]
    external_interlock: bool
    torque_unit: str = SUPPORTED_TORQUE_UNIT


@dataclass(frozen=True)
class AllocatorConfig:
    max_input_age_ms: int


@dataclass(frozen=True)
class AllocationResult:
    wheel_torque_nm: tuple[float, float, float, float]
    requested_nm: float
    delivered_nm: float
    status: str
    fault: str | None


def _finite_number(value: object) -> float | None:
    """Finite float-compatible int/float, excluding booleans and overflow.

    Dataclass annotations do not validate synthetic replay inputs at runtime.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        converted = float(value)
    except (OverflowError, ValueError):
        return None
    return converted if isfinite(converted) else None


def _zero(requested_nm: object, fault: str) -> AllocationResult:
    requested = _finite_number(requested_nm)
    return AllocationResult((0.0, 0.0, 0.0, 0.0), requested if requested is not None else 0.0, 0.0, "fault", fault)


def allocate_propulsive_torque(
    inp: AllocationInput,
    cfg: AllocatorConfig,
) -> AllocationResult:
    """Allocate a nonnegative synthetic propulsive request across four wheels.

    This is a reference-only equal-allocation / saturation routine. It contains
    no vehicle dynamics, slip controller, yaw controller, CAN mapping, regen,
    firmware timing, or safety-system authority.
    """

    # Offline clock contract: integer, nonnegative millisecond ticks only.
    if type(cfg.max_input_age_ms) is not int or cfg.max_input_age_ms < 0:
        return _zero(inp.request_nm, "invalid_max_input_age")
    if inp.torque_unit != SUPPORTED_TORQUE_UNIT:
        return _zero(inp.request_nm, "unsupported_torque_unit")
    # Keep the existing nonfinite-float reason distinct from a malformed or
    # unrepresentable numeric value. Never let int->float overflow escape.
    if isinstance(inp.request_nm, bool) or not isinstance(inp.request_nm, (int, float)):
        return _zero(inp.request_nm, "invalid_request_numeric")
    request = _finite_number(inp.request_nm)
    if request is None:
        reason = "nonfinite_request" if isinstance(inp.request_nm, float) else "invalid_request_numeric"
        return _zero(inp.request_nm, reason)
    if request < 0.0:
        return _zero(inp.request_nm, "negative_request_unsupported")
    if (
        not isinstance(inp.wheel_limits_nm, (list, tuple))
        or not isinstance(inp.wheel_enabled, (list, tuple))
        or len(inp.wheel_limits_nm) != WHEEL_COUNT
        or len(inp.wheel_enabled) != WHEEL_COUNT
    ):
        return _zero(inp.request_nm, "invalid_wheel_vector")
    # Reject truthy strings/integers in synthetic enable and interlock fields.
    if any(type(flag) is not bool for flag in inp.wheel_enabled):
        return _zero(inp.request_nm, "invalid_wheel_enabled")
    if type(inp.external_interlock) is not bool:
        return _zero(inp.request_nm, "invalid_external_interlock")
    limits = tuple(_finite_number(limit) for limit in inp.wheel_limits_nm)
    if any(limit is None or limit < 0.0 for limit in limits):
        return _zero(inp.request_nm, "invalid_wheel_limit")
    if not inp.external_interlock:
        return _zero(inp.request_nm, "external_interlock_open")
    # Comparing NaN with ordered values silently returns False in Python.
    if (
        type(inp.now_ms) is not int
        or type(inp.input_timestamp_ms) is not int
        or inp.now_ms < 0
        or inp.input_timestamp_ms < 0
    ):
        return _zero(inp.request_nm, "invalid_input_timestamp")
    if inp.input_timestamp_ms > inp.now_ms:
        return _zero(inp.request_nm, "input_timestamp_in_future")
    if inp.now_ms - inp.input_timestamp_ms > cfg.max_input_age_ms:
        return _zero(inp.request_nm, "stale_input")
    if request == 0.0:
        return AllocationResult((0.0, 0.0, 0.0, 0.0), 0.0, 0.0, "ok", None)

    active = {
        index
        for index, (enabled, limit) in enumerate(zip(inp.wheel_enabled, limits))
        if enabled and limit > 0.0
    }
    if not active:
        return _zero(inp.request_nm, "no_available_wheels")

    outputs = [0.0] * WHEEL_COUNT
    remaining = request
    epsilon = 1e-12

    # Deterministic water-filling: share equally among available wheels, cap
    # saturated wheels, then redistribute only the unserved remainder.
    while active and remaining > epsilon:
        share = remaining / len(active)
        saturated: list[int] = []
        for index in sorted(active):
            capacity = limits[index] - outputs[index]
            if capacity <= share + epsilon:
                saturated.append(index)

        if not saturated:
            for index in sorted(active):
                outputs[index] += share
            remaining = 0.0
            break

        for index in saturated:
            capacity = max(0.0, limits[index] - outputs[index])
            outputs[index] += capacity
            remaining -= capacity
            active.remove(index)

    delivered = wheel_total(outputs)
    if remaining > 1e-9:
        return AllocationResult(
            tuple(outputs), inp.request_nm, delivered, "saturated", "aggregate_limit"
        )
    return AllocationResult(tuple(outputs), inp.request_nm, delivered, "ok", None)


def replay(
    samples: Iterable[AllocationInput],
    cfg: AllocatorConfig,
) -> tuple[AllocationResult, ...]:
    """Replay at most 4,096 synthetic steps; never exhaust an infinite stream.

    This CPU/offline scenario cap is not a real-time or vehicle safety limit.
    """

    bounded = tuple(islice(samples, MAX_OFFLINE_REPLAY_STEPS + 1))
    if len(bounded) > MAX_OFFLINE_REPLAY_STEPS:
        raise ValueError("offline allocator replay exceeds 4096 steps")
    return tuple(allocate_propulsive_torque(sample, cfg) for sample in bounded)
