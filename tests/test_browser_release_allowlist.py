"""Private/unreviewed replay files must never enter a staged browser site."""
import importlib.util
from pathlib import Path
import shutil

import pytest


def builder(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("allowlisted_web_build", root / "scripts/build_web.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "checkout"
    shutil.copytree(root / "web", source / "web")
    (source / "web/examples/private-receipt.json").write_text('"private sentinel"')
    monkeypatch.setattr(module, "ROOT", source)
    monkeypatch.setattr(module, "runtime_files", lambda: {"bundle/build-info.json": b"{}"})
    return module


def test_only_two_reviewed_examples_are_staged(tmp_path, monkeypatch):
    module = builder(tmp_path, monkeypatch)
    output = tmp_path / "site"
    module.build(output)
    expected = {"enme408-synthetic-replay.json", "enme408-native-c-replay.json"}
    assert {path.name for path in (output / "examples").iterdir()} == expected
    for name in expected:
        assert (output / "examples" / name).read_bytes() == (module.ROOT / "web/examples" / name).read_bytes()


@pytest.mark.parametrize("runtime_only", [False, True])
def test_stale_unreviewed_output_is_preserved_and_build_fails(tmp_path, monkeypatch, runtime_only):
    module = builder(tmp_path, monkeypatch)
    output = tmp_path / "site"
    examples = output / "examples"
    examples.mkdir(parents=True)
    private = examples / "previous-private.json"
    private.write_bytes(b"retain but do not publish")
    with pytest.raises(ValueError, match="unreviewed"):
        module.build(output, runtime_only=runtime_only)
    assert private.read_bytes() == b"retain but do not publish"
