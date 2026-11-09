"""Four independent AWD OFF policy adapters; plant alone owns energy.

No RWD fallback,arbitrary command,model dispatch or OS/probe operation.
"""
from dataclasses import dataclass
from math import cos,sin,isfinite
from lapsim_light_core.actuation import ActuationEvaluation,AWD_TOPOLOGY_ID
from ._case import OffActuationCase
from .core_registry import TOPOLOGY,entry
from . import awd_contracts as awd_fixture
from . import policy_layers
ZERO=(0.,0.,0.,0.)
SHARES=(.3,.3,.2,.2)
BLEND_VERSION='common_four_brake_weighted_redistribution.release_observable.v3'

def require(value,message):
    if not value:raise ValueError(message)
def finite(value,low,high,name):
    require(type(value) in (int,float) and isfinite(value) and low<=value<=high,'Invalid '+name)
def ensure_topology(pack,available=awd_fixture.AVAILABLE):
    require(pack.topology_id==TOPOLOGY==AWD_TOPOLOGY_ID and type(available) is tuple and
            available==awd_fixture.AVAILABLE and all(type(v) is bool and v for v in available),
            'Four independent AWD motors and four-true availability required;no rear-only fallback')
def controller_for(config_id):return entry(config_id)['controller']
def case_for(config_id,*,initial_soc=.5,pack_voltage_v=300.,motor_temperature_c=40.,regen_available=False):
    entry(config_id);require(regen_available is False,'Only explicit four-channel regen OFF is implemented')
    return OffActuationCase('awd_fixed_total_demand_10ms',duration_s=.01,initial_soc=initial_soc,pack_voltage_v=pack_voltage_v,
                motor_temperature_c=motor_temperature_c,regen_available=False,friction_fallback=True)
def wheel_plane_kinematics(car,point,steering):
    """Same ideal wheel-plane projection as the allocator;not a tire-force estimate."""
    angles=awd_fixture.steering(steering);local=[];slip=[]
    for i,((x,y),angle) in enumerate(zip(car.wheel_positions_m,angles)):
        u=cos(angle)*(point.u_mps-point.yaw_rate_rad_s*y)+sin(angle)*(point.v_mps+point.yaw_rate_rad_s*x)
        local.append(u);slip.append((car.wheel_radius_m*point.wheel_speeds_rad_s[i]-u)/max(abs(u),car.low_speed_regularization_mps))
    require(all(isfinite(v) for v in (*local,*slip)),'Nonfinite wheel-plane estimate')
    return tuple(local),tuple(slip)
@dataclass(frozen=True)
class Allocation:
    requested:tuple
    proposed:tuple
    limited:ActuationEvaluation
    integral:float
    total_brake:float
    raw_regen:float
    diagnostics:dict
def allocate_core(config_id,state,physical,steering,total_drive_nm,total_brake_nm,integral,car,pack,case,dt=.01):
    policy=entry(config_id);ensure_topology(pack);angles=awd_fixture.steering(steering)
    finite(total_drive_nm,0.,190.,'total drive');finite(total_brake_nm,0.,320.,'common brake');finite(integral,-1.,1.,'integral')
    require(not (total_drive_nm > 0 and total_brake_nm > 0),
            'Simultaneous drive and brake demand is outside the common driver domain')
    require(dt==.01 and case.regen_available is False and case.friction_fallback is True,'Common OFF actuation/brakes')
    require(all(t>=0 for t in state.actuator_memory_nm),'OFF cannot import generating memory')
    local,slip=wheel_plane_kinematics(car,state.plant,angles)
    def decide(freeze_integral=False):
        return policy_layers.allocate(policy['torque'],total_drive_nm=total_drive_nm,
            normal_loads_n=[w.normal_load_n for w in physical.wheels],slip=slip,steer=angles[0],u_mps=state.plant.u_mps,
            yaw_rate_rad_s=state.plant.yaw_rate_rad_s,integral=integral,wheel_positions_m=car.wheel_positions_m,
            wheel_radius_m=car.wheel_radius_m,wheelbase_m=car.cg_to_front_axle_m+car.cg_to_rear_axle_m,
            wheel_speeds_rad_s=state.plant.wheel_speeds_rad_s,mass_kg=car.mass_kg,nominal_mu=car.tire_mu,pack=pack,dt=dt,
            freeze_integral=freeze_integral)
    proposed,updated,audit=decide()
    from lapsim_light_core.actuation import constrain_actuation
    limited=constrain_actuation(pack,proposed,state.plant.wheel_speeds_rad_s,state.pack_energy_j,dt,awd_fixture.AVAILABLE)
    if any(abs(a-b)>1e-9 for a,b in zip(proposed,limited.wheel_torques_nm)):
        if updated!=integral:
            proposed,updated,audit=decide(freeze_integral=True)
            require(updated==integral,'Actuator-limit integral freeze must preserve prior state')
            limited=constrain_actuation(pack,proposed,state.plant.wheel_speeds_rad_s,state.pack_energy_j,dt,awd_fixture.AVAILABLE)
        audit['antiwindup_actuator_limit_freeze']=True
    requested=(total_drive_nm/4,)*4
    audit.update(config_id=config_id,regen_inhibited=True,command_constraints=list(limited.constraints),
        topology_id=TOPOLOGY,motor_count=4,drive_availability=[True]*4,baseline_weights=[.25]*4,
        estimated_wheel_plane_u_mps=list(local),estimated_slip=list(slip),steering_angles_rad=list(angles))
    return Allocation(requested,proposed,limited,updated,total_brake_nm,0.,audit)


