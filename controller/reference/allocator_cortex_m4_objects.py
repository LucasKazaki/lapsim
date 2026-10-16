"""Separate allocator object annex; never link or execute generated ARM code."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import zipfile

REFERENCE = Path(__file__).resolve().parent
PROJECT = REFERENCE.parent
PROTOCOL = PROJECT / "research/TC-03J-allocator-object-protocol.json"
PROTOCOL_SHA256 = "6cd2ab954e137c0f052e5f83e6c3a3516b5813d7c2749a7ee415c2e2bf0c9912"
SOURCES = ("torque_allocator.c", "torque_allocator.h", "torque_contract.h")
ABIS = ("hard", "softfp")
TOOLS = ("clang.exe", "llvm-readobj.exe", "llvm-size.exe", "llvm-nm.exe", "llvm-objdump.exe")
PUBLIC = ("tc_allocator_version", "tc_allocator_abi_sizeof", "tc_allocate_propulsive_torque")


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def load_protocol(path=PROTOCOL):
    if digest(path) != PROTOCOL_SHA256:
        raise ValueError("frozen allocator object protocol changed")
    plan = json.loads(path.read_text(encoding="utf-8"))
    matrix = plan["matrix"]
    if (set(plan["sources"]) != set(SOURCES) or matrix["units"] != ["torque_allocator.c"]
            or tuple(matrix["abis"]) != ABIS or matrix["repetitions"] != 2
            or matrix["planned_objects"] != 4 or matrix["planned_toolchain_commands"] != 31
            or tuple(row[0] for row in plan["version_commands_in_order"]) != TOOLS
            or len(plan["per_object_inspections_in_order"]) != 5):
        raise ValueError("unexpected allocator object cohort/matrix")
    return plan


def load_shared(plan):
    path = REFERENCE / "cortex_m4_objects.py"
    if digest(path) != plan["shared_helper"]["sha256"]:
        raise ValueError("frozen shared helper changed")
    spec = importlib.util.spec_from_file_location("allocator_object_verified_helpers", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load verified helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_facts(native, plan):
    if set(plan["sources"]) != set(SOURCES):
        raise ValueError("unexpected allocator sources")
    result = {}
    for name in SOURCES:
        path = native / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("ordinary source required: " + name)
        raw = path.read_bytes()
        exact = hashlib.sha256(raw).hexdigest()
        normalized = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
        if (exact != plan["sources"][name]["exact_local_sha256"]
                or normalized != plan["sources"][name]["lf_normalized_sha256"]):
            raise ValueError("frozen allocator source changed: " + name)
        result[name] = {"sha256": exact, "bytes": len(raw)}
    return result


def load_baseline(plan):
    identity = plan["frozen_research_baseline"]
    path = PROJECT / identity["path"]
    if path.stat().st_size != identity["bytes"] or digest(path) != identity["sha256"]:
        raise ValueError("frozen historical baseline changed")
    return json.loads(path.read_text(encoding="utf-8"))


def historical_facts(baseline):
    """Read/check old artifacts only. Their original statuses are not recomputed."""
    result = {"anchors": [], "attempts": []}
    for row in baseline["historical_anchors"]:
        path = Path(row["path"])
        if path.is_symlink() or not path.is_file() or path.stat().st_size != row["bytes"] or digest(path) != row["sha256"]:
            raise ValueError("historical anchor changed: " + str(path))
        result["anchors"].append(dict(row))
    for attempt in baseline["historical_attempts"]:
        root = Path(attempt["root"])
        files = []
        for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
            if path.is_symlink():
                raise ValueError("historical symlink: " + str(path))
            if path.is_file():
                files.append({"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
                              "sha256": digest(path)})
        if files != attempt["files"]:
            raise ValueError("historical attempt changed: " + str(root))
        result["attempts"].append({"root": str(root), "file_count": len(files),
            "sorted_file_records_sha256": hashlib.sha256(json.dumps(files, separators=(",", ":"),
                ensure_ascii=True).encode("ascii")).hexdigest()})
    return result


def attempt_path(path, protected):
    resolved = path.resolve()
    if path.exists() or path.is_symlink():
        raise ValueError("refusing existing attempt")
    for value in protected:
        owner = Path(value).resolve()
        if resolved == owner or resolved.is_relative_to(owner) or owner.is_relative_to(resolved):
            raise ValueError("attempt overlaps protected source/archive/toolchain/history")
    if any((parent / "receipt.json").is_file() for parent in resolved.parents):
        raise ValueError("attempt must be outside retained attempts")
    return resolved


def compile_args(tool, flags, abi, unit, obj):
    if abi not in ABIS or unit != "torque_allocator":
        raise ValueError("unexpected allocator ABI/unit")
    if flags != load_protocol()["compile_common_flags"]:
        raise ValueError("exact frozen flags/order required")
    return [str(tool), *flags, "-mfloat-abi=" + abi, "-MD", "-MF", str(obj.with_suffix(".d")),
            "-c", "torque_allocator.c", "-o", str(obj)]


def schedule(plan, toolchain, output):
    """The only executable argv source: 7 preflights then four fixed six-call rows."""
    if plan != load_protocol():
        raise ValueError("exact frozen command plan required")
    commands = []

    def append(argv, label):
        if argv[0] not in TOOLS:
            raise ValueError("unexpected executable")
        commands.append({"slot": len(commands), "label": label, "status": "not_run", "launch_state": "not_attempted",
            "argv": [str(toolchain / "bin" / argv[0]), *argv[1:]],
            "cwd": str((output / "native").resolve())})

    for argv in plan["version_commands_in_order"]:
        append(argv, "version-" + Path(argv[0]).stem)
    for abi, argv in zip(ABIS, plan["multilib_preflights_in_order"]):
        append(argv, "multilib-" + abi)
    rows = []
    for repeat in (1, 2):
        for abi in ABIS:
            obj = output / ("repeat-" + str(repeat)) / abi / "torque_allocator.o"
            label = str(repeat) + "-" + abi + "-torque_allocator"
            row = {"repeat": repeat, "abi": abi, "unit": "torque_allocator", "status": "not_run",
                   "path": obj.relative_to(output).as_posix(), "compile_slot": len(commands)}
            argv = compile_args(Path("clang.exe"), plan["compile_common_flags"], abi, "torque_allocator", obj)
            append(argv, "compile-" + label)
            row["inspection_slots"] = []
            for index, template in enumerate(plan["per_object_inspections_in_order"]):
                row["inspection_slots"].append(len(commands))
                append(template[:-1] + [str(obj)], "inspect-" + label + "-" + str(index))
            rows.append(row)
    if len(commands) != 31 or len(rows) != 4:
        raise ValueError("unexpected command denominator")
    return commands, rows


def manifest_records(path, names):
    result = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["path"] in names:
                if row["path"] in result:
                    raise ValueError("duplicate selected manifest entry")
                result[row["path"]] = row
    if set(result) != set(names):
        raise ValueError("missing selected verified manifest entry")
    return result


def verify_five_tools(archive_path, root, plan, verification, manifest):
    """Fifth tool is independently bound; never mutate the old helper's TOOLS."""
    if digest(manifest) != verification["manifest_sha256"] or verification["verified_file_count"] != 48211:
        raise ValueError("fresh full verification manifest mismatch")
    pins = plan["toolchain"]["five_proposed_tool_pins"]
    selected = manifest_records(manifest, {"bin/" + tool for tool in TOOLS})
    root = root.resolve()
    if set(verification["tools"]) != set(TOOLS[:-1]):
        raise ValueError("unexpected historical helper tool identities")
    tools = {}
    for tool in TOOLS:
        relative = "bin/" + tool
        path = root / relative
        pin = pins[tool]
        if (selected[relative] != pin or path.is_symlink() or not path.is_file()
                or not path.resolve().is_relative_to(root) or path.stat().st_size != pin["bytes"]
                or digest(path) != pin["sha256"]):
            raise ValueError("unverified tool bytes/path: " + tool)
        if tool != "llvm-objdump.exe":
            if verification["tools"][tool] != {"path": str(path), "sha256": pin["sha256"]}:
                raise ValueError("original tool identity mismatch: " + tool)
        tools[tool] = {"path": str(path), "bytes": pin["bytes"], "sha256": pin["sha256"]}
    member = root.name + "/bin/llvm-objdump.exe"
    with zipfile.ZipFile(archive_path) as archive:
        if archive.namelist().count(member) != 1:
            raise ValueError("duplicate/missing fifth ZIP member")
        expected = hashlib.sha256()
        info = archive.getinfo(member)
        with archive.open(info) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                expected.update(chunk)
    if info.file_size != pins["llvm-objdump.exe"]["bytes"] or expected.hexdigest() != pins["llvm-objdump.exe"]["sha256"]:
        raise ValueError("fifth tool ZIP member mismatch")
    return tools


