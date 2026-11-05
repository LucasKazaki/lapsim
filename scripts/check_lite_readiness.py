"""Audit the public lite archive without importing or starting the simulator.

This source-only report cannot authorize execution or establish runtime readiness.
Exit 2 means the archive was inspected but the lite launch remains blocked.
Exit 1 means archive integrity, the source audit or optional report write failed.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import sys

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = "research/light/"
MAX_SOURCE_BYTES = 1_048_576


def read_bound(path: Path) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(MAX_SOURCE_BYTES + 1)
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("source-audit file exceeds 1 MiB")
    return raw


def json_file(path: Path):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate source-audit JSON key")
            value[key] = item
        return value

    def reject_nonfinite(value):
        raise ValueError("nonfinite source-audit JSON")

    return json.loads(read_bound(path), object_pairs_hook=pairs,
                      parse_constant=reject_nonfinite)


def archive_file(root: Path, name: str) -> Path:
    if (not isinstance(name, str) or not name.startswith(ARCHIVE)
            or "\\" in name or ":" in name
            or any(part in (".", "..", "") for part in name.split("/"))
            or PurePosixPath(name).is_absolute()):
        raise ValueError("manifest path must stay inside research/light")
    candidate = root / name
    if not candidate.resolve().is_relative_to((root / ARCHIVE).resolve()):
        raise ValueError("manifest path escapes research/light")
    for item in (candidate, *candidate.parents):
        if item == root:
            break
        if item.is_symlink() or getattr(item.lstat(), "st_file_attributes", 0) & 1024:
            raise ValueError("source-audit paths must not use links or reparse points")
    return candidate


def audit(root: Path = ROOT) -> dict:
    root = root.resolve()
    manifest = json_file(archive_file(root, ARCHIVE + "SOURCE_MANIFEST.json"))
    status = json_file(archive_file(root, ARCHIVE + "STATUS.json"))
    registry = json_file(archive_file(root, ARCHIVE + "awd-standing-v15/registry-core.json"))
    if any(type(value) is not dict for value in (manifest, status, registry)):
        raise ValueError("source-audit metadata must be JSON objects")
    entries = manifest["source_entries"]
    if (manifest.get("schema") != "lapsim.public-light-archival-source-manifest.v1"
            or type(entries) is not list or not 1 <= len(entries) <= 256
            or type(manifest.get("source_files")) is not int
            or manifest["source_files"] != len(entries)):
        raise ValueError("unsupported or inconsistent archival source manifest")
    checked = []
    seen = set()
    for entry in entries:
        if type(entry) is not dict:
            raise ValueError("manifest entries must be JSON objects")
        name = entry["path"]
        path = archive_file(root, name)
        if name in seen:
            raise ValueError("duplicate manifest path")
        seen.add(name)
        digest, size = entry["sha256"], entry["bytes"]
        if (type(size) is not int or not 0 <= size <= MAX_SOURCE_BYTES
                or not isinstance(digest, str) or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)):
            raise ValueError("invalid source identity")
        raw = read_bound(path)
        actual = sha256(raw).hexdigest()
        checked.append({"path": name, "expected_sha256": digest, "actual_sha256": actual,
                        "expected_bytes": size, "actual_bytes": len(raw),
                        "matches": actual == digest and len(raw) == size})
    policies = registry["policies"]
    if (type(policies) is not list or len(policies) != 7
            or any(type(item) is not dict for item in policies)):
        raise ValueError("expected the archived seven-policy registry")
    matched = sum(row["matches"] for row in checked)
    return {
        "schema": "lapsim.lite-source-readiness.v1",
        "scope": "SOURCE_FILES_ONLY_NOT_RUNTIME_QUALIFICATION_OR_EXECUTION_AUTHORITY",
        "status": "blocked",
        "archive_integrity": "passed" if matched == len(checked) else "failed",
        "files_matched": matched, "files_checked": len(checked), "files": checked,
        "archive_declared_status": manifest.get("status"),
        "publication_role": status.get("publication_role"),
        "policies": [{"id": item["id"],
                      "native_qualification": item.get("native_qualification"),
                      "campaign_eligible": item.get("campaign_eligible")} for item in policies],
        "runtime_checks_executed": False,
        "execution_authority": False,
        "blocking_reasons": [
            "Public lite source archive has no supported launch/tournament entry point.",
            "Complete installed driver/plant/policy dependency closure is not qualified.",
            "An independently authenticated racing-line producer/consumer binding is required.",
            "Actual process/activity/game/memory guards, exclusive lease and owned cleanup are unqualified here.",
            "Native tests, standing-start pilot, UI acceptance and matched campaign coverage remain required.",
            "A source report or local qualification flag cannot resolve the retained execution-review denial.",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Create a new local JSON report; never overwrite")
    args = parser.parse_args(argv)
    try:
        report = audit()
        text = json.dumps(report, indent=2, allow_nan=False) + "\n"
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
        print(text, end="")
        return 2 if report["archive_integrity"] == "passed" else 1
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("Lite source audit failed: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
