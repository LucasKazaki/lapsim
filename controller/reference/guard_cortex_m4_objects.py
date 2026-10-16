"""Separate four-object base-guard annex. Never link or execute target code."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import time

REFERENCE = Path(__file__).resolve().parent
PROTOCOL = REFERENCE.parent / "research/TC-03G-base-guard-object-protocol.json"
PROTOCOL_SHA256 = "6fd1aa2c1aab66d5fef12ccb46d727e233ecc1d4a531eb21e7148e55ad9b8d20"
SOURCES = ("torque_guard.c", "torque_guard.h", "torque_contract.h")
ABIS = ("hard", "softfp")
TOOLS = ("clang.exe", "llvm-readobj.exe", "llvm-size.exe", "llvm-nm.exe")


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""): value.update(chunk)
    return value.hexdigest()


def load_protocol(path=PROTOCOL):
    if digest(path) != PROTOCOL_SHA256: raise ValueError("frozen annex protocol changed")
    plan = json.loads(path.read_text(encoding="utf-8"))
    matrix = plan["matrix"]
    if (set(plan["sources"]) != set(SOURCES) or matrix["units"] != ["torque_guard.c"]
            or tuple(matrix["abis"]) != ABIS or matrix["repetitions"] != 2
            or matrix["planned_objects"] != 4 or matrix["planned_commands"] != 26):
        raise ValueError("unexpected annex cohort or matrix")
    original = REFERENCE.parent / "research/TC-03E-cortex-m4-object-protocol.json"
    if digest(original) != plan["original_protocol_sha256"]:
        raise ValueError("historical three-unit protocol changed")
    return plan


def load_shared(plan):
    # Verify before import: the reviewed module is executable Python source.
    path = REFERENCE / "cortex_m4_objects.py"
    if digest(path) != plan["shared_helper"]["sha256"]:
        raise ValueError("frozen metadata/verification helper changed")
    spec = importlib.util.spec_from_file_location("verified_guard_annex_helpers", path)
    if spec is None or spec.loader is None: raise ValueError("cannot load frozen helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_facts(native, plan):
    result = {}
    if set(plan["sources"]) != set(SOURCES): raise ValueError("unexpected annex sources")
    for name in SOURCES:
        path = native / name
        if path.is_symlink() or not path.is_file(): raise ValueError("ordinary annex source required: " + name)
        raw = path.read_bytes()
        if hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() != plan["sources"][name]["lf_normalized_sha256"]:
            raise ValueError("frozen annex source changed: " + name)
        result[name] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    return result


def compile_args(tool, flags, abi, unit, obj):
    if abi not in ABIS or unit != "torque_guard": raise ValueError("unexpected annex ABI/unit")
    if flags != load_protocol()["compile_common_flags"]: raise ValueError("exact frozen annex flags/order required")
    return [str(tool), *flags, "-mfloat-abi=" + abi, "-MD", "-MF", str(obj.with_suffix(".d")),
            "-c", "torque_guard.c", "-o", str(obj)]


def build(toolchain, archive, output):
    plan = load_protocol()
    shared = load_shared(plan)
    native = REFERENCE / "native"
    sources = source_facts(native, plan)
    output = shared.output_path(output, native)
    # A new annex must not become a child of a retained attempt.
    if any((parent / "receipt.json").is_file() for parent in output.parents):
        raise ValueError("annex must be outside retained attempt directories")
    output.mkdir(parents=True)
    (output / "logs").mkdir()
    snapshot = output / "native"
    snapshot.mkdir()
    for name in SOURCES: shutil.copyfile(native / name, snapshot / name)
    shutil.copyfile(PROTOCOL, output / "protocol.json")
    shutil.copyfile(Path(__file__), output / "executed-guard_cortex_m4_objects.py")
    shutil.copyfile(REFERENCE / "cortex_m4_objects.py", output / "executed-shared-helper.py")
    receipt = {"schema": "enme408-base-guard-cortex-m4-annex/v1", "status": "preparing",
        "protocol_sha256": digest(PROTOCOL), "driver_sha256": digest(Path(__file__)),
        "helper_sha256": digest(REFERENCE / "cortex_m4_objects.py"), "source_files": sources,
        "planned_objects": 4, "planned_commands": 26, "commands": [],
        "objects": [{"repeat": repeat, "abi": abi, "unit": "torque_guard", "status": "not_run"}
                    for repeat in (1, 2) for abi in ABIS],
        "linked_firmware": False, "target_execution_calls": 0, "limitations": plan["limitations"]}
    started = time.monotonic()
    shared.save(output / "receipt.json", receipt)
    try:
        receipt["toolchain"] = shared.verify_toolchain(archive, toolchain, plan["toolchain"],
                                                     output / "verified-toolchain-files.jsonl")
        toolchain = toolchain.resolve()
        environment = shared.clean_environment(toolchain / "bin")

        def command(tool, arguments, label):
            if tool not in TOOLS: raise ValueError("unexpected annex executable")
            argv = [str(toolchain / "bin" / tool), *arguments]
            entry = {"argv": argv, "cwd": "native snapshot", "status": "starting"}
            receipt["commands"].append(entry)
            shared.save(output / "receipt.json", receipt)
            before = time.monotonic()
            try:
                result = subprocess.run(argv, cwd=snapshot, env=environment, capture_output=True,
                                        timeout=60, check=False)
            except (OSError, subprocess.TimeoutExpired) as error:
                entry.update({"status": "launch_or_timeout_error", "error": str(error),
                              "error_type": type(error).__name__, "seconds": time.monotonic() - before})
                for channel in ("stdout", "stderr"):
                    path = output / "logs" / (label + "." + channel + ".txt")
                    path.write_bytes(getattr(error, channel, None) or b"")
                    entry[channel] = path.relative_to(output).as_posix()
                    entry[channel + "_sha256"] = digest(path)
                shared.save(output / "receipt.json", receipt)
                raise
            for channel in ("stdout", "stderr"):
                path = output / "logs" / (label + "." + channel + ".txt")
                path.write_bytes(getattr(result, channel))
                entry[channel] = path.relative_to(output).as_posix()
                entry[channel + "_sha256"] = digest(path)
            entry.update({"status": "completed", "exit_code": result.returncode,
                          "seconds": time.monotonic() - before})
            shared.save(output / "receipt.json", receipt)
            return result.returncode, result.stdout.decode("utf-8")

        for tool in TOOLS:
            code, _ = command(tool, ["--version"], "version-" + Path(tool).stem)
            if code: raise ValueError("annex tool preflight failed")
        for abi in ABIS:
            code, _ = command("clang.exe", plan["preflight_commands"][-1][1:-2] +
                ["-mfloat-abi=" + abi, "-print-multi-directory"], "multilib-" + abi)
            if code: raise ValueError("annex multilib preflight failed")
        for row in receipt["objects"]:
            folder = output / ("repeat-" + str(row["repeat"])) / row["abi"]
            folder.mkdir(parents=True)
            obj = folder / "torque_guard.o"
            label = f"{row['repeat']}-{row['abi']}-torque_guard"
            argv = compile_args(toolchain / "bin/clang.exe", plan["compile_common_flags"], row["abi"], row["unit"], obj)
            row["status"] = "compile_started"
            code, _ = command("clang.exe", argv[1:], "compile-" + label)
            if code:
                row["status"] = "compile_error"
                shared.save(output / "receipt.json", receipt)
                continue
            row.update({"status": "compiled", "path": obj.relative_to(output).as_posix(),
                        "sha256": digest(obj), "bytes": obj.stat().st_size})
            for index, inspection in enumerate(plan["inspection_commands"]):
                code, stdout = command(inspection[0], inspection[1:-1] + [str(obj)],
                                       "inspect-" + label + "-" + str(index))
                if code:
                    row["status"] = "inspection_error"
                    break
                if index == 1:
                    fields = stdout.splitlines()[-1].split()
                    row["berkeley_size"] = dict(zip(("text", "data", "bss", "total"), map(int, fields[:4])))
                if index == 3: row["undefined_symbols"] = [line.split()[-1] for line in stdout.splitlines() if line.strip()]
            if row["status"] == "compiled":
                try:
                    row["elf"] = shared.read_elf(obj)
                    shared.validate_abi(row["elf"]["arm_attribute_tags"], row["abi"])
                    row["stack_usage"] = shared.stack_records(obj.with_suffix(".su"))
                    row["dependency_file"] = {"path": obj.with_suffix(".d").relative_to(output).as_posix(),
                                              "sha256": digest(obj.with_suffix(".d"))}
                    row["dependencies"] = shared.dependency_facts(obj.with_suffix(".d"), snapshot, toolchain)
                    row["status"] = "inspected"
                except (ValueError, OSError, UnicodeError) as error:
                    row.update({"status": "metadata_error", "error": str(error)})
            shared.save(output / "receipt.json", receipt)
        receipt["repeat_comparisons"] = []
        for abi in ABIS:
            pair = [row for row in receipt["objects"] if row["abi"] == abi]
            receipt["repeat_comparisons"].append({"abi": abi,
                "equal_object_sha256": all(row["status"] == "inspected" for row in pair) and pair[0]["sha256"] == pair[1]["sha256"]})
        if sources != source_facts(native, plan) or sources != source_facts(snapshot, plan):
            raise ValueError("annex source changed during experiment")
        if (digest(PROTOCOL) != receipt["protocol_sha256"]
                or digest(REFERENCE / "cortex_m4_objects.py") != receipt["helper_sha256"]
                or digest(Path(__file__)) != receipt["driver_sha256"]):
            raise ValueError("annex protocol/helper changed during experiment")
        load_protocol()  # Also rechecks the unchanged historical protocol.
        passed = (all(row["status"] == "inspected" for row in receipt["objects"])
                  and all(pair["equal_object_sha256"] for pair in receipt["repeat_comparisons"])
                  and len(receipt["commands"]) == 26)
        receipt["status"] = "passed" if passed else "failed_retained"
    except Exception as error:
        for row in receipt["objects"]:
            if row["status"] == "compile_started": row["status"] = "compile_launch_or_timeout_error"
        receipt.update({"status": "failed_retained", "error_type": type(error).__name__, "error": str(error)})
    receipt["elapsed_seconds"] = time.monotonic() - started
    shared.save(output / "receipt.json", receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain-dir", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    result = build(args.toolchain_dir.resolve(), args.archive.resolve(), args.output_dir)
    print(json.dumps({"status": result["status"], "planned_objects": 4,
                      "inspected": sum(row["status"] == "inspected" for row in result["objects"]),
                      "target_execution_calls": 0}))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__": raise SystemExit(main())
