"""UNTESTED explicit continuation proposal and fresh raw-prefix storage.

New interfaces, not recovered original admission/guard implementations. No
terminal journal is reopened, and no DTO or storage operation grants authority.
"""
from abc import abstractmethod
from hashlib import sha256
import os
from pathlib import Path
from typing import Protocol

from . import raw_journal as journal
from .raw_evidence import MAX_EXPORT_BYTES, replay_raw_bundle
from .dispatch_request import MAX_REQUEST_BYTES
from .guarded_dispatch import (NUMERICAL_BACKEND_FAMILY, MAX_OWNED_RECEIPT_BYTES,
                               OwnedChunkResult, bind_owned_result, require_owned_result_bytes,
                               require_provider, validate_staged_request)
from .input_contracts import decode, digest, encode, exact, is_sha256, require


SCHEMA = "lapsim.light-continuation.staged-request.v1"
ANCESTRY_SCHEMA = "lapsim.light-continuation.raw-child-ancestry.v1"
MAX_CONTINUATION_BYTES = 256 * 1024
MAX_HISTORY_BYTES = 64 * 1024 * 1024  # New opaque transport cap, not an original receipt format.


def _prepare(bundle_raw, staged_request_raw, historical_owned_receipts_raw, *,
             expected_bundle_sha256, expected_manifest_sha256, lineage_id):
    require(is_sha256(lineage_id), "Externally unique child-lineage identity required")
    require(type(historical_owned_receipts_raw) is bytes and
            0 < len(historical_owned_receipts_raw) <= MAX_HISTORY_BYTES,
            "Bounded complete historical owned evidence required")
    bundle = decode(bundle_raw, MAX_EXPORT_BYTES, canonical=True)
    tail = replay_raw_bundle(bundle, expected_bundle_sha256=expected_bundle_sha256,
                             expected_manifest_sha256=expected_manifest_sha256)
    terminal, checkpoint = tail["terminal"], tail["checkpoint"]
    require(terminal is not None and terminal["terminal"]["status"] == "paused_budget" and
            tail["records"] >= 1 and checkpoint["checkpoint"]["status"] == "running",
            "Only an explicit advanced paused-budget/running predecessor is proposed; no terminal state revival")
    staged = decode(staged_request_raw, MAX_REQUEST_BYTES, canonical=True)
    staged_body = validate_staged_request(staged_request_raw, encode(checkpoint),
                                          expected_request_sha256=staged["request_sha256"])
    require(staged_body["identity"] == bundle["bundle"]["manifest"]["identity"],
            "Continuation cannot change source, environment, fixture, course or policy")
    body = {
        "schema": SCHEMA, "operation": "continue_paused_budget", "lineage_id": lineage_id,
        "predecessor": {
            "bundle_sha256": expected_bundle_sha256, "export_raw_sha256": sha256(bundle_raw).hexdigest(),
            "manifest_sha256": expected_manifest_sha256,
            "terminal_sha256": terminal["terminal_sha256"],
            "last_storage_receipt_sha256": tail["receipt_sha256"],
            "checkpoint_sha256": checkpoint["checkpoint_sha256"],
            "context_sha256": checkpoint["checkpoint"]["context_sha256"],
            "records": tail["records"], "tick": checkpoint["checkpoint"]["tick"],
            "segment": checkpoint["checkpoint"]["segment"],
        },
        "historical_owned_receipts_sha256": sha256(historical_owned_receipts_raw).hexdigest(),
        "fresh_dispatch_request": staged,
        "child_storage": "NEW_OUTER_ANCESTRY_AND_INNER_V1_JOURNAL_WITH_COMPLETE_ORIGINAL_PREFIX",
        "status": "STAGED_CONTINUATION_REQUIRES_ORIGINAL_HISTORY_ADMISSION_AND_FRESH_GUARDS",
        "qualification_or_execution_authority": False,
    }
    value = {"continuation": body, "continuation_sha256": digest(body)}
    require(len(encode(value)) <= MAX_CONTINUATION_BYTES, "Continuation request exceeds bound")
    return value, bundle, tail, staged_body