def berkeley_size(text):
    fields = text.splitlines()[-1].split()
    value = dict(zip(("text", "data", "bss", "total"), map(int, fields[:4])))
    if len(value) != 4 or min(value.values()) < 0 or value["total"] != sum(value[key] for key in ("text", "data", "bss")):
        raise ValueError("invalid Berkeley size record")
    return value


def public_symbols(text):
    found = []
    for block in re.findall(r"\bSymbol\s*\{([^{}]*)\}", text):
        name = re.search(r"^\s*Name:\s+(\S+)", block, re.M)
        if name and name.group(1) in PUBLIC:
            if (not re.search(r"^\s*Binding:\s+Global\b", block, re.M)
                    or not re.search(r"^\s*Type:\s+Function\b", block, re.M)
                    or not re.search(r"^\s*Section:\s+\.text", block, re.M)):
                raise ValueError("allocator export is not a defined global function")
            found.append(name.group(1))
    if sorted(found) != sorted(PUBLIC):
        raise ValueError("missing/duplicate allocator public function definitions")
    return found


def disassembly_facts(text):
    if not text.strip() or "<unknown>" in text.lower():
        raise ValueError("empty/unknown allocator disassembly")
    labels = [name for name in PUBLIC if re.search(r"<" + re.escape(name) + r">:\s*", text)]
    if len(labels) != len(PUBLIC) or not re.search(r"^\s*[0-9a-fA-F]+:\s+(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{4}|[0-9a-fA-F]{2})\s", text, re.M):
        raise ValueError("missing allocator instruction bytes/function labels")
    return {"public_labels": labels, "unknown_instructions": False,
            "scope": "Unexecuted executable-section listing/relocations; no cycle/WCET or runtime-parity inference"}


