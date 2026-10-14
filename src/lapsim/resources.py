"""Read-only assets and source identity in checkouts and portable builds."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import webbrowser


def repository_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "bundle"
    return Path(__file__).resolve().parents[2]


def build_identity() -> dict | None:
    """Frozen builds use captured identity, never a teammate's ambient Git repo."""
    if not getattr(sys, "frozen", False):
        return None
    return json.loads((repository_root() / "build-info.json").read_text(encoding="utf-8"))


def documentation_root() -> Path:
    """Keep offline help alive after a one-file app removes its extraction dir."""
    source = repository_root()
    if not getattr(sys, "frozen", False):
        return source
    identity = build_identity()
    version = identity["source_sha256"]
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".lapsim")
    target = base / "LapSim" / "documentation" / version
    marker = target / ".complete"
    if not marker.is_file():
        target.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, dirs_exist_ok=True)
        marker.write_text(version, encoding="ascii")
    return target


def open_simulator_map() -> bool:
    path = documentation_root() / "docs" / "simulator_flowchart" / "index.html"
    if not path.is_file():
        raise FileNotFoundError(f"Simulator map is missing: {path}")
    return webbrowser.open(path.as_uri())
