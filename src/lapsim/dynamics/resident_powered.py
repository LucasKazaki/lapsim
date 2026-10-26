"""Explicit device-resident powered state with checked held-command updates.

Supported road: uniform flat grip, arbitrary uniform wind/drag. Patches/domains
are rejected rather than sampled once and incorrectly frozen across RK stages.
No CPU physics fallback. Host controller/driver scheduling remains separate.
"""
from __future__ import annotations

import ctypes as ct
from dataclasses import replace
from math import isfinite
from time import perf_counter

import numpy as np

from lapsim.backends.opencl_runtime import OpenCLKernel,OpenCLError,_check
from .actuation import (TOPOLOGY_ID,AWD_TOPOLOGY_ID,SINGLE_MOTOR_RWD_TOPOLOGY_ID,
    SPOOL_RWD_TOPOLOGY_ID,four_numbers)
from .planar import PlanarControls
from .planar_opencl import PlanarSample,pack_samples
from .powered_opencl import PoweredInterval
from .powered_planar import MAX_ALLOCATED_POWERED_WORK,_vector,_state
from .resident_powered_kernel import RESIDENT_KERNEL

ACTUATION_FIELDS=('gear_ratio','gear_efficiency','motor_conversion_efficiency','inverter_efficiency',
    'torque_constant_nm_per_a','motor_current_limit_a','inverter_current_limit_a','motor_peak_torque_nm',
    'motor_base_speed_rad_s','motor_maximum_speed_rad_s','equivalent_copper_resistance_ohm','pack_voltage_v',
    'pack_capacity_j','pack_discharge_current_limit_a','pack_charge_current_limit_a','pack_discharge_power_limit_w',
    'pack_charge_power_limit_w','actuator_time_constant_s','actuator_slew_nm_per_s')
TOPOLOGIES={TOPOLOGY_ID:0,AWD_TOPOLOGY_ID:1,SINGLE_MOTOR_RWD_TOPOLOGY_ID:2,SPOOL_RWD_TOPOLOGY_ID:3}
ERRORS={1:'reverse wheel domain',2:'cumulative powered work exceeded',3:'pack energy bounds',
    4:'brake-stop temporal resolution',5:'nonfinite powered state',6:'locked axle speed mismatch',
    7:'GPU watchdog work ceiling (2048 trials per interval)',8:'unsupported topology/input'}


def _validate_commands(request,command,steering,brakes):
    command=four_numbers(command,'held command')
    PlanarControls(steering_angles_rad=four_numbers(steering,'steering'),
        drive_torques_nm=command,brake_torques_nm=four_numbers(brakes,'brakes'))
    if request.actuation.topology_id!=AWD_TOPOLOGY_ID and (command[0]!=0 or command[1]!=0):
        raise ValueError('Front command unavailable in RWD')
    if request.actuation.topology_id in (SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID) and command[2]!=command[3]:
        raise ValueError('Single motor requires equal rear command')


def _parameters(requests):
    samples=[];parameters=np.empty((len(requests),89),dtype=np.float64)
    for index,r in enumerate(requests):
        if not isinstance(r,PoweredInterval):raise TypeError('Expected PoweredInterval')
        if r.environment.road.patches or r.environment.road.valid_domain is not None:
            raise ValueError('Resident GPU backend supports uniform road only; no CPU fallback')
        if not isfinite(r.timestep_s) or not 0<r.timestep_s<=.01:raise ValueError('Require (0, .01] s interval')
        if type(r.maximum_work) is not int or not 1<=r.maximum_work<=MAX_ALLOCATED_POWERED_WORK:
            raise ValueError('Invalid cumulative powered work allocation')
        if not isfinite(r.driver_proxy_n):raise ValueError('Driver proxy must be finite')
        if len(r.available)!=4 or any(type(v) is not bool for v in r.available):raise ValueError('Require four availability booleans')
        if r.actuation.topology_id!=AWD_TOPOLOGY_ID and (r.available[0] or r.available[1]):
            raise ValueError('Front actuators unavailable in RWD')
        _validate_commands(r,r.command_nm,r.steering,r.brakes)
        _validate_commands(r,r.state.actuator_memory_nm,r.steering,r.brakes)
        if r.actuation.topology_id==SPOOL_RWD_TOPOLOGY_ID and r.state.plant.wheel_speeds_rad_s[2]!=r.state.plant.wheel_speeds_rad_s[3]:
            raise ValueError('Locked axle requires equal rear angular velocity')
        if min(r.state.plant.wheel_speeds_rad_s)<0:raise ValueError('Negative wheel speed unsupported')
        if not 0<=r.state.pack_energy_j<=r.actuation.pack_capacity_j:raise ValueError('Invalid initial pack energy')
        samples.append(PlanarSample(r.config,r.state.plant,PlanarControls(
            steering_angles_rad=r.steering,drive_torques_nm=r.command_nm,
            brake_torques_nm=r.brakes,wheel_radii_m=r.wheel_radii_m),r.environment))
        step_config=replace(r.config,wheel_radius_m=max(r.wheel_radii_m)) if r.wheel_radii_m else r.config
        parameters[index,60:]=(*(getattr(r.actuation,name) for name in ACTUATION_FIELDS),
            TOPOLOGIES[r.actuation.topology_id],*r.available,r.timestep_s,r.maximum_work,
            r.driver_proxy_n,step_config.integration_step_limit_s,1.)
    parameters[:,:60]=pack_samples(samples)
    if not np.isfinite(parameters).all():raise ValueError('Nonfinite resident parameters')
    return parameters