def verify_dependencies(dependencies, manifest, snapshot, toolchain):
    selected = manifest_records(manifest, {row["path"] for row in dependencies if row["owner"] == "verified_toolchain"})
    for row in dependencies:
        owner = snapshot if row["owner"] == "native_snapshot" else toolchain
        path = owner / row["path"]
        if path.is_symlink() or not path.resolve().is_relative_to(owner.resolve()) or digest(path) != row["sha256"]:
            raise ValueError("dependency changed: " + row["path"])
        if row["owner"] == "verified_toolchain" and row["sha256"] != selected[row["path"]]["sha256"]:
            raise ValueError("dependency differs from fresh verified manifest")


def verify_frozen_copies(plan, receipt, sources, baseline, native, snapshot, output):
    """Check after slow verification, before a first executable, and again at end."""
    if sources != source_facts(native, plan) or sources != source_facts(snapshot, plan):
        raise ValueError("allocator source changed during attempt")
    if (digest(PROTOCOL) != receipt["protocol_sha256"] or digest(Path(__file__)) != receipt["driver_sha256"]
            or digest(REFERENCE / "cortex_m4_objects.py") != receipt["helper_sha256"]):
        raise ValueError("allocator protocol/driver/helper changed during attempt")
    for name, key in (("protocol.json", "protocol_sha256"),
                      ("executed-allocator_cortex_m4_objects.py", "driver_sha256"),
                      ("executed-shared-helper.py", "helper_sha256"),
                      ("historical-baseline.json", "baseline_sha256")):
        if digest(output / name) != receipt[key]:
            raise ValueError("retained executed source/protocol/baseline changed")
    if load_baseline(plan) != baseline:
        raise ValueError("historical baseline changed during attempt")


