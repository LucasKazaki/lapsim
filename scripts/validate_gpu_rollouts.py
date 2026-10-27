"""Full-lap CPU/resident-GPU parity, raw records and honest workflow timings."""
from dataclasses import asdict
from datetime import datetime,timezone
from hashlib import sha256
import argparse,json
from pathlib import Path
import sys
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import numpy as np
from lapsim.experiments.gpu_tournament import GPUJob,rollout_gpu_batch
from lapsim.experiments.tournament_rollout import Controller,Case,rollout


def save(path,value):
    path=Path(path)
    if path.exists():raise ValueError('Preserve existing validation evidence: '+str(path))
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')


def parity(actual,expected):
    # Declared before complete-lap execution. Numeric differences accumulate
    # through closed-loop steering; none of these tolerances relax validity.
    for key in ('status','eligible','violations','profile','topology','car','actuation','driver','clocks'):
        if actual[key]!=expected[key]:raise AssertionError('Full-lap contract differs: '+key)
    if actual['status']!='completed' or not actual['eligible']:raise AssertionError('Full lap did not complete validly')
    if actual['work']!=expected['work']:raise AssertionError('Full-lap numerical work counters differ')
    metric_tolerance={'lap_time_s':1e-5,'net_energy_kwh':1e-8,'energy_residual_j':1e-5,
        'max_slip':1e-6,'max_yaw_rad_s':1e-6,'max_sideslip_rad':1e-6,'max_cross_track_m':1e-5}
    differences={}
    for key,tolerance in metric_tolerance.items():
        error=abs(actual['metrics'][key]-expected['metrics'][key]);differences[key]=error
        if error>tolerance:raise AssertionError(f'Full-lap {key} error {error} > {tolerance}')
    if len(actual['telemetry'])!=len(expected['telemetry']):raise AssertionError('Logging tick count differs')
    channels={'x_m':1e-5,'y_m':1e-5,'heading_rad':1e-6,'u_mps':1e-6,'v_mps':1e-6,
        'yaw_rad_s':1e-6,'wheel_omega_rad_s':1e-5,'pack_energy_j':.036,
        'requested_nm':1e-4,'proposed_nm':1e-4,'limited_nm':1e-4,'achieved_nm':1e-4,'friction_nm':1e-4}
    channel_error={}
    for key,tolerance in channels.items():
        error=float(np.max(np.abs(np.asarray([r[key] for r in actual['telemetry']])-
            np.asarray([r[key] for r in expected['telemetry']]))));channel_error[key]=error
        if error>tolerance:raise AssertionError(f'Full-lap channel {key} error {error} > {tolerance}')
    return {'passed':True,'metric_absolute_errors':differences,'channel_max_absolute_errors':channel_error,
        'metric_tolerances':metric_tolerance,'channel_tolerances':channels,'work_counters_equal':True,
        'logging_ticks_equal':True,'scope':'Complete closed-loop synthetic lap; physical/road calibration remains unverified'}


def representative_jobs():
    return [GPUJob('awd-fixed-off',Controller(),Case('gpu-full-lap',duration_s=40,regen_available=False)),
        GPUJob('awd-yaw-regen',Controller('yaw_pi'),Case('gpu-full-lap',duration_s=40)),
        GPUJob('open-rwd-traction',Controller('traction',yaw_kp=0.,yaw_ki=0.),Case('gpu-full-lap',duration_s=40),profile='synthetic_single_motor_rwd'),
        GPUJob('spool-regen',Controller('tire_reserve',yaw_kp=0.,yaw_ki=0.,pedal_mode='proportional'),Case('gpu-full-lap',duration_s=40),profile='synthetic_spool_rwd')]


