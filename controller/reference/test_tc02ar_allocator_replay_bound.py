"""Offline replay input-bound tests; no vehicle interface or CAN access."""
from __future__ import annotations

import unittest

from allocator import AllocationInput, AllocatorConfig, replay

CFG = AllocatorConfig(max_input_age_ms=20)
LIMIT = 4096  # Scenario cap, not a measured vehicle or MCU limit.


def request() -> AllocationInput:
    return AllocationInput(
        now_ms=100, input_timestamp_ms=100, request_nm=40.0,
        wheel_limits_nm=(20.0,) * 4, wheel_enabled=(True,) * 4,
        external_interlock=True,
    )


class CountedUnbounded:
    """Never ends by itself; throws if a consumer reads beyond the guard."""
    def __init__(self, max_reads=LIMIT + 1):
        self.reads = 0
        self.max_reads = max_reads

    def __iter__(self):
        return self

    def __next__(self):
        self.reads += 1
        if self.reads > self.max_reads:
            raise RuntimeError("unbounded input consumed past permitted guard")
        return request()


class BoundedAllocatorReplayTests(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(replay(iter(()), CFG), ())

    def test_finite_sequence_preserves_allocation(self):
        values = (request(), request())
        a = replay(values, CFG)
        self.assertEqual(len(a), 2)
        self.assertEqual(a[0].wheel_torque_nm, (10.0,) * 4)
        self.assertEqual(a[0], a[1])

    def test_exact_boundary_accepted(self):
        output = replay((request() for _ in range(LIMIT)), CFG)
        self.assertEqual(len(output), LIMIT)
        self.assertEqual(output[-1].delivered_nm, 40.0)

    def test_one_past_boundary_rejected(self):
        with self.assertRaisesRegex(ValueError, r"4096"):
            replay((request() for _ in range(LIMIT + 1)), CFG)

    def test_unbounded_generator_consumes_at_most_limit_plus_one(self):
        stream = CountedUnbounded()
        with self.assertRaisesRegex(ValueError, r"4096"):
            replay(stream, CFG)
        self.assertEqual(stream.reads, LIMIT + 1)


if __name__ == "__main__":
    unittest.main()
