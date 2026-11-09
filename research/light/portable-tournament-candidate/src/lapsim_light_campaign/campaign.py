"""Finite fresh-field execution and real RAW storage, under native owner controls.

This is the installed library Start implementation. The trusted native bootstrap
must supply the REAL OriginalGuardProvider, fresh request data and compatible
writer/path exclusion + finite finalization windows. A returned chunk/cleanup
receipt does not grant continuing host write authority. No lease is acquired,
native factory discovered, request issuer invented or active cancellation claimed.
"""
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from threading import Event, Lock

from . import raw_journal as journal
from .dispatch_request import MAX_REQUEST_BYTES
from .field_archive import MAX_METADATA_BYTES, MAX_OBJECTS, prepare_field_archive, write_field_archive
from .field_dispatch import MAX_FIELD_CALLS, MAX_RESULT_PAYLOAD_BYTES, FieldDispatchCoordinator
from .guarded_dispatch import OriginalGuardProvider, require_provider, validate_staged_request
from .input_contracts import decode, encode, require
from .raw_evidence import MAX_EXPORT_BYTES, MAX_SOURCE_BYTES, snapshot_raw_journal, write_raw_export
from .stepping import MAX_CHUNK_TICKS
from .tournament_plan import MAX_PLAN_BYTES, validate_tournament_plan
from .tournament_results import MAX_REPORT_BYTES, RawCellExport, summarize_tournament

MAX_CONTROL_BYTES = MAX_REQUEST_BYTES
MAX_TREE_ENTRIES = 2 * (100 + 8 * MAX_FIELD_CALLS + MAX_OBJECTS)
RECORD_GROWTH = journal.MAX_CHUNK + journal.MAX_CHECKPOINT + journal.MAX_RECEIPT


@dataclass(frozen=True, slots=True)
class CampaignLimits:
    chunk_ticks: int
    maximum_total_requested_wall_time_ms: int
    maximum_retained_history_payload_bytes: int
    journal_maximum_records: int
    journal_maximum_bytes: int
    archive_maximum_bytes: int
    campaign_maximum_file_bytes: int
    sync_files: bool

    def validate(self):
        for value, low, high in (
            (self.chunk_ticks, 1, MAX_CHUNK_TICKS),
            (self.maximum_total_requested_wall_time_ms, 1, 2**63-1),
            (self.maximum_retained_history_payload_bytes, 1, 2**31),
            (self.journal_maximum_records, 1, journal.MAX_RECORDS),
            (self.journal_maximum_bytes, 4*1024*1024, MAX_SOURCE_BYTES),
            (self.archive_maximum_bytes, 1, 2**31),
            (self.campaign_maximum_file_bytes, 1, 2**33),
        ):
            require(type(value) is int and low <= value <= high, "Explicit bounded campaign limits required")
        require(type(self.sync_files) is bool, "Explicit sync request required")


@dataclass(frozen=True, slots=True)
class CampaignResult:
    root: str
    status: str
    cancel_requested: bool
    field_snapshot: object
    persisted_checkpoint_pins: tuple
    cell_exports: tuple
    report_raw: bytes
    archive_sha256: str

    @property
    def qualification_or_execution_authority(self):
        return False


def _write_raw(path, raw, maximum, sync):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, "Bounded complete raw bytes required")
    journal._no_alias(path)
    with path.open("xb") as stream:
        require(stream.write(raw) == len(raw), "Partial write retained; no automatic retry")
        stream.flush()
        if sync:
            import os
            os.fsync(stream.fileno())
    journal._sync_directory(path.parent, sync)


def _file_bytes(root, cap):
    """Count this owner-controlled output tree, not filesystem capacity or RSS."""
    pending, total, entries = [(root, 0)], 0, 0
    while pending:
        directory, depth = pending.pop()
        journal._no_alias(directory)
        require(directory.is_dir() and depth <= 6, "Unsupported campaign tree")
        for item in directory.iterdir():
            entries += 1
            require(entries <= MAX_TREE_ENTRIES, "Campaign file count exceeded")
            journal._no_alias(item)
            if item.is_dir():
                pending.append((item, depth+1))
            else:
                require(item.is_file(), "Regular campaign file required")
                total += item.stat().st_size
                require(total <= cap, "Campaign file-byte cap exceeded")
    return total


