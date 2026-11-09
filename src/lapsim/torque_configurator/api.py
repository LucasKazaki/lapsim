"""Shared local-server actions; no hardware or external service routes."""
from pathlib import Path
import re
import stat
import sys
from uuid import uuid4

from lapsim.resources import repository_root
from .profile import VehicleProfile,example_profile,require
from .adapter import validate
from .export import export_source

_DEVICE_NAMES = frozenset(('con','prn','aux','nul') +
    tuple(name+str(i) for name in ('com','lpt') for i in range(1,10)))


def _no_alias(path):
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode) and
                not (getattr(info, 'st_file_attributes', 0) & 0x400),
                'Aliased simulator work/resource paths are unsupported')


def confined_file(root, parts):
    """Resolve an existing or new file beneath one explicitly selected mount."""
    require(parts and all(part and part not in ('.', '..') and not part.startswith('.') and
                not part.endswith(('.', ' ')) and part.split('.',1)[0].casefold() not in _DEVICE_NAMES and
                not any(ord(c) < 32 or ord(c) == 127 or c in '\\:' for c in part) for part in parts),
            'Invalid simulator resource/work path')
    root = Path(root)
    candidate = root.joinpath(*parts)
    _no_alias(candidate)
    require(candidate.resolve().is_relative_to(root.resolve()),
            'Simulator path leaves its selected root')
    return candidate


def resolve_work_directory(work_dir=None, *, resource_root=None, create=False):
    """Keep mutable studies outside installed resources; retain checkout work/.

    This selects local storage, not process ownership or native admission.
    Installed/frozen callers must name an explicit writable directory.
    """
    resources = Path(repository_root() if resource_root is None else resource_root).resolve()
    installed = (resources / 'build-info.json').is_file() or getattr(sys, 'frozen', False)
    if work_dir is None:
        require(not installed, 'Installed simulator requires an explicit absolute --work-dir outside package resources')
        work = resources / 'work'
    else:
        work = Path(work_dir).expanduser()
        require(work.is_absolute(), 'Use an absolute simulator --work-dir')
    _no_alias(work)
    work = work.resolve()
    require(work != Path(work.anchor), 'Choose a simulator work directory, not a filesystem root')
    if installed:
        forbidden = (resources, Path(__file__).resolve().parents[2])
        if resources.name == '_resources':
            forbidden += (resources.parent.parent,)
        require(not any(work.is_relative_to(root) for root in forbidden),
                'Simulator work directory must be outside installed package resources/site-packages')
    elif work.is_relative_to(resources):
        require(work.is_relative_to(resources / 'work'),
                'Checkout simulator outputs must stay under work/ or an explicit external directory')
    if create:
        work.mkdir(parents=True, exist_ok=True)
    require(not work.exists() or work.is_dir(), 'Simulator work path is not a directory')
    return work


def action(name,body,*,work_dir=None):
    if name=='compare':
        require(type(body) is dict and set(body)<={'profile','reference_architecture','duration_ms','course','course_bundle'},'Unsupported comparison fields')
        from .comparison import compare,save_comparison
        profile=VehicleProfile.from_dict(body.get('profile'))
        architecture=body.get('reference_architecture')
        if not isinstance(architecture,str):raise ValueError('Reference architecture is required')
        reference=example_profile(architecture)
        if profile.to_dict()['schema']=='lapsim.torque-profile.v2':
            from .policy import experimental_profile
            reference=experimental_profile(body.get('reference_architecture'))
        work = resolve_work_directory(work_dir, create=True)
        study=compare([profile,reference],duration_ms=body.get('duration_ms',1000),course=body.get('course','stadium'),course_bundle=body.get('course_bundle'))
        relative=Path('work')/('torque-comparison-'+uuid4().hex[:12]);study['configured_study']=relative.as_posix()
        save_comparison(study,confined_file(work, (relative.name,)))
        return {'directory':relative.as_posix(),'fingerprint':study['fingerprint'],'runs':len(study['runs']),
                'viewer_url':'/web/tournament.html?configured='+relative.name.removeprefix('torque-comparison-'),
                'scope':'Bounded configured diagnostic; elapsed/energy/slip only, no lap ranking or official points'}
    if name=='export-result':
        require(type(body) is dict and set(body)=={'study','run_id'},'Study and selected run identity required')
        require(isinstance(body['study'],str) and re.fullmatch(r'work/torque-comparison-[a-f0-9]{12}',body['study']),
                'Select a saved local configured study')
        from .comparison import export_selected,STUDY_BYTE_LIMIT
        from .verify import bounded_json
        work = resolve_work_directory(work_dir, create=True)
        directory=confined_file(work, (Path(body['study']).name,))
        study=bounded_json(confined_file(work, (directory.name, 'replay.json')),limit=STUDY_BYTE_LIMIT)
        relative=Path('work')/('torque-selected-'+uuid4().hex[:12])
        result=export_selected(study,body['run_id'],confined_file(work, (relative.name,)))
        return {**result,'directory':relative.as_posix(),'package_url':'/'+relative.as_posix()+'/simulation-source.zip',
                'report_url':'/'+relative.as_posix()+'/result-reproduction.json',
                'transfer_status':'Saved locally; browser download delivery remains unverified'}
    require(type(body) is dict and set(body)<= {'profile','duration_ms'},'Unsupported configurator request fields')
    profile=VehicleProfile.from_dict(body.get('profile'))
    if name=='validate':
        value={'valid':True,'profile_sha256':profile.sha256,'architecture':profile.to_dict()['architecture'],
                'scope':'synthetic simulation controller; no hardware or official-points claim'}
        if profile.to_dict()['schema']=='lapsim.torque-profile.v2':
            from .policy import PolicySpec
            spec=PolicySpec.from_dict(profile.to_dict()['controller'],profile.actuation.topology_id)
            value.update(active_policy_parameters=spec.active_parameters,effective_policy_sha256=spec.effective_identity)
        return value
    require(name in ('preview','export'),'Unknown configurator action')
    duration=body.get('duration_ms',300)
    if name=='preview':return validate(profile,duration)
    work = resolve_work_directory(work_dir, create=True)
    relative=Path('work')/('torque-export-'+uuid4().hex[:12])
    completed=export_source(profile,confined_file(work, (relative.name,)),duration)
    return {**completed,'directory':relative.as_posix(),'package_url':'/'+relative.as_posix()+'/simulation-source.zip',
            'report_url':'/'+relative.as_posix()+'/validation-report.json',
            'transfer_status':'saved locally; browser download delivery is unverified'}
