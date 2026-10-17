"""Link original five-owner binary64 core for a generic QEMU STM32F405 bench."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(toolchain: Path, output: Path) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    suffix = ".exe" if sys.platform == "win32" else ""
    compiler = toolchain / "bin" / ("arm-none-eabi-gcc" + suffix)
    size = toolchain / "bin" / ("arm-none-eabi-size" + suffix)
    version = subprocess.run(
        [str(compiler), "--version"],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    ).stdout.splitlines()[0]
    if "12.3.1" not in version:
        raise ValueError("this frozen bench build requires Arm GNU GCC 12.3.1")
    native = ROOT / "controller/reference/native"
    bench = ROOT / "firmware/bench"
    sources = [
        native / name
        for name in (
            "torque_contract.c",
            "torque_clock.c",
            "torque_pedal.c",
            "torque_guard.c",
            "torque_allocator.c",
        )
    ]
    harness = [bench / "startup.c", bench / "main.c", bench / "f405-qemu.ld"]
    bindings = {
        p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest()
        for p in [*sources, *sorted(native.glob("torque_*.h")), *harness]
    }
    flags = [
        "-mcpu=cortex-m4",
        "-mthumb",
        "-mfloat-abi=soft",
        "-std=c11",
        "-Os",
        "-g3",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-pedantic",
        "-fno-fast-math",
        "-fno-finite-math-only",
        "-ffp-contract=off",
        "-fexcess-precision=standard",
        "-ffunction-sections",
        "-fdata-sections",
        "-nostartfiles",
        "--specs=nosys.specs",
    ]
    identity = {
        "source_files_sha256": bindings,
        "compiler_version": version,
        "flags": flags,
        "platform": "qemu-netduinoplus2-stm32f405",
        "controller_policy": {
            "period_ms": 10,
            "maximum_age_ms": 50,
            "rise_nm_per_s": 8000,
            "trip": 0.25,
            "clear": 0.05,
            "recover_samples": 2,
        },
        "numeric_contract": "binary64 software helpers; no float32 substitution",
    }
    build_id = sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (output / "build_id.h").write_text(
        '#define LAPSIM_BUILD_ID "' + build_id + '"\n', encoding="ascii"
    )
    elf = output / "lapsim-f405-bench.elf"
    link_map = output / "lapsim-f405-bench.map"
    command = [
        str(compiler),
        *flags,
        "-I",
        str(native),
        "-I",
        str(output),
        "-T",
        str(bench / "f405-qemu.ld"),
        *[str(p) for p in [bench / "startup.c", bench / "main.c", *sources]],
        "-Wl,--gc-sections",
        "-Wl,-Map=" + str(link_map),
        "-o",
        str(elf),
        "-lm",
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, cwd=ROOT, timeout=90, check=False
    )
    (output / "compile-stdout.txt").write_text(result.stdout, encoding="utf-8")
    (output / "compile-stderr.txt").write_text(result.stderr, encoding="utf-8")
    if result.returncode or not elf.is_file():
        raise ValueError("firmware link failed; inspect retained compiler logs")
    sections = subprocess.run(
        [str(size), str(elf)], capture_output=True, text=True, check=True, timeout=15
    ).stdout
    (output / "size.txt").write_text(sections, encoding="utf-8")
    receipt = {
        "schema": "lapsim.stm32-bench-build.v1",
        "status": "linked_only",
        "build_id": build_id,
        **identity,
        "compiler_executable_sha256": sha256(compiler.read_bytes()).hexdigest(),
        "argv": command,
        "elf": str(elf),
        "elf_sha256": sha256(elf.read_bytes()).hexdigest(),
        "map_sha256": sha256(link_map.read_bytes()).hexdigest(),
        "section_sizes": sections,
        "limits": "Generic data-only emulation adapter; 8 KiB stack region reserved, not a proven whole-system stack bound. No target execution or timing is implied by this build.",
    }
    (output / "build.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(
            # Keep existing short-path/launcher spelling for path-sensitive tools.
            json.dumps(build(args.toolchain_dir.absolute(), args.output_dir), indent=2)
        )
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(2, str(error) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
