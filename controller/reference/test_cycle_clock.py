"""Compare the extracted owner with the frozen pre-port Python clock block."""
import itertools
import math
import unittest

from allocation_contract import ordinary_finite
from cycle_clock import CycleClockState, observe_cycle_clock


def legacy_clock(previous_tick, tick, dt_s, period_ms):
    # Exact source block from 9baeb614/control_pipeline.py. Keep independent of
    # the extracted owner so a future accidental anchor-policy change is seen.
    dt = ordinary_finite(dt_s)
    clock_fault = None
    if type(tick) is not int or tick < 0:
        clock_fault = "invalid_cycle_timestamp"
    elif previous_tick is not None and tick <= previous_tick:
        clock_fault = "nonmonotonic_cycle_timestamp"
    else:
        if previous_tick is not None and tick - previous_tick != period_ms:
            clock_fault = "cycle_period_mismatch"
        previous_tick = tick
    if dt is None or not math.isclose(dt, period_ms / 1000, rel_tol=0., abs_tol=1e-12):
        clock_fault = clock_fault or "guard_period_mismatch"
    return previous_tick, tick if type(tick) is int and tick >= 0 else None, clock_fault


def dt_edges(period_ms):
    expected = period_ms / 1000
    edges = [None, True, "0.05", -1., -0., 0., math.nan, math.inf, -math.inf,
             10**400, expected, math.nextafter(expected, -math.inf),
             math.nextafter(expected, math.inf), 1, 100., 5e-324]
    for bound in (expected-1e-12, expected+1e-12):
        edges.extend((math.nextafter(bound, -math.inf), bound,
                      math.nextafter(bound, math.inf)))
    return edges


class CycleClockTests(unittest.TestCase):
    def test_extraction_retains_legacy_semantics_including_unbounded_python_ticks(self):
        previous = (None, 0, 50, 2**53+7, 2**64-1, 2**100)
        ticks = (None, True, "50", 50., -1, 0, 1, 49, 50, 51, 100,
                 2**53+7, 2**53+57, 2**64-1, 2**100, 2**100+50)
        count = 0
        for period in (1, 7, 50, 999, 1000, 60000):
            for prior, tick, dt in itertools.product(previous, ticks, dt_edges(period)):
                expected = legacy_clock(prior, tick, dt, period)
                actual = observe_cycle_clock(CycleClockState(prior), tick, dt, period)
                self.assertEqual((actual.next_state.previous_tick, actual.now_ms, actual.fault), expected)
                count += 1
        self.assertEqual(count, 12672)

    def test_rejected_forward_dt_and_gap_advance_anchor_but_duplicate_and_invalid_do_not(self):
        state = CycleClockState()
        ticks = (0, 50, 50, None, 150, 200)
        dts = (100., .05, 100., 100., .05, .05)
        expected = ((0, "guard_period_mismatch"), (50, None),
                    (50, "nonmonotonic_cycle_timestamp"), (50, "invalid_cycle_timestamp"),
                    (150, "cycle_period_mismatch"), (200, None))
        for tick, dt, wanted in zip(ticks, dts, expected):
            result = observe_cycle_clock(state, tick, dt, 50)
            self.assertEqual((result.next_state.previous_tick, result.fault), wanted)
            state = result.next_state

    def test_invalid_owner_state_and_policy_are_explicit_api_errors(self):
        for period in (True, 0, -1, 1.5, 60001):
            with self.subTest(period=period), self.assertRaises(ValueError):
                observe_cycle_clock(CycleClockState(), 0, .05, period)
        for state in (None, CycleClockState(True), CycleClockState(-1), CycleClockState(50.)):
            with self.subTest(state=state), self.assertRaises(ValueError):
                observe_cycle_clock(state, 0, .05, 50)


if __name__ == "__main__":
    unittest.main()
