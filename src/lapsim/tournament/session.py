"""One serial chunk and explicitly admitted continuation, with UI lifecycle control.

No process, lock, resource observer or native provider is created here. A reviewed
host must own the ORIGINAL lease and an enclosing deadline from before launch
through output finalization and authenticated cleanup. In particular, it must
not nest run_worker calls that acquire the same nonblocking FileLock. Polling
and Stop are bounded nonblocking host calls. The UI timer requests cancellation;
it does not replace the host watchdog or establish that a process has stopped.
"""
from abc import abstractmethod
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from math import isfinite
from pathlib import Path
from threading import Event, get_ident
from time import monotonic
from typing import Protocol

from lapsim_light_campaign import raw_journal as journal
from lapsim_light_campaign.campaign import CampaignLimits, CampaignProgram, RECORD_GROWTH, _write_raw
from lapsim_light_campaign.continuation import (
    OriginalContinuationProvider, copy_raw_prefix_in_owned_worker,
    dispatch_continuation, validate_continuation_request,
)
from lapsim_light_campaign.continuation_archive import snapshot_raw_continuation_child, validate_raw_child_archive
from lapsim_light_campaign.dispatch_request import MAX_REQUEST_BYTES
from lapsim_light_campaign.field_archive import MAX_METADATA_BYTES, read_field_archive
from lapsim_light_campaign.field_dispatch import MAX_RESULT_PAYLOAD_BYTES
from lapsim_light_campaign.guarded_dispatch import MAX_OWNED_RECEIPT_BYTES, _require_chunk_checkpoint_binding, require_provider, validate_staged_request
from lapsim_light_campaign.input_contracts import decode, digest, encode, is_sha256, require
from lapsim_light_campaign.raw_evidence import MAX_EXPORT_BYTES, MAX_SOURCE_BYTES, read_raw_export, replay_raw_bundle, write_raw_export
from lapsim_light_campaign.tournament_plan import MAX_PLAN_BYTES, validate_tournament_plan
from lapsim_light_campaign.tournament_results import MAX_REPORT_BYTES, RawCellExport, summarize_tournament


def _path(value):
    require(type(value) is str and value and Path(value).is_absolute(), "Explicit absolute new output root required")
    path = Path(value)
    require(".." not in path.parts and "." not in path.parts, "Normalized output path without traversal required")
    return str(path.absolute())


def _disjoint(left, right):
    # Native host must additionally qualify real filesystem aliases/case rules.
    a, b = Path(left), Path(right)
    return a != b and a not in b.parents and b not in a.parents


def _timeout(value):
    require(type(value) in (int, float) and isfinite(value) and 0 < value <= 3600,
            "Finite session timeout proposal (at most one hour) required; not a native allocation")


@dataclass(frozen=True, slots=True)
class FreshOperation:
    """One first-policy chunk of an unchanged seven-cell plan, not a full field."""
    plan_raw: bytes
    plan_sha256: str
    request_raw: bytes
    request_sha256: str
    provider_sha256: str
    output_root: str
    limits: CampaignLimits
    timeout_s: float

    def validate(self):
        _timeout(self.timeout_s)
        require(is_sha256(self.provider_sha256) and type(self.limits) is CampaignLimits, "Pinned provider and exact limits required")
        self.limits.validate()
        require(_path(self.output_root) == self.output_root, "Canonical absolute output root required")
        plan = validate_tournament_plan(self.plan_raw, expected_plan_sha256=self.plan_sha256)
        require(self.limits.maximum_retained_history_payload_bytes >= MAX_REQUEST_BYTES + MAX_RESULT_PAYLOAD_BYTES,
                "Session must reserve one complete request/result before native launch")
        minimum_archive = len(self.plan_raw) + 7*journal.MAX_CHECKPOINT + MAX_METADATA_BYTES + MAX_REQUEST_BYTES + MAX_RESULT_PAYLOAD_BYTES
        final_reserve = self.limits.archive_maximum_bytes + 7*MAX_EXPORT_BYTES + MAX_REPORT_BYTES + 2*MAX_REQUEST_BYTES
        first_growth = MAX_REQUEST_BYTES + MAX_RESULT_PAYLOAD_BYTES + journal.MAX_RECEIPT + RECORD_GROWTH + journal.MAX_MANIFEST
        require(self.limits.archive_maximum_bytes >= minimum_archive and
                len(self.plan_raw) + MAX_REQUEST_BYTES + final_reserve + first_growth <= self.limits.campaign_maximum_file_bytes,
                "Session must reserve campaign initial files, first result and finalization before native launch")
        first = plan["cells"][0]
        request = validate_staged_request(self.request_raw, encode(first["origin"]), expected_request_sha256=self.request_sha256)
        require(request["identity"] == first["identity"] and
                request["chunk_plan"]["plan"]["requested_ticks"] == self.limits.chunk_ticks,
                "This bounded flow selects exactly the first frozen policy/course chunk")
        wall = request["resource_request"]["maximum_wall_time_ms"]
        require(wall <= self.limits.maximum_total_requested_wall_time_ms and wall <= self.timeout_s * 1000,
                "Chunk proposal exceeds session or campaign bound")
        return plan, request

    @property
    def operation_sha256(self):
        return digest({"schema": "lapsim.light-session.fresh.v1", "plan_raw_sha256": sha256(self.plan_raw).hexdigest(),
            "request_raw_sha256": sha256(self.request_raw).hexdigest(), "provider_sha256": self.provider_sha256,
            "output_root": self.output_root, "limits": asdict(self.limits), "timeout_s": self.timeout_s})


