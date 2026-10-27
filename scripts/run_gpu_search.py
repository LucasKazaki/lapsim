"""One explicitly guarded GPU GA evaluation at a time, with frozen sources."""
from dataclasses import asdict,replace
from datetime import datetime,timezone
from hashlib import sha256
import argparse,json,platform,random,sys
from pathlib import Path
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import numpy,scipy
from lapsim.courses.library import CAMPAIGN_COURSE_IDS,course_library
from lapsim.courses.course_bundle import CourseBundle
from lapsim.dynamics.actuation import AWD_TOPOLOGY_ID
from lapsim.experiments.gpu_tournament import GPUJob,rollout_gpu_batch
from lapsim.experiments.gpu_search import record_summary,matched_ranking,next_generation,freeze_finalists,controller_for,digest
from lapsim.experiments.search_policy import initial_population
from lapsim.experiments.tournament_rollout import Case,Controller,fixture
from lapsim.experiments.search_provenance import read_verified,publish_verified,verify_anchor


def now():return datetime.now(timezone.utc).isoformat()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def save(path,value,*,replace=False):
    path=Path(path)
    if path.exists() and not replace:raise ValueError('Preserve prior evidence: '+str(path))
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')


def sources():
    paths=[*sorted((ROOT/'src/lapsim').rglob('*.py')),Path(__file__).resolve(),
        ROOT/'scripts/run_gpu_validation_guarded.ps1',ROOT/'scripts/run_gpu_search_campaign.ps1']
    return {p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in paths}


def candidates(directory,plan):
    result=[*plan['anchors'],*plan['initial_population']]
    path=directory/'generation-1.json'
    if path.exists():result+=load(path)['offspring']
    return result


def records(directory,plan,cs):
    result={}
    for c in cs:
        for scenario in plan['scenarios']:
            for course in plan['courses']:
                path=directory/'records'/scenario/c['id']/(course+'.summary.json')
                row=read_verified(path,plan['sources'],c['id'],scenario,course)
                if row is not None:result[c['id'],scenario,course]=row
    return result


def summary(directory,plan):
    cs=candidates(directory,plan);rs=records(directory,plan,cs)
    train=matched_ranking(cs,rs,list(plan['courses']),['train'])
    train['provisional']=any((c['id'],'train',course) not in rs for c in cs for course in plan['courses'])
    held=None
    if (directory/'heldout-pool.json').exists():
        pool=load(directory/'heldout-pool.json')['candidates']
        held=matched_ranking(pool,rs,list(plan['courses']),['heldout-a','heldout-b'])
        held['provisional']=any((c['id'],scenario,course) not in rs for c in pool
            for scenario in ('heldout-a','heldout-b') for course in plan['courses'])
    result={'schema':'lapsim.gpu-ga-coverage.v1','utc':now(),'scoring_version':train['scoring_version'],
        'official_points':False,'training':train,'heldout':held,
        'counts':{'training_planned':len(cs)*6,'training_saved':sum(k[1]=='train' for k in rs),
            'training_valid':sum(k[1]=='train' and r['status']=='completed' and r['eligible'] and not r['violations'] for k,r in rs.items()),
            'heldout_saved':sum(k[1]!='train' for k in rs)},
        'source_sha256':plan['sources'],'seed':plan['seed'],'hardware':plan['hardware'],
        'scope':'Complete common six-course coverage only; anchors reuse previously validated GPU data. No official event or real-car optimality claim.'}
    save(directory/'coverage.json',result,replace=True)
    return result


