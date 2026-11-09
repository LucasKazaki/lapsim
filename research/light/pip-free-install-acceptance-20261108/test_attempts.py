"""Inert launch/control-error fixtures; no installer or native process runs."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import argparse,importlib.util,json,subprocess,sys,unittest

spec = importlib.util.spec_from_file_location('install_validation_fixture', Path(__file__).with_name('validate_install.py'))
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)
WHEEL = SOURCE = None


class AttemptEvidenceTests(unittest.TestCase):
    def attempt(self, error):
        with TemporaryDirectory(prefix='install-attempt-test-') as temp:
            output = Path(temp)/'new-validation'
            argv = ['validate_install.py','--base-python',sys.executable,'--installer-python',sys.executable,
                    '--wheel',str(WHEEL),'--source-root',str(SOURCE),'--output',str(output)]
            with patch.object(sys,'argv',argv), patch.object(validation.subprocess,'run',side_effect=error) as call:
                with self.assertRaises(type(error)) as raised:
                    validation.main()
            self.assertIs(raised.exception,error)
            self.assertEqual(call.call_count,1)
            rows = json.loads((output/'commands.json').read_bytes())
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['label'],'installer-version')
            self.assertEqual(rows[0]['argv'][0],sys.executable)
            self.assertIsNone(rows[0]['actual_exit'])
            self.assertEqual(rows[0]['state'],'attempted_outcome_unresolved')
            self.assertFalse(rows[0]['descendant_cleanup_proven'])
            self.assertFalse((output/'result.json').exists())
            self.assertFalse((output/'installer-version.stdout').exists())

    def test_launch_error_keeps_attempt_and_original_error(self):
        self.attempt(FileNotFoundError('UNTRUSTED injected launch failure'))

    def test_timeout_is_unresolved_not_success_or_cleanup_proof(self):
        self.attempt(subprocess.TimeoutExpired(['UNTRUSTED-no-process'],20,output=b'partial-not-returned'))

    def test_unknown_control_propagates_with_attempt_intact(self):
        class OwnerControl(BaseException):
            pass
        self.attempt(OwnerControl('UNTRUSTED injected owner control'))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel',required=True,type=Path)
    parser.add_argument('--source-root',required=True,type=Path)
    args = parser.parse_args()
    WHEEL,SOURCE = args.wheel,args.source_root
    unittest.main(argv=[sys.argv[0]],verbosity=2)