@dataclass(frozen=True, slots=True)
class SessionOutput:
    """Immutable RAW result data. Hashes/consistency never authenticate execution."""
    operation_sha256: str
    output_root: str
    bundle_raw: bytes
    bundle_sha256: str
    manifest_sha256: str
    report_raw: bytes
    ancestry_raw: bytes = b""
    owned_admission_raw: bytes = b""

    def inspect(self, operation):
        require(self.operation_sha256 == operation.operation_sha256 and self.output_root == operation.output_root,
                "Session output belongs to another operation/namespace")
        plan = validate_tournament_plan(operation.plan_raw, expected_plan_sha256=operation.plan_sha256)
        bundle = decode(self.bundle_raw, MAX_EXPORT_BYTES, canonical=True)
        tail = replay_raw_bundle(bundle, expected_bundle_sha256=self.bundle_sha256, expected_manifest_sha256=self.manifest_sha256)
        first = plan["cells"][0]
        require(bundle["bundle"]["manifest"]["identity"] == first["identity"] and
                encode(bundle["bundle"]["manifest"]["origin"]) == encode(first["origin"]),
                "Session changed original policy/course/source/environment/initial state")
        maximum_records = operation.maximum_records if type(operation) is ContinuationOperation else operation.limits.journal_maximum_records
        maximum_bytes = operation.maximum_bytes if type(operation) is ContinuationOperation else operation.limits.journal_maximum_bytes
        sync = operation.sync_files if type(operation) is ContinuationOperation else operation.limits.sync_files
        manifest = bundle["bundle"]["manifest"]
        require(manifest["limits"]["maximum_records"] == maximum_records and manifest["limits"]["maximum_bytes"] == maximum_bytes and
                manifest["sync_files"] is sync, "Output journal bounds/sync request changed")
        require(tail["terminal"] is not None and tail["records"] >= 1, "Only finalized advanced output can be displayed/continued")
        status, checkpoint = tail["terminal"]["terminal"]["status"], tail["checkpoint"]["checkpoint"]
        require((status == "paused_budget" and checkpoint["status"] == "running") or
                (status == "raw_completed" and checkpoint["status"] == "completed") or
                status in ("cancelled", "failed"), "RAW terminal and numerical checkpoint disagree")
        expected_report = encode(summarize_tournament(operation.plan_raw,
            {first["policy_id"]: RawCellExport(self.bundle_raw, self.bundle_sha256, self.manifest_sha256)},
            expected_plan_sha256=operation.plan_sha256))
        require(self.report_raw == expected_report, "Report differs from one actual cell and six unrun cells")
        if type(operation) is ContinuationOperation:
            ancestry = decode(self.ancestry_raw, journal.MAX_MANIFEST, canonical=True)
            summary = validate_raw_child_archive(self.ancestry_raw, self.owned_admission_raw,
                operation.predecessor.bundle_raw, operation.historical_owned_receipts_raw, self.bundle_raw,
                expected_ancestry_sha256=ancestry["ancestry_sha256"],
                expected_continuation_sha256=operation.continuation_sha256,
                expected_child_bundle_sha256=self.bundle_sha256)
            require(summary["new_raw_records"] == 1 and summary["child_manifest_sha256"] == self.manifest_sha256,
                    "Continuation must preserve prefix and append exactly one result")
            _, _, parent_tail, staged = validate_continuation_request(operation.request_raw,
                operation.predecessor.bundle_raw, operation.historical_owned_receipts_raw,
                expected_continuation_sha256=operation.continuation_sha256)
            parent_checkpoint = parent_tail["checkpoint"]
        else:
            require(not self.ancestry_raw and not self.owned_admission_raw and tail["records"] == 1,
                    "Fresh session must contain exactly one original result")
            parent_checkpoint = first["origin"]
            staged = validate_staged_request(operation.request_raw, encode(parent_checkpoint),
                expected_request_sha256=operation.request_sha256)
        last = bundle["bundle"]["records"][-1]["receipt"]
        _require_chunk_checkpoint_binding(staged, encode(parent_checkpoint),
            encode(bundle["bundle"]["objects"][last["chunk_object_sha256"]]), encode(tail["checkpoint"]))
        return tail


