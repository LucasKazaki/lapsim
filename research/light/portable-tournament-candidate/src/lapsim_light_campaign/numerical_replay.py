"""UNTESTED exact-request replay source and genuine-provider boundary.

No automatic replay, registration or fallback. Numerical imports occur only in
the explicit owned-worker helper; calling that helper still requires a real
external admitted allocation. No historical callback behavior is reconstructed.
"""
from abc import abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from . import raw_journal as journal
from .continuation import MAX_HISTORY_BYTES
from .dispatch_request import MAX_REQUEST_BYTES
from .guarded_dispatch import (MAX_OWNED_RECEIPT_BYTES, NUMERICAL_BACKEND_FAMILY,
                               require_provider, validate_staged_request)
from .input_contracts import decode, digest, encode, exact, is_sha256, require
from .raw_evidence import MAX_EXPORT_BYTES, replay_raw_bundle
from .raw_failures import RawOutputQuarantined
from .stepping import require_committed_work_transition, require_clocked_counter_transition


SCHEMA = "lapsim.light-exact-numerical-replay.staged-request.v1"
REPORT_SCHEMA = "lapsim.light-exact-numerical-replay.raw-report.v1"
MAX_REPLAY_REQUEST_BYTES = 1024 * 1024
MAX_ORIGINAL_REQUEST_BYTES = 16 * 1024 * 1024
MAX_REPORT_BYTES = 3 * 1024 * 1024


