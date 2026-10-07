"""Focused checks for the optional synthetic pose-driving experiment."""

from dataclasses import replace
from math import cos, pi, sin

import numpy as np
import pytest

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Straight, Track
from lapsim.dynamics.conditions import (
    PlanarEnvironment,
    PlanarRoad,
    RectangularGripPatch,
    RoadDomain,
)
import lapsim.optimization.pose_driver as pose_driver
from lapsim.optimization.racing_line import (
    RacingLinePlanner, TrackCorridor, _track_from_closed_points,
)
from lapsim.optimization.pose_driver import (
    PoseDriverSettings,
    replay_pose_driver,
    run_pose_driver,
)
from lapsim.dynamics.planar import PlanarState
from lapsim.ui.course_catalog import SYNTHETIC_DEMO_COURSE_ID, load_course
from lapsim.ui.pose_driver_playback import PoseDriverPlayback


@pytest.fixture(scope="module")
def segment_run():
    return run_pose_driver()


def test_synthetic_driver_follows_a_bend_inside_assumed_corridor(segment_run):
    run = segment_run
    assert run.completed
    assert run.samples[-1].progress_m >= 80.0
    assert run.elapsed_pose_model_time_s <= run.settings.maximum_simulated_time_s
    assert run.internal_substeps <= run.settings.maximum_internal_substeps
    assert len(run.states) == len(run.controls) + 1 == len(run.samples)
    assert run.maximum_absolute_cross_track_error_m < 1.0
    assert run.minimum_assumed_boundary_slack_m > 0.0
    # The edge cap is inactive for the centered, default-corridor case.
    assert run.minimum_assumed_boundary_slack_m > run.settings.edge_slowdown_slack_m
    negligible_cap = run_pose_driver(settings=replace(
        run.settings, edge_slowdown_slack_m=1e-6,
        edge_outward_prediction_s=1e-6,
    ))
    assert run.times_s == negligible_cap.times_s
    assert run.states == negligible_cap.states
    assert any(abs(control.steering_angles_rad[0]) > 0.04 for control in run.controls)


def test_controls_replay_pose_and_detect_changed_state(segment_run):
    report = replay_pose_driver(segment_run)
    assert report.passed
    assert report.maximum_position_error_m < 1e-8

    changed_states = list(segment_run.states)
    changed_states[30] = replace(changed_states[30], x_m=changed_states[30].x_m + 0.01)
    altered = replace(segment_run, states=tuple(changed_states))
    mismatch = replay_pose_driver(altered)
    assert not mismatch.passed
    assert mismatch.maximum_position_error_m >= 0.009


@pytest.mark.parametrize(("field", "altered_value"), [
    ("time_s", 999.0),
    ("progress_m", 999.0),
    ("cross_track_error_m", 999.0),
    ("heading_error_rad", 1.0),
    ("local_grip_multiplier", 0.1),
    ("minimum_assumed_boundary_slack_m", -1.0),
    ("projection_valid", False),
])
def test_replay_rejects_changed_pose_diagnostic(
    segment_run, field, altered_value,
):
    changed_samples = list(segment_run.samples)
    changed_samples[30] = replace(changed_samples[30], **{field: altered_value})
    report = replay_pose_driver(replace(segment_run, samples=tuple(changed_samples)))
    assert not report.passed
    assert report.status_agrees


def test_replay_rejects_changed_terminal_status_and_time_origin(segment_run):
    changed_status = replay_pose_driver(replace(segment_run, status="maximum_control_steps"))
    assert not changed_status.passed
    assert not changed_status.status_agrees

    shifted = replay_pose_driver(replace(
        segment_run,
        times_s=tuple(time + 0.1 for time in segment_run.times_s),
        samples=tuple(replace(sample, time_s=sample.time_s + 0.1)
                      for sample in segment_run.samples),
    ))
    assert not shifted.passed
    assert shifted.maximum_sample_time_error_s >= 0.099


