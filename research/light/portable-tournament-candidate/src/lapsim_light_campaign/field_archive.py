"""UNTESTED create-only storage of finalized field DTOs and exact raw packets.

Data inventory only: no journal/terminal/RawCellExport, receipt authentication,
native writer, coordinator restoration or continuation authority. Unadopted
numerical payloads stay opaque. Source/receipt hashes prove consistency only.
Invoke I/O only under the original owner's actual writer/path exclusion, finite
allocation and cleanup controls. Requested fsync is not universal durability.
"""

from dataclasses import dataclass, fields, replace
from hashlib import sha256
import os
from pathlib import Path
import stat

from . import raw_journal as journal
from .dispatch_request import MAX_REQUEST_BYTES
from .field_dispatch import (MAX_FIELD_CALLS, MAX_RESULT_PAYLOAD_BYTES,
    FieldCellProgress, FieldDispatchAttempt, FieldDispatchSnapshot, _charged_bytes, _payload_bytes, _work)
from .guarded_dispatch import (MAX_OWNED_RECEIPT_BYTES, OwnedChunkResult,
    _require_chunk_checkpoint_binding, require_owned_result_bytes, validate_staged_request)
from .input_contracts import decode, encode, exact, is_sha256, require
from .tournament_plan import MAX_PLAN_BYTES, validate_tournament_plan


SCHEMA = "lapsim.light-finalized-field-packet-archive.data.v1"
MAX_METADATA_BYTES = 16 * 1024 * 1024
MAX_OBJECTS = 8 + 4 * MAX_FIELD_CALLS
MAX_BLOB_BYTES = max(MAX_PLAN_BYTES, MAX_REQUEST_BYTES, journal.MAX_CHUNK,
                     journal.MAX_CHECKPOINT, MAX_OWNED_RECEIPT_BYTES)
_SCALARS = tuple(f.name for f in fields(FieldDispatchSnapshot) if f.name not in ("plan_raw", "cells", "attempts"))
_ATTEMPT_SCALARS = tuple(f.name for f in fields(FieldDispatchAttempt) if f.name not in ("request_raw", "result"))


@dataclass(frozen=True, slots=True)
class PreparedFieldArchive:
    """Preflight bytes/pin, not a capability. Retain its pin before any write."""
    archive_raw: bytes
    archive_sha256: str
    objects: tuple[tuple[str, bytes], ...]
    maximum_archive_bytes: int

    @property
    def qualification_or_execution_authority(self):
        return False


@dataclass(frozen=True, slots=True)
class FieldArchiveData:
    archive_sha256: str
    snapshot: FieldDispatchSnapshot
    physical_file_bytes: int
    file_sync_requested: bool  # Stored request, never proof that a flush succeeded.

    @property
    def qualification_or_execution_authority(self):
        return False

    @property
    def power_loss_durability_guaranteed(self):
        return False


def _cap(value):
    require(type(value) is int and 1 <= value <= 2**31, "Explicit bounded archive-file byte cap required")


def _equal_fields(value, expected):
    for name, item in expected.items():
        actual = getattr(value, name)
        require(type(actual) is type(item) and actual == item, "Field metadata differs: " + name)


