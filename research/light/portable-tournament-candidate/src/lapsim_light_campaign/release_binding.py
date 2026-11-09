"""Pure supplied-byte source/wheel consistency for the reviewed purelib profile.

The bootstrap must independently select and trust this checker and its helpers
BEFORE importing them. This cannot authenticate its own executing code, an
installed package, a runtime environment or native admission. No file, installed
RECORD, import from the supplied wheel, observation, extraction or process occurs.
"""
from hashlib import sha256
import re

from .distribution_observation import (_KNOWN_ERRORS, MAX_FILES, MAX_WHEEL_BYTES,
    _headers, _member_name, _one_header, _zip_entries)
from .input_contracts import decode, digest, is_sha256, require
from .runtime_observation import ObservationUnavailable

MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_CONTRACT_BYTES = 4 * 1024 * 1024
_NOTICE_PATHS = ('CORE_NOTICE.md', 'src/lapsim_light_course/data/LICENSE.md')


class ReleaseBindingError(ValueError):
    """Supplied bytes do not satisfy the supported release-binding profile."""


def _pin(raw, pin, cap):
    require(type(raw) is bytes and 0 < len(raw) <= cap and is_sha256(pin) and
            sha256(raw).hexdigest() == pin, 'Exact bounded independently pinned release bytes required')


