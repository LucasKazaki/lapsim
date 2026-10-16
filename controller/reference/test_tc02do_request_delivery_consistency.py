"""TC-02DO synthetic allocator-result consistency (not hardware evidence)."""
import json
import unittest

from allocator import (AllocationInput, AllocationResult, AllocatorConfig,
                       allocate_propulsive_torque)
from fault_state import (FaultPolicy, FaultSnapshot, INHIBITED, READY,
                         RECOVERY_PENDING, observe_fault_state, replay_fault_states)


def candidate(request=40.0, delivered=40.0, status="ok", fault=None):
    return AllocationResult((delivered / 4.0,) * 4, request, delivered,
                            status, fault)


class AllocationRequestDeliveryContract(unittest.TestCase):
    def test_success_status_rejects_negative_propulsive_request(self):
        for status in ("ok", "saturated"):
            with self.subTest(status=status):
                result = candidate(request=-40.0, status=status,
                                   fault="aggregate_limit" if status == "saturated" else None)
                state, event = observe_fault_state(FaultSnapshot(), result, FaultPolicy(2), sequence=0)
                self.assertEqual(state.state, INHIBITED)
                self.assertFalse(event.reference_gate_allowed)
                self.assertEqual(event.reason, "invalid_allocator_result")
                json.dumps(event.as_record(), allow_nan=False)

    def test_success_status_rejects_more_delivered_than_requested(self):
        for status in ("ok", "saturated"):
            with self.subTest(status=status):
                state, event = observe_fault_state(
                    FaultSnapshot(), candidate(request=10.0, delivered=40.0,
                                               status=status,
                                               fault="aggregate_limit" if status == "saturated" else None),
                    FaultPolicy(2), sequence=0)
                self.assertEqual(state.state, INHIBITED)
                self.assertFalse(event.reference_gate_allowed)
                self.assertEqual(event.reason, "invalid_allocator_result")

    def test_zero_request_rejects_even_tiny_positive_delivery(self):
        state, event = observe_fault_state(FaultSnapshot(), candidate(request=0.0, delivered=1e-12),
                                           FaultPolicy(2), sequence=0)
        self.assertEqual(state.state, INHIBITED)
        self.assertFalse(event.reference_gate_allowed)

    def test_fault_retains_negative_request_and_precise_reason(self):
        inp = AllocationInput(200, 200, -5.0, (100.0,)*4, (True,)*4, True)
        result = allocate_propulsive_torque(inp, AllocatorConfig(50))
        self.assertEqual(result.status, "fault")
        state, event = observe_fault_state(FaultSnapshot(), result, FaultPolicy(2), sequence=0)
        self.assertEqual(state.state, INHIBITED)
        self.assertEqual(event.reason, "negative_request_unsupported")
        self.assertEqual(event.requested_nm, -5.0)
        self.assertFalse(event.reference_gate_allowed)

    def test_valid_unsaturated_saturated_and_roundoff_examples_stay_accepted(self):
        examples = (
            (candidate(), READY),
            (candidate(request=100.0, delivered=40.0,
                       status="saturated", fault="aggregate_limit"), "limited"),
            (candidate(request=40.0 - 1e-14, delivered=40.0), READY),
            (candidate(request=0.0, delivered=0.0), READY),
        )
        for result, expected in examples:
            with self.subTest(requested=result.requested_nm, status=result.status):
                state, event = observe_fault_state(FaultSnapshot(), result, FaultPolicy(2), sequence=0)
                self.assertEqual(state.state, expected)
                self.assertTrue(event.reference_gate_allowed)

    def test_recovery_and_replay_are_deterministic_after_inconsistent_record(self):
        faulty = candidate(request=10.0, delivered=40.0)
        samples = [faulty, candidate(), candidate()]
        a = replay_fault_states(samples, FaultPolicy(2))
        b = replay_fault_states(samples, FaultPolicy(2))
        self.assertEqual(a, b)
        self.assertEqual([event.next_state for event in a], [INHIBITED, RECOVERY_PENDING, READY])
        self.assertEqual([event.reference_gate_allowed for event in a], [False, False, True])
        json.dumps([e.as_record() for e in a], allow_nan=False, sort_keys=True)


if __name__ == "__main__":
    unittest.main()
