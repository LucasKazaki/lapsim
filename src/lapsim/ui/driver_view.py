"""Reference-path playback data for the desktop driver's view.

This module deliberately keeps the playback geometry separate from Tk.  The
distance-domain lap solver uses prescribed curvature, not a simulated steering
trajectory.  Playback follows the distance-aligned x/y map visualization and
reports the solved speed and acceleration at each station.  Map x/y and solver
curvature are separate source channels and can disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, isfinite, sin
from typing import Any

import numpy as np

from lapsim.courses.spatial_track import SpatialTrack


@dataclass(frozen=True, slots=True)
class DriverFrame:
    time_s: float
    distance_m: float
    x_m: float
    y_m: float
    course_heading_rad: float
    speed_mps: float
    lateral_acceleration_mps2: float


class DriverPlayback:
    """Interpolate synchronized lap telemetry onto the displayed x/y map."""

    def __init__(self, track: SpatialTrack, telemetry: Any) -> None:
        self.track = track
        self.track_distance = np.asarray(track.distance_m, dtype=float)
        self.track_x = np.asarray(track.x_m, dtype=float)
        self.track_y = np.asarray(track.y_m, dtype=float)
        channels = (
            "vehicle.time_s",
            "vehicle.distance_m",
            "vehicle.speed_mps",
            "vehicle.lateral_acceleration_mps2",
        )
        try:
            arrays = [np.asarray(telemetry[channel], dtype=float) for channel in channels]
        except (KeyError, TypeError) as error:
            raise ValueError("The run has no synchronized lap playback channels") from error
        if any(array.ndim != 1 for array in arrays):
            raise ValueError("Playback channels must be one-dimensional")
        if not arrays[0].size or any(array.size != arrays[0].size for array in arrays):
            raise ValueError("Playback channels must have the same nonzero length")
        if any(not np.all(np.isfinite(array)) for array in arrays):
            raise ValueError("Playback channels must contain finite numbers")
        times, distances, speeds, lateral = arrays
        if times.size == 1 and times[0] == 0.0:
            raise ValueError("Playback requires a positive elapsed duration")
        if np.any(np.diff(times) <= 0) or times[0] < 0:
            raise ValueError("Playback times must increase from a nonnegative start")
        if np.any(np.diff(distances) < 0) or distances[0] < 0:
            raise ValueError("Playback distances must be nondecreasing and nonnegative")
        if np.any(speeds < 0):
            raise ValueError("Playback speeds must be nonnegative")
        if distances[-1] > track.length_m + 1e-5:
            raise ValueError("Playback distance exceeds the reference path")
        if times[0] > 0:
            # Endurance telemetry is recorded after accepted cells.  The first
            # display frame is the starting grid, not the first completed cell.
            # The vehicle solver traverses each cell at constant acceleration,
            # so its first average speed recovers the unrecorded entry speed.
            # Keep the recorded exit speed if older telemetry is inconsistent.
            with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
                entry_speed = 2.0 * distances[0] / times[0] - speeds[0]
            if not isfinite(float(entry_speed)) or entry_speed < -1e-6:
                entry_speed = speeds[0]
            else:
                entry_speed = max(entry_speed, 0.0)
            times = np.concatenate(([0.0], times))
            distances = np.concatenate(([0.0], distances))
            speeds = np.concatenate(([entry_speed], speeds))
            lateral = np.concatenate(([lateral[0]], lateral))
        self.times = times
        self.distances = distances
        self.speeds = speeds
        self.lateral_accelerations = lateral
        self.duration_s = float(times[-1])

    def point_at(self, distance_m: float) -> tuple[float, float]:
        """Return the path point at a station, wrapping only closed courses."""

        if not isfinite(distance_m):
            raise ValueError("Distance must be finite")
        if self.track.closed:
            station = (
                distance_m if 0.0 <= distance_m <= self.track.length_m
                else distance_m % self.track.length_m
            )
        else:
            station = min(max(distance_m, 0.0), self.track.length_m)
        return (
            float(np.interp(station, self.track_distance, self.track_x)),
            float(np.interp(station, self.track_distance, self.track_y)),
        )

    def frame_at(self, time_s: float) -> DriverFrame:
        """Interpolate constant-acceleration cells and derive a map tangent.

        The vehicle model uses ``ds = (v_in + v_out) * dt / 2`` for each cell.
        Applying the same relation here keeps the moving marker in step with
        its displayed speed.  Imported telemetry that does not satisfy this
        relation uses linear station interpolation instead.
        """

        if not isfinite(time_s):
            raise ValueError("Time must be finite")
        instant = min(max(time_s, 0.0), self.duration_s)
        segment = min(
            int(np.searchsorted(self.times, instant, side="right")),
            len(self.times) - 1,
        )
        lower = segment - 1
        interval_s = self.times[segment] - self.times[lower]
        elapsed_s = instant - self.times[lower]
        entry_speed = self.speeds[lower]
        exit_speed = self.speeds[segment]
        cell_distance_m = self.distances[segment] - self.distances[lower]
        expected_distance_m = 0.5 * (entry_speed + exit_speed) * interval_s
        if abs(expected_distance_m - cell_distance_m) <= max(
            1e-6, 1e-5 * cell_distance_m
        ):
            acceleration = (exit_speed - entry_speed) / interval_s
            station = (
                self.distances[lower] + entry_speed * elapsed_s
                + 0.5 * acceleration * elapsed_s**2
            )
            station = float(
                min(max(station, self.distances[lower]), self.distances[segment])
            )
            if elapsed_s == interval_s:
                station = float(self.distances[segment])
            speed = float(entry_speed + acceleration * elapsed_s)
        else:
            fraction = elapsed_s / interval_s
            station = float(self.distances[lower] + fraction * cell_distance_m)
            speed = float(entry_speed + fraction * (exit_speed - entry_speed))
        position = self.point_at(station)
        tangent_half_span = min(2.0, self.track.length_m / 16.0)
        before = self.point_at(station - tangent_half_span)
        after = self.point_at(station + tangent_half_span)
        heading = atan2(after[1] - before[1], after[0] - before[0])
        return DriverFrame(
            time_s=instant,
            distance_m=station,
            x_m=position[0],
            y_m=position[1],
            course_heading_rad=heading,
            speed_mps=speed,
            lateral_acceleration_mps2=float(
                np.interp(instant, self.times, self.lateral_accelerations)
            ),
        )

    def local_path_m(
        self, frame: DriverFrame, *, behind_m: float, ahead_m: float,
        spacing_m: float = 2.0,
    ) -> tuple[tuple[float, float], ...]:
        """Path samples as (right, forward) metres in a car-fixed view."""

        if (
            not all(isfinite(value) for value in (behind_m, ahead_m, spacing_m))
            or behind_m < 0 or ahead_m <= 0 or spacing_m <= 0
        ):
            raise ValueError("Playback view ranges and spacing must be finite and positive")
        offsets = np.arange(-behind_m, ahead_m + spacing_m * 0.5, spacing_m)
        if not self.track.closed:
            offsets = offsets[
                (frame.distance_m + offsets >= 0)
                & (frame.distance_m + offsets <= self.track.length_m)
            ]
        stations = frame.distance_m + offsets
        if self.track.closed:
            stations = np.where(
                (stations >= 0.0) & (stations <= self.track.length_m),
                stations,
                np.mod(stations, self.track.length_m),
            )
        x_m = np.interp(stations, self.track_distance, self.track_x)
        y_m = np.interp(stations, self.track_distance, self.track_y)
        dx = x_m - frame.x_m
        dy = y_m - frame.y_m
        heading_cos = cos(frame.course_heading_rad)
        heading_sin = sin(frame.course_heading_rad)
        right = heading_sin * dx - heading_cos * dy
        forward = heading_cos * dx + heading_sin * dy
        return tuple(
            (float(r), float(f)) for r, f in zip(right, forward, strict=True)
        )
