from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable

from allocator import AllocationResult, WHEEL_COUNT
from allocation_contract import allocation_contract_fault


@dataclass(frozen=True)
class CommandGuardConfig:
    """Synthetic reference policy; values are not Terps Racing requirements."""

    max_rise_nm_per_s: float
    pedal_overlap_trip_fraction: float
    pedal_clear_fraction: float


@dataclass(frozen=True)
class CommandGuardInput:
    """One synthetic guard cycle around an already-computed torque allocation."""

    dt_s: float
    accelerator_fraction: float
    brake_active: bool
    critical_comms_ok: bool
    sensor_agreement_ok: bool
    external_interlock: bool


@dataclass(frozen=True)
class CommandGuardState:
    previous_output_nm: tuple[float, float, float, float]
    pedal_overlap_latched: bool = False


@dataclass(frozen=True)
class CommandGuardResult:
    output_nm: tuple[float, float, float, float]
    next_state: CommandGuardState
    status: str
    reason: str | None


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _finite_numeric(value: object) -> float | None:
    """Validate numeric values before narrowing Python integers to floats.

    Offline records may contain arbitrary-precision integers; conversion of a
    sufficiently large integer raises OverflowError instead of returning inf.
    """
    if not _is_number(value):
        return None
    try:
        converted = float(value)
    except (OverflowError, ValueError):
        return None
    return converted if isfinite(converted) else None


def _valid_nonnegative_vector(values: object) -> bool:
    """Accept only ordinary wheel vectors; annotations do not validate input.

    Reject opaque iterables (including bytes/dicts) and missing vectors before
    calling len() or consuming contents. Synthetic data loaders can otherwise
    raise TypeError or silently reinterpret raw bytes as torque magnitudes.
    """
    if type(values) not in (tuple, list) or len(values) != WHEEL_COUNT:
        return False
    for value in values:
        converted = _finite_numeric(value)
        if converted is None or converted < 0.0:
            return False
    return True


def _validate_config(cfg: CommandGuardConfig) -> str | None:
    rate = _finite_numeric(cfg.max_rise_nm_per_s)
    if rate is None or rate <= 0.0:
        return "invalid_max_rise_rate"

    trip = _finite_numeric(cfg.pedal_overlap_trip_fraction)
    clear = _finite_numeric(cfg.pedal_clear_fraction)
    if trip is None or clear is None or not (0.0 <= clear < trip <= 1.0):
        return "invalid_pedal_threshold"
    return None


def _zero(state: CommandGuardState, latched: bool, reason: str) -> CommandGuardResult:
    zero = (0.0, 0.0, 0.0, 0.0)
    return CommandGuardResult(
        output_nm=zero,
        next_state=CommandGuardState(zero, latched),
        status="inhibited",
        reason=reason,
    )


def apply_command_guard(
    candidate: AllocationResult,
    inp: CommandGuardInput,
    cfg: CommandGuardConfig,
    state: CommandGuardState,
) -> CommandGuardResult:
    """Apply synthetic plausibility gates and an upward-only torque slew limit.

    The guard never delays a torque decrease. Any inhibit condition commands
    zero immediately in this reference model. This layer is not a vehicle safety
    system and does not replace an independent shutdown/interlock path.
    """

    # Reject corrupted offline replay latch state before any gate can copy an
    # arbitrary value into the next state. Treat its provenance as unknown:
    # inhibit now and require a valid low-pedal observation to clear the latch.
    # This is a synthetic reference policy requiring team review, not an
    # implementation of the vehicle's independent shutdown system.
    if type(state.pedal_overlap_latched) is not bool:
        return _zero(state, True, "invalid_pedal_latch_state")

    config_fault = _validate_config(cfg)
    if config_fault:
        return _zero(state, state.pedal_overlap_latched, config_fault)

    if not _valid_nonnegative_vector(state.previous_output_nm):
        return _zero(state, state.pedal_overlap_latched, "invalid_previous_output")

    dt = _finite_numeric(inp.dt_s)
    if dt is None or dt <= 0.0:
        return _zero(state, state.pedal_overlap_latched, "invalid_dt")
    accel = _finite_numeric(inp.accelerator_fraction)
    if accel is None or not (0.0 <= accel <= 1.0):
        return _zero(state, state.pedal_overlap_latched, "invalid_accelerator_fraction")
    if any(type(value) is not bool for value in (
        inp.brake_active,
        inp.critical_comms_ok,
        inp.sensor_agreement_ok,
        inp.external_interlock,
    )):
        return _zero(state, state.pedal_overlap_latched, "invalid_boolean_input")

    # The observer and compatibility adapter consume this exact same contract.
    # An "ok" label cannot override a fault or authorize an over-request vector.
    contract_fault = allocation_contract_fault(candidate)
    if contract_fault:
        return _zero(state, state.pedal_overlap_latched, contract_fault)

    latched = state.pedal_overlap_latched
    if latched:
        if accel <= float(cfg.pedal_clear_fraction):
            latched = False
    elif inp.brake_active and accel >= float(cfg.pedal_overlap_trip_fraction):
        latched = True

    # Inhibits bypass the normal rise limiter. The reference deliberately does
    # not ramp faults down because that could prolong torque after an invalid
    # input or an external safety/interlock request.
    if candidate.status == "fault":
        return _zero(state, latched, "allocator_fault")
    if not inp.external_interlock:
        return _zero(state, latched, "external_interlock_open")
    if not inp.critical_comms_ok:
        return _zero(state, latched, "critical_communication_loss")
    if not inp.sensor_agreement_ok:
        return _zero(state, latched, "sensor_disagreement")
    if latched:
        return _zero(state, latched, "brake_accelerator_overlap")

    max_step = float(cfg.max_rise_nm_per_s) * dt
    if not isfinite(max_step):
        return _zero(state, latched, "invalid_rise_step")
    output: list[float] = []
    rate_limited = False
    for previous, target in zip(state.previous_output_nm, candidate.wheel_torque_nm):
        previous_f = float(previous)
        target_f = float(target)
        if target_f <= previous_f:
            # Immediate decreases preserve new lower allocator/traction/limit
            # commands instead of holding stale higher torque.
            commanded = target_f
        else:
            commanded = min(target_f, previous_f + max_step)
            rate_limited = rate_limited or commanded < target_f - 1e-12
        output.append(commanded)

    out_tuple = tuple(output)
    limited = candidate.status == "saturated" or rate_limited
    if rate_limited and candidate.status == "saturated":
        reason = "aggregate_and_rise_rate_limit"
    elif candidate.status == "saturated":
        reason = "aggregate_limit"
    elif rate_limited:
        reason = "rise_rate_limit"
    else:
        reason = None

    return CommandGuardResult(
        output_nm=out_tuple,
        next_state=CommandGuardState(out_tuple, latched),
        status="limited" if limited else "ok",
        reason=reason,
    )


def replay_guard(
    candidates: Iterable[AllocationResult],
    inputs: Iterable[CommandGuardInput],
    cfg: CommandGuardConfig,
    initial_state: CommandGuardState,
) -> tuple[CommandGuardResult, ...]:
    """Replay candidates and guard inputs deterministically with explicit state."""

    candidate_list = tuple(candidates)
    input_list = tuple(inputs)
    if len(candidate_list) != len(input_list):
        raise ValueError("candidate/input length mismatch")

    state = initial_state
    results: list[CommandGuardResult] = []
    for candidate, inp in zip(candidate_list, input_list):
        result = apply_command_guard(candidate, inp, cfg, state)
        results.append(result)
        state = result.next_state
    return tuple(results)