def _validate_snapshot(snapshot):
    """Reconstruct RAW metadata only; invoke no provider or numerical bridge."""
    require(type(snapshot) is FieldDispatchSnapshot, "Exact immutable field snapshot required")
    plan = validate_tournament_plan(snapshot.plan_raw, expected_plan_sha256=snapshot.plan_sha256)
    require(is_sha256(snapshot.original_provider_sha256), "Declared original-provider pin required; not authentication")
    require(type(snapshot.sealed) is bool and type(snapshot.cells) is tuple and len(snapshot.cells) == 7 and
            all(type(cell) is FieldCellProgress and type(cell.policy_id) is str and type(cell.status) is str and
                type(cell.checkpoint_raw) is bytes and 0 < len(cell.checkpoint_raw) <= journal.MAX_CHECKPOINT
                for cell in snapshot.cells) and type(snapshot.attempts) is tuple and
            len(snapshot.attempts) <= MAX_FIELD_CALLS, "Exact bounded native field DTO tuples required")
    require(type(snapshot.requested_wall_time_cap_ms) is int and 1 <= snapshot.requested_wall_time_cap_ms <= 2**63 - 1,
            "Original finite proposed-wall-time cap required")
    _cap(snapshot.retained_history_payload_cap_bytes)
    cells = [FieldCellProgress(cell["policy_id"], "missing", encode(cell["origin"])) for cell in plan["cells"]]
    prior, nonces, requests = [], set(), set()
    last_index = None
    failure_reason = None
    for position, attempt in enumerate(snapshot.attempts):
        require(type(attempt) is FieldDispatchAttempt and type(attempt.checkpoint_adopted) is bool,
                "Exact immutable field attempt required")
        index = next((i for i, cell in enumerate(cells) if cell.status != "completed"), None)
        require(index is not None and failure_reason is None, "Attempt follows completed or failed field")
        cell = cells[index]
        body = validate_staged_request(attempt.request_raw, cell.checkpoint_raw,
                                      expected_request_sha256=attempt.request_sha256)
        require(encode(body["identity"]) == encode(plan["cells"][index]["identity"]), "Attempt changed frozen cell identity")
        proposed, resources = body["chunk_plan"]["plan"], body["resource_request"]
        _equal_fields(attempt, {"policy_id": cell.policy_id, "request_nonce": body["request_nonce"],
            "parent_checkpoint_sha256": proposed["parent_checkpoint_sha256"], "requested_ticks": proposed["requested_ticks"],
            "maximum_new_ticks": proposed["maximum_new_ticks"], "maximum_new_work": proposed["maximum_new_work"],
            "requested_wall_time_ms": resources["maximum_wall_time_ms"], "requested_rss_bytes": resources["maximum_rss_bytes"]})
        require(attempt.request_sha256 not in requests and attempt.request_nonce not in nonces, "Reused local request/nonce")
        requests.add(attempt.request_sha256)
        nonces.add(attempt.request_nonce)
        require(sum(item.requested_wall_time_ms for item in prior) + attempt.requested_wall_time_ms <= snapshot.requested_wall_time_cap_ms,
                "Consumed requests exceed original wall proposal cap")
        require(sum(_charged_bytes(item) for item in prior) + len(attempt.request_raw) + MAX_RESULT_PAYLOAD_BYTES <=
                snapshot.retained_history_payload_cap_bytes, "Original full-result reservation was unavailable")
        if attempt.result is not None:
            require(type(attempt.result) is OwnedChunkResult and
                    all(is_sha256(getattr(attempt.result, name)) for name in
                        ("request_sha256", "source_sha256", "receipt_bundle_sha256")), "Exact raw result pin strings required")
            require_owned_result_bytes(attempt.result, body, attempt.request_sha256)
        if attempt.checkpoint_adopted:
            require(attempt.result is not None, "Adoption requires a returned packet")
            result = attempt.result
            _require_chunk_checkpoint_binding(body, cell.checkpoint_raw, result.raw_chunk_json, result.linked_checkpoint_json)
            output = decode(result.linked_checkpoint_json, journal.MAX_CHECKPOINT, canonical=True)["checkpoint"]
            limits = output["context"]["limits"]
            require(output["tick"] <= limits["maximum_ticks"] and _work(output) <= limits["maximum_work"], "Adopted mission ceiling exceeded")
            cells[index] = FieldCellProgress(cell.policy_id, output["status"], result.linked_checkpoint_json)
            checkpoints = [decode(item.checkpoint_raw, journal.MAX_CHECKPOINT, canonical=True)["checkpoint"] for item in cells]
            require(sum(item["tick"] for item in checkpoints) <= plan["request_ceilings"]["maximum_total_simulated_ticks"] and
                    sum(_work(item) for item in checkpoints) <= plan["request_ceilings"]["maximum_total_work"], "Adopted field ceiling exceeded")
            if output["status"] not in ("running", "completed"):
                failure_reason = "returned_terminal_numerical_status_" + output["status"]
        else:
            # Do not decode unadopted numerical bytes or demand adoption validity.
            cells[index] = replace(cell, status="dispatch_failed")
            failure_reason = "consumed_dispatch_failed_or_interrupted"
        prior.append(attempt)
        last_index = index
        if failure_reason is not None:
            require(position == len(snapshot.attempts) - 1, "Failed field cannot have later attempts")
    if last_index is not None and snapshot.cells[last_index].status == "dispatch_failed":
        cells[last_index] = replace(cells[last_index], status="dispatch_failed")
        failure_reason = "consumed_dispatch_failed_or_interrupted"
    require(snapshot.cells == tuple(cells), "Stored cells differ from exact adopted-parent progression")
    require(snapshot.sealed or all(cell.status == "completed" for cell in cells), "Only idle finalized snapshots may be archived")
    expected_reason = failure_reason or ("caller_local_seal_no_os_action" if snapshot.sealed else None)
    require(failure_reason is None or snapshot.sealed, "Failed snapshot must be locally sealed")
    checkpoints = [decode(cell.checkpoint_raw, journal.MAX_CHECKPOINT, canonical=True)["checkpoint"] for cell in cells]
    _equal_fields(snapshot, {"next_policy_id": None, "seal_reason": expected_reason,
        "requested_wall_time_ms": sum(item.requested_wall_time_ms for item in prior),
        "requested_ticks": sum(item.requested_ticks for item in prior),
        "requested_new_tick_ceiling_sum": sum(item.maximum_new_ticks for item in prior),
        "requested_new_work_ceiling_sum": sum(item.maximum_new_work for item in prior),
        "requested_peak_rss_bytes": max((item.requested_rss_bytes for item in prior), default=0),
        "retained_history_payload_bytes": sum(_payload_bytes(item) for item in prior),
        "charged_history_payload_bytes": sum(_charged_bytes(item) for item in prior),
        "accepted_ticks": sum(item["tick"] for item in checkpoints), "accepted_work": sum(_work(item) for item in checkpoints),
        "unresolved_dispatches": sum(not item.checkpoint_adopted for item in prior)})


