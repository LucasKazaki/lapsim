"""TC-02DC: numeric-domain rejection in the synthetic reference allocator.

All values are scenario fixtures. No firmware, CAN, or vehicle claims.
"""
from __future__ import annotations

import math
import unittest
from dataclasses import replace

from allocator import AllocationInput, AllocatorConfig, allocate_propulsive_torque, replay


CFG = AllocatorConfig(max_input_age_ms=50)
GOOD = AllocationInput(
    now_ms=1000, input_timestamp_ms=1000, request_nm=40.0,
    wheel_limits_nm=(20.0,) * 4, wheel_enabled=(True,) * 4,
    external_interlock=True,
)
HUGE = 10 ** 400
ZERO = (0.0,) * 4


class AllocatorNumericDomainTests(unittest.TestCase):
    def assert_zero_fault(self, request, expected, config=CFG):
        result = allocate_propulsive_torque(request, config)
        self.assertEqual(result.status, "fault")
        self.assertEqual(result.fault, expected)
        self.assertEqual(result.wheel_torque_nm, ZERO)
        self.assertEqual(result.delivered_nm, 0.0)
        self.assertTrue(math.isfinite(result.requested_nm))
        return result

    def test_original_nonfinite_float_classification(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=repr(value)):
                self.assert_zero_fault(replace(GOOD, request_nm=value), "nonfinite_request")

    def test_unrepresentable_positive_integer_request(self):
        self.assert_zero_fault(replace(GOOD, request_nm=HUGE), "invalid_request_numeric")

    def test_unrepresentable_negative_integer_request(self):
        self.assert_zero_fault(replace(GOOD, request_nm=-HUGE), "invalid_request_numeric")

    def test_wrong_type_request_string(self):
        self.assert_zero_fault(replace(GOOD, request_nm="40.0"), "invalid_request_numeric")

    def test_wrong_type_request_none(self):
        self.assert_zero_fault(replace(GOOD, request_nm=None), "invalid_request_numeric")

    def test_boolean_request_does_not_silently_convert_to_one(self):
        for value in (True, False):
            with self.subTest(value=value):
                self.assert_zero_fault(replace(GOOD, request_nm=value), "invalid_request_numeric")

    def test_huge_request_does_not_crash_other_fault_paths(self):
        self.assert_zero_fault(replace(GOOD, request_nm=HUGE), "invalid_max_input_age", AllocatorConfig(-1))
        self.assert_zero_fault(replace(GOOD, request_nm=HUGE, torque_unit="lb*ft"), "unsupported_torque_unit")

    def test_huge_wheel_limit_rejected_without_overflow(self):
        self.assert_zero_fault(replace(GOOD, wheel_limits_nm=(20.0, HUGE, 20.0, 20.0)), "invalid_wheel_limit")

    def test_non_numeric_wheel_limit_rejected(self):
        for value in (None, "20", True, False):
            with self.subTest(value=repr(value)):
                self.assert_zero_fault(replace(GOOD, wheel_limits_nm=(20.0, value, 20.0, 20.0)), "invalid_wheel_limit")

    def test_nonfinite_wheel_limits_still_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=repr(value)):
                self.assert_zero_fault(replace(GOOD, wheel_limits_nm=(value, 20.0, 20.0, 20.0)), "invalid_wheel_limit")

    def test_missing_limit_vector_rejected(self):
        self.assert_zero_fault(replace(GOOD, wheel_limits_nm=None), "invalid_wheel_vector")

    def test_missing_enabled_vector_rejected(self):
        self.assert_zero_fault(replace(GOOD, wheel_enabled=None), "invalid_wheel_vector")

    def test_valid_integer_request_and_limits_preserve_allocation(self):
        sample = replace(GOOD, request_nm=40, wheel_limits_nm=(20, 20, 20, 20))
        result = allocate_propulsive_torque(sample, CFG)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.wheel_torque_nm, (10.0,) * 4)
        self.assertEqual(result.delivered_nm, 40.0)

    def test_valid_fractional_request_preserves_allocation(self):
        result = allocate_propulsive_torque(replace(GOOD, request_nm=17.5), CFG)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.wheel_torque_nm, (4.375,) * 4)

    def test_negative_finite_request_still_inhibited(self):
        self.assert_zero_fault(replace(GOOD, request_nm=-1.0), "negative_request_unsupported")

    def test_mixed_replay_faults_are_deterministic(self):
        seq = [GOOD, replace(GOOD, request_nm=HUGE), GOOD, replace(GOOD, wheel_limits_nm=(20, HUGE, 20, 20))]
        a = replay(iter(seq), CFG)
        self.assertEqual(a, replay(seq, CFG))
        self.assertEqual([r.status for r in a], ["ok", "fault", "ok", "fault"])
        self.assertEqual([r.fault for r in a], [None, "invalid_request_numeric", None, "invalid_wheel_limit"])
        self.assertEqual(a[1].wheel_torque_nm, ZERO)
        self.assertEqual(a[3].wheel_torque_nm, ZERO)


if __name__ == "__main__":
    unittest.main()
