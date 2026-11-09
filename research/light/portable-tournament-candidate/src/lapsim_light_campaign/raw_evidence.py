"""UNTESTED raw-journal export and storage-chain replay, with no plant calls.

This module verifies local consistency only. No result grants qualification,
execution admission, cleanup approval, resume authority or a resource lease.
The owning caller must retain its original exclusive writer/resource controls.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from . import raw_journal as journal


EXPORT_SCHEMA = "lapsim.light-raw-evidence.export.v1"
MAX_EXPORT_BYTES = 64 * 1024 * 1024
# Leave explicit room for export keys/structure around the journal's raw bytes.
MAX_SOURCE_BYTES = MAX_EXPORT_BYTES - 1024 * 1024
_EXPORT_FIELDS = frozenset({
    "schema", "manifest", "manifest_sha256", "records", "objects", "terminal",
    "evidence_status", "qualification_or_execution_authority", "numerical_replay_performed",
})


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _manifest(value, expected_sha256):
    """Mirror the pinned journal's manifest gate without filesystem access."""
    _require(
        type(value) is dict and set(value) == {
            "schema", "identity", "origin", "limits", "sync_files",
            "directory_sync", "evidence_status", "qualification_or_execution_authority",
        }
        and len(journal._encode(value)) <= journal.MAX_MANIFEST
        and journal._digest(value) == expected_sha256
        and value["schema"] == journal.MANIFEST_SCHEMA
        and value["evidence_status"] == journal.RAW_LABEL
        and value["qualification_or_execution_authority"] is False,
        "Export manifest identity differs",
    )
    journal._validate_identity(value["identity"])
    limits = value["limits"]
    _require(
        type(limits) is dict and set(limits) == {
            "maximum_records", "maximum_bytes", "terminal_reserve_bytes",
        }
        and type(limits["maximum_records"]) is int
        and 1 <= limits["maximum_records"] <= journal.MAX_RECORDS
        and type(limits["maximum_bytes"]) is int
        and 4 * 1024 * 1024 <= limits["maximum_bytes"] <= 2**31
        and limits["terminal_reserve_bytes"] == journal.MAX_RECEIPT
        and type(value["sync_files"]) is bool
        and value["directory_sync"] in {
            "posix_fsync_requested", "not_available_or_not_requested",
        },
        "Export journal bounds differ",
    )
    journal._origin(value["origin"], value["identity"])


def _terminal(value, manifest_sha256, last_receipt_sha256, checkpoint):
    """Retain the pinned raw terminal rules; no terminal reopens a journal."""
    if value is None:
        return
    _require(
        type(value) is dict and set(value) == {"terminal", "terminal_sha256"}
        and len(journal._encode(value)) <= journal.MAX_RECEIPT,
        "Exact bounded raw terminal required",
    )
    body = value["terminal"]
    _require(
        type(body) is dict and set(body) == {
            "schema", "manifest_sha256", "status", "reason", "last_receipt_sha256",
            "checkpoint_sha256", "evidence_status",
        }
        and value["terminal_sha256"] == journal._digest(body)
        and body["schema"] == journal.TERMINAL_SCHEMA
        and body["manifest_sha256"] == manifest_sha256
        and body["status"] in journal.TERMINAL_STATUSES
        and body["last_receipt_sha256"] == last_receipt_sha256
        and body["checkpoint_sha256"] == checkpoint["checkpoint_sha256"]
        and type(body["reason"]) is str and 0 < len(body["reason"]) <= 1024
        and body["evidence_status"] == journal.RAW_LABEL,
        "Export terminal chain differs",
    )
    if body["status"] == "raw_completed":
        _require(checkpoint["checkpoint"]["status"] == "completed",
                 "Raw completion requires a completed checkpoint")


