"""Shared acceptance boundary for the synthetic allocator's result records.

This validates offline data consistency, not sensor provenance, motor limits,
firmware timing, or a vehicle's independent shutdown path.
"""
from __future__ import annotations

from math import isfinite, ulp
from allocator import AllocationResult, WHEEL_COUNT
from torque_numeric import wheel_total


def ordinary_finite(value: object) -> float | None:
    """Accept JSON-style numeric scalars without custom conversion hooks."""
    if type(value) not in (int, float):
        return None
    try:
        converted = float(value)
    except (OverflowError, ValueError):
        return None
    return converted if isfinite(converted) else None


def allocation_contract_fault(candidate: object) -> str | None:
    """Return a stable diagnostic, or None for one consistent result.

    Numeric contract version 2 uses fixed slot-order binary64 accumulation.
    The tolerance is eight floating-point ULPs, not a physical torque margin.
    Zero request and fault output have exact zero requirements. A fault can
    retain a negative unsupported request as diagnostic evidence.
    """
    if type(candidate) is not AllocationResult:
        return "invalid_candidate_type"
    if type(candidate.status) is not str or candidate.status not in ("ok", "saturated", "fault"):
        return "invalid_candidate_status"
    wheels = candidate.wheel_torque_nm
    if type(wheels) not in (list, tuple) or len(wheels) != WHEEL_COUNT:
        return "invalid_candidate_output"
    values = tuple(ordinary_finite(value) for value in wheels)
    if any(value is None or value < 0.0 for value in values):
        return "invalid_candidate_output"
    delivered = ordinary_finite(candidate.delivered_nm)
    if delivered is None or delivered < 0.0:
        return "invalid_candidate_delivered"
    total = wheel_total(values)
    if not isfinite(total) or abs(total - delivered) > 8 * max(ulp(total), ulp(delivered)):
        return "candidate_sum_mismatch"
    requested = ordinary_finite(candidate.requested_nm)
    if requested is None or (candidate.status != "fault" and requested < 0.0):
        return "invalid_candidate_requested"
    if candidate.fault is not None and type(candidate.fault) is not str:
        return "invalid_candidate_fault"
    if candidate.status == "ok" and candidate.fault is not None:
        return "candidate_status_fault_mismatch"
    if candidate.status == "saturated" and candidate.fault != "aggregate_limit":
        return "candidate_status_fault_mismatch"
    if candidate.status == "fault":
        if not candidate.fault or delivered != 0.0 or any(value != 0.0 for value in values):
            return "candidate_status_fault_mismatch"
    else:
        commanded = max(total, delivered)
        roundoff = 8 * max(ulp(requested), ulp(commanded))
        if (requested == 0.0 and commanded != 0.0) or commanded - requested > roundoff:
            return "candidate_exceeds_request"
    return None
