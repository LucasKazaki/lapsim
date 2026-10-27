"""Strict, complete SI snapshots; architecture is not a numeric parameter."""
from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import re

from lapsim.dynamics.actuation import ActuationConfig, TOPOLOGY_ID, SINGLE_MOTOR_RWD_TOPOLOGY_ID, AWD_TOPOLOGY_ID, SPOOL_RWD_TOPOLOGY_ID
from lapsim.dynamics.planar import PlanarVehicleConfig
from lapsim.resources import repository_root

SCHEMA='lapsim.torque-profile.v1'
UNITS={'length':'m','mass':'kg','time':'s','timestamp':'ms','torque':'N*m',
       'angle':'rad','angular_speed':'rad/s','energy':'J','power':'W','current':'A','voltage':'V'}
POLICY={'period_ms':10,'maximum_age_ms':50,'maximum_drive_request_nm':400.,
        'maximum_friction_brake_nm':40.,'initial_speed_mps':5.,'initial_soc':.7}
PROFILE_FILES={TOPOLOGY_ID:'synthetic-two-rear-v1.json',
               SINGLE_MOTOR_RWD_TOPOLOGY_ID:'synthetic-single-rear-v1.json',
               AWD_TOPOLOGY_ID:'synthetic-four-awd-v1.json',SPOOL_RWD_TOPOLOGY_ID:'synthetic-spool-v1.json'}


def drive_availability(profile: "VehicleProfile") -> tuple[bool, bool, bool, bool]:
    if profile.actuation.topology_id == AWD_TOPOLOGY_ID:
        return (True, True, True, True)
    return (False, False, True, True)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def require(condition,message):
    if not condition:raise ValueError(message)


def number(value,name,low,high):
    require(type(value) in (int,float) and low<=value<=high and isfinite(value),
            f'{name} must be a finite number in [{low}, {high}]')


def keys(value,expected,name):
    require(type(value) is dict and set(value)==set(expected),f'{name}: complete known fields are required; unknown fields are rejected')


@dataclass(frozen=True,slots=True)
class VehicleProfile:
    payload_json:str
    vehicle:PlanarVehicleConfig
    actuation:ActuationConfig

    @property
    def policy(self):return self.to_dict()['policy']
    @property
    def sha256(self):return sha256(self.payload_json.encode()).hexdigest()
    def to_dict(self):return json.loads(self.payload_json)

    @classmethod
    def from_dict(cls,value):
        keys(value,('schema','profile_id','revision','evidence_status','provenance','units','architecture',
                    'controller','vehicle','actuation','policy'),'profile')
        require(value['schema'] in (SCHEMA,'lapsim.torque-profile.v2'),'Unsupported profile schema/version')
        require(isinstance(value['profile_id'],str) and re.fullmatch(r'[a-z0-9_-]{1,64}',value['profile_id']), 'Invalid profile_id')
        require(type(value['revision']) is int and 1<=value['revision']<=1_000_000,'revision must be a positive integer')
        require(value['evidence_status']=='synthetic_unvalidated','Configurator profiles must be explicitly synthetic and unvalidated')
        require(isinstance(value['provenance'],str) and 1<=len(value['provenance'])<=1000,'Profile provenance is required')
        require(value['units']==UNITS,'Unsupported units; the v1 boundary requires the complete SI unit contract')
        require(isinstance(value['architecture'],str) and value['architecture'] in PROFILE_FILES,'Unsupported architecture: choose an explicit synthetic single-motor/open-differential RWD, two-rear-motor RWD spool RWD or four-independent-motor AWD profile')
        if value['schema']==SCHEMA:
            require(value['controller']=='equal_split_reference_v1','Unsupported controller; v1 uses the shared equal-split reference core')
            normalized_controller=value['controller']
        else:
            from .policy import PolicySpec
            normalized_controller=PolicySpec.from_dict(value['controller'],value['architecture']).to_dict()
        keys(value['vehicle'],[f.name for f in fields(PlanarVehicleConfig)],'vehicle')
        keys(value['actuation'],[f.name for f in fields(ActuationConfig)],'actuation')
        for name,item in value['vehicle'].items():number(item,'vehicle.'+name,1e-8,1e7)
        for name,item in value['actuation'].items():
            if name!='topology_id':number(item,'actuation.'+name,0. if name=='equivalent_copper_resistance_ohm' else 1e-8,1e9)
        require(value['actuation']['topology_id']==value['architecture'],'Actuator topology must match the selected architecture')
        car=PlanarVehicleConfig(**value['vehicle'])
        pack=ActuationConfig(**value['actuation'])
        number(car.mass_kg,'mass_kg',25.,2000.)
        number(car.wheel_radius_m,'wheel_radius_m',.05,1.)
        number(pack.pack_voltage_v,'pack_voltage_v',100.,600.)
        number(pack.pack_capacity_j,'pack_capacity_j',360_000.,360_000_000.)
        require(car.integration_step_limit_s>=1e-5,'Vehicle stiffness/inertia exceeds the bounded preview compute domain')
        keys(value['policy'],POLICY,'policy')
        policy=value['policy']
        require(type(policy['period_ms']) is int and policy['period_ms']==10,'v1 controller period is exactly 10 integer milliseconds')
        require(type(policy['maximum_age_ms']) is int and 10<=policy['maximum_age_ms']<=100,'maximum_age_ms must be an integer in [10,100]')
        number(policy['maximum_drive_request_nm'],'maximum_drive_request_nm',1.,1000.)
        number(policy['maximum_friction_brake_nm'],'maximum_friction_brake_nm',0.,80.)
        number(policy['initial_speed_mps'],'initial_speed_mps',0.,15.)
        number(policy['initial_soc'],'initial_soc',0.,1.)
        # JSON transports have one numeric type; browsers serialize 580.0 as
        # 580. Normalize physical numbers before identifying the snapshot.
        normalized=json.loads(canonical(value))
        normalized['controller']=normalized_controller
        normalized['vehicle']={k:float(v) for k,v in value['vehicle'].items()}
        normalized['actuation']={k:v if k=='topology_id' else float(v) for k,v in value['actuation'].items()}
        normalized['policy']={k:v if k in ('period_ms','maximum_age_ms') else float(v) for k,v in policy.items()}
        return cls(canonical(normalized),PlanarVehicleConfig(**normalized['vehicle']),ActuationConfig(**normalized['actuation']))


def load_profile(path):
    raw=Path(path).read_bytes()
    require(len(raw)<=65_536,'Profile exceeds 64 KiB')
    return VehicleProfile.from_dict(json.loads(raw))


def example_profile(architecture=TOPOLOGY_ID):
    require(isinstance(architecture,str) and architecture in PROFILE_FILES,'Unsupported architecture example')
    return load_profile(repository_root()/'configs/torque_profiles'/PROFILE_FILES[architecture])