def _prepare(bundle_raw, original_requests_raw, fresh_input_request_raw, historical_owned_receipts_raw, *,
             expected_bundle_sha256, expected_manifest_sha256):
    bundle = decode(bundle_raw, MAX_EXPORT_BYTES, canonical=True)
    tail = replay_raw_bundle(bundle, expected_bundle_sha256=expected_bundle_sha256,
                             expected_manifest_sha256=expected_manifest_sha256)
    body = bundle["bundle"]
    require(type(original_requests_raw) is tuple and len(original_requests_raw) == tail["records"] and
            1 <= len(original_requests_raw) <= journal.MAX_RECORDS and
            all(type(raw) is bytes and 0 < len(raw) <= MAX_REQUEST_BYTES for raw in original_requests_raw) and
            sum(map(len, original_requests_raw)) <= MAX_ORIGINAL_REQUEST_BYTES,
            "Complete bounded original request sequence required; end ticks cannot substitute")
    require(type(historical_owned_receipts_raw) is bytes and
            0 < len(historical_owned_receipts_raw) <= MAX_HISTORY_BYTES,
            "Bounded complete original execution/cleanup evidence required")
    origin = body["manifest"]["origin"]
    fresh = decode(fresh_input_request_raw, MAX_REQUEST_BYTES, canonical=True)
    fresh_body = validate_staged_request(fresh_input_request_raw, encode(origin),
                                         expected_request_sha256=fresh["request_sha256"])
    require(fresh_body["identity"] == body["manifest"]["identity"] and
            fresh_body["chunk_plan"]["plan"]["requested_ticks"] == 1,
            "Fresh one-tick origin input-review proposal required; this is NOT the replay work permit")
    prior, declarations, plans, nonces = origin, [], [], {fresh_body["request_nonce"]}
    for sequence, (record, raw) in enumerate(zip(body["records"], original_requests_raw), 1):
        receipt = record["receipt"]
        chunk = body["objects"][receipt["chunk_object_sha256"]]
        linked = body["objects"][receipt["checkpoint_object_sha256"]]
        request = decode(raw, MAX_REQUEST_BYTES, canonical=True)
        original = validate_staged_request(raw, encode(prior), expected_request_sha256=request["request_sha256"])
        plan = original["chunk_plan"]["plan"]
        require(original["identity"] == fresh_body["identity"] and original["request_nonce"] not in nonces,
                "Every original request and the fresh replay challenge must be distinct and input-identical")
        nonces.add(original["request_nonce"])
        require(chunk["chunk"]["end_tick"] <= plan["end_tick_ceiling"],
                "Original output exceeds its recorded request")
        before = prior["checkpoint"]["state"]["thermal"]["light"]["powered"]
        after = linked["checkpoint"]["state"]["thermal"]["light"]["powered"]
        require_committed_work_transition(before, after, start_tick=chunk["chunk"]["start_tick"],
            end_tick=chunk["chunk"]["end_tick"], maximum_new_work=plan["maximum_new_work"])
        require_clocked_counter_transition(prior["checkpoint"]["memory"], linked["checkpoint"]["memory"],
            start_tick=chunk["chunk"]["start_tick"], end_tick=chunk["chunk"]["end_tick"])
        declarations.append({"sequence": sequence, "original_request_sha256": request["request_sha256"],
                             "original_request_raw_sha256": sha256(raw).hexdigest(),
                             "chunk_sha256": chunk["chunk_sha256"],
                             "checkpoint_sha256": linked["checkpoint_sha256"],
                             "requested_ticks": plan["requested_ticks"]})
        plans.append(plan)
        prior = linked
    proposal = {
        "schema": SCHEMA, "operation": "exact_numerical_replay", "bundle_sha256": expected_bundle_sha256,
        "export_raw_sha256": sha256(bundle_raw).hexdigest(), "manifest_sha256": expected_manifest_sha256,
        "historical_owned_receipts_sha256": sha256(historical_owned_receipts_raw).hexdigest(),
        "fresh_input_review_request": fresh, "records": declarations,
        "work_request": {"chunks": len(plans), "sum_requested_ticks": sum(p["requested_ticks"] for p in plans),
                         "sum_chunk_work_ceilings": sum(p["maximum_new_work"] for p in plans),
                         "scope": "FINITE_CONSERVATIVE_REQUEST_BOUNDS_NOT_MEASURED_COST_OR_NEW_MISSION_LIMITS"},
        "comparison": "WHOLE_CANONICAL_CHUNKS_AND_LINKED_CHECKPOINTS_EXACT_BYTES_NO_TOLERANCE",
        "status": "STAGED_REPLAY_REQUIRES_ORIGINAL_HISTORY_ADMISSION_AND_FRESH_GUARDS",
        "qualification_or_execution_authority": False,
    }
    value = {"replay": proposal, "replay_sha256": digest(proposal)}
    require(len(encode(value)) <= MAX_REPLAY_REQUEST_BYTES, "Replay request exceeds bound")
    return value, bundle, plans


def prepare_numerical_replay_request(bundle_raw, original_requests_raw, fresh_input_request_raw,
                                     historical_owned_receipts_raw, *, expected_bundle_sha256,
                                     expected_manifest_sha256):
    """Bind original v2 no-callback requests; no numeric work or authentication."""
    return _prepare(bundle_raw, original_requests_raw, fresh_input_request_raw, historical_owned_receipts_raw,
                    expected_bundle_sha256=expected_bundle_sha256,
                    expected_manifest_sha256=expected_manifest_sha256)[0]


def validate_numerical_replay_request(request_raw, bundle_raw, original_requests_raw,
                                      historical_owned_receipts_raw, *, expected_replay_sha256):
    value = decode(request_raw, MAX_REPLAY_REQUEST_BYTES, canonical=True)
    exact(value, {"replay", "replay_sha256"}, "numerical replay envelope")
    require(is_sha256(expected_replay_sha256) and value["replay_sha256"] == expected_replay_sha256,
            "Externally pinned replay request required")
    body = value["replay"]
    rebuilt, bundle, plans = _prepare(
        bundle_raw, original_requests_raw, encode(body["fresh_input_review_request"]), historical_owned_receipts_raw,
        expected_bundle_sha256=body["bundle_sha256"], expected_manifest_sha256=body["manifest_sha256"])
    require(encode(rebuilt) == request_raw, "Replay proposal differs from exact original request/input inventory")
    return value, bundle, plans


