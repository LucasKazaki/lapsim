"""TC-02DF: reject aggregate overflow deterministically in offline guard.

All values are synthetic numeric counterexamples, not physical vehicle limits.
No CAN, embedded firmware or hardware is exercised.
"""
from __future__ import annotations

import unittest

from allocator import AllocationResult
from command_guard import (
    CommandGuardConfig, CommandGuardInput, CommandGuardState,
    apply_command_guard, replay_guard,
)

CFG = CommandGuardConfig(100.0, 0.6, 0.2)
INPUT = CommandGuardInput(0.05, 0.3, False, True, True, True)
STATE = CommandGuardState((0.0, 0.0, 0.0, 0.0))
ZERO = (0.0, 0.0, 0.0, 0.0)


def candidate(wheels, delivered):
    return AllocationResult(tuple(wheels), delivered, delivered, "ok", None)


class GuardAggregateDomainTests(unittest.TestCase):
    def assertInhibitedMismatch(self, wheels, delivered):
        result = apply_command_guard(candidate(wheels, delivered), INPUT, CFG, STATE)
        self.assertEqual(result.status, "inhibited")
        self.assertEqual(result.reason, "candidate_sum_mismatch")
        self.assertEqual(result.output_nm, ZERO)
        self.assertEqual(result.next_state.previous_output_nm, ZERO)

    def test_four_individually_float_finite_large_integers_do_not_raise(self):
        self.assertInhibitedMismatch((10**308,) * 4, 0.0)

    def test_mixed_large_integer_and_float_sum_overflow_does_not_raise(self):
        self.assertInhibitedMismatch((10**308, 1e308, 0.0, 0.0), 0.0)

    def test_float_only_finite_elements_with_infinite_total_inhibit(self):
        self.assertInhibitedMismatch((1e308, 1e308, 1e308, 1e308), 1e308)

    def test_finite_within_range_large_integer_aggregate_is_accepted(self):
        total = float(4 * 10**306)
        result = apply_command_guard(candidate((10**306,) * 4, total), INPUT, CFG, STATE)
        self.assertEqual(result.status, "limited")
        self.assertEqual(result.reason, "rise_rate_limit")
        self.assertEqual(result.output_nm, (5.0,) * 4)

    def test_mixed_ordinary_integer_float_vector_keeps_slew_logic(self):
        result = apply_command_guard(candidate((10, 10.0, 10, 10.0), 40), INPUT, CFG, STATE)
        self.assertEqual(result.status, "limited")
        self.assertEqual(result.output_nm, (5.0,) * 4)

    def test_ordinary_sum_mismatch_still_inhibits(self):
        self.assertInhibitedMismatch((2.0,) * 4, 7.0)

    def test_existing_nonfinite_per_wheel_classification_preserved(self):
        r = apply_command_guard(candidate((1.0, float("inf"), 2.0, 3.0), 6.0), INPUT, CFG, STATE)
        self.assertEqual((r.status, r.reason, r.output_nm),
                         ("inhibited", "invalid_candidate_output", ZERO))

    def test_replay_after_oversized_candidate_recovers_deterministically(self):
        examples = [candidate((10**308,) * 4, 0.0), candidate((10.0,) * 4, 40.0)]
        first = replay_guard(examples, (INPUT, INPUT), CFG, STATE)
        second = replay_guard(examples, (INPUT, INPUT), CFG, STATE)
        self.assertEqual(first, second)
        self.assertEqual((first[0].status, first[0].reason),
                         ("inhibited", "candidate_sum_mismatch"))
        self.assertEqual((first[1].status, first[1].reason, first[1].output_nm),
                         ("limited", "rise_rate_limit", (5.0,) * 4))


if __name__ == "__main__":
    unittest.main()
