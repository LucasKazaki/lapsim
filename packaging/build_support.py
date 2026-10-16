"""Declared runtime resources, verified controller and captured wheel identity."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from setuptools.command.build import build
from setuptools.command.build_py import build_py
from setuptools.command.install import install
from setuptools.command.sdist import sdist

ROOT = Path(__file__).resolve().parents[1]
SOURCE_INFO = ".lapsim-source-info.json"


def io_path(path: Path) -> Path:
    if os.name != "nt":
        return path
    value = str(path.absolute())
    if value.startswith("\\\\?\\"):
        return Path(value)
    return Path(
        "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
    )


ROOT = io_path(ROOT)


def local_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resource_files() -> list[Path]:
    # The existing independent import verifier pins all original blobs and
    # relocation patches, and rejects extra controller files before packaging.
    local_module(
        "lapsim_wheel_import_verifier", "scripts/check_controller_import.py"
    ).verify(ROOT)
    paths: set[Path] = set()
    for folder, patterns in (
        ("src", ("*.py",)),
        ("scripts", ("*.py", "*.ps1", "*.mjs")),
        ("tests", ("*.py",)),
        ("docs", ("*.md", "*.html", "*.css", "*.js", "*.py", "*.cjs", "*.svg")),
        ("quality", ("*.py", "*.md")),
        ("firmware", ("*.c", "*.h", "*.ld", "*.md")),
        ("packaging", ("*.py", "*.spec")),
        ("analysis", ("*.md", "*.py")),
        (".github/workflows", ("*.yml", "*.yaml")),
    ):
        for pattern in patterns:
            paths.update((ROOT / folder).rglob(pattern))
    paths.update(path for path in (ROOT / "controller").rglob("*") if path.is_file())
    for name in (
        "README.md",
        "START-HERE.txt",
        "AGENTS.md",
        "ENME408_IMPLEMENTATION_PLAN.md",
        "pyproject.toml",
        "setup.py",
        "requirements-build.lock",
        "build_lapsim.cmd",
        "setup_lapsim.cmd",
        "setup_lapsim.ps1",
        "launch_lapsim.cmd",
        "analysis/data/track/gnss_imu_endurance_track.csv",
        "analysis/data/track/gnss_imu_endurance_track.json",
        "tests/fixtures/legacy_browser_grid_v2.json",
        "tests/fixtures/closed-loop-v1-accepted-launch.json",
        "data/tires/hoosier_16x7p5-10_r20_upc.tir",
        "output/pdf/LapSim_Engineering_Handoff.pdf",
        "docs/evidence/e15-calculix-refinement.json",
        "docs/evidence/e15-calculix-process-outcomes.json",
    ):
        paths.add(ROOT / name)
    paths.update(ROOT.glob("LICENSE*"))
    web = local_module("lapsim_wheel_web_inventory", "scripts/build_windows.py")
    for name in web.WEB_SOURCE_FILES:
        paths.add(ROOT / "web" / name)
    for name, digest in web.REVIEWED_WEB_REPLAYS.items():
        path = ROOT / "web/examples" / name
        if (
            not path.is_file()
            or path.stat().st_size > 20_000_000
            or sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != digest
        ):
            raise ValueError("unreviewed or missing wheel replay: " + name)
        paths.add(path)
    selected = []
    for path in sorted(paths):
        relative = path.relative_to(ROOT)
        if any(
            part in {"__pycache__", ".venv", "build", "work", "output", "tuning_output"}
            for part in relative.parts
        ) and relative.parts[:2] != ("output", "pdf"):
            continue
        if (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_nlink != 1
            or path.resolve() != ROOT.resolve() / relative
        ):
            raise ValueError(
                "missing or aliased wheel resource: " + relative.as_posix()
            )
        selected.append(path)
    return selected


def identity(hashes: dict[str, str]) -> dict:
    commit = None
    dirty = True
    if (ROOT / ".git").exists():
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=normal"],
                cwd=ROOT,
                text=True,
            ).strip()
        )
    else:
        previous = ROOT / SOURCE_INFO
        if previous.is_file():
            saved = json.loads(previous.read_text(encoding="utf-8"))
            commit = saved.get("code_commit")
            dirty = (
                saved.get("dirty_worktree") is not False
                or saved.get("files_sha256") != hashes
            )
        elif (ROOT / "build-info.json").is_file():
            commit = json.loads(
                (ROOT / "build-info.json").read_text(encoding="utf-8")
            ).get("code_commit")
    return {
        "build_kind": "installed_python_resource_bundle",
        "code_commit": commit,
        "dirty_worktree": dirty,
        "source_sha256": sha256(
            json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "source_hash_scope": "declared resource paths and exact file-byte SHA256 values; excludes build-info.json",
        "files_sha256": hashes,
        "publication": "Internal build; public release deferred pending owner decision",
    }


def source_identity() -> dict:
    return identity(
        {
            path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest()
            for path in resource_files()
        }
    )


class ExtendedBuild(build):
    def finalize_options(self):
        super().finalize_options()
        for name in (
            "build_base",
            "build_lib",
            "build_purelib",
            "build_platlib",
            "build_temp",
            "build_scripts",
        ):
            value = getattr(self, name, None)
            if value:
                setattr(self, name, str(io_path(Path(value))))


class BundledBuildPy(build_py):
    def get_source_files(self):
        return sorted(
            set(super().get_source_files())
            | {path.relative_to(ROOT).as_posix() for path in resource_files()}
        )

    def run(self):
        if getattr(self, "editable_mode", False):
            super().run()
            return
        sources = resource_files()
        super().run()
        target = Path(self.build_lib).resolve() / "lapsim/_resources"
        boundary = Path(self.build_lib).resolve()
        if not target.resolve().is_relative_to(boundary) or target.is_symlink():
            raise ValueError("unexpected wheel resource destination")
        if target.exists():
            marker = target / "build-info.json"
            if (
                not marker.is_file()
                or json.loads(marker.read_text()).get("build_kind")
                != "installed_python_resource_bundle"
            ):
                raise ValueError(
                    "choose a clean build directory; unknown resource output exists"
                )
        target.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(
            prefix="resource-stage-", dir=io_path(target.parent)
        ) as temporary:
            stage = Path(temporary) / "bundle"
            stage.mkdir()
            hashes = {}
            for source in sources:
                relative = source.relative_to(ROOT)
                raw = source.read_bytes()
                destination = stage / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
                hashes[relative.as_posix()] = sha256(raw).hexdigest()
            (stage / "build-info.json").write_text(
                json.dumps(identity(hashes), indent=2) + "\n", encoding="utf-8"
            )
            if target.exists():
                # Only the verified child of this wheel's build directory is replaced.
                shutil.rmtree(target)
            stage.replace(target)


class NormalizedInstall(install):
    def finalize_options(self):
        super().finalize_options()
        for name in (
            "install_lib",
            "install_purelib",
            "install_platlib",
            "install_headers",
            "install_scripts",
            "install_data",
            "install_base",
            "install_platbase",
        ):
            value = getattr(self, name, None)
            if value:
                setattr(self, name, os.path.normpath(value))


class VerifiedSdist(sdist):
    def make_release_tree(self, base_dir, files):
        captured = source_identity()
        selected = {path.relative_to(ROOT).as_posix() for path in resource_files()}
        metadata = {name for name in files if ".egg-info/" in name.replace("\\", "/")}
        super().make_release_tree(
            str(io_path(Path(base_dir))),
            [os.path.normpath(name) for name in sorted(selected | metadata)],
        )
        (io_path(Path(base_dir)) / SOURCE_INFO).write_text(
            json.dumps(captured, indent=2) + "\n", encoding="utf-8"
        )
