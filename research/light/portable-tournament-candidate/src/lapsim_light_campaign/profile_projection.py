"""Bounded partial projection of explicit ordinary resolved-manifest JSON.

Only stdlib/local contracts are used. Pins prove byte consistency, never source
authenticity, calibration, reference admission or permission to execute a worker.
"""
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
import re

from .input_contracts import decode, encode, exact, is_sha256, require

FAMILY = "lapsim.portable-light-partial-profile-projection.v1"
MAX_PROFILE_BYTES = 64 * 1024
MAX_PROFILE_FIXTURE_BYTES = 96 * 1024
MAX_PROFILE_CONTEXT_BYTES = 128 * 1024

_UNITS = {
    "mass_kg": "kg", "chassis.static_front_weight_fraction": "fraction",
    "chassis.wheelbase_m": "m", "chassis.front_track_width_m": "m",
    "chassis.rear_track_width_m": "m", "chassis.cg_height_m": "m",
    "chassis.front_axle_height_m": "m", "chassis.rear_axle_height_m": "m",
    "chassis.front_roll_axis_height_m": "m", "chassis.rear_roll_axis_height_m": "m",
    "aero.lift_coefficient": "dimensionless", "aero.drag_coefficient": "dimensionless",
    "aero.frontal_area_m2": "m^2", "aero.front_downforce_fraction": "fraction",
    "air_density_kgpm3": "kg/m^3",
}
_TARGETS = {
    "mass_kg": ("settings.forces.plant.mass_kg",),
    "chassis.wheelbase_m": ("settings.forces.plant.cg_to_front_axle_m", "settings.forces.plant.cg_to_rear_axle_m"),
    "chassis.static_front_weight_fraction": ("settings.forces.plant.cg_to_front_axle_m", "settings.forces.plant.cg_to_rear_axle_m"),
    "chassis.front_track_width_m": ("settings.forces.plant.front_track_m",),
    "chassis.rear_track_width_m": ("settings.forces.plant.rear_track_m",),
    "chassis.cg_height_m": ("settings.forces.cg_height_m",),
    "air_density_kgpm3": ("environment.air_density_kgpm3",),
}
_MANIFEST_KEYS = {"profile_id", "profile_name", "profile_schema_version", "backend", "code_commit",
    "dirty_worktree", "registry_dataset_id", "registry_sha256", "profile_sha256", "artifact_sha256",
    "selected_fields", "inherited_fields", "unused_records", "limitations", "model_config", "run_context"}
_FIELD_KEYS = {"path", "value", "unit", "origin", "model_use", "parameter_id", "source_id",
    "source_locator", "artifact_id", "evidence_status", "conversion", "caveat"}
