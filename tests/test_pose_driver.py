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


def test_session_budgets_stop_stateful_simulator():
    settings = replace(PoseDriverSettings(), maximum_control_steps=2)
    run = run_pose_driver(settings=settings)
    assert run.status == "maximum_control_steps"
    assert len(run.controls) == 2

    per_control = run.internal_substeps // len(run.controls)
    capped = run_pose_driver(settings=replace(
        PoseDriverSettings(), maximum_internal_substeps=per_control,
    ))
    assert capped.status == "maximum_internal_substeps"
    assert len(capped.controls) == 1
    assert capped.internal_substeps == per_control


def test_initial_road_and_assumed_footprint_are_checked_before_driving():
    limited_road = PlanarEnvironment(road=PlanarRoad(
        valid_domain=RoadDomain(-1.0, 1.0, -0.5, 0.5),
    ))
    off_road = run_pose_driver(environment=limited_road)
    assert off_road.status == "road_domain_invalid"
    assert not off_road.road_valid
    assert len(off_road.controls) == 0
    assert replay_pose_driver(off_road).passed

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
        RectangularGripPatch(30.0, 55.0, -5.0, 15.0, 0.3),
    )))
    run = run_pose_driver(
        environment=low_grip,
        settings=replace(PoseDriverSettings(), target_progress_m=55.0),
    )
    assert run.completed
    assert run.road_valid
    assert min(sample.local_grip_multiplier for sample in run.samples) == 0.3
    assert any(sum(control.brake_torques_nm) > 0.0
               for control in run.controls[150:])

    # Hold pose and speed fixed to isolate the controller's response to the
    # upcoming bend under the lower observed wheel-contact grip.
    state = PlanarState(
        x_m=34.0, y_m=0.0, u_mps=5.5,
        wheel_speeds_rad_s=(27.5,) * 4,
    )
    projection = pose_driver._project_local(run.track, 34.0, 0.0, 34.0, 12.0)
    base_controls, _ = pose_driver._controller(
        run.track, run.vehicle_config, PlanarEnvironment(), run.settings,
        state, projection,
    )
    patch_controls, _ = pose_driver._controller(
        run.track, run.vehicle_config, low_grip, run.settings,
        state, projection,
    )
    assert sum(patch_controls.brake_torques_nm) > sum(base_controls.brake_torques_nm)


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
