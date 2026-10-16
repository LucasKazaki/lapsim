from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from allocator import AllocationResult
from allocation_contract import allocation_contract_fault, ordinary_finite

READY = "ready"
LIMITED = "limited"
INHIBITED = "inhibited"
RECOVERY_PENDING = "recovery_pending"
_ALLOWED_STATES = {READY, LIMITED, INHIBITED, RECOVERY_PENDING}


def _finite_number(value: object) -> float | None:
    """Normalize synthetic replay numerics without unbounded-int overflow."""
    return ordinary_finite(value)


def _safe_wheels(values: object) -> tuple[float, float, float, float]:
    """Keep malformed observation logs fixed-shape and strict-JSON-safe."""
    if type(values) not in (tuple, list) or len(values) != 4:
        return (0.0, 0.0, 0.0, 0.0)
    return tuple(_safe_finite_number(value) for value in values)


@dataclass(frozen=True)
class FaultPolicy:
    """Synthetic supervisor policy for portable replay only.

    valid_samples_to_recover is a count of replay samples, not a time value and
    not a Terps Racing requirement. Real recovery criteria require team review.
    """

    valid_samples_to_recover: int = 2

    def __post_init__(self) -> None:
        if isinstance(self.valid_samples_to_recover, bool) or not isinstance(
            self.valid_samples_to_recover, int
        ):
            raise ValueError("valid_samples_to_recover must be an integer")
        if self.valid_samples_to_recover < 1:
            raise ValueError("valid_samples_to_recover must be >= 1")


@dataclass(frozen=True)
class FaultSnapshot:
    state: str = READY
    recovery_streak: int = 0
    generation: int = 0


@dataclass(frozen=True)
class FaultEvent:
    sequence: int
    generation: int
    restart_requested: bool
    previous_state: str
    next_state: str
    allocator_status: str
    allocator_fault: str | None
    requested_nm: float
    delivered_nm: float
    wheel_torque_nm: tuple[float, float, float, float]
    recovery_streak: int
    reference_gate_allowed: bool
    reason: str

    def as_record(self) -> dict[str, object]:
        record = asdict(self)
        record["wheel_torque_nm"] = list(self.wheel_torque_nm)
        return record


def _result_is_well_formed(result: object) -> bool:
    return allocation_contract_fault(result) is None


def _safe_finite_number(value: object) -> float:
    converted = _finite_number(value)
    return converted if converted is not None else 0.0


def _validate_snapshot(snapshot: FaultSnapshot) -> None:
    if type(snapshot.state) is not str or snapshot.state not in _ALLOWED_STATES:
        raise ValueError("snapshot state is invalid")
    for name, value in (("recovery_streak", snapshot.recovery_streak), ("generation", snapshot.generation)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"snapshot {name} must be a nonnegative integer")


def observe_fault_state(
    snapshot: FaultSnapshot,
    result: AllocationResult,
    policy: FaultPolicy,
    *,
    sequence: int,
    restart_requested: bool = False,
) -> tuple[FaultSnapshot, FaultEvent]:
    """Advance a synthetic supervisory fault state from one allocator result."""

    _validate_snapshot(snapshot)
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ValueError("sequence must be a nonnegative integer")
    if type(restart_requested) is not bool:
        raise ValueError("restart_requested must be boolean")

    previous_state = snapshot.state
    generation = snapshot.generation + (1 if restart_requested else 0)
    recovery_streak = 0 if restart_requested else snapshot.recovery_streak
    effective_previous = INHIBITED if restart_requested else previous_state

    if not _result_is_well_formed(result):
        next_state = INHIBITED
        recovery_streak = 0
        gate = False
        reason = "invalid_allocator_result"
    elif result.status == "fault":
        next_state = INHIBITED
        recovery_streak = 0
        gate = False
        reason = result.fault or "allocator_fault_without_code"
    elif effective_previous in {INHIBITED, RECOVERY_PENDING}:
        if result.status == "ok":
            recovery_streak += 1
            if recovery_streak >= policy.valid_samples_to_recover:
                next_state = READY
                gate = True
                reason = "recovery_criteria_met"
            else:
                next_state = RECOVERY_PENDING
                gate = False
                reason = "recovery_valid_sample"
        else:
            recovery_streak = 0
            next_state = RECOVERY_PENDING
            gate = False
            reason = "recovery_waiting_for_unsaturated_valid_sample"
    elif result.status == "saturated":
        next_state = LIMITED
        recovery_streak = 0
        gate = True
        reason = "aggregate_limit"
    else:
        next_state = READY
        recovery_streak = 0
        gate = True
        reason = "allocator_ok"

    next_snapshot = FaultSnapshot(next_state, recovery_streak, generation)
    # Invalid replay records must not trigger a second exception during event
    # construction or make the retained log impossible to encode as JSON.
    observed = result if type(result) is AllocationResult else None
    raw_status = observed.status if observed is not None else None
    status = (raw_status if type(raw_status) is str else
              "invalid_type" if observed is None else "invalid_status")
    raw_fault = observed.fault if observed is not None else None
    event = FaultEvent(
        sequence=sequence,
        generation=generation,
        restart_requested=restart_requested,
        previous_state=previous_state,
        next_state=next_state,
        allocator_status=status,
        allocator_fault=raw_fault if type(raw_fault) is str else None,
        requested_nm=_safe_finite_number(observed.requested_nm) if observed is not None else 0.0,
        delivered_nm=_safe_finite_number(observed.delivered_nm) if observed is not None else 0.0,
        wheel_torque_nm=_safe_wheels(observed.wheel_torque_nm) if observed is not None else (0.0,)*4,
        recovery_streak=recovery_streak,
        reference_gate_allowed=gate,
        reason=reason,
    )
    return next_snapshot, event


def replay_fault_states(
    results: Iterable[AllocationResult],
    policy: FaultPolicy,
    *,
    restart_before: Iterable[int] = (),
) -> tuple[FaultEvent, ...]:
    restart_set = set(restart_before)
    if any(isinstance(index, bool) or not isinstance(index, int) or index < 0 for index in restart_set):
        raise ValueError("restart_before indices must be nonnegative integers")

    results_tuple = tuple(results)
    if any(index >= len(results_tuple) for index in restart_set):
        raise ValueError("restart_before index is outside replay")

    snapshot = FaultSnapshot()
    events: list[FaultEvent] = []
    for sequence, result in enumerate(results_tuple):
        snapshot, event = observe_fault_state(
            snapshot,
            result,
            policy,
            sequence=sequence,
            restart_requested=sequence in restart_set,
        )
        events.append(event)
    return tuple(events)
