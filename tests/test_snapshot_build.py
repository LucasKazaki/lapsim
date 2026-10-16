"""A recipient rebuilding a source snapshot retains the documented handoff."""

import importlib.util
import json
from pathlib import Path


def test_no_git_rebuild_preserves_handoff_and_hashes(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("snapshot_build", root / "scripts/build_windows.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    snapshot = tmp_path / "source snapshot"
    snapshot.mkdir()
    names = (
        "README.md", "START-HERE.txt", "AGENTS.md", "ENME408_IMPLEMENTATION_PLAN.md",
        "pyproject.toml", "requirements-build.lock", "build_lapsim.cmd",
        "setup_lapsim.cmd", "setup_lapsim.ps1", "launch_lapsim.cmd", "packaging/LapSim.spec",
        "analysis/data/track/gnss_imu_endurance_track.csv",
        "analysis/data/track/gnss_imu_endurance_track.json",
        "docs/controller_testing_contract.md", "docs/team_release_contract.md",
        "controller/reference/native/torque_allocator.c", "controller/import-manifest.json",
        "web/index.html", "web/basic.html", "web/basic.js", "web/worker.js",
        "web/examples/synthetic_controller_bench_v1.json",
    )
    for name in names:
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"snapshot content: {name}\n", encoding="utf-8")
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
