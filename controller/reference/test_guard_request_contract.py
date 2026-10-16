"""Offline request/delivery invariant tests; all inputs are synthetic."""
from __future__ import annotations

import math
import random
import unittest

from allocator import AllocationInput, AllocationResult, AllocatorConfig, allocate_propulsive_torque
from command_guard import (
    CommandGuardConfig, CommandGuardInput, CommandGuardState, apply_command_guard,
)
from guard_request_contract import apply_request_checked_guard, request_contract_fault

CFG = CommandGuardConfig(1000.0, 0.60, 0.20)
INPUT = CommandGuardInput(0.1, 0.3, False, True, True, True)
ZERO = CommandGuardState((0.0,) * 4)


def candidate(requested=40.0, delivered=40.0, status="ok", wheels=(10.0,) * 4, fault=None):
    return AllocationResult(wheels, requested, delivered, status, fault)


class GuardRequestContractTests(unittest.TestCase):
    def test_known_good_passes_through_unchanged(self):
        data = candidate()
        self.assertIsNone(request_contract_fault(data))
        self.assertEqual(apply_request_checked_guard(data, INPUT, CFG, ZERO),
                         apply_command_guard(data, INPUT, CFG, ZERO))

    def test_valid_saturation_preserves_original_reason(self):
        data = candidate(requested=60.0, delivered=40.0, status="saturated", fault="aggregate_limit")
        actual = apply_request_checked_guard(data, INPUT, CFG, ZERO)
        self.assertEqual((actual.status, actual.reason), ("limited", "aggregate_limit"))

    def test_zero_request_with_positive_command_is_inhibited(self):
        data = candidate(requested=0.0)
        self.assertEqual(apply_command_guard(data, INPUT, CFG, ZERO).output_nm, (0.0,) * 4)
        actual = apply_request_checked_guard(data, INPUT, CFG, ZERO)
        self.assertEqual((actual.output_nm, actual.reason), ((0.0,) * 4, "candidate_exceeds_request"))
        self.assertEqual(actual.next_state.previous_output_nm, (0.0,) * 4)

    def test_nonzero_overrequest_is_inhibited(self):
        actual = apply_request_checked_guard(candidate(requested=20.0), INPUT, CFG, ZERO)
        self.assertEqual((actual.status, actual.reason), ("inhibited", "candidate_exceeds_request"))
        self.assertEqual(actual.output_nm, (0.0,) * 4)

    def test_negative_requested_is_inhibited(self):
        self.assertEqual(request_contract_fault(candidate(requested=-1.0)), "invalid_candidate_requested")

    def test_nonfinite_requested_is_inhibited(self):
        for bad in (math.nan, math.inf, -math.inf):
            with self.subTest(bad=repr(bad)):
                self.assertEqual(request_contract_fault(candidate(requested=bad)),
                                 "invalid_candidate_requested")

    def test_bool_and_large_integer_requested_are_inhibited(self):
        for bad in (True, 10**400):
            with self.subTest(kind=type(bad).__name__):
                self.assertEqual(request_contract_fault(candidate(requested=bad)),
                                 "invalid_candidate_requested")

    def test_comparison_spoof_cannot_impersonate_status(self):
        class FakeStatus:
            def __hash__(self): return hash("ok")
            def __eq__(self, other): return other == "ok"
        data = candidate(status=FakeStatus())
        self.assertEqual(apply_command_guard(data, INPUT, CFG, ZERO).output_nm, (0.0,) * 4)
        self.assertEqual(request_contract_fault(data), "invalid_candidate_status")
        self.assertEqual(apply_request_checked_guard(data, INPUT, CFG, ZERO).output_nm, (0.0,) * 4)

    def test_arbitrary_float_conversion_methods_are_not_called(self):
        class Trap:
            def __float__(self): raise AssertionError("must never execute __float__")
            def __lt__(self, other): raise AssertionError("must never compare")
        self.assertEqual(request_contract_fault(candidate(requested=Trap())),
                         "invalid_candidate_requested")

    def test_negative_delivered_and_nonfinite_delivered(self):
        for bad in (-1.0, math.inf, math.nan, True):
            with self.subTest(bad=repr(bad)):
                self.assertEqual(request_contract_fault(candidate(delivered=bad)),
                                 "invalid_candidate_delivered")

    def test_invalid_vector_is_rejected_without_exotic_conversion(self):
        class Trap:
            def __float__(self): raise AssertionError("must never execute")
        self.assertEqual(request_contract_fault(candidate(wheels=(Trap(), 10.0, 10.0, 10.0))),
                         "invalid_candidate_output")

    def test_fault_candidate_delegates_to_published_immediate_zero(self):
        data = candidate(requested=40.0, delivered=0.0, status="fault",
                         wheels=(0.0,) * 4, fault="stale_input")
        actual = apply_request_checked_guard(data, INPUT, CFG, CommandGuardState((10.0,) * 4))
        self.assertEqual((actual.reason, actual.output_nm), ("allocator_fault", (0.0,) * 4))

    def test_existing_interlock_inhibit_is_preserved(self):
        data = candidate()
        input_bad = CommandGuardInput(0.1, 0.3, False, True, True, False)
        actual = apply_request_checked_guard(data, input_bad, CFG, CommandGuardState((10.0,) * 4))
        self.assertEqual((actual.reason, actual.output_nm), ("external_interlock_open", (0.0,) * 4))

    def test_valid_seeded_allocator_results_match_published_guard(self):
        rng = random.Random(20261010)
        for index in range(1000):
            request = float(rng.randrange(0, 401))
            limits = tuple(float(rng.randrange(0, 201)) for _ in range(4))
            enabled = tuple(bool(rng.getrandbits(1)) for _ in range(4))
            item = AllocationInput(1000, 1000, request, limits, enabled, True)
            data = allocate_propulsive_torque(item, AllocatorConfig(50))
            expected = apply_command_guard(data, INPUT, CFG, ZERO)
            actual = apply_request_checked_guard(data, INPUT, CFG, ZERO)
            with self.subTest(index=index):
                self.assertEqual(expected, actual)

    def test_relative_ulp_roundoff_not_misclassified(self):
        # 0.1+0.2 differs slightly from 0.3 in binary floating point.
        data = candidate(requested=0.3, delivered=0.1 + 0.2,
                         wheels=(0.1, 0.2, 0.0, 0.0))
        self.assertIsNone(request_contract_fault(data))

    def test_non_plain_allocation_result_is_inhibited(self):
        class Fake:
            def __getattribute__(self, name): raise AssertionError("must never inspect")
        self.assertEqual(request_contract_fault(Fake()), "invalid_candidate_type")


if __name__ == "__main__":
    unittest.main()
