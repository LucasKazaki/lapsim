"""TC-01B portable kinematic electronic-differential reference.

Synthetic/offline reference only.

This module computes no-slip wheel path-speed references from simple Ackermann/
bicycle geometry. It does not compute torque, traction control, yaw-moment
control, tire forces, inverter commands, CAN messages, or vehicle safety state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math


class KinematicEDiffError(ValueError):
    pass


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise KinematicEDiffError(f"{name} must be a finite number")
    out = float(value)
    if not math.isfinite(out):
        raise KinematicEDiffError(f"{name} must be a finite number")
    return out


def _positive(value: float, name: str) -> float:
    out = _finite(value, name)
    if out <= 0.0:
        raise KinematicEDiffError(f"{name} must be positive")
    return out


@dataclass(frozen=True)
class Geometry:
    wheelbase_m: float
    front_track_m: float
    rear_track_m: float
    wheel_radius_m: float

    def validated(self) -> "Geometry":
        return Geometry(
            _positive(self.wheelbase_m, "wheelbase_m"),
            _positive(self.front_track_m, "front_track_m"),
            _positive(self.rear_track_m, "rear_track_m"),
            _positive(self.wheel_radius_m, "wheel_radius_m"),
        )


@dataclass(frozen=True)
class KinematicInput:
    center_speed_mps: float
    equivalent_steer_rad: float

    def validated(self) -> "KinematicInput":
        speed = _finite(self.center_speed_mps, "center_speed_mps")
        steer = _finite(self.equivalent_steer_rad, "equivalent_steer_rad")
        if speed < 0.0:
            raise KinematicEDiffError("center_speed_mps must be nonnegative")
        if abs(steer) >= math.pi / 2:
            raise KinematicEDiffError("equivalent_steer_rad must remain within (-pi/2, pi/2)")
        return KinematicInput(speed, steer)


@dataclass(frozen=True)
class WheelReferences:
    schema: str
    turn_direction: str
    center_speed_mps: float
    equivalent_steer_rad: float
    rear_axle_center_radius_m: float | None
    yaw_rate_rad_s: float
    front_left_radius_m: float | None
    front_right_radius_m: float | None
    rear_left_radius_m: float | None
    rear_right_radius_m: float | None
    front_left_speed_mps: float
    front_right_speed_mps: float
    rear_left_speed_mps: float
    rear_right_speed_mps: float
    front_left_omega_rad_s: float
    front_right_omega_rad_s: float
    rear_left_omega_rad_s: float
    rear_right_omega_rad_s: float
    front_left_steer_rad: float
    front_right_steer_rad: float
    requests_yaw_moment: bool = False
    traction_control: bool = False
    torque_command_generated: bool = False
    vehicle_acceptance_proven: bool = False
    action_authority: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), allow_nan=False)


def wheel_references(
    geometry: Geometry,
    inp: KinematicInput,
    *,
    straight_epsilon_rad: float = 1e-9,
) -> WheelReferences:
    g = geometry.validated()
    x = inp.validated()
    eps = _positive(straight_epsilon_rad, "straight_epsilon_rad")

    if abs(x.equivalent_steer_rad) <= eps:
        omega = x.center_speed_mps / g.wheel_radius_m
        return WheelReferences(
            schema="enme408-tc01b-kinematic-ediff/v1",
            turn_direction="straight",
            center_speed_mps=x.center_speed_mps,
            equivalent_steer_rad=x.equivalent_steer_rad,
            rear_axle_center_radius_m=None,
            yaw_rate_rad_s=0.0,
            front_left_radius_m=None,
            front_right_radius_m=None,
            rear_left_radius_m=None,
            rear_right_radius_m=None,
            front_left_speed_mps=x.center_speed_mps,
            front_right_speed_mps=x.center_speed_mps,
            rear_left_speed_mps=x.center_speed_mps,
            rear_right_speed_mps=x.center_speed_mps,
            front_left_omega_rad_s=omega,
            front_right_omega_rad_s=omega,
            rear_left_omega_rad_s=omega,
            rear_right_omega_rad_s=omega,
            front_left_steer_rad=x.equivalent_steer_rad,
            front_right_steer_rad=x.equivalent_steer_rad,
        )

    steer_abs = abs(x.equivalent_steer_rad)
    radius = g.wheelbase_m / math.tan(steer_abs)
    if radius <= max(g.front_track_m, g.rear_track_m) / 2.0:
        raise KinematicEDiffError(
            "turn radius intersects/enters the wheel track; simple forward Ackermann reference is invalid"
        )

    yaw_mag = 0.0 if x.center_speed_mps == 0.0 else x.center_speed_mps / radius
    yaw_rate = math.copysign(yaw_mag, x.equivalent_steer_rad)

    rear_inner = radius - g.rear_track_m / 2.0
    rear_outer = radius + g.rear_track_m / 2.0
    front_inner = math.hypot(radius - g.front_track_m / 2.0, g.wheelbase_m)
    front_outer = math.hypot(radius + g.front_track_m / 2.0, g.wheelbase_m)

    rear_inner_speed = yaw_mag * rear_inner
    rear_outer_speed = yaw_mag * rear_outer
    front_inner_speed = yaw_mag * front_inner
    front_outer_speed = yaw_mag * front_outer

    inner_steer = math.atan2(g.wheelbase_m, radius - g.front_track_m / 2.0)
    outer_steer = math.atan2(g.wheelbase_m, radius + g.front_track_m / 2.0)

    if x.equivalent_steer_rad > 0.0:
        fl_r, fr_r = front_inner, front_outer
        rl_r, rr_r = rear_inner, rear_outer
        fl_v, fr_v = front_inner_speed, front_outer_speed
        rl_v, rr_v = rear_inner_speed, rear_outer_speed
        fl_delta, fr_delta = inner_steer, outer_steer
        direction = "left"
    else:
        fl_r, fr_r = front_outer, front_inner
        rl_r, rr_r = rear_outer, rear_inner
        fl_v, fr_v = front_outer_speed, front_inner_speed
        rl_v, rr_v = rear_outer_speed, rear_inner_speed
        fl_delta, fr_delta = -outer_steer, -inner_steer
        direction = "right"

    return WheelReferences(
        schema="enme408-tc01b-kinematic-ediff/v1",
        turn_direction=direction,
        center_speed_mps=x.center_speed_mps,
        equivalent_steer_rad=x.equivalent_steer_rad,
        rear_axle_center_radius_m=radius,
        yaw_rate_rad_s=yaw_rate,
        front_left_radius_m=fl_r,
        front_right_radius_m=fr_r,
        rear_left_radius_m=rl_r,
        rear_right_radius_m=rr_r,
        front_left_speed_mps=fl_v,
        front_right_speed_mps=fr_v,
        rear_left_speed_mps=rl_v,
        rear_right_speed_mps=rr_v,
        front_left_omega_rad_s=fl_v / g.wheel_radius_m,
        front_right_omega_rad_s=fr_v / g.wheel_radius_m,
        rear_left_omega_rad_s=rl_v / g.wheel_radius_m,
        rear_right_omega_rad_s=rr_v / g.wheel_radius_m,
        front_left_steer_rad=fl_delta,
        front_right_steer_rad=fr_delta,
    )


@dataclass(frozen=True)
class EqualSpeedCounterexample:
    schema: str
    duration_s: float
    equal_speed_mps: float
    ideal_distances_m: tuple[float, float, float, float]
    equal_distances_m: tuple[float, float, float, float]
    signed_distance_errors_m: tuple[float, float, float, float]
    max_abs_distance_error_m: float
    vehicle_loss_or_slip_proven: bool = False
    action_authority: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), allow_nan=False)


def equal_speed_counterexample(
    refs: WheelReferences,
    *,
    duration_s: float,
    equal_speed_mps: float | None = None,
) -> EqualSpeedCounterexample:
    duration = _positive(duration_s, "duration_s")
    equal_speed = refs.center_speed_mps if equal_speed_mps is None else _finite(equal_speed_mps, "equal_speed_mps")
    if equal_speed < 0.0:
        raise KinematicEDiffError("equal_speed_mps must be nonnegative")
    ideal_speeds = (
        refs.front_left_speed_mps,
        refs.front_right_speed_mps,
        refs.rear_left_speed_mps,
        refs.rear_right_speed_mps,
    )
    ideal = tuple(v * duration for v in ideal_speeds)
    equal = (equal_speed * duration,) * 4
    errors = tuple(eq - target for eq, target in zip(equal, ideal))
    return EqualSpeedCounterexample(
        schema="enme408-tc01b-equal-speed-counterexample/v1",
        duration_s=duration,
        equal_speed_mps=equal_speed,
        ideal_distances_m=ideal,
        equal_distances_m=equal,
        signed_distance_errors_m=errors,
        max_abs_distance_error_m=max(abs(x) for x in errors),
    )
