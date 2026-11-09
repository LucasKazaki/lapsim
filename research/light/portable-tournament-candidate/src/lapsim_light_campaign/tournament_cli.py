"""UNTESTED file commands for the existing matched-plan/RAW-result workflow.

Frozen behavior: require explicit input digest pins, bounded canonical JSON and
regular non-aliased files. A result index names only confined relative files.
Validate every input before exclusive output creation; preserve partial outputs.
Release verification joins supplied source/contract/wheel pins, with independently
trusted checker code required before import; it does not check its own loaded code.
No command creates origins, modifies journals, starts a worker, authenticates
execution or awards points. A valid incomplete raw comparison is written in full
and exits 3. Source installation/import hygiene is separate from runtime identity.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import os
from pathlib import Path, PurePosixPath
import stat
import sys

from . import raw_journal as journal
from .input_contracts import decode, digest, encode, exact, is_sha256, require
from .raw_evidence import MAX_EXPORT_BYTES
from .tournament_plan import MAX_PLAN_BYTES, freeze_tournament, validate_tournament_plan
from .tournament_results import MAX_REPORT_BYTES, RawCellExport, summarize_tournament


INDEX_SCHEMA = "lapsim.light-field-result-files.v1"
MAX_INDEX_BYTES = 64 * 1024
COMPARISON_SCHEMA = "lapsim.light-field-file-comparison.v1"
INSPECTION_SCHEMA = "lapsim.light-field-plan-inspection.v1"
MAX_COMMAND_OUTPUT_BYTES = MAX_REPORT_BYTES + MAX_INDEX_BYTES
_RESERVED_WINDOWS_NAMES = frozenset(("con", "prn", "aux", "nul", "clock$", "conin$", "conout$") +
                                    tuple(name + str(i) for name in ("com", "lpt") for i in range(1, 10)))


def _absolute(value):
    # Do not resolve aliases away before the journal's path checks inspect them.
    lexical = os.fspath(value)
    require(not lexical.startswith(("\\\\", "//")), "Use ordinary local-disk paths, without UNC/device/extended namespaces")
    path = Path(os.path.abspath(lexical))
    require(not str(path).startswith(("\\\\", "//")), "Absolute file paths cannot use UNC/device/extended namespaces")
    require(all(part.split(".", 1)[0].rstrip(" ").casefold() not in _RESERVED_WINDOWS_NAMES
                for part in path.parts if part != path.anchor), "Device/reserved input path is unsupported")
    return path


def _read(path, maximum, *, expected_raw_sha256=None):
    path = _absolute(path)
    journal._no_alias(path)
    require(path.is_file() and stat.S_ISREG(path.stat().st_mode), "Expected a regular input file: " + str(path))
    with path.open("rb") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Input is not a regular file")
        raw = stream.read(maximum + 1)
    require(0 < len(raw) <= maximum, "Input exceeds its explicit byte bound: " + str(path))
    if expected_raw_sha256 is not None:
        require(is_sha256(expected_raw_sha256) and sha256(raw).hexdigest() == expected_raw_sha256,
                "Input raw-file SHA-256 differs: " + str(path))
    return raw


def _relative_file(parent, name):
    require(type(name) is str and 0 < len(name) <= 512 and
            not any(ord(character) < 32 or character in '\\:<>"|?*' for character in name),
            "Result paths must use portable relative components without drive/ADS/backslash forms")
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and str(relative) == name and
            all(part not in (".", "..") and not part.endswith((".", " ")) and
                part.split(".", 1)[0].rstrip(" ").casefold() not in _RESERVED_WINDOWS_NAMES for part in relative.parts),
            "Noncanonical, escaping or reserved result-file path")
    target = parent.joinpath(*relative.parts)
    require(target.is_relative_to(parent), "Result file escapes its index directory")
    journal._no_alias(target)
    return target


def _result_files(index_raw, parent, plan):
    index = decode(index_raw, MAX_INDEX_BYTES, canonical=True)
    exact(index, {"schema", "cells"}, "result-file index")
    require(index["schema"] == INDEX_SCHEMA and type(index["cells"]) is dict and
            index["cells"].keys() <= set(plan["policy_order"]), "Index may name only the frozen field's policy slots")
    declarations, paths = [], set()
    # Validate the whole index before opening any of its raw export files.
    for policy_id, descriptor in index["cells"].items():
        exact(descriptor, {"path", "raw_sha256", "bundle_sha256", "manifest_sha256"}, "result-file descriptor")
        require(all(is_sha256(descriptor[key]) for key in ("raw_sha256", "bundle_sha256", "manifest_sha256")),
                "Exact raw, bundle and manifest SHA-256 pins required for every result")
        path = _relative_file(parent, descriptor["path"])
        require(path not in paths, "A result file cannot fill multiple policy slots")
        paths.add(path)
        declarations.append((policy_id, path, descriptor))
    exports = {}
    for policy_id, path, descriptor in declarations:
        raw = _read(path, MAX_EXPORT_BYTES, expected_raw_sha256=descriptor["raw_sha256"])
        exports[policy_id] = RawCellExport(raw, descriptor["bundle_sha256"], descriptor["manifest_sha256"])
    return exports


def _output_path(value, output_root):
    target, root = _absolute(value), _absolute(output_root)
    journal._no_alias(target)
    require(target != root and target.is_relative_to(root), "Choose a new output file under the command's work/ directory")
    require(_relative_file(root, target.relative_to(root).as_posix()) == target, "Unsupported output-file path")
    code_origin = _absolute(__file__)
    journal._no_alias(code_origin)
    code_root = code_origin.parents[2]
    require(not target.is_relative_to(code_root), "Outputs cannot modify the immutable candidate or installed source tree")
    require(target.parent.is_dir(), "Output directory must already exist: " + str(target.parent))
    require(not target.exists(), "Output already exists; preserve it and choose a new filename")
    return target


def _write(target, value, maximum):
    raw = encode(value)
    require(0 < len(raw) <= maximum, "Command output exceeds its explicit byte bound")
    journal._no_alias(target)
    # The raw store's exclusive-create/fsync order, with an extra regular-file
    # check for user-selected names. Never delete interrupted files or append.
    with target.open("xb") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Output is not a regular file")
        require(stream.write(raw) == len(raw), "Incomplete command output write; preserve partial file without retry")
        stream.flush()
        os.fsync(stream.fileno())
    journal._sync_directory(target.parent, True)
    return {"output": str(target), "output_raw_sha256": sha256(raw).hexdigest(), "output_bytes": len(raw)}


def _inspect(plan, plan_sha256, plan_raw):
    first = plan["cells"][0]["origin"]["checkpoint"]["context"]
    body = {
        "schema": INSPECTION_SCHEMA, "plan_sha256": plan_sha256,
        "plan_raw_sha256": sha256(plan_raw).hexdigest(), "policy_order": plan["policy_order"],
        "frozen_cells": len(plan["cells"]), "shared_identity": plan["shared_identity"],
        "shared_context_sha256": plan["shared_context_sha256"],
        "shared_initial_checkpoint_sha256": plan["shared_initial_checkpoint_sha256"],
        "request_ceilings": plan["request_ceilings"], "course_id": first["course"]["id"], "mode": first["mode"],
        "status": plan["status"], "completed_laps_established_by_this_inspection": False,
        "source_runtime_or_original_input_authentication_performed": False,
        "qualification_or_execution_authority": False, "campaign_eligible": False,
        "official_points": None, "overall_winner": None,
    }
    return {"inspection": body, "inspection_sha256": digest(body)}


def _execute(args, output_root):
    output = None if args.output is None else _output_path(args.output, output_root)
    if args.command == "verify-release":
        from .release_binding import (MAX_CONTRACT_BYTES, MAX_MANIFEST_BYTES,
                                      MAX_WHEEL_BYTES, verify_source_wheel_binding)
        manifest = _read(args.source_manifest, MAX_MANIFEST_BYTES, expected_raw_sha256=args.manifest_sha256)
        contract = _read(args.install_contract, MAX_CONTRACT_BYTES)
        wheel = _read(args.wheel, MAX_WHEEL_BYTES, expected_raw_sha256=args.wheel_sha256)
        value = verify_source_wheel_binding(manifest, contract, wheel,
            expected_source_manifest_sha256=args.manifest_sha256, expected_wheel_sha256=args.wheel_sha256)
        return 0, value if output is None else {**_write(output, value, MAX_COMMAND_OUTPUT_BYTES), **value}
    if args.command == "create-plan":
        raw = _read(args.origins, MAX_PLAN_BYTES, expected_raw_sha256=args.origins_sha256)
        options = {} if args.policy_order is None else {"policy_order": tuple(args.policy_order)}
        value = freeze_tournament(raw, expected_origins_raw_sha256=args.origins_sha256, **options)
        summary = {**_write(output, value, MAX_PLAN_BYTES), "plan_sha256": value["plan_sha256"],
                   "status": value["plan"]["status"], "qualification_or_execution_authority": False}
        return 0, summary
    plan_raw = _read(args.plan, MAX_PLAN_BYTES)
    plan = validate_tournament_plan(plan_raw, expected_plan_sha256=args.plan_sha256)
    if args.command == "inspect-plan":
        value = _inspect(plan, args.plan_sha256, plan_raw)
        return 0, value if output is None else {
            **_write(output, value, MAX_COMMAND_OUTPUT_BYTES), "inspection": value,
        }
    index_path = _absolute(args.results_index)
    index_raw = _read(index_path, MAX_INDEX_BYTES, expected_raw_sha256=args.index_sha256)
    exports = _result_files(index_raw, index_path.parent, plan)
    report = summarize_tournament(plan_raw, exports, expected_plan_sha256=args.plan_sha256)
    body = {
        "schema": COMPARISON_SCHEMA, "plan_raw_sha256": sha256(plan_raw).hexdigest(),
        "results_index_raw_sha256": args.index_sha256, "raw_report": report,
        "completed_laps_independently_verified": False, "numerical_validation_performed": False,
        "qualification_or_execution_authority": False,
    }
    value = {"comparison": body, "comparison_sha256": digest(body)}
    complete = report["coverage"]["all_raw_cells_comparable"]
    summary = {**_write(output, value, MAX_COMMAND_OUTPUT_BYTES), "comparison_sha256": value["comparison_sha256"],
               "status": "RAW_FIELD_REPORT_COMPLETE_UNAUTHENTICATED" if complete else "RAW_FIELD_REPORT_INCOMPLETE_OR_EXCLUDED",
               "coverage": report["coverage"], "qualification_or_execution_authority": False,
               "completed_laps_independently_verified": False, "official_points": None, "overall_winner": None}
    return 0 if complete else 3, summary


def main(argv=None, *, output_root=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-plan", help="Freeze seven real supplied origins; no origin generation or execution")
    create.add_argument("--origins", required=True, type=Path)
    create.add_argument("--origins-sha256", required=True)
    create.add_argument("--policy-order", nargs=7, choices=journal.POLICIES)
    create.add_argument("--output", required=True, type=Path)
    release = commands.add_parser("verify-release", help="Compare pinned source/contract/wheel bytes; checker must already be independently trusted")
    release.add_argument("--source-manifest", required=True, type=Path)
    release.add_argument("--manifest-sha256", required=True)
    release.add_argument("--install-contract", required=True, type=Path)
    release.add_argument("--wheel", required=True, type=Path)
    release.add_argument("--wheel-sha256", required=True)
    release.add_argument("--output", type=Path)
    for name in ("inspect-plan", "compare-results"):
        command = commands.add_parser(name, help="Inspect pinned metadata only; never authenticate or execute a tournament")
        command.add_argument("--plan", required=True, type=Path)
        command.add_argument("--plan-sha256", required=True)
        command.add_argument("--output", required=name == "compare-results", type=Path)
        if name == "compare-results":
            command.add_argument("--results-index", required=True, type=Path)
            command.add_argument("--index-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        status, summary = _execute(args, Path.cwd() / "work" if output_root is None else output_root)
        print(encode(summary).decode("utf-8"))
        return status
    except KeyboardInterrupt as error:
        if args.command == "verify-release" and type(error) is not KeyboardInterrupt:
            raise
        print("Light evidence command interrupted; any partial output is preserved. No worker was started.", file=sys.stderr)
        return 130
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        if args.command == "verify-release":
            from .release_binding import ReleaseBindingError, _KNOWN_ERRORS
            if type(error) not in (*_KNOWN_ERRORS, ReleaseBindingError, RecursionError):
                raise  # Do not demote unknown owner/control subclasses to ordinary command errors.
        print("Light evidence command stopped: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
