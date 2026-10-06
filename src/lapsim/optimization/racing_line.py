"""Optional, bounded minimum-curvature racing-line planning.

This is a path planner, not a learned policy or a replacement vehicle model.
It requires explicit left/right corridor clearance and builds *both* the
centerline and candidate from the same smoothed x/y samples. Each returned
``SpatialTrack`` has chord arc length and signed curvature recomputed from its
own geometry. The ordinary desktop lap remains on its original centerline.

Inspired by TUM FTM's open global racetrajectory planner:
https://github.com/TUMFTM/global_racetrajectory_optimization
The bounded minimum-curvature objective is a computationally cheap proposal,
not a proof of minimum lap time. Use ``compare_lines_with_lap_model`` to check
the proposed path with this repository's actual vehicle-dependent lap model.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from math import atan2, ceil, cos, hypot, isfinite, pi, sin
from numbers import Real
from time import perf_counter
from typing import Callable

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.interpolate import CubicSpline
from scipy.optimize import LinearConstraint, minimize

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.dynamics.conditions import PlanarRoad
from lapsim.events.endurance import EnduranceRunResult, LapProgressSnapshot
from lapsim.solvers.path_constraints import PathConstraintProgressSnapshot


@dataclass(frozen=True, slots=True)
class TrackCorridor:
    """Clearance from a reference line to left/right boundaries at each point.

    The start point is not repeated: arrays have ``track.cell_count`` entries.
    Clearances are relative to the smoothed reference constructed by the
    planner. A survey-derived corridor must use that same reference frame.
    ``source`` records whether dimensions were measured or assumed.
    """

    left_width_m: tuple[float, ...]
    right_width_m: tuple[float, ...]
    vehicle_width_m: float
    safety_margin_m: float = 0.0
    source: str = "unspecified"

    def __post_init__(self) -> None:
        if not self.left_width_m or len(self.left_width_m) != len(self.right_width_m):
            raise ValueError("left and right widths need equal, nonzero lengths")
        if any(not isfinite(v) or v <= 0.0 for v in (*self.left_width_m, *self.right_width_m)):
            raise ValueError("track widths must be finite and positive")
        if not isfinite(self.vehicle_width_m) or self.vehicle_width_m <= 0.0:
            raise ValueError("vehicle_width_m must be finite and positive")
        if not isfinite(self.safety_margin_m) or self.safety_margin_m < 0.0:
            raise ValueError("safety_margin_m must be finite and nonnegative")
        if not self.source.strip():
            raise ValueError("corridor source must be named")
        required = 0.5 * self.vehicle_width_m + self.safety_margin_m
        if any(min(left, right) <= required for left, right in zip(self.left_width_m, self.right_width_m)):
            raise ValueError("vehicle width and margin leave no usable corridor")

    @classmethod
    def constant(
        cls,
        track: SpatialTrack,
        *,
        left_width_m: float,
        right_width_m: float,
        vehicle_width_m: float,
        safety_margin_m: float = 0.0,
        source: str,
    ) -> "TrackCorridor":
        return cls(
            left_width_m=(left_width_m,) * track.cell_count,
            right_width_m=(right_width_m,) * track.cell_count,
            vehicle_width_m=vehicle_width_m,
            safety_margin_m=safety_margin_m,
            source=source,
        )


@dataclass(frozen=True, slots=True)
class RacingLinePlan:
    """Candidate, same-preprocessing baseline, and transparent diagnostics.

    Planner-created instances retain the explicit corridor and original source
    stations so comparison can check modeled arc positions. Legacy/manual
    plans without those inputs are ineligible for automatic path selection.
    """

    baseline_track: SpatialTrack
    candidate_track: SpatialTrack
    offset_m: tuple[float, ...]
    source_cell_center_offset_m: tuple[float, ...]
    status: str
    message: str
    objective_baseline: float
    objective_candidate: float
    max_abs_offset_m: float
    max_constraint_violation_m: float
    source_closure_error_m: float
    processing_shift_max_m: float
    source_vs_processed_length_m: float
    source_vs_processed_length_fraction: float
    corridor_fold_ratio_max: float
    iterations: int
    objective_evaluations: int
    compute_time_s: float
    corridor_source: str
    corridor: TrackCorridor | None = None
    source_station_m: tuple[float, ...] | None = None


@dataclass(frozen=True, slots=True)
class CurvaturePathAudit:
    """Clearance of the path actually integrated from cell curvature.

    The trajectory starts at the proposed path's first point, with its initial
    heading inferred from the first chord and half the start-vertex turn. Four
    points per cell are compared with the planner's processed reference and
    declared normal-coordinate corridor. The intervals between those points
    are certified with a conservative second-derivative bound, subdividing
    near a boundary. The integrated end position must also close near the
    start. On a certified path, ``minimum_corridor_slack_m`` is a conservative
    lower bound on clearance over every interval; on a failed path it includes
    the observed violation or unresolved interval bound. The certificate is
    for the declared scalar normal-coordinate model, not the vehicle's swept
    body or a surveyed pavement boundary.
    """

    valid: bool
    sample_count: int
    maximum_lateral_offset_m: float
    maximum_corridor_excess_m: float
    allowed_numerical_excess_m: float
    seam_position_error_m: float
    allowed_seam_position_error_m: float
    corridor_source: str
    vehicle_width_m: float
    safety_margin_m: float
    initial_heading_policy: str
    minimum_corridor_slack_m: float = 0.0
    continuous_clearance_certified: bool = False
    unresolved_clearance_intervals: int = 0
    clearance_status: str = "unavailable"


@dataclass(frozen=True, slots=True)
class RacingLineComparison:
    """Full-model timings for a centerline and bounded candidate trials.

    ``trials`` retains each attempted path and returned model run so callers
    can inspect or save every result without repeating the physics solve.
    ``candidate_*`` refers to the fastest eligible nonzero-strength trial,
    not necessarily the full-strength geometric proposal. If no candidate is
    eligible, its run/track retain a completed diagnostic trial when available.
    Eligible times require a completed model run, the requested speed-seam
    rule when enabled, and a passing continuous scalar curvature-path
    corridor audit.
    Completed but ineligible times remain in ``*_diagnostic_time_s``.
    ``selected_*`` uses the candidate only when its modeled time beats the
    baseline by more than ``selection_margin_s``. This margin is a conservative
    selection heuristic, not a proven numerical error bound. A faster but
    unresolved candidate remains available through ``candidate_*``.
    """

    baseline_time_s: float | None
    candidate_time_s: float | None
    baseline_run: EnduranceRunResult | None
    candidate_run: EnduranceRunResult | None
    candidate_track: SpatialTrack
    candidate_strength: float | None
    trials: tuple[RacingLineTrial, ...]
    rank_status: str
    selection_margin_s: float
    selected_mode: str
    selected_track: SpatialTrack
    selected_run: EnduranceRunResult | None
    baseline_error: str | None
    candidate_error: str | None
    compute_time_s: float
    baseline_path_audit: CurvaturePathAudit | None = None
    candidate_path_audit: CurvaturePathAudit | None = None
    baseline_diagnostic_time_s: float | None = None
    candidate_diagnostic_time_s: float | None = None
    baseline_cell_road_grip_multiplier: tuple[float, ...] | None = None


@dataclass(frozen=True, slots=True)
class RacingLineTrial:
    """One nonzero lateral-offset strength and its exact evaluated path/run."""

    strength: float
    path_length_m: float | None
    lap_time_s: float | None
    error: str | None
    path_audit: CurvaturePathAudit | None = None
    diagnostic_lap_time_s: float | None = None
    track: SpatialTrack | None = field(default=None, repr=False, compare=False)
    run: EnduranceRunResult | None = field(default=None, repr=False, compare=False)
    cell_road_grip_multiplier: tuple[float, ...] | None = field(
        default=None, repr=False, compare=False,
    )


def _periodic_cubic_basis_at(
    station_m: np.ndarray, track_length_m: float, control_count: int
) -> np.ndarray:
    """Uniform periodic cubic B-spline weights; each row is a convex blend."""

    parameter = station_m * control_count / track_length_m
    segment = np.floor(parameter).astype(int)
    t = parameter - segment
    weights = np.column_stack(
        ((1.0 - t) ** 3 / 6.0,
         (3.0 * t**3 - 6.0 * t**2 + 4.0) / 6.0,
         (-3.0 * t**3 + 3.0 * t**2 + 3.0 * t + 1.0) / 6.0,
         t**3 / 6.0)
    )
    basis = np.zeros((len(station_m), control_count), dtype=float)
    rows = np.arange(len(station_m))
    for column, shift in enumerate((-1, 0, 1, 2)):
        basis[rows, (segment + shift) % control_count] += weights[:, column]
    return basis


def _periodic_cubic_basis(station_count: int, control_count: int) -> np.ndarray:
    return _periodic_cubic_basis_at(
        np.arange(station_count, dtype=float), float(station_count), control_count
    )


def _corridor_bounds_at(
    station_m: np.ndarray,
    source_station_m: np.ndarray,
    corridor: TrackCorridor,
    half_vehicle_plus_margin_m: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Cell widths at stations; shared cell boundaries use the narrower side."""

    # The lap endpoint is the same physical seam as station zero. Without
    # wrapping it, searchsorted clips L into the last cell and misses the
    # first cell's potentially narrower boundary at the final audit sample.
    station_m = np.mod(station_m, source_station_m[-1])
    cell = np.minimum(
        np.searchsorted(source_station_m, station_m, side="right") - 1,
        len(corridor.left_width_m) - 1,
    )
    left = np.asarray(corridor.left_width_m)[cell].copy()
    right = np.asarray(corridor.right_width_m)[cell].copy()
    at_boundary = np.isclose(station_m, source_station_m[cell], rtol=0.0, atol=1e-9)
    previous = (cell - 1) % len(corridor.left_width_m)
    left[at_boundary] = np.minimum(left[at_boundary], np.asarray(corridor.left_width_m)[previous[at_boundary]])
    right[at_boundary] = np.minimum(right[at_boundary], np.asarray(corridor.right_width_m)[previous[at_boundary]])
    return half_vehicle_plus_margin_m - right, left - half_vehicle_plus_margin_m


