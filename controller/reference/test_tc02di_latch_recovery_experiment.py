"""Deterministic offline-only counterfactual recovery tests (not vehicle QA)."""
import itertools
import unittest

from allocator import AllocationResult
from command_guard import (
    CommandGuardConfig, CommandGuardInput, CommandGuardState,
    apply_command_guard,
)
from latch_recovery_experiment import (
    MAX_EXPERIMENT_STEPS, ZERO, compare_replays, experiment_one_step,
)

CFG = CommandGuardConfig(100.0, 0.60, 0.20)
CANDIDATE = AllocationResult((10.0,) * 4, 40.0, 40.0, "ok", None)
FAULT = AllocationResult(ZERO, 0.0, 0.0, "fault", "synthetic_stale_input")
START = CommandGuardState(ZERO, True)


def obs(accel=0.1, brake=False, comms=True, sensors=True, interlock=True):
    return CommandGuardInput(0.05, accel, brake, comms, sensors, interlock)


class RequalificationPolicyExperiment(unittest.TestCase):
    def test_counterexample_brake_held(self):
        baseline = apply_command_guard(CANDIDATE, obs(brake=True), CFG, START)
        candidate = experiment_one_step(CANDIDATE, obs(brake=True), CFG, START)
        self.assertEqual(baseline.output_nm, (5.0,) * 4)
        self.assertIs(baseline.next_state.pedal_overlap_latched, False)
        self.assertEqual(candidate.output_nm, ZERO)
        self.assertIs(candidate.next_state.pedal_overlap_latched, True)
        self.assertEqual(candidate.reason, "experiment_requalification_blocked")

    def test_healthy_requalification_adds_zero_output_dwell(self):
        regular = apply_command_guard(CANDIDATE, obs(), CFG, START)
        proposed = experiment_one_step(CANDIDATE, obs(), CFG, START)
        self.assertEqual(regular.output_nm, (5.0,) * 4)
        self.assertEqual(proposed.output_nm, ZERO)
        self.assertIs(proposed.next_state.pedal_overlap_latched, False)
        self.assertEqual(proposed.reason, "experiment_requalification_dwell")

    def test_requalified_next_step_can_produce_rate_limited_torque(self):
        seq = compare_replays((CANDIDATE,) * 2, (obs(), obs(accel=0.3)), CFG, START)
        self.assertEqual([x.baseline.output_nm for x in seq], [(5.0,) * 4, (10.0,) * 4])
        self.assertEqual([x.experimental.output_nm for x in seq], [ZERO, (5.0,) * 4])
        self.assertIs(seq[-1].experimental.next_state.pedal_overlap_latched, False)

    def test_fault_blocks_requalification_even_with_low_accelerator(self):
        for label, candidate, inputs in (
            ("comms", CANDIDATE, obs(comms=False)),
            ("sensors", CANDIDATE, obs(sensors=False)),
            ("interlock", CANDIDATE, obs(interlock=False)),
            ("allocator", FAULT, obs()),
        ):
            with self.subTest(label=label):
                baseline = apply_command_guard(candidate, inputs, CFG, START)
                proposed = experiment_one_step(candidate, inputs, CFG, START)
                self.assertEqual((baseline.output_nm, proposed.output_nm), (ZERO, ZERO))
                self.assertIs(baseline.next_state.pedal_overlap_latched, False)
                self.assertIs(proposed.next_state.pedal_overlap_latched, True)
                self.assertEqual(proposed.status, "inhibited")

    def test_two_cycle_loss_then_healthy_requalification(self):
        seq = compare_replays((CANDIDATE,) * 3,
                              (obs(comms=False), obs(), obs(accel=0.3)), CFG, START)
        self.assertEqual([x.experimental.output_nm for x in seq], [ZERO, ZERO, (5.0,) * 4])
        self.assertEqual([x.experimental.next_state.pedal_overlap_latched for x in seq],
                         [True, False, False])
        self.assertEqual([x.baseline.output_nm for x in seq], [ZERO, (5.0,) * 4, (10.0,) * 4])

    def test_new_overlap_still_uses_baseline_latching(self):
        inp = obs(accel=0.7, brake=True)
        initial = CommandGuardState(ZERO, False)
        self.assertEqual(experiment_one_step(CANDIDATE, inp, CFG, initial),
                         apply_command_guard(CANDIDATE, inp, CFG, initial))
        self.assertIs(experiment_one_step(CANDIDATE, inp, CFG, initial)
                      .next_state.pedal_overlap_latched, True)

    def test_unlatched_passthrough_on_healthy_step(self):
        initial = CommandGuardState(ZERO, False)
        self.assertEqual(experiment_one_step(CANDIDATE, obs(accel=0.3), CFG, initial),
                         apply_command_guard(CANDIDATE, obs(accel=0.3), CFG, initial))

    def test_invalid_latch_provenance_still_inhibits(self):
        r = experiment_one_step(CANDIDATE, obs(), CFG, CommandGuardState(ZERO, 0))
        self.assertEqual((r.output_nm, r.reason), (ZERO, "invalid_pedal_latch_state"))
        self.assertIs(r.next_state.pedal_overlap_latched, True)

    def test_bad_accelerator_cannot_clear_existing_latch(self):
        for bad in (float("nan"), float("inf"), -0.1, 1.1, "0.1", True):
            with self.subTest(bad=repr(bad)):
                r = experiment_one_step(CANDIDATE, obs(accel=bad), CFG, START)
                self.assertEqual(r.output_nm, ZERO)
                self.assertIs(r.next_state.pedal_overlap_latched, True)

    def test_malformed_candidate_cannot_clear_existing_latch(self):
        invalid = AllocationResult(None, 40.0, 40.0, "ok", None)
        r = experiment_one_step(invalid, obs(), CFG, START)
        self.assertEqual((r.output_nm, r.reason), (ZERO, "invalid_candidate_output"))
        self.assertIs(r.next_state.pedal_overlap_latched, True)

    def test_deterministic_replay_and_length_mismatch(self):
        c = (CANDIDATE,) * 4
        i = (obs(brake=True), obs(comms=False), obs(), obs(accel=0.3))
        self.assertEqual(compare_replays(c, i, CFG, START),
                         compare_replays(c, i, CFG, START))
        with self.assertRaisesRegex(ValueError, "length mismatch"):
            compare_replays(c, i[:3], CFG, START)

    def test_infinite_candidate_stream_is_bounded(self):
        count = itertools.count()
        def endless():
            for _ in count:
                yield CANDIDATE
        with self.assertRaisesRegex(ValueError, "4096"):
            compare_replays(endless(), itertools.repeat(obs()), CFG, START)
        self.assertEqual(next(count), MAX_EXPERIMENT_STEPS + 1)

    def test_large_but_in_range_replay(self):
        seq = compare_replays(itertools.repeat(CANDIDATE, MAX_EXPERIMENT_STEPS),
                              itertools.repeat(obs(), MAX_EXPERIMENT_STEPS), CFG, START)
        self.assertEqual(len(seq), MAX_EXPERIMENT_STEPS)
        self.assertEqual(seq[0].experimental.output_nm, ZERO)
        self.assertEqual(seq[1].experimental.output_nm, (5.0,) * 4)


if __name__ == "__main__":
    unittest.main()
