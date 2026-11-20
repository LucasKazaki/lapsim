"""Bounded checks of the same command-to-Light path as the native window."""

from math import hypot
from threading import Event
from time import perf_counter


def run_checks(exchange):
    def command(kind, throttle=0.0, brake=0.0, steering=0.0, cancelled=None):
        return exchange(dict(kind=kind, throttle=throttle, brake=brake,
                             steering=steering, cancelled=cancelled))

    def advance(throttle=0.0, brake=0.0, steering=0.0):
        frame = command("drive", throttle=throttle, brake=brake, steering=steering)
        if frame["reason"]:
            raise RuntimeError(f"Physical check stopped at {frame['sim_s']:.3f} s: {frame['reason']}")
        return frame

    def trajectory():
        initial = command("reset")
        straight = [advance(throttle=1.0) for _ in range(22)]
        turn = [advance(throttle=0.20, steering=0.25) for _ in range(7)]
        braking = [advance(brake=1.0) for _ in range(24)]
        return [initial, *straight, *turn, *braking]

    def check(predicate, reason):
        if not predicate:
            raise RuntimeError(reason)

    started = perf_counter()
    left = trajectory()
    left_wall_s = perf_counter() - started
    repeat = trajectory()
    baseline, accelerating, turning, stopped = left[0], left[22], left[29], left[-1]
    check(baseline["sim_s"] == baseline["speed_mps"] == baseline["steer_rad"] == 0,
          "Reset did not restore the standing physical state")
    check(accelerating["speed_mps"] > 2.0 and hypot(accelerating["x"] - baseline["x"],
                                                   accelerating["y"] - baseline["y"]) > 1.0,
          "Throttle did not accelerate from rest")
    check(turning["speed_mps"] > 1.0 and turning["steer_rad"] > 0
          and turning["heading"] - accelerating["heading"] > 0.005,
          "Steering did not turn the moving chassis to the left")
    check(stopped["speed_mps"] < 0.30 * turning["speed_mps"], "Braking did not substantially reduce speed")
    comparable = lambda trace: [{k: v for k, v in row.items() if k != "sim_per_step_wall"} for row in trace]
    check(comparable(left) == comparable(repeat), "Repeated exact driving commands diverged")

    paused = command("pause")
    cancelled = Event()
    cancelled.set()
    rejected = command("drive", throttle=1.0, cancelled=cancelled)
    check(paused["sim_s"] == stopped["sim_s"] == rejected["sim_s"]
          and rejected["throttle"] == rejected["brake"] == 0, "Pause or cancelled drive advanced physics")
    command("reset")
    for _ in range(22):
        right_start = advance(throttle=1.0)
    for _ in range(7):
        right = advance(throttle=0.20, steering=-0.25)
    check(right["speed_mps"] > 1.0 and right["steer_rad"] < 0
          and right["heading"] - right_start["heading"] < -0.005,
          "Steering did not turn the moving chassis to the right")
    command("close")
    return dict(
        result="same-path physical checks passed",
        throttle_speed_mps=accelerating["speed_mps"],
        turn_speed_mps=turning["speed_mps"],
        left_heading_change_rad=turning["heading"] - accelerating["heading"],
        right_heading_change_rad=right["heading"] - right_start["heading"],
        braking_final_speed_mps=stopped["speed_mps"],
        repeated_pose_samples=len(left),
        exact_repeatability=True,
        no_advances_while_paused_or_cancelled=True,
        trial_sim_s=stopped["sim_s"],
        first_trial_wall_s=left_wall_s,
    )
