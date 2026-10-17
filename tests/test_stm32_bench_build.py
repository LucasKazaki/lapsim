"""The bench CLI retains the caller's compiler invocation path."""

import importlib.util
import json
from hashlib import sha256
from pathlib import Path
import subprocess
import sys


def test_cli_anchors_relative_toolchain_without_canonicalizing_invoked_spelling(
    tmp_path, monkeypatch, capsys
):
    script = Path(__file__).resolve().parents[1] / "scripts/build_stm32_bench.py"
    spec = importlib.util.spec_from_file_location("stm32_bench_build", script)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    caller = tmp_path / "caller directory"
    (caller / "caller-spelling").mkdir(parents=True)
    toolchain = Path("caller-spelling") / ".." / "GNU~1"
    invoked = caller / toolchain
    suffix = ".exe" if sys.platform == "win32" else ""
    compiler = invoked / "bin" / ("arm-none-eabi-gcc" + suffix)
    compiler.parent.mkdir(parents=True)
    compiler.write_bytes(b"nonexecuting compiler identity fixture")
    output = caller / "linked-output"
    commands = []

    def tool(command, **kwargs):
        commands.append(command)
        if command[-1] == "--version":
            stdout = "Arm GNU Toolchain 12.3.Rel1 12.3.1\n"
        elif "-o" in command:
            Path(command[command.index("-o") + 1]).write_bytes(b"ELF fixture")
            map_arg = next(arg for arg in command if arg.startswith("-Wl,-Map="))
            Path(map_arg.removeprefix("-Wl,-Map=")).write_bytes(b"map fixture")
            stdout = ""
        else:
            stdout = "text data bss\n1 0 0\n"
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.chdir(caller)
    monkeypatch.setattr(builder.subprocess, "run", tool)
    monkeypatch.setattr(
        sys, "argv",
        [str(script), "--toolchain-dir", str(toolchain), "--output-dir", str(output)],
    )
    assert builder.main() == 0
    receipt = json.loads((output / "build.json").read_text())
    # Compiler/version/size calls must use the selected lexical spelling even
    # though the compilation itself runs from the repository source directory.
    assert commands[0][0] == commands[1][0] == str(compiler)
    assert commands[2][0] == str(invoked / "bin" / ("arm-none-eabi-size" + suffix))
    assert receipt["argv"][0] == str(compiler)
    assert receipt["compiler_executable_sha256"] == sha256(compiler.read_bytes()).hexdigest()
    assert json.loads(capsys.readouterr().out) == receipt
