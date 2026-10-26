"""Hybrid batched powered RK4: host events/limits, actual GPU planar forces.

The cooperative event algorithm mirrors powered_planar.advance_powered while
reusing its state packing, axle reaction, electrical limits and work contracts.
Each yielded stage is batched on the explicitly selected FP64 GPU. No thread,
controller tick, hidden time advancement or CPU force fallback is introduced.
This is a plant interval backend; tournament scheduling is a separate adapter.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil, isfinite
from time import perf_counter
from typing import Sequence

import numpy as np

from .actuation import (ActuationConfig, SINGLE_MOTOR_RWD_TOPOLOGY_ID,
    SPOOL_RWD_TOPOLOGY_ID, constrain_actuation, four_numbers)
from .conditions import PlanarEnvironment
from .planar import PlanarControls, PlanarVehicleConfig
from .planar_opencl import PlanarOpenCL, PlanarSample, unpack_evaluation
from .powered_planar import (PoweredState, BRAKE_STOP_SPEED_RAD_S,
    MAX_POWERED_WORK, MAX_ALLOCATED_POWERED_WORK, _BrakeStopTrial,
    _couple_locked_rear, _state, _vector)


@dataclass(frozen=True)
class PoweredInterval:
    config: PlanarVehicleConfig
    actuation: ActuationConfig
    state: PoweredState
    command_nm: tuple
    steering: tuple
    brakes: tuple
    available: tuple
    timestep_s: float
    environment: PlanarEnvironment = PlanarEnvironment()
    driver_proxy_n: float = 0.0
    maximum_work: int = MAX_POWERED_WORK
    wheel_radii_m: tuple | None = None


def _evaluate(request, state, horizon):
    c=request
    if c.actuation.topology_id in (SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID):
        command=four_numbers(c.command_nm,'single-motor command')
        if command[0]!=0 or command[1]!=0 or command[2]!=command[3]:
            raise ValueError('single-motor command requires zero front and equal rear torques')
    electrical=constrain_actuation(c.actuation,state.actuator_memory_nm,
        state.plant.wheel_speeds_rad_s,state.pack_energy_j,horizon,c.available)
    sample=PlanarSample(c.config,state.plant,PlanarControls(
        steering_angles_rad=c.steering,drive_torques_nm=electrical.wheel_torques_nm,
        brake_torques_nm=c.brakes,wheel_radii_m=c.wheel_radii_m),c.environment)
    values=yield sample
    if values[28]!=0:
        raise ValueError('GPU powered stage queried outside valid road domain')
    if c.actuation.topology_id==SPOOL_RWD_TOPOLOGY_ID:
        physical=unpack_evaluation(sample,np.asarray(values))
        physical=_couple_locked_rear(c.config,state,physical,electrical.wheel_torques_nm,
            c.brakes,c.wheel_radii_m or (c.config.wheel_radius_m,)*4)
        d=physical.derivative
        derivative=(d.x_dot_mps,d.y_dot_mps,d.heading_dot_rad_s,d.u_dot_mps2,d.v_dot_mps2,
            d.yaw_rate_dot_rad_s2,*d.wheel_accelerations_rad_s2)
    else:
        # Avoid constructing 4 wheel objects and 89 named fields at every RK
        # stage. The CPU shared shaft helper alone needs the typed object.
        derivative=tuple(values[:10])
    slew=c.actuation.actuator_slew_nm_per_s/(2 if c.actuation.topology_id in
        (SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID) else 1)
    memory=tuple(max(-slew,min(slew,(command-value)/c.actuation.actuator_time_constant_s))
        for command,value in zip(c.command_nm,state.actuator_memory_nm,strict=True))
    contact=sum(values[36+15*i] for i in range(4))
    result=(*derivative,*memory,
        -electrical.pack_power_w,electrical.wheel_power_w,electrical.conversion_loss_w,
        values[26],values[18],values[19],
        c.driver_proxy_n,contact,abs(c.driver_proxy_n-contact))
    if not all(isfinite(v) for v in result):
        raise ValueError('GPU powered derivative exceeds finite numerical domain')
    return result


def _trial(request,state,h):
    value=_vector(state)
    def check(values):
        for i,omega in enumerate(values[6:10]):
            if omega<0:
                if request.brakes[i]>0 or (request.actuation.topology_id==SPOOL_RWD_TOPOLOGY_ID
                    and i in (2,3) and (request.brakes[2]>0 or request.brakes[3]>0)):
                    raise _BrakeStopTrial()
                raise ValueError('reverse wheel motion is outside the powered domain')
    def derivative(values):
        check(values)
        return (yield from _evaluate(request,_state(values),h))
    def shifted(rate,scale):
        return tuple(x+scale*dx for x,dx in zip(value,rate,strict=True))
    k1=yield from derivative(value)
    k2=yield from derivative(shifted(k1,h/2))
    k3=yield from derivative(shifted(k2,h/2))
    k4=yield from derivative(shifted(k3,h))
    final=tuple(x+h/6*(a+2*b+2*c+d) for x,a,b,c,d in zip(value,k1,k2,k3,k4,strict=True))
    check(final)
    return _state(final)


def _advance(request):
    c=request
    if not isinstance(c,PoweredInterval):raise TypeError('Expected PoweredInterval')
    for name in ('command_nm','steering','brakes'):four_numbers(getattr(c,name),name)
    if not isfinite(c.timestep_s) or not 0<c.timestep_s<=.01:
        raise ValueError('powered plant step must be in (0, 0.01] s')
    if not isfinite(c.driver_proxy_n):raise ValueError('driver proxy must be finite')
    if type(c.maximum_work) is not int or not 1<=c.maximum_work<=MAX_ALLOCATED_POWERED_WORK:
        raise ValueError('powered work allocation must be an integer in [1, 200000]')
    if c.wheel_radii_m is not None:PlanarControls(wheel_radii_m=c.wheel_radii_m)
    step_config=replace(c.config,wheel_radius_m=max(c.wheel_radii_m)) if c.wheel_radii_m else c.config
    limit=min(step_config.integration_step_limit_s,c.actuation.actuator_time_constant_s/4)
    count=ceil(c.timestep_s/limit)
    if count>50000:raise ValueError('powered integration exceeds the work budget')
    h=c.timestep_s/count;state=c.state;trials=state.integration_trials
    for _ in range(count):
        remaining=h
        while remaining>0:
            rate=yield from _evaluate(c,state,remaining)
            stops=[i for i,omega in enumerate(state.plant.wheel_speeds_rad_s)
                if 0<omega<=BRAKE_STOP_SPEED_RAD_S and c.brakes[i]>0 and rate[6+i]<0]
            if c.actuation.topology_id==SPOOL_RWD_TOPOLOGY_ID and any(i in stops for i in (2,3)):
                stops=sorted(set(stops)|{2,3})
            if stops:
                wheels=list(state.plant.wheel_speeds_rad_s)
                loss=.5*c.config.wheel_inertia_kgm2*sum(wheels[i]**2 for i in stops)
                for i in stops:wheels[i]=0.
                state=replace(state,plant=replace(state.plant,wheel_speeds_rad_s=four_numbers(wheels,'stopped wheels')),
                    wheel_stop_dissipation_j=state.wheel_stop_dissipation_j+loss,
                    wheel_stop_events=state.wheel_stop_events+len(stops))
                if trials+state.wheel_stop_events>c.maximum_work:
                    raise ValueError('powered integration exceeds the actual work budget')
                continue
            trial_h=min([remaining]+[.25*omega/-rate[6+i]
                for i,omega in enumerate(state.plant.wheel_speeds_rad_s)
                if omega>0 and c.brakes[i]>0 and rate[6+i]<0])
            while True:
                trials+=1
                if trials+state.wheel_stop_events>c.maximum_work:
                    raise ValueError('powered integration exceeds the actual work budget')
                try:
                    candidate=yield from _trial(c,state,trial_h)
                    break
                except _BrakeStopTrial:
                    trial_h/=2
                    if remaining-trial_h==remaining:
                        raise ValueError('brake stop exceeds supported temporal resolution') from None
            state=replace(candidate,integration_substeps=state.integration_substeps+1,
                integration_trials=trials,wheel_stop_events=state.wheel_stop_events,
                wheel_stop_dissipation_j=state.wheel_stop_dissipation_j)
            remaining-=trial_h
            if not 0<=state.pack_energy_j<=c.actuation.pack_capacity_j:
                raise ValueError('pack energy crossed physical bounds; integration rejected')
    return state


def advance_powered_batch(backend: PlanarOpenCL, requests: Sequence[PoweredInterval]):
    """Advance up to 256 independent held-command lanes; all-or-error semantics.

    Adaptive lanes may take different stage counts. Finished lanes are removed;
    active requests retain stable identity. Every numerical force batch uses
    the selected GPU, including single-lane tails. No CPU fallback exists.
    """
    if not 1<=len(requests)<=256:raise ValueError('Require 1..256 powered lanes')
    started=perf_counter();active={};results=[None]*len(requests);launches=0;device_s=0.;rows=0
    try:
        for i,request in enumerate(requests):
            generator=_advance(request)
            active[i]=(generator,next(generator))
        while active:
            identities=list(active)
            physical,evidence=backend.evaluate([active[i][1] for i in identities])
            launches+=1;rows+=len(identities);device_s+=evidence['device_kernel_s']
            for i,evaluation in zip(identities,physical,strict=True):
                generator=active[i][0]
                try:active[i]=(generator,generator.send(evaluation.tolist()))
                except StopIteration as done:
                    results[i]=done.value
                    del active[i]
    finally:
        for generator,_ in active.values():generator.close()
    return results,{'backend':'Hybrid OpenCL GPU FP64 forces / CPU events and limits',
        'device':backend.runtime.device.name,'cpu_force_fallback':False,
        'kernel_launches':launches,'force_rows':rows,'device_kernel_s':device_s,
        'total_interval_batch_s':perf_counter()-started,'lanes':len(requests),
        'scope':'Powered held-command plant intervals; controller/course scheduling not included'}
