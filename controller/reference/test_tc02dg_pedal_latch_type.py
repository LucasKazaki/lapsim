"""TC-02DG synthetic guard-state provenance: malformed latch must inhibit.

These are malformed offline replay/state values, not team vehicle observations.
The proposed policy latches an invalid state True until a valid low-pedal
observation clears it; acceptance requires independent team review.
"""
import unittest

from allocator import AllocationResult
from command_guard import (
    CommandGuardConfig, CommandGuardInput, CommandGuardState,
    apply_command_guard, replay_guard,
)

CFG = CommandGuardConfig(100.0, 0.60, 0.20)
NORMAL = CommandGuardInput(0.05, 0.30, False, True, True, True)
CLEAR = CommandGuardInput(0.05, 0.10, False, True, True, True)
CANDIDATE = AllocationResult((10.0,) * 4, 40.0, 40.0, 'ok', None)
ZERO = (0.0,) * 4


class PedalLatchTypeTests(unittest.TestCase):
    def test_malformed_latch_values_always_inhibit_and_preserve_conservative_latch(self):
        for bad in (None, 0, 1, '', 'False', [], {}, (False,)):
            with self.subTest(bad=repr(bad)):
                initial = CommandGuardState(ZERO, bad)
                result = apply_command_guard(CANDIDATE, NORMAL, CFG, initial)
                self.assertEqual((result.status, result.reason, result.output_nm),
                                 ('inhibited', 'invalid_pedal_latch_state', ZERO))
                self.assertIs(result.next_state.pedal_overlap_latched, True)

    def test_invalid_latch_fails_closed_even_when_bad_config_precedes_normal_validation(self):
        bad_cfg = CommandGuardConfig(0.0, 0.60, 0.20)
        result = apply_command_guard(CANDIDATE, NORMAL, bad_cfg, CommandGuardState(ZERO, 0))
        self.assertEqual((result.status, result.reason, result.output_nm),
                         ('inhibited', 'invalid_pedal_latch_state', ZERO))
        self.assertIs(result.next_state.pedal_overlap_latched, True)

    def test_invalid_latch_requires_valid_low_pedal_requalification(self):
        initial = CommandGuardState(ZERO, False)  # healthy control reference
        regular = apply_command_guard(CANDIDATE, NORMAL, CFG, initial)
        self.assertEqual(regular.output_nm, (5.0,) * 4)
        bad_initial = CommandGuardState(ZERO, 0)
        replay = replay_guard((CANDIDATE,) * 3, (NORMAL, NORMAL, CLEAR), CFG, bad_initial)
        self.assertEqual([r.reason for r in replay],
                         ['invalid_pedal_latch_state', 'brake_accelerator_overlap', 'rise_rate_limit'])
        self.assertEqual([r.output_nm for r in replay], [ZERO, ZERO, (5.0,) * 4])
        self.assertEqual([r.next_state.pedal_overlap_latched for r in replay],
                         [True, True, False])

    def test_valid_boolean_latch_behavior_unchanged(self):
        for prior in (False, True):
            with self.subTest(prior=prior):
                r = apply_command_guard(CANDIDATE, NORMAL, CFG, CommandGuardState(ZERO, prior))
                if prior:
                    self.assertEqual((r.status, r.reason, r.output_nm),
                                     ('inhibited', 'brake_accelerator_overlap', ZERO))
                else:
                    self.assertEqual((r.status, r.reason, r.output_nm),
                                     ('limited', 'rise_rate_limit', (5.0,) * 4))
                self.assertIs(r.next_state.pedal_overlap_latched, prior)

    def test_fault_output_stays_zero_and_latched_on_invalid_state(self):
        fault_candidate = AllocationResult(ZERO, 0.0, 0.0, 'fault', 'stale_input')
        r = apply_command_guard(fault_candidate, NORMAL, CFG, CommandGuardState((2.0,) * 4, 'bad'))
        self.assertEqual(r.output_nm, ZERO)
        self.assertEqual(r.reason, 'invalid_pedal_latch_state')
        self.assertIs(r.next_state.pedal_overlap_latched, True)

    def test_replay_with_bad_latch_is_deterministic(self):
        start = CommandGuardState(ZERO, 1)
        a = replay_guard((CANDIDATE,) * 3, (NORMAL, CLEAR, NORMAL), CFG, start)
        b = replay_guard((CANDIDATE,) * 3, (NORMAL, CLEAR, NORMAL), CFG, start)
        self.assertEqual(a, b)
        self.assertEqual([r.reason for r in a],
                         ['invalid_pedal_latch_state', 'rise_rate_limit', None])


if __name__ == '__main__':
    unittest.main()