def _continuous_offset_violation(
    controls: np.ndarray,
    source_station_m: np.ndarray,
    corridor: TrackCorridor,
    half_vehicle_plus_margin_m: float,
) -> float:
    """Exact cubic extrema against each source cell's constant width.

    This certifies the *lateral offset function* relative to the processed
    reference, not surveyed pavement or between-cell boundary geometry.
    """

    control_count = len(controls)
    knot_length = source_station_m[-1] / control_count
    coefficients: list[tuple[float, float, float, float]] = []
    for knot in range(control_count):
        left = controls[(knot - 1) % control_count]
        center = controls[knot]
        right = controls[(knot + 1) % control_count]
        far_right = controls[(knot + 2) % control_count]
        coefficients.append((
            (left + 4.0 * center + right) / 6.0,
            (-left + right) / 2.0,
            (left - 2.0 * center + right) / 2.0,
            (-left + 3.0 * center - 3.0 * right + far_right) / 6.0,
        ))
    maximum_violation = 0.0
    for cell in range(len(corridor.left_width_m)):
        start_m = source_station_m[cell]
        end_m = source_station_m[cell + 1]
        lower = half_vehicle_plus_margin_m - corridor.right_width_m[cell]
        upper = corridor.left_width_m[cell] - half_vehicle_plus_margin_m
        first_knot = int(np.floor(start_m / knot_length))
        last_knot = min(control_count - 1, int(np.floor(np.nextafter(end_m, -np.inf) / knot_length)))
        for knot in range(first_knot, last_knot + 1):
            knot_start = knot * knot_length
            lo = max(start_m, knot_start) / knot_length - knot
            hi = min(end_m, knot_start + knot_length) / knot_length - knot
            a0, a1, a2, a3 = coefficients[knot]
            locations = [lo, hi]
            if abs(a3) > 1e-14:
                discriminant = a2 * a2 - 3.0 * a3 * a1
                if discriminant >= 0.0:
                    root = discriminant**0.5
                    locations.extend(((-a2 - root) / (3.0 * a3), (-a2 + root) / (3.0 * a3)))
            elif abs(a2) > 1e-14:
                locations.append(-a1 / (2.0 * a2))
            for t in locations:
                if lo - 1e-12 <= t <= hi + 1e-12:
                    value = a0 + t * (a1 + t * (a2 + t * a3))
                    maximum_violation = max(maximum_violation, lower - value, value - upper)
    return maximum_violation


