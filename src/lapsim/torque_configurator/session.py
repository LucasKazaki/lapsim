"""One deterministic session around the existing imported controller owners."""
from dataclasses import asdict,replace
import json
from pathlib import Path

from lapsim.dynamics.actuation import constrain_actuation,SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID,TOPOLOGY_ID
from lapsim.experiments.controller_backend import PythonController
from .profile import VehicleProfile, keys, number, require,drive_availability
from .trace_mode import trace_mode

EXPERIMENTAL_FRAME_FIELDS=('u_mps','v_mps','yaw_rate_rad_s','actuator_memory_nm','regen_available','motor_temperature_c','friction_fallback')
FRAME_FIELDS=('now_ms','timestamp_ms','accelerator_fraction','brake_fraction','steering_rad',
              'wheel_speeds_rad_s','pack_energy_j','valid','enabled','restart_requested','wheel_available')


class ControlSession:
    def __init__(self,profile):
        require(type(profile) is VehicleProfile,'A validated VehicleProfile is required')
        self.profile=profile
        self.reset()

    def reset(self):
        """Start a new simulated session; no restart signal to physical hardware."""
        if hasattr(self,'backend'):self.backend.close()
        profile=self.profile
        self.experimental=None
        if profile.to_dict()['schema']=='lapsim.torque-profile.v2':
            from .policy import PolicyRuntime
            self.experimental=PolicyRuntime(profile)
        self.backend=PythonController(profile.policy['period_ms'],profile.policy['maximum_age_ms'])
        if profile.actuation.topology_id!=TOPOLOGY_ID:
            # New explicit adapters bound the guard by the declared physical
            # rate while preserving the existing reference ceiling/lag owner.
            channels=2 if profile.actuation.topology_id in (SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID) else 1
            guard=self.backend.config.guard
            self.backend.config=replace(self.backend.config,guard=replace(guard,
                max_rise_nm_per_s=min(guard.max_rise_nm_per_s,profile.actuation.actuator_slew_nm_per_s/channels)))

    def step(self,frame):
        keys(frame,FRAME_FIELDS+(EXPERIMENTAL_FRAME_FIELDS if self.experimental else ()),'frame')
        if self.experimental:
            for key,lo,hi in [('u_mps',0.,80.),('v_mps',-40.,40.),('yaw_rate_rad_s',-3.,3.),('motor_temperature_c',-20.,150.)]:number(frame[key],key,lo,hi)
            for key in ('regen_available','friction_fallback'):require(type(frame[key]) is bool,key+' must be Boolean')
            memory=frame['actuator_memory_nm']
            require(isinstance(memory,(tuple,list)) and len(memory)==4,'Four actuator-memory torques required')
            for v in memory:number(v,'actuator_memory_nm',-1000.,1000.)
        for key in ('now_ms','timestamp_ms'):
            require(type(frame[key]) is int and 0<=frame[key]<=86_400_000,key+' must be nonnegative integer milliseconds')
        for key in ('valid','enabled','restart_requested'):require(type(frame[key]) is bool,key+' must be Boolean')
        for key in ('accelerator_fraction','brake_fraction'):number(frame[key],key,0.,1.)
        number(frame['steering_rad'],'steering_rad',-.4,.4)
        number(frame['pack_energy_j'],'pack_energy_j',0.,self.profile.actuation.pack_capacity_j)
        speeds=frame['wheel_speeds_rad_s'];available=frame['wheel_available']
        require(isinstance(speeds,(tuple,list)) and len(speeds)==4,'Four FL,FR,RL,RR wheel speeds are required')
        for v in speeds:number(v,'wheel_speed_rad_s',0.,2000.)
        require(isinstance(available,(tuple,list)) and len(available)==4 and all(type(v) is bool for v in available),'Four Boolean wheel availability flags are required')
        powered=drive_availability(self.profile)
        require(all(not enabled or allowed for enabled,allowed in zip(available,powered)),
                'Front actuators are not part of this RWD architecture')
        pack=self.profile.actuation
        if pack.topology_id==SPOOL_RWD_TOPOLOGY_ID:require(speeds[2]==speeds[3],'Locked axle requires equal rear angular velocities')
        nominal=min(pack.motor_peak_torque_nm,pack.torque_constant_nm_per_a*min(pack.motor_current_limit_a,pack.inverter_current_limit_a))*pack.gear_ratio*pack.gear_efficiency
        if pack.topology_id in (SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID):
            nominal/=2
            shared=available[2] and available[3]
            available=(False,False,shared,shared)
        limits=tuple(nominal if enabled else 0. for enabled in powered)
        sample=self.backend.sample(frame['now_ms'],frame['timestamp_ms'],
            frame['accelerator_fraction']*self.profile.policy['maximum_drive_request_nm'],limits,tuple(available),
            frame['accelerator_fraction'],frame['brake_fraction']>0,frame['valid'],frame['enabled'],frame['restart_requested'])
        result=self.backend.step(sample)
        if self.experimental:
            policy=self.experimental.decide({**frame,'wheel_available':list(available)},result['command_allowed'])
            controller={k:result[k] for k in ('sequence','now_ms','fault','clock_fault','command_allowed','command_reason')}
            controller.update(allocator={'wheel_torque_nm':list(policy['proposed_nm']),'status':'EXPERIMENTAL_SIGNED'},
                command_nm=list(policy['command_nm']),mode=policy['mode'],mode_code=policy['mode_code'],
                guard={'status':'SIGNED_SIMULATION_POLICY','output_nm':list(policy['command_nm']),'pedal_overlap_latched':result['guard']['pedal_overlap_latched']},
                reference_gate={'allocator_status':result['allocator']['status'],'guard_status':result['guard']['status'],'command_nm':result['command_nm']})
            return {'controller':controller,'limited':policy['limited'],'friction_nm':list(policy['friction_nm']),
                'brake_shortfall_nm':policy['brake_shortfall_nm'],'raw_regen_nm':policy['raw_regen_nm'],
                'profile_sha256':self.profile.sha256,'scope':policy['scope']}
        limited=constrain_actuation(pack,tuple(result['command_nm']),tuple(speeds),frame['pack_energy_j'],.01,tuple(available))
        return {'controller':result,'limited':asdict(limited),'profile_sha256':self.profile.sha256,
                'scope':'simulation-only propulsive baseline; actuator response belongs to the plant'}

    def state_snapshot(self):
        value={'guard':asdict(self.backend.guard_state),'fault':asdict(self.backend.fault_state),
                'clock':asdict(self.backend.clock_state),'sequence':self.backend.sequence}
        if self.experimental:value['experimental']=self.experimental.state_snapshot()
        return value

    def close(self):self.backend.close()


