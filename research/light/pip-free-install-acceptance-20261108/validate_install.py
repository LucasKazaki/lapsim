"""Bounded development installation check for the frozen dev37 release.

Uses explicit reviewed interpreters and an exact local wheel only. This is not
a native tournament installer, guard, allocation, cleanup proof or Start command.
Native use still requires the original owner's separate admission and controls.
"""
from hashlib import sha256
from pathlib import Path
import argparse,json,os,subprocess,time

NAME = 'lapsim-light-tournament-source-candidate'
VERSION = '0.0.0.dev37'
WHEEL_SHA = '13655550284cd2abbfda591d20bbbc93b0bc4dd46a8ccd060b00d764c77218aa'
MANIFEST_SHA = '85f56f361f2596e918c13c1271c08629d968537f23284e513ef64113b22f2456'
SOURCE_COMMIT = '0ba674bc9960335cd3d96a01c533d9ca9eb7d12b'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base-python','installer-python','wheel','source-root','output'):
        parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args()
    for path in (args.base_python,args.installer_python,args.wheel,args.source_root,args.output):
        if not path.is_absolute():
            raise ValueError('Explicit absolute paths required; no PATH or environment fallback')
    if args.wheel.stat().st_size != 311345:
        raise ValueError('Frozen wheel byte count differs')
    wheel = args.wheel.read_bytes()
    with (args.source_root/'SOURCE_MANIFEST.json').open('rb') as stream:
        manifest_raw = stream.read(16*1024*1024+1)
    if len(manifest_raw) > 16*1024*1024:
        raise ValueError('Source manifest exceeds bound')
    if sha256(wheel).hexdigest() != WHEEL_SHA or sha256(manifest_raw).hexdigest() != MANIFEST_SHA:
        raise ValueError('Frozen dev37 wheel/source manifest differs')
    manifest = json.loads(manifest_raw)
    rows = {r['path']:r for r in manifest['files']}
    with (args.source_root/'INSTALL_CONTRACT.json').open('rb') as stream:
        contract_raw = stream.read(4*1024*1024+1)
    if len(contract_raw) > 4*1024*1024:
        raise ValueError('Installation contract exceeds bound')
    if sha256(contract_raw).hexdigest() != rows['INSTALL_CONTRACT.json']['sha256']:
        raise ValueError('Frozen contract differs')
    args.output.mkdir()  # Never reuse or overwrite an earlier validation namespace.
    commands = []
    # This fixture owns only its fresh target. Ambient pip destinations/logs or
    # configuration must not redirect writes elsewhere; leave OS/proxy/CA state.
    environment = {k:v for k,v in os.environ.items() if not k.upper().startswith('PIP_')}
    environment.update(PYTHONDONTWRITEBYTECODE='1', PIP_CONFIG_FILE=os.devnull,
                       PIP_DISABLE_PIP_VERSION_CHECK='1')
    started = time.monotonic()

    def run(label, argv, expected):
        remaining = 60 - (time.monotonic()-started)
        if remaining <= 0:
            raise TimeoutError('Finite development acceptance window exhausted')
        row = {'label':label,'argv':[str(x) for x in argv], 'expected_exit':expected,'actual_exit':None,
               'state':'attempted_outcome_unresolved', 'descendant_cleanup_proven':False}
        commands.append(row)
        (args.output/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        # Unknown launch/timeout/control exceptions propagate. The prewritten
        # attempt remains unresolved; only returned commands have logs below.
        # Actual unreturned output/OS cleanup remains the outer owner's duty.
        result = subprocess.run(row['argv'], cwd=args.output, env=environment,
                                capture_output=True, text=True, timeout=min(20,remaining))
        (args.output/(label+'.stdout')).write_text(result.stdout)
        (args.output/(label+'.stderr')).write_text(result.stderr)
        row.update(actual_exit=result.returncode,state='returned')
        (args.output/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        if result.returncode != expected:
            raise RuntimeError('Unexpected exit; retained evidence: '+label)
        return result

    version = run('installer-version',[args.installer_python,'-I','-B','-m','pip','--version'],0)
    if not version.stdout.startswith('pip 26.2.2 '):
        raise ValueError('Reviewed external pip26.2.2 required; no installer upgrade attempted')
    target = args.output/'runtime'
    run('create-pip-free-runtime',[args.base_python,'-I','-B','-m','venv','--without-pip',target],0)
    python = target/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    lock = args.output/'exact-wheel.lock'
    lock.write_text(args.wheel.as_uri()+' --hash=sha256:'+WHEEL_SHA+'\n')
    install = ['install','--no-cache-dir','--no-index','--no-deps','--no-compile','--require-hashes','-r',lock]
    missing = run('documented-target-pip-refusal',[python,'-I','-B','-m','pip',*install],1)
    if 'No module named pip' not in missing.stderr:
        raise ValueError('Expected missing-pip counterexample was not established')
    run('external-installer-success',[args.installer_python,'-I','-B','-m','pip','--python',python,*install],0)
    query = 'import importlib.metadata as m,json,sys,sysconfig;print(json.dumps({"prefix":sys.prefix,"base_prefix":sys.base_prefix,"purelib":sysconfig.get_path("purelib"),"distributions":sorted((d.metadata["Name"],d.version) for d in m.distributions())}))'
    facts = json.loads(run('runtime-inventory',[python,'-I','-B','-c',query],0).stdout)
    if facts['distributions'] != [[NAME,VERSION]] or facts['prefix'] == facts['base_prefix']:
        raise ValueError('Runtime is not isolated with only the exact project distribution')
    purelib = Path(facts['purelib'])
    if not purelib.resolve().is_relative_to(target.resolve()):
        raise ValueError('Runtime package location escapes this new environment')
    checked = []
    for name,row in sorted(rows.items()):
        if not name.startswith('src/'):
            continue
        path = purelib/name[4:]
        if path.is_symlink() or not path.resolve().is_relative_to(target.resolve()):
            raise ValueError('Installed payload alias or escape')
        raw = path.read_bytes()
        if len(raw) != row['bytes'] or sha256(raw).hexdigest() != row['sha256']:
            raise ValueError('Installed payload differs: '+name)
        checked.append(name)
    if len(checked) != 69:
        raise ValueError('Frozen63module/6resource inventory differs')
    missing = run('target-remains-pip-free',[python,'-I','-B','-m','pip','--version'],1)
    if 'No module named pip' not in missing.stderr:
        raise ValueError('Post-install pip-free condition was not established')
    binding = json.loads(run('installed-release-binding',[python,'-I','-B','-m','lapsim_light_campaign.tournament_cli',
        'verify-release','--source-manifest',args.source_root/'SOURCE_MANIFEST.json','--manifest-sha256',MANIFEST_SHA,
        '--install-contract',args.source_root/'INSTALL_CONTRACT.json','--wheel',args.wheel,'--wheel-sha256',WHEEL_SHA],0).stdout)
    if binding['binding']['version'] != VERSION or binding['binding']['qualification_or_execution_authority'] is not False:
        raise ValueError('Unexpected supplied-byte binding result')
    report = {'scope':'DEVELOPMENT_PIP_FREE_OFFLINE_INSTALL_ACCEPTANCE_NOT_NATIVE_AUTHENTICATION_OR_TOURNAMENT',
        'frozen_source_commit':SOURCE_COMMIT,'source_manifest_sha256':MANIFEST_SHA,'wheel_sha256':WHEEL_SHA,
        'commands':commands,'runtime_facts':facts,'installed_payloads_verified':len(checked),
        'pip_installed_into_runtime':False,'numerical_suite_rerun':False,
        'ambient_pip_options_removed_for_child':True,'child_pip_config_file':os.devnull,
        'attempts_recorded_before_launch':True,'output_logs_scope':'RETURNED_COMMANDS_ONLY_UNRETURNED_OUTPUT_AND_CLEANUP_REQUIRE_OUTER_OWNER',
        'native_jobs_or_resource_probes_or_leases':False,'network_download_or_resolution':False,
        'windows_qualification':False,'qualification_or_execution_authority':False,
        'seconds':time.monotonic()-started}
    (args.output/'result.json').open('x').write(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('commands','runtime_facts')},indent=2))


if __name__ == '__main__':
    main()