def _describe(snapshot, sync_files):
    blobs = {}
    def keep(raw):
        require(type(raw) is bytes and 0 < len(raw) <= MAX_BLOB_BYTES, "Bounded immutable packet bytes required")
        key = sha256(raw).hexdigest()
        require(key not in blobs or blobs[key] == raw, "Conflicting raw object hash")
        blobs[key] = raw
        return key
    attempts = []
    for attempt in snapshot.attempts:
        result = attempt.result
        packet = None if result is None else {"request_sha256": result.request_sha256, "source_sha256": result.source_sha256,
            "raw_chunk_json": keep(result.raw_chunk_json), "linked_checkpoint_json": keep(result.linked_checkpoint_json),
            "receipt_bundle_raw": keep(result.receipt_bundle_raw), "receipt_bundle_sha256": result.receipt_bundle_sha256}
        attempts.append({"metadata": {name: getattr(attempt, name) for name in _ATTEMPT_SCALARS},
                         "request_raw": keep(attempt.request_raw), "result": packet})
    data = {"metadata": {name: getattr(snapshot, name) for name in _SCALARS}, "plan_raw": keep(snapshot.plan_raw),
        "cells": [{"policy_id": cell.policy_id, "status": cell.status, "checkpoint_raw": keep(cell.checkpoint_raw)} for cell in snapshot.cells],
        "attempts": attempts}
    value = {"schema": SCHEMA, "snapshot": data, "objects": {key: len(raw) for key, raw in sorted(blobs.items())},
        "file_sync_requested": sync_files, "power_loss_durability_guaranteed": False, "qualification_or_execution_authority": False}
    raw = encode(value)
    require(len(blobs) <= MAX_OBJECTS and len(raw) <= MAX_METADATA_BYTES, "Archive object/metadata bound exceeded")
    return raw, blobs