def replay_in_owned_worker(request_raw, bundle_raw, original_requests_raw, historical_owned_receipts_raw, *,
                            expected_replay_sha256, bridge):
    """Actual replay helper ONLY inside a genuinely admitted/exclusive owned worker.

    The original provider must authenticate all inputs and own fresh guards,
    finite resources, deadline, watchdog, raw exception/crash preservation and
    cleanup. This library helper is NOT an enforceable resource boundary.
    It stops at the first divergence, retaining that entire generated raw output.
    """
    value, bundle, plans = validate_numerical_replay_request(
        request_raw, bundle_raw, original_requests_raw, historical_owned_receipts_raw,
        expected_replay_sha256=expected_replay_sha256)
    from .numerical_bridge import NumericalBridge, checkpoint

    require(type(bridge) is NumericalBridge, "Exact reviewed numerical bridge required; no callback backend")
    body = bundle["bundle"]
    identity = body["manifest"]["identity"]
    require(bridge.identity == identity, "Replay bridge input/source/environment identity differs")
    source = identity["source_sha256"]
    origin = body["manifest"]["origin"]
    context = origin["checkpoint"]["context"]
    session = bridge.initialize(context["course"]["id"], identity["policy_id"], context["mode"],
                                expected_source_sha256=source)
    generated_origin = checkpoint(session)
    origin_equal = encode(generated_origin) == encode(origin)
    report = {
        "schema": REPORT_SCHEMA, "replay_request_sha256": expected_replay_sha256,
        "source_sha256": source, "records_total": len(plans), "records_compared": 0,
        "origin": {"expected_checkpoint_sha256": origin["checkpoint_sha256"],
                   "generated_checkpoint_sha256": generated_origin["checkpoint_sha256"], "identical": origin_equal},
        "comparison": "identical" if origin_equal else "mismatch",
        "comparisons": [], "divergent_origin": None if origin_equal else generated_origin,
        "divergent_chunk": None, "divergent_checkpoint": None,
        "numerical_replay_performed": True, "campaign_eligible": False,
        "qualification_or_execution_authority": False,
    }
    if origin_equal:
        for sequence, (record, plan) in enumerate(zip(body["records"], plans), 1):
            receipt = record["receipt"]
            expected_chunk = body["objects"][receipt["chunk_object_sha256"]]
            expected_linked = body["objects"][receipt["checkpoint_object_sha256"]]
            before = checkpoint(session)
            generated = bridge.advance_chunk(session, ticks=plan["requested_ticks"],
                                              expected_source_sha256=source, progress_callback=None)
            linked = deepcopy(generated["chunk"]["output_checkpoint"])
            linked["checkpoint"]["parent_chunk_sha256"] = generated["chunk_sha256"]
            linked["checkpoint_sha256"] = digest(linked["checkpoint"])
            same = encode(generated) == encode(expected_chunk) and encode(linked) == encode(expected_linked)
            report["comparisons"].append({
                "sequence": sequence, "expected_chunk_sha256": expected_chunk["chunk_sha256"],
                "generated_chunk_sha256": generated["chunk_sha256"],
                "expected_checkpoint_sha256": expected_linked["checkpoint_sha256"],
                "generated_checkpoint_sha256": linked["checkpoint_sha256"], "identical": same})
            report["records_compared"] = sequence
            if not same:
                report.update(comparison="mismatch", divergent_chunk=generated, divergent_checkpoint=linked)
                break
            session = bridge.accept_chunk(generated, expected_input_checkpoint=before,
                                            expected_source_sha256=source)
    require(len(encode(report)) <= MAX_REPORT_BYTES, "Replay report exceeds bound; preserve raw evidence externally")
    try:
        require(bridge.source_identity()["sha256"] == source, "Replay source drift; do not admit this report")
    except Exception as error:
        raise RawOutputQuarantined(artifact_kind="raw_replay_report", artifact=report,
                                   expected_source_sha256=source, error=error) from error
    return report


