"""Versioned GPU-search bookkeeping and canonical common-field selection.

No raw weighted time/energy proxy. Parents and children are rescored together
against one common field at each selection; stale relative scores never carry
between generations. Finalists/scenarios freeze before held-out execution.
"""
from dataclasses import asdict
from hashlib import sha256
import json
from math import isfinite

from .search_policy import SearchPolicy,initial_population,offspring
from .tournament_rollout import Controller
from .tournament_scoring import ScoringRun,score_field,VERSION


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def record_summary(record):
    car=record['car'];rows=record['telemetry']
    def kinetic(row):
        return .5*car['mass_kg']*(row['u_mps']**2+row['v_mps']**2)+.5*car['yaw_inertia_kgm2']*row['yaw_rad_s']**2+.5*car['wheel_inertia_kgm2']*sum(w*w for w in row['wheel_omega_rad_s'])
    metrics=record['metrics']
    return {'status':record['status'],'eligible':record['eligible'],'violations':record['violations'],
        'geometry_sha256':record['course']['geometry_sha256'],'distance_m':record['course']['length_m'],
        'lap_time_s':metrics['lap_time_s'],'net_energy_kwh':metrics['net_energy_kwh'],
        'gross_draw_kwh':metrics['gross_pack_draw_kwh_10ms'],'recovered_kwh':metrics['recovered_pack_kwh_10ms'],
        'terminal_speed_mps':rows[-1]['u_mps'] if rows else None,'kinetic_gain_j':kinetic(rows[-1])-kinetic(rows[0]) if rows else None,
        'energy_residual_j':metrics['energy_residual_j'],'max_slip':metrics['max_slip'],
        'limited_ticks':metrics['limited_ticks'],'search_policy':record.get('search_policy'),
        'generating_log_samples':sum(row['pack_power_w']<0 for row in rows),
        'backend':record.get('numerical_backend')}


def matched_ranking(candidates,records,courses,scenarios):
    """Only complete valid common coverage participates in field references."""
    keys=[(scenario,course) for scenario in scenarios for course in courses]
    qualified=[];excluded={}
    for candidate in candidates:
        identity=candidate['id'];reasons=[]
        for scenario,course in keys:
            row=records.get((identity,scenario,course))
            if row is None:reasons.append(f'{scenario}/{course}:unrun');continue
            if row['status']!='completed' or not row['eligible'] or row['violations']:
                reasons.append(f'{scenario}/{course}:invalid_or_unfinished');continue
            for field in ('lap_time_s','net_energy_kwh','distance_m'):
                v=row[field]
                if type(v) not in (int,float) or not isfinite(v) or v<=0:reasons.append(f'{scenario}/{course}:unmeasurable_{field}')
        if reasons:excluded[identity]=reasons
        else:qualified.append(identity)
    components={identity:[] for identity in qualified};references={}
    for scenario,course in keys:
        field=[]
        for identity in qualified:
            row=records[identity,scenario,course]
            field.append(ScoringRun(identity,'synthetic_awd',row['geometry_sha256'],1,row['distance_m'],
                row['lap_time_s'],row['net_energy_kwh'],True,True))
        if not field:continue
        scored=score_field(field)
        if not scored['available']:raise ValueError('Canonical matched-field scoring unavailable')
        references[scenario+'/'+course]=scored['references']
        for identity in qualified:components[identity].append(scored['rows'][identity])
    aggregate=[]
    for identity in qualified:
        rows=[records[identity,scenario,course] for scenario,course in keys]
        points=components[identity]
        policies=[r.get('search_policy') for r in rows]
        behavior=digest([p['command_digest'] for p in policies]) if all(p and p.get('command_digest') for p in policies) else None
        intervention={};modes={}
        for p in policies:
            if p:
                for key,value in p['intervention_ticks'].items():intervention[key]=intervention.get(key,0)+value
                for key,value in p['mode_occupancy'].items():modes[key]=modes.get(key,0)+value
        aggregate.append({'id':identity,'mean_points':sum(r['total_points'] for r in points)/len(points),
            'mean_endurance_points':sum(r['endurance_points'] for r in points)/len(points),
            'mean_efficiency_points':sum(r['efficiency_points'] for r in points)/len(points),
            'sum_time_s':sum(r['lap_time_s'] for r in rows),'net_energy_wh':1000*sum(r['net_energy_kwh'] for r in rows),
            'recovered_wh':1000*sum(r['recovered_kwh'] for r in rows),
            'all_efficiency_eligible':all(r['efficiency_eligible'] for r in points),
            'valid_laps':len(rows),'components':points,'behavior_sha256':behavior,
            'observed_intervention_ticks':intervention,'observed_modes':modes})
    aggregate.sort(key=lambda row:(-row['mean_points'],row['sum_time_s'],row['net_energy_wh'],row['id']))
    pareto=[a['id'] for a in aggregate if not any(b['sum_time_s']<=a['sum_time_s'] and b['net_energy_wh']<=a['net_energy_wh']
        and (b['sum_time_s']<a['sum_time_s'] or b['net_energy_wh']<a['net_energy_wh']) for b in aggregate)]
    def winners(key,maximum=False):
        if not aggregate:return []
        best=(max if maximum else min)(r[key] for r in aggregate)
        return [r['id'] for r in aggregate if abs(r[key]-best)<=1e-9]
    return {'scoring_version':VERSION,'official_points':False,'qualified':aggregate,'excluded':excluded,
        'pareto':pareto,'highest_points':winners('mean_points',True),'fastest':winners('sum_time_s'),
        'least_net_energy':winners('net_energy_wh'),'field_references':references,
        'coverage_per_qualified_candidate':len(keys),'pool_sha256':digest(sorted(qualified)),
        'command_equivalence_groups':[[r['id'] for r in aggregate if r['behavior_sha256']==key]
            for key in sorted({r['behavior_sha256'] for r in aggregate if r['behavior_sha256'] is not None})],
        'objective':'Equal mean of canonical 275 endurance +100 efficiency component points across the matched course/scenario cells; simulation adaptation, not official event points.'}


def next_generation(candidates,ranking,seed):
    by_id={c['id']:c for c in candidates}
    eligible=[row['id'] for row in ranking['qualified'] if by_id[row['id']].get('can_breed',True)]
    # Retain score elites and the time-energy frontier, with no invented win
    # for inactive genes. Random immigrants provide independent exploration.
    identities=[]
    for identity in [*ranking['highest_points'],*ranking['fastest'],*ranking['least_net_energy'],*ranking['pareto'],*eligible[:6]]:
        if identity in eligible and identity not in identities:identities.append(identity)
    parents=[by_id[i] for i in identities]
    return offspring(parents,seed,[c['sha256'] for c in candidates if 'sha256' in c],6)


def freeze_finalists(candidates,ranking):
    by_id={c['id']:c for c in candidates};chosen=[]
    # Reserve a deterministic representative from EVERY requested category
    # before consuming the remaining budget with point ties/Pareto alternatives.
    for category in ('highest_points','fastest','least_net_energy'):
        if ranking[category]:
            identity=min(ranking[category])
            if identity not in chosen:chosen.append(identity)
    for identity in [*ranking['highest_points'],*ranking['fastest'],*ranking['least_net_energy'],*ranking['pareto']]:
        if len(chosen)>=4:break
        if identity not in chosen:chosen.append(identity)
    if 'anchor-gpu-fixed-off' not in chosen:chosen.append('anchor-gpu-fixed-off')
    return [by_id[i] for i in chosen]


def controller_for(candidate):
    return Controller(**candidate['policy']) if candidate.get('anchor') else SearchPolicy(**candidate['policy'])
