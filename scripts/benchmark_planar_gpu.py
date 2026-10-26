"""Bounded real planar-physics GPU benchmark, not a lap/GA performance claim."""
from dataclasses import asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
import argparse
import json
from pathlib import Path
import random
import statistics
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import numpy as np
from lapsim.dynamics.conditions import PlanarEnvironment, PlanarRoad, RectangularGripPatch, RoadDomain
from lapsim.dynamics.planar import PlanarControls, PlanarState, PlanarVehicleConfig
from lapsim.dynamics.planar_opencl import PlanarOpenCL, PlanarSample, FIELDS, evaluate_cpu
from lapsim.experiments.closed_loop import synthetic_car


def generated_samples(count, seed=20261026):
    rng=random.Random(seed)
    values=[]
    for i in range(count):
        car=replace(synthetic_car(),mass_kg=rng.uniform(200,500),yaw_inertia_kgm2=rng.uniform(100,240),
            wheel_inertia_kgm2=rng.uniform(.3,.9),tire_mu=rng.uniform(.6,1.6),
            cg_to_front_axle_m=rng.uniform(.6,1.0),cg_to_rear_axle_m=rng.uniform(.6,1.0),
            longitudinal_stiffness_n_per_slip=rng.uniform(2000,8000),
            cornering_stiffness_n_per_rad=rng.uniform(3000,9000))
        speed=rng.uniform(-2,30)
        state=PlanarState(x_m=rng.uniform(-8,8),y_m=rng.uniform(-8,8),heading_rad=rng.uniform(-3.14,3.14),
            u_mps=speed,v_mps=rng.uniform(-3,3),yaw_rate_rad_s=rng.uniform(-1,1),
            wheel_speeds_rad_s=tuple((speed+rng.uniform(-8,8))/.2 for _ in range(4)))
        control=PlanarControls(steering_angles_rad=tuple(rng.uniform(-.4,.4) for _ in range(4)),
            drive_torques_nm=tuple(rng.uniform(-150,280) for _ in range(4)),
            brake_torques_nm=tuple(rng.uniform(0,150) for _ in range(4)),
            normal_loads_n=(0.,700.,800.,0.) if i%17==0 else None,
            wheel_radii_m=tuple(rng.uniform(.18,.24) for _ in range(4)),
            external_force_x_n=rng.uniform(-200,200),external_force_y_n=rng.uniform(-100,100),
            external_yaw_moment_nm=rng.uniform(-30,30))
        env=PlanarEnvironment(wind_world_x_mps=rng.uniform(-5,5),wind_world_y_mps=rng.uniform(-5,5),
            drag_area_m2=rng.uniform(0,2),air_density_kgpm3=rng.uniform(1,1.4),
            road=PlanarRoad(base_friction_multiplier=rng.uniform(.5,1.3),
                patches=(RectangularGripPatch(-4,4,-4,4,.25),),valid_domain=RoadDomain(-7,7,-7,7)))
        values.append(PlanarSample(car,state,control,env))
    return values


def saved_course_samples():
    receipt=json.loads((ROOT/'configs/courses/acceptance_20261026.json').read_text())
    values=[];provenance=[]
    for entry in receipt['completed']:
        path=ROOT/entry['record_path']
        payload=path.read_bytes()
        if sha256(payload).hexdigest()!=entry['record_sha256']:
            raise ValueError('Saved baseline record changed')
        record=json.loads(payload.decode('utf-8-sig'))
        car=PlanarVehicleConfig(**record['car'])
        env_values=record['environment'].copy()
        # Public baseline is uniform road. Reject rather than guessing if the
        # stored environment schema later includes patches or a bounded domain.
        road=env_values.pop('road')
        if road['patches'] or road['valid_domain'] is not None:
            raise ValueError('Saved-course benchmark requires explicit road parser for nonuniform road')
        env=PlanarEnvironment(**env_values,road=PlanarRoad(**{**road,'patches':()}))
        rows=record['telemetry']
        indices=np.linspace(0,len(rows)-1,min(512,len(rows)),dtype=int)
        for i in indices:
            row=rows[int(i)]
            state=PlanarState(row['x_m'],row['y_m'],row['heading_rad'],row['u_mps'],row['v_mps'],
                row['yaw_rad_s'],tuple(row['wheel_omega_rad_s']))
            control=PlanarControls(steering_angles_rad=tuple(row['steering_rad']),
                drive_torques_nm=tuple(row['achieved_nm']),brake_torques_nm=tuple(row['friction_nm']))
            values.append(PlanarSample(car,state,control,env))
        provenance.append({'course_id':entry['course_id'],'record_sha256':entry['record_sha256'],
            'samples':len(indices),'scope':'Re-evaluation of saved instantaneous states/achieved controls; not replay or a new lap'})
    return values,provenance


