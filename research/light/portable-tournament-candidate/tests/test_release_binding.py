"""Supplied-byte release checks using explicit UNTRUSTED synthetic wheels.

No installer, observed environment, original provider, wheel payload import or
native authority is exercised. Mutated wheels rebuild their own valid RECORD.
"""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO, StringIO
from unittest.mock import patch
import base64,csv,json,unittest,zipfile

from lapsim_light_campaign import release_binding as r
from lapsim_light_campaign.runtime_observation import ObservationUnavailable

NAME = 'lapsim-light-tournament-source-candidate'
PACKAGES = ['lapsim_light_campaign', 'lapsim_light_core', 'lapsim_light_course',
            'lapsim_light_guidance', 'lapsim_light_policies']
VERSION = '0.0.0.dev999'


def raw_json(value):
    return (json.dumps(value, sort_keys=True, indent=2)+'\n').encode()


def wheel_bytes(files):
    files = dict(files)
    prefix = next(name.rsplit('/', 1)[0] for name in files if name.endswith('/METADATA'))
    record = prefix+'/RECORD'
    stream = StringIO(newline='')
    writer = csv.writer(stream)
    for name, raw in sorted(files.items()):
        writer.writerow([name, 'sha256='+base64.urlsafe_b64encode(sha256(raw).digest()).decode().rstrip('='), len(raw)])
    writer.writerow([record, '', ''])
    files[record] = stream.getvalue().encode()
    out = BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_STORED) as z:
        for name, raw in sorted(files.items()):
            z.writestr(name, raw)
    return out.getvalue()


def fixture(*, contract_change=None, manifest_change=None, wheel_change=None):
    # These bytes would fail immediately if a checker tried to execute them.
    sources = {'src/'+name+'/__init__.py': b"raise RuntimeError('UNTRUSTED wheel payload must never execute')\n" for name in PACKAGES}
    sources.update({'src/lapsim_light_course/data/LICENSE.md': b'UNTRUSTED synthetic MIT notice\n',
                    'CORE_NOTICE.md': b'UNTRUSTED fixture rights notice\n'})
    selected = sorted([*sources, 'INSTALL_CONTRACT.json', 'SOURCE_MANIFEST.json'])
    c = {'schema':'lapsim.light-current-source-install-contract.v1',
        'source_distribution':{'manifest_includes_exact_paths':selected,'file_count_including_source_manifest':len(selected)},
        'project':{'name':NAME,'version':VERSION,'requires_python':'>=3.11','required_third_party_runtime_dependencies':[],
                   'bundled_packages':PACKAGES.copy(),'modules':[{'path':'src/'+n+'/__init__.py','module':n} for n in PACKAGES]},
        'package_data':[{'source_path':'src/lapsim_light_course/data/LICENSE.md','package':'lapsim_light_course',
                         'resource':'data/LICENSE.md','raw_sha256':sha256(sources['src/lapsim_light_course/data/LICENSE.md']).hexdigest()}],
        'optional_verifier':{'extra':'admission-verifier','requirement':'cryptography==50.0.2'},
        'entry_points':{'console_scripts':{'lapsim-light-evidence':'lapsim_light_campaign.tournament_cli:main'}}}
    if contract_change is not None:
        contract_change(c)
    contract = raw_json(c)
    sources['INSTALL_CONTRACT.json'] = contract
    m = {'schema':'lapsim.light-tournament-source-integration.v40','entries_count':len(sources),
        'files':[{'path':n,'bytes':len(raw),'sha256':sha256(raw).hexdigest()} for n, raw in sorted(sources.items())]}
    if manifest_change is not None:
        manifest_change(m)
    prefix = NAME.replace('-', '_')+'-'+VERSION+'.dist-info'
    files = {n[4:]:raw for n,raw in sources.items() if n.startswith('src/')}
    for n in ('CORE_NOTICE.md','src/lapsim_light_course/data/LICENSE.md'):
        files[prefix+'/licenses/'+n] = sources[n]
    files.update({prefix+'/METADATA':('Metadata-Version: 2.4\nName: '+NAME+'\nVersion: '+VERSION+
        '\nRequires-Python: >=3.11\nProvides-Extra: admission-verifier\nRequires-Dist: cryptography==50.0.2; extra == "admission-verifier"'+
        '\nLicense-File: CORE_NOTICE.md\nLicense-File: src/lapsim_light_course/data/LICENSE.md\n\nUNTRUSTED fixture\n').encode(),
        prefix+'/WHEEL':b'Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
        prefix+'/entry_points.txt':b'[console_scripts]\nlapsim-light-evidence = lapsim_light_campaign.tournament_cli:main\n',
        prefix+'/top_level.txt':''.join(n+'\n' for n in sorted(PACKAGES)).encode()})
    if wheel_change is not None:
        wheel_change(files, prefix)
    return raw_json(m), contract, wheel_bytes(files)