@dataclass(frozen=True, slots=True)
class OwnedReplayResult:
    replay_request_sha256: str
    source_sha256: str
    report_raw: bytes
    receipt_bundle_raw: bytes
    receipt_bundle_sha256: str

    @property
    def qualification_or_execution_authority(self):
        return False


class OriginalReplayProvider(Protocol):
    """No implementation supplied: original history admission and full owned lifecycle.

    Authenticate the outer request, exact original requests/receipts and inputs,
    consume ONLY the fresh replay challenge (never reuse historical resources),
    own all original guards, allocation/deadline/watchdog and raw/failing evidence,
    call the fixed replay helper in that worker and clean up on every outcome.
    A replay of an invalid result remains invalid historical development data.
    Preserve RawOutputQuarantined.evidence_raw on cooperative source-gate
    failure, finish owned cleanup, and propagate failure rather than admitting
    its nested chunk/report as a successful replay.
    """

    implementation_sha256: str

    @abstractmethod
    def execute_owned_replay(self, request_raw: bytes, bundle_raw: bytes,
                             original_requests_raw: tuple, historical_owned_receipts_raw: bytes, *,
                             numerical_backend_family: str) -> OwnedReplayResult:
        raise NotImplementedError("Original replay worker/guard integration unavailable")

    @abstractmethod
    def require_authenticated_replay_and_cleanup(self, request_raw: bytes, bundle_raw: bytes,
                                                 original_requests_raw: tuple,
                                                 historical_owned_receipts_raw: bytes,
                                                 result: OwnedReplayResult) -> None:
        raise NotImplementedError("Original replay/cleanup receipt admission unavailable")


def _require_report(report, request, bundle):
    exact(report, {"schema", "replay_request_sha256", "source_sha256", "records_total", "records_compared",
                   "origin", "comparison", "comparisons", "divergent_origin", "divergent_chunk",
                   "divergent_checkpoint", "numerical_replay_performed", "campaign_eligible",
                   "qualification_or_execution_authority"}, "raw replay report")
    body, original = request["replay"], bundle["bundle"]
    require(report["schema"] == REPORT_SCHEMA and report["replay_request_sha256"] == request["replay_sha256"] and
            report["source_sha256"] == original["manifest"]["identity"]["source_sha256"] and
            type(report["records_total"]) is int and report["records_total"] == len(body["records"]) and
            type(report["records_compared"]) is int and 0 <= report["records_compared"] <= report["records_total"] and
            report["numerical_replay_performed"] is True and report["campaign_eligible"] is False and
            report["qualification_or_execution_authority"] is False and report["comparison"] in {"identical", "mismatch"},
            "Replay report identity or scope differs")
    origin = report["origin"]
    exact(origin, {"expected_checkpoint_sha256", "generated_checkpoint_sha256", "identical"}, "origin comparison")
    require(origin["expected_checkpoint_sha256"] == original["manifest"]["origin"]["checkpoint_sha256"] and
            is_sha256(origin["generated_checkpoint_sha256"]) and type(origin["identical"]) is bool and
            origin["identical"] == (origin["expected_checkpoint_sha256"] == origin["generated_checkpoint_sha256"]),
            "Replay origin comparison differs")
    rows = report["comparisons"]
    require(type(rows) is list and len(rows) == report["records_compared"], "Replay comparison inventory differs")
    for sequence, row in enumerate(rows, 1):
        exact(row, {"sequence", "expected_chunk_sha256", "generated_chunk_sha256", "expected_checkpoint_sha256",
                    "generated_checkpoint_sha256", "identical"}, "chunk comparison")
        declared = body["records"][sequence - 1]
        require(type(row["sequence"]) is int and row["sequence"] == sequence and
                row["expected_chunk_sha256"] == declared["chunk_sha256"] and
                row["expected_checkpoint_sha256"] == declared["checkpoint_sha256"] and
                is_sha256(row["generated_chunk_sha256"]) and is_sha256(row["generated_checkpoint_sha256"]) and
                type(row["identical"]) is bool and row["identical"] ==
                (row["expected_chunk_sha256"] == row["generated_chunk_sha256"] and
                 row["expected_checkpoint_sha256"] == row["generated_checkpoint_sha256"]),
                "Replay chunk comparison differs")
    if report["comparison"] == "identical":
        require(origin["identical"] and len(rows) == len(body["records"]) and all(row["identical"] for row in rows) and
                all(report[name] is None for name in ("divergent_origin", "divergent_chunk", "divergent_checkpoint")),
                "Identical replay must cover the entire exact sequence")
    elif not origin["identical"]:
        require(not rows and report["divergent_chunk"] is None and report["divergent_checkpoint"] is None and
                report["divergent_origin"]["checkpoint_sha256"] == origin["generated_checkpoint_sha256"],
                "Origin mismatch must retain exactly its generated origin")
        journal._checkpoint(report["divergent_origin"])
    else:
        require(rows and all(row["identical"] for row in rows[:-1]) and not rows[-1]["identical"] and
                report["divergent_origin"] is None, "Replay must stop at its first divergent chunk")
        chunk, linked = report["divergent_chunk"], report["divergent_checkpoint"]
        exact(chunk, {"chunk", "chunk_sha256"}, "divergent raw chunk")
        require(chunk["chunk_sha256"] == digest(chunk["chunk"]) == rows[-1]["generated_chunk_sha256"] and
                linked["checkpoint_sha256"] == rows[-1]["generated_checkpoint_sha256"] and
                len(encode(chunk)) <= journal.MAX_CHUNK, "Divergent replay output bytes differ")
        prior = original["manifest"]["origin"] if len(rows) == 1 else original["objects"][
            original["records"][len(rows) - 2]["receipt"]["checkpoint_object_sha256"]]
        journal._transition(prior, chunk, linked, original["manifest"]["identity"])


