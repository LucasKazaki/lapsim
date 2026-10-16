"""File-only audit of existing Cortex-M4 objects; never invokes any tool."""
import argparse
import json
from pathlib import Path

import cortex_m4_objects as evidence


def child(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("artifact escapes original attempt")
    return path


def require(test: bool, message: str) -> None:
    if not test:
        raise ValueError(message)


def reaccount(run: Path, output: Path) -> dict:
    run, output = run.resolve(), output.resolve()
    require(not output.exists() and not output.is_relative_to(run), "preserve original attempt and existing audit")
    receipt = json.loads((run / "receipt.json").read_text(encoding="utf-8"))
    original_hash = evidence.digest(run / "receipt.json")
    require(receipt["schema"] == "enme408-cortex-m4-objects/v1", "unexpected original receipt")
    require(receipt["protocol_sha256"] == evidence.PROTOCOL_SHA256 == evidence.digest(run / "protocol.json"), "protocol changed")
    require(receipt["runner_sha256"] == evidence.digest(run / "executed-cortex_m4_objects.py"), "executed source changed")
    require(receipt["target_execution_calls"] == 0 and receipt["linked_firmware"] is False, "unexpected execution scope")
    plan = evidence.load_protocol(run / "protocol.json")
    require(evidence.source_facts(run / "native", plan) == receipt["source_files"], "snapshot changed")
    require(evidence.digest(run / "verified-toolchain-files.jsonl") == receipt["toolchain"]["manifest_sha256"], "toolchain manifest changed")
    tools = receipt["toolchain"]["tools"]
    toolchain = Path(tools["clang.exe"]["path"]).parent.parent
    require(len(receipt["commands"]) == 66, "expected four versions, two multilib, twelve compile and forty-eight inspections")
    for command in receipt["commands"]:
        require(command["status"] == "completed" and command["exit_code"] == 0, "original tool call did not complete")
        for name in ("stdout", "stderr"):
            require(evidence.digest(child(run, command[name])) == command[name + "_sha256"], "command log changed")
    order = [(repeat, abi, unit) for repeat in (1, 2) for abi in evidence.ABIS for unit in evidence.UNITS]
    require([(r["repeat"], r["abi"], r["unit"]) for r in receipt["objects"]] == order, "original denominator/order changed")
    rows = []
    wanted_headers = {}
    for row in receipt["objects"]:
        require(row["status"] == "metadata_error" and "dependency outside verified" in row["error"], "unexpected original failure")
        obj = child(run, row["path"])
        require(evidence.digest(obj) == row["sha256"] and obj.stat().st_size == row["bytes"], "original object changed")
        # Validate each compiler invocation against the protocol without launching it.
        expected = evidence.compile_args(Path(tools["clang.exe"]["path"]), plan["compile_common_flags"], row["abi"], row["unit"], obj)
        require(sum(c["argv"] == expected for c in receipt["commands"]) == 1, "compile arguments differ from protocol")
        elf = evidence.read_elf(obj)
        evidence.validate_abi(elf["arm_attribute_tags"], row["abi"])
        require(json.loads(json.dumps(elf)) == row["elf"], "ELF accounting changed")
        stack = evidence.stack_records(obj.with_suffix(".su"))
        require(stack == row["stack_usage"], "stack record changed")
        require(evidence.digest(obj.with_suffix(".d")) == row["dependency_file"]["sha256"], "dependency file changed")
        dependencies = evidence.dependency_facts(obj.with_suffix(".d"), run / "native", toolchain)
        for value in dependencies:
            if value["owner"] == "verified_toolchain":
                if value["path"] in wanted_headers:
                    require(wanted_headers[value["path"]] == value["sha256"], "header changed between objects")
                wanted_headers[value["path"]] = value["sha256"]
            else:
                require(receipt["source_files"][value["path"]]["sha256"] == value["sha256"], "native dependency changed")
        label = f"{row['repeat']}-{row['abi']}-{row['unit']}"
        nm = child(run, "logs/inspect-" + label + "-3.stdout.txt")
        undefined = [line.split()[-1] for line in nm.read_text().splitlines() if line.strip()]
        require(undefined == row["undefined_symbols"], "undefined symbols changed")
        size_output = child(run, "logs/inspect-" + label + "-1.stdout.txt").read_text().splitlines()[-1].split()
        size = dict(zip(("text", "data", "bss", "total"), map(int, size_output[:4])))
        require(size == row["berkeley_size"], "size accounting changed")
        rows.append({**row, "original_status": row["status"], "original_error": row["error"],
                     "status": "audited_existing_object", "dependencies": dependencies})
    found = set()
    with (run / "verified-toolchain-files.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            value = json.loads(line)
            if value["path"] in wanted_headers:
                require(value["sha256"] == wanted_headers[value["path"]], "dependency differs from pre-call verified toolchain")
                found.add(value["path"])
    require(found == set(wanted_headers), "dependency not in pre-call verified toolchain")
    repeats = []
    for abi in evidence.ABIS:
        for unit in evidence.UNITS:
            pair = [r for r in rows if r["abi"] == abi and r["unit"] == unit]
            require(pair[0]["sha256"] == pair[1]["sha256"], "repeated object bytes differ")
            repeats.append({"abi": abi, "unit": unit, "equal_object_sha256": True})
    require(evidence.digest(run / "receipt.json") == original_hash, "original receipt mutated")
    result = {"schema": "enme408-cortex-m4-file-only-reaccount/v1", "status": "passed_file_only_audit",
        "original_receipt_sha256": original_hash, "original_status": receipt["status"],
        "original_executed_runner_sha256": receipt["runner_sha256"], "postrun_library_sha256": evidence.digest(Path(evidence.__file__)),
        "auditor_sha256": evidence.digest(Path(__file__)), "protocol_sha256": receipt["protocol_sha256"],
        "new_compiler_or_tool_calls": 0, "target_execution_calls": 0,
        "planned_objects": 12, "audited_objects": len(rows), "verified_command_logs": 66,
        "precall_verified_dependency_files": len(found), "objects": rows, "repeat_comparisons": repeats,
        "correction": "POSIX shell tokenization removed literal Windows drive-path backslashes. Post-run make-word parsing preserves them and escaped spaces/continuations. No object/source/flags/protocol or original receipt changed.",
        "limitations": plan["limitations"]}
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = reaccount(args.run, args.output)
    print(json.dumps({"status": result["status"], "objects": result["audited_objects"], "new_tool_calls": 0}))


if __name__ == "__main__":
    main()
