"""Fixed-period normalized millisecond owner; no raw counter or live timer IO."""
from __future__ import annotations

from dataclasses import dataclass
from math import isclose

from allocation_contract import ordinary_finite

CLOCK_CONTRACT_VERSION = 1


@dataclass(frozen=True)
class CycleClockState:
    previous_tick: int | None = None


@dataclass(frozen=True)
class CycleClockResult:
    next_state: CycleClockState
    now_ms: int | None
    fault: str | None


def observe_cycle_clock(previous: CycleClockState, tick: object, dt_s: object,
                        period_ms: int) -> CycleClockResult:
    """Preserve the source pipeline's timestamp precedence and anchor policy.

    Forward gaps and invalid dt still advance a valid forward anchor; duplicate,
    backward or malformed ticks do not. Restart is owned elsewhere and does not
    reset this clock. Python intentionally retains unbounded integer ticks.
    """
    if type(period_ms) is not int or not 1 <= period_ms <= 60_000:
        raise ValueError("period_ms must be an integer in [1, 60000]")
    if type(previous) is not CycleClockState or (previous.previous_tick is not None and
            (type(previous.previous_tick) is not int or previous.previous_tick < 0)):
        raise ValueError("invalid cycle clock state")
    previous_tick = previous.previous_tick
    clock_fault = None
    if type(tick) is not int or tick < 0:
        clock_fault = "invalid_cycle_timestamp"
    elif previous_tick is not None and tick <= previous_tick:
        clock_fault = "nonmonotonic_cycle_timestamp"
    else:
        if previous_tick is not None and tick - previous_tick != period_ms:
            clock_fault = "cycle_period_mismatch"
        previous_tick = tick
    dt = ordinary_finite(dt_s)
    if dt is None or not isclose(dt, period_ms / 1000, rel_tol=0., abs_tol=1e-12):
        clock_fault = clock_fault or "guard_period_mismatch"
    return CycleClockResult(CycleClockState(previous_tick),
                            tick if type(tick) is int and tick >= 0 else None, clock_fault)
