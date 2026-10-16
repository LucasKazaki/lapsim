"""Startup cannot overwrite existing environments or claim failed setup is ready."""

import importlib.util
import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest


@pytest.fixture
def bootstrap(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "tested_bootstrap", root / "scripts/bootstrap.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
    return module


@pytest.mark.parametrize(
    "name", [".", "../elsewhere", "src/env", "controller/env", "data/env", ".git/env"]
)
def test_environment_cannot_replace_sources_or_leave_project(bootstrap, name):
    with pytest.raises(ValueError):
        bootstrap.environment_path(name)


def test_space_unicode_environment_is_resolved_from_script_root(bootstrap):
    assert (
        bootstrap.environment_path("work/env space λ")
        == bootstrap.ROOT / "work/env space λ"
    )


def test_check_does_not_create_an_absent_environment(bootstrap, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["bootstrap", "--check"])
    assert bootstrap.main() == 2
    assert not (bootstrap.ROOT / ".venv").exists()


def test_existing_incomplete_environment_and_its_files_are_preserved(
    bootstrap, monkeypatch
):
    target = bootstrap.ROOT / ".venv"
    target.mkdir()
    (target / "keep.txt").write_text("keep this")
    monkeypatch.setattr(sys, "argv", ["bootstrap"])
    assert bootstrap.main() == 2
    assert (target / "keep.txt").read_text() == "keep this"
    assert not (target / ".lapsim-ready.json").exists()


def test_interrupted_install_returns_failure_without_ready_marker(
    bootstrap, monkeypatch
):
    target = bootstrap.ROOT / ".venv"
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.write_text("not executed")
    (target / "pyvenv.cfg").write_text("test environment")
    (target / "keep.txt").write_text("keep this")
    monkeypatch.setattr(sys, "argv", ["bootstrap"])
    monkeypatch.setattr(
        bootstrap, "inspect_environment", lambda *args: {"version": [3, 13, 15]}
    )

    def fail_install(argv, **kwargs):
        if "install" in argv:
            raise subprocess.CalledProcessError(
                1, argv, stderr="simulated installation interruption"
            )
        return subprocess.CompletedProcess(argv, 0, stdout="pip ready")

    monkeypatch.setattr(bootstrap, "command", fail_install)
    assert bootstrap.main() == 2
    assert not (target / ".lapsim-ready.json").exists()
    assert (target / "keep.txt").read_text() == "keep this"


def test_failed_actual_launch_invalidates_ready_marker_without_deleting_environment(
    bootstrap, monkeypatch
):
    target = bootstrap.ROOT / ".venv"
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.write_text("not executed")
    (target / "pyvenv.cfg").write_text("test")
    (target / "keep.txt").write_text("retained")
    monkeypatch.setattr(sys, "argv", ["bootstrap", "--launch"])
    monkeypatch.setattr(
        bootstrap, "inspect_environment", lambda *args: {"version": [3, 13, 15]}
    )
    monkeypatch.setattr(
        bootstrap, "check", lambda *args, **kwargs: {"status": "passed"}
    )

    def fail_launch(argv, **kwargs):
        if "lapsim.desktop" in argv:
            raise subprocess.CalledProcessError(
                1, argv, stderr="simulated launch failure"
            )
        return subprocess.CompletedProcess(argv, 0, stdout="ok")

    monkeypatch.setattr(bootstrap, "command", fail_launch)
    assert bootstrap.main() == 2
    assert not (target / ".lapsim-ready.json").exists()
    assert (target / "keep.txt").read_text() == "retained"


@pytest.mark.parametrize(
    "fault", ["absent", "corrupt", "dependency", "source", "python", "dev"]
)
def test_readonly_check_rejects_stale_marker_without_touching_environment(
    bootstrap, monkeypatch, fault
):
    target = bootstrap.ROOT / ".venv"
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.write_text("not executed", encoding="utf-8")
    (target / "pyvenv.cfg").write_text("retained", encoding="utf-8")
    marker = target / ".lapsim-ready.json"
    expected = {
        "schema": 1,
        "dependency_sha256": sha256(
            (bootstrap.ROOT / "pyproject.toml").read_bytes()
        ).hexdigest(),
        "source_root": str(bootstrap.ROOT),
        "python": [3, 13, 15],
        "dev": False,
    }
    if fault == "dependency":
        expected["dependency_sha256"] = "0" * 64
    elif fault == "source":
        expected["source_root"] = "another checkout"
    elif fault == "python":
        expected["python"] = [3, 12, 2]
    elif fault == "dev":
        expected["dev"] = True
    if fault != "absent":
        marker.write_text(
            "{bad" if fault == "corrupt" else json.dumps(expected), encoding="utf-8"
        )
    before = (
        (marker.read_bytes(), marker.stat().st_mtime_ns) if marker.exists() else None
    )
    monkeypatch.setattr(sys, "argv", ["bootstrap", "--check"])
    monkeypatch.setattr(
        bootstrap, "inspect_environment", lambda *args: {"version": [3, 13, 15]}
    )

    def no_install_or_runtime(*args, **kwargs):
        raise AssertionError(
            "stale check must stop before installing or certifying runtime"
        )

    monkeypatch.setattr(bootstrap, "command", no_install_or_runtime)
    monkeypatch.setattr(bootstrap, "check", no_install_or_runtime)
    assert bootstrap.main() == 2
    assert (target / "pyvenv.cfg").read_text(encoding="utf-8") == "retained"
    assert (
        (marker.read_bytes(), marker.stat().st_mtime_ns) if marker.exists() else None
    ) == before