def test_session_budgets_stop_stateful_simulator():
    settings = replace(PoseDriverSettings(), maximum_control_steps=2)
    run = run_pose_driver(settings=settings)
    assert run.status == "maximum_control_steps"
    assert len(run.controls) == 2
    assert replay_pose_driver(run).passed

    per_control = run.internal_substeps // len(run.controls)
    capped = run_pose_driver(settings=replace(
        PoseDriverSettings(), maximum_internal_substeps=per_control,
    ))
    assert capped.status == "maximum_internal_substeps"
    assert len(capped.controls) == 1
    assert capped.internal_substeps == per_control
    assert replay_pose_driver(capped).passed


def test_initial_road_and_assumed_footprint_are_checked_before_driving():
    limited_road = PlanarEnvironment(road=PlanarRoad(
        valid_domain=RoadDomain(-1.0, 1.0, -0.5, 0.5),
    ))
    off_road = run_pose_driver(environment=limited_road)
    assert off_road.status == "road_domain_invalid"
    assert not off_road.road_valid
    assert len(off_road.controls) == 0
    assert replay_pose_driver(off_road).passed

    road_exited_after_step = run_pose_driver(environment=PlanarEnvironment(
        road=PlanarRoad(valid_domain=RoadDomain(-1.0, 0.95, -1.0, 1.0)),
    ))
    assert road_exited_after_step.status == "road_domain_invalid"
    assert len(road_exited_after_step.controls) == 1
    assert replay_pose_driver(road_exited_after_step).passed

    circle = SpatialTrack.from_track(
        Track.from_segments((Curve(2.0, 2.0 * pi),)),
        maximum_cell_length_m=0.1,
    )
    outside = run_pose_driver(circle, settings=replace(
        PoseDriverSettings(), target_progress_m=1.0,
        assumed_half_width_m=1.201,
    ))
    assert outside.status == "outside_assumed_corridor"
    assert outside.minimum_assumed_boundary_slack_m < 0.0
    assert len(outside.controls) == 0
    assert replay_pose_driver(outside).passed


