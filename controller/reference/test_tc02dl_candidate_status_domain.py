"""TC-02DL: malformed synthetic allocator-status replay values stay fail-closed.

Offline Python reference only. This is not a vehicle safety or firmware test.
"""
import unittest

from allocator import AllocationResult
from command_guard import (
    CommandGuardConfig, CommandGuardInput, CommandGuardState,
    apply_command_guard, replay_guard,
)
from latch_recovery_experiment import experiment_one_step

ZERO = (0.0, 0.0, 0.0, 0.0)
CFG = CommandGuardConfig(100.0, 0.60, 0.20)
INPUT = CommandGuardInput(0.05, 0.10, False, True, True, True)
INITIAL = CommandGuardState(ZERO, False)


def candidate(status):
    return AllocationResult((10.0,) * 4, 40.0, 40.0, status, "aggregate_limit" if status == "saturated" else None)


class CandidateStatusValidation(unittest.TestCase):
    def test_unhashable_statuses_inhibit_without_exception(self):
        # A decoded JSON record or other mis-typed replay input can supply
        # a list/dict rather than a scalar status string. These must not crash.
        for bad in ([], ["ok"], {}, {"status": "ok"}, set(), bytearray(b"ok")):
            with self.subTest(status=repr(bad)):
                result = apply_command_guard(candidate(bad), INPUT, CFG, INITIAL)
                self.assertEqual(result.output_nm, ZERO)
                self.assertEqual(result.status, "inhibited")
                self.assertEqual(result.reason, "invalid_candidate_status")
                self.assertIs(result.next_state.pedal_overlap_latched, False)

    def test_wrong_hashable_statuses_preserve_existing_reason(self):
        for bad in (None, 0, True, "", "OK", b"ok"):
            with self.subTest(status=repr(bad)):
                result = apply_command_guard(candidate(bad), INPUT, CFG, INITIAL)
                self.assertEqual((result.output_nm, result.reason),
                                 (ZERO, "invalid_candidate_status"))

    def test_fault_then_healthy_replay_is_deterministic(self):
        observations = (candidate(["ok"]), candidate("ok"))
        a = replay_guard(observations, (INPUT, INPUT), CFG, INITIAL)
        b = replay_guard(observations, (INPUT, INPUT), CFG, INITIAL)
        self.assertEqual(a, b)
        self.assertEqual(a[0].output_nm, ZERO)
        self.assertEqual(a[0].reason, "invalid_candidate_status")
        self.assertEqual(a[1].output_nm, (5.0,) * 4)
        self.assertEqual(a[1].status, "limited")

    def test_latched_experimental_comparator_keeps_latch_on_bad_status(self):
        result = experiment_one_step(
            candidate({"status": "ok"}), INPUT, CFG, CommandGuardState(ZERO, True)
        )
        self.assertEqual(result.output_nm, ZERO)
        self.assertEqual(result.reason, "invalid_candidate_status")
        self.assertIs(result.next_state.pedal_overlap_latched, True)

    def test_valid_status_contract_is_unchanged(self):
        for status, expected in (("ok", "limited"), ("saturated", "limited")):
            with self.subTest(status=status):
                result = apply_command_guard(candidate(status), INPUT, CFG, INITIAL)
                self.assertEqual(result.output_nm, (5.0,) * 4)
                self.assertEqual(result.status, expected)
        fault = AllocationResult(ZERO, 40.0, 0.0, "fault", "synthetic_fault")
        result = apply_command_guard(fault, INPUT, CFG, INITIAL)
        self.assertEqual((result.output_nm, result.reason), (ZERO, "allocator_fault"))


if __name__ == "__main__":
    unittest.main()
