"""Shared local-server actions; no hardware or external service routes."""
from pathlib import Path
import re
from uuid import uuid4

from lapsim.resources import repository_root
from .profile import VehicleProfile,example_profile,require
from .adapter import validate
from .export import export_source


def action(name,body):
    if name=='compare':
        require(type(body) is dict and set(body)<={'profile','reference_architecture','duration_ms','course','course_bundle'},'Unsupported comparison fields')
        from .comparison import compare,save_comparison
        profile=VehicleProfile.from_dict(body.get('profile'))
        reference=example_profile(body.get('reference_architecture'))
        if profile.to_dict()['schema']=='lapsim.torque-profile.v2':
            from .policy import experimental_profile
            reference=experimental_profile(body.get('reference_architecture'))
        study=compare([profile,reference],duration_ms=body.get('duration_ms',1000),course=body.get('course','stadium'),course_bundle=body.get('course_bundle'))
        relative=Path('work')/('torque-comparison-'+uuid4().hex[:12]);study['configured_study']=relative.as_posix()
        save_comparison(study,repository_root()/relative)
        return {'directory':relative.as_posix(),'fingerprint':study['fingerprint'],'runs':len(study['runs']),
                'viewer_url':'/web/tournament.html?configured='+relative.name.removeprefix('torque-comparison-'),
                'scope':'Bounded configured diagnostic; elapsed/energy/slip only, no lap ranking or official points'}
    if name=='export-result':
        require(type(body) is dict and set(body)=={'study','run_id'},'Study and selected run identity required')
        require(isinstance(body['study'],str) and re.fullmatch(r'work/torque-comparison-[a-f0-9]{12}',body['study']),
                'Select a saved local configured study')
        from .comparison import export_selected,STUDY_BYTE_LIMIT
        from .verify import bounded_json
        directory=(repository_root()/body['study']).resolve()
        require(directory.is_relative_to(repository_root()/'work'),'Study path leaves the local work directory')
        study=bounded_json(directory/'replay.json',limit=STUDY_BYTE_LIMIT)
        relative=Path('work')/('torque-selected-'+uuid4().hex[:12])
        result=export_selected(study,body['run_id'],repository_root()/relative)
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
    relative=Path('work')/('torque-export-'+uuid4().hex[:12])
    completed=export_source(profile,repository_root()/relative,duration)
    return {**completed,'directory':relative.as_posix(),'package_url':'/'+relative.as_posix()+'/simulation-source.zip',
            'report_url':'/'+relative.as_posix()+'/validation-report.json',
            'transfer_status':'saved locally; browser download delivery is unverified'}
