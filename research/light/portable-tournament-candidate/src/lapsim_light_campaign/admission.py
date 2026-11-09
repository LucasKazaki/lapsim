"""UNTESTED external authentication adapter; no built-in trust or verifier.

The trusted owner must establish key/verifier provenance, receipt semantics,
time and a fresh non-reused challenge before calling this boundary. This new
protocol is not a decoder for the archive's unavailable producer receipts.
"""
from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Protocol

from .input_contracts import decode, digest, encode, exact, is_sha256, require


SCHEMA = "lapsim.light-input-admission.ed25519.v1"
AUDIENCE = "lapsim.light-tournament-source-candidate"
DOMAIN = b"lapsim.light-input-admission.ed25519.v1\x00"
PURPOSES = frozenset({"line_geometry_review", "runtime_environment_review"})
SUBJECT_FIELDS = frozenset({
    "source_sha256", "configuration_sha256", "course_bundle_sha256",
    "cones_raw_sha256", "line_artifact_sha256", "environment_lock_sha256",
})
RECEIPTS = frozenset({"supported_tool_terminal", "owned_cleanup", "independent_review"})
MAX_STATEMENT_BYTES = 32 * 1024
MAX_RECEIPT_BYTES = 512 * 1024


class AdmissionUnavailable(ValueError):
    pass


class DetachedVerifier(Protocol):
    """Trusted bootstrap adapter, not an implementation selected by input JSON."""

    implementation_sha256: str

    def verify_ed25519(self, public_key: bytes, message: bytes, signature: bytes) -> None:
        """Verify with a reviewed crypto library; raise on invalid or unavailable."""
        raise NotImplementedError("A reviewed detached-signature implementation is required")


@dataclass(frozen=True, slots=True)
class AuthorityPolicy:
    """Out-of-band owner policy; input artifacts must never supply this policy."""

    key_id: str
    public_key: bytes
    public_key_sha256: str
    verifier_implementation_sha256: str
    maximum_validity_seconds: int

    def __post_init__(self):
        require(type(self.key_id) is str and re.fullmatch(r"[A-Za-z0-9._-]{1,64}", self.key_id),
                "Explicit authority key identifier required")
        require(type(self.public_key) is bytes and len(self.public_key) == 32 and
                is_sha256(self.public_key_sha256) and
                sha256(self.public_key).hexdigest() == self.public_key_sha256 and
                is_sha256(self.verifier_implementation_sha256), "Pinned public key and verifier required")
        require(type(self.maximum_validity_seconds) is int and
                1 <= self.maximum_validity_seconds <= 86400, "Bounded external validity policy required")


@dataclass(frozen=True, slots=True)
class AuthenticatedInputStatement:
    """Transport result only; direct construction or a type check confers no trust."""

    envelope_raw: bytes
    statement_sha256: str
    verifier_implementation_sha256: str
    purpose: str

    @property
    def qualification_or_execution_authority(self):
        return False


def authenticate_input_statement(raw, *, policy, verifier, expected_purpose,
                                 expected_nonce, expected_subject, receipts, now_unix_s):
    """Authenticate exact scoped input claims through the trusted external adapter.

    No verifier is discovered or substituted. Hashing the raw receipts binds
    them; the trusted issuer/owner must separately establish their semantics.
    A caller must retain/use its challenge once; this function owns no nonce
    database and grants no execution, resource or continuation capability.
    """
    if verifier is None:
        raise AdmissionUnavailable("No independently pinned detached-signature verifier")
    require(type(policy) is AuthorityPolicy and type(expected_purpose) is str and expected_purpose in PURPOSES,
            "Explicit authority policy and input-review purpose required")
    require(is_sha256(expected_nonce) and type(now_unix_s) is int and now_unix_s >= 0,
            "Fresh external challenge and trusted UTC time required")
    exact(expected_subject, SUBJECT_FIELDS, "expected admission subject")
    require(all(is_sha256(v) for v in expected_subject.values()), "Exact expected subject digests required")
    exact(receipts, RECEIPTS, "external receipt bundle")
    require(all(type(v) is bytes and 0 < len(v) <= MAX_RECEIPT_BYTES for v in receipts.values()),
            "Bounded raw supported-tool, cleanup and independent-review evidence required")
    value = decode(raw, MAX_STATEMENT_BYTES, canonical=True)
    exact(value, {"schema", "statement", "signature_hex"}, "signed admission envelope")
    require(value["schema"] == SCHEMA, "Unsupported admission protocol")
    statement = value["statement"]
    exact(statement, {"key_id", "audience", "purpose", "nonce", "issued_at_unix_s",
                      "expires_at_unix_s", "subject", "receipts"}, "admission statement")
    issued, expires = statement["issued_at_unix_s"], statement["expires_at_unix_s"]
    require(type(issued) is int and type(expires) is int and
            0 <= issued <= now_unix_s < expires and
            expires - issued <= policy.maximum_validity_seconds,
            "Admission statement is future-dated, expired or outside validity policy")
    require(statement["key_id"] == policy.key_id and statement["audience"] == AUDIENCE and
            statement["purpose"] == expected_purpose and statement["nonce"] == expected_nonce,
            "Admission issuer, audience, scope or challenge differs")
    exact(statement["subject"], SUBJECT_FIELDS, "signed admission subject")
    require(statement["subject"] == expected_subject, "Admission source/config/input bindings differ")
    exact(statement["receipts"], RECEIPTS, "signed receipt identities")
    require(statement["receipts"] == {name: sha256(data).hexdigest() for name, data in receipts.items()},
            "Raw external receipts differ from authenticated statement")
    signature = value["signature_hex"]
    require(type(signature) is str and re.fullmatch(r"[0-9a-f]{128}", signature),
            "Exact detached Ed25519 signature required")
    require(getattr(verifier, "implementation_sha256", None) == policy.verifier_implementation_sha256,
            "Detached verifier differs from independently pinned bootstrap")
    verify = getattr(verifier, "verify_ed25519", None)
    if not callable(verify):
        raise AdmissionUnavailable("Pinned detached-signature verification is unavailable")
    # The verifier raises on rejection/unavailability. Preserve unknown original
    # owner control exceptions and their type; never downgrade fatal cleanup to
    # a recoverable-looking local admission failure.
    result = verify(policy.public_key, DOMAIN + encode(statement), bytes.fromhex(signature))
    require(result is None, "Detached verifier must raise on failure and return None only on success")
    return AuthenticatedInputStatement(raw, digest(statement), policy.verifier_implementation_sha256,
                                       expected_purpose)
