"""UNTESTED raw child-lineage consistency and read-only continuation snapshots.

No authentication, numerical imports, provider calls, writes or recovery. The
real owner must exclude writers and admit lineage/history separately. Repeated
reads detect observed changes; they do not supply a hostile-writer atomic lock.
"""
from hashlib import sha256
from pathlib import Path

from . import raw_journal as journal
from .continuation import ANCESTRY_SCHEMA, validate_continuation_request
from .guarded_dispatch import MAX_OWNED_RECEIPT_BYTES
from .input_contracts import decode, digest, encode, exact, is_sha256, require
from .raw_evidence import MAX_EXPORT_BYTES, replay_raw_bundle, snapshot_raw_journal


_ANCESTRY_FIELDS = frozenset({
    "schema", "continuation", "external_owned_admission_sha256", "child_manifest_sha256",
    "copied_prefix_records", "copied_prefix_receipt_sha256", "copied_prefix_checkpoint_sha256",
    "history_credit", "evidence_status", "qualification_or_execution_authority",
})
_OUTER_ENTRIES = frozenset({"ancestry.json", "owned-admission.bin", "journal"})


def _ancestry(raw, expected_ancestry_sha256):
    value = decode(raw, journal.MAX_MANIFEST, canonical=True)
    exact(value, {"ancestry", "ancestry_sha256"}, "raw continuation ancestry envelope")
    body = value["ancestry"]
    exact(body, _ANCESTRY_FIELDS, "raw continuation ancestry")
    require(is_sha256(expected_ancestry_sha256) and
            value["ancestry_sha256"] == expected_ancestry_sha256 == digest(body) and
            body["schema"] == ANCESTRY_SCHEMA and body["evidence_status"] == journal.RAW_LABEL and
            body["qualification_or_execution_authority"] is False and
            body["history_credit"] == "COPIED_ORIGINAL_HISTORY_NOT_NEW_EXECUTION" and
            type(body["copied_prefix_records"]) is int and
            1 <= body["copied_prefix_records"] < journal.MAX_RECORDS and
            all(is_sha256(body[name]) for name in ("external_owned_admission_sha256", "child_manifest_sha256",
                                                  "copied_prefix_receipt_sha256", "copied_prefix_checkpoint_sha256")),
            "Exact externally pinned raw child ancestry required")
    return value


def validate_raw_child_archive(ancestry_raw, owned_admission_raw, predecessor_bundle_raw,
                               historical_owned_receipts_raw, child_bundle_raw, *,
                               expected_ancestry_sha256, expected_continuation_sha256,
                               expected_child_bundle_sha256):
    """Check complete parent/prefix/child bytes; never authenticate or award credit.

    The predecessor export and historical evidence are separate required inputs:
    the ancestry file contains their digests, not their original contents.
    Parent and child storage receipts may differ after manifest reconstruction.
    """
    envelope = _ancestry(ancestry_raw, expected_ancestry_sha256)
    ancestry = envelope["ancestry"]
    request, parent, parent_tail, _ = validate_continuation_request(
        encode(ancestry["continuation"]), predecessor_bundle_raw, historical_owned_receipts_raw,
        expected_continuation_sha256=expected_continuation_sha256)
    require(type(owned_admission_raw) is bytes and 0 < len(owned_admission_raw) <= MAX_OWNED_RECEIPT_BYTES and
            sha256(owned_admission_raw).hexdigest() == ancestry["external_owned_admission_sha256"],
            "Exact external admission bytes required; a hash match does not establish authentication")
    child = decode(child_bundle_raw, MAX_EXPORT_BYTES, canonical=True)
    child_tail = replay_raw_bundle(child, expected_bundle_sha256=expected_child_bundle_sha256,
                                   expected_manifest_sha256=ancestry["child_manifest_sha256"])
    original, current = parent["bundle"], child["bundle"]
    copied = parent_tail["records"]
    require(ancestry["copied_prefix_records"] == copied <= child_tail["records"] and
            current["manifest"]["limits"]["maximum_records"] > copied and
            encode(current["manifest"]["identity"]) == encode(original["manifest"]["identity"]) and
            encode(current["manifest"]["origin"]) == encode(original["manifest"]["origin"]),
            "Child origin, identity or copied-prefix extent differs")
    for parent_record, child_record in zip(original["records"], current["records"][:copied]):
        for name in ("chunk_object_sha256", "checkpoint_object_sha256"):
            parent_object = original["objects"][parent_record["receipt"][name]]
            child_object = current["objects"][child_record["receipt"][name]]
            require(encode(parent_object) == encode(child_object),
                    "Child copied prefix changed original raw chunk/checkpoint bytes")
    prefix_receipt = current["records"][copied - 1]
    prefix_checkpoint = current["objects"][prefix_receipt["receipt"]["checkpoint_object_sha256"]]
    require(ancestry["copied_prefix_receipt_sha256"] == prefix_receipt["receipt_sha256"] and
            ancestry["copied_prefix_checkpoint_sha256"] == prefix_checkpoint["checkpoint_sha256"] ==
            parent_tail["checkpoint"]["checkpoint_sha256"] and
            encode(prefix_checkpoint) == encode(parent_tail["checkpoint"]),
            "Ancestry must bind the child's prefix receipt and exact predecessor checkpoint")
    return {
        "scope": "RAW_CHILD_LINEAGE_AND_STORAGE_CONSISTENCY_ONLY",
        "ancestry_sha256": expected_ancestry_sha256,
        "continuation_sha256": expected_continuation_sha256,
        "lineage_id": request["continuation"]["lineage_id"],
        "predecessor_bundle_sha256": parent_tail["bundle_sha256"],
        "predecessor_manifest_sha256": parent_tail["manifest_sha256"],
        "child_bundle_sha256": expected_child_bundle_sha256,
        "child_manifest_sha256": ancestry["child_manifest_sha256"],
        "copied_prefix_records": copied,
        "new_raw_records": child_tail["records"] - copied,
        "total_child_records": child_tail["records"],
        "child_checkpoint": child_tail["checkpoint"], "child_terminal": child_tail["terminal"],
        "history_credit": "COPIED_ORIGINAL_HISTORY_NOT_NEW_EXECUTION",
        "lineage_and_execution_admission": "REQUIRES_GENUINE_ORIGINAL_PROVIDER",
        "numerical_replay_performed": False, "qualification_or_execution_authority": False,
    }


