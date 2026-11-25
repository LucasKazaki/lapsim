"""Deterministic synthetic closed-course torque experiments; SI throughout.

The fixed pure-pursuit driver is inherited from pose_driver. Only the torque
controller is selected/tuned. The existing powered four-wheel plant owns all
physical states and the RK energy ledger. No hardware backend is selected.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from itertools import count
import json
from struct import pack as pack_binary
from math import atan2, cos, hypot, isfinite, pi, remainder, sin, sqrt, tan

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Straight, Track
from lapsim.courses.course_bundle import CourseBundle, course_geometry_sha256
from lapsim.dynamics.actuation import ActuationConfig, ActuationEvaluation, constrain_actuation, AWD_TOPOLOGY_ID, SINGLE_MOTOR_RWD_TOPOLOGY_ID, SPOOL_RWD_TOPOLOGY_ID
from .lap_ledger import LapLedger
from lapsim.dynamics.conditions import PlanarEnvironment, PlanarRoad, RectangularGripPatch
from lapsim.dynamics.planar import PlanarState, evaluate_planar_dynamics, PlanarControls
from lapsim.dynamics.powered_planar import PoweredState, advance_powered, energy_residual_j, evaluate_powered, MAX_ALLOCATED_POWERED_WORK
from lapsim.experiments.closed_loop import synthetic_car
from lapsim.optimization.pose_driver import (
    PoseDriverSettings, _controller, _project_local, _reference_start_heading,
    _assumed_footprint_slack,
)

ZERO = (0.0, 0.0, 0.0, 0.0)
AVAILABLE = (False, False, True, True)
PHILOSOPHIES = ("fixed", "traction", "yaw_pi", "tire_reserve")
CONFIGURED_REFERENCE = 'configured_equal_split_reference_v1'
# The finite-finish opt-in keeps the existing per-allocation plant bound and
# the same cumulative envelope as the configured ten-lap allocation.
# Neither physical state, controller state, nor energy is restarted.
FINITE_TOTAL_WORK = 10 * MAX_ALLOCATED_POWERED_WORK
FINITE_BATCH_ROLLOVER = MAX_ALLOCATED_POWERED_WORK // 2
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
    pedal_mode: str = 'two_stage'

    def __post_init__(self):
        if self.philosophy not in (*PHILOSOPHIES,CONFIGURED_REFERENCE):
            raise ValueError("unsupported controller philosophy")
        if self.pedal_mode not in ('two_stage','proportional'):
            raise ValueError('unsupported regen pedal policy')
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
    duration_s: float | None = 30.0
    reverse: bool = False
    mirror: bool = False
    course_bundle: dict | None = None
    laps: int = 1
    long_course: bool = False

    def __post_init__(self):
        if type(self.laps) is not int or self.laps not in (1,2,10) or (self.laps==2 and self.duration_s is not None):
            raise ValueError('Choose a one-lap diagnostic, explicit two-lap finite round, or ten-lap competition')
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
                            ("motor_temperature_c", -20, 150)):
            number(getattr(self, key), key, lo, hi)
        if self.duration_s is None:
            if self.laps not in (1,2):
                raise ValueError('Finite-finish mode requires one or two laps')
        else:
            number(self.duration_s, "duration_s", .01, 600 if self.laps==10 else 300 if self.long_course else 60)
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
             integral, car, pack, case, dt=.01,*,audit=None):
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
    if audit is not None:
        audit.update(slip_binding=False,yaw_changed=False,reserve_binding=False,
            drive_scale_changed=drive_each>0 and controller.drive_scale!=1.,
            front_bias_used=drive_each>0 and abs(getattr(controller,'allocation_front_bias',.5)-.5)>1e-12)
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
            before=proposed[i]
            proposed[i] *= min(1.0, controller.slip_target / max(controller.slip_target, slips[i]))
            if audit is not None:audit['slip_binding']|=abs(before-proposed[i])>1e-8
    yaw_error = p.u_mps * tan(steering) / 1.6 - p.yaw_rate_rad_s
    integral = max(-1.0, min(1.0, integral + dt * yaw_error))
    if getattr(controller,'yaw_control',controller.philosophy=='yaw_pi') and drive_each > 0 and pack.topology_id not in (SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID):
        before_yaw=tuple(proposed)
        differential = max(-25.0, min(25.0, controller.yaw_kp * yaw_error
                                     + controller.yaw_ki * integral))
        # Right-positive torque produces left-positive yaw. Do not create
        # negative drive/regen on the inside as part of the yaw allocator.
        for left, right in (((0, 1), (2, 3)) if len(driven) == 4 else ((2, 3),)):
            total = proposed[left] + proposed[right]
            proposed[right] = max(0, min(total, proposed[right] + differential * 2 / len(driven)))
            proposed[left] = total - proposed[right]
        if audit is not None:audit['yaw_changed']=any(abs(a-b)>1e-8 for a,b in zip(before_yaw,proposed))
    nominal_lateral = abs(p.u_mps * p.yaw_rate_rad_s) * car.mass_kg / 4
    reserve = [sqrt(max(0.0, (.85 * car.tire_mu * load) ** 2 - nominal_lateral ** 2))
               * car.wheel_radius_m for load in car.static_normal_loads_n]
    if getattr(controller,'reserve_control',controller.philosophy=='tire_reserve'):
        for i in driven:
            before=proposed[i]
            proposed[i] = min(proposed[i], reserve[i])
            if audit is not None:audit['reserve_binding']|=abs(before-proposed[i])>1e-8
    total_brake, raw_regen = brake_request(min(1.0, brake_each / 80.0), controller)
    regen_ok = (case.regen_available and case.pack_voltage_v < 600.0
                and case.motor_temperature_c < 90 and p.u_mps > 2.0)
    if audit is not None:
        audit['regen_requested']=total_brake>0 and regen_ok
        audit['pedal_above_regen_region']=regen_ok and brake_each/80.>controller.regen_region
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


def physical_finish_contract(case: Case, configured_profile):
    """Explicit source-bound opt-in contract for the reviewed synthetic stadium.

    Imported, transformed, and measured courses are deliberately not admitted
    by this first implementation. Missing contracts never select the legacy
    projected finish. Canonical gate lists come from the configured car and
    built-in assumed corridor, not a caller's asserted digest or geometry.
    """
    from lapsim.torque_configurator import VehicleProfile
    from .finite_gate_observer import canonical_gate_contract
    if type(configured_profile) is not VehicleProfile:
        raise ValueError('A validated configured profile is required')
    if (case.course != 'stadium' or case.course_bundle is not None or case.reverse or case.mirror
            or case.long_course or case.initial_offset_m != 0.):
        raise ValueError('Finite finish is qualified only for the original synthetic stadium and its exact spawn')
    if case.duration_s is not None or case.laps not in (1,2):
        raise ValueError('Finite finish requires an explicit one- or two-lap terminal case')
    car=replace(configured_profile.vehicle,tire_mu=configured_profile.vehicle.tire_mu*case.grip)
    return canonical_gate_contract(course_for(case),fixture()[2],car)


def rollout(controller: Controller, case: Case, *, profile="synthetic_rwd", parameter_overrides=None, configured_profile=None, configured_full_lap=False,progress_callback=None,plant_step=None,physical_finish=False,stop_requested=None,finite_gate_contract=None):
    """Run the configured or legacy simulation.

    The physical finish path is opt-in, configured-only and synthetic-only.
    Existing default callers retain their original timed/projected results.
    """
    if progress_callback is not None and not callable(progress_callback):raise ValueError('Progress callback must be callable')
    if type(configured_full_lap) is not bool:raise ValueError('Configured full-lap mode must be Boolean')
    if plant_step is not None and not callable(plant_step):raise ValueError('Plant step must be callable')
    if plant_step is not None and configured_profile is not None:raise ValueError('Custom plant backend is not accepted for configured export equivalence')
    if type(physical_finish) is not bool:raise ValueError('Physical finish opt-in must be Boolean')
    duration_s=case.duration_s
    until_terminal=duration_s is None
    if physical_finish != until_terminal:
        raise ValueError('Uncapped terminal cases require explicit physical_finish opt-in; timed legacy cases do not')
    if physical_finish and (configured_profile is None or not configured_full_lap or case.laps not in (1,2)
                            or not callable(stop_requested) or finite_gate_contract is None):
        raise ValueError('Physical finish requires full configured acceptance, explicit finite gates, and cancellation callback')
    if not physical_finish and (stop_requested is not None or finite_gate_contract is not None):
        raise ValueError('Finite gates and cancellation callback belong only to explicit physical finish')
    if configured_profile is None:
        if configured_full_lap:raise ValueError('Full-lap configured acceptance requires its profile')
        if controller.philosophy==CONFIGURED_REFERENCE:raise ValueError('Configured strategy requires its exact vehicle profile')
        return _rollout(controller,case,profile=profile,parameter_overrides=parameter_overrides,progress_callback=progress_callback,plant_step=plant_step)
    from lapsim.torque_configurator import ControlSession,VehicleProfile
    from lapsim.torque_configurator.profile import require
    require(type(configured_profile) is VehicleProfile,'A validated configured profile is required')
    require(case.laps in (1,10) or (case.laps==2 and until_terminal),'Configured round requires one or ten laps, or explicit two-lap finite mode')
    aliases={'synthetic_independent_rear_rwd_v1':'synthetic_rwd',
             SINGLE_MOTOR_RWD_TOPOLOGY_ID:'synthetic_single_motor_rwd',SPOOL_RWD_TOPOLOGY_ID:'synthetic_spool_rwd',AWD_TOPOLOGY_ID:'synthetic_awd'}
    require(profile==aliases[configured_profile.actuation.topology_id],'Configured profile/tournament topology mismatch')
    require(controller==Controller(CONFIGURED_REFERENCE),'Configured profile supports only its exact equal-split reference strategy; no strategy/tuning substitution')
    require(not parameter_overrides,'Configured profiles cannot have unrecorded physical overrides')
    maximum=600 if case.laps==10 and configured_full_lap else 60 if configured_full_lap else 2
    if duration_s is not None:
        require(.1<=duration_s<=maximum and abs(duration_s*1000-round(duration_s*1000))<1e-9
                and round(duration_s*1000)%10==0,'Configured duration exceeds its explicit mode bound or 10 ms clock')
    require(case.pack_voltage_v==configured_profile.actuation.pack_voltage_v and case.initial_soc==configured_profile.policy['initial_soc'],
            'Case voltage/SOC conflicts with configured profile')
    require(configured_profile.to_dict()['schema']=='lapsim.torque-profile.v2' or (not case.regen_available and case.friction_fallback and case.motor_temperature_c==40.),
            'Configured propulsive baseline requires explicit no-regen/friction scenario; thermal calibration is unavailable')
    if physical_finish:
        from .finite_gate_observer import validate_canonical_contract
        finite_gate_contract=validate_canonical_contract(finite_gate_contract,physical_finish_contract(case,configured_profile))
    session=ControlSession(configured_profile)
    try:return _rollout(controller,case,profile=profile,configured_profile=configured_profile,session=session,configured_full_lap=configured_full_lap,progress_callback=progress_callback,stop_requested=stop_requested,finite_gate_contract=finite_gate_contract)
    finally:session.close()


def _round_state(state,integral,session=None):
    value=asdict(state)
    for key in ('integration_substeps','integration_trials','wheel_stop_events'):value.pop(key)
    value['controller_yaw_integral']=integral
    if session is not None:value['configured_controller_state']=session.state_snapshot()
    return value


def _state_digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _rollout(controller, case, *, profile, parameter_overrides=None, configured_profile=None, session=None, configured_full_lap=False,progress_callback=None,plant_step=None,stop_requested=None,finite_gate_contract=None):
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
    duration_s=case.duration_s
    timed_ticks=round(duration_s/.01) if duration_s is not None else None
    until_terminal=duration_s is None
    finite_owner=None
    finite_cycle=None
    first_projected_boundary=None
    if duration_s is None:
        from .finite_gate_observer import FiniteGateObserver, canonical_gate_contract, validate_canonical_contract
        from .finite_cycle_ledger import CyclicGateLedger
        if (configured_profile is None or not configured_full_lap or session is None or
                not callable(stop_requested)):
            raise ValueError('Finite finish requires the configured runner')
        # Bind the supplied contract again at the actual source/vehicle
        # boundary. No caller-provided width or gate order overrides it.
        approved=physical_finish_contract(case,configured_profile)
        canonical=canonical_gate_contract(track,driver,replace(car,tire_mu=car.tire_mu*case.grip))
        if canonical!=approved:raise ValueError('Actual source differs from the admitted physical-finish contract')
        finite_gate_contract=validate_canonical_contract(finite_gate_contract,canonical)
        if case.laps==1:
            finite_owner=FiniteGateObserver(finite_gate_contract)
        else:
            finite_cycle=CyclicGateLedger(finite_gate_contract)
            finite_owner=finite_cycle
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
    # The fixed timed/ten-lap owner remains unchanged. In the new scope the
    # finite ledger alone owns lap count; it receives actual accepted poses.
    finite_round=finite_cycle is not None
    ledger=None if finite_round else LapLedger(track.length_m,pack.pack_capacity_j,case.laps,initial.pack_energy_j)
    seam_states=[]
    completed_work={'integration_substeps':0,'integration_trials':0,'wheel_stop_events':0}
    accepted_ticks=0
    last_checked=None
    stationary_anchor=None
    work_rollovers=[]
    terminal_detail=None
    logging_stride=50 if case.laps==10 else 5
    status = "running" if until_terminal else "time_limit"
    records, violations = [], []
    max_slip = max_yaw = max_beta = max_util = max_cross = shortfall_impulse = rejected_regen = 0.0
    limited_ticks = 0
    gross_pack_draw_j=recovered_pack_j=0.0
    policy_modes={};policy_changed_ticks=generating_ticks=0
    policy_interventions={};policy_command_digest=sha256()
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
        if duration_s is None:
            compute_limits={'maximum_duration_s':None,'maximum_controller_observations':None,
                'per_allocation_trials_and_stop_events':MAX_ALLOCATED_POWERED_WORK,
                'rollover_at_trials_and_stop_events':FINITE_BATCH_ROLLOVER,
                'maximum_cumulative_trials_and_stop_events':FINITE_TOTAL_WORK,
                'scope':'Explicit finite-finish allocation; continuous accepted state, original per-allocation plant checks, external cancellation'}
        else:
            compute_limits=work_plan(configured_profile,round(duration_s*1000),ten_lap=case.laps==10)
    for tick in (count() if timed_ticks is None else range(timed_ticks+1)):
        time_s = tick / 100
        p = state.plant
        current_budget=None
        try:
            projection = _project_local(track, p.x_m, p.y_m, previous_progress, 12.0)
            crossed=[]
            if case.laps==10:
                if ledger is None:raise ValueError('Missing legacy timed-round ledger')
                crossed=ledger.observe(time_s,projection.station_m,state.pack_energy_j)
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
            if case.laps==10:
                if ledger is None:raise ValueError('Missing legacy timed-round ledger')
                if len(ledger.rows)<10 and time_s-ledger.boundary_time>=60:
                    violations.append('lap_time_limit')
            slack = _assumed_footprint_slack(track, car, driver, p, projection.station_m)
            if until_terminal:
                if tick != accepted_ticks:
                    raise ValueError('Accepted control clock differs from the terminal-run clock')
                last_checked={'tick':tick,'t_s':time_s,'progress_m':projection.station_m,'slack_m':slack,
                              'x_m':p.x_m,'y_m':p.y_m}
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
                effective=controller
                policy_audit=None
                if hasattr(controller,'effective_policy'):
                    effective,mode=controller.effective_policy(state,command.steering_angles_rad[0],car,pack)
                    policy_modes[mode]=policy_modes.get(mode,0)+1
                    policy_audit={}
                requested, proposed, limited, brakes, integral, shortfall, raw_regen = allocate(
                    effective, state, physical, command.steering_angles_rad[0],
                    command.drive_torques_nm[2], command.brake_torques_nm[0],
                    integral, replace(car, tire_mu=driver_car.tire_mu), pack, case,audit=policy_audit)
                if policy_audit is not None:
                    for key,active in policy_audit.items():policy_interventions[key]=policy_interventions.get(key,0)+int(active)
                    policy_interventions['economy_scale_changed']=policy_interventions.get('economy_scale_changed',0)+int(effective.drive_scale!=controller.drive_scale)
                    # Diagnostic rounding only; executed commands are untouched.
                    policy_command_digest.update(pack_binary('12d',
                        *(round(v,10) for v in command.steering_angles_rad),
                        *(round(v,8) for v in (*limited.wheel_torques_nm,*brakes))))
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
            policy_changed_ticks+=sum(requested)>0 and any(abs(a-b)>1e-8 for a,b in zip(requested,proposed))
            generating_ticks+=actual.pack_power_w<0
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
            stalled=external_stop=resource_exhausted=False
            stock_violation=bool(violations)
            projected_finish=projection.station_m >= case.laps*track.length_m
            finish_now=projected_finish
            if until_terminal:
                assert finite_owner is not None
                # Only accepted physical boundaries enter the observer. Do
                # not change the driver, projection, command, or RK step; a
                # projected seam by itself merely records a diagnostic.
                if finite_cycle is not None:
                    count_before=finite_cycle.completed_count
                    before_carry=_round_state(state,integral,session)
                    finish_now=finite_cycle.observe(tick,(p.x_m,p.y_m),state.pack_energy_j,projection.station_m,
                                                    boundary_ok=not stock_violation)
                    if finite_cycle.completed_count != count_before:
                        carried=_round_state(state,integral,session)
                        if carried!=before_carry:
                            raise ValueError('Finite lap ledger changed physical/controller state')
                        crossed=finite_cycle.rows[-1:]
                        seam_states.append({'lap':finite_cycle.completed_count,'accepted_tick':tick,
                            'accepted_state':carried,'carry_state_sha256':_state_digest(carried),
                            'before_ledger_sha256':_state_digest(before_carry),
                            'accepted_work':{key:completed_work[key]+getattr(state,key) for key in completed_work},
                            'accepted_frame':frame,'accepted_output_sha256':_state_digest(output),
                            'following_interval_integrated':False})
                else:
                    finish_now=finite_owner.observe(tick,(p.x_m,p.y_m),state.pack_energy_j,projection.station_m,
                                                    boundary_ok=not stock_violation)
                failure=finite_owner.failure
                if failure is not None and failure['reason']!='stock_boundary_rejected':
                    violations.append('finite_gate:'+failure['reason'])
                if projected_finish and first_projected_boundary is None:
                    if last_checked is None:raise ValueError('Missing accepted projection observation')
                    before=last or (0.,0.)
                    fraction=(case.laps*track.length_m-before[1])/max(1e-12,projection.station_m-before[1])
                    first_projected_boundary={**last_checked,'legacy_projected_finish_s':before[0]+.01*fraction,
                        'confirmed_gate_count':finite_cycle.confirmed_gate_count if finite_cycle is not None else len(finite_owner.events),'signed_finish_m':finite_owner.receipt()['last_signed_finish_m'],
                        'accepted_state':_round_state(state,integral,session),
                        'accepted_work':{key:completed_work[key]+getattr(state,key) for key in completed_work}}
                # Genuine stationary loss of progress, not elapsed race time:
                # five consecutive simulated seconds at near-zero body speed
                # and yaw, with <=0.25 m motion and <=0.25 m station change.
                if hypot(p.u_mps,p.v_mps)<=.05 and abs(p.yaw_rate_rad_s)<=.05:
                    if (stationary_anchor is None or
                            hypot(p.x_m-stationary_anchor[1],p.y_m-stationary_anchor[2])>.25 or
                            abs(projection.station_m-stationary_anchor[3])>.25):
                        stationary_anchor=(tick,p.x_m,p.y_m,projection.station_m)
                    stalled=tick-stationary_anchor[0]>=500
                else:
                    stationary_anchor=None
                if stop_requested is None:raise ValueError('Missing finite-finish cancellation callback')
                external_stop=stop_requested()
                if type(external_stop) is not bool:raise ValueError('Cancellation callback must return a Boolean')
                resource_exhausted=(completed_work['integration_trials']+completed_work['wheel_stop_events']+
                    state.integration_trials+state.wheel_stop_events)>=FINITE_TOTAL_WORK
            terminal = (bool(violations) or finish_now or
                        (timed_ticks is not None and tick == timed_ticks) or
                        stalled or external_stop or resource_exhausted)
            if tick % logging_stride == 0 or crossed or terminal or (until_terminal and first_projected_boundary is not None):
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
            if until_terminal and progress_callback is not None and (tick%500==0 or terminal or (finite_round and crossed)):
                report={'accepted_tick':tick,'t_s':time_s,'progress_m':projection.station_m,
                    'course_length_m':track.length_m,'slack_m':slack,
                    'accepted_substeps':completed_work['integration_substeps']+state.integration_substeps,
                    'integration_trials':completed_work['integration_trials']+state.integration_trials,
                    'external_stop_requested':external_stop,'terminal_observed':terminal}
                if finite_cycle is not None:
                    report.update(finite_completed_laps=finite_cycle.completed_count,
                                  finite_confirmed_gates=finite_cycle.confirmed_gate_count)
                progress_callback(report)
            if violations:
                status = "invalid"
                # An actual stock fault (including brake shortfall) takes
                # precedence over the observer's "stock_boundary_rejected"
                # marker. Preserve independent finite failures in the audit.
                terminal_detail='Existing stock rollout violation' if stock_violation else 'Ordered finite gate violation'
                break
            if finish_now:
                status = "completed"
                if until_terminal:
                    assert finite_owner is not None and finite_owner.done
                    finish_event=finite_owner.finish
                    if finish_event is None:raise ValueError('Missing confirmed finite finish event')
                    finish_time=finish_event['time_s']
                    terminal_detail='Accepted ordered finite gate crossing'
                else:
                    before = last or (0.0, 0.0)
                    fraction = (case.laps*track.length_m - before[1]) / max(1e-12, projection.station_m - before[1])
                    finish_time = before[0] + .01 * fraction
                    terminal_detail='Existing stock projected seam crossing'
                break
            if terminal:
                if until_terminal:
                    if external_stop:
                        status="external_stop"
                        terminal_detail='Host cancellation requested at an accepted control boundary'
                    elif resource_exhausted:
                        status="external_resource_limit"
                        terminal_detail='Separate cumulative numerical work allocation exhausted'
                    elif stalled:
                        status="no_progress"
                        terminal_detail='Genuine stationary accepted-state window'
                break
            limited_ticks += bool(limited.constraints)
            shortfall_impulse += shortfall * .01
            rejected_regen += max(0, raw_regen - sum(max(0, -t) for t in limited.wheel_torques_nm)) * .01
            last = (time_s, projection.station_m)
            previous_progress = projection.station_m
            if until_terminal:
                # Existing round-state pattern: at an accepted 10 ms boundary,
                # preserve exact physical/controller state, account the old
                # numerical allocation, and start another bounded allocation.
                if state.integration_trials+state.wheel_stop_events>=FINITE_BATCH_ROLLOVER:
                    carried=_round_state(state,integral,session)
                    counts={key:getattr(state,key) for key in completed_work}
                    for key in completed_work:completed_work[key]+=counts[key]
                    state=replace(state,integration_substeps=0,integration_trials=0,wheel_stop_events=0)
                    if _round_state(state,integral,session)!=carried:
                        raise ValueError('Finite-finish work rollover changed physical/controller state')
                    work_rollovers.append({'accepted_tick':tick,'t_s':time_s,'prior_allocation':counts,
                        'cumulative_accounted':dict(completed_work),'carry_state_sha256':_state_digest(carried)})
                remaining=FINITE_TOTAL_WORK-completed_work['integration_trials']-completed_work['wheel_stop_events']
                current_budget=min(MAX_ALLOCATED_POWERED_WORK,remaining)
                options={'maximum_work':current_budget}
            else:
                options={'maximum_work':200000} if case.laps==10 or case.long_course else {'maximum_work':compute_limits['maximum_cumulative_trials_and_stop_events']} if configured_full_lap else {}
            before_pack_j=state.pack_energy_j
            stepper=advance_powered if plant_step is None else plant_step
            state = stepper(car, pack, state, limited.wheel_torques_nm,
                command.steering_angles_rad, brakes, available, .01, env,wheel_radii_m=radii,**options)
            accepted_ticks+=1
            if finite_round and crossed:
                seam_states[-1]['following_interval_integrated']=True
                following=_round_state(state,integral,session)
                seam_states[-1]['following_accepted_tick']=accepted_ticks
                seam_states[-1]['following_accepted_state']=following
                seam_states[-1]['following_accepted_state_sha256']=_state_digest(following)
                seam_states[-1]['following_accepted_work']={key:completed_work[key]+getattr(state,key) for key in completed_work}
            delta_pack_j=before_pack_j-state.pack_energy_j
            gross_pack_draw_j+=max(0.,delta_pack_j)
            recovered_pack_j+=max(0.,-delta_pack_j)
        except (ValueError, ArithmeticError) as error:
            if (until_terminal and current_budget is not None and current_budget<MAX_ALLOCATED_POWERED_WORK
                    and str(error)=="powered integration exceeds the actual work budget"):
                status="external_resource_limit"
                terminal_detail=str(error)+' (remaining cumulative finite-finish allocation)'
            else:
                status = "model_error"
                violations.append(str(error))
                terminal_detail=str(error)
            break
    residual = energy_residual_j(car, initial, state)
    if abs(residual) > .5:
        if until_terminal and status == "completed":
            terminal_detail='Existing stock rollout violation'
        violations.append("energy_residual")
        status = "invalid"
    eligible = status == "completed" and not violations
    if until_terminal and not eligible:
        finish_time=None
    draw_kwh = (initial.pack_energy_j - state.pack_energy_j) / 3_600_000
    post_tick_draw_kwh=draw_kwh
    if case.laps==10 and eligible:
        if ledger is None:raise ValueError('Missing legacy timed-round ledger')
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
            "gross_pack_draw_kwh_10ms":gross_pack_draw_j/3_600_000,
            "recovered_pack_kwh_10ms":recovered_pack_j/3_600_000,
            "pack_delta_net_kwh_10ms":(gross_pack_draw_j-recovered_pack_j)/3_600_000,
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
    if until_terminal:
        result['metrics']['elapsed_s']=accepted_ticks/100
        assert finite_owner is not None
        accepted_completion=bool(eligible and finite_owner.done)
        count_gates=finite_cycle.confirmed_gate_count if finite_cycle is not None else len(finite_owner.events)
        result['metrics']['completion_fraction']=1.0 if accepted_completion else min(count_gates,finite_owner.n-1)/finite_owner.n
        result['work']['wheel_stop_events']=completed_work['wheel_stop_events']+state.wheel_stop_events
        finite_receipt=finite_owner.receipt()
        finish_event=finite_owner.finish if accepted_completion else None
        if accepted_completion and finish_event is None:raise ValueError('Missing confirmed finite finish event')
        # A physical event observed on a rejected whole round is not an
        # accepted terminal time. Leave the raw event audit for diagnosis.
        if not accepted_completion:
            finite_receipt['finish_event']=None
        result['finite_terminal']={'schema':'lapsim.configured-finite-terminal.v1','maximum_simulated_time_s':None,
            'status':status,'detail':terminal_detail,'accepted_ticks':accepted_ticks,
            'accepted_sim_time_s':accepted_ticks/100,'last_checked_projection':last_checked,
            'accepted_state':_round_state(state,integral,session),'work_rollovers':work_rollovers,
            'current_allocation':{key:getattr(state,key) for key in completed_work},
            'cumulative_accounted_before_current':dict(completed_work),
            'cumulative_work_limit':FINITE_TOTAL_WORK,'per_allocation_limit':MAX_ALLOCATED_POWERED_WORK,
            'finish_scope':'Ordered finite CG intersections on accepted 10ms chords of the fixed assumed corridor; separate body and actuator checks still required',
            'completion_owner':'ordered_finite_round_v1' if finite_round else 'ordered_finite_gate_v1',
            'finite_completion':{**finite_receipt,'accepted_completion':accepted_completion,
                'first_legacy_projection_boundary':first_projected_boundary,
                'extra_accepted_intervals_after_projection':accepted_ticks-first_projected_boundary['tick'] if first_projected_boundary is not None else 0,
                'old_projected_fraction':min(1,last_checked['progress_m']/(track.length_m*case.laps)) if last_checked is not None else 0.,
                'finite_crossing_net_energy_kwh':(initial.pack_energy_j-finish_event['interpolated_pack_energy_j'])/3_600_000 if finish_event is not None else None}}
        if finite_cycle is not None:
            result['metrics']['round_time_s']=finish_time
            result['metrics']['mean_lap_time_s']=finish_time/case.laps if finish_time is not None else None
            result['metrics']['time_scope']='lap_time_s is a legacy field alias for total two-lap finite round time'
            result['round']={'schema':'lapsim.finite-round.v1','target_laps':case.laps,
                'completed_laps':finite_cycle.completed_count,'lap_rows':finite_cycle.rows,
                'incomplete_lap':None if finite_cycle.done else finite_cycle.completed_count+1,
                'seam_states':seam_states,'initial_state':initial_round_state,
                'initial_state_sha256':_state_digest(initial_round_state),
                'final_state_sha256':_state_digest(_round_state(state,integral,session)),
                'final_state':_round_state(state,integral,session),
                'post_tick_net_energy_kwh':post_tick_draw_kwh,
                'finite_crossing_net_energy_kwh':result['finite_terminal']['finite_completion']['finite_crossing_net_energy_kwh'],
                'state_carry':'One continuous plant, pack, actuator memory, controller session, global clocks; finite observer alone renews its expected gate list. No per-lap physical or numerical reset.',
                'energy_reporting':'Each lap uses consecutive interpolated physical crossing energies. Existing net_energy_kwh remains actual accepted-boundary pack delta.',
                'penalties':[] if accepted_completion else [{'kind':'unfinished_or_invalid_round',
                    'unfinished_laps':case.laps-finite_cycle.completed_count,'reasons':violations or [status]}]}
    if profile=='synthetic_spool_rwd' or mismatch:
        result['contact_radii_m']=radii
        result['radius_model']='Declared plant contact radii; controller keeps nominal radius. Locked axle starts at one shared angular velocity, not four no-slip speeds.'
    if hasattr(controller,'effective_policy'):
        result['search_policy']={'structure':controller.structure,'regen_mode':controller.regen_mode,
            'mode_occupancy':policy_modes,'drive_policy_changed_ticks':policy_changed_ticks,
            'intervention_ticks':policy_interventions,'command_digest':policy_command_digest.hexdigest(),
            'command_digest_scope':'All evaluated 100 Hz boundaries; steering rounded only for diagnostic digest to 1e-10 rad, limited torque/friction to 1e-8 Nm; executed values unrounded',
            'generating_boundary_ticks':generating_ticks,'scope':'Evaluated 10 ms controller boundaries, including terminal boundary; actual mode/intervention observations, not proof every gene activated'}
    if case.laps==10:
        if ledger is None:raise ValueError('Missing legacy timed-round ledger')
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
            result['configuration']['mode']='finite_finish_acceptance_v1' if until_terminal else 'ten_lap_acceptance_v1' if case.laps==10 else 'full_lap_acceptance_v1'
            result['configuration']['scope']='Explicit synthetic finite finish; stock controller-boundary audit, no surveyed geometry or calibrated hardware' if until_terminal else 'Synthetic configured acceptance; one lap/60 s or ten continuous laps/600 s, no calibrated hardware or official-points claim'
            if until_terminal:result['configuration']['completion_owner']='ordered_finite_round_v1' if finite_round else 'ordered_finite_gate_v1'
            result['configuration']['compute_limits']=compute_limits
            result['configuration']['acceptance']=audit.finish(result)
            if finite_cycle is not None:
                acc=result['configuration']['acceptance']
                checks=acc['checks']
                checks.update(two_ordered_finite_laps=bool(eligible and finite_cycle.done and finite_cycle.completed_count==2 and finite_cycle.confirmed_gate_count==2*finite_cycle.gates_per_lap),
                    continuous_seam_carry=len(seam_states)==2 and all(z['carry_state_sha256']==z['before_ledger_sha256'] for z in seam_states)
                    and seam_states[0]['following_interval_integrated'] and not seam_states[-1]['following_interval_integrated'])
                acc['passed']=all(checks.values())
    return result
