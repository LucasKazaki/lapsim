"""TC-02CY bounded-stream contract; portable synthetic-reference tests."""
from __future__ import annotations

import itertools
import unittest

from allocator import AllocationResult, MAX_OFFLINE_REPLAY_STEPS
from bounded_guard_replay import replay_guard_bounded
from command_guard import (
    CommandGuardConfig, CommandGuardInput, CommandGuardState, replay_guard,
)

LIMIT = MAX_OFFLINE_REPLAY_STEPS
CFG = CommandGuardConfig(100.0, 0.6, 0.2)
STATE = CommandGuardState((0.0,) * 4)
CANDIDATE = AllocationResult((4.0,) * 4, 16.0, 16.0, "ok", None)
BAD_CANDIDATE = AllocationResult((0.0,) * 4, 16.0, 0.0, "fault", "stale_input")
INPUT = CommandGuardInput(.1, .3, False, True, True, True)


class CountedUnbounded:
    def __init__(self, value):
        self.value = value
        self.reads = 0

    def __iter__(self):
        return self

    def __next__(self):
        self.reads += 1
        if self.reads > LIMIT + 1:
            raise AssertionError("iterator over-consumed past overflow sentinel")
        return self.value


class BoundedGuardReplayTests(unittest.TestCase):
    def test_empty_streams(self):
        self.assertEqual(replay_guard_bounded(iter(()), iter(()), CFG, STATE), ())

    def test_finite_replay_matches_existing_reference(self):
        candidates = [CANDIDATE, BAD_CANDIDATE, CANDIDATE]
        inputs = [INPUT, INPUT, INPUT]
        self.assertEqual(
            replay_guard_bounded(iter(candidates), iter(inputs), CFG, STATE),
            replay_guard(candidates, inputs, CFG, STATE),
        )

    def test_determinism(self):
        candidates = (CANDIDATE, BAD_CANDIDATE, CANDIDATE)
        inputs = (INPUT,) * 3
        self.assertEqual(replay_guard_bounded(candidates, inputs, CFG, STATE),
                         replay_guard_bounded(candidates, inputs, CFG, STATE))

    def test_fault_still_zeroes_without_delayed_ramp(self):
        c = [CANDIDATE, BAD_CANDIDATE]
        result = replay_guard_bounded(c, [INPUT] * 2, CFG, STATE)
        self.assertEqual(result[1].output_nm, (0.0,) * 4)
        self.assertEqual(result[1].reason, "allocator_fault")

    def test_exact_4096_accepted(self):
        result = replay_guard_bounded(itertools.repeat(CANDIDATE, LIMIT),
                                      itertools.repeat(INPUT, LIMIT), CFG, STATE)
        self.assertEqual(len(result), LIMIT)
        self.assertEqual(result[-1].output_nm, (4.0,) * 4)

    def test_candidate_4097_rejected_without_reading_inputs(self):
        sentinel = CountedUnbounded(INPUT)
        with self.assertRaisesRegex(ValueError, "candidates exceed 4096"):
            replay_guard_bounded(itertools.repeat(CANDIDATE, LIMIT + 1),
                                 sentinel, CFG, STATE)
        self.assertEqual(sentinel.reads, 0)

    def test_input_4097_rejected(self):
        with self.assertRaisesRegex(ValueError, "inputs exceed 4096"):
            replay_guard_bounded([CANDIDATE],
                                 itertools.repeat(INPUT, LIMIT + 1), CFG, STATE)

    def test_infinite_candidate_stream_bounded(self):
        stream = CountedUnbounded(CANDIDATE)
        with self.assertRaisesRegex(ValueError, "candidates exceed 4096"):
            replay_guard_bounded(stream, [], CFG, STATE)
        self.assertEqual(stream.reads, LIMIT + 1)

    def test_infinite_input_stream_bounded(self):
        stream = CountedUnbounded(INPUT)
        with self.assertRaisesRegex(ValueError, "inputs exceed 4096"):
            replay_guard_bounded([CANDIDATE], stream, CFG, STATE)
        self.assertEqual(stream.reads, LIMIT + 1)

    def test_length_mismatch_keeps_original_error(self):
        with self.assertRaisesRegex(ValueError, "candidate/input length mismatch"):
            replay_guard_bounded([CANDIDATE, CANDIDATE], [INPUT], CFG, STATE)

    def test_original_direct_replay_has_no_cap_counterexample(self):
        # Finite counterexample only, never feed an infinite iterator to original.
        observed = replay_guard(itertools.repeat(CANDIDATE, LIMIT + 1),
                                itertools.repeat(INPUT, LIMIT + 1), CFG, STATE)
        self.assertEqual(len(observed), LIMIT + 1)

    def test_inputs_not_overconsumed_for_exact_boundary(self):
        class Exact:
            def __init__(self, value):
                self.value = value
                self.reads = 0
            def __iter__(self):
                for _ in range(LIMIT):
                    self.reads += 1
                    yield self.value
        cand, inp = Exact(CANDIDATE), Exact(INPUT)
        self.assertEqual(len(replay_guard_bounded(cand, inp, CFG, STATE)), LIMIT)
        self.assertEqual((cand.reads, inp.reads), (LIMIT, LIMIT))


if __name__ == "__main__":
    unittest.main()
