"""Thin fixed-clock adapter: the plant supplies snapshots and owns achieved effort."""
from dataclasses import asdict
from hashlib import sha256

from lapsim.dynamics.planar import PlanarState
from lapsim.dynamics.powered_planar import PoweredState, advance_powered, evaluate_powered, energy_residual_j
from lapsim.dynamics.conditions import PlanarEnvironment
from lapsim.experiments.controller_backend import controller_source_identity
from .profile import canonical, require,drive_availability
from .session import ControlSession, replay
from .trace_mode import trace_mode


def simulate(profile,duration_ms=300):
    require(type(duration_ms) is int and 100<=duration_ms<=1000 and duration_ms%10==0,'Preview duration must be 100-1000 integer ms in 10 ms steps')
    car,pack=profile.vehicle,profile.actuation
    initial_speed=profile.policy['initial_speed_mps']
    state=PoweredState(PlanarState(u_mps=initial_speed,wheel_speeds_rad_s=(initial_speed/car.wheel_radius_m,)*4),
                       (0.,)*4,profile.policy['initial_soc']*pack.pack_capacity_j)
    initial=state;session=ControlSession(profile);frames=[];outputs=[];plant=[]
    available=drive_availability(profile);environment=PlanarEnvironment()
    try:
        for now in range(0,duration_ms,10):
            fraction=now/duration_ms
            accelerator=.0 if fraction<.1 or fraction>=.65 else .65
            braking=.25 if .65<=fraction<.85 else 0.
            frame={'now_ms':now,'timestamp_ms':now,'accelerator_fraction':accelerator,'brake_fraction':braking,
                   'steering_rad':.03 if fraction>.3 else 0.,'wheel_speeds_rad_s':list(state.plant.wheel_speeds_rad_s),
                   'pack_energy_j':state.pack_energy_j,'valid':True,'enabled':True,'restart_requested':False,
                   'wheel_available':list(available)}
            if session.experimental:
                frame.update(u_mps=state.plant.u_mps,v_mps=state.plant.v_mps,yaw_rate_rad_s=state.plant.yaw_rate_rad_s,
                    actuator_memory_nm=list(state.actuator_memory_nm),regen_available=True,motor_temperature_c=40.,friction_fallback=True)
            command=session.step(frame)
            torques=tuple(command['limited']['wheel_torques_nm'])
            steer=(frame['steering_rad'],frame['steering_rad'],0.,0.)
            brakes=tuple(command['friction_nm']) if session.experimental else (profile.policy['maximum_friction_brake_nm']*braking,)*4
            rate,_,actual=evaluate_powered(car,pack,state,torques,steer,brakes,available,.01,environment)
            frames.append(frame);outputs.append(command)
            plant.append({'time_ms':now,'u_mps':state.plant.u_mps,'pack_energy_j':state.pack_energy_j,
                          'achieved_nm':list(actual.wheel_torques_nm),'friction_nm':list(brakes),
                          'actuator_memory_nm':list(state.actuator_memory_nm),'actuator_rate_nm_per_s':list(rate[10:14]),
                          'achieved_pack_power_w':actual.pack_power_w,'motor_currents_a':list(actual.motor_currents_a),
                          'motor_speeds_rad_s':list(actual.motor_speeds_rad_s)})
            state=advance_powered(car,pack,state,torques,steer,brakes,available,.01,environment)
    finally:session.close()
    return {'profile_sha256':profile.sha256,'frames':frames,'outputs':outputs,'plant':plant,
            'duration_ms':duration_ms,'energy_residual_j':energy_residual_j(car,initial,state),
            'scope':'ideal synchronous sensors; existing four-wheel plant; no hardware or regen-controller claim'}


def validate(profile,duration_ms=300):
    integrated=simulate(profile,duration_ms)
    return validate_integration(profile,integrated)


def validate_integration(profile,integrated):
    duration_ms=integrated['duration_ms']
    mode=integrated.get('mode')
    require(mode in (None,'full_lap_acceptance_v1','ten_lap_acceptance_v1'),'Unsupported integration mode')
    ten_lap=mode=='ten_lap_acceptance_v1'
    full_lap=mode=='full_lap_acceptance_v1'
    standalone=replay(profile,integrated['frames'],full_lap=full_lap,ten_lap=ten_lap)
    repeat=replay(profile,integrated['frames'],full_lap=full_lap,ten_lap=ten_lap)
    same=standalone==integrated['outputs']
    deterministic=standalone==repeat
    require(same and deterministic,'Standalone/integrated controller output mismatch')
    if not (full_lap or ten_lap):require(abs(integrated['energy_residual_j'])<.5,'Plant energy ledger failed')
    report={'schema':trace_mode(full_lap=full_lap,ten_lap=ten_lap).schema('validation'),'profile':profile.to_dict(),'profile_sha256':profile.sha256,
            'equivalent':same,'repeat_exact':deterministic,'cycles':len(standalone),
            'outputs_sha256':sha256(canonical(standalone).encode()).hexdigest(),
            'energy_residual_j':integrated['energy_residual_j'],'duration_ms':duration_ms,
            'source':controller_source_identity(),
            'scope':'synthetic simulation evidence; no firmware, physical-car calibration or hardware timing validation',
            'integration':integrated}
    if full_lap or ten_lap:report['energy_ledger_pass']=abs(integrated['energy_residual_j'])<.5
    return report
