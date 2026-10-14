"""The portable build must not depend on a source checkout or ambient Git."""
import json
from pathlib import Path
import sys
from unittest.mock import patch

from lapsim.resources import build_identity, documentation_root, repository_root


def test_checkout_resources_follow_module_location():
    assert (repository_root() / "analysis/data/track/gnss_imu_endurance_track.csv").is_file()
    assert build_identity() is None


def test_frozen_assets_and_durable_offline_help(tmp_path, monkeypatch):
    extract = tmp_path / "extracted"
    assets = extract / "bundle"
    (assets / "docs/simulator_flowchart").mkdir(parents=True)
    map_path = assets / "docs/simulator_flowchart/index.html"
    map_path.write_text("offline", encoding="utf-8")
    (assets / "src/lapsim").mkdir(parents=True)
    (assets / "src/lapsim/example.py").write_text("source", encoding="utf-8")
    identity = {"code_commit": "captured", "dirty_worktree": True, "source_sha256": "abc123"}
    (assets / "build-info.json").write_text(json.dumps(identity), encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(extract), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "user"))
    assert repository_root() == assets
    assert build_identity() == identity
    cached = documentation_root()
    assert cached != assets
    map_path.unlink()
    assert (documentation_root() / "docs/simulator_flowchart/index.html").read_text() == "offline"
    assert (cached / "src/lapsim/example.py").read_text() == "source"
    from lapsim.profiles.adapter import _code_identity
    with patch("lapsim.profiles.adapter.subprocess.run", side_effect=AssertionError("Ambient Git must not run")):
        assert _code_identity() == ("captured", True)
