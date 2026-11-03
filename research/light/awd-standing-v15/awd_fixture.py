"""Explicit synthetic four-motor AWD light profile; no fallback or runtime I/O."""
from dataclasses import dataclass,replace,asdict
from hashlib import sha256
import json
from math import isfinite
from lapsim.dynamics.actuation import ActuationConfig,AWD_TOPOLOGY_ID
from lapsim.dynamics.conditions import PlanarEnvironment,PlanarRoad
from lapsim.dynamics.planar import PlanarControls,PlanarVehicleConfig
from lapsim.dynamics.torque_light_drs import AutomaticDrsPolicy
from lapsim.dynamics.torque_light_forces import AeroAreas,LightForceConfig
from lapsim.dynamics.torque_light_powered import LightPoweredConfig
from lapsim.dynamics.torque_light_thermal import LumpedTireThermalConfig
from lapsim.optimization.pose_driver import PoseDriverSettings
from lapsim.experiments.tournament_rollout import _stadium_course

PROFILE_ID='synthetic_four_independent_awd_light_v1'
PROFILE_CONFIGURATION_SHA256='782eaf45732856e77c77affa25d79b0aefbd7d62ebee8ce37e7835c7a52dfb9f'
AVAILABLE=(True,True,True,True)
STEERING_MODEL='parallel_front_v1'
TOTAL_DRIVE_MAX_NM=190.
PROVENANCE='Synthetic four-independent-motor AWD;unmeasured tire/aero/thermal/motor/pack defaults;no physical-car calibration'

def require(value,message):
    if not value:raise ValueError(message)
def four(values,name):
    require(type(values) in (tuple,list) and len(values)==4 and
            all(type(v) in (int,float) and isfinite(v) for v in values),'Four finite '+name)
    return tuple(values)
def steering(values):
    angles=four(values,'wheel steer rad')
    require(all(abs(v)<=.4 for v in angles) and angles[0]==angles[1] and angles[2:]==(0.,0.),
            'Explicit parallel front steering required;no silent Ackermann/rear-steer approximation')
    return angles
def validate_driver_command(command):
    require(type(command) is PlanarControls,'Typed common driver controls')
    steering(command.steering_angles_rad)
    drive=four(command.drive_torques_nm,'AWD baseline wheel Nm');brakes=four(command.brake_torques_nm,'brake Nm')
    require(all(0<=v<=TOTAL_DRIVE_MAX_NM/4 for v in drive) and len(set(drive))==1 and
            all(0<=v<=80. for v in brakes) and len(set(brakes))==1 and
            not(sum(drive)>0 and sum(brakes)>0),'Common normalized AWD drive/brake demand')
    require(command.normal_loads_n is None and command.wheel_radii_m is None and
            command.external_force_x_n==command.external_force_y_n==command.external_yaw_moment_nm==0,
            'Driver cannot override tire loads/radii or inject unrecorded forces')
    return command
def normalize_driver_command(command):
    """The existing pose driver generates scalar demand as two rear proxies.

    Convert once before saving/allocating: total stays2*proxy, all four authoritative
    drive channels are equal. This is a demand adapter,never rear actuator fallback.
    """
    require(type(command) is PlanarControls,'Known pose-driver controls required')
    steering(command.steering_angles_rad);drive=four(command.drive_torques_nm,'legacy driver proxy')
    require(drive[0]==drive[1]==0. and drive[2]==drive[3] and 0<=drive[2]<=95.,
            'Exact bounded legacy pose-driver scalar demand;no double conversion')
    mapped=replace(command,drive_torques_nm=(sum(drive)/4,)*4)
    return validate_driver_command(mapped)
