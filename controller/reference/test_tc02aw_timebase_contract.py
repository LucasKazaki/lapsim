"""Additional synthetic timebase-contract checks; no physical timing or CAN I/O."""
from __future__ import annotations

import math
import random
import unittest
from dataclasses import replace
from decimal import Decimal

from allocator import AllocationInput, AllocatorConfig, allocate_propulsive_torque, replay


def scenario(**updates):
    value = AllocationInput(
        now_ms=1050, input_timestamp_ms=1000, request_nm=80.0,
        wheel_limits_nm=(30.0, 30.0, 30.0, 30.0),
        wheel_enabled=(True, True, True, True), external_interlock=True,
    )
    return replace(value, **updates)


class TimebaseContractIntegrationTests(unittest.TestCase):
    def test_integral_float_is_not_an_integer_tick(self):
        for name in ('now_ms', 'input_timestamp_ms'):
            with self.subTest(name=name):
                r = allocate_propulsive_torque(
                    scenario(**{name: float(getattr(scenario(), name))}),
                    AllocatorConfig(50),
                )
                self.assertEqual((r.fault, r.delivered_nm), ('invalid_input_timestamp', 0.0))

    def test_decimal_tick_not_silently_accepted(self):
        r = allocate_propulsive_torque(
            scenario(now_ms=Decimal(1050)), AllocatorConfig(50)
        )
        self.assertEqual((r.fault, r.wheel_torque_nm),
                         ('invalid_input_timestamp', (0.0,) * 4))

    def test_valid_age_boundary_and_one_millisecond_stale(self):
        cfg = AllocatorConfig(50)
        self.assertEqual(allocate_propulsive_torque(scenario(), cfg).delivered_nm, 80.0)
        r = allocate_propulsive_torque(scenario(now_ms=1051), cfg)
        self.assertEqual((r.fault, r.delivered_nm), ('stale_input', 0.0))

    def test_mixed_replay_fault_isolated_to_bad_sample(self):
        samples = (scenario(), scenario(now_ms=math.nan), scenario(now_ms=1050))
        result = replay(samples, AllocatorConfig(50))
        self.assertEqual(tuple(r.status for r in result), ('ok', 'fault', 'ok'))
        self.assertEqual(tuple(r.delivered_nm for r in result), (80.0, 0.0, 80.0))
        self.assertEqual(result, replay(samples, AllocatorConfig(50)))

    def test_invalid_age_configuration_cannot_enable_allocation(self):
        for age in (-1, float('nan'), float('inf'), 50.0, True, '50'):
            with self.subTest(age=repr(age)):
                r = allocate_propulsive_torque(scenario(), AllocatorConfig(age))
                self.assertEqual((r.fault, r.delivered_nm), ('invalid_max_input_age', 0.0))

    def test_hypothetical_uint32_rollover_is_not_supported_by_offline_reference(self):
        # If these were verified uint32 ticks in one clock domain, age would
        # be (3 - 0xfffffffe) mod 2**32 = 5 ticks. The Python reference instead
        # assumes monotonically increasing no-wrap integer milliseconds.
        sample = scenario(now_ms=3, input_timestamp_ms=0xfffffffe)
        r = allocate_propulsive_torque(sample, AllocatorConfig(50))
        self.assertEqual((r.fault, r.delivered_nm), ('input_timestamp_in_future', 0.0))
        self.assertEqual((3 - 0xfffffffe) % (2 ** 32), 5)

    def test_seeded_valid_integer_scenarios_are_bounded_and_reproducible(self):
        rng = random.Random(20261009)
        for _ in range(500):
            now = rng.randrange(0, 250_000)
            age = rng.randrange(0, 100)
            born = max(0, now - age)
            limits = tuple(float(rng.randrange(0, 101)) for _ in range(4))
            enabled = tuple(bool(rng.getrandbits(1)) for _ in range(4))
            request = float(rng.randrange(0, 251))
            item = scenario(now_ms=now, input_timestamp_ms=born,
                            wheel_limits_nm=limits, wheel_enabled=enabled,
                            request_nm=request)
            cfg = AllocatorConfig(50)
            result = allocate_propulsive_torque(item, cfg)
            self.assertTrue(all(math.isfinite(x) and x >= 0 for x in result.wheel_torque_nm))
            self.assertTrue(all(x <= lim + 1e-9 for x, lim in zip(result.wheel_torque_nm, limits)))
            self.assertAlmostEqual(result.delivered_nm, sum(result.wheel_torque_nm), places=9)
            self.assertEqual(result, allocate_propulsive_torque(item, cfg))


if __name__ == '__main__':
    unittest.main()
