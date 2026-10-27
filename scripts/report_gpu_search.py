"""Verify saved records and render completed held-out winners; never deploy."""
from datetime import datetime,timezone
from hashlib import sha256
import argparse,csv,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from lapsim.experiments.gpu_search import matched_ranking,record_summary,digest
from lapsim.experiments.search_provenance import read_verified,verify_anchor
from lapsim.experiments.tournament_rollout import Case
from lapsim.courses.course_bundle import CourseBundle
from dataclasses import asdict


def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def detailed(candidate,scenario,course,row):
    policy=row.get('search_policy') or {}
    return {'candidate':candidate,'scenario':scenario,'course':course,
        'status':row['status'],'eligible':row['eligible'],'time_s':row['lap_time_s'],
        'net_wh':1000*row['net_energy_kwh'],'gross_draw_wh':1000*row['gross_draw_kwh'],
        'recovered_wh':1000*row['recovered_kwh'],'terminal_speed_mps':row['terminal_speed_mps'],
        'kinetic_gain_j':row['kinetic_gain_j'],'energy_residual_j':row['energy_residual_j'],
        'max_slip':row['max_slip'],'limited_ticks':row['limited_ticks'],
        'violations':json.dumps(row['violations']),'modes':json.dumps(policy.get('mode_occupancy',{})),
        'interventions':json.dumps(policy.get('intervention_ticks',{}))}


def with_components(rows,ranking,courses,scenarios):
    qualified={row['id']:row for row in ranking['qualified']}
    for row in rows:
        result=qualified.get(row['candidate'])
        component=(result['components'][scenarios.index(row['scenario'])*len(courses)+courses.index(row['course'])]
            if result else {})
        for field in ('endurance_points','efficiency_points','total_points','efficiency_eligible'):
            row[field]=component.get(field)
        row['candidate_exclusion']=json.dumps(ranking['excluded'].get(row['candidate'],[]))
    return rows


