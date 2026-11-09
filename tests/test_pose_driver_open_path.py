"""Open-reference helper contracts; no native or skidpad worker execution."""

from dataclasses import replace
from math import pi
from types import SimpleNamespace

import pytest

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Track
from lapsim.dynamics.conditions import PlanarEnvironment
from lapsim.events.skidpad_sequence import standard_skidpad_sequence
from lapsim.optimization import pose_driver


def _straight():
    return SpatialTrack.from_cells(
        cell_length_m=(4.0, 6.0), curvature_per_m=(0.0, 0.0), closed=False,
    )


def _preview(track, station, *, geometry="coherent_arcs", road=None):
    settings = replace(pose_driver.PoseDriverSettings(), reference_geometry=geometry)
    environment = PlanarEnvironment() if road is None else SimpleNamespace(road=road)
    return pose_driver._preview_speed_target(
        track, pose_driver.synthetic_pose_vehicle(), environment,
        settings, station, 5.0, 1.0,
    )


@pytest.mark.parametrize("station,expected_x", [
    (-3.0, 0.0), (0.0, 0.0), (3.0, 3.0),
    (10.0, 10.0), (13.0, 10.0),
])
def test_open_path_point_clamps_without_wrapping(station, expected_x):
    assert pose_driver._path_point(_straight(), station) == pytest.approx((expected_x, 0.0))


@pytest.mark.parametrize("previous,window,query_x,expected_station", [
    (0.1, 0.2, 10.0, 0.3),
    (9.9, 0.2, 0.0, 9.7),
    (21.0, 15.0, 8.0, 8.0),
    (-0.1, 0.5, -2.0, 0.0),
    (10.1, 0.5, 12.0, 10.0),
    (5.0, 1.0, 9.0, 6.0),
])
def test_open_projection_keeps_original_window_and_has_no_lap_copies(previous, window, query_x, expected_station):
    result = pose_driver._project_local(_straight(), query_x, 0.0, previous, window)
    assert result.station_m == pytest.approx(expected_station)
    assert 0.0 <= result.station_m <= 10.0
    assert previous - window <= result.station_m <= previous + window


def test_exact_open_finish_with_zero_window_uses_final_segment_heading():
    # A polygon helper fixture, not a coherent-arc or physical course claim.
    path = SpatialTrack(
        distance_m=(0.0, 10.0, 13.0), x_m=(0.0, 10.0, 10.0),
        y_m=(0.0, 0.0, 3.0), curvature_per_m=(0.0, 0.0), closed=False,
    )
    result = pose_driver._project_local(path, 10.0, 4.0, 13.0, 0.0)
    assert result.station_m == 13.0
    assert result.heading_rad == pytest.approx(pi / 2.0)
    assert result.cross_track_m == pytest.approx(0.0)


@pytest.mark.parametrize("previous,window", [(-2.0, 0.5), (12.0, 0.5)])
def test_disjoint_open_projection_window_is_rejected_not_recentered(previous, window):
    with pytest.raises(ValueError, match="local projection window"):
        pose_driver._project_local(_straight(), 5.0, 0.0, previous, window)


class _RecordedRoad:
    """Deterministic road-query fixture, not physical environment evidence."""

    def __init__(self):
        self.points = []

    def query(self, x, y):
        self.points.append((x, y))
        return SimpleNamespace(valid=True, friction_multiplier=0.0 if x < 2.0 else 1.0)


def test_open_tail_preview_never_queries_the_start_after_the_finish():
    road = _RecordedRoad()
    speed = _preview(_straight(), 9.9, road=road)
    assert speed == pose_driver.PoseDriverSettings().cruise_speed_mps
    # Each sample queries CG then four wheel centers. Wheel centers may lie
    # beyond the end; the reference CG samples themselves must stay on the tail.
    centers = road.points[::5]
    assert centers
    assert all(9.9 <= x <= 10.0 for x, _ in centers)
    assert all(y == 0.0 for _, y in centers)
    assert centers[-1] == (10.0, 0.0)
    assert len(centers) <= pose_driver._MAX_SPEED_PREVIEW_SAMPLES + 1


