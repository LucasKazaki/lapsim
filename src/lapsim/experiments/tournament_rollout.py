"""Deterministic synthetic closed-course torque experiments; SI throughout.

The fixed pure-pursuit driver is inherited from pose_driver. Only the torque
controller is selected/tuned. The existing powered four-wheel plant owns all
physical states and the RK energy ledger. No hardware backend is selected.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from math import atan2, cos, hypot, isfinite, pi, remainder, sin, sqrt, tan

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Straight, Track
from lapsim.courses.course_bundle import CourseBundle, course_geometry_sha256
from lapsim.dynamics.actuation import ActuationConfig, ActuationEvaluation, constrain_actuation, AWD_TOPOLOGY_ID, SINGLE_MOTOR_RWD_TOPOLOGY_ID, SPOOL_RWD_TOPOLOGY_ID
from .lap_ledger import LapLedger
from lapsim.dynamics.conditions import PlanarEnvironment, PlanarRoad, RectangularGripPatch
from lapsim.dynamics.planar import PlanarState, evaluate_planar_dynamics, PlanarControls
from lapsim.dynamics.powered_planar import PoweredState, advance_powered, energy_residual_j, evaluate_powered
from lapsim.experiments.closed_loop import synthetic_car
from lapsim.optimization.pose_driver import (
    PoseDriverSettings, _controller, _project_local, _reference_start_heading,
    _assumed_footprint_slack,
)

ZERO = (0.0, 0.0, 0.0, 0.0)
AVAILABLE = (False, False, True, True)
PHILOSOPHIES = ("fixed", "traction", "yaw_pi", "tire_reserve")
CONFIGURED_REFERENCE = 'configured_equal_split_reference_v1'
PROFILES = ("synthetic_rwd", "synthetic_awd", "synthetic_single_motor_rwd", "synthetic_spool_rwd")
BOUNDS = {"drive_scale": (0.6, 1.0), "slip_target": (0.035, 0.18),
          "yaw_kp": (0.0, 45.0), "yaw_ki": (0.0, 15.0),
          "regen_fraction": (0.0, 0.95), "regen_region": (0.1, 0.4)}
PHYSICAL_BOUNDS={"mass_kg":(200,500),"drag_area_m2":(0,2),"gear_ratio":(2,8),
    "tire_mu":(.6,1.6),"wheel_radius_m":(.18,.24),"wheel_inertia_kgm2":(.3,.9),
    "rear_radius_mismatch_fraction":(-.03,.03),"pack_discharge_power_limit_w":(15000,40000)}


def number(value, name, low, high):
    if type(value) not in (float, int) or not isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be finite in [{low}, {high}]")


@dataclass(frozen=True)
class Controller:
    philosophy: str = "fixed"
    drive_scale: float = 1.0
    slip_target: float = 0.10
    yaw_kp: float = 20.0
    yaw_ki: float = 3.0
    regen_fraction: float = 0.65
    regen_region: float = 0.25

    def __post_init__(self):
        if self.philosophy not in (*PHILOSOPHIES,CONFIGURED_REFERENCE):
            raise ValueError("unsupported controller philosophy")
        for key, (lo, hi) in BOUNDS.items():
            number(getattr(self, key), key, lo, hi)


@dataclass(frozen=True)
class Case:
    name: str
    course: str = "stadium"
    grip: float = 1.0
    patch: bool = False
    initial_soc: float = 0.7
    pack_voltage_v: float = 580.0
    initial_offset_m: float = 0.0
    regen_available: bool = True
    friction_fallback: bool = True
    motor_temperature_c: float = 40.0
    duration_s: float = 30.0
    reverse: bool = False
    mirror: bool = False
    course_bundle: dict | None = None
    laps: int = 1
    long_course: bool = False

    def __post_init__(self):
        if type(self.laps) is not int or self.laps not in (1,10):
            raise ValueError('Choose a one-lap diagnostic or ten-lap competition')
        if self.course not in ("stadium", "reverse_stadium", "autocross", "bundle"):
            raise ValueError("unknown coherent course")
        if self.course == "bundle":
            if self.course_bundle is None:raise ValueError('Bundle course requires its geometry')
            bundle = CourseBundle.from_dict(self.course_bundle)
            if bundle.schema_version != 1:
                raise ValueError("tournament requires a v1 bundle with an explicitly assumed corridor; source-cell walls are not yet supported")
            bundle.solver_cell_count(.5)
        elif self.course_bundle is not None:
            raise ValueError("course_bundle requires the bundle course")
        if type(self.long_course) is not bool or (self.long_course and (self.course!='bundle' or self.laps!=1)):
            raise ValueError('Long-course mode requires one lap of a validated bundle')
        for key, lo, hi in (("grip", .2, 1.3), ("initial_soc", 0, 1),
                           ("pack_voltage_v", 100, 650), ("initial_offset_m", -1, 1),
                           ("motor_temperature_c", -20, 150), ("duration_s", .01, 600 if self.laps==10 else 300 if self.long_course else 60)):
            number(getattr(self, key), key, lo, hi)
        for key in ("patch", "regen_available", "friction_fallback", "reverse", "mirror"):
            if type(getattr(self, key)) is not bool:
                raise ValueError(f"{key} must be boolean")


def course_for(case: Case):
    if case.course == "bundle":
        if case.course_bundle is None:raise ValueError('Bundle course requires its geometry')
        track = CourseBundle.from_dict(case.course_bundle).solver_track(.5)
    elif case.course == "autocross":
        # Two rotationally symmetric halves close exactly. Alternating turns,
        # short straights and hairpins exercise more than a stadium loop.
        # Original synthetic geometry, not an official or measured event map.
        half = [Straight(10), Curve(8, pi/2), Straight(2), Curve(6, -pi/2),
                Straight(6), Curve(6, -pi/2), Straight(2), Curve(8, pi/2),
                Straight(10), Curve(22, pi)]
        track = SpatialTrack.from_track(Track.from_segments(half + half),
                                        maximum_cell_length_m=.5, close_geometry=False)
    else:
        track = _stadium_course(case.course == "reverse_stadium")
    if case.reverse:
        track = SpatialTrack(tuple(track.length_m-v for v in reversed(track.distance_m)),
                             tuple(reversed(track.x_m)), tuple(reversed(track.y_m)),
                             tuple(-v for v in reversed(track.curvature_per_m)), closed=True)
    if case.mirror:
        track = SpatialTrack(track.distance_m, track.x_m, tuple(-v for v in track.y_m),
                             tuple(-v for v in track.curvature_per_m), closed=True)
    track.validate_coherent_arcs()
    return track


def _stadium_course(reverse):
    radius = 9.0 if reverse else 10.0
    segments = []
    for length in ((14, 8, 14, 8) if reverse else (12, 6, 12, 6)):
        segments += [Straight(length), Curve(radius, (-1 if reverse else 1) * pi / 2)]
    track = SpatialTrack.from_track(Track.from_segments(segments),
                                  maximum_cell_length_m=.5, close_geometry=False)
    track.validate_coherent_arcs()
    return track


def fixture():
    # Deliberately synthetic softer tire / inertia fixture for bounded desktop
    # experiments. These are not a tire fit, measured inertia or a 2025 car.
    car = replace(synthetic_car(), wheel_inertia_kgm2=.6,
                  longitudinal_stiffness_n_per_slip=2500.0,
                  cornering_stiffness_n_per_rad=6000.0)
    pack = replace(ActuationConfig(), pack_voltage_v=580.0,
                   pack_capacity_j=5.5 * 3_600_000, pack_charge_power_limit_w=8000.0)
    driver = PoseDriverSettings(output_step_s=.01, maximum_steering_rad=.4,
                               cruise_speed_mps=9.0, initial_speed_mps=5.0,
                               vehicle_width_m=1.4, maximum_rear_drive_torque_nm=95.0,
                               maximum_wheel_brake_torque_nm=80.0,
                               lookahead_base_m=2.0, lookahead_seconds=.35)
    return car, pack, driver


def brake_request(pedal, controller, total_capacity_nm=320.0):
    """Initial region requests regen only; friction fills any rejected portion."""
    number(pedal, "pedal", 0, 1)
    total_capacity_nm=getattr(controller,'brake_capacity_nm',total_capacity_nm)
    total = pedal * total_capacity_nm
    region = controller.regen_region
    regen = (pedal if pedal <= region else region + (pedal - region) * controller.regen_fraction) * total_capacity_nm
    if getattr(controller,'pedal_mode','two_stage')=='proportional':regen=total*controller.regen_fraction
    return total, regen*getattr(controller,'regen_scale',1.)


def friction_blend(total_brake,raw_regen,achieved_regen,residual_drive,*,fallback,
                   capacity_nm=80.,shares=(.3,.3,.2,.2)):
    """Existing friction compensation, with explicit per-wheel capacity/shares."""
    number(capacity_nm,'friction capacity',0.,80.)
    if len(shares)!=4 or abs(sum(shares)-1.)>1e-12 or any(not 0<=v<=1 for v in shares):
        raise ValueError('Four normalized friction shares are required')
    friction_total=max(0,total_brake+residual_drive-achieved_regen) if fallback else max(0,total_brake-raw_regen)
    brakes=tuple(min(capacity_nm,share*friction_total) for share in shares)
    return brakes,max(0,total_brake+residual_drive-achieved_regen-sum(brakes))


def allocate(controller, state, evaluation, steering, drive_each, brake_each,
             integral, car, pack, case, dt=.01):
    """Controller sees ideal current kinematics; tire reserve is a nominal estimate.

    Wheel speed is compared with velocity projected into the steered wheel
    plane. True road/material/friction force is never supplied to the controller.
    The plant and actuator still impose their own physical limits separately.
    """
    if controller.philosophy==CONFIGURED_REFERENCE:raise ValueError('Configured strategy requires the shared ControlSession adapter')
    p = state.plant
    driven = (0, 1, 2, 3) if pack.topology_id == AWD_TOPOLOGY_ID else (2, 3)
    available = (0 in driven,1 in driven,2 in driven,3 in driven)
    requested = tuple(2 * drive_each / len(driven) if i in driven else 0.0 for i in range(4))
    if len(driven)==4 and hasattr(controller,'allocation_front_bias'):
        bias=controller.allocation_front_bias
        requested=(drive_each*bias,drive_each*bias,drive_each*(1-bias),drive_each*(1-bias))
    proposed = list(requested)
    slips = []
    for i, (x, y) in enumerate(car.wheel_positions_m):
        angle = steering if i < 2 else 0.0
        local_u = (cos(angle) * (p.u_mps - p.yaw_rate_rad_s * y)
                   + sin(angle) * (p.v_mps + p.yaw_rate_rad_s * x))
        slips.append((car.wheel_radius_m * p.wheel_speeds_rad_s[i] - local_u)
                     / max(abs(local_u), car.low_speed_regularization_mps))
    for i in driven:
        proposed[i] *= controller.drive_scale
        if getattr(controller,'slip_control',controller.philosophy!='fixed'):
            proposed[i] *= min(1.0, controller.slip_target / max(controller.slip_target, slips[i]))
    yaw_error = p.u_mps * tan(steering) / 1.6 - p.yaw_rate_rad_s
    integral = max(-1.0, min(1.0, integral + dt * yaw_error))
    if getattr(controller,'yaw_control',controller.philosophy=='yaw_pi') and drive_each > 0 and pack.topology_id not in (SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID):
        differential = max(-25.0, min(25.0, controller.yaw_kp * yaw_error
                                     + controller.yaw_ki * integral))
        # Right-positive torque produces left-positive yaw. Do not create
        # negative drive/regen on the inside as part of the yaw allocator.
        for left, right in (((0, 1), (2, 3)) if len(driven) == 4 else ((2, 3),)):
            total = proposed[left] + proposed[right]
            proposed[right] = max(0, min(total, proposed[right] + differential * 2 / len(driven)))
            proposed[left] = total - proposed[right]
    nominal_lateral = abs(p.u_mps * p.yaw_rate_rad_s) * car.mass_kg / 4
    reserve = [sqrt(max(0.0, (.85 * car.tire_mu * load) ** 2 - nominal_lateral ** 2))
               * car.wheel_radius_m for load in car.static_normal_loads_n]
    if getattr(controller,'reserve_control',controller.philosophy=='tire_reserve'):
        for i in driven:
            proposed[i] = min(proposed[i], reserve[i])
    total_brake, raw_regen = brake_request(min(1.0, brake_each / 80.0), controller)
    regen_ok = (case.regen_available and case.pack_voltage_v < 600.0
                and case.motor_temperature_c < 90 and p.u_mps > 2.0)
    if total_brake > 0:
        proposed = [0.0, 0.0, 0.0, 0.0]
        if regen_ok:
            for i in driven:
                proposed[i] = -min(raw_regen / len(driven), reserve[i])
    if case.motor_temperature_c >= 100 or case.pack_voltage_v > 600:
        proposed = list(ZERO)
    if pack.topology_id in (SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID):
        # The controller has only common axle authority. The smaller magnitude
        # satisfies both wheel estimates; no independent yaw command is sent.
        common = min(proposed[2], proposed[3]) if total_brake <= 0 else -min(abs(proposed[2]), abs(proposed[3]))
        proposed[2] = proposed[3] = common
    limited = constrain_actuation(pack, tuple(proposed), p.wheel_speeds_rad_s,
                                  state.pack_energy_j, dt, available)
    # Brake blending uses currently achievable generating effort, including
    # actuator lag, rather than crediting a future requested regen command.
    actual = constrain_actuation(pack, state.actuator_memory_nm, p.wheel_speeds_rad_s,
                                 state.pack_energy_j, dt, available)
    achieved_regen = sum(max(0, -t) for t in actual.wheel_torques_nm)
    residual_drive = sum(max(0, t) for t in actual.wheel_torques_nm) if total_brake > 0 else 0.0
    brakes,shortfall=friction_blend(total_brake,raw_regen,achieved_regen,residual_drive,fallback=case.friction_fallback)
    return requested, tuple(proposed), limited, brakes, integral, shortfall, raw_regen


def rollout(controller: Controller, case: Case, *, profile="synthetic_rwd", parameter_overrides=None, configured_profile=None, configured_full_lap=False,progress_callback=None):
    if progress_callback is not None and not callable(progress_callback):raise ValueError('Progress callback must be callable')
    if type(configured_full_lap) is not bool:raise ValueError('Configured full-lap mode must be Boolean')
    if configured_profile is None:
        if configured_full_lap:raise ValueError('Full-lap configured acceptance requires its profile')
        if controller.philosophy==CONFIGURED_REFERENCE:raise ValueError('Configured strategy requires its exact vehicle profile')
        return _rollout(controller,case,profile=profile,parameter_overrides=parameter_overrides,progress_callback=progress_callback)
    from lapsim.torque_configurator import ControlSession,VehicleProfile
    from lapsim.torque_configurator.profile import require
    require(type(configured_profile) is VehicleProfile,'A validated configured profile is required')
    require(case.laps in (1,10),'Configured round requires one or ten laps')
    aliases={'synthetic_independent_rear_rwd_v1':'synthetic_rwd',
             SINGLE_MOTOR_RWD_TOPOLOGY_ID:'synthetic_single_motor_rwd',SPOOL_RWD_TOPOLOGY_ID:'synthetic_spool_rwd',AWD_TOPOLOGY_ID:'synthetic_awd'}
    require(profile==aliases[configured_profile.actuation.topology_id],'Configured profile/tournament topology mismatch')
    require(controller==Controller(CONFIGURED_REFERENCE),'Configured profile supports only its exact equal-split reference strategy; no strategy/tuning substitution')
    require(not parameter_overrides,'Configured profiles cannot have unrecorded physical overrides')
    maximum=600 if case.laps==10 and configured_full_lap else 60 if configured_full_lap else 2
    require(.1<=case.duration_s<=maximum and abs(case.duration_s*1000-round(case.duration_s*1000))<1e-9
            and round(case.duration_s*1000)%10==0,'Configured duration exceeds its explicit mode bound or 10 ms clock')
    require(case.pack_voltage_v==configured_profile.actuation.pack_voltage_v and case.initial_soc==configured_profile.policy['initial_soc'],
            'Case voltage/SOC conflicts with configured profile')
    require(configured_profile.to_dict()['schema']=='lapsim.torque-profile.v2' or (not case.regen_available and case.friction_fallback and case.motor_temperature_c==40.),
            'Configured propulsive baseline requires explicit no-regen/friction scenario; thermal calibration is unavailable')
    session=ControlSession(configured_profile)
    try:return _rollout(controller,case,profile=profile,configured_profile=configured_profile,session=session,configured_full_lap=configured_full_lap,progress_callback=progress_callback)
    finally:session.close()


def _round_state(state,integral,session=None):
    value=asdict(state)
    for key in ('integration_substeps','integration_trials','wheel_stop_events'):value.pop(key)
    value['controller_yaw_integral']=integral
    if session is not None:value['configured_controller_state']=session.state_snapshot()
    return value


def _state_digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _rollout(controller, case, *, profile, parameter_overrides=None, configured_profile=None, session=None, configured_full_lap=False,progress_callback=None):
    if profile not in PROFILES:
        raise ValueError("2025-derived AWD baseline is blocked by unknown reviewed 2025 parameters and selected drivetrain specifications")
    car, pack, driver = fixture()
    if configured_profile is not None:car,pack=configured_profile.vehicle,configured_profile.actuation
    if case.course == "bundle":
        bundle = CourseBundle.from_dict(case.course_bundle)
        driver = replace(driver, assumed_half_width_m=bundle.default_ai_half_width_m,
                         vehicle_width_m=bundle.default_ai_vehicle_width_m,
                         safety_margin_m=bundle.default_ai_margin_m)
    overrides = {} if parameter_overrides is None else dict(parameter_overrides)
    override_bounds = PHYSICAL_BOUNDS
    if set(overrides) - set(override_bounds):
        raise ValueError("unknown physical sweep parameter")
    for name, value in overrides.items():
        number(value, name, *override_bounds[name])
    car = replace(car, **{key:overrides[key] for key in ('mass_kg','tire_mu','wheel_radius_m','wheel_inertia_kgm2') if key in overrides})
    pack = replace(pack, **{key:overrides[key] for key in ('gear_ratio','pack_discharge_power_limit_w') if key in overrides})
    if profile == "synthetic_awd":
        pack = replace(pack, topology_id=AWD_TOPOLOGY_ID)
    elif profile == "synthetic_single_motor_rwd":
        pack = replace(pack, topology_id=SINGLE_MOTOR_RWD_TOPOLOGY_ID)
    elif profile == 'synthetic_spool_rwd':
        pack = replace(pack, topology_id=SPOOL_RWD_TOPOLOGY_ID)
    available = (True,True,True,True) if profile == "synthetic_awd" else AVAILABLE
    pack = replace(pack, pack_voltage_v=case.pack_voltage_v)
    track = course_for(case)
    road = PlanarRoad(patches=(RectangularGripPatch(4, 14, -2, 2, .65, "synthetic_patch"),) if case.patch else ())
    env = PlanarEnvironment(road=road, drag_area_m2=overrides.get("drag_area_m2", .5))
    car = replace(car, tire_mu=car.tire_mu * case.grip)
    # Driver preview keeps its declared nominal grip across held-out surfaces.
    driver_car = configured_profile.vehicle if configured_profile is not None else fixture()[0]
    heading = _reference_start_heading(track, driver)
    initial_p = PlanarState(x_m=track.x_m[0] - sin(heading) * case.initial_offset_m,
                           y_m=track.y_m[0] + cos(heading) * case.initial_offset_m,
                           heading_rad=heading, u_mps=5.0, wheel_speeds_rad_s=(25.0,25.0,25.0,25.0))
    mismatch=overrides.get('rear_radius_mismatch_fraction',0.)
    radii=(car.wheel_radius_m,car.wheel_radius_m,car.wheel_radius_m*(1-mismatch),car.wheel_radius_m*(1+mismatch))
    initial_omega=[5./radius for radius in radii]
    if profile=='synthetic_spool_rwd':initial_omega[2:]=[5./((radii[2]+radii[3])/2)]*2
    initial_p=replace(initial_p,wheel_speeds_rad_s=(initial_omega[0],initial_omega[1],initial_omega[2],initial_omega[3]))
    if configured_profile is not None:
        speed=configured_profile.policy['initial_speed_mps']
        omega=speed/car.wheel_radius_m
        initial_p=replace(initial_p,u_mps=speed,wheel_speeds_rad_s=(omega,omega,omega,omega))
    initial = PoweredState(initial_p, ZERO, case.initial_soc * pack.pack_capacity_j)
    state = initial
    integral = 0.0
    initial_round_state=_round_state(state,integral,session)
    ledger=LapLedger(track.length_m,pack.pack_capacity_j,case.laps,initial.pack_energy_j)
    completed_work={'integration_substeps':0,'integration_trials':0,'wheel_stop_events':0}
    logging_stride=50 if case.laps==10 else 5
    status = "time_limit"
    records, violations = [], []
    max_slip = max_yaw = max_beta = max_util = max_cross = shortfall_impulse = rejected_regen = 0.0
    limited_ticks = 0
    previous_progress = 0.0
    finish_time = None
    last = None
    configured_frames,configured_outputs=[],[]
    audit=None
    compute_limits={}
    command=None
    frame={}
    output={}
    if configured_full_lap:
        from lapsim.torque_configurator.acceptance import BoundaryAudit,work_plan
        audit=BoundaryAudit(configured_profile)
        compute_limits=work_plan(configured_profile,round(case.duration_s*1000),ten_lap=case.laps==10)
    for tick in range(round(case.duration_s / .01) + 1):
        time_s = tick / 100
        p = state.plant
        try:
            projection = _project_local(track, p.x_m, p.y_m, previous_progress, 12.0)
            crossed=ledger.observe(time_s,projection.station_m,state.pack_energy_j) if case.laps==10 else []
            if crossed:
                carried=_round_state(state,integral,session)
                crossed[-1]['post_crossing_state']=carried
                crossed[-1]['carry_state_sha256']=_state_digest(carried)
                crossed[-1]['lap_numerical_work']={key:getattr(state,key) for key in completed_work}
                for key in completed_work:completed_work[key]+=getattr(state,key)
                state=replace(state,integration_substeps=0,integration_trials=0,wheel_stop_events=0)
                if _round_state(state,integral,session)!=carried:raise ValueError('lap state reset changed physical/controller state')
                if progress_callback is not None:
                    progress_callback(json.loads(json.dumps(crossed[-1],allow_nan=False)))
            if case.laps==10 and len(ledger.rows)<10 and time_s-ledger.boundary_time>=60:
                violations.append('lap_time_limit')
            slack = _assumed_footprint_slack(track, car, driver, p, projection.station_m)
            if tick % 5 == 0:
                command, _ = _controller(track, driver_car, PlanarEnvironment(), driver,
                                          p, projection, slack)
            assert command is not None
            # Feedback uses the same held steering as the powered plant. Zero
            # steering changes wheel-plane slip and the estimated tire reserve.
            physical = evaluate_planar_dynamics(car, p,
                PlanarControls(steering_angles_rad=command.steering_angles_rad,wheel_radii_m=radii), environment=env)
            max_slip = max(max_slip, *(abs(w.slip_ratio) for w in physical.wheels))
            max_yaw = max(max_yaw, abs(p.yaw_rate_rad_s))
            max_beta = max(max_beta, abs(atan2(p.v_mps, max(.5, p.u_mps))))
            max_util = max(max_util, *(w.force_utilization for w in physical.wheels))
            max_cross = max(max_cross, abs(projection.cross_track_m))
            if configured_profile is None:
                requested, proposed, limited, brakes, integral, shortfall, raw_regen = allocate(
                    controller, state, physical, command.steering_angles_rad[0],
                    command.drive_torques_nm[2], command.brake_torques_nm[0],
                    integral, replace(car, tire_mu=driver_car.tire_mu), pack, case)
            else:
                assert session is not None
                accelerator=min(1.,max(0.,sum(command.drive_torques_nm)/(2*driver.maximum_rear_drive_torque_nm)))
                # Record a common 20 ms zero-demand initialization phase. The
                # imported fault owner still requires unsaturated recovery.
                if tick<2:accelerator=0.
                braking=min(1.,max(command.brake_torques_nm)/driver.maximum_wheel_brake_torque_nm)
                frame={'now_ms':tick*10,'timestamp_ms':tick*10,'accelerator_fraction':accelerator,'brake_fraction':braking,
                    'steering_rad':command.steering_angles_rad[0],'wheel_speeds_rad_s':list(p.wheel_speeds_rad_s),
                    'pack_energy_j':state.pack_energy_j,'valid':True,'enabled':True,'restart_requested':False,'wheel_available':list(available)}
                if session.experimental:
                    frame.update(u_mps=p.u_mps,v_mps=p.v_mps,yaw_rate_rad_s=p.yaw_rate_rad_s,actuator_memory_nm=list(state.actuator_memory_nm),
                        regen_available=case.regen_available,motor_temperature_c=case.motor_temperature_c,friction_fallback=case.friction_fallback)
                output=session.step(frame);configured_frames.append(frame);configured_outputs.append(output)
                requested=tuple(accelerator*configured_profile.policy['maximum_drive_request_nm']/sum(available) if v else 0. for v in available)
                proposed=tuple(output['controller']['allocator']['wheel_torque_nm'])
                limited=ActuationEvaluation(**output['limited'])
                present=constrain_actuation(pack,state.actuator_memory_nm,p.wheel_speeds_rad_s,state.pack_energy_j,.01,available)
                capacity=configured_profile.policy['maximum_friction_brake_nm']
                if braking>0:
                    brakes,shortfall=friction_blend(4*capacity*braking,0.,sum(max(0.,-v) for v in present.wheel_torques_nm),
                        sum(max(0.,v) for v in present.wheel_torques_nm),fallback=True,capacity_nm=capacity,shares=(.25,)*4)
                else:brakes,shortfall=ZERO,0.
                raw_regen=0.
                if session.experimental:
                    brakes=tuple(output['friction_nm']);shortfall=output['brake_shortfall_nm'];raw_regen=output['raw_regen_nm']
            rate, achieved_physical, actual = evaluate_powered(car, pack, state, limited.wheel_torques_nm,
                command.steering_angles_rad, brakes, available, .01, env,wheel_radii_m=radii)
            if audit is not None:
                violations.extend('configured_constraint:'+name for name in audit.observe(frame,output,actual,rate,brakes,shortfall))
            for reason, bad in (("corridor", slack < 0), ("sideslip", max_beta > .5),
                                ("yaw", max_yaw > 2), ("wheel_slip", max_slip > 1),
                                ("road_domain", not all(w.road_valid for w in physical.wheels)),
                                ("pack_voltage", case.pack_voltage_v > 600),
                                ("thermal", case.motor_temperature_c >= 100),
                                ("brake_shortfall", shortfall > 1e-6)):
                if bad and reason not in violations:
                    violations.append(reason)
            terminal = bool(violations) or projection.station_m >= case.laps*track.length_m or tick == round(case.duration_s / .01)
            if tick % logging_stride == 0 or crossed or terminal:
                records.append({"t_s": time_s, "x_m": p.x_m, "y_m": p.y_m,
                    "heading_rad": p.heading_rad, "u_mps": p.u_mps, "v_mps": p.v_mps,
                    "yaw_rad_s": p.yaw_rate_rad_s, "progress_m": projection.station_m,
                    "cross_track_m": projection.cross_track_m, "slack_m": slack,
                    "wheel_omega_rad_s": list(p.wheel_speeds_rad_s),
                    "steering_rad": list(command.steering_angles_rad),
                    "slip": [w.slip_ratio for w in physical.wheels],
                    "utilization": [w.force_utilization for w in physical.wheels],
                    "requested_nm": list(requested), "proposed_nm": list(proposed),
                    "limited_nm": list(limited.wheel_torques_nm),
                    "achieved_nm": list(actual.wheel_torques_nm), "friction_nm": list(brakes),
                    "pack_energy_j": state.pack_energy_j, "pack_power_w": actual.pack_power_w,
                    "brake_shortfall_nm": shortfall, "constraints": list(limited.constraints)})
                if session is not None and session.experimental:
                    records[-1].update(policy_mode_code=output['controller']['mode_code'],brake_pedal_fraction=frame['brake_fraction'],regen_request_nm=raw_regen,pack_soc_ratio=state.pack_energy_j/pack.pack_capacity_j)
                if profile=='synthetic_spool_rwd':
                    records[-1]['axle_reaction_nm']=list(achieved_physical.axle_constraint_reactions_nm)
            if violations:
                status = "invalid"
                break
            if projection.station_m >= case.laps*track.length_m:
                status = "completed"
                before = last or (0.0, 0.0)
                fraction = (case.laps*track.length_m - before[1]) / max(1e-12, projection.station_m - before[1])
                finish_time = before[0] + .01 * fraction
                break
            if terminal:
                break
            limited_ticks += bool(limited.constraints)
            shortfall_impulse += shortfall * .01
            rejected_regen += max(0, raw_regen - sum(max(0, -t) for t in limited.wheel_torques_nm)) * .01
            last = (time_s, projection.station_m)
            previous_progress = projection.station_m
            options={'maximum_work':200000} if case.laps==10 or case.long_course else {'maximum_work':compute_limits['maximum_cumulative_trials_and_stop_events']} if configured_full_lap else {}
            state = advance_powered(car, pack, state, limited.wheel_torques_nm,
                command.steering_angles_rad, brakes, available, .01, env,wheel_radii_m=radii,**options)
        except (ValueError, ArithmeticError) as error:
            status = "model_error"
            violations.append(str(error))
            break
    residual = energy_residual_j(car, initial, state)
    if abs(residual) > .5:
        violations.append("energy_residual")
        status = "invalid"
    eligible = status == "completed" and not violations
    draw_kwh = (initial.pack_energy_j - state.pack_energy_j) / 3_600_000
    post_tick_draw_kwh=draw_kwh
    if case.laps==10 and eligible:
        draw_kwh=(initial.pack_energy_j-ledger.boundary_energy)/3_600_000
    # Explicit engineering proxy, not official competition points. Fixed
    # reference opposition/rule edition is needed before FSAE scoring is enabled.
    if eligible:
        assert finish_time is not None
        fitness=finish_time+120.0*draw_kwh
    else:fitness=None
    result={"controller": asdict(controller), "case": asdict(case), "profile": profile,
        "topology": {"motor_count": 1 if profile in ("synthetic_single_motor_rwd","synthetic_spool_rwd") else 4 if profile == "synthetic_awd" else 2,
            "differential": "ideal locked/spool" if profile=='synthetic_spool_rwd' else "ideal symmetric open" if profile == "synthetic_single_motor_rwd" else "independent actuators",
            "independent_yaw_authority": profile not in ("synthetic_single_motor_rwd","synthetic_spool_rwd"),
            "classification": "synthetic, not verified DTI/team hardware"},
        "status": status, "eligible": eligible, "violations": violations, "parameter_overrides": overrides,
        "metrics": {"lap_time_s": finish_time, "elapsed_s": records[-1]["t_s"] if records else 0,
            "completion_fraction": min(1, records[-1]["progress_m"] / (case.laps*track.length_m)) if records else 0,
            "net_energy_kwh": draw_kwh, "max_slip": max_slip, "max_yaw_rad_s": max_yaw,
            "max_sideslip_rad": max_beta, "max_tire_utilization": max_util,
            "max_cross_track_m": max_cross, "energy_residual_j": residual,
            "limited_ticks": limited_ticks, "brake_shortfall_nm_s": shortfall_impulse,
            "rejected_regen_nm_s": rejected_regen, "fitness": fitness},
        "telemetry": records, "car": asdict(car), "actuation": asdict(pack),
        "driver": asdict(driver), "environment": asdict(env),
        "course": {"x_m": list(track.x_m), "y_m": list(track.y_m),
            "length_m": track.length_m, "geometry_sha256": course_geometry_sha256(track),
            "label": CourseBundle.from_dict(case.course_bundle).label if case.course=='bundle' else case.course,
            "reverse": case.reverse, "mirror": case.mirror,
            "boundary_status": "assumed corridor, not surveyed boundaries",
            "audit": asdict(track.geometry_audit())},
        "clocks": {"controller_us": 10000, "driver_us": 50000, "logging_us": logging_stride*10000,
            "plant_max_internal_s": min(replace(car,wheel_radius_m=max(radii)).integration_step_limit_s,pack.actuator_time_constant_s/4)},
        "work": {"integration_substeps": completed_work['integration_substeps']+state.integration_substeps,
                 "integration_trials": completed_work['integration_trials']+state.integration_trials}}
    if profile=='synthetic_spool_rwd' or mismatch:
        result['contact_radii_m']=radii
        result['radius_model']='Declared plant contact radii; controller keeps nominal radius. Locked axle starts at one shared angular velocity, not four no-slip speeds.'
    if case.laps==10:
        result['round']={**ledger.summary(ledger.previous[0],ledger.previous[1],state.pack_energy_j),
            'initial_state_sha256':_state_digest(initial_round_state),'final_state_sha256':_state_digest(_round_state(state,integral,session)),
            'initial_state':initial_round_state,'final_state':_round_state(state,integral,session),
            'state_carry':'Continuous plant, battery, actuator memory, yaw integral and clocks; only numerical counters roll into a cumulative ledger at seams',
            'maximum_work_per_lap':200000,'maximum_round_work':2000000,'maximum_lap_s':60,
            'finish_energy_j':ledger.boundary_energy if eligible else state.pack_energy_j,
            'post_tick_net_energy_kwh':post_tick_draw_kwh,
            'energy_reporting':'Completed-round metrics sum interpolated lap crossings; final physical state/energy ledger remains at the accepted plant tick',
            'penalties':[] if eligible else [{'kind':'unfinished_or_invalid_round','unfinished_laps':10-len(ledger.rows),'reasons':violations or [status]}]}
        result['metrics']['round_time_s']=finish_time
        result['metrics']['mean_lap_time_s']=finish_time/10 if finish_time is not None else None
        result['metrics']['time_scope']='lap_time_s is a legacy field alias for total ten-lap round time'
    if case.course=='bundle':
        bundle=CourseBundle.from_dict(case.course_bundle)
        result['course']['input_evidence']={'source_kind':bundle.source_kind,'bundle_sha256':bundle.bundle_sha256,
            'provenance':bundle.to_dict()['provenance'],'scope':'Imported approximation/assumptions as recorded; not surveyed boundaries or official-event validation'}
    if configured_profile is not None:
        assert session is not None
        from .controller_backend import controller_source_identity
        result['configuration']={'schema':'lapsim.configured-rollout.v1','profile':configured_profile.to_dict(),
            'profile_sha256':configured_profile.sha256,'source':controller_source_identity(),
            'frames':configured_frames,'outputs':configured_outputs,
            'driver_mapping':{'zero_demand_initialization_ms':20,'accelerator':'sum(driver drive torque) / (2 * driver rear cap), bounded 0..1',
                              'brake':'driver brake fraction with existing residual-drive friction compensation, equal shares within profile cap; no regen'},
            'scope':'synthetic bounded course diagnostic; propulsive reference with driver friction; no lap ranking or calibrated hardware'}
        if session.experimental:
            result['controller']={'philosophy':'composed_policy','specification':configured_profile.to_dict()['controller']}
            result['configuration']['driver_mapping']['brake']='Shared experimental signed policy and actual-regen/friction compensation'
            result['configuration']['scope']='Shared experimental Python signed controller; reference freshness/fault gate; no portable C or hardware equivalence claim'
            result['configuration']['mode_occupancy']=session.experimental.occupancy
        result['metrics']['fitness']=None
        result['eligible']=False
        if configured_full_lap:
            assert audit is not None
            result['configuration']['mode']='ten_lap_acceptance_v1' if case.laps==10 else 'full_lap_acceptance_v1'
            result['configuration']['scope']='Synthetic configured acceptance; one lap/60 s or ten continuous laps/600 s, no calibrated hardware or official-points claim'
            result['configuration']['compute_limits']=compute_limits
            result['configuration']['acceptance']=audit.finish(result)
    return result
