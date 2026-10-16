"""Actual compiled owner checks; no model or simulated C substitute."""
import math
from pathlib import Path
import sys
import tempfile
import unittest

from guard_parity import build_guard_library, verify_in_child, frozen_protocol


class CompiledCommandGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="enme408-guard-tests-")
        root = Path(cls.temporary.name)
        (root / "one").mkdir(); (root / "two").mkdir()
        library, first = build_guard_library(root / "one")
        _, second = build_guard_library(root / "two")
        cls.binary_repeat_equal = first["binary_sha256"] == second["binary_sha256"]
        cls.receipt = verify_in_child(library)

    @classmethod
    def tearDownClass(cls): cls.temporary.cleanup()

    def test_frozen_owner_policy_and_separate_binary_repeat(self):
        self.assertEqual(frozen_protocol()["base"]["draft_pr"], 73)
        self.assertTrue(self.binary_repeat_equal)

    def test_direct_faults_cover_order_and_shared_contract(self):
        reasons = self.receipt["results"]["reasons"]
        for reason in ("invalid_pedal_latch_state", "invalid_max_rise_rate", "invalid_pedal_threshold",
                "invalid_previous_output", "invalid_dt", "invalid_accelerator_fraction", "invalid_boolean_input",
                "invalid_candidate_type", "candidate_sum_mismatch", "candidate_exceeds_request",
                "allocator_fault", "external_interlock_open", "critical_communication_loss", "sensor_disagreement",
                "brake_accelerator_overlap", "invalid_rise_step", "aggregate_and_rise_rate_limit"):
            with self.subTest(reason=reason): self.assertGreater(reasons[reason], 0)

    def test_stateful_and_actual_compiled_composition(self):
        results = self.receipt["results"]
        self.assertEqual(results["stateful_cycles"], 8192)
        self.assertEqual(results["composed_cycles"], 8262)
        self.assertGreater(results["allowed_cycles"], 0)
        self.assertGreater(results["held_cycles"], 0)
        self.assertGreater(results["clock_fault_cycles"], 0)

    def test_negative_zero_preserved_and_addition_overflow_target_wins(self):
        corners = self.receipt["results"]["corners"]
        self.assertEqual(corners["negative_zero"]["output_hex"], ["-0x0.0p+0"] * 4)
        self.assertEqual(corners["addition_overflow"]["output_hex"][0], sys.float_info.max.hex())
        self.assertEqual(corners["addition_overflow"]["status"], "ok")

    def test_underflow_epsilon_label_and_immediate_decrease(self):
        corners = self.receipt["results"]["corners"]
        self.assertEqual(corners["underflow_epsilon_label"]["output_hex"], [0.0.hex()] * 4)
        self.assertEqual(corners["underflow_epsilon_label"]["status"], "ok")
        self.assertIsNone(corners["underflow_epsilon_label"]["reason"])
        self.assertEqual(corners["above_epsilon_label"]["status"], "limited")
        self.assertEqual(corners["above_epsilon_label"]["output_hex"][0], math.ulp(0.).hex())
        self.assertEqual(corners["immediate_decrease"]["output_hex"][0], 1.0.hex())

    def test_raw_base_latch_behavior_remains_separate_from_trust_adapters(self):
        corners = self.receipt["results"]["corners"]
        self.assertFalse(corners["raw_fault_clear"]["latched"])
        self.assertEqual(corners["raw_fault_clear"]["reason"], "allocator_fault")
        self.assertTrue(corners["trip_before_comms"]["latched"])
        self.assertEqual(corners["trip_before_comms"]["reason"], "critical_communication_loss")
        self.assertFalse(corners["raw_invalid_dt_missed_trip"]["latched"])

    def test_raw_abi_tags_and_nulls_fail_closed(self):
        self.assertGreater(self.receipt["boundaries"]["checks"], 5000)
        self.assertEqual(set(self.receipt["guard_abi_sizes"]), {"GuardConfig", "GuardInput", "GuardState", "GuardResult"})


if __name__ == "__main__": unittest.main()
