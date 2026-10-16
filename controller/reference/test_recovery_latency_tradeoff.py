"""TC-02CE offline analytic and finite enumeration regressions."""
import itertools
import json
import math
import unittest

from recovery_latency_tradeoff import (
    compare_recovery_latency,
    expected_samples_to_qualify,
    probability_qualified_by,
)


def brute_force_hit_probability(p, consecutive, horizon):
    """Independent enumerator for small horizons only, not production code."""
    prob = 0.0
    for outcomes in itertools.product((False, True), repeat=horizon):
        weight = math.prod(p if x else 1.0 - p for x in outcomes)
        streak = 0
        for outcome in outcomes:
            streak = streak + 1 if outcome else 0
            if streak >= consecutive:
                prob += weight
                break
    return prob


class RecoveryLatencyTests(unittest.TestCase):
    def test_known_waiting_times(self):
        self.assertEqual(expected_samples_to_qualify(1, 2), 2.0)
        self.assertEqual(expected_samples_to_qualify(0.5, 2), 6.0)
        self.assertEqual(expected_samples_to_qualify(0.5, 3), 14.0)
        self.assertAlmostEqual(expected_samples_to_qualify(0.9, 2), 2.345679012345679)

    def test_no_recovery_at_zero_probability(self):
        self.assertTrue(math.isinf(expected_samples_to_qualify(0, 2)))
        self.assertEqual(probability_qualified_by(0, 2, 256), 0.0)

    def test_guaranteed_recovery_at_full_probability(self):
        self.assertEqual(probability_qualified_by(1, 3, 2), 0.0)
        self.assertEqual(probability_qualified_by(1, 3, 3), 1.0)

    def test_finite_horizon_counterexample(self):
        self.assertAlmostEqual(probability_qualified_by(0.5, 2, 2), 0.25)
        self.assertAlmostEqual(probability_qualified_by(0.5, 2, 3), 0.375)
        self.assertEqual(probability_qualified_by(0.5, 2, 0), 0.0)

    def test_independent_exhaustive_enumerator(self):
        for p in (0.0, 0.1, 0.5, 0.8, 1.0):
            for r in (1, 2, 3, 4):
                for n in range(0, 7):
                    with self.subTest(p=p, r=r, n=n):
                        self.assertAlmostEqual(
                            probability_qualified_by(p, r, n),
                            brute_force_hit_probability(p, r, n), places=12)

    def test_monotonic_qualified_probability_and_wait(self):
        for r in (1, 2, 4, 8):
            prev_prob = 0.0
            prev_wait = math.inf
            for p in (0.0, 0.2, 0.6, 0.9, 1.0):
                got_prob = probability_qualified_by(p, r, 12)
                got_wait = expected_samples_to_qualify(p, r)
                self.assertGreaterEqual(got_prob + 1e-14, prev_prob)
                self.assertLessEqual(got_wait, prev_wait)
                prev_prob, prev_wait = got_prob, got_wait

    def test_comparison_order(self):
        row = compare_recovery_latency(allocator_valid_probability=0.99,
                                       end_to_end_valid_probability=0.8,
                                       required_samples=2, horizon_samples=5)
        self.assertGreater(row.qualified_expected_samples, row.allocator_expected_samples)
        self.assertLess(row.qualified_probability_by_horizon, row.allocator_probability_by_horizon)
        self.assertEqual(row.schema, "enme408-tc02ce-recovery-latency-sensitivity/v1")

    def test_equal_probabilities_equal_results(self):
        row = compare_recovery_latency(allocator_valid_probability=.9,
                                       end_to_end_valid_probability=.9)
        self.assertEqual(row.qualified_expected_samples, row.allocator_expected_samples)
        self.assertEqual(row.qualified_probability_by_horizon, row.allocator_probability_by_horizon)

    def test_reject_out_of_order_probabilities(self):
        with self.assertRaises(ValueError):
            compare_recovery_latency(allocator_valid_probability=.8,
                                     end_to_end_valid_probability=.9)

    def test_reject_malformed_probabilities(self):
        for bad in (True, -0.1, 1.1, float("nan"), float("inf"), "0.9", 10**400):
            with self.subTest(bad=type(bad).__name__), self.assertRaises(ValueError):
                expected_samples_to_qualify(bad, 2)

    def test_bounded_integer_contract(self):
        for bad_r in (0, -1, True, 1.0, 17):
            with self.assertRaises(ValueError):
                expected_samples_to_qualify(0.9, bad_r)
        for bad_h in (-1, True, 1.0, 257):
            with self.assertRaises(ValueError):
                probability_qualified_by(.9, 2, bad_h)

    def test_strict_json_supports_no_recovery(self):
        row = compare_recovery_latency(allocator_valid_probability=.9,
                                       end_to_end_valid_probability=0.0)
        payload = json.loads(json.dumps(row.as_json_record(), allow_nan=False))
        self.assertIsNone(payload["qualified_expected_samples"])
        self.assertGreater(payload["allocator_expected_samples"], 2.0)


if __name__ == "__main__":
    unittest.main()
