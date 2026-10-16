"""TC-02CV: portable independent finite-horizon log evidence tests."""
import itertools
import json
import math
import unittest

from recovery_latency_tradeoff import probability_qualified_by
from recovery_probability_log_evidence import classify_horizon_probability


class LogHorizonEvidenceTests(unittest.TestCase):
    def test_known_finite(self):
        item = classify_horizon_probability(0.5, 2, 2)
        self.assertAlmostEqual(item.log10_hit_probability, math.log10(0.25), places=12)
        self.assertAlmostEqual(item.log10_no_hit_probability, math.log10(0.75), places=12)
        self.assertEqual(item.classification, "finite_float_representable")

    def test_positive_probability_underflow(self):
        item = classify_horizon_probability(1e-30, 16, 16)
        self.assertEqual(item.baseline_float_probability, 0.0)
        self.assertEqual(item.classification, "positive_but_float_underflow")
        self.assertAlmostEqual(item.log10_hit_probability, -480, places=10)
        self.assertEqual(item.log10_no_hit_probability, 0.0)

    def test_smallest_positive_float_does_not_lose_log(self):
        item = classify_horizon_probability(math.ulp(0.0), 16, 16)
        self.assertTrue(math.isfinite(item.log10_hit_probability))
        self.assertLess(item.log10_hit_probability, -5000)
        self.assertEqual(item.classification, "positive_but_float_underflow")

    def test_tiny_but_representable_baseline(self):
        item = classify_horizon_probability(1e-10, 16, 16)
        self.assertGreater(item.baseline_float_probability, 0)
        self.assertAlmostEqual(item.log10_hit_probability, -160, places=10)
        self.assertEqual(item.classification, "finite_float_representable")

    def test_float_one_can_still_mean_positive_failure(self):
        item = classify_horizon_probability(0.5, 1, 256)
        self.assertEqual(item.baseline_float_probability, 1.0)
        self.assertEqual(item.classification, "not_certain_but_float_rounded_to_one")
        self.assertAlmostEqual(item.log10_no_hit_probability, 256 * math.log10(.5), places=10)

    def test_true_zero_cases(self):
        for p, r, h in [(0.0, 1, 20), (0.5, 3, 2), (1.0, 16, 0)]:
            with self.subTest(p=p, r=r, h=h):
                row = classify_horizon_probability(p, r, h)
                self.assertEqual(row.classification, "mathematically_impossible")
                self.assertIsNone(row.log10_hit_probability)
                self.assertEqual(row.log10_no_hit_probability, 0)

    def test_true_certainty(self):
        for h in (3, 16, 256):
            row = classify_horizon_probability(1.0, 3, h)
            self.assertEqual(row.classification, "mathematically_certain")
            self.assertEqual(row.log10_hit_probability, 0)
            self.assertIsNone(row.log10_no_hit_probability)

    def test_json_strict_roundtrip(self):
        for p, r, h in [(0, 2, 4), (1, 2, 4), (.5, 2, 4), (1e-30, 16, 16), (.5, 1, 256)]:
            row = classify_horizon_probability(p, r, h).as_json_record()
            decoded = json.loads(json.dumps(row, allow_nan=False))
            self.assertEqual(row, decoded)

    def test_short_horizon_against_independent_enumeration(self):
        for p in (0.05, 0.25, 0.5, 0.8, 0.95):
            for r in (1, 2, 3):
                for h in range(0, 8):
                    ref = 0.0
                    for bits in itertools.product((0, 1), repeat=h):
                        streak = 0
                        event = False
                        for bit in bits:
                            streak = streak+1 if bit else 0
                            event |= streak >= r
                        if event:
                            ref += math.prod(p if bit else 1-p for bit in bits)
                    row = classify_horizon_probability(p, r, h)
                    if ref == 0:
                        self.assertIsNone(row.log10_hit_probability)
                    else:
                        self.assertAlmostEqual(10**row.log10_hit_probability, ref, places=12)

    def test_probability_mass_conservation(self):
        for p in (1e-8, 0.01, 0.3, 0.5, 0.95, 1-1e-9):
            for r in (1, 2, 5, 16):
                for h in (r, r+1, 32, 256):
                    row = classify_horizon_probability(p, r, h)
                    a = 10**row.log10_hit_probability
                    b = 10**row.log10_no_hit_probability
                    self.assertAlmostEqual(a+b, 1.0, delta=2e-12)

    def test_monotonic_horizon_qualified_probability(self):
        for p in (.01, 0.5, .95):
            for r in (1, 2, 7):
                a = [classify_horizon_probability(p, r, h).log10_hit_probability for h in range(r, 40)]
                self.assertTrue(all(x <= y+1e-12 for x,y in zip(a,a[1:])))

    def test_positive_event_and_complement_for_interior_p(self):
        for p in (math.ulp(0.0), 0.5, 1-1e-15):
            row = classify_horizon_probability(p, 1, 256)
            self.assertTrue(math.isfinite(row.log10_hit_probability))
            self.assertTrue(math.isfinite(row.log10_no_hit_probability))

    def test_input_contract_matches_existing_reference(self):
        for p,r,h in [(True,1,1), (float("nan"),1,1), (float("inf"),1,1), (".5",1,1),
                      (-.1,1,1), (1.1,1,1), (0.5,0,1), (0.5,17,17), (0.5,1,257),
                      (0.5,1,-1), (0.5,1,True), (10**400,1,1)]:
            with self.subTest(p=str(p)[:15],r=r,h=h), self.assertRaises(ValueError):
                classify_horizon_probability(p,r,h)

    def test_original_reference_unchanged_behavior(self):
        self.assertEqual(probability_qualified_by(1e-30, 16, 16), 0.0)
        self.assertEqual(probability_qualified_by(.5, 2, 2), 0.25)

    def test_deterministic_records(self):
        params=(.17,3,140)
        a=classify_horizon_probability(*params).as_json_record()
        b=classify_horizon_probability(*params).as_json_record()
        self.assertEqual(a,b)


if __name__=="__main__":
    unittest.main()