def prepare_continuation_request(bundle_raw, staged_request_raw, historical_owned_receipts_raw, *,
                                 expected_bundle_sha256, expected_manifest_sha256, lineage_id):
    """Bind full immutable history to a fresh already input-bound proposal only."""
    return _prepare(bundle_raw, staged_request_raw, historical_owned_receipts_raw,
                    expected_bundle_sha256=expected_bundle_sha256,
                    expected_manifest_sha256=expected_manifest_sha256, lineage_id=lineage_id)[0]


def validate_continuation_request(request_raw, bundle_raw, historical_owned_receipts_raw, *,
                                  expected_continuation_sha256):
    """Rebuild all consistency bindings; this does not authenticate historical evidence."""
    request = decode(request_raw, MAX_CONTINUATION_BYTES, canonical=True)
    exact(request, {"continuation", "continuation_sha256"}, "continuation envelope")
    require(is_sha256(expected_continuation_sha256) and
            request["continuation_sha256"] == expected_continuation_sha256,
            "Externally pinned continuation request required")
    body = request["continuation"]
    rebuilt, bundle, tail, staged = _prepare(
        bundle_raw, encode(body["fresh_dispatch_request"]), historical_owned_receipts_raw,
        expected_bundle_sha256=body["predecessor"]["bundle_sha256"],
        expected_manifest_sha256=body["predecessor"]["manifest_sha256"], lineage_id=body["lineage_id"])
    require(encode(rebuilt) == request_raw, "Continuation request differs from complete predecessor/fresh proposal")
    return request, bundle, tail, staged


class OriginalContinuationProvider(Protocol):
    """A genuine integration must authenticate ALL history and explicit continuation.

    It must bind the outer request and historical evidence to real original
    execution/cleanup admission, consume the fresh challenge once, enforce every
    original live guard, allocate fresh finite resources and an owned new output
    namespace, preserve evidence, and clean up on all returns/exceptions. It may
    not reset numerical/segment/work state or mutate/reopen predecessor storage.
    No implementation or original evidence decoder is supplied here.
    Quarantined output remains a failed operation; retain its raw evidence and
    actual cleanup without promoting it to a continuation checkpoint/result.
    """

    implementation_sha256: str

    @abstractmethod
    def execute_owned_continuation(self, request_raw: bytes, bundle_raw: bytes,
                                   historical_owned_receipts_raw: bytes, *,
                                   numerical_backend_family: str) -> OwnedChunkResult:
        raise NotImplementedError("Original continuation admission/worker unavailable")

    @abstractmethod
    def require_authenticated_continuation_and_cleanup(self, request_raw: bytes,
                                                       bundle_raw: bytes,
                                                       historical_owned_receipts_raw: bytes,
                                                       result: OwnedChunkResult) -> None:
        raise NotImplementedError("Original continuation/cleanup receipt admission unavailable")


def dispatch_continuation(request_raw, bundle_raw, historical_owned_receipts_raw, *,
                          expected_continuation_sha256, expected_provider_sha256, provider=None):
    """Require genuine admission/ownership; return raw output without storage promotion."""
    require_provider(provider, expected_provider_sha256, (
        ("execute_owned_continuation", OriginalContinuationProvider.execute_owned_continuation),
        ("require_authenticated_continuation_and_cleanup",
         OriginalContinuationProvider.require_authenticated_continuation_and_cleanup),
    ))
    request, _, tail, staged = validate_continuation_request(
        request_raw, bundle_raw, historical_owned_receipts_raw,
        expected_continuation_sha256=expected_continuation_sha256)
    inner = request["continuation"]["fresh_dispatch_request"]
    result = provider.execute_owned_continuation(
        request_raw, bundle_raw, historical_owned_receipts_raw,
        numerical_backend_family=NUMERICAL_BACKEND_FAMILY)
    require_owned_result_bytes(result, staged, inner["request_sha256"])
    require(provider.require_authenticated_continuation_and_cleanup(
        request_raw, bundle_raw, historical_owned_receipts_raw, result) is None,
        "Original continuation receipt verifier must raise on failure")
    return bind_owned_result(encode(inner), encode(tail["checkpoint"]), result,
                             expected_request_sha256=inner["request_sha256"])


