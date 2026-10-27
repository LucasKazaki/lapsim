"""Receipt-gated search data. Raw/partial results never become eligible alone."""
from hashlib import sha256
import json
from pathlib import Path
import re

from .gpu_search import digest

VERIFICATION_KEYS={'verification_state','batch_receipt','batch_receipt_sha256'}


def payload(row):return {k:v for k,v in row.items() if k not in VERIFICATION_KEYS}


def save_new(path,value):
    path=Path(path)
    if path.exists():raise ValueError('Preserve prior provenance: '+str(path))
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')


def publish_verified(folder,candidate,scenario,rows,*,before_sources,after_sources,
                     kind='evaluation',execution_sources=None,extra=None):
    """Commit a receipt before publishing summaries; reject drift atomically.

    Raw records and staged summaries already exist. A killed process before
    receipt publication leaves no accepted summary. A killed process during
    publication leaves a verified subset whose receipt covers its exact data.
    """
    folder=Path(folder)
    if before_sources!=after_sources:raise ValueError('Source drift: staged results remain unverified')
    if kind not in ('evaluation','historical_anchor','verified_import'):raise ValueError('Unknown verification kind')
    if kind=='historical_anchor' and candidate!='anchor-gpu-fixed-off':raise ValueError('Historical anchor identity mismatch')
    if kind=='evaluation' and execution_sources is not None and execution_sources!=before_sources:
        raise ValueError('Evaluation receipt cannot accept mismatched execution sources')
    name='batch-'+str(len(list(folder.glob('batch-*.json')))).zfill(2)+'.json'
    receipt={'schema':'lapsim.verified-search-batch.v1','status':'verified','kind':kind,
        'candidate':candidate,'scenario':scenario,'sources':before_sources,
        'execution_sources':execution_sources if execution_sources is not None else before_sources,
        'summaries':{course:{'summary_sha256':digest(payload(row)),
            'raw_record_sha256':row['raw_record_sha256']} for course,row in rows.items()},
        'extra':extra or {}}
    save_new(folder/name,receipt)
    receipt_hash=sha256((folder/name).read_bytes()).hexdigest()
    for course,row in rows.items():
        save_new(folder/(course+'.summary.json'),{**payload(row),'verification_state':'verified',
            'batch_receipt':name,'batch_receipt_sha256':receipt_hash})
    return receipt


def read_verified(path,sources,candidate,scenario,course):
    path=Path(path)
    if not path.exists():return None
    row=json.loads(path.read_text(encoding='utf-8-sig'))
    if row.get('verification_state')!='verified':return None
    name=row.get('batch_receipt','')
    if not re.fullmatch(r'batch-[0-9]+\.json',name):return None
    receipt_path=path.parent/name
    if not receipt_path.exists():return None
    blob=receipt_path.read_bytes()
    if sha256(blob).hexdigest()!=row.get('batch_receipt_sha256'):return None
    receipt=json.loads(blob)
    if receipt.get('schema')!='lapsim.verified-search-batch.v1' or receipt.get('status')!='verified':return None
    if receipt.get('sources')!=sources or receipt.get('candidate')!=candidate or receipt.get('scenario')!=scenario:return None
    if receipt.get('kind') not in ('evaluation','historical_anchor','verified_import'):return None
    if receipt.get('kind')=='historical_anchor' and candidate!='anchor-gpu-fixed-off':return None
    if receipt.get('kind')=='evaluation' and receipt.get('execution_sources')!=sources:return None
    entry=receipt.get('summaries',{}).get(course)
    if not entry or entry['summary_sha256']!=digest(payload(row)) or entry['raw_record_sha256']!=row.get('raw_record_sha256'):return None
    return row


def verify_anchor(blob,expected_sha,*,expected_controller,expected_case,expected_car,
                  expected_pack,expected_driver,geometry_sha256,distance_m):
    """Verify original bytes and matched inputs before historical metric reuse."""
    if sha256(blob).hexdigest()!=expected_sha:raise ValueError('Anchor raw record hash mismatch')
    record=json.loads(blob.decode('utf-8-sig'))
    if record.get('status')!='completed' or not record.get('eligible') or record.get('violations'):
        raise ValueError('Anchor is not a valid completed original record')
    if record.get('profile')!='synthetic_awd':raise ValueError('Anchor hardware profile mismatch')
    checks=(('controller',expected_controller),('car',expected_car),('actuation',expected_pack),('driver',expected_driver))
    for name,expected in checks:
        if record.get(name)!=expected:raise ValueError('Anchor '+name+' mismatch')
    actual_case={k:v for k,v in record.get('case',{}).items() if k!='name'}
    case={k:v for k,v in expected_case.items() if k!='name'}
    if actual_case!=case:raise ValueError('Anchor case mismatch')
    course=record.get('course',{})
    if course.get('geometry_sha256')!=geometry_sha256 or abs(course.get('length_m',0)-distance_m)>1e-9:
        raise ValueError('Anchor geometry/length mismatch')
    rows=record.get('telemetry',[])
    if not rows:raise ValueError('Anchor initial state unavailable')
    first=rows[0]
    if (first.get('t_s')!=0 or first.get('u_mps')!=5 or first.get('v_mps')!=0 or first.get('yaw_rad_s')!=0
        or abs(first.get('pack_energy_j',-1)-expected_case['initial_soc']*expected_pack['pack_capacity_j'])>1e-8
        or first.get('wheel_omega_rad_s')!=[5/expected_car['wheel_radius_m']]*4):
        raise ValueError('Anchor initial conditions mismatch')
    return record
