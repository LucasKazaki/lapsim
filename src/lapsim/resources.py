"""Read-only assets and source identity in checkouts and portable builds."""

from __future__ import annotations

import json
import os
import shutil
import sys
import webbrowser
from hashlib import sha256
from pathlib import Path


def repository_root() -> Path:
    if getattr(sys, "frozen", False):
        extraction_root = getattr(sys, "_MEIPASS", None)
        if not isinstance(extraction_root, str):
            raise RuntimeError("Frozen build is missing its extraction directory")
        return Path(extraction_root) / "bundle"
    module = Path(__file__).resolve()
    installed = module.parent / "_resources"
    if (installed / "build-info.json").is_file():
        return installed
    checkout = module.parents[2]
    if (checkout / "pyproject.toml").is_file() and (
        checkout / "src/lapsim/resources.py"
    ).resolve() == module:
        return checkout
    raise RuntimeError(
        "LapSim package resources are missing; reinstall a complete wheel or use a source checkout"
    )


def build_identity() -> dict | None:
    """Packaged builds use captured identity, never ambient Git."""
    root = repository_root()
    if (
        getattr(sys, "frozen", False)
        or (Path(__file__).resolve().parent / "_resources/build-info.json").is_file()
    ):
        return json.loads((root / "build-info.json").read_text(encoding="utf-8"))
    if (root / ".git").exists():
        return None
    for name in (".lapsim-source-info.json", "build-info.json"):
        capture = root / name
        if capture.is_file():
            identity = json.loads(capture.read_text(encoding="utf-8"))
            if not isinstance(identity, dict):
                raise ValueError("Invalid captured source identity")
            saved = identity.get("files_sha256")
            if not isinstance(saved, dict):
                return dict(identity, dirty_worktree=True)
            actual = {}
            boundary = _io_path(root).resolve()
            for relative in saved:
                path = Path(relative)
                if path.is_absolute() or path.drive or ".." in path.parts:
                    raise ValueError("Invalid captured source path")
                source = _io_path(root / path)
                if source.is_symlink() or not source.resolve().is_relative_to(boundary):
                    raise ValueError("Captured source path is aliased")
                actual[relative] = (
                    sha256(source.read_bytes()).hexdigest()
                    if source.is_file()
                    else None
                )
            for source in _io_path(root / "src").rglob("*.py"):
                if source.is_symlink() or not source.resolve().is_relative_to(boundary):
                    raise ValueError("Python source path is aliased")
                actual[source.relative_to(_io_path(root)).as_posix()] = sha256(
                    source.read_bytes()
                ).hexdigest()
            if actual != saved:
                identity = dict(
                    identity,
                    dirty_worktree=True,
                    captured_source_sha256=identity.get("source_sha256"),
                    files_sha256=actual,
                    source_sha256=sha256(
                        json.dumps(
                            actual, sort_keys=True, separators=(",", ":")
                        ).encode()
                    ).hexdigest(),
                    source_hash_scope="current captured snapshot paths plus Python source; missing paths are null",
                )
            return identity
    return None


def _extended_windows_path(value: str) -> str:
    if value.startswith("\\\\?\\"):
        return value
    if value.startswith("\\\\"):
        return "\\\\?\\UNC\\" + value[2:]
    return "\\\\?\\" + value


def _io_path(path: Path) -> Path:
    return (
        Path(_extended_windows_path(str(path.absolute()))) if os.name == "nt" else path
    )


def documentation_root() -> Path:
    """Keep offline help alive after a one-file app removes its extraction dir."""
    source = repository_root()
    if not getattr(sys, "frozen", False):
        return source
    identity = build_identity()
    if identity is None:
        raise RuntimeError("Frozen build is missing its captured identity")
    version = identity["source_sha256"]
    if (
        not isinstance(version, str)
        or len(version) != 64
        or any(c not in "0123456789abcdef" for c in version)
    ):
        raise ValueError("Invalid documentation source identity")
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".lapsim")
    target = base / "LapSim" / "documentation" / version
    destination = _io_path(target)
    marker = destination / ".complete"
    if not marker.is_file():
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copytree(_io_path(source), destination, dirs_exist_ok=True)
        marker.write_text(version, encoding="ascii")
    return target


def open_simulator_map() -> bool:
    path = documentation_root() / "docs" / "simulator_flowchart" / "index.html"
    if not path.is_file():
        raise FileNotFoundError(f"Simulator map is missing: {path}")
    value = str(path)
    if os.name == "nt" and value.startswith("\\\\?\\UNC\\"):
        path = Path("\\\\" + value[8:])
    elif os.name == "nt" and value.startswith("\\\\?\\"):
        path = Path(value[4:])
    return webbrowser.open(path.as_uri())
