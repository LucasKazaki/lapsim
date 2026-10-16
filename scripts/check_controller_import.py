"""Verify the exact scoped import and its standard-library/local dependency closure."""
from __future__ import annotations

import ast
from hashlib import sha256
import json
from pathlib import Path
import sys


def verify(root: Path) -> dict:
    controller = root / "controller"
    manifest = json.loads((controller / "import-manifest.json").read_text(encoding="utf-8"))
    local = {path.stem for path in (controller / "reference").glob("*.py")}
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
