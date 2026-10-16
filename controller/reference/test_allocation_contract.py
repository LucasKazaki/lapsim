"""One acceptance contract for offline allocation consumers; no hardware IO."""
import random
import unittest
from dataclasses import replace

from allocator import AllocationInput, AllocationResult, AllocatorConfig, allocate_propulsive_torque
from command_guard import CommandGuardConfig, CommandGuardInput, CommandGuardState, apply_command_guard
from fault_state import FaultPolicy, FaultSnapshot, observe_fault_state
from guard_request_contract import apply_request_checked_guard, request_contract_fault

GOOD = AllocationResult((10.0,) * 4, 40.0, 40.0, "ok", None)
ZERO = (0.0,) * 4
CFG = CommandGuardConfig(1000.0, 0.6, 0.2)
INP = CommandGuardInput(0.1, 0.3, False, True, True, True)


class AllocationConsumerContractTests(unittest.TestCase):
    def test_contradictory_status_and_fault_never_release_torque(self):
        for item in (
            replace(GOOD, fault="external_interlock_open"),
            replace(GOOD, fault="aggregate_limit"),
            replace(GOOD, status="saturated", fault="stale_input"),
            replace(GOOD, status="saturated", fault=None),
            replace(GOOD, status="fault", fault="stale_input"),
            replace(GOOD, status="fault", wheel_torque_nm=ZERO, delivered_nm=0.0),
        ):
            with self.subTest(status=item.status, fault=item.fault):
                guarded = apply_command_guard(item, INP, CFG, CommandGuardState((12.0,) * 4))
                _, observed = observe_fault_state(FaultSnapshot(), item, FaultPolicy(), sequence=0)
                self.assertEqual(guarded.output_nm, ZERO)
                self.assertEqual(guarded.status, "inhibited")
                self.assertFalse(observed.reference_gate_allowed)
                self.assertIsNotNone(request_contract_fault(item))

    def test_zero_request_rejects_tiny_wheel_delivery_even_with_zero_aggregate(self):
        bad = replace(GOOD, requested_nm=0.0, delivered_nm=0.0, wheel_torque_nm=(1e-12, 0., 0., 0.))
        self.assertEqual(apply_command_guard(bad, INP, CFG, CommandGuardState(ZERO)).output_nm, ZERO)
        self.assertIsNotNone(request_contract_fault(bad))

    def test_request_bound_is_shared_at_small_and_large_magnitudes(self):
        for magnitude in (1e-12, 1.0, 40.0, 1e100):
            bad = replace(GOOD, requested_nm=magnitude, delivered_nm=magnitude * 1.001,
                          wheel_torque_nm=(magnitude * 1.001 / 4,) * 4)
            with self.subTest(magnitude=magnitude):
                self.assertIsNotNone(request_contract_fault(bad))
                self.assertEqual(apply_command_guard(bad, INP, CFG, CommandGuardState(ZERO)).output_nm, ZERO)
                self.assertFalse(observe_fault_state(FaultSnapshot(), bad, FaultPolicy(), sequence=0)[1].reference_gate_allowed)

    def test_real_allocator_outputs_remain_accepted_by_both_consumers(self):
        rng = random.Random(408)
        for sequence in range(2000):
            inp = AllocationInput(1000, 1000, rng.uniform(0, 400),
                                  tuple(rng.uniform(0, 100) for _ in range(4)),
                                  tuple(bool(rng.getrandbits(1)) for _ in range(4)), True)
            item = allocate_propulsive_torque(inp, AllocatorConfig(50))
            with self.subTest(sequence=sequence):
                self.assertIsNone(request_contract_fault(item))
                guarded = apply_command_guard(item, INP, CFG, CommandGuardState(ZERO))
                self.assertEqual(guarded, apply_request_checked_guard(item, INP, CFG, CommandGuardState(ZERO)))
                event = observe_fault_state(FaultSnapshot(), item, FaultPolicy(), sequence=sequence)[1]
                self.assertEqual(event.reference_gate_allowed, item.status != "fault")

    def test_valid_fault_may_retain_negative_diagnostic_request(self):
        item = replace(GOOD, wheel_torque_nm=ZERO, requested_nm=-5., delivered_nm=0.,
                       status="fault", fault="negative_request_unsupported")
        self.assertIsNone(request_contract_fault(item))
        self.assertEqual(apply_command_guard(item, INP, CFG, CommandGuardState(ZERO)).reason, "allocator_fault")
        self.assertEqual(observe_fault_state(FaultSnapshot(), item, FaultPolicy(), sequence=0)[1].reason,
                         "negative_request_unsupported")

    def test_ordinary_binary_roundoff_is_accepted(self):
        item = replace(GOOD, wheel_torque_nm=(0.1, 0.2, 0., 0.), requested_nm=0.3, delivered_nm=0.1 + 0.2)
        self.assertIsNone(request_contract_fault(item))

    def test_nonordinary_subclass_never_executes_conversion(self):
        class Trap(float):
            def __float__(self):
                raise AssertionError("custom conversion must not run")
        self.assertIsNotNone(request_contract_fault(replace(GOOD, requested_nm=Trap(40))))


if __name__ == "__main__":
    unittest.main()
