"""TC-02DD: synthetic command-guard wheel-vector container validation.

These are malformed Python replay records, not actual vehicle frames or MCU tests.
"""
from __future__ import annotations

import unittest
from dataclasses import replace

from allocator import AllocationResult
from command_guard import (
    CommandGuardConfig, CommandGuardInput, CommandGuardState,
    apply_command_guard, replay_guard,
)

CFG = CommandGuardConfig(100.0, 0.60, 0.20)
INP = CommandGuardInput(0.05, 0.30, False, True, True, True)
GOOD = AllocationResult((2.0,) * 4, 8.0, 8.0, "ok", None)
ZERO = (0.0,) * 4
STATE = CommandGuardState(ZERO)


class PoisonVector:
    def __len__(self):
        raise AssertionError("do not inspect arbitrary vector __len__")
    def __iter__(self):
        raise AssertionError("do not iterate arbitrary vector")


class VectorShapeTests(unittest.TestCase):
    def assert_inhibited(self, *, state=STATE, candidate=GOOD, reason):
        res = apply_command_guard(candidate, INP, CFG, state)
        self.assertEqual(res.status, "inhibited")
        self.assertEqual(res.output_nm, ZERO)
        self.assertEqual(res.next_state.previous_output_nm, ZERO)
        self.assertEqual(res.reason, reason)
        return res

    def test_previous_none(self):
        self.assert_inhibited(state=CommandGuardState(None), reason="invalid_previous_output")

    def test_previous_scalar(self):
        self.assert_inhibited(state=CommandGuardState(1.0), reason="invalid_previous_output")

    def test_previous_generator(self):
        self.assert_inhibited(state=CommandGuardState((x for x in [1.0] * 4)), reason="invalid_previous_output")

    def test_previous_raw_bytes(self):
        self.assert_inhibited(state=CommandGuardState(bytes([1] * 4)), reason="invalid_previous_output")

    def test_previous_mapping(self):
        self.assert_inhibited(state=CommandGuardState({0: 0.0, 1: 1.0, 2: 2.0, 3: 3.0}), reason="invalid_previous_output")

    def test_previous_poison_is_not_inspected(self):
        self.assert_inhibited(state=CommandGuardState(PoisonVector()), reason="invalid_previous_output")

    def test_candidate_none(self):
        self.assert_inhibited(candidate=replace(GOOD, wheel_torque_nm=None), reason="invalid_candidate_output")

    def test_candidate_scalar(self):
        self.assert_inhibited(candidate=replace(GOOD, wheel_torque_nm=2.0), reason="invalid_candidate_output")

    def test_candidate_generator(self):
        self.assert_inhibited(candidate=replace(GOOD, wheel_torque_nm=(x for x in [2.0] * 4)), reason="invalid_candidate_output")

    def test_candidate_raw_bytes(self):
        self.assert_inhibited(candidate=replace(GOOD, wheel_torque_nm=bytes([2] * 4)), reason="invalid_candidate_output")

    def test_candidate_mapping(self):
        self.assert_inhibited(candidate=replace(GOOD, wheel_torque_nm={0: 0.0, 1: 1.0, 2: 2.0, 3: 3.0}), reason="invalid_candidate_output")

    def test_candidate_poison_is_not_inspected(self):
        self.assert_inhibited(candidate=replace(GOOD, wheel_torque_nm=PoisonVector()), reason="invalid_candidate_output")

    def test_ordinary_list_and_tuple_still_accepted(self):
        for cls in (list, tuple):
            with self.subTest(cls=cls.__name__):
                state = CommandGuardState(cls([1.0] * 4))
                candidate = replace(GOOD, wheel_torque_nm=cls([2.0] * 4))
                result = apply_command_guard(candidate, INP, CFG, state)
                self.assertEqual(result.output_nm, (2.0,) * 4)
                self.assertEqual(result.status, "ok")
                self.assertIsNone(result.reason)

    def test_bad_replay_step_does_not_poison_next_step(self):
        candidates = [replace(GOOD, wheel_torque_nm=None), GOOD]
        inputs = [INP, INP]
        res1 = replay_guard(candidates, inputs, CFG, STATE)
        res2 = replay_guard(candidates, inputs, CFG, STATE)
        self.assertEqual(res1, res2)
        self.assertEqual(res1[0].reason, "invalid_candidate_output")
        self.assertEqual(res1[0].output_nm, ZERO)
        self.assertEqual(res1[1].output_nm, (2.0,) * 4)
        self.assertEqual(res1[1].status, "ok")


if __name__ == "__main__":
    unittest.main()