def _outer_layout(root):
    journal._no_alias(root)
    require(root.is_dir(), "Expected owner-controlled outer continuation directory")
    entries = {entry.name: entry for entry in root.iterdir()}
    require(entries.keys() == _OUTER_ENTRIES, "Missing/unknown outer evidence; original owner must reconcile it")
    for name, entry in entries.items():
        journal._no_alias(entry)
        require(entry.is_dir() if name == "journal" else entry.is_file(), "Outer continuation entry kind differs")


def _read_admission(path):
    journal._no_alias(path)
    require(path.is_file(), "Expected regular raw owned-admission file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_OWNED_RECEIPT_BYTES + 1)
    require(0 < len(raw) <= MAX_OWNED_RECEIPT_BYTES, "Raw owned admission exceeds explicit transport bound")
    return raw


def snapshot_raw_continuation_child(root, predecessor_bundle_raw, historical_owned_receipts_raw, *,
                                     expected_ancestry_sha256, expected_continuation_sha256):
    """Read separate outer evidence and a complete inner v1 storage snapshot.

    Real owner-controlled writer exclusion is mandatory throughout. Existing
    bounded journal export refuses torn/orphan/reconciliation candidates. No
    path comes from JSON, and no original/partial artifact is modified/deleted.
    The newly computed child export digest binds this snapshot only; it is not
    independent execution, cleanup, lineage admission or renewed permission.
    """
    root = Path(root).absolute()
    _outer_layout(root)
    ancestry_raw = encode(journal._read(root / "ancestry.json", journal.MAX_MANIFEST))
    ancestry = _ancestry(ancestry_raw, expected_ancestry_sha256)["ancestry"]
    # Bind the complete predecessor before reading the potentially larger child.
    validate_continuation_request(encode(ancestry["continuation"]), predecessor_bundle_raw,
                                   historical_owned_receipts_raw,
                                   expected_continuation_sha256=expected_continuation_sha256)
    admission_raw = _read_admission(root / "owned-admission.bin")
    require(sha256(admission_raw).hexdigest() == ancestry["external_owned_admission_sha256"],
            "Raw outer admission bytes differ")
    child = snapshot_raw_journal(root / "journal", expected_manifest_sha256=ancestry["child_manifest_sha256"])
    child_raw = encode(child)
    summary = validate_raw_child_archive(
        ancestry_raw, admission_raw, predecessor_bundle_raw, historical_owned_receipts_raw, child_raw,
        expected_ancestry_sha256=expected_ancestry_sha256,
        expected_continuation_sha256=expected_continuation_sha256,
        expected_child_bundle_sha256=child["bundle_sha256"])
    _outer_layout(root)
    require(encode(journal._read(root / "ancestry.json", journal.MAX_MANIFEST)) == ancestry_raw and
            _read_admission(root / "owned-admission.bin") == admission_raw,
            "Outer continuation evidence changed during snapshot")
    return {"ancestry_raw": ancestry_raw, "owned_admission_raw": admission_raw,
            "predecessor_bundle_raw": predecessor_bundle_raw,
            "historical_owned_receipts_raw": historical_owned_receipts_raw,
            "child_bundle_raw": child_raw, "summary": summary,
            "qualification_or_execution_authority": False}
