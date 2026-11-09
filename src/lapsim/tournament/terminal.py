"""Canonical terminal/failure DATA transport for the original native host.

No receipt issuer, trust root, exception loader or native evidence verifier is
provided. A caller can construct/hash every value here. Decoding never proves
host issuance, current outer-writer admission, process exit or cleanup.
"""
import base64
import binascii
from dataclasses import dataclass
from hashlib import sha256

from lapsim_light_campaign import raw_journal as journal
from lapsim_light_campaign.guarded_dispatch import MAX_OWNED_RECEIPT_BYTES
from lapsim_light_campaign.input_contracts import decode, digest, encode, exact, is_sha256, require
from lapsim_light_campaign.raw_evidence import MAX_EXPORT_BYTES
from lapsim_light_campaign.tournament_results import MAX_REPORT_BYTES

from .session import ContinuationOperation, FreshOperation, HostUpdate, SessionOutput


SCHEMA = "lapsim.light-session.terminal-data.v1"
FAILURE_SCHEMA = "lapsim.light-session.failure-data.v1"
MAX_TERMINAL_BYTES = 128 * 1024 * 1024
SCOPE = "DATA_REQUIRES_ORIGINAL_HOST_ISSUANCE_ADMISSION_AND_CLEANUP_AUTHENTICATION"


def _text(value, maximum, label):
    require(type(value) is str and len(value) <= maximum and "\x00" not in value, "Bounded " + label + " required")


def _raw(value, maximum, *, empty=False):
    require(type(value) is bytes and (empty or len(value) > 0) and len(value) <= maximum,
            "Bounded complete immutable transport bytes required")
    return base64.b64encode(value).decode("ascii")


