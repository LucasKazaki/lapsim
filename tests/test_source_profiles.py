"""Synthetic checks for evidence preservation and strict profile promotion."""

from copy import deepcopy
from hashlib import sha256
import json
from math import isclose

import pytest

from lapsim.profiles import (
    EngineeringRegistry, build_vehicle, browse_records, import_intake,
    list_profiles, load_intake,
)
from vehicle_model import Vehicle


def _synthetic_bundle(tmp_path):
    registry_dir = tmp_path / "data" / "registry"
    profile_dir = tmp_path / "data" / "profiles"
    registry_dir.mkdir(parents=True)
    profile_dir.mkdir()
    binding = {
        "parameter_id": "SYN-MASS", "target_path_relative_to_vehicle": "mass_kg",
        "value": 45.359237, "unit": "kg", "source_id": "SYN-SOURCE",
        "source_artifact_id": "SYN-ART", "source_locator": "Sheet!A1",
        "evidence_status": "synthetic fixture",
        "conversion": {
            "expression": "source_value * conversion_factor",
            "source_value_text": "100", "conversion_factor": "0.45359237",
            "result_decimal": "45.359237", "interpretation": "lb interpreted as pound mass",
        },
    }
    records = [
        {
            "parameter_id": "SYN-MASS", "name": "Synthetic mass",
            "subsystem": "Vehicle", "configuration_group": "synthetic",
            "source_value": {"kind": "scalar", "value": 100, "text": "100"},
            "original_unit_text": "lb", "evidence_status": "synthetic",
            "source": {"source_id": "SYN-SOURCE", "associated_uploaded_artifact_id": "SYN-ART"},
            "candidate_binding": binding, "caveats": "testing only",
            "future_key": {"kept": [0, None]},
        },
        {
            "parameter_id": "SYN-UNKNOWN", "name": "Unknown sensor",
            "subsystem": "Sensors", "configuration_group": "synthetic",
            "source_value": {"kind": "unknown", "value": None, "text": "unknown"},
            "original_unit_text": None, "evidence_status": "unknown",
            "source": {"source_id": "SYN-SOURCE"}, "candidate_binding": None,
        },
        {
            "parameter_id": "SYN-ZERO", "name": "Known zero",
            "subsystem": "Sensors", "configuration_group": "synthetic",
            "source_value": {"kind": "scalar", "value": 0, "text": "0"},
            "original_unit_text": "count", "evidence_status": "synthetic",
            "source": {"source_id": "SYN-SOURCE"}, "candidate_binding": None,
        },
    ]
    payload = {
        "schema_version": "1", "dataset_id": "synthetic_fixture",
        "record_count": len(records), "parameters": records,
        "source_records": [{"source_id": "SYN-SOURCE", "future_source_field": "preserved"}],
        "open_questions": [{"question_id": "SYN-Q", "source_id": "SYN-SOURCE"}],
        "unrecognized_top_level": {"revision": 0},
    }
    spec = {
        "schema_version": "1", "kind": "implementation_profile_specification",
        "auto_load": False, "profile_id": "trev5_working_geometry",
        "bindings": [binding], "required_for_physics_overlay": ["SYN-MASS"],
    }
    (registry_dir / "engineering_registry.json").write_text(json.dumps(payload), encoding="utf-8")
    artifact_path = tmp_path / "data" / "raw" / "synthetic.bin"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"synthetic evidence")
    (registry_dir / "artifacts.json").write_text(json.dumps({
        "artifacts": [{
            "artifact_id": "SYN-ART", "logical_source_id": "SYN-SOURCE",
            "bundle_path": "data/raw/synthetic.bin",
            "sha256": sha256(artifact_path.read_bytes()).hexdigest(),
        }]
    }), encoding="utf-8")
    (profile_dir / "trev5_working_geometry.json").write_text(json.dumps(spec), encoding="utf-8")
    manifest_files = []
    for path in sorted((tmp_path / "data").rglob("*")):
        if path.is_file():
            manifest_files.append({
                "path": path.relative_to(tmp_path).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path.read_bytes()).hexdigest(),
            })
    (tmp_path / "manifest.json").write_text(json.dumps({"files": manifest_files}), encoding="utf-8")
    return tmp_path


def test_baseline_profile_keeps_model_defaults(tmp_path):
    ids = {item.profile_id for item in list_profiles(tmp_path)}
    assert ids == {"repository_baseline", "prius_2026_le"}
    vehicle, manifest = build_vehicle("repository_baseline", tmp_path)
    assert vehicle.mass_kg == Vehicle().mass_kg
    assert manifest.selected_fields == ()
    assert manifest.to_dict()["model_config"]["fields"]["mass_kg"] == vehicle.mass_kg


