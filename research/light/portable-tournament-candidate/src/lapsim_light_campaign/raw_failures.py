"""UNTESTED bounded cooperative-failure transport, never a journal/admission.

No I/O or numerical imports. The genuine original owner must retain this raw
evidence and finish actual owned cleanup. This cannot catch process death/OOM
or preserve arbitrary earlier/private intermediate integrator state.
"""
from .input_contracts import decode, digest, encode, exact, is_sha256, require


SCHEMA = "lapsim.light-source-observation-quarantine.raw.v1"
MAX_QUARANTINE_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_BYTES = 3 * 1024 * 1024
KINDS_AND_STAGES = {
    "raw_chunk": "chunk_final_source_observation",
    "raw_replay_report": "replay_final_source_observation",
}


class RawOutputQuarantined(ValueError):
    """Still a failed operation; diagnostic bytes carry NO execution capability."""

    def __init__(self, *, artifact_kind, artifact, expected_source_sha256, error):
        require(artifact_kind in KINDS_AND_STAGES and type(artifact) is dict and
                len(encode(artifact)) <= MAX_ARTIFACT_BYTES and is_sha256(expected_source_sha256) and
                isinstance(error, Exception), "Bounded raw output and original cooperative error required")
        body = {
            "schema": SCHEMA, "stage": KINDS_AND_STAGES[artifact_kind],
            "artifact_kind": artifact_kind, "artifact": artifact, "artifact_sha256": digest(artifact),
            "expected_source_sha256": expected_source_sha256,
            "error": {"type": type(error).__name__, "message": str(error)},
            "status": "QUARANTINED_FINAL_SOURCE_OBSERVATION_FAILED_DO_NOT_ADMIT",
            "source_observation_verified": False, "qualification_or_execution_authority": False,
            "retry_or_continuation_authority": False,
        }
        self.quarantine_sha256 = digest(body)
        self.evidence_raw = encode({"quarantine": body, "quarantine_sha256": self.quarantine_sha256})
        require(len(self.evidence_raw) <= MAX_QUARANTINE_BYTES,
                "Quarantine exceeds bound; original owner must preserve complete evidence externally")
        super().__init__("Numerical output quarantined after final source observation; do not admit or resume it")


def read_quarantined_output(raw, *, expected_quarantine_sha256):
    """Verify transport consistency only; never extract a successful result."""
    value = decode(raw, MAX_QUARANTINE_BYTES, canonical=True)
    exact(value, {"quarantine", "quarantine_sha256"}, "raw quarantine envelope")
    body = value["quarantine"]
    exact(body, {"schema", "stage", "artifact_kind", "artifact", "artifact_sha256", "expected_source_sha256",
                 "error", "status", "source_observation_verified", "qualification_or_execution_authority",
                 "retry_or_continuation_authority"}, "raw quarantine")
    require(is_sha256(expected_quarantine_sha256) and
            value["quarantine_sha256"] == expected_quarantine_sha256 == digest(body) and
            body["schema"] == SCHEMA and body["artifact_kind"] in KINDS_AND_STAGES and
            body["stage"] == KINDS_AND_STAGES[body["artifact_kind"]] and
            body["status"] == "QUARANTINED_FINAL_SOURCE_OBSERVATION_FAILED_DO_NOT_ADMIT" and
            body["source_observation_verified"] is False and body["qualification_or_execution_authority"] is False and
            body["retry_or_continuation_authority"] is False and is_sha256(body["expected_source_sha256"]) and
            type(body["artifact"]) is dict and len(encode(body["artifact"])) <= MAX_ARTIFACT_BYTES and
            body["artifact_sha256"] == digest(body["artifact"]), "Raw quarantine identity/scope differs")
    exact(body["error"], {"type", "message"}, "original cooperative error")
    require(type(body["error"]["type"]) is str and body["error"]["type"] and
            type(body["error"]["message"]) is str, "Original error type and complete message required")
    return value
