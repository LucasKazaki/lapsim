"""Small, source-bound ten-lap experiments; hardware groups stay distinct."""
from dataclasses import asdict
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
from importlib.metadata import version

from lapsim.courses.library import course_library
from lapsim.torque_configurator.export import write_json
from .controller_tournament import canonical,sources
from .record_io import write_text_atomic
from .tournament_rollout import Case,Controller,PROFILES,PHYSICAL_BOUNDS,BOUNDS,rollout,number

SCHEMA='lapsim.ten-lap-candidate.v1'
CONDITIONS={'grip':1.,'initial_soc':.7,'pack_voltage_v':580.,'initial_offset_m':0.,
            'regen_available':True,'friction_fallback':True,'motor_temperature_c':40.,'reverse':False,'mirror':False}


def digest(value):return sha256(canonical(value).encode()).hexdigest()


def evaluation_key(value):
    """Exact model inputs/source, excluding phase/seed-only provenance."""
    value=validate_candidate(value)
    return digest({'inputs':{k:value[k] for k in ('profile','controller','course_id','geometry_sha256','parameters','conditions','laps')},'sources':sources()})


def candidate(profile,controller,course_id,*,seed=4082025,parameters=None,conditions=None,phase='shakedown'):
    if profile not in PROFILES:raise ValueError('Choose an explicit synthetic topology')
    if type(controller) is not Controller:raise ValueError('Validated controller required')
    if type(seed) is not int or not 0<=seed<2**32:raise ValueError('Unsigned 32-bit seed required')
    if phase not in ('shakedown','shortlist','tuning','heldout'):raise ValueError('Unknown campaign phase')
    parameters={} if parameters is None else dict(parameters)
    if set(parameters)-set(PHYSICAL_BOUNDS):raise ValueError('Unknown physical sample field')
    for key,value in parameters.items():number(value,key,*PHYSICAL_BOUNDS[key])
    conditions={} if conditions is None else dict(conditions)
    if set(conditions)-set(CONDITIONS):raise ValueError('Unknown scenario condition')
    conditions={**CONDITIONS,**conditions}
    entry=next((e for e in course_library()['courses'] if e['id']==course_id),None)
    if entry is None:raise ValueError('Choose a validated library course')
    Case('ten_lap_competition',course='bundle',course_bundle=entry['bundle'],duration_s=600,laps=10,**conditions)
    value={'schema':SCHEMA,'profile':profile,'controller':asdict(controller),'course_id':course_id,
           'geometry_sha256':entry['geometry_sha256'],'seed':seed,'parameters':parameters,'conditions':conditions,
           'phase':phase,'laps':10,'hardware_group_id':digest({'profile':profile,'parameters':parameters,'pack_voltage_v':conditions['pack_voltage_v']})[:20]}
    value['configuration_sha256']=digest(value)
    return value


def validate_candidate(value):
    if type(value) is not dict or value.get('schema')!=SCHEMA:raise ValueError('Unsupported candidate schema')
    seed,phase=value.get('seed'),value.get('phase')
    if type(seed) is not int or not isinstance(phase,str):raise ValueError('Candidate seed and phase are required')
    expected=candidate(value.get('profile'),Controller(**value.get('controller',{})),value.get('course_id'),
        seed=seed,parameters=value.get('parameters'),conditions=value.get('conditions'),phase=phase)
    if value!=expected:raise ValueError('Candidate configuration/geometry identity mismatch')
    return expected


def sampled_hardware(seed,count=2):
    """Bounded Latin-hypercube samples; engineering hypotheses, not team data."""
    if type(seed) is not int or not 0<=seed<2**32 or type(count) is not int or not 1<=count<=4:
        raise ValueError('Seed/count outside the bounded sample domain')
    from scipy.stats import qmc
    keys=('mass_kg','tire_mu','gear_ratio','wheel_radius_m','wheel_inertia_kgm2','rear_radius_mismatch_fraction','pack_discharge_power_limit_w')
    from lapsim.qmc_sampler import latin_hypercube
    values=latin_hypercube(len(keys),seed).random(count)
    lower=[PHYSICAL_BOUNDS[key][0] for key in keys];upper=[PHYSICAL_BOUNDS[key][1] for key in keys]
    return [dict(zip(keys,map(float,row))) for row in qmc.scale(values,lower,upper)]


