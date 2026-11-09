"""UNTESTED adapter boundary for a genuine original-owner guard provider.

This is a NEW interface, not a recovered original API implementation. No real
provider is installed/registered here. There is no fallback execution path,
local lease, watchdog, process launch, device operation or permission override.
No numerical module is imported by this metadata/receipt binding layer.
"""
from dataclasses import dataclass
from abc import abstractmethod
from hashlib import sha256
from typing import Protocol

from . import raw_journal as journal
from .dispatch_request import SCHEMA, MAX_REQUEST_BYTES, REQUIRED_RUNTIME_SERVICES, NUMERICAL_ENTRYPOINT
from .input_contracts import decode, digest, encode, exact, is_sha256, require
from .stepping import (plan_chunk, require_committed_work_transition,
                       require_clocked_counter_transition)


NUMERICAL_BACKEND_FAMILY = "lapsim.portable-awd-standing-numerical-bridge.v1"
MAX_OWNED_RECEIPT_BYTES = 8 * 1024 * 1024  # New transport cap, not an original receipt-format claim.
_REQUEST_FIELDS = frozenset({
    "schema", "mode", "identity", "request_nonce", "prepared_at_unix_s", "numerical_entrypoint",
    "input_admission_expires_at_unix_s", "authority_key_id", "authority_public_key_sha256",
    "chunk_plan", "input_admissions", "resource_request", "required_external_runtime_services",
    "status", "qualification_or_execution_authority", "provider_registration_performed",
    "runtime_guards_performed", "runtime_probe_performed", "full_checkpoint_validation_performed",
    "numerical_step_performed", "retry_or_continuation_authority",
})