def _restore(value, blobs):
    def get(key, maximum):
        require(is_sha256(key) and key in blobs and len(blobs[key]) <= maximum, "Missing or oversized raw packet reference")
        return blobs[key]
    data = value["snapshot"]
    exact(data, {"metadata", "plan_raw", "cells", "attempts"}, "snapshot data")
    exact(data["metadata"], _SCALARS, "snapshot scalar metadata")
    require(type(data["cells"]) is list and len(data["cells"]) == 7 and type(data["attempts"]) is list and
            len(data["attempts"]) <= MAX_FIELD_CALLS, "Bounded snapshot rows required")
    cells, attempts = [], []
    for cell in data["cells"]:
        exact(cell, {"policy_id", "status", "checkpoint_raw"}, "cell data")
        cells.append(FieldCellProgress(cell["policy_id"], cell["status"], get(cell["checkpoint_raw"], journal.MAX_CHECKPOINT)))
    for attempt in data["attempts"]:
        exact(attempt, {"metadata", "request_raw", "result"}, "attempt data")
        exact(attempt["metadata"], _ATTEMPT_SCALARS, "attempt scalar metadata")
        packet = attempt["result"]
        result = None
        if packet is not None:
            exact(packet, {"request_sha256", "source_sha256", "raw_chunk_json", "linked_checkpoint_json", "receipt_bundle_raw", "receipt_bundle_sha256"}, "returned packet")
            result = OwnedChunkResult(packet["request_sha256"], packet["source_sha256"], get(packet["raw_chunk_json"], journal.MAX_CHUNK),
                get(packet["linked_checkpoint_json"], journal.MAX_CHECKPOINT), get(packet["receipt_bundle_raw"], MAX_OWNED_RECEIPT_BYTES), packet["receipt_bundle_sha256"])
        attempts.append(FieldDispatchAttempt(**attempt["metadata"], request_raw=get(attempt["request_raw"], MAX_REQUEST_BYTES), result=result))
    return FieldDispatchSnapshot(**data["metadata"], plan_raw=get(data["plan_raw"], MAX_PLAN_BYTES), cells=tuple(cells), attempts=tuple(attempts))


def prepare_field_archive(snapshot, *, maximum_archive_bytes, sync_files=True):
    """Pure byte preflight. Retain the returned raw inventory pin before I/O."""
    _cap(maximum_archive_bytes)
    require(type(sync_files) is bool, "Explicit file-sync request required")
    _validate_snapshot(snapshot)
    raw, blobs = _describe(snapshot, sync_files)
    require(len(raw) + sum(map(len, blobs.values())) <= maximum_archive_bytes, "Complete archive exceeds byte cap; no files created")
    return PreparedFieldArchive(raw, sha256(raw).hexdigest(), tuple(sorted(blobs.items())), maximum_archive_bytes)


def _header(raw, maximum_archive_bytes):
    _cap(maximum_archive_bytes)
    value = decode(raw, MAX_METADATA_BYTES, canonical=True)
    exact(value, {"schema", "snapshot", "objects", "file_sync_requested", "power_loss_durability_guaranteed", "qualification_or_execution_authority"}, "archive data inventory")
    require(value["schema"] == SCHEMA and type(value["file_sync_requested"]) is bool and
            value["power_loss_durability_guaranteed"] is False and value["qualification_or_execution_authority"] is False,
            "Archive is RAW data only")
    require(type(value["objects"]) is dict and len(value["objects"]) <= MAX_OBJECTS and
            all(is_sha256(key) and type(size) is int and 0 < size <= MAX_BLOB_BYTES
            for key, size in value["objects"].items()), "Bounded raw object declarations required")
    require(len(raw) + sum(value["objects"].values()) <= maximum_archive_bytes, "Complete archive exceeds external byte cap")
    return value


def _unpack(raw, blobs, maximum_archive_bytes):
    value = _header(raw, maximum_archive_bytes)
    exact(blobs, value["objects"], "complete raw object inventory")
    require(all(type(blob) is bytes and len(blob) == value["objects"][key] and sha256(blob).hexdigest() == key
                for key, blob in blobs.items()), "Raw object bytes differ")
    snapshot = _restore(value, blobs)
    _validate_snapshot(snapshot)
    rebuilt, used = _describe(snapshot, value["file_sync_requested"])
    require(rebuilt == raw and used == blobs, "Inventory has unknown objects or differs from complete DTO reconstruction")
    return FieldArchiveData(sha256(raw).hexdigest(), snapshot, len(raw) + sum(map(len, blobs.values())), value["file_sync_requested"])


def _directory(path):
    journal._no_alias(path)
    require(stat.S_ISDIR(path.lstat().st_mode), "Regular archive directory required")


def _names(path, maximum):
    _directory(path)
    names = set()
    for item in path.iterdir():
        names.add(item.name)
        require(len(names) <= maximum, "Archive entry count exceeded")
    return names


