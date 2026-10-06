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
from dataclasses import dataclass
from math import ceil, hypot, isfinite
from time import perf_counter
from typing import Callable

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import LinearConstraint, minimize

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.events.endurance import EnduranceRunResult, LapProgressSnapshot


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
    """Candidate, same-preprocessing baseline, and transparent diagnostics."""

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
    iterations: int
    objective_evaluations: int
    compute_time_s: float
    corridor_source: str


@dataclass(frozen=True, slots=True)
class RacingLineComparison:
    """Full-model timings for a centerline and bounded candidate trials.

    ``candidate_*`` refers to the fastest completed nonzero-strength trial,
    not necessarily the full-strength geometric proposal. If no candidate
    completes, it refers to the first failed trial when a run was returned.
    ``selected_*`` remains the faster completed path when both complete.
    """

    baseline_time_s: float | None
    candidate_time_s: float | None
    baseline_run: EnduranceRunResult | None
    candidate_run: EnduranceRunResult | None
    candidate_track: SpatialTrack
    candidate_strength: float | None
    trials: tuple[RacingLineTrial, ...]
    selected_mode: str
    selected_track: SpatialTrack
    selected_run: EnduranceRunResult | None
    baseline_error: str | None
    candidate_error: str | None
    compute_time_s: float


@dataclass(frozen=True, slots=True)
class RacingLineTrial:
    """One nonzero lateral-offset strength checked with the lap model."""

    strength: float
    path_length_m: float | None
    lap_time_s: float | None
    error: str | None


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


