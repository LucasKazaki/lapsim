"""Composed simulation policies; one signed core for host replay and plant use.

The imported reference core still owns freshness/fault authority. This signed
policy and its command limiter are Python simulation code, not portable MCU C.
"""
from dataclasses import dataclass,asdict
from hashlib import sha256
from math import cos,sin,sqrt
from types import SimpleNamespace

STRUCTURES={'drive':('linear','square','sqrt'),'traction':('off','ratio','hysteresis'),
    'yaw':('off','p','pi'),'reserve':('off','on'),'pedal':('two_stage','proportional','adaptive'),
    'condition':('steady','corner_blend','energy_save'),'allocation':('equal','front_bias')}
PARAMETERS={'drive_scale':(.6,1.),'slip_target':(.035,.18),'yaw_kp':(0.,45.),'yaw_ki':(0.,15.),
    'regen_fraction':(0.,.95),'regen_region':(.1,.4),'hysteresis_release':(.3,.9),
    'corner_threshold_rad':(.03,.25),'soc_threshold':(.2,.9),'coast_fraction':(0.,.7),'front_bias':(.25,.75)}
DEFAULTS={'drive_scale':1.,'slip_target':.1,'yaw_kp':20.,'yaw_ki':3.,'regen_fraction':.65,
    'regen_region':.25,'hysteresis_release':.6,'corner_threshold_rad':.10,'soc_threshold':.75,
    'coast_fraction':.25,'front_bias':.5}
SCHEMA='lapsim.experimental-policy.v1'
MODE_CODES={'inhibited':0,'drive':1,'corner_blend':2,'energy_save':3,'slip_hold':4,'brake_stage_1':5,'brake_stage_2':6,'brake_proportional':7}


@dataclass(frozen=True)
class PolicySpec:
    payload_json:str
    topology:str

    @classmethod
    def from_dict(cls,value,topology):
        from .profile import keys,require,number,canonical
        from lapsim.dynamics.actuation import SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID,AWD_TOPOLOGY_ID
        keys(value,('schema','structure','parameters'),'experimental controller')
        require(value['schema']==SCHEMA,'Unsupported experimental policy schema')
        keys(value['structure'],STRUCTURES,'policy structure');keys(value['parameters'],PARAMETERS,'policy parameters')
        for key,options in STRUCTURES.items():require(value['structure'][key] in options,'Unknown policy '+key)
        for key,(lo,hi) in PARAMETERS.items():number(value['parameters'][key],key,lo,hi)
        if topology in (SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID):
            require(value['structure']['yaw']=='off','One shared motor cannot provide independent yaw authority')
        require(value['structure']['allocation']=='equal' or topology==AWD_TOPOLOGY_ID,'Front bias requires independent AWD')
        normalized={**value,'parameters':{k:float(v) for k,v in value['parameters'].items()}}
        return cls(canonical(normalized),topology)

    def to_dict(self):
        import json
        return json.loads(self.payload_json)

    @property
    def active_parameters(self):
        s=self.to_dict()['structure'];names=['drive_scale','regen_fraction']
        if s['pedal']!='proportional':names+=['regen_region']
        if s['traction']!='off' or s['condition']=='corner_blend':names+=['slip_target']
        if s['traction']=='hysteresis':names+=['hysteresis_release']
        if s['yaw']!='off':names+=['yaw_kp']
        if s['yaw']=='pi':names+=['yaw_ki']
        if s['condition']=='corner_blend':names+=['corner_threshold_rad']
        if s['condition']=='energy_save':names+=['soc_threshold','coast_fraction']
        if s['allocation']=='front_bias':names+=['front_bias']
        return tuple(names)

    @property
    def effective_identity(self):
        from .profile import canonical
        value=self.to_dict()
        return sha256(canonical({'topology':self.topology,'structure':value['structure'],
            'active_parameters':{k:value['parameters'][k] for k in self.active_parameters}}).encode()).hexdigest()


def experimental_profile(architecture):
    from .profile import example_profile,VehicleProfile
    from lapsim.dynamics.actuation import SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID
    value=example_profile(architecture).to_dict()
    value['schema']='lapsim.torque-profile.v2';value['profile_id']+='-experimental'
    value['provenance']+=' Explicit R11 synthetic soft-tire desktop fixture; not calibrated team data. Experimental signed Python controller is not the portable C baseline.'
    value['vehicle'].update(wheel_inertia_kgm2=.6,longitudinal_stiffness_n_per_slip=2500.,cornering_stiffness_n_per_rad=6000.)
    value['policy'].update(maximum_drive_request_nm=190.,maximum_friction_brake_nm=80.)
    value['controller']={'schema':SCHEMA,'structure':{'drive':'linear','traction':'ratio',
        'yaw':'off' if architecture in (SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID) else 'pi',
        'reserve':'on','pedal':'two_stage','condition':'steady','allocation':'equal'},'parameters':dict(DEFAULTS)}
    return VehicleProfile.from_dict(value)


