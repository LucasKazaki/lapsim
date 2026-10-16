"""TC-03B0 untouched-build reproduction receipt contract.

Portable reference only. This module records source/build provenance for a
build-only handoff. It does not flash hardware, execute firmware, establish
vehicle safety, or prove Formula SAE compliance.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any

SCHEMA = "enme408-build-reproduction-receipt/v1"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class BuildReceiptError(ValueError):
    pass


def _str(value: Any, path: str) -> str:
    if type(value) is not str or not value.strip():
        raise BuildReceiptError(f"{path} must be a non-empty string")
    return value


def _hex40(value: Any, path: str) -> str:
    value = _str(value, path)
    if not _HEX40.fullmatch(value):
        raise BuildReceiptError(f"{path} must be exactly 40 lowercase hex characters")
    return value


def _hex64(value: Any, path: str) -> str:
    value = _str(value, path)
    if not _HEX64.fullmatch(value):
        raise BuildReceiptError(f"{path} must be exactly 64 lowercase hex characters")
    return value


def _bool(value: Any, path: str) -> bool:
    if type(value) is not bool:
        raise BuildReceiptError(f"{path} must be boolean")
    return value


def _int(value: Any, path: str) -> int:
    if type(value) is not int:
        raise BuildReceiptError(f"{path} must be an integer")
    return value


def _relative_artifact_path(value: Any, path: str) -> str:
    raw = _str(value, path)
    if "\\" in raw:
        raise BuildReceiptError(f"{path} must use normalized forward slashes")
    p = PurePosixPath(raw)
    if p.is_absolute() or any(part in {"", ".", ".."} for part in p.parts):
        raise BuildReceiptError(f"{path} must be a normalized relative path without traversal")
    return str(p)


def _submodule_state_ok(raw: str) -> bool:
    if raw == "":
        return True
    for line in raw.splitlines():
        if not line:
            raise BuildReceiptError("submodule status contains an empty line")
        if line[0] not in {" ", "-", "+", "U"}:
            raise BuildReceiptError("submodule status line has an unsupported prefix")
        if line[0] != " ":
            return False
    return True


@dataclass(frozen=True)
class BuildReadiness:
    schema: str
    evidence_complete: bool
    blockers: tuple[str, ...]
    action_authority: bool = False

    def to_json(self) -> str:
        data = asdict(self)
        data["blockers"] = list(self.blockers)
        return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class Comparison:
    schema: str
    comparable_inputs: bool
    byte_identical: bool
    differences: tuple[str, ...]
    action_authority: bool = False

    def to_json(self) -> str:
        data = asdict(self)
        data["differences"] = list(self.differences)
        return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_json(record: Any) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_sha256(record: Any) -> str:
    return hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()


def validate_receipt(receipt: Any) -> BuildReadiness:
    if type(receipt) is not dict:
        raise BuildReceiptError("receipt must be an object")

    expected_keys = {
        "schema", "target_car", "evidence_request_sha256", "source",
        "build", "toolchain", "artifacts", "scope",
    }
    if set(receipt) != expected_keys:
        raise BuildReceiptError("receipt keys do not match the v1 schema")
    if receipt["schema"] != SCHEMA:
        raise BuildReceiptError(f"receipt.schema must equal {SCHEMA}")
    if receipt["target_car"] != "2027-28":
        raise BuildReceiptError("receipt.target_car must equal 2027-28")
    _hex64(receipt["evidence_request_sha256"], "receipt.evidence_request_sha256")

    source = receipt["source"]
    if type(source) is not dict or set(source) != {
        "expected_commit_sha", "observed_commit_sha", "head_verified_as_commit",
        "status_porcelain_v1", "submodule_status_recursive",
    }:
        raise BuildReceiptError("receipt.source keys invalid")
    expected = _hex40(source["expected_commit_sha"], "receipt.source.expected_commit_sha")
    observed = _hex40(source["observed_commit_sha"], "receipt.source.observed_commit_sha")
    _bool(source["head_verified_as_commit"], "receipt.source.head_verified_as_commit")
    if type(source["status_porcelain_v1"]) is not str:
        raise BuildReceiptError("receipt.source.status_porcelain_v1 must be a string")
    if type(source["submodule_status_recursive"]) is not str:
        raise BuildReceiptError("receipt.source.submodule_status_recursive must be a string")
    submodule_ok = _submodule_state_ok(source["submodule_status_recursive"])

    build = receipt["build"]
    if type(build) is not dict or set(build) != {
        "declared_working_directory", "observed_working_directory",
        "declared_command", "executed_command", "exit_code",
        "stdout_sha256", "stderr_sha256",
    }:
        raise BuildReceiptError("receipt.build keys invalid")
    declared_cwd = _str(build["declared_working_directory"], "receipt.build.declared_working_directory")
    observed_cwd = _str(build["observed_working_directory"], "receipt.build.observed_working_directory")
    declared_cmd = _str(build["declared_command"], "receipt.build.declared_command")
    executed_cmd = _str(build["executed_command"], "receipt.build.executed_command")
    exit_code = _int(build["exit_code"], "receipt.build.exit_code")
    _hex64(build["stdout_sha256"], "receipt.build.stdout_sha256")
    _hex64(build["stderr_sha256"], "receipt.build.stderr_sha256")

    toolchain = receipt["toolchain"]
    if type(toolchain) is not dict or set(toolchain) != {"executable", "version_text"}:
        raise BuildReceiptError("receipt.toolchain keys invalid")
    _str(toolchain["executable"], "receipt.toolchain.executable")
    _str(toolchain["version_text"], "receipt.toolchain.version_text")

    artifacts = receipt["artifacts"]
    if type(artifacts) is not list:
        raise BuildReceiptError("receipt.artifacts must be a list")
    seen = set()
    for i, item in enumerate(artifacts):
        if type(item) is not dict or set(item) != {"path", "sha256", "bytes"}:
            raise BuildReceiptError(f"receipt.artifacts[{i}] keys invalid")
        path = _relative_artifact_path(item["path"], f"receipt.artifacts[{i}].path")
        if path in seen:
            raise BuildReceiptError("receipt.artifacts paths must be unique")
        seen.add(path)
        _hex64(item["sha256"], f"receipt.artifacts[{i}].sha256")
        size = _int(item["bytes"], f"receipt.artifacts[{i}].bytes")
        if size <= 0:
            raise BuildReceiptError(f"receipt.artifacts[{i}].bytes must be > 0")

    scope = receipt["scope"]
    if type(scope) is not dict or set(scope) != {
        "hardware_accessed", "flash_attempted", "vehicle_actuation_attempted",
    }:
        raise BuildReceiptError("receipt.scope keys invalid")
    hardware = _bool(scope["hardware_accessed"], "receipt.scope.hardware_accessed")
    flash = _bool(scope["flash_attempted"], "receipt.scope.flash_attempted")
    actuation = _bool(scope["vehicle_actuation_attempted"], "receipt.scope.vehicle_actuation_attempted")

    blockers = []
    if expected != observed:
        blockers.append("source_commit_mismatch")
    if not source["head_verified_as_commit"]:
        blockers.append("head_not_verified_as_commit")
    if source["status_porcelain_v1"] != "":
        blockers.append("worktree_or_index_not_clean")
    if not submodule_ok:
        blockers.append("submodule_state_not_exact")
    if declared_cwd != observed_cwd:
        blockers.append("working_directory_mismatch")
    if declared_cmd != executed_cmd:
        blockers.append("build_command_mismatch")
    if exit_code != 0:
        blockers.append("build_exit_nonzero")
    if not artifacts:
        blockers.append("no_build_artifacts")
    if hardware:
        blockers.append("hardware_access_was_reported")
    if flash:
        blockers.append("flash_attempt_was_reported")
    if actuation:
        blockers.append("vehicle_actuation_was_reported")

    return BuildReadiness(
        schema=SCHEMA,
        evidence_complete=not blockers,
        blockers=tuple(blockers),
    )


def compare_reproductions(first: Any, second: Any) -> Comparison:
    a = validate_receipt(first)
    b = validate_receipt(second)

    differences = []
    comparable_fields = [
        ("target_car", first["target_car"], second["target_car"]),
        ("evidence_request_sha256", first["evidence_request_sha256"], second["evidence_request_sha256"]),
        ("commit", first["source"]["observed_commit_sha"], second["source"]["observed_commit_sha"]),
        ("working_directory", first["build"]["observed_working_directory"], second["build"]["observed_working_directory"]),
        ("build_command", first["build"]["executed_command"], second["build"]["executed_command"]),
        ("toolchain_executable", first["toolchain"]["executable"], second["toolchain"]["executable"]),
        ("toolchain_version", first["toolchain"]["version_text"], second["toolchain"]["version_text"]),
    ]
    for label, left, right in comparable_fields:
        if left != right:
            differences.append(f"input:{label}")

    comparable = not any(item.startswith("input:") for item in differences)
    if not a.evidence_complete:
        differences.append("first_receipt_incomplete")
    if not b.evidence_complete:
        differences.append("second_receipt_incomplete")

    art_a = {x["path"]: (x["sha256"], x["bytes"]) for x in first["artifacts"]}
    art_b = {x["path"]: (x["sha256"], x["bytes"]) for x in second["artifacts"]}
    if comparable:
        for path in sorted(set(art_a) | set(art_b)):
            if path not in art_a:
                differences.append(f"artifact_added:{path}")
            elif path not in art_b:
                differences.append(f"artifact_missing:{path}")
            elif art_a[path] != art_b[path]:
                differences.append(f"artifact_changed:{path}")

    byte_identical = comparable and a.evidence_complete and b.evidence_complete and not differences
    return Comparison(
        schema=SCHEMA,
        comparable_inputs=comparable,
        byte_identical=byte_identical,
        differences=tuple(differences),
    )
