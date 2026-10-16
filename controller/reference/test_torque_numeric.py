"""Versioned accumulation is explicit, not an interpreter-sum side effect."""
import math
import unittest

from allocation_contract import allocation_contract_fault
from allocator import AllocationResult
from torque_numeric import NUMERIC_CONTRACT_VERSION, wheel_total


class TorqueNumericTests(unittest.TestCase):
    def test_fixed_order_rounds_each_mixed_scale_addition(self):
        unit = math.ulp(1.5)
        wheels = (1.5, unit/2, unit/2, 0.)
        self.assertEqual(NUMERIC_CONTRACT_VERSION, 2)
        self.assertEqual(wheel_total(wheels).hex(), "0x1.8000000000000p+0")
        self.assertIsNone(allocation_contract_fault(AllocationResult(wheels, 2., 1.5-8*unit, "ok", None)))
        self.assertEqual(allocation_contract_fault(AllocationResult(wheels, 2., 1.5+9*unit, "ok", None)),
                         "candidate_sum_mismatch")

    def test_slot_order_is_part_of_the_contract(self):
        unit = math.ulp(1.5)
        self.assertEqual(wheel_total((unit/2, unit/2, 1.5, 0.)), 1.5+unit)
        for values in ((), (1.,)*3, (1.,)*5):
            with self.assertRaises(ValueError):
                wheel_total(values)


if __name__ == "__main__":
    unittest.main()