def _closed_chord_lengths_and_turns(
    x: np.ndarray, y: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Return each polygon edge length and signed turn at its start vertex."""

    dx = np.roll(x, -1) - x
    dy = np.roll(y, -1) - y
    lengths = np.hypot(dx, dy)
    if not np.all(np.isfinite(lengths)) or float(np.min(lengths)) < 1e-5:
        raise ValueError("candidate contains a degenerate path cell")
    prev_dx = np.roll(dx, 1)
    prev_dy = np.roll(dy, 1)
    next_chord = np.hypot(prev_dx + dx, prev_dy + dy)
    if float(np.min(next_chord)) < 1e-5:
        raise ValueError("candidate folds back across a path point")
    cross = prev_dx * dy - prev_dy * dx
    dot = prev_dx * dx + prev_dy * dy
    vertex_turn = np.arctan2(cross, dot)
    return lengths, vertex_turn


def _track_from_closed_points(x: np.ndarray, y: np.ndarray) -> SpatialTrack:
    """Recompute chord arc length and integral-consistent signed curvature.

    The discrete heading turn at each vertex is shared equally by its two
    adjacent cells. Thus ``sum(curvature_i * cell_length_i)`` equals the
    polygon's signed winding angle exactly, including across the lap seam.
    """

    lengths, vertex_turn = _closed_chord_lengths_and_turns(x, y)
    cell_curvature = 0.5 * (vertex_turn + np.roll(vertex_turn, -1)) / lengths
    distance = np.concatenate(([0.0], np.cumsum(lengths)))
    return SpatialTrack(
        distance_m=tuple(float(v) for v in distance),
        x_m=tuple(float(v) for v in np.append(x, x[0])),
        y_m=tuple(float(v) for v in np.append(y, y[0])),
        curvature_per_m=tuple(float(v) for v in cell_curvature),
        closed=True,
    )


def _has_nonadjacent_segment_intersection(x: np.ndarray, y: np.ndarray) -> bool:
    """Reject crossings/touches outside neighboring closed-path segments.

    Axis-aligned filtering keeps the exact segment tests local on ordinary
    courses. The worst case is O(N^2) and the planner limits N to 5000.
    """

    count = len(x)
    next_x = np.roll(x, -1)
    next_y = np.roll(y, -1)
    dx = next_x - x
    dy = next_y - y
    x_low = np.minimum(x, next_x)
    x_high = np.maximum(x, next_x)
    y_low = np.minimum(y, next_y)
    y_high = np.maximum(y, next_y)
    for i in range(count - 2):
        other = np.arange(i + 2, count)
        if i == 0:
            other = other[:-1]  # closing segment shares the start point
        nearby = (
            (x_low[i] <= x_high[other])
            & (x_low[other] <= x_high[i])
            & (y_low[i] <= y_high[other])
            & (y_low[other] <= y_high[i])
        )
        other = other[nearby]
        if not len(other):
            continue
        qx, qy = x[other] - x[i], y[other] - y[i]
        denominator = dx[i] * dy[other] - dy[i] * dx[other]
        tolerance = 1e-10 * np.maximum(
            1.0, np.hypot(dx[i], dy[i]) * np.hypot(dx[other], dy[other])
        )
        regular = np.abs(denominator) > tolerance
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (qx * dy[other] - qy * dx[other]) / denominator
            u = (qx * dy[i] - qy * dx[i]) / denominator
        crossing = regular & (t >= -1e-9) & (t <= 1.0 + 1e-9) & (u >= -1e-9) & (u <= 1.0 + 1e-9)
        collinear = (~regular) & (np.abs(qx * dy[i] - qy * dx[i]) <= tolerance)
        if bool(np.any(crossing | collinear)):
            return True
    return False


class RacingLinePlanner:
    """Propose a smooth line inside a known corridor with bounded work.

    ``length_penalty`` has units 1/m². It multiplies relative path-length
    change so both terms in the geometric objective have units 1/m².
    ``maximum_cell_length_m`` optionally bounds the actual physics cells in
    both generated paths. The generated geometry can be locally longer than
    its nominal station spacing, so the planner increases its sample count
    and rebuilds the paths when necessary. Omitting it preserves the legacy
    nominal-spacing behavior.
    """

    def __init__(
        self,
        *,
        sample_spacing_m: float = 2.0,
        control_count: int = 24,
        smoothing_m: float = 0.8,
        maximum_iterations: int = 60,
        length_penalty: float = 0.01,
        maximum_cell_length_m: float | None = None,
    ) -> None:
        if not isfinite(sample_spacing_m) or sample_spacing_m <= 0.0:
            raise ValueError("sample_spacing_m must be finite and positive")
        if control_count < 8 or control_count > 64:
            raise ValueError("control_count must be 8 through 64")
        if not isfinite(smoothing_m) or smoothing_m < 0.0:
            raise ValueError("smoothing_m must be finite and nonnegative")
        if maximum_iterations < 1 or maximum_iterations > 200:
            raise ValueError("maximum_iterations must be 1 through 200")
        if not isfinite(length_penalty) or length_penalty < 0.0:
            raise ValueError("length_penalty must be finite and nonnegative")
        if maximum_cell_length_m is not None and (
            isinstance(maximum_cell_length_m, bool)
            or not isinstance(maximum_cell_length_m, Real)
            or not isfinite(maximum_cell_length_m)
            or maximum_cell_length_m <= 0.0
        ):
            raise ValueError("maximum_cell_length_m must be finite and positive")
        self.sample_spacing_m = sample_spacing_m
        self.control_count = control_count
        self.smoothing_m = smoothing_m
        self.maximum_iterations = maximum_iterations
        self.length_penalty = length_penalty
        self.maximum_cell_length_m = maximum_cell_length_m

    def plan(self, track: SpatialTrack, corridor: TrackCorridor) -> RacingLinePlan:
        """Return candidate and baseline; no car simulation is run here.

        The corridor must be supplied explicitly. The spline offset is
        checked against every supplied piecewise width, including its cubic
        extrema. This only certifies the declared numerical corridor, not
        unmeasured pavement or physical track survey quality.
        """

        if not track.closed:
            raise ValueError("racing-line planning requires a closed course")
        if track.cell_count < 4:
            raise ValueError("racing-line planning requires at least four geometry cells")
        if len(corridor.left_width_m) != track.cell_count:
            raise ValueError("corridor widths must match reference track cells")
        spacing_m = (
            self.sample_spacing_m if self.maximum_cell_length_m is None
            else min(self.sample_spacing_m, self.maximum_cell_length_m)
        )
        count = max(ceil(track.length_m / spacing_m), 4 * self.control_count, 32)
        if count > 5000:
            raise ValueError("planner grid exceeds its 5000-point compute cap")
        total_start = perf_counter()
        for _ in range(8):
            plan = self._plan_at_count(track, corridor, count)
            if self.maximum_cell_length_m is None:
                return plan
            actual_maximum_m = max(
                max(plan.baseline_track.cell_length_m),
                max(plan.candidate_track.cell_length_m),
            )
            if actual_maximum_m <= self.maximum_cell_length_m + 1e-10:
                return replace(plan, compute_time_s=perf_counter() - total_start)
            if count == 5000:
                raise ValueError(
                    "AI path cannot meet the requested maximum cell length "
                    "within the 5000-point compute cap"
                )
            # Uniform source stations do not imply uniformly long offset
            # chords. Increase the count based on the longest actual cell,
            # with a small margin to avoid roundoff-triggered repeat solves.
            # Try the cap itself before rejecting a margin-induced overshoot.
            count = min(5000, max(
                count + 1,
                ceil(count * actual_maximum_m / self.maximum_cell_length_m * 1.01),
            ))
        raise ValueError(
            "AI path cannot meet the requested maximum cell length "
            "within eight bounded planning attempts"
        )

    def _plan_at_count(
        self, track: SpatialTrack, corridor: TrackCorridor, count: int,
    ) -> RacingLinePlan:
        start = perf_counter()
        source_station = np.asarray(track.distance_m, dtype=float)
        station = np.arange(count, dtype=float) * track.length_m / count
        source_x = np.asarray(track.x_m, dtype=float)
        source_y = np.asarray(track.y_m, dtype=float)
        closure_error = hypot(source_x[-1] - source_x[0], source_y[-1] - source_y[0])
        # Bring the noisy endpoint onto the start by a visible, recorded repair.
        corrected_x = source_x - (source_station / track.length_m) * (source_x[-1] - source_x[0])
        corrected_y = source_y - (source_station / track.length_m) * (source_y[-1] - source_y[0])
        corrected_x[-1], corrected_y[-1] = corrected_x[0], corrected_y[0]
        # Periodic cubic interpolation avoids curvature aliasing when source
        # and planner stations differ, and closes the reference tangent at the
        # lap seam. Linear interpolation can create artificial corner spikes.
        raw_x = CubicSpline(source_station, corrected_x, bc_type="periodic")(station)
        raw_y = CubicSpline(source_station, corrected_y, bc_type="periodic")(station)
        sigma = self.smoothing_m / (track.length_m / count)
        if sigma:
            base_x = gaussian_filter1d(raw_x, sigma, mode="wrap")
            base_y = gaussian_filter1d(raw_y, sigma, mode="wrap")
        else:
            base_x, base_y = raw_x, raw_y
        original_x = np.interp(station, source_station, source_x)
        original_y = np.interp(station, source_station, source_y)
        processing_shift = float(np.max(np.hypot(base_x - original_x, base_y - original_y)))
        baseline = _track_from_closed_points(base_x, base_y)
        if _has_nonadjacent_segment_intersection(base_x, base_y):
            raise ValueError("reference centerline intersects itself after processing")
        tangent_x = np.roll(base_x, -1) - np.roll(base_x, 1)
        tangent_y = np.roll(base_y, -1) - np.roll(base_y, 1)
        tangent_norm = np.hypot(tangent_x, tangent_y)
        if float(np.min(tangent_norm)) < 1e-5:
            raise ValueError("reference line has an undefined tangent")
        normal_x, normal_y = -tangent_y / tangent_norm, tangent_x / tangent_norm
        half_width = 0.5 * corridor.vehicle_width_m + corridor.safety_margin_m
        base_lengths, base_vertex_turn = _closed_chord_lengths_and_turns(base_x, base_y)
        point_curvature = base_vertex_turn / (
            0.5 * (base_lengths + np.roll(base_lengths, 1))
        )
        # Include every source cell center: a locally wide source cell can be
        # shorter than the planner grid and would otherwise evade this guard.
        fold_station = np.unique(np.concatenate((
            station,
            0.5 * (source_station[:-1] + source_station[1:]),
        )))
        fold_lower, fold_upper = _corridor_bounds_at(
            fold_station, source_station, corridor, half_width
        )
        preceding = np.searchsorted(station, fold_station, side="right") - 1
        following = (preceding + 1) % count
        local_positive_curvature = np.maximum.reduce((
            np.maximum(point_curvature[preceding], 0.0),
            np.maximum(point_curvature[following], 0.0),
        ))
        local_negative_curvature = np.maximum.reduce((
            np.maximum(-point_curvature[preceding], 0.0),
            np.maximum(-point_curvature[following], 0.0),
        ))
        # The normal-coordinate map has tangential Jacobian 1 - kappa*d.
        # When the usable inside offset reaches the local bend radius, that
        # coordinate system folds and "inside the corridor" ceases to be a
        # meaningful local safety claim. Leave a 2% numerical buffer.
        corridor_fold_ratio = float(np.max(np.maximum(
            local_positive_curvature * fold_upper,
            local_negative_curvature * (-fold_lower),
        )))
        if corridor_fold_ratio >= 0.98:
            raise ValueError(
                "usable corridor reaches the local bend radius and folds in normal coordinates"
            )
        basis = _periodic_cubic_basis(count, self.control_count)
        # Solver stations alone can miss a source cell narrower than the
        # planner grid. Constrain every source cell at its center and both
        # boundaries, along with planner samples and midpoints.
        constraint_station = np.unique(np.concatenate((
            station,
            (station + track.length_m / (2.0 * count)) % track.length_m,
            source_station[:-1],
            0.5 * (source_station[:-1] + source_station[1:]),
        )))
        constraint_basis = _periodic_cubic_basis_at(
            constraint_station, track.length_m, self.control_count
        )
        lower, upper = _corridor_bounds_at(
            constraint_station, source_station, corridor, half_width
        )
        baseline_length = baseline.length_m

        def geometry(controls: np.ndarray) -> SpatialTrack:
            offsets = basis @ controls
            path_x = base_x + offsets * normal_x
            path_y = base_y + offsets * normal_y
            base_dx = np.roll(base_x, -1) - base_x
            base_dy = np.roll(base_y, -1) - base_y
            path_dx = np.roll(path_x, -1) - path_x
            path_dy = np.roll(path_y, -1) - path_y
            forward_cosine = (base_dx * path_dx + base_dy * path_dy) / (
                np.hypot(base_dx, base_dy) * np.hypot(path_dx, path_dy)
            )
            if not np.all(np.isfinite(forward_cosine)) or float(np.min(forward_cosine)) < 0.15:
                raise ValueError("candidate reverses direction relative to reference")
            return _track_from_closed_points(path_x, path_y)

        def unscaled_objective(controls: np.ndarray) -> float:
            try:
                candidate = geometry(controls)
            except ValueError:
                return 1e6
            curvature = np.asarray(candidate.curvature_per_m)
            lengths = np.diff(np.asarray(candidate.distance_m))
            return float(
                # Both terms have units 1/m²: mean curvature squared plus
                # a dimensioned weight times dimensionless relative length.
                np.sum(curvature * curvature * lengths) / candidate.length_m
                + self.length_penalty * (candidate.length_m / baseline_length - 1.0)
            )

        zero = np.zeros(self.control_count, dtype=float)
        # Curvature squared is about 1e-3 on a Formula SAE course. Multiplying
        # the numerical objective prevents SLSQP's absolute tolerances from
        # falsely declaring the zero-offset seed optimal after one iteration.
        objective_scale = 10_000.0

        def objective(controls: np.ndarray) -> float:
            return objective_scale * unscaled_objective(controls)

        baseline_objective = unscaled_objective(zero)
        result = minimize(
            objective,
            zero,
            method="SLSQP",
            jac="2-point",
            constraints=(LinearConstraint(constraint_basis, lower, upper),),
            bounds=[(float(np.min(lower)), float(np.max(upper)))] * self.control_count,
            options={"maxiter": self.maximum_iterations, "ftol": 1e-6, "disp": False},
        )
        controls = np.asarray(result.x, dtype=float)
        offsets = basis @ controls
        constrained_offset = constraint_basis @ controls
        violation = float(max(
            0.0,
            np.max(lower - constrained_offset),
            np.max(constrained_offset - upper),
            _continuous_offset_violation(controls, source_station, corridor, half_width),
        ))
        candidate_objective = unscaled_objective(controls)
        improved = candidate_objective < baseline_objective - 1e-9
        valid = bool(np.all(np.isfinite(controls)) and violation <= 1e-6 and improved)
        if valid:
            try:
                candidate = geometry(controls)
            except ValueError:
                valid = False
            else:
                if _has_nonadjacent_segment_intersection(
                    np.asarray(candidate.x_m[:-1]), np.asarray(candidate.y_m[:-1])
                ):
                    valid = False
        if not valid:
            candidate = baseline
            offsets = np.zeros(count, dtype=float)
            candidate_objective = baseline_objective
        status = "candidate" if valid else "centerline"
        if valid and not result.success:
            message = f"Bounded solver stopped after {result.nit} iterations; feasible candidate retained."
        elif valid:
            message = "Feasible geometric candidate; compare with the vehicle lap model before claiming time improvement."
        elif violation > 1e-6:
            message = "Optimization violated the corridor; centerline retained."
        elif improved:
            message = "Candidate geometry crossed itself or folded; centerline retained."
        else:
            message = "No better feasible geometric candidate; centerline retained."
        source_cell_centers = 0.5 * (source_station[:-1] + source_station[1:])
        center_offsets = (
            _periodic_cubic_basis_at(
                source_cell_centers, track.length_m, self.control_count
            ) @ controls
            if valid else np.zeros(track.cell_count)
        )
        return RacingLinePlan(
            baseline_track=baseline,
            candidate_track=candidate,
            offset_m=tuple(float(value) for value in offsets),
            source_cell_center_offset_m=tuple(float(value) for value in center_offsets),
            status=status,
            message=message,
            objective_baseline=baseline_objective,
            objective_candidate=candidate_objective,
            max_abs_offset_m=float(np.max(np.abs(offsets))),
            max_constraint_violation_m=violation,
            source_closure_error_m=closure_error,
            processing_shift_max_m=processing_shift,
            source_vs_processed_length_m=baseline_length - track.length_m,
            source_vs_processed_length_fraction=(baseline_length - track.length_m) / track.length_m,
            corridor_fold_ratio_max=corridor_fold_ratio,
            iterations=int(result.nit),
            objective_evaluations=int(result.nfev),
            compute_time_s=perf_counter() - start,
            corridor_source=corridor.source,
            corridor=corridor,
            source_station_m=track.distance_m,
        )


def _scaled_candidate_track(plan: RacingLinePlan, strength: float) -> SpatialTrack:
    """Interpolate a valid offset toward its baseline and rebuild geometry.

    Both endpoints use the same processed stations. For strengths in [0, 1],
    the offset is a convex blend of zero and the validated spline, so it stays
    inside the spline's piecewise lateral bounds. That fact does not establish
    that the interpolated polygon is simple; check it independently.
    """

    if not isfinite(strength) or not 0.0 < strength < 1.0:
        raise ValueError("intermediate line strength must be between zero and one")
    if plan.status != "candidate":
        raise ValueError("no validated candidate is available for interpolation")
    base_x = np.asarray(plan.baseline_track.x_m[:-1])
    base_y = np.asarray(plan.baseline_track.y_m[:-1])
    full_x = np.asarray(plan.candidate_track.x_m[:-1])
    full_y = np.asarray(plan.candidate_track.y_m[:-1])
    if base_x.shape != full_x.shape or base_y.shape != full_y.shape:
        raise ValueError("baseline and candidate need identical planning grids")
    x = base_x + strength * (full_x - base_x)
    y = base_y + strength * (full_y - base_y)
    track = _track_from_closed_points(x, y)
    base_dx, base_dy = np.roll(base_x, -1) - base_x, np.roll(base_y, -1) - base_y
    dx, dy = np.roll(x, -1) - x, np.roll(y, -1) - y
    forward_cosine = (base_dx * dx + base_dy * dy) / (
        np.hypot(base_dx, base_dy) * np.hypot(dx, dy)
    )
    if not np.all(np.isfinite(forward_cosine)) or float(np.min(forward_cosine)) < 0.15:
        raise ValueError("intermediate path reverses direction relative to reference")
    if _has_nonadjacent_segment_intersection(x, y):
        raise ValueError("intermediate path crosses itself")
    return track


def _audit_interval_coordinates(
    cell_stations: np.ndarray, start_station: float, end_station: float,
) -> tuple[int, float, float]:
    """Locate a distinct audit interval without snapping source boundaries.

    Fractions are formed from the *station difference* so a source-width
    boundary an ulp from a generated planner boundary keeps positive span.
    A caller must conservatively reject intervals that cannot be represented
    without crossing a modeled cell or collapsing under floating arithmetic.
    """

    if end_station <= start_station:
        raise ValueError("audit interval has no positive physical span")
    count = len(cell_stations) - 1
    index = min(int(np.searchsorted(
        cell_stations, start_station, side="right",
    ) - 1), count - 1)
    cell_start = float(cell_stations[index])
    cell_end = float(cell_stations[index + 1])
    if end_station > cell_end:
        raise ValueError("audit interval crosses a modeled cell boundary")
    cell_span = cell_end - cell_start
    interval_span = (end_station - start_station) / cell_span
    if end_station == cell_end:
        b = 1.0
        a = b - interval_span
    elif start_station == cell_start:
        a = 0.0
        b = interval_span
    else:
        a = (start_station - cell_start) / cell_span
        b = a + interval_span
    if not 0.0 <= a < b <= 1.0:
        raise ValueError("audit interval fractions cannot be represented")
    return index, a, b


def _audit_curvature_path(
    track: SpatialTrack,
    reference: SpatialTrack,
    source_station_m: tuple[float, ...],
    corridor: TrackCorridor,
) -> CurvaturePathAudit:
    """Screen an integrated constant-curvature path against declared clearance.

    The planner and model use the polygon chord as each spatial cell length,
    but the model travels a circular arc at that length and curvature. Thus
    following every prescribed curvature does not generally visit the polygon
    vertices. Sample each modeled arc at quarter-cell intervals, and also at
    each source-corridor boundary and midpoint, in the same processed
    normal-coordinate frame used to bound the proposed spline. For every
    interval left by those samples, bound the interpolation error of the
    lateral coordinate and bisect intervals close to a corridor boundary.
    This certifies the scalar normal-coordinate inequality continuously, or
    conservatively rejects an interval that cannot be certified within the
    bounded work budget. It does not certify the swept vehicle envelope.
    """

    count = track.cell_count
    if (
        not track.closed or not reference.closed
        or count != reference.cell_count
        or len(source_station_m) != len(corridor.left_width_m) + 1
        or source_station_m[0] != 0.0
        or source_station_m[-1] <= 0.0
    ):
        raise ValueError("curvature-path audit needs aligned closed planner paths and source stations")
    x = np.asarray(track.x_m, dtype=float)
    y = np.asarray(track.y_m, dtype=float)
    reference_x = np.asarray(reference.x_m, dtype=float)
    reference_y = np.asarray(reference.y_m, dtype=float)
    length = np.asarray(track.cell_length_m, dtype=float)
    curvature = np.asarray(track.curvature_per_m, dtype=float)
    chord_x = np.diff(x)
    chord_y = np.diff(y)
    previous_x = np.roll(chord_x, 1)
    previous_y = np.roll(chord_y, 1)
    start_turn = atan2(
        previous_x[0] * chord_y[0] - previous_y[0] * chord_x[0],
        previous_x[0] * chord_x[0] + previous_y[0] * chord_y[0],
    )
    cell_turn = length * curvature
    chord_length = np.hypot(chord_x, chord_y)
    arc_chord_length = length * np.sinc(0.5 * cell_turn / pi)
    if bool(np.all(
        np.abs(arc_chord_length - chord_length)
        <= np.maximum(1e-8, 1e-8 * chord_length)
    )):
        # A coherent circular-arc cell connects its saved endpoints. Its
        # midpoint bearing determines the exact entry heading. For legacy
        # polygon paths that use each chord as the arc length, this equality
        # does not hold and the shared-vertex tangent is the appropriate seed.
        first_heading = atan2(chord_y[0], chord_x[0]) - 0.5 * cell_turn[0]
        heading_policy = "coherent_first_arc_chord"
    else:
        first_heading = atan2(chord_y[0], chord_x[0]) - 0.5 * start_turn
        heading_policy = "polygon_start_vertex_tangent"
    entry_heading = first_heading + np.concatenate(((0.0,), np.cumsum(cell_turn)[:-1]))

    def arc_displacement(fraction: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        arc_length = length * fraction
        half_turn = 0.5 * cell_turn * fraction
        magnitude = arc_length * np.sinc(half_turn / pi)
        return (
            magnitude * np.cos(entry_heading + half_turn),
            magnitude * np.sin(entry_heading + half_turn),
        )

    exit_dx, exit_dy = arc_displacement(np.ones(count))
    entry_x = x[0] + np.concatenate(((0.0,), np.cumsum(exit_dx)[:-1]))
    entry_y = y[0] + np.concatenate(((0.0,), np.cumsum(exit_dy)[:-1]))
    fractions = np.asarray((0.25, 0.5, 0.75, 1.0))
    source_stations = np.asarray(source_station_m, dtype=float)
    planner_station = np.unique(np.concatenate((
        (np.repeat(np.arange(count), len(fractions))
         + np.tile(fractions, count)) * source_stations[-1] / count,
        source_stations,
        0.5 * (source_stations[:-1] + source_stations[1:]),
    )))
    planner_cell_position = planner_station * count / source_stations[-1]
    cell = np.minimum(np.floor(planner_cell_position).astype(int), count - 1)
    fraction = planner_cell_position - cell
    half_turn = 0.5 * cell_turn[cell] * fraction
    magnitude = length[cell] * fraction * np.sinc(half_turn / pi)
    driven_x = entry_x[cell] + magnitude * np.cos(entry_heading[cell] + half_turn)
    driven_y = entry_y[cell] + magnitude * np.sin(entry_heading[cell] + half_turn)
    reference_sample_x = reference_x[cell] + fraction * (
        reference_x[cell + 1] - reference_x[cell]
    )
    reference_sample_y = reference_y[cell] + fraction * (
        reference_y[cell + 1] - reference_y[cell]
    )
    tangent_x = np.roll(reference_x[:-1], -1) - np.roll(reference_x[:-1], 1)
    tangent_y = np.roll(reference_y[:-1], -1) - np.roll(reference_y[:-1], 1)
    tangent_length = np.hypot(tangent_x, tangent_y)
    if float(np.min(tangent_length)) < 1e-8:
        raise ValueError("processed reference has an undefined normal")
    normal_x = -tangent_y / tangent_length
    normal_y = tangent_x / tangent_length
    next_cell = (cell + 1) % count
    sample_normal_x = (1.0 - fraction) * normal_x[cell] + fraction * normal_x[next_cell]
    sample_normal_y = (1.0 - fraction) * normal_y[cell] + fraction * normal_y[next_cell]
    normal_length = np.hypot(sample_normal_x, sample_normal_y)
    if float(np.min(normal_length)) < 1e-8:
        raise ValueError("processed reference normal reverses within a path cell")
    lateral_offset = (
        (driven_x - reference_sample_x) * sample_normal_x
        + (driven_y - reference_sample_y) * sample_normal_y
    ) / normal_length
    half_vehicle_plus_margin = 0.5 * corridor.vehicle_width_m + corridor.safety_margin_m
    lower, upper = _corridor_bounds_at(
        planner_station,
        source_stations,
        corridor,
        half_vehicle_plus_margin,
    )
    maximum_excess = float(max(
        0.0,
        np.max(lower - lateral_offset),
        np.max(lateral_offset - upper),
    ))
    minimum_slack = float(np.min(np.minimum(
        lateral_offset - lower, upper - lateral_offset,
    )))
    maximum_lateral_offset = float(np.max(np.abs(lateral_offset)))
    seam_error = max(
        hypot(
            float(entry_x[-1] + exit_dx[-1] - x[0]),
            float(entry_y[-1] + exit_dy[-1] - y[0]),
        ),
        hypot(float(x[-1] - x[0]), float(y[-1] - y[0])),
        hypot(
            float(reference_x[-1] - reference_x[0]),
            float(reference_y[-1] - reference_y[0]),
        ),
    )
    if not all(isfinite(value) for value in (
        maximum_excess, minimum_slack, seam_error,
        maximum_lateral_offset,
    )):
        raise ValueError("curvature-path audit produced a nonfinite result")
    # Roundoff only for declared clearance. A generated closed solver path
    # must also bring the integrated vehicle path and both declared polygon
    # endpoints back to their starts within one centimeter. Comparing only to
    # the saved last vertex would let an open path marked closed pass.
    # This fixed numerical tolerance is not a survey or tracking claim.
    numerical_epsilon_m = 1e-8
    seam_tolerance_m = 0.01
    clearance_certified = False
    unresolved_intervals = 0
    extra_samples = 0
    clearance_status = (
        "sampled_excess" if maximum_excess > numerical_epsilon_m
        else "seam_failure" if seam_error > seam_tolerance_m
        else "certified"
    )
    if maximum_excess <= numerical_epsilon_m and seam_error <= seam_tolerance_m:
        # Within each interval the reference point is linear, the arc position
        # has |P''| = length**2 * |curvature|, and the normal is the normalized
        # blend of its two endpoint normals. Let g=(P-R) dot n. The bound below
        # follows from g''=D'' dot n + 2 D' dot n' + D dot n'', with
        # |D'| <= length+|R'|, |n'| <= |N'|/min|N| and
        # |n''| <= 3|N'|**2/min|N|**2. Thus g differs from the straight line
        # between two samples by at most max|g''| * (b-a)**2 / 8.
        reference_dx = np.diff(reference_x)
        reference_dy = np.diff(reference_y)
        interval_lower, interval_upper = _corridor_bounds_at(
            0.5 * (planner_station[:-1] + planner_station[1:]),
            source_stations, corridor, half_vehicle_plus_margin,
        )
        # Assign intervals from physical stations, not the floating product
        # station * count / length. An exact generated cell boundary can land
        # a few ulps below an integer after that product; a distinct source
        # width boundary can also lie extremely close to it. Snapping both
        # would erase a real interval and falsely certify its interior.
        cell_stations = np.arange(count + 1, dtype=float) * source_stations[-1] / count
        # The final product/division can differ by one ulp from the exact
        # source endpoint. Both denote the same physical lap seam; use the
        # supplied endpoint so a tiny final audit interval stays in the last
        # modeled cell instead of being falsely classified as crossing it.
        cell_stations[-1] = source_stations[-1]
        maximum_extra_samples = min(50_000, max(1_024, 2 * len(planner_station)))
        maximum_depth = 10
        recursive_samples = 0

        def interval_error_bound(
            index: int, a: float, b: float,
            da_x: float, da_y: float, db_x: float, db_y: float,
        ) -> float:
            span = b - a
            if span <= 0.0 or b > 1.0 + 1e-9:
                return float("inf")
            ndx = normal_x[(index + 1) % count] - normal_x[index]
            ndy = normal_y[(index + 1) % count] - normal_y[index]
            na_x = normal_x[index] + a * ndx
            na_y = normal_y[index] + a * ndy
            normal_derivative_squared = ndx * ndx + ndy * ndy
            if normal_derivative_squared > 0.0:
                minimum_at = max(0.0, min(span,
                    -(na_x * ndx + na_y * ndy) / normal_derivative_squared,
                ))
            else:
                minimum_at = 0.0
            minimum_normal = hypot(
                na_x + minimum_at * ndx, na_y + minimum_at * ndy,
            )
            if minimum_normal <= 1e-8:
                return float("inf")
            normal_derivative = hypot(ndx, ndy)
            reference_derivative = hypot(reference_dx[index], reference_dy[index])
            displacement_derivative = length[index] + reference_derivative
            displacement_max = max(hypot(da_x, da_y), hypot(db_x, db_y)) + (
                displacement_derivative * span / 2.0
            )
            second_derivative_bound = (
                length[index] ** 2 * abs(curvature[index])
                + 2.0 * displacement_derivative * normal_derivative / minimum_normal
                + 3.0 * displacement_max * normal_derivative**2 / minimum_normal**2
            )
            return float(second_derivative_bound * span**2 / 8.0)

        def point_at(index: int, fraction: float) -> tuple[float, float, float]:
            half = 0.5 * cell_turn[index] * fraction
            sinc = (1.0 - half**2 / 6.0 + half**4 / 120.0
                    if abs(half) < 1e-5 else sin(half) / half)
            magnitude = length[index] * fraction * sinc
            px = entry_x[index] + magnitude * cos(entry_heading[index] + half)
            py = entry_y[index] + magnitude * sin(entry_heading[index] + half)
            dx = px - reference_x[index] - fraction * reference_dx[index]
            dy = py - reference_y[index] - fraction * reference_dy[index]
            nx = normal_x[index] + fraction * (
                normal_x[(index + 1) % count] - normal_x[index]
            )
            ny = normal_y[index] + fraction * (
                normal_y[(index + 1) % count] - normal_y[index]
            )
            norm = hypot(nx, ny)
            if norm <= 1e-8:
                return float(dx), float(dy), float("nan")
            return float(dx), float(dy), float((dx * nx + dy * ny) / norm)

        point_cache: dict[tuple[int, float], tuple[float, float, float]] = {}

        def endpoint_at(
            index: int, station: float, fraction: float,
        ) -> tuple[float, float, float]:
            nonlocal extra_samples
            key = index, station
            if key not in point_cache:
                point_cache[key] = point_at(index, fraction)
                extra_samples += 1
            return point_cache[key]

        clearance_certified = True
        for interval in range(len(planner_station) - 1):
            start_station = float(planner_station[interval])
            end_station = float(planner_station[interval + 1])
            low = float(interval_lower[interval])
            high = float(interval_upper[interval])
            try:
                index, a, b = _audit_interval_coordinates(
                    cell_stations, start_station, end_station,
                )
            except ValueError:
                clearance_certified = False
                unresolved_intervals += 1
                clearance_status = "unresolved_clearance"
                break
            left_dx, left_dy, left_g = endpoint_at(index, start_station, a)
            right_dx, right_dy, right_g = endpoint_at(index, end_station, b)
            if not isfinite(left_g) or not isfinite(right_g):
                clearance_certified = False
                unresolved_intervals += 1
                clearance_status = "undefined_reference_normal"
                break
            maximum_lateral_offset = max(
                maximum_lateral_offset, abs(left_g), abs(right_g),
            )
            endpoint_slack = min(
                left_g - low, high - left_g,
                right_g - low, high - right_g,
            )
            minimum_slack = min(minimum_slack, endpoint_slack)
            maximum_excess = max(maximum_excess, -endpoint_slack)
            if endpoint_slack < -numerical_epsilon_m:
                clearance_certified = False
                clearance_status = "interval_endpoint_excess"
                break
            stack = [(
                a, b, left_g, right_g,
                left_dx, left_dy, right_dx, right_dy, 0,
            )]
            while stack:
                left_f, right_f, left_g, right_g, left_dx, left_dy, right_dx, right_dy, depth = stack.pop()
                error_bound = interval_error_bound(
                    index, left_f, right_f, left_dx, left_dy, right_dx, right_dy,
                )
                endpoint_slack = min(
                    left_g - low, high - left_g,
                    right_g - low, high - right_g,
                )
                interval_slack_bound = endpoint_slack - error_bound
                if (
                    min(left_g, right_g) - error_bound >= low - numerical_epsilon_m
                    and max(left_g, right_g) + error_bound <= high + numerical_epsilon_m
                ):
                    minimum_slack = min(minimum_slack, interval_slack_bound)
                    continue
                if depth >= maximum_depth or recursive_samples >= maximum_extra_samples:
                    clearance_certified = False
                    unresolved_intervals += 1
                    clearance_status = "unresolved_clearance"
                    if isfinite(interval_slack_bound):
                        minimum_slack = min(minimum_slack, interval_slack_bound)
                    break
                midpoint = 0.5 * (left_f + right_f)
                middle_dx, middle_dy, middle_g = point_at(index, midpoint)
                extra_samples += 1
                recursive_samples += 1
                if not isfinite(middle_g):
                    clearance_certified = False
                    unresolved_intervals += 1
                    clearance_status = "undefined_reference_normal"
                    break
                maximum_lateral_offset = max(maximum_lateral_offset, abs(middle_g))
                middle_slack = min(middle_g - low, high - middle_g)
                minimum_slack = min(minimum_slack, middle_slack)
                maximum_excess = max(maximum_excess, -middle_slack)
                if middle_slack < -numerical_epsilon_m:
                    clearance_certified = False
                    clearance_status = "between_sample_excess"
                    break
                stack.append((
                    midpoint, right_f, middle_g, right_g,
                    middle_dx, middle_dy, right_dx, right_dy, depth + 1,
                ))
                stack.append((
                    left_f, midpoint, left_g, middle_g,
                    left_dx, left_dy, middle_dx, middle_dy, depth + 1,
                ))
            if not clearance_certified:
                break
    return CurvaturePathAudit(
        valid=bool(
            maximum_excess <= numerical_epsilon_m
            and seam_error <= seam_tolerance_m
            and clearance_certified
        ),
        sample_count=len(lateral_offset) + extra_samples,
        maximum_lateral_offset_m=maximum_lateral_offset,
        maximum_corridor_excess_m=float(maximum_excess),
        allowed_numerical_excess_m=numerical_epsilon_m,
        seam_position_error_m=seam_error,
        allowed_seam_position_error_m=seam_tolerance_m,
        corridor_source=corridor.source,
        vehicle_width_m=corridor.vehicle_width_m,
        safety_margin_m=corridor.safety_margin_m,
        initial_heading_policy=heading_policy,
        minimum_corridor_slack_m=float(minimum_slack),
        continuous_clearance_certified=clearance_certified,
        unresolved_clearance_intervals=unresolved_intervals,
        clearance_status=clearance_status,
    )


def _adaptive_fourth_strength(
    baseline_time_s: float | None,
    baseline_audit: CurvaturePathAudit | None,
    full_trial: RacingLineTrial,
    half_trial: RacingLineTrial,
    minimum_gain_s: float,
) -> float:
    """Choose one bounded car-specific probe after the first three paths.

    A convex quadratic through the eligible times at strengths 0, 0.5, and
    1 estimates an interior minimum. The finite grid keeps the fourth probe
    away from those already timed and makes the budget deterministic. If the
    three path audits and model times cannot support an interior estimate,
    retain the established three-quarter probe.
    """

    fallback = 0.75
    if (
        baseline_time_s is None
        or baseline_audit is None or not baseline_audit.valid
        or full_trial.lap_time_s is None
        or full_trial.path_audit is None or not full_trial.path_audit.valid
        or half_trial.lap_time_s is None
        or half_trial.path_audit is None or not half_trial.path_audit.valid
    ):
        return fallback

    full_time_s = full_trial.lap_time_s
    half_time_s = half_trial.lap_time_s
    # A bracketed minimum must stand clear of the existing numerical tie
    # margin on both sides before a parabolic estimate is useful.
    if min(baseline_time_s, full_time_s) - half_time_s <= minimum_gain_s:
        return fallback
    curvature_s = baseline_time_s - 2.0 * half_time_s + full_time_s
    if curvature_s <= 0.0:
        return fallback
    vertex = 0.5 + (baseline_time_s - full_time_s) / (4.0 * curvature_s)
    if not isfinite(vertex) or not 0.0 < vertex < 1.0:
        return fallback
    strengths = (0.25, 0.375, 0.625, 0.75, 0.875)
    return min(strengths, key=lambda strength: (abs(strength - vertex), strength))


def _clearance_aware_fourth_strength(
    plan: RacingLinePlan,
    audit_trial: Callable[[SpatialTrack], tuple[CurvaturePathAudit | None, str | None]],
    baseline_time_s: float | None,
    full_trial: RacingLineTrial,
    half_trial: RacingLineTrial,
    minimum_gain_s: float,
) -> float | None:
    """Screen stronger offsets cheaply when the full path misses clearance.

    A clear half-strength model win is evidence to probe farther along the
    same offset, but the invalid full-strength lap cannot be ranked. Check a
    fixed, descending grid of intermediate strengths with geometry and the
    existing curvature-path clearance audit before spending the one remaining
    model run.
    A 2 cm *additional selection buffer* avoids deliberately choosing a path
    in the declared normal-coordinate corridor. It is not surveyed road clearance or a
    continuous swept-body guarantee. No monotonic feasibility is assumed.
    """

    if (
        plan.status != "candidate"
        or baseline_time_s is None
        or full_trial.path_audit is None or full_trial.path_audit.valid
        or half_trial.lap_time_s is None
        or half_trial.path_audit is None or not half_trial.path_audit.valid
        or baseline_time_s - half_trial.lap_time_s <= minimum_gain_s
    ):
        return None
    selection_buffer_m = 0.02
    for strength in (0.975, 0.95, 0.9, 0.875, 0.75, 0.625):
        try:
            trial_track = _scaled_candidate_track(plan, strength)
        except ValueError:
            continue
        audit, error = audit_trial(trial_track)
        if (
            error is None and audit is not None and audit.valid
            and audit.minimum_corridor_slack_m >= selection_buffer_m
        ):
            return strength
    return None


def compare_lines_with_lap_model(
    vehicle: object,
    plan: RacingLinePlan,
    *,
    torque_request_fraction: float,
    progress_callback: Callable[[str, SpatialTrack, LapProgressSnapshot], None] | None = None,
    constraint_progress_callback: Callable[[str, PathConstraintProgressSnapshot], None] | None = None,
    speed_periodic: bool = False,
    minimum_selection_gain_s: float = 0.05,
    road: PlanarRoad | None = None,
) -> RacingLineComparison:
    """Evaluate a candidate and its baseline with the same lap physics.

    The vehicle is copied before each run because a lap mutates pack and
    chassis state. The full geometric candidate and a validated half-offset
    path are tried first. One bounded fourth strength is chosen from their
    eligible car-specific times. If the full path fails its clearance audit but
    the half path wins clearly, a few cheap geometry-only clearance probes
    can move the fourth model trial closer to full strength. Otherwise it
    defaults to three-quarter offset. The default evaluates one lap per path;
    opt-in
    ``speed_periodic`` permits one dry seam-speed probe plus one final lap per
    path, at a fixed initial vehicle/pack state. This checks speed at the
    closed-course seam, not full-state periodicity. A candidate is selected
    only if both it and the baseline yield acceptable times and the gain is
    larger than ``minimum_selection_gain_s``. A planner-created path is also
    screened by integration of the curvature that the vehicle model follows.
    The screen certifies scalar lateral clearance around the processed
    reference with adaptive interval bounds, but is not a swept-body
    certificate. When the
    processed baseline is valid, a failed candidate screen skips that
    candidate's expensive model run; its trial retains the geometric error.
    If the baseline itself fails, all trial model runs remain diagnostic so
    the source-course mismatch can still be inspected.
    The selection margin is not a certified discretization error bound.
    Errors remain explicit.
    With a callback, accepted-cell snapshots carry a phase label and the exact
    track being simulated; periodic probes do not emit callbacks. Constraint
    progress separately reports exact cells processed in each solver stage,
    with no claim that a braking pass is a percent of total convergence.
    """

    if (
        isinstance(minimum_selection_gain_s, bool)
        or not isinstance(minimum_selection_gain_s, Real)
        or not isfinite(minimum_selection_gain_s)
        or minimum_selection_gain_s < 0.0
    ):
        raise ValueError("minimum_selection_gain_s must be finite and nonnegative")
    if road is not None and not isinstance(road, PlanarRoad):
        raise ValueError("road must be a PlanarRoad or None")

    from lapsim.ui.simulation import run_one_lap, run_speed_periodic_lap

    start = perf_counter()
    baseline_time: float | None = None
    candidate_time: float | None = None
    baseline_diagnostic_time: float | None = None
    candidate_diagnostic_time: float | None = None
    baseline_run: EnduranceRunResult | None = None
    candidate_run: EnduranceRunResult | None = None
    candidate_track = plan.candidate_track
    baseline_path_audit: CurvaturePathAudit | None = None
    candidate_path_audit: CurvaturePathAudit | None = None
    candidate_strength: float | None = (
        1.0 if plan.status == "candidate" else None
    )
    trials: list[RacingLineTrial] = []
    baseline_error: str | None = None
    candidate_error: str | None = None

    def audit_trial(track: SpatialTrack) -> tuple[CurvaturePathAudit | None, str | None]:
        if plan.corridor is None or plan.source_station_m is None:
            return None, "Curvature-path corridor audit unavailable: corridor or source stations missing"
        try:
            audit = _audit_curvature_path(
                track, plan.baseline_track, plan.source_station_m, plan.corridor,
            )
        except ValueError as error:
            return None, f"Curvature-path corridor audit unavailable: {error}"
        if not audit.valid:
            reasons = []
            if audit.maximum_corridor_excess_m > audit.allowed_numerical_excess_m:
                reasons.append(
                    "modeled curvature path exceeds declared centerline "
                    f"clearance by {audit.maximum_corridor_excess_m:.6f} m"
                )
            if audit.unresolved_clearance_intervals:
                reasons.append(
                    "continuous normal-coordinate clearance could not be "
                    "certified within the bounded interval budget"
                )
            if audit.seam_position_error_m > audit.allowed_seam_position_error_m:
                reasons.append(
                    "integrated path misses its closed start position by "
                    f"{audit.seam_position_error_m:.6f} m "
                    f"(limit {audit.allowed_seam_position_error_m:.3f} m)"
                )
            return audit, (
                "; ".join(reasons)
                + f" ({audit.sample_count} arc evaluations; no swept-body certificate)"
            )
        return audit, None

    def combined_error(*messages: str | None) -> str | None:
        return "; ".join(message for message in messages if message) or None

    def completed_diagnostic_time(result: EnduranceRunResult | None) -> float | None:
        if (
            result is not None and result.completed
            and isfinite(result.driving_time_s) and result.driving_time_s > 0.0
        ):
            return result.driving_time_s
        return None

    def run_trial(
        track: SpatialTrack, phase: str,
    ) -> tuple[
        EnduranceRunResult | None, float | None, str | None,
        tuple[float, ...] | None,
    ]:
        cell_grip = None
        try:
            condition_options = {}
            if road is not None:
                from .road_grip_schedule import world_patch_grip_schedule

                cell_grip = world_patch_grip_schedule(track, vehicle, road)
                condition_options["cell_road_grip_multiplier"] = cell_grip
            constraint_options = (
                {"constraint_progress_callback": lambda snapshot: (
                    constraint_progress_callback(phase, snapshot)
                )}
                if constraint_progress_callback is not None else {}
            )
            if speed_periodic:
                periodic_options = dict(
                    torque_request_fraction=torque_request_fraction,
                    maximum_lap_passes=2,
                    speed_tolerance_mps=0.005,
                )
                if progress_callback is None:
                    periodic = run_speed_periodic_lap(
                        vehicle, track, **periodic_options, **constraint_options,
                        **condition_options,
                    )
                else:
                    periodic = run_speed_periodic_lap(
                        vehicle, track, **periodic_options, **constraint_options,
                        **condition_options,
                        progress_callback=lambda snapshot: progress_callback(
                            phase, track, snapshot,
                        ),
                    )
                result = periodic.run
                if not periodic.converged:
                    return result, None, periodic.failure_reason or (
                        "Speed-only lap seam did not converge"
                    ), cell_grip
            else:
                if progress_callback is None:
                    result = run_one_lap(
                        deepcopy(vehicle), track,
                        torque_request_fraction=torque_request_fraction,
                        **constraint_options, **condition_options,
                    )
                else:
                    result = run_one_lap(
                        deepcopy(vehicle), track,
                        torque_request_fraction=torque_request_fraction,
                        **constraint_options, **condition_options,
                        progress_callback=lambda snapshot: progress_callback(
                            phase, track, snapshot,
                        ),
                    )
        except (ValueError, RuntimeError, ArithmeticError, OverflowError) as error:
            return None, None, f"{type(error).__name__}: {error}", cell_grip
        if result.completed and isfinite(result.driving_time_s) and result.driving_time_s > 0.0:
            return result, result.driving_time_s, None, cell_grip
        return result, None, result.failure_reason or "Lap did not complete with a finite positive time", cell_grip

    baseline_path_audit, baseline_path_error = audit_trial(plan.baseline_track)

    def run_ai_trial(
        track: SpatialTrack, phase: str, path_audit: CurvaturePathAudit | None,
    ) -> tuple[
        EnduranceRunResult | None, float | None, str | None,
        tuple[float, ...] | None,
    ]:
        # A failed clearance path cannot become selectable by running physics.
        # Preserve diagnostic runs when the processed baseline also fails,
        # because those runs expose the source-course mismatch.
        if (
            baseline_path_error is None
            and path_audit is not None and not path_audit.valid
        ):
            return None, None, "Model run skipped after failed path audit", None
        return run_trial(track, phase)

    baseline_run, baseline_model_time, baseline_run_error, baseline_cell_grip = run_trial(
        plan.baseline_track, "baseline"
    )
    baseline_diagnostic_time = completed_diagnostic_time(baseline_run)
    baseline_time = (
        baseline_model_time if baseline_path_error is None else None
    )
    baseline_error = combined_error(baseline_path_error, baseline_run_error)
    baseline_comparison_error = (
        "Processed baseline path failed the corridor audit; candidate "
        "time is diagnostic only"
        if baseline_path_error is not None else None
    )
    if plan.status == "candidate":
        full_audit, full_path_error = audit_trial(plan.candidate_track)
        full_run, full_model_time, full_run_error, full_cell_grip = run_ai_trial(
            plan.candidate_track, "full", full_audit,
        )
        full_diagnostic_time = completed_diagnostic_time(full_run)
        full_time = (
            full_model_time
            if full_path_error is None and baseline_path_error is None
            else None
        )
        full_error = combined_error(
            full_path_error, baseline_comparison_error, full_run_error
        )
        trials.append(RacingLineTrial(
            1.0, plan.candidate_track.length_m, full_time, full_error,
            full_audit, full_diagnostic_time, plan.candidate_track, full_run,
            full_cell_grip,
        ))
        candidate_run, candidate_time, candidate_error = full_run, full_time, full_error
        candidate_path_audit = full_audit
        candidate_diagnostic_time = full_diagnostic_time
        # Scaling a valid spline offset toward zero preserves every convex
        # lateral corridor bound. Each intermediate x/y geometry still needs
        # its own fold, self-intersection, and modeled-arc clearance checks.
        # The fourth strength is selected after the half trial so it may use
        # this car's eligible model times without adding another physics pass.
        for trial_index in range(2):
            if trial_index == 0:
                strength, phase = 0.5, "half"
            else:
                strength = _adaptive_fourth_strength(
                    baseline_time, baseline_path_audit,
                    trials[0], trials[1], minimum_selection_gain_s,
                )
                stronger_feasible = _clearance_aware_fourth_strength(
                    plan, audit_trial, baseline_time,
                    trials[0], trials[1], minimum_selection_gain_s,
                )
                if stronger_feasible is not None:
                    strength = stronger_feasible
                phase = "three_quarter" if strength == 0.75 else "adaptive"
            try:
                trial_track = _scaled_candidate_track(plan, strength)
            except ValueError as error:
                trials.append(RacingLineTrial(strength, None, None, f"Geometry: {error}"))
                continue
            trial_audit, trial_path_error = audit_trial(trial_track)
            trial_run, trial_model_time, trial_run_error, trial_cell_grip = run_ai_trial(
                trial_track, phase, trial_audit,
            )
            trial_diagnostic_time = completed_diagnostic_time(trial_run)
            trial_time = (
                trial_model_time
                if trial_path_error is None and baseline_path_error is None
                else None
            )
            trial_error = combined_error(
                trial_path_error, baseline_comparison_error, trial_run_error
            )
            trials.append(RacingLineTrial(
                strength, trial_track.length_m, trial_time, trial_error,
                trial_audit, trial_diagnostic_time, trial_track, trial_run,
                trial_cell_grip,
            ))
            if trial_time is not None and (candidate_time is None or trial_time < candidate_time):
                candidate_track, candidate_run = trial_track, trial_run
                candidate_time, candidate_error = trial_time, None
                candidate_path_audit = trial_audit
                candidate_diagnostic_time = trial_diagnostic_time
                candidate_strength = strength
            elif candidate_run is None and trial_run is not None:
                # Preserve the path belonging to any available failed
                # result so the desktop can save a diagnostic run.
                candidate_track, candidate_run = trial_track, trial_run
                candidate_path_audit = trial_audit
                candidate_diagnostic_time = trial_diagnostic_time
                candidate_strength = strength
            elif (
                candidate_time is None and trial_time is None
                and trial_diagnostic_time is not None
                and (
                    candidate_diagnostic_time is None
                    or trial_diagnostic_time < candidate_diagnostic_time
                )
            ):
                # Keep the fastest completed but ineligible trial as a
                # diagnostic, never as a selectable lap-time comparison.
                candidate_track, candidate_run = trial_track, trial_run
                candidate_path_audit = trial_audit
                candidate_diagnostic_time = trial_diagnostic_time
                candidate_strength = strength
        if candidate_time is None:
            candidate_error = "; ".join(
                f"{trial.strength:g}x: {trial.error}"
                for trial in trials if trial.error is not None
            ) or "No candidate lap completed"
    if baseline_path_audit is None:
        rank_status = "path_audit_unavailable"
    elif not baseline_path_audit.valid:
        rank_status = "invalid_processed_baseline"
    elif plan.status == "candidate" and candidate_time is None and any(
        trial.path_length_m is not None and trial.path_audit is None
        for trial in trials
    ):
        rank_status = "path_audit_unavailable"
    elif plan.status == "candidate" and candidate_time is None and any(
        trial.path_audit is not None and not trial.path_audit.valid
        for trial in trials
    ):
        rank_status = "invalid_candidate_path"
    elif baseline_time is None or candidate_time is None:
        rank_status = "no_comparison"
    elif candidate_time >= baseline_time:
        rank_status = "candidate_not_faster"
    elif baseline_time - candidate_time <= minimum_selection_gain_s:
        rank_status = "unresolved_close_gain"
    else:
        rank_status = "candidate_selected"
    use_candidate = rank_status == "candidate_selected"
    return RacingLineComparison(
        baseline_time_s=baseline_time,
        candidate_time_s=candidate_time,
        baseline_run=baseline_run,
        candidate_run=candidate_run,
        candidate_track=candidate_track,
        candidate_strength=candidate_strength,
        trials=tuple(trials),
        rank_status=rank_status,
        selection_margin_s=minimum_selection_gain_s,
        selected_mode="candidate" if use_candidate else "centerline",
        selected_track=candidate_track if use_candidate else plan.baseline_track,
        selected_run=candidate_run if use_candidate else (baseline_run if baseline_time is not None else None),
        baseline_error=baseline_error,
        candidate_error=candidate_error,
        compute_time_s=perf_counter() - start,
        baseline_path_audit=baseline_path_audit,
        candidate_path_audit=candidate_path_audit,
        baseline_diagnostic_time_s=baseline_diagnostic_time,
        candidate_diagnostic_time_s=candidate_diagnostic_time,
        baseline_cell_road_grip_multiplier=baseline_cell_grip,
    )


__all__ = [
    "TrackCorridor", "RacingLinePlan", "CurvaturePathAudit",
    "RacingLineComparison", "RacingLineTrial",
    "RacingLinePlanner", "compare_lines_with_lap_model",
]
