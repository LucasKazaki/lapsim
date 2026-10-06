"""Bounded, grip-aware *proposal* for one optional racing-line trial.

The geometric planner remains independent of the road scenario. This module
proposes a local, smooth shift around one group of its processed baseline's
low-grip wheel contacts. It checks the declared scalar corridor, polygon
geometry, requested cell size, and the same path-specific road mapper used by
the lap model. Lower weighted grip exposure only decides which *one* detour
is worth a full model trial; it says nothing about lap-time improvement or
continuous vehicle-footprint clearance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from numbers import Real
from time import perf_counter

import numpy as np

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.dynamics.conditions import PlanarRoad
from lapsim.optimization.racing_line import (
    RacingLinePlan,
    _corridor_bounds_at,
    _has_nonadjacent_segment_intersection,
    _track_from_closed_points,
)
from lapsim.optimization.road_grip_schedule import world_patch_grip_schedule
from vehicle_model import Vehicle


_MAX_PATCHES = 1
_MAX_CONTACT_GROUPS = 2
_MAX_ABSOLUTE_OFFSET_M = 3.0
_MIN_EXPOSURE_REDUCTION_M = 0.01
_AMPLITUDE_FRACTIONS = (0.50, 0.75, 1.0)


@dataclass(frozen=True, slots=True)
class GripDetourProposal:
    """One candidate, or a transparent reason that none passed screening.

    ``exposure_m`` is the path-length integral of the relative reduction
    below the road's uniform grip. It is a geometric screening proxy, not a
    predicted time, friction-circle proof, or measured road condition.
    ``candidate_count`` counts constructed geometries before the inexpensive
    screens; ``mapped_candidate_count`` counts completed world-road maps.
    """

    status: str
    reason: str
    track: SpatialTrack | None = field(default=None, repr=False, compare=False)
    side: str | None = None
    max_offset_m: float | None = None
    baseline_exposure_m: float | None = None
    candidate_exposure_m: float | None = None
    baseline_reduced_grip_cells: int | None = None
    candidate_reduced_grip_cells: int | None = None
    baseline_reduced_grip_distance_m: float | None = None
    candidate_reduced_grip_distance_m: float | None = None
    candidate_count: int = 0
    mapped_candidate_count: int = 0
    compute_time_s: float = 0.0


def _exposure(
    track: SpatialTrack, schedule: tuple[float, ...], uniform: float,
) -> tuple[float, int, float]:
    reduced = tuple(value < uniform for value in schedule)
    return (
        sum(length * max(0.0, 1.0 - grip / uniform)
            for length, grip in zip(track.cell_length_m, schedule, strict=True)),
        sum(reduced),
        sum(length for length, is_reduced in zip(
            track.cell_length_m, reduced, strict=True,
        ) if is_reduced),
    )


def _contact_groups(mask: tuple[bool, ...]) -> list[tuple[int, int]]:
    """Return cyclic contact groups as (start index, cell count)."""

    count = len(mask)
    if not any(mask) or all(mask):
        return []
    starts = [index for index, hit in enumerate(mask)
              if hit and not mask[(index - 1) % count]]
    groups = []
    for start in starts:
        length = 0
        while mask[(start + length) % count]:
            length += 1
        groups.append((start, length))
    return groups


def _quintic_plateau_pulse(
    station_m: np.ndarray, *, start_m: float, width_m: float,
    transition_m: float, lap_length_m: float,
) -> np.ndarray:
    """C2 periodic plateau over the baseline's affected cells.

    The quintic 6u^5 - 15u^4 + 10u^3 has zero first and second derivatives
    at both shoulder endpoints, avoiding a curvature jump in the nominal
    offset function where the detour rejoins the processed reference.
    """

    def smoothstep(fraction: np.ndarray) -> np.ndarray:
        return fraction**3 * (fraction * (6.0 * fraction - 15.0) + 10.0)

    from_start = np.mod(station_m - start_m, lap_length_m)
    pulse = np.zeros_like(from_start)
    pulse[from_start <= width_m] = 1.0
    leaving = (from_start > width_m) & (
        from_start < width_m + transition_m
    )
    pulse[leaving] = 1.0 - smoothstep(
        (from_start[leaving] - width_m) / transition_m
    )
    approaching = from_start > lap_length_m - transition_m
    pulse[approaching] = 1.0 - smoothstep(
        (lap_length_m - from_start[approaching]) / transition_m
    )
    return pulse


def propose_grip_detour(
    plan: RacingLinePlan,
    vehicle: Vehicle,
    road: PlanarRoad,
    *,
    maximum_cell_length_m: float | None = None,
) -> GripDetourProposal:
    """Suggest one lower-exposure local detour for a subsequent model trial.

    At most two cyclic contact groups, both sides, and three amplitudes per
    side are screened. No optimizer, lap solve, or tuning loop runs here.
    A result with ``track`` still requires the full modeled-arc corridor
    audit and lap-model timing before it can be compared or selected.
    """

    if not isinstance(plan, RacingLinePlan):
        raise TypeError("plan must be a RacingLinePlan")
    if not isinstance(vehicle, Vehicle):
        raise TypeError("vehicle must be a Vehicle")
    if not isinstance(road, PlanarRoad):
        raise TypeError("road must be a PlanarRoad")
    if maximum_cell_length_m is not None and (
        isinstance(maximum_cell_length_m, bool)
        or not isinstance(maximum_cell_length_m, Real)
        or not isfinite(maximum_cell_length_m)
        or maximum_cell_length_m <= 0.0
    ):
        raise ValueError("maximum_cell_length_m must be finite and positive")

    start_time = perf_counter()

    def result(status: str, reason: str, **details: object) -> GripDetourProposal:
        return GripDetourProposal(
            status=status, reason=reason,
            compute_time_s=perf_counter() - start_time,
            **details,
        )

    if not road.patches:
        return result("no_patch", "No local low-grip patch was supplied.")
    if len(road.patches) > _MAX_PATCHES:
        return result(
            "unsupported_road",
            "The bounded detour proposer supports one patch at a time.",
        )
    if plan.corridor is None or plan.source_station_m is None:
        return result(
            "missing_corridor",
            "A planner-created processed baseline and declared corridor are required.",
        )
    baseline = plan.baseline_track
    count = baseline.cell_count
    if (
        not baseline.closed or count != len(plan.offset_m)
        or len(plan.source_station_m) != len(plan.corridor.left_width_m) + 1
        or plan.source_station_m[0] != 0.0
        or plan.source_station_m[-1] <= 0.0
    ):
        return result(
            "unaligned_plan",
            "Processed baseline, planner grid, and source corridor are not aligned.",
        )
    if count > 5_000:
        return result("compute_cap", "The detour grid exceeds 5000 cells.")

    # The path-specific mapper intentionally fails on an unsupported road or
    # a baseline whose modeled curvature does not close. Preserve that reason.
    try:
        baseline_schedule = world_patch_grip_schedule(baseline, vehicle, road)
    except (ValueError, RuntimeError, ArithmeticError, OverflowError) as error:
        return result("baseline_mapping_failed", str(error))
    uniform = vehicle.tire.road_grip_multiplier * road.base_friction_multiplier
    baseline_exposure, baseline_cells, baseline_distance = _exposure(
        baseline, baseline_schedule, uniform,
    )
    diagnostic = dict(
        baseline_exposure_m=baseline_exposure,
        baseline_reduced_grip_cells=baseline_cells,
        baseline_reduced_grip_distance_m=baseline_distance,
    )
    if baseline_cells == 0:
        return result(
            "no_patch_contact",
            "The processed baseline's nominal wheel centers never touch the patch.",
            **diagnostic,
        )
    contact_mask = tuple(value < uniform for value in baseline_schedule)
    groups = _contact_groups(contact_mask)
    if not groups:
        return result(
            "no_local_group",
            "Low-grip contact occupies the complete closed path.",
            **diagnostic,
        )

    source_length_m = float(plan.source_station_m[-1])
    station_spacing_m = source_length_m / count
    station_m = np.arange(count, dtype=float) * station_spacing_m
    source_station_m = np.asarray(plan.source_station_m, dtype=float)
    # More than a few grid cells are needed on each shoulder to avoid a
    # discontinuous steering demand. Refuse a near-global bump.
    transition_m = max(
        12.0, 5.0 * vehicle.chassis.wheelbase_m,
        6.0 * station_spacing_m,
    )
    baseline_x = np.asarray(baseline.x_m[:-1], dtype=float)
    baseline_y = np.asarray(baseline.y_m[:-1], dtype=float)
    tangent_x = np.roll(baseline_x, -1) - np.roll(baseline_x, 1)
    tangent_y = np.roll(baseline_y, -1) - np.roll(baseline_y, 1)
    tangent_length = np.hypot(tangent_x, tangent_y)
    if float(np.min(tangent_length)) < 1e-5:
        return result(
            "undefined_normal", "The processed baseline has an undefined tangent.",
            **diagnostic,
        )
    normal_x, normal_y = -tangent_y / tangent_length, tangent_x / tangent_length
    half_width = 0.5 * plan.corridor.vehicle_width_m + plan.corridor.safety_margin_m
    constraint_stations = np.unique(np.concatenate((
        station_m,
        source_station_m[:-1],
        0.5 * (source_station_m[:-1] + source_station_m[1:]),
    )))
    lower, upper = _corridor_bounds_at(
        constraint_stations, source_station_m, plan.corridor, half_width,
    )

    # Prioritize the greatest affected length, but cap geometry attempts.
    groups.sort(key=lambda group: (
        -sum(baseline.cell_length_m[(group[0] + i) % count]
             for i in range(group[1])), group[0],
    ))
    best: tuple[tuple[float, float, float, int], SpatialTrack, str,
                float, float, int, float] | None = None
    candidate_count = 0
    mapped_count = 0
    for group_start, group_length in groups[:_MAX_CONTACT_GROUPS]:
        width_m = group_length * station_spacing_m
        if width_m + 2.0 * transition_m >= 0.9 * source_length_m:
            continue
        start_m = group_start * station_spacing_m
        pulse = _quintic_plateau_pulse(
            station_m, start_m=start_m, width_m=width_m,
            transition_m=transition_m, lap_length_m=source_length_m,
        )
        constraint_pulse = _quintic_plateau_pulse(
            constraint_stations, start_m=start_m, width_m=width_m,
            transition_m=transition_m, lap_length_m=source_length_m,
        )
        active = constraint_pulse > 1e-9
        if not bool(np.any(active)):
            continue
        for side_sign, side_name in ((1.0, "left"), (-1.0, "right")):
            room = upper if side_sign > 0.0 else -lower
            maximum_amplitude = min(
                _MAX_ABSOLUTE_OFFSET_M,
                0.9 * float(np.min(room[active] / constraint_pulse[active])),
            )
            if not isfinite(maximum_amplitude) or maximum_amplitude < 0.05:
                continue
            for fraction in _AMPLITUDE_FRACTIONS:
                amplitude = maximum_amplitude * fraction
                offset = side_sign * amplitude * pulse
                candidate_count += 1
                candidate_x = baseline_x + offset * normal_x
                candidate_y = baseline_y + offset * normal_y
                base_dx = np.roll(baseline_x, -1) - baseline_x
                base_dy = np.roll(baseline_y, -1) - baseline_y
                candidate_dx = np.roll(candidate_x, -1) - candidate_x
                candidate_dy = np.roll(candidate_y, -1) - candidate_y
                denominator = np.hypot(base_dx, base_dy) * np.hypot(
                    candidate_dx, candidate_dy,
                )
                if float(np.min(denominator)) < 1e-10:
                    continue
                forward = (base_dx * candidate_dx + base_dy * candidate_dy) / denominator
                if not np.all(np.isfinite(forward)) or float(np.min(forward)) < 0.15:
                    continue
                try:
                    candidate = _track_from_closed_points(candidate_x, candidate_y)
                except ValueError:
                    continue
                # Keep the processed baseline's stations and cell count so
                # the existing modeled-path audit compares like with like.
                # Refining only this detour would break that alignment.
                if (
                    maximum_cell_length_m is not None
                    and max(candidate.cell_length_m) > maximum_cell_length_m + 1e-10
                ):
                    continue
                try:
                    schedule = world_patch_grip_schedule(candidate, vehicle, road)
                except (ValueError, RuntimeError, ArithmeticError, OverflowError):
                    continue
                mapped_count += 1
                exposure, reduced_cells, reduced_distance = _exposure(
                    candidate, schedule, uniform,
                )
                if baseline_exposure - exposure < _MIN_EXPOSURE_REDUCTION_M:
                    continue
                if _has_nonadjacent_segment_intersection(candidate_x, candidate_y):
                    continue
                # Exposure is a screening proxy only. Use path length and
                # absolute offset as deterministic tie-breakers; the lap
                # model makes the eventual time decision.
                score = (exposure, candidate.length_m, amplitude, candidate_count)
                if best is None or score < best[0]:
                    best = (
                        score, candidate, side_name, amplitude,
                        exposure, reduced_cells, reduced_distance,
                    )

    work = dict(candidate_count=candidate_count,
                mapped_candidate_count=mapped_count)
    if best is None:
        return result(
            "no_lower_exposure_detour",
            "No bounded smooth detour reduced modeled wheel-contact grip exposure.",
            **diagnostic, **work,
        )
    _, track, side, amplitude, exposure, reduced_cells, reduced_distance = best
    return result(
        "candidate",
        "One lower-exposure detour is ready for modeled-path audit and lap timing.",
        track=track, side=side, max_offset_m=amplitude,
        candidate_exposure_m=exposure,
        candidate_reduced_grip_cells=reduced_cells,
        candidate_reduced_grip_distance_m=reduced_distance,
        **diagnostic, **work,
    )


__all__ = ["GripDetourProposal", "propose_grip_detour"]