@dataclass(frozen=True, slots=True)
class ContinuationOperation:
    """Fresh outer admission proposal for one paused predecessor; never a retry."""
    previous_operation: FreshOperation  # Also accepts a prior ContinuationOperation at runtime.
    predecessor: SessionOutput
    request_raw: bytes
    continuation_sha256: str
    historical_owned_receipts_raw: bytes
    provider_sha256: str
    output_root: str
    timeout_s: float
    maximum_records: int
    maximum_bytes: int
    sync_files: bool
    _pin: str = field(init=False, repr=False)
    _depth: int = field(init=False, repr=False)
    _plan_raw: bytes = field(init=False, repr=False)
    _plan_sha256: str = field(init=False, repr=False)

    def __post_init__(self):
        require(type(self.previous_operation) in (FreshOperation, ContinuationOperation), "Exact previous operation required")
        depth = 1 if type(self.previous_operation) is FreshOperation else self.previous_operation._depth + 1
        require(depth < journal.MAX_RECORDS, "Finite continuation ancestry exceeded")
        object.__setattr__(self, "_depth", depth)
        object.__setattr__(self, "_plan_raw", self.previous_operation.plan_raw)
        object.__setattr__(self, "_plan_sha256", self.previous_operation.plan_sha256)
        object.__setattr__(self, "_pin", digest({"schema": "lapsim.light-session.continue.v1",
            "parent_operation_sha256": self.previous_operation.operation_sha256,
            "continuation_raw_sha256": sha256(self.request_raw).hexdigest(), "provider_sha256": self.provider_sha256,
            "output_root": self.output_root, "timeout_s": self.timeout_s, "maximum_records": self.maximum_records,
            "maximum_bytes": self.maximum_bytes, "sync_files": self.sync_files}))

    @property
    def plan_raw(self):
        return self._plan_raw

    @property
    def plan_sha256(self):
        return self._plan_sha256

    def validate(self):
        _timeout(self.timeout_s)
        require(type(self.predecessor) is SessionOutput, "Exact immutable predecessor output required")
        require(_path(self.output_root) == self.output_root and _disjoint(self.output_root, self.previous_operation.output_root),
                "Continuation needs a new canonical output namespace")
        ancestor, count = self.previous_operation, 0
        while True:
            count += 1
            require(count <= journal.MAX_RECORDS and _disjoint(self.output_root, ancestor.output_root),
                    "Continuation output overlaps an ancestor namespace")
            if type(ancestor) is FreshOperation:
                break
            ancestor = ancestor.previous_operation
        require(is_sha256(self.provider_sha256), "Pinned original continuation provider required")
        parent = self.predecessor.inspect(self.previous_operation)
        request, bundle, tail, staged = validate_continuation_request(self.request_raw, self.predecessor.bundle_raw,
            self.historical_owned_receipts_raw, expected_continuation_sha256=self.continuation_sha256)
        require(parent["bundle_sha256"] == request["continuation"]["predecessor"]["bundle_sha256"] and
                staged["resource_request"]["maximum_wall_time_ms"] <= self.timeout_s * 1000,
                "Continuation parent or finite wall proposal differs")
        require(type(self.maximum_records) is int and tail["records"] < self.maximum_records <= journal.MAX_RECORDS and
                type(self.maximum_bytes) is int and 4*1024*1024 <= self.maximum_bytes <= MAX_SOURCE_BYTES and
                type(self.sync_files) is bool, "Explicit exportable continuation bounds required")
        # Conservative reserve for a rebuilt manifest, complete prefix, one new record and terminal.
        prefix = sum(len(encode(v)) for v in bundle["bundle"]["objects"].values())
        prefix += sum(len(encode(v)) for v in bundle["bundle"]["records"])
        require(prefix + journal.MAX_MANIFEST + RECORD_GROWTH + journal.MAX_RECEIPT <= self.maximum_bytes,
                "Continuation cap cannot reserve complete prefix, new record and terminal")
        return request, tail, staged

    @property
    def operation_sha256(self):
        return self._pin


