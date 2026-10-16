"""Synthetic input-timebase validation, not firmware or vehicle tests."""
from __future__ import annotations

import math
import unittest
from dataclasses import replace

from allocator import AllocationInput, AllocatorConfig, allocate_propulsive_torque


def good_input() -> AllocationInput:
    return AllocationInput(
        now_ms=1000, input_timestamp_ms=980, request_nm=40.0,
        wheel_limits_nm=(30.0,) * 4, wheel_enabled=(True,) * 4,
        external_interlock=True,
    )


class InputTimebaseValidationTests(unittest.TestCase):
    def assert_fault_zero(self, inp, cfg, fault):
        result = allocate_propulsive_torque(inp, cfg)
        self.assertEqual(result.status, "fault")
        self.assertEqual(result.fault, fault)
        self.assertEqual(result.wheel_torque_nm, (0.0,) * 4)
        self.assertEqual(result.delivered_nm, 0.0)

    def test_valid_integer_milliseconds_unchanged(self):
        result = allocate_propulsive_torque(good_input(), AllocatorConfig(50))
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.wheel_torque_nm, (10.0,) * 4)

    def test_nan_now_cannot_bypass_age_check(self):
        self.assert_fault_zero(replace(good_input(), now_ms=math.nan), AllocatorConfig(50), "invalid_input_timestamp")

    def test_nan_generation_tick_cannot_bypass_age_check(self):
        self.assert_fault_zero(replace(good_input(), input_timestamp_ms=math.nan), AllocatorConfig(50), "invalid_input_timestamp")

    def test_infinite_now_and_generation_tick_rejected(self):
        for field in ("now_ms", "input_timestamp_ms"):
            for v in (math.inf, -math.inf):
                with self.subTest(field=field, value=v):
                    self.assert_fault_zero(replace(good_input(), **{field: v}), AllocatorConfig(50), "invalid_input_timestamp")

    def test_fractional_milliseconds_rejected_as_undeclared_units(self):
        self.assert_fault_zero(replace(good_input(), now_ms=1000.5), AllocatorConfig(50), "invalid_input_timestamp")

    def test_boolean_milliseconds_rejected(self):
        self.assert_fault_zero(replace(good_input(), input_timestamp_ms=True), AllocatorConfig(50), "invalid_input_timestamp")

    def test_negative_milliseconds_rejected(self):
        self.assert_fault_zero(replace(good_input(), now_ms=-1, input_timestamp_ms=-2), AllocatorConfig(50), "invalid_input_timestamp")

    def test_nan_infinite_and_wrong_type_max_age_rejected(self):
        for v in (math.nan, math.inf, "50", True):
            with self.subTest(value=v):
                self.assert_fault_zero(good_input(), AllocatorConfig(v), "invalid_max_input_age")

    def test_zero_age_boundary_and_stale_behavior_retained(self):
        cfg = AllocatorConfig(0)
        same = replace(good_input(), input_timestamp_ms=1000)
        self.assertEqual(allocate_propulsive_torque(same, cfg).status, "ok")
        self.assert_fault_zero(replace(good_input(), input_timestamp_ms=999), cfg, "stale_input")

    def test_future_timestamp_fault_priority_retained(self):
        self.assert_fault_zero(replace(good_input(), input_timestamp_ms=1001), AllocatorConfig(50), "input_timestamp_in_future")


if __name__ == "__main__":
    unittest.main()
