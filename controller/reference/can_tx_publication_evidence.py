"""TC-02R portable CAN command-publication evidence model.

Synthetic host-side reference only. This module does not access a CAN peripheral,
define Terps Racing CAN IDs/payloads, command torque, choose a retry policy, or
establish vehicle delivery/safety acceptance.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json

SCHEMA = "enme408-can-tx-publication-evidence/v1"

MAILBOXES = (0, 1, 2)
FAILURE_RESULTS = {"arbitration_lost", "transmit_error", "aborted"}
ENQUEUE_REASONS = {"no_free_mailbox", "not_ready", "parameter_error", "other"}


class TxEvidenceError(ValueError):
    pass


def _u32(value: object, path: str) -> int:
    if type(value) is not int or not (0 <= value <= 0xFFFFFFFF):
        raise TxEvidenceError(f"{path} must be an unsigned 32-bit integer")
    return value


def _positive_seq(value: object, path: str) -> int:
    if type(value) is not int or value <= 0:
        raise TxEvidenceError(f"{path} must be a positive integer")
    return value


def _mailbox(value: object, path: str) -> int:
    if type(value) is not int or value not in MAILBOXES:
        raise TxEvidenceError(f"{path} must be one of {MAILBOXES}")
    return value


def _nonempty(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TxEvidenceError(f"{path} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class TxRecord:
    seq: int
    request_tag: str
    state: str
    mailbox: int | None
    enqueue_reason: str | None
    terminal_result: str | None

    @property
    def transmitted(self) -> bool:
        return self.state == "transmitted"


@dataclass(frozen=True)
class TxSnapshot:
    schema: str
    records: tuple[TxRecord, ...]
    pending_mailboxes: tuple[tuple[int, int], ...]
    latest_intent_seq: int | None
    latest_transmitted_seq: int | None
    transmitted_count: int
    failed_count: int
    rejected_count: int
    pending_count: int
    action_authority: bool = False
    descriptive_only: bool = True

    def to_json(self) -> str:
        payload = asdict(self)
        payload["records"] = [asdict(x) | {"transmitted": x.transmitted} for x in self.records]
        payload["pending_mailboxes"] = [list(x) for x in self.pending_mailboxes]
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


class TxPublicationEvidence:
    """Evidence state machine separating intent, enqueue, and terminal Tx result."""

    def __init__(self) -> None:
        self._records: dict[int, TxRecord] = {}
        self._pending_by_mailbox: dict[int, int] = {}
        self._latest_intent_seq: int | None = None

    def add_intent(self, seq: int, request_tag: str) -> None:
        seq = _positive_seq(seq, "seq")
        tag = _nonempty(request_tag, "request_tag")
        if seq in self._records:
            raise TxEvidenceError(f"duplicate command sequence: {seq}")
        if self._latest_intent_seq is not None and seq != self._latest_intent_seq + 1:
            raise TxEvidenceError("command sequences must be contiguous")
        self._records[seq] = TxRecord(seq, tag, "computed_not_enqueued", None, None, None)
        self._latest_intent_seq = seq

    def enqueue_accepted(self, seq: int, mailbox: int) -> None:
        seq = _positive_seq(seq, "seq")
        mailbox = _mailbox(mailbox, "mailbox")
        record = self._get(seq)
        if record.state != "computed_not_enqueued":
            raise TxEvidenceError(f"command {seq} cannot be enqueued from state {record.state}")
        if mailbox in self._pending_by_mailbox:
            raise TxEvidenceError(f"mailbox {mailbox} already has pending command")
        self._records[seq] = TxRecord(record.seq, record.request_tag, "pending", mailbox, None, None)
        self._pending_by_mailbox[mailbox] = seq

    def enqueue_rejected(self, seq: int, reason: str) -> None:
        seq = _positive_seq(seq, "seq")
        if reason not in ENQUEUE_REASONS:
            raise TxEvidenceError(f"unsupported enqueue rejection reason: {reason}")
        record = self._get(seq)
        if record.state != "computed_not_enqueued":
            raise TxEvidenceError(f"command {seq} cannot be rejected from state {record.state}")
        self._records[seq] = TxRecord(record.seq, record.request_tag, "enqueue_rejected", None, reason, None)

    def complete(self, mailbox: int, result: str) -> None:
        mailbox = _mailbox(mailbox, "mailbox")
        result = _nonempty(result, "result")
        if result not in {"transmitted", *FAILURE_RESULTS}:
            raise TxEvidenceError(f"unsupported terminal result: {result}")
        if mailbox not in self._pending_by_mailbox:
            raise TxEvidenceError(f"mailbox {mailbox} has no pending command")
        seq = self._pending_by_mailbox.pop(mailbox)
        record = self._get(seq)
        state = "transmitted" if result == "transmitted" else "tx_failed"
        self._records[seq] = TxRecord(record.seq, record.request_tag, state, mailbox, None, result)

    def observe_free_level(self, value: int) -> None:
        value = _u32(value, "free_level")
        if value > 3:
            raise TxEvidenceError("free_level must be <= 3 for the HAL-inspired model")

    def snapshot(self) -> TxSnapshot:
        records = tuple(self._records[k] for k in sorted(self._records))
        transmitted = [r for r in records if r.state == "transmitted"]
        failed = [r for r in records if r.state == "tx_failed"]
        rejected = [r for r in records if r.state == "enqueue_rejected"]
        pending = [r for r in records if r.state == "pending"]
        latest_transmitted = transmitted[-1].seq if transmitted else None
        return TxSnapshot(
            schema=SCHEMA,
            records=records,
            pending_mailboxes=tuple(sorted((mb, seq) for mb, seq in self._pending_by_mailbox.items())),
            latest_intent_seq=self._latest_intent_seq,
            latest_transmitted_seq=latest_transmitted,
            transmitted_count=len(transmitted),
            failed_count=len(failed),
            rejected_count=len(rejected),
            pending_count=len(pending),
        )

    def _get(self, seq: int) -> TxRecord:
        try:
            return self._records[seq]
        except KeyError as exc:
            raise TxEvidenceError(f"unknown command sequence: {seq}") from exc


def classify_publication(record: TxRecord) -> str:
    """Return an evidence-level publication class, not a vehicle-control decision."""
    if not isinstance(record, TxRecord):
        raise TxEvidenceError("record must be TxRecord")
    if record.state == "computed_not_enqueued":
        return "intent_only"
    if record.state == "enqueue_rejected":
        return "enqueue_failed"
    if record.state == "pending":
        return "requested_not_confirmed"
    if record.state == "transmitted":
        return "transmit_confirmed"
    if record.state == "tx_failed":
        return f"transmit_failed:{record.terminal_result}"
    raise TxEvidenceError(f"unsupported record state: {record.state}")
