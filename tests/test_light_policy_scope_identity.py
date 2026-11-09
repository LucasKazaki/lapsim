"""Standard-library source-identity checks; no model, GUI, guard or lease runs."""
from hashlib import sha256
import builtins
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1] / "research/light/portable-tournament-candidate"
DESCRIPTOR = Path(__file__).resolve().parents[1] / "src/lapsim/experiments/light_policy_scope.py"
PUBLIC_SNAPSHOT = "a84990be7bf121707abbd27eb4f06cf2b442131b"
PUBLIC_MANIFEST = "bb73c5513265748713e49bfabbc82466d9eb65d9513956b9cef120a3143ef847"


def load_descriptor():
    """Exercise the actual pure descriptor without importing its application package."""
    original_import = builtins.__import__
    blocked = ("lapsim", "lapsim_light_", "numpy", "scipy", "matplotlib")
    def guarded_import(name, *args, **kwargs):
        if name.startswith(blocked):
            raise AssertionError("Descriptor imported a model/application dependency: " + name)
        return original_import(name, *args, **kwargs)
    spec = importlib.util.spec_from_file_location("pure_light_policy_scope_under_test", DESCRIPTOR)
    module = importlib.util.module_from_spec(spec)
    with patch("builtins.__import__", side_effect=guarded_import):
        spec.loader.exec_module(module)
        module.portable_policy_scope()
    return module


class PortableSourceIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.descriptor = load_descriptor()

    def test_public_snapshot_matches_manifest_contract_and_all_declared_files(self):
        audit = self.descriptor.portable_policy_scope()
        raw = (ROOT / "SOURCE_MANIFEST.json").read_bytes()
        self.assertEqual(audit["source_commit"], PUBLIC_SNAPSHOT)
        self.assertEqual(audit["source_manifest_sha256"], PUBLIC_MANIFEST)
        self.assertEqual(sha256(raw).hexdigest(), PUBLIC_MANIFEST)
        self.assertEqual(audit["distribution_version"], "0.0.0.dev38")
        contract = json.loads((ROOT / "INSTALL_CONTRACT.json").read_bytes())
        self.assertEqual(audit["distribution_version"], contract["project"]["version"])
        rows = {row["path"]: row["sha256"] for row in json.loads(raw)["files"]}
        self.assertEqual(len(self.descriptor.SOURCE_PINS), 14)
        for path, pin in self.descriptor.SOURCE_PINS.items():
            with self.subTest(path=path):
                self.assertEqual(pin, rows[path])
                self.assertEqual(sha256((ROOT / path).read_bytes()).hexdigest(), pin)

    def test_current_and_historical_evidence_are_distinct_and_not_admission(self):
        audit = self.descriptor.portable_policy_scope()
        evidence = audit["bounded_component_tests"]
        self.assertEqual(evidence["source_and_installed_cases"], 273)
        self.assertEqual(evidence["evidence_origin_commit"],
                         "6db5c9df28166bb45350be687858e35be0f7f0fd")
        self.assertFalse(evidence["new_native_execution_performed"])
        self.assertFalse(evidence["course_or_native_qualification"])
        self.assertFalse(evidence["campaign_eligibility_promoted"])
        self.assertEqual(audit["historical_dev28_component_evidence"]["source_and_installed_cases"], 110)
        self.assertEqual(audit["source_course_preparation"]["evidence_origin_distribution"], "0.0.0.dev28")
        components = audit["current_source_components"]
        self.assertTrue(components["fsg_development_consumer"])
        self.assertTrue(components["fsg_checkpoint_and_short_replay_worker"])
        self.assertFalse(components["native_worker_or_Start_registered"])
        self.assertFalse(components["full_event_continuation_qualified"])

    def test_returned_data_is_independent_and_does_not_import_portable_runtime(self):
        before = set(sys.modules)
        module = load_descriptor()
        audit = module.portable_policy_scope()
        self.assertEqual(len(audit["policies"]), 7)
        self.assertTrue(all(not p["implemented_in_this_suite"]
                            and not p["source_declared_campaign_eligible"]
                            and p["source_declared_native_qualification"] == "UNRUN"
                            for p in audit["policies"]))
        audit["policies"][0]["source_declared_campaign_eligible"] = True
        audit["source_course_preparation"]["fsg_numerical_path_enabled"] = True
        self.assertFalse(module.portable_policy_scope()["policies"][0]["source_declared_campaign_eligible"])
        self.assertFalse(module.portable_policy_scope()["source_course_preparation"]["fsg_numerical_path_enabled"])
        self.assertFalse(module.portable_policy_scope()["qualification_or_execution_authority"])
        self.assertFalse(any(name.startswith(("lapsim_light_core", "lapsim_light_campaign",
                                             "lapsim_light_course", "lapsim_light_guidance"))
                             for name in set(sys.modules) - before))
        with self.assertRaises(TypeError):
            module.SOURCE_PINS["unreviewed"] = "0" * 64


if __name__ == "__main__":
    unittest.main(verbosity=2)