def prepare(directory,device,anchor_root=None):
    if directory.exists():raise ValueError('Existing search must be preserved')
    seed=20261026;rng=random.Random(seed+997)
    catalog=course_library();entries={r['id']:r for r in catalog['courses'] if r['id'] in CAMPAIGN_COURSE_IDS}
    if len(entries)!=6:raise ValueError('Six exact campaign courses required')
    acceptance=load(ROOT/'docs/resident_gpu_20261026.json')['six_course_laps']
    if not acceptance['all_passed']:raise ValueError('GPU course acceptance missing')
    car,pack,driver=fixture()
    pack=replace(pack,topology_id=AWD_TOPOLOGY_ID)
    anchor_rows={};anchor_reasons={}
    for row in acceptance['rows']:
        course=row['job'];entry=entries[course]
        try:
            if anchor_root is None:raise ValueError('Original anchor record unavailable; fresh evaluation required')
            raw=(Path(anchor_root)/row['raw_record']).read_bytes()
            bundle=CourseBundle.from_dict(entry['bundle'])
            expected_driver=replace(driver,assumed_half_width_m=bundle.default_ai_half_width_m,
                vehicle_width_m=bundle.default_ai_vehicle_width_m,safety_margin_m=bundle.default_ai_margin_m)
            expected_case=Case('verified-anchor',course='bundle',course_bundle=entry['bundle'],duration_s=300,
                long_course=True,regen_available=False,grip=1.,initial_soc=.7)
            record=verify_anchor(raw,row['raw_record_sha256'],expected_controller=asdict(Controller()),
                expected_case=asdict(expected_case),expected_car=asdict(car),expected_pack=asdict(pack),
                expected_driver=asdict(expected_driver),geometry_sha256=entry['geometry_sha256'],distance_m=entry['length_m'])
            anchor_rows[course]={**record_summary(record),'raw_record_sha256':sha256(raw).hexdigest(),
                'anchor_reuse':True,'source':'Verified original raw GPU baseline, case/controller/fixture/geometry matched'}
        except (ValueError,OSError,KeyError) as error:anchor_reasons[course]=str(error)
    plan={'schema':'lapsim.gpu-ga-plan.v1','created_utc':now(),'seed':seed,'device':device,
        'versions':{'python':platform.python_version(),'numpy':numpy.__version__,'scipy':scipy.__version__},
        'sources':sources(),'hardware':'synthetic_awd','courses':entries,
        'fixed_fixture':{'car':asdict(car),'pack':asdict(pack),'driver':asdict(driver),'initial_speed_mps':5.,'voltage_v':580.,'motor_temperature_c':40.,'laps':1},
        'initial_population':initial_population(seed),'anchors':[{'id':'anchor-gpu-fixed-off','anchor':True,'can_breed':False,
            'policy':asdict(Controller()),'origin':'Previously validated six-course resident GPU baseline; no duplicate evaluation'}],
        'scenarios':{'train':{'grip':1.,'initial_soc':.7},
            'heldout-a':{'grip':rng.uniform(.8,.92),'initial_soc':rng.uniform(.4,.55)},
            'heldout-b':{'grip':rng.uniform(1.05,1.2),'initial_soc':rng.uniform(.8,.9)}},
        'budget':{'initial_gpu_candidates':18,'offspring':6,'genetic_children':4,'random_immigrants':2,
            'generations':2,'maximum_finalists_plus_anchor':5,'heldout_scenarios':2,'maximum_new_gpu_laps':204+6-len(anchor_rows),'aggregate_guard_wall_s':4800,'per_job_outer_wall_s':180},
        'anchor_provenance':{'verified_reused_courses':list(anchor_rows),'fresh_evaluation_required':anchor_reasons},
        'selection':'Canonical 275+100 adaptation, all eligible parents and children rescored together in a common field before selection. Reference anchor fixed; new best field references update for every candidate equally. Final pool frozen before held-out evaluation; no stale normalized scores or held-out retuning.',
        'eligibility':'All six valid completed training laps, and all twelve held-out laps for final ranking. Failed, unfinished, unrun and unmeasurable energy are excluded from winner/reference pools.',
        'exclusions':['One synthetic AWD hardware stratum; no RWD/AWD hardware ranking.','Uniform-road deterministic model; held-out seed draws shared scenario inputs, not invented sensor noise.','No calibrated motor maps, measured tires, thermal accumulation or official endurance/driver-change/inspection validation.','Hard physical/resource limits unchanged; no publication/deployment of results.']}
    directory.mkdir(parents=True);save(directory/'plan.json',plan)
    if anchor_rows:
        publish_verified(directory/'records/train/anchor-gpu-fixed-off','anchor-gpu-fixed-off','train',anchor_rows,
            before_sources=plan['sources'],after_sources=sources(),kind='historical_anchor',
            execution_sources=load(ROOT/'docs/resident_gpu_20261026.json')['executed_source_sha256'],
            extra={'checks':'Original raw hash, controller, case, AWD car/pack/driver fixture, geometry, distance and initial conditions verified',
                'original_receipt_sha256':sha256((ROOT/'docs/resident_gpu_20261026.json').read_bytes()).hexdigest()})
    summary(directory,plan)
    print(json.dumps({'prepared':str(directory),'seed':seed,'initial_candidates':18,'new_training_laps':108,'reused_anchor_laps':len(anchor_rows),'anchor_reruns_required':anchor_reasons,'budget':plan['budget']}),flush=True)


