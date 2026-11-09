"""Real bounded evidence-file CLI paths; all campaign inputs are UNTRUSTED.

No worker, predicate, native guard, lease or physical lap is exercised.
Injected partial I/O tests preservation and honest command exit/status only.
"""
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from lapsim_light_campaign import tournament_cli as cli
from lapsim_light_campaign.input_contracts import decode, encode
from test_campaign import plan_fixture
from test_release_binding import fixture as release_fixture


class PartialStream:
    def __init__(self, stream, error=None):
        self.stream, self.error = stream, error

    def __enter__(self):
        self.stream.__enter__()
        return self

    def __exit__(self, *args):
        return self.stream.__exit__(*args)

    def fileno(self):
        return self.stream.fileno()

    def write(self, raw):
        count = self.stream.write(raw[:max(1, len(raw)//2)])
        if self.error is not None:
            raise self.error
        return count

    def flush(self):
        return self.stream.flush()


class TournamentCliTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(prefix='untrusted-cli-unit-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.work = self.root/'work'
        self.work.mkdir()
        raw, self.pin = plan_fixture()
        self.plan = self.root/'plan.json'
        self.plan.write_bytes(raw)
        self.target = self.work/'inspection.json'

    def invoke(self, args):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(args, output_root=self.work)
        return code, out.getvalue(), err.getvalue()

    def inspection_args(self, *, output=True, pin=None):
        args = ['inspect-plan', '--plan', str(self.plan), '--plan-sha256', self.pin if pin is None else pin]
        return args + ['--output', str(self.target)] if output else args

    def partial_open(self, *, error=None):
        original = Path.open
        def opening(path, mode='r', *args, **kwargs):
            stream = original(path, mode, *args, **kwargs)
            return PartialStream(stream, error) if path == self.target and mode == 'xb' else stream
        return patch.object(Path, 'open', opening)

    def test_short_write_is_error_preserves_partial_and_has_no_success_summary(self):
        with self.partial_open():
            code, out, err = self.invoke(self.inspection_args())
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('Incomplete', err)
        partial = self.target.read_bytes()
        self.assertGreater(len(partial), 0)
        code, out, err = self.invoke(self.inspection_args())
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('Output already exists', err)
        self.assertEqual(self.target.read_bytes(), partial)

    def test_interrupted_write_retains_partial_and_reports_interruption(self):
        with self.partial_open(error=KeyboardInterrupt('UNTRUSTED interrupted file write')):
            code, out, err = self.invoke(self.inspection_args())
        self.assertEqual(code, 130)
        self.assertEqual(out, '')
        self.assertIn('partial output is preserved', err)
        self.assertIn('No worker was started', err)
        self.assertGreater(self.target.stat().st_size, 0)

    def test_invalid_plan_pin_refused_before_output_creation(self):
        code, out, err = self.invoke(self.inspection_args(pin='0'*64))
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertTrue(err)
        self.assertFalse(self.target.exists())

    def test_plan_inspection_retains_no_execution_status(self):
        code, out, err = self.invoke(self.inspection_args(output=False))
        self.assertEqual(code, 0)
        self.assertEqual(err, '')
        value = decode(out.strip().encode(), cli.MAX_COMMAND_OUTPUT_BYTES)
        self.assertEqual(value['inspection']['frozen_cells'], 7)
        self.assertFalse(value['inspection']['qualification_or_execution_authority'])
        self.assertFalse(value['inspection']['source_runtime_or_original_input_authentication_performed'])
        self.assertFalse(value['inspection']['completed_laps_established_by_this_inspection'])
        self.assertEqual(list(self.work.iterdir()), [])

    def test_incomplete_field_report_is_written_and_exits_three_without_rank(self):
        raw = encode({'schema': cli.INDEX_SCHEMA, 'cells': {}})
        index = self.root/'index.json'
        index.write_bytes(raw)
        code, out, err = self.invoke(['compare-results', '--plan', str(self.plan), '--plan-sha256', self.pin,
            '--results-index', str(index), '--index-sha256', sha256(raw).hexdigest(), '--output', str(self.target)])
        self.assertEqual(code, 3)
        self.assertEqual(err, '')
        summary = decode(out.strip().encode(), cli.MAX_COMMAND_OUTPUT_BYTES)
        self.assertEqual(summary['status'], 'RAW_FIELD_REPORT_INCOMPLETE_OR_EXCLUDED')
        report = decode(self.target.read_bytes(), cli.MAX_COMMAND_OUTPUT_BYTES)['comparison']['raw_report']
        self.assertEqual(len(report['rows']), 7)
        self.assertTrue(all(row['submission'] == 'missing' for row in report['rows']))
        self.assertIsNone(report['descriptive_raw_orders'])
        self.assertFalse(report['qualification_or_execution_authority'])

    def release_args(self, values):
        manifest, contract, wheel = values
        paths = [self.root/name for name in ('source-manifest.json', 'install-contract.json', 'release.whl')]
        for path, raw in zip(paths, values):
            path.write_bytes(raw)
        return ['verify-release', '--source-manifest', str(paths[0]), '--manifest-sha256', sha256(manifest).hexdigest(),
            '--install-contract', str(paths[1]), '--wheel', str(paths[2]), '--wheel-sha256', sha256(wheel).hexdigest()]

    def test_release_command_binds_matching_bytes_without_execution_claim(self):
        code, out, err = self.invoke(self.release_args(release_fixture()))
        self.assertEqual(code, 0)
        self.assertEqual(err, '')
        value = decode(out.strip().encode(), cli.MAX_COMMAND_OUTPUT_BYTES)
        self.assertFalse(value['binding']['qualification_or_execution_authority'])
        self.assertFalse(value['binding']['installed_files_or_record_checked'])
        self.assertEqual(list(self.work.iterdir()), [])

    def test_wrong_revision_release_refused_before_output(self):
        def change(files, prefix):
            files['lapsim_light_core/__init__.py'] += b'# other revision\n'
        args = self.release_args(release_fixture(wheel_change=change))+['--output', str(self.target)]
        code, out, err = self.invoke(args)
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('Wheel/source bytes differ', err)
        self.assertFalse(self.target.exists())

    def test_release_manifest_pin_refused_before_output(self):
        args = self.release_args(release_fixture())+['--output', str(self.target)]
        args[args.index('--manifest-sha256')+1] = '0'*64
        code, out, err = self.invoke(args)
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('SHA-256 differs', err)
        self.assertFalse(self.target.exists())

    def test_release_unknown_owner_control_is_not_downgraded_to_exit_two(self):
        args = self.release_args(release_fixture())
        for base in (ValueError, KeyboardInterrupt):
            class OwnerControl(base):
                pass
            error = OwnerControl('UNTRUSTED owner control fixture')
            with self.subTest(base=base), patch.object(cli, '_read', side_effect=error):
                with self.assertRaises(OwnerControl) as raised:
                    self.invoke(args)
            self.assertIs(raised.exception, error)
        self.assertFalse(self.target.exists())


if __name__ == '__main__':
    unittest.main()
