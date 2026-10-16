"""TC-02DA: fail-closed synthetic command-guard numeric-domain regression.

No real EV data, CAN signals, timing claims or firmware assertions.
"""
from __future__ import annotations

import math
import unittest
from dataclasses import replace

from allocator import AllocationResult
from command_guard import (
    CommandGuardConfig,
    CommandGuardInput,
    CommandGuardState,
    apply_command_guard,
    replay_guard,
)

TOO_LARGE_FOR_FLOAT = 10 ** 400
CFG = CommandGuardConfig(100.0, 0.6, 0.2)
INP = CommandGuardInput(0.05, 0.3, False, True, True, True)
STATE = CommandGuardState((0.0,) * 4)
CANDIDATE = AllocationResult((4.0,) * 4, 16.0, 16.0, "ok", None)
ZERO = (0.0,) * 4


class NumericDomainTests(unittest.TestCase):
    def assert_inhibits(self, expected_reason, *, candidate=CANDIDATE, inp=INP, cfg=CFG, state=STATE):
        observed = apply_command_guard(candidate, inp, cfg, state)
        self.assertEqual(observed.status, "inhibited")
        self.assertEqual(observed.reason, expected_reason)
        self.assertEqual(observed.output_nm, ZERO)
        self.assertEqual(observed.next_state.previous_output_nm, ZERO)

    def test_large_integer_rate_fails_closed(self):
        self.assert_inhibits("invalid_max_rise_rate", cfg=replace(CFG, max_rise_nm_per_s=TOO_LARGE_FOR_FLOAT))

    def test_large_negative_integer_rate_fails_closed(self):
        self.assert_inhibits("invalid_max_rise_rate", cfg=replace(CFG, max_rise_nm_per_s=-TOO_LARGE_FOR_FLOAT))

    def test_large_integer_trip_threshold_fails_closed(self):
        self.assert_inhibits("invalid_pedal_threshold", cfg=replace(CFG, pedal_overlap_trip_fraction=TOO_LARGE_FOR_FLOAT))

    def test_large_integer_clear_threshold_fails_closed(self):
        self.assert_inhibits("invalid_pedal_threshold", cfg=replace(CFG, pedal_clear_fraction=TOO_LARGE_FOR_FLOAT))

    def test_large_integer_dt_fails_closed(self):
        self.assert_inhibits("invalid_dt", inp=replace(INP, dt_s=TOO_LARGE_FOR_FLOAT))

    def test_large_integer_accelerator_fails_closed(self):
        self.assert_inhibits("invalid_accelerator_fraction", inp=replace(INP, accelerator_fraction=TOO_LARGE_FOR_FLOAT))

    def test_large_integer_previous_state_fails_closed(self):
        self.assert_inhibits("invalid_previous_output", state=CommandGuardState((TOO_LARGE_FOR_FLOAT, 0.0, 0.0, 0.0)))

    def test_large_integer_wheel_command_fails_closed(self):
        self.assert_inhibits("invalid_candidate_output", candidate=replace(CANDIDATE, wheel_torque_nm=(TOO_LARGE_FOR_FLOAT, 4., 4., 4.)))

    def test_large_integer_delivered_value_fails_closed(self):
        self.assert_inhibits("invalid_candidate_delivered", candidate=replace(CANDIDATE, delivered_nm=TOO_LARGE_FOR_FLOAT))

    def test_finite_factors_but_overflowed_rate_step_fails_closed(self):
        self.assert_inhibits("invalid_rise_step", cfg=replace(CFG, max_rise_nm_per_s=1e308), inp=replace(INP, dt_s=2.0))

    def test_valid_integer_rate_and_dt_still_cap(self):
        cfg = replace(CFG, max_rise_nm_per_s=3)
        inp = replace(INP, dt_s=1)
        result = apply_command_guard(CANDIDATE, inp, cfg, STATE)
        self.assertEqual(result.output_nm, (3.0,) * 4)
        self.assertEqual(result.reason, "rise_rate_limit")

    def test_nonfinite_float_remains_invalid(self):
        for bad in (math.nan, math.inf, -math.inf):
            with self.subTest(bad=repr(bad)):
                self.assert_inhibits("invalid_dt", inp=replace(INP, dt_s=bad))

    def test_boolean_remains_invalid_for_numeric_field(self):
        self.assert_inhibits("invalid_accelerator_fraction", inp=replace(INP, accelerator_fraction=True))

    def test_replay_recovers_deterministically_after_bad_dt(self):
        inputs = [replace(INP, dt_s=TOO_LARGE_FOR_FLOAT), INP, INP]
        expected = replay_guard([CANDIDATE] * 3, inputs, CFG, STATE)
        repeated = replay_guard([CANDIDATE] * 3, inputs, CFG, STATE)
        self.assertEqual(expected, repeated)
        self.assertEqual([r.reason for r in expected], ["invalid_dt", None, None])
        self.assertEqual(expected[0].output_nm, ZERO)
        self.assertEqual(expected[1].output_nm, (4.0,) * 4)

    def test_ordinary_rate_limit_unchanged(self):
        result = apply_command_guard(CANDIDATE, INP, CFG, STATE)
        self.assertEqual(result.output_nm, (4.0,) * 4)
        self.assertEqual(result.reason, None)


if __name__ == "__main__":
    unittest.main()