def command_counts(receipt):
    """An intent is not a call. Incomplete durable pre-call records are uncertain."""
    receipt["prepared_commands"] = len(receipt["commands"])
    receipt["actual_commands"] = sum(entry.get("launch_state") in ("confirmed_return", "confirmed_error")
                                     for entry in receipt["command_slots"])
    receipt["uncertain_command_slots"] = [entry["slot"] for entry in receipt["command_slots"]
                                           if entry.get("launch_state") == "unconfirmed"]
    receipt["not_run_command_slots"] = [entry["slot"] for entry in receipt["command_slots"]
                                         if entry.get("launch_state", "not_attempted") == "not_attempted"]
    receipt["actual_commands_is_confirmed_lower_bound"] = bool(receipt["uncertain_command_slots"])
    receipt["command_count_scope"] = "Confirmed subprocess API requests, not spawned children. Prepared/unconfirmed intent is separate; interruption can leave launch uncertainty."


def artifact_failure(receipt, stage, path, error, entry=None):
    failure = {"stage": stage, "file": str(path), "error_type": type(error).__name__, "error": str(error)}
    if entry is not None:
        entry.setdefault("artifact_errors", []).append(failure)
        entry["artifact_status"] = "failed_retained"
        failure = {"command_slot": entry["slot"], **failure}
    receipt.setdefault("artifact_errors", []).append(failure)


