"""Build and integration-test a public Windows x64 demonstration."""

from __future__ import annotations

import argparse
from hashlib import sha256
from importlib.metadata import distribution, version
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import sysconfig
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]

PUBLIC_DOCUMENTATION_FILES = (
    "docs/architecture.md",
    "docs/extending_models.md",
    "docs/licensing.md",
    "docs/public_demo.md",
    "docs/release.md",
)
PUBLIC_SCRIPT_FILES = (
    "scripts/build_windows.py",
    "scripts/check_dco.py",
    "scripts/check_license_policy.py",
    "scripts/portable_entry.py",
)
PUBLIC_ROOT_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "LOCAL-WORKER.md",
    "START-HERE.txt",
    "packaging/LapSim.spec",
    "pyproject.toml",
    "requirements-build.lock",
)
REQUIRED_LEGAL_FILES = (
    "LICENSE",
    "LICENSE_SCOPE.md",
    "NOTICE",
    "CONTRIBUTING.md",
    "docs/licensing.md",
)
PUBLIC_DISTRIBUTION_EXCLUSIONS = frozenset({
    "analysis/data/track/gnss_imu_endurance_track.csv",
    "analysis/data/track/gnss_imu_endurance_track.json",
    "data/tires/hoosier_16x7p5-10_r20_upc.tir",
    "docs/simulator_flowchart/QA.md",
})
PUBLIC_DISTRIBUTION_EXCLUDED_PREFIXES = (
    "analysis/",
    "data/",
    "docs/evidence/",
    "logs/",
    "output/",
    "outputs/",
    "tests/",
    "work/",
)


def run(*args: str, **kwargs) -> None:
    subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def _is_publicly_excluded(relative: Path) -> bool:
    posix = relative.as_posix()
    return (
        posix in PUBLIC_DISTRIBUTION_EXCLUSIONS
        or any(
            posix.startswith(prefix)
            for prefix in PUBLIC_DISTRIBUTION_EXCLUDED_PREFIXES
        )
    )


def _existing_paths(relative_names: tuple[str, ...]) -> list[Path]:
    paths = [ROOT / name for name in relative_names]
    missing = [
        path.relative_to(ROOT).as_posix()
        for path in paths
        if not path.is_file()
    ]
    if missing:
        raise RuntimeError(
            "Required public release file is missing: " + ", ".join(missing)
        )
    return paths


