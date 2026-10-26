"""Offline source/config/trace consistency, never a hardware or signature claim."""
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path,PurePosixPath
from zipfile import BadZipFile,ZipFile

from lapsim.experiments.controller_backend import controller_source_identity
from .profile import canonical,load_profile,require
from .session import replay,read_trace
from .trace_mode import trace_mode


def bounded_json(path,limit=2_000_000):
    with path.open('rb') as stream:raw=stream.read(limit+1)
    require(len(raw)<=limit,'Verification metadata exceeds its byte bound')
    value=json.loads(raw)
    require(type(value) is dict,'Verification metadata must be an object')
    return value


def member_limit(name,full_lap,*,ten_lap=False):
    mode=trace_mode(full_lap=full_lap,ten_lap=ten_lap)
    if name=='selected-result.json':return mode.selected_bytes
    if name=='validation-trace.json':return mode.trace_bytes
    return 8_000_000


def verify_archive(path,hashes,manifest_path,*,full_lap=False,ten_lap=False):
    """Inspect bounded members without extracting or executing package source."""
    expected={**hashes,'manifest.json':sha256(manifest_path.read_bytes()).hexdigest()}
    try:
        with ZipFile(path) as archive:
            members=archive.infolist()
            require(len(members)==len(expected) and {m.filename for m in members}==expected.keys(),
                    'Archive contents differ from the source manifest')
            require(sum(m.file_size for m in members)<=trace_mode(full_lap=full_lap,ten_lap=ten_lap).aggregate_bytes,'Archive contents exceed the byte bound')
            for member in members:
                limit=member_limit(member.filename,full_lap,ten_lap=ten_lap)
                require(not member.is_dir() and member.file_size<=limit,'Archive contents include an oversized member')
                with archive.open(member) as stream:raw=stream.read(limit+1)
                require(len(raw)<=limit and sha256(raw).hexdigest()==expected[member.filename],
                        'Archive contents differ from the source manifest')
    except BadZipFile as error:
        raise ValueError('Archive contents are not a valid source ZIP') from error


def verify_package(directory):
    directory=Path(directory).resolve()
    manifest=bounded_json(directory/'manifest.json')
    require(manifest.get('schema') in ('lapsim.torque-source-export.v1','lapsim.torque-source-export.v2','lapsim.torque-source-export.v3') and manifest.get('simulation_only') is True,
            'Unsupported simulation source manifest')
    full_lap=manifest['schema']=='lapsim.torque-source-export.v2'
    ten_lap=manifest['schema']=='lapsim.torque-source-export.v3'
    total_limit=trace_mode(full_lap=full_lap,ten_lap=ten_lap).aggregate_bytes
    hashes=manifest.get('files_sha256')
    require(type(hashes) is dict and 1<=len(hashes)<=1000,'Bounded source manifest required')
    required={'profile.json','validation-trace.json','validation-report.json','run_controller.py',
              'src/lapsim/torque_configurator/session.py','src/lapsim/torque_configurator/profile.py',
              'controller/reference/allocator.py'}
    require(required<=hashes.keys(),'Manifest is missing required configuration/control sources')
    total_bytes=0
    for name,expected in hashes.items():
        require(isinstance(name,str) and name and '\\' not in name,'Manifest paths must be relative POSIX paths')
        relative=PurePosixPath(name)
        require(not relative.is_absolute() and '..' not in relative.parts and ':' not in name
                and relative.as_posix()==name,'Manifest path leaves the source package')
        path=directory/name
        require(not path.is_symlink() and path.resolve().is_relative_to(directory),'Aliased source path is not verified')
        require(path.is_file() and path.stat().st_size<=member_limit(name,full_lap,ten_lap=ten_lap),'Missing or oversized manifest file')
        total_bytes+=path.stat().st_size
        require(total_bytes<=total_limit,'Source package exceeds the byte bound')
        require(isinstance(expected,str) and sha256(path.read_bytes()).hexdigest()==expected,'Source/config manifest mismatch: '+name)
    for base in ('src','controller/reference'):
        for path in (directory/base).rglob('*'):
            if path.is_file() and path.suffix in ('.py','.c','.h'):
                require(path.relative_to(directory).as_posix() in hashes,'Unmanifested source file')
    profile=load_profile(directory/'profile.json')
    report=bounded_json(directory/'validation-report.json')
    require(report.get('schema')==trace_mode(full_lap=full_lap,ten_lap=ten_lap).schema('validation'),'Unsupported recorded validation report')
    if full_lap or ten_lap:
        require(isfinite(report['energy_residual_j']) and type(report.get('energy_ledger_pass')) is bool
                and report['energy_ledger_pass']==(abs(report['energy_residual_j'])<.5),
                'Recorded energy ledger verdict differs')
    require(profile.sha256==manifest['profile_sha256']==report.get('profile_sha256'),'Profile/report identity mismatch')
    require(report.get('profile')==profile.to_dict() and report.get('equivalent') is True
            and report.get('repeat_exact') is True,'Recorded validation report profile/equivalence mismatch')
    require(report.get('source')==manifest.get('controller_source')==controller_source_identity(),
            'Reference controller identity differs from the recorded package')
    for name,expected in report['source']['source_files_sha256'].items():
        require(hashes.get(name)==expected,'Manifest/controller source identity mismatch')
    frames=read_trace(profile,directory/'validation-trace.json',full_lap=full_lap,ten_lap=ten_lap)
    outputs=replay(profile,frames,full_lap=full_lap,ten_lap=ten_lap)
    require(outputs==replay(profile,frames,full_lap=full_lap,ten_lap=ten_lap),'Standalone repeat differs')
    output_hash=sha256(canonical(outputs).encode()).hexdigest()
    require(output_hash==report.get('outputs_sha256') and len(outputs)==report.get('cycles'),
            'Recorded controller output hash/cycle count does not reproduce')
    archive_verified=False
    if (directory/'completion.json').exists():
        completed=bounded_json(directory/'completion.json')
        require(completed.get('complete') is True and completed.get('simulation_only') is True,'Source package completion is not confirmed')
        require(completed.get('profile_sha256')==profile.sha256 and completed.get('outputs_sha256')==output_hash,
                'Completion identity differs from the recorded outputs')
        archive=directory/'simulation-source.zip'
        require(archive.is_file() and archive.stat().st_size<=total_limit,'Completed archive is missing or oversized')
        require(sha256(archive.read_bytes()).hexdigest()==completed.get('zip_sha256'),'Archive hash differs from completion record')
        verify_archive(archive,hashes,directory/'manifest.json',full_lap=full_lap,ten_lap=ten_lap)
        archive_verified=True
    return {'schema':'lapsim.torque-package-verification.v1','verified':True,'simulation_only':True,
            'profile_sha256':profile.sha256,'outputs_sha256':output_hash,'cycles':len(outputs),
            'manifest_files_verified':len(hashes),'repeat_exact':True,'recorded_outputs_match':True,
            'archive_hash_verified':archive_verified,
            'scope':'manifest/report consistency and recorded-trace reproduction; not a signature, hardware timing or safety certificate'}