def replay(profile,frames,*,full_lap=False,ten_lap=False):
    mode=trace_mode(full_lap=full_lap,ten_lap=ten_lap)
    require(isinstance(frames,list) and 1<=len(frames)<=mode.maximum_frames,f'A bounded trace of 1-{mode.maximum_frames} frames is required')
    if mode.maximum_clock_ms is not None:
        require(all(type(f) is dict and type(f.get('now_ms')) is int and 0<=f['now_ms']<=mode.maximum_clock_ms for f in frames),
                f'Full-lap trace clock exceeds {mode.maximum_clock_ms} integer ms')
    session=ControlSession(profile)
    try:return [session.step(frame) for frame in frames]
    finally:session.close()


def read_trace(profile,path,*,full_lap=False,ten_lap=False):
    mode=trace_mode(full_lap=full_lap,ten_lap=ten_lap)
    with Path(path).open('rb') as stream:raw=stream.read(mode.trace_bytes+1)
    require(len(raw)<=mode.trace_bytes,f'Trace exceeds {mode.trace_bytes//1_000_000} MB')
    trace=json.loads(raw);keys(trace,('schema','profile_sha256','frames'),'trace')
    require(trace['schema']==mode.schema('trace') and trace['profile_sha256']==profile.sha256,'Trace schema/profile identity mismatch')
    require(isinstance(trace['frames'],list) and 1<=len(trace['frames'])<=mode.maximum_frames,'Trace frame count exceeds its version bound')
    return trace['frames']