def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();directory=Path(a.directory).resolve();output=Path(a.output).resolve()
    plan=load(directory/'plan.json');coverage=load(directory/'coverage.json')
    held=coverage['heldout']
    if held is None or held['provisional']:raise ValueError('Held-out coverage incomplete; no final report/winner')
    pool=load(directory/'heldout-pool.json')
    if digest(pool['candidates'])!=pool['pool_sha256']:raise ValueError('Frozen finalist pool hash mismatch')
    if output.exists():raise ValueError('Preserve previous report')
    for path,identity in plan['sources'].items():
        if sha256((ROOT/path).read_bytes()).hexdigest()!=identity:raise ValueError('Frozen source changed: '+path)
    records={};checked=[];detail=[]
    for candidate in pool['candidates']:
        for scenario in ('heldout-a','heldout-b'):
            for course,entry in plan['courses'].items():
                folder=directory/'records'/scenario/candidate['id']
                summary=read_verified(folder/(course+'.summary.json'),plan['sources'],candidate['id'],scenario,course)
                if summary is None:raise ValueError('Unverified held-out result cannot be reported')
                raw_path=folder/(course+'.record.json')
                blob=raw_path.read_bytes();record=json.loads(blob)
                if sha256(blob).hexdigest()!=summary['raw_record_sha256']:raise ValueError('Raw record hash mismatch')
                if record['controller']!=candidate['policy']:raise ValueError('Executed controller differs from frozen finalist')
                if record['profile']!='synthetic_awd':raise ValueError('Mixed hardware field')
                if record['case']['grip']!=plan['scenarios'][scenario]['grip'] or record['case']['initial_soc']!=plan['scenarios'][scenario]['initial_soc']:
                    raise ValueError('Unpaired scenario inputs')
                if record['course']['geometry_sha256']!=entry['geometry_sha256']:raise ValueError('Course mismatch')
                for key,value in record_summary(record).items():
                    if summary.get(key)!=value:raise ValueError('Raw metric/summary mismatch: '+key)
                if record['status']=='completed' and record['eligible'] and not record['violations']:
                    bundle=CourseBundle.from_dict(entry['bundle']);driver=dict(plan['fixed_fixture']['driver'])
                    driver.update(assumed_half_width_m=bundle.default_ai_half_width_m,
                        vehicle_width_m=bundle.default_ai_vehicle_width_m,safety_margin_m=bundle.default_ai_margin_m)
                    regen=False if candidate.get('anchor') else candidate['policy']['regen_mode']!='off'
                    case=Case('report-verification',course='bundle',course_bundle=entry['bundle'],duration_s=300,
                        long_course=True,regen_available=regen,**plan['scenarios'][scenario])
                    car=dict(plan['fixed_fixture']['car'])
                    car['tire_mu']*=case.grip  # Same declared scenario transform as the rollout.
                    verify_anchor(blob,summary['raw_record_sha256'],expected_controller=candidate['policy'],
                        expected_case=asdict(case),expected_car=car,
                        expected_pack=plan['fixed_fixture']['pack'],expected_driver=driver,
                        geometry_sha256=entry['geometry_sha256'],distance_m=entry['length_m'])
                backend=record['numerical_backend']
                if (backend['cpu_physics_fallback'] or not backend['kernel_sha256']
                    or backend['device']!=plan['device'] or backend['kernel_launches_so_far']<=0
                    or backend['state_initializations']!=1):raise ValueError('GPU execution identity missing')
                records[candidate['id'],scenario,course]=summary
                checked.append({'candidate':candidate['id'],'scenario':scenario,'course':course,
                    'sha256':summary['raw_record_sha256'],'status':summary['status'],'eligible':summary['eligible']})
                detail.append(detailed(candidate['id'],scenario,course,summary))
    rank=matched_ranking(pool['candidates'],records,list(plan['courses']),['heldout-a','heldout-b'])
    if rank['qualified']!=held['qualified']:raise ValueError('Canonical common-field rescore differs from saved coverage')
    detail=with_components(detail,rank,list(plan['courses']),['heldout-a','heldout-b'])
    training_candidates=[*plan['anchors'],*plan['initial_population'],*load(directory/'generation-1.json')['offspring']]
    training_records={};training_detail=[]
    for candidate in training_candidates:
        for course in plan['courses']:
            path=directory/'records/train'/candidate['id']/(course+'.summary.json')
            row=read_verified(path,plan['sources'],candidate['id'],'train',course)
            if row is None:raise ValueError('Unverified or incomplete training result cannot be reported')
            training_records[candidate['id'],'train',course]=row
            training_detail.append(detailed(candidate['id'],'train',course,row))
    training_rank=matched_ranking(training_candidates,training_records,list(plan['courses']),['train'])
    if training_rank['qualified']!=coverage['training']['qualified']:
        raise ValueError('Canonical training rescore differs from saved coverage')
    training_detail=with_components(training_detail,training_rank,list(plan['courses']),['train'])
    output.mkdir(parents=True)
    for name,rows in [('per-course-results.csv',detail),('training-per-course-results.csv',training_detail)]:
        with (output/name).open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    by_id={c['id']:c for c in pool['candidates']}
    winners={key:rank[key] for key in ('fastest','highest_points','least_net_energy')}
    configurations={identity:by_id[identity] for ids in winners.values() for identity in ids}
    for name,value in [('experiment-plan.json',plan),('generation-1.json',load(directory/'generation-1.json')),
                       ('heldout-pool.json',pool),('winner-policies.json',configurations)]:
        (output/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    columns=['id','structure','regen','mean_points','mean_endurance_points','mean_efficiency_points','sum_time_s','net_energy_wh','recovered_wh','valid_laps','all_efficiency_eligible']
    with (output/'heldout-results.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader()
        for row in rank['qualified']:
            policy=by_id[row['id']]['policy']
            writer.writerow({**{k:row[k] for k in columns if k in row},'structure':policy.get('structure','fixed anchor'),
                'regen':policy.get('regen_mode','off')})
    lines=['# GPU torque/regen search  -  held-out result', '',
        'Synthetic AWD, six estimated courses × two frozen held-out scenarios. One lap per cell; no physical calibration or official endurance result.', '',
        '| Category | Candidate(s) |','|---|---|']
    for key,label in [('fastest','Fastest'),('highest_points','Highest 275+100 adapted points'),('least_net_energy','Least net battery energy')]:
        lines.append('| '+label+' | '+(', '.join(winners[key]) or 'No fully eligible candidate')+' |')
    lines+=['','Points are the equal mean of the canonical component scores across twelve matched cells. Time and energy below are totals over those cells. One candidate may win multiple categories.', '',
        '| Candidate | Points /375 | Endurance /275 | Efficiency /100 | Time (s) | Net Wh | Recovered Wh |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for row in rank['qualified']:
        lines.append(f"| {row['id']} | {row['mean_points']:.3f} | {row['mean_endurance_points']:.3f} | {row['mean_efficiency_points']:.3f} | {row['sum_time_s']:.3f} | {row['net_energy_wh']:.3f} | {row['recovered_wh']:.3f} |")
    lines+=['','Exact executed genes and precision remain in plan.json/generation-1.json/heldout-pool.json; display rounding changes no simulation input. Net energy already credits regen once.',
        '','Unrun/invalid candidates never score as successful low-energy laps. Exclusions: '+json.dumps(rank['excluded']),
        '','Conditional mode/intervention counts and diagnostic command-equivalence groups are retained in final-results.json. A nonbinding limit may legitimately produce equality; observed numeric differences alone do not validate the physical model.',
        '','The field omits official endurance distance, driver change, event penalties, inspections and real metering. Points are the explicitly documented simulated adaptation of the rule equations. Hardware profiles and track scales are provisional. No website publication or hardware action.',
        '','Seed: '+str(plan['seed'])+'. All finalist/scenario choices froze before held-out execution.']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    result={'schema':'lapsim.gpu-ga-final.v1','utc':datetime.now(timezone.utc).isoformat(),'seed':plan['seed'],
        'winners':winners,'winner_configurations':configurations,'heldout_ranking':rank,'training_ranking':training_rank,
        'finalist_pool_sha256':pool['pool_sha256'],'verified_raw_records':checked,'sources':plan['sources'],
        'budget':plan['budget'],'coverage':coverage['counts'],'per_course_results':detail,
        'verified_training_receipts':len(training_records),'training_per_course_results':training_detail,
        'report_source_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),'official_points':False,'published':False}
    (output/'final-results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(9,5))
    midpoint=(min(row['sum_time_s'] for row in rank['qualified'])+max(row['sum_time_s'] for row in rank['qualified']))/2 if rank['qualified'] else 0
    for row in rank['qualified']:
        labels=[label for key,label in [('fastest','fastest'),('highest_points','most points'),('least_net_energy','least energy')] if row['id'] in winners[key]]
        ax.scatter(row['sum_time_s'],row['net_energy_wh'],s=85 if labels else 40,c='#137b80' if labels else '#8d9aa0')
        right=row['sum_time_s']>midpoint
        ax.annotate(row['id']+(' · '+', '.join(labels) if labels else ''),(row['sum_time_s'],row['net_energy_wh']),
            xytext=(-5 if right else 5,5),ha='right' if right else 'left',textcoords='offset points',fontsize=7)
    ax.set(xlabel='Total time over 12 matched held-out laps (s)',ylabel='Net battery energy over those laps (Wh)',
        title='Synthetic AWD: frozen held-out speed - energy comparison')
    ax.grid(alpha=.2);fig.text(.01,.01,'Estimated courses · simulation-only · points use the 275+100 rule-inspired adaptation · no physical/official result',fontsize=8)
    fig.tight_layout(rect=(0,.04,1,1));fig.savefig(output/'heldout-time-energy.png',dpi=180);plt.close(fig)
    print(json.dumps({'output':str(output),'winners':winners,'verified_records':len(checked),'published':False}))

if __name__=='__main__':main()
