"""Synthetic boolean-flag validation for reference torque allocator, not firmware."""
from __future__ import annotations

import unittest
from dataclasses import replace

from allocator import AllocationInput, AllocatorConfig, allocate_propulsive_torque, replay

CFG = AllocatorConfig(max_input_age_ms=20)


def sample() -> AllocationInput:
    return AllocationInput(
        now_ms=100,
        input_timestamp_ms=100,
        request_nm=40.0,
        wheel_limits_nm=(20.0,) * 4,
        wheel_enabled=(True,) * 4,
        external_interlock=True,
    )


class BooleanFlagValidationTests(unittest.TestCase):
    def check_zero_fault(self, inp: AllocationInput, reason: str) -> None:
        output = allocate_propulsive_torque(inp, CFG)
        self.assertEqual(output.status, "fault")
        self.assertEqual(output.fault, reason)
        self.assertEqual(output.delivered_nm, 0.0)
        self.assertEqual(output.wheel_torque_nm, (0.0,) * 4)

    def test_explicit_true_interlock_and_bool_wheels_unchanged(self):
        output = allocate_propulsive_torque(sample(), CFG)
        self.assertEqual(output.status, "ok")
        self.assertEqual(output.wheel_torque_nm, (10.0,) * 4)

    def test_explicit_false_interlock_keeps_existing_fault(self):
        self.check_zero_fault(replace(sample(), external_interlock=False),
                              "external_interlock_open")

    def test_valid_disabled_wheel_still_redistributes(self):
        inp = replace(sample(), wheel_enabled=(False, True, True, True))
        output = allocate_propulsive_torque(inp, CFG)
        self.assertEqual(output.wheel_torque_nm[0], 0.0)
        self.assertAlmostEqual(output.delivered_nm, 40.0)

    def test_nonempty_string_false_does_not_open_interlock(self):
        self.check_zero_fault(replace(sample(), external_interlock="False"),
                              "invalid_external_interlock")

    def test_numeric_true_interlock_rejected(self):
        self.check_zero_fault(replace(sample(), external_interlock=1),
                              "invalid_external_interlock")

    def test_numeric_false_interlock_rejected_instead_of_silent_coercion(self):
        self.check_zero_fault(replace(sample(), external_interlock=0),
                              "invalid_external_interlock")

    def test_none_interlock_rejected_as_invalid_type(self):
        self.check_zero_fault(replace(sample(), external_interlock=None),
                              "invalid_external_interlock")

    def test_each_nonempty_false_string_wheel_flag_rejected(self):
        for index in range(4):
            with self.subTest(wheel=index):
                flags = [True] * 4
                flags[index] = "False"
                self.check_zero_fault(replace(sample(), wheel_enabled=tuple(flags)),
                                      "invalid_wheel_enabled")

    def test_each_numeric_wheel_flag_rejected(self):
        for index in range(4):
            for replacement in (0, 1):
                with self.subTest(wheel=index, value=replacement):
                    flags = [True] * 4
                    flags[index] = replacement
                    self.check_zero_fault(replace(sample(), wheel_enabled=tuple(flags)),
                                          "invalid_wheel_enabled")

    def test_none_wheel_flag_rejected(self):
        self.check_zero_fault(replace(sample(), wheel_enabled=(True, None, True, True)),
                              "invalid_wheel_enabled")

    def test_valid_replay_is_deterministic(self):
        sequence = (sample(), replace(sample(), external_interlock=False),
                    replace(sample(), wheel_enabled=(True, False, True, True)))
        self.assertEqual(replay(sequence, CFG), replay(iter(sequence), CFG))


if __name__ == "__main__":
    unittest.main()
