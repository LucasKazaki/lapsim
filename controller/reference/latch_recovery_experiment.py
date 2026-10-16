"""TC-02DI: optional OFFLINE latch-requalification experiment.

NOT an approved control policy, not firmware, and not part of the production
command path. Compare against the published synthetic command guard without
modifying it. An already-active pedal overlap latch is only cleared after a
healthy, brake-released, low-accelerator observation. The clearing observation
always outputs zero; a later independent control step may produce torque.

This is a proposed alternative for team review, NOT evidence of vehicle safety.
No extra authority is conferred over the independent shutdown system.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from typing import Iterable

from allocator import AllocationResult
from command_guard import (
    CommandGuardConfig,
    CommandGuardInput,
    CommandGuardResult,
    CommandGuardState,
    apply_command_guard,
)

MAX_EXPERIMENT_STEPS = 4096  # synthetic replay resource bound only
ZERO = (0.0, 0.0, 0.0, 0.0)


@dataclass(frozen=True)
class ComparisonStep:
    baseline: CommandGuardResult
    experimental: CommandGuardResult


def experiment_one_step(
    candidate: AllocationResult,
    inp: CommandGuardInput,
    cfg: CommandGuardConfig,
    state: CommandGuardState,
) -> CommandGuardResult:
    """Apply an isolated counterfactual policy to the published guard result.

    The regular guard still validates all inputs and handles new overlaps.
    Only an already-latched (well-typed) state triggers extra qualification.
    This deliberately does not claim that every fault needs a latch.
    """
    observed = apply_command_guard(candidate, inp, cfg, state)
    if state.pedal_overlap_latched is not True:
        # Covers ordinary unlatched behavior and the reference guard's existing
        # invalid-latch fail-closed response without changing its priority.
        return observed

    # A prior latch must not disappear while the brake is applied, health
    # checks fail, or the allocator/guard still reports an inhibited step.
    # `observed.status` indicates that the reference validated all values.
    # Exact Boolean comparisons also reject truthy offline record values.
    qualifies = (
        observed.next_state.pedal_overlap_latched is False
        and observed.status in ("ok", "limited")
        and inp.brake_active is False
        and inp.critical_comms_ok is True
        and inp.sensor_agreement_ok is True
        and inp.external_interlock is True
    )
    if qualifies:
        # The clearing cycle is an observation, not a torque-command cycle.
        return CommandGuardResult(
            output_nm=ZERO,
            next_state=CommandGuardState(ZERO, False),
            status="inhibited",
            reason="experiment_requalification_dwell",
        )

    return CommandGuardResult(
        output_nm=ZERO,
        next_state=CommandGuardState(ZERO, True),
        status="inhibited",
        reason=(
            observed.reason
            if observed.status == "inhibited"
            else "experiment_requalification_blocked"
        ),
    )


def compare_replays(
    candidates: Iterable[AllocationResult],
    inputs: Iterable[CommandGuardInput],
    cfg: CommandGuardConfig,
    initial_state: CommandGuardState,
) -> tuple[ComparisonStep, ...]:
    """Bound both streams and evolve independent baseline/experiment states."""
    c = tuple(islice(candidates, MAX_EXPERIMENT_STEPS + 1))
    i = tuple(islice(inputs, MAX_EXPERIMENT_STEPS + 1))
    if len(c) > MAX_EXPERIMENT_STEPS or len(i) > MAX_EXPERIMENT_STEPS:
        raise ValueError("offline comparison exceeds 4096 observations")
    if len(c) != len(i):
        raise ValueError("candidate/input length mismatch")
    baseline_state = initial_state
    experimental_state = initial_state
    out = []
    for candidate, inp in zip(c, i):
        baseline = apply_command_guard(candidate, inp, cfg, baseline_state)
        experimental = experiment_one_step(candidate, inp, cfg, experimental_state)
        out.append(ComparisonStep(baseline=baseline, experimental=experimental))
        baseline_state = baseline.next_state
        experimental_state = experimental.next_state
    return tuple(out)
