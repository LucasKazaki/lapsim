"""Independent finite standing-drag replay, reached only by the admitted parent.

No owner, admission, process, filesystem, transport, or simulation entry point is
provided here. Each call reconstructs a fresh canonical plant and replays every
physical tick under the SAME parent's semantic/resource/deadline/stop callback.
The returned record is semantic evidence, never POST or cleanup authority.
"""
from dataclasses import asdict
from hashlib import sha256
from math import cos, hypot, isfinite, sin, pi
import struct

from lapsim.learning.live.initialization import canonical, construct, digest
from lapsim.learning.live.row_codec import (
    EncodedRows, block_count, MAX_OPERATION_EXPANDED,
)
from lapsim_light_core.torque_light_combined import advance_combined_light
from lapsim_light_core.torque_light_thermal import evaluate_thermal_light


STAGING = {'schema': 'lapsim.fsae-staged-straight-timing.v1', 'start_gate_m': 0.0, 'finish_gate_m': 75.0, 'foremost_initial_gate_coordinate_m': -0.3, 'launch_speed_mps': 0.0, 'wheel_speeds_rad_s': [0.0, 0.0, 0.0, 0.0], 'reference': 'body CG; longitudinal projection on initial heading; front support of symmetric rectangle', 'body_half_length_m': 1.0, 'body_half_width_m': 0.7, 'geometry_status': 'inherited modeled symmetric footprint; bumper/CG dimensions not measured', 'gate_time': 'first foremost-part finish crossing minus first foremost-part start crossing', 'interpolation': 'linear crossing time and velocity between accepted1ms endpoints; endpoint retained'}

def replay_nose_coordinate(point, origin):
    dx,dy=point.x_m-origin.x_m,point.y_m-origin.y_m
    relative=point.heading_rad-origin.heading_rad
    longitudinal=cos(origin.heading_rad)*dx+sin(origin.heading_rad)*dy
    support=1.*abs(cos(relative))+.7*abs(sin(relative))
    return longitudinal+support-(1.+.30)

def replay_crossing(low, high, gate, tick, prior, endpoint):
    if low < gate <= high:
        portion=(gate-low)/(high-low)
        _require(isfinite(portion) and 0 < portion <= 1., 'finite first crossing fraction required')
        u=prior.u_mps+(endpoint.u_mps-prior.u_mps)*portion
        v=prior.v_mps+(endpoint.v_mps-prior.v_mps)*portion
        return dict(fraction=portion, elapsed_s=(tick+portion)/1000., speed_mps=hypot(u,v),
            interpolation='time and velocity only; physical endpoint retained, no synthetic state continuation')
    return None

TARGET_M = 75.
MAX_TICKS = 8000
MAX_WORK = 4000000
MAX_TICK_WORK = 50000
MAX_EVIDENCE = 33554432
MAX_TRACE_ROWS = MAX_TICKS + 2
CASES = ('driver_full_pedal', 'configured_motor_full_throttle')


def _require(value, message):
    if not value:
        raise ValueError(message)


def _same(actual, expected, message):
    # JSON numeric spelling, signed zero, shape and EVERY field remain exact.
    _require(canonical(actual) == canonical(expected), message)


def _pin(value):
    return (type(value) is str and len(value) == 64
            and all(c in '0123456789abcdef' for c in value))


def _work(state):
    powered = state.thermal.light.powered
    return powered.integration_trials + powered.wheel_stop_events


def _encoded_rows(ctx, raw):
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_EVIDENCE,
             'immutable bounded drag trace required')
    offset = count = expanded = 0
    while offset < len(raw):
        ctx.semantic_check()
        _require(offset + 5 <= len(raw), 'truncated drag frame header')
        tag = raw[offset:offset + 1]
        size = struct.unpack_from('>I', raw, offset + 1)[0]
        offset += 5
        _require(0 < size <= 1048576 and offset + size <= len(raw),
                 'bounded complete drag frame required')
        if tag == b'Z':
            payload = raw[offset:offset + size]
            count += block_count(payload)
            expanded += struct.unpack_from('>I', payload, 8)[0]
        else:
            _require(tag == b'R', 'only captured drag Z/R frames accepted')
            count += 1
            expanded += size + 5
        offset += size
        _require(count <= MAX_TRACE_ROWS and expanded < MAX_OPERATION_EXPANDED,
                 'finite drag row/expanded budget exceeded')
    _require(3 <= count <= MAX_TRACE_ROWS, 'construction, feedback and summary required')
    # Fresh iterator validates decompression/checksum/EOF/duplicates/nonfinite/
    # canonical JSON and exact actual row count, not just declarations above.
    return EncodedRows(raw, count, MAX_TRACE_ROWS), count, expanded


