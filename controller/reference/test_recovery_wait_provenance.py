"""Adversarial portable tests for the TC-02CS overflow distinction."""
import json
import math
import sys
import unittest

from recovery_wait_provenance import classify_wait_estimate


class RecoveryWaitProvenanceTests(unittest.TestCase):
    def test_zero_probability_is_genuinely_impossible(self):
        r = classify_wait_estimate(0.0, 16)
        self.assertEqual(r.classification, "impossible_when_probability_zero")
        self.assertIsNone(r.expected_observations)
        self.assertIsNone(r.log10_expected_observations)

    def test_nonzero_probability_extremely_small_is_not_impossible(self):
        r = classify_wait_estimate(1e-30, 16)
        self.assertEqual(r.classification, "finite_float_overflow")
        self.assertIsNone(r.expected_observations)
        self.assertAlmostEqual(r.log10_expected_observations, 480.0, places=9)

    def test_subnormal_nonzero_probability(self):
        r = classify_wait_estimate(math.nextafter(0.0, 1.0), 16)
        self.assertEqual(r.classification, "finite_float_overflow")
        self.assertTrue(math.isfinite(r.log10_expected_observations))
        self.assertGreater(r.log10_expected_observations, 5000)

    def test_near_zero_overflow_in_one_observation(self):
        r = classify_wait_estimate(math.nextafter(0.0, 1.0), 1)
        self.assertEqual(r.classification, "finite_float_overflow")
        self.assertIsNone(r.expected_observations)

    def test_one_probability_exact(self):
        r = classify_wait_estimate(1.0, 16)
        self.assertEqual(r.classification, "finite_representable")
        self.assertEqual(r.expected_observations, 16)
        self.assertAlmostEqual(r.log10_expected_observations, math.log10(16))

    def test_known_waits_and_magnitudes(self):
        for p, n, expected in [(0.5,2,6.0),(0.5,3,14.0),(.9,1,1/.9)]:
            with self.subTest(p=p,n=n):
                r=classify_wait_estimate(p,n)
                self.assertEqual(r.classification,"finite_representable")
                self.assertAlmostEqual(r.expected_observations,expected)
                self.assertAlmostEqual(r.log10_expected_observations,math.log10(expected))

    def test_strict_json_roundtrip_for_zero_and_overflow(self):
        for p in (0, 1e-30, 1):
            with self.subTest(p=p):
                data = classify_wait_estimate(p,16).as_json_record()
                out = json.loads(json.dumps(data, allow_nan=False))
                self.assertEqual(out["classification"],data["classification"])
                self.assertIn("log10_expected_observations",out)
                self.assertNotIn(out["classification"],("NaN","Infinity"))

    def test_strict_input_validation_inherited(self):
        for p in (-.1, 1.1, float("nan"),float("inf"), True, "0.3", 10**400):
            with self.subTest(p=type(p).__name__), self.assertRaises(ValueError):
                classify_wait_estimate(p,2)

    def test_required_run_validation_inherited(self):
        for n in (0,-1,17,True, 2.0):
            with self.subTest(n=n), self.assertRaises(ValueError):
                classify_wait_estimate(.1,n)

    def test_magnitude_monotone_as_probability_decreases(self):
        mags = [classify_wait_estimate(p,16).log10_expected_observations
                for p in (1,.9,.5,.01,1e-30)]
        self.assertEqual(mags,sorted(mags))

    def test_magnitude_monotone_as_run_increases(self):
        mags = [classify_wait_estimate(1e-30,k).log10_expected_observations
                for k in (1,2,3,8,16)]
        self.assertEqual(mags,sorted(mags))

    def test_report_remains_observation_count_not_time(self):
        evidence=classify_wait_estimate(.5,2).as_json_record()
        self.assertIn("expected_observations",evidence)
        self.assertFalse(any("second" in name or "hz" in name for name in evidence))
        self.assertEqual(evidence["schema"],"enme408-tc02cs-wait-evidence/v1")

    def test_valid_float_maximum_range(self):
        # A large, but representable finite wait should not become 'impossible'.
        r=classify_wait_estimate(1e-19,16)
        self.assertEqual(r.classification,"finite_representable")
        self.assertLess(r.expected_observations,sys.float_info.max)
        self.assertGreater(r.log10_expected_observations,300)

    def test_overflow_above_float_maximum_range(self):
        r=classify_wait_estimate(1e-20,16)
        self.assertEqual(r.classification,"finite_float_overflow")
        self.assertGreater(r.log10_expected_observations,math.log10(sys.float_info.max))

if __name__ == "__main__":
    unittest.main()
