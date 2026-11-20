"""Presentation adapter for the frozen single-motor Light plant."""

from dataclasses import dataclass
import json
from math import atan2, hypot, isfinite
from time import perf_counter

from lapsim.learning.live.carrier_control import compute_carrier_control
from lapsim.learning.live.demo_initialization import construct
from lapsim.learning.live.parking_lot_mission import ParkingLotMission, swept_rectangle_bounds
from lapsim.learning.live.projection import swept_rectangle_cone_collision
from lapsim_light_core.torque_light_combined import advance_combined_light


TICK_S = 0.001
FRAME_TICKS = 50
MAX_TICKS = 12800
MAX_WORK = 4_000_000
MAX_TICK_WORK = 50_000


def map_and_start(raws):
    course = json.loads(raws["course"])["geometry"]
    cones = json.loads(raws["cones"])["cones"]
    centerline = list(map(list, zip(course["x_m"], course["y_m"])))
    (x, y), (next_x, next_y) = centerline[:2]
    heading = atan2(next_y - y, next_x - x) - (
        course["curvature_per_m"][0] * (course["distance_m"][1] - course["distance_m"][0]) / 2
    )
    mission = ParkingLotMission.from_raws(raws)
    geometry = {
        "centerline": centerline,
        "cones": [{"x": c["x_m"], "y": c["y_m"], "side": c["side"]} for c in cones],
        "start": [x, y],
        "bounds": [mission.xmin_m, mission.ymin_m, mission.xmax_m, mission.ymax_m],
    }
    start = dict(x=x, y=y, heading=heading, speed_mps=0.0, sim_s=0.0, steer_rad=0.0,
                 throttle=0.0, brake=0.0, reason="ready")
    return geometry, start


@dataclass(frozen=True)
class Demand:
    steering: float
    throttle: float
    brake: float

    @classmethod
    def from_command(cls, command):
        steering, throttle, brake = (command[key] for key in ("steering", "throttle", "brake"))
        for value, lower, upper in ((steering, -1, 1), (throttle, 0, 1), (brake, 0, 1)):
            if type(value) not in (int, float) or not isfinite(value) or not lower <= value <= upper:
                raise ValueError("Input outside the normalized keyboard control range")
        return cls(steering, 0.0 if brake else throttle, brake)