def verify_drag(ctx, raw_zframes: bytes, summary: dict, *, stage: str) -> dict:
    """Replay ONE freshly admitted case; a second call repeats all construction.

    ctx.operation_id, drag_throttle_case and manifest_sha must be independently
    bound by the original parent, never obtained from the worker's trace. The
    caller retains original source POST, Job/lease closure and admission checks.
    """
    _require(type(stage) is str and 0 < len(stage) <= 128,
             'named independent semantic stage required')
    _require(type(summary) is dict and callable(ctx.semantic_check),
             'complete bounded summary and original semantic callback required')
    operation = ctx.operation_id
    case = ctx.drag_throttle_case
    _require(type(operation) is str and 1 <= len(operation) <= 128
             and all(c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in operation),
             'parent-generated native operation identity required')
    _require(type(case) is str and case in CASES and _pin(ctx.manifest_sha),
             'independently bound drag case/source required')
    ctx.semantic_check()
    rows, row_count, expanded = _encoded_rows(ctx, raw_zframes)
    iterator = iter(rows)
    ctx.semantic_check()
    plant = construct(ctx.input_bytes)
    ctx.semantic_check()
    _require(plant.construction_record.get('start_mode') == 'standing',
             'corrected standing-start construction required')
    state = plant.state
    initial = asdict(state)
    origin = state.thermal.light.powered.plant
    _require((origin.u_mps, origin.v_mps, origin.yaw_rate_rad_s,
              *origin.wheel_speeds_rad_s) == (0.,) * 7,
             'canonical drag starts fully at rest')
    car = plant.settings.forces.plant
    c, s = cos(origin.heading_rad), sin(origin.heading_rad)

    def distance(point):
        return (point.x_m - origin.x_m) * c + (point.y_m - origin.y_m) * s

    def lateral(point):
        return -(point.x_m - origin.x_m) * s + (point.y_m - origin.y_m) * c

    # Derive from canonical profile/actuator independently of drag_command().
    axle = (plant.profile['policy']['maximum_drive_request_nm'] if case == CASES[0]
            else plant.actuation.motor_peak_torque_nm * plant.actuation.gear_ratio
            * plant.actuation.gear_efficiency)
    command = (0., 0., axle / 2., axle / 2.)
    steering = brakes = (0.,) * 4
    available = (False, False, True, True)
    context = dict(staging=STAGING, profile_sha256=plant.construction_record['input_pins']['profile'][1], schema='lapsim.drag75m-staged-source.v2', operation_id=operation,
        source_manifest_sha256=ctx.manifest_sha, construction=plant.construction_record,
        mission='official-style75m timing gates; foremost part initially0.30m behind start at rest; no driver learning',
        throttle=1., throttle_case=case,
        throttle_convention=('actual learned-driver full-pedal axle request cap; no policy inference'
            if case == CASES[0] else 'configured motor_peak_torque transformed once to wheel-side; separate hardware-envelope diagnostic'),
        physical_limits='canonical current/speed/power/pack/actuator/traction limits retained in both cases',
        motor_input_nm=command, steering_rad=steering, friction_nm=brakes,
        regen='no negative motor request; no requested regeneration',
        automatic_drs_enabled=state.automatic_drs_enabled, physics_tick_s=.001,
        target_m=TARGET_M, maximum_ticks=MAX_TICKS, maximum_work=MAX_WORK,
        maximum_tick_work=MAX_TICK_WORK, reference_target_s=4.188,
        reference_status='official2026 Michigan UMD acceleration best; model and vehicle calibration remain unverified')
    _same(next(iterator, None), dict(kind='construction', context=context,
                                   initial_state=initial),
          'independent drag construction/context/command differs')
    baseline_work = _work(state)
    max_speed = max_ax = max_slip = 0.
    min_ax = 0.
    max_motor_torque = max_motor_speed = 0.
    crossing = start_crossing = launch75_crossing = None
    maximum_endpoint_motor_rpm = maximum_heading_deviation_rad = 0.
    feedback_count = diagnostics_count = 0
    for tick in range(MAX_TICKS):
        ctx.semantic_check()
        row = next(iterator, None)
        _require(type(row) is dict and row.get('kind') == 'feedback',
                 'exact complete drag feedback sequence required')
        before = state
        before_view = asdict(before)
        bp = before.thermal.light.powered
        work = _work(before) - baseline_work
        _require(0 <= work < MAX_WORK, 'finite cumulative replay work exhausted')
        diagnostic = None
        if tick % 10 == 0:
            ctx.semantic_check()
            _, physical, electrical = evaluate_thermal_light(
                plant.settings, plant.thermal, plant.actuation, before.thermal,
                command, steering, brakes, available, plant.environment,
                aero_mode=before.drs.actual_mode,
                wheel_radii_m=(car.wheel_radius_m,) * 4, driver_proxy_n=0.)
            ctx.semantic_check()
            max_ax = max(max_ax, physical.cg_longitudinal_acceleration_mps2)
            min_ax = min(min_ax, physical.cg_longitudinal_acceleration_mps2)
            max_slip = max(max_slip, *(abs(w.slip_ratio) for w in physical.wheels))
            max_motor_torque = max(max_motor_torque,
                                   *(abs(x) for x in electrical.motor_torques_nm))
            max_motor_speed = max(max_motor_speed, *electrical.motor_speeds_rad_s)
            diagnostic = dict(sample='tick-start every10ms', physical=asdict(physical),
                              electrical=asdict(electrical))
            diagnostics_count += 1
        ctx.semantic_check()
        state = advance_combined_light(
            plant.settings, plant.thermal, plant.drs, plant.actuation, before,
            command, steering, brakes, available, plant.environment,
            braking_requested=False, wheel_radii_m=(car.wheel_radius_m,) * 4,
            maximum_work=min(MAX_TICK_WORK, MAX_WORK - work), driver_proxy_n=0.)
        ctx.semantic_check()
        powered = state.thermal.light.powered
        point = powered.plant
        new_work = _work(state) - baseline_work
        _require(asdict(before) == before_view and state.model_sha256 == before.model_sha256
                 and state.thermal.light.feedback_ticks == tick + 1
                 and state.drs.ticks == tick + 1
                 and state.thermal.thermal.ticks == tick + 1
                 and work <= new_work <= min(work + MAX_TICK_WORK, MAX_WORK),
                 'drag replay state/clock/work/mutation continuity differs')
        d0, d1 = distance(bp.plant), distance(point)
        nose_before=replay_nose_coordinate(bp.plant,origin)
        nose_after=replay_nose_coordinate(point,origin)
        maximum_heading_deviation_rad=max(maximum_heading_deviation_rad,abs(point.heading_rad-origin.heading_rad))
        rpm=abs((point.wheel_speeds_rad_s[2]+point.wheel_speeds_rad_s[3])*.5*plant.actuation.gear_ratio)*60./(2.*pi)
        maximum_endpoint_motor_rpm=max(maximum_endpoint_motor_rpm,rpm)
        if start_crossing is None:start_crossing=replay_crossing(nose_before,nose_after,0.,tick,bp.plant,point)
        if launch75_crossing is None:launch75_crossing=replay_crossing(d0,d1,75.,tick,bp.plant,point)
        finish_crossing=replay_crossing(nose_before,nose_after,75.,tick,bp.plant,point)
        speed = hypot(point.u_mps, point.v_mps)
        side = lateral(point)
        _require(all(isfinite(x) for x in (d0, d1, speed, side)) and d1 >= d0
                 and hypot(point.x_m - bp.plant.x_m, point.y_m - bp.plant.y_m) <= .5
                 and abs(side) <= 1., 'nonforward/nonstraight replay trajectory refused')
        max_speed = max(max_speed, speed)
        state_view = asdict(state)
        _same(row, dict(kind='feedback', from_ms=tick, until_ms=tick + 1,
            input_state_sha256=digest(before_view), accepted_state_sha256=digest(state_view),
            complete_accepted_state=state_view, distance_endpoints_m=(d0, d1),
            nose_gate_endpoints_m=(nose_before,nose_after), lateral_m=side, diagnostics=diagnostic),
            'independent drag physical state/control/diagnostic row differs at tick ' + str(tick + 1))
        feedback_count += 1
        if finish_crossing is not None:
            _require(start_crossing is not None and launch75_crossing is not None,'preceding stage crossings required')
            crossing=finish_crossing
            break
    expected = dict(schema='lapsim.drag75m-staged-result.v2', context_sha256=digest(context),
        status='reached_staged_finish' if crossing else 'finite_horizon_without_staged_finish', crossing=crossing,
        timing=dict(start=start_crossing,finish=crossing,launch_to_original75m=launch75_crossing,
            gate_to_gate_s=None if crossing is None else crossing['elapsed_s']-start_crossing['elapsed_s']),
        maximum_endpoint_motor_rpm=maximum_endpoint_motor_rpm,maximum_heading_deviation_rad=maximum_heading_deviation_rad,
        accepted_tick=state.thermal.light.feedback_ticks,
        endpoint_distance_m=distance(state.thermal.light.powered.plant),
        maximum_endpoint_speed_mps=max_speed, acceleration_10ms_min_mps2=min_ax,
        acceleration_10ms_max_mps2=max_ax, maximum_sampled_abs_tire_slip=max_slip,
        maximum_sampled_motor_torque_nm=max_motor_torque,
        maximum_sampled_motor_speed_rad_s=max_motor_speed, terminal_state=asdict(state),
        qualification='diagnostic canonical synthetic profile; no verified2026 vehicle accuracy or lap validation')
    ctx.semantic_check()
    _same(next(iterator, None), dict(kind='summary', result=expected),
          'independently reconstructed drag terminal row differs')
    _require(next(iterator, None) is None, 'extra rows after drag summary')
    _same(summary, expected, 'external drag summary differs from full independent replay')
    _require(row_count == feedback_count + 2, 'drag accepted tick/row accounting differs')
    ctx.semantic_check()
    return dict(schema='lapsim.drag75m-independent-replay.v1', stage=stage,
        status='semantically_replayed_not_post_admitted', operation_id=operation,
        source_manifest_sha256=ctx.manifest_sha, throttle_case=case,
        context_sha256=digest(context), trace_sha256=sha256(raw_zframes).hexdigest(),
        trace_bytes=len(raw_zframes), expanded_bytes=expanded, rows=row_count,
        feedback_ticks=feedback_count, diagnostic_samples=diagnostics_count,
        cumulative_work=_work(state) - baseline_work,
        terminal_state_sha256=digest(asdict(state)), summary_sha256=digest(expected),
        summary=expected)
