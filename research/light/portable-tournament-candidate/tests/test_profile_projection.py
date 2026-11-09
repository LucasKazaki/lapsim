"""Synthetic manifest/configuration regressions; no native or car evidence.

These deliberately invented values exercise the public resolved-manifest shape.
No original TREV5 artifact, admitted reference or physical trajectory is used.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
import json
from math import isfinite
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lapsim_light_campaign import fixture
from lapsim_light_campaign.input_contracts import decode, digest, encode
from lapsim_light_campaign import profile_projection


def synthetic_manifest():
    values = {
        "mass_kg": (310., "kg"),
        "chassis.static_front_weight_fraction": (.45, "fraction"),
        "chassis.wheelbase_m": (1.7, "m"),
        "chassis.front_track_width_m": (1.25, "m"),
        "chassis.rear_track_width_m": (1.18, "m"),
        "chassis.cg_height_m": (.29, "m"),
        "chassis.front_axle_height_m": (.23, "m"),
        "chassis.rear_axle_height_m": (.23, "m"),
        "chassis.front_roll_axis_height_m": (.07, "m"),
        "chassis.rear_roll_axis_height_m": (.09, "m"),
        "aero.lift_coefficient": (-3., "dimensionless"),
        "aero.drag_coefficient": (.7, "dimensionless"),
        "aero.frontal_area_m2": (1.1, "m^2"),
        "aero.front_downforce_fraction": (.46, "fraction"),
        "air_density_kgpm3": (1.19, "kg/m^3"),
    }
    selected, inherited = [], []
    model = {"class": "Vehicle", "fields": {}}
    for path, (value, unit) in values.items():
        is_default = path == "air_density_kgpm3" or path.startswith("aero.")
        field = dict(path=path, value=value, unit=unit,
            origin="inherited_model_default" if is_default else "selected_source_profile",
            model_use="supported_metadata_only" if "axle_height" in path else "used_by_this_run",
            parameter_id=None if is_default else "synthetic-" + path,
            source_id=None if is_default else "SYNTHETIC-NOT-CAR-EVIDENCE",
            source_locator=None, artifact_id=None if is_default else "synthetic-artifact",
            evidence_status="SYNTHETIC TEST DATA", conversion=None, caveat="INVENTED UNIT FIXTURE")
        (inherited if is_default else selected).append(field)
        parent = model["fields"]
        names = path.split(".")
        for name in names[:-1]:
            parent = parent.setdefault(name, {"class": name.title(), "fields": {}})["fields"]
        parent[names[-1]] = value
    return dict(profile_id="SYNTHETIC-UNIT-ONLY", profile_name="Synthetic unit fixture",
        profile_schema_version="1", backend="vehicle_model.Vehicle", code_commit=None,
        dirty_worktree=None, registry_dataset_id="SYNTHETIC", registry_sha256="1"*64,
        profile_sha256="2"*64, artifact_sha256={"synthetic-artifact": "3"*64},
        selected_fields=selected, inherited_fields=inherited,
        unused_records=[{"parameter_id": "unused-synthetic", "model_use": "stored_for_future"}],
        limitations=["Synthetic unit values; no car provenance."], model_config=model,
        run_context={"label": "SYNTHETIC NONEXECUTING TEST"})


class PartialProfileTests(unittest.TestCase):
    def build(self, manifest=None, *, raw=None, pin=None):
        raw = encode(synthetic_manifest() if manifest is None else manifest) if raw is None else raw
        return fixture.construct_partial_profile_fixture(fixture.fixture_resource_bytes(),
            resolved_manifest_raw=raw,
            reviewed_resolved_manifest_raw_sha256=sha256(raw).hexdigest() if pin is None else pin,
            reference_length_m=123., reference_geometry_sha256="4"*64)

    def test_profile_changes_actual_typed_mass_and_coupled_geometry(self):
        raw = encode(synthetic_manifest())
        result = fixture.construct_partial_profile_fixture(fixture.fixture_resource_bytes(),
            resolved_manifest_raw=raw, reviewed_resolved_manifest_raw_sha256=sha256(raw).hexdigest(),
            reference_length_m=123., reference_geometry_sha256="4"*64)
        car = result.settings.forces.plant
        self.assertEqual(car.mass_kg, 310.)
        self.assertAlmostEqual(car.cg_to_front_axle_m, 1.7*(1-.45))
        self.assertAlmostEqual(car.cg_to_rear_axle_m, 1.7*.45)
        self.assertAlmostEqual(sum(car.static_normal_loads_n[:2]), 310*car.gravity_mps2*.45)
        self.assertAlmostEqual(sum(car.static_normal_loads_n), 310*car.gravity_mps2)
        self.assertEqual(result.environment.air_density_kgpm3, 1.19)
        self.assertEqual(result.settings.forces.cg_height_m, .29)
        record = decode(result.configuration_json, 128*1024)
        self.assertEqual(record["partial_profile_projection"]["resolved_manifest_json"], raw.decode())

    def test_baseline_bytes_match_frozen_pre_profile_constructor(self):
        # Measured directly from HEAD 9885a2e's unchanged baseline constructor.
        baseline = fixture.construct_standing_fixture(fixture.fixture_resource_bytes(),
            reference_length_m=123., reference_geometry_sha256="4"*64)
        self.assertEqual(baseline.configuration_sha256,
            "d39f13388c29e06814235f0cad9cbd77bb2566e7ba82edf6035034017e8ff3cd")
        self.assertEqual(len(baseline.configuration_json), 4075)
        self.assertNotIn("partial_profile_projection", fixture.validate_standing_fixture(baseline))

    def test_complete_metadata_and_raw_spelling_survive_with_explicit_field_accounting(self):
        manifest = synthetic_manifest()
        raw = (json.dumps(manifest, indent=2) + "\n").encode()
        result = self.build(raw=raw)
        record = fixture.validate_standing_fixture(result)
        payload = record["partial_profile_projection"]
        self.assertEqual(payload["resolved_manifest_raw_sha256"], sha256(raw).hexdigest())
        self.assertEqual(payload["resolved_manifest_json"].encode(), raw)
        self.assertEqual(json.loads(payload["resolved_manifest_json"]), manifest)
        fields = {field["path"]: field for field in payload["field_accounting"]}
        self.assertEqual(fields["air_density_kgpm3"]["status"], "inherited_model_default")
        self.assertEqual(fields["air_density_kgpm3"]["light_use"], "PARTIAL_PROJECTED")
        self.assertIn("UNMAPPED", fields["aero.drag_coefficient"]["light_use"])
        self.assertIn("UNMAPPED", fields["chassis.front_roll_axis_height_m"]["light_use"])
        self.assertEqual(len(fields), len(manifest["selected_fields"] + manifest["inherited_fields"]))
        self.assertFalse(payload["qualification_or_execution_authority"])
        self.assertTrue(any("fresh profile-specific native admission" in item for item in payload["limitations"]))

    def test_every_unmapped_physical_assumption_is_unchanged(self):
        baseline = fixture.construct_standing_fixture(fixture.fixture_resource_bytes(),
            reference_length_m=123., reference_geometry_sha256="4"*64)
        result = self.build()
        before = fixture.validate_standing_fixture(baseline)["values"]
        after = fixture.validate_standing_fixture(result)
        def leaves(value, prefix=""):
            if type(value) is dict and value:
                return {path: leaf for key, child in value.items()
                        for path, leaf in leaves(child, prefix + ("." if prefix else "") + key).items()}
            return {prefix: value}
        old, new = leaves(before), leaves(after["values"])
        expected_changes = {"settings.forces.plant.mass_kg", "settings.forces.plant.cg_to_front_axle_m",
            "settings.forces.plant.cg_to_rear_axle_m", "settings.forces.plant.front_track_m",
            "settings.forces.plant.rear_track_m", "settings.forces.cg_height_m",
            "settings.forces.provenance", "environment.air_density_kgpm3"}
        self.assertEqual({path for path in old if old[path] != new[path]}, expected_changes)
        self.assertEqual(set(after["partial_profile_projection"]["retained_synthetic_baseline_paths"]),
                         set(old) - expected_changes)
        self.assertEqual(result.settings.forces.closed, baseline.settings.forces.closed)
        self.assertEqual(result.settings.forces.open, baseline.settings.forces.open)
        self.assertEqual(result.settings.forces.front_roll_moment_fraction, baseline.settings.forces.front_roll_moment_fraction)
        for name in ("yaw_inertia_kgm2", "wheel_inertia_kgm2", "wheel_radius_m", "tire_mu"):
            self.assertEqual(getattr(result.settings.forces.plant, name), getattr(baseline.settings.forces.plant, name))

    def test_all_inherited_manifest_is_explicitly_partial(self):
        manifest = synthetic_manifest()
        for field in manifest["selected_fields"]:
            field["origin"] = "inherited_model_default"
        manifest["inherited_fields"] += manifest["selected_fields"]
        manifest["selected_fields"] = []
        result = self.build(manifest)
        payload = fixture.validate_standing_fixture(result)["partial_profile_projection"]
        self.assertTrue(all(field["status"] == "inherited_model_default" for field in payload["field_accounting"]))
        self.assertEqual(result.settings.forces.plant.mass_kg, 310.)

    def test_pretty_manifest_size_of_actual_repository_export_is_supported(self):
        # The actual ordinary repository-baseline exporter produced 39,760
        # bytes. Keep this independent of MAX_PROFILE_BYTES so reducing that
        # limit cannot silently reintroduce the cross-package incompatibility.
        manifest = synthetic_manifest()
        manifest["run_context"]["export_size_regression_padding"] = ""
        serialize = lambda: (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
        manifest["run_context"]["export_size_regression_padding"] = "X" * (39_760-len(serialize()))
        raw = serialize()
        self.assertEqual(len(raw), 39_760)
        result = self.build(raw=raw)
        payload = fixture.validate_standing_fixture(result)["partial_profile_projection"]
        self.assertEqual(payload["resolved_manifest_json"].encode("utf-8"), raw)

    def test_nonmapped_yaw_inertia_is_preserved_as_metadata(self):
        manifest = synthetic_manifest()
        field = deepcopy(manifest["inherited_fields"][0])
        field.update(path="yaw_inertia_kgm2", value=9999., unit="kg*m^2")
        manifest["inherited_fields"].append(field)
        manifest["model_config"]["fields"]["yaw_inertia_kgm2"] = 9999.
        result = self.build(manifest)
        self.assertNotEqual(result.settings.forces.plant.yaw_inertia_kgm2, 9999.)
        payload = fixture.validate_standing_fixture(result)["partial_profile_projection"]
        self.assertIn("UNMAPPED", payload["field_accounting"][-1]["light_use"])

    def test_missing_coupled_geometry_or_other_mapped_field_is_refused(self):
        for path in ("chassis.wheelbase_m", "chassis.static_front_weight_fraction", "mass_kg", "air_density_kgpm3",
                     "aero.drag_coefficient", "chassis.front_axle_height_m"):
            manifest = synthetic_manifest()
            for group in ("selected_fields", "inherited_fields"):
                manifest[group] = [field for field in manifest[group] if field["path"] != path]
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "Complete mass/coupled"):
                self.build(manifest)

    def test_rehashed_unit_value_origin_and_use_discrepancies_are_refused(self):
        for key, changed in (("unit", "lb"), ("value", True), ("value", 309.),
            ("origin", "unresolved"), ("model_use", "supported_metadata_only"), ("model_use", "unresolved")):
            manifest = synthetic_manifest()
            manifest["selected_fields"][0][key] = changed
            with self.subTest(key=key, changed=changed), self.assertRaises(ValueError):
                self.build(manifest)
        manifest = synthetic_manifest()
        manifest["model_config"]["fields"]["mass_kg"] = True
        with self.assertRaisesRegex(ValueError, "snapshot"):
            self.build(manifest)

    def test_duplicate_paths_parameter_ids_and_path_conflicts_are_refused(self):
        for mode in ("path", "parameter", "ancestor", "unused"):
            manifest = synthetic_manifest()
            if mode == "path":
                manifest["inherited_fields"].append(deepcopy(manifest["selected_fields"][0]))
            elif mode == "parameter":
                manifest["selected_fields"][1]["parameter_id"] = manifest["selected_fields"][0]["parameter_id"]
            elif mode == "unused":
                manifest["unused_records"][0]["parameter_id"] = manifest["selected_fields"][0]["parameter_id"]
            else:
                manifest["selected_fields"][2]["path"] = "chassis"
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.build(manifest)

    def test_raw_pin_missing_invalid_duplicate_nonfinite_mutable_and_oversized_inputs_refused(self):
        valid = encode(synthetic_manifest())
        for raw in (b'{"profile_id":"a","profile_id":"b"}',
                    valid.replace(b'310.0', b'NaN'), valid.replace(b'310.0', b'1e999'),
                    b'[]', valid+b' trailing', b'x'*(profile_projection.MAX_PROFILE_BYTES+1), bytearray(valid)):
            with self.subTest(raw_type=type(raw)), self.assertRaises(ValueError):
                self.build(raw=raw)
        for pin in ("0"*64, "", False):
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                self.build(raw=valid, pin=pin)

    def test_artifact_pin_and_manifest_strict_types_are_required(self):
        cases = []
        for key, value in (("dirty_worktree", 1), ("artifact_sha256", []), ("run_context", []),
                           ("limitations", "missing list"), ("selected_fields", {}), ("profile_schema_version", 1)):
            manifest = synthetic_manifest()
            manifest[key] = value
            cases.append(manifest)
        manifest = synthetic_manifest()
        del manifest["model_config"]
        cases.append(manifest)
        manifest = synthetic_manifest()
        manifest["artifact_sha256"] = {}
        cases.append(manifest)
        manifest = synthetic_manifest()
        manifest["artifact_sha256"]["synthetic-artifact"] = "not-a-pin"
        cases.append(manifest)
        for manifest in cases:
            with self.subTest(keys=tuple(manifest)), self.assertRaises(ValueError):
                self.build(manifest)

    def test_geometry_larger_than_original_rectangle_is_refused(self):
        for path, value in (("chassis.wheelbase_m", 2.7), ("chassis.front_track_width_m", 1.5),
                            ("chassis.rear_track_width_m", 1.5), ("chassis.static_front_weight_fraction", .8)):
            manifest = synthetic_manifest()
            for field in manifest["selected_fields"]:
                if field["path"] == path:
                    field["value"] = value
            manifest["model_config"]["fields"]["chassis"]["fields"][path.split(".")[-1]] = value
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "reference envelope"):
                self.build(manifest)

    def test_resealed_object_recipe_and_profile_metadata_mismatches_are_refused(self):
        result = self.build()
        for alter in ("object", "value", "accounting", "pin", "family"):
            body = decode(result.configuration_json, 128*1024)
            if alter == "object":
                forged = replace(result, settings=replace(result.settings,
                    forces=replace(result.settings.forces, plant=replace(result.settings.forces.plant, mass_kg=311.))))
            else:
                if alter == "value":
                    body["values"]["settings"]["forces"]["plant"]["mass_kg"] = 311.
                elif alter == "accounting":
                    body["partial_profile_projection"]["field_accounting"][0]["light_use"] = "QUALIFIED"
                elif alter == "pin":
                    body["partial_profile_projection"]["resolved_manifest_raw_sha256"] = "0"*64
                else:
                    body["family"] = fixture.FAMILY
                forged = replace(result, configuration_json=encode(body), configuration_sha256=digest(body))
            with self.subTest(alter=alter), self.assertRaises(ValueError):
                fixture.validate_standing_fixture(forged)

    def test_all_seven_actual_policies_receive_projected_mass_and_geometry_without_stepping(self):
        from lapsim_light_core.planar import PlanarState
        from lapsim_light_core.powered_planar import PoweredState
        from lapsim_light_policies import core_adapter, core_registry, policy_layers
        result = self.build()
        car = result.settings.forces.plant
        # Typed powered state and explicitly static-load observation double only.
        point = PlanarState(u_mps=8., wheel_speeds_rad_s=(8/car.wheel_radius_m,)*4)
        state = PoweredState(point, (0.,)*4, 9_000_000.)
        physical = SimpleNamespace(wheels=tuple(SimpleNamespace(normal_load_n=value)
                                               for value in car.static_normal_loads_n))
        with patch.object(policy_layers, "allocate", wraps=policy_layers.allocate) as allocate:
            for policy in core_registry.IDS:
                case = core_adapter.case_for(policy)
                outcome = core_adapter.allocate_core(policy, state, physical, (.1,.1,0.,0.),
                    100., 0., 0., car, result.actuation, case)
                self.assertTrue(all(isfinite(value) and value >= 0 for value in outcome.proposed))
                self.assertFalse(core_registry.entry(policy)["campaign_eligible"])
            self.assertEqual(allocate.call_count, 7)
            for call in allocate.call_args_list:
                self.assertEqual(call.kwargs["mass_kg"], car.mass_kg)
                self.assertEqual(call.kwargs["wheel_positions_m"], car.wheel_positions_m)
                self.assertEqual(call.kwargs["wheelbase_m"], car.cg_to_front_axle_m+car.cg_to_rear_axle_m)


class ProfileBridgeTests(unittest.TestCase):
    """Actual bridge/configuration code with a synthetic line and binding doubles.

    Initialization is pure state construction. No worker, native observation,
    producer admission, force evaluation, plant stepping or lap occurs here.
    """
    @classmethod
    def setUpClass(cls):
        from test_canonical_frame import BUNDLE, CONES, synthetic_artifact
        from lapsim_light_course import course
        from lapsim_light_campaign.numerical_inputs import raw_reference_inputs
        cls.pin = sha256(b"UNTRUSTED PROFILE BRIDGE UNIT FIXTURE").hexdigest()
        local = course.construct_fsi_course(BUNDLE, CONES)
        raw = encode(synthetic_artifact(local))
        cls.course = course.construct_fsi_course_from_reference(BUNDLE, CONES, raw,
            expected_line_artifact_sha256=sha256(raw).hexdigest())
        cls.reference = raw_reference_inputs(raw, cls.course,
            producer_audit_sha256=cls.pin, reviewed_promotion_sha256=cls.pin)

    def setUp(self):
        from lapsim_light_campaign.numerical_bridge import BRIDGE_FAMILY
        self.source = dict(family=BRIDGE_FAMILY, source_manifest_sha256=self.pin,
            numerical_environment_sha256=self.pin, external_bindings=dict(
                source_observer_sha256=self.pin, residual_regen_rule_sha256=self.pin))
        self.source["sha256"] = digest(self.source)
        self.baseline = fixture.construct_standing_fixture(fixture.fixture_resource_bytes(),
            reference_length_m=self.reference.length_m,
            reference_geometry_sha256=self.reference.provenance["reference_geometry_sha256"])
        raw = encode(synthetic_manifest())
        self.profiled = fixture.construct_partial_profile_fixture(fixture.fixture_resource_bytes(),
            resolved_manifest_raw=raw, reviewed_resolved_manifest_raw_sha256=sha256(raw).hexdigest(),
            reference_length_m=self.reference.length_m,
            reference_geometry_sha256=self.reference.provenance["reference_geometry_sha256"])

    def bridge(self, configured, *, policy=None, identity_overrides=None):
        from lapsim_light_campaign.numerical_bridge import NumericalBridge
        from lapsim_light_campaign.numerical_inputs import NumericalBindings
        from lapsim_light_policies import core_registry
        source = self.source
        class UntrustedObserverDouble:
            implementation_sha256 = self.pin
            def observe_source_identity(self):
                return deepcopy(source)
        class UntrustedResidualDouble:
            implementation_sha256 = self.pin
            def residual_low_speed_regen(self, *args):
                raise AssertionError("No physical evaluation is authorized by this unit double")
        identity = dict(source_sha256=self.source["sha256"], configuration_sha256=configured.configuration_sha256,
            course_bundle_sha256=self.course.bundle_raw_sha256,
            line_artifact_sha256=self.reference.provenance["artifact_sha256"], environment_sha256=self.pin,
            policy_id=core_registry.IDS[0] if policy is None else policy,
            topology_id=core_registry.TOPOLOGY, drive_availability=[True]*4, regen_enabled=False,
            role="development", heldout_used=False)
        identity.update(identity_overrides or {})
        bindings = NumericalBindings(UntrustedObserverDouble(), UntrustedResidualDouble(), self.pin, self.pin)
        return NumericalBridge(fixture=configured, source_course=self.course, reference=self.reference,
            bindings=bindings, expected_identity=identity, reviewed_source_manifest_sha256=self.pin)

    def initialize(self, bridge):
        return bridge.initialize("amz_fssim_fsi_approx", bridge.identity["policy_id"], "one_lap",
                                 expected_source_sha256=self.source["sha256"])

    def test_real_context_binds_complete_profile_and_changes_model_identity(self):
        from lapsim_light_campaign.numerical_bridge import checkpoint
        baseline = self.initialize(self.bridge(self.baseline))
        profiled = self.initialize(self.bridge(self.profiled))
        self.assertEqual(baseline.context["profile"], fixture.FAMILY)
        self.assertNotIn("partial_profile_projection", baseline.context)
        self.assertEqual(profiled.context["profile"], fixture.PARTIAL_PROFILE_FAMILY)
        expected_payload = fixture.validate_standing_fixture(self.profiled)["partial_profile_projection"]
        self.assertEqual(profiled.context["partial_profile_projection"], expected_payload)
        self.assertEqual(profiled.context["configuration_sha256"], self.profiled.configuration_sha256)
        self.assertNotEqual(profiled.state.model_sha256, baseline.state.model_sha256)
        self.assertNotEqual(profiled.context_sha256, baseline.context_sha256)
        self.assertLess(len(encode(checkpoint(profiled))), 256*1024)
        self.assertEqual(profiled.state.thermal.light.powered.integration_trials, 0)
        self.assertEqual(profiled.state.thermal.light.powered.pack_energy_j, 9_000_000.)
        self.assertEqual(profiled.state.thermal.thermal.temperature_c, 70.)

    def test_context_and_checkpoint_fit_with_complete_near_budget_manifest(self):
        from lapsim_light_campaign.numerical_bridge import checkpoint
        manifest = synthetic_manifest()
        manifest["run_context"]["padding"] = "X" * (profile_projection.MAX_PROFILE_BYTES-len(encode(manifest))-32)
        raw = encode(manifest)
        self.assertLessEqual(len(raw), profile_projection.MAX_PROFILE_BYTES)
        configured = fixture.construct_partial_profile_fixture(fixture.fixture_resource_bytes(),
            resolved_manifest_raw=raw, reviewed_resolved_manifest_raw_sha256=sha256(raw).hexdigest(),
            reference_length_m=self.reference.length_m,
            reference_geometry_sha256=self.reference.provenance["reference_geometry_sha256"])
        session = self.initialize(self.bridge(configured))
        self.assertEqual(json.loads(session.context["partial_profile_projection"]["resolved_manifest_json"]), manifest)
        self.assertLess(len(configured.configuration_json), profile_projection.MAX_PROFILE_FIXTURE_BYTES)
        self.assertLess(len(encode(session.context)), profile_projection.MAX_PROFILE_CONTEXT_BYTES)
        self.assertLess(len(encode(checkpoint(session))), 256*1024)

    def test_bridge_refuses_request_configuration_object_and_resealed_provenance_changes(self):
        with self.assertRaisesRegex(ValueError, "input identity"):
            self.bridge(self.profiled, identity_overrides={"configuration_sha256": self.baseline.configuration_sha256})
        forged = replace(self.profiled, environment=replace(self.profiled.environment, air_density_kgpm3=1.2))
        with self.assertRaisesRegex(ValueError, "objects differ"):
            self.bridge(forged)
        body = decode(self.profiled.configuration_json, 128*1024)
        body["partial_profile_projection"]["limitations"] = []
        forged = replace(self.profiled, configuration_json=encode(body), configuration_sha256=digest(body))
        with self.assertRaisesRegex(ValueError, "recipe"):
            self.bridge(forged)

    def test_old_checkpoint_cannot_be_relabelled_as_new_profile(self):
        from lapsim_light_campaign.numerical_bridge import checkpoint
        baseline = self.initialize(self.bridge(self.baseline))
        envelope = checkpoint(baseline)
        profiled_bridge = self.bridge(self.profiled)
        with self.assertRaisesRegex(ValueError, "Checkpoint mission"):
            profiled_bridge.resume(envelope, expected_checkpoint_sha256=envelope["checkpoint_sha256"],
                expected_source_sha256=self.source["sha256"])
        # Rehashing a label/configuration change cannot update the old context/model.
        body = envelope["checkpoint"]
        body["context"]["profile"] = fixture.PARTIAL_PROFILE_FAMILY
        body["context"]["configuration_sha256"] = self.profiled.configuration_sha256
        body["context_sha256"] = digest(body["context"])
        envelope["checkpoint_sha256"] = digest(body)
        with self.assertRaisesRegex(ValueError, "Checkpoint mission"):
            profiled_bridge.resume(envelope, expected_checkpoint_sha256=envelope["checkpoint_sha256"],
                expected_source_sha256=self.source["sha256"])

    def test_seven_policy_matched_field_requires_same_complete_profile_context(self):
        from lapsim_light_campaign.numerical_bridge import checkpoint
        from lapsim_light_campaign.tournament_plan import freeze_tournament
        from lapsim_light_policies import core_registry
        origins = {}
        for policy in core_registry.IDS:
            bridge = self.bridge(self.profiled, policy=policy)
            origins[policy] = dict(identity=bridge.identity, origin=checkpoint(self.initialize(bridge)))
        raw = encode(origins)
        plan = freeze_tournament(raw, expected_origins_raw_sha256=sha256(raw).hexdigest())
        self.assertEqual(len(plan["plan"]["cells"]), 7)
        altered = origins[core_registry.IDS[-1]]["origin"]
        altered["checkpoint"]["context"]["partial_profile_projection"]["limitations"].append("PER-POLICY CHANGE")
        altered["checkpoint"]["context_sha256"] = digest(altered["checkpoint"]["context"])
        altered["checkpoint_sha256"] = digest(altered["checkpoint"])
        raw = encode(origins)
        with self.assertRaisesRegex(ValueError, "matched|differ|identical|same"):
            freeze_tournament(raw, expected_origins_raw_sha256=sha256(raw).hexdigest())


if __name__ == "__main__":
    unittest.main()