class ReleaseBindingTests(unittest.TestCase):
    def verify(self, values=None, **kwargs):
        m,c,w = fixture() if values is None else values
        return r.verify_source_wheel_binding(m,c,w,expected_source_manifest_sha256=sha256(m).hexdigest(),
            expected_wheel_sha256=sha256(w).hexdigest(),**kwargs)

    def test_valid_binding_keeps_all_three_identities_distinct_and_no_authority(self):
        values = fixture()
        with patch('builtins.open', side_effect=AssertionError('No file access')), \
             patch.object(zipfile.ZipFile, 'extractall', side_effect=AssertionError('No extraction')):
            value = self.verify(values)
        b = value['binding']
        self.assertEqual([b[k] for k in ('source_manifest_raw_sha256','install_contract_raw_sha256','wheel_raw_sha256')],
                         [sha256(raw).hexdigest() for raw in values])
        self.assertEqual(b['runtime_modules'], 5)
        self.assertEqual(b['runtime_resources'], 1)
        for k in ('installed_files_or_record_checked','supplied_wheel_imported_or_extracted',
                  'verifier_code_authenticated_by_this_check','loaded_code_or_environment_authenticated',
                  'native_admission_or_cleanup_performed','qualification_or_execution_authority'):
            self.assertIs(b[k], False)

    def test_self_consistent_wrong_source_payload_is_rejected(self):
        def change(files, prefix):
            files['lapsim_light_core/__init__.py'] += b'# other revision\n'
        values = fixture(wheel_change=change)
        # The existing framing/RECORD check alone accepts this internally
        # coherent archive. The new source association must still reject it.
        _, files, _ = r._zip_entries(values[2])
        self.assertIn('lapsim_light_core/__init__.py', files)
        with self.assertRaisesRegex(r.ReleaseBindingError, 'Wheel/source bytes differ'):
            self.verify(values)

    def test_contract_must_match_manifest_row_before_its_claims_are_used(self):
        m,c,w = fixture()
        with self.assertRaisesRegex(r.ReleaseBindingError, 'contract differs'):
            self.verify((m,c+b' ',w))

    def test_wheel_and_manifest_external_pins_are_required(self):
        m,c,w = fixture()
        for mp,wp in (('0'*64,sha256(w).hexdigest()),(sha256(m).hexdigest(),'0'*64)):
            with self.subTest(mp=mp,wp=wp), self.assertRaises(r.ReleaseBindingError):
                r.verify_source_wheel_binding(m,c,w,expected_source_manifest_sha256=mp,expected_wheel_sha256=wp)

    def test_unsupported_manifest_schema_and_duplicate_rows_are_rejected(self):
        for change in (lambda m:m.update(schema='future-unsupported'),
                       lambda m:(m['files'].append(deepcopy(m['files'][0])),m.update(entries_count=m['entries_count']+1))):
            with self.subTest(change=change), self.assertRaises(r.ReleaseBindingError):
                self.verify(fixture(manifest_change=change))

    def test_reviewed_v41_schema_keeps_complete_payload_requirements(self):
        change = lambda m:m.update(schema='lapsim.light-tournament-source-integration.v41')
        self.assertFalse(self.verify(fixture(manifest_change=change))['binding']['qualification_or_execution_authority'])
        with self.assertRaisesRegex(r.ReleaseBindingError, 'omit or duplicate'):
            self.verify(fixture(manifest_change=change, contract_change=lambda c:c['project']['modules'].pop()))

    def test_incomplete_module_declaration_cannot_hide_selected_source(self):
        with self.assertRaisesRegex(r.ReleaseBindingError, 'omit or duplicate'):
            self.verify(fixture(contract_change=lambda c:c['project']['modules'].pop()))

    def test_unexpected_wheel_payload_rejected_even_with_valid_record(self):
        def change(files, prefix):
            files['lapsim_light_campaign/extra.py'] = b'# unselected extra code\n'
        with self.assertRaisesRegex(r.ReleaseBindingError, 'unexpected'):
            self.verify(fixture(wheel_change=change))

    def test_license_copy_is_bound_to_original_source_notice(self):
        def change(files, prefix):
            files[prefix+'/licenses/CORE_NOTICE.md'] += b'other grant'
        with self.assertRaisesRegex(r.ReleaseBindingError, 'Wheel/source bytes differ'):
            self.verify(fixture(wheel_change=change))

    def test_changed_entrypoint_is_not_accepted_as_native_start(self):
        def change(files, prefix):
            files[prefix+'/entry_points.txt'] = b'[console_scripts]\nstart = made_up:main\n'
        with self.assertRaisesRegex(r.ReleaseBindingError, 'entry_points'):
            self.verify(fixture(wheel_change=change))

    def test_changed_version_dependency_and_platform_profile_rejected(self):
        variants = [('/METADATA',b'Version: '+VERSION.encode(),b'Version: 0.0.0.dev998'),
                    ('/METADATA',b'cryptography==50.0.2',b'cryptography==0.0.0'),
                    ('/WHEEL',b'py3-none-any',b'cp313-cp313-win_amd64')]
        for suffix,old,new in variants:
            def change(files, prefix):
                files[prefix+suffix] = files[prefix+suffix].replace(old,new)
            with self.subTest(suffix=suffix,old=old), self.assertRaises(r.ReleaseBindingError):
                self.verify(fixture(wheel_change=change))

    def test_row_bool_byte_count_and_escaping_path_refused(self):
        for key,value in (('bytes',True),('path','../outside.py')):
            with self.subTest(key=key), self.assertRaises(r.ReleaseBindingError):
                self.verify(fixture(manifest_change=lambda m:m['files'][0].update({key:value})))

    def test_explicit_input_bound_is_enforced_before_wheel_parsing(self):
        with patch.object(r, 'MAX_WHEEL_BYTES', 1), patch.object(r, '_zip_entries') as parse:
            with self.assertRaises(r.ReleaseBindingError):
                self.verify()
        parse.assert_not_called()

    def test_unknown_control_and_memory_errors_propagate_unchanged(self):
        class OwnerControl(ObservationUnavailable):
            pass
        for error in (OwnerControl('owner fatal control'), MemoryError('bounded fixture')):
            with self.subTest(error=error), patch.object(r, '_zip_entries', side_effect=error):
                with self.assertRaises(type(error)) as raised:
                    self.verify()
            self.assertIs(raised.exception, error)

    def test_unsupported_or_duplicate_metadata_version_is_rejected(self):
        for replacement in (b'Metadata-Version: 999', b'Metadata-Version: 2.4\nMetadata-Version: 2.4'):
            def change(files, prefix):
                files[prefix+'/METADATA'] = files[prefix+'/METADATA'].replace(b'Metadata-Version: 2.4', replacement)
            with self.subTest(replacement=replacement), self.assertRaises(r.ReleaseBindingError):
                self.verify(fixture(wheel_change=change))

    def test_added_project_wide_license_claim_is_rejected(self):
        for header in (b'License-Expression: MIT', b'License: MIT'):
            def change(files, prefix):
                files[prefix+'/METADATA'] = files[prefix+'/METADATA'].replace(b'\n\n', b'\n'+header+b'\n\n', 1)
            with self.subTest(header=header), self.assertRaises(r.ReleaseBindingError):
                self.verify(fixture(wheel_change=change))


if __name__ == '__main__':
    unittest.main()