@pytest.mark.parametrize("station", [0.0, 0.01, 9.99, 10.0, 12.0])
def test_open_straight_sampled_polyline_preview_has_no_artificial_endpoint_bend(station):
    assert _preview(_straight(), station, geometry="sampled_polyline") == (
        pose_driver.PoseDriverSettings().cruise_speed_mps
    )


def test_open_preview_past_finish_is_one_endpoint_sample():
    road = _RecordedRoad()
    assert _preview(_straight(), 13.0, road=road) == pose_driver.PoseDriverSettings().cruise_speed_mps
    assert road.points[::5] == [(10.0, 0.0)]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_open_helpers_reject_nonfinite_station_inputs(value):
    track = _straight()
    with pytest.raises(ValueError):
        pose_driver._path_point(track, value)
    with pytest.raises(ValueError):
        pose_driver._project_local(track, 0.0, 0.0, value, 1.0)
    with pytest.raises(ValueError):
        _preview(track, value)


def test_open_projection_rejects_negative_window_and_nonfinite_query():
    track = _straight()
    for x, y, window in [(1.0, 0.0, -1.0), (float("inf"), 0.0, 1.0), (1.0, float("nan"), 1.0), (1.0, 0.0, float("inf"))]:
        with pytest.raises(ValueError):
            pose_driver._project_local(track, x, y, 1.0, window)


def test_closed_point_and_projection_keep_existing_seam_wrapping():
    track = SpatialTrack.from_track(
        Track.from_segments([Curve(10.0, 2.0 * pi)]),
        maximum_cell_length_m=0.5, close_geometry=False,
    )
    assert pose_driver._path_point(track, track.length_m) == pose_driver._path_point(track, 0.0)
    assert pose_driver._path_point(track, -0.2) == pose_driver._path_point(track, track.length_m - 0.2)
    x, y = pose_driver._path_point(track, 0.2)
    result = pose_driver._project_local(track, x, y, track.length_m - 0.1, 1.0)
    assert result.station_m == pytest.approx(track.length_m + 0.2)
    assert result.cross_track_m == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("geometry", ["coherent_arcs", "sampled_polyline"])
def test_closed_speed_preview_retains_periodic_station_behavior(geometry):
    track = SpatialTrack.from_track(
        Track.from_segments([Curve(5.0, 2.0 * pi)]),
        maximum_cell_length_m=0.5, close_geometry=False,
    )
    settings = replace(
        pose_driver.PoseDriverSettings(), cruise_speed_mps=10.0,
        reference_geometry=geometry,
    )
    config = pose_driver.synthetic_pose_vehicle()
    values = tuple(
        pose_driver._preview_speed_target(
            track, config, PlanarEnvironment(), settings,
            1.2 + lap * track.length_m, 5.0, 1.0,
        )
        for lap in (-1, 0, 1)
    )
    assert max(values) < settings.cruise_speed_mps
    assert values == pytest.approx((values[1],) * 3, abs=1e-10)


@pytest.mark.parametrize("phase_index", [1, 2, 3, 4])
def test_open_repeated_circle_positions_keep_the_local_ordered_station(phase_index):
    # Reference projection only, not a physical gate or completed-circle proof.
    course = standard_skidpad_sequence(
        entry_length_m=2.0, exit_length_m=3.0, maximum_cell_length_m=0.5,
    )
    expected = course.phases[phase_index].end_distance_m
    result = pose_driver._project_local(course.track, 0.0, 0.0, expected, 1.0)
    assert result.station_m == pytest.approx(expected, abs=1e-10)
    assert expected - 1.0 <= result.station_m <= expected + 1.0


def test_public_pose_driver_still_rejects_open_courses():
    with pytest.raises(ValueError, match="closed course"):
        pose_driver.run_pose_driver(_straight())


def test_closed_zero_horizon_underflow_retains_legacy_preview_sample_count():
    # Tiny helper-only fixture; no valid closed-course or physical claim.
    length = float.fromhex("0x0.0000000000001p-1022")
    track = SpatialTrack(
        distance_m=(0.0, length), x_m=(0.0, length), y_m=(0.0, 0.0),
        curvature_per_m=(0.0,), closed=True,
    )
    road = _RecordedRoad()
    _preview(track, 0.0, road=road)
    assert len(road.points) == 15  # Three legacy samples, CG + four wheel centers.
