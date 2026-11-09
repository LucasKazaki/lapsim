"""UNTESTED fixed numerical worker program; no OS bootstrap or guard provider.

Frozen contract: resolve only existing v2 advance_chunk with no callback; bind
exact parent/identity; advance once; retain bytes before numerical acceptance;
link/validate and enforce original request bounds; check unchanged source.
No source observation or numerical import occurs until explicit execute().

Execution requires the original owner's already authenticated inputs/operation,
live guards/lease/allocation/deadline/watchdog, durable failure retention and
cleanup. The local attempt lock is not that lease or challenge authentication.
No provider, process, file I/O, receipt, signing, retry or campaign is created.
Snapshots preserve memory only after a call; they cannot survive process death.
Exceptions received from dependencies propagate unchanged. The bridge's own
quarantine/error semantics remain separate and must be preserved by its owner.
"""

from dataclasses import dataclass
from threading import Lock

from . import raw_journal as journal
from .guarded_dispatch import (NUMERICAL_BACKEND_FAMILY, validate_staged_request,
                               _require_chunk_checkpoint_binding)
from .input_contracts import decode, encode, require


@dataclass(frozen=True, slots=True)
class RawChunkWorkerOutput:
    """Data only, not OwnedChunkResult or original execution/cleanup evidence."""

    request_sha256: str
    source_sha256: str
    raw_chunk_json: bytes
    linked_checkpoint_json: bytes

    @property
    def qualification_or_execution_authority(self):
        return False


@dataclass(frozen=True, slots=True)
class ChunkWorkerSnapshot:
    """Post-call memory view; direct construction/flags establish no provenance."""

    request_sha256: str
    input_checkpoint_sha256: str
    phase: str
    local_attempt_started: bool
    local_attempt_finished: bool
    raw_chunk_json: bytes | None
    linked_checkpoint_json: bytes | None
    source_before_json: bytes | None
    source_after_json: bytes | None

    @property
    def qualification_or_execution_authority(self):
        return False


class ChunkWorkerProgram:
    """One fixed numerical call, for a genuinely admitted owned worker only.

    The original provider retains this object and reads snapshot() after return
    or exception to preserve already-produced bytes under its real writer and
    cleanup controls. A phase is not an OS terminal, successful admission or
    durable evidence. The object has no reset or retry operation.
    """

    __slots__ = ("_request_raw", "_checkpoint_raw", "_request_sha256", "_parent_sha256",
                 "_attempt_lock", "_attempted", "_finished", "_phase", "_raw_chunk_json",
                 "_linked_checkpoint_json", "_source_before_json", "_source_after_json")

    def __init__(self, request_raw, checkpoint_raw, *, expected_request_sha256):
        require(type(request_raw) is bytes and type(checkpoint_raw) is bytes,
                "Immutable exact worker request/parent bytes required")
        body = validate_staged_request(request_raw, checkpoint_raw,
                                       expected_request_sha256=expected_request_sha256)
        self._request_raw, self._checkpoint_raw = request_raw, checkpoint_raw
        self._request_sha256 = expected_request_sha256
        self._parent_sha256 = body["chunk_plan"]["plan"]["parent_checkpoint_sha256"]
        self._attempt_lock = Lock()  # Per-object claim only, never an owned resource lease.
        self._attempted = self._finished = False
        self._phase = "constructed"
        self._raw_chunk_json = self._linked_checkpoint_json = None
        self._source_before_json = self._source_after_json = None

    def snapshot(self):
        with self._attempt_lock:
            require(not self._attempted or self._finished, "Snapshot requires a returned/raised worker call")
            return ChunkWorkerSnapshot(self._request_sha256, self._parent_sha256, self._phase,
                self._attempted, self._finished, self._raw_chunk_json, self._linked_checkpoint_json,
                self._source_before_json, self._source_after_json)

    def execute(self, *, bridge):
        claimed = False
        try:
            with self._attempt_lock:
                require(not self._attempted and not self._finished, "Worker attempt already consumed; no retry/reset")
                claimed = True  # Set before the instance flag: finally seals an interrupted claim too.
                self._attempted = True
            self._phase = "validating_bridge"
            from .numerical_bridge import NumericalBridge, checkpoint

            require(type(bridge) is NumericalBridge, "Exact reviewed numerical bridge required")
            body = validate_staged_request(self._request_raw, self._checkpoint_raw,
                                           expected_request_sha256=self._request_sha256)
            require(bridge.identity == body["identity"], "Worker bridge differs from complete request identity")
            source = body["identity"]["source_sha256"]
            parent = decode(self._checkpoint_raw, journal.MAX_CHECKPOINT, canonical=True)
            self._phase = "observing_initial_source"
            self._source_before_json = encode(bridge.source_identity())
            self._phase = "resuming_parent"
            session = bridge.resume(parent, expected_checkpoint_sha256=self._parent_sha256,
                                     expected_source_sha256=source)
            require(encode(checkpoint(session)) == self._checkpoint_raw,
                    "Resumed parent differs from exact canonical input")
            self._phase = "advancing"
            generated = bridge.advance_chunk(session, ticks=body["chunk_plan"]["plan"]["requested_ticks"],
                                              expected_source_sha256=source, progress_callback=None)
            self._raw_chunk_json = encode(generated)
            require(len(self._raw_chunk_json) <= journal.MAX_CHUNK, "Worker raw chunk exceeds byte bound")
            self._phase = "validating_output"
            accepted = bridge.accept_chunk(decode(self._raw_chunk_json, journal.MAX_CHUNK, canonical=True),
                expected_input_checkpoint=parent, expected_source_sha256=source)
            self._linked_checkpoint_json = encode(checkpoint(accepted))
            require(len(self._linked_checkpoint_json) <= journal.MAX_CHECKPOINT, "Worker linked checkpoint exceeds bound")
            self._phase = "binding_request"
            _require_chunk_checkpoint_binding(body, self._checkpoint_raw,
                self._raw_chunk_json, self._linked_checkpoint_json)
            self._phase = "observing_final_source"
            self._source_after_json = encode(bridge.source_identity())
            require(self._source_after_json == self._source_before_json, "Worker source changed; retain RAW bytes as failure")
            output = RawChunkWorkerOutput(self._request_sha256, source,
                                          self._raw_chunk_json, self._linked_checkpoint_json)
            self._phase = "raw_output_ready"
            return output
        finally:
            if claimed:
                with self._attempt_lock:
                    self._attempted = True
                    self._finished = True


def create_chunk_worker(request_raw, checkpoint_raw, *, expected_request_sha256, numerical_backend_family):
    """Fixed one-family resolver; no arbitrary imports/callables or provider registration.

    Staged-request validation additionally fixes advance_chunk/callback=none.
    The returned object is not an execution permit or a production OS worker.
    """
    require(type(numerical_backend_family) is str and numerical_backend_family == NUMERICAL_BACKEND_FAMILY,
            "Unsupported numerical worker family; no fallback")
    return ChunkWorkerProgram(request_raw, checkpoint_raw, expected_request_sha256=expected_request_sha256)