def _verify(manifest_raw, contract_raw, wheel_raw, manifest_pin, wheel_pin):
    _pin(manifest_raw, manifest_pin, MAX_MANIFEST_BYTES)
    _pin(wheel_raw, wheel_pin, MAX_WHEEL_BYTES)
    require(type(contract_raw) is bytes and 0 < len(contract_raw) <= MAX_CONTRACT_BYTES,
            'Bounded immutable installation contract required')
    manifest = decode(manifest_raw, MAX_MANIFEST_BYTES)
    require(type(manifest) is dict and manifest.get('schema') in
            ('lapsim.light-tournament-source-integration.v39', 'lapsim.light-tournament-source-integration.v40',
             'lapsim.light-tournament-source-integration.v41') and
            type(manifest.get('files')) is list and type(manifest.get('entries_count')) is int and
            0 < len(manifest['files']) == manifest['entries_count'] <= MAX_FILES,
            'Bounded complete source manifest rows required')
    rows, names = {}, set()
    for row in manifest['files']:
        require(type(row) is dict and {'path', 'bytes', 'sha256'} <= row.keys(), 'Source row is incomplete')
        name = row['path']
        _member_name(name)
        require(name.casefold() not in names and type(row['bytes']) is int and
                0 < row['bytes'] <= MAX_WHEEL_BYTES and is_sha256(row['sha256']), 'Source row differs or collides')
        rows[name] = row
        names.add(name.casefold())
    require('INSTALL_CONTRACT.json' in rows and 'SOURCE_MANIFEST.json' not in rows,
            'Manifest must pin the install contract and exclude its own bytes')
    contract_row = rows['INSTALL_CONTRACT.json']
    require(len(contract_raw) == contract_row['bytes'] and sha256(contract_raw).hexdigest() == contract_row['sha256'],
            'Installation contract differs from the pinned source manifest')
    contract = decode(contract_raw, MAX_CONTRACT_BYTES)
    require(contract['schema'] == 'lapsim.light-current-source-install-contract.v1', 'Unsupported installation contract schema')
    selection = contract['source_distribution']['manifest_includes_exact_paths']
    require(type(selection) is list and len(selection) <= MAX_FILES and
            all(type(name) is str for name in selection) and len(set(selection)) == len(selection) and
            set(selection) == set(rows) | {'SOURCE_MANIFEST.json'} and
            contract['source_distribution']['file_count_including_source_manifest'] == len(selection),
            'Source selection differs from complete manifest coverage')
    project = contract['project']
    require(project['name'] == 'lapsim-light-tournament-source-candidate' and
            type(project['version']) is str and re.fullmatch(r'0\.0\.0\.dev[0-9]+', project['version']) and
            project['requires_python'] == '>=3.11' and project['required_third_party_runtime_dependencies'] == [],
            'Unsupported project/version/dependency profile')
    modules, data = project['modules'], contract['package_data']
    require(type(modules) is list and 0 < len(modules) <= MAX_FILES and
            type(data) is list and len(data) <= MAX_FILES, 'Bounded declared runtime inventory required')
    module_paths = []
    for item in modules:
        name = item['path']
        require(type(name) is str and name.startswith('src/') and name.endswith('.py'), 'Unsupported module source path')
        relative = name[4:-3]
        module = (relative[:-9] if relative.endswith('/__init__') else relative).replace('/', '.')
        require(item['module'] == module, 'Module spelling differs from source mapping')
        module_paths.append(name)
    data_paths = []
    for item in data:
        name = item['source_path']
        require(name == 'src/' + item['package'] + '/' + item['resource'] and not name.endswith('.py') and
                name in rows and item['raw_sha256'] == rows[name]['sha256'], 'Resource mapping or digest differs')
        data_paths.append(name)
    declared = module_paths + data_paths
    source_payload = {name for name in rows if name.startswith('src/')}
    require(len(set(declared)) == len(declared) and set(declared) == source_payload,
            'Module/resource declarations omit or duplicate source payload')
    packages = project['bundled_packages']
    require(type(packages) is list and packages and len(set(packages)) == len(packages) and
            all(type(name) is str and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) for name in packages) and
            all('src/' + name + '/__init__.py' in module_paths for name in packages) and
            {name.split('/')[1] for name in declared} == set(packages), 'Unsupported package layout')
    prefix, wheel_files, metadata_bytes = _zip_entries(wheel_raw)
    metadata = _headers(metadata_bytes[prefix + '/METADATA'])
    require(_one_header(metadata, 'Metadata-Version') == '2.4', 'Unsupported wheel core metadata version')
    for key, value in (('Name', project['name']), ('Version', project['version']), ('Requires-Python', project['requires_python'])):
        require(_one_header(metadata, key) == value, 'Wheel metadata differs: ' + key)
    require(prefix == project['name'].replace('-', '_') + '-' + project['version'] + '.dist-info',
            'Wheel dist-info differs from selected project')
    optional = contract['optional_verifier']
    require(optional['extra'] == 'admission-verifier' and optional['requirement'] == 'cryptography==50.0.2' and
            metadata.get_all('Provides-Extra', []) == [optional['extra']] and
            metadata.get_all('Requires-Dist', []) == [optional['requirement'] + '; extra == "' + optional['extra'] + '"'],
            'Wheel dependency/extra declarations differ; no implicit verifier install')
    require(metadata.get_all('License-File', []) == list(_NOTICE_PATHS), 'Wheel license declarations differ')
    require(not metadata.get_all('License-Expression', []) and not metadata.get_all('License', []),
            'No project-wide license grant is supplied by this release profile')
    wheel_headers = _headers(metadata_bytes[prefix + '/WHEEL'])
    require(_one_header(wheel_headers, 'Wheel-Version') == '1.0' and
            _one_header(wheel_headers, 'Root-Is-Purelib') == 'true' and
            wheel_headers.get_all('Tag', []) == ['py3-none-any'], 'Unsupported purelib wheel profile')
    expected = {name[4:]: rows[name] for name in declared}
    for name in _NOTICE_PATHS:
        require(name in rows, 'Source license notice missing')
        expected[prefix + '/licenses/' + name] = rows[name]
    scripts = contract['entry_points']['console_scripts']
    require(scripts == {'lapsim-light-evidence': 'lapsim_light_campaign.tournament_cli:main'},
            'Unsupported entrypoint profile; no native Start command inferred')
    generated = {
        prefix + '/entry_points.txt': b'[console_scripts]\nlapsim-light-evidence = lapsim_light_campaign.tournament_cli:main\n',
        prefix + '/top_level.txt': ''.join(name + '\n' for name in sorted(packages)).encode(),
    }
    for name, raw in generated.items():
        expected[name] = {'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}
    require(set(wheel_files) == set(expected) | {prefix + '/' + name for name in ('METADATA', 'WHEEL', 'RECORD')},
            'Wheel contains missing or unexpected payload/metadata files')
    for name, row in expected.items():
        require(wheel_files[name]['bytes'] == row['bytes'] and wheel_files[name]['sha256'] == row['sha256'],
                'Wheel/source bytes differ: ' + name)
    body = {'schema': 'lapsim.light-source-wheel-consistency.raw.v1',
        'source_manifest_raw_sha256': manifest_pin, 'install_contract_raw_sha256': sha256(contract_raw).hexdigest(),
        'wheel_raw_sha256': wheel_pin, 'distribution': project['name'], 'version': project['version'],
        'source_rows': len(rows), 'source_selection_paths': len(selection), 'runtime_modules': len(modules),
        'runtime_resources': len(data), 'wheel_record_files': len(wheel_files),
        'scope': 'SUPPLIED_IMMUTABLE_BYTES_ONLY_REQUIRES_INDEPENDENTLY_TRUSTED_CHECKER_BEFORE_IMPORT',
        'source_files_read': False,
        'installed_files_or_record_checked': False, 'supplied_wheel_imported_or_extracted': False,
        'verifier_code_authenticated_by_this_check': False, 'loaded_code_or_environment_authenticated': False,
        'native_admission_or_cleanup_performed': False, 'qualification_or_execution_authority': False}
    return {'binding': body, 'binding_sha256': digest(body)}


def verify_source_wheel_binding(source_manifest_raw, install_contract_raw, wheel_raw, *,
                                expected_source_manifest_sha256, expected_wheel_sha256):
    """Join distinct source/contract/wheel pins without disk or installed probing.

    Reuse bounded wheel framing/RECORD verification. Do not infer that supplied
    pins are independently authentic, or load the wheel to validate its source.
    Unknown owner/control exceptions and MemoryError propagate unchanged.
    """
    try:
        return _verify(source_manifest_raw, install_contract_raw, wheel_raw,
                       expected_source_manifest_sha256, expected_wheel_sha256)
    except ReleaseBindingError:
        raise
    except ObservationUnavailable as error:
        if type(error) is not ObservationUnavailable:
            raise
        raise ReleaseBindingError(str(error)) from error
    except Exception as error:
        if type(error) not in _KNOWN_ERRORS:
            raise
        raise ReleaseBindingError('Source/wheel binding unavailable: ' + str(error)) from error
