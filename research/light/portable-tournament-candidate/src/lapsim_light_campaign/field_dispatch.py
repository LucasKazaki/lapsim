"""UNTESTED bounded in-memory dispatch for one exact frozen seven-policy field.

One caller-supplied request per call, through the REAL required original provider.
No request issuer, numerical bypass, OS worker, writer, receipt, lease or retry.
The provider must wire the fixed chunk_worker family inside its original controls,
retain even unreturned output, and authenticate execution/cleanup. This object
cannot observe native storage closure or admit outer paused-budget continuation.
Snapshots/returned packets are memory only, not RawCellExport or campaign credit.
"""

from dataclasses import dataclass, replace
from threading import Lock

from . import raw_journal as journal
from .guarded_dispatch import (MAX_OWNED_RECEIPT_BYTES, OriginalGuardProvider,
                               OwnedChunkResult, dispatch_owned_chunk,
                               require_provider, validate_staged_request)
from .input_contracts import decode, encode, is_sha256, require
from .tournament_plan import validate_tournament_plan


MAX_FIELD_CALLS = 7 * journal.MAX_RECORDS
MAX_RESULT_PAYLOAD_BYTES = journal.MAX_CHUNK + journal.MAX_CHECKPOINT + MAX_OWNED_RECEIPT_BYTES


@dataclass(frozen=True, slots=True)
class FieldCellProgress:
    policy_id: str
    status: str  # Local progress; never an OS terminal or storage receipt.
    checkpoint_raw: bytes


@dataclass(frozen=True, slots=True)
class FieldDispatchAttempt:
    policy_id: str
    request_raw: bytes
    request_sha256: str
    request_nonce: str
    parent_checkpoint_sha256: str
    requested_ticks: int
    maximum_new_ticks: int
    maximum_new_work: int
    requested_wall_time_ms: int
    requested_rss_bytes: int
    result: OwnedChunkResult | None
    checkpoint_adopted: bool


@dataclass(frozen=True, slots=True)
class FieldDispatchSnapshot:
    plan_sha256: str
    plan_raw: bytes
    original_provider_sha256: str
    cells: tuple[FieldCellProgress, ...]
    attempts: tuple[FieldDispatchAttempt, ...]
    next_policy_id: str | None
    sealed: bool
    seal_reason: str | None
    requested_wall_time_cap_ms: int
    requested_wall_time_ms: int
    requested_ticks: int
    requested_new_tick_ceiling_sum: int
    requested_new_work_ceiling_sum: int
    requested_peak_rss_bytes: int
    retained_history_payload_cap_bytes: int
    retained_history_payload_bytes: int
    charged_history_payload_bytes: int
    accepted_ticks: int
    accepted_work: int
    unresolved_dispatches: int

    @property
    def actual_elapsed_rss_or_provisional_work_measured(self):
        return False

    @property
    def qualification_or_execution_authority(self):
        return False


@dataclass(frozen=True, slots=True)
class _FieldState:
    cells: tuple[FieldCellProgress, ...]
    attempts: tuple[FieldDispatchAttempt, ...]
    sealed: bool = False
    seal_reason: str | None = None


def _payload_bytes(attempt):
    result = attempt.result
    return len(attempt.request_raw) + (0 if result is None else
        len(result.raw_chunk_json) + len(result.linked_checkpoint_json) + len(result.receipt_bundle_raw))


def _charged_bytes(attempt):
    # Unreturned output has unknown size/cost, never a zero-cost successful call.
    return (len(attempt.request_raw) + MAX_RESULT_PAYLOAD_BYTES
            if attempt.result is None else _payload_bytes(attempt))


def _work(checkpoint):
    power = checkpoint["state"]["thermal"]["light"]["powered"]
    return power["integration_trials"] + power["wheel_stop_events"]


