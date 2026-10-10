"""Stage a static browser simulator with exact Python source and course data.

This creates files locally. Hosting/publishing is a separate operation.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from importlib.metadata import distribution
import json
from pathlib import Path
import platform
import shutil
import subprocess
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
PYODIDE_VERSION = "314.0.7"
VENDORED_PURE_PYTHON = {"openpyxl": "3.1.5", "et_xmlfile": "2.0.0"}


def _git(arguments: list[str]) -> str | None:
    try:
        return subprocess.run(
            ["git", *arguments], cwd=ROOT, check=True, capture_output=True,
            text=True, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def runtime_files() -> dict[str, bytes]:
    files = {
        f"bundle/{path.relative_to(ROOT).as_posix()}": path.read_bytes()
        for path in sorted((ROOT / "src").rglob("*.py"))
        if "__pycache__" not in path.parts
    }
    files["bundle/web/bridge.py"] = (ROOT / "web/bridge.py").read_bytes()
    data = ROOT / "analysis/data/track"
    for path in sorted(data.iterdir()):
        if path.is_file() and path.suffix.lower() in {".csv", ".json"}:
            files[f"bundle/{path.relative_to(ROOT).as_posix()}"] = path.read_bytes()
    # Course parsing imports openpyxl even when no spreadsheet is selected.
    # Ship actual universal-package source and original distribution metadata
    # from the locked build environment, rather than needing PyPI at runtime.
    for name, required_version in VENDORED_PURE_PYTHON.items():
        installed = distribution(name)
        if installed.version != required_version:
            raise RuntimeError(f"browser packaging requires {name}=={required_version}; install requirements-build.lock")
        metadata_directory = f"{name}-{required_version}.dist-info"
        copied = 0
        for relative in installed.files or ():
            relative = Path(str(relative))
            if (
                not relative.parts or relative.parts[0] not in {name, metadata_directory}
                or ".." in relative.parts or "__pycache__" in relative.parts
                or relative.suffix == ".pyc"
            ):
                continue
            path = installed.locate_file(relative)
            if path.is_file():
                files[f"bundle/vendor/{relative.as_posix()}"] = path.read_bytes()
                copied += 1
        if not copied or f"bundle/vendor/{metadata_directory}/METADATA" not in files:
            raise RuntimeError(f"could not preserve real {name} source and metadata")
    digest = sha256()
    for name, content in sorted(files.items()):
        digest.update(name.encode("utf-8") + b"\0" + content + b"\0")
    commit = _git(["rev-parse", "HEAD"])
    dirty = _git(["status", "--porcelain", "--untracked-files=normal"])
    identity = {
        "build_kind": "browser_python_source_snapshot",
        "code_commit": commit,
        "dirty_worktree": bool(dirty) if dirty is not None else None,
        "source_sha256": digest.hexdigest(),
        "source_hash_scope": "sorted runtime archive paths + NUL + exact file bytes + NUL, excluding build-info.json",
        "build_python": platform.python_version(),
        "pyodide_version": PYODIDE_VERSION,
        "vendored_pure_python": VENDORED_PURE_PYTHON,
        "file_sha256": {name.removeprefix("bundle/"): sha256(content).hexdigest() for name, content in sorted(files.items())},
    }
    files["bundle/build-info.json"] = (json.dumps(identity, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return files


def build(output: Path, *, runtime_only: bool = False) -> dict:
    output = output.resolve()
    if output == ROOT or output in {ROOT / "src", ROOT / "web"}:
        raise ValueError("choose a separate output folder")
    assets = output / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    if not runtime_only:
        for name in ("index.html", "app.js", "styles.css", "worker.js"):
            source = ROOT / "web" / name
            if not source.is_file():
                raise FileNotFoundError(f"Frontend file is missing: {source}")
            shutil.copy2(source, output / name)
    else:
        shutil.copy2(ROOT / "web/worker.js", output / "worker.js")
    files = runtime_files()
    archive = assets / "lapsim-runtime.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=9) as package:
        for name, content in sorted(files.items()):
            info = ZipInfo(name, (2026, 10, 9, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            package.writestr(info, content)
    identity = json.loads(files["bundle/build-info.json"])
    manifest = {
        "protocolVersion": 1,
        "pyodideVersion": PYODIDE_VERSION,
        "pyodideIndexUrl": f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/",
        "packages": ["numpy", "scipy", "matplotlib"],
        "vendoredPurePython": VENDORED_PURE_PYTHON,
        "archiveSha256": sha256(archive.read_bytes()).hexdigest(),
        "archiveBytes": archive.stat().st_size,
        "sourceIdentity": identity,
        "sourceFiles": len(files),
        "runtimeRequirements": "HTTPS or localhost; module Web Worker; WebAssembly; access to the pinned Pyodide CDN",
    }
    (assets / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output / "serve.cmd").write_text("@echo off\r\ncd /d \"%~dp0\"\r\npython -m http.server 8000\r\n", encoding="ascii")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist/web")
    parser.add_argument("--runtime-only", action="store_true", help="Stage physics assets while the frontend is being developed")
    args = parser.parse_args()
    manifest = build(args.output_dir, runtime_only=args.runtime_only)
    print(json.dumps({"output": str(args.output_dir.resolve()), "archiveBytes": manifest["archiveBytes"], "archiveSha256": manifest["archiveSha256"], "sourceFiles": manifest["sourceFiles"], "pyodideVersion": manifest["pyodideVersion"]}, indent=2))


if __name__ == "__main__":
    main()
