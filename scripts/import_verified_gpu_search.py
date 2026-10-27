"""One-time, audited import of completed pre-gate search batches.

Does not import unverified partial output or rerun simulations. Numerical,
controller, sampling and scoring sources and all actual inputs must match.
"""
import argparse,ast,json,shutil,sys
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from dataclasses import asdict,replace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from lapsim.courses.course_bundle import CourseBundle
from lapsim.experiments.tournament_rollout import Case
from lapsim.experiments.gpu_search import record_summary,digest
from lapsim.experiments.search_provenance import verify_anchor,publish_verified,save_new


def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def functions(path,names):
    tree=ast.parse(Path(path).read_text(encoding='utf-8-sig'))
    return {node.name:ast.dump(node,include_attributes=False) for node in tree.body
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in names}


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-root',required=True);p.add_argument('--source-directory',required=True);p.add_argument('--destination',required=True)
    a=p.parse_args();old_root=Path(a.source_root).resolve();old=(old_root/a.source_directory).resolve();new=Path(a.destination).resolve()
    before=load(old/'plan.json');after=load(new/'plan.json')
    if not (old/'pause.requested').exists():raise ValueError('Original campaign must be paused')
    if (old/'generation-1.json').exists() or (old/'heldout-pool.json').exists():raise ValueError('Post-selection migration needs separate review')
    for field in ('initial_population','scenarios','seed','hardware','courses'):
        if before[field]!=after[field]:raise ValueError('Frozen inputs changed: '+field)
    allowed={'src/lapsim/experiments/gpu_search.py','src/lapsim/experiments/search_provenance.py',
        'scripts/run_gpu_search.py','scripts/run_gpu_search_campaign.ps1'}
    changed={key for key in set(before['sources'])|set(after['sources']) if before['sources'].get(key)!=after['sources'].get(key)}
    if changed-allowed:raise ValueError('Unexpected source changes: '+str(changed-allowed))
    names={'digest','record_summary','matched_ranking','next_generation','controller_for'}
    if functions(old_root/'src/lapsim/experiments/gpu_search.py',names)!=functions(ROOT/'src/lapsim/experiments/gpu_search.py',names):
        raise ValueError('Existing metric/scoring/breeding functions changed')
    for path,identity in before['sources'].items():
        if sha256((old_root/path).read_bytes()).hexdigest()!=identity:raise ValueError('Original frozen source no longer available: '+path)
    accepted_sources=[before['sources']]
    provenance=old/'continuation-provenance.json'
    if provenance.exists():
        previous=load(old_root/load(provenance)['source_directory']/'plan.json')
        different={key for key in before['sources'] if before['sources'][key]!=previous['sources'].get(key)}
        if different!={'scripts/run_gpu_validation_guarded.ps1'}:raise ValueError('Unexpected earlier launcher continuation')
        accepted_sources.append(previous['sources'])
    imported=[];quarantined=[]
    for candidate in before['initial_population']:
        source=old/'records/train'/candidate['id'];receipts=list(source.glob('batch-*.json'))
        if not source.exists():continue
        if len(receipts)!=1:
            quarantined.append({'candidate':candidate['id'],'reason':'Missing or ambiguous successful original batch receipt'});continue
        batch=load(receipts[0])
        if batch.get('sources') not in accepted_sources or 'workflow' not in batch or not batch['workflow'].get('owned_threads_exited'):
            quarantined.append({'candidate':candidate['id'],'reason':'Original batch source/completion receipt not verified'});continue
        rows={};blobs={}
        for course,entry in after['courses'].items():
            old_summary=load(source/(course+'.summary.json'));blob=(source/(course+'.record.json')).read_bytes()
            case=Case('gpu-ga/train',course='bundle',course_bundle=entry['bundle'],duration_s=300,long_course=True,
                regen_available=candidate['policy']['regen_mode']!='off',**after['scenarios']['train'])
            bundle=CourseBundle.from_dict(entry['bundle']);driver=dict(after['fixed_fixture']['driver'])
            driver.update(assumed_half_width_m=bundle.default_ai_half_width_m,
                vehicle_width_m=bundle.default_ai_vehicle_width_m,safety_margin_m=bundle.default_ai_margin_m)
            record=verify_anchor(blob,old_summary['raw_record_sha256'],expected_controller=candidate['policy'],
                expected_case=asdict(case),expected_car=after['fixed_fixture']['car'],expected_pack=after['fixed_fixture']['pack'],
                expected_driver=driver,geometry_sha256=entry['geometry_sha256'],distance_m=entry['length_m'])
            values=record_summary(record)
            for key,value in values.items():
                if old_summary.get(key)!=value:raise ValueError('Original summary disagrees with raw record: '+key)
            rows[course]={**values,'raw_record_sha256':sha256(blob).hexdigest(),'policy_sha256':candidate['sha256'],
                'scenario_sha256':digest(after['scenarios']['train']),'original_finished_utc':old_summary.get('finished_utc')}
            blobs[course]=blob
        destination=new/'records/train'/candidate['id']
        if destination.exists():raise ValueError('Preserve prior imported candidate')
        destination.mkdir(parents=True)
        for course,blob in blobs.items():(destination/(course+'.record.json')).write_bytes(blob)
        publish_verified(destination,candidate['id'],'train',rows,before_sources=after['sources'],after_sources=after['sources'],
            kind='verified_import',execution_sources=batch['sources'],extra={
                'original_batch_sha256':sha256(receipts[0].read_bytes()).hexdigest(),
                'original_workflow':batch['workflow'],'validated_inputs':'Original raw hash, controller, case, actual AWD fixture, geometry, initial state and all metric summaries matched',
                'unchanged_numeric_sources':True,'changed_metadata_or_finalist_files':sorted(changed)})
        imported.append({'candidate':candidate['id'],'laps':len(rows),'original_batch_sha256':sha256(receipts[0].read_bytes()).hexdigest()})
    # Keep aggregate resource accounting inclusive of completed/failed old jobs.
    guard_source=old_root/'work/gpu-readiness-20261026';guard_target=ROOT/'work/gpu-readiness-20261026';guard_target.mkdir(parents=True,exist_ok=True)
    guards=[]
    for path in guard_source.glob('search-evaluate-ga-*.guard.json'):
        target=guard_target/path.name
        if target.exists():raise ValueError('Existing guard accounting needs inspection')
        shutil.copyfile(path,target);guards.append(path.name)
    receipt={'utc':datetime.now(timezone.utc).isoformat(),'source':str(old),'imported':imported,'quarantined':quarantined,
        'guard_records_carried_forward':guards,'old_manifest_descriptor':'Default RWD pack descriptor was wrong; actual records are verified AWD. No executed hardware input changed.',
        'importer_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    save_new(new/'verified-continuation.json',receipt)
    print(json.dumps({'imported_candidates':len(imported),'imported_laps':sum(v['laps'] for v in imported),'quarantined':quarantined,'guards':len(guards)}))

if __name__=='__main__':main()
