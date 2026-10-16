"""Finite consumer boundaries and actual compiled native replay/export evidence."""
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_bench_replay as replay
from allocator_parity import AllocatorCore, build_allocator_library


def scenario(count=3):
    value = json.loads((replay.ROOT / 'bench-scenario.example.json').read_bytes())
    template = value['samples'][0]
    value['samples'] = [deepcopy(template) for _ in range(count)]
    for i, row in enumerate(value['samples']):
        row['allocation']['now_ms'] = row['allocation']['input_timestamp_ms'] = i * 50
        row['allocation']['request_nm'] = 40.
        row['allocation']['wheel_limits_nm'] = [100.] * 4
    return value


class NativeBenchConsumer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='enme408-native-consumer-')
        cls.library, cls.build = build_allocator_library(Path(cls.temp.name))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def native(self, value):
        parsed, cfg, samples = replay.preflight(replay.encoded(value))
        rows, trace, mismatch = replay.verify_in_child(self.library, samples, cfg)
        self.assertIsNone(mismatch, mismatch)
        self.assertTrue(all(t['agreement'] for t in trace))
        return parsed, cfg, rows, trace

    def test_builtin_actual_rows_and_positive_coverage(self):
        value = json.loads((replay.ROOT / 'bench-scenario.example.json').read_bytes())
        _, _, rows, trace = self.native(value)
        self.assertEqual(len(rows), 18)
        self.assertEqual(sum(r['command_allowed'] for r in rows), 9)
        self.assertEqual(sum(r['fault']['next_state'] == 'recovery_pending' for r in rows), 5)
        self.assertGreater(sum(r['command_allowed'] and any(r['command_nm']) for r in rows), 0)
        self.assertEqual(len(trace), 18)

    def test_startup_clock_fault_and_history(self):
        value = scenario(7)
        _, _, rows, _ = self.native(value)
        self.assertEqual([r['command_nm'][0] for r in rows[:3]], [0., 5., 10.])
        value['samples'][3]['guard']['dt_s'] = .1
        _, _, rows, _ = self.native(value)
        self.assertEqual(rows[3]['clock_fault'], 'guard_period_mismatch')
        self.assertEqual(rows[3]['fault']['allocator_status'], 'fault')
        self.assertEqual(rows[3]['fault']['allocator_fault'], 'guard_period_mismatch')
        self.assertEqual(rows[3]['command_nm'], [0.] * 4)
        self.assertEqual(rows[5]['command_nm'], [5.] * 4)

    def test_contract_rejection_and_nonfinite_raw_trace(self):
        value = scenario(5)
        value['samples'][2]['allocation'].update(request_nm=1., wheel_limits_nm=[1. + 1e-12, 0., 0., 0.])
        _, _, rows, _ = self.native(value)
        self.assertEqual(rows[2]['command_reason'], 'candidate_exceeds_request')
        maximum = float.fromhex('0x1.fffffffffffffp+1023')
        value['samples'][2]['allocation'].update(request_nm=maximum, wheel_limits_nm=[maximum] * 3 + [0.])
        parsed, cfg, rows, trace = self.native(value)
        self.assertEqual(replay.native.bits(rows[2]['allocator']['delivered_nm']), '7ff0000000000000')
        self.assertFalse(rows[2]['command_allowed'])
        self.assertEqual(len(trace), 5)
        replay.encoded(trace)  # Nonfinite evidence is retained in strict bit form.
        receipt = replay.viewer_receipt(parsed, cfg, rows, {'test': '0'*64}, b'x', '1'*64)
        with self.assertRaisesRegex(ValueError, 'nonfinite viewer field'):
            replay.representation_check(receipt)

    def test_nul_and_safe_integer_boundary(self):
        value = scenario(1)
        value['samples'][0]['allocation'].update(now_ms=replay.MAX_SAFE, input_timestamp_ms=replay.MAX_SAFE,
                                                torque_unit='N*m\0ignored')
        _, _, rows, _ = self.native(value)
        self.assertEqual(rows[0]['allocator']['fault'], 'unsupported_torque_unit')
        value['samples'][0]['allocation']['now_ms'] += 1
        with self.assertRaisesRegex(ValueError, 'JavaScript-safe'):
            replay.preflight(replay.encoded(value))