class GuardProviderUnavailable(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OwnedChunkResult:
    """Raw transport, never a capability or automatic campaign admission."""

    request_sha256: str
    source_sha256: str
    raw_chunk_json: bytes
    linked_checkpoint_json: bytes
    receipt_bundle_raw: bytes
    receipt_bundle_sha256: str

    @property
    def qualification_or_execution_authority(self):
        return False


class OriginalGuardProvider(Protocol):
    """Trusted external bootstrap supplies a reviewed REAL original integration.

    The implementation must reauthenticate inputs; check exact loaded source,
    runtime and complete checkpoint/reference; consume the fresh challenge;
    perform original activity/session/game/memory checks; own the exclusive
    writer/resource lease, finite allocation, deadline and external watchdog;
    run and validate the fixed numerical backend with progress_callback=None
    in its owned worker; durably
    retain raw/partial/failing evidence; and complete owned cleanup on every
    success/failure path before returning or raising. An identity attribute is
    not proof of that provenance or behavior. No such implementation is supplied.

    RawOutputQuarantined is a failed operation: preserve its evidence_raw under
    the genuine owned controls and finish cleanup before propagating failure.
    Never turn its nested raw artifact into a successful owned result/admission.
    """

    implementation_sha256: str

    @abstractmethod
    def execute_owned_request(self, request_raw: bytes, checkpoint_raw: bytes,
                              *, numerical_backend_family: str) -> OwnedChunkResult:
        raise NotImplementedError("Original guarded owned-worker integration is unavailable")

    @abstractmethod
    def require_authenticated_owned_execution_and_cleanup(self, request_raw: bytes,
                                                           result: OwnedChunkResult) -> None:
        """Authenticate exact source/request/output/tool/cleanup receipts; raise on failure.

        This must use actual supported original evidence, not local pass flags.
        No numerical work or replacement resource probing belongs in this callback.
        """
        raise NotImplementedError("Original owned execution/cleanup receipt admission is unavailable")


def require_provider(provider, expected_provider_sha256, methods):
    """Reject absent/known incomplete integrations before any owned work."""
    if provider is None:
        raise GuardProviderUnavailable("Original guard provider unavailable; no owned work performed")
    require(is_sha256(expected_provider_sha256) and
            getattr(provider, "implementation_sha256", None) == expected_provider_sha256,
            "Externally reviewed original-provider pin required")
    for name, placeholder in methods:
        method = getattr(provider, name, None)
        if not callable(method) or getattr(method, "__func__", method) is placeholder:
            raise GuardProviderUnavailable("Required original integration unavailable: " + name)


def validate_staged_request(request_raw, checkpoint_raw, *, expected_request_sha256):
    """Metadata consistency only; never consumes a challenge or invokes a guard."""
    require(is_sha256(expected_request_sha256), "Pinned staged request required")
    envelope = decode(request_raw, MAX_REQUEST_BYTES, canonical=True)
    exact(envelope, {"request", "request_sha256"}, "staged request envelope")
    body = envelope["request"]
    exact(body, _REQUEST_FIELDS, "staged request")
    require(envelope["request_sha256"] == expected_request_sha256 == digest(body) and
            body["schema"] == SCHEMA and body["mode"] == "simulation_only" and
            body["status"] == "STAGED_SIGNED_INPUT_CLAIMS_BOUND_ORIGINAL_RUNTIME_GUARDS_PENDING" and
            body["required_external_runtime_services"] == list(REQUIRED_RUNTIME_SERVICES) and
            body["numerical_entrypoint"] == dict(NUMERICAL_ENTRYPOINT),
            "Staged request identity or required original service inventory differs")
    for name in ("qualification_or_execution_authority", "provider_registration_performed",
                 "runtime_guards_performed", "runtime_probe_performed", "full_checkpoint_validation_performed",
                 "numerical_step_performed", "retry_or_continuation_authority"):
        require(body[name] is False, "Staged metadata cannot claim completed execution gates")
    journal._validate_identity(body["identity"])
    require(is_sha256(body["request_nonce"]) and is_sha256(body["authority_public_key_sha256"]) and
            type(body["prepared_at_unix_s"]) is int and body["prepared_at_unix_s"] >= 0 and
            type(body["input_admission_expires_at_unix_s"]) is int and
            body["input_admission_expires_at_unix_s"] > body["prepared_at_unix_s"],
            "Staged challenge/key/validity declarations differ; actual freshness remains the original guard's job")
    exact(body["resource_request"], {"maximum_wall_time_ms", "maximum_rss_bytes", "workers"}, "resource request")
    resources = body["resource_request"]
    require(all(type(resources[k]) is int and 0 < resources[k] <= 2**63-1
                for k in ("maximum_wall_time_ms", "maximum_rss_bytes")) and
            type(resources["workers"]) is int and resources["workers"] == 1,
            "Exact finite single-worker resource proposal required")
    exact(body["input_admissions"], {"line_geometry_review", "runtime_environment_review"}, "input admission references")
    for reference in body["input_admissions"].values():
        exact(reference, {"envelope_sha256", "statement_sha256", "verifier_implementation_sha256"}, "input admission reference")
        require(all(is_sha256(value) for value in reference.values()), "Exact input receipt/verifier digests required")
    declared = body["chunk_plan"]["plan"]
    plan = plan_chunk(checkpoint_raw, expected_checkpoint_sha256=declared["parent_checkpoint_sha256"],
                      expected_identity=body["identity"], ticks=declared["requested_ticks"])
    require(encode(plan) == encode(body["chunk_plan"]), "Staged chunk plan differs from exact parent")
    return body


def require_owned_result_bytes(result, body, expected_request_sha256):
    require(type(result) is OwnedChunkResult and result.request_sha256 == expected_request_sha256 and
            result.source_sha256 == body["identity"]["source_sha256"], "Owned result request/source differs")
    for raw, bound in ((result.raw_chunk_json, journal.MAX_CHUNK),
                       (result.linked_checkpoint_json, journal.MAX_CHECKPOINT),
                       (result.receipt_bundle_raw, MAX_OWNED_RECEIPT_BYTES)):
        require(type(raw) is bytes and 0 < len(raw) <= bound, "Bounded complete owned result bytes required")
    require(is_sha256(result.receipt_bundle_sha256) and
            sha256(result.receipt_bundle_raw).hexdigest() == result.receipt_bundle_sha256,
            "Owned receipt bytes differ")


def _require_chunk_checkpoint_binding(body, checkpoint_raw, raw_chunk_json, linked_checkpoint_json):
    """Shared RAW metadata checks, not execution/cleanup authentication.

    Both callers first validate the exact staged request. The numerical worker
    checks these bounds before returning RAW bytes. bind_owned_result additionally
    requires the real external execution/cleanup admission before this check.
    No numerical work, resource observation, receipt or authority is supplied.
    """
    require(type(raw_chunk_json) is bytes and 0 < len(raw_chunk_json) <= journal.MAX_CHUNK and
            type(linked_checkpoint_json) is bytes and 0 < len(linked_checkpoint_json) <= journal.MAX_CHECKPOINT,
            "Bounded immutable raw numerical output bytes required")
    declared = body["chunk_plan"]["plan"]
    parent = decode(checkpoint_raw, journal.MAX_CHECKPOINT, canonical=True)
    chunk = decode(raw_chunk_json, journal.MAX_CHUNK, canonical=True)
    linked = decode(linked_checkpoint_json, journal.MAX_CHECKPOINT, canonical=True)
    journal._transition(parent, chunk, linked, body["identity"])
    output = linked["checkpoint"]
    require(chunk["chunk"]["start_tick"] == declared["start_tick"] and
            output["tick"] <= declared["end_tick_ceiling"], "Owned chunk exceeds reviewed tick request")
    before_power = parent["checkpoint"]["state"]["thermal"]["light"]["powered"]
    after_power = output["state"]["thermal"]["light"]["powered"]
    require_committed_work_transition(before_power, after_power,
        start_tick=declared["start_tick"], end_tick=output["tick"], maximum_new_work=declared["maximum_new_work"])
    require_clocked_counter_transition(parent["checkpoint"]["memory"], output["memory"],
        start_tick=declared["start_tick"], end_tick=output["tick"])
    for clock in (output["state"]["drs"]["ticks"], output["state"]["thermal"]["thermal"]["ticks"],
                  output["state"]["thermal"]["light"]["feedback_ticks"]):
        require(type(clock) is int and clock == output["tick"], "Owned component clocks differ")


def bind_owned_result(request_raw, checkpoint_raw, result, *, expected_request_sha256):
    """Only metadata consistency AFTER external owned execution/cleanup admission."""
    body = validate_staged_request(request_raw, checkpoint_raw,
                                   expected_request_sha256=expected_request_sha256)
    require_owned_result_bytes(result, body, expected_request_sha256)
    # Full numerical validation already happened inside the owned allocation;
    # dispatch_owned_chunk authenticates its original receipts before binding.
    _require_chunk_checkpoint_binding(body, checkpoint_raw, result.raw_chunk_json, result.linked_checkpoint_json)
    return result


def dispatch_owned_chunk(request_raw, checkpoint_raw, *, expected_request_sha256,
                         expected_provider_sha256, provider=None):
    """Require a genuine original integration; return RAW data, never a capability."""
    require_provider(provider, expected_provider_sha256, (
        ("execute_owned_request", OriginalGuardProvider.execute_owned_request),
        ("require_authenticated_owned_execution_and_cleanup",
         OriginalGuardProvider.require_authenticated_owned_execution_and_cleanup),
    ))
    body = validate_staged_request(request_raw, checkpoint_raw,
                                   expected_request_sha256=expected_request_sha256)
    result = provider.execute_owned_request(request_raw, checkpoint_raw,
                                            numerical_backend_family=NUMERICAL_BACKEND_FAMILY)
    require_owned_result_bytes(result, body, expected_request_sha256)
    require(provider.require_authenticated_owned_execution_and_cleanup(request_raw, result) is None,
            "Original receipt verifier must raise on failure")
    return bind_owned_result(request_raw, checkpoint_raw, result,
                             expected_request_sha256=expected_request_sha256)
