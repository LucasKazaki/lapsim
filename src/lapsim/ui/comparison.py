"""Immutable display summaries for reproducible lap comparisons."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import numpy as np

from lapsim.events.endurance import EnduranceRunResult


STANDARD_GRAVITY_MPS2 = 9.80665


@dataclass(frozen=True, slots=True)
class LapSummary:
    lap_time_s: float
    peak_speed_kph: float
    average_speed_kph: float
    distance_m: float
    pack_energy_kwh: float
    peak_lateral_g: float


def summarize_lap(result: EnduranceRunResult, track_length_m: float) -> LapSummary:
    """Extract metrics from one complete run, rejecting missing or bad data."""

    if not result.completed or result.completed_laps != 1 or result.telemetry is None:
        raise ValueError("A complete one-lap run with telemetry is required")
    if not isfinite(track_length_m) or track_length_m <= 0.0:
        raise ValueError("Track length must be finite and positive")
    speed_mps = np.asarray(result.telemetry["vehicle.speed_mps"], dtype=float)
    lateral_mps2 = np.asarray(
        result.telemetry["vehicle.lateral_acceleration_mps2"], dtype=float
    )
    if speed_mps.size == 0 or lateral_mps2.size == 0:
        raise ValueError("Run telemetry is empty")
    if not np.all(np.isfinite(speed_mps)) or not np.all(np.isfinite(lateral_mps2)):
        raise ValueError("Run telemetry contains non-finite values")
    if not isfinite(result.driving_time_s) or result.driving_time_s <= 0.0:
        raise ValueError("Lap time must be finite and positive")
    if not isfinite(result.pack_energy_kwh):
        raise ValueError("Run energy must be finite")
    return LapSummary(
        lap_time_s=result.driving_time_s,
        peak_speed_kph=float(np.max(speed_mps)) * 3.6,
        average_speed_kph=track_length_m / result.driving_time_s * 3.6,
        distance_m=track_length_m,
        pack_energy_kwh=result.pack_energy_kwh,
        peak_lateral_g=float(np.max(np.abs(lateral_mps2))) / STANDARD_GRAVITY_MPS2,
    )