class DemoPlant:
    """One owned plant. Reset restores the complete immutable standing state."""

    def __init__(self, raws, check_owner):
        self.check_owner = check_owner
        self.check_owner()
        self.plant = construct(raws)
        self.mission = ParkingLotMission.from_raws(raws)
        self.cones = tuple((c.x_m, c.y_m) for c in self.plant.cone_map.cones)
        self.vehicle = self.plant.settings.forces.plant
        self.wheel_radii = (self.vehicle.wheel_radius_m,) * 4
        policy = self.plant.profile["policy"]
        self.maximum_drive = policy["maximum_drive_request_nm"]
        self.maximum_brake = policy["maximum_friction_brake_nm"]
        self.total_ticks = 0
        self.total_work = 0
        self.total_wall_s = 0.0
        self.reset()

    def reset(self):
        self.check_owner()
        self.state = self.plant.state
        p = self.state.thermal.light.powered.plant
        pose = (p.x_m, p.y_m, p.heading_rad)
        if self.geometry_event(pose, pose):
            raise RuntimeError("Standing spawn does not clear the parking boundary or modeled cones")
        self.ticks = 0
        self.steering = 0.0
        self.reason = None
        return self.view("ready")

    def view(self, reason=None, *, demand=Demand(0.0, 0.0, 0.0)):
        p = self.state.thermal.light.powered.plant
        return dict(x=p.x_m, y=p.y_m, heading=p.heading_rad, speed_mps=hypot(p.u_mps, p.v_mps),
                    yaw_rate_rad_s=p.yaw_rate_rad_s, sim_s=self.ticks * TICK_S,
                    steer_rad=self.steering, throttle=demand.throttle, brake=demand.brake,
                    reason=self.reason or reason,
                    sim_per_step_wall=self.total_ticks * TICK_S / self.total_wall_s if self.total_wall_s else None)

    def geometry_event(self, before_pose, after_pose):
        box = swept_rectangle_bounds(before_pose, after_pose, self.mission.half_length_m, self.mission.half_width_m)
        if (box["xmin_m"] < self.mission.xmin_m or box["xmax_m"] > self.mission.xmax_m
                or box["ymin_m"] < self.mission.ymin_m or box["ymax_m"] > self.mission.ymax_m):
            return "Parking boundary reached"
        # The original broad phase uses the center segment with a radius of
        # hypot(1, 0.7) m and tiny numeric padding. The 2 m box encloses it.
        xmin, xmax = sorted((before_pose[0], after_pose[0]))
        ymin, ymax = sorted((before_pose[1], after_pose[1]))
        nearby = tuple((x, y) for x, y in self.cones
                       if xmin - 2.0 <= x <= xmax + 2.0 and ymin - 2.0 <= y <= ymax + 2.0)
        if swept_rectangle_cone_collision(before_pose, after_pose, self.mission.half_length_m,
                                          self.mission.half_width_m, nearby, 0.0):
            return "Modeled cone contact"
        return None

    def exchange(self, command):
        self.check_owner()
        kind = command["kind"]
        if kind == "reset":
            return self.reset()
        if kind in ("pause", "close"):
            return self.view("paused")
        if kind != "drive":
            raise ValueError("Unknown keyboard command")
        if self.reason:
            return self.view()
        demand = Demand.from_command(command)
        cancellation = command.get("cancelled")
        started = perf_counter()
        try:
            self._drive(demand, cancellation)
        finally:
            self.total_wall_s += perf_counter() - started
        if cancellation is not None and cancellation.is_set():
            return self.view("paused")
        return self.view(demand=demand if self.reason is None else Demand(0.0, 0.0, 0.0))

    def _drive(self, demand, cancellation):
        requested_steering = demand.steering * 0.4
        requested_drive = demand.throttle * self.maximum_drive
        brakes = (demand.brake * self.maximum_brake,) * 4
        steering = self.steering
        if self.ticks % FRAME_TICKS == 0:
            steering = max(steering - 0.1, min(steering + 0.1, requested_steering))
        wheels = (steering, steering, 0.0, 0.0)
        motor = (0.0, 0.0, requested_drive / 2.0, requested_drive / 2.0)
        for _ in range(FRAME_TICKS - self.ticks % FRAME_TICKS):
            self.check_owner()
            if cancellation is not None and cancellation.is_set():
                return
            if self.total_ticks >= MAX_TICKS:
                self.reason = "Session drive limit reached. Close and relaunch."
                return
            budget = min(MAX_TICK_WORK, MAX_WORK - self.total_work)
            if budget <= 0:
                self.reason = "Session work limit reached. Close and relaunch."
                return
            previous = self.state.thermal.light.powered
            if self.ticks % 10 == 0:
                motor = tuple(compute_carrier_control("DIRECT_CARRIER", requested_drive, previous.plant,
                                                      self.vehicle, target_slip=0.1)["command"])
            updated = advance_combined_light(
                self.plant.settings, self.plant.thermal, self.plant.drs, self.plant.actuation,
                self.state, motor, wheels, brakes, (False, False, True, True), self.plant.environment,
                braking_requested=demand.brake > 0.0, wheel_radii_m=self.wheel_radii,
                maximum_work=budget, driver_proxy_n=0.0,
            )
            current = updated.thermal.light.powered
            work = current.integration_trials + current.wheel_stop_events
            work -= previous.integration_trials + previous.wheel_stop_events
            next_tick = self.ticks + 1
            if (not 0 <= work <= budget or updated.model_sha256 != self.state.model_sha256
                    or updated.thermal.light.feedback_ticks != next_tick
                    or updated.thermal.thermal.ticks != next_tick or updated.drs.ticks != next_tick):
                raise RuntimeError("Light clock, work or model continuity failed")
            self.total_work += work
            self.check_owner()
            if cancellation is not None and cancellation.is_set():
                return
            p0, p1 = previous.plant, current.plant
            if hypot(p1.x_m - p0.x_m, p1.y_m - p0.y_m) > 0.5:
                raise RuntimeError("Light per-tick motion bound exceeded")
            reason = self.geometry_event((p0.x_m, p0.y_m, p0.heading_rad),
                                         (p1.x_m, p1.y_m, p1.heading_rad))
            self.check_owner()
            if cancellation is not None and cancellation.is_set():
                return
            self.state, self.ticks, self.steering = updated, next_tick, steering
            self.total_ticks += 1
            self.reason = reason
            if reason:
                return
