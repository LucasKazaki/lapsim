"""Host-only source -> allocator -> guard -> recovery-gated command replay.

No transport, CAN encoding, firmware, motor enable, or hardware IO exists here.
The fixed-period and recovery settings are explicit synthetic review policies.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import islice
from typing import Iterable

from allocator import (AllocationInput, AllocatorConfig, MAX_OFFLINE_REPLAY_STEPS,
                       allocate_propulsive_torque, AllocationResult)
from command_guard import (CommandGuardConfig, CommandGuardInput,
                           CommandGuardState)
from fault_state import (FaultPolicy, FaultSnapshot, INHIBITED,
                         observe_fault_state)
from guard_trusted_clear import apply_trusted_clear_guard
from cycle_clock import CycleClockState, observe_cycle_clock

ZERO = (0.0,) * 4


@dataclass(frozen=True)
class PipelineConfig:
    allocator: AllocatorConfig
    guard: CommandGuardConfig
    fault: FaultPolicy
    period_ms: int

    def __post_init__(self) -> None:
        if type(self.period_ms) is not int or not 1 <= self.period_ms <= 60_000:
            raise ValueError("period_ms must be an integer in [1, 60000]")


@dataclass(frozen=True)
class ControlSample:
    allocation: AllocationInput
    guard: CommandGuardInput
    restart_requested: bool = False


def replay_control_pipeline(samples: Iterable[ControlSample],
                            cfg: PipelineConfig) -> tuple[dict[str, object], ...]:
    """Return deterministic proposed commands, preserving all three layers.

    Start and restart require the configured number of consecutive healthy,
    unsaturated samples. Every guard inhibit participates in fault recovery;
    a logging-only observer can never accidentally allow a proposed command.
    Recovery gating resets slew history to the actually proposed zero vector.
    A restart preserves an existing pedal latch.
    """
    bounded = tuple(islice(samples, MAX_OFFLINE_REPLAY_STEPS + 1))
    if len(bounded) > MAX_OFFLINE_REPLAY_STEPS:
        raise ValueError("offline control replay exceeds 4096 steps")
    fault_state = FaultSnapshot(INHIBITED)
    guard_state = CommandGuardState(ZERO)
    clock_state = CycleClockState()
    records = []
    for sequence, sample in enumerate(bounded):
        if type(sample) is not ControlSample:
            raise ValueError("each sample must be a ControlSample")
        if type(sample.restart_requested) is not bool:
            raise ValueError("restart_requested must be boolean")
        if sample.restart_requested:
            guard_state = CommandGuardState(ZERO, guard_state.pedal_overlap_latched)
        allocation = allocate_propulsive_torque(sample.allocation, cfg.allocator)
        guard = apply_trusted_clear_guard(allocation, sample.guard, cfg.guard, guard_state)

        # This runner models a fixed-period task, rather than accepting an
        # arbitrary replay dt that could inflate its upward slew allowance.
        clock = observe_cycle_clock(clock_state, sample.allocation.now_ms,
                                    sample.guard.dt_s, cfg.period_ms)
        clock_state = clock.next_state
        clock_fault = clock.fault

        effective = allocation
        if clock_fault or guard.status == "inhibited":
            reason = clock_fault or (allocation.fault if allocation.status == "fault" else guard.reason)
            effective = AllocationResult(ZERO, allocation.requested_nm, 0., "fault", reason)
        fault_state, event = observe_fault_state(
            fault_state, effective, cfg.fault, sequence=sequence,
            restart_requested=sample.restart_requested,
        )
        allowed = event.reference_gate_allowed and guard.status != "inhibited" and clock_fault is None
        command = guard.output_nm if allowed else ZERO
        # Do not accumulate invisible rise-rate credit while recovery is held.
        # A rejected clock cycle cannot be the sole low-pedal evidence that
        # clears an existing latch. Conservative new trips remain preserved.
        latch = guard.next_state.pedal_overlap_latched or (
            clock_fault is not None and guard_state.pedal_overlap_latched)
        guard_state = CommandGuardState(command, latch)
        record = {
            "sequence": sequence,
            "now_ms": clock.now_ms,
            "restart_requested": sample.restart_requested,
            "allocator": asdict(allocation),
            "guard": {"status": guard.status, "reason": guard.reason,
                      "output_nm": list(guard.output_nm),
                      "pedal_overlap_latched": guard_state.pedal_overlap_latched},
            "fault": event.as_record(),
            "clock_fault": clock_fault,
            "command_allowed": allowed,
            "command_nm": list(command),
            "command_reason": guard.reason if allowed else event.reason,
        }
        records.append(record)
    return tuple(records)
