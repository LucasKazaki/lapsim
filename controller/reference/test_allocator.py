from __future__ import annotations

import math
import unittest

from allocator import (
    AllocationInput,
    AllocatorConfig,
    allocate_propulsive_torque,
    replay,
)


CFG = AllocatorConfig(max_input_age_ms=50)


def sample(
    *,
    request_nm: float = 40.0,
    limits=(20.0, 20.0, 20.0, 20.0),
    enabled=(True, True, True, True),
    now_ms: int = 1000,
    input_timestamp_ms: int = 1000,
    interlock: bool = True,
    torque_unit: str = "N*m",
):
    return AllocationInput(
        now_ms=now_ms,
        input_timestamp_ms=input_timestamp_ms,
        request_nm=request_nm,
        wheel_limits_nm=limits,
        wheel_enabled=enabled,
        external_interlock=interlock,
        torque_unit=torque_unit,
    )


class TorqueAllocatorTests(unittest.TestCase):
    def assert_invariants(self, inp, result):
        self.assertEqual(len(result.wheel_torque_nm), 4)
        for output, limit, enabled in zip(
            result.wheel_torque_nm, inp.wheel_limits_nm, inp.wheel_enabled
        ):
            self.assertTrue(math.isfinite(output))
            self.assertGreaterEqual(output, 0.0)
            self.assertLessEqual(output, limit + 1e-9)
            if not enabled:
                self.assertEqual(output, 0.0)
        self.assertAlmostEqual(sum(result.wheel_torque_nm), result.delivered_nm)

    def test_equal_allocation(self):
        inp = sample(request_nm=40.0)
        result = allocate_propulsive_torque(inp, CFG)
        self.assertEqual(result.wheel_torque_nm, (10.0, 10.0, 10.0, 10.0))
        self.assertEqual(result.status, "ok")
        self.assert_invariants(inp, result)

    def test_disabled_wheel_redistributes(self):
        inp = sample(enabled=(True, True, True, False))
        result = allocate_propulsive_torque(inp, CFG)
        self.assertAlmostEqual(result.wheel_torque_nm[0], 40.0 / 3.0)
        self.assertEqual(result.wheel_torque_nm[3], 0.0)
        self.assert_invariants(inp, result)

    def test_limited_wheel_redistributes(self):
        inp = sample(request_nm=40.0, limits=(4.0, 20.0, 20.0, 20.0))
        result = allocate_propulsive_torque(inp, CFG)
        self.assertEqual(result.wheel_torque_nm[0], 4.0)
        self.assertAlmostEqual(result.wheel_torque_nm[1], 12.0)
        self.assertAlmostEqual(result.wheel_torque_nm[2], 12.0)
        self.assertAlmostEqual(result.wheel_torque_nm[3], 12.0)
        self.assert_invariants(inp, result)

    def test_aggregate_saturation_is_explicit(self):
        inp = sample(request_nm=100.0, limits=(10.0, 10.0, 10.0, 10.0))
        result = allocate_propulsive_torque(inp, CFG)
        self.assertEqual(result.status, "saturated")
        self.assertEqual(result.fault, "aggregate_limit")
        self.assertEqual(result.delivered_nm, 40.0)
        self.assert_invariants(inp, result)

    def test_stale_input_fails_closed(self):
        inp = sample(now_ms=1000, input_timestamp_ms=949)
        result = allocate_propulsive_torque(inp, CFG)
        self.assertEqual(result.fault, "stale_input")
        self.assertEqual(result.delivered_nm, 0.0)

    def test_future_timestamp_fails_closed(self):
        inp = sample(now_ms=1000, input_timestamp_ms=1001)
        result = allocate_propulsive_torque(inp, CFG)
        self.assertEqual(result.fault, "input_timestamp_in_future")
        self.assertEqual(result.delivered_nm, 0.0)

    def test_external_interlock_fails_closed(self):
        result = allocate_propulsive_torque(sample(interlock=False), CFG)
        self.assertEqual(result.fault, "external_interlock_open")
        self.assertEqual(result.delivered_nm, 0.0)

    def test_nonfinite_request_fails_closed(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                result = allocate_propulsive_torque(sample(request_nm=value), CFG)
                self.assertEqual(result.fault, "nonfinite_request")
                self.assertEqual(result.delivered_nm, 0.0)

    def test_negative_request_is_not_silently_regen(self):
        result = allocate_propulsive_torque(sample(request_nm=-1.0), CFG)
        self.assertEqual(result.fault, "negative_request_unsupported")
        self.assertEqual(result.delivered_nm, 0.0)

    def test_wrong_unit_fails_closed(self):
        result = allocate_propulsive_torque(sample(torque_unit="lb*ft"), CFG)
        self.assertEqual(result.fault, "unsupported_torque_unit")
        self.assertEqual(result.delivered_nm, 0.0)

    def test_invalid_limit_fails_closed(self):
        for bad_limit in (-1.0, math.nan, math.inf):
            with self.subTest(bad_limit=bad_limit):
                result = allocate_propulsive_torque(
                    sample(limits=(20.0, 20.0, bad_limit, 20.0)), CFG
                )
                self.assertEqual(result.fault, "invalid_wheel_limit")
                self.assertEqual(result.delivered_nm, 0.0)

    def test_no_available_wheels_fails_closed(self):
        result = allocate_propulsive_torque(
            sample(enabled=(False, False, False, False)), CFG
        )
        self.assertEqual(result.fault, "no_available_wheels")
        self.assertEqual(result.delivered_nm, 0.0)

    def test_zero_request(self):
        inp = sample(request_nm=0.0)
        result = allocate_propulsive_torque(inp, CFG)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.delivered_nm, 0.0)
        self.assert_invariants(inp, result)

    def test_replay_is_deterministic_and_bounded(self):
        inputs = (
            sample(request_nm=20.0),
            sample(request_nm=60.0, limits=(5.0, 25.0, 25.0, 25.0)),
            sample(now_ms=1000, input_timestamp_ms=900),
            sample(interlock=False),
        )
        first = replay(inputs, CFG)
        second = replay(inputs, CFG)
        self.assertEqual(first, second)
        for inp, result in zip(inputs, first):
            if result.fault in (None, "aggregate_limit"):
                self.assert_invariants(inp, result)


if __name__ == "__main__":
    unittest.main()
