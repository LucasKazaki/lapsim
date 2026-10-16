"""TC-02BV: synthetic trust gate for clearing an observed pedal-overlap latch.

Candidate policy for independent team review, NOT real vehicle software.
Only a completed, healthy command-guard cycle may clear a previously latched
pedal-overlap condition. A failed allocator, communication fault, sensor
uncertainty, or external interlock inhibit must retain the prior latch.

This wraps the existing request and overlap adapters without changing them.
The original result's fault reason is retained; the adapter never commands
positive torque when it vetoes clearance. No authority over an independent
safety shutdown or any real APPS/BPPS signal is implied.
"""
from __future__ import annotations

from allocator import AllocationResult
from command_guard import CommandGuardInput, CommandGuardConfig, CommandGuardState, CommandGuardResult
from guard_overlap_observation import apply_overlap_observed_guard

_ZERO = (0.0, 0.0, 0.0, 0.0)


def trusted_clear_cycle(candidate: object, inp: object, result: object) -> bool:
    """A narrow synthetic clearance predicate, not a pedal-signal attestation."""
    return (
        type(candidate) is AllocationResult
        and type(candidate.status) is str
        and candidate.status in ("ok", "saturated")
        and type(inp) is CommandGuardInput
        and type(inp.critical_comms_ok) is bool and inp.critical_comms_ok
        and type(inp.sensor_agreement_ok) is bool and inp.sensor_agreement_ok
        and type(inp.external_interlock) is bool and inp.external_interlock
        and type(result) is CommandGuardResult
        and type(result.status) is str and result.status in ("ok", "limited")
    )


def apply_trusted_clear_guard(
    candidate: AllocationResult,
    inp: CommandGuardInput,
    cfg: CommandGuardConfig,
    state: CommandGuardState,
) -> CommandGuardResult:
    """Preserve a prior latch unless a trusted normal-cycle clearance occurs.

    This adapter only changes the false-latch transition on a fault/inhibit
    cycle. It deliberately does not define actual pedal provenance or fault
    latch ownership; the team must approve both before embedded adaptation.
    """
    result = apply_overlap_observed_guard(candidate, inp, cfg, state)
    if (type(state.pedal_overlap_latched) is not bool
            or not state.pedal_overlap_latched
            or result.next_state.pedal_overlap_latched is not False):
        return result
    if trusted_clear_cycle(candidate, inp, result):
        return result
    return CommandGuardResult(
        output_nm=_ZERO,
        next_state=CommandGuardState(_ZERO, True),
        status="inhibited",
        reason=result.reason or "untrusted_overlap_latch_clear",
    )
