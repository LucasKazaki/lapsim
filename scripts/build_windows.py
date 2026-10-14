"""Build and integration-test a standalone Windows x64 team distribution."""
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


def run(*args: str, **kwargs) -> None:
    subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def stage_assets() -> Path:
    assets = ROOT / "build" / "assets"
    # Only a verified child of this checkout's build directory can be replaced.
    if assets.exists():
        if assets.resolve().parent != (ROOT / "build").resolve() or assets.is_symlink():
            raise RuntimeError("Refusing to replace an unexpected asset path")
        shutil.rmtree(assets)
    assets.mkdir(parents=True)
    paths = []
    for folder, patterns in (
        ("src", ("*.py",)), ("scripts", ("*.py", "*.ps1")),
        ("tests", ("*.py",)), ("docs", ("*.md", "*.html", "*.css", "*.js", "*.py", "*.cjs")),
        ("data", ("*.tir",)), ("analysis", ("README.md",)),
        ("output/pdf", ("*.pdf",)),
    ):
        for pattern in patterns:
            paths.extend((ROOT / folder).rglob(pattern))
    paths.extend(ROOT / name for name in (
        "README.md", "START-HERE.txt", "pyproject.toml", "requirements-build.lock", "build_lapsim.cmd",
        "setup_lapsim.cmd", "setup_lapsim.ps1", "launch_lapsim.cmd", "packaging/LapSim.spec",
        "analysis/data/track/gnss_imu_endurance_track.csv",
        "analysis/data/track/gnss_imu_endurance_track.json",
    ))
    if (ROOT / ".git").exists():
        tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
        paths.extend(ROOT / name for name in tracked if name and (ROOT / name).is_file())
        source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        source_dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=ROOT, text=True).strip())
    else:
        # A distributed source snapshot may be rebuilt without a Git checkout.
        previous = ROOT / "build-info.json"
        identity = json.loads(previous.read_text(encoding="utf-8")) if previous.is_file() else {}
        source_commit = identity.get("code_commit")
        source_dirty = True  # This snapshot has no live clean-worktree guarantee.
        for folder in ("src", "scripts", "tests", "docs", "data", "analysis", "output", "packaging", ".vscode"):
            paths.extend(path for path in (ROOT / folder).rglob("*") if path.is_file())
        paths.extend(path for path in ROOT.glob("LICENSE*") if path.is_file())
        paths.extend(ROOT / name for name in (".gitignore", ".gitattributes") if (ROOT / name).is_file())
    checksums = {}
    for source in sorted(set(paths)):
        if any(part in {"__pycache__", ".venv", "build", "work"} for part in source.relative_to(ROOT).parts):
            continue
        relative = source.relative_to(ROOT)
        destination = assets / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        checksums[relative.as_posix()] = sha256(source.read_bytes()).hexdigest()
    identity = {
        "code_commit": source_commit,
        "dirty_worktree": source_dirty,
        "source_sha256": sha256(json.dumps(checksums, sort_keys=True).encode()).hexdigest(),
        "files_sha256": checksums,
        "python": platform.python_version(), "architecture": platform.machine(),
        "dependencies": {name: version(name) for name in ("numpy", "scipy", "matplotlib", "openpyxl", "pyinstaller")},
        "artifact": "Windows x64 internal team demonstration; unsigned",
    }
    # Preserve the license texts shipped by the interpreter and bundled runtime
    # dependencies alongside the build's own source snapshot.
    notices = assets / "third-party"
    notices.mkdir()
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy2(python_license, notices / "Python-LICENSE.txt")
    from packaging.requirements import Requirement
    pending = ["numpy", "scipy", "matplotlib", "openpyxl"]
    seen = set()
    while pending:
        package = pending.pop()
        installed = distribution(package)
        normalized = installed.metadata["Name"].lower().replace("_", "-")
        if normalized in seen:
            continue
        seen.add(normalized)
        for dependency in installed.requires or ():
            requirement = Requirement(dependency)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
        for file in installed.files or ():
            if any("license" in part.lower() or "copying" in part.lower() or "notice" in part.lower() for part in file.parts):
                origin = Path(installed.locate_file(file))
                if origin.is_file():
                    destination = notices / normalized / Path(str(file))
                    # Wheel file paths containing parent traversal are not assets.
                    if ".." in file.parts:
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(origin, destination)
    (notices / "README.txt").write_text(
        "License and notice texts from the Python interpreter and installed runtime dependencies.\n"
        "The repository itself does not declare a redistribution license; this build is for internal team review.\n",
        encoding="utf-8",
    )
    for path in notices.rglob("*"):
        if path.is_file():
            checksums[path.relative_to(assets).as_posix()] = sha256(path.read_bytes()).hexdigest()
    identity["source_sha256"] = sha256(json.dumps(checksums, sort_keys=True).encode()).hexdigest()
    (assets / "build-info.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    return assets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--skip-tests", action="store_true", help="Build after separately running the full repository checks")
    args = parser.parse_args()
    if sys.platform != "win32" or sys.maxsize <= 2**32 or sysconfig.get_platform() != "win-amd64":
        parser.error("Build with an x64 (win-amd64) Python interpreter on Windows")
    for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[variable] = "1"
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if not args.skip_tests:
        run(sys.executable, str(ROOT / "scripts/check_all.py"))
    generator = ROOT / "docs/simulator_flowchart/generate_inventory.py"
    if generator.is_file():
        run(sys.executable, str(generator))
    assets = stage_assets()
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(output), str(ROOT / "packaging/LapSim.spec"))
    executable = output / "LapSim.exe"
    report_path = output / "portable-self-test.json"
    # Launch a copy outside the checkout, with no Python/Git on PATH and no
    # optional engineering evidence or existing user data.
    with TemporaryDirectory(prefix="LapSim team test ") as temporary:
        sandbox = Path(temporary)
        copied_exe = sandbox / "LapSim.exe"
        shutil.copy2(executable, copied_exe)
        environment = os.environ.copy()
        environment["PATH"] = str(Path(environment.get("SystemRoot", "C:/Windows")) / "System32")
        environment["LOCALAPPDATA"] = str(sandbox / "user-data")
        environment["LAPSIM_DATA_BUNDLE"] = str(sandbox / "no-external-evidence")
        environment.pop("PYTHONPATH", None)
        environment.pop("TCL_LIBRARY", None)
        environment.pop("TK_LIBRARY", None)
        result = subprocess.run([str(copied_exe), "--self-test", str(report_path)], cwd=sandbox, env=environment, timeout=180)
        if result.returncode or not report_path.is_file():
            raise RuntimeError(f"Portable self-test failed; inspect {report_path}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("status") != "passed" or not report.get("frozen"):
            raise RuntimeError(f"Portable self-test did not pass: {report_path}")
    checksums = {"LapSim.exe": sha256(executable.read_bytes()).hexdigest()}
    (output / "checksums.json").write_text(json.dumps(checksums, indent=2) + "\n", encoding="utf-8")
    archive = output / "LapSim-Windows-x64.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in (executable, report_path, output / "checksums.json"):
            bundle.write(path, path.name)
        for path in assets.rglob("*"):
            if path.is_file():
                bundle.write(path, path.relative_to(assets).as_posix())
        for path in (ROOT / "work").glob("*results.xml"):
            bundle.write(path, "verification/" + path.name)
        for filename in (
            "test-suite.log", "physics-operating-sweep.json", "documentation-qa.json",
            "gui-recovery.json", "gui-recovery.log", "gui-repeat-course.log",
            "gui-repeat-evidence.log", "gui-repeat-restart.log", "gui-capture-sys.log",
            "gui-capture-sys-lifecycle.log", "gui-shutdown.log",
        ):
            path = ROOT / "work" / filename
            if path.is_file():
                bundle.write(path, "verification/" + filename)
    print(f"Portable checks passed. Share {archive} or {executable}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