def _replay(bundle, expected_bundle_sha256, expected_manifest_sha256):
    _require(journal._sha(expected_bundle_sha256) and journal._sha(expected_manifest_sha256),
             "Externally pinned bundle and manifest digests required")
    _require(
        type(bundle) is dict and set(bundle) == {"bundle", "bundle_sha256"}
        and len(journal._encode(bundle)) <= MAX_EXPORT_BYTES
        and type(bundle["bundle"]) is dict
        and set(bundle["bundle"]) == _EXPORT_FIELDS
        and bundle["bundle_sha256"] == expected_bundle_sha256
        and journal._digest(bundle["bundle"]) == expected_bundle_sha256,
        "Raw export envelope, identity or size differs",
    )
    body = bundle["bundle"]
    _require(
        body["schema"] == EXPORT_SCHEMA
        and body["manifest_sha256"] == expected_manifest_sha256
        and body["evidence_status"] == journal.RAW_LABEL
        and body["qualification_or_execution_authority"] is False
        and body["numerical_replay_performed"] is False,
        "Raw export scope differs",
    )
    manifest = body["manifest"]
    _manifest(manifest, expected_manifest_sha256)
    records, objects = body["records"], body["objects"]
    _require(
        type(records) is list and len(records) <= manifest["limits"]["maximum_records"]
        and type(objects) is dict and len(objects) <= 2 * len(records)
        and all(journal._sha(key) for key in objects),
        "Bounded committed records and objects required",
    )
    prior = manifest["origin"]
    previous_receipt = None
    referenced = set()
    for sequence, envelope in enumerate(records, 1):
        _require(
            type(envelope) is dict and set(envelope) == {"receipt", "receipt_sha256"}
            and len(journal._encode(envelope)) <= journal.MAX_RECEIPT,
            "Exact bounded raw receipt required",
        )
        receipt = envelope["receipt"]
        _require(
            type(receipt) is dict and set(receipt) == journal.RECEIPT_FIELDS
            and envelope["receipt_sha256"] == journal._digest(receipt)
            and receipt["schema"] == journal.RECORD_SCHEMA
            and receipt["manifest_sha256"] == expected_manifest_sha256
            and type(receipt["sequence"]) is int and receipt["sequence"] == sequence
            and receipt["previous_receipt_sha256"] == previous_receipt
            and receipt["input_checkpoint_sha256"] == prior["checkpoint_sha256"]
            and receipt["evidence_status"] == journal.RAW_LABEL,
            "Export receipt chain differs",
        )
        values = []
        for key, bound in (("chunk_object_sha256", journal.MAX_CHUNK),
                           ("checkpoint_object_sha256", journal.MAX_CHECKPOINT)):
            object_id = receipt[key]
            _require(journal._sha(object_id) and object_id in objects,
                     "Referenced raw object is missing")
            value = objects[object_id]
            _require(len(journal._encode(value)) <= bound and journal._digest(value) == object_id,
                     "Raw object bound or digest differs")
            referenced.add(object_id)
            values.append(value)
        chunk, linked = values
        journal._transition(prior, chunk, linked, manifest["identity"])
        _require(receipt["chunk_sha256"] == chunk["chunk_sha256"] and
                 receipt["checkpoint_sha256"] == linked["checkpoint_sha256"],
                 "Raw receipt content identities differ")
        prior = linked
        previous_receipt = envelope["receipt_sha256"]
    _require(referenced == set(objects), "Unreferenced objects cannot be promoted into committed export")
    _terminal(body["terminal"], expected_manifest_sha256, previous_receipt, prior)
    physical_bytes = (len(journal._encode(manifest))
                      + sum(len(journal._encode(value)) for value in records)
                      + sum(len(journal._encode(value)) for value in objects.values())
                      + (0 if body["terminal"] is None else len(journal._encode(body["terminal"]))))
    _require(physical_bytes <= manifest["limits"]["maximum_bytes"],
             "Exported journal exceeds its declared storage quota")
    return {
        "evidence_status": journal.RAW_LABEL,
        "replay_scope": "STORAGE_CHAIN_CONSISTENCY_ONLY",
        "bundle_sha256": expected_bundle_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "records": len(records), "receipt_sha256": previous_receipt,
        "physical_bytes": physical_bytes,
        "checkpoint": deepcopy(prior), "terminal": deepcopy(body["terminal"]),
        "qualification_or_execution_authority": False,
        "physical_validation_performed": False, "numerical_replay_performed": False,
    }


