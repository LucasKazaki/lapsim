"""Create/check a project-local environment and optionally launch the desktop."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
RESERVED = {
    "src",
    "controller",
    "docs",
    "data",
    "scripts",
    "web",
    "packaging",
    "output",
    "outputs",
    "analysis",
    "tests",
    ".git",
    ".github",
    ".vscode",
    "firmware",
    "quality",
}


def environment_path(value: str) -> Path:
    lexical = Path(value)
    if not lexical.is_absolute():
        lexical = ROOT / lexical
    target = lexical.resolve()
    if target == ROOT or not target.is_relative_to(ROOT):
        raise ValueError(
            "The environment must be a separate directory inside this project"
        )
    if target.relative_to(ROOT).parts[0] in RESERVED:
        raise ValueError(
            "Choose .venv or a directory under work; source directories are protected"
        )
    for path in (lexical, *lexical.parents):
        if path == ROOT:
            break
        if path.is_symlink():
            raise ValueError("The environment path must not contain a symbolic link")
    return target


def command(
    argv: list[str], *, timeout: float | None, capture: bool = False
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        PYTHONUTF8="1",
        PIP_DISABLE_PIP_VERSION_CHECK="1",
        PIP_NO_INPUT="1",
    )
    return subprocess.run(
        [argv[0], "-X", "utf8", *argv[1:]],
        cwd=ROOT,
        env=env,
        timeout=timeout,
        check=True,
        capture_output=capture,
        text=True,
        encoding="utf-8",
    )


def inspect_environment(python: Path, target: Path) -> dict:
    result = command(
        [
            str(python),
            "-I",
            "-c",
            "import json,sys; print(json.dumps({'version':list(sys.version_info[:3]),'prefix':sys.prefix,'base':sys.base_prefix,'bits':64 if sys.maxsize>2**32 else 32}))",
        ],
        timeout=20,
        capture=True,
    )
    value = json.loads(result.stdout)
    if (
        value["version"][:2] < [3, 11]
        or value["bits"] != 64
        or Path(value["prefix"]).resolve() != target
        or value["prefix"] == value["base"]
    ):
        raise ValueError(
            "Existing environment is incompatible; preserve it and select a new project-local environment"
        )
    return value


def check(python: Path, *, desktop: bool) -> dict:
    owner = command(
        [str(python), "-I", "-B", "-c", "import lapsim; print(lapsim.__file__)"],
        timeout=20,
        capture=True,
    )
    if (
        Path(owner.stdout.strip()).resolve()
        != (ROOT / "src/lapsim/__init__.py").resolve()
    ):
        raise ValueError(
            "Environment imports another LapSim installation; rerun setup without --check"
        )
    result = command(
        [
            str(python),
            "-I",
            "-B",
            "-m",
            "lapsim.diagnostics",
            *(["--desktop"] if desktop else []),
        ],
        timeout=60,
        capture=True,
    )
    value = json.loads(result.stdout)
    if value.get("status") != "passed":
        raise ValueError("Actual runtime check did not pass")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Read-only environment and offline synthetic checks",
    )
    mode.add_argument(
        "--launch",
        action="store_true",
        help="Set up if needed, check and launch the desktop",
    )
    parser.add_argument("--environment", default=".venv")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Also install/check development test dependencies",
    )
    parser.add_argument(
        "--desktop", action="store_true", help="Also verify Tk/display in check mode"
    )
    parser.add_argument(
        "--desktop-self-test",
        type=Path,
        help="With --launch, run the executable-level UI/replay check and exit",
    )
    args = parser.parse_args()
    marker = None
    temporary = None
    try:
        if sys.version_info < (3, 11) or sys.maxsize <= 2**32:
            raise ValueError("Run this command with 64-bit Python 3.11 or newer")
        if args.desktop_self_test and not args.launch:
            raise ValueError("--desktop-self-test requires --launch")
        target = environment_path(args.environment)
        python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if target.exists() and (
            not python.is_file() or not (target / "pyvenv.cfg").is_file()
        ):
            raise ValueError(
                "Existing environment is incomplete; preserve it and choose another --environment"
            )
        if not target.exists():
            if args.check:
                raise ValueError(
                    "Environment is absent; rerun without --check to install it"
                )
            print("Creating the project environment…", flush=True)
            command([sys.executable, "-I", "-m", "venv", str(target)], timeout=90)
        probe = inspect_environment(python, target)
        marker = target / ".lapsim-ready.json"
        dependency_id = sha256((ROOT / "pyproject.toml").read_bytes()).hexdigest()
        expected = {
            "schema": 1,
            "dependency_sha256": dependency_id,
            "source_root": str(ROOT),
            "python": probe["version"],
            "dev": args.dev,
        }
        try:
            ready = (
                marker.is_file()
                and json.loads(marker.read_text(encoding="utf-8")) == expected
            )
        except (OSError, ValueError):
            ready = False
        if args.check and not ready:
            raise ValueError(
                "Environment setup marker is absent or stale; rerun without --check "
                "using the same --dev and --environment options to verify/install the declared dependencies"
            )
        if not args.check and not ready:
            print("Installing the declared source dependencies…", flush=True)
            try:
                command(
                    [str(python), "-I", "-m", "pip", "--version"],
                    timeout=20,
                    capture=True,
                )
            except subprocess.CalledProcessError:
                command([str(python), "-I", "-m", "ensurepip", "--upgrade"], timeout=90)
            command(
                [
                    str(python),
                    "-I",
                    "-m",
                    "pip",
                    "--isolated",
                    "install",
                    "--prefix",
                    str(target),
                    "--no-user",
                    "--disable-pip-version-check",
                    "--no-input",
                    "-e",
                    str(ROOT) + ("[dev]" if args.dev else ""),
                ],
                timeout=300,
            )
        if args.dev:
            command(
                [str(python), "-I", "-B", "-c", "import pytest,defusedxml"],
                timeout=20,
                capture=True,
            )
        result = check(python, desktop=args.desktop or args.launch)
        if args.check:
            print(json.dumps(result, indent=2))
            return 0
        temporary = marker.with_name(marker.name + "." + uuid4().hex + ".tmp")
        temporary.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
        temporary.replace(marker)
        print(
            "LapSim is ready. Bicycle and controller replay checks passed.", flush=True
        )
        if args.launch:
            command(
                [
                    str(python),
                    "-I",
                    "-m",
                    "lapsim.desktop",
                    *(
                        ["--self-test", str(args.desktop_self_test.resolve())]
                        if args.desktop_self_test
                        else []
                    ),
                ],
                timeout=300 if args.desktop_self_test else None,
            )
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        if not args.check:
            for owned in (temporary, marker):
                if owned is not None:
                    try:
                        owned.unlink(missing_ok=True)
                    except OSError as cleanup_error:
                        print(
                            "Could not invalidate the setup marker: "
                            + str(cleanup_error),
                            file=sys.stderr,
                        )
        print("LapSim setup stopped: " + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr[-4000:], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
