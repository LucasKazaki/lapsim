"""UNTESTED extracted guidance; no course loading or execution.

Frozen behavior contract:
- Keep the original driver/projection/preview/edge formulas and clock settings.
- _controller returns legacy scalar-demand proxies, never plant AWD commands.
- Normalize once with lapsim_light_policies.awd_contracts.normalize_driver_command
  before storing or allocating; never apply raw proxies to the plant.
- ReferenceTrack supplies annotations, not runtime geometry or line admission.
- Do not reuse old source identities, numerical receipts or checkpoints.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import asdict, dataclass
from math import (
    atan2, ceil, cos, floor, fsum, hypot, isfinite, pi, remainder, sin, sqrt,
)
from typing import Protocol

from lapsim_light_core.conditions import PlanarEnvironment
from lapsim_light_core.planar import (
    MAX_INTERNAL_SUBSTEPS, MAX_RUN_STEPS, PlanarControls,
    PlanarState, PlanarVehicleConfig,
)
from lapsim_light_policies.awd_contracts import normalize_driver_command, require


class ReferenceTrack(Protocol):
    distance_m: tuple[float, ...]
    x_m: tuple[float, ...]
    y_m: tuple[float, ...]
    curvature_per_m: tuple[float, ...]
    cell_length_m: tuple[float, ...]
    length_m: float
    cell_count: int
    closed: bool


POSE_MODEL_LABEL = "Synthetic four-wheel pose experiment"
_MAX_POSE_CELL_LENGTH_M = 0.5
_MAX_SPEED_PREVIEW_M = 60.0
_MAX_SPEED_PREVIEW_SAMPLES = 120
_MAX_STEERING_LOOKAHEAD_M = 30.0
_POLYLINE_PREVIEW_SPAN_M = 0.5
_REFERENCE_GEOMETRIES = ("coherent_arcs", "sampled_polyline")
_MAX_POSE_CELLS = 100_000


@dataclass(frozen=True, slots=True)
class PoseDriverSettings:
    """Numerical experiment, assumed corridor, control, and compute bounds."""

    output_step_s: float = 0.05
    target_progress_m: float = 80.0
    maximum_simulated_time_s: float = 20.0
    maximum_control_steps: int = 400
    maximum_internal_substeps: int = 60_000
    assumed_half_width_m: float = 3.0
    vehicle_width_m: float = 1.8
    safety_margin_m: float = 0.2
    initial_speed_mps: float = 4.5
    initial_lateral_offset_m: float = 0.0
    cruise_speed_mps: float = 5.5
    edge_slowdown_slack_m: float = 0.8
    edge_outward_prediction_s: float = 0.5
    edge_rejoin_speed_mps: float = 2.0
    lookahead_base_m: float = 2.5
    lookahead_seconds: float = 0.45
    maximum_steering_rad: float = 0.30
    maximum_rear_drive_torque_nm: float = 80.0
    maximum_wheel_brake_torque_nm: float = 80.0
    drive_gain_nm_per_mps: float = 40.0
    brake_gain_nm_per_mps: float = 35.0
    local_projection_window_m: float = 12.0
    reference_geometry: str = "coherent_arcs"

    def __post_init__(self) -> None:
        if (type(self.reference_geometry) is not str or
                self.reference_geometry not in _REFERENCE_GEOMETRIES):
            raise ValueError("reference_geometry must be coherent_arcs or sampled_polyline")
        positive = (
            "output_step_s", "target_progress_m", "maximum_simulated_time_s",
            "assumed_half_width_m", "vehicle_width_m", "initial_speed_mps",
            "cruise_speed_mps", "edge_slowdown_slack_m",
            "edge_outward_prediction_s", "edge_rejoin_speed_mps",
            "lookahead_base_m", "lookahead_seconds",
            "maximum_steering_rad", "maximum_rear_drive_torque_nm",
            "maximum_wheel_brake_torque_nm", "drive_gain_nm_per_mps",
            "brake_gain_nm_per_mps", "local_projection_window_m",
        )
        for name in positive:
            value = getattr(self, name)
            if not isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if not isfinite(self.safety_margin_m) or self.safety_margin_m < 0.0:
            raise ValueError("safety_margin_m must be finite and nonnegative")
        if self.usable_half_width_m <= 0.0:
            raise ValueError("assumed corridor must exceed half vehicle width and margin")
        if (not isfinite(self.initial_lateral_offset_m) or
                abs(self.initial_lateral_offset_m) > self.usable_half_width_m):
            raise ValueError("initial_lateral_offset_m must be finite and inside the assumed usable half-width")
        if self.maximum_steering_rad >= pi / 2:
            raise ValueError("maximum_steering_rad must be below pi/2")
        for name in ("maximum_control_steps", "maximum_internal_substeps"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.maximum_control_steps > MAX_RUN_STEPS:
            raise ValueError("maximum_control_steps exceeds the planar model cap")
        if self.maximum_internal_substeps > MAX_INTERNAL_SUBSTEPS:
            raise ValueError("maximum_internal_substeps exceeds the planar model cap")

    @property
    def usable_half_width_m(self) -> float:
        """Conservative CG offset limit under the declared width assumption."""

        return self.assumed_half_width_m - self.vehicle_width_m / 2.0 - self.safety_margin_m


@dataclass(frozen=True, slots=True)
class _Projection:
    station_m: float
    cross_track_m: float
    heading_rad: float


def _validate_sampled_polyline(track: ReferenceTrack) -> None:
    """Gate an opt-in polygon reference, independently of solver arc curvature.

    The cells must be saved as x/y chords with matching station increments.
    This does not establish a surveyed corridor or exclude nonlocal crossings;
    the AI planner performs its own separate candidate-path audit.
    """

    if not track.closed or track.cell_count < 3:
        raise ValueError("sampled polyline requires a closed path with at least three cells")
    if track.cell_count > _MAX_POSE_CELLS:
        raise ValueError("sampled polyline exceeds the 100000-cell compute cap")
    if hypot(track.x_m[-1] - track.x_m[0],
             track.y_m[-1] - track.y_m[0]) > 1e-6:
        raise ValueError("sampled polyline has a closed endpoint mismatch")
    first: tuple[float, float] | None = None
    previous: tuple[float, float] | None = None
    chord_lengths_m: list[float] = []
    for index, station_length_m in enumerate(track.cell_length_m):
        dx = track.x_m[index + 1] - track.x_m[index]
        dy = track.y_m[index + 1] - track.y_m[index]
        chord_m = hypot(dx, dy)
        if not isfinite(chord_m) or chord_m < 1e-5:
            raise ValueError(f"sampled polyline cell {index} has a degenerate chord")
        if abs(chord_m - station_length_m) > max(1e-6, 1e-8 * station_length_m):
            raise ValueError(f"sampled polyline cell {index} has a station/chord mismatch")
        chord_lengths_m.append(chord_m)
        direction = (dx / chord_m, dy / chord_m)
        if previous is not None and (
            previous[0] * direction[0] + previous[1] * direction[1] < -1.0 + 1e-8
        ):
            raise ValueError(f"sampled polyline folds back at cell {index}")
        first = direction if first is None else first
        previous = direction
    if previous is not None and first is not None and (
        previous[0] * first[0] + previous[1] * first[1] < -1.0 + 1e-8
    ):
        raise ValueError("sampled polyline folds back at the closed seam")
    if abs(fsum(chord_lengths_m) - track.length_m) > max(1e-5, 1e-8 * track.length_m):
        raise ValueError("sampled polyline total station/chord length mismatch")


def _reference_start_heading(track: ReferenceTrack, settings: PoseDriverSettings) -> float:
    first_chord_heading = atan2(
        track.y_m[1] - track.y_m[0], track.x_m[1] - track.x_m[0],
    )
    if settings.reference_geometry == "sampled_polyline":
        return first_chord_heading
    return first_chord_heading - (
        track.curvature_per_m[0] * track.cell_length_m[0] / 2.0
    )


def _polyline_preview_curvature(
    track: ReferenceTrack, station_m: float, cell: int,
) -> float:
    """Estimate local polygon bend over a fixed physical preview span.

    Subdividing an unchanged x/y polygon inserts collinear vertices. A turn
    divided by *adjacent cell length* then grows as the grid gets finer, so
    preview speed changes without a path change. Chord headings measured at
    fixed stations are invariant to that subdivision. This remains a bounded
    speed-control heuristic, not finite point curvature at a sharp corner.
    """

    span_m = min(_POLYLINE_PREVIEW_SPAN_M, track.length_m / 8.0)
    before_x, before_y = _path_point(track, station_m - span_m)
    center_x, center_y = _path_point(track, station_m)
    after_x, after_y = _path_point(track, station_m + span_m)
    before_dx, before_dy = center_x - before_x, center_y - before_y
    after_dx, after_dy = after_x - center_x, after_y - center_y
    if min(hypot(before_dx, before_dy), hypot(after_dx, after_dy)) < 1e-9:
        # A folded local chord has undefined heading. Request a slow preview
        # instead of treating atan2(0, 0) as a trustworthy straight path.
        return max(abs(track.curvature_per_m[cell]), pi / span_m)
    before_heading = atan2(before_dy, before_dx)
    after_heading = atan2(after_dy, after_dx)
    return max(
        abs(track.curvature_per_m[cell]),
        abs(remainder(after_heading - before_heading, 2.0 * pi)) / span_m,
    )


def _path_point(track: ReferenceTrack, station_m: float) -> tuple[float, float]:
    station_m %= track.length_m
    # The course grid is at most 0.5 m in the supplied synthetic case.
    # Linear chords are a reference geometry approximation, not road edges.
    i = min(bisect_right(track.distance_m, station_m) - 1, track.cell_count - 1)
    fraction = ((station_m - track.distance_m[i]) /
                (track.distance_m[i + 1] - track.distance_m[i]))
    return (
        track.x_m[i] + fraction * (track.x_m[i + 1] - track.x_m[i]),
        track.y_m[i] + fraction * (track.y_m[i + 1] - track.y_m[i]),
    )


def _project_local(
    track: ReferenceTrack, x_m: float, y_m: float, previous_station_m: float,
    window_m: float,
) -> _Projection:
    best_distance_sq = float("inf")
    best: _Projection | None = None
    length_m = track.length_m
    lower_m = previous_station_m - window_m
    upper_m = previous_station_m + window_m
    candidate_entries: set[tuple[int, int]] = set()
    if window_m >= length_m / 2.0:
        for i in range(track.cell_count):
            center_station = 0.5 * (track.distance_m[i] + track.distance_m[i + 1])
            nearest_lap = round((previous_station_m - center_station) / length_m)
            candidate_entries.add((i, nearest_lap))
            # A window shorter than one lap can cover both ends of a cell
            # longer than half a lap. The adjacent copies remain bounded.
            if window_m < length_m:
                candidate_entries.add((i, nearest_lap - 1))
                candidate_entries.add((i, nearest_lap + 1))
    else:
        # Station and cell boundaries are sorted. Visit cells that overlap the
        # local window, including each overlapping lap copy at the seam.
        for lap in range(floor(lower_m / length_m), floor(upper_m / length_m) + 1):
            interval_lower_m = max(0.0, lower_m - lap * length_m)
            interval_upper_m = min(length_m, upper_m - lap * length_m)
            if interval_lower_m > interval_upper_m:
                continue
            first = max(0, bisect_right(track.distance_m, interval_lower_m) - 1)
            last = min(track.cell_count,
                       bisect_right(track.distance_m, interval_upper_m))
            candidate_entries.update((i, lap) for i in range(first, last))

    def candidate_order(entry: tuple[int, int]) -> tuple[int, int, float, int]:
        i, lap = entry
        center_station = 0.5 * (track.distance_m[i] + track.distance_m[i + 1])
        nearest_lap = round((previous_station_m - center_station) / length_m)
        return (i, lap != nearest_lap,
                abs(center_station + lap * length_m - previous_station_m), lap)

    # Cell index remains the primary tie order; the former nearest-center
    # copy wins physical-distance ties within one cell.
    for i, lap in sorted(candidate_entries, key=candidate_order):
        lap_shift = lap * length_m
        start_station_m = track.distance_m[i] + lap_shift
        end_station_m = track.distance_m[i + 1] + lap_shift
        overlap_lower_m = max(start_station_m, lower_m)
        overlap_upper_m = min(end_station_m, upper_m)
        if overlap_lower_m > overlap_upper_m:
            continue
        dx = track.x_m[i + 1] - track.x_m[i]
        dy = track.y_m[i + 1] - track.y_m[i]
        norm_sq = dx * dx + dy * dy
        if norm_sq <= 0.0:
            continue
        cell_length_m = end_station_m - start_station_m
        lower_fraction = (overlap_lower_m - start_station_m) / cell_length_m
        upper_fraction = (overlap_upper_m - start_station_m) / cell_length_m
        fraction = min(upper_fraction, max(lower_fraction,
            ((x_m - track.x_m[i]) * dx + (y_m - track.y_m[i]) * dy) / norm_sq
        ))
        px = track.x_m[i] + fraction * dx
        py = track.y_m[i] + fraction * dy
        error_x, error_y = x_m - px, y_m - py
        distance_sq = error_x * error_x + error_y * error_y
        if distance_sq < best_distance_sq:
            best_distance_sq = distance_sq
            best = _Projection(
                start_station_m + fraction * cell_length_m,
                (dx * error_y - dy * error_x) / sqrt(norm_sq),
                atan2(dy, dx),
            )
    if best is None:
        raise ValueError("no course segment lies in the local projection window")
    return best


def _preview_speed_target(
    track: ReferenceTrack, config: PlanarVehicleConfig,
    environment: PlanarEnvironment, settings: PoseDriverSettings,
    station_m: float, speed_mps: float, current_grip: float,
) -> float:
    """Sample path grip/curvature and approach each bend before reaching it.

    This is a deliberately bounded speed-control heuristic, not a tire-force
    feasibility proof. Future wheel centers are placed on the reference-path
    tangent; the actual four-wheel state may follow a different trajectory.
    """

    # A half-lap limit avoids looking through a full circuit to the same bend.
    # The fixed 60 m / 120-interval ceiling bounds work even for extreme but
    # finite user speed and lookahead settings. Narrower patches can be missed
    # by the 0.5 m-or-finer sampling, so this is no road-clearance certificate.
    horizon_m = min(_MAX_SPEED_PREVIEW_M, track.length_m / 2.0)
    count = max(2, min(_MAX_SPEED_PREVIEW_SAMPLES, ceil(horizon_m / 0.5)))
    wheel_positions = config.wheel_positions_m
    samples: list[tuple[float, float, float]] = []
    minimum_grip = current_grip
    for index in range(count + 1):
        distance_ahead_m = horizon_m * index / count
        sample_station_m = (station_m + distance_ahead_m) % track.length_m
        cell = min(bisect_right(track.distance_m, sample_station_m) - 1,
                   track.cell_count - 1)
        fraction = ((sample_station_m - track.distance_m[cell]) /
                    (track.distance_m[cell + 1] - track.distance_m[cell]))
        dx = track.x_m[cell + 1] - track.x_m[cell]
        dy = track.y_m[cell + 1] - track.y_m[cell]
        x_m = track.x_m[cell] + fraction * dx
        y_m = track.y_m[cell] + fraction * dy
        tangent_norm = hypot(dx, dy)
        if not isfinite(tangent_norm) or tangent_norm <= 0.0:
            raise ValueError(f"cell {cell} has an invalid preview-path tangent")
        tangent_cos = dx / tangent_norm
        tangent_sin = dy / tangent_norm
        road_points = ((x_m, y_m), *(
            (x_m + tangent_cos * body_x - tangent_sin * body_y,
             y_m + tangent_sin * body_x + tangent_cos * body_y)
            for body_x, body_y in wheel_positions
        ))
        # Invalid future road data must not be mistaken for trustworthy base
        # pavement grip. A zero preview grip asks for maximum caution there.
        grip = min(
            road_sample.friction_multiplier if road_sample.valid else 0.0
            for road_sample in (environment.road.query(x, y) for x, y in road_points)
        )
        minimum_grip = min(minimum_grip, grip)
        curvature_per_m = (
            _polyline_preview_curvature(track, sample_station_m, cell)
            if settings.reference_geometry == "sampled_polyline"
            else abs(track.curvature_per_m[cell])
        )
        samples.append((distance_ahead_m, curvature_per_m, grip))

    # Reserve a fraction of the friction estimate for simultaneous steering
    # and model error. Maximum wheel brake torque gives a separate upper bound
    # on achievable straight-line deceleration. These are planning bounds,
    # not a guarantee that the feedback gains attain the target exactly.
    brake_deceleration_mps2 = min(
        0.20 * config.tire_mu * minimum_grip * config.gravity_mps2,
        4.0 * settings.maximum_wheel_brake_torque_nm /
        (config.mass_kg * config.wheel_radius_m),
    )
    response_margin_m = 1.0 + 0.45 * speed_mps + config.cg_to_front_axle_m
    target_speed_mps = settings.cruise_speed_mps
    for distance_ahead_m, curvature_per_m, grip in samples:
        lateral_acceleration_mps2 = min(
            4.0, 0.35 * config.tire_mu * min(current_grip, grip) *
            config.gravity_mps2,
        )
        corner_speed_sq = lateral_acceleration_mps2 / max(curvature_per_m, 1e-9)
        usable_distance_m = max(0.0, distance_ahead_m - response_margin_m)
        allowed_speed_mps = sqrt(
            corner_speed_sq + 2.0 * brake_deceleration_mps2 * usable_distance_m
        )
        target_speed_mps = min(target_speed_mps, allowed_speed_mps)
    return target_speed_mps


def _wheel_world_positions(
    config: PlanarVehicleConfig, state: PlanarState,
) -> tuple[tuple[float, float], ...]:
    heading_cos, heading_sin = cos(state.heading_rad), sin(state.heading_rad)
    return tuple(
        (state.x_m + heading_cos * body_x - heading_sin * body_y,
         state.y_m + heading_sin * body_x + heading_cos * body_y)
        for body_x, body_y in config.wheel_positions_m
    )


def _conservative_local_grip(
    config: PlanarVehicleConfig, environment: PlanarEnvironment,
    state: PlanarState,
) -> float:
    """Choose the least grip seen at the CG or four wheel contact centers."""

    points = ((state.x_m, state.y_m), *_wheel_world_positions(config, state))
    return min(environment.road.query(x, y).friction_multiplier for x, y in points)


def _initial_road_valid(
    config: PlanarVehicleConfig, environment: PlanarEnvironment,
    state: PlanarState,
) -> bool:
    return all(
        environment.road.query(x, y).valid
        for x, y in _wheel_world_positions(config, state)
    )


def _assumed_footprint_slack(
    track: ReferenceTrack, config: PlanarVehicleConfig,
    settings: PoseDriverSettings, state: PlanarState, station_m: float,
) -> float:
    """Check an axle-span body rectangle in the declared numerical corridor.

    The width and margin are assumed inputs. This covers the rectangle between
    axle lines, but does not claim measured cones, body overhang, or swept-area
    certification between output samples.
    """

    heading_cos, heading_sin = cos(state.heading_rad), sin(state.heading_rad)
    body_half_width = settings.vehicle_width_m / 2.0
    half_width_after_margin = settings.assumed_half_width_m - settings.safety_margin_m
    minimum_slack = float("inf")
    for body_x in (config.cg_to_front_axle_m, -config.cg_to_rear_axle_m):
        for body_y in (-body_half_width, body_half_width):
            x = state.x_m + heading_cos * body_x - heading_sin * body_y
            y = state.y_m + heading_sin * body_x + heading_cos * body_y
            projected = _project_local(
                track, x, y, station_m, settings.local_projection_window_m,
            )
            minimum_slack = min(
                minimum_slack,
                half_width_after_margin - abs(projected.cross_track_m),
            )
    return minimum_slack


def _edge_speed_target(
    config: PlanarVehicleConfig, settings: PoseDriverSettings,
    state: PlanarState, projection: _Projection,
    footprint_slack_m: float, prior_target_mps: float,
) -> float:
    """Reduce speed near an assumed edge while retaining slow rejoin motion.

    This is a bounded synthetic recovery heuristic, not swept-path clearance.
    The footprint slack is sampled at the four axle-span body corners. The CG
    lateral velocity is measured relative to the projected path tangent; a
    yaw-rate bound covers the sampled axle-span body corners. Outward
    travel over the declared response time is subtracted from current slack.
    """

    relative_heading = state.heading_rad - projection.heading_rad
    lateral_velocity_mps = (
        state.u_mps * sin(relative_heading) +
        state.v_mps * cos(relative_heading)
    )
    if abs(projection.cross_track_m) <= 1e-9:
        outward_velocity_mps = abs(lateral_velocity_mps)
    else:
        side = 1.0 if projection.cross_track_m > 0.0 else -1.0
        outward_velocity_mps = max(0.0, side * lateral_velocity_mps)
    outward_velocity_mps += (
        abs(state.yaw_rate_rad_s) *
        hypot(
            max(config.cg_to_front_axle_m, config.cg_to_rear_axle_m),
            settings.vehicle_width_m / 2.0,
        )
    )
    predicted_slack_m = max(
        0.0,
        footprint_slack_m -
        settings.edge_outward_prediction_s * outward_velocity_mps,
    )
    fraction = sqrt(min(1.0, predicted_slack_m / settings.edge_slowdown_slack_m))
    slow_target_mps = min(prior_target_mps, settings.edge_rejoin_speed_mps)
    return slow_target_mps + fraction * (prior_target_mps - slow_target_mps)


def _controller(
    track: ReferenceTrack, config: PlanarVehicleConfig,
    environment: PlanarEnvironment, settings: PoseDriverSettings,
    state: PlanarState, projection: _Projection,
    current_footprint_slack_m: float | None = None,
) -> tuple[PlanarControls, float]:
    speed_mps = hypot(state.u_mps, state.v_mps)
    lookahead_m = min(
        _MAX_STEERING_LOOKAHEAD_M, track.length_m / 2.0,
        settings.lookahead_base_m + settings.lookahead_seconds * speed_mps,
    )
    # Pure pursuit's kinematic curvature is defined at the rear axle. The
    # planar state is at the CG, so transform both the controller origin and
    # its local station before computing the target angle.
    rear_x = state.x_m - config.cg_to_rear_axle_m * cos(state.heading_rad)
    rear_y = state.y_m - config.cg_to_rear_axle_m * sin(state.heading_rad)
    rear_projection = _project_local(
        track, rear_x, rear_y, projection.station_m,
        settings.local_projection_window_m,
    )
    target_x, target_y = _path_point(track, rear_projection.station_m + lookahead_m)
    dx, dy = target_x - rear_x, target_y - rear_y
    target_angle = remainder(atan2(dy, dx) - state.heading_rad, 2.0 * pi)
    target_distance = max(0.5, hypot(dx, dy))
    wheelbase_m = config.cg_to_front_axle_m + config.cg_to_rear_axle_m
    steering = atan2(2.0 * wheelbase_m * sin(target_angle), target_distance)
    steering = min(settings.maximum_steering_rad,
                   max(-settings.maximum_steering_rad, steering))

    grip = _conservative_local_grip(config, environment, state)
    target_speed = _preview_speed_target(
        track, config, environment, settings, projection.station_m,
        speed_mps, grip,
    )
    if current_footprint_slack_m is None:
        current_footprint_slack_m = _assumed_footprint_slack(
            track, config, settings, state, projection.station_m,
        )
    target_speed = _edge_speed_target(
        config, settings, state, projection,
        current_footprint_slack_m, target_speed,
    )
    speed_error = target_speed - speed_mps
    drive = min(settings.maximum_rear_drive_torque_nm,
                max(0.0, settings.drive_gain_nm_per_mps * speed_error))
    brake = min(settings.maximum_wheel_brake_torque_nm,
                max(0.0, -settings.brake_gain_nm_per_mps * speed_error))
    return PlanarControls(
        steering_angles_rad=(steering, steering, 0.0, 0.0),
        drive_torques_nm=(0.0, 0.0, drive, drive),
        brake_torques_nm=(brake, brake, brake, brake),
    ), grip


@dataclass(frozen=True,slots=True)
class StandingPoseDriverSettings(PoseDriverSettings):
    """The existing driver settings, with an exact zero initial-speed contract.

    The source driver requires a positive initial speed because its standalone
    runner historically starts moving. The light bridge supplies its own
    physical state and uses only the existing controller/projection functions.
    Validate every other inherited field with the original settings validator;
    the positive value below is used for validation only, never as a vehicle
    speed or controller input. The actual setting remains exactly zero.
    """
    def __post_init__(self):
        require(type(self.initial_speed_mps) in (int,float) and isfinite(self.initial_speed_mps) and
                self.initial_speed_mps==0.,'Standing driver requires exact zero initial speed')
        values=asdict(self);values['initial_speed_mps']=1.
        PoseDriverSettings(**values)

def standing_driver(driver):
    require(type(driver) is PoseDriverSettings,'The original driver profile is required')
    values=asdict(driver);values['initial_speed_mps']=0.
    return StandingPoseDriverSettings(**values)


def common_awd_driver_command(
    track: ReferenceTrack, config: PlanarVehicleConfig,
    environment: PlanarEnvironment, settings: PoseDriverSettings,
    state: PlanarState, projection: _Projection,
    current_footprint_slack_m: float | None = None,
) -> tuple[PlanarControls, float]:
    """Return the shared four-channel demand before policy allocation.

    The caller owns the original driver clock and admitted track/state. This
    helper advances no plant, allocator or clock and never admits a racing line.
    It converts the retained driver's two scalar-demand proxies exactly once;
    all four normalized wheel requests are equal before a policy acts on them.
    The allocator, common brakes and plant still own constraints and achievement.
    """
    command, grip = _controller(
        track, config, environment, settings, state, projection,
        current_footprint_slack_m,
    )
    return normalize_driver_command(command), grip
