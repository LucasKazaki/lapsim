"""The reviewed source/receipt inventory cannot shrink with mutable metadata."""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]


def verifier():
    spec = importlib.util.spec_from_file_location("controller_inventory_check", ROOT / "scripts/check_controller_import.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_import_retains_all_419_original_blobs():
    assert verifier().verify(ROOT)["verified_original_files"] == 419


def test_deleting_receipt_and_inventory_entry_cannot_redefine_the_import(tmp_path):
    shutil.copytree(ROOT / "controller", tmp_path / "controller")
    path = tmp_path / "controller/import-manifest.json"
    manifest = json.loads(path.read_text())
    name = next(name for name in manifest["files"] if name.endswith(".log"))
    (tmp_path / "controller" / name).unlink()
    del manifest["files"][name]
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="inventory identity"):
        verifier().verify(tmp_path)


def test_modified_source_and_coordinated_manifest_hash_cannot_pass(tmp_path):
    from hashlib import sha256
    shutil.copytree(ROOT / "controller", tmp_path / "controller")
    path = tmp_path / "controller/import-manifest.json"
    manifest = json.loads(path.read_text())
    name = "reference/allocator.py"
    raw = b"# substituted controller\n"
    (tmp_path / "controller" / name).write_bytes(raw)
    manifest["files"][name].update(bytes=len(raw), sha256=sha256(raw).hexdigest())
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="inventory identity"):
        verifier().verify(tmp_path)
