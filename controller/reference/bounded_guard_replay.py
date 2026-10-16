"""TC-02CY: bounded offline wrapper for the existing synthetic guard replay.

No vehicle/CAN/firmware interfaces. The cap is an analyst resource bound,
not a sample period, recovery policy, watchdog limit or safety threshold.
The published direct replay_guard remains unchanged for compatibility.
"""
from __future__ import annotations

from itertools import islice
from typing import Iterable

from allocator import AllocationResult, MAX_OFFLINE_REPLAY_STEPS
from command_guard import (
    CommandGuardConfig,
    CommandGuardInput,
    CommandGuardResult,
    CommandGuardState,
    replay_guard,
)


def replay_guard_bounded(
    candidates: Iterable[AllocationResult],
    inputs: Iterable[CommandGuardInput],
    cfg: CommandGuardConfig,
    initial_state: CommandGuardState,
) -> tuple[CommandGuardResult, ...]:
    """Limit both replay streams to 4,096 entries, rejecting oversize input.

    Each iterable is consumed no more than MAX_OFFLINE_REPLAY_STEPS+1 times;
    the excess element is only a bounded overflow sentinel. A generator that
    itself blocks/raises is still the caller's responsibility. The wrapper
    delegates all paired replay semantics to the existing unmodified guard.
    """
    max_steps = MAX_OFFLINE_REPLAY_STEPS
    bounded_candidates = tuple(islice(candidates, max_steps + 1))
    if len(bounded_candidates) > max_steps:
        raise ValueError(f"offline guard replay candidates exceed {max_steps} steps")

    bounded_inputs = tuple(islice(inputs, max_steps + 1))
    if len(bounded_inputs) > max_steps:
        raise ValueError(f"offline guard replay inputs exceed {max_steps} steps")

    return replay_guard(bounded_candidates, bounded_inputs, cfg, initial_state)