def compare(expected,actual):
    error=np.abs(expected-actual)
    tolerance=1e-8+1e-10*np.abs(expected)
    if not np.all(error<=tolerance):
        lane,column=np.unravel_index(np.argmax(error/tolerance),error.shape)
        raise AssertionError(f'CPU/GPU mismatch lane {lane} field {FIELDS[column]}: {expected[lane,column]} vs {actual[lane,column]}')
    return {'all_fields_passed':True,'absolute_tolerance':1e-8,'relative_tolerance':1e-10,
        'max_absolute_error':float(error.max()),'max_tolerance_fraction':float((error/tolerance).max()),
        'rationale':'FP64 independent host/device transcendental functions and reordered reductions permit roundoff; all 89 SI derivative/force/power/contact fields checked. Not a long-trajectory tolerance.'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--device',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--saved-course-samples',action='store_true',help='Also validate local hashed baseline records; unavailable records fail explicitly')
    args=parser.parse_args();output=Path(args.output)
    if output.exists():raise ValueError('Preserve prior benchmark evidence')
    values=generated_samples(8192)
    rounds=[]
    with PlanarOpenCL(device_name=args.device) as backend:
        cold=backend.runtime.initialization_s
        for size in (1,32,512,8192):
            subset=values[:size];cpu_trials=[]
            for _ in range(3):
                started=perf_counter();reference=evaluate_cpu(subset);cpu_trials.append(perf_counter()-started)
            cpu=statistics.median(cpu_trials)
            trials=[];device=[]
            for _ in range(3):
                actual,evidence=backend.evaluate(subset);parity=compare(reference,actual)
                trials.append(evidence['total_batch_s']);device.append(evidence['device_kernel_s'])
            median=statistics.median(trials)
            rounds.append({'rows':size,'cpu_reference_median_s':cpu,'cpu_reference_trials_s':cpu_trials,'gpu_total_batch_median_s':median,
                'gpu_total_batch_trials_s':trials,'gpu_device_kernel_trials_s':device,
                'warm_end_to_end_speedup':cpu/median,'new_context_one_batch_speedup':cpu/(cold+trials[0]),
                'parity':parity,'evidence':evidence})
        saved_result={'status':'not_requested','rows':0,'reason':'Local saved records are optional; generated public fixtures remain self-contained'}
        if args.saved_course_samples:
            saved,provenance=saved_course_samples()
            started=perf_counter();reference=evaluate_cpu(saved);cpu=perf_counter()-started
            actual,evidence=backend.evaluate(saved);parity=compare(reference,actual)
            repeated,_=backend.evaluate(saved)
            if not np.array_equal(actual,repeated):raise AssertionError('Device repeats differ')
            saved_result={'status':'passed','rows':len(saved),'provenance':provenance,
                'cpu_reference_s':cpu,'gpu_evidence':evidence,'parity':parity,'deterministic_repeat':True}
        result={'schema':'lapsim.gpu-planar-benchmark.v1','utc':datetime.now(timezone.utc).isoformat(),
            'seed':20261026,'device':asdict(backend.runtime.device),'backend':'OpenCL GPU FP64',
            'kernel_sha256':backend.runtime.source_sha256,'context_compile_initialization_s':cold,
            'driver_compilation_cache':'Existing driver cache is retained; new context/program build timing is not an uncached compiler benchmark.',
            'generated_batches':rounds,'six_course_saved_samples':saved_result,
            'cpu_screening_preserved':True,'full_laps_executed':0,'ga_executed':False,
            'scope':'Instantaneous four-wheel planar force/derivative batch only. Includes host road lookup/packing, allocation, transfers, kernel, readback and release; new-context build separately and amortized once; driver cache may be warm.',
            'not_implemented':['Powered RK event loop','Actuator/pack constraints on GPU','Locked-axle reaction on GPU','Course driver/controller clocks on GPU','GPU full-lap or GA evaluation'],
            'official_points':False}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'output':str(output),'device':result['device']['name'],'compile_s':cold,
        'batches':[{'rows':r['rows'],'speedup':r['warm_end_to_end_speedup'],'parity':r['parity']['all_fields_passed']} for r in rounds],
        'saved_course_samples':saved_result['rows'],'saved_parity':saved_result['status'],'full_laps_executed':0,'ga_executed':False}))

if __name__=='__main__':main()
