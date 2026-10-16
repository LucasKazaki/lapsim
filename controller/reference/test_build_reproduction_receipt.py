import copy
import unittest

from build_reproduction_receipt import (
    BuildReceiptError,
    compare_reproductions,
    validate_receipt,
)

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def fixture():
    return {
        "schema": "enme408-build-reproduction-receipt/v1",
        "target_car": "2027-28",
        "evidence_request_sha256": "1" * 64,
        "source": {
            "expected_commit_sha": "a" * 40,
            "observed_commit_sha": "a" * 40,
            "head_verified_as_commit": True,
            "status_porcelain_v1": "",
            "submodule_status_recursive": "",
        },
        "build": {
            "declared_working_directory": "firmware",
            "observed_working_directory": "firmware",
            "declared_command": "example-build",
            "executed_command": "example-build",
            "exit_code": 0,
            "stdout_sha256": EMPTY_SHA256,
            "stderr_sha256": EMPTY_SHA256,
        },
        "toolchain": {
            "executable": "example-compiler",
            "version_text": "example-compiler 0.0",
        },
        "artifacts": [{"path": "build/firmware.bin", "sha256": "2" * 64, "bytes": 10}],
        "scope": {
            "hardware_accessed": False,
            "flash_attempted": False,
            "vehicle_actuation_attempted": False,
        },
    }


class BuildReceiptTests(unittest.TestCase):
    def test_complete_fixture(self):
        self.assertTrue(validate_receipt(fixture()).evidence_complete)

    def test_exact_commit_required(self):
        x = fixture()
        x["source"]["expected_commit_sha"] = "main"
        with self.assertRaises(BuildReceiptError):
            validate_receipt(x)

    def test_dirty_source_blocks(self):
        x = fixture()
        x["source"]["status_porcelain_v1"] = " M src/control.c\n"
        self.assertIn("worktree_or_index_not_clean", validate_receipt(x).blockers)

    def test_submodule_mismatch_blocks(self):
        x = fixture()
        x["source"]["submodule_status_recursive"] = "+" + "a" * 40 + " lib/example\n"
        self.assertIn("submodule_state_not_exact", validate_receipt(x).blockers)

    def test_command_mismatch_blocks(self):
        x = fixture()
        x["build"]["executed_command"] = "example-build-altered"
        self.assertIn("build_command_mismatch", validate_receipt(x).blockers)

    def test_missing_artifact_blocks(self):
        x = fixture()
        x["artifacts"] = []
        self.assertIn("no_build_artifacts", validate_receipt(x).blockers)

    def test_scope_is_observational_only(self):
        x = fixture()
        x["scope"]["hardware_accessed"] = True
        self.assertIn("hardware_access_was_reported", validate_receipt(x).blockers)

    def test_repeat_artifact_drift_is_preserved(self):
        second = copy.deepcopy(fixture())
        second["artifacts"][0]["sha256"] = "3" * 64
        result = compare_reproductions(fixture(), second)
        self.assertTrue(result.comparable_inputs)
        self.assertFalse(result.byte_identical)
        self.assertEqual(result.differences, ("artifact_changed:build/firmware.bin",))


if __name__ == "__main__":
    unittest.main()
