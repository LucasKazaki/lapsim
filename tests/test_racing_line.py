"""Focused checks for the optional deterministic racing-line proposal."""

from __future__ import annotations

from dataclasses import replace
from math import pi
from types import SimpleNamespace

import numpy as np
import pytest

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Straight, Track
from lapsim.optimization.racing_line import (
    RacingLinePlanner,
    TrackCorridor,
    _continuous_offset_violation,
    _has_nonadjacent_segment_intersection,
    _periodic_cubic_basis_at,
    _scaled_candidate_track,
    compare_lines_with_lap_model,
)
from lapsim.ui.presets import VehicleSetup, make_prius_benchmark


def _rounded_rectangle() -> SpatialTrack:
    return SpatialTrack.from_track(
        Track.from_segments(
            [
                Straight(40.0), Curve(12.0, pi / 2),
                Straight(20.0), Curve(12.0, pi / 2),
                Straight(40.0), Curve(12.0, pi / 2),
                Straight(20.0), Curve(12.0, pi / 2),
            ]
        ),
        maximum_cell_length_m=0.5,
    )


def _corridor(track: SpatialTrack) -> TrackCorridor:
    return TrackCorridor.constant(
        track,
        left_width_m=3.0,
        right_width_m=3.0,
        vehicle_width_m=1.4,
        safety_margin_m=0.2,
        source="synthetic test corridor",
    )


def test_missing_or_unusable_corridor_is_not_inferred() -> None:
    track = _rounded_rectangle()
    with pytest.raises(ValueError, match="no usable corridor"):
        TrackCorridor.constant(
            track,
            left_width_m=0.8,
            right_width_m=2.0,
            vehicle_width_m=1.4,
            safety_margin_m=0.2,
            source="synthetic",
        )
    with pytest.raises(TypeError):
        RacingLinePlanner().plan(track)  # type: ignore[call-arg]


def test_generated_paths_recompute_arc_length_and_curvature() -> None:
    track = _rounded_rectangle()
    plan = RacingLinePlanner().plan(track, _corridor(track))
    assert plan.status == "candidate"
    assert plan.objective_candidate < plan.objective_baseline
    assert plan.max_constraint_violation_m <= 1e-6
    assert plan.max_abs_offset_m > 0.1
    assert plan.candidate_track.length_m != pytest.approx(track.length_m, abs=0.1)
    assert plan.candidate_track.length_m != pytest.approx(plan.baseline_track.length_m, abs=0.1)
    for path in (plan.baseline_track, plan.candidate_track):
        assert path.x_m[0] == path.x_m[-1]
        assert path.y_m[0] == path.y_m[-1]
        chords = np.hypot(np.diff(path.x_m), np.diff(path.y_m))
        assert np.diff(path.distance_m) == pytest.approx(chords, abs=1e-10)
        assert np.all(np.isfinite(path.curvature_per_m))
        assert np.min(chords) > 0.0
        headings = np.arctan2(np.diff(path.y_m), np.diff(path.x_m))
        turns = np.arctan2(
            np.sin(np.roll(headings, -1) - headings),
            np.cos(np.roll(headings, -1) - headings),
        )
        assert float(np.sum(turns)) == pytest.approx(2.0 * pi, abs=1e-9)
        assert abs(float(turns[-1])) < 0.2  # finite, smooth closure at this test seam


def test_variable_widths_are_respected_at_every_planner_station() -> None:
    track = _rounded_rectangle()
    narrow = tuple(1.25 if 0.20 < i / track.cell_count < 0.35 else 3.0 for i in range(track.cell_count))
    corridor = TrackCorridor(
        left_width_m=narrow,
        right_width_m=(3.0,) * track.cell_count,
        vehicle_width_m=1.4,
        safety_margin_m=0.2,
        source="synthetic variable widths",
    )
    plan = RacingLinePlanner().plan(track, corridor)
    station = np.arange(len(plan.offset_m)) * track.length_m / len(plan.offset_m)
    source_cell = np.searchsorted(track.distance_m, station, side="right") - 1
    upper = np.asarray(corridor.left_width_m)[source_cell] - 0.9
    lower = 0.9 - np.asarray(corridor.right_width_m)[source_cell]
    assert np.all(np.asarray(plan.offset_m) <= upper + 1e-6)
    assert np.all(np.asarray(plan.offset_m) >= lower - 1e-6)


def test_narrow_source_cell_between_planner_samples_is_not_skipped() -> None:
    track = _rounded_rectangle()
    left = [3.0] * track.cell_count
    right = [3.0] * track.cell_count
    narrow_cell = 236
    left[narrow_cell] = right[narrow_cell] = 0.91
    corridor = TrackCorridor(
        left_width_m=tuple(left),
        right_width_m=tuple(right),
        vehicle_width_m=1.4,
        safety_margin_m=0.2,
        source="synthetic narrow source cell",
    )
    plan = RacingLinePlanner().plan(track, corridor)
    assert abs(plan.source_cell_center_offset_m[narrow_cell]) <= 0.01 + 1e-6
    assert plan.max_constraint_violation_m <= 1e-6


