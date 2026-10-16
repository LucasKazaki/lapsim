from __future__ import annotations

import json
import math
import unittest

from allocator import AllocationResult
from fault_state import (
    FaultPolicy,
    FaultSnapshot,
    INHIBITED,
    LIMITED,
    READY,
    RECOVERY_PENDING,
    observe_fault_state,
    replay_fault_states,
)


def result(status="ok", fault=None, delivered=40.0, outputs=(10.0, 10.0, 10.0, 10.0), requested=40.0):
    return AllocationResult(tuple(outputs), requested, delivered, status, fault)


class FaultStateTests(unittest.TestCase):
    def test_nominal_stays_ready(self):
        events = replay_fault_states([result()], FaultPolicy(2))
        self.assertEqual(events[0].next_state, READY)
        self.assertTrue(events[0].reference_gate_allowed)

    def test_aggregate_saturation_is_limited_not_input_fault(self):
        events = replay_fault_states(
            [result("saturated", "aggregate_limit", 20.0, (5.0, 5.0, 5.0, 5.0))],
            FaultPolicy(2),
        )
        self.assertEqual(events[0].next_state, LIMITED)
        self.assertTrue(events[0].reference_gate_allowed)
        self.assertEqual(events[0].reason, "aggregate_limit")

    def test_fault_inhibits_immediately(self):
        events = replay_fault_states(
            [result("fault", "stale_input", 0.0, (0.0, 0.0, 0.0, 0.0))],
            FaultPolicy(2),
        )
        self.assertEqual(events[0].next_state, INHIBITED)
        self.assertFalse(events[0].reference_gate_allowed)

    def test_recovery_requires_configured_consecutive_ok_samples(self):
        events = replay_fault_states(
            [
                result("fault", "stale_input", 0.0, (0.0, 0.0, 0.0, 0.0)),
                result(),
                result(),
            ],
            FaultPolicy(2),
        )
        self.assertEqual([e.next_state for e in events], [INHIBITED, RECOVERY_PENDING, READY])
        self.assertEqual([e.reference_gate_allowed for e in events], [False, False, True])

    def test_saturation_does_not_advance_recovery_streak(self):
        events = replay_fault_states(
            [
                result("fault", "stale_input", 0.0, (0.0, 0.0, 0.0, 0.0)),
                result(),
                result("saturated", "aggregate_limit", 20.0, (5.0, 5.0, 5.0, 5.0)),
                result(),
                result(),
            ],
            FaultPolicy(2),
        )
        self.assertEqual(events[2].next_state, RECOVERY_PENDING)
        self.assertEqual(events[2].recovery_streak, 0)
        self.assertEqual(events[4].next_state, READY)

    def test_restart_does_not_clear_persistent_fault(self):
        fault = result("fault", "external_interlock_open", 0.0, (0.0, 0.0, 0.0, 0.0))
        events = replay_fault_states([fault, fault], FaultPolicy(2), restart_before={1})
        self.assertEqual(events[1].generation, 1)
        self.assertEqual(events[1].next_state, INHIBITED)
        self.assertFalse(events[1].reference_gate_allowed)

    def test_restart_with_healthy_input_reenters_through_recovery(self):
        events = replay_fault_states([result(), result(), result()], FaultPolicy(2), restart_before={1})
        self.assertEqual(events[1].next_state, RECOVERY_PENDING)
        self.assertFalse(events[1].reference_gate_allowed)
        self.assertEqual(events[2].next_state, READY)
        self.assertTrue(events[2].reference_gate_allowed)

    def test_replay_is_deterministic(self):
        samples = [
            result(),
            result("fault", "stale_input", 0.0, (0.0, 0.0, 0.0, 0.0)),
            result(),
            result(),
        ]
        first = replay_fault_states(samples, FaultPolicy(2), restart_before={2})
        second = replay_fault_states(samples, FaultPolicy(2), restart_before={2})
        self.assertEqual(first, second)

    def test_event_records_are_strict_json_serializable(self):
        events = replay_fault_states([result()], FaultPolicy(2))
        encoded = json.dumps([e.as_record() for e in events], allow_nan=False, sort_keys=True)
        self.assertIn('"next_state": "ready"', encoded)

    def test_nonfinite_allocator_result_fails_closed_in_supervisor(self):
        malformed = result("ok", None, math.nan, (math.nan, 0.0, 0.0, 0.0))
        events = replay_fault_states([malformed], FaultPolicy(2))
        self.assertEqual(events[0].next_state, INHIBITED)
        self.assertEqual(events[0].reason, "invalid_allocator_result")
        self.assertFalse(events[0].reference_gate_allowed)
        json.dumps(events[0].as_record(), allow_nan=False)

    def test_unknown_allocator_status_fails_closed(self):
        malformed = result("mystery", None)
        events = replay_fault_states([malformed], FaultPolicy(2))
        self.assertEqual(events[0].next_state, INHIBITED)
        self.assertEqual(events[0].reason, "invalid_allocator_result")

    def test_malformed_allocator_scalar_types_fail_closed(self):
        malformed = result("ok", None, 4.0, (1.0, "bad", 1.0, 1.0))
        events = replay_fault_states([malformed], FaultPolicy(2))
        self.assertEqual(events[0].next_state, INHIBITED)
        self.assertEqual(events[0].reason, "invalid_allocator_result")
        self.assertFalse(events[0].reference_gate_allowed)

    def test_boolean_allocator_value_fails_closed(self):
        malformed = result("ok", None, 3.0, (True, 1.0, 1.0, 0.0))
        events = replay_fault_states([malformed], FaultPolicy(2))
        self.assertEqual(events[0].next_state, INHIBITED)
        self.assertEqual(events[0].reason, "invalid_allocator_result")

    def test_malformed_fault_code_fails_closed(self):
        malformed = result("fault", 123, 0.0, (0.0, 0.0, 0.0, 0.0))
        events = replay_fault_states([malformed], FaultPolicy(2))
        self.assertEqual(events[0].next_state, INHIBITED)
        self.assertEqual(events[0].reason, "invalid_allocator_result")

    def test_invalid_snapshot_is_rejected(self):
        healthy = result()
        bad_snapshots = (
            FaultSnapshot("mystery", 0, 0),
            FaultSnapshot(READY, -1, 0),
            FaultSnapshot(READY, 0, -1),
            FaultSnapshot(READY, True, 0),
            FaultSnapshot(READY, 0, True),
        )
        for snapshot in bad_snapshots:
            with self.subTest(snapshot=snapshot):
                with self.assertRaises(ValueError):
                    observe_fault_state(snapshot, healthy, FaultPolicy(2), sequence=0)

    def test_sequence_and_restart_types_are_rejected(self):
        with self.assertRaises(ValueError):
            observe_fault_state(FaultSnapshot(), result(), FaultPolicy(2), sequence=True)
        with self.assertRaises(ValueError):
            observe_fault_state(
                FaultSnapshot(), result(), FaultPolicy(2), sequence=0, restart_requested=1
            )

    def test_invalid_policy_is_rejected(self):
        for value in (0, -1, True, 1.5):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    FaultPolicy(value)  # type: ignore[arg-type]

    def test_invalid_restart_indices_are_rejected(self):
        with self.assertRaises(ValueError):
            replay_fault_states([result()], FaultPolicy(2), restart_before={-1})
        with self.assertRaises(ValueError):
            replay_fault_states([result()], FaultPolicy(2), restart_before={1})


if __name__ == "__main__":
    unittest.main()
