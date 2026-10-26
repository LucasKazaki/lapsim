"""Configured diagnostics in the existing tournament rollout/replay workflow."""
from dataclasses import asdict,replace
from hashlib import sha256
from pathlib import Path
import re

from lapsim.resources import repository_root
from lapsim.experiments.controller_backend import controller_source_identity
from lapsim.experiments.controller_tournament import SCHEMA,UPSTREAM
from lapsim.experiments.tournament_rollout import Case,Controller,rollout,CONFIGURED_REFERENCE
from .profile import VehicleProfile,canonical,require
from .export import export_source,write_json
from .verify import bounded_json,verify_package

ALIASES={'synthetic_independent_rear_rwd_v1':'synthetic_rwd',
         'synthetic_single_motor_open_diff_rwd_v1':'synthetic_single_motor_rwd',
         'synthetic_independent_four_awd_v1':'synthetic_awd','synthetic_single_motor_locked_axle_rwd_v1':'synthetic_spool_rwd'}


def expected_strategy(profile):
    value=profile.to_dict()
    return {'philosophy':'composed_policy','specification':value['controller']} if value['schema']=='lapsim.torque-profile.v2' else asdict(Controller(CONFIGURED_REFERENCE))


def digest(value):return sha256(canonical(value).encode()).hexdigest()


def source_identity():
    root=repository_root()
    files=list((root/'src').rglob('*.py'))
    require(all(not p.is_symlink() and p.resolve().is_relative_to(root) for p in files),'Aliased numerical source is not recorded')
    names=[p.relative_to(root).as_posix() for p in files]
    return {'files_sha256':{p:sha256((root/p).read_bytes()).hexdigest() for p in sorted(names)},
            'controller':controller_source_identity()}


STUDY_BYTE_LIMIT=768_000_000
SELECTED_BYTE_LIMIT=256_000_000


def execute(profile,case,*,full_lap=False):
    return rollout(Controller(CONFIGURED_REFERENCE),case,profile=ALIASES[profile.actuation.topology_id],
                   configured_profile=profile,configured_full_lap=full_lap)


def compare(profiles,*,duration_ms=1000,course='stadium',course_bundle=None,full_lap=False,ten_lap=False):
    require(isinstance(profiles,list) and len(profiles)==2 and all(type(p) is VehicleProfile for p in profiles),
            'Exactly two validated profiles are required')
    require(profiles[0].sha256!=profiles[1].sha256,'Choose distinct profiles or change an input before comparing')
    require(type(full_lap) is bool,'Full-lap comparison mode must be Boolean')
    require(type(ten_lap) is bool and not (full_lap and ten_lap),'Choose one explicit lap/round mode')
    maximum=600000 if ten_lap else 60000 if full_lap else 2000
    require(type(duration_ms) is int and 100<=duration_ms<=maximum and duration_ms%10==0,
            f'Comparison duration must be 100-{maximum} integer ms in 10 ms steps')
    require(course in ('stadium','autocross','bundle'),'Choose a supported course or validated bundle')
    starts=[(p.policy['initial_soc'],p.policy['initial_speed_mps'],p.actuation.pack_voltage_v) for p in profiles]
    require(starts[0]==starts[1],'Comparison requires matching initial SOC, speed and pack voltage; profile values are not silently overridden')
    case=Case('configured_full_lap_acceptance' if full_lap else 'configured_diagnostic',course=course,course_bundle=course_bundle,duration_s=duration_ms/1000,
              initial_soc=starts[0][0],pack_voltage_v=starts[0][2],regen_available=all(p.to_dict()['schema']=='lapsim.torque-profile.v2' for p in profiles),laps=10 if ten_lap else 1)
    source=source_identity()
    records=[execute(profile,case,full_lap=full_lap or ten_lap) for profile in profiles]
    return assemble(profiles,case,records,source,full_lap=full_lap or ten_lap)


