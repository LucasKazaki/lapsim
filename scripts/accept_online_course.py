"""One actual full-lap attempt; use the owned resource guard, no hidden retries."""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from lapsim.courses.library import CAMPAIGN_COURSE_IDS,course_library
from lapsim.experiments.tournament_rollout import Case,Controller,rollout
from lapsim.experiments.record_io import write_text_atomic

def main():
    p=argparse.ArgumentParser();p.add_argument('--course',choices=CAMPAIGN_COURSE_IDS,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Preserve prior result')
    entry=next(r for r in course_library()['courses'] if r['id']==a.course)
    case=Case('online-course-baseline-v1',course='bundle',course_bundle=entry['bundle'],duration_s=300,long_course=True,regen_available=False)
    started=datetime.now(timezone.utc).isoformat()
    print(json.dumps({'starting_utc':started,'course':a.course,'backend':'cpu-python','profile':'synthetic_awd','controller':'fixed','regen':'disabled','maximum_sim_s':300,'maximum_work':200000}),flush=True)
    record=rollout(Controller('fixed'),case,profile='synthetic_awd')
    write_text_atomic(a.output,json.dumps(record,allow_nan=False,separators=(',',':'))+'\n')
    summary={'started_utc':started,'finished_utc':datetime.now(timezone.utc).isoformat(),'course':a.course,'backend':'cpu-python','status':record['status'],'eligible':record['eligible'],'violations':record['violations'],'metrics':record['metrics'],'work':record['work'],'record_sha256':sha256(a.output.read_bytes()).hexdigest()}
    write_text_atomic(a.output.with_suffix('.summary.json'),json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps(summary,allow_nan=False),flush=True)
    return 0 if record['eligible'] else 2
if __name__=='__main__':raise SystemExit(main())
