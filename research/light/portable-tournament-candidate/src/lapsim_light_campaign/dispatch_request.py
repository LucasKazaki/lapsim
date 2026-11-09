"""UNTESTED input-bound dispatch staging, with no worker/provider/guard calls.

This request is not an execution permit. Real original-owner resource guards,
lease/deadline/watchdog, physical validation, nonce consumption and owned cleanup
are still required. There is no execute/run/registration or fallback entrypoint.
"""
from hashlib import sha256

from .admission import (AuthorityPolicy, MAX_STATEMENT_BYTES, authenticate_input_statement)
from .environment_contract import require_environment_match
from .input_contracts import decode, digest, encode, exact, is_sha256, require
from .stepping import plan_chunk


SCHEMA = "lapsim.light-guarded-dispatch.staged-request.v2"
NUMERICAL_ENTRYPOINT = (
    ("family", "lapsim.portable-awd-standing-numerical-bridge.v1"),
    ("function", "advance_chunk"), ("progress_callback", "none"),
)
MAX_REQUEST_BYTES = 128 * 1024
REQUIRED_RUNTIME_SERVICES = (
    "exact_loaded_source_and_runtime_identity_before_and_after",
    "single_use_fresh_request_challenge_and_input_expiry",
    "original_activity_session_game_memory_guards",
    "exclusive_owned_writer_and_resource_lease",
    "fresh_finite_allocation_deadline_and_watchdog",
    "full_checkpoint_line_physical_and_output_validation",
    "exact_owned_execution_and_cleanup_receipt_admission",
)


def prepare_dispatch_request(
    checkpoint_raw, *, expected_checkpoint_sha256, expected_identity, ticks,
    line_statement_raw, environment_statement_raw, line_receipts, environment_receipts,
    authority_policy, verifier, request_nonce, now_unix_s, expected_cones_raw_sha256,
    environment_recipe_raw, environment_observation_raw, resource_request,
):
    """Bind reviewed input claims to a hash-bound proposal for the original owner.

    One fresh request challenge binds both purpose-separated signatures. The
    original owner must consume that challenge once at execution admission and
    recheck expiry, actual resources and all required services before a worker.
    Matching declarations are not runtime measurements made by this module.
    """
    require(type(authority_policy) is AuthorityPolicy and is_sha256(expected_cones_raw_sha256),
            "Externally pinned authority policy and cone identity required")
    exact(resource_request, {"maximum_wall_time_ms", "maximum_rss_bytes", "workers"},
          "finite resource request")
    require(all(type(resource_request[k]) is int and 0 < resource_request[k] <= 2**63 - 1
                for k in ("maximum_wall_time_ms", "maximum_rss_bytes")) and
            type(resource_request["workers"]) is int and resource_request["workers"] == 1,
            "Explicit finite single-worker resource request required; no allocation is inferred")
    resources = decode(encode(resource_request), MAX_REQUEST_BYTES)
    plan = plan_chunk(checkpoint_raw, expected_checkpoint_sha256=expected_checkpoint_sha256,
                      expected_identity=expected_identity, ticks=ticks)
    identity = plan["plan"]["identity"]
    environment = require_environment_match(
        environment_recipe_raw, environment_observation_raw,
        expected_numerical_environment_sha256=identity["environment_sha256"],
        expected_source_sha256=identity["source_sha256"],
        expected_verifier_sha256=authority_policy.verifier_implementation_sha256,
    )
    subject = {
        "source_sha256": identity["source_sha256"],
        "configuration_sha256": identity["configuration_sha256"],
        "course_bundle_sha256": identity["course_bundle_sha256"],
        "cones_raw_sha256": expected_cones_raw_sha256,
        "line_artifact_sha256": identity["line_artifact_sha256"],
        "environment_lock_sha256": environment["environment_sha256"],
    }
    common = {"policy": authority_policy, "verifier": verifier, "expected_nonce": request_nonce,
              "expected_subject": subject, "now_unix_s": now_unix_s}
    line = authenticate_input_statement(line_statement_raw, expected_purpose="line_geometry_review",
                                        receipts=line_receipts, **common)
    runtime = authenticate_input_statement(environment_statement_raw,
                                           expected_purpose="runtime_environment_review",
                                           receipts=environment_receipts, **common)
    admissions = {}
    expires = []
    for name, statement in (("line_geometry_review", line), ("runtime_environment_review", runtime)):
        value = decode(statement.envelope_raw, MAX_STATEMENT_BYTES, canonical=True)
        expires.append(value["statement"]["expires_at_unix_s"])
        admissions[name] = {"envelope_sha256": sha256(statement.envelope_raw).hexdigest(),
                            "statement_sha256": statement.statement_sha256,
                            "verifier_implementation_sha256": statement.verifier_implementation_sha256}
    body = {
        "schema": SCHEMA, "mode": "simulation_only", "identity": identity,
        "numerical_entrypoint": dict(NUMERICAL_ENTRYPOINT),
        "request_nonce": request_nonce, "prepared_at_unix_s": now_unix_s,
        "input_admission_expires_at_unix_s": min(expires),
        "authority_key_id": authority_policy.key_id,
        "authority_public_key_sha256": authority_policy.public_key_sha256,
        "chunk_plan": plan, "input_admissions": admissions,
        "resource_request": resources,
        "required_external_runtime_services": list(REQUIRED_RUNTIME_SERVICES),
        "status": "STAGED_SIGNED_INPUT_CLAIMS_BOUND_ORIGINAL_RUNTIME_GUARDS_PENDING",
        "qualification_or_execution_authority": False, "provider_registration_performed": False,
        "runtime_guards_performed": False, "runtime_probe_performed": False,
        "full_checkpoint_validation_performed": False, "numerical_step_performed": False,
        "retry_or_continuation_authority": False,
    }
    request = {"request": body, "request_sha256": digest(body)}
    require(len(encode(request)) <= MAX_REQUEST_BYTES, "Staged dispatch request exceeds bound")
    return request
