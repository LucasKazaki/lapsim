"""Complete resident plant interval batches with matched continuous CPU state."""
from dataclasses import replace
from datetime import datetime,timezone
import argparse,json
from pathlib import Path
import statistics,sys
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from benchmark_powered_gpu import requests,cpu,compare
from lapsim.dynamics.resident_powered import ResidentPowered


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--device',required=True);parser.add_argument('--output',required=True)
    a=parser.parse_args();destination=Path(a.output)
    if destination.exists():raise ValueError('Preserve prior evidence')
    rounds=[]
    for size in (1,32,128):
        initial=requests(size);cpu_trials=[]
        for trial in range(3):
            rows=initial;reference=[];started=perf_counter()
            for _ in range(10):
                states=[cpu(r) for r in rows];reference.append(states)
                rows=[replace(r,state=s) for r,s in zip(rows,states,strict=True)]
            cpu_trials.append(perf_counter()-started)
        gpu_trials=[];setup=[];device=[]
        for _ in range(3):
            with ResidentPowered(initial,device_name=a.device) as backend:
                setup.append(backend.initialization_s);started=perf_counter();device_s=0
                for step in range(10):
                    states,evidence=backend.step();device_s+=evidence['device_kernel_s']
                    parity=compare(states,reference[step])
                gpu_trials.append(perf_counter()-started);device.append(device_s)
        rounds.append({'lanes':size,'continuous_intervals':10,'interval_s':.01,'cpu_trials_s':cpu_trials,
            'gpu_trials_s':gpu_trials,'setup_build_upload_trials_s':setup,'device_kernel_trials_s':device,
            'warm_workflow_speedup':statistics.median(cpu_trials)/statistics.median(gpu_trials),
            'setup_inclusive_speedup':statistics.median(cpu_trials)/statistics.median([x+y for x,y in zip(gpu_trials,setup,strict=True)]),
            'parity':parity,'evidence':evidence})
    result={'schema':'lapsim.resident-powered-benchmark.v1','utc':datetime.now(timezone.utc).isoformat(),
        'backend':evidence['backend'],'device':evidence['device'],'kernel_sha256':evidence['kernel_sha256'],
        'seed':20261026,'rounds':rounds,'full_laps_executed':0,'ga_executed':False,
        'scope':'Ten continuous 10 ms powered intervals; host limits/events are now on device. Includes controls upload, state readback, reconstruction and parity comparison. Driver/controller/course loop not included. Driver cache retained.'}
    destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'output':str(destination),'rounds':[{'lanes':r['lanes'],'warm_speedup':r['warm_workflow_speedup'],
        'setup_inclusive_speedup':r['setup_inclusive_speedup'],'parity':r['parity']} for r in rounds]}))

if __name__=='__main__':main()