def evaluate(directory,plan,identity,scenario):
    if plan['sources']!=sources():raise ValueError('Frozen search source changed; no evaluation launched')
    if (directory/'pause.requested').exists():raise ValueError('Coordinated pause requested; no evaluation launched')
    guards=list((ROOT/'work/gpu-readiness-20261026').glob('search-evaluate-ga-*.guard.json'))
    used=sum(load(p).get('wallSeconds',0.) for p in guards)
    if used+180>plan['budget']['aggregate_guard_wall_s']:raise ValueError('Aggregate guarded campaign budget exhausted')
    cs=candidates(directory,plan);candidate=next(c for c in cs if c['id']==identity)
    if scenario!='train':
        pool=load(directory/'heldout-pool.json')['candidates']
        if identity not in {c['id'] for c in pool}:raise ValueError('Candidate outside frozen held-out pool')
    if scenario not in plan['scenarios']:raise ValueError('Unknown scenario')
    controller=controller_for(candidate);conditions=plan['scenarios'][scenario]
    regen=False if candidate.get('anchor') else controller.regen_mode!='off'
    destination=directory/'records'/scenario/identity;jobs=[]
    for course,entry in plan['courses'].items():
        if read_verified(destination/(course+'.summary.json'),plan['sources'],identity,scenario,course) is not None:continue
        if (destination/(course+'.record.json')).exists() or (destination/'staged'/(course+'.summary.json')).exists():
            raise ValueError('Unverified prior partial output requires inspection; no blind replay')
        case=Case('gpu-ga/'+scenario,course='bundle',course_bundle=entry['bundle'],duration_s=300,
            long_course=True,regen_available=regen,**conditions)
        jobs.append(GPUJob(course,controller,case,profile='synthetic_awd'))
    if not jobs:raise ValueError('Candidate/scenario already evaluated; no duplicate')
    started=perf_counter();print(json.dumps({'started_utc':now(),'candidate':identity,'scenario':scenario,'jobs':len(jobs),'aggregate_guard_used_s':used}),flush=True)
    staged={}
    def completed(job,record):
        raw=destination/(job.identity+'.record.json');save(raw,record)
        value={**record_summary(record),'raw_record_sha256':sha256(raw.read_bytes()).hexdigest(),
            'policy_sha256':candidate.get('sha256'),'scenario_sha256':digest(conditions),'finished_utc':now()}
        save(destination/'staged'/(job.identity+'.summary.json'),{**value,'verification_state':'unverified_batch'})
        staged[job.identity]=value
        print(json.dumps({'finished_course':job.identity,'candidate':identity,'scenario':scenario,'status':record['status'],'valid':record['eligible'],'lap_time_s':record['metrics']['lap_time_s']}),flush=True)
    _,evidence=rollout_gpu_batch(jobs,device_name=plan['device'],wall_limit_s=145,record_callback=completed)
    publish_verified(destination,identity,scenario,staged,before_sources=plan['sources'],after_sources=sources(),
        extra={'utc':now(),'workflow':evidence,'wall_s':perf_counter()-started})
    coverage=summary(directory,plan)
    print(json.dumps({'candidate':identity,'scenario':scenario,'workflow':evidence,'counts':coverage['counts']}),flush=True)


def breed(directory,plan):
    cs=candidates(directory,plan);rs=records(directory,plan,cs)
    if any((c['id'],'train',course) not in rs for c in cs for course in plan['courses']):raise ValueError('Initial common coverage incomplete')
    rank=matched_ranking(cs,rs,list(plan['courses']),['train'])
    children=next_generation(cs,rank,plan['seed']+1)
    save(directory/'generation-1.json',{'created_utc':now(),'parent_ranking':rank,'parent_record_pool_sha256':digest(rank),
        'seed':plan['seed']+1,'offspring':children,'heldout_used':False})
    summary(directory,plan);print(json.dumps({'offspring':[c['id'] for c in children]}),flush=True)


def freeze(directory,plan):
    cs=candidates(directory,plan);rs=records(directory,plan,cs)
    if not (directory/'generation-1.json').exists():raise ValueError('Generation one not prepared')
    if any((c['id'],'train',course) not in rs for c in cs for course in plan['courses']):raise ValueError('Training common coverage incomplete')
    rank=matched_ranking(cs,rs,list(plan['courses']),['train'])
    pool=freeze_finalists(cs,rank)
    save(directory/'heldout-pool.json',{'created_utc':now(),'training_ranking':rank,'candidates':pool,
        'pool_sha256':digest(pool),'scenarios':{k:v for k,v in plan['scenarios'].items() if k!='train'},
        'no_retuning_after_this_point':True})
    summary(directory,plan);print(json.dumps({'finalists':[c['id'] for c in pool]}),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',default='work/gpu-search-20261026');p.add_argument('--device',default='NVIDIA GeForce RTX 5080')
    actions=p.add_mutually_exclusive_group(required=True);actions.add_argument('--prepare',action='store_true');actions.add_argument('--run');actions.add_argument('--breed',action='store_true');actions.add_argument('--freeze',action='store_true');actions.add_argument('--summary',action='store_true')
    p.add_argument('--scenario',default='train',choices=('train','heldout-a','heldout-b'));p.add_argument('--anchor-root');a=p.parse_args();directory=Path(a.directory).resolve()
    if a.prepare:prepare(directory,a.device,a.anchor_root);return
    plan=load(directory/'plan.json')
    if a.run:evaluate(directory,plan,a.run,a.scenario)
    elif a.breed:breed(directory,plan)
    elif a.freeze:freeze(directory,plan)
    else:print(json.dumps(summary(directory,plan)))

if __name__=='__main__':main()
