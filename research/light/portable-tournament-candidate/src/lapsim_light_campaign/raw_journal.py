"""Immutable local storage for RAW seven-policy AWD development evidence.

Frozen behavior contract (UNTESTED): import performs no I/O or simulator import.
Each journal belongs to one exact AWD/OFF development policy and pinned inputs.
Exclusive-create objects precede an immutable receipt, written last. A complete,
digest-linked receipt commits local storage consistency only, never execution
admission. Torn receipts, gaps and orphan objects remain recovery candidates and
block further append. They must not be used for automatic resume.

The guarded owner must perform the original bridge validation, external owned
receipt admission and resource/writer exclusion separately. This module supplies
no runner, provider, observer, lease, admission override or automatic resume.
Its path checks assume an owner-controlled directory; they are not protection
against a concurrent hostile filesystem writer. File fsync and POSIX directory
fsync are optional requests, not a cross-platform power-loss guarantee.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path, PureWindowsPath
import re


MANIFEST_SCHEMA = "lapsim.light-raw-journal.manifest.v1"
RECORD_SCHEMA = "lapsim.light-raw-journal.record.v1"
TERMINAL_SCHEMA = "lapsim.light-raw-journal.terminal.v1"
CHECKPOINT_SCHEMA = "lapsim.torque-light-awd-racingline-standing-checkpoint.v1"
CHUNK_SCHEMA = "lapsim.torque-light-awd-racingline-standing-chunk.v1"
TOPOLOGY = "synthetic_independent_four_awd_v1"
POLICIES = tuple(
    "awd7-" + name.replace("_", "-") + "-v4"
    for name in (
        "equal_off", "load_off", "slip_off", "feedforward_off", "yaw_pi_off",
        "yaw_slip_off", "eco_neutral_off",
    )
)
RAW_LABEL = "RAW_PERSISTED_PENDING_EXTERNAL_ADMISSION"
_PORTABLE_NUMERICAL_FAMILY = "lapsim.portable-awd-standing-numerical-bridge.v1"
MAX_MANIFEST = 512 * 1024
# The bridge caps canonical bodies; storage also retains their hash envelopes.
MAX_CHECKPOINT_BODY = 256 * 1024
MAX_CHECKPOINT = MAX_CHECKPOINT_BODY + 1024
MAX_CHUNK_BODY = 2 * 1024 * 1024
MAX_CHUNK = MAX_CHUNK_BODY + 1024
MAX_RECEIPT = 16 * 1024
MAX_RECORDS = 750
OBJECT_NAME = re.compile(r"[0-9a-f]{64}\.json\Z")
RECORD_NAME = re.compile(r"[0-9]{6}\.json\Z")
TERMINAL_STATUSES = frozenset({
    "raw_completed", "paused_budget", "stopped_by_guard", "cancelled", "failed",
    "interrupted",
})
IDENTITY_FIELDS = frozenset({
    "source_sha256", "configuration_sha256", "course_bundle_sha256",
    "line_artifact_sha256", "environment_sha256", "policy_id", "topology_id",
    "drive_availability", "regen_enabled", "role", "heldout_used",
})
CHUNK_FIELDS = frozenset({
    "schema", "source_sha256", "config_id", "course_id", "context_sha256",
    "start_tick", "end_tick", "parent_chunk_sha256", "input_checkpoint_sha256",
    "output_checkpoint", "telemetry", "status", "execution_evidence", "awards",
})
RECEIPT_FIELDS = frozenset({
    "schema", "manifest_sha256", "sequence", "previous_receipt_sha256",
    "input_checkpoint_sha256", "chunk_object_sha256", "checkpoint_object_sha256",
    "chunk_sha256", "checkpoint_sha256", "evidence_status",
})


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _encode(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _digest(value):
    return sha256(_encode(value)).hexdigest()


def _sha(value):
    return (
        type(value) is str and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _pairs(items):
    result = {}
    for key, value in items:
        _require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def _check_windows_component_spelling(path):
    """Refuse ambiguous non-anchor Windows components without normalization/I/O.

    Actual WindowsPath inherits PureWindowsPath. POSIX spelling and existing
    dot/parent semantics are unchanged. Anchors, other alias forms and filesystem
    ownership remain the original owner's qualification, not this check's proof.
    """
    if isinstance(path, PureWindowsPath):
        for part in path.parts:
            if part == path.anchor or part in ('.', '..'):
                continue
            _require(not part.startswith(' ') and not part.endswith((' ', '.')),
                     'Ambiguous Windows component spelling refused before filesystem access')


def _no_alias(path):
    _check_windows_component_spelling(path)
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        _require(
            not item.is_symlink()
            and not getattr(info, "st_file_attributes", 0) & 1024,
            "Symlink or reparse-point path refused",
        )


def _read(path, maximum):
    _no_alias(path)
    _require(path.is_file(), "Expected regular file")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    _require(len(raw) <= maximum, "Stored JSON exceeds bound")
    value = json.loads(
        raw, object_pairs_hook=_pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError("Nonfinite JSON: " + value)
        ),
    )
    _require(raw == _encode(value), "Noncanonical or incomplete stored JSON")
    return value


def _sync_directory(path, enabled):
    # Windows directory flushing is not implemented by this stdlib candidate.
    if enabled and os.name == "posix":
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _write_new(path, value, maximum, sync):
    raw = _encode(value)
    _require(len(raw) <= maximum, "Output JSON exceeds bound")
    _no_alias(path)
    # Interrupted writes remain evidence. Never delete or overwrite on failure.
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        if sync:
            os.fsync(stream.fileno())
    _sync_directory(path.parent, sync)


def _checkpoint(value):
    _require(
        type(value) is dict and set(value) == {"checkpoint", "checkpoint_sha256"},
        "Exact bridge checkpoint envelope required",
    )
    body = value["checkpoint"]
    _require(
        type(body) is dict and body.get("schema") == CHECKPOINT_SCHEMA
        and value["checkpoint_sha256"] == _digest(body)
        and type(body.get("tick")) is int and 0 <= body["tick"] <= 1030000
        and type(body.get("segment")) is int and 0 <= body["segment"] <= MAX_RECORDS
        and body.get("status") in {
            "running", "completed", "diagnostic_complete", "time_limit", "invalid",
        }
        and len(_encode(body)) <= MAX_CHECKPOINT_BODY
        and len(_encode(value)) <= MAX_CHECKPOINT,
        "Checkpoint schema, digest or size differs",
    )
    return body


def _validate_identity(identity):
    _require(
        type(identity) is dict and set(identity) == IDENTITY_FIELDS,
        "Exact declared input identity required",
    )
    for name in (
        "source_sha256", "configuration_sha256", "course_bundle_sha256",
        "line_artifact_sha256", "environment_sha256",
    ):
        _require(_sha(identity[name]), "Exact SHA256 required: " + name)
    _require(
        identity["policy_id"] in POLICIES
        and identity["topology_id"] == TOPOLOGY
        and identity["drive_availability"] == [True] * 4
        and all(type(v) is bool for v in identity["drive_availability"])
        and identity["regen_enabled"] is False
        and identity["role"] == "development"
        and identity["heldout_used"] is False,
        "Exact four-independent AWD/OFF development identity required",
    )


def _bind_checkpoint(value, identity):
    body = _checkpoint(value)
    context = body["context"]
    selected = context["controller_policy"]
    source = context["source"]
    _require(
        body["config_id"] == identity["policy_id"]
        and source["sha256"] == identity["source_sha256"]
        and _digest({k: v for k, v in source.items() if k != "sha256"})
        == identity["source_sha256"]
        and context["configuration_sha256"] == identity["configuration_sha256"]
        and context["course"]["bundle_sha256"] == identity["course_bundle_sha256"]
        and context["reference_line"]["artifact_sha256"] == identity["line_artifact_sha256"]
        and body["context_sha256"] == _digest(context)
        and context["actuation"]["topology_id"] == TOPOLOGY
        and type(context["motor_count"]) is int and context["motor_count"] == 4
        and context["drive_availability"] == [True] * 4
        and all(type(v) is bool for v in context["drive_availability"])
        and selected["id"] == identity["policy_id"]
        and selected["supported_topology"] == TOPOLOGY
        and selected["regen_enabled"] is False
        and selected["campaign_eligible"] is False
        and context["campaign_eligible"] is False,
        "Checkpoint differs from declared AWD/OFF input identity",
    )
    if ("numerical_environment_sha256" in source or
            _PORTABLE_NUMERICAL_FAMILY in (context.get("family"), source.get("family"))):
        environment = source.get("numerical_environment_sha256")
        _require(_sha(environment) and environment == identity["environment_sha256"],
                 "Checkpoint source/environment declarations differ")
    # Matching declarations are not observed runtime or authenticated evidence.
    # Legacy non-portable source formats without E retain storage-only caller
    # declarations; they gain no current execution, environment or data-use trust.
    return body


def _origin(value, identity):
    body = _bind_checkpoint(value, identity)
    _require(
        type(body["tick"]) is int and body["tick"] == 0
        and type(body["segment"]) is int and body["segment"] == 0
        and body["parent_chunk_sha256"] is None and body["status"] == "running",
        "Fresh bridge origin required",
    )


def _transition(prior, chunk, linked, identity):
    before = _bind_checkpoint(prior, identity)
    after = _bind_checkpoint(linked, identity)
    _require(
        type(chunk) is dict and set(chunk) == {"chunk", "chunk_sha256"}
        and chunk["chunk_sha256"] == _digest(chunk["chunk"])
        and len(_encode(chunk)) <= MAX_CHUNK,
        "Exact bounded raw chunk envelope required",
    )
    body = chunk["chunk"]
    _require(
        type(body) is dict and set(body) == CHUNK_FIELDS
        and len(_encode(body)) <= MAX_CHUNK_BODY,
        "Exact bounded raw chunk fields required",
    )
    _require(
        body["schema"] == CHUNK_SCHEMA
        and body["source_sha256"] == identity["source_sha256"]
        and body["config_id"] == identity["policy_id"]
        and body["input_checkpoint_sha256"] == prior["checkpoint_sha256"]
        and body["parent_chunk_sha256"] == before["parent_chunk_sha256"]
        and type(body["start_tick"]) is int and body["start_tick"] == before["tick"]
        and type(body["end_tick"]) is int and body["end_tick"] == after["tick"]
        and body["context_sha256"] == before["context_sha256"]
        and body["course_id"] == before["context"]["course"]["id"]
        and body["status"] == after["status"] and before["status"] == "running"
        and before["tick"] <= body["end_tick"] <= before["tick"] + 10000
        and (body["end_tick"] > before["tick"] or body["status"] == "invalid")
        and body["execution_evidence"] == "RAW_STAGED_REQUIRES_SEPARATE_OWNED_RECEIPT_ADMISSION"
        and body["awards"] == {"points": None, "overall_winner": None},
        "Raw chunk source, order, bounds or status differs",
    )
    expected = deepcopy(body["output_checkpoint"])
    raw_output = _checkpoint(expected)
    _require(
        type(raw_output["segment"]) is int
        and raw_output["segment"] == before["segment"] + 1
        and raw_output["parent_chunk_sha256"] is None
        and raw_output["context_sha256"] == before["context_sha256"],
        "Raw output checkpoint position differs",
    )
    raw_output["parent_chunk_sha256"] = chunk["chunk_sha256"]
    expected["checkpoint_sha256"] = _digest(raw_output)
    _require(
        _encode(expected) == _encode(linked),
        "Linked checkpoint differs from exact raw-output transformation",
    )
    # The original bridge remains responsible for physical/telemetry validation.


class RawJournal:
    """Local raw-evidence store; no execution/admission/resume implementation."""

    def __init__(self, root, expected_manifest_sha256):
        self.root = Path(root).absolute()
        _require(_sha(expected_manifest_sha256), "Externally pinned manifest required")
        self.expected_manifest_sha256 = expected_manifest_sha256
        self._manifest = _read(self.root / "manifest.json", MAX_MANIFEST)
        _require(
            set(self._manifest) == {
                "schema", "identity", "origin", "limits", "sync_files",
                "directory_sync", "evidence_status", "qualification_or_execution_authority",
            }
            and _digest(self._manifest) == expected_manifest_sha256
            and self._manifest["schema"] == MANIFEST_SCHEMA
            and self._manifest["evidence_status"] == RAW_LABEL
            and self._manifest["qualification_or_execution_authority"] is False,
            "Manifest identity differs",
        )
        _validate_identity(self._manifest["identity"])
        limits = self._manifest["limits"]
        _require(
            type(limits) is dict and set(limits) == {
                "maximum_records", "maximum_bytes", "terminal_reserve_bytes",
            }
            and type(limits["maximum_records"]) is int
            and 1 <= limits["maximum_records"] <= MAX_RECORDS
            and type(limits["maximum_bytes"]) is int
            and 4 * 1024 * 1024 <= limits["maximum_bytes"] <= 2**31
            and limits["terminal_reserve_bytes"] == MAX_RECEIPT
            and type(self._manifest["sync_files"]) is bool
            and self._manifest["directory_sync"] in {
                "posix_fsync_requested", "not_available_or_not_requested",
            },
            "Stored journal bounds differ",
        )
        _origin(self._manifest["origin"], self._manifest["identity"])

    @property
    def manifest(self):
        return deepcopy(self._manifest)

    @classmethod
    def create(
        cls, root, identity, initial_checkpoint, *, maximum_records=750,
        maximum_bytes=256 * 1024 * 1024, sync_files=True,
    ):
        _validate_identity(identity)
        _origin(initial_checkpoint, identity)
        _require(
            type(maximum_records) is int and 1 <= maximum_records <= MAX_RECORDS
            and type(maximum_bytes) is int
            and 4 * 1024 * 1024 <= maximum_bytes <= 2**31
            and type(sync_files) is bool,
            "Explicit finite storage bounds required",
        )
        manifest = {
            "schema": MANIFEST_SCHEMA, "identity": deepcopy(identity),
            "origin": deepcopy(initial_checkpoint),
            "limits": {
                "maximum_records": maximum_records, "maximum_bytes": maximum_bytes,
                "terminal_reserve_bytes": MAX_RECEIPT,
            },
            "sync_files": sync_files,
            "directory_sync": (
                "posix_fsync_requested" if sync_files and os.name == "posix"
                else "not_available_or_not_requested"
            ),
            "evidence_status": RAW_LABEL, "qualification_or_execution_authority": False,
        }
        _require(len(_encode(manifest)) <= MAX_MANIFEST, "Manifest exceeds bound")
        root = Path(root).absolute()
        _no_alias(root)
        root.mkdir()  # Existing directories are never reused implicitly.
        (root / "objects").mkdir()
        (root / "records").mkdir()
        _sync_directory(root, sync_files)
        _sync_directory(root.parent, sync_files)
        _write_new(root / "manifest.json", manifest, MAX_MANIFEST, sync_files)
        return cls(root, _digest(manifest))

    def _inventory(self):
        _no_alias(self.root)
        _require(self.root.is_dir(), "Journal directory missing")
        top = set()
        for item in self.root.iterdir():
            top.add(item.name)
            _require(len(top) <= 4, "Unexpected journal entries")
        _require(
            top <= {"manifest.json", "objects", "records", "terminal.json"}
            and {"manifest.json", "objects", "records"} <= top,
            "Unexpected journal entries",
        )
        # Detect an altered manifest rather than trusting the cached copy.
        _require(
            _digest(_read(self.root / "manifest.json", MAX_MANIFEST))
            == self.expected_manifest_sha256,
            "Manifest changed since opening",
        )
        objects, records = {}, {}
        size = (self.root / "manifest.json").stat().st_size
        maximum = self._manifest["limits"]["maximum_records"]
        for dirname, pattern, target, count_limit in (
            ("objects", OBJECT_NAME, objects, 2 * maximum + 2),
            ("records", RECORD_NAME, records, maximum),
        ):
            directory = self.root / dirname
            _no_alias(directory)
            _require(directory.is_dir(), "Journal subdirectory missing")
            for item in directory.iterdir():
                _no_alias(item)
                _require(pattern.fullmatch(item.name) and item.is_file(), "Unexpected journal file")
                target[item.name] = item
                _require(len(target) <= count_limit, "File-count bound exceeded")
                size += item.stat().st_size
        terminal = self.root / "terminal.json"
        if "terminal.json" in top:
            _no_alias(terminal)
            _require(terminal.is_file(), "Terminal must be a regular file")
            size += terminal.stat().st_size
        _require(size <= self._manifest["limits"]["maximum_bytes"], "Journal exceeds byte quota")
        return objects, records, size

    def inspect(self):
        """Separate storage-committed tail from crash-recovery candidates.

        This tail is authoritative only for this journal's storage chain. It is
        not an admitted execution checkpoint and carries no resume authority.
        """
        objects, records, size = self._inventory()
        prior = deepcopy(self._manifest["origin"])
        previous_receipt = None
        referenced, recovery = set(), []
        committed_count = 0
        for sequence, name in enumerate(sorted(records), 1):
            if recovery or name != f"{sequence:06d}.json":
                recovery.append("records/" + name)
                continue
            try:
                envelope = _read(records[name], MAX_RECEIPT)
                _require(
                    type(envelope) is dict and set(envelope) == {"receipt", "receipt_sha256"},
                    "Exact receipt envelope required",
                )
                receipt = envelope["receipt"]
                _require(
                    type(receipt) is dict and set(receipt) == RECEIPT_FIELDS
                    and envelope["receipt_sha256"] == _digest(receipt)
                    and receipt["schema"] == RECORD_SCHEMA
                    and receipt["manifest_sha256"] == self.expected_manifest_sha256
                    and type(receipt["sequence"]) is int and receipt["sequence"] == sequence
                    and receipt["previous_receipt_sha256"] == previous_receipt
                    and receipt["input_checkpoint_sha256"] == prior["checkpoint_sha256"]
                    and receipt["evidence_status"] == RAW_LABEL,
                    "Receipt chain differs",
                )
                names, values = [], []
                for key, bound in (
                    ("chunk_object_sha256", MAX_CHUNK),
                    ("checkpoint_object_sha256", MAX_CHECKPOINT),
                ):
                    object_id = receipt[key]
                    _require(_sha(object_id), "Object identity required")
                    object_name = object_id + ".json"
                    _require(object_name in objects, "Committed object absent")
                    value = _read(objects[object_name], bound)
                    _require(_digest(value) == object_id, "Object digest differs")
                    names.append(object_name)
                    values.append(value)
                chunk, linked = values
                _transition(prior, chunk, linked, self._manifest["identity"])
                _require(
                    receipt["chunk_sha256"] == chunk["chunk_sha256"]
                    and receipt["checkpoint_sha256"] == linked["checkpoint_sha256"],
                    "Receipt content identities differ",
                )
                referenced.update(names)
                prior = linked
                previous_receipt = envelope["receipt_sha256"]
                committed_count += 1
            except (ValueError, KeyError, TypeError, OSError, RecursionError) as error:
                recovery.append("records/" + name + ": " + str(error)[:512])
        recovery.extend("objects/" + name for name in sorted(set(objects) - referenced))
        terminal = None
        terminal_path = self.root / "terminal.json"
        if terminal_path.exists():
            try:
                terminal = _read(terminal_path, MAX_RECEIPT)
                self._validate_terminal(terminal, previous_receipt, prior)
            except (ValueError, KeyError, TypeError, OSError, RecursionError) as error:
                recovery.append("terminal.json: " + str(error)[:512])
                terminal = None
        return {
            "evidence_status": RAW_LABEL,
            "journal_committed_tail": {
                "records": committed_count, "receipt_sha256": previous_receipt,
                "checkpoint": prior,
            },
            "recovery_candidates": recovery, "reconciliation_required": bool(recovery),
            "terminal": None if recovery else terminal,
            "terminal_candidate": terminal if recovery else None,
            "physical_bytes": size,
            "qualification_or_execution_authority": False,
            "power_loss_durability_guaranteed": False,
        }

    def _validate_terminal(self, value, previous_receipt, prior):
        _require(
            type(value) is dict and set(value) == {"terminal", "terminal_sha256"},
            "Exact terminal envelope required",
        )
        body = value["terminal"]
        _require(
            type(body) is dict and set(body) == {
                "schema", "manifest_sha256", "status", "reason", "last_receipt_sha256",
                "checkpoint_sha256", "evidence_status",
            }
            and value["terminal_sha256"] == _digest(body)
            and body["schema"] == TERMINAL_SCHEMA
            and body["manifest_sha256"] == self.expected_manifest_sha256
            and body["status"] in TERMINAL_STATUSES
            and body["last_receipt_sha256"] == previous_receipt
            and body["checkpoint_sha256"] == prior["checkpoint_sha256"]
            and type(body["reason"]) is str and 0 < len(body["reason"]) <= 1024
            and body["evidence_status"] == RAW_LABEL,
            "Terminal consistency differs",
        )
        if body["status"] == "raw_completed":
            _require(prior["checkpoint"]["status"] == "completed", "Raw completion needs completed checkpoint")

    def _writable_state(self):
        state = self.inspect()
        _require(not state["reconciliation_required"], "Recovery candidates require original-owner reconciliation")
        _require(state["terminal"] is None, "Terminal journal is immutable")
        return state

    def append(self, raw_chunk, linked_checkpoint):
        """Persist consistency-validated raw data; never admit or resume it."""
        state = self._writable_state()
        tail = state["journal_committed_tail"]
        sequence = tail["records"] + 1
        _require(sequence <= self._manifest["limits"]["maximum_records"], "Record quota exhausted")
        _transition(tail["checkpoint"], raw_chunk, linked_checkpoint, self._manifest["identity"])
        chunk_id, checkpoint_id = _digest(raw_chunk), _digest(linked_checkpoint)
        receipt = {
            "schema": RECORD_SCHEMA, "manifest_sha256": self.expected_manifest_sha256,
            "sequence": sequence, "previous_receipt_sha256": tail["receipt_sha256"],
            "input_checkpoint_sha256": tail["checkpoint"]["checkpoint_sha256"],
            "chunk_object_sha256": chunk_id, "checkpoint_object_sha256": checkpoint_id,
            "chunk_sha256": raw_chunk["chunk_sha256"],
            "checkpoint_sha256": linked_checkpoint["checkpoint_sha256"],
            "evidence_status": RAW_LABEL,
        }
        envelope = {"receipt": receipt, "receipt_sha256": _digest(receipt)}
        new_objects = []
        for object_id, value, bound in (
            (chunk_id, raw_chunk, MAX_CHUNK),
            (checkpoint_id, linked_checkpoint, MAX_CHECKPOINT),
        ):
            path = self.root / "objects" / (object_id + ".json")
            if path.exists():
                _require(_encode(_read(path, bound)) == _encode(value), "Existing object differs")
            else:
                new_objects.append((path, value, bound))
        added = len(_encode(envelope)) + sum(len(_encode(value)) for _, value, _ in new_objects)
        limits = self._manifest["limits"]
        _require(
            state["physical_bytes"] + added <= limits["maximum_bytes"] - limits["terminal_reserve_bytes"],
            "Byte quota exhausted; terminal reserve preserved",
        )
        sync = self._manifest["sync_files"]
        for path, value, bound in new_objects:
            _write_new(path, value, bound, sync)
        # Receipt is the sole storage-commit point and is written last.
        _write_new(self.root / "records" / f"{sequence:06d}.json", envelope, MAX_RECEIPT, sync)
        return envelope

    def write_terminal(self, status, reason):
        """Close this store without claiming cleanup, admission or continuation.

        paused_budget records cessation too. It does not unlock a resume path;
        an explicitly admitted continuation protocol is outside this candidate.
        """
        _require(status in TERMINAL_STATUSES, "Explicit terminal status required")
        _require(type(reason) is str and 0 < len(reason) <= 1024, "Bounded terminal reason required")
        state = self._writable_state()
        tail = state["journal_committed_tail"]
        body = {
            "schema": TERMINAL_SCHEMA, "manifest_sha256": self.expected_manifest_sha256,
            "status": status, "reason": reason, "last_receipt_sha256": tail["receipt_sha256"],
            "checkpoint_sha256": tail["checkpoint"]["checkpoint_sha256"], "evidence_status": RAW_LABEL,
        }
        value = {"terminal": body, "terminal_sha256": _digest(body)}
        self._validate_terminal(value, tail["receipt_sha256"], tail["checkpoint"])
        _require(
            state["physical_bytes"] + len(_encode(value)) <= self._manifest["limits"]["maximum_bytes"],
            "Terminal byte quota exhausted",
        )
        _write_new(self.root / "terminal.json", value, MAX_RECEIPT, self._manifest["sync_files"])
        return value
