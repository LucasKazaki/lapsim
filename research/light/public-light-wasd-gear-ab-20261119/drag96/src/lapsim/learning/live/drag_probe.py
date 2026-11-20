"""Unbound finite drag measurement for the original admitted child only.

No CLI, process, lease, admission, writer or permissive owner implementation.
The execution owner must integrate and pin this module in a fresh finite route.
"""
from dataclasses import asdict
from math import cos, sin, hypot, isfinite, pi

from .initialization import construct, canonical, digest
from .owner import SupervisedChildOwner
from .row_codec import encode_block, MAX_ROWS, MAX_EXPANDED
from lapsim_light_core.torque_light_combined import advance_combined_light
from lapsim_light_core.torque_light_thermal import evaluate_thermal_light

STAGING = {'schema': 'lapsim.fsae-staged-straight-timing.v1', 'start_gate_m': 0.0, 'finish_gate_m': 75.0, 'foremost_initial_gate_coordinate_m': -0.3, 'launch_speed_mps': 0.0, 'wheel_speeds_rad_s': [0.0, 0.0, 0.0, 0.0], 'reference': 'body CG; longitudinal projection on initial heading; front support of symmetric rectangle', 'body_half_length_m': 1.0, 'body_half_width_m': 0.7, 'geometry_status': 'inherited modeled symmetric footprint; bumper/CG dimensions not measured', 'gate_time': 'first foremost-part finish crossing minus first foremost-part start crossing', 'interpolation': 'linear crossing time and velocity between accepted1ms endpoints; endpoint retained'}

def nose_coordinate(point, origin):
    heading = point.heading_rad-origin.heading_rad
    projected = ((point.x_m-origin.x_m)*cos(origin.heading_rad)
                 +(point.y_m-origin.y_m)*sin(origin.heading_rad))
    return projected + (abs(cos(heading))*1. + abs(sin(heading))*.7) - 1.30

def first_crossing(before_coordinate, after_coordinate, target, tick, before, after):
    if before_coordinate < target <= after_coordinate:
        fraction=(target-before_coordinate)/(after_coordinate-before_coordinate)
        return dict(fraction=fraction, elapsed_s=(tick+fraction)/1000.,
            speed_mps=hypot(before.u_mps+fraction*(after.u_mps-before.u_mps),
                            before.v_mps+fraction*(after.v_mps-before.v_mps)),
            interpolation='time and velocity only; physical endpoint retained, no synthetic state continuation')
    return None

TARGET_M = 75.
MAX_TICKS = 8000
MAX_WORK = 4000000
MAX_TICK_WORK = 50000
MAX_EVIDENCE = 33554432

THROTTLE_CASES=('driver_full_pedal','configured_motor_full_throttle')

def drag_command(actuation, policy, *, throttle_case):
    """Keep the actual driver limit and motor ceiling as separate explicit cases."""
    if throttle_case=='driver_full_pedal':
        axle=policy['maximum_drive_request_nm']
    elif throttle_case=='configured_motor_full_throttle':
        axle=actuation.motor_peak_torque_nm*actuation.gear_ratio*actuation.gear_efficiency
    else:raise ValueError('explicit admitted drag throttle case required')
    return (0., 0., axle/2., axle/2.)