def test_prius_manifest_separates_published_specs_from_estimates(tmp_path):
    vehicle, manifest = build_vehicle("prius_2026_le", tmp_path)
    selected = {item.path: item for item in manifest.selected_fields}
    inherited = {item.path: item for item in manifest.inherited_fields}
    assert selected["mass_kg"].value == vehicle.mass_kg
    assert selected["mass_kg"].origin == "prius_benchmark_preset"
    assert selected["mass_kg"].evidence_status == "published Toyota specification"
    assert selected["chassis.wheelbase_m"].evidence_status == "published Toyota specification"
    assert selected["aero.drag_coefficient"].evidence_status == "engineering estimate"
    assert selected["aero.frontal_area_m2"].evidence_status == "engineering estimate"
    assert "mass_kg" not in inherited
    assert "chassis.wheelbase_m" not in inherited
    assert inherited["air_density_kgpm3"].origin == "inherited_model_default"


def test_registry_round_trip_preserves_unknowns_and_zero(tmp_path):
    bundle = _synthetic_bundle(tmp_path / "bundle")
    registry = load_intake(bundle)
    destination = tmp_path / "snapshot.json"
    registry.save(destination)
    restored = EngineeringRegistry.load_snapshot(destination)
    assert restored.snapshot() == registry.snapshot()
    assert restored.parameters[0]["future_key"] == {"kept": [0, None]}
    views = browse_records(bundle, profile_id="trev5_working_geometry")
    assert next(item for item in views if item["parameter_id"] == "SYN-ZERO")["value"] == 0
    assert next(item for item in views if item["parameter_id"] == "SYN-UNKNOWN")["value"] is None
    assert next(item for item in views if item["parameter_id"] == "SYN-UNKNOWN")["model_use"] == "unresolved"


def test_private_import_is_idempotent_and_preserves_original_bundle(tmp_path):
    bundle = _synthetic_bundle(tmp_path / "bundle")
    store = tmp_path / "private_store"
    first = import_intake(bundle, store)
    second = import_intake(bundle, store)
    assert first == second
    assert len(load_intake(first, verify_artifacts=True).parameters) == 3
    assert (first / "data" / "raw" / "synthetic.bin").read_bytes() == b"synthetic evidence"


def test_synthetic_overlay_is_fresh_and_source_labeled(tmp_path):
    bundle = _synthetic_bundle(tmp_path / "bundle")
    first, manifest = build_vehicle("trev5_working_geometry", bundle)
    second, _ = build_vehicle("trev5_working_geometry", bundle)
    assert isclose(first.mass_kg, 100 * 0.45359237)
    assert manifest.selected_fields[0].source_id == "SYN-SOURCE"
    assert manifest.selected_fields[0].model_use == "used_by_this_run"
    assert Vehicle().mass_kg != first.mass_kg
    first.mass_kg = 60
    assert second.mass_kg != first.mass_kg
    frozen = manifest.with_run_context(distance_m=10, random_seed=None)
    frozen_dict = frozen.to_dict()
    frozen_dict["run_context"]["distance_m"] = 99
    assert frozen.to_dict()["run_context"]["distance_m"] == 10


@pytest.mark.parametrize("change", [
    {"target_path_relative_to_vehicle": "battery.secret_limit_w"},
    {"unit": "N"},
    {"value": float("nan")},
    {"value": 0.0},
])
def test_bad_solver_binding_fails_before_application(tmp_path, change):
    bundle = _synthetic_bundle(tmp_path / "bundle")
    path = bundle / "data" / "profiles" / "trev5_working_geometry.json"
    spec = json.loads(path.read_text(encoding="utf-8"))
    spec["bindings"][0].update(change)
    path.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError):
        build_vehicle("trev5_working_geometry", bundle)
    assert Vehicle().mass_kg > 0


def test_aero_source_area_coefficients_are_atomic(tmp_path):
    bundle = _synthetic_bundle(tmp_path / "bundle")
    path = bundle / "data" / "profiles" / "trev5_working_geometry.json"
    spec = json.loads(path.read_text(encoding="utf-8"))
    added = deepcopy(spec["bindings"][0])
    added.update({
        "parameter_id": "SYN-AREA", "target_path_relative_to_vehicle": "aero.frontal_area_m2",
        "value": 2.0, "unit": "m^2",
        "conversion": {
            "expression": "source_value * conversion_factor", "source_value_text": "2",
            "conversion_factor": "1", "result_decimal": "2", "interpretation": "m2",
        },
    })
    registry_path = bundle / "data" / "registry" / "engineering_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    record = deepcopy(registry["parameters"][0])
    record.update({
        "parameter_id": "SYN-AREA", "source_value": {"kind": "scalar", "value": 2, "text": "2"},
        "original_unit_text": "m^2", "candidate_binding": added,
    })
    registry["parameters"].append(record)
    registry["record_count"] += 1
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    spec["bindings"].append(added)
    path.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="reference area"):
        build_vehicle("trev5_working_geometry", bundle)