class FreshExecution:
    """Concrete CampaignProgram composition inside the genuine native host context.

    Retain this object before run(). On failure snapshot() is read-only and does
    not finalize output. The native host must retain/quarantine partial files.
    Active Stop additionally needs the native handle; the Event acts between chunks.
    """
    def __init__(self, operation, *, provider, cancel_event):
        require(type(operation) is FreshOperation and type(cancel_event) is Event, "Fresh operation and sticky cancellation Event required")
        plan, _ = operation.validate()
        self.operation, self._used = operation, False
        self._supplied = False

        def source(policy, checkpoint_raw, *, requested_ticks, remaining_requested_wall_time_ms):
            if self._supplied:
                return None
            require(policy == plan["cells"][0]["policy_id"] and checkpoint_raw == encode(plan["cells"][0]["origin"]) and
                    requested_ticks == operation.limits.chunk_ticks, "Frozen first-cell request changed")
            self._supplied = True
            return operation.request_raw

        self.program = CampaignProgram(operation.plan_raw, expected_plan_sha256=operation.plan_sha256,
            expected_provider_sha256=operation.provider_sha256, provider=provider, request_source=source,
            output_root=operation.output_root, limits=operation.limits, cancel_event=cancel_event)

    def run(self):
        require(not self._used, "Execution is single-use; no automatic retry")
        self._used = True
        result = self.program.run()
        if not result.cell_exports:
            require(result.cancel_requested, "Unexpected empty session outcome")
            return None  # Native terminal still must authenticate cancellation/cleanup.
        require(len(result.cell_exports) == 1, "Bounded session dispatched more than one cell")
        export = result.cell_exports[0][1]
        policy_id = result.cell_exports[0][0]
        saved = read_raw_export(Path(result.root) / "exports" / (policy_id + ".json"),
            expected_bundle_sha256=export.bundle_sha256, expected_manifest_sha256=export.manifest_sha256)
        require(encode(saved) == export.bundle_raw and
                encode(journal._read(Path(result.root)/"results.json", MAX_REPORT_BYTES)) == result.report_raw,
                "Fresh export/report readback differs; retain output without adoption")
        archived = read_field_archive(Path(result.root)/"field-packets", expected_archive_sha256=result.archive_sha256,
            maximum_archive_bytes=self.operation.limits.archive_maximum_bytes)
        require(archived.snapshot == result.field_snapshot, "Fresh packet archive readback differs")
        bundle = decode(export.bundle_raw, MAX_EXPORT_BYTES, canonical=True)
        tail = replay_raw_bundle(bundle, expected_bundle_sha256=export.bundle_sha256,
            expected_manifest_sha256=export.manifest_sha256)
        if tail["records"] == 0:
            require(result.cancel_requested and tail["terminal"]["terminal"]["status"] == "cancelled",
                    "Zero-result output must remain an explicit pre-dispatch cancellation")
            return None
        output = SessionOutput(self.operation.operation_sha256, self.operation.output_root, export.bundle_raw,
            export.bundle_sha256, export.manifest_sha256, result.report_raw)
        output.inspect(self.operation)
        return output

    def snapshot(self):
        return self.program.snapshot()