def _unraw(value, maximum, *, empty=False):
    require(type(value) is str and len(value) <= 4*((maximum+2)//3), "Bounded base64 field required")
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("Invalid base64 transport bytes") from error
    require(_raw(raw, maximum, empty=empty) == value, "Canonical base64 bytes required")
    return raw


@dataclass(frozen=True, slots=True)
class SessionFailureData:
    """Diagnostic values only; never a serialized exception or cleanup proof."""
    stage: str
    category: str
    exception_type: str
    message: str
    output_root: str

    def body(self, operation):
        _text(self.stage, 128, "failure stage")
        _text(self.exception_type, 256, "exception type name")
        _text(self.message, 2048, "failure message")
        require(self.stage and self.exception_type and self.category in
                ("admission", "execution", "storage", "control", "verification"), "Explicit failure category/stage/type required")
        require(self.output_root == operation.output_root, "Failure output namespace changed")
        return {"schema": FAILURE_SCHEMA, "stage": self.stage, "category": self.category,
            "exception_type": self.exception_type, "message": self.message, "output_root": self.output_root,
            "qualification_or_execution_authority": False}


@dataclass(frozen=True, slots=True)
class DecodedTerminalData:
    """No authority. The host must authenticate THESE original issued bytes."""
    raw: bytes
    raw_sha256: str
    record_sha256: str
    update: HostUpdate
    failure: SessionFailureData | None

    @property
    def qualification_or_execution_authority(self):
        return False


def _validate_update(operation, update):
    require(type(operation) in (FreshOperation, ContinuationOperation) and type(update) is HostUpdate,
            "Exact operation and terminal data required")
    operation.validate()
    require(update.operation_sha256 == operation.operation_sha256 and update.phase == "terminal" and
            type(update.sequence) is int and update.sequence >= 0 and
            update.outcome in ("returned", "cancelled", "timed_out", "failed"), "Terminal operation/sequence/outcome differs")
    staged = decode(operation.request_raw, MAX_TERMINAL_BYTES, canonical=True)
    if type(operation) is ContinuationOperation:
        staged = staged["continuation"]["fresh_dispatch_request"]
    ceiling = staged["request"]["chunk_plan"]["plan"]["end_tick_ceiling"]
    require(type(update.progress_ticks) is int and 0 <= update.progress_ticks <= ceiling,
            "Terminal progress exceeds staged request")
    _text(update.detail, 2048, "terminal detail")
    require(type(update.paused_continuation_eligible) is bool and
            (update.output is None or type(update.output) is SessionOutput), "Exact eligibility/output types required")
    tail = None if update.output is None else update.output.inspect(operation)
    require(update.outcome != "returned" or tail is not None, "Returned terminal needs finalized output")
    require(not update.paused_continuation_eligible or
            (update.outcome == "returned" and tail is not None and tail["terminal"]["terminal"]["status"] == "paused_budget"),
            "Only an explicit paused result can claim proposal eligibility")
    _raw(update.terminal_evidence_raw, MAX_OWNED_RECEIPT_BYTES)


def _output_body(output):
    if output is None:
        return None
    return {"operation_sha256": output.operation_sha256, "output_root": output.output_root,
        "bundle_b64": _raw(output.bundle_raw, MAX_EXPORT_BYTES), "bundle_sha256": output.bundle_sha256,
        "manifest_sha256": output.manifest_sha256, "report_b64": _raw(output.report_raw, MAX_REPORT_BYTES),
        "ancestry_b64": _raw(output.ancestry_raw, journal.MAX_MANIFEST, empty=True),
        "owned_admission_b64": _raw(output.owned_admission_raw, MAX_OWNED_RECEIPT_BYTES, empty=True)}


def encode_terminal_record(operation, update, *, failure=None):
    """Encode exact consistency-bound data, never sign/issue/authenticate it.

    Failed outcomes require structured diagnostics. Native fatal exceptions and
    unproved cleanup must follow original creator-fatal control flow; they cannot
    be converted into a normal cleaned terminal by constructing this envelope.
    """
    _validate_update(operation, update)
    require((update.outcome == "failed" and type(failure) is SessionFailureData) or
            (update.outcome != "failed" and failure is None), "Failed terminal needs exact failure data; other outcomes cannot carry it")
    body = {"schema": SCHEMA, "scope": SCOPE, "qualification_or_execution_authority": False,
        "operation_sha256": update.operation_sha256, "sequence": update.sequence,
        "phase": update.phase, "progress_ticks": update.progress_ticks, "outcome": update.outcome,
        "detail": update.detail, "paused_continuation_eligible": update.paused_continuation_eligible,
        "output": _output_body(update.output), "failure": None if failure is None else failure.body(operation),
        "original_evidence_b64": _raw(update.terminal_evidence_raw, MAX_OWNED_RECEIPT_BYTES)}
    raw = encode({"terminal_record": body, "record_sha256": digest(body)})
    require(len(raw) <= MAX_TERMINAL_BYTES, "Terminal data exceeds transport bound")
    return raw


def decode_terminal_record(raw, *, operation, expected_raw_sha256):
    """Decode pinned raw data without granting its claimed provenance/authority.

    expected_raw_sha256 must come from the real host's retained issued record.
    An arbitrary caller can supply a matching hash too: the real native verifier
    must separately correlate this record with its current handle/attempt journal,
    authenticated outer admission, original execution evidence and proved cleanup.
    It must bind the eligibility claim as well. Never authorize Close/Continue or
    manufacture a native receipt based on this function returning successfully.
    """
    require(type(raw) is bytes and 0 < len(raw) <= MAX_TERMINAL_BYTES and is_sha256(expected_raw_sha256) and
            sha256(raw).hexdigest() == expected_raw_sha256, "Externally pinned complete terminal bytes required")
    value = decode(raw, MAX_TERMINAL_BYTES, canonical=True)
    exact(value, {"terminal_record", "record_sha256"}, "terminal data envelope")
    body = value["terminal_record"]
    exact(body, {"schema", "scope", "qualification_or_execution_authority", "operation_sha256", "sequence", "phase",
        "progress_ticks", "outcome", "detail", "paused_continuation_eligible", "output", "failure", "original_evidence_b64"}, "terminal data")
    require(body["schema"] == SCHEMA and body["scope"] == SCOPE and body["qualification_or_execution_authority"] is False and
            is_sha256(value["record_sha256"]) and digest(body) == value["record_sha256"], "Terminal schema/scope/digest differs")
    failure = None
    if body["failure"] is not None:
        item = body["failure"]
        exact(item, {"schema", "stage", "category", "exception_type", "message", "output_root", "qualification_or_execution_authority"}, "failure data")
        require(item["schema"] == FAILURE_SCHEMA and item["qualification_or_execution_authority"] is False, "Failure data cannot claim authority")
        failure = SessionFailureData(item["stage"], item["category"], item["exception_type"], item["message"], item["output_root"])
    output = None
    if body["output"] is not None:
        item = body["output"]
        exact(item, {"operation_sha256", "output_root", "bundle_b64", "bundle_sha256", "manifest_sha256", "report_b64",
            "ancestry_b64", "owned_admission_b64"}, "terminal RAW output")
        output = SessionOutput(item["operation_sha256"], item["output_root"], _unraw(item["bundle_b64"], MAX_EXPORT_BYTES),
            item["bundle_sha256"], item["manifest_sha256"], _unraw(item["report_b64"], MAX_REPORT_BYTES),
            _unraw(item["ancestry_b64"], journal.MAX_MANIFEST, empty=True),
            _unraw(item["owned_admission_b64"], MAX_OWNED_RECEIPT_BYTES, empty=True))
    update = HostUpdate(body["operation_sha256"], body["sequence"], body["phase"], body["progress_ticks"], body["outcome"],
        output, _unraw(body["original_evidence_b64"], MAX_OWNED_RECEIPT_BYTES), body["detail"], body["paused_continuation_eligible"])
    # Rebuild to enforce all current operation/output/failure consistency checks
    # and reject a noncanonical alternate representation, without native calls.
    require(encode_terminal_record(operation, update, failure=failure) == raw, "Terminal data differs from exact canonical representation")
    return DecodedTerminalData(raw, expected_raw_sha256, value["record_sha256"], update, failure)
