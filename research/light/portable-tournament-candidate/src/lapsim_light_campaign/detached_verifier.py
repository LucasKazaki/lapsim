"""UNTESTED optional Ed25519 verification primitive, not a trust bootstrap.

Frozen behavior: importing/constructing this adapter does not import the crypto
library, read files, observe runtime state or create a key/policy. A separately
authorized original owner must qualify the exact loaded Python/native/library
closure and establish key, receipt, time/challenge and cleanup provenance.
Only an explicit verify call imports the pinned public verification API. It
verifies the exact bounded domain-prefixed bytes without re-encoding them.
Missing/version-mismatched/unsupported/invalid verification refuses; unknown
exception classes/subclasses, MemoryError and BaseException propagate unchanged.
No signing, key discovery/generation, auto-install, CLI or provider registration.
An implementation hash attribute and package version are not source authority.
"""

from dataclasses import dataclass

from .admission import AdmissionUnavailable, DOMAIN, MAX_STATEMENT_BYTES
from .input_contracts import is_sha256, require


CRYPTOGRAPHY_VERSION = "50.0.2"


@dataclass(frozen=True, slots=True)
class CryptographyEd25519Verifier:
    """Explicit optional implementation of the existing DetachedVerifier API.

    implementation_sha256 is the externally reviewed adapter-source pin, not
    a wheel hash, version or value selected by an untrusted input statement.
    This object is never installed into AuthorityPolicy/Start automatically.
    The owner must prepare reviewed dependencies before its exact environment
    observation if deferred imports would change that observed loaded closure.
    """

    implementation_sha256: str

    def __post_init__(self):
        require(is_sha256(self.implementation_sha256), "Independently reviewed adapter-source pin required")

    def verify_ed25519(self, public_key: bytes, message: bytes, signature: bytes) -> None:
        require(type(public_key) is bytes and len(public_key) == 32 and
                type(signature) is bytes and len(signature) == 64 and
                type(message) is bytes and len(DOMAIN) < len(message) <= len(DOMAIN) + MAX_STATEMENT_BYTES and
                message.startswith(DOMAIN), "Exact bounded Ed25519 admission bytes required")
        try:
            import cryptography
            from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        except ImportError as error:
            if type(error) not in (ImportError, ModuleNotFoundError):
                raise
            raise AdmissionUnavailable("Pinned optional Ed25519 library is unavailable; no install or fallback") from error
        version = getattr(cryptography, "__version__", None)
        if type(version) is not str or version != CRYPTOGRAPHY_VERSION:
            raise AdmissionUnavailable("Ed25519 library version differs; this check is not loaded-source authentication")
        try:
            key = Ed25519PublicKey.from_public_bytes(public_key)
            result = key.verify(signature, message)
        except (InvalidSignature, UnsupportedAlgorithm, ValueError) as error:
            if type(error) not in (InvalidSignature, UnsupportedAlgorithm, ValueError):
                raise
            raise AdmissionUnavailable("Ed25519 signature rejected or algorithm unavailable") from error
        if result is not None:
            raise AdmissionUnavailable("Ed25519 verifier returned an unsupported success value")
