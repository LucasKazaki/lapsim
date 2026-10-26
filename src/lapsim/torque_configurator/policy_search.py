"""Bounded grammar/LHS exploration and endpoint-aware feasible Pareto selection."""
from copy import deepcopy
from hashlib import sha256
from math import isfinite
import random

from .profile import VehicleProfile,canonical,require
from .policy import PolicySpec,STRUCTURES,PARAMETERS,DEFAULTS


def hardware_identity(profile):
    value=profile.to_dict()
    return sha256(canonical({k:value[k] for k in ('vehicle','actuation','policy')}).encode()).hexdigest()


def sample_profiles(base,seed,count=4):
    require(type(seed) is int and 0<=seed<2**32 and type(count) is int and 2<=count<=16,'Bounded integer seed/count required')
    from lapsim.qmc_sampler import latin_hypercube
    from lapsim.dynamics.actuation import SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID,AWD_TOPOLOGY_ID
    rng=random.Random(seed);options={k:list(v) for k,v in STRUCTURES.items()}
    if base.actuation.topology_id in (SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID):options['yaw']=['off']
    if base.actuation.topology_id!=AWD_TOPOLOGY_ID:options['allocation']=['equal']
    columns={}
    for key,values in options.items():
        selected=[values[i%len(values)] for i in range(count)];rng.shuffle(selected);columns[key]=selected
    numeric=latin_hypercube(len(PARAMETERS),seed).random(count)
    output=[];seen=set()
    for i,row in enumerate(numeric):
        value=base.to_dict();value['schema']='lapsim.torque-profile.v2';value['profile_id']=f'r11-sample-{seed}-{i}'
        structure={k:columns[k][i] for k in columns}
        parameters={k:lo+float(x)*(hi-lo) for x,(k,(lo,hi)) in zip(row,PARAMETERS.items())}
        spec={'schema':'lapsim.experimental-policy.v1','structure':structure,'parameters':parameters}
        active=PolicySpec.from_dict(spec,base.actuation.topology_id).active_parameters
        for key in set(PARAMETERS)-set(active):parameters[key]=DEFAULTS[key]
        value['controller']=spec;profile=VehicleProfile.from_dict(value)
        identity=PolicySpec.from_dict(spec,base.actuation.topology_id).effective_identity
        require(identity not in seen,'Duplicate effective sampled policy');seen.add(identity);output.append(profile)
    return output


def terminal_state(record):
    car=record['car'];before=record['round']['initial_state']['plant'];after=record['round']['final_state']['plant']
    def kinetic(p):return .5*car['mass_kg']*(p['u_mps']**2+p['v_mps']**2)+.5*car['yaw_inertia_kgm2']*p['yaw_rate_rad_s']**2+.5*car['wheel_inertia_kgm2']*sum(v*v for v in p['wheel_speeds_rad_s'])
    return {'initial_kinetic_j':kinetic(before),'final_kinetic_j':kinetic(after),'final_speed_mps':after['u_mps'],
        'net_energy_less_kinetic_gain_kwh':record['metrics']['net_energy_kwh']-(kinetic(after)-kinetic(before))/3_600_000,
        'scope':'Kinetic state at accepted plant ticks; lap energy uses interpolated seam; diagnostic correction is not official scoring'}


def pareto(points,reference_speed_mps,*,speed_tolerance_mps=1.):
    require(type(reference_speed_mps) in (int,float) and isfinite(reference_speed_mps),'Finite fixed endpoint reference required')
    require(type(speed_tolerance_mps) in (int,float) and 0<speed_tolerance_mps<=1.,'Endpoint tolerance is bounded to 1 m/s')
    eligible=[];excluded=[]
    for p in points:
        valid=(p.get('accepted') is True and p.get('completed_laps')==10 and
            all(type(p.get(k)) in (int,float) and isfinite(p[k]) for k in ('time_s','net_energy_kwh','final_speed_mps')) and p['time_s']>0)
        if not valid:excluded.append({'id':p['id'],'reason':'unfinished/invalid/nonfinite round'});continue
        if abs(p['final_speed_mps']-reference_speed_mps)>speed_tolerance_mps:
            excluded.append({'id':p['id'],'reason':'terminal speed outside fixed reference band; retain physical result but exclude energy ranking'});continue
        eligible.append(p)
    frontier=[p for p in eligible if not any(q['time_s']<=p['time_s'] and q['net_energy_kwh']<=p['net_energy_kwh'] and
        (q['time_s']<p['time_s'] or q['net_energy_kwh']<p['net_energy_kwh']) for q in eligible)]
    choices={}
    if eligible:
        choices={'fastest':min(eligible,key=lambda p:p['time_s'])['id'],
            'lowest_energy':min(eligible,key=lambda p:p['net_energy_kwh'])['id'],
            'proxy':min(eligible,key=lambda p:p['time_s']+120*p['net_energy_kwh'])['id']}
    return {'frontier_ids':[p['id'] for p in frontier],'exemplars':choices,'excluded':excluded,
        'reference_speed_mps':reference_speed_mps,'terminal_speed_tolerance_mps':speed_tolerance_mps,
        'scope':'Same hardware/course/start only; feasible raw time-energy tradeoffs; no official points or universal winner'}


def diverse_elites(points,selection,maximum=3):
    require(type(maximum) is int and 1<=maximum<=4,'Bounded elite count required')
    lookup={p['id']:p for p in points};ordered=list(dict.fromkeys(selection['exemplars'].values()))
    ordered+=selection['frontier_ids'];chosen=[];seen_behavior=set()
    for key in ordered:
        p=lookup[key];behavior=p['behavior_sha256']
        if behavior in seen_behavior:continue
        chosen.append(key);seen_behavior.add(behavior)
        if len(chosen)==maximum:break
    return chosen
