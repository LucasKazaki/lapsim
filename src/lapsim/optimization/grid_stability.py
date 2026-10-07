"""Optional paired grid-sensitivity diagnostic for an already eligible AI trial.

The function in this module is deliberately separate from racing-line selection.
It subdivides the *same* two prescribed paths, reruns the same car settings, and
reports whether the candidate-minus-baseline time difference changes sign or
crosses the caller's selection margin. One extra grid is a sensitivity check,
not a convergence proof, path-clearance audit, or reason to promote a new line.

An optional per-cell grip tuple means an absolute, piecewise-constant road
multiplier on each original path cell. Refinement repeats that value across
the cell's subdivisions. Alternatively, a supplied world-fixed road is
remapped onto each refined modeled path, using the original path's entry
heading so chord interpolation cannot rotate a coherent course.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import ceil, isfinite
from numbers import Real

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.dynamics.conditions import PlanarRoad
from lapsim.optimization.road_grip_schedule import (
    modeled_entry_heading_rad, world_patch_grip_schedule,
)
from vehicle_model import Vehicle


MAX_GRID_STABILITY_CELLS = 5_000


@dataclass(frozen=True, slots=True)
class PairedGridStabilityReport:
    """One bounded resolution probe, with no implication of path eligibility."""

    status: str
    original_baseline_time_s: float
    original_candidate_time_s: float
    original_candidate_minus_baseline_s: float
    refined_baseline_time_s: float | None
    refined_candidate_time_s: float | None
    refined_candidate_minus_baseline_s: float | None
    sign_stable: bool | None
    selection_margin_stable: bool | None
    selection_margin_s: float
    maximum_refined_cell_length_m: float
    original_baseline_cells: int
    original_candidate_cells: int
    refined_baseline_cells: int | None
    refined_candidate_cells: int | None
    failure_reason: str | None = None


def _finite_number(value: float, name: str, *, positive: bool) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not isfinite(value)
        or (value <= 0.0 if positive else value < 0.0)
    ):
        qualifier = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be finite and {qualifier}")
    return float(value)


def _subdivision_counts(
    track: SpatialTrack, maximum_cell_length_m: float,
) -> tuple[int, ...] | None:
    """Preflight the 5k limit before allocating any refined track arrays."""

    counts: list[int] = []
    total = 0
    for length_m in track.cell_length_m:
        ratio = length_m / maximum_cell_length_m
        if not isfinite(ratio) or ratio > MAX_GRID_STABILITY_CELLS - total:
            return None
        count = ceil(ratio)
        total += count
        counts.append(count)
    return tuple(counts)


def _validate_grip(
    values: tuple[float, ...] | None, track: SpatialTrack, name: str,
) -> tuple[float, ...] | None:
    if values is None:
        return None
    if type(values) is not tuple or len(values) != track.cell_count:
        raise ValueError(f"{name} must be one immutable value per original cell")
    return tuple(
        _finite_number(value, name, positive=True)
        for value in values
    )


def _refined_grip(
    original: tuple[float, ...] | None, counts: tuple[int, ...],
) -> tuple[float, ...] | None:
    if original is None:
        return None
    return tuple(
        value
        for value, count in zip(original, counts, strict=True)
        for _ in range(count)
    )


def _sign(value: float) -> int:
    return (value > 0.0) - (value < 0.0)


def diagnose_paired_grid_stability(
    vehicle: Vehicle,
    baseline_track: SpatialTrack,
    candidate_track: SpatialTrack,
    *,
    original_baseline_time_s: float,
    original_candidate_time_s: float,
    torque_request_fraction: float,
    speed_periodic: bool = False,
    maximum_refined_cell_length_m: float | None = None,
    selection_margin_s: float = 0.05,
    baseline_cell_road_grip_multiplier: tuple[float, ...] | None = None,
    candidate_cell_road_grip_multiplier: tuple[float, ...] | None = None,
    road: PlanarRoad | None = None,
) -> PairedGridStabilityReport:
    """Rerun an eligible baseline/candidate pair on boundary-preserving grids.

    ``vehicle`` is the same configured, pre-run car used for the original
    comparison. It is copied for each refined path, so the caller's instance
    is not advanced. The original times are trusted inputs; callers must have
    established both original paths' audit eligibility separately. The default
    is a one-pass lap, matching racing-line comparison; callers that compared
    speed-periodic laps must explicitly request the same policy here.

    The default target halves the smaller of the two original maximum cell
    lengths. A count above 5,000 on either path returns ``cell_cap_exceeded``
    before allocation or physics. Model failures are reported without treating
    a missing refined time as evidence of stability. This routine does not
    re-audit corridor geometry and never selects a path. A world-fixed ``road``
    is mutually exclusive with original per-cell grip schedules; the latter
    are station-local values, not world-fixed rectangles. Road mapping failure
    produces an explicit non-completed report before either physics solve.
    """

    if not isinstance(baseline_track, SpatialTrack) or not isinstance(candidate_track, SpatialTrack):
        raise TypeError("baseline_track and candidate_track must be SpatialTrack")
    if not baseline_track.closed or not candidate_track.closed:
        raise ValueError("paired grid stability requires two closed tracks")
    if type(speed_periodic) is not bool:
        raise TypeError("speed_periodic must be bool")
    if road is not None and not isinstance(road, PlanarRoad):
        raise TypeError("road must be a PlanarRoad or None")
    if road is not None and (
        baseline_cell_road_grip_multiplier is not None
        or candidate_cell_road_grip_multiplier is not None
    ):
        raise ValueError("road cannot be combined with original per-cell grip schedules")
    baseline_time_s = _finite_number(
        original_baseline_time_s, "original_baseline_time_s", positive=True,
    )
    candidate_time_s = _finite_number(
        original_candidate_time_s, "original_candidate_time_s", positive=True,
    )
    torque_fraction = _finite_number(
        torque_request_fraction, "torque_request_fraction", positive=False,
    )
    if torque_fraction > 1.0:
        raise ValueError("torque_request_fraction must be at most 1")
    margin_s = _finite_number(selection_margin_s, "selection_margin_s", positive=False)
    baseline_grip = _validate_grip(
        baseline_cell_road_grip_multiplier, baseline_track,
        "baseline_cell_road_grip_multiplier",
    )
    candidate_grip = _validate_grip(
        candidate_cell_road_grip_multiplier, candidate_track,
        "candidate_cell_road_grip_multiplier",
    )

    smaller_original_max_m = min(
        max(baseline_track.cell_length_m), max(candidate_track.cell_length_m),
    )
    target_m = _finite_number(
        smaller_original_max_m / 2.0
        if maximum_refined_cell_length_m is None
        else maximum_refined_cell_length_m,
        "maximum_refined_cell_length_m", positive=True,
    )
    if target_m >= smaller_original_max_m:
        raise ValueError(
            "maximum_refined_cell_length_m must refine both original paths"
        )

    baseline_counts = _subdivision_counts(baseline_track, target_m)
    candidate_counts = _subdivision_counts(candidate_track, target_m)
    baseline_refined_cells = sum(baseline_counts) if baseline_counts is not None else None
    candidate_refined_cells = sum(candidate_counts) if candidate_counts is not None else None
    original_delta_s = candidate_time_s - baseline_time_s

    def report(
        status: str,
        *,
        refined_baseline_time_s: float | None = None,
        refined_candidate_time_s: float | None = None,
        failure_reason: str | None = None,
    ) -> PairedGridStabilityReport:
        refined_delta_s = (
            refined_candidate_time_s - refined_baseline_time_s
            if refined_baseline_time_s is not None and refined_candidate_time_s is not None
            else None
        )
        return PairedGridStabilityReport(
            status=status,
            original_baseline_time_s=baseline_time_s,
            original_candidate_time_s=candidate_time_s,
            original_candidate_minus_baseline_s=original_delta_s,
            refined_baseline_time_s=refined_baseline_time_s,
            refined_candidate_time_s=refined_candidate_time_s,
            refined_candidate_minus_baseline_s=refined_delta_s,
            sign_stable=(
                _sign(original_delta_s) == _sign(refined_delta_s)
                if refined_delta_s is not None else None
            ),
            selection_margin_stable=(
                (original_delta_s < -margin_s) == (refined_delta_s < -margin_s)
                if refined_delta_s is not None else None
            ),
            selection_margin_s=margin_s,
            maximum_refined_cell_length_m=target_m,
            original_baseline_cells=baseline_track.cell_count,
            original_candidate_cells=candidate_track.cell_count,
            refined_baseline_cells=baseline_refined_cells,
            refined_candidate_cells=candidate_refined_cells,
            failure_reason=failure_reason,
        )

    if baseline_counts is None or candidate_counts is None:
        return report(
            "cell_cap_exceeded",
            failure_reason=(
                "At least one refined path would exceed the 5000-cell "
                "diagnostic compute cap"
            ),
        )

    assert baseline_refined_cells is not None and candidate_refined_cells is not None
    refined_baseline = baseline_track.refine(target_m)
    refined_candidate = candidate_track.refine(target_m)
    if (
        refined_baseline.cell_count != baseline_refined_cells
        or refined_candidate.cell_count != candidate_refined_cells
    ):
        raise RuntimeError("refined grid does not match preflight subdivision counts")

    if road is None:
        baseline_refined_grip = _refined_grip(baseline_grip, baseline_counts)
        candidate_refined_grip = _refined_grip(candidate_grip, candidate_counts)
    else:
        try:
            # The original comparison used the original path's modeled
            # heading. Chord-interpolated refinement can change an automatic
            # coherent-arc versus polygon-tangent decision, so freeze it.
            baseline_heading = (
                modeled_entry_heading_rad(baseline_track)
                if road.patches else None
            )
            candidate_heading = (
                modeled_entry_heading_rad(candidate_track)
                if road.patches else None
            )
            baseline_refined_grip = world_patch_grip_schedule(
                refined_baseline, vehicle, road,
                initial_heading_rad=baseline_heading,
            )
            candidate_refined_grip = world_patch_grip_schedule(
                refined_candidate, vehicle, road,
                initial_heading_rad=candidate_heading,
            )
        except (ValueError, RuntimeError, ArithmeticError, OverflowError) as error:
            return report(
                "road_mapping_failed",
                failure_reason=f"Refined world road mapping failed: {type(error).__name__}: {error}",
            )
    from lapsim.ui.simulation import run_one_lap, run_speed_periodic_lap

    def run_refined(
        track: SpatialTrack, grip: tuple[float, ...] | None,
    ) -> tuple[float | None, str | None]:
        kwargs: dict[str, object] = {"torque_request_fraction": torque_fraction}
        if grip is not None:
            kwargs["cell_road_grip_multiplier"] = grip
        try:
            if speed_periodic:
                periodic = run_speed_periodic_lap(
                    deepcopy(vehicle), track,
                    maximum_lap_passes=2, speed_tolerance_mps=0.005,
                    **kwargs,
                )
                result = periodic.run
                if not periodic.converged:
                    return None, periodic.failure_reason or "speed seam did not converge"
            else:
                result = run_one_lap(deepcopy(vehicle), track, **kwargs)
        except (ValueError, RuntimeError, ArithmeticError, OverflowError) as error:
            return None, f"{type(error).__name__}: {error}"
        if not result.completed or not isfinite(result.driving_time_s) or result.driving_time_s <= 0.0:
            return None, result.failure_reason or "refined lap did not complete with a finite positive time"
        return result.driving_time_s, None

    refined_baseline_time_s, baseline_error = run_refined(
        refined_baseline, baseline_refined_grip,
    )
    if baseline_error is not None:
        return report("baseline_failed", failure_reason=baseline_error)
    refined_candidate_time_s, candidate_error = run_refined(
        refined_candidate, candidate_refined_grip,
    )
    if candidate_error is not None:
        return report(
            "candidate_failed", refined_baseline_time_s=refined_baseline_time_s,
            failure_reason=candidate_error,
        )
    return report(
        "completed", refined_baseline_time_s=refined_baseline_time_s,
        refined_candidate_time_s=refined_candidate_time_s,
    )


__all__ = [
    "MAX_GRID_STABILITY_CELLS", "PairedGridStabilityReport",
    "diagnose_paired_grid_stability",
]
