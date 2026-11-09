"""UNTESTED source preparation; no light runtime entrypoint is available.

This file is for Lucas's later execution. Do not invoke it during source review.
Start/preparation use only Python's standard library. --evidence imports verified
portable metadata commands, never original runtime modules or the numerical bridge.
--start refuses before setup. --prepare stages pinned bytes and an empty venv.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
from uuid import uuid4
import venv


ROOT = Path(__file__).resolve().parents[1]
PYTHON_VERSION = (3, 13, 15)
REPOSITORY = "https://github.com/LucasKazaki/lapsim.git"
PUBLIC_COMMIT = "07ccb4b84138aedcc5b9cb85c2e81d283d6c132e"
PUBLIC_MANIFEST_PATH = "research/light/SOURCE_MANIFEST.json"
PUBLIC_MANIFEST_SHA256 = "4b1b3c712b0e5a31a0670046e13440fde08e903db7df3138c0cf18ee6def6e88"
LOCAL_CANDIDATE_PATH = "research/light/portable-tournament-candidate"
LOCAL_CANDIDATE_COMMIT = "7f57932943ea617fe87b9679cf645eec24ca01f0"
LOCAL_MANIFEST_SHA256 = "3e2da770c31aba0feffd5f9b561d8c8cdc15729c561e0ac988c9ef148fb1ab05"
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
WORKSPACE_MARKER = b'lapsim.light-source-preparation-root.v1\nNO_RUNTIME_AUTHORITY\n'
MISSING_START_REQUIREMENTS = (
    "The frozen native handoff confirms that no native campaign-start provider is implemented.",
    "No exact installable numerical/runtime dependency recipe is supplied; authenticated course/producer/receipt inputs remain unresolved.",
    "Independent trust/verifier, source/runtime observer, trusted time and single-use challenges are not integrated.",
    "Current finite admission, original guards/ownership/deadline/watchdog and authenticated cleanup are not integrated.",
    "The complete tournament orchestration and active Run/Stop/Close application mapping are absent.",
    "Execution and qualification remain deferred; source review establishes no working tournament.",
)


class PreparationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise PreparationError(message)


def no_alias(path):
    """Reject symlinks/junctions/reparse points without resolving them away."""
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode) and
                not (getattr(info, "st_file_attributes", 0) & 0x400),
                "Aliased path is unsupported; preserve it and choose a real project path: " + str(part))


def bounded_bytes(path):
    no_alias(path)
    require(stat.S_ISREG(path.stat().st_mode), "Expected a regular source file: " + str(path))
    with path.open("rb") as stream:
        raw = stream.read(MAX_FILE_BYTES + 1)
    require(len(raw) <= MAX_FILE_BYTES, "Source file exceeds the preparation bound: " + str(path))
    return raw


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate key in source inventory")
        result[key] = value
    return result


def inventory(raw, expected_sha256, *, key, count):
    require(sha256(raw).hexdigest() == expected_sha256, "Pinned source manifest differs; no repair or pin regeneration is performed")
    value = json.loads(raw, object_pairs_hook=unique_object)
    entries = value.get(key)
    require(type(entries) is list and len(entries) == count, "Source inventory count differs")
    result = {}
    for entry in entries:
        require(type(entry) is dict, "Source entry must be an object")
        name, size, digest = (entry.get(field) for field in ("path", "bytes", "sha256"))
        require(type(name) is str and re.fullmatch(r"[A-Za-z0-9_.\-/]+", name), "Invalid source path")
        path = PurePosixPath(name)
        require(not path.is_absolute() and str(path) == name and
                all(part not in (".", "..") for part in path.parts) and name not in result,
                "Duplicate or noncanonical source path")
        require(type(size) is int and 0 <= size <= MAX_FILE_BYTES and
                type(digest) is str and re.fullmatch(r"[a-f0-9]{64}", digest), "Invalid source byte identity")
        result[name] = (size, digest)
    require(sum(size for size, _ in result.values()) <= MAX_TOTAL_BYTES, "Source inventory exceeds total bound")
    return result


def file_names(root):
    """Bounded scan that checks directory aliases before descending."""
    pending, names, visited = [root], set(), 0
    while pending:
        directory = pending.pop()
        no_alias(directory)
        visited += 1
        require(visited <= 1024, "Too many source directories")
        with os.scandir(directory) as children:
            for child in children:
                path = Path(child.path)
                no_alias(path)
                if child.is_dir(follow_symlinks=False):
                    require(visited + len(pending) < 1024, "Too many source directories")
                    pending.append(path)
                else:
                    require(child.is_file(follow_symlinks=False), "Nonregular source entry")
                    names.add(path.relative_to(root).as_posix())
                    require(len(names) <= 512, "Too many source files")
    return names


def verified_local_candidate():
    source = ROOT / LOCAL_CANDIDATE_PATH
    require(source.is_dir(),
            "The unpublished light candidate is not local. The previous official patch transfer failed; "
            "this command does not retry it or fetch an unpublished branch. See docs/light_tournament_startup.md.")
    manifest = bounded_bytes(source / "SOURCE_MANIFEST.json")
    entries = inventory(manifest, LOCAL_MANIFEST_SHA256, key="files", count=66)
    require(file_names(source) == set(entries) | {"SOURCE_MANIFEST.json"},
            "Local candidate has extra/missing files; preserve it and restore the exact reviewed snapshot separately")
    blobs = {"SOURCE_MANIFEST.json": manifest}
    for name, (size, digest) in entries.items():
        raw = bounded_bytes(source / name)
        require(len(raw) == size and sha256(raw).hexdigest() == digest,
                "Local candidate bytes differ: " + name)
        blobs[name] = raw
    return blobs


def create_files(root, blobs):
    root.mkdir()
    for name, raw in blobs.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)
        require(bounded_bytes(target) == raw, "Staged source copy differs: " + name)


def verified_public_archive():
    """Read only the already-local archive; do not retry denied source access."""
    require((ROOT / PUBLIC_MANIFEST_PATH).is_file(),
            "The pinned public archive is not local. Source access needs supported resolution; no Git/download retry is performed")
    manifest = bounded_bytes(ROOT / PUBLIC_MANIFEST_PATH)
    entries = inventory(manifest, PUBLIC_MANIFEST_SHA256, key="source_entries", count=16)
    blobs = {PUBLIC_MANIFEST_PATH: manifest}
    for name, (size, digest) in entries.items():
        require(name.startswith("research/light/"), "Unexpected public archive path")
        raw = bounded_bytes(ROOT / name)
        require(len(raw) == size and sha256(raw).hexdigest() == digest, "Local public archive bytes differ: " + name)
        blobs[name] = raw
    return blobs


def write_record(attempt, status, **details):
    record = {
        "schema": "lapsim.light-source-preparation.v1", "status": status,
        "source_acquisition": "ALREADY_LOCAL_BYTES_ONLY_NO_TRANSFER_OR_DOWNLOAD",
        "repository_provenance": REPOSITORY,
        "public_commit": PUBLIC_COMMIT, "public_manifest_sha256": PUBLIC_MANIFEST_SHA256,
        "local_candidate_commit": LOCAL_CANDIDATE_COMMIT,
        "local_candidate_manifest_sha256": LOCAL_MANIFEST_SHA256,
        "preparation_python_version": list(sys.version_info[:3]),
        "preparation_python_executable_sha256": sha256(Path(sys.executable).read_bytes()).hexdigest(),
        "third_party_distributions_installed": [], "candidate_package_installed": False,
        "numerical_runtime_observed_or_qualified": False, "tournament_ready": False,
        "admission_or_execution_authority": False, "original_guards_or_shared_locks_accessed": False,
        "candidate_imported_or_executed": False, "missing_start_requirements": MISSING_START_REQUIREMENTS,
        **details,
    }
    with (attempt / (status.lower() + ".json")).open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2, allow_nan=False)
        stream.write("\n")


def prepare(workspace_value):
    require(sys.platform == "win32" and sys.implementation.name == "cpython" and
            sys.maxsize > 2**32 and sys.version_info[:3] == PYTHON_VERSION,
            "Preparation requires installed 64-bit Windows CPython 3.13.15. "
            "No interpreter is downloaded automatically; this pin is not light-runtime qualification")
    blobs = verified_local_candidate()
    public_blobs = verified_public_archive()
    workspace = Path(os.path.abspath(ROOT / workspace_value))
    work_root = ROOT / "work"
    require(workspace.is_relative_to(work_root) and workspace != work_root,
            "Preparation workspace must be a separate directory under this project's work/")
    no_alias(workspace)
    if workspace.exists():
        marker = workspace / ".source-preparation-root"
        require(marker.is_file() and bounded_bytes(marker) == WORKSPACE_MARKER,
                "Existing workspace is not this preparer's owned staging root; preserve it and select a new work/ directory")
    else:
        workspace.mkdir(parents=True)
        no_alias(workspace)
        with (workspace / ".source-preparation-root").open("xb") as stream:
            stream.write(WORKSPACE_MARKER)
    gate = workspace / ".preparation-active"
    token = (uuid4().hex + "\n").encode("ascii")
    try:
        with gate.open("xb") as stream:
            stream.write(token)
    except FileExistsError as error:
        raise PreparationError("Preparation gate already exists. Do not start a duplicate preparation; "
                               "preserve the prior attempt and reconcile it before removing the gate or choosing another workspace") from error
    attempt = None
    stages = {"local_candidate_verified": True, "candidate_copy_verified": False,
              "local_public_archive_verified": True, "public_archive_copy_verified": False,
              "empty_venv_created": False}
    try:
        attempt = Path(tempfile.mkdtemp(prefix="attempt-", dir=workspace))
        create_files(attempt / "candidate-source", blobs)
        stages["candidate_copy_verified"] = True
        create_files(attempt / "public-light-archive", public_blobs)
        stages["public_archive_copy_verified"] = True
        venv.EnvBuilder(with_pip=False, clear=False, symlinks=False).create(attempt / ".venv")
        stages["empty_venv_created"] = True
        write_record(attempt, "PREPARED_SOURCE_ONLY", **stages)
        print("Source preparation finished: " + str(attempt))
        print("Tournament start remains unavailable. No packages, original adapters or admission were installed.")
    except (KeyboardInterrupt, OSError, ValueError, RuntimeError) as error:
        if attempt is not None:
            try:
                write_record(attempt, "FAILED_SOURCE_PREPARATION", error_type=type(error).__name__, **stages)
            except (OSError, ValueError):
                pass
        raise
    finally:
        no_alias(gate)
        require(bounded_bytes(gate) == token, "Preparation gate changed; preserve it for reconciliation")
        gate.unlink()


def _metadata_provenance(source, blobs):
    """Import path/byte hygiene only; never the missing original SourceObserver."""
    for name, module in list(sys.modules.items()):
        if not name.startswith("lapsim_light_"):
            continue
        relative = "src/" + name.replace(".", "/")
        locations = getattr(module, "__path__", None)
        relative += "/__init__.py" if locations is not None else ".py"
        expected = source / relative
        require(relative in blobs and type(getattr(module, "__file__", None)) is str and
                Path(os.path.abspath(module.__file__)) == expected and bounded_bytes(expected) == blobs[relative],
                "Loaded light metadata namespace differs from the verified source snapshot: " + name)
        if locations is not None:
            require(list(locations) == [str(expected.parent)], "Loaded light package search path differs: " + name)


def evidence(arguments):
    """Run file-only commands from the exact local candidate; no installed fallback."""
    require(sys.version_info >= (3, 11), "Evidence commands require Python 3.11 or newer")
    require(not any(name.startswith("lapsim_light_") for name in sys.modules),
            "Light namespaces are already loaded. Run this command in a fresh Python process; do not mix installations")
    blobs = verified_local_candidate()
    source = Path(os.path.abspath(ROOT / LOCAL_CANDIDATE_PATH))
    original_path, original_bytecode = list(sys.path), sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(source / "src"))
        command = importlib.import_module("lapsim_light_campaign.tournament_cli")
        _metadata_provenance(source, blobs)
        return command.main(arguments, output_root=ROOT / "work")
    finally:
        sys.path[:] = original_path
        sys.dont_write_bytecode = original_bytecode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true", help="Stage exact source and an empty venv; never launch")
    mode.add_argument("--start", action="store_true", help="Refuse: original runtime integration is still missing")
    mode.add_argument("--evidence", nargs=argparse.REMAINDER,
                      help="Run pinned create-plan/inspect-plan/compare-results file commands; never launch")
    parser.add_argument("--workspace", default="work/light-tournament-preparation",
                        help="Preparation staging root; evidence file outputs stay under repository work/")
    args = parser.parse_args()
    if args.start:
        print("LIGHT TOURNAMENT START BLOCKED: missing implementation, not an execution-ready release.", file=sys.stderr)
        for requirement in MISSING_START_REQUIREMENTS:
            print("- " + requirement, file=sys.stderr)
        return 2
    try:
        if args.evidence is not None:
            return evidence(args.evidence)
        prepare(args.workspace)
        return 0
    except KeyboardInterrupt:
        action = "evidence command" if args.evidence is not None else "source preparation"
        print("Light " + action + " interrupted; partial files are preserved. Reconcile any remaining setup gate before retrying.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, ImportError, SyntaxError) as error:
        action = "evidence command" if args.evidence is not None else "source preparation"
        print("Light " + action + " stopped: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
