import math
import unittest

from allocator import AllocationResult
from command_guard import (
    CommandGuardConfig,
    CommandGuardInput,
    CommandGuardState,
    apply_command_guard,
    replay_guard,
)


CFG = CommandGuardConfig(
    max_rise_nm_per_s=100.0,
    pedal_overlap_trip_fraction=0.60,
    pedal_clear_fraction=0.20,
)


def candidate(values=(10.0, 10.0, 10.0, 10.0), status="ok", fault=None):
    delivered = sum(values) if all(math.isfinite(v) for v in values) else 0.0
    return AllocationResult(tuple(values), 40.0, delivered, status, fault)


def inp(**kwargs):
    values = dict(
        dt_s=0.05,
        accelerator_fraction=0.30,
        brake_active=False,
        critical_comms_ok=True,
        sensor_agreement_ok=True,
        external_interlock=True,
    )
    values.update(kwargs)
    return CommandGuardInput(**values)


class CommandGuardTests(unittest.TestCase):
    def test_nominal_upward_slew_is_bounded(self):
        result = apply_command_guard(candidate(), inp(), CFG, CommandGuardState((0.0,) * 4))
        self.assertEqual(result.output_nm, (5.0, 5.0, 5.0, 5.0))
        self.assertEqual(result.status, "limited")
        self.assertEqual(result.reason, "rise_rate_limit")

    def test_decrease_is_immediate_not_rate_limited(self):
        state = CommandGuardState((20.0, 20.0, 20.0, 20.0))
        result = apply_command_guard(candidate((4.0, 5.0, 6.0, 7.0)), inp(dt_s=0.001), CFG, state)
        self.assertEqual(result.output_nm, (4.0, 5.0, 6.0, 7.0))
        self.assertEqual(result.status, "ok")

    def test_allocator_fault_bypasses_ramp_to_zero(self):
        state = CommandGuardState((12.0, 12.0, 12.0, 12.0))
        result = apply_command_guard(candidate((0.0,) * 4, "fault", "stale_input"), inp(), CFG, state)
        self.assertEqual(result.output_nm, (0.0,) * 4)
        self.assertEqual(result.reason, "allocator_fault")

    def test_external_interlock_bypasses_ramp_to_zero(self):
        state = CommandGuardState((12.0,) * 4)
        result = apply_command_guard(candidate(), inp(external_interlock=False), CFG, state)
        self.assertEqual(result.output_nm, (0.0,) * 4)
        self.assertEqual(result.reason, "external_interlock_open")

    def test_communication_loss_inhibits(self):
        result = apply_command_guard(candidate(), inp(critical_comms_ok=False), CFG, CommandGuardState((2.0,) * 4))
        self.assertEqual(result.status, "inhibited")
        self.assertEqual(result.reason, "critical_communication_loss")
        self.assertEqual(result.output_nm, (0.0,) * 4)

    def test_sensor_disagreement_inhibits(self):
        result = apply_command_guard(candidate(), inp(sensor_agreement_ok=False), CFG, CommandGuardState((2.0,) * 4))
        self.assertEqual(result.status, "inhibited")
        self.assertEqual(result.reason, "sensor_disagreement")

    def test_brake_accelerator_overlap_latches(self):
        result = apply_command_guard(
            candidate(), inp(accelerator_fraction=0.80, brake_active=True), CFG, CommandGuardState((2.0,) * 4)
        )
        self.assertTrue(result.next_state.pedal_overlap_latched)
        self.assertEqual(result.reason, "brake_accelerator_overlap")
        self.assertEqual(result.output_nm, (0.0,) * 4)

    def test_overlap_remains_latched_after_brake_release_until_clear(self):
        latched = CommandGuardState((0.0,) * 4, True)
        still = apply_command_guard(candidate(), inp(accelerator_fraction=0.30, brake_active=False), CFG, latched)
        self.assertTrue(still.next_state.pedal_overlap_latched)
        self.assertEqual(still.reason, "brake_accelerator_overlap")
        clear = apply_command_guard(candidate(), inp(accelerator_fraction=0.10, brake_active=False), CFG, still.next_state)
        self.assertFalse(clear.next_state.pedal_overlap_latched)
        self.assertNotEqual(clear.status, "inhibited")

    def test_nonfinite_accelerator_inhibits(self):
        result = apply_command_guard(candidate(), inp(accelerator_fraction=float("nan")), CFG, CommandGuardState((0.0,) * 4))
        self.assertEqual(result.reason, "invalid_accelerator_fraction")
        self.assertEqual(result.output_nm, (0.0,) * 4)

    def test_invalid_dt_inhibits(self):
        result = apply_command_guard(candidate(), inp(dt_s=0.0), CFG, CommandGuardState((1.0,) * 4))
        self.assertEqual(result.reason, "invalid_dt")
        self.assertEqual(result.output_nm, (0.0,) * 4)

    def test_nonfinite_candidate_inhibits(self):
        bad = AllocationResult((1.0, float("inf"), 1.0, 1.0), 4.0, 0.0, "ok", None)
        result = apply_command_guard(bad, inp(), CFG, CommandGuardState((1.0,) * 4))
        self.assertEqual(result.reason, "invalid_candidate_output")
        self.assertEqual(result.output_nm, (0.0,) * 4)

    def test_candidate_sum_mismatch_inhibits(self):
        bad = AllocationResult((1.0, 1.0, 1.0, 1.0), 4.0, 3.0, "ok", None)
        result = apply_command_guard(bad, inp(), CFG, CommandGuardState((1.0,) * 4))
        self.assertEqual(result.reason, "candidate_sum_mismatch")

    def test_aggregate_saturation_remains_limited(self):
        result = apply_command_guard(candidate((2.0,) * 4, "saturated", "aggregate_limit"), inp(), CFG, CommandGuardState((2.0,) * 4))
        self.assertEqual(result.status, "limited")
        self.assertEqual(result.reason, "aggregate_limit")

    def test_invalid_config_fails_closed(self):
        bad_cfg = CommandGuardConfig(0.0, 0.6, 0.2)
        result = apply_command_guard(candidate(), inp(), bad_cfg, CommandGuardState((1.0,) * 4))
        self.assertEqual(result.status, "inhibited")
        self.assertEqual(result.reason, "invalid_max_rise_rate")

    def test_deterministic_replay(self):
        candidates = [candidate((10.0,) * 4), candidate((20.0,) * 4), candidate((5.0,) * 4)]
        inputs = [inp(), inp(), inp()]
        initial = CommandGuardState((0.0,) * 4)
        self.assertEqual(
            replay_guard(candidates, inputs, CFG, initial),
            replay_guard(candidates, inputs, CFG, initial),
        )

    def test_replay_length_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            replay_guard([candidate()], [], CFG, CommandGuardState((0.0,) * 4))


if __name__ == "__main__":
    unittest.main()
