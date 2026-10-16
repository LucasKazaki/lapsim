"""Software-only annex guards; every subprocess launch is forbidden here."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import guard_cortex_m4_objects as annex


class GuardObjectAnnexTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="guard-annex-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        patch = mock.patch.object(annex.subprocess, "run", side_effect=AssertionError("no executable calls in software guard tests"))
        self.launch = patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.launch.assert_not_called)

    def test_frozen_cohort_denominator_and_base(self):
        plan = annex.load_protocol()
        self.assertEqual(plan["base_pr"], 74)
        self.assertEqual(plan["matrix"]["planned_objects"], 4)
        self.assertEqual(plan["matrix"]["planned_commands"], 26)
        self.assertEqual(set(annex.source_facts(annex.REFERENCE / "native", plan)),
                         {"torque_guard.c", "torque_guard.h", "torque_contract.h"})

    def test_changed_protocol_is_rejected(self):
        changed = self.root / "changed.json"
        changed.write_bytes(annex.PROTOCOL.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "frozen annex protocol"):
            annex.load_protocol(changed)

    def test_changed_source_and_wrong_cohort_are_rejected(self):
        plan = annex.load_protocol()
        for name in annex.SOURCES: shutil.copyfile(annex.REFERENCE / "native" / name, self.root / name)
        (self.root / "torque_guard.c").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "frozen annex source"):
            annex.source_facts(self.root, plan)
        plan["sources"]["torque_clock.c"] = {}
        with self.assertRaisesRegex(ValueError, "unexpected annex sources"):
            annex.source_facts(self.root, plan)

    def test_exact_flag_order_and_unit_are_enforced(self):
        flags = annex.load_protocol()["compile_common_flags"]
        variants = [flags[:i] + flags[i + 1:] for i in range(len(flags))]
        for i in range(len(flags) - 1):
            reordered = list(flags)
            reordered[i], reordered[i + 1] = reordered[i + 1], reordered[i]
            variants.append(reordered)
        variants += [flags + [extra] for extra in ("-ffast-math", "-Ofast", "-shared", "--config=Omax.cfg")]
        for changed in variants:
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "exact frozen"):
                annex.compile_args(Path("clang.exe"), changed, "hard", "torque_guard", self.root / "bad.o")
        for abi, unit in (("soft", "torque_guard"), ("hard", "torque_contract"), ("hard", "../../other")):
            with self.subTest(abi=abi, unit=unit), self.assertRaises(ValueError):
                annex.compile_args(Path("clang.exe"), flags, abi, unit, self.root / "bad.o")

    def test_only_object_compile_commands_are_constructed(self):
        flags = annex.load_protocol()["compile_common_flags"]
        for abi in annex.ABIS:
            obj = self.root / "space path" / "torque_guard.o"
            argv = annex.compile_args(Path("clang.exe"), flags, abi, "torque_guard", obj)
            self.assertEqual(argv.count("-c"), 1)
            self.assertEqual(argv[-3:], ["torque_guard.c", "-o", str(obj)])
            self.assertIn("-mfloat-abi=" + abi, argv)
            self.assertNotIn("-shared", argv)

    def test_changed_helper_is_rejected_before_import(self):
        plan = annex.load_protocol()
        plan["shared_helper"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "helper changed"):
            annex.load_shared(plan)

    def test_retained_attempt_descendant_is_rejected_before_creation(self):
        retained = self.root / "retained"
        retained.mkdir()
        (retained / "receipt.json").write_text("preserve")
        output = retained / "new"
        with self.assertRaisesRegex(ValueError, "outside retained"):
            annex.build(self.root / "no-toolchain", self.root / "no-archive", output)
        self.assertFalse(output.exists())
        self.assertEqual((retained / "receipt.json").read_text(), "preserve")

    def test_existing_output_is_rejected(self):
        output = self.root / "existing"
        output.mkdir()
        with self.assertRaisesRegex(ValueError, "existing attempt"):
            annex.build(self.root / "no-toolchain", self.root / "no-archive", output)

    def test_bad_archive_retains_four_not_run_rows_and_no_executable_calls(self):
        archive = self.root / "bad.zip"
        archive.write_bytes(b"unverified")
        output = self.root / "new-attempt"
        result = annex.build(self.root / "no-toolchain", archive, output)
        self.assertEqual(result["status"], "failed_retained")
        self.assertEqual(result["error_type"], "ValueError")
        self.assertEqual(result["commands"], [])
        self.assertEqual(len(result["objects"]), 4)
        self.assertTrue(all(row["status"] == "not_run" for row in result["objects"]))
        self.assertEqual(json.loads((output / "receipt.json").read_text())["planned_commands"], 26)


if __name__ == "__main__": unittest.main()