def stage_assets() -> Path:
    """Stage a reviewed synthetic-data-only source snapshot."""

    assets = ROOT / "build" / "assets"
    if assets.exists():
        if (
            assets.resolve().parent != (ROOT / "build").resolve()
            or assets.is_symlink()
        ):
            raise RuntimeError("Refusing to replace an unexpected asset path")
        shutil.rmtree(assets)
    assets.mkdir(parents=True)

    missing_legal_files = [
        name for name in REQUIRED_LEGAL_FILES if not (ROOT / name).is_file()
    ]
    if missing_legal_files:
        raise RuntimeError(
            "Refusing to build a distributable archive without legal notices: "
            + ", ".join(missing_legal_files)
        )

    paths: list[Path] = []
    paths.extend(path for path in (ROOT / "src").rglob("*.py"))
    paths.extend(_existing_paths(PUBLIC_DOCUMENTATION_FILES))
    paths.extend(_existing_paths(PUBLIC_SCRIPT_FILES))
    paths.extend(_existing_paths(PUBLIC_ROOT_FILES))
    paths.extend(_existing_paths(REQUIRED_LEGAL_FILES))

    flowchart_root = ROOT / "docs" / "simulator_flowchart"
    if not flowchart_root.is_dir():
        raise RuntimeError("Public simulator-flowchart directory is missing")
    paths.extend(
        path
        for path in flowchart_root.rglob("*")
        if path.is_file()
        and not _is_publicly_excluded(path.relative_to(ROOT))
    )

    if (ROOT / ".git").exists():
        source_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip()
        source_dirty = bool(
            subprocess.check_output(
                [
                    "git",
                    "status",
                    "--porcelain",
                    "--untracked-files=normal",
                ],
                cwd=ROOT,
                text=True,
            ).strip()
        )
    else:
        previous = ROOT / "build-info.json"
        prior_identity = (
            json.loads(previous.read_text(encoding="utf-8"))
            if previous.is_file()
            else {}
        )
        source_commit = prior_identity.get("code_commit")
        source_dirty = True

    checksums: dict[str, str] = {}
    for source in sorted(set(paths)):
        relative = source.relative_to(ROOT)
        if any(
            part in {"__pycache__", ".venv", "build"}
            for part in relative.parts
        ):
            continue
        if _is_publicly_excluded(relative):
            raise RuntimeError(
                "Public release allowlist contains excluded material: "
                f"{relative.as_posix()}"
            )
        destination = assets / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        checksums[relative.as_posix()] = sha256(source.read_bytes()).hexdigest()

    missing_staged_legal_files = [
        name for name in REQUIRED_LEGAL_FILES if not (assets / name).is_file()
    ]
    if missing_staged_legal_files:
        raise RuntimeError(
            "Refusing to build a distributable archive because legal notices "
            "were not staged: " + ", ".join(missing_staged_legal_files)
        )

    leaked_excluded_files = [
        path
        for path in assets.rglob("*")
        if path.is_file()
        and _is_publicly_excluded(path.relative_to(assets))
    ]
    if leaked_excluded_files:
        raise RuntimeError(
            "Refusing to build a public archive containing excluded material: "
            + ", ".join(
                path.relative_to(assets).as_posix()
                for path in leaked_excluded_files
            )
        )

    identity = {
        "code_commit": source_commit,
        "dirty_worktree": source_dirty,
        "source_sha256": sha256(
            json.dumps(checksums, sort_keys=True).encode()
        ).hexdigest(),
        "files_sha256": checksums,
        "python": platform.python_version(),
        "architecture": platform.machine(),
        "dependencies": {
            name: version(name)
            for name in (
                "numpy",
                "scipy",
                "matplotlib",
                "openpyxl",
                "pyinstaller",
            )
        },
        "artifact": (
            "Windows x64 public synthetic-data-only demonstration; unsigned"
        ),
    }

    notices = assets / "third-party"
    notices.mkdir()
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy2(python_license, notices / "Python-LICENSE.txt")

    from packaging.requirements import Requirement

    pending = ["numpy", "scipy", "matplotlib", "openpyxl"]
    seen: set[str] = set()
    while pending:
        package = pending.pop()
        installed = distribution(package)
        normalized = installed.metadata["Name"].lower().replace("_", "-")
        if normalized in seen:
            continue
        seen.add(normalized)
        for dependency in installed.requires or ():
            requirement = Requirement(dependency)
            if (
                requirement.marker is None
                or requirement.marker.evaluate({"extra": ""})
            ):
                pending.append(requirement.name)
        for file in installed.files or ():
            if any(
                "license" in part.lower()
                or "copying" in part.lower()
                or "notice" in part.lower()
                for part in file.parts
            ):
                if ".." in file.parts:
                    continue
                origin = Path(installed.locate_file(file))
                if origin.is_file():
                    destination = notices / normalized / Path(str(file))
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(origin, destination)

    (notices / "README.txt").write_text(
        "License and notice texts from the Python interpreter and installed "
        "runtime dependencies.\n"
        "Project permissions are controlled separately by LICENSE, "
        "LICENSE_SCOPE.md, and NOTICE.\n"
        "Third-party notices do not expand or replace the project's "
        "source-available terms.\n",
        encoding="utf-8",
    )
    for path in notices.rglob("*"):
        if path.is_file():
            checksums[path.relative_to(assets).as_posix()] = sha256(
                path.read_bytes()
            ).hexdigest()
    identity["source_sha256"] = sha256(
        json.dumps(checksums, sort_keys=True).encode()
    ).hexdigest()
    (assets / "build-info.json").write_text(
        json.dumps(identity, indent=2) + "\n",
        encoding="utf-8",
    )
    return assets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "dist",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Build after separately running the full repository checks",
    )
    args = parser.parse_args()
    if (
        sys.platform != "win32"
        or sys.maxsize <= 2**32
        or sysconfig.get_platform() != "win-amd64"
    ):
        parser.error(
            "Build with an x64 (win-amd64) Python interpreter on Windows"
        )

    for variable in (
        "OPENBLAS_NUM_THREADS",
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
    ):
        os.environ[variable] = "1"
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    run(sys.executable, str(ROOT / "scripts/check_license_policy.py"))
    if not args.skip_tests:
        run(sys.executable, str(ROOT / "scripts/check_all.py"))
    generator = ROOT / "docs/simulator_flowchart/generate_inventory.py"
    if generator.is_file():
        run(sys.executable, str(generator))

    assets = stage_assets()
    run(
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--distpath",
        str(output),
        str(ROOT / "packaging/LapSim.spec"),
    )
    executable = output / "LapSim.exe"
    report_path = output / "portable-self-test.json"

    with TemporaryDirectory(prefix="LapSim public test ") as temporary:
        sandbox = Path(temporary)
        copied_exe = sandbox / "LapSim.exe"
        sandbox_report = sandbox / "portable-self-test.json"
        shutil.copy2(executable, copied_exe)
        environment = os.environ.copy()
        environment["PATH"] = str(
            Path(environment.get("SystemRoot", "C:/Windows")) / "System32"
        )
        environment["LOCALAPPDATA"] = str(sandbox / "user-data")
        environment["LAPSIM_DATA_BUNDLE"] = str(
            sandbox / "no-external-evidence"
        )
        environment.pop("PYTHONPATH", None)
        environment.pop("TCL_LIBRARY", None)
        environment.pop("TK_LIBRARY", None)
        result = subprocess.run(
            [str(copied_exe), "--self-test", str(sandbox_report)],
            cwd=sandbox,
            env=environment,
            timeout=180,
            shell=False,
        )
        if sandbox_report.is_file():
            shutil.copy2(sandbox_report, report_path)
        if result.returncode or not sandbox_report.is_file():
            raise RuntimeError(
                f"Portable self-test failed; inspect {report_path}"
            )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if (
            report.get("status") != "passed"
            or not report.get("frozen")
            or not report.get("course_synthetic")
        ):
            raise RuntimeError(
                "Portable self-test did not pass the frozen "
                "synthetic-data-only release gate: "
                f"{report_path}"
            )

    checksums = {"LapSim.exe": sha256(executable.read_bytes()).hexdigest()}
    (output / "checksums.json").write_text(
        json.dumps(checksums, indent=2) + "\n",
        encoding="utf-8",
    )
    archive = output / "LapSim-Windows-x64.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in (executable, report_path, output / "checksums.json"):
            bundle.write(path, path.name)
        for path in assets.rglob("*"):
            if path.is_file():
                bundle.write(path, path.relative_to(assets).as_posix())

    print(f"Portable checks passed. Share {archive} or {executable}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
