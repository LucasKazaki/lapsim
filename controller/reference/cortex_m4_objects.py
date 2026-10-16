"""Strict binary64 Cortex-M4 object evidence. Never link or execute target code."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import struct
import subprocess
import sys
import time
import zipfile

REFERENCE = Path(__file__).resolve().parent
PROTOCOL = REFERENCE.parent / "research/TC-03E-cortex-m4-object-protocol.json"
PROTOCOL_SHA256 = "c1c8117a1c8a1e765afb8c2e44ab0362af7cbd296806a07498c348505fbf8f2a"
UNITS = ("torque_contract", "torque_clock", "torque_pedal")
ABIS = ("hard", "softfp")
TOOLS = ("clang.exe", "llvm-readobj.exe", "llvm-size.exe", "llvm-nm.exe")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def save(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_protocol(path: Path = PROTOCOL) -> dict:
    if digest(path) != PROTOCOL_SHA256:
        raise ValueError("frozen protocol identity mismatch")
    plan = json.loads(path.read_text(encoding="utf-8"))
    matrix = plan["build_matrix"]
    if (tuple(matrix["abis"]) != ABIS or matrix["repetitions"] != 2 or
            matrix["translation_units"] != [u + ".c" for u in UNITS] or matrix["planned_objects"] != 12):
        raise ValueError("unexpected object matrix")
    return plan


def source_facts(native: Path, plan: dict) -> dict:
    expected = {u + suffix for u in UNITS for suffix in (".c", ".h")}
    if set(plan["sources"]) != expected:
        raise ValueError("unexpected source cohort")
    result = {}
    for name in sorted(expected):
        path = native / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("source must be an ordinary file: " + name)
        raw = path.read_bytes()  # Six small source/header files, never a tool/archive.
        if hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() != plan["sources"][name]["lf_normalized_sha256"]:
            raise ValueError("frozen source changed: " + name)
        result[name] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    return result


def output_path(path: Path, native: Path) -> Path:
    resolved = path.resolve()
    source_root = native.resolve()
    if path.exists() or path.is_symlink():
        raise ValueError("refusing an existing attempt")
    if resolved == source_root or resolved.is_relative_to(source_root) or source_root.is_relative_to(resolved):
        raise ValueError("attempt must not contain or overlap native source")
    return resolved


def safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (path.is_absolute() or ".." in path.parts or "\\" in name or
            not path.parts or any(":" in part for part in path.parts)):
        raise ValueError("unsafe ZIP path")
    return path


def verify_toolchain(archive_path: Path, root: Path, identity: dict, log: Path) -> dict:
    """Verify the entire extracted tree against the pinned archive before execution.

    Files are streamed serially. The aggregate manifest is JSONL on disk rather
    than retaining large executable bytes or per-file dictionaries in memory.
    """
    if (archive_path.stat().st_size != identity["archive_bytes"] or
            archive_path.stat().st_size > identity["archive_size_cap_bytes"] or
            digest(archive_path) != identity["archive_sha256"]):
        raise ValueError("official archive size/hash mismatch")
    started = time.monotonic()
    found = set()
    tools = {}
    licenses = []
    root = root.resolve()
    with zipfile.ZipFile(archive_path) as archive, log.open("x", encoding="utf-8") as output:
        for member in archive.infolist():
            path = safe_member(member.filename)
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError("ZIP symlink is unsupported")
            if path.parts[0] != root.name:
                raise ValueError("toolchain directory does not match archive root")
            if member.is_dir():
                continue
            relative = PurePosixPath(*path.parts[1:]).as_posix()
            if relative in found:
                raise ValueError("duplicate archive file")
            local = root / relative
            if not local.resolve().is_relative_to(root) or local.is_symlink() or not local.is_file():
                raise ValueError("unsafe/missing extracted file: " + relative)
            expected = hashlib.sha256()
            with archive.open(member) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    expected.update(chunk)
            actual = digest(local)
            if local.stat().st_size != member.file_size or actual != expected.hexdigest():
                raise ValueError("extracted file differs from verified ZIP: " + relative)
            found.add(relative)
            output.write(json.dumps({"path": relative, "bytes": member.file_size, "sha256": actual}) + "\n")
            if relative in {"bin/" + name for name in TOOLS}:
                tools[Path(relative).name] = {"path": str(local), "sha256": actual}
            if local.name.upper().startswith(("LICENSE", "NOTICE", "COPYING")):
                licenses.append({"path": relative, "sha256": actual})
    actual_paths = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual_paths != found or set(tools) != set(TOOLS):
        raise ValueError("extra/missing extracted files or tools")
    return {"archive_sha256": identity["archive_sha256"], "archive_bytes": identity["archive_bytes"],
            "verified_file_count": len(found), "tools": tools, "manifest_sha256": digest(log),
            "license_files": licenses, "verification_seconds": time.monotonic() - started}


def clean_environment(bin_directory: Path) -> dict:
    env = os.environ.copy()
    for name in ("CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "OBJC_INCLUDE_PATH", "CCC_OVERRIDE_OPTIONS",
                 "CLANG_CONFIG_FILE_SYSTEM_DIR", "CLANG_CONFIG_FILE_USER_DIR", "SDKROOT", "GCC_EXEC_PREFIX",
                 "COMPILER_PATH", "LIBRARY_PATH", "CFLAGS", "CPPFLAGS", "CC"):
        env.pop(name, None)
    windows = Path(env.get("SystemRoot", "C:/Windows"))
    env["PATH"] = os.pathsep.join(map(str, (bin_directory, windows / "System32", windows)))
    return env


def compile_args(tool: Path, flags: list, abi: str, unit: str, destination: Path) -> list[str]:
    if abi not in ABIS or unit not in UNITS:
        raise ValueError("unsupported ABI/unit")
    if flags != load_protocol()["compile_common_flags"]:
        raise ValueError("compile flags differ from exact frozen list/order")
    return [str(tool), *flags, "-mfloat-abi=" + abi, "-MD", "-MF", str(destination.with_suffix(".d")),
            "-c", unit + ".c", "-o", str(destination)]


def read_elf(path: Path) -> dict:
    raw = path.read_bytes()  # Generated objects are small; never load toolchain binaries.
    if len(raw) < 52 or raw[:6] != b"\x7fELF\x01\x01":
        raise ValueError("expected ELF32 little-endian object")
    header = struct.unpack_from("<16sHHIIIIIHHHHHH", raw)
    if header[1] != 1 or header[2] != 40:
        raise ValueError("expected ARM relocatable object")
    offset, stride, count, names_index = header[6], header[11], header[12], header[13]
    if stride != 40 or count == 0 or names_index >= count or offset + stride * count > len(raw):
        raise ValueError("invalid ELF section table")
    sections = [struct.unpack_from("<IIIIIIIIII", raw, offset + i * stride) for i in range(count)]
    names = sections[names_index]
    strings = raw[names[4]:names[4] + names[5]]
    values = []
    attributes = None
    for section in sections:
        if section[0] >= len(strings):
            raise ValueError("invalid ELF section name")
        name = strings[section[0]:].split(b"\0", 1)[0].decode("ascii")
        if section[1] != 8 and section[4] + section[5] > len(raw):
            raise ValueError("section extends beyond object")
        values.append({"name": name, "type": section[1], "flags": section[2], "bytes": section[5]})
        if name == ".ARM.attributes":
            attributes = raw[section[4]:section[4] + section[5]]
    if attributes is None:
        raise ValueError("missing ARM attributes")
    return {"class": "ELF32", "byte_order": "little", "type": "relocatable", "machine": "ARM",
            "flags": header[7], "sections": values, "arm_attribute_tags": arm_tags(attributes)}


def arm_tags(raw: bytes) -> dict[int, object]:
    if not raw or raw[0] != 0x41:
        raise ValueError("invalid ARM attributes format")
    tags = {}
    position = 1

    def uleb(index, end):
        value = shift = 0
        while index < end and shift < 35:
            byte = raw[index]
            index += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value, index
            shift += 7
        raise ValueError("invalid attribute integer")

    def string(index, end):
        finish = raw.find(b"\0", index, end)
        if finish < 0:
            raise ValueError("unterminated attribute string")
        return raw[index:finish].decode("ascii"), finish + 1

    while position < len(raw):
        start = position
        if position + 4 > len(raw):
            raise ValueError("truncated vendor length")
        length = struct.unpack_from("<I", raw, position)[0]
        end = start + length
        if length < 5 or end > len(raw):
            raise ValueError("invalid vendor length")
        vendor, position = string(position + 4, end)
        while position < end:
            sub_start = position
            tag, position = uleb(position, end)
            if position + 4 > end:
                raise ValueError("truncated subsection")
            sub_end = sub_start + struct.unpack_from("<I", raw, position)[0]
            position += 4
            if sub_end < position or sub_end > end:
                raise ValueError("invalid attribute subsection length")
            if vendor != "aeabi" or tag != 1:
                position = sub_end
                continue
            while position < sub_end:
                key, position = uleb(position, sub_end)
                if key in (4, 5) or key >= 32 and key % 2 == 1:
                    value, position = string(position, sub_end)
                else:
                    value, position = uleb(position, sub_end)
                    if key == 32:
                        suffix, position = string(position, sub_end)
                        value = [value, suffix]
                if key in tags and tags[key] != value:
                    raise ValueError("contradictory ARM attributes")
                tags[key] = value
        position = end
    return tags


def validate_abi(tags: dict, abi: str) -> None:
    if abi not in ABIS or tags.get(6) != 13 or tags.get(7) != 77 or tags.get(9) != 2:
        raise ValueError("expected ARMv7E-M, M-profile and Thumb-2 attributes")
    if tags.get(10) != 6 or tags.get(27) != 1:
        raise ValueError("expected VFPv4-D16/single-precision-only permission tags")
    if tags.get(28, 0) != (1 if abi == "hard" else 0):
        raise ValueError("unexpected floating-point argument ABI")


def stack_records(path: Path) -> dict:
    if not path.is_file():
        return {"status": "not_emitted", "records": []}
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or not fields[1].isdigit():
            raise ValueError("unrecognized Clang stack-usage record")
        rows.append({"location": fields[0], "function": fields[0].rsplit(":", 1)[-1],
                     "bytes": int(fields[1]), "qualifier": fields[2]})
    return {"status": "emitted", "sha256": digest(path), "records": rows,
            "scope": "Compiler-local frame only; excludes callees/helper frames, interrupts, scheduler and FPU context"}


def dependency_names(text: str) -> list[str]:
    """Clang make-dependency words, including its literal Windows backslashes.

    These are make records, not shell words. A backslash before an ordinary
    drive-path character is literal; escaped whitespace/hash/colon is unquoted.
    """
    text = text.replace("\r\n", "\n").replace("\\\n", " ")
    if ": " not in text:
        raise ValueError("unrecognized make dependency record")
    body = text.split(": ", 1)[1]
    words, current = [], []
    index = 0
    while index < len(body):
        char = body[index]
        if char == "\\" and index + 1 < len(body) and body[index + 1] in " \t#:":
            current.append(body[index + 1])
            index += 2
            continue
        if char.isspace():
            if current:
                words.append("".join(current))
                current = []
        else:
            current.append(char)
        index += 1
    if current:
        words.append("".join(current))
    return words


def dependency_facts(path: Path, snapshot: Path, toolchain: Path) -> list[dict]:
    snapshot, toolchain = snapshot.resolve(), toolchain.resolve()
    files = []
    for name in dependency_names(path.read_text(encoding="utf-8")):
        resolved = (snapshot / name).resolve()
        owner = snapshot if resolved.is_relative_to(snapshot.resolve()) else toolchain
        if not resolved.is_relative_to(owner.resolve()) or not resolved.is_file():
            raise ValueError("dependency outside verified source/toolchain: " + name)
        files.append({"owner": "native_snapshot" if owner == snapshot else "verified_toolchain",
                      "path": resolved.relative_to(owner).as_posix(), "sha256": digest(resolved)})
    if not files:
        raise ValueError("empty dependency record")
    return files


def build(toolchain: Path, archive: Path, out: Path) -> dict:
    plan = load_protocol()
    native = REFERENCE / "native"
    sources = source_facts(native, plan)
    out = output_path(out, native)
    out.mkdir(parents=True)
    (out / "logs").mkdir()
    snapshot = out / "native"
    snapshot.mkdir()
    for name in sources:
        shutil.copyfile(native / name, snapshot / name)
    shutil.copyfile(PROTOCOL, out / "protocol.json")
    shutil.copyfile(Path(__file__), out / "executed-cortex_m4_objects.py")
    receipt = {"schema": "enme408-cortex-m4-objects/v1", "status": "preparing", "protocol_sha256": digest(PROTOCOL),
               "runner_sha256": digest(Path(__file__)), "source_files": sources, "commands": [],
               "runtime": {"python": sys.version, "platform": platform.platform(), "machine": platform.machine()},
               "objects": [{"repeat": repeat, "abi": abi, "unit": unit, "status": "not_run"}
                           for repeat in (1, 2) for abi in ABIS for unit in UNITS],
               "target_execution_calls": 0, "linked_firmware": False, "limitations": plan["limitations"]}
    started = time.monotonic()
    save(out / "receipt.json", receipt)
    try:
        receipt["toolchain"] = verify_toolchain(archive, toolchain, plan["toolchain"], out / "verified-toolchain-files.jsonl")
        env = clean_environment(toolchain / "bin")

        def command(tool, arguments, label):
            args = [str(toolchain / "bin" / tool), *arguments]
            before = time.monotonic()
            entry = {"argv": args, "cwd": "native snapshot", "status": "starting"}
            receipt["commands"].append(entry)
            save(out / "receipt.json", receipt)
            try:
                result = subprocess.run(args, cwd=snapshot, env=env, capture_output=True, timeout=60, check=False)
            except (OSError, subprocess.TimeoutExpired) as error:
                entry.update({"status": "launch_or_timeout_error", "error_type": type(error).__name__,
                              "error": str(error), "seconds": time.monotonic() - before})
                save(out / "receipt.json", receipt)
                raise
            stdout, stderr = out / "logs" / (label + ".stdout.txt"), out / "logs" / (label + ".stderr.txt")
            stdout.write_bytes(result.stdout)
            stderr.write_bytes(result.stderr)
            entry.update({"status": "completed", "exit_code": result.returncode,
                "seconds": time.monotonic() - before, "stdout": stdout.relative_to(out).as_posix(), "stdout_sha256": digest(stdout),
                "stderr": stderr.relative_to(out).as_posix(), "stderr_sha256": digest(stderr)})
            save(out / "receipt.json", receipt)
            return result.returncode, result.stdout.decode("utf-8"), result.stderr.decode("utf-8")

        for name in TOOLS:
            code, _, _ = command(name, ["--version"], "version-" + Path(name).stem)
            if code:
                raise ValueError("tool preflight failed: " + name)
        for abi in ABIS:
            code, _, _ = command("clang.exe", plan["preflight_commands"][-1][1:-2] + ["-mfloat-abi=" + abi, "-print-multi-directory"], "multilib-" + abi)
            if code:
                raise ValueError("multilib preflight failed: " + abi)
        for row in receipt["objects"]:
            folder = out / ("repeat-" + str(row["repeat"])) / row["abi"]
            folder.mkdir(parents=True, exist_ok=True)
            obj = folder / (row["unit"] + ".o")
            label = str(row["repeat"]) + "-" + row["abi"] + "-" + row["unit"]
            arguments = compile_args(toolchain / "bin/clang.exe", plan["compile_common_flags"], row["abi"], row["unit"], obj)
            code, _, _ = command("clang.exe", arguments[1:], "compile-" + label)
            if code:
                row["status"] = "compile_error"
                continue
            row.update({"status": "compiled", "path": obj.relative_to(out).as_posix(), "sha256": digest(obj), "bytes": obj.stat().st_size})
            for index, inspection in enumerate(plan["inspection_commands"]):
                code, stdout, _ = command(inspection[0], inspection[1:-1] + [str(obj)], "inspect-" + label + "-" + str(index))
                if code:
                    row["status"] = "inspection_error"
                    break
                if index == 1:
                    fields = stdout.splitlines()[-1].split()
                    row["berkeley_size"] = dict(zip(("text", "data", "bss", "total"), map(int, fields[:4])))
                if index == 3:
                    row["undefined_symbols"] = [line.split()[-1] for line in stdout.splitlines() if line.strip()]
            if row["status"] == "compiled":
                try:
                    row["elf"] = read_elf(obj)
                    validate_abi(row["elf"]["arm_attribute_tags"], row["abi"])
                    row["stack_usage"] = stack_records(obj.with_suffix(".su"))
                    row["dependency_file"] = {"path": obj.with_suffix(".d").relative_to(out).as_posix(), "sha256": digest(obj.with_suffix(".d"))}
                    row["dependencies"] = dependency_facts(obj.with_suffix(".d"), snapshot, toolchain)
                    row["status"] = "inspected"
                except (ValueError, OSError, UnicodeError) as error:
                    row.update({"status": "metadata_error", "error": str(error)})
            save(out / "receipt.json", receipt)
        pairs = []
        for abi in ABIS:
            for unit in UNITS:
                rows = [r for r in receipt["objects"] if r["abi"] == abi and r["unit"] == unit]
                pairs.append({"abi": abi, "unit": unit, "equal_object_sha256": all(r["status"] == "inspected" for r in rows)
                              and rows[0]["sha256"] == rows[1]["sha256"]})
        receipt["repeat_comparisons"] = pairs
        if sources != source_facts(native, plan) or sources != source_facts(snapshot, plan):
            raise ValueError("source changed during build")
        receipt["status"] = "passed" if all(r["status"] == "inspected" for r in receipt["objects"]) and all(p["equal_object_sha256"] for p in pairs) else "failed_retained"
    except Exception as error:
        receipt.update({"status": "failed_retained", "error_type": type(error).__name__, "error": str(error)})
    receipt["elapsed_seconds"] = time.monotonic() - started
    save(out / "receipt.json", receipt)
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain-dir", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    result = build(args.toolchain_dir.resolve(), args.archive.resolve(), args.output_dir)
    print(json.dumps({"status": result["status"], "planned": 12,
                      "inspected": sum(row["status"] == "inspected" for row in result["objects"]), "target_execution_calls": 0}))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