def assemble(profiles,case,records,source,*,full_lap):
    """Presentation assembly only; execution and selected reproduction stay separate."""
    runs={};candidates={};baselines=[]
    for profile,record in zip(profiles,records):
        run_id=digest(record)[:20];candidate=profile.sha256[:20]
        runs[run_id]=record;candidates[candidate]={'controller':record['controller'],'run_ids':[run_id],
            'summary':{'eligible':False,'fitness':None,'mean_lap_time_s':None,
                       'mean_net_energy_kwh':record['metrics']['net_energy_kwh'],
                       'failures':int(not record['configuration']['acceptance']['passed']) if full_lap else (0 if record['status']=='time_limit' else 1)}}
        baselines.append(candidate)
    specification={'seed':0,'profile':'configured_profiles','upstream':UPSTREAM,'profiles':[p.to_dict() for p in profiles],
        'training':[asdict(case)],'duration_ms':round(case.duration_s*1000),'strategy':CONFIGURED_REFERENCE,
        'objective':{'name':'engineering_proxy','expression':'lap_time_s + 120 * net_energy_kwh','lower_is_better':True,
                     'fsae_points_enabled':False,'ranking_enabled':False,'reason':'Bounded course diagnostic; compare elapsed time, energy and slip; no lap ranking'},
        'resources':{'workers':1,'maximum_runs':2,'gpu_physics':False},
        'scenario_inputs':{'status':'Explicit synthetic profiles; no measured team hardware or official scoring'}}
    if full_lap:
        specification['mode']='ten_lap_acceptance_v1' if case.laps==10 else 'full_lap_acceptance_v1'
        specification['objective']['reason']='Synthetic full-lap acceptance; show observed laps and failures without ranking, optimization or official points'
    result={'schema':SCHEMA,'status':'configured_full_lap_acceptance' if full_lap else 'configured_diagnostic','specification':specification,
        'sources':source['files_sha256'],'configured_source':source,'runs':runs,'candidates':candidates,
        'baselines':baselines,'generations':[],'holdout':{},'best_so_far':None,'diagnostic_ids':[]}
    result['fingerprint']=study_fingerprint(result)
    return result


def compare_saved_baselines(paths):
    require(isinstance(paths,list) and len(paths)==2,'Choose exactly two saved baseline receipts')
    source=source_identity()
    receipts=[bounded_json(Path(path),limit=SELECTED_BYTE_LIMIT) for path in paths]
    profiles=[];records=[]
    for receipt in receipts:
        require(receipt.get('schema')=='lapsim.configured-full-lap-baseline.v1','A full-lap baseline receipt is required')
        require(receipt.get('source')==source,'Saved baseline source identity changed; do not mix revisions')
        record=receipt['record'];configuration=record['configuration']
        profile=VehicleProfile.from_dict(configuration['profile'])
        require(configuration.get('mode') in ('full_lap_acceptance_v1','ten_lap_acceptance_v1') and 'acceptance' in configuration,
                'Saved baseline has no versioned per-tick acceptance audit')
        require(configuration['acceptance'].get('schema')=='lapsim.configured-full-lap-acceptance.v1'
                and type(configuration['acceptance'].get('passed')) is bool,'Saved acceptance verdict is invalid')
        require(configuration['profile_sha256']==profile.sha256 and record['profile']==ALIASES[profile.actuation.topology_id]
                and record['actuation']==profile.to_dict()['actuation'],'Saved baseline profile/topology identity mismatch')
        require(configuration['source']==controller_source_identity() and record['controller']==expected_strategy(profile),
                'Saved baseline controller identity mismatch')
        require(not record['eligible'] and record['metrics']['fitness'] is None,'Configured baseline cannot enable ranking')
        require(record['parameter_overrides']=={},'Unrecorded physical overrides are unsupported')
        profiles.append(profile);records.append(record)
    require(profiles[0].sha256!=profiles[1].sha256,'Choose distinct configured profiles')
    starts=[(p.policy['initial_soc'],p.policy['initial_speed_mps'],p.actuation.pack_voltage_v) for p in profiles]
    require(starts[0]==starts[1],'Saved baseline initial conditions differ')
    for key in ('case','course','driver','clocks','environment'):
        require(records[0][key]==records[1][key],'Saved baselines must share '+key)
    case=Case(**records[0]['case'])
    require(case.course in ('stadium','autocross','bundle') and (all(p.to_dict()['schema']=='lapsim.torque-profile.v2' for p in profiles) or not case.regen_available) and case.friction_fallback
            and case.motor_temperature_c==40. and .1<=case.duration_s<=(600 if case.laps==10 else 60)
            and abs(case.duration_s*100-round(case.duration_s*100))<1e-9,'Unsupported saved baseline scenario')
    require(case.initial_soc==starts[0][0] and case.pack_voltage_v==starts[0][2],'Saved case/profile inputs differ')
    for profile,record in zip(profiles,records):
        require(record['car']==asdict(replace(profile.vehicle,tire_mu=profile.vehicle.tire_mu*case.grip)),
                'Saved vehicle differs from its profile and declared grip')
        frames=record['configuration']['frames'];outputs=record['configuration']['outputs']
        require(type(frames) is list and type(outputs) is list and 1<=len(frames)<=(60001 if case.laps==10 else 6001) and len(frames)==len(outputs),
                'Saved baseline trace exceeds its version bound or lacks outputs')
    study=assemble(profiles,case,records,source,full_lap=True)
    study['specification']['input_evidence']={'kind':'saved_baseline_pair','reexecuted':False,
        'receipt_payload_sha256':[digest(receipt) for receipt in receipts],
        'scope':'Current source/profile/scenario identities checked; full selected replay is required before source export'}
    study['fingerprint']=study_fingerprint(study)
    return study


