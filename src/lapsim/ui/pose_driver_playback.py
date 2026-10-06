"""Driver-view adapter for an actual synthetic planar pose trace.

Its x/y and heading come from the four-wheel simulation. Its displayed time
is a pose-model experiment duration, not an endurance lap or battery result.
"""

from __future__ import annotations

from bisect import bisect_right
from math import hypot, isfinite, pi, remainder

import numpy as np

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.dynamics.planar import PlanarState
from lapsim.optimization.pose_driver import (
    POSE_MODEL_LABEL, PoseDriverRun, PoseDriverSample,
)

from .driver_view import DriverFrame, DriverPlayback


class PoseDriverPlayback(DriverPlayback):
    """Expose the existing viewport surface using simulated vehicle pose."""

    display_time_label = "Pose-model time"
    evidence_label = POSE_MODEL_LABEL
    has_battery_telemetry = False

    def __init__(self, run: PoseDriverRun) -> None:
        if not isinstance(run, PoseDriverRun):
            raise TypeError("run must be PoseDriverRun")
        if len(run.states) != len(run.samples) or len(run.times_s) != len(run.states):
            raise ValueError("pose trace states, samples, and times must align")
        self.run = run
        self.track = run.track
        self.track_distance = np.asarray(run.track.distance_m, dtype=float)
        self.track_x = np.asarray(run.track.x_m, dtype=float)
        self.track_y = np.asarray(run.track.y_m, dtype=float)
        self.times = run.times_s
        self.duration_s = run.elapsed_pose_model_time_s

    def frame_at(self, time_s: float) -> DriverFrame:
        """Interpolate actual x/y and heading between model state boundaries."""

        if not isfinite(time_s):
            raise ValueError("Time must be finite")
        instant = min(max(time_s, 0.0), self.duration_s)
        if len(self.times) == 1:
            lower = upper = 0
            fraction = 0.0
        else:
            upper = min(bisect_right(self.times, instant), len(self.times) - 1)
            lower = max(0, upper - 1)
            interval_s = self.times[upper] - self.times[lower]
            fraction = 0.0 if interval_s == 0.0 else (
                instant - self.times[lower]
            ) / interval_s
        first, second = self.run.states[lower], self.run.states[upper]
        first_sample, second_sample = self.run.samples[lower], self.run.samples[upper]
        heading_delta = remainder(second.heading_rad - first.heading_rad, 2.0 * pi)
        heading = first.heading_rad + fraction * heading_delta
        body_u = first.u_mps + fraction * (second.u_mps - first.u_mps)
        body_v = first.v_mps + fraction * (second.v_mps - first.v_mps)
        if self.run.evaluations:
            first_lateral = self.run.evaluations[min(lower, len(self.run.evaluations) - 1)].cg_lateral_acceleration_mps2
            second_lateral = self.run.evaluations[min(upper, len(self.run.evaluations) - 1)].cg_lateral_acceleration_mps2
            lateral = first_lateral + fraction * (second_lateral - first_lateral)
        else:
            lateral = 0.0
        return DriverFrame(
            time_s=instant,
            distance_m=(first_sample.progress_m + fraction * (
                second_sample.progress_m - first_sample.progress_m
            )),
            x_m=first.x_m + fraction * (second.x_m - first.x_m),
            y_m=first.y_m + fraction * (second.y_m - first.y_m),
            course_heading_rad=heading,
            speed_mps=hypot(body_u, body_v),
            lateral_acceleration_mps2=lateral,
            decision=None,
        )

    def local_path_m(
        self, frame: DriverFrame, *, behind_m: float, ahead_m: float,
        spacing_m: float = 2.0,
    ) -> tuple[tuple[float, float], ...]:
        """Reference path around modeled pose; it may miss the car marker."""

        return super().local_path_m(
            frame, behind_m=behind_m, ahead_m=ahead_m,
            spacing_m=spacing_m,
        )

    def control_values_at(self, time_s: float) -> tuple[float, ...] | None:
        """Recorded active commands and interpolated pose diagnostics for boxes.

        Controls are held over their output interval. Geometry diagnostics are
        linearly displayed between recorded boundary samples; this display
        interpolation does not add a new physics evaluation.
        """

        if not isfinite(time_s):
            raise ValueError("Time must be finite")
        if not self.run.controls:
            return None
        instant = min(max(time_s, 0.0), self.duration_s)
        index = min(bisect_right(self.times, instant) - 1, len(self.run.controls) - 1)
        interval_s = self.times[index + 1] - self.times[index]
        fraction = 0.0 if interval_s <= 0.0 else (
            instant - self.times[index]
        ) / interval_s
        first, second = self.run.samples[index:index + 2]
        first_state, second_state = self.run.states[index:index + 2]
        command = self.run.controls[index]

        def linear(a: float, b: float) -> float:
            return a + fraction * (b - a)

        return (
            command.steering_angles_rad[0] * 180.0 / pi,
            command.drive_torques_nm[2],
            command.brake_torques_nm[0],
            command.brake_torques_nm[1],
            linear(first.cross_track_error_m, second.cross_track_error_m),
            (first.heading_error_rad + fraction * remainder(
                second.heading_error_rad - first.heading_error_rad, 2.0 * pi,
            )) * 180.0 / pi,
            first.local_grip_multiplier,
            linear(first.minimum_assumed_boundary_slack_m,
                   second.minimum_assumed_boundary_slack_m),
            linear(first_state.yaw_rate_rad_s, second_state.yaw_rate_rad_s)
            * 180.0 / pi,
        )


class PoseDriverLivePlayback(DriverPlayback):
    """One accepted pose state for the live, car-centered viewport.

    The worker sends only its newest state. Controls and acceleration remain
    unavailable until the completed run provides their recorded channels.
    """

    display_time_label = "Pose-model time"
    evidence_label = POSE_MODEL_LABEL
    has_battery_telemetry = False

    def __init__(
        self, track: SpatialTrack, sample: PoseDriverSample, state: PlanarState,
    ) -> None:
        self.track = track
        self.track_distance = np.asarray(track.distance_m, dtype=float)
        self.track_x = np.asarray(track.x_m, dtype=float)
        self.track_y = np.asarray(track.y_m, dtype=float)
        self.sample = sample
        self.state = state
        self.duration_s = sample.time_s

    def frame_at(self, time_s: float) -> DriverFrame:
        if not isfinite(time_s):
            raise ValueError("Time must be finite")
        return DriverFrame(
            time_s=self.sample.time_s,
            distance_m=self.sample.progress_m,
            x_m=self.state.x_m,
            y_m=self.state.y_m,
            course_heading_rad=self.state.heading_rad,
            speed_mps=hypot(self.state.u_mps, self.state.v_mps),
            lateral_acceleration_mps2=float("nan"),
            decision=None,
        )

    def control_values_at(self, time_s: float) -> tuple[float, ...]:
        if not isfinite(time_s):
            raise ValueError("Time must be finite")
        unavailable = float("nan")
        return (
            unavailable, unavailable, unavailable, unavailable,
            self.sample.cross_track_error_m,
            self.sample.heading_error_rad * 180.0 / pi,
            self.sample.local_grip_multiplier,
            self.sample.minimum_assumed_boundary_slack_m,
            self.state.yaw_rate_rad_s * 180.0 / pi,
        )


__all__ = ["PoseDriverPlayback", "PoseDriverLivePlayback"]
