"""Batched resident-GPU plant behind the existing tournament driver/controller.

One host worker per lane prepares the next 10 ms command. A single dispatcher
waits for every active lane and launches one resident device batch. Finished
lanes freeze in place; no simulation runs in the presentation/browser layer.
Threads share no vehicle/controller state. The existing rollout owns clocks,
logging, failure criteria and records. No duplicated allocator or driver logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from queue import Queue,Empty
from threading import Event,Thread
from time import perf_counter

from lapsim.dynamics.conditions import PlanarEnvironment
from lapsim.dynamics.powered_opencl import PoweredInterval
from lapsim.dynamics.resident_powered import ResidentPowered
from .tournament_rollout import Case,Controller,rollout


@dataclass(frozen=True)
class GPUJob:
    identity: str
    controller: Controller
    case: Case
    profile: str = 'synthetic_awd'
    parameter_overrides: dict | None = None


class _Lane:
    def __init__(self):
        self.ready=Event();self.value=None;self.error: str | None=None


def rollout_gpu_batch(jobs,*,device_name,wall_limit_s=150,record_callback=None):
    """Return aligned records and measured batch evidence; no CPU fallback.

    Uniform-road one-lap diagnostics only, at most 64 lanes. Controller/driver
    computations remain the exact CPU functions; plant states, limits, RK and
    wheel-stop events run on the selected GPU. Relative scoring is separate.
    """
    if not 1<=len(jobs)<=64:raise ValueError('Require 1..64 tournament lanes')
    if not 0<wall_limit_s<=150:raise ValueError('Require wall allocation in (0,150] s')
    if len({j.identity for j in jobs})!=len(jobs):raise ValueError('Duplicate job identity')
    for job in jobs:
        if job.case.laps!=1 or job.case.patch:
            raise ValueError('Resident tournament supports one lap and uniform road only')
    started=perf_counter();messages=Queue();lanes=[_Lane() for _ in jobs]
    records=[None]*len(jobs);workers=[];engine=None
    launches=0;device_s=0.;setup_s=0.;initializations=0;aborted=False
    actual_device=device_name;kernel_identity=None

    def worker(index,job):
        lane=lanes[index]
        def step(config,actuation,state,command_nm,steering,brakes,available,timestep_s,
                 environment=None,*,driver_proxy_n=0.,maximum_work=50000,wheel_radii_m=None):
            if lane.error:raise ValueError(lane.error)
            request=PoweredInterval(config,actuation,state,command_nm,steering,brakes,available,
                timestep_s,environment or PlanarEnvironment(),driver_proxy_n,maximum_work,wheel_radii_m)
            lane.ready.clear();messages.put(('request',index,request))
            if not lane.ready.wait(30):raise ValueError('GPU batch dispatcher response timeout')
            if lane.error:raise ValueError(lane.error)
            return lane.value
        try:
            record=rollout(job.controller,job.case,profile=job.profile,
                parameter_overrides=job.parameter_overrides,plant_step=step)
            messages.put(('done',index,record))
        except BaseException as error:
            messages.put(('error',index,f'{type(error).__name__}: {error}'))

    active=set(range(len(jobs)));pending={};mapping={};last={};fixed={}
    try:
        for index,job in enumerate(jobs):
            thread=Thread(target=worker,args=(index,job),name=f'lapsim-gpu-lane-{index}',daemon=True)
            workers.append(thread);thread.start()
        while active:
            remaining=wall_limit_s-(perf_counter()-started)
            if remaining<=0:raise RuntimeError('GPU tournament wall allocation exceeded')
            try:kind,index,payload=messages.get(timeout=min(30,remaining))
            except Empty:raise RuntimeError('GPU tournament lane barrier timed out') from None
            if kind=='request':
                if index in pending:raise RuntimeError('Duplicate pending GPU lane')
                pending[index]=payload
            elif kind=='done':
                records[index]=payload;active.remove(index);pending.pop(index,None)
                payload['numerical_backend']={'backend':'Resident OpenCL GPU FP64 powered plant / original CPU driver-controller',
                    'device':actual_device,'cpu_physics_fallback':False,
                    'kernel_sha256':kernel_identity,'kernel_launches_so_far':launches,
                    'job_identity':jobs[index].identity,'state_initializations':1 if engine else 0}
                if record_callback is not None:record_callback(jobs[index],payload)
            else:raise RuntimeError(f'Tournament lane {index} failed: {payload}')
            if not active or set(pending)!=active:continue
            if engine is None:
                identities=sorted(active);mapping={identity:i for i,identity in enumerate(identities)}
                fixed={identity:pending[identity] for identity in identities}
                engine=ResidentPowered([pending[i] for i in identities],device_name=device_name)
                runtime=engine.runtime
                assert runtime is not None
                actual_device=runtime.device.name;kernel_identity=runtime.source_sha256
                setup_s=engine.initialization_s;initializations=1
                last={i:pending[i].state for i in identities}
            for identity in active:
                request,base=pending[identity],fixed[identity]
                for field in ('config','actuation','available','timestep_s','environment','driver_proxy_n','maximum_work','wheel_radii_m'):
                    if getattr(request,field)!=getattr(base,field):raise RuntimeError('GPU lane fixed inputs changed: '+field)
                if request.state!=last[identity]:raise RuntimeError('GPU lane state reset or identity mismatch')
            commands=[tuple(row[21:25]) for row in engine.parameters]
            steering=[tuple(row[17:21]) for row in engine.parameters]
            brakes=[tuple(row[25:29]) for row in engine.parameters]
            mask=[False]*len(mapping)
            for identity in active:
                slot=mapping[identity];request=pending[identity];mask[slot]=True
                commands[slot]=request.command_nm;steering[slot]=request.steering;brakes[slot]=request.brakes
            states,evidence=engine.step(commands=commands,steering=steering,brakes=brakes,active=mask)
            launches+=1;device_s+=evidence['device_kernel_s']
            for identity in active:
                last[identity]=states[mapping[identity]]
                lanes[identity].value=last[identity];lanes[identity].ready.set()
            pending.clear()
    except BaseException:
        aborted=True;raise
    finally:
        if aborted:
            for lane in lanes:lane.error='GPU batch aborted; no fallback';lane.ready.set()
        deadline=perf_counter()+5
        for thread in workers:thread.join(max(0.,deadline-perf_counter()))
        if engine:engine.close()
    if any(thread.is_alive() for thread in workers):raise RuntimeError('Owned GPU lane thread did not exit')
    elapsed=perf_counter()-started
    evidence={'backend':'Resident OpenCL GPU FP64 powered plant / original CPU driver-controller',
        'device':actual_device,'cpu_physics_fallback':False,
        'lanes':len(jobs),'kernel_launches':launches,'device_kernel_s':device_s,
        'setup_build_initial_upload_s':setup_s,'total_batch_wall_s':elapsed,
        'kernel_sha256':kernel_identity,
        'state_initializations_per_lane':initializations,'owned_threads_exited':True,
        'scope':'One-lap uniform-road simulator records; hardware strata and geometry remain distinct; no scoring in this adapter'}
    for job,record in zip(jobs,records,strict=True):
        assert record is not None
        record['numerical_backend']={**evidence,'job_identity':job.identity,'source':'Resident GPU powered plant with CPU boundary/controller evaluations'}
    return records,evidence