def main():
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=('representative','courses'),required=True)
    p.add_argument('--device',required=True);p.add_argument('--output',required=True);p.add_argument('--baseline-root')
    p.add_argument('--reuse-cpu',help='Explicit prior representative record directory; avoids repeating completed CPU laps')
    a=p.parse_args();destination=Path(a.output).resolve();directory=destination.with_suffix('')
    if destination.exists() or directory.exists():raise ValueError('Preserve earlier attempt')
    directory.mkdir(parents=True)
    references=[];provenance=[];cpu_wall=0.
    if a.phase=='representative':
        jobs=representative_jobs();start=perf_counter()
        for job in jobs:
            record=json.loads((Path(a.reuse_cpu)/(job.identity+'.cpu.json')).read_text()) if a.reuse_cpu else rollout(job.controller,job.case,profile=job.profile)
            if record['controller']!=asdict(job.controller) or record['case']!=asdict(job.case) or record['profile']!=job.profile:
                raise ValueError('Prior CPU record configuration mismatch')
            references.append(record);save(directory/(job.identity+'.cpu.json'),record)
        cpu_wall=perf_counter()-start
        provenance=[{'job':j.identity,'cpu_reference':'Explicit preserved representative CPU record' if a.reuse_cpu else 'Fresh same-process scalar CPU rollout'} for j in jobs]
        if a.reuse_cpu:cpu_wall=None
    else:
        if not a.baseline_root:raise ValueError('Explicit local baseline root required')
        baseline=Path(a.baseline_root).resolve();receipt=json.loads((ROOT/'configs/courses/acceptance_20261026.json').read_text())
        jobs=[]
        for entry in receipt['completed']:
            raw=(baseline/entry['record_path']).read_bytes()
            if sha256(raw).hexdigest()!=entry['record_sha256']:raise ValueError('Baseline record hash changed')
            record=json.loads(raw.decode('utf-8-sig'));references.append(record)
            jobs.append(GPUJob(entry['course_id'],Controller(**record['controller']),Case(**record['case']),profile=record['profile']))
            provenance.append({'job':entry['course_id'],'cpu_record_sha256':entry['record_sha256'],
                'cpu_reference':'Preserved completed CPU baseline; not rerun','historical_wall_s':entry['wall_s']})
        cpu_wall=sum(row['historical_wall_s'] for row in provenance)
    print(json.dumps({'started_utc':datetime.now(timezone.utc).isoformat(),'phase':a.phase,'jobs':len(jobs),'cpu_reference_wall_s':cpu_wall}),flush=True)
    records,evidence=rollout_gpu_batch(jobs,device_name=a.device,wall_limit_s=145,
        record_callback=lambda job,record:save(directory/(job.identity+'.gpu.json'),record))
    save(directory/'workflow.json',evidence)
    rows=[];failed=False
    for job,record,reference in zip(jobs,records,references,strict=True):
        try:check=parity(record,reference)
        except AssertionError as error:check={'passed':False,'reason':str(error)};failed=True
        rows.append({'job':job.identity,'status':record['status'],'eligible':record['eligible'],'violations':record['violations'],
            'lap_time_s':record['metrics']['lap_time_s'],'net_energy_wh':1000*record['metrics']['net_energy_kwh'],
            'gross_draw_wh':1000*record['metrics']['gross_pack_draw_kwh_10ms'],'recovered_wh':1000*record['metrics']['recovered_pack_kwh_10ms'],
            'generating_log_samples':sum(r['pack_power_w']<0 for r in record['telemetry']),
            'parity':check,'raw_record':(directory/(job.identity+'.gpu.json')).relative_to(ROOT).as_posix()})
    result={'schema':'lapsim.full-lap-gpu-validation.v1','utc':datetime.now(timezone.utc).isoformat(),'phase':a.phase,
        'rows':rows,'all_passed':not failed,'workflow':evidence,'cpu_reference_wall_s':cpu_wall,
        'workflow_speedup':cpu_wall/evidence['total_batch_wall_s'] if cpu_wall is not None else None,
        'timing_scope':'Reused CPU records; current GPU workflow time only; earlier CPU timing retained separately' if a.reuse_cpu else 'Fresh CPU sequential / GPU batched including initialization and scheduler' if a.phase=='representative' else 'Historical six CPU baseline wall times / current GPU batch including initialization; different measurement times, not a simultaneous benchmark',
        'cpu_provenance':provenance,'ga_executed':False,'official_points':False}
    save(destination,result)
    print(json.dumps(result),flush=True)
    return 2 if failed else 0

if __name__=='__main__':raise SystemExit(main())