class FieldDispatchCoordinator:
    """Explicit sequential composition, not an installed/admitted tournament.

    The owner supplies a fresh real v2 request on every call. This object cannot
    restore history, issue requests, reopen closed native journals or allocate
    anything. Its explicit wall cap bounds SUMMED REQUESTS, not measured time or
    original allocation. Retention covers immutable request/result byte payloads;
    Python object overhead and original worker RSS remain the original guard's job.

    After a consumed-call failure received in the claimed body, retain a snapshot
    under genuine owner controls. Only results that escaped dispatch are visible
    here. Interruption during finalization, repeated asynchronous interruption,
    OOM and process death have no recovery or durability guarantee. Exceptions
    received by this layer are re-raised unchanged; finalization must complete.
    """

    def __init__(self, plan_raw, *, expected_plan_sha256, expected_provider_sha256,
                 maximum_total_requested_wall_time_ms, maximum_retained_history_payload_bytes):
        plan = validate_tournament_plan(plan_raw, expected_plan_sha256=expected_plan_sha256)
        require(is_sha256(expected_provider_sha256), "Externally reviewed original-provider pin required")
        require(type(maximum_total_requested_wall_time_ms) is int and
                1 <= maximum_total_requested_wall_time_ms <= 2**63 - 1,
                "Explicit finite total requested-wall-time cap required; not an allocation")
        require(type(maximum_retained_history_payload_bytes) is int and
                1 <= maximum_retained_history_payload_bytes <= 2**31,
                "Explicit finite retained request/result payload cap required")
        self._plan_sha256 = expected_plan_sha256
        self._plan_raw = plan_raw  # Retain the complete unchanged frozen origins/order.
        self._provider_sha256 = expected_provider_sha256
        self._wall_cap = maximum_total_requested_wall_time_ms
        self._payload_cap = maximum_retained_history_payload_bytes
        self._identities = tuple(encode(cell["identity"]) for cell in plan["cells"])
        self._state = _FieldState(tuple(FieldCellProgress(cell["policy_id"], "missing", encode(cell["origin"]))
                                        for cell in plan["cells"]), ())
        self._mission_ticks = plan["request_ceilings"]["maximum_total_simulated_ticks"]
        self._mission_work = plan["request_ceilings"]["maximum_total_work"]
        self._lock = Lock()  # Local state only; never the original resource/writer lease.
        self._active = False

    def _next_index(self):
        return next((i for i, cell in enumerate(self._state.cells) if cell.status != "completed"), None)

    def snapshot(self):
        with self._lock:
            require(not self._active, "Snapshot requires a returned/raised dispatch call")
            state = self._state
            attempts, cells = state.attempts, state.cells
            checkpoints = tuple(decode(cell.checkpoint_raw, journal.MAX_CHECKPOINT, canonical=True)["checkpoint"]
                                for cell in cells)
            index = self._next_index()
            return FieldDispatchSnapshot(self._plan_sha256, self._plan_raw, self._provider_sha256, cells, attempts,
                None if state.sealed or index is None else cells[index].policy_id,
                state.sealed, state.seal_reason, self._wall_cap,
                sum(item.requested_wall_time_ms for item in attempts),
                sum(item.requested_ticks for item in attempts),
                sum(item.maximum_new_ticks for item in attempts),
                sum(item.maximum_new_work for item in attempts),
                max((item.requested_rss_bytes for item in attempts), default=0),
                self._payload_cap, sum(_payload_bytes(item) for item in attempts),
                sum(_charged_bytes(item) for item in attempts),
                sum(value["tick"] for value in checkpoints), sum(_work(value) for value in checkpoints),
                sum(not item.checkpoint_adopted for item in attempts))

    def seal(self):
        """Idle local seal only; no worker cancellation, cleanup receipt or restart."""
        with self._lock:
            require(not self._active, "Active Stop belongs to the genuine original provider")
            self._state = replace(self._state, sealed=True,
                seal_reason=self._state.seal_reason or "caller_local_seal_no_os_action")

    def submit_next_request(self, request_raw, *, expected_request_sha256, provider=None):
        """Dispatch once through exact original guards; return original RAW transport.

        Known preflight refusals do not consume an attempt. After consumption a
        failure received in this body seals the field if finalization completes,
        even if no worker creation can be confirmed.
        No automatic retry/skip or failed-cost refund is performed.
        """
        claimed = failed = False
        index = attempt_index = None
        result = None
        try:
            with self._lock:
                require(not self._active and not self._state.sealed, "Field active or sealed; no overlapping call/retry")
                index = self._next_index()
                require(index is not None, "Frozen field already numerically completed")
                claimed = True
                self._active = True
            state = self._state
            cell = state.cells[index]
            require_provider(provider, self._provider_sha256, (
                ("execute_owned_request", OriginalGuardProvider.execute_owned_request),
                ("require_authenticated_owned_execution_and_cleanup",
                 OriginalGuardProvider.require_authenticated_owned_execution_and_cleanup),
            ))
            body = validate_staged_request(request_raw, cell.checkpoint_raw,
                                           expected_request_sha256=expected_request_sha256)
            require(encode(body["identity"]) == self._identities[index],
                    "Request changed frozen policy/source/environment/vehicle/line/course identity")
            require(all(item.request_sha256 != expected_request_sha256 and
                        item.request_nonce != body["request_nonce"] for item in state.attempts),
                    "Request hash/nonce already consumed locally; global authentication remains original")
            require(len(state.attempts) < MAX_FIELD_CALLS, "Finite field call slots exhausted")
            require(sum(item.requested_wall_time_ms for item in state.attempts) +
                    body["resource_request"]["maximum_wall_time_ms"] <= self._wall_cap,
                    "Summed requested-wall-time cap exhausted; no allocation extension")
            require(sum(_charged_bytes(item) for item in state.attempts) + len(request_raw) +
                    MAX_RESULT_PAYLOAD_BYTES <= self._payload_cap,
                    "Reserve a complete bounded original result before dispatch")
            proposed = body["chunk_plan"]["plan"]
            attempt = FieldDispatchAttempt(cell.policy_id, request_raw, expected_request_sha256,
                body["request_nonce"], proposed["parent_checkpoint_sha256"], proposed["requested_ticks"],
                proposed["maximum_new_ticks"], proposed["maximum_new_work"],
                body["resource_request"]["maximum_wall_time_ms"], body["resource_request"]["maximum_rss_bytes"],
                None, False)
            attempt_index = len(state.attempts)
            # One immutable assignment consumes nonce, request and full reservation
            # together. Finally detects consumption from stored state, not a flag.
            self._state = replace(state, attempts=(*state.attempts, attempt))
            result = dispatch_owned_chunk(request_raw, cell.checkpoint_raw,
                expected_request_sha256=expected_request_sha256,
                expected_provider_sha256=self._provider_sha256, provider=provider)
            attempt = replace(attempt, result=result)
            self._state = replace(self._state, attempts=(*self._state.attempts[:-1], attempt))
            output = decode(result.linked_checkpoint_json, journal.MAX_CHECKPOINT, canonical=True)["checkpoint"]
            require(output["tick"] <= output["context"]["limits"]["maximum_ticks"] and
                    _work(output) <= output["context"]["limits"]["maximum_work"],
                    "Returned checkpoint exceeds its unchanged mission ceiling")
            other = tuple(decode(value.checkpoint_raw, journal.MAX_CHECKPOINT, canonical=True)["checkpoint"]
                          for i, value in enumerate(state.cells) if i != index)
            require(output["tick"] + sum(value["tick"] for value in other) <= self._mission_ticks and
                    _work(output) + sum(_work(value) for value in other) <= self._mission_work,
                    "Returned accepted counters exceed the exact frozen field ceilings")
            updated = FieldCellProgress(cell.policy_id, output["status"], result.linked_checkpoint_json)
            terminal_failure = output["status"] not in ("running", "completed")
            self._state = _FieldState(
                (*state.cells[:index], updated, *state.cells[index + 1:]),
                (*state.attempts, replace(attempt, checkpoint_adopted=True)), terminal_failure,
                "returned_terminal_numerical_status_" + output["status"] if terminal_failure else None)
            return result
        except BaseException:
            # Remember failure only; preserve owner-control exception type/identity.
            failed = True
            raise
        finally:
            if claimed:
                with self._lock:
                    state = self._state
                    if attempt_index is not None and len(state.attempts) > attempt_index and failed:
                        attempts = state.attempts
                        if result is not None and attempts[-1].result is None:
                            attempts = (*attempts[:-1], replace(attempts[-1], result=result))
                        # Preserve a coherently adopted checkpoint/flag if interruption
                        # followed that single commit; otherwise keep the prior parent.
                        # This local failure label is never a numerical/OS terminal.
                        cell = state.cells[index]
                        self._state = _FieldState(
                            (*state.cells[:index], replace(cell, status="dispatch_failed"), *state.cells[index + 1:]),
                            attempts, True, "consumed_dispatch_failed_or_interrupted")
                    self._active = False
