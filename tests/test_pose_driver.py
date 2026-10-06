"""Focused checks for the optional synthetic pose-driving experiment."""

from dataclasses import replace
from math import pi

import pytest

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Track
from lapsim.dynamics.conditions import (
    PlanarEnvironment,
    PlanarRoad,
    RectangularGripPatch,
    RoadDomain,
)
import lapsim.optimization.pose_driver as pose_driver
from lapsim.optimization.pose_driver import (
    PoseDriverSettings,
    replay_pose_driver,
    run_pose_driver,
)
from lapsim.dynamics.planar import PlanarState
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
    assert len(run.states) == len(run.times_s) == len(run.samples)
    assert not run.samples[-1].projection_valid
    assert PoseDriverPlayback(run).frame_at(run.elapsed_pose_model_time_s)


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
