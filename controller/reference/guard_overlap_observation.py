"""TC-02BU synthetic offline pedal-overlap observation adapter.

Scenario policy (pending independent review): a TRUSTED, valid observation of
simultaneous brake and accelerator above a configured threshold sets the pedal
latch even when upstream allocation validation fails. Fault cycles do NOT clear
an existing latch; only the underlying valid guard progression may clear it.

This is not firmware, a safety controller, an FSAE compliance implementation,
or a substitute for the independent shutdown/interlock path.
"""
from __future__ import annotations

from math import isfinite

from command_guard import (
    CommandGuardConfig, CommandGuardInput, CommandGuardResult, CommandGuardState
)
from guard_request_contract import apply_request_checked_guard

_ZERO = (0.0, 0.0, 0.0, 0.0)


def _number(value: object) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        result = float(value)
    except (OverflowError, ValueError):
        return None
    return result if isfinite(result) else None


def trusted_overlap_trip(inp: object, cfg: object, state: object) -> bool:
    """Report only a trusted, ordinary, in-range synthetic pedal observation.

    With the existing guard interface, critical_comms_ok and
    sensor_agreement_ok are coarse global trust gates, NOT validated pedal
    provenance. Team review must establish per-signal trust ownership.
    """
    if not (type(inp) is CommandGuardInput and type(cfg) is CommandGuardConfig
            and type(state) is CommandGuardState):
        return False
    if type(state.pedal_overlap_latched) is not bool:
        return False
    if any(type(b) is not bool for b in
           (inp.brake_active, inp.critical_comms_ok, inp.sensor_agreement_ok)):
        return False
    if not (inp.brake_active and inp.critical_comms_ok and inp.sensor_agreement_ok):
        return False
    accel = _number(inp.accelerator_fraction)
    trip = _number(cfg.pedal_overlap_trip_fraction)
    clear = _number(cfg.pedal_clear_fraction)
    rise = _number(cfg.max_rise_nm_per_s)
    if accel is None or trip is None or clear is None or rise is None:
        return False
    return (rise > 0.0 and 0.0 <= clear < trip <= 1.0
            and 0.0 <= accel <= 1.0 and accel >= trip)


def apply_overlap_observed_guard(candidate: object, inp: CommandGuardInput,
                                 cfg: CommandGuardConfig,
                                 state: CommandGuardState) -> CommandGuardResult:
    """Run the existing adapter, then preserve a trusted missed latch trip.

    Under the synthetic policy the original fault reason has priority. This
    adapter never converts an inhibited fault to an accepted torque command,
    and never changes a valid underlying guard transition.
    """
    result = apply_request_checked_guard(candidate, inp, cfg, state)
    if not trusted_overlap_trip(inp, cfg, state):
        return result
    if result.next_state.pedal_overlap_latched is True:
        return result
    return CommandGuardResult(
        output_nm=_ZERO,
        next_state=CommandGuardState(_ZERO, True),
        status="inhibited",
        reason=result.reason or "brake_accelerator_overlap",
    )
