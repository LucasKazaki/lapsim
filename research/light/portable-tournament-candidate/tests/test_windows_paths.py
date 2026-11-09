"""Pure Windows path spelling/order fixtures; no Windows API or native guard.

The campaign provider and checkpoint metadata are explicitly UNTRUSTED doubles.
NoIOWindowsPath raises on any attempted filesystem access. These tests do not
qualify UNC/device anchors, actual Win32 behavior or original ownership/cleanup.
"""
from pathlib import PurePosixPath, PureWindowsPath
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from lapsim_light_campaign import raw_journal as journal, campaign
from lapsim_light_campaign.input_contracts import decode
from test_campaign import FakeProvider, RequestSource, plan_fixture


class NoIOWindowsPath(PureWindowsPath):
    def absolute(self):
        return self

    def lstat(self):
        raise AssertionError('No Windows filesystem probe permitted by this fixture')

    def mkdir(self, *args, **kwargs):
        raise AssertionError('No Windows directory creation permitted by this fixture')

    def is_symlink(self):
        raise AssertionError('No Windows filesystem probe permitted by this fixture')


BAD = (r'C:\owned\new-run.', 'C:\\owned\\new-run ', 'C:\\owned\\ new-run',
       r'C:\owned.\new-run', 'C:\\owned \\new-run', 'C:\\ owned\\new-run',
       r'\\server\share\new-run.', r'\\?\C:\owned\new-run.')


class WindowsPathSpellingTests(unittest.TestCase):
    def test_ambiguous_components_are_refused_by_pure_check(self):
        for name in BAD:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Windows component spelling'):
                journal._check_windows_component_spelling(PureWindowsPath(name))

    def test_no_alias_refuses_bad_spelling_before_any_lstat(self):
        for name in BAD:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Windows component spelling'):
                journal._no_alias(NoIOWindowsPath(name))

    def test_ordinary_spaces_hidden_names_unicode_and_dot_parent_semantics_preserved(self):
        for name in (r'C:\owned folder\new run', r'C:\owned\.hidden', r'C:\試験\new-run',
                     r'C:\owned\..\new-run', 'C:/', r'owned\new-run'):
            with self.subTest(name=name):
                self.assertIsNone(journal._check_windows_component_spelling(PureWindowsPath(name)))

    def test_anchor_is_not_rewritten_or_claimed_qualified(self):
        for name in (r'\\server\share\owned\new-run', r'\\?\C:\owned\new-run'):
            path = PureWindowsPath(name)
            before = str(path)
            self.assertIsNone(journal._check_windows_component_spelling(path))
            self.assertEqual(str(path), before)

    def test_posix_spelling_unchanged(self):
        for name in ('/owned/new-run.', '/owned/new-run ', '/owned/ new-run'):
            self.assertIsNone(journal._check_windows_component_spelling(PurePosixPath(name)))

    def test_journal_creation_rejects_bad_namespace_before_filesystem_access(self):
        plan, _ = plan_fixture()
        cell = decode(plan, 2*1024*1024)['plan']['cells'][0]
        with patch.object(journal, 'Path', return_value=NoIOWindowsPath(BAD[0])):
            with self.assertRaisesRegex(ValueError, 'Windows component spelling'):
                journal.RawJournal.create(BAD[0], cell['identity'], cell['origin'], sync_files=False)

    def test_campaign_rejects_bad_namespace_before_source_or_dispatch(self):
        plan, pin = plan_fixture()
        provider, source = FakeProvider(), RequestSource(plan)
        limits = campaign.CampaignLimits(10,10000,64*1024*1024,750,4*1024*1024,
                                         64*1024*1024,1024*1024*1024,False)
        with patch.object(campaign, 'Path', return_value=NoIOWindowsPath(BAD[0])):
            program = campaign.CampaignProgram(plan,expected_plan_sha256=pin,
                expected_provider_sha256=provider.implementation_sha256,provider=provider,
                request_source=source,output_root=BAD[0],limits=limits)
        with self.assertRaisesRegex(ValueError, 'Windows component spelling'):
            program.run()
        self.assertFalse(provider.calls)
        self.assertFalse(source.calls)
        self.assertFalse(program.snapshot()['field'].attempts)

    def test_existing_reparse_refusal_remains_after_valid_spelling(self):
        path = NoIOWindowsPath(r'C:\owned\new-run')
        with patch.object(NoIOWindowsPath, 'lstat', return_value=SimpleNamespace(st_file_attributes=1024)), \
             patch.object(NoIOWindowsPath, 'is_symlink', return_value=False):
            with self.assertRaisesRegex(ValueError, 'reparse-point'):
                journal._no_alias(path)


if __name__=='__main__':
    unittest.main()
