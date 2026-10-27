"""Compare complete held-command powered intervals, not just force kernels."""
from dataclasses import replace
from datetime import datetime,timezone
import argparse
from hashlib import sha256
import json
from pathlib import Path
import random
import statistics
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import numpy as np
from lapsim.dynamics.actuation import AWD_TOPOLOGY_ID,SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID
from lapsim.dynamics.planar import PlanarState
from lapsim.dynamics.planar_opencl import PlanarOpenCL
from lapsim.dynamics.powered_planar import PoweredState,advance_powered,_vector
from lapsim.dynamics.powered_opencl import PoweredInterval,advance_powered_batch
from lapsim.experiments.tournament_rollout import fixture


def requests(count):
    rng=random.Random(20261026);result=[]
    car,act,_=fixture()
    for i in range(count):
        topology=(AWD_TOPOLOGY_ID,SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID)[i%3]
        speed=rng.uniform(5,15);omega=speed/car.wheel_radius_m
        available=(True,)*4 if topology==AWD_TOPOLOGY_ID else (False,False,True,True)
        command=tuple((-60. if i%2 else 100.) if v else 0. for v in available)
        plant=PlanarState(u_mps=speed,v_mps=rng.uniform(-.2,.2),yaw_rate_rad_s=rng.uniform(-.1,.1),
            wheel_speeds_rad_s=(omega,)*4)
        pack=replace(act,topology_id=topology)
        result.append(PoweredInterval(car,pack,PoweredState(plant,command,.7*pack.pack_capacity_j),
            command,(.04,.04,0.,0.),(3.,)*4,available,.01,maximum_work=200000))
    return result


def cpu(request):
    r=request
    return advance_powered(r.config,r.actuation,r.state,r.command_nm,r.steering,r.brakes,
        r.available,r.timestep_s,r.environment,driver_proxy_n=r.driver_proxy_n,
        maximum_work=r.maximum_work,wheel_radii_m=r.wheel_radii_m)


def compare(actual,expected):
    a=np.asarray([_vector(v) for v in actual]);e=np.asarray([_vector(v) for v in expected])
    np.testing.assert_allclose(a,e,rtol=1e-10,atol=1e-8)
    for first,second in zip(actual,expected,strict=True):
        for field in ('integration_trials','integration_substeps','wheel_stop_events'):
            if getattr(first,field)!=getattr(second,field):raise AssertionError('Event/work counters differ')
    return {'passed':True,'rtol':1e-10,'atol':1e-8,'max_absolute_state_ledger_error':float(np.abs(a-e).max()),
        'event_work_counters_equal':True,'scope':'Ten-millisecond held-command intervals only; not long-lap tolerance'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--device',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();destination=Path(args.output)
    if destination.exists():raise ValueError('Preserve prior benchmark')
    rounds=[]
    with PlanarOpenCL(device_name=args.device) as backend:
        for size in (1,32,128):
            values=requests(size);cpu_trials=[]
            for _ in range(3):
                started=perf_counter();reference=[cpu(r) for r in values];cpu_trials.append(perf_counter()-started)
            cpu_s=statistics.median(cpu_trials)
            timings=[]
            for _ in range(3):
                actual,evidence=advance_powered_batch(backend,values)
                parity=compare(actual,reference);timings.append(evidence['total_interval_batch_s'])
            median=statistics.median(timings)
            rounds.append({'lanes':size,'cpu_median_s':cpu_s,'cpu_trials_s':cpu_trials,'gpu_hybrid_trials_s':timings,
                'end_to_end_speedup':cpu_s/median,'new_context_one_batch_speedup':cpu_s/(timings[0]+backend.runtime.initialization_s),
                'evidence':evidence,'parity':parity})
        result={'schema':'lapsim.powered-gpu-benchmark.v1','utc':datetime.now(timezone.utc).isoformat(),
            'device':backend.runtime.device.name,'driver':backend.runtime.device.driver,
            'backend':'Hybrid OpenCL GPU FP64 forces / CPU events and limits','seed':20261026,
            'kernel_sha256':backend.runtime.source_sha256,'new_context_build_s':backend.runtime.initialization_s,
            'driver_cache':'Retained; program build may use installed driver cache',
            'sources':{path:sha256((ROOT/path).read_bytes()).hexdigest() for path in
                ('src/lapsim/dynamics/powered_planar.py','src/lapsim/dynamics/actuation.py',
                 'src/lapsim/dynamics/powered_opencl.py','src/lapsim/dynamics/planar_opencl.py')},
            'rounds':rounds,'full_laps_executed':0,'ga_executed':False,
            'scope':'Complete .01 s powered plant intervals, including CPU event/limit work, packing, allocation, GPU forces, transfer, readback and typed reconstruction. No controller/course loop and no lap speedup claim.'}
    destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'output':str(destination),'device':result['device'],'rounds':
        [{'lanes':r['lanes'],'speedup':r['end_to_end_speedup'],'parity':r['parity']} for r in rounds]}))

if __name__=='__main__':main()