def _require_continuation_provider(provider, expected_provider_sha256):
    require_provider(provider, expected_provider_sha256, (
        ("execute_owned_continuation", OriginalContinuationProvider.execute_owned_continuation),
        ("require_authenticated_continuation_and_cleanup", OriginalContinuationProvider.require_authenticated_continuation_and_cleanup),
    ))


class ContinuationExecution:
    """Actual append/export composition, only INSIDE renewed native writer admission.

    Native host authenticates owned_admission_raw before construction. Keeping
    the same enclosing original lease/deadline across dispatch and these writes
    is mandatory; child cleanup does not extend host write authority. Exceptions
    cause no more writes, no finally-finalization and no reuse of partial output.
    """
    def __init__(self, operation, *, provider, owned_admission_raw, owned_admission_sha256, cancel_event):
        require(type(operation) is ContinuationOperation and type(cancel_event) is Event, "Exact continuation/Event required")
        operation.validate()
        _require_continuation_provider(provider, operation.provider_sha256)
        require(type(owned_admission_raw) is bytes and 0 < len(owned_admission_raw) <= MAX_OWNED_RECEIPT_BYTES and
                is_sha256(owned_admission_sha256) and
                sha256(owned_admission_raw).hexdigest() == owned_admission_sha256, "Complete original outer admission bytes required")
        self.operation, self.provider, self.cancel = operation, provider, cancel_event
        self.admission, self.admission_pin = owned_admission_raw, owned_admission_sha256
        self._used, self.phase = False, "constructed"

    def run(self):
        require(not self._used, "Continuation consumed; partial output cannot be retried")
        self._used = True
        op = self.operation
        op.validate()
        _require_continuation_provider(self.provider, op.provider_sha256)
        require(not self.cancel.is_set(), "Cancelled before continuation; no dispatch")
        root = Path(op.output_root)
        self.phase = "create_outer_namespace"
        journal._no_alias(root)
        root.mkdir()
        journal._sync_directory(root.parent, op.sync_files)
        _write_raw(root / "request.json", op.request_raw, MAX_EXPORT_BYTES, op.sync_files)
        self.phase = "copy_and_verify_prefix"
        copied = copy_raw_prefix_in_owned_worker(root / "child", op.request_raw, op.predecessor.bundle_raw,
            op.historical_owned_receipts_raw, expected_continuation_sha256=op.continuation_sha256,
            owned_admission_raw=self.admission, expected_owned_admission_sha256=self.admission_pin,
            maximum_records=op.maximum_records, maximum_bytes=op.maximum_bytes, sync_files=op.sync_files)
        # Includes full admission-byte readback, not just the helper's returned pin.
        snapshot_raw_continuation_child(root / "child", op.predecessor.bundle_raw, op.historical_owned_receipts_raw,
            expected_ancestry_sha256=copied["ancestry_sha256"], expected_continuation_sha256=op.continuation_sha256)
        require(not self.cancel.is_set(), "Cancelled before dispatch; preserve unfinalized child")
        self.phase = "original_continuation_dispatch"
        result = dispatch_continuation(op.request_raw, op.predecessor.bundle_raw, op.historical_owned_receipts_raw,
            expected_continuation_sha256=op.continuation_sha256, expected_provider_sha256=op.provider_sha256, provider=self.provider)
        self.phase = "retain_returned_packet"
        for name, raw in (("chunk.json", result.raw_chunk_json), ("checkpoint.json", result.linked_checkpoint_json),
                          ("owned-receipts.bin", result.receipt_bundle_raw)):
            _write_raw(root / name, raw, MAX_EXPORT_BYTES, op.sync_files)
        store = journal.RawJournal(root / "child" / "journal", expected_manifest_sha256=copied["manifest_sha256"])
        self.phase = "append_and_readback"
        store.append(decode(result.raw_chunk_json, journal.MAX_CHUNK, canonical=True),
            decode(result.linked_checkpoint_json, journal.MAX_CHECKPOINT, canonical=True))
        checked = store.inspect()
        require(not checked["reconciliation_required"] and checked["terminal"] is None and
                encode(checked["journal_committed_tail"]["checkpoint"]) == result.linked_checkpoint_json,
                "Continuation tail differs; preserve partial output")
        status = decode(result.linked_checkpoint_json, journal.MAX_CHECKPOINT)["checkpoint"]["status"]
        terminal = "raw_completed" if status == "completed" else "failed" if status != "running" else "cancelled" if self.cancel.is_set() else "paused_budget"
        self.phase = "finalize_and_verify_export"
        terminal_receipt = store.write_terminal(terminal, "One explicit session continuation; no new admission or award")
        child = snapshot_raw_continuation_child(root / "child", op.predecessor.bundle_raw, op.historical_owned_receipts_raw,
            expected_ancestry_sha256=copied["ancestry_sha256"], expected_continuation_sha256=op.continuation_sha256)
        require(terminal_receipt is not None and child["summary"]["child_terminal"] == terminal_receipt and
                child["summary"]["new_raw_records"] == 1 and
                encode(child["summary"]["child_checkpoint"]) == result.linked_checkpoint_json,
                "Final terminal/checkpoint readback differs; no export published")
        bundle_raw = child["child_bundle_raw"]
        bundle = decode(bundle_raw, MAX_EXPORT_BYTES, canonical=True)
        write_raw_export(root / "export.json", bundle, expected_bundle_sha256=bundle["bundle_sha256"],
            expected_manifest_sha256=copied["manifest_sha256"], sync_files=op.sync_files)
        exported = read_raw_export(root / "export.json", expected_bundle_sha256=bundle["bundle_sha256"], expected_manifest_sha256=copied["manifest_sha256"])
        require(encode(exported) == bundle_raw, "Export readback differs")
        policy = bundle["bundle"]["manifest"]["identity"]["policy_id"]
        report = encode(summarize_tournament(op.plan_raw,
            {policy: RawCellExport(bundle_raw, bundle["bundle_sha256"], copied["manifest_sha256"])}, expected_plan_sha256=op.plan_sha256))
        _write_raw(root / "results.json", report, MAX_EXPORT_BYTES, op.sync_files)
        require(encode(journal._read(root / "results.json", MAX_EXPORT_BYTES)) == report, "Result readback differs")
        output = SessionOutput(op.operation_sha256, op.output_root, bundle_raw, bundle["bundle_sha256"],
            copied["manifest_sha256"], report, child["ancestry_raw"], child["owned_admission_raw"])
        output.inspect(op)
        self.phase = "finalized_raw_results"
        return output


