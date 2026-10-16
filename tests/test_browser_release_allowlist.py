"""Private/unreviewed replay files must never enter a staged browser site."""
import importlib.util
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess

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


@pytest.mark.parametrize("runtime_only", [False, True])
@pytest.mark.parametrize("name", ["enme408-synthetic-replay.json", "enme408-native-c-replay.json"])
def test_private_bytes_under_reviewed_source_name_fail_before_manifest(tmp_path, monkeypatch, runtime_only, name):
    module = builder(tmp_path, monkeypatch)
    (module.ROOT / "web/examples" / name).write_bytes(b"private replacement")
    output = tmp_path / "site"
    with pytest.raises(ValueError, match="unreviewed replay source"):
        module.build(output, runtime_only=runtime_only)
    assert not (output / "assets/runtime-manifest.json").exists()


@pytest.mark.parametrize("runtime_only", [False, True])
def test_private_bytes_under_reviewed_output_name_fail(tmp_path, monkeypatch, runtime_only):
    module = builder(tmp_path, monkeypatch)
    output = tmp_path / "site"
    module.build(output)
    target = output / "examples/enme408-native-c-replay.json"
    target.write_bytes(b"private output replacement")
    with pytest.raises(ValueError, match="unreviewed examples"):
        module.build(output, runtime_only=runtime_only)
    assert target.read_bytes() == b"private output replacement"


def test_reviewed_examples_survive_repeated_full_and_runtime_only_builds(tmp_path, monkeypatch):
    module = builder(tmp_path, monkeypatch)
    output = tmp_path / "site"
    for runtime_only in (False, True, False):
        manifest = module.build(output, runtime_only=runtime_only)
        assert manifest["reviewedReplaySha256"] == module.REVIEWED_REPLAY_EXAMPLES
        for name in module.REVIEWED_REPLAY_EXAMPLES:
            assert (output / "examples" / name).read_bytes() == (module.ROOT / "web/examples" / name).read_bytes()


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell is required for the actual site staging adapter")
@pytest.mark.parametrize("directory", ["examples", "web/examples"])
@pytest.mark.parametrize("name", ["private-extra.json", "enme408-native-c-replay.json"])
def test_site_staging_rejects_post_build_private_replays(tmp_path, monkeypatch, directory, name):
    module = builder(tmp_path, monkeypatch)
    output = tmp_path / "site"
    module.build(output)
    target = output / directory / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"post-build private sentinel")
    script = Path(__file__).resolve().parents[1] / "scripts/stage_team_site.ps1"
    result = subprocess.run([shutil.which("pwsh"), "-NoProfile", "-File", str(script),
                             "-OutputDirectory", str(output)], capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert "Unreviewed staged replay" in result.stderr
    assert target.read_bytes() == b"post-build private sentinel"


@pytest.mark.parametrize("runtime_only", [False, True])
def test_existing_windows_crlf_checkout_is_accepted_without_content_changes(tmp_path, monkeypatch, runtime_only):
    module = builder(tmp_path, monkeypatch)
    output = tmp_path / "site"
    module.build(output)
    for name in module.REVIEWED_REPLAY_EXAMPLES:
        for directory in (module.ROOT / "web/examples", output / "examples"):
            path = directory / name
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    module.build(output, runtime_only=runtime_only)


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell is required for the actual site staging adapter")
def test_site_source_copy_excludes_even_tracked_unreviewed_replays(tmp_path, monkeypatch):
    module = builder(tmp_path, monkeypatch)
    source = module.ROOT
    (source / "scripts").mkdir()
    original = Path(__file__).resolve().parents[1] / "scripts/stage_team_site.ps1"
    script = source / "scripts/stage_team_site.ps1"
    shutil.copy2(original, script)
    docs = source / "docs"
    (docs / "simulator_flowchart").mkdir(parents=True)
    (docs / "simulator_flowchart/index.html").write_text('<a class="repo-link" href="../../README.md">Repository README</a>')
    (docs / "simulator_research.md").write_text("# Synthetic test report")
    (docs / "web_simulator.md").write_text("Synthetic test guide")
    subprocess.run(["git", "init", "--quiet", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "add", "."], check=True, capture_output=True)
    output = tmp_path / "site"
    module.build(output)
    result = subprocess.run([shutil.which("pwsh"), "-NoProfile", "-File", str(script),
                             "-OutputDirectory", str(output)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (output / "web/examples/private-receipt.json").exists()
    assert {path.name for path in (output / "web/examples").iterdir()} == set(module.REVIEWED_REPLAY_EXAMPLES)


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell is required for the actual site staging adapter")
def test_mutable_manifest_cannot_redefine_reviewed_private_contents(tmp_path, monkeypatch):
    module = builder(tmp_path, monkeypatch)
    source = module.ROOT
    (source / "scripts").mkdir()
    original = Path(__file__).resolve().parents[1] / "scripts/stage_team_site.ps1"
    script = source / "scripts/stage_team_site.ps1"
    shutil.copy2(original, script)
    output = tmp_path / "site"
    module.build(output)
    name = "enme408-native-c-replay.json"
    private = b'"private receipt substituted together with mutable metadata"'
    (source / "web/examples" / name).write_bytes(private)
    (output / "examples" / name).write_bytes(private)
    manifest_path = output / "assets/runtime-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["reviewedReplaySha256"][name] = sha256(private).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    result = subprocess.run([shutil.which("pwsh"), "-NoProfile", "-File", str(script),
                             "-OutputDirectory", str(output)], capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert "Reviewed replay digest mismatch" in result.stderr
    assert not (output / "web/examples" / name).exists()