def verify_configuration(settings,thermal,drs,act,env,driver):
    """Bind actual FSI constructors to the explicit reviewed SI profile snapshot."""
    values={'settings':asdict(settings),'thermal':asdict(thermal),'drs_policy':asdict(drs),
            'actuation':asdict(act),'environment':asdict(env),'driver':asdict(driver)}
    initial={'u_mps':5.,'wheel_omega_rad_s':[25.]*4,'pack_energy_j':9000000.,'temperature_c':70.,
             'actuator_memory_nm':[0.]*4,'load_longitudinal_mps2':0.,'load_lateral_mps2':0.,
             'position_heading':'Exact selectedFSI firstpoint/coherentarctangent'}
    body={'profile_id':PROFILE_ID,'values':values,'initial':initial,'topology_id':AWD_TOPOLOGY_ID,
          'availability':list(AVAILABLE),'steering':STEERING_MODEL,'total_drive_cap_nm':190.,'equal_weights':[.25]*4}
    observed=sha256(json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    require(observed==PROFILE_CONFIGURATION_SHA256,'AWD physical/driver profile changed;new configuration identity required')
    return observed

@dataclass(frozen=True,slots=True)
class StandingPoseDriverSettings(PoseDriverSettings):
    """The existing driver settings, with an exact zero initial-speed contract.

    The source driver requires a positive initial speed because its standalone
    runner historically starts moving. The light bridge supplies its own
    physical state and uses only the existing controller/projection functions.
    Validate every other inherited field with the original settings validator;
    the positive value below is used for validation only, never as a vehicle
    speed or controller input. The actual setting remains exactly zero.
    """
    def __post_init__(self):
        require(type(self.initial_speed_mps) in (int,float) and isfinite(self.initial_speed_mps) and
                self.initial_speed_mps==0.,'Standing driver requires exact zero initial speed')
        values=asdict(self);values['initial_speed_mps']=1.
        PoseDriverSettings(**values)

def standing_driver(driver):
    require(type(driver) is PoseDriverSettings,'The original driver profile is required')
    values=asdict(driver);values['initial_speed_mps']=0.
    return StandingPoseDriverSettings(**values)

RACING_PROFILE_ID='synthetic_four_independent_awd_racingline_standing_v1'
def verify_racing_configuration(settings,thermal,drs,act,env,driver,reference):
    """Use the historical parameter snapshot, but bind a new zero-speed identity.

    The saved baseline's 5 m/s initializer is provenance only, not this start.
    """
    from pathlib import Path
    from math import ceil
    path=Path(__file__).with_name('baseline-configuration.json')
    with path.open('rb') as stream:raw=stream.read(131073)
    require(len(raw)<=131072,'Bounded baseline parameter snapshot')
    saved=json.loads(raw);baseline=saved['body']
    require(sha256(json.dumps(baseline,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==
        saved['baseline_configuration_sha256']==PROFILE_CONFIGURATION_SHA256,'Original physical+driver snapshot changed')
    actual={'settings':asdict(settings),'thermal':asdict(thermal),'drs_policy':asdict(drs),'actuation':asdict(act),
        'environment':asdict(env),'driver':asdict(driver)}
    actual=json.loads(json.dumps(actual,sort_keys=True,separators=(',',':'),allow_nan=False))
    require(all(actual[k]==baseline['values'][k] for k in ('settings','thermal','drs_policy','actuation','environment')),
        'No unreviewed physical changes during racing-line guidance port')
    expected=dict(baseline['values']['driver']);ticks=(ceil(reference['reference_length_m']/3)+30)*1000
    expected.update(initial_speed_mps=0.,target_progress_m=reference['reference_length_m'],maximum_simulated_time_s=ticks*.001,
        maximum_control_steps=max(1,ceil(ticks/10)),maximum_internal_substeps=50000,reference_geometry='sampled_polyline')
    require(actual['driver']==expected,'Only explicit reference/horizon changes permitted in driver')
    body={'profile_id':RACING_PROFILE_ID,'base_configuration_sha256':PROFILE_CONFIGURATION_SHA256,
        'values':actual,'reference':reference,'initial_geometry':'Frozen racing-line first point/tangent at original physical source gate',
        'standing_start':{'u_mps':0.,'v_mps':0.,'yaw_rate_rad_s':0.,'wheel_omega_rad_s':[0.]*4,
            'pack_energy_j':9000000.,'temperature_c':70.,'actuator_memory_nm':[0.]*4,
            'load_longitudinal_mps2':0.,'load_lateral_mps2':0.,'clock_s':0.}}
    return sha256(json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def fixture():
    """Construct AWD directly;never construct or evolve a rear-only plant."""
    car=PlanarVehicleConfig(300.,160.,.8,.8,1.2,1.2,.2,.3,1.2,7000.,8000.,.5,9.80665,.001)
    force=LightForceConfig(car,AeroAreas(.8,2.,.5),AeroAreas(.5,1.,.4),.25,.5,PROVENANCE)
    settings=LightPoweredConfig(force,.05,PROVENANCE,.001)
    thermal=LumpedTireThermalConfig(20000.,80.,.6,25.,-20.,160.,20.,70.,120.,.8,.7,True,PROVENANCE)
    drs=AutomaticDrsPolicy(12.,10.,.02,.05,.1,.2,1.,2.,.05,.1,.002,PROVENANCE)
    act=ActuationConfig(topology_id=AWD_TOPOLOGY_ID,gear_ratio=4.,gear_efficiency=.96,
        motor_conversion_efficiency=.95,inverter_efficiency=.97,torque_constant_nm_per_a=.8,
        motor_current_limit_a=100.,inverter_current_limit_a=90.,motor_peak_torque_nm=80.,
        motor_base_speed_rad_s=250.,motor_maximum_speed_rad_s=700.,equivalent_copper_resistance_ohm=.02,
        pack_voltage_v=300.,pack_capacity_j=18000000.,pack_discharge_current_limit_a=100.,
        pack_charge_current_limit_a=40.,pack_discharge_power_limit_w=25000.,pack_charge_power_limit_w=8000.,
        actuator_time_constant_s=.025,actuator_slew_nm_per_s=8000.)
    env=PlanarEnvironment(road=PlanarRoad('synthetic_reference_pavement',1.,(),None),
        wind_world_x_mps=0.,wind_world_y_mps=0.,air_density_kgpm3=1.225,drag_area_m2=0.)
    track=_stadium_course(False)
    driver=PoseDriverSettings(output_step_s=.01,target_progress_m=track.length_m,maximum_simulated_time_s=20.,
        maximum_control_steps=2000,maximum_internal_substeps=100000,assumed_half_width_m=3.,vehicle_width_m=1.4,
        safety_margin_m=.2,initial_speed_mps=5.,initial_lateral_offset_m=0.,cruise_speed_mps=9.,
        edge_slowdown_slack_m=.8,edge_outward_prediction_s=.5,edge_rejoin_speed_mps=2.,lookahead_base_m=2.,
        lookahead_seconds=.35,maximum_steering_rad=.4,maximum_rear_drive_torque_nm=95.,
        maximum_wheel_brake_torque_nm=80.,drive_gain_nm_per_mps=40.,brake_gain_nm_per_mps=35.,
        local_projection_window_m=12.,reference_geometry='coherent_arcs')
    return settings,thermal,drs,act,env,track,driver