_PATH = re.compile(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*\Z")

LIMITATIONS = (
    "PARTIAL mass/geometry/density projection only; not all car data or native qualification.",
    "Reviewed raw SHA establishes consistency only; source authenticity and current admission remain native responsibilities.",
    "Inherited ordinary model defaults retain their declared inherited_model_default labels; they are not source-car evidence.",
    "Closed ordinary aero is unmapped: light requires both closed/open DRS states. Both synthetic aero states and automatic DRS policy remain unchanged.",
    "Roll-axis heights and TLLTD are not equivalent to light front_roll_moment_fraction; synthetic roll-moment split remains unchanged.",
    "Yaw/wheel inertia, wheel radius, tire stiffness/friction, motor/pack/brake maps, thermal model, topology and controls retain synthetic baseline assumptions.",
    "Standing energy 9000000 J, tire temperature 70 C, zero initial motion and load memory retain synthetic baseline assumptions.",
    "Reference recipe remains synthetic: wheelbase 1.6 m, steering limit 0.4 rad, width 1.4 m and longitudinal extents +/-1 m; it is not requalified for this profile.",
    "Unchanged producer line, DRS, brakes, power, tires, yaw inertia, body/tracking assumptions require fresh profile-specific native admission; this is not an as-built car claim.",
    "Only wheel-center compatibility with the existing declared rectangle is checked. True tire/body envelope and continuous swept clearance remain unknown.",
    "Parsing a resolved manifest does not independently verify original TREV5 source artifacts or calibrate this projection; original-data compatibility requires separate evidence.",
)


def _text(value, name, *, optional=False):
    require((optional and value is None) or (type(value) is str and 0 < len(value) <= 8192),
            "Explicit bounded string required: " + name)


def _snapshot_value(snapshot, path):
    node = snapshot
    for name in path.split("."):
        exact(node, {"class", "fields"}, "model_config object on " + path)
        _text(node["class"], "model_config class")
        require(type(node["fields"]) is dict and name in node["fields"],
                "Resolved path missing from model_config: " + path)
        node = node["fields"][name]
    return node


def _unmapped_reason(path):
    if path.startswith("aero."):
        return "UNMAPPED: ordinary closed aero cannot supply both light DRS states"
    if "roll" in path.lower() or "tlltd" in path.lower():
        return "UNMAPPED: no equivalence to light roll-moment fraction"
    return "UNMAPPED: no reviewed light semantic mapping; retained as declared metadata"


@dataclass(frozen=True, slots=True)
class PartialProfileProjection:
    """Immutable validated declaration; no source-car or execution authority."""
    resolved_manifest_raw: bytes
    reviewed_raw_sha256: str
    values_json: bytes
    accounting_json: bytes

    def values(self):
        return decode(self.values_json, MAX_PROFILE_BYTES)

    def payload(self):
        return {"family": FAMILY, "resolved_manifest_raw_sha256": self.reviewed_raw_sha256,
                "resolved_manifest_json": self.resolved_manifest_raw.decode("utf-8"),
                "field_accounting": decode(self.accounting_json, MAX_PROFILE_BYTES),
                "limitations": list(LIMITATIONS), "qualification_or_execution_authority": False}


def resolve_partial_profile(resolved_manifest_raw, *, reviewed_resolved_manifest_raw_sha256):
    """Validate complete to_dict v1 shape, metadata and final snapshot consistency."""
    require(type(resolved_manifest_raw) is bytes and 0 < len(resolved_manifest_raw) <= MAX_PROFILE_BYTES and
            is_sha256(reviewed_resolved_manifest_raw_sha256) and
            sha256(resolved_manifest_raw).hexdigest() == reviewed_resolved_manifest_raw_sha256,
            "Bounded immutable complete resolved manifest and explicit reviewed raw SHA256 required")
    manifest = decode(resolved_manifest_raw, MAX_PROFILE_BYTES)
    exact(manifest, _MANIFEST_KEYS, "resolved manifest v1")
    require(manifest["profile_schema_version"] == "1" and manifest["backend"] == "vehicle_model.Vehicle",
            "Only explicit ordinary resolved-manifest v1 backend is supported")
    for name in ("profile_id", "profile_name"):
        _text(manifest[name], name)
    for name in ("code_commit", "registry_dataset_id"):
        _text(manifest[name], name, optional=True)
    require(manifest["dirty_worktree"] is None or type(manifest["dirty_worktree"]) is bool,
            "dirty_worktree must be bool or null")
    for name in ("registry_sha256", "profile_sha256"):
        require(manifest[name] is None or is_sha256(manifest[name]), "Invalid declared " + name)
    require(type(manifest["artifact_sha256"]) is dict, "Explicit artifact pin map required")
    for artifact, pin in manifest["artifact_sha256"].items():
        _text(artifact, "artifact_id")
        require(is_sha256(pin), "Invalid declared artifact SHA256")
    require(type(manifest["limitations"]) is list and type(manifest["unused_records"]) is list and
            (manifest["run_context"] is None or type(manifest["run_context"]) is dict),
            "Explicit limitations, unused records and optional run context required")
    for limitation in manifest["limitations"]:
        _text(limitation, "limitation")
    exact(manifest["model_config"], {"class", "fields"}, "model_config root")
    require(manifest["model_config"]["class"] == "Vehicle" and
            type(manifest["model_config"]["fields"]) is dict, "Vehicle constructor snapshot required")
    seen, ids, values, accounting = set(), set(), {}, []
    for group in ("selected_fields", "inherited_fields"):
        require(type(manifest[group]) is list and len(manifest[group]) <= 128,
                "Bounded explicit resolved-field lists required")
        for field in manifest[group]:
            exact(field, _FIELD_KEYS, "resolved field")
            path = field["path"]
            require(type(path) is str and len(path) <= 256 and _PATH.fullmatch(path) is not None,
                    "Explicit dotted model path required")
            require(not any(path == other or path.startswith(other + ".") or other.startswith(path + ".")
                            for other in seen), "Duplicate or conflicting resolved path: " + path)
            seen.add(path)
            require(type(field["value"]) in (int, float) and isfinite(field["value"]),
                    "Finite nonboolean resolved value required: " + path)
            for name in ("unit", "origin", "model_use"):
                _text(field[name], name)
            for name in _FIELD_KEYS - {"path", "value", "unit", "origin", "model_use"}:
                _text(field[name], name, optional=True)
            require((field["origin"] == "inherited_model_default") == (group == "inherited_fields"),
                    "Selected/inherited origin differs: " + path)
            require(field["origin"] in ("inherited_model_default", "selected_source_profile", "prius_benchmark_preset"),
                    "Unsupported resolved-manifest v1 origin: " + path)
            require(path not in _UNITS or field["unit"] == _UNITS[path], "Unit mismatch: " + path)
            if path in _UNITS:
                expected_use = "supported_metadata_only" if path in (
                    "chassis.front_axle_height_m", "chassis.rear_axle_height_m") else "used_by_this_run"
                require(field["model_use"] == expected_use,
                        "Resolved-manifest v1 model_use differs: " + path)
            snapshot = _snapshot_value(manifest["model_config"], path)
            require(type(snapshot) in (int, float) and isfinite(snapshot) and snapshot == field["value"],
                    "Resolved value differs from model_config snapshot: " + path)
            parameter = field["parameter_id"]
            require(parameter is None or parameter not in ids, "Duplicate resolved parameter_id")
            if parameter is not None:
                ids.add(parameter)
            artifact = field["artifact_id"]
            require(artifact is None or artifact in manifest["artifact_sha256"],
                    "Resolved artifact lacks declared SHA256: " + path)
            if field["origin"] == "selected_source_profile":
                require(parameter is not None and field["source_id"] is not None and artifact is not None,
                        "Selected source profile requires parameter/source/artifact pins: " + path)
            if path in _TARGETS:
                values[path] = field["value"]
            accounting.append({"path": path, "origin": field["origin"],
                "status": "inherited_model_default" if group == "inherited_fields" else "selected_declared_value",
                "light_use": "PARTIAL_PROJECTED" if path in _TARGETS else _unmapped_reason(path),
                "target_paths": list(_TARGETS.get(path, ()))})
    require(_UNITS.keys() <= seen, "Complete mass/coupled geometry/density and unmapped v1 fields required")
    for record in manifest["unused_records"]:
        exact(record, {"parameter_id", "model_use"}, "unused record")
        _text(record["parameter_id"], "unused parameter_id")
        _text(record["model_use"], "unused model_use")
        require(record["parameter_id"] not in ids, "Duplicate selected/unused parameter_id")
        ids.add(record["parameter_id"])
    require(all(value > 0 for path, value in values.items() if path != "chassis.static_front_weight_fraction") and
            0 < values["chassis.static_front_weight_fraction"] < 1,
            "Positive mass/geometry/density and interior front fraction required")
    length, front = values["chassis.wheelbase_m"], values["chassis.static_front_weight_fraction"]
    require(length*(1-front) <= 1. and length*front <= 1. and
            values["chassis.front_track_width_m"] <= 1.4 and values["chassis.rear_track_width_m"] <= 1.4,
            "Profile wheel centers exceed existing +/-1m by 1.4m reference envelope")
    return PartialProfileProjection(resolved_manifest_raw, reviewed_resolved_manifest_raw_sha256,
                                    encode(values), encode(accounting))