def test_lost_local_projection_keeps_trace_aligned(monkeypatch):
    original = pose_driver._project_local
    calls = 0

    def lose_after_first_step(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 7:
            raise ValueError("projection unavailable")
        return original(*args, **kwargs)

    monkeypatch.setattr(pose_driver, "_project_local", lose_after_first_step)
    run = run_pose_driver()
    assert run.status == "projection_lost"
    assert len(run.controls) == 1
    assert len(run.states) == len(run.times_s) == len(run.samples)
    assert not run.samples[-1].projection_valid
    playback = PoseDriverPlayback(run)
    start = playback.control_values_at(run.times_s[-2])
    midway = playback.control_values_at(
        (run.times_s[-2] + run.times_s[-1]) / 2.0
    )
    terminal = playback.control_values_at(run.times_s[-1])
    assert start is not None and midway is not None and terminal is not None
    assert start[4] == pytest.approx(run.samples[-2].cross_track_error_m)
    assert start[5] == pytest.approx(run.samples[-2].heading_error_rad * 180.0 / pi)
    assert start[7] == pytest.approx(run.samples[-2].minimum_assumed_boundary_slack_m)
    for displayed in (midway, terminal):
        assert all(np.isnan(displayed[index]) for index in (4, 5, 7))
        assert displayed[:4] == start[:4]
        assert np.isfinite(displayed[6])
        assert np.isfinite(displayed[8])
    assert midway[6] == run.samples[-2].local_grip_multiplier
    assert terminal[6] == run.samples[-1].local_grip_multiplier
    assert terminal[8] == pytest.approx(run.states[-1].yaw_rate_rad_s * 180.0 / pi)
    frame = playback.frame_at(run.elapsed_pose_model_time_s)
    assert frame.x_m == pytest.approx(run.states[-1].x_m)
    assert frame.y_m == pytest.approx(run.states[-1].y_m)


def test_local_grip_changes_closed_loop_commands():
    low_grip = PlanarEnvironment(road=PlanarRoad(patches=(
        RectangularGripPatch(36.0, 55.0, -3.0, 16.0, 0.3),
    )))
    run = run_pose_driver(
        environment=low_grip,
        settings=replace(PoseDriverSettings(), target_progress_m=55.0),
    )
    assert run.completed
    assert run.road_valid
    assert min(sample.local_grip_multiplier for sample in run.samples) == 0.3
    assert run.minimum_assumed_boundary_slack_m > 0.0
    first_brake = next(
        sample.progress_m for sample, control in zip(run.samples, run.controls)
        if sum(control.brake_torques_nm) > 0.0
    )
    first_contact = next(
        sample.progress_m for sample in run.samples
        if sample.local_grip_multiplier < 1.0
    )
    assert first_brake < first_contact - 1.0
    assert replay_pose_driver(run).passed

    # Hold pose and speed fixed to isolate the controller's response to the
    # upcoming bend under the lower observed wheel-contact grip.
    state = PlanarState(
        x_m=33.0, y_m=0.0, u_mps=5.5,
        wheel_speeds_rad_s=(27.5,) * 4,
    )
    projection = pose_driver._project_local(run.track, 33.0, 0.0, 33.0, 12.0)
    base_controls, base_grip = pose_driver._controller(
        run.track, run.vehicle_config, PlanarEnvironment(), run.settings,
        state, projection,
    )
    patch_controls, patch_grip = pose_driver._controller(
        run.track, run.vehicle_config, low_grip, run.settings,
        state, projection,
    )
    assert base_grip == patch_grip == 1.0
    assert sum(patch_controls.brake_torques_nm) > sum(base_controls.brake_torques_nm)


@pytest.mark.parametrize("offset_m", (1.5, -1.5))
def test_initial_lateral_offset_uses_start_path_normal_and_bounded_work(offset_m):
    settings = replace(
        PoseDriverSettings(), initial_lateral_offset_m=offset_m,
        maximum_control_steps=2,
    )
    run = run_pose_driver(settings=settings)
    first = run.states[0]
    assert first.x_m == pytest.approx(
        run.track.x_m[0] - sin(first.heading_rad) * offset_m,
    )
    assert first.y_m == pytest.approx(
        run.track.y_m[0] + cos(first.heading_rad) * offset_m,
    )
    assert run.samples[0].cross_track_error_m == pytest.approx(offset_m, abs=0.001)
    assert 0.0 < run.samples[0].minimum_assumed_boundary_slack_m < 0.5
    assert sum(run.controls[0].brake_torques_nm) > 0.0
    assert run.status == "maximum_control_steps"
    assert len(run.controls) == 2
    assert run.internal_substeps <= settings.maximum_internal_substeps
    assert replay_pose_driver(run).passed


def test_nominal_offset_limit_can_still_start_outside_curved_footprint():
    # A CG offset can satisfy the static width bound while the front/rear
    # body corners cross the reference corridor on the curved starting cell.
    run = run_pose_driver(settings=replace(
        PoseDriverSettings(), initial_lateral_offset_m=-1.9,
    ))
    assert run.status == "outside_assumed_corridor"
    assert run.minimum_assumed_boundary_slack_m < 0.0
    assert len(run.controls) == 0
    assert replay_pose_driver(run).passed


@pytest.mark.parametrize("offset_m", (1.8, -1.8))
@pytest.mark.parametrize("with_patch", (False, True))
def test_near_edge_pose_run_recovers_on_declared_synthetic_road(
    offset_m, with_patch,
):
    environment = PlanarEnvironment(road=PlanarRoad(patches=(
        RectangularGripPatch(36.0, 55.0, -3.0, 16.0, 0.3),
    ))) if with_patch else PlanarEnvironment()
    run = run_pose_driver(
        settings=replace(PoseDriverSettings(), initial_lateral_offset_m=offset_m),
        environment=environment,
    )
    assert run.completed
    assert run.minimum_assumed_boundary_slack_m > 0.0
    assert run.samples[-1].progress_m >= 80.0
    assert abs(run.samples[-1].cross_track_error_m) < 0.5
    assert run.internal_substeps <= run.settings.maximum_internal_substeps
    assert replay_pose_driver(run).passed


def test_edge_cap_retains_corridor_in_one_long_lookahead_experiment():
    # This deliberately challenging controller setting is an example, not a
    # guarantee for other paths or grip maps. Tiny positive parameters make
    # the edge cap effectively inactive while preserving validated settings.
    base = replace(
        PoseDriverSettings(), initial_lateral_offset_m=1.8,
        lookahead_seconds=3.0, maximum_simulated_time_s=25.0,
        maximum_control_steps=500, maximum_internal_substeps=80_000,
    )
    negligible_cap = run_pose_driver(settings=replace(
        base, edge_slowdown_slack_m=1e-6,
        edge_outward_prediction_s=1e-6,
    ))
    recovery_cap = run_pose_driver(settings=base)
    assert negligible_cap.status == "outside_assumed_corridor"
    assert negligible_cap.minimum_assumed_boundary_slack_m < 0.0
    assert recovery_cap.completed
    assert recovery_cap.minimum_assumed_boundary_slack_m > 0.0
    assert recovery_cap.elapsed_pose_model_time_s > negligible_cap.elapsed_pose_model_time_s
    assert replay_pose_driver(negligible_cap).passed
    assert replay_pose_driver(recovery_cap).passed


@pytest.mark.parametrize("side", (1.0, -1.0))
def test_edge_speed_cap_responds_to_outward_velocity_and_future_low_grip(
    segment_run, side,
):
    run = segment_run
    options = run.settings
    wheel_speed_rad_s = options.initial_speed_mps / run.vehicle_config.wheel_radius_m

    def brake_at(x_m, world_side_speed_mps, environment):
        state = PlanarState(
            x_m=x_m, y_m=side * 1.5, u_mps=options.initial_speed_mps,
            v_mps=world_side_speed_mps,
            wheel_speeds_rad_s=(wheel_speed_rad_s,) * 4,
        )
        projection = pose_driver._project_local(
            run.track, state.x_m, state.y_m, x_m,
            options.local_projection_window_m,
        )
        slack = pose_driver._assumed_footprint_slack(
            run.track, run.vehicle_config, options, state,
            projection.station_m,
        )
        command, _ = pose_driver._controller(
            run.track, run.vehicle_config, environment, options,
            state, projection, slack,
        )
        return sum(command.brake_torques_nm)

    base_road = PlanarEnvironment()
    inward_brake = brake_at(0.0, -side * 0.8, base_road)
    still_brake = brake_at(0.0, 0.0, base_road)
    outward_brake = brake_at(0.0, side * 0.8, base_road)
    # Nonzero inward body speed also changes total speed and the independent
    # bend preview; only the outward-versus-inward ordering is guaranteed by
    # the additional edge cap at these fixed states.
    assert outward_brake > inward_brake
    assert outward_brake > still_brake

    patch = PlanarEnvironment(road=PlanarRoad(patches=(
        RectangularGripPatch(36.0, 55.0, -3.0, 16.0, 0.3),
    )))
    assert brake_at(33.0, 0.0, patch) > brake_at(33.0, 0.0, base_road)


@pytest.mark.parametrize(("field", "value"), [
    ("initial_lateral_offset_m", float("nan")),
    ("initial_lateral_offset_m", float("inf")),
    ("initial_lateral_offset_m", 1.901),
    ("initial_lateral_offset_m", -1.901),
    ("edge_slowdown_slack_m", 0.0),
    ("edge_slowdown_slack_m", float("inf")),
    ("edge_outward_prediction_s", -0.1),
    ("edge_outward_prediction_s", float("nan")),
    ("edge_rejoin_speed_mps", 0.0),
    ("edge_rejoin_speed_mps", float("inf")),
])
def test_offset_and_recovery_settings_are_finite_and_bounded(field, value):
    with pytest.raises(ValueError):
        replace(PoseDriverSettings(), **{field: value})


def test_local_projection_preserves_seam_and_large_window_results(segment_run):
    track = segment_run.track

    def full_scan(x_m, y_m, previous_station_m, window_m):
        nearest = None
        for index in range(track.cell_count):
            center_m = 0.5 * (track.distance_m[index] + track.distance_m[index + 1])
            lap_shift_m = round((previous_station_m - center_m) / track.length_m) * track.length_m
            if abs(center_m + lap_shift_m - previous_station_m) > window_m:
                continue
            dx = track.x_m[index + 1] - track.x_m[index]
            dy = track.y_m[index + 1] - track.y_m[index]
            norm_sq = dx * dx + dy * dy
            if norm_sq <= 0.0:
                continue
            fraction = min(1.0, max(0.0,
                ((x_m - track.x_m[index]) * dx +
                 (y_m - track.y_m[index]) * dy) / norm_sq,
            ))
            px = track.x_m[index] + fraction * dx
            py = track.y_m[index] + fraction * dy
            distance_sq = (x_m - px)**2 + (y_m - py)**2
            if nearest is None or distance_sq < nearest[0]:
                nearest = (distance_sq,
                           track.distance_m[index] + fraction *
                           (track.distance_m[index + 1] - track.distance_m[index]) +
                           lap_shift_m)
        return nearest

    for previous_station_m, window_m in (
        (0.05, 12.0), (track.length_m - 0.05, 12.0),
        (track.length_m + 0.05, 12.0),
        (25.0, track.length_m / 2.0 + 1.0),
    ):
        x_m, y_m = pose_driver._path_point(track, previous_station_m + 0.2)
        found = pose_driver._project_local(
            track, x_m + 0.1, y_m + 0.2, previous_station_m, window_m,
        )
        expected = full_scan(x_m + 0.1, y_m + 0.2,
                             previous_station_m, window_m)
        assert expected is not None
        assert found.station_m == pytest.approx(expected[1], abs=1e-10)


def test_local_projection_includes_long_cells_overlapping_a_seam_window():
    # This course is an exact closed sequence of long straights and arcs.
    # A cell's midpoint may lie outside a narrow search window even while its
    # endpoint and the requested projection lie inside that window.
    segments = tuple(
        segment
        for straight_length_m in (40.0, 20.0, 40.0, 20.0)
        for segment in (Straight(straight_length_m), Curve(12.0, pi / 2.0))
    )
    track = SpatialTrack.from_track(
        Track.from_segments(segments),
        maximum_cell_length_m=100.0,
        close_geometry=False,
    )
    track.validate_coherent_arcs()
    assert track.cell_length_m[0] == pytest.approx(40.0)

    for previous_station_m, station_m in (
        (0.15, 0.30),
        (track.length_m - 0.15, track.length_m - 0.30),
        (track.length_m + 0.15, track.length_m + 0.30),
    ):
        x_m, y_m = pose_driver._path_point(track, station_m)
        projection = pose_driver._project_local(
            track, x_m, y_m, previous_station_m, 0.5,
        )
        assert projection.station_m == pytest.approx(station_m, abs=1e-10)
        assert projection.cross_track_m == pytest.approx(0.0, abs=1e-10)


def test_local_projection_clips_station_to_requested_window_on_long_cell():
    segments = tuple(
        segment
        for straight_length_m in (40.0, 20.0, 40.0, 20.0)
        for segment in (Straight(straight_length_m), Curve(12.0, pi / 2.0))
    )
    track = SpatialTrack.from_track(
        Track.from_segments(segments),
        maximum_cell_length_m=100.0,
        close_geometry=False,
    )
    track.validate_coherent_arcs()
    x_m, y_m = pose_driver._path_point(track, 35.0)
    projection = pose_driver._project_local(track, x_m, y_m, 15.0, 8.0)
    assert projection.station_m == pytest.approx(23.0, abs=1e-10)


def test_local_projection_considers_both_lap_copies_of_a_major_arc():
    # A coherent circle can have one saved arc longer than half a lap. Near
    # the seam, both copies of that arc overlap the station search window.
    track = SpatialTrack.from_track(
        Track.from_segments((
            Curve(12.0, 4.0 * pi / 3.0),
            Curve(12.0, pi / 3.0),
            Curve(12.0, pi / 3.0),
        )),
        maximum_cell_length_m=100.0,
        close_geometry=False,
    )
    track.validate_coherent_arcs()
    assert track.cell_length_m[0] > track.length_m / 2.0
    station_m = track.distance_m[1] - 1.0
    x_m, y_m = pose_driver._path_point(track, station_m)
    projection = pose_driver._project_local(track, x_m, y_m, 0.0, 30.0)
    assert projection.station_m == pytest.approx(station_m - track.length_m, abs=1e-10)
    assert projection.cross_track_m == pytest.approx(0.0, abs=1e-10)


def test_pose_driver_refines_coarse_coherent_arcs_before_driving():
    source = SpatialTrack.from_track(
        Track.from_segments(tuple(
            segment
            for straight_length_m in (40.0, 20.0, 40.0, 20.0)
            for segment in (Straight(straight_length_m), Curve(12.0, pi / 2.0))
        )),
        maximum_cell_length_m=100.0,
        close_geometry=False,
    )
    source.validate_coherent_arcs()
    arc_midpoint_station_m = source.distance_m[1] + 12.0 * pi / 4.0
    source_chord_point = pose_driver._path_point(source, arc_midpoint_station_m)

    run = run_pose_driver(source, settings=replace(
        PoseDriverSettings(), target_progress_m=55.0,
    ))
    assert run.completed
    assert run.track.cell_count > source.cell_count
    assert max(run.track.cell_length_m) <= 0.5 + 1e-12
    assert run.track.length_m == pytest.approx(source.length_m)
    for station_m, x_m, y_m in zip(
        source.distance_m, source.x_m, source.y_m, strict=True,
    ):
        refined_index = run.track.distance_m.index(station_m)
        assert run.track.x_m[refined_index] == pytest.approx(x_m)
        assert run.track.y_m[refined_index] == pytest.approx(y_m)
    refined_point = pose_driver._path_point(run.track, arc_midpoint_station_m)
    assert refined_point[0] == pytest.approx(40.0 + 12.0 * sin(pi / 4.0), abs=0.01)
    assert refined_point[1] == pytest.approx(12.0 * (1.0 - cos(pi / 4.0)), abs=0.01)
    assert ((refined_point[0] - source_chord_point[0])**2 +
            (refined_point[1] - source_chord_point[1])**2)**0.5 > 3.4
    assert replay_pose_driver(run).passed


def test_pose_driver_preserves_default_fine_grid_identity():
    source = load_course(SYNTHETIC_DEMO_COURSE_ID)
    assert max(source.cell_length_m) <= 0.5 + 1e-9
    run = run_pose_driver(source, settings=replace(
        PoseDriverSettings(), maximum_control_steps=1,
    ))
    assert run.track is source
    assert replay_pose_driver(run).passed


def _sampled_demo_polyline() -> SpatialTrack:
    course = load_course(SYNTHETIC_DEMO_COURSE_ID)
    return _track_from_closed_points(
        np.asarray(course.x_m[:-1:2]), np.asarray(course.y_m[:-1:2]),
    )


def test_sampled_polyline_is_explicit_and_replayable():
    path = _sampled_demo_polyline()
    with pytest.raises(ValueError, match="arc chord mismatch"):
        run_pose_driver(path, settings=replace(
            PoseDriverSettings(), maximum_control_steps=1,
        ))

    settings = replace(
        PoseDriverSettings(), reference_geometry="sampled_polyline",
        target_progress_m=20.0,
    )
    run = run_pose_driver(path, settings=settings)
    assert run.completed
    assert run.track.cell_count > path.cell_count
    assert max(run.track.cell_length_m) <= 0.5 + 1e-9
    assert run.states[0].heading_rad == pytest.approx(
        pose_driver.atan2(
            run.track.y_m[1] - run.track.y_m[0],
            run.track.x_m[1] - run.track.x_m[0],
        )
    )
    assert run.internal_substeps <= settings.maximum_internal_substeps
    assert replay_pose_driver(run).passed


def test_sampled_polyline_rejects_bad_saved_geometry():
    path = _sampled_demo_polyline()
    settings = replace(PoseDriverSettings(), reference_geometry="sampled_polyline")
    station = list(path.distance_m)
    station[1] += 0.01
    with pytest.raises(ValueError, match="station/chord mismatch"):
        run_pose_driver(replace(path, distance_m=tuple(station)), settings=settings)

    x = list(path.x_m)
    x[-1] += 0.01
    with pytest.raises(ValueError, match="closed endpoint mismatch"):
        run_pose_driver(replace(path, x_m=tuple(x)), settings=settings)

    x = list(path.x_m)
    y = list(path.y_m)
    x[1], y[1] = x[0], y[0]
    with pytest.raises(ValueError, match="degenerate chord"):
        run_pose_driver(replace(path, x_m=tuple(x), y_m=tuple(y)), settings=settings)

    with pytest.raises(ValueError, match="reference_geometry"):
        replace(PoseDriverSettings(), reference_geometry="unsupported")


def test_polyline_speed_preview_is_stable_under_collinear_refinement():
    source = load_course(SYNTHETIC_DEMO_COURSE_ID)
    corridor = TrackCorridor.constant(
        source, left_width_m=3.0, right_width_m=3.0,
        vehicle_width_m=1.8, safety_margin_m=0.2,
        source="assumed synthetic demonstration corridor",
    )
    plan = RacingLinePlanner(maximum_cell_length_m=1.0).plan(source, corridor)
    assert plan.status == "candidate"
    polygon = plan.candidate_track
    half_meter = polygon.refine(0.5)
    quarter_meter = polygon.refine(0.25)
    settings = replace(PoseDriverSettings(), reference_geometry="sampled_polyline")
    preview_settings = replace(settings, cruise_speed_mps=8.0)
    preview_stations_m = (35.0, 40.0, 45.0, 50.0, 55.0, 80.0)
    preview_by_grid = tuple(tuple(
        pose_driver._preview_speed_target(
            path, pose_driver.synthetic_pose_vehicle(), PlanarEnvironment(),
            preview_settings, station_m, 8.0, 1.0,
        )
        for station_m in preview_stations_m
    ) for path in (half_meter, quarter_meter))
    assert min(preview_by_grid[0]) < 7.0  # the bend limit is active
    assert preview_by_grid[0] == pytest.approx(preview_by_grid[1], abs=1e-8)

    half_run = run_pose_driver(half_meter, settings=settings)
    quarter_run = run_pose_driver(quarter_meter, settings=settings)
    assert half_run.completed and quarter_run.completed
    # The controller samples on a 0.05 s grid, so agreement within one
    # output interval is the meaningful duration tolerance.
    assert abs(half_run.elapsed_pose_model_time_s -
               quarter_run.elapsed_pose_model_time_s) <= settings.output_step_s + 1e-9
    assert replay_pose_driver(half_run).passed
    assert replay_pose_driver(quarter_run).passed


def test_pose_driver_rejects_refinement_above_cell_budget():
    source = SpatialTrack.from_track(
        Track.from_segments((Curve(10_000.0, pi / 2.0),) * 4),
        maximum_cell_length_m=20_000.0,
        close_geometry=False,
    )
    source.validate_coherent_arcs()
    with pytest.raises(ValueError, match="100000-cell compute cap"):
        run_pose_driver(source)


def test_speed_preview_is_bounded_and_rejects_zero_chord(segment_run):
    run = segment_run
    options = replace(
        PoseDriverSettings(), lookahead_base_m=1e308,
        lookahead_seconds=1e308,
    )
    state = run.states[0]
    projection = pose_driver._project_local(
        run.track, state.x_m, state.y_m, 0.0, options.local_projection_window_m,
    )
    controls, grip = pose_driver._controller(
        run.track, run.vehicle_config, run.environment,
        options, state, projection,
    )
    assert grip == 1.0
    assert abs(controls.steering_angles_rad[0]) <= options.maximum_steering_rad

    malformed = replace(run.track,
        x_m=run.track.x_m[:10] + (run.track.x_m[9],) + run.track.x_m[11:],
        y_m=run.track.y_m[:10] + (run.track.y_m[9],) + run.track.y_m[11:],
    )
    with pytest.raises(ValueError, match="zero chord"):
        run_pose_driver(malformed)
    with pytest.raises(ValueError, match="invalid preview-path tangent"):
        pose_driver._preview_speed_target(
            malformed, run.vehicle_config, run.environment, run.settings,
            0.0, 4.5, 1.0,
        )


def test_pose_playback_uses_recorded_vehicle_pose(segment_run):
    playback = PoseDriverPlayback(segment_run)
    index = 100
    frame = playback.frame_at(segment_run.times_s[index])
    state = segment_run.states[index]
    assert playback.track is segment_run.track
    assert playback.duration_s == segment_run.elapsed_pose_model_time_s
    assert playback.display_time_label == "Pose-model time"
    assert not playback.has_battery_telemetry
    assert frame.decision is None
    assert frame.x_m == pytest.approx(state.x_m)
    assert frame.y_m == pytest.approx(state.y_m)
    assert frame.course_heading_rad == pytest.approx(state.heading_rad)
    assert playback.local_path_m(frame, behind_m=10.0, ahead_m=20.0)
    displayed = playback.control_values_at(segment_run.times_s[index])
    assert displayed is not None
    assert displayed[0] == pytest.approx(
        segment_run.controls[index].steering_angles_rad[0] * 180.0 / 3.141592653589793
    )
    assert displayed[4] == pytest.approx(segment_run.samples[index].cross_track_error_m)
    assert displayed[6] == pytest.approx(segment_run.samples[index].local_grip_multiplier)
    between = playback.control_values_at(
        (segment_run.times_s[index] + segment_run.times_s[index + 1]) / 2.0
    )
    assert between is not None
    assert between[:4] == displayed[:4]
    assert between[6] == pytest.approx(segment_run.samples[index].local_grip_multiplier)


def test_pose_playback_uses_terminal_grip_sample_after_patch_crossing():
    road = PlanarRoad(patches=(
        RectangularGripPatch(0.15, 0.4, -0.5, 0.5, 0.3),
    ))
    run = run_pose_driver(
        environment=PlanarEnvironment(road=road),
        settings=PoseDriverSettings(
            target_progress_m=0.1, maximum_control_steps=2,
            maximum_simulated_time_s=0.1,
        ),
    )
    assert run.status == "target_reached"
    assert len(run.controls) == 1
    assert [sample.local_grip_multiplier for sample in run.samples] == [1.0, 0.3]

    playback = PoseDriverPlayback(run)
    during = playback.control_values_at(run.times_s[-1] / 2.0)
    terminal = playback.control_values_at(playback.duration_s)
    assert during is not None and terminal is not None
    assert during[6] == 1.0
    assert terminal[6] == run.samples[-1].local_grip_multiplier
    assert terminal[:4] == during[:4]
