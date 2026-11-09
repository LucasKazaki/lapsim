"""Installed command dispatch preserves arguments and caller import state."""

import sys

import pytest

from lapsim.events import cli


def test_command_uses_captured_resource_and_restores_path(tmp_path, monkeypatch):
    script = tmp_path / "analysis/events/skidpad_points.py"
    script.parent.mkdir(parents=True)
    script.write_text("# captured command\n", encoding="utf-8")
    monkeypatch.setattr(cli, "repository_root", lambda: tmp_path)
    initial = list(sys.path)
    arguments = ["--sequence", "--cone-penalty-policy", "raw-only"]

    def load(path, *, run_name):
        assert path == str(script)
        assert run_name != "__main__"
        sys.path.insert(0, "temporary command imports")

        def main(argv):
            assert argv is arguments
            return 3

        return {"main": main}

    monkeypatch.setattr(cli.runpy, "run_path", load)
    assert cli.main(arguments) == 3
    assert sys.path == initial


def test_command_exception_restores_import_path(tmp_path, monkeypatch):
    script = tmp_path / "analysis/events/skidpad_points.py"
    script.parent.mkdir(parents=True)
    script.write_text("# captured command\n", encoding="utf-8")
    monkeypatch.setattr(cli, "repository_root", lambda: tmp_path)
    initial = list(sys.path)

    def load(*args, **kwargs):
        sys.path.insert(0, "temporary command imports")
        raise ValueError("command failed")

    monkeypatch.setattr(cli.runpy, "run_path", load)
    with pytest.raises(ValueError, match="command failed"):
        cli.main([])
    assert sys.path == initial


def test_missing_command_has_no_checkout_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "repository_root", lambda: tmp_path)
    with pytest.raises(RuntimeError, match="unavailable"):
        cli.main([])
