"""A recipient rebuilding a source snapshot retains the documented handoff."""

import importlib.util
import json
from pathlib import Path
import shutil

import pytest


def test_no_git_rebuild_preserves_handoff_and_hashes(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("snapshot_build", root / "scripts/build_windows.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    snapshot = tmp_path / "source snapshot"
    snapshot.mkdir()
    names = (
        "README.md", "START-HERE.txt", "AGENTS.md", "ENME408_IMPLEMENTATION_PLAN.md",
        "pyproject.toml", "setup.py", "requirements-build.lock", "build_lapsim.cmd",
        "setup_lapsim.cmd", "setup_lapsim.ps1", "launch_lapsim.cmd", "packaging/LapSim.spec",
        "analysis/data/track/gnss_imu_endurance_track.csv",
        "analysis/data/track/gnss_imu_endurance_track.json",
        "docs/controller_testing_contract.md", "docs/team_release_contract.md",
        "controller/reference/native/torque_allocator.c", "controller/import-manifest.json",
        "web/index.html", "web/basic.html", "web/basic.js", "web/worker.js",
        "web/examples/enme408-synthetic-replay.json", "web/examples/enme408-native-c-replay.json",
        "web/control.html", "web/control.css", "web/control.js",
        "firmware/bench/main.c", "firmware/bench/startup.c", "firmware/bench/f405-qemu.ld",
    )
    for name in names:
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"snapshot content: {name}\n", encoding="utf-8")
    # Use the actual reviewed bytes, then contaminate the recipient's copy.
    shutil.copytree(root / "web", snapshot / "web", dirs_exist_ok=True)
    private = snapshot / "web/examples/private-capture.json"
    private.write_text('"private sentinel"', encoding="utf-8")
    (snapshot / "web/private-notes.txt").write_text("private notes", encoding="utf-8")
    (snapshot / "build-info.json").write_text('{"code_commit":"upstream-identity"}')
    monkeypatch.setattr(builder, "ROOT", snapshot)
    monkeypatch.setattr(builder, "version", lambda name: "test-version")

    class NoDependencyFiles:
        requires = ()
        files = ()

        def __init__(self, name):
            self.metadata = {"Name": name}

    monkeypatch.setattr(builder, "distribution", NoDependencyFiles)
    assets = builder.stage_assets()
    identity = json.loads((assets / "build-info.json").read_text())
    assert identity["code_commit"] == "upstream-identity"
    assert identity["dirty_worktree"] is True
    for name in names:
        assert (assets / name).read_bytes() == (snapshot / name).read_bytes()
        assert name in identity["files_sha256"]
    assert not (assets / "web/examples/private-capture.json").exists()
    assert not (assets / "web/private-notes.txt").exists()
    assert private.read_text(encoding="utf-8") == '"private sentinel"'


@pytest.mark.parametrize("mutation", ["replace", "remove", "missing_frontend", "missing_directory"])
def test_snapshot_rejects_changed_or_missing_reviewed_replay(tmp_path, monkeypatch, mutation):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("snapshot_replay_guard", root / "scripts/build_windows.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    shutil.copytree(root / "web", tmp_path / "web")
    replay = tmp_path / "web/examples/enme408-native-c-replay.json"
    if mutation == "replace":
        replay.write_bytes(b"private replacement")
    elif mutation == "remove":
        replay.unlink()
    elif mutation == "missing_frontend":
        (tmp_path / "web/app.js").unlink()
    else:
        shutil.rmtree(tmp_path / "web")
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="unreviewed|missing required"):
        builder.stage_assets()