def _layout(root, keys, *, committed):
    require(_names(root, 2) == ({"objects", "archive.json"} if committed else {"objects"}), "Incomplete or unknown archive layout")
    require(_names(root / "objects", MAX_OBJECTS) == {key + ".bin" for key in keys}, "Missing/orphan archive objects require reconciliation")


def _read_raw(path, maximum):
    journal._no_alias(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and getattr(info, "st_nlink", 0) == 1, "Regular single-link archive file required")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    require(0 < len(raw) <= maximum, "Archive file byte bound exceeded")
    return raw


def _write_blob(path, raw, sync):
    journal._no_alias(path)
    with path.open("xb") as stream:
        require(stream.write(raw) == len(raw), "Incomplete raw object write; preserve partial file")
        stream.flush()
        if sync:
            os.fsync(stream.fileno())
    journal._sync_directory(path.parent, sync)


def write_field_archive(root, prepared):
    """Create once under original owner controls; preserve every partial on error.

    A final write/flush exception has uncertain outcome. Do not retry this root;
    use separate explicit readback with the already retained external pin.
    No candidate call here acquires a lease or authenticates original receipts.
    """
    require(type(prepared) is PreparedFieldArchive and type(prepared.archive_raw) is bytes and
            0 < len(prepared.archive_raw) <= MAX_METADATA_BYTES and type(prepared.objects) is tuple and
            len(prepared.objects) <= MAX_OBJECTS and all(type(item) is tuple and len(item) == 2 and
                is_sha256(item[0]) and type(item[1]) is bytes and 0 < len(item[1]) <= MAX_BLOB_BYTES for item in prepared.objects),
            "Exact bounded preflight data required")
    blobs = dict(prepared.objects)
    require(len(blobs) == len(prepared.objects) and is_sha256(prepared.archive_sha256) and
            sha256(prepared.archive_raw).hexdigest() == prepared.archive_sha256, "Preflight pin/objects differ")
    data = _unpack(prepared.archive_raw, blobs, prepared.maximum_archive_bytes)
    root = Path(root).absolute()
    journal._no_alias(root)
    root.mkdir()  # Existing/partial roots are never reused or repaired implicitly.
    (root / "objects").mkdir()
    journal._sync_directory(root, data.file_sync_requested)
    journal._sync_directory(root.parent, data.file_sync_requested)
    for key, blob in sorted(blobs.items()):
        _write_blob(root / "objects" / (key + ".bin"), blob, data.file_sync_requested)
    _layout(root, blobs, committed=False)
    require(all(_read_raw(root / "objects" / (key + ".bin"), len(blob)) == blob for key, blob in blobs.items()), "Object readback differs; no inventory committed")
    # Existing canonical exclusive writer; inventory is the final file.
    journal._write_new(root / "archive.json", decode(prepared.archive_raw, MAX_METADATA_BYTES, canonical=True),
                       MAX_METADATA_BYTES, data.file_sync_requested)
    return read_field_archive(root, expected_archive_sha256=prepared.archive_sha256,
                              maximum_archive_bytes=prepared.maximum_archive_bytes)


def read_field_archive(root, *, expected_archive_sha256, maximum_archive_bytes):
    """Verify data/readability under real writer exclusion, never restore execution.

    Checks observed bytes/layout, not hostile-writer atomicity or power-loss
    durability. No file is modified, no opaque receipt is authenticated, and no
    unadopted numerical payload is parsed/promoted.
    """
    _cap(maximum_archive_bytes)
    require(is_sha256(expected_archive_sha256), "Externally retained raw inventory-file pin required")
    root = Path(root).absolute()
    raw = _read_raw(root / "archive.json", min(MAX_METADATA_BYTES, maximum_archive_bytes))
    require(sha256(raw).hexdigest() == expected_archive_sha256, "Archive inventory pin differs")
    value = _header(raw, maximum_archive_bytes)
    objects = value["objects"]
    _layout(root, objects, committed=True)
    blobs = {key: _read_raw(root / "objects" / (key + ".bin"), size) for key, size in objects.items()}
    data = _unpack(raw, blobs, maximum_archive_bytes)
    require(_read_raw(root / "archive.json", len(raw)) == raw, "Archive inventory changed during readback")
    _layout(root, objects, committed=True)
    return data