def study_fingerprint(study):
    return digest({'specification':study['specification'],'source':study['configured_source'],
                   'runs':{key:digest(value) for key,value in study['runs'].items()}})


def save_comparison(study,destination):
    destination=Path(destination).resolve()
    require(not destination.exists(),'Comparison directory already exists; prior results are preserved')
    root=repository_root().resolve()
    if destination.is_relative_to(root):
        relative=destination.relative_to(root).as_posix()
        if re.fullmatch(r'work/torque-comparison-[a-f0-9]{12}',relative):
            require(study.get('configured_study',relative)==relative,'Saved comparison has a different local viewer identity')
            study['configured_study']=relative
    destination.mkdir(parents=True,exist_ok=False)
    write_json(destination/'replay.json',study,limit=STUDY_BYTE_LIMIT)
    write_json(destination/'viewer.json',viewer_projection(study),limit=8_000_000)
    local=study.get('configured_study')
    write_json(destination/'summary.json',{'schema':'lapsim.configured-study-summary.v1','fingerprint':study['fingerprint'],
        'status':study['status'],'simulation_only':True,'configured_study':local,
        'viewer_url':('/web/tournament.html?configured='+local.split('-')[-1]) if local else None,
        'runs':[{'run_id':run_id,'profile_id':record['configuration']['profile']['profile_id'],
                 'profile_sha256':record['configuration']['profile_sha256'],'architecture':record['configuration']['profile']['architecture'],
                 'status':record['status'],'metrics':record['metrics'],'acceptance':record['configuration'].get('acceptance')}
                for run_id,record in study['runs'].items()]},limit=65_536)


def viewer_projection(study):
    runs={}
    for run_id,record in study['runs'].items():
        configuration=record['configuration']
        projected={key:value for key,value in configuration.items() if key not in ('frames','outputs')}
        projected['dense_trace']={'retained_in':'replay.json','observations':len(configuration['frames'])}
        runs[run_id]={**record,'configuration':projected}
    return {**study,'runs':runs,'display_projection':True,
        'projection_scope':'Unmodified recorded telemetry and identities; dense controller frames/outputs remain in replay.json; export uses the full saved record'}