def prepare_session_execution(operation, *, provider, cancel_event,
                              owned_admission_raw=None, owned_admission_sha256=None):
    """Fixed native-host factory: construct a real runner, never admit or run it.

    The native owner passes its actual reviewed provider and the host-local
    cancellation Event targeted by the handle's original Stop relay. A thread
    Event is not a cross-process cancellation transport. For continuation the
    owner must first authenticate the
    original renewed outer admission, and keep the original writer/lease/deadline
    through run(), storage verification and cleanup. These bytes/pins cannot
    establish that context. No context manager, lock, worker or provider is
    discovered/created, and no fallback or control-exception handler is supplied.
    Retain the returned execution before run(): FreshExecution.snapshot() is
    available after failure; ContinuationExecution.phase identifies its stage.
    Neither observation grants retry, recovery or terminal cleanup authority.
    """
    require(type(cancel_event) is Event, "Explicit original-host cancellation Event required")
    if type(operation) is FreshOperation:
        require(owned_admission_raw is None and owned_admission_sha256 is None,
                "Continuation admission arguments cannot be applied to a fresh operation")
        return FreshExecution(operation, provider=provider, cancel_event=cancel_event)
    require(type(operation) is ContinuationOperation, "Exact supported session operation required")
    return ContinuationExecution(operation, provider=provider, cancel_event=cancel_event,
        owned_admission_raw=owned_admission_raw, owned_admission_sha256=owned_admission_sha256)


@dataclass(frozen=True, slots=True)
class HostUpdate:
    operation_sha256: str
    sequence: int
    phase: str
    progress_ticks: int
    outcome: str | None = None  # returned / cancelled / timed_out / failed; native authentication required.
    output: SessionOutput | None = None
    terminal_evidence_raw: bytes = b""
    detail: str = ""
    paused_continuation_eligible: bool = False


