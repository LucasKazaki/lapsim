"""Verify the exact scoped import and its standard-library/local dependency closure."""
from __future__ import annotations

import ast
from hashlib import sha256
import json
from pathlib import Path
import sys

EXPECTED_UPSTREAM_COMMIT = "73cc2e2bbbf3fdae4a4fed1cc6e7b3df8bbb110e"
EXPECTED_MANIFEST_SHA256 = "90da35d8fa1386a1d7a12b024d2b5a32431c3d5dc36a91d6f5150599c430596e"


def verify(root: Path) -> dict:
    controller = root / "controller"
    manifest = json.loads((controller / "import-manifest.json").read_text(encoding="utf-8"))
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if (manifest.get("upstream_commit") != EXPECTED_UPSTREAM_COMMIT
            or sha256(canonical).hexdigest() != EXPECTED_MANIFEST_SHA256):
        raise ValueError("reviewed controller inventory identity mismatch")
    expected = set(manifest["files"])
    integration_files = {"import-manifest.json", "UPSTREAM.md"}
    for path in controller.rglob("*"):
        relative = path.relative_to(controller).as_posix()
        if path.is_symlink() or not path.resolve().is_relative_to(controller.resolve()):
            raise ValueError(f"linked controller path: {relative}")
        if path.is_file() and relative not in expected | integration_files:
            # Normal reference execution creates bytecode caches. These are
            # generated files, never source inventory or dependency owners.
            if path.parent.name == "__pycache__" and path.suffix == ".pyc":
                continue
            raise ValueError(f"unmanifested controller file: {relative}")
    local = {Path(name).stem for name in expected if name.startswith("reference/") and name.endswith(".py")}
    dependencies = set()
    for relative, facts in manifest["files"].items():
        path = controller / relative
        if not path.resolve().is_relative_to(controller.resolve()) or path.is_symlink():
            raise ValueError(f"import path escapes the controller: {relative}")
        raw = path.read_bytes()
        if len(raw) != facts["bytes"] or sha256(raw).hexdigest() != facts["sha256"]:
            raise ValueError(f"import identity mismatch: {relative}")
        if relative.startswith("reference/") and path.suffix == ".py":
            for node in ast.walk(ast.parse(raw, filename=relative)):
                if isinstance(node, ast.Import):
                    dependencies.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    dependencies.add(node.module.split(".")[0])
    external = dependencies - local - sys.stdlib_module_names - {"__future__"}
    if external:
        raise ValueError(f"undeclared controller Python dependencies: {sorted(external)}")
    return {"schema": "lapsim.controller-import-verification.v1",
            "upstream_commit": manifest["upstream_commit"],
            "verified_original_files": len(manifest["files"]),
            "python_dependencies": sorted(dependencies),
            "dependency_scope": "standard library and neighboring reference modules only"}


if __name__ == "__main__":
    print(json.dumps(verify(Path(__file__).resolve().parents[1]), indent=2))
