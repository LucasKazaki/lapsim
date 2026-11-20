"""Pure RWD carrier-command adapter; no plant, clock or actuator ownership.

The ratio law is retained from tournament_rollout.allocate, source SHA256
fb36599aeab7accb4b3698b02c0e61f70176225df094f69b2b8f93aef629423f.
Unsteered rear-wheel longitudinal velocity is u - yaw_rate * wheel_y.
The shared carrier uses the smaller of the two rear ratio reductions. This
does not command the two physical LSD output shafts independently.
"""

from math import isfinite

DIRECT_CARRIER = "DIRECT_CARRIER"
CARRIER_TRACTION_RATIO = "CARRIER_TRACTION_RATIO"
MODES = (DIRECT_CARRIER, CARRIER_TRACTION_RATIO)


def _number(value, name):
    if type(value) not in (int, float):
        raise ValueError(name + " must be an ordinary finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(name + " must fit binary64") from error
    if not isfinite(result):
        raise ValueError(name + " must be finite")
    return result


def compute_carrier_control(mode, total_drive_request_nm, plant_state,
                            vehicle_config, *, target_slip=.10):
    """Return audited pre-actuation motor inputs in FL, FR, RL, RR order.

    Inputs are the current PlanarState-like u_mps/v_mps/yaw_rate_rad_s and four
    wheel_speeds_rad_s, plus PlanarVehicleConfig-like wheel_radius_m,
    rear_track_m and low_speed_regularization_mps. All are SI values. Slip and
    scales are dimensionless; requested_total and command are N*m. The caller
    owns the intended 10ms update/hold, independent replay and all physical
    limiting. No time, route, grip, load or privileged tire force is consumed.
    """
    if type(mode) is not str or mode not in MODES:
        raise ValueError("unknown carrier-control mode")
    total = _number(total_drive_request_nm, "total drive request")
    target = _number(target_slip, "target slip")
    if total < 0 or target <= 0:
        raise ValueError("nonnegative drive request and positive target required")
    if total == 0:
        total = 0.0
    u = _number(plant_state.u_mps, "body longitudinal speed")
    _number(plant_state.v_mps, "body lateral speed")
    yaw = _number(plant_state.yaw_rate_rad_s, "body yaw rate")
    wheels = plant_state.wheel_speeds_rad_s
    if type(wheels) not in (tuple, list) or len(wheels) != 4:
        raise ValueError("four FL, FR, RL, RR wheel speeds required")
    wheels = tuple(_number(value, "wheel speed") for value in wheels)
    radius = _number(vehicle_config.wheel_radius_m, "wheel radius")
    track = _number(vehicle_config.rear_track_m, "rear track")
    floor = _number(vehicle_config.low_speed_regularization_mps, "speed floor")
    if radius <= 0 or track <= 0 or floor <= 0:
        raise ValueError("positive wheel radius, rear track and speed floor required")
    half_track = track / 2.0
    if half_track == 0:
        raise ValueError("rear half track is not representable")

    half = total / 2.0
    if half + half != total:
        raise ValueError("requested total cannot be represented by equal rear halves")
    slips = []
    for omega, wheel_y in ((wheels[2], half_track), (wheels[3], -half_track)):
        local_u = _number(u - yaw * wheel_y, "rear wheel-plane velocity")
        slip = _number((radius * omega - local_u) / max(abs(local_u), floor),
                       "rear wheel slip")
        slips.append(slip)
    if mode == DIRECT_CARRIER:
        left = right = 1.0
    else:
        # Exact existing ratio law; negative/braking slip never increases drive.
        left, right = (min(1.0, target / max(target, slip)) for slip in slips)
    common = min(left, right)
    rear = _number(half * common, "rear motor input")
    return dict(mode=mode, target=target, requested_total=total,
                slip_left=slips[0], slip_right=slips[1], scale_left=left,
                scale_right=right, common_scale=common,
                command=(0.0, 0.0, rear, rear))
