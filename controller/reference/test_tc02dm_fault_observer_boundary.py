"""TC-02DM: malformed synthetic allocator results must not crash fault-state replay.

Scenario-only offline tests; not native vehicle or safety-system testing.
"""
import json
import unittest
from allocator import AllocationResult
from fault_state import FaultPolicy, FaultSnapshot, observe_fault_state, replay_fault_states, INHIBITED, READY, RECOVERY_PENDING


GOOD = AllocationResult((10.0,)*4, 40.0, 40.0, "ok", None)
ZERO = (0.0,)*4


def bad(**changes):
    values = dict(wheel_torque_nm=(10.0,)*4, requested_nm=40.0,
                  delivered_nm=40.0, status="ok", fault=None)
    values.update(changes)
    return AllocationResult(**values)


class MalformedObservationBoundaryTests(unittest.TestCase):
    def check_inhibited_json(self, candidate):
        snapshot, event = observe_fault_state(FaultSnapshot(), candidate,
                                               FaultPolicy(2), sequence=0)
        self.assertEqual(snapshot.state, INHIBITED)
        self.assertFalse(event.reference_gate_allowed)
        self.assertEqual(event.reason, "invalid_allocator_result")
        self.assertEqual(len(event.wheel_torque_nm), 4)
        self.assertTrue(all(type(x) is float for x in event.wheel_torque_nm))
        blob = json.dumps(event.as_record(), allow_nan=False, sort_keys=True)
        self.assertIn('"reason": "invalid_allocator_result"', blob)
        return event

    def test_unhashable_statuses_fail_closed_and_log(self):
        for status in ([], {}, set(), bytearray(b"ok")):
            with self.subTest(kind=type(status).__name__):
                e = self.check_inhibited_json(bad(status=status))
                self.assertEqual(e.allocator_status, "invalid_status")

    def test_status_comparison_spoof_fails_closed(self):
        class PretendOK:
            def __hash__(self): return hash("ok")
            def __eq__(self, other): return other == "ok"
        e = self.check_inhibited_json(bad(status=PretendOK()))
        self.assertEqual(e.allocator_status, "invalid_status")

    def test_arbitrary_precision_integers_fail_closed_without_conversion_crash(self):
        huge = 10**400
        for item in (bad(requested_nm=huge), bad(delivered_nm=huge),
                     bad(wheel_torque_nm=(10.0, 10.0, huge, 10.0))):
            with self.subTest(field=("request" if item.requested_nm == huge else
                                     "delivery" if item.delivered_nm == huge else "wheel")):
                self.check_inhibited_json(item)

    def test_invalid_vectors_fail_closed_and_log_fixed_shape(self):
        for item in (bad(wheel_torque_nm=None), bad(wheel_torque_nm=7),
                     bad(wheel_torque_nm=(10.0,)*3), bad(wheel_torque_nm=b"1234")):
            with self.subTest(kind=type(item.wheel_torque_nm).__name__):
                e = self.check_inhibited_json(item)
                self.assertEqual(e.wheel_torque_nm, ZERO)

    def test_invalid_fault_field_preserves_inhibit_with_serializable_event(self):
        e = self.check_inhibited_json(bad(fault={"bad"}))
        self.assertIsNone(e.allocator_fault)

    def test_invalid_allocation_object_fails_closed(self):
        e = self.check_inhibited_json(None)
        self.assertEqual((e.allocator_status, e.requested_nm, e.delivered_nm),
                         ("invalid_type", 0.0, 0.0))

    def test_unhashable_snapshot_state_raises_value_error(self):
        with self.assertRaisesRegex(ValueError, "snapshot state"):
            observe_fault_state(FaultSnapshot([], 0, 0), GOOD, FaultPolicy(2), sequence=0)

    def test_valid_replay_and_fault_recovery_unchanged(self):
        fault = bad(wheel_torque_nm=ZERO, requested_nm=0.0, delivered_nm=0.0,
                    status="fault", fault="stale_input")
        sample = (GOOD, fault, GOOD, GOOD)
        first = replay_fault_states(sample, FaultPolicy(2))
        second = replay_fault_states(sample, FaultPolicy(2))
        self.assertEqual(first, second)
        self.assertEqual([e.next_state for e in first],
                         [READY, INHIBITED, RECOVERY_PENDING, READY])
        self.assertEqual([e.reference_gate_allowed for e in first],
                         [True, False, False, True])


if __name__ == "__main__":
    unittest.main()