class Recorder:
    def __init__(self, output, receipt, shared, environment):
        self.output, self.receipt, self.shared, self.environment = output, receipt, shared, environment

    def run(self, slot):
        entry = self.receipt["command_slots"][slot]
        if entry["status"] != "not_run":
            raise ValueError("command slot already used")
        # This durable intent cannot prove whether a launch subsequently occurred.
        entry.update({"status": "prepared", "launch_state": "unconfirmed", "artifact_status": "preparing"})
        self.receipt["commands"].append(entry)
        command_counts(self.receipt)
        try:
            self.persist(entry, "before_launch_receipt")
        except OSError:
            # We know run() has not been requested in this process.
            entry.update({"status": "not_launched_artifact_error", "launch_state": "not_attempted"})
            command_counts(self.receipt)
            raise
        before = time.monotonic()
        try:
            result = subprocess.run(entry["argv"], cwd=Path(entry["cwd"]), env=self.environment,
                                    capture_output=True, timeout=60, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            entry.update({"status": "launch_or_timeout_error", "error_type": type(error).__name__,
                          "error": str(error), "seconds": time.monotonic() - before,
                          "launch_state": "confirmed_error"})
            command_counts(self.receipt)
            for channel in ("stdout", "stderr"):
                self.log(entry, channel, getattr(error, channel, None) or b"")
            entry["artifact_status"] = "written"
            self.persist(entry, "after_error_receipt")
            raise
        except BaseException as error:
            # It may have reached the subprocess API. Never invent an exact count.
            entry.update({"status": "interrupted_unconfirmed", "launch_state": "unconfirmed",
                          "interruption_type": type(error).__name__, "seconds": time.monotonic() - before})
            command_counts(self.receipt)
            try:
                self.persist(entry, "interrupted_receipt")
            except OSError:
                pass  # Preserve the original interruption and the durable uncertain intent.
            raise
        # A known return is recorded before any fallible artifact operation.
        entry.update({"status": "completed", "exit_code": result.returncode, "seconds": time.monotonic() - before,
                      "launch_state": "confirmed_return"})
        command_counts(self.receipt)
        for channel in ("stdout", "stderr"):
            raw = getattr(result, channel)
            entry[channel + "_observed_bytes"] = len(raw)
            entry[channel + "_observed_sha256"] = hashlib.sha256(raw).hexdigest()
        for channel in ("stdout", "stderr"):
            self.log(entry, channel, getattr(result, channel))
        entry["artifact_status"] = "written"
        self.persist(entry, "after_return_receipt")
        return result.returncode, result.stdout.decode("utf-8")

    def persist(self, entry, stage):
        path = self.output / "receipt.json"
        try:
            self.shared.save(path, self.receipt)
        except OSError as error:
            artifact_failure(self.receipt, stage, path, error, entry)
            raise

    def log(self, entry, channel, raw):
        path = self.output / "logs" / (entry["label"] + "." + channel + ".txt")
        try:
            path.write_bytes(raw)
            actual = digest(path)
        except OSError as error:
            artifact_failure(self.receipt, channel + "_artifact", path, error, entry)
            raise
        entry[channel] = path.relative_to(self.output).as_posix()
        entry[channel + "_sha256"] = actual


def build(toolchain, archive, destination):
    plan = load_protocol()
    shared = load_shared(plan)
    baseline = load_baseline(plan)
    native = REFERENCE / "native"
    sources = source_facts(native, plan)
    protected = [PROJECT.parent, native, archive, toolchain,
                 *(Path(row["root"]) for row in baseline["historical_attempts"])]
    output = attempt_path(destination, protected)
    toolchain, archive = toolchain.resolve(), archive.resolve()
    slots, rows = schedule(plan, toolchain, output)
    receipt = {"schema": "enme408-allocator-cortex-m4-annex/v1", "status": "preparing",
        "protocol_sha256": digest(PROTOCOL), "driver_sha256": digest(Path(__file__)),
        "helper_sha256": digest(REFERENCE / "cortex_m4_objects.py"),
        "baseline_sha256": digest(PROJECT / plan["frozen_research_baseline"]["path"]),
        "source_files": sources, "planned_objects": 4, "planned_commands": 31,
        "command_slots": slots, "commands": [], "objects": rows,
        "tool_status": "not_run", "metadata_status": "not_run", "repeat_status": "not_run",
        "integrity_status": "preparing", "independent_artifact_review": "pending_separate_receipt",
        "linked_firmware": False, "target_execution_calls": 0, "limitations": plan["limitations"]}
    output.mkdir(parents=True)
    (output / "logs").mkdir()
    snapshot = output / "native"
    snapshot.mkdir()
    started = time.monotonic()
    shared.save(output / "receipt.json", receipt)
    try:
        for name in SOURCES:
            shutil.copyfile(native / name, snapshot / name)
        shutil.copyfile(PROTOCOL, output / "protocol.json")
        shutil.copyfile(Path(__file__), output / "executed-allocator_cortex_m4_objects.py")
        shutil.copyfile(REFERENCE / "cortex_m4_objects.py", output / "executed-shared-helper.py")
        shutil.copyfile(PROJECT / plan["frozen_research_baseline"]["path"], output / "historical-baseline.json")
        receipt["historical_before"] = historical_facts(baseline)
        manifest = output / "verified-toolchain-files.jsonl"
        receipt["toolchain"] = shared.verify_toolchain(archive, toolchain, plan["toolchain"], manifest)
        receipt["verified_five_tools"] = verify_five_tools(archive, toolchain, plan, receipt["toolchain"], manifest)
        verify_frozen_copies(plan, receipt, sources, baseline, native, snapshot, output)
        if digest(manifest) != receipt["toolchain"]["manifest_sha256"]:
            raise ValueError("fresh verification manifest changed before first executable")
        receipt["pre_call_frozen_copy_check"] = "passed"
        environment = shared.clean_environment(toolchain / "bin")
        environment.pop("DEBUGINFOD_URLS", None)
        recorder = Recorder(output, receipt, shared, environment)
        for slot in range(7):
            code, _ = recorder.run(slot)
            if code:
                raise ValueError("allocator tool/multilib preflight failed")
        for row in rows:
            obj = output / row["path"]
            obj.parent.mkdir(parents=True)
            row["status"] = "compile_started"
            code, _ = recorder.run(row["compile_slot"])
            if code:
                row["status"] = "compile_error"
                shared.save(output / "receipt.json", receipt)
                continue
            row.update({"status": "compiled", "sha256": digest(obj), "bytes": obj.stat().st_size})
            transcripts = []
            for slot in row["inspection_slots"]:
                code, text = recorder.run(slot)
                if code:
                    row["status"] = "inspection_error"
                    break
                transcripts.append(text)
            if row["status"] == "compiled":
                try:
                    row["public_definitions"] = public_symbols(transcripts[0])
                    row["berkeley_size"] = berkeley_size(transcripts[1])
                    row["undefined_symbols"] = [line.split()[-1] for line in transcripts[3].splitlines() if line.strip()]
                    row["disassembly"] = disassembly_facts(transcripts[4])
                    row["elf"] = shared.read_elf(obj)
                    shared.validate_abi(row["elf"]["arm_attribute_tags"], row["abi"])
                    row["stack_usage"] = shared.stack_records(obj.with_suffix(".su"))
                    row["dependency_file"] = {"path": obj.with_suffix(".d").relative_to(output).as_posix(),
                                              "sha256": digest(obj.with_suffix(".d"))}
                    row["dependencies"] = shared.dependency_facts(obj.with_suffix(".d"), snapshot, toolchain)
                    verify_dependencies(row["dependencies"], manifest, snapshot, toolchain)
                    row["status"] = "inspected"
                except (ValueError, OSError, UnicodeError, IndexError) as error:
                    row.update({"status": "metadata_error", "error_type": type(error).__name__, "error": str(error)})
            shared.save(output / "receipt.json", receipt)
        receipt["repeat_comparisons"] = []
        for abi in ABIS:
            pair = [row for row in rows if row["abi"] == abi]
            receipt["repeat_comparisons"].append({"abi": abi, "equal_object_sha256":
                all(row["status"] == "inspected" for row in pair) and pair[0]["sha256"] == pair[1]["sha256"]})
        receipt["tool_status"] = "passed" if len(receipt["commands"]) == 31 and all(
            row["status"] == "completed" and row["exit_code"] == 0 for row in slots) else "failed_retained"
        receipt["metadata_status"] = "passed" if all(row["status"] == "inspected" for row in rows) else "failed_retained"
        receipt["repeat_status"] = "passed" if all(pair["equal_object_sha256"] for pair in receipt["repeat_comparisons"]) else "failed_retained"
        verify_frozen_copies(plan, receipt, sources, baseline, native, snapshot, output)
        if digest(manifest) != receipt["toolchain"]["manifest_sha256"]:
            raise ValueError("fresh verification manifest changed")
        for tool, pin in receipt["verified_five_tools"].items():
            if digest(toolchain / "bin" / tool) != pin["sha256"]:
                raise ValueError("used tool changed during attempt")
        for row in rows:
            if row["status"] == "inspected":
                if digest(output / row["path"]) != row["sha256"]:
                    raise ValueError("object changed during attempt")
                if digest(output / row["dependency_file"]["path"]) != row["dependency_file"]["sha256"]:
                    raise ValueError("dependency record changed during attempt")
                if row["stack_usage"]["status"] == "emitted" and digest((output / row["path"]).with_suffix(".su")) != row["stack_usage"]["sha256"]:
                    raise ValueError("local stack record changed during attempt")
                verify_dependencies(row["dependencies"], manifest, snapshot, toolchain)
        receipt["historical_after"] = historical_facts(baseline)
        if receipt["historical_before"] != receipt["historical_after"]:
            raise ValueError("historical artifacts changed during attempt")
        receipt["integrity_status"] = "passed"
        receipt["status"] = "passed" if all(receipt[key] == "passed" for key in (
            "tool_status", "metadata_status", "repeat_status", "integrity_status")) else "failed_retained"
    except (Exception, KeyboardInterrupt) as error:
        for row in rows:
            if row["status"] == "compile_started":
                row["status"] = "compile_incomplete_check_command_and_artifact_status"
            elif row["status"] == "compiled":
                row["status"] = "inspection_incomplete_check_command_and_artifact_status"
        receipt.update({"status": "failed_retained", "error_type": type(error).__name__, "error": str(error)})
        command_counts(receipt)
        if receipt["tool_status"] == "not_run" and (receipt["actual_commands"] or receipt["uncertain_command_slots"]):
            receipt["tool_status"] = "failed_or_not_completed"
        if receipt["metadata_status"] == "not_run" and any(row["status"] != "not_run" for row in rows):
            receipt["metadata_status"] = "failed_or_not_completed"
        if receipt["integrity_status"] != "passed":
            receipt["integrity_status"] = "failed_or_not_completed"
    command_counts(receipt)
    receipt["elapsed_seconds"] = time.monotonic() - started
    receipt["final_receipt_persisted"] = True
    try:
        shared.save(output / "receipt.json", receipt)
    except OSError as error:
        receipt.update({"status": "failed_retained", "final_receipt_persisted": False})
        artifact_failure(receipt, "final_receipt", output / "receipt.json", error)
        # Keep known command results observable if storage remains unavailable.
        print(json.dumps({"event": "allocator_annex_receipt_write_failed", "receipt": receipt}), file=sys.stderr)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain-dir", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build(args.toolchain_dir, args.archive, args.output_dir)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "preparation_failed", "error_type": type(error).__name__, "error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps({key: receipt[key] for key in ("status", "planned_objects", "planned_commands",
          "actual_commands", "not_run_command_slots", "target_execution_calls")}))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