class CampaignProgram:
    """One actual fresh-field run, with honest between-chunk cancellation.

    request_source(policy_id, checkpoint_raw, *, requested_ticks,
                   remaining_requested_wall_time_ms) -> canonical v2 bytes or None
    is data supply only. It must provide actual signed-input/freshness evidence;
    existing validation and the original provider still admit every operation.
    Native deadlines must cover a blocking source and all writes/finalization.

    The native owner must establish writer lifecycle ordering with the provider,
    rather than guessing a nested lease. Exceptions cause no further file writes.
    run() is single-use; partial/uncertain output is never reused automatically.
    A paused export requires separate original outer continuation admission.
    """

    def __init__(self, plan_raw, *, expected_plan_sha256, expected_provider_sha256,
                 provider, request_source, output_root, limits, cancel_event=None):
        require(type(limits) is CampaignLimits, "Exact campaign limits required")
        limits.validate()
        require(callable(request_source), "Actual fresh request data source required")
        require_provider(provider, expected_provider_sha256, (
            ("execute_owned_request", OriginalGuardProvider.execute_owned_request),
            ("require_authenticated_owned_execution_and_cleanup", OriginalGuardProvider.require_authenticated_owned_execution_and_cleanup),
        ))
        require(cancel_event is None or type(cancel_event) is Event, "A local cancellation Event is required")
        self._plan = validate_tournament_plan(plan_raw, expected_plan_sha256=expected_plan_sha256)
        self._plan_raw, self._plan_pin = plan_raw, expected_plan_sha256
        self._field = FieldDispatchCoordinator(plan_raw, expected_plan_sha256=expected_plan_sha256,
            expected_provider_sha256=expected_provider_sha256,
            maximum_total_requested_wall_time_ms=limits.maximum_total_requested_wall_time_ms,
            maximum_retained_history_payload_bytes=limits.maximum_retained_history_payload_bytes)
        self._provider, self._source, self._limits = provider, request_source, limits
        self._cancel = Event() if cancel_event is None else cancel_event
        self._root = Path(output_root).absolute()
        self._stores, self._exports, self._persisted = {}, {}, {}
        self._claim, self._started, self._running = Lock(), False, False
        self._phase, self._status = "constructed", None
        self._final_cancel_requested = None  # Not yet observed at the local finalization boundary.
        self._header_raw = encode({"plan_sha256": self._plan_pin, "limits": asdict(limits),
            "scope": "RAW_CAMPAIGN_STORAGE_NOT_ORIGINAL_ADMISSION", "qualification_or_execution_authority": False})
        minimum_archive = len(plan_raw) + 7*journal.MAX_CHECKPOINT + MAX_METADATA_BYTES
        minimum_archive += MAX_REQUEST_BYTES + MAX_RESULT_PAYLOAD_BYTES
        require(limits.archive_maximum_bytes >= minimum_archive, "Archive cap cannot reserve a complete first result and finalized field")
        final_reserve = limits.archive_maximum_bytes + 7*MAX_EXPORT_BYTES + MAX_REPORT_BYTES + MAX_CONTROL_BYTES
        first_growth = MAX_REQUEST_BYTES + MAX_RESULT_PAYLOAD_BYTES + journal.MAX_RECEIPT + RECORD_GROWTH + journal.MAX_MANIFEST
        require(len(plan_raw) + len(self._header_raw) + final_reserve + first_growth <= limits.campaign_maximum_file_bytes,
                "Campaign cap cannot reserve initial files, dispatch and final artifacts; no output created")

    def snapshot(self):
        with self._claim:
            require(not self._running, "Observe only after run returned/raised")
            return {"phase": self._phase, "status": self._status,
                    "cancel_requested": self._final_cancel_requested, "field": self._field.snapshot(),
                    "persisted_checkpoint_pins": tuple(self._persisted.items()),
                    "qualification_or_execution_authority": False, "retry_or_resume_authority": False}

    def _room(self, snapshot, store):
        limits = self._limits
        # Independent reservations for final archive, reports and remaining exports.
        final = limits.archive_maximum_bytes + MAX_REPORT_BYTES + 2*MAX_CONTROL_BYTES
        final += (7-len(self._exports))*MAX_EXPORT_BYTES
        growth = MAX_REQUEST_BYTES + MAX_RESULT_PAYLOAD_BYTES + journal.MAX_RECEIPT + RECORD_GROWTH
        if store is None:
            growth += journal.MAX_MANIFEST
        if _file_bytes(self._root, limits.campaign_maximum_file_bytes) + final + growth > limits.campaign_maximum_file_bytes:
            return False
        archive_growth = len(snapshot.plan_raw) + 7*journal.MAX_CHECKPOINT + MAX_METADATA_BYTES
        if snapshot.retained_history_payload_bytes + archive_growth + MAX_REQUEST_BYTES + MAX_RESULT_PAYLOAD_BYTES > limits.archive_maximum_bytes:
            return False
        if len(snapshot.attempts) >= MAX_FIELD_CALLS:
            return False
        if snapshot.charged_history_payload_bytes + MAX_REQUEST_BYTES + MAX_RESULT_PAYLOAD_BYTES > limits.maximum_retained_history_payload_bytes:
            return False
        if snapshot.requested_wall_time_ms >= limits.maximum_total_requested_wall_time_ms:
            return False
        if store is not None:
            inspected = store.inspect()
            require(not inspected["reconciliation_required"] and inspected["terminal"] is None, "Reconcile journal before any new request")
            tail = inspected["journal_committed_tail"]
            cell = next(item for item in snapshot.cells if item.policy_id == snapshot.next_policy_id)
            require(encode(tail["checkpoint"]) == cell.checkpoint_raw, "Disk tail and accepted in-memory parent differ")
            if tail["records"] >= limits.journal_maximum_records:
                return False
            if inspected["physical_bytes"] + RECORD_GROWTH > limits.journal_maximum_bytes-journal.MAX_RECEIPT:
                return False
        return True

    def _close_export(self, policy_id, status, reason):
        store = self._stores[policy_id]
        store.write_terminal(status, reason)
        bundle = snapshot_raw_journal(store.root, expected_manifest_sha256=store.expected_manifest_sha256)
        raw = encode(bundle)
        write_raw_export(self._root / "exports" / (policy_id + ".json"), bundle,
            expected_bundle_sha256=bundle["bundle_sha256"], expected_manifest_sha256=store.expected_manifest_sha256,
            sync_files=self._limits.sync_files)
        self._exports[policy_id] = RawCellExport(raw, bundle["bundle_sha256"], store.expected_manifest_sha256)

    def run(self):
        claimed = False
        try:
            with self._claim:
                require(not self._started, "Campaign already consumed; no restart/retry")
                claimed = True
                self._started = self._running = True
            self._phase = "create_owned_output_namespace"
            journal._no_alias(self._root)
            self._root.mkdir()
            for name in ("cells", "packets", "exports"):
                (self._root / name).mkdir()
            journal._sync_directory(self._root, self._limits.sync_files)
            journal._sync_directory(self._root.parent, self._limits.sync_files)
            _write_raw(self._root / "plan.json", self._plan_raw, MAX_PLAN_BYTES, self._limits.sync_files)
            _write_raw(self._root / "run.json", self._header_raw, MAX_CONTROL_BYTES, self._limits.sync_files)
            active = None
            while True:
                snapshot = self._field.snapshot()
                if snapshot.next_policy_id is None:
                    self._status = "numerically_completed" if all(c.status == "completed" for c in snapshot.cells) else "numerical_failure"
                    break
                if self._cancel.is_set():
                    self._status = "cancelled_between_chunks"
                    break
                policy_id = snapshot.next_policy_id
                store = self._stores.get(policy_id)
                self._phase = "reserve_before_request"
                if not self._room(snapshot, store):
                    self._status = "paused_budget"
                    break
                cell = next(c for c in snapshot.cells if c.policy_id == policy_id)
                self._phase = "obtain_fresh_request"
                request_raw = self._source(policy_id, cell.checkpoint_raw, requested_ticks=self._limits.chunk_ticks,
                    remaining_requested_wall_time_ms=self._limits.maximum_total_requested_wall_time_ms-snapshot.requested_wall_time_ms)
                if self._cancel.is_set():
                    self._status = "cancelled_between_chunks"
                    break
                if request_raw is None:
                    self._status = "request_source_exhausted"
                    break
                staged = decode(request_raw, MAX_REQUEST_BYTES, canonical=True)
                request_pin = staged["request_sha256"]
                body = validate_staged_request(request_raw, cell.checkpoint_raw, expected_request_sha256=request_pin)
                require(body["identity"] == self._plan["cells"][len(self._exports)]["identity"] and
                        body["chunk_plan"]["plan"]["requested_ticks"] == self._limits.chunk_ticks,
                        "Fresh request changed the current frozen cell or requested extent")
                require(body["resource_request"]["maximum_wall_time_ms"] <= self._limits.maximum_total_requested_wall_time_ms-snapshot.requested_wall_time_ms,
                        "Fresh request exceeds remaining summed wall proposal")
                self._phase = "stage_request_storage"
                if store is None:
                    declaration = next(c for c in self._plan["cells"] if c["policy_id"] == policy_id)
                    store = journal.RawJournal.create(self._root / "cells" / policy_id, declaration["identity"], declaration["origin"],
                        maximum_records=self._limits.journal_maximum_records, maximum_bytes=self._limits.journal_maximum_bytes,
                        sync_files=self._limits.sync_files)
                    self._stores[policy_id] = store
                active = policy_id
                packet = self._root / "packets" / ("%06d" % (len(snapshot.attempts)+1))
                packet.mkdir()
                journal._sync_directory(packet.parent, self._limits.sync_files)
                _write_raw(packet / "request.json", request_raw, MAX_REQUEST_BYTES, self._limits.sync_files)
                if self._cancel.is_set():
                    self._status = "cancelled_between_chunks"
                    break
                self._phase = "original_owned_dispatch"
                result = self._field.submit_next_request(request_raw, expected_request_sha256=request_pin, provider=self._provider)
                self._phase = "persist_returned_packet"
                files = {"chunk.json": result.raw_chunk_json, "checkpoint.json": result.linked_checkpoint_json,
                         "owned-receipts.bin": result.receipt_bundle_raw}
                for name, raw in files.items():
                    _write_raw(packet / name, raw, MAX_RESULT_PAYLOAD_BYTES, self._limits.sync_files)
                journal._write_new(packet / "packet.json", {"request_sha256": request_pin,
                    "files": {name: {"bytes": len(raw), "raw_sha256": sha256(raw).hexdigest()} for name, raw in files.items()},
                    "scope": "RETURNED_RAW_PACKET_NOT_NEW_ADMISSION", "qualification_or_execution_authority": False},
                    journal.MAX_RECEIPT, self._limits.sync_files)
                self._phase = "append_and_verify_journal"
                store.append(decode(result.raw_chunk_json, journal.MAX_CHUNK, canonical=True),
                             decode(result.linked_checkpoint_json, journal.MAX_CHECKPOINT, canonical=True))
                readback = store.inspect()
                require(not readback["reconciliation_required"] and readback["terminal"] is None and
                        encode(readback["journal_committed_tail"]["checkpoint"]) == result.linked_checkpoint_json,
                        "Journal commit readback differs; no further dispatch")
                self._persisted[policy_id] = readback["journal_committed_tail"]["checkpoint"]["checkpoint_sha256"]
                status = readback["journal_committed_tail"]["checkpoint"]["checkpoint"]["status"]
                if status != "running":
                    self._phase = "close_and_export_cell"
                    self._close_export(policy_id, "raw_completed" if status == "completed" else "failed", "Returned numerical status: " + status)
                    active = None
            self._phase = "finalize_between_chunks"
            # Freeze the Stop observed before finalization, rather than sampling
            # a live external Event separately for disk and returned status.
            # Keep an already observed Stop sticky even if the caller clears it.
            self._final_cancel_requested = self._status == "cancelled_between_chunks" or self._cancel.is_set()
            if self._final_cancel_requested and self._status in ("paused_budget", "request_source_exhausted"):
                self._status = "cancelled_between_chunks"
            self._field.seal()
            snapshot = self._field.snapshot()
            final_reserve = self._limits.archive_maximum_bytes + MAX_REPORT_BYTES + MAX_CONTROL_BYTES
            final_reserve += MAX_EXPORT_BYTES if active is not None else 0
            require(_file_bytes(self._root, self._limits.campaign_maximum_file_bytes) + final_reserve <=
                    self._limits.campaign_maximum_file_bytes, "Final artifact reservation unavailable; preserve unfinalized output")
            if active is not None:
                stopped = "cancelled" if self._status == "cancelled_between_chunks" else "paused_budget"
                self._close_export(active, stopped, "Local campaign stop: " + self._status + "; no continuation authority")
            prepared = prepare_field_archive(snapshot, maximum_archive_bytes=self._limits.archive_maximum_bytes, sync_files=self._limits.sync_files)
            archived = write_field_archive(self._root / "field-packets", prepared)
            report = summarize_tournament(self._plan_raw, self._exports, expected_plan_sha256=self._plan_pin)
            report_raw = encode(report)
            _write_raw(self._root / "results.json", report_raw, MAX_REPORT_BYTES, self._limits.sync_files)
            journal._write_new(self._root / "outcome.json", {"status": self._status, "cancel_requested": self._final_cancel_requested,
                "report_raw_sha256": sha256(report_raw).hexdigest(), "field_archive_sha256": archived.archive_sha256,
                "persisted_checkpoint_pins": self._persisted, "qualification_or_execution_authority": False},
                MAX_CONTROL_BYTES, self._limits.sync_files)
            _file_bytes(self._root, self._limits.campaign_maximum_file_bytes)
            self._phase = "finalized_raw_results"
            return CampaignResult(str(self._root), self._status, self._final_cancel_requested, snapshot,
                tuple(self._persisted.items()), tuple(self._exports.items()), report_raw, archived.archive_sha256)
        except BaseException:
            if claimed:
                self._status = "failed_unfinalized_at_" + self._phase
            # No more I/O after provider/control or uncertain storage failure.
            raise
        finally:
            if claimed:
                with self._claim:
                    self._started, self._running = True, False


def start_tournament(plan_raw, **native_owned_arguments):
    """Installed library Start: explicit real native services, no default provider."""
    return CampaignProgram(plan_raw, **native_owned_arguments).run()