class PolicyRuntime:
    def __init__(self,profile):
        self.profile=profile;self.spec=PolicySpec.from_dict(profile.to_dict()['controller'],profile.actuation.topology_id)
        self.integral=0.;self.slip_latched=False;self.previous=(0.,)*4;self.occupancy={}

    def state_snapshot(self):
        return {'integral':self.integral,'slip_latched':self.slip_latched,'previous_signed_command_nm':self.previous,
                'mode_occupancy':dict(self.occupancy),'effective_policy_sha256':self.spec.effective_identity}

    def decide(self,frame,allowed):
        from lapsim.dynamics.planar import PlanarState
        from lapsim.dynamics.powered_planar import PoweredState
        from lapsim.dynamics.actuation import constrain_actuation,SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID
        from lapsim.experiments.tournament_rollout import allocate,friction_blend,brake_request
        from .profile import drive_availability
        car,pack=self.profile.vehicle,self.profile.actuation
        value=self.spec.to_dict();s=value['structure'];params=dict(value['parameters'])
        p=PlanarState(u_mps=frame['u_mps'],v_mps=frame['v_mps'],yaw_rate_rad_s=frame['yaw_rate_rad_s'],
                      wheel_speeds_rad_s=tuple(frame['wheel_speeds_rad_s']))
        state=PoweredState(p,tuple(frame['actuator_memory_nm']),frame['pack_energy_j'])
        available=tuple(frame['wheel_available']);steer=frame['steering_rad'];speed=p.u_mps
        soc=frame['pack_energy_j']/pack.pack_capacity_j
        corner=s['condition']=='corner_blend' and abs(steer)>=params['corner_threshold_rad'] and speed>3.
        saving=s['condition']=='energy_save' and soc<params['soc_threshold']
        fraction=frame['accelerator_fraction']
        if s['drive']=='square':fraction*=fraction
        elif s['drive']=='sqrt':fraction=sqrt(fraction)
        if saving:fraction*=1-params['coast_fraction']
        slips=[]
        for i,(x,y) in enumerate(car.wheel_positions_m):
            angle=steer if i<2 else 0.
            local=cos(angle)*(p.u_mps-p.yaw_rate_rad_s*y)+sin(angle)*(p.v_mps+p.yaw_rate_rad_s*x)
            slips.append((car.wheel_radius_m*p.wheel_speeds_rad_s[i]-local)/max(abs(local),car.low_speed_regularization_mps))
        if s['traction']=='hysteresis':
            peak=max(slips[i] for i,a in enumerate(available) if a) if any(available) else 0.
            if peak>params['slip_target']:self.slip_latched=True
            if peak<params['slip_target']*params['hysteresis_release']:self.slip_latched=False
            if self.slip_latched:fraction*=.35
        if s['yaw']!='pi':params['yaw_ki']=0.
        regen_scale=min(1.,max(0.,(1-soc)/.2))*min(1.,max(0.,speed/8.)) if s['pedal']=='adaptive' else 1.
        control=SimpleNamespace(**params,philosophy='composed',slip_control=s['traction']=='ratio' or corner,
            yaw_control=s['yaw']!='off' and (s['condition']!='corner_blend' or corner),
            reserve_control=s['reserve']=='on' or corner,pedal_mode=s['pedal'],regen_scale=regen_scale,
            brake_capacity_nm=4*self.profile.policy['maximum_friction_brake_nm'],
            allocation_front_bias=params['front_bias'] if s['allocation']=='front_bias' else .5)
        case=SimpleNamespace(regen_available=frame['regen_available'],pack_voltage_v=pack.pack_voltage_v,
            motor_temperature_c=frame['motor_temperature_c'],friction_fallback=frame['friction_fallback'])
        requested,proposed,_,_,self.integral,_,raw=allocate(control,state,None,steer,
            fraction*self.profile.policy['maximum_drive_request_nm']/2,
            frame['brake_fraction']*80.,self.integral,car,pack,case)
        shared=pack.topology_id in (SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID)
        rise=min(8000.,pack.actuator_slew_nm_per_s/(2 if shared else 1))*.01
        guarded=tuple(max(old-rise,min(old+rise,new)) if a else 0. for old,new,a in zip(self.previous,proposed,available))
        if frame['brake_fraction']>0:guarded=tuple(min(0.,v) for v in guarded)
        if not allowed:
            guarded=(0.,)*4;self.integral=0.;self.slip_latched=False
        limited=constrain_actuation(pack,guarded,p.wheel_speeds_rad_s,state.pack_energy_j,.01,available)
        actual=constrain_actuation(pack,state.actuator_memory_nm,p.wheel_speeds_rad_s,state.pack_energy_j,.01,available)
        total,raw=brake_request(frame['brake_fraction'],control)
        brakes,shortfall=friction_blend(total,raw,sum(max(0.,-v) for v in actual.wheel_torques_nm),
            sum(max(0.,v) for v in actual.wheel_torques_nm) if total>0 else 0.,fallback=frame['friction_fallback'],
            capacity_nm=self.profile.policy['maximum_friction_brake_nm'],shares=(.25,)*4) if total>0 else ((0.,)*4,0.)
        mode='inhibited' if not allowed else 'brake_proportional' if frame['brake_fraction']>0 and s['pedal']=='proportional' else 'brake_stage_1' if 0<frame['brake_fraction']<=params['regen_region'] else 'brake_stage_2' if frame['brake_fraction']>0 else 'corner_blend' if corner else 'energy_save' if saving else 'slip_hold' if self.slip_latched else 'drive'
        self.occupancy[mode]=self.occupancy.get(mode,0)+1;self.previous=guarded
        return {'requested_nm':requested,'proposed_nm':proposed,'command_nm':guarded,'limited':asdict(limited),
            'friction_nm':brakes,'brake_shortfall_nm':shortfall,'raw_regen_nm':raw,'mode':mode,'mode_code':MODE_CODES[mode],
            'scope':'shared simulation-only signed policy; reference freshness/fault authority; plant owns physical response'}