def run_admitted_drag(owner, raws, *, throttle_case, source_manifest_sha256, publish_block, collection_check):
    """Original owner admission and checked parent cleanup remain prerequisites."""
    if type(owner) is not SupervisedChildOwner:
        raise TypeError('actual original supervised child owner required')
    owner.require_owner_live()
    if (type(source_manifest_sha256) is not str or len(source_manifest_sha256)!=64
            or any(c not in '0123456789abcdef' for c in source_manifest_sha256)
            or not callable(publish_block) or not callable(collection_check)):
        raise ValueError('fixed source identity and bounded original writer required')
    collection_check()
    plant=construct(raws)
    owner.require_owner_live()
    if plant.construction_record.get('start_mode')!='standing':
        raise ValueError('explicit corrected standing-start construction required')
    state=plant.state;initial=asdict(state);p0=state.thermal.light.powered.plant
    if (p0.u_mps,p0.v_mps,p0.yaw_rate_rad_s,*p0.wheel_speeds_rad_s)!=(0.,)*7:
        raise ValueError('drag test must begin fully at rest')
    car=plant.settings.forces.plant
    heading=p0.heading_rad;c,s=cos(heading),sin(heading)
    def distance(p):return (p.x_m-p0.x_m)*c+(p.y_m-p0.y_m)*s
    def lateral(p):return -(p.x_m-p0.x_m)*s+(p.y_m-p0.y_m)*c
    command=drag_command(plant.actuation,plant.profile['policy'],throttle_case=throttle_case)
    steering=brakes=(0.,)*4;available=(False,False,True,True)
    pending=[];pending_bytes=total_bytes=rows=0
    def flush():
        nonlocal pending,pending_bytes,total_bytes
        if not pending:return
        packet=encode_block(tuple(pending))
        if total_bytes+len(packet)+5>MAX_EVIDENCE:raise RuntimeError('finite drag evidence exhausted')
        owner.reserve_evidence(len(packet)+5)
        publish_block(packet)
        total_bytes+=len(packet)+5;pending=[];pending_bytes=0
    def emit(value):
        nonlocal pending_bytes,rows
        raw=canonical(value).encode()
        if len(raw)+5>MAX_EXPANDED:raise RuntimeError('finite drag row exhausted')
        if pending and (len(pending)>=MAX_ROWS or pending_bytes+len(raw)+5>MAX_EXPANDED):flush()
        pending.append(raw);pending_bytes+=len(raw)+5;rows+=1
        if rows>MAX_TICKS*2+3:raise RuntimeError('finite drag row count exhausted')
    context=dict(staging=STAGING, profile_sha256=plant.construction_record['input_pins']['profile'][1], schema='lapsim.drag75m-staged-source.v2',operation_id=owner.operation_id,
        source_manifest_sha256=source_manifest_sha256,construction=plant.construction_record,
        mission='official-style75m timing gates; foremost part initially0.30m behind start at rest; no driver learning',
        throttle=1.,throttle_case=throttle_case,
        throttle_convention=('actual learned-driver full-pedal axle request cap; no policy inference' if throttle_case=='driver_full_pedal' else 'configured motor_peak_torque transformed once to wheel-side; separate hardware-envelope diagnostic'),
        physical_limits='canonical current/speed/power/pack/actuator/traction limits retained in both cases',
        motor_input_nm=command,steering_rad=steering,friction_nm=brakes,regen='no negative motor request; no requested regeneration',
        automatic_drs_enabled=state.automatic_drs_enabled,physics_tick_s=.001,target_m=TARGET_M,
        maximum_ticks=MAX_TICKS,maximum_work=MAX_WORK,maximum_tick_work=MAX_TICK_WORK,
        reference_target_s=4.188,reference_status='official2026 Michigan UMD acceleration best; model and vehicle calibration remain unverified')
    emit(dict(kind='construction',context=context,initial_state=initial))
    max_speed=max_ax=max_slip=0.;min_ax=0.;max_motor_torque=max_motor_speed=0.
    baseline_work=state.thermal.light.powered.integration_trials+state.thermal.light.powered.wheel_stop_events
    crossing = start_crossing = launch75_crossing = None
    maximum_endpoint_motor_rpm = maximum_heading_deviation_rad = 0.
    for tick in range(MAX_TICKS):
        collection_check()
        owner.require_owner_live()
        before=state;before_view=asdict(before);bp=before.thermal.light.powered
        work=bp.integration_trials+bp.wheel_stop_events-baseline_work
        if not 0<=work<MAX_WORK:raise RuntimeError('finite cumulative drag work exhausted')
        diag=None
        if tick%10==0:
            _,physical,electrical=evaluate_thermal_light(plant.settings,plant.thermal,plant.actuation,
                before.thermal,command,steering,brakes,available,plant.environment,
                aero_mode=before.drs.actual_mode,wheel_radii_m=(car.wheel_radius_m,)*4,driver_proxy_n=0.)
            owner.require_owner_live()
            max_ax=max(max_ax,physical.cg_longitudinal_acceleration_mps2);min_ax=min(min_ax,physical.cg_longitudinal_acceleration_mps2)
            max_slip=max(max_slip,*(abs(w.slip_ratio) for w in physical.wheels))
            max_motor_torque=max(max_motor_torque,*(abs(x) for x in electrical.motor_torques_nm))
            max_motor_speed=max(max_motor_speed,*electrical.motor_speeds_rad_s)
            diag=dict(sample='tick-start every10ms',physical=asdict(physical),electrical=asdict(electrical))
        state=advance_combined_light(plant.settings,plant.thermal,plant.drs,plant.actuation,before,
            command,steering,brakes,available,plant.environment,braking_requested=False,
            wheel_radii_m=(car.wheel_radius_m,)*4,maximum_work=min(MAX_TICK_WORK,MAX_WORK-work),driver_proxy_n=0.)
        owner.require_owner_live()
        ap=state.thermal.light.powered;p=ap.plant
        new_work=ap.integration_trials+ap.wheel_stop_events-baseline_work
        if (asdict(before)!=before_view or state.model_sha256!=before.model_sha256
                or state.thermal.light.feedback_ticks!=tick+1 or state.drs.ticks!=tick+1
                or state.thermal.thermal.ticks!=tick+1 or not work<=new_work<=min(work+MAX_TICK_WORK,MAX_WORK)):
            raise RuntimeError('drag state/clock/work continuity differs')
        d0,d1=distance(bp.plant),distance(p)
        n0,n1=nose_coordinate(bp.plant,p0),nose_coordinate(p,p0)
        maximum_heading_deviation_rad=max(maximum_heading_deviation_rad,abs(p.heading_rad-heading))
        # Single carrier motor speed is mean rear-wheel speed times final reduction.
        maximum_endpoint_motor_rpm=max(maximum_endpoint_motor_rpm,
            abs(sum(p.wheel_speeds_rad_s[2:])/2.*plant.actuation.gear_ratio)*60./(2.*pi))
        if start_crossing is None:start_crossing=first_crossing(n0,n1,0.,tick,bp.plant,p)
        if launch75_crossing is None:launch75_crossing=first_crossing(d0,d1,75.,tick,bp.plant,p)
        finish_crossing=first_crossing(n0,n1,75.,tick,bp.plant,p)
        speed=hypot(p.u_mps,p.v_mps);max_speed=max(max_speed,speed)
        if (not all(isfinite(x) for x in (d0,d1,speed,lateral(p))) or d1<d0
                or hypot(p.x_m-bp.plant.x_m,p.y_m-bp.plant.y_m)>.5 or abs(lateral(p))>1.):
            raise RuntimeError('unsupported nonforward or nonstraight drag trajectory')
        emit(dict(kind='feedback',from_ms=tick,until_ms=tick+1,input_state_sha256=digest(before_view),
            accepted_state_sha256=digest(asdict(state)),complete_accepted_state=asdict(state),
            distance_endpoints_m=(d0,d1),nose_gate_endpoints_m=(n0,n1),lateral_m=lateral(p),diagnostics=diag))
        if finish_crossing is not None:
            if start_crossing is None or launch75_crossing is None:raise RuntimeError('missing preceding timing crossing')
            crossing=finish_crossing
            break
    summary=dict(schema='lapsim.drag75m-staged-result.v2',context_sha256=digest(context),
        status='reached_staged_finish' if crossing else 'finite_horizon_without_staged_finish',crossing=crossing,
        timing=dict(start=start_crossing,finish=crossing,launch_to_original75m=launch75_crossing,
            gate_to_gate_s=None if crossing is None else crossing['elapsed_s']-start_crossing['elapsed_s']),
        maximum_endpoint_motor_rpm=maximum_endpoint_motor_rpm,maximum_heading_deviation_rad=maximum_heading_deviation_rad,
        accepted_tick=state.thermal.light.feedback_ticks,endpoint_distance_m=distance(state.thermal.light.powered.plant),
        maximum_endpoint_speed_mps=max_speed,acceleration_10ms_min_mps2=min_ax,acceleration_10ms_max_mps2=max_ax,
        maximum_sampled_abs_tire_slip=max_slip,maximum_sampled_motor_torque_nm=max_motor_torque,
        maximum_sampled_motor_speed_rad_s=max_motor_speed,terminal_state=asdict(state),
        qualification='diagnostic canonical synthetic profile; no verified2026 vehicle accuracy or lap validation')
    collection_check()
    emit(dict(kind='summary',result=summary));flush();owner.require_owner_live()
    return summary
