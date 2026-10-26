"""Offline package consistency and isolated reproduction, without a plant rerun."""
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile

import pytest

from lapsim.torque_configurator import example_profile
from lapsim.torque_configurator.export import export_source
from lapsim.torque_configurator.session import read_trace
from lapsim.torque_configurator.verify import verify_package


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


def refresh_manifest(package, name):
    manifest=read(package/'manifest.json')
    manifest['files_sha256'][name]=sha256((package/name).read_bytes()).hexdigest()
    save(package/'manifest.json',manifest)


@pytest.fixture(scope='module')
def original(tmp_path_factory):
    path=tmp_path_factory.mktemp('verification-base')/'source'
    export_source(example_profile(),path,100)
    return path


@pytest.fixture
def package(original,tmp_path):
    return Path(shutil.copytree(original,tmp_path/'source'))


def test_valid_package_matches_recorded_outputs_and_archive(package):
    result=verify_package(package)
    assert result['verified'] and result['repeat_exact'] and result['recorded_outputs_match']
    assert result['archive_hash_verified'] and result['cycles']==10
    assert result['profile_sha256']==example_profile().sha256
    assert result['manifest_files_verified']==len(read(package/'manifest.json')['files_sha256'])
    assert result['simulation_only'] and 'not a signature' in result['scope']


def test_extracted_package_needs_neither_original_checkout_nor_embedded_zip(original,tmp_path):
    target=tmp_path/'extracted'
    with ZipFile(original/'simulation-source.zip') as archive:
        archive.extractall(target)  # Only this fixture's known, just-generated ZIP.
    result=verify_package(target)
    assert result['verified'] and not result['archive_hash_verified']


@pytest.mark.parametrize('name',['profile.json','src/lapsim/torque_configurator/session.py',
                                'controller/reference/allocator.py'])
def test_changed_artifact_fails_before_replay(package,name):
    with (package/name).open('ab') as stream:stream.write(b'\n# changed\n')
    with pytest.raises(ValueError,match='manifest mismatch'):verify_package(package)


def test_unmanifested_source_is_rejected(package):
    (package/'src/unlisted.py').write_text('raise RuntimeError("must never execute")')
    with pytest.raises(ValueError,match='Unmanifested source'):verify_package(package)


@pytest.mark.parametrize('name',['../outside.py','C:/outside.py','src\\outside.py','/outside.py','src/./extra.py'])
def test_manifest_paths_are_bounded_before_reading_outside_files(package,name):
    manifest=read(package/'manifest.json');manifest['files_sha256'][name]='0'*64
    save(package/'manifest.json',manifest)
    with pytest.raises(ValueError,match='path|paths'):verify_package(package)


@pytest.mark.parametrize('mutation',[
    lambda report:report.update(outputs_sha256='0'*64),
    lambda report:report.update(cycles=11),
    lambda report:report['profile']['vehicle'].update(mass_kg=310.),
    lambda report:report.update(equivalent=False),
    lambda report:report.update(repeat_exact=False),
])
def test_self_consistent_manifest_cannot_hide_mismatched_recorded_report(package,mutation):
    report=read(package/'validation-report.json');mutation(report)
    save(package/'validation-report.json',report);refresh_manifest(package,'validation-report.json')
    with pytest.raises(ValueError,match='report|reproduce'):verify_package(package)


def test_trace_identity_is_checked_independently_of_file_hash(package):
    trace=read(package/'validation-trace.json');trace['profile_sha256']='0'*64
    save(package/'validation-trace.json',trace);refresh_manifest(package,'validation-trace.json')
    with pytest.raises(ValueError,match='Trace schema/profile'):verify_package(package)


def test_wrong_controller_identity_is_rejected(package):
    manifest=read(package/'manifest.json');manifest['controller_source']['backend']='other'
    save(package/'manifest.json',manifest)
    with pytest.raises(ValueError,match='controller identity'):verify_package(package)


def test_changed_archive_fails_completion_checksum(package):
    with (package/'simulation-source.zip').open('ab') as stream:stream.write(b'changed')
    with pytest.raises(ValueError,match='Archive hash'):verify_package(package)


def test_archive_contents_must_match_manifest_even_with_fresh_archive_checksum(package):
    with ZipFile(package/'simulation-source.zip','a') as archive:
        archive.writestr('unrecorded.py','raise RuntimeError("must never execute")')
    completed=read(package/'completion.json')
    completed['zip_sha256']=sha256((package/'simulation-source.zip').read_bytes()).hexdigest()
    save(package/'completion.json',completed)
    with pytest.raises(ValueError,match='Archive contents'):verify_package(package)


@pytest.mark.parametrize('name',['manifest.json','validation-report.json','completion.json'])
def test_metadata_requires_object_not_list(package,name):
    save(package/name,[])
    if name=='validation-report.json':refresh_manifest(package,name)
    with pytest.raises(ValueError):verify_package(package)


def test_oversized_trace_is_rejected_before_json_parse(tmp_path):
    path=tmp_path/'large.json';path.write_bytes(b' '*1_000_001)
    with pytest.raises(ValueError,match='1 MB'):read_trace(example_profile(),path)


def test_exported_verifier_executes_with_isolated_python_and_no_private_bundle(package,tmp_path):
    output=tmp_path/'verification.json'
    env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'}
    env['LAPSIM_DATA_BUNDLE']=str(tmp_path/'deliberately-unavailable-private-bundle')
    command=[sys.executable,'-I',str(package/'run_controller.py'),'verify','--package',str(package),
             '--output',str(output)]
    completed=subprocess.run(command,cwd=tmp_path,env=env,capture_output=True,text=True,timeout=60)
    assert completed.returncode==0,completed.stderr
    assert read(output)['recorded_outputs_match']
    saved=output.read_bytes()
    repeated=subprocess.run(command,cwd=tmp_path,env=env,capture_output=True,text=True,timeout=60)
    assert repeated.returncode==2 and 'exists' in repeated.stderr
    assert output.read_bytes()==saved
