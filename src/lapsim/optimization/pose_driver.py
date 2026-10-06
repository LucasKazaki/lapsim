"""Bounded, synthetic closed-loop driving experiment with an actual planar pose.

This is a separate time-domain four-wheel model. Its elapsed time is a pose
experiment duration, never an endurance-model lap time or vehicle prediction.
The corridor is an explicit numerical assumption, not a surveyed boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, ceil, cos, hypot, isfinite, pi, remainder, sin, sqrt
from typing import Callable

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.dynamics.conditions import PlanarEnvironment
from lapsim.dynamics.planar import (
    MAX_INTERNAL_SUBSTEPS,
    MAX_RUN_STEPS,
    PlanarControls,
    PlanarEvaluation,
    PlanarSimulator,
    PlanarState,
    PlanarVehicleConfig,
)
from lapsim.ui.course_catalog import SYNTHETIC_DEMO_COURSE_ID, load_course


POSE_MODEL_LABEL = "Synthetic four-wheel pose experiment"


def synthetic_pose_vehicle() -> PlanarVehicleConfig:
    """The explicit synthetic car also used by the desktop Dynamics Lab."""

    return PlanarVehicleConfig(
        mass_kg=300.0,
        yaw_inertia_kgm2=160.0,
        cg_to_front_axle_m=0.8,
        cg_to_rear_axle_m=0.8,
        front_track_m=1.2,
        rear_track_m=1.2,
        wheel_radius_m=0.2,
        wheel_inertia_kgm2=0.3,
        tire_mu=1.5,
        longitudinal_stiffness_n_per_slip=7000.0,
        cornering_stiffness_n_per_rad=8000.0,
    )


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
    cruise_speed_mps: float = 5.5
    lookahead_base_m: float = 2.5
    lookahead_seconds: float = 0.45
    maximum_steering_rad: float = 0.30
    maximum_rear_drive_torque_nm: float = 80.0
    maximum_wheel_brake_torque_nm: float = 80.0
    drive_gain_nm_per_mps: float = 40.0
    brake_gain_nm_per_mps: float = 35.0
    local_projection_window_m: float = 12.0

    def __post_init__(self) -> None:
        positive = (
            "output_step_s", "target_progress_m", "maximum_simulated_time_s",
            "assumed_half_width_m", "vehicle_width_m", "initial_speed_mps",
            "cruise_speed_mps", "lookahead_base_m", "lookahead_seconds",
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
class PoseDriverSample:
    time_s: float
    progress_m: float
    cross_track_error_m: float
    heading_error_rad: float
    local_grip_multiplier: float
    minimum_assumed_boundary_slack_m: float
    projection_valid: bool = True


@dataclass(frozen=True, slots=True)
class PoseDriverRun:
    """Every issued control and resulting boundary state on one fixed time grid."""

    track: SpatialTrack
    vehicle_config: PlanarVehicleConfig
    environment: PlanarEnvironment
    settings: PoseDriverSettings
    times_s: tuple[float, ...]
    states: tuple[PlanarState, ...]
    controls: tuple[PlanarControls, ...]
    evaluations: tuple[PlanarEvaluation, ...]
    samples: tuple[PoseDriverSample, ...]
    status: str
    internal_substeps: int
    road_valid: bool

    @property
    def completed(self) -> bool:
        return self.status == "target_reached"

    @property
    def elapsed_pose_model_time_s(self) -> float:
        return self.times_s[-1]

    @property
    def maximum_absolute_cross_track_error_m(self) -> float:
        return max(abs(sample.cross_track_error_m) for sample in self.samples)

    @property
    def minimum_assumed_boundary_slack_m(self) -> float:
        return min(sample.minimum_assumed_boundary_slack_m for sample in self.samples)


@dataclass(frozen=True, slots=True)
class PoseReplayTolerances:
    position_m: float = 1e-8
    heading_rad: float = 1e-8
    body_velocity_mps: float = 1e-8
    yaw_rate_rad_s: float = 1e-8
    wheel_speed_rad_s: float = 1e-8
    sample_time_s: float = 1e-9
    progress_m: float = 1e-8
    cross_track_m: float = 1e-8
    sample_heading_rad: float = 1e-8
    local_grip_multiplier: float = 1e-10
    assumed_boundary_slack_m: float = 1e-8

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and nonnegative")


@dataclass(frozen=True, slots=True)
class PoseReplayReport:
    passed: bool
    state_count: int
    maximum_position_error_m: float
    maximum_heading_error_rad: float
    maximum_body_velocity_error_mps: float
    maximum_yaw_rate_error_rad_s: float
    maximum_wheel_speed_error_rad_s: float
    road_valid_agrees: bool
    maximum_sample_time_error_s: float
    maximum_progress_error_m: float
    maximum_cross_track_error_m: float
    maximum_sample_heading_error_rad: float
    maximum_local_grip_error: float
    maximum_assumed_boundary_slack_error_m: float
    projection_valid_agrees: bool
    status_agrees: bool


@dataclass(frozen=True, slots=True)
class _Projection:
    station_m: float
    cross_track_m: float
    heading_rad: float


def _path_point(track: SpatialTrack, station_m: float) -> tuple[float, float]:
    station_m %= track.length_m
    # The course grid is at most 0.5 m in the supplied synthetic case.
    # Linear chords are a reference geometry approximation, not road edges.
    from bisect import bisect_right

    i = min(bisect_right(track.distance_m, station_m) - 1, track.cell_count - 1)
    fraction = ((station_m - track.distance_m[i]) /
                (track.distance_m[i + 1] - track.distance_m[i]))
    return (
        track.x_m[i] + fraction * (track.x_m[i + 1] - track.x_m[i]),
        track.y_m[i] + fraction * (track.y_m[i + 1] - track.y_m[i]),
    )


def _project_local(
    track: SpatialTrack, x_m: float, y_m: float, previous_station_m: float,
    window_m: float,
) -> _Projection:
    best_distance_sq = float("inf")
    best: _Projection | None = None
    length_m = track.length_m
    for i in range(track.cell_count):
        center_station = 0.5 * (track.distance_m[i] + track.distance_m[i + 1])
        lap_shift = round((previous_station_m - center_station) / length_m) * length_m
        if abs(center_station + lap_shift - previous_station_m) > window_m:
            continue
        dx = track.x_m[i + 1] - track.x_m[i]
        dy = track.y_m[i + 1] - track.y_m[i]
        norm_sq = dx * dx + dy * dy
        if norm_sq <= 0.0:
            continue
        fraction = min(1.0, max(0.0,
            ((x_m - track.x_m[i]) * dx + (y_m - track.y_m[i]) * dy) / norm_sq
        ))
        px = track.x_m[i] + fraction * dx
        py = track.y_m[i] + fraction * dy
        error_x, error_y = x_m - px, y_m - py
        distance_sq = error_x * error_x + error_y * error_y
        if distance_sq < best_distance_sq:
            best_distance_sq = distance_sq
            best = _Projection(
                track.distance_m[i] + fraction * (
                    track.distance_m[i + 1] - track.distance_m[i]
                ) + lap_shift,
                (dx * error_y - dy * error_x) / sqrt(norm_sq),
                atan2(dy, dx),
            )
    if best is None:
        raise ValueError("no course segment lies in the local projection window")
    return best


def _preview_curvature(track: SpatialTrack, station_m: float, ahead_m: float) -> float:
    """Conservative sampled bend strength within the short speed preview."""

    from bisect import bisect_right

    count = max(2, ceil(ahead_m / 0.5))
    peak = 0.0
    for index in range(count + 1):
        sample_station = (station_m + ahead_m * index / count) % track.length_m
        cell = min(bisect_right(track.distance_m, sample_station) - 1,
                   track.cell_count - 1)
        peak = max(peak, abs(track.curvature_per_m[cell]))
    return peak


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
    track: SpatialTrack, config: PlanarVehicleConfig,
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


def _controller(
    track: SpatialTrack, config: PlanarVehicleConfig,
    environment: PlanarEnvironment, settings: PoseDriverSettings,
    state: PlanarState, projection: _Projection,
) -> tuple[PlanarControls, float]:
    speed_mps = hypot(state.u_mps, state.v_mps)
    lookahead_m = settings.lookahead_base_m + settings.lookahead_seconds * speed_mps
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
    upcoming_curvature = _preview_curvature(track, rear_projection.station_m,
                                             lookahead_m + 4.0)
    available_lateral_mps2 = min(4.0, 0.35 * config.tire_mu * grip * config.gravity_mps2)
    corner_speed = sqrt(max(0.0, available_lateral_mps2) /
                        max(upcoming_curvature, 1e-9))
    target_speed = min(settings.cruise_speed_mps, corner_speed)
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


def run_pose_driver(
    track: SpatialTrack | None = None,
    *,
    vehicle_config: PlanarVehicleConfig | None = None,
    environment: PlanarEnvironment | None = None,
    settings: PoseDriverSettings | None = None,
    progress_callback: Callable[[PoseDriverSample, PlanarState], None] | None = None,
) -> PoseDriverRun:
    """Drive a finite segment with state feedback and bounded model work.

    The default is the coherent synthetic rounded rectangle. A completed run
    means the requested station progress was reached inside the assumed
    corridor; it does not certify a real road, cone clearance, or a lap time.
    """

    course = load_course(SYNTHETIC_DEMO_COURSE_ID) if track is None else track
    course.validate_coherent_arcs()
    if not course.closed:
        raise ValueError("pose driver requires a closed coherent course")
    car = synthetic_pose_vehicle() if vehicle_config is None else vehicle_config
    conditions = PlanarEnvironment() if environment is None else environment
    options = PoseDriverSettings() if settings is None else settings
    if not isinstance(car, PlanarVehicleConfig):
        raise TypeError("vehicle_config must be PlanarVehicleConfig")
    if not isinstance(conditions, PlanarEnvironment):
        raise TypeError("environment must be PlanarEnvironment")
    if not isinstance(options, PoseDriverSettings):
        raise TypeError("settings must be PoseDriverSettings")
    if options.target_progress_m > course.length_m:
        raise ValueError("target progress cannot exceed one course lap")

    first_dx = course.x_m[1] - course.x_m[0]
    first_dy = course.y_m[1] - course.y_m[0]
    start_heading = atan2(first_dy, first_dx) - (
        course.curvature_per_m[0] * course.cell_length_m[0] / 2.0
    )
    wheel_speed = options.initial_speed_mps / car.wheel_radius_m
    initial = PlanarState(
        x_m=course.x_m[0], y_m=course.y_m[0], heading_rad=start_heading,
        u_mps=options.initial_speed_mps,
        wheel_speeds_rad_s=(wheel_speed,) * 4,
    )
    simulator = PlanarSimulator(car, initial, environment=conditions)
    projection = _project_local(course, initial.x_m, initial.y_m, 0.0,
                                options.local_projection_window_m)
    initial_grip = _conservative_local_grip(car, conditions, initial)
    initial_slack = _assumed_footprint_slack(
        course, car, options, initial, projection.station_m,
    )
    times = [0.0]
    states = [initial]
    controls: list[PlanarControls] = []
    evaluations: list[PlanarEvaluation] = []
    samples = [PoseDriverSample(0.0, projection.station_m,
                                projection.cross_track_m,
                                remainder(initial.heading_rad - projection.heading_rad,
                                2.0 * pi), initial_grip, initial_slack)]
    substeps_per_control = ceil(options.output_step_s / car.integration_step_limit_s)
    internal_substeps = 0
    initial_road_valid = _initial_road_valid(car, conditions, initial)
    initial_status = (
        "road_domain_invalid" if not initial_road_valid else
        "outside_assumed_corridor" if initial_slack < 0.0 else None
    )
    status = initial_status or "maximum_control_steps"
    for _ in range(0 if initial_status is not None else options.maximum_control_steps):
        if simulator.time_s + options.output_step_s > options.maximum_simulated_time_s + 1e-12:
            status = "maximum_simulated_time"
            break
        if internal_substeps + substeps_per_control > options.maximum_internal_substeps:
            status = "maximum_internal_substeps"
            break
        try:
            command, _ = _controller(course, car, conditions, options,
                                     simulator.state, projection)
        except ValueError:
            status = "projection_lost"
            break
        try:
            evaluation = simulator.step(command, options.output_step_s)
        except (ValueError, ArithmeticError, OverflowError) as error:
            status = f"model_error: {error}"
            break
        internal_substeps += substeps_per_control
        controls.append(command)
        evaluations.append(evaluation)
        times.append(simulator.time_s)
        states.append(simulator.state)
        prior_projection = projection
        try:
            projection = _project_local(
                course, simulator.state.x_m, simulator.state.y_m,
                projection.station_m, options.local_projection_window_m,
            )
            footprint_slack = _assumed_footprint_slack(
                course, car, options, simulator.state, projection.station_m,
            )
        except ValueError:
            # A model step has already completed and cannot be rolled back.
            # Retain its state with an explicitly invalid station sample.
            grip = _conservative_local_grip(car, conditions, simulator.state)
            samples.append(PoseDriverSample(
                simulator.time_s, prior_projection.station_m,
                prior_projection.cross_track_m,
                remainder(simulator.state.heading_rad - prior_projection.heading_rad,
                          2.0 * pi), grip, float("-inf"), False,
            ))
            status = "projection_lost"
            break
        grip = _conservative_local_grip(car, conditions, simulator.state)
        sample = PoseDriverSample(
            simulator.time_s, projection.station_m, projection.cross_track_m,
            remainder(simulator.state.heading_rad - projection.heading_rad,
                      2.0 * pi), grip, footprint_slack,
        )
        samples.append(sample)
        if progress_callback is not None:
            progress_callback(sample, simulator.state)
        if not simulator.road_valid:
            status = "road_domain_invalid"
            break
        if sample.minimum_assumed_boundary_slack_m < 0.0:
            status = "outside_assumed_corridor"
            break
        if sample.progress_m >= options.target_progress_m:
            status = "target_reached"
            break
    return PoseDriverRun(
        track=course, vehicle_config=car, environment=conditions,
        settings=options, times_s=tuple(times), states=tuple(states),
        controls=tuple(controls), evaluations=tuple(evaluations),
        samples=tuple(samples), status=status,
        internal_substeps=internal_substeps,
        road_valid=initial_road_valid and simulator.road_valid,
    )


def replay_pose_driver(
    run: PoseDriverRun, *, tolerances: PoseReplayTolerances | None = None,
) -> PoseReplayReport:
    """Reintegrate controls and check recorded pose-derived diagnostics.

    This checks the declared synthetic track, car, and road inputs. It does not
    establish that those inputs describe a measured road or vehicle.
    """

    if not isinstance(run, PoseDriverRun):
        raise TypeError("run must be PoseDriverRun")
    limits = PoseReplayTolerances() if tolerances is None else tolerances
    if not isinstance(limits, PoseReplayTolerances):
        raise TypeError("tolerances must be PoseReplayTolerances")
    if (len(run.states) != len(run.controls) + 1 or
            len(run.times_s) != len(run.states) or
            len(run.samples) != len(run.states)):
        raise ValueError("recorded controls, states, times, and samples are not aligned")
    if len(run.controls) > run.settings.maximum_control_steps:
        raise ValueError("recorded controls exceed the declared step budget")
    if run.times_s[-1] > run.settings.maximum_simulated_time_s + 1e-9:
        raise ValueError("recorded duration exceeds the declared time budget")
    simulator = PlanarSimulator(run.vehicle_config, run.states[0],
                                environment=run.environment)
    max_position = max_heading = max_velocity = max_yaw = max_wheel = 0.0
    expected_samples: list[PoseDriverSample] = []
    projection = _project_local(
        run.track, simulator.state.x_m, simulator.state.y_m, 0.0,
        run.settings.local_projection_window_m,
    )
    initial_slack = _assumed_footprint_slack(
        run.track, run.vehicle_config, run.settings, simulator.state,
        projection.station_m,
    )
    expected_samples.append(PoseDriverSample(
        0.0, projection.station_m, projection.cross_track_m,
        remainder(simulator.state.heading_rad - projection.heading_rad, 2.0 * pi),
        _conservative_local_grip(run.vehicle_config, run.environment, simulator.state),
        initial_slack,
    ))
    initial_road_valid = _initial_road_valid(
        run.vehicle_config, run.environment, simulator.state,
    )
    terminal_status = (
        "road_domain_invalid" if not initial_road_valid else
        "outside_assumed_corridor" if initial_slack < 0.0 else None
    )
    stopped_at = 0 if terminal_status is not None else None
    replayed_substeps = 0
    for index, command in enumerate(run.controls, start=1):
        dt_s = run.times_s[index] - run.times_s[index - 1]
        if not isfinite(dt_s) or dt_s <= 0.0:
            raise ValueError("recorded times must be strictly increasing")
        if abs(dt_s - run.settings.output_step_s) > 1e-9:
            raise ValueError("recorded control interval differs from the fixed output step")
        replayed_substeps += ceil(
            run.settings.output_step_s / run.vehicle_config.integration_step_limit_s
        )
        if replayed_substeps > run.settings.maximum_internal_substeps:
            raise ValueError("recorded controls exceed the internal-substep budget")
        simulator.step(command, dt_s)
        actual, expected = simulator.state, run.states[index]
        max_position = max(max_position,
            hypot(actual.x_m - expected.x_m, actual.y_m - expected.y_m))
        max_heading = max(max_heading,
            abs(remainder(actual.heading_rad - expected.heading_rad, 2.0 * pi)))
        max_velocity = max(max_velocity,
            hypot(actual.u_mps - expected.u_mps, actual.v_mps - expected.v_mps))
        max_yaw = max(max_yaw,
            abs(actual.yaw_rate_rad_s - expected.yaw_rate_rad_s))
        max_wheel = max(max_wheel,
            *(abs(a - b) for a, b in zip(
                actual.wheel_speeds_rad_s, expected.wheel_speeds_rad_s,
                strict=True,
            )))
        prior_projection = projection
        try:
            projection = _project_local(
                run.track, actual.x_m, actual.y_m,
                prior_projection.station_m, run.settings.local_projection_window_m,
            )
            footprint_slack = _assumed_footprint_slack(
                run.track, run.vehicle_config, run.settings, actual,
                projection.station_m,
            )
        except ValueError:
            # Match the driver's retained final state after a lost projection.
            expected_samples.append(PoseDriverSample(
                simulator.time_s, prior_projection.station_m,
                prior_projection.cross_track_m,
                remainder(actual.heading_rad - prior_projection.heading_rad, 2.0 * pi),
                _conservative_local_grip(run.vehicle_config, run.environment, actual),
                float("-inf"), False,
            ))
            projection = prior_projection
            if terminal_status is None:
                terminal_status, stopped_at = "projection_lost", index
            continue
        expected_samples.append(PoseDriverSample(
            simulator.time_s, projection.station_m, projection.cross_track_m,
            remainder(actual.heading_rad - projection.heading_rad, 2.0 * pi),
            _conservative_local_grip(run.vehicle_config, run.environment, actual),
            footprint_slack,
        ))
        if terminal_status is None:
            if not simulator.road_valid:
                terminal_status = "road_domain_invalid"
            elif footprint_slack < 0.0:
                terminal_status = "outside_assumed_corridor"
            elif projection.station_m >= run.settings.target_progress_m:
                terminal_status = "target_reached"
            if terminal_status is not None:
                stopped_at = index
    if replayed_substeps != run.internal_substeps:
        raise ValueError("recorded internal-substep count disagrees with controls")
    road_agrees = (initial_road_valid and simulator.road_valid) == run.road_valid

    # The driver checks these limits before trying another control hold.
    if terminal_status is None:
        if len(run.controls) >= run.settings.maximum_control_steps:
            terminal_status = "maximum_control_steps"
        elif simulator.time_s + run.settings.output_step_s > (
            run.settings.maximum_simulated_time_s + 1e-12
        ):
            terminal_status = "maximum_simulated_time"
        elif replayed_substeps + ceil(
            run.settings.output_step_s / run.vehicle_config.integration_step_limit_s
        ) > run.settings.maximum_internal_substeps:
            terminal_status = "maximum_internal_substeps"
        elif run.status == "projection_lost" or run.status.startswith("model_error: "):
            try:
                next_command, _ = _controller(
                    run.track, run.vehicle_config, run.environment, run.settings,
                    simulator.state, projection,
                )
            except ValueError:
                terminal_status = "projection_lost"
            else:
                if run.status.startswith("model_error: "):
                    try:
                        simulator.step(next_command, run.settings.output_step_s)
                    except (ValueError, ArithmeticError, OverflowError) as error:
                        terminal_status = f"model_error: {error}"

    def absolute_error(recorded: float, derived: float) -> float:
        if recorded == derived:
            return 0.0
        if isfinite(recorded) and isfinite(derived):
            return abs(recorded - derived)
        return float("inf")

    def angular_error(recorded: float, derived: float) -> float:
        if isfinite(recorded) and isfinite(derived):
            return abs(remainder(recorded - derived, 2.0 * pi))
        return 0.0 if recorded == derived else float("inf")

    max_sample_time = max_progress = max_cross_track = 0.0
    max_sample_heading = max_grip = max_slack = 0.0
    projection_valid_agrees = True
    for recorded, derived, recorded_time in zip(
        run.samples, expected_samples, run.times_s, strict=True,
    ):
        max_sample_time = max(
            max_sample_time,
            absolute_error(recorded.time_s, derived.time_s),
            absolute_error(recorded_time, derived.time_s),
        )
        max_progress = max(max_progress,
                           absolute_error(recorded.progress_m, derived.progress_m))
        max_cross_track = max(max_cross_track, absolute_error(
            recorded.cross_track_error_m, derived.cross_track_error_m,
        ))
        max_sample_heading = max(max_sample_heading, angular_error(
            recorded.heading_error_rad, derived.heading_error_rad,
        ))
        max_grip = max(max_grip, absolute_error(
            recorded.local_grip_multiplier, derived.local_grip_multiplier,
        ))
        max_slack = max(max_slack, absolute_error(
            recorded.minimum_assumed_boundary_slack_m,
            derived.minimum_assumed_boundary_slack_m,
        ))
        projection_valid_agrees &= (
            recorded.projection_valid == derived.projection_valid
        )
    status_agrees = (run.status == terminal_status and
                     (stopped_at is None or stopped_at == len(run.controls)))
    return PoseReplayReport(
        passed=(
            max_position <= limits.position_m
            and max_heading <= limits.heading_rad
            and max_velocity <= limits.body_velocity_mps
            and max_yaw <= limits.yaw_rate_rad_s
            and max_wheel <= limits.wheel_speed_rad_s
            and road_agrees
            and max_sample_time <= limits.sample_time_s
            and max_progress <= limits.progress_m
            and max_cross_track <= limits.cross_track_m
            and max_sample_heading <= limits.sample_heading_rad
            and max_grip <= limits.local_grip_multiplier
            and max_slack <= limits.assumed_boundary_slack_m
            and projection_valid_agrees
            and status_agrees
        ),
        state_count=len(run.states),
        maximum_position_error_m=max_position,
        maximum_heading_error_rad=max_heading,
        maximum_body_velocity_error_mps=max_velocity,
        maximum_yaw_rate_error_rad_s=max_yaw,
        maximum_wheel_speed_error_rad_s=max_wheel,
        road_valid_agrees=road_agrees,
        maximum_sample_time_error_s=max_sample_time,
        maximum_progress_error_m=max_progress,
        maximum_cross_track_error_m=max_cross_track,
        maximum_sample_heading_error_rad=max_sample_heading,
        maximum_local_grip_error=max_grip,
        maximum_assumed_boundary_slack_error_m=max_slack,
        projection_valid_agrees=projection_valid_agrees,
        status_agrees=status_agrees,
    )


__all__ = [
    "POSE_MODEL_LABEL", "PoseDriverSettings", "PoseDriverSample",
    "PoseDriverRun", "PoseReplayTolerances", "PoseReplayReport",
    "synthetic_pose_vehicle", "run_pose_driver", "replay_pose_driver",
]