def test_exact_cubic_extrema_check_matches_dense_independent_samples() -> None:
    stations = np.asarray([0.0, 0.7, 1.1, 1.8, 2.0])
    corridor = TrackCorridor(
        left_width_m=(1.2, 1.0, 1.5, 1.1),
        right_width_m=(1.3, 1.4, 1.1, 1.2),
        vehicle_width_m=1.0,
        safety_margin_m=0.1,
        source="analytic-extrema unit test",
    )
    controls = np.asarray([0.9, -0.8, 1.1, -1.0, 0.7, -0.6, 1.2, -0.9])
    exact = _continuous_offset_violation(controls, stations, corridor, 0.6)
    dense_stations = np.linspace(0.0, 2.0, 40_001)[:-1]
    dense_offset = _periodic_cubic_basis_at(dense_stations, 2.0, len(controls)) @ controls
    cell = np.searchsorted(stations, dense_stations, side="right") - 1
    sampled = max(
        0.0,
        float(np.max(0.6 - np.asarray(corridor.right_width_m)[cell] - dense_offset)),
        float(np.max(dense_offset - np.asarray(corridor.left_width_m)[cell] + 0.6)),
    )
    assert exact >= sampled - 1e-8
    assert exact == pytest.approx(sampled, abs=1e-3)


def test_planner_is_deterministic_and_bounded() -> None:
    track = _rounded_rectangle()
    planner = RacingLinePlanner(maximum_iterations=20)
    first = planner.plan(track, _corridor(track))
    second = planner.plan(track, _corridor(track))
    assert first.offset_m == second.offset_m
    assert first.candidate_track == second.candidate_track
    assert first.iterations <= 20
    assert first.objective_evaluations <= (20 + 1) * (24 + 1) * 2


def test_crossing_and_collinear_self_touch_are_rejected() -> None:
    assert _has_nonadjacent_segment_intersection(
        np.asarray([0.0, 2.0, 0.0, 2.0]),
        np.asarray([0.0, 2.0, 2.0, 0.0]),
    )
    assert not _has_nonadjacent_segment_intersection(
        np.asarray([0.0, 2.0, 2.0, 0.0]),
        np.asarray([0.0, 0.0, 2.0, 2.0]),
    )


def test_curvature_is_derived_from_xy_not_copied_from_source_channel() -> None:
    radius = 20.0
    count = 80
    angle = np.linspace(0.0, 2.0 * pi, count + 1)
    x = radius * np.cos(angle)
    y = radius * np.sin(angle)
    chord = np.hypot(np.diff(x), np.diff(y))
    track = SpatialTrack(
        distance_m=tuple(np.r_[0.0, np.cumsum(chord)]),
        x_m=tuple(x),
        y_m=tuple(y),
        curvature_per_m=(0.0,) * count,
    )
    plan = RacingLinePlanner(length_penalty=1.0).plan(track, _corridor(track))
    assert np.mean(plan.baseline_track.curvature_per_m) == pytest.approx(1.0 / radius, rel=0.03)
    assert plan.baseline_track.curvature_per_m != track.curvature_per_m


def test_full_lap_model_can_select_faster_candidate_on_synthetic_course() -> None:
    track = _rounded_rectangle()
    plan = RacingLinePlanner().plan(track, _corridor(track))
    comparison = compare_lines_with_lap_model(
        make_prius_benchmark(VehicleSetup()),
        plan,
        torque_request_fraction=0.8,
    )
    assert comparison.baseline_error is None
    assert comparison.candidate_error is None
    assert comparison.baseline_time_s is not None
    assert comparison.candidate_time_s is not None
    assert comparison.candidate_time_s < comparison.baseline_time_s
    assert comparison.selected_mode == "candidate"
    assert comparison.selected_track is plan.candidate_track
    assert comparison.selected_run is comparison.candidate_run
    assert comparison.compute_time_s > 0.0


@pytest.fixture(scope="module")
def _adaptive_plan():
    track = _rounded_rectangle()
    plan = RacingLinePlanner().plan(track, _corridor(track))
    assert plan.status == "candidate"
    return plan


def test_half_strength_path_rebuilds_geometry_inside_valid_endpoints(_adaptive_plan) -> None:
    plan = _adaptive_plan
    half = _scaled_candidate_track(plan, 0.5)
    base_x = np.asarray(plan.baseline_track.x_m)
    base_y = np.asarray(plan.baseline_track.y_m)
    full_x = np.asarray(plan.candidate_track.x_m)
    full_y = np.asarray(plan.candidate_track.y_m)
    assert half.x_m == pytest.approx(0.5 * (base_x + full_x))
    assert half.y_m == pytest.approx(0.5 * (base_y + full_y))
    assert np.diff(half.distance_m) == pytest.approx(
        np.hypot(np.diff(half.x_m), np.diff(half.y_m)), abs=1e-10,
    )
    assert not _has_nonadjacent_segment_intersection(
        np.asarray(half.x_m[:-1]), np.asarray(half.y_m[:-1]),
    )
    with pytest.raises(ValueError, match="between zero and one"):
        _scaled_candidate_track(plan, 1.0)


