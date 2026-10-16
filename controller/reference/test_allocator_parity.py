"""Compiled candidate owner plus actual composed-state acceptance checks."""
from dataclasses import replace
import math
from pathlib import Path
import tempfile
import unittest

from allocator import AllocatorConfig
from allocator_parity import (allocator_input, allocator_config, build_allocator_library,
                              verify_in_child, frozen_protocol, frozen_cases, ordinary, bits)


class CompiledAllocatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='enme408-allocator-tests-')
        root = Path(cls.temporary.name)
        (root / 'one').mkdir(); (root / 'two').mkdir()
        library, first = build_allocator_library(root / 'one')
        _, second = build_allocator_library(root / 'two')
        cls.binary_repeat_equal = first['binary_sha256'] == second['binary_sha256']
        cls.receipt = verify_in_child(library)

    @classmethod
    def tearDownClass(cls): cls.temporary.cleanup()

    def test_frozen_policy_generator_and_two_identical_builds(self):
        self.assertEqual(frozen_protocol()['base_pr'], 75)
        self.assertEqual(frozen_cases()['seed'], 2026101508)
        self.assertTrue(self.binary_repeat_equal)

    def test_finite_grid_random_and_every_source_fault(self):
        result = self.receipt['results']
        self.assertEqual(result['grid_cases'], 4608)
        self.assertEqual(result['random_cases'], 8192)
        for reason in ('invalid_max_input_age', 'unsupported_torque_unit', 'invalid_request_numeric',
                'nonfinite_request', 'negative_request_unsupported', 'invalid_wheel_vector', 'invalid_wheel_enabled',
                'invalid_external_interlock', 'invalid_wheel_limit', 'external_interlock_open',
                'invalid_input_timestamp', 'input_timestamp_in_future', 'stale_input', 'no_available_wheels', 'aggregate_limit'):
            with self.subTest(reason=reason): self.assertGreater(result['reasons'][reason], 0)

    def test_original_epsilon_overshoot_is_preserved_and_rejected(self):
        label = bits(1.) + '/' + bits(1. + 1e-12)
        corner = self.receipt['results']['named'][label]
        self.assertEqual(corner['result']['status'], 'ok')
        self.assertIsNone(corner['result']['fault'])
        self.assertEqual(corner['result']['wheel_bits'][0], bits(1. + 1e-12))
        self.assertEqual(corner['contract'], 'candidate_exceeds_request')
        self.assertEqual(self.receipt['results']['composed_reasons']['candidate_exceeds_request'], 128)

    def test_shortfall_label_and_tiny_request_remain_source_behavior(self):
        named = self.receipt['results']['named']
        under = named[bits(1.) + '/' + bits(1. - 5e-10)]
        self.assertEqual(under['result']['status'], 'ok')
        self.assertEqual(under['result']['delivered_bits'], bits(1. - 5e-10))
        tiny = named[bits(1e-13) + '/' + bits(20.)]['result']
        self.assertEqual(tiny['status'], 'ok')
        self.assertEqual(tiny['wheel_bits'], [bits(0.)] * 4)
        self.assertEqual(tiny['requested_bits'], bits(1e-13))

    def test_negative_zero_request_success_normalizes_positive_zero(self):
        corner = self.receipt['results']['named'][bits(-0.) + '/' + bits(0.)]['result']
        self.assertEqual(corner['requested_bits'], bits(0.))
        self.assertEqual(corner['wheel_bits'], [bits(0.)] * 4)

    def test_real_five_unit_pipeline_has_positive_held_and_recovery_coverage(self):
        result = self.receipt['results']
        self.assertEqual(result['healthy_cycles'], 1024)
        self.assertEqual(result['recovery_cycles'], 4096)
        self.assertEqual(result['composed_cycles'], 5120)
        self.assertEqual(result['composed_reasons']['guard_period_mismatch'], 128)
        self.assertEqual(result['composed_reasons']['cycle_period_mismatch'], 128)
        self.assertEqual(result['composed_reasons']['nonmonotonic_cycle_timestamp'], 128)
        for name in ('positive_allowed_cycles', 'held_cycles', 'allowed_limited_cycles', 'clock_fault_cycles', 'latch_clearances', 'restarts'):
            with self.subTest(name=name): self.assertGreater(result[name], 16)

    def test_tag_null_decoder_domain_boundaries_were_exercised(self):
        self.assertGreater(self.receipt['boundaries']['checks'], 9000)
        self.assertEqual(set(self.receipt['allocator_abi_sizes']), {'AllocatorConfigC', 'AllocatorInputC'})


class AllocatorDecoderTests(unittest.TestCase):
    def test_embedded_nul_source_unit_is_not_truncated_to_valid(self):
        inp, _ = ordinary()
        for unit in ('N*m\0', 'N*m\0ignored'):
            with self.subTest(unit=unit):
                self.assertEqual(allocator_input(replace(inp, torque_unit=unit)).torque_unit.kind, 2)

    def test_timestamp_overflow_is_out_of_domain_and_not_reclassified(self):
        inp, _ = ordinary()
        for field in ('now_ms', 'input_timestamp_ms'):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'no-wrap uint64 domain'):
                allocator_input(replace(inp, **{field: 2**64}))
        with self.assertRaisesRegex(ValueError, 'no-wrap uint64 domain'): allocator_config(AllocatorConfig(2**64))

    def test_nonfinite_float_and_unrepresentable_integer_remain_distinct(self):
        inp, _ = ordinary()
        self.assertEqual(allocator_input(replace(inp, request_nm=math.inf)).request.numeric, 1)
        self.assertEqual(allocator_input(replace(inp, request_nm=10**400)).request.numeric, 0)
        self.assertEqual(allocator_input(replace(inp, request_nm=True)).request.numeric, 0)


if __name__ == '__main__': unittest.main()