def copy_raw_prefix_in_owned_worker(root, request_raw, bundle_raw, historical_owned_receipts_raw, *,
                                    expected_continuation_sha256, owned_admission_raw,
                                    expected_owned_admission_sha256, maximum_records=750,
                                    maximum_bytes=256 * 1024 * 1024, sync_files=True):
    """Storage helper ONLY for the genuine owner's admitted exclusive allocation.

    This function checks raw consistency, not authority. The real provider must
    authenticate the supplied admission bytes before calling, own writer/path
    exclusion throughout, and preserve all partial files on failure. A caller
    cannot acquire permission by constructing these inputs. No numerical code
    is imported/called, and no copied historical result gains fresh credit.
    """
    request, bundle, tail, _ = validate_continuation_request(
        request_raw, bundle_raw, historical_owned_receipts_raw,
        expected_continuation_sha256=expected_continuation_sha256)
    require(type(owned_admission_raw) is bytes and 0 < len(owned_admission_raw) <= MAX_OWNED_RECEIPT_BYTES and
            is_sha256(expected_owned_admission_sha256) and
            sha256(owned_admission_raw).hexdigest() == expected_owned_admission_sha256,
            "Exact raw external admission evidence required; digest matching is not authentication")
    require(type(maximum_records) is int and tail["records"] < maximum_records <= journal.MAX_RECORDS and
            type(maximum_bytes) is int and 4 * 1024 * 1024 <= maximum_bytes <= 2**31 and
            type(sync_files) is bool, "Finite child bounds must include the copied prefix and a remaining slot")
    root = Path(root).absolute()
    journal._no_alias(root)
    root.mkdir()  # Never reuse an existing output directory or parent journal.
    journal._sync_directory(root.parent, sync_files)
    with (root / "owned-admission.bin").open("xb") as stream:
        stream.write(owned_admission_raw)
        stream.flush()
        if sync_files:
            os.fsync(stream.fileno())
    original = bundle["bundle"]
    store = journal.RawJournal.create(
        root / "journal", original["manifest"]["identity"], original["manifest"]["origin"],
        maximum_records=maximum_records, maximum_bytes=maximum_bytes, sync_files=sync_files)
    for record in original["records"]:
        receipt = record["receipt"]
        store.append(original["objects"][receipt["chunk_object_sha256"]],
                     original["objects"][receipt["checkpoint_object_sha256"]])
    state = store.inspect()
    child_tail = state["journal_committed_tail"]
    require(not state["reconciliation_required"] and state["terminal"] is None and
            child_tail["records"] == tail["records"] and
            encode(child_tail["checkpoint"]) == encode(tail["checkpoint"]),
            "Fresh child prefix differs; retain incomplete child for original-owner reconciliation")
    ancestry = {
        "schema": ANCESTRY_SCHEMA, "continuation": request,
        "external_owned_admission_sha256": expected_owned_admission_sha256,
        "child_manifest_sha256": store.expected_manifest_sha256,
        "copied_prefix_records": tail["records"], "copied_prefix_receipt_sha256": child_tail["receipt_sha256"],
        "copied_prefix_checkpoint_sha256": tail["checkpoint"]["checkpoint_sha256"],
        "history_credit": "COPIED_ORIGINAL_HISTORY_NOT_NEW_EXECUTION",
        "evidence_status": journal.RAW_LABEL, "qualification_or_execution_authority": False,
    }
    envelope = {"ancestry": ancestry, "ancestry_sha256": digest(ancestry)}
    journal._write_new(root / "ancestry.json", envelope, journal.MAX_MANIFEST, sync_files)
    return {"root": str(root), "manifest_sha256": store.expected_manifest_sha256,
            "ancestry_sha256": envelope["ancestry_sha256"],
            "checkpoint_sha256": tail["checkpoint"]["checkpoint_sha256"],
            "copied_prefix_records": tail["records"], "qualification_or_execution_authority": False}
