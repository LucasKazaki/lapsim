"""The portable build must not depend on a source checkout or ambient Git."""

import json
import sys
from unittest.mock import patch

from lapsim.resources import build_identity, documentation_root, repository_root


def test_checkout_resources_follow_module_location():
    assert (
        repository_root() / "analysis/data/track/gnss_imu_endurance_track.csv"
    ).is_file()
    assert build_identity() is None


def test_frozen_assets_and_durable_offline_help(tmp_path, monkeypatch):
    extract = tmp_path / "extracted"
    assets = extract / "bundle"
    (assets / "docs/simulator_flowchart").mkdir(parents=True)
    map_path = assets / "docs/simulator_flowchart/index.html"
    map_path.write_text("offline", encoding="utf-8")
    (assets / "src/lapsim").mkdir(parents=True)
    (assets / "src/lapsim/example.py").write_text("source", encoding="utf-8")
    identity = {
        "code_commit": "captured",
        "dirty_worktree": True,
        "source_sha256": "a" * 64,
    }
    (assets / "build-info.json").write_text(json.dumps(identity), encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(extract), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "user"))
    assert repository_root() == assets
    assert build_identity() == identity
    cached = documentation_root()
    assert cached != assets
    map_path.unlink()
    assert (
        documentation_root() / "docs/simulator_flowchart/index.html"
    ).read_text() == "offline"
    assert (cached / "src/lapsim/example.py").read_text() == "source"
    from lapsim.profiles.adapter import _code_identity

    with patch(
        "lapsim.profiles.adapter.subprocess.run",
        side_effect=AssertionError("Ambient Git must not run"),
    ):
        assert _code_identity() == ("captured", True)


def test_extended_windows_path_preserves_drive_unc_and_existing_prefix():
    from lapsim.resources import _extended_windows_path

    assert (
        _extended_windows_path("C:\\user space\\long") == "\\\\?\\C:\\user space\\long"
    )
    assert (
        _extended_windows_path("\\\\server\\share\\long")
        == "\\\\?\\UNC\\server\\share\\long"
    )
    assert _extended_windows_path("\\\\?\\C:\\long") == "\\\\?\\C:\\long"


def test_no_git_snapshot_uses_captured_identity_and_detects_modified_source(
    tmp_path, monkeypatch
):
    import subprocess
    from hashlib import sha256

    from lapsim import resources
    from lapsim.experiments.dynamics_record import _code_identity

    outer = tmp_path / "unrelated"
    outer.mkdir()
    subprocess.run(["git", "init", "-q", str(outer)], check=True)
    (outer / "note.txt").write_text("unrelated repository")
    subprocess.run(["git", "add", "note.txt"], cwd=outer, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "unrelated fixture",
        ],
        cwd=outer,
        check=True,
    )
    source = outer / "extracted source"
    module = source / "src/lapsim/resources.py"
    module.parent.mkdir(parents=True)
    module.write_text("original source", encoding="utf-8")
    (source / "pyproject.toml").write_text("[project]\n")
    hashes = {"src/lapsim/resources.py": sha256(module.read_bytes()).hexdigest()}
    identity = {
        "code_commit": "captured-source",
        "dirty_worktree": False,
        "source_sha256": "a" * 64,
        "files_sha256": hashes,
    }
    (source / ".lapsim-source-info.json").write_text(json.dumps(identity))
    monkeypatch.setattr(resources, "__file__", str(module))
    assert _code_identity()["code_commit"] == "captured-source"
    assert resources.build_identity()["dirty_worktree"] is False
    module.write_text("changed source", encoding="utf-8")
    changed = resources.build_identity()
    assert (
        changed["code_commit"] == "captured-source"
        and changed["dirty_worktree"] is True
    )
    assert changed["source_sha256"] != identity["source_sha256"]
    assert changed["captured_source_sha256"] == identity["source_sha256"]