def validate_awd_row(row,*,expected_configuration_sha256):
    require(row['topology_id']==TOPOLOGY and row['configuration_sha256']==expected_configuration_sha256 and
            type(row['motor_count']) is int and row['motor_count']==4 and
            row['drive_availability']==[True]*4 and all(type(v) is bool for v in row['drive_availability']) and
            row['baseline_weights']==[.25]*4,'Exact AWD row architecture')
    awd_fixture.steering(row['steering_rad'])
    finite(row['driver_total_drive_request_nm'],0.,190.,'recorded total drive Nm')
    finite(row['driver_total_brake_request_nm'],0.,320.,'recorded total brake Nm')
    for key in ('requested_nm','proposed_nm','limited_nm','achieved_nm','motor_current_a','motor_torque_nm'):
        values=awd_fixture.four(row[key],key)
        require(all(v>=0 for v in values),'AWD OFF row cannot contain a negative '+key)
    require(tuple(row['requested_nm'])==(row['driver_total_drive_request_nm']/4,)*4,
            'Recorded request differs from the exact equal four-wheel demand baseline')
    return True

def brake_blend(total, raw_regen, electrical):
    """Common capacities/priority for every regime, using actual lagged torque.

    Weighted water filling preserves60/40 bias until a wheel saturates, then
    redistributes to available friction capacity. It never creates extra motor
    or friction authority. Positive motor lag can still cause an honest shortfall
    above320Nm; excess actual regen can cause overshoot, never negative friction.
    Torque demand is not a guarantee of equal physical deceleration on all grips.
    """
    finite(total, 0., 320., "total brake demand Nm")
    finite(raw_regen, 0., 320., "raw regen Nm")
    torques = electrical.wheel_torques_nm
    require(len(torques) == 4 and all(type(v) in (int, float) and isfinite(v) for v in torques), "Four finite actual torques required")
    regen = sum(max(0., -value) for value in torques)
    actual_drive = sum(max(0., value) for value in torques)
    drive = actual_drive if total > 0 else 0.
    required = max(0., total + drive - regen) if total > 0 else 0.
    target = min(320., required)
    brakes = [0.] * 4
    remaining = target
    free = list(range(4))
    for _ in range(4):
        if not free or remaining <= 1e-12:
            break
        mass = sum(SHARES[i] for i in free)
        additions = {i: min(80. - brakes[i], remaining * SHARES[i] / mass) for i in free}
        for i, value in additions.items():
            brakes[i] += value
        remaining = max(0., target - sum(brakes))
        free = [i for i in free if brakes[i] < 80. - 1e-12]
    require(all(0 <= v <= 80. for v in brakes), "Common friction capacity exceeded")
    shortfall = max(0., required - sum(brakes))
    actual_net = regen + sum(brakes) - actual_drive
    return tuple(brakes), {"version": BLEND_VERSION, "demand_nm": total, "actual_regen_nm": regen,
        "raw_regen_request_nm": raw_regen, "actual_drive_nm_all_phases": actual_drive,
        "actual_torques_nm": list(torques), "actual_net_braking_nm": actual_net,
        "residual_drive_nm": drive, "required_friction_nm": required, "delivered_friction_nm": sum(brakes),
        "shortfall_nm": shortfall, "overshoot_nm": max(0., actual_net - total),
        "observation_scope": "Pre-integration current actual torque; release excess is reported even at zero brake demand",
        "redistributed": any(abs(value - target * share) > 1e-8 for value, share in zip(brakes, SHARES)),
        "authority": "Same four80Nm friction brakes; residual drive or tire limits can still prevent requested deceleration"}