def _track_from_closed_points(x: np.ndarray, y: np.ndarray) -> SpatialTrack:
    """Recompute chord arc length and signed three-point curvature."""

    dx = np.roll(x, -1) - x
    dy = np.roll(y, -1) - y
    lengths = np.hypot(dx, dy)
    if not np.all(np.isfinite(lengths)) or float(np.min(lengths)) < 1e-5:
        raise ValueError("candidate contains a degenerate path cell")
    prev_dx = np.roll(dx, 1)
    prev_dy = np.roll(dy, 1)
    prev_lengths = np.roll(lengths, 1)
    next_chord = np.hypot(prev_dx + dx, prev_dy + dy)
    if float(np.min(next_chord)) < 1e-5:
        raise ValueError("candidate folds back across a path point")
    cross = prev_dx * dy - prev_dy * dx
    point_curvature = 2.0 * cross / (prev_lengths * lengths * next_chord)
    cell_curvature = 0.5 * (point_curvature + np.roll(point_curvature, -1))
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
    """

    def __init__(
        self,
        *,
        sample_spacing_m: float = 2.0,
        control_count: int = 24,
        smoothing_m: float = 0.8,
        maximum_iterations: int = 60,
        length_penalty: float = 0.01,
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
        self.sample_spacing_m = sample_spacing_m
        self.control_count = control_count
        self.smoothing_m = smoothing_m
        self.maximum_iterations = maximum_iterations
        self.length_penalty = length_penalty

    def plan(self, track: SpatialTrack, corridor: TrackCorridor) -> RacingLinePlan:
        """Return candidate and baseline; no car simulation is run here.

        The corridor must be supplied explicitly. The spline offset is
        checked against every supplied piecewise width, including its cubic
        extrema. This only certifies the declared numerical corridor, not
        unmeasured pavement or physical track survey quality.
        """

        start = perf_counter()
        if not track.closed:
            raise ValueError("racing-line planning requires a closed course")
        if len(corridor.left_width_m) != track.cell_count:
            raise ValueError("corridor widths must match reference track cells")
        count = max(ceil(track.length_m / self.sample_spacing_m), 4 * self.control_count, 32)
        if count > 5000:
            raise ValueError("planner grid exceeds its 5000-point compute cap")
        source_station = np.asarray(track.distance_m, dtype=float)
        station = np.arange(count, dtype=float) * track.length_m / count
        source_x = np.asarray(track.x_m, dtype=float)
        source_y = np.asarray(track.y_m, dtype=float)
        closure_error = hypot(source_x[-1] - source_x[0], source_y[-1] - source_y[0])
        # Bring the noisy endpoint onto the start by a visible, recorded repair.
        corrected_x = source_x - (source_station / track.length_m) * (source_x[-1] - source_x[0])
        corrected_y = source_y - (source_station / track.length_m) * (source_y[-1] - source_y[0])
        raw_x = np.interp(station, source_station, corrected_x)
        raw_y = np.interp(station, source_station, corrected_y)
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
            iterations=int(result.nit),
            objective_evaluations=int(result.nfev),
            compute_time_s=perf_counter() - start,
            corridor_source=corridor.source,
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


def compare_lines_with_lap_model(
    vehicle: object,
    plan: RacingLinePlan,
    *,
    torque_request_fraction: float,
    progress_callback: Callable[[str, SpatialTrack, LapProgressSnapshot], None] | None = None,
) -> RacingLineComparison:
    """Evaluate a candidate and its baseline with the unchanged lap physics.

    The vehicle is copied before each run because a lap mutates pack and
    chassis state. The full geometric candidate is tried first. A half-offset
    path is tried only if that candidate fails or does not beat a completed
    baseline. Thus at most three full laps run, and the ordinary centerline
    path still avoids this module entirely. A candidate is selected only if
    both it and the baseline complete and it is faster. Errors remain explicit.
    With a callback, accepted-cell snapshots carry a phase label and the exact
    track being simulated; no callback keyword is passed in the default case.
    """

    from lapsim.ui.simulation import run_one_lap

    start = perf_counter()
    baseline_time: float | None = None
    candidate_time: float | None = None
    baseline_run: EnduranceRunResult | None = None
    candidate_run: EnduranceRunResult | None = None
    candidate_track = plan.candidate_track
    candidate_strength: float | None = None
    trials: list[RacingLineTrial] = []
    baseline_error: str | None = None
    candidate_error: str | None = None

    def run_trial(
        track: SpatialTrack, phase: str,
    ) -> tuple[EnduranceRunResult | None, float | None, str | None]:
        try:
            if progress_callback is None:
                result = run_one_lap(
                    deepcopy(vehicle), track,
                    torque_request_fraction=torque_request_fraction,
                )
            else:
                result = run_one_lap(
                    deepcopy(vehicle), track,
                    torque_request_fraction=torque_request_fraction,
                    progress_callback=lambda snapshot: progress_callback(phase, track, snapshot),
                )
        except (ValueError, RuntimeError, ArithmeticError, OverflowError) as error:
            return None, None, f"{type(error).__name__}: {error}"
        if result.completed and isfinite(result.driving_time_s) and result.driving_time_s > 0.0:
            return result, result.driving_time_s, None
        return result, None, result.failure_reason or "Lap did not complete with a finite positive time"

    baseline_run, baseline_time, baseline_error = run_trial(plan.baseline_track, "baseline")
    if plan.status == "candidate":
        full_run, full_time, full_error = run_trial(plan.candidate_track, "full")
        trials.append(RacingLineTrial(1.0, plan.candidate_track.length_m, full_time, full_error))
        candidate_run, candidate_time, candidate_error = full_run, full_time, full_error
        candidate_strength = 1.0 if full_time is not None else None
        if full_time is None or (baseline_time is not None and full_time >= baseline_time):
            # Scaling a valid spline offset toward zero preserves every
            # convex lateral corridor bound. The intermediate x/y geometry
            # still needs its own fold and self-intersection checks.
            try:
                half_track = _scaled_candidate_track(plan, 0.5)
            except ValueError as error:
                trials.append(RacingLineTrial(0.5, None, None, f"Geometry: {error}"))
            else:
                half_run, half_time, half_error = run_trial(half_track, "half")
                trials.append(RacingLineTrial(0.5, half_track.length_m, half_time, half_error))
                if half_time is not None and (candidate_time is None or half_time < candidate_time):
                    candidate_track, candidate_run = half_track, half_run
                    candidate_time, candidate_error = half_time, None
                    candidate_strength = 0.5
                elif candidate_run is None and half_run is not None:
                    # Preserve the path belonging to any available failed
                    # result so the desktop can save a diagnostic run.
                    candidate_track, candidate_run = half_track, half_run
        if candidate_time is None:
            candidate_error = "; ".join(
                f"{trial.strength:g}x: {trial.error}"
                for trial in trials if trial.error is not None
            ) or "No candidate lap completed"
    use_candidate = (
        baseline_time is not None
        and candidate_time is not None
        and isfinite(candidate_time)
        and candidate_time < baseline_time
    )
    return RacingLineComparison(
        baseline_time_s=baseline_time,
        candidate_time_s=candidate_time,
        baseline_run=baseline_run,
        candidate_run=candidate_run,
        candidate_track=candidate_track,
        candidate_strength=candidate_strength,
        trials=tuple(trials),
        selected_mode="candidate" if use_candidate else "centerline",
        selected_track=candidate_track if use_candidate else plan.baseline_track,
        selected_run=candidate_run if use_candidate else (baseline_run if baseline_time is not None else None),
        baseline_error=baseline_error,
        candidate_error=candidate_error,
        compute_time_s=perf_counter() - start,
    )


__all__ = [
    "TrackCorridor", "RacingLinePlan", "RacingLineComparison", "RacingLineTrial",
    "RacingLinePlanner", "compare_lines_with_lap_model",
]
