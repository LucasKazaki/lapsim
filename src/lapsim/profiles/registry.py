"""Read and preserve an external engineering evidence bundle.

The registry is evidence, not solver configuration.  In particular, imported
normalizations and candidate bindings never set vehicle attributes on their
own.  This module deliberately has no dependency on the vehicle model.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import re
import shutil
from typing import Any


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON constant is forbidden: {value}")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        result = json.load(stream, parse_constant=_reject_constant)
    if not isinstance(result, dict):
        raise ValueError(f"expected a JSON object in {path.name}")
    def check(item: Any) -> None:
        if isinstance(item, float) and not isfinite(item):
            raise ValueError(f"nonfinite JSON number in {path.name}")
        if isinstance(item, dict):
            for nested in item.values():
                check(nested)
        elif isinstance(item, list):
            for nested in item:
                check(nested)
    check(result)
    return result


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_bundle_file(bundle_dir: Path, relative: str) -> Path:
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(f"unsafe bundle file path: {relative}")
    path = (bundle_dir / relative_path).resolve()
    if not path.is_relative_to(bundle_dir.resolve()):
        raise ValueError(f"bundle file escapes its directory: {relative}")
    return path


@dataclass(frozen=True)
class EngineeringRegistry:
    """Unmodified source records, including fields unknown to this adapter."""

    payload: dict[str, Any]
    artifact_map: dict[str, Any]
    profile_specs: dict[str, dict[str, Any]]
    bundle_manifest: dict[str, Any]
    bundle_dir: Path | None = None

    @property
    def dataset_id(self) -> str:
        return str(self.payload["dataset_id"])

    @property
    def parameters(self) -> tuple[dict[str, Any], ...]:
        return tuple(deepcopy(item) for item in self.payload["parameters"])

    @property
    def source_records(self) -> tuple[dict[str, Any], ...]:
        return tuple(deepcopy(item) for item in self.payload["source_records"])

    @property
    def open_questions(self) -> tuple[dict[str, Any], ...]:
        return tuple(deepcopy(item) for item in self.payload["open_questions"])

    @property
    def fingerprint(self) -> str:
        canonical = json.dumps(self.payload, sort_keys=True, allow_nan=False).encode("utf-8")
        return sha256(canonical).hexdigest()

    def snapshot(self) -> dict[str, Any]:
        return {
            "snapshot_schema_version": 1,
            "payload": deepcopy(self.payload),
            "artifact_map": deepcopy(self.artifact_map),
            "profile_specs": deepcopy(self.profile_specs),
            "bundle_manifest": deepcopy(self.bundle_manifest),
        }

    def save(self, path: str | Path) -> None:
        """Save a lossless JSON index; original evidence stays in the bundle."""

        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(self.snapshot(), stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, destination)

    @classmethod
    def load_snapshot(cls, path: str | Path) -> EngineeringRegistry:
        snapshot = _read_json(Path(path))
        if snapshot.get("snapshot_schema_version") != 1:
            raise ValueError("unsupported engineering registry snapshot")
        result = cls(
            payload=snapshot["payload"],
            artifact_map=snapshot["artifact_map"],
            profile_specs=snapshot["profile_specs"],
            bundle_manifest=snapshot["bundle_manifest"],
        )
        _validate_registry(result)
        return result


def _validate_registry(registry: EngineeringRegistry) -> None:
    parameters = registry.payload.get("parameters")
    sources = registry.payload.get("source_records")
    questions = registry.payload.get("open_questions")
    if not all(isinstance(items, list) for items in (parameters, sources, questions)):
        raise ValueError("registry requires parameter, source, and question lists")
    ids = [item["parameter_id"] for item in parameters]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate parameter ID")
    source_ids = [item["source_id"] for item in sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("duplicate source ID")
    known_sources = set(source_ids)
    for item in parameters:
        if item["source"]["source_id"] not in known_sources:
            raise ValueError(f"unknown source for {item['parameter_id']}")
    for item in questions:
        source = item.get("source_id")
        if source:
            for source_part in (part.strip() for part in str(source).split(";")):
                if source_part.startswith("SRC-") and source_part not in known_sources:
                    raise ValueError(f"unknown question source: {source_part}")
    if registry.payload.get("record_count") != len(parameters):
        raise ValueError("parameter count does not match registry")


def load_intake(bundle_dir: str | Path, *, verify_artifacts: bool = False) -> EngineeringRegistry:
    """Load an evidence bundle without applying its values to a simulator."""

    bundle = Path(bundle_dir).expanduser().resolve()
    registry = EngineeringRegistry(
        payload=_read_json(bundle / "data" / "registry" / "engineering_registry.json"),
        artifact_map=_read_json(bundle / "data" / "registry" / "artifacts.json"),
        profile_specs={path.stem: _read_json(path) for path in sorted((bundle / "data" / "profiles").glob("*.json"))},
        bundle_manifest=_read_json(bundle / "manifest.json"),
        bundle_dir=bundle,
    )
    _validate_registry(registry)
    if verify_artifacts:
        for file_record in registry.bundle_manifest.get("files", []):
            path = _safe_bundle_file(bundle, file_record["path"])
            if not path.is_file() or path.stat().st_size != file_record["size_bytes"]:
                raise ValueError(f"missing or incorrect bundle file: {file_record['path']}")
            if _file_hash(path) != file_record["sha256"]:
                raise ValueError(f"bundle hash mismatch: {file_record['path']}")
        for artifact in registry.artifact_map.get("artifacts", []):
            path = _safe_bundle_file(bundle, artifact["bundle_path"])
            if not path.is_file() or _file_hash(path) != artifact["sha256"]:
                raise ValueError(f"artifact hash mismatch: {artifact['artifact_id']}")
    return registry


def import_intake(bundle_dir: str | Path, private_store_dir: str | Path) -> Path:
    """Copy one verified immutable source revision to private local storage.

    A repeated import returns the same path.  A changed package receives a new
    hash-scoped path, so it cannot overwrite the previous evidence revision.
    """

    registry = load_intake(bundle_dir, verify_artifacts=True)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", registry.dataset_id):
        raise ValueError("unsafe registry dataset ID")
    manifest_hash = _file_hash(Path(bundle_dir) / "manifest.json")
    destination = Path(private_store_dir).expanduser().resolve() / registry.dataset_id / manifest_hash
    if destination.exists():
        load_intake(destination, verify_artifacts=True)
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        raise FileExistsError(f"unfinished private import exists: {temporary}")
    shutil.copytree(Path(bundle_dir), temporary)
    try:
        load_intake(temporary, verify_artifacts=True)
        temporary.rename(destination)
    except Exception:
        shutil.rmtree(temporary)
        raise
    return destination


def default_bundle_dir() -> Path | None:
    """Locate optional local evidence; package source is never auto-imported."""

    override = os.environ.get("LAPSIM_DATA_BUNDLE")
    if override:
        path = Path(override).expanduser()
        return path if (path / "data" / "registry" / "engineering_registry.json").is_file() else None
    path = Path.home() / "Downloads" / "ENME408_LapSim_Data_Integration" / "ENME408_LapSim_Data_Integration"
    return path if (path / "data" / "registry" / "engineering_registry.json").is_file() else None


__all__ = ["EngineeringRegistry", "default_bundle_dir", "import_intake", "load_intake"]
