"""Explicit profile-to-vehicle adapter with per-field source accounting."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from math import isclose, isfinite
from pathlib import Path
import subprocess
from typing import Any

from vehicle_model import Vehicle

from .registry import EngineeringRegistry, default_bundle_dir, load_intake


@dataclass(frozen=True, slots=True)
class ProfileInfo:
    profile_id: str
    name: str
    description: str
    source: str
    available: bool = True


@dataclass(frozen=True, slots=True)
class ResolvedField:
    path: str
    value: float
    unit: str
    origin: str
    model_use: str
    parameter_id: str | None = None
    source_id: str | None = None
    source_locator: str | None = None
    artifact_id: str | None = None
    evidence_status: str | None = None
    conversion: str | None = None
    caveat: str | None = None


@dataclass(frozen=True, slots=True)
class ResolvedManifest:
    """An immutable summary of the exact selected and inherited inputs."""

    profile_id: str
    profile_name: str
    profile_schema_version: str
    backend: str
    code_commit: str | None
    dirty_worktree: bool | None
    registry_dataset_id: str | None
    registry_sha256: str | None
    profile_sha256: str | None
    artifact_sha256: tuple[tuple[str, str], ...]
    selected_fields: tuple[ResolvedField, ...]
    inherited_fields: tuple[ResolvedField, ...]
    unused_records: tuple[tuple[str, str], ...]
    limitations: tuple[str, ...]
    model_config_json: str
    run_context_json: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["artifact_sha256"] = dict(self.artifact_sha256)
        result["unused_records"] = [
            {"parameter_id": parameter_id, "model_use": model_use}
            for parameter_id, model_use in self.unused_records
        ]
        result["run_context"] = json.loads(self.run_context_json) if self.run_context_json else None
        result["model_config"] = json.loads(self.model_config_json)
        del result["model_config_json"]
        del result["run_context_json"]
        return result

    def with_run_context(self, **settings: Any) -> ResolvedManifest:
        """Freeze track/controller/solver/initial-state details for a saved run."""

        context = json.dumps(settings, sort_keys=True, allow_nan=False)
        return replace(self, run_context_json=context)

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.to_dict(), indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )


# Only these paths can be promoted from the external evidence package.  The
# declared unit must match the public model's unit.  Axle heights are retained
# in model telemetry but are not currently used by the suspension force model.
_ALLOWED_BINDINGS: dict[str, tuple[str, str]] = {
    "mass_kg": ("kg", "used_by_this_run"),
    "chassis.static_front_weight_fraction": ("fraction", "used_by_this_run"),
    "chassis.wheelbase_m": ("m", "used_by_this_run"),
    "chassis.front_track_width_m": ("m", "used_by_this_run"),
    "chassis.rear_track_width_m": ("m", "used_by_this_run"),
    "chassis.cg_height_m": ("m", "used_by_this_run"),
    "chassis.front_axle_height_m": ("m", "supported_metadata_only"),
    "chassis.rear_axle_height_m": ("m", "supported_metadata_only"),
    "chassis.front_roll_axis_height_m": ("m", "used_by_this_run"),
    "chassis.rear_roll_axis_height_m": ("m", "used_by_this_run"),
    "aero.lift_coefficient": ("dimensionless", "used_by_this_run"),
    "aero.drag_coefficient": ("dimensionless", "used_by_this_run"),
    "aero.frontal_area_m2": ("m^2", "used_by_this_run"),
    "aero.front_downforce_fraction": ("fraction", "used_by_this_run"),
    "air_density_kgpm3": ("kg/m^3", "used_by_this_run"),
}
_AERO_ATOMIC_PATHS = frozenset((
    "aero.lift_coefficient", "aero.drag_coefficient", "aero.frontal_area_m2"
))


def _code_identity() -> tuple[str | None, bool | None]:
    root = Path(__file__).resolve().parents[3]
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True,
            text=True, timeout=5,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"], cwd=root,
            check=True, capture_output=True, text=True, timeout=5,
        ).stdout.strip())
        return head, dirty
    except (OSError, subprocess.SubprocessError):
        return None, None


def _get_value(vehicle: Vehicle, path: str) -> float:
    part = vehicle
    for name in path.split("."):
        part = getattr(part, name)
    return float(part)


def _snapshot_config(value: Any) -> Any:
    """Capture constructor fields, excluding changing simulation state."""

    if is_dataclass(value) and not isinstance(value, type):
        return {
            "class": type(value).__name__,
            "fields": {
                item.name: _snapshot_config(getattr(value, item.name))
                for item in fields(value)
                if item.init and not (type(value).__name__ == "Drivetrain" and item.name == "tire")
            },
        }
    if isinstance(value, (tuple, list)):
        return [_snapshot_config(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _snapshot_config(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("nonfinite configured model input")
        return value
    raise TypeError(f"cannot snapshot model configuration type {type(value).__name__}")


def _set_value(vehicle: Vehicle, path: str, value: float) -> None:
    names = path.split(".")
    parent = vehicle
    for name in names[:-1]:
        parent = getattr(parent, name)
    setattr(parent, names[-1], value)


def _manifest(
    info: ProfileInfo,
    vehicle: Vehicle,
    selected: tuple[ResolvedField, ...] = (),
    registry: EngineeringRegistry | None = None,
    spec: dict[str, Any] | None = None,
    limitations: tuple[str, ...] = (),
) -> ResolvedManifest:
    selected_paths = {item.path for item in selected}
    inherited = tuple(
        ResolvedField(
            path=path, value=_get_value(vehicle, path), unit=unit,
            origin="inherited_model_default", model_use=model_use,
            caveat="Current repository Vehicle default; no source-car claim",
        )
        for path, (unit, model_use) in _ALLOWED_BINDINGS.items()
        if path not in selected_paths
    )
    selected_ids = {item.parameter_id for item in selected}
    unused = tuple(
        (record["parameter_id"], _classify_record(record, selected_ids))
        for record in registry.payload["parameters"]
        if record["parameter_id"] not in selected_ids
    ) if registry else ()
    profile_hash = sha256(json.dumps(spec, sort_keys=True, allow_nan=False).encode()).hexdigest() if spec else None
    artifact_hashes = tuple(sorted(
        (artifact["artifact_id"], artifact["sha256"])
        for artifact in registry.artifact_map.get("artifacts", [])
    )) if registry else ()
    code_commit, dirty = _code_identity()
    return ResolvedManifest(
        profile_id=info.profile_id, profile_name=info.name,
        profile_schema_version=str(spec.get("schema_version", "1")) if spec else "1",
        backend="vehicle_model.Vehicle", code_commit=code_commit,
        dirty_worktree=dirty,
        registry_dataset_id=registry.dataset_id if registry else None,
        registry_sha256=registry.fingerprint if registry else None,
        profile_sha256=profile_hash,
        artifact_sha256=artifact_hashes, selected_fields=selected,
        inherited_fields=inherited, unused_records=unused,
        limitations=limitations,
        model_config_json=json.dumps(_snapshot_config(vehicle), sort_keys=True, allow_nan=False),
    )


def _classify_record(record: dict[str, Any], selected_ids: set[str]) -> str:
    if record["parameter_id"] in selected_ids:
        binding = record.get("candidate_binding")
        if binding and binding.get("target_path_relative_to_vehicle") in _ALLOWED_BINDINGS:
            return _ALLOWED_BINDINGS[binding["target_path_relative_to_vehicle"]][1]
    if record.get("source_value", {}).get("kind") == "unknown":
        return "unresolved"
    if record.get("candidate_binding"):
        return "available_but_unselected"
    return "stored_for_future"


def _resolve_bundle(data_dir: str | Path | None) -> EngineeringRegistry:
    path = Path(data_dir) if data_dir is not None else default_bundle_dir()
    if path is None:
        raise FileNotFoundError("Local ENME408 evidence bundle is unavailable; set LAPSIM_DATA_BUNDLE")
    return load_intake(path)


def list_profiles(data_dir: str | Path | None = None) -> tuple[ProfileInfo, ...]:
    """List runnable profiles. The private source profiles are optional."""

    result = [
        ProfileInfo("repository_baseline", "Repository baseline", "Current Formula SAE model defaults", "repository"),
        ProfileInfo("prius_2026_le", "2026 Prius LE benchmark", "Simplified published-power benchmark with engineering estimates", "Toyota and model assumptions"),
    ]
    path = Path(data_dir) if data_dir is not None else default_bundle_dir()
    if path is not None and (path / "data" / "registry" / "engineering_registry.json").is_file():
        result.extend((
            ProfileInfo("trev5_working_geometry", "TREV5 working geometry", "Partial source working scenario; uncalibrated", "local ENME408 intake"),
            ProfileInfo("trev5_working_geometry_aero", "TREV5 working geometry + aero", "Partial source aero comparison; uncalibrated", "local ENME408 intake"),
        ))
    return tuple(result)


def _validated_bindings(registry: EngineeringRegistry, spec: dict[str, Any]) -> tuple[ResolvedField, ...]:
    if spec.get("kind") != "implementation_profile_specification" or spec.get("auto_load") is not False:
        raise ValueError("profile must be an explicitly selected implementation specification")
    records = {record["parameter_id"]: record for record in registry.payload["parameters"]}
    artifacts = {item["artifact_id"]: item for item in registry.artifact_map.get("artifacts", [])}
    bindings = spec.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        raise ValueError("profile has no bindings")
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    resolved = []
    for binding in bindings:
        parameter_id = binding.get("parameter_id")
        path = binding.get("target_path_relative_to_vehicle")
        if parameter_id in seen_ids or path in seen_paths:
            raise ValueError(f"duplicate profile binding: {parameter_id} / {path}")
        seen_ids.add(parameter_id)
        seen_paths.add(path)
        if path not in _ALLOWED_BINDINGS:
            raise ValueError(f"unsupported solver binding: {path}")
        unit, model_use = _ALLOWED_BINDINGS[path]
        if binding.get("unit") != unit:
            raise ValueError(f"unit mismatch for {parameter_id}: expected {unit}")
        if parameter_id not in records:
            raise ValueError(f"missing registry record: {parameter_id}")
        record = records[parameter_id]
        source = record["source"]
        if binding.get("source_id") != source["source_id"] or binding.get("source_artifact_id") != source.get("associated_uploaded_artifact_id"):
            raise ValueError(f"source mismatch for {parameter_id}")
        artifact = artifacts.get(binding.get("source_artifact_id"))
        if artifact is None or artifact.get("logical_source_id") != binding.get("source_id"):
            raise ValueError(f"unresolved source artifact for {parameter_id}")
        value = binding.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise ValueError(f"nonfinite or nonnumeric solver value for {parameter_id}")
        conversion = binding.get("conversion", {})
        if conversion.get("expression") != "source_value * conversion_factor":
            raise ValueError(f"unreviewed conversion for {parameter_id}")
        try:
            source_value = Decimal(conversion["source_value_text"])
            factor = Decimal(conversion["conversion_factor"])
            exact = source_value * factor
            claimed = Decimal(conversion["result_decimal"])
            original = Decimal(record["source_value"]["text"])
        except (InvalidOperation, KeyError, TypeError) as exc:
            raise ValueError(f"invalid conversion for {parameter_id}") from exc
        if source_value != original or not isclose(float(exact), float(claimed), rel_tol=1e-12, abs_tol=1e-12) or not isclose(float(exact), float(value), rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError(f"conversion disagrees with source for {parameter_id}")
        if path == "mass_kg" and (record.get("original_unit_text") != "lb" or "pound mass" not in conversion.get("interpretation", "")):
            raise ValueError("vehicle mass requires explicit pound-mass interpretation")
        if path == "aero.lift_coefficient" and value > 0:
            raise ValueError("source lift coefficient must use signed negative downforce")
        if path in {"mass_kg", "chassis.wheelbase_m", "chassis.cg_height_m", "chassis.front_track_width_m", "chassis.rear_track_width_m", "aero.frontal_area_m2", "air_density_kgpm3"} and value <= 0:
            raise ValueError(f"{path} must be positive")
        if path.endswith("fraction") and not 0 <= value <= 1:
            raise ValueError(f"{path} must be in [0, 1]")
        if path == "aero.drag_coefficient" and value < 0:
            raise ValueError("drag coefficient cannot be negative")
        resolved.append(ResolvedField(
            path=path, value=float(value), unit=unit, origin="selected_source_profile",
            model_use=model_use, parameter_id=parameter_id,
            source_id=binding["source_id"], source_locator=binding.get("source_locator"),
            artifact_id=binding.get("source_artifact_id"),
            evidence_status=binding.get("evidence_status"),
            conversion=conversion.get("interpretation"),
            caveat=binding.get("additional_caveat") or record.get("caveats"),
        ))
    required = spec.get("required_for_physics_overlay")
    if not isinstance(required, list) or not required or not all(isinstance(item, str) for item in required):
        raise ValueError("profile must declare mandatory physics bindings")
    if not set(required).issubset(seen_ids):
        raise ValueError("mandatory profile physics binding is missing")
    if seen_paths & _AERO_ATOMIC_PATHS and not _AERO_ATOMIC_PATHS.issubset(seen_paths):
        raise ValueError("reference area, drag and lift coefficients must be selected together")
    for group in spec.get("atomic_groups", []):
        ids = set(group.get("apply_together", []))
        if seen_ids & ids and not ids.issubset(seen_ids):
            raise ValueError(f"incomplete atomic binding group: {group.get('group')}")
    return tuple(resolved)


def build_vehicle(profile_id: str, data_dir: str | Path | None = None) -> tuple[Vehicle, ResolvedManifest]:
    """Create a fresh vehicle and a source-aware configuration snapshot."""

    infos = {info.profile_id: info for info in list_profiles(data_dir)}
    if profile_id not in infos:
        raise ValueError(f"unknown or unavailable vehicle profile: {profile_id}")
    info = infos[profile_id]
    if profile_id == "repository_baseline":
        vehicle = Vehicle()
        return vehicle, _manifest(info, vehicle, limitations=("Repository defaults are a model baseline, not an as-built car.",))
    if profile_id == "prius_2026_le":
        from lapsim.ui.presets import VehicleSetup, make_prius_benchmark, TOYOTA_2026_PRIUS_SPECS
        vehicle = make_prius_benchmark(VehicleSetup())
        published = {"mass_kg", "chassis.wheelbase_m"}
        explicit = (
            "mass_kg", "chassis.wheelbase_m", "chassis.cg_height_m",
            "chassis.front_track_width_m", "chassis.rear_track_width_m",
            "chassis.static_front_weight_fraction", "aero.frontal_area_m2",
            "aero.drag_coefficient", "aero.lift_coefficient",
            "aero.front_downforce_fraction",
        )
        selected = tuple(
            ResolvedField(
                path=path, value=_get_value(vehicle, path),
                unit=_ALLOWED_BINDINGS[path][0], origin="prius_benchmark_preset",
                model_use=_ALLOWED_BINDINGS[path][1],
                source_locator=TOYOTA_2026_PRIUS_SPECS["sources"][0] if path in published else None,
                evidence_status="published Toyota specification" if path in published else "engineering estimate",
                caveat=None if path in published else "Simplified benchmark assumption",
            ) for path in explicit
        )
        return vehicle, _manifest(info, vehicle, selected=selected, limitations=(
            "Equivalent power source and estimated tire/aero/pack inputs; hybrid drivetrain is not modeled.",
        ))
    registry = _resolve_bundle(data_dir)
    spec = registry.profile_specs.get(profile_id)
    if spec is None or spec.get("profile_id") != profile_id:
        raise ValueError(f"missing profile specification: {profile_id}")
    # Validate every selected mapping and its source before constructing or
    # mutating a vehicle. A failed selection cannot alter a live prior run.
    selected = _validated_bindings(registry, spec)
    vehicle = Vehicle()
    for field in selected:
        _set_value(vehicle, field.path, field.value)
    vehicle.validate()
    vehicle.reset_state()
    return vehicle, _manifest(info, vehicle, selected, registry, spec, limitations=(
        str(spec.get("evidence_label", "Partial source scenario")),
        "Driver inclusion and released vehicle identity are unknown.",
        "Unselected motor, tire, pack, brake, and controls stay at current repository defaults.",
        "Aero roll-loss settings are inherited from the repository model.",
    ))


def preview_profile(profile_id: str, data_dir: str | Path | None = None) -> ResolvedManifest:
    """Inspect a profile without changing an existing vehicle."""

    return build_vehicle(profile_id, data_dir)[1]


def browse_records(
    data_dir: str | Path | None = None, *, profile_id: str | None = None,
    subsystem: str | None = None, configuration: str | None = None,
    source_id: str | None = None, model_use: str | None = None,
    query: str | None = None,
) -> tuple[dict[str, Any], ...]:
    """Return source facts with evidence and profile-specific model-use status."""

    registry = _resolve_bundle(data_dir)
    selected_ids: set[str] = set()
    if profile_id is not None:
        if profile_id not in {"repository_baseline", "prius_2026_le"}:
            spec = registry.profile_specs.get(profile_id)
            if spec is None:
                raise ValueError(f"unknown source profile: {profile_id}")
            selected_ids = {field.parameter_id for field in _validated_bindings(registry, spec)}
    views = []
    for record in registry.payload["parameters"]:
        use = _classify_record(record, selected_ids)
        view = {
            "parameter_id": record["parameter_id"],
            "name": record.get("name"),
            "value": record.get("source_value", {}).get("value"),
            "value_text": record.get("source_value", {}).get("text"),
            "unit": record.get("original_unit_text"),
            "evidence": record.get("evidence_status"),
            "source_id": record.get("source", {}).get("source_id"),
            "source_locator": record.get("source", {}).get("locator_as_recorded"),
            "artifact_id": record.get("source", {}).get("associated_uploaded_artifact_id"),
            "model_use": use,
            "caveat": record.get("caveats"),
            "subsystem": record.get("subsystem"),
            "configuration": record.get("configuration_group"),
            "future_capability": record.get("potential_use_as_recorded"),
        }
        if subsystem and view["subsystem"].casefold() != subsystem.casefold():
            continue
        if configuration and view["configuration"].casefold() != configuration.casefold():
            continue
        if source_id and view["source_id"] != source_id:
            continue
        if model_use and use != model_use:
            continue
        if query and query.casefold() not in " ".join(str(item) for item in view.values()).casefold():
            continue
        views.append(view)
    return tuple(views)


__all__ = [
    "ProfileInfo", "ResolvedField", "ResolvedManifest", "browse_records",
    "build_vehicle", "list_profiles", "preview_profile",
]