def replay_raw_bundle(bundle, *, expected_bundle_sha256, expected_manifest_sha256):
    """Verify full storage lineage in memory; never execute plant/controller code."""
    try:
        return _replay(bundle, expected_bundle_sha256, expected_manifest_sha256)
    except (KeyError, TypeError, OverflowError, RecursionError) as error:
        raise ValueError("Malformed raw evidence export") from error


def snapshot_raw_journal(root, *, expected_manifest_sha256):
    """Read a bounded consistent journal while its owner excludes other writers.

    A second inspection detects observed changes; it is not a replacement lock
    or an atomic snapshot against a hostile writer. No journal file is changed.
    """
    store = journal.RawJournal(root, expected_manifest_sha256)
    state = store.inspect()
    _require(not state["reconciliation_required"], "Reconcile torn/orphan evidence before committed export")
    _require(state["physical_bytes"] <= MAX_SOURCE_BYTES, "Journal exceeds explicit export byte cap")
    objects, records, physical_bytes = store._inventory()
    _require(physical_bytes == state["physical_bytes"], "Journal changed during export")
    exported_records, exported_objects = [], {}
    for name in sorted(records):
        receipt = journal._read(records[name], journal.MAX_RECEIPT)
        exported_records.append(receipt)
        for key, bound in (("chunk_object_sha256", journal.MAX_CHUNK),
                           ("checkpoint_object_sha256", journal.MAX_CHECKPOINT)):
            object_id = receipt["receipt"][key]
            _require(journal._sha(object_id) and object_id + ".json" in objects,
                     "Journal changed during object export")
            if object_id not in exported_objects:
                exported_objects[object_id] = journal._read(objects[object_id + ".json"], bound)
    body = {
        "schema": EXPORT_SCHEMA, "manifest": store.manifest,
        "manifest_sha256": expected_manifest_sha256,
        "records": exported_records, "objects": exported_objects, "terminal": state["terminal"],
        "evidence_status": journal.RAW_LABEL,
        "qualification_or_execution_authority": False, "numerical_replay_performed": False,
    }
    bundle = {"bundle": body, "bundle_sha256": journal._digest(body)}
    summary = replay_raw_bundle(bundle, expected_bundle_sha256=bundle["bundle_sha256"],
                                expected_manifest_sha256=expected_manifest_sha256)
    _require(summary["physical_bytes"] == state["physical_bytes"],
             "Exported raw bytes differ from journal inventory")
    _require(store.inspect() == state, "Journal changed during export; no stable snapshot")
    return bundle


def write_raw_export(path, bundle, *, expected_bundle_sha256, expected_manifest_sha256,
                     sync_files=True):
    """Exclusive-create a verified raw export; retain partial output on I/O error."""
    _require(type(sync_files) is bool, "Explicit file-sync choice required")
    replay_raw_bundle(bundle, expected_bundle_sha256=expected_bundle_sha256,
                      expected_manifest_sha256=expected_manifest_sha256)
    output = Path(path).absolute()
    journal._write_new(output, bundle, MAX_EXPORT_BYTES, sync_files)
    return output


def read_raw_export(path, *, expected_bundle_sha256, expected_manifest_sha256):
    """Read canonical, bounded saved evidence and check its external digest pins."""
    try:
        bundle = journal._read(Path(path).absolute(), MAX_EXPORT_BYTES)
    except (KeyError, TypeError, OverflowError, RecursionError) as error:
        raise ValueError("Malformed raw evidence export") from error
    replay_raw_bundle(bundle, expected_bundle_sha256=expected_bundle_sha256,
                      expected_manifest_sha256=expected_manifest_sha256)
    return bundle