def reproduce_record(record,source):
    require(source==source_identity(),'Configured result source identity changed; use its exact source package')
    configuration=record['configuration'];profile=VehicleProfile.from_dict(configuration['profile'])
    require(profile.sha256==configuration['profile_sha256'],'Configured profile identity mismatch')
    require(configuration['source']==controller_source_identity(),'Configured controller identity mismatch')
    require(record['controller']==expected_strategy(profile),'Incompatible selected strategy')
    require(record['profile']==ALIASES[profile.actuation.topology_id],'Selected result topology mismatch')
    mode=configuration.get('mode')
    require(mode in (None,'full_lap_acceptance_v1','ten_lap_acceptance_v1'),'Unsupported selected result mode')
    repeated=execute(profile,Case(**record['case']),full_lap=mode is not None)
    require(digest(repeated)==digest(record),'Selected result does not reproduce exactly')
    return repeated,profile


def export_selected(study,run_id,destination):
    require(not study.get('display_projection'),'Display projection cannot be exported; select its complete replay.json')
    require(study['schema']==SCHEMA and study['status'] in ('configured_diagnostic','configured_full_lap_acceptance'),'A configured study is required')
    require(study['fingerprint']==study_fingerprint(study),'Configured study fingerprint mismatch')
    require(1<=len(study['runs'])<=2 and run_id in study['runs'],'Select one recorded configured result')
    record,profile=reproduce_record(study['runs'][run_id],study['configured_source'])
    require(profile.to_dict() in study['specification']['profiles'],'Selected profile is not in the recorded study')
    require(record['case'] in study['specification']['training'],'Selected case is not in the recorded study')
    integration={**record['configuration'],'duration_ms':round(record['case']['duration_s']*1000),
                 'energy_residual_j':record['metrics']['energy_residual_j']}
    selected_spec={'schema':'lapsim.selected-configured-result.v1','profile':profile.to_dict(),
        'case':record['case'],'strategy':record['controller'],'sources':study['configured_source'],
        'result_sha256':digest(record),'study_fingerprint':study['fingerprint'],'run_id':run_id,
        'study_specification':study['specification']}
    proof={'schema':'lapsim.configured-result-reproduction.v1','matched_exactly':True,
        'result_sha256':digest(record),'profile_sha256':profile.sha256,'simulation_only':True,
        'recorded_status':record['status'],'recorded_violations':record['violations'],
        'scope':'Exact synthetic bounded result reproduction; no calibration, lap ranking, official points or hardware timing claim'}
    completed=export_source(profile,destination,integration=integration,attachments={
        'selected-result.json':record,'comparison-spec.json':selected_spec,'result-reproduction.json':proof})
    return {**completed,'selected_result_sha256':digest(record),'run_id':run_id}


def reproduce_package(directory):
    directory=Path(directory);verified=verify_package(directory)
    spec=bounded_json(directory/'comparison-spec.json');record=bounded_json(directory/'selected-result.json',limit=SELECTED_BYTE_LIMIT)
    require(spec['schema']=='lapsim.selected-configured-result.v1' and spec['result_sha256']==digest(record),'Selected result identity mismatch')
    require(spec['profile']==record['configuration']['profile'] and spec['case']==record['case']
            and spec['strategy']==record['controller'],'Selected result inputs differ from its specification')
    require(spec['profile'] in spec['study_specification']['profiles'] and spec['case'] in spec['study_specification']['training'],
            'Selected result lost its comparison context')
    repeated,profile=reproduce_record(record,spec['sources'])
    require(profile.sha256==verified['profile_sha256'],'Selected result/package profile mismatch')
    return {'schema':'lapsim.configured-result-reproduction.v1','matched_exactly':True,'simulation_only':True,
        'result_sha256':digest(repeated),'profile_sha256':profile.sha256,'metrics':repeated['metrics'],
        'recorded_status':repeated['status'],'recorded_violations':repeated['violations'],
        'scope':'Recorded bounded synthetic diagnostic; no lap ranking, official points or physical validation'}
