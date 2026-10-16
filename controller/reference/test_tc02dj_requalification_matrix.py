"""Offline policy truth table. These are synthetic candidate semantics only."""
import itertools
import unittest

from allocator import AllocationResult
from command_guard import CommandGuardConfig, CommandGuardInput, CommandGuardState
from latch_recovery_experiment import ZERO, experiment_one_step

CFG = CommandGuardConfig(100.0, 0.60, 0.20)
GOOD = AllocationResult((10.0,) * 4, 40.0, 40.0, "ok", None)
BAD = AllocationResult(ZERO, 0.0, 0.0, "fault", "synthetic_allocator_fault")


class CandidateRequalificationTruthTable(unittest.TestCase):
    def test_all_64_latched_input_combinations(self):
        """Clear only on a distinct healthy, low-pedal, brake-released cycle.

        Independent truth-table oracle rather than following the guard's reason
        strings. For all 64 cases, the latched incoming state means no torque.
        """
        for low, brake, comms, sensors, interlock, allocator_ok in itertools.product(
            (False, True), repeat=6
        ):
            with self.subTest(low=low, brake=brake, comms=comms,
                              sensors=sensors, interlock=interlock,
                              allocator_ok=allocator_ok):
                inp = CommandGuardInput(
                    dt_s=0.05, accelerator_fraction=0.10 if low else 0.70,
                    brake_active=brake, critical_comms_ok=comms,
                    sensor_agreement_ok=sensors, external_interlock=interlock,
                )
                r = experiment_one_step(
                    GOOD if allocator_ok else BAD, inp, CFG,
                    CommandGuardState(ZERO, True),
                )
                expected_cleared = low and not brake and comms and sensors and interlock and allocator_ok
                self.assertEqual(r.output_nm, ZERO)
                self.assertEqual(r.next_state.previous_output_nm, ZERO)
                self.assertEqual(r.status, "inhibited")
                self.assertIs(r.next_state.pedal_overlap_latched, not expected_cleared)
                if expected_cleared:
                    self.assertEqual(r.reason, "experiment_requalification_dwell")

    def test_clear_is_not_equivalent_to_permission_to_apply_torque(self):
        """The zero-output clearing observation must precede any torque rise."""
        low = CommandGuardInput(0.05, 0.10, False, True, True, True)
        high = CommandGuardInput(0.05, 0.30, False, True, True, True)
        first = experiment_one_step(GOOD, low, CFG, CommandGuardState(ZERO, True))
        self.assertIs(first.next_state.pedal_overlap_latched, False)
        self.assertEqual(first.output_nm, ZERO)
        second = experiment_one_step(GOOD, high, CFG, first.next_state)
        self.assertEqual(second.output_nm, (5.0,) * 4)
        self.assertIs(second.next_state.pedal_overlap_latched, False)


if __name__ == "__main__":
    unittest.main()