def execute_candidate(value,output):
    value=validate_candidate(value);output=Path(output)
    checkpoint=output.with_name(output.stem+'.checkpoint.json')
    started=output.with_name(output.stem+'.started.json')
    if output.exists() or checkpoint.exists() or started.exists():raise ValueError('Preserve earlier candidate attempt')
    entry=next(e for e in course_library()['courses'] if e['id']==value['course_id'])
    source=sources();laps=[]
    header={'schema':'lapsim.ten-lap-result.v1','configuration':value,'sources':source,
            'started_utc':datetime.now(timezone.utc).isoformat(),'runtime_python':platform.python_version(),
            'runtime_dependencies':{name:version(name) for name in ('numpy','scipy')},
            'scope':'Synthetic ten-lap competition; one continuous state; no official FSAE score or physical calibration'}
    write_json(started,header)
    def observe(row):
        laps.append(row)
        write_text_atomic(checkpoint,canonical({**header,'status':'running','completed_laps':len(laps),'laps':laps}))
        print(canonical({'utc':datetime.now(timezone.utc).isoformat(),'lap_completed':row['lap'],
            'lap_time_s':row['lap_time_s'],'net_energy_wh':row['net_energy_kwh']*1000,
            'soc_after':row['soc_after'],'carry_state_sha256':row['carry_state_sha256']}),flush=True)
    case=Case('ten_lap_competition',course='bundle',course_bundle=entry['bundle'],duration_s=600,laps=10,**value['conditions'])
    record=rollout(Controller(**value['controller']),case,profile=value['profile'],
                   parameter_overrides=value['parameters'],progress_callback=observe)
    if source!=sources():raise ValueError('Source changed during this round; retained checkpoint is not a matched result')
    accepted=record['status']=='completed' and record['eligible'] and record['round']['completed_laps']==10 and not record['violations']
    if accepted:
        if abs(sum(r['lap_time_s'] for r in record['round']['laps'])-record['metrics']['round_time_s'])>1e-9:
            raise ValueError('Per-lap and round time disagree')
        if abs(sum(r['net_energy_kwh'] for r in record['round']['laps'])-record['metrics']['net_energy_kwh'])>1e-12:
            raise ValueError('Per-lap and round energy disagree')
    result={**header,'finished_utc':datetime.now(timezone.utc).isoformat(),'record':record,
            'record_sha256':digest(record),'acceptance_passed':accepted,
            'bounds':{'physical':PHYSICAL_BOUNDS,'controller':BOUNDS,'laps':10,'maximum_round_s':600,'maximum_lap_s':60,'maximum_round_work':2000000},
            'seed_role':'Sampling/search seed; a fixed rollout contains no injected randomness',
            'ranking_scope':'Only compare controllers within the same hardware group and matched course/scenario; no universal winner'}
    result['evaluation_key']=evaluation_key(value)
    result['selection_cost']={'eligible':accepted,
        'value_s':record['metrics']['fitness'] if accepted else 1_000_000+10_000*(10-record['round']['completed_laps'])+1000*len(record['violations'])+record['metrics']['elapsed_s'],
        'policy':'Completed comparable rounds use total seconds + 120 s/kWh * net energy. DNF has 1,000,000 s base + 10,000 s/unfinished lap + 1,000 s/reason + elapsed seconds. Search penalty only, not FSAE points.'}
    write_json(output,result,limit=5_000_000)
    write_text_atomic(checkpoint,canonical({**header,'status':record['status'],'completed_laps':len(laps),'laps':laps,'result':output.as_posix()}))
    print(canonical({'finished':True,'profile':value['profile'],'controller':value['controller']['philosophy'],
        'acceptance_passed':accepted,'status':record['status'],'completed_laps':record['round']['completed_laps'],
        'violations':record['violations'],'metrics':record['metrics'],'output':output.as_posix()}),flush=True)
    return result