class ResidentPowered:
    """Long-lived device state. One launch owns every RK/event stage per lane."""
    def __init__(self,requests,*,device_name):
        if not 1<=len(requests)<=256:raise ValueError('Require 1..256 resident lanes')
        started=perf_counter()
        self.requests=tuple(requests);self.parameters=_parameters(requests)
        self.runtime=None;self.parameter_buffer=self.state_buffer=None;self.faulted=False
        self.host=np.asarray([(*_vector(r.state),r.state.wheel_stop_dissipation_j,
            r.state.integration_substeps,r.state.integration_trials,r.state.wheel_stop_events,0.) for r in requests],dtype=np.float64)
        try:
            self.runtime=OpenCLKernel(RESIDENT_KERNEL,'powered_interval',device_name=device_name)
            error=ct.c_int();api=self.runtime.api
            self.parameter_buffer=api.clCreateBuffer(self.runtime.context,4|32,self.parameters.nbytes,
                self.parameters.ctypes.data_as(ct.c_void_p),ct.byref(error))
            _check(error.value,'allocate resident parameters')
            self.state_buffer=api.clCreateBuffer(self.runtime.context,1|32,self.host.nbytes,
                self.host.ctypes.data_as(ct.c_void_p),ct.byref(error))
            _check(error.value,'allocate and initialize resident state')
            for index,handle in enumerate((self.parameter_buffer,self.state_buffer)):
                value=ct.c_void_p(handle)
                _check(api.clSetKernelArg(self.runtime.kernel,index,ct.sizeof(value),ct.byref(value)),'bind resident buffer')
            count=ct.c_uint(len(requests))
            _check(api.clSetKernelArg(self.runtime.kernel,2,ct.sizeof(count),ct.byref(count)),'bind resident lane count')
        except BaseException:
            self.close();raise
        self.initialization_s=perf_counter()-started

    def __enter__(self):return self
    def __exit__(self,*_):self.close()

    def close(self):
        if self.runtime:
            for name in ('state_buffer','parameter_buffer'):
                handle=getattr(self,name,None)
                if handle:self.runtime.api.clReleaseMemObject(handle);setattr(self,name,None)
            self.runtime.close()

    def step(self,*,commands=None,steering=None,brakes=None,active=None):
        if not self.runtime or not self.runtime.kernel:raise OpenCLError('Resident GPU context is closed')
        if self.faulted:raise OpenCLError('Resident GPU lane fault is latched; create an explicit new session to reset')
        started=perf_counter();count=len(self.requests)
        updates=[]
        for values,start,label in ((commands,21,'commands'),(steering,17,'steering'),(brakes,25,'brakes')):
            if values is not None:
                if len(values)!=count:raise ValueError('Lane count changed for '+label)
                updates.append((start,[four_numbers(v,label) for v in values]))
        candidate=self.parameters.copy()
        if active is not None:
            if len(active)!=count or any(type(v) is not bool for v in active):raise ValueError('Require one active boolean per lane')
            candidate[:,88]=active
        for start,values in updates:candidate[:,start:start+4]=values
        for index,r in enumerate(self.requests):
            _validate_commands(r,tuple(candidate[index,21:25]),tuple(candidate[index,17:21]),tuple(candidate[index,25:29]))
        self.parameters=candidate
        api=self.runtime.api;event=ct.c_void_p();size=ct.c_size_t(count)
        try:
            _check(api.clEnqueueWriteBuffer(self.runtime.queue,self.parameter_buffer,1,0,self.parameters.nbytes,
                self.parameters.ctypes.data_as(ct.c_void_p),0,None,None),'update resident held controls')
            _check(api.clEnqueueNDRangeKernel(self.runtime.queue,self.runtime.kernel,1,None,ct.byref(size),None,
                0,None,ct.byref(event)),'launch resident powered intervals')
            _check(api.clEnqueueReadBuffer(self.runtime.queue,self.state_buffer,1,0,self.host.nbytes,
                self.host.ctypes.data_as(ct.c_void_p),0,None,None),'read resident interval boundaries')
            beginning,ending=ct.c_ulonglong(),ct.c_ulonglong()
            _check(api.clGetEventProfilingInfo(event,0x1282,8,ct.byref(beginning),None),'profile resident start')
            _check(api.clGetEventProfilingInfo(event,0x1283,8,ct.byref(ending),None),'profile resident end')
        finally:
            api.clFinish(self.runtime.queue)
            if event.value:api.clReleaseEvent(event)
        failures={i:ERRORS.get(int(row[27]),'unknown GPU error') for i,row in enumerate(self.host) if row[27]!=0}
        if failures or not np.isfinite(self.host).all():
            self.faulted=True
            raise OpenCLError(f'Resident powered interval rejected; lanes={failures}; no CPU fallback')
        results=[replace(_state(tuple(map(float,row[:23]))),wheel_stop_dissipation_j=float(row[23]),
            integration_substeps=int(row[24]),integration_trials=int(row[25]),wheel_stop_events=int(row[26])) for row in self.host]
        return results,{'backend':'Resident OpenCL GPU FP64 powered RK/events/limits',
            'device':self.runtime.device.name,'cpu_fallback':False,'lanes':count,'kernel_launches':1,
            'device_kernel_s':(ending.value-beginning.value)*1e-9,'total_step_s':perf_counter()-started,
            'state_initializations':1,'state_uploaded_this_step':False,'kernel_sha256':self.runtime.source_sha256,
            'scope':'Held-command powered intervals; driver/controller scheduling on host; uniform road only'}
