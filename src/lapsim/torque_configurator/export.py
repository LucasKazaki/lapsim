"""Exact local source distribution; never produces firmware or reads private data."""
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED

from lapsim.resources import repository_root
from .adapter import validate,validate_integration
from .profile import canonical,require
from .trace_mode import trace_mode


def write_json(path,value,*,limit=None):
    body=json.dumps(value,indent=2,allow_nan=False)+'\n'
    require(limit is None or len(body.encode('utf-8'))<=limit,'JSON output exceeds its byte bound')
    with Path(path).open('x',encoding='utf-8',newline='') as stream:
        stream.write(body)


def export_source(profile,destination,duration_ms=300,*,integration=None,attachments=None):
    root=repository_root();destination=Path(destination).resolve()
    for protected in ('src','controller','.git'):
        require(not destination.is_relative_to(root/protected),'Export must not modify source, imported core or Git metadata')
    require(not destination.exists(),'Export directory already exists; prior output is preserved')
    require(attachments is None or set(attachments)<={'selected-result.json','comparison-spec.json','result-reproduction.json'},'Unsupported export attachment')
    report=validate(profile,duration_ms) if integration is None else validate_integration(profile,integration)
    full_lap=report['schema']=='lapsim.torque-validation.v2'
    ten_lap=report['schema']=='lapsim.torque-validation.v3'
    mode=trace_mode(full_lap=full_lap,ten_lap=ten_lap)
    frames=report.pop('integration')['frames']
    experimental=profile.to_dict()['schema']=='lapsim.torque-profile.v2'
    files=list((root/'src').rglob('*.py'))
    files+=list((root/'controller/reference').glob('*.py'))
    files+=list((root/'controller/reference/native').glob('torque_*.[ch]'))
    files += [root/name for name in ('pyproject.toml','controller/import-manifest.json',
              'controller/integration/relocation-patches.json','controller/UPSTREAM.md')]
    files+=list((root/'configs/torque_profiles').glob('synthetic-*-v1.json'))
    # Derived library geometry can be embedded in selected results. Carry the
    # data provenance and original MIT notice with source packages as well.
    files+=list((root/'configs/courses').glob('*.json'))
    files+=list((root/'configs/courses/upstream/amz-fssim').glob('*'))
    files += [p for p in root.iterdir() if p.is_file() and p.name.upper().startswith(('LICENSE','COPYING'))]
    for file in files:
        require(not file.is_symlink() and file.resolve().is_relative_to(root),'Aliased source is not exported')
    destination.mkdir(parents=True,exist_ok=False)
    for file in files:
        target=destination/file.relative_to(root)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(file.read_bytes())
    write_json(destination/'profile.json',profile.to_dict())
    write_json(destination/'validation-trace.json',{'schema':mode.schema('trace'),
        'profile_sha256':profile.sha256,'frames':frames})
    write_json(destination/'validation-report.json',report)
    for name,value in (attachments or {}).items():write_json(destination/name,value)
    (destination/'run_controller.py').write_text(
        'from pathlib import Path\nimport sys\nsys.path.insert(0,str(Path(__file__).resolve().parent/"src"))\n'
        'from lapsim.torque_configurator.__main__ import main\nraise SystemExit(main())\n',encoding='utf-8',newline='')
    (destination/'README.txt').write_text(
        'SIMULATION-ONLY CONTROLLER SOURCE / CONFIGURATION\n\n'
        'Python 3.11+: python -I run_controller.py run --profile profile.json --trace validation-trace.json --output replay.json'+(' --ten-lap' if ten_lap else ' --full-lap' if full_lap else '')+'\n'
        'Use a Python environment with the simulator dependencies declared in pyproject.toml; third-party wheels are not bundled.\n'
        'Compare outputs_sha256 in replay.json and validation-report.json.\n'
        'Offline verification: python -I run_controller.py verify --package . --output verification.json\n'
        'The existing reference allocator/guard/fault/clock source is copied byte-for-byte with its provenance.\n'
        'No native binary, firmware image, CAN/serial driver, private evidence bundle or credentials are exported.\n'
        'No hardware timing, safety approval, measured-car calibration or road-ready claim is made.\n'
        'Architecture is explicit in profile.json: synthetic one-motor/open-differential RWD, one-motor locked/spool axle, two rear motors or four-motor AWD.\n'
        +('Experimental signed composed Python policy. The portable host C files remain the separate propulsive baseline.\n' if experimental else 'Propulsive equal allocation only.\n')+
        'Plant owns actuator response/friction; no calibrated team hardware is inferred.\n'
        'Existing repository licensing is unchanged; no additional license is asserted. Source provenance: controller/UPSTREAM.md.\n',
        encoding='utf-8',newline='')
    if attachments:
        with (destination/'README.txt').open('a',encoding='utf-8',newline='') as stream:
            stream.write('\nSELECTED CONFIGURED COURSE RESULT\n'
                'python -I run_controller.py reproduce-result --package . --output reproduced-result.json\n'
                'The trace is the selected course snapshot sequence, not a substitute preview.\n'
                'comparison-spec.json retains profiles, case, limits, source identity and comparison context.\n'
                'A bounded diagnostic has no complete-lap ranking or official points.\n')
    from .verify import member_limit
    sizes={p.relative_to(destination).as_posix():p.stat().st_size for p in destination.rglob('*') if p.is_file()}
    require(all(size<=member_limit(name,full_lap,ten_lap=ten_lap) for name,size in sizes.items()),'Export member exceeds its version byte bound')
    require(sum(sizes.values())<=mode.aggregate_bytes,'Export exceeds its version aggregate byte bound')
    hashes={p.relative_to(destination).as_posix():sha256(p.read_bytes()).hexdigest()
            for p in sorted(destination.rglob('*')) if p.is_file()}
    write_json(destination/'manifest.json',{'schema':mode.schema('source-export'),
        'profile_sha256':profile.sha256,'simulation_only':True,'files_sha256':hashes,
        'controller_source':report['source'],'license_status':'Existing repository choices unchanged; no additional license asserted'})
    with ZipFile(destination/'simulation-source.zip','x',compression=ZIP_DEFLATED) as archive:
        for name in sorted([*hashes,'manifest.json']):
            info=ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=ZIP_DEFLATED
            info.external_attr=0o644<<16
            archive.writestr(info,(destination/name).read_bytes())
    complete={'complete':True,'profile_sha256':profile.sha256,'outputs_sha256':report['outputs_sha256'],
              'zip_sha256':sha256((destination/'simulation-source.zip').read_bytes()).hexdigest(),
              'source_files':len(files),'cycles':report['cycles'],'simulation_only':True}
    write_json(destination/'completion.json',complete)
    return complete
