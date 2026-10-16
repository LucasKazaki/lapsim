"""TC-02BU portable synthetic state-machine tests, not vehicle verification."""
from __future__ import annotations
import math
import random
import unittest

from allocator import AllocationResult
from command_guard import CommandGuardConfig, CommandGuardInput, CommandGuardState, apply_command_guard
from guard_request_contract import apply_request_checked_guard
from guard_overlap_observation import apply_overlap_observed_guard, trusted_overlap_trip

CFG = CommandGuardConfig(1000.0, 0.60, 0.20)
ZERO = CommandGuardState((0.0,) * 4)
BAD = AllocationResult((10.0,)*4, 0.0, 40.0, "ok", None)
GOOD = AllocationResult((10.0,)*4, 40.0, 40.0, "ok", None)

def inp(accel=0.8, brake=True, comms=True, sensors=True):
    return CommandGuardInput(0.1, accel, brake, comms, sensors, True)

class OverlapObservationTests(unittest.TestCase):
    def test_counterexample_fault_then_high_accel_release_then_clear(self):
        first = apply_overlap_observed_guard(BAD, inp(), CFG, ZERO)
        self.assertEqual((first.status, first.reason), ("inhibited", "candidate_exceeds_request"))
        self.assertEqual(first.output_nm, (0.0,)*4)
        self.assertTrue(first.next_state.pedal_overlap_latched)
        second = apply_overlap_observed_guard(GOOD, inp(brake=False), CFG, first.next_state)
        self.assertEqual((second.status, second.reason), ("inhibited", "brake_accelerator_overlap"))
        self.assertTrue(second.next_state.pedal_overlap_latched)
        third = apply_overlap_observed_guard(GOOD, inp(accel=0.1, brake=False), CFG, second.next_state)
        self.assertFalse(third.next_state.pedal_overlap_latched)
        self.assertEqual(third.output_nm, (10.0,)*4)

    def test_malformed_candidate_status_still_records_trusted_trip(self):
        malformed = AllocationResult((10.0,)*4, 40.0, 40.0, "unexpected", None)
        first = apply_overlap_observed_guard(malformed, inp(), CFG, ZERO)
        self.assertEqual((first.output_nm, first.reason), ((0.0,)*4, "invalid_candidate_status"))
        self.assertTrue(first.next_state.pedal_overlap_latched)

    def test_invalid_candidate_vector_still_records_trusted_trip(self):
        malformed = AllocationResult((10.0,)*3, 40.0, 30.0, "ok", None)
        first = apply_overlap_observed_guard(malformed, inp(), CFG, ZERO)
        self.assertEqual(first.reason, "invalid_candidate_output")
        self.assertTrue(first.next_state.pedal_overlap_latched)

    def test_fault_cycle_cannot_clear_latched_state(self):
        s = CommandGuardState((0.0,)*4, True)
        a = apply_overlap_observed_guard(BAD, inp(accel=0.0, brake=False), CFG, s)
        self.assertEqual(a.reason, "candidate_exceeds_request")
        self.assertTrue(a.next_state.pedal_overlap_latched)
        b = apply_overlap_observed_guard(GOOD, inp(accel=0.0, brake=False), CFG, a.next_state)
        self.assertFalse(b.next_state.pedal_overlap_latched)

    def test_invalid_pedal_fraction_does_not_manufacture_latch(self):
        for v in (math.nan, math.inf, -1.0, 1.01, True, "0.8", 10**400):
            with self.subTest(v=repr(v)):
                self.assertFalse(trusted_overlap_trip(inp(accel=v), CFG, ZERO))
                result = apply_overlap_observed_guard(BAD, inp(accel=v), CFG, ZERO)
                self.assertFalse(result.next_state.pedal_overlap_latched)
                self.assertEqual(result.output_nm, (0.0,)*4)

    def test_untrusted_observations_do_not_set_latch(self):
        for kwargs in (dict(comms=False), dict(sensors=False), dict(brake=False)):
            with self.subTest(kwargs=kwargs):
                self.assertFalse(trusted_overlap_trip(inp(**kwargs), CFG, ZERO))
                self.assertFalse(apply_overlap_observed_guard(BAD, inp(**kwargs), CFG, ZERO)
                                 .next_state.pedal_overlap_latched)

    def test_bad_config_does_not_set_latch_on_early_fault(self):
        for cfg in (CommandGuardConfig(0.0, 0.6, 0.2),
                    CommandGuardConfig(1000.0, 0.2, 0.6),
                    CommandGuardConfig(1000.0, math.nan, 0.2)):
            with self.subTest(cfg=repr(cfg)):
                self.assertFalse(trusted_overlap_trip(inp(), cfg, ZERO))
                self.assertFalse(apply_overlap_observed_guard(BAD, inp(), cfg, ZERO)
                                 .next_state.pedal_overlap_latched)

    def test_threshold_boundary_is_inclusive(self):
        self.assertTrue(trusted_overlap_trip(inp(accel=0.6), CFG, ZERO))
        self.assertFalse(trusted_overlap_trip(inp(accel=math.nextafter(0.6, -math.inf)), CFG, ZERO))

    def test_valid_candidate_unchanged_existing_latch_behavior(self):
        for a, b in ((0.8, True), (0.1, True), (0.8, False), (0.2, False)):
            with self.subTest(a=a, b=b):
                expected = apply_request_checked_guard(GOOD, inp(a, b), CFG, ZERO)
                self.assertEqual(apply_overlap_observed_guard(GOOD, inp(a,b), CFG, ZERO), expected)

    def test_valid_fault_candidate_does_not_gain_torque(self):
        fault = AllocationResult((0.0,)*4, 40.0, 0.0, "fault", "stale")
        actual = apply_overlap_observed_guard(fault, inp(), CFG, ZERO)
        self.assertEqual((actual.output_nm, actual.reason), ((0.0,)*4, "allocator_fault"))
        self.assertTrue(actual.next_state.pedal_overlap_latched)

    def test_seeded_good_replay_equivalence_with_published_adapter(self):
        rng = random.Random(20261010)
        for i in range(1000):
            a = rng.choice((0.0, 0.1, 0.2, 0.3, 0.59, 0.6, 0.8, 1.0))
            b = bool(rng.getrandbits(1))
            st = CommandGuardState((0.0,)*4, bool(rng.getrandbits(1)))
            candidate = GOOD
            before = apply_request_checked_guard(candidate, inp(a, b), CFG, st)
            after = apply_overlap_observed_guard(candidate, inp(a, b), CFG, st)
            with self.subTest(i=i): self.assertEqual(before, after)

    def test_original_fault_path_demonstrates_missing_state_transition(self):
        old = apply_request_checked_guard(BAD, inp(), CFG, ZERO)
        self.assertFalse(old.next_state.pedal_overlap_latched)
        corrected = apply_overlap_observed_guard(BAD, inp(), CFG, ZERO)
        self.assertTrue(corrected.next_state.pedal_overlap_latched)

if __name__ == '__main__': unittest.main()
