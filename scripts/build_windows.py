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
from subprocess import CalledProcessError
import sys
import sysconfig
from tempfile import TemporaryDirectory, gettempdir, mkdtemp
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
WEB_SOURCE_FILES = (
    "index.html", "app.js", "styles.css", "worker.js", "bridge.py",
    "bench.html", "bench.css", "bench.js", "bench-data.js",
    "basic.html", "basic.css", "basic.js",
    "control.html", "control.css", "control.js",
)
# Independently pinned like the site staging script; a mutable recipient
# manifest cannot authorize new replay data in a source package.
REVIEWED_WEB_REPLAYS = {
    "enme408-synthetic-replay.json": "3c77722726b4ef7e43e172df4adee75d312ed89a8c5a648b79f314d485996bec",
    "enme408-native-c-replay.json": "dbb91a06097a4cdd38c4c72db7ca1e15f85e1866d02efc77de5bac5f281046b8",
}
VERIFICATION_SOURCE_SCOPE = (
    "When run, full repository tests precede inventory generation; "
    "packaged snapshot identity is separate."
)


def run(*args: str, **kwargs) -> None:
    subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def stage_assets(*, verification_dir: Path | None = None) -> Path:
    """Stage sources; main may supply only its freshly allocated evidence leaf."""
    verification_relative: Path | None = None
    if verification_dir is not None:
        owned = verification_dir.absolute()
        resolved = owned.resolve(strict=True)
        root = ROOT.resolve()
        if owned != resolved or not resolved.is_dir() or resolved == root:
            raise ValueError("Refusing to exclude an unexpected verification directory")
        if resolved.is_relative_to(root):
            verification_relative = resolved.relative_to(root)
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
        "README.md", "START-HERE.txt", "AGENTS.md", "ENME408_IMPLEMENTATION_PLAN.md",
        "pyproject.toml", "setup.py", "requirements-build.lock", "build_lapsim.cmd",
        "setup_lapsim.cmd", "setup_lapsim.ps1", "launch_lapsim.cmd", "packaging/LapSim.spec",
        "analysis/data/track/gnss_imu_endurance_track.csv",
        "analysis/data/track/gnss_imu_endurance_track.json",
    ))
    if (ROOT / ".git").exists():
        tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
        paths.extend(ROOT / name for name in tracked if name and (ROOT / name).is_file())
        source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        status_command = ["git", "status", "--porcelain", "--untracked-files=all"]
        if verification_relative is not None:
            status_command.extend(
                [
                    "--",
                    ":(top,literal,exclude)" + verification_relative.as_posix(),
                ]
            )
        status_environment = os.environ.copy()
        for variable in (
            "GIT_LITERAL_PATHSPECS",
            "GIT_GLOB_PATHSPECS",
            "GIT_NOGLOB_PATHSPECS",
            "GIT_ICASE_PATHSPECS",
        ):
            status_environment.pop(variable, None)
        source_dirty = bool(
            subprocess.check_output(
                status_command,
                cwd=ROOT,
                text=True,
                env=status_environment,
            ).strip()
        )
    else:
        # A distributed source snapshot may be rebuilt without a Git checkout.
        previous = ROOT / "build-info.json"
        identity = json.loads(previous.read_text(encoding="utf-8")) if previous.is_file() else {}
        source_commit = identity.get("code_commit")
        source_dirty = True  # This snapshot has no live clean-worktree guarantee.
        for folder in ("src", "controller", "firmware", "web", "scripts", "tests", "docs", "data", "analysis", "output", "packaging", ".vscode"):
            paths.extend(path for path in (ROOT / folder).rglob("*") if path.is_file())
        paths.extend(path for path in ROOT.glob("LICENSE*") if path.is_file())
        paths.extend(ROOT / name for name in (".gitignore", ".gitattributes") if (ROOT / name).is_file())
    checksums = {}
    allowed_web = {"web/" + name for name in WEB_SOURCE_FILES}
    allowed_web.update("web/examples/" + name for name in REVIEWED_WEB_REPLAYS)
    for name in allowed_web:
        source = ROOT / name
        if not source.is_file():
            raise ValueError("missing required browser source: " + name)
        if source.is_symlink() or source.resolve() != ROOT.resolve() / name or source.stat().st_nlink != 1:
            raise ValueError("refusing aliased browser source")
    for name, expected in REVIEWED_WEB_REPLAYS.items():
        source = ROOT / "web/examples" / name
        if (source.stat().st_size > 20_000_000
                or sha256(source.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != expected):
            raise ValueError("unreviewed source-package replay: " + name)
    for source in sorted(set(paths)):
        if any(part in {"__pycache__", ".venv", "build", "work"} for part in source.relative_to(ROOT).parts):
            continue
        relative = source.relative_to(ROOT)
        if relative.parts[0] == "web":
            if relative.as_posix() not in allowed_web:
                continue
            if source.is_symlink() or source.resolve() != ROOT.resolve() / relative or source.stat().st_nlink != 1:
                raise ValueError("refusing aliased browser source")
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
    evidence = Path(mkdtemp(prefix="verification-", dir=output))
    print(f"Build verification evidence: {evidence}", flush=True)
    suite_report = evidence / "test-results.xml"
    suite_command = (
        None
        if args.skip_tests
        else [
            sys.executable,
            str(ROOT / "scripts/check_all.py"),
            "--output-dir",
            str(evidence),
        ]
    )

    def save_local_suite(
        status: str,
        *,
        exit_code: int | None = None,
        error: str | None = None,
    ) -> None:
        local = {
            "status": status,
            "command": suite_command,
            "exit_code": exit_code,
            "report_path": str(suite_report) if suite_command is not None else None,
            "report_sha256": sha256(suite_report.read_bytes()).hexdigest()
            if suite_report.is_file()
            else None,
            "error": error,
            "source_scope": VERIFICATION_SOURCE_SCOPE,
            "scope": "Local literal invocation evidence; excluded from distributed ZIP.",
        }
        (evidence / "full-suite-invocation.json").write_text(
            json.dumps(local, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )

    save_local_suite("skipped" if args.skip_tests else "running")
    if suite_command is not None:
        try:
            run(*suite_command)
        except CalledProcessError as error:
            save_local_suite("failed", exit_code=error.returncode, error=str(error))
            raise
        except OSError as error:
            save_local_suite("failed", error=str(error))
            raise
        if not suite_report.is_file():
            message = (
                "Full-suite report was not produced in build verification directory"
            )
            save_local_suite("missing-report", exit_code=0, error=message)
            raise RuntimeError(message + ": " + str(evidence))
        save_local_suite("passed", exit_code=0)
    generator = ROOT / "docs/simulator_flowchart/generate_inventory.py"
    if generator.is_file():
        run(sys.executable, str(generator))
    assets = stage_assets(verification_dir=evidence)
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(output), str(ROOT / "packaging/LapSim.spec"))
    executable = output / "LapSim.exe"
    report_path = output / "portable-self-test.json"
    # Launch a copy outside the checkout, with no Python/Git on PATH and no
    # optional engineering evidence or existing user data.
    # Keep the owned directory's cleanup on the same extended-path route as
    # the frozen help copy; ordinary Win32 cleanup cannot unlink long names.
    temporary_parent = gettempdir()
    if os.name == "nt" and not temporary_parent.startswith("\\\\?\\"):
        temporary_parent = ("\\\\?\\UNC\\" + temporary_parent[2:]
                            if temporary_parent.startswith("\\\\") else "\\\\?\\" + temporary_parent)
    with TemporaryDirectory(prefix="LapSim team test ", dir=temporary_parent) as temporary:
        sandbox = Path(temporary)
        copied_exe = sandbox / "LapSim.exe"
        sandbox_report = sandbox / "portable-self-test.json"
        shutil.copy2(executable, copied_exe)
        environment = os.environ.copy()
        environment["PATH"] = str(Path(environment.get("SystemRoot", "C:/Windows")) / "System32")
        environment["LOCALAPPDATA"] = str(sandbox / "user-data")
        environment["LAPSIM_DATA_BUNDLE"] = str(sandbox / "no-external-evidence")
        environment.pop("PYTHONPATH", None)
        environment.pop("TCL_LIBRARY", None)
        environment.pop("TK_LIBRARY", None)
        result = subprocess.run(
            [str(copied_exe), "--self-test", str(sandbox_report)],
            cwd=sandbox, env=environment, timeout=180, shell=False,
        )
        if sandbox_report.is_file():
            shutil.copy2(sandbox_report, report_path)
        if result.returncode or not sandbox_report.is_file():
            raise RuntimeError(f"Portable self-test failed; inspect {report_path}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("status") != "passed" or not report.get("frozen"):
            raise RuntimeError(f"Portable self-test did not pass: {report_path}")
    checksums = {"LapSim.exe": sha256(executable.read_bytes()).hexdigest()}
    (output / "checksums.json").write_text(json.dumps(checksums, indent=2) + "\n", encoding="utf-8")
    suite: dict[str, object] = {"status": "skipped", "command": None, "report": None}
    if not args.skip_tests:
        suite = {
            "status": "passed",
            "command": [
                "python",
                "scripts/check_all.py",
                "--output-dir",
                "<build-owned-report-directory>",
            ],
            "command_scope": (
                "Sanitized logical command; actual argv is retained only in local build evidence."
            ),
            "report": {
                "path": "verification/test-results.xml",
                "sha256": sha256(suite_report.read_bytes()).hexdigest(),
            },
        }
    identity = json.loads((assets / "build-info.json").read_text(encoding="utf-8"))
    verification = evidence / "build-verification.json"
    verification.write_text(
        json.dumps(
            {
                "schema": "lapsim.build-verification.v1",
                "full_suite": suite,
                "source_scope": VERIFICATION_SOURCE_SCOPE,
                "packaged_source": {
                    name: identity[name]
                    for name in ("code_commit", "dirty_worktree", "source_sha256")
                },
            },
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    archive = output / "LapSim-Windows-x64.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in (executable, report_path, output / "checksums.json"):
            bundle.write(path, path.name)
        for path in assets.rglob("*"):
            if path.is_file():
                bundle.write(path, path.relative_to(assets).as_posix())
        bundle.write(verification, "verification/build-verification.json")
        if not args.skip_tests:
            bundle.write(suite_report, "verification/test-results.xml")
    print(f"Portable checks passed. Share {archive} or {executable}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