class InputAndArtifactBoundaries(unittest.TestCase):
    def test_preflight_failures_make_zero_builder_calls(self):
        good = scenario(1)
        cases = []
        for field, value in (('restart_requested', 'false'),):
            case = deepcopy(good); case['samples'][0][field] = value; cases.append(replay.encoded(case))
        for count in (0, 4097):
            case = deepcopy(good); case['samples'] *= count; cases.append(replay.encoded(case))
        for value in (2**53, -(2**53)):
            case = deepcopy(good); case['config']['allocator']['max_input_age_ms'] = value; cases.append(replay.encoded(case))
        case = deepcopy(good); case['config']['fault']['valid_samples_to_recover'] = 2**32; cases.append(replay.encoded(case))
        case = deepcopy(good); case['samples'][0]['allocation']['request_nm'] = 10**400; cases.append(replay.encoded(case))
        cases += [b'{"schema":0,"schema":1}', b'['*2000+b'0'+b']'*2000,
                  replay.encoded(good).replace(b'40.0', b'1e999')]
        with tempfile.TemporaryDirectory() as folder, patch.object(replay.native, 'build_allocator_library', side_effect=AssertionError('unexpected build')):
            for index, raw in enumerate(cases):
                with self.subTest(index=index):
                    attempt = replay.reserve_directory(Path(folder) / str(index))
                    self.assertEqual(replay.execute(raw, attempt), 2)
                    run = json.loads((attempt / 'run.json').read_bytes())
                    self.assertEqual(run['actual_invocations'], {'version': 0, 'compile': 0})
                    self.assertEqual(run['input_status'], 'failed')
                    self.assertFalse((attempt / 'viewer-receipt.json').exists())

    def test_utf16_prefix_and_surrogate_boundaries(self):
        value = scenario(1)
        units = 4000 - len(replay.LABEL_PREFIX)
        value['label'] = '\U0001f600' * (units // 2) + 'x' * (units % 2)
        replay.preflight(replay.encoded(value))
        value['label'] += 'x'
        with self.assertRaisesRegex(ValueError, 'UTF-16'):
            replay.preflight(replay.encoded(value))
        value['label'] = '\ud800'
        with self.assertRaises(UnicodeError): replay.preflight(replay.encoded(value))

    def test_path_reservation_preserves_sources_and_previous_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.json'; source.write_bytes(b'keep')
            with self.assertRaises(ValueError): replay.reserve_directory(source)
            attempt = replay.reserve_directory(Path(folder) / 'attempt')
            with self.assertRaises(ValueError): replay.reserve_directory(attempt)
            with self.assertRaises(ValueError): replay.reserve_directory(attempt / 'nested')
            self.assertEqual(source.read_bytes(), b'keep')
            with self.assertRaises(ValueError): replay.reserve_directory(replay.ROOT / 'must-not-create')

    def test_real_build_failure_has_actual_command_accounting(self):
        with tempfile.TemporaryDirectory() as folder:
            attempt = replay.reserve_directory(Path(folder) / 'attempt')
            self.assertEqual(replay.execute(replay.encoded(scenario(1)), attempt, 'no-such-enme408-compiler'), 2)
            run = json.loads((attempt / 'run.json').read_bytes())
            self.assertEqual(run['build_status'], 'failed')
            self.assertEqual(run['actual_invocations'], {'version': 0, 'compile': 0})
            self.assertIs(replay.native.subprocess, replay.subprocess)

    def test_sealed_run_survives_actual_export_io_failure(self):
        # Reuse one genuine library already built by the compiled test class;
        # this is a packaging injection, not a claimed real build attempt.
        with tempfile.TemporaryDirectory() as folder:
            library, build = build_allocator_library(Path(folder))
            for index, failed in enumerate(({'viewer-receipt.json'}, {'trace.csv'}, {'export-status.json'},
                                             {'export-status.json', 'export-failure.json'})):
                with self.subTest(failed=sorted(failed)):
                    attempt = replay.reserve_directory(Path(folder) / str(index))
                    original, sealed, stderr = replay.write_new, [], io.StringIO()
                    def fail_export(path, raw):
                        if path.name in failed: raise OSError('identical finite injected IO failure')
                        original(path, raw)
                        if path.name == 'run.json': sealed.append(raw)
                    with patch.object(replay.native, 'build_allocator_library', return_value=(library, build)), \
                         patch.object(replay, 'write_new', side_effect=fail_export), patch.object(replay.sys, 'stderr', stderr):
                        self.assertEqual(replay.execute(replay.encoded(scenario()), attempt), 2)
                    self.assertEqual((attempt / 'run.json').read_bytes(), sealed[0])
                    if 'export-status.json' in failed:
                        if 'export-failure.json' in failed:
                            status = json.loads(stderr.getvalue())
                            self.assertEqual(status['fallback_error']['stage'], 'write_export_failure')
                            self.assertEqual(status['fallback_error']['failed_file'], 'export-failure.json')
                        else:
                            status = json.loads((attempt / 'export-failure.json').read_bytes())
                        self.assertEqual(status['error']['stage'], 'write_export_status')
                        self.assertEqual(status['error']['failed_file'], 'export-status.json')
                        completed = status['prior_export']['completed_files']
                        self.assertEqual(set(completed), {'run.json', 'viewer-receipt.json', 'trace.csv'})
                    else:
                        status = json.loads((attempt / 'export-status.json').read_bytes())
                        name = next(iter(failed))
                        self.assertEqual(status['status'], 'failed_retained')
                        self.assertEqual(status['error']['failed_file'], name)
                        self.assertEqual(status['error']['stage'], 'write_csv' if name == 'trace.csv' else 'write_viewer_receipt')
                        completed = status['completed_files']
                        self.assertNotIn(name, completed)
                    self.assertEqual(completed['run.json'], hashlib.sha256(sealed[0]).hexdigest())
                    if (attempt / 'viewer-receipt.json').exists():
                        receipt = json.loads((attempt / 'viewer-receipt.json').read_bytes())
                        self.assertEqual(receipt['native_execution']['run_sha256'], hashlib.sha256(sealed[0]).hexdigest())


if __name__ == '__main__':
    unittest.main()