class NativeSessionHost(Protocol):
    """Missing Windows binding, NOT implemented by this portable controller.

    launch(operation) returns a handle with operation_sha256, poll()->HostUpdate
    or None, and request_stop(reason). All three calls must return promptly.
    Launch must establish the actual original outer lease/Job/deadline topology;
    timeout_s is a proposal, never authority. Uncertain launch exceptions retain
    cleanup responsibility at the host. Terminal verification binds operation,
    source/input/environment, exact outputs, accounting, cancellation, stable
    process exit + empty Job + joined observers/readers before handle closure.
    It also authenticates paused_continuation_eligible: original historical
    lineage is eligible for proposing continuation, NOT a fresh execution grant.
    False is required if unavailable, unverified or not explicitly paused.
    Failure terminals need authentication too. Native FatalCreatorExit remains
    inside the lease; a Tk callback cannot implement it. No default host exists.
    """
    implementation_sha256: str

    @abstractmethod
    def launch(self, operation):
        raise NotImplementedError("Original native session launch is unavailable")

    @abstractmethod
    def require_authenticated_terminal(self, operation, update):
        raise NotImplementedError("Original native session terminal authentication is unavailable")


class SessionController:
    """Single UI-thread state machine; never marks cleanup from local time/flags."""
    def __init__(self, host, *, expected_host_sha256, clock=monotonic):
        require(host is not None and is_sha256(expected_host_sha256) and
                getattr(host, "implementation_sha256", None) == expected_host_sha256 and
                all(callable(getattr(host, name, None)) for name in ("launch", "require_authenticated_terminal")),
                "Reviewed real native session host required; no fallback")
        for name in ("launch", "require_authenticated_terminal"):
            method = getattr(host, name)
            require(getattr(method, "__func__", method) is not getattr(NativeSessionHost, name),
                    "Original native session host method is still a placeholder: " + name)
        self.host, self.clock = host, clock
        self.state, self.phase, self.detail = "idle", "idle", ""
        self.progress_ticks, self.output = 0, None
        self.operation = self.handle = None
        self._owner, self._sequence, self._deadline = get_ident(), -1, None
        self._operation_pin, self._maximum_progress_tick = None, 0
        self._used, self._roots, self._nonces, self._lineages = set(), set(), set(), set()
        self._stop_reason, self.close_requested, self.cleanup_verified = None, False, True
        self._continuation_eligible = False

    def _thread(self):
        require(get_ident() == self._owner, "Session control belongs to its UI thread")

    @property
    def active(self):
        return not self.cleanup_verified

    @property
    def can_continue(self):
        return self.state == "paused" and self.cleanup_verified and self._continuation_eligible and not self.close_requested and self._stop_reason is None

    @property
    def paused_continuation_eligible(self):
        return self.state == "paused" and self.cleanup_verified and self._continuation_eligible

    @property
    def stop_requested(self):
        return self._stop_reason

    @property
    def can_close(self):
        return self.cleanup_verified

    def start(self, operation):
        self._thread()
        require(not self.active and not self.close_requested, "Previous operation cleanup unproved or window closing")
        require(type(operation) in (FreshOperation, ContinuationOperation), "Exact session operation required")
        operation.validate()
        if type(operation) is ContinuationOperation:
            require(self.can_continue and operation.previous_operation is self.operation and operation.predecessor is self.output,
                    "Continue only this authenticated paused session, never failed/cancelled output")
            request = decode(operation.request_raw, MAX_EXPORT_BYTES)["continuation"]
            nonce = request["fresh_dispatch_request"]["request"]["request_nonce"]
            lineage = request["lineage_id"]
            require(lineage not in self._lineages, "Child lineage already consumed")
        else:
            nonce = decode(operation.request_raw, MAX_REQUEST_BYTES)["request"]["request_nonce"]
            lineage = None
        pin = operation.operation_sha256
        require(pin not in self._used and all(_disjoint(operation.output_root, root) for root in self._roots) and nonce not in self._nonces,
                "No operation, namespace or challenge retry")
        self._used.add(pin)
        self._roots.add(operation.output_root)
        self._nonces.add(nonce)
        if lineage is not None:
            self._lineages.add(lineage)
        self.operation, self.output = operation, None
        self._continuation_eligible = False
        self.handle = None
        self.state, self.phase, self.detail = "starting", "native_admission", ""
        self.cleanup_verified, self._stop_reason = False, None
        self.progress_ticks, self._sequence = 0, -1
        self._operation_pin = pin
        staged = decode(operation.request_raw, MAX_EXPORT_BYTES)
        if type(operation) is ContinuationOperation:
            staged = staged["continuation"]["fresh_dispatch_request"]
        plan = staged["request"]["chunk_plan"]["plan"]
        self._maximum_progress_tick = plan["start_tick"] + plan["maximum_new_ticks"]
        self._deadline = self.clock() + operation.timeout_s
        try:
            handle = self.host.launch(operation)
            require(getattr(handle, "operation_sha256", None) == pin and
                    all(callable(getattr(handle, n, None)) for n in ("poll", "request_stop")), "Native handle binding differs")
            self.handle = handle
        except BaseException:
            self.state, self.detail = "blocked", "Launch outcome/cleanup unconfirmed; native owner must reconcile"
            raise

    def stop(self, reason="user_stop"):
        self._thread()
        require(reason in ("user_stop", "window_close", "timeout"), "Explicit Stop reason required")
        if not self.active or self._stop_reason is not None:
            return
        self._stop_reason, self.state = reason, "stopping"
        self.detail = "Stop requested; waiting for authenticated owned cleanup"
        if self.handle is not None:
            try:
                self.handle.request_stop(reason)
            except BaseException:
                self.state = "blocked"
                raise

    def close(self):
        self._thread()
        self.close_requested = True
        self.stop("window_close")
        return self.can_close

    def poll(self):
        self._thread()
        if not self.active or self.handle is None:
            return
        try:
            if self.clock() >= self._deadline:
                self.stop("timeout")
            update = self.handle.poll()
            if update is None:
                return
            require(type(update) is HostUpdate, "Exact native update required")
            if update.operation_sha256 != self._operation_pin:
                return  # Stale event from a different operation cannot change current state.
            require(type(update.sequence) is int and update.sequence >= 0, "Monotonic update sequence required")
            if update.sequence <= self._sequence:
                return
            require(type(update.progress_ticks) is int and self.progress_ticks <= update.progress_ticks <= self._maximum_progress_tick and
                    update.phase in ("admitting", "running", "finalizing", "cleanup", "terminal") and
                    type(update.detail) is str and len(update.detail) <= 2048 and
                    type(update.paused_continuation_eligible) is bool, "Malformed/regressing current status")
            if update.outcome is None:
                require(update.phase != "terminal" and update.output is None and not update.terminal_evidence_raw and
                        not update.paused_continuation_eligible,
                        "Nonterminal update carried terminal data")
                self._sequence, self.progress_ticks = update.sequence, update.progress_ticks
                self.phase, self.detail = update.phase, update.detail
                if self._stop_reason is None:
                    self.state = "running" if update.phase != "cleanup" else "cleaning"
                return
            require(update.phase == "terminal" and update.outcome in ("returned", "cancelled", "timed_out", "failed") and
                    type(update.terminal_evidence_raw) is bytes and 0 < len(update.terminal_evidence_raw) <= MAX_OWNED_RECEIPT_BYTES,
                    "Complete native terminal/cleanup evidence required")
            require(update.output is None or type(update.output) is SessionOutput, "Exact immutable RAW session output required")
            tail = None if update.output is None else update.output.inspect(self.operation)
            require(update.outcome != "returned" or tail is not None, "Returned terminal missing finalized RAW output")
            require(not update.paused_continuation_eligible or
                    (update.outcome == "returned" and tail is not None and tail["terminal"]["terminal"]["status"] == "paused_budget"),
                    "Only an authenticated explicit paused result can propose continuation")
            require(self.host.require_authenticated_terminal(self.operation, update) is None,
                    "Native terminal verifier must raise on failure")
            self._sequence, self.progress_ticks = update.sequence, update.progress_ticks
            self.phase, self.detail = update.phase, update.detail
            # This point alone releases UI work/close controls. Preserve the
            # actual authenticated result, with a separate sticky Stop request.
            self.cleanup_verified, self.output = True, update.output
            self._continuation_eligible = update.paused_continuation_eligible
            if update.outcome != "returned":
                self.state = update.outcome
            else:
                status = tail["terminal"]["terminal"]["status"]
                self.state = {"paused_budget": "paused", "raw_completed": "completed", "cancelled": "cancelled", "failed": "failed"}[status]
        except BaseException:
            self.state = "blocked"
            raise