def dispatch_numerical_replay(request_raw, bundle_raw, original_requests_raw, historical_owned_receipts_raw, *,
                               expected_replay_sha256, expected_provider_sha256, provider=None):
    """Require real original replay/cleanup admission; do no numerical work locally."""
    require_provider(provider, expected_provider_sha256, (
        ("execute_owned_replay", OriginalReplayProvider.execute_owned_replay),
        ("require_authenticated_replay_and_cleanup", OriginalReplayProvider.require_authenticated_replay_and_cleanup),
    ))
    request, bundle, _ = validate_numerical_replay_request(
        request_raw, bundle_raw, original_requests_raw, historical_owned_receipts_raw,
        expected_replay_sha256=expected_replay_sha256)
    result = provider.execute_owned_replay(
        request_raw, bundle_raw, original_requests_raw, historical_owned_receipts_raw,
        numerical_backend_family=NUMERICAL_BACKEND_FAMILY)
    require(type(result) is OwnedReplayResult and result.replay_request_sha256 == expected_replay_sha256 and
            result.source_sha256 == bundle["bundle"]["manifest"]["identity"]["source_sha256"] and
            type(result.report_raw) is bytes and 0 < len(result.report_raw) <= MAX_REPORT_BYTES and
            type(result.receipt_bundle_raw) is bytes and 0 < len(result.receipt_bundle_raw) <= MAX_OWNED_RECEIPT_BYTES and
            is_sha256(result.receipt_bundle_sha256) and sha256(result.receipt_bundle_raw).hexdigest() == result.receipt_bundle_sha256,
            "Bounded complete original-owned replay result/evidence required")
    require(provider.require_authenticated_replay_and_cleanup(
        request_raw, bundle_raw, original_requests_raw, historical_owned_receipts_raw, result) is None,
        "Original replay receipt verifier must raise on failure")
    _require_report(decode(result.report_raw, MAX_REPORT_BYTES, canonical=True), request, bundle)
    return result