def test_vehicle_model_selects_half_strength_if_full_line_is_slower(
    _adaptive_plan, monkeypatch,
) -> None:
    plan = _adaptive_plan
    calls = []

    def fake_lap(vehicle, track, *, torque_request_fraction):
        assert torque_request_fraction == 0.7
        calls.append(track)
        time_s = 100.0 if track is plan.baseline_track else (
            102.0 if track is plan.candidate_track else 98.0
        )
        return SimpleNamespace(completed=True, driving_time_s=time_s, failure_reason=None)

    monkeypatch.setattr("lapsim.ui.simulation.run_one_lap", fake_lap)
    comparison = compare_lines_with_lap_model(
        {"vehicle": "test"}, plan, torque_request_fraction=0.7,
    )
    assert len(calls) == 3
    assert comparison.baseline_time_s == 100.0
    assert comparison.candidate_time_s == 98.0
    assert comparison.candidate_strength == 0.5
    assert tuple(trial.strength for trial in comparison.trials) == (1.0, 0.5)
    assert tuple(trial.lap_time_s for trial in comparison.trials) == (102.0, 98.0)
    assert comparison.candidate_track is calls[2]
    assert comparison.selected_mode == "candidate"
    assert comparison.selected_track is calls[2]
    assert comparison.selected_run is comparison.candidate_run


def test_full_strength_win_skips_extra_lap(_adaptive_plan, monkeypatch) -> None:
    plan = _adaptive_plan
    calls = []

    def fake_lap(vehicle, track, *, torque_request_fraction):
        calls.append(track)
        time_s = 100.0 if track is plan.baseline_track else 99.0
        return SimpleNamespace(completed=True, driving_time_s=time_s, failure_reason=None)

    monkeypatch.setattr("lapsim.ui.simulation.run_one_lap", fake_lap)
    comparison = compare_lines_with_lap_model(object(), plan, torque_request_fraction=0.7)
    assert calls == [plan.baseline_track, plan.candidate_track]
    assert comparison.candidate_strength == 1.0
    assert comparison.candidate_track is plan.candidate_track
    assert len(comparison.trials) == 1


def test_no_geometric_candidate_runs_only_baseline(_adaptive_plan, monkeypatch) -> None:
    plan = replace(
        _adaptive_plan,
        status="centerline",
        candidate_track=_adaptive_plan.baseline_track,
    )
    calls = []

    def fake_lap(vehicle, track, *, torque_request_fraction):
        calls.append(track)
        return SimpleNamespace(completed=True, driving_time_s=100.0, failure_reason=None)

    monkeypatch.setattr("lapsim.ui.simulation.run_one_lap", fake_lap)
    comparison = compare_lines_with_lap_model(object(), plan, torque_request_fraction=0.7)
    assert calls == [plan.baseline_track]
    assert comparison.trials == ()
    assert comparison.candidate_strength is None
    assert comparison.candidate_time_s is None
    assert comparison.selected_mode == "centerline"


def test_half_strength_can_recover_from_failed_full_lap(_adaptive_plan, monkeypatch) -> None:
    plan = _adaptive_plan

    def fake_lap(vehicle, track, *, torque_request_fraction):
        if track is plan.candidate_track:
            return SimpleNamespace(completed=False, driving_time_s=0.0, failure_reason="stalled")
        time_s = 100.0 if track is plan.baseline_track else 99.0
        return SimpleNamespace(completed=True, driving_time_s=time_s, failure_reason=None)

    monkeypatch.setattr("lapsim.ui.simulation.run_one_lap", fake_lap)
    comparison = compare_lines_with_lap_model(object(), plan, torque_request_fraction=0.7)
    assert comparison.candidate_strength == 0.5
    assert comparison.candidate_time_s == 99.0
    assert comparison.candidate_error is None
    assert comparison.trials[0].error == "stalled"
    assert comparison.trials[1].lap_time_s == 99.0


def test_failed_trials_have_no_fictitious_time(_adaptive_plan, monkeypatch) -> None:
    plan = _adaptive_plan

    def fake_lap(vehicle, track, *, torque_request_fraction):
        return SimpleNamespace(completed=False, driving_time_s=0.0, failure_reason="stalled")

    monkeypatch.setattr("lapsim.ui.simulation.run_one_lap", fake_lap)
    comparison = compare_lines_with_lap_model(object(), plan, torque_request_fraction=0.7)
    assert comparison.baseline_time_s is None
    assert comparison.candidate_time_s is None
    assert comparison.candidate_strength is None
    assert comparison.selected_mode == "centerline"
    assert comparison.selected_run is None
    assert comparison.candidate_run is not None
    assert len(comparison.trials) == 2
    assert "1x: stalled" in comparison.candidate_error
    assert "0.5x: stalled" in comparison.candidate_error
