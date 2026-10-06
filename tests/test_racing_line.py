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
    _corridor_bounds_at,
    _audit_curvature_path,
    _has_nonadjacent_segment_intersection,
    _periodic_cubic_basis_at,
    _scaled_candidate_track,
    compare_lines_with_lap_model,
)
from lapsim.profiles import build_vehicle, list_profiles
from lapsim.ui.presets import VehicleSetup, make_prius_benchmark
from lapsim.ui.simulation import load_team_endurance_track, run_speed_periodic_lap


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


def test_closed_course_seam_uses_narrower_first_and_last_cell() -> None:
    corridor = TrackCorridor(
        left_width_m=(1.2, 3.0, 4.0),
        right_width_m=(1.4, 3.0, 4.0),
        vehicle_width_m=1.0,
        source="variable-width seam check",
    )
    lower, upper = _corridor_bounds_at(
        np.asarray((0.0, 3.0)), np.asarray((0.0, 1.0, 2.0, 3.0)),
        corridor, 0.5,
    )
    assert lower == pytest.approx((-0.9, -0.9))
    assert upper == pytest.approx((0.7, 0.7))


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
        assert float(np.dot(path.curvature_per_m, chords)) == pytest.approx(
            float(np.sum(turns)), abs=1e-9
        )
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
    assert max(plan.baseline_track.curvature_per_m) - min(plan.baseline_track.curvature_per_m) < 0.001
    assert float(np.dot(
        plan.baseline_track.curvature_per_m,
        np.diff(plan.baseline_track.distance_m),
    )) == pytest.approx(2.0 * pi, abs=1e-9)
    assert plan.baseline_track.curvature_per_m != track.curvature_per_m


def test_normal_offset_corridor_that_folds_inside_circle_is_rejected() -> None:
    radius = 5.0
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
    with pytest.raises(ValueError, match="folds in normal coordinates"):
        RacingLinePlanner().plan(
            track,
            TrackCorridor.constant(
                track,
                left_width_m=8.0,
                right_width_m=8.0,
                vehicle_width_m=1.4,
                safety_margin_m=0.2,
                source="oversized synthetic corridor",
            ),
        )


def test_unsampled_wide_source_cell_still_triggers_fold_guard() -> None:
    radius = 5.0
    count = 400
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
    planner_stations = np.arange(96) * track.length_m / 96
    wide_cell = next(
        i for i in range(1, count)
        if not np.any(
            (planner_stations >= track.distance_m[i])
            & (planner_stations < track.distance_m[i + 1])
        )
    )
    left = [2.0] * count
    right = [2.0] * count
    left[wide_cell] = right[wide_cell] = 8.0
    with pytest.raises(ValueError, match="folds in normal coordinates"):
        RacingLinePlanner().plan(
            track,
            TrackCorridor(
                left_width_m=tuple(left),
                right_width_m=tuple(right),
                vehicle_width_m=1.4,
                safety_margin_m=0.2,
                source="single wide source cell",
            ),
        )


def test_full_lap_model_can_select_faster_candidate_on_synthetic_course() -> None:
    track = _rounded_rectangle()
    plan = RacingLinePlanner().plan(track, _corridor(track))
    progress = []
    comparison = compare_lines_with_lap_model(
        make_prius_benchmark(VehicleSetup()),
        plan,
        torque_request_fraction=0.8,
        progress_callback=lambda phase, active_track, snapshot: progress.append(
            (phase, active_track, snapshot)
        ),
    )
    assert comparison.baseline_error is None
    assert comparison.candidate_error is None
    assert comparison.baseline_time_s is not None
    assert comparison.candidate_time_s is not None
    assert comparison.candidate_time_s < comparison.baseline_time_s
    assert comparison.selected_mode == "candidate"
    assert comparison.candidate_strength == 0.95
    assert comparison.selected_track is comparison.candidate_track
    assert comparison.selected_run is comparison.candidate_run
    assert comparison.compute_time_s > 0.0
    assert comparison.baseline_path_audit is not None
    assert comparison.baseline_path_audit.valid
    assert comparison.trials[0].path_audit is not None
    assert not comparison.trials[0].path_audit.valid
    assert comparison.trials[0].diagnostic_lap_time_s is None
    assert comparison.trials[0].run is None
    assert "Model run skipped" in comparison.trials[0].error
    assert comparison.trials[0].lap_time_s is None
    assert comparison.trials[0].path_audit.maximum_corridor_excess_m > 0.03
    assert all(phase != "full" for phase, _track, _snapshot in progress)
    assert comparison.trials[1].path_audit is not None
    assert comparison.trials[1].path_audit.valid
    assert comparison.trials[2].path_audit is not None
    assert comparison.trials[2].path_audit.valid
    assert comparison.trials[2].path_audit.minimum_corridor_slack_m >= 0.02
    assert comparison.trials[2].lap_time_s < comparison.trials[1].lap_time_s
    for phase, active_track, run in (
        ("baseline", plan.baseline_track, comparison.baseline_run),
        ("adaptive", comparison.candidate_track, comparison.candidate_run),
    ):
        phase_events = [
            snapshot for observed_phase, observed_track, snapshot in progress
            if observed_phase == phase and observed_track is active_track
        ]
        assert len(phase_events) == active_track.cell_count
        assert [item.cell_index for item in phase_events] == list(range(active_track.cell_count))
        assert phase_events[-1].lap_station_m == pytest.approx(active_track.length_m)
        assert phase_events[-1].elapsed_time_s == pytest.approx(run.driving_time_s)


def test_speed_periodic_prius_selects_stronger_feasible_path() -> None:
    track = _rounded_rectangle()
    corridor = TrackCorridor.constant(
        track, left_width_m=3.0, right_width_m=3.0,
        vehicle_width_m=1.8, safety_margin_m=0.2,
        source="assumed synthetic default-width scenario",
    )
    plan = RacingLinePlanner().plan(track, corridor)
    comparison = compare_lines_with_lap_model(
        make_prius_benchmark(VehicleSetup(tire_mu=0.95)), plan,
        torque_request_fraction=0.8, speed_periodic=True,
    )

    assert comparison.rank_status == "candidate_selected"
    assert comparison.baseline_time_s is not None
    assert comparison.candidate_strength == 0.95
    assert comparison.candidate_time_s is not None
    assert comparison.candidate_time_s < comparison.trials[1].lap_time_s
    assert comparison.candidate_time_s < comparison.baseline_time_s
    assert comparison.selected_track is comparison.candidate_track
    assert comparison.selected_run is comparison.candidate_run
    assert tuple(trial.strength for trial in comparison.trials) == (1.0, 0.5, 0.95)
    assert comparison.trials[0].lap_time_s is None
    assert comparison.trials[0].diagnostic_lap_time_s is None
    assert comparison.trials[0].run is None
    assert "Model run skipped" in comparison.trials[0].error
    assert comparison.trials[0].path_audit is not None
    assert not comparison.trials[0].path_audit.valid
    assert comparison.trials[2].path_audit is comparison.candidate_path_audit
    assert comparison.trials[2].path_audit.valid
    assert comparison.trials[2].path_audit.minimum_corridor_slack_m > 0.02
    assert comparison.trials[2].path_audit.minimum_corridor_slack_m < 0.06
    assert comparison.candidate_time_s == pytest.approx(14.556611, abs=0.002)
    near_boundary_audit = _audit_curvature_path(
        _scaled_candidate_track(plan, 0.975), plan.baseline_track,
        plan.source_station_m, corridor,
    )
    assert near_boundary_audit.valid
    assert near_boundary_audit.minimum_corridor_slack_m < 0.02

    # A fixed, on-demand 1 m grid check does not rerun the geometry planner.
    # It only asks whether the observed gain over the old 0.75 fallback is
    # larger than a minor cell-size effect; eligibility was audited above on
    # the actual generated paths.
    old_fallback = _scaled_candidate_track(plan, 0.75)
    vehicle = make_prius_benchmark(VehicleSetup(tire_mu=0.95))
    refined_selected = run_speed_periodic_lap(
        vehicle, comparison.candidate_track.refine(1.0),
        torque_request_fraction=0.8,
    )
    refined_fallback = run_speed_periodic_lap(
        vehicle, old_fallback.refine(1.0),
        torque_request_fraction=0.8,
    )
    assert refined_selected.converged
    assert refined_fallback.converged
    assert refined_fallback.run.driving_time_s - refined_selected.run.driving_time_s > 0.3


def test_optional_ai_mode_can_evaluate_every_available_car_profile() -> None:
    """The shared planner must accept every runnable car without special cases."""

    track = _rounded_rectangle()
    corridor = TrackCorridor.constant(
        track, left_width_m=3.0, right_width_m=3.0,
        vehicle_width_m=1.8, safety_margin_m=0.2,
        source="assumed synthetic cross-profile corridor",
    )
    plan = RacingLinePlanner().plan(track, corridor)
    assert plan.status == "candidate"
    for info in list_profiles():
        vehicle, _ = build_vehicle(info.profile_id)
        comparison = compare_lines_with_lap_model(
            vehicle, plan, torque_request_fraction=0.8, speed_periodic=True,
        )
        assert comparison.baseline_run is not None, info.profile_id
        assert comparison.baseline_run.completed, info.profile_id
        assert comparison.baseline_time_s is not None, info.profile_id
        assert comparison.baseline_path_audit is not None, info.profile_id
        assert comparison.baseline_path_audit.valid, info.profile_id
        assert comparison.candidate_run is not None, info.profile_id
        assert comparison.candidate_run.completed, info.profile_id
        assert comparison.candidate_time_s is not None, info.profile_id
        assert comparison.candidate_path_audit is not None, info.profile_id
        assert comparison.candidate_path_audit.valid, info.profile_id


def test_curvature_arc_audit_rejects_chord_based_square_with_small_clearance() -> None:
    side_m = 10.0
    square = SpatialTrack(
        distance_m=(0.0, 10.0, 20.0, 30.0, 40.0),
        x_m=(0.0, 10.0, 10.0, 0.0, 0.0),
        y_m=(0.0, 0.0, 10.0, 10.0, 0.0),
        curvature_per_m=(pi / (2.0 * side_m),) * 4,
    )
    corridor = TrackCorridor.constant(
        square, left_width_m=1.0, right_width_m=1.0,
        vehicle_width_m=0.5, safety_margin_m=0.1,
        source="synthetic square clearance",
    )
    audit = _audit_curvature_path(square, square, square.distance_m, corridor)
    assert not audit.valid
    assert audit.sample_count == 17  # quarter cells plus the start/seam sample
    assert audit.maximum_corridor_excess_m > 0.05
    assert audit.allowed_numerical_excess_m == 1e-8
    # Equal turns close heading and position on this symmetric path, but the
    # intermediate arc endpoints do not coincide with polygon vertices.
    assert audit.seam_position_error_m < 1e-10


def test_curvature_arc_audit_uses_exact_heading_for_coherent_arc_cells() -> None:
    track = _rounded_rectangle()
    audit = _audit_curvature_path(
        track, track, track.distance_m, _corridor(track),
    )
    assert audit.initial_heading_policy == "coherent_first_arc_chord"
    assert audit.seam_position_error_m < 1e-8
    assert audit.maximum_corridor_excess_m == 0.0
    assert audit.valid


def test_modeled_arc_audit_samples_a_narrow_source_cell_between_quarters() -> None:
    angles = np.linspace(0.0, 2.0 * pi, 81)

    def circle(radius_m: float) -> SpatialTrack:
        x = radius_m * np.cos(angles)
        y = radius_m * np.sin(angles)
        chords = np.hypot(np.diff(x), np.diff(y))
        stations = np.r_[0.0, np.cumsum(chords)]
        return SpatialTrack(
            distance_m=tuple(stations), x_m=tuple(x), y_m=tuple(y),
            curvature_per_m=(2.0 * pi / stations[-1],) * 80,
            closed=True,
        )

    reference = circle(6.0)
    shifted = circle(7.5)
    # The tight 1 cm source cell lies wholly between the old quarter-cell
    # samples; source boundary and midpoint samples must still catch it.
    assert reference.length_m / (4 * shifted.cell_count) > 0.07
    source_stations = (0.0, 0.06, 0.07, reference.length_m)
    wide = TrackCorridor(
        left_width_m=(3.0,) * 3, right_width_m=(3.0,) * 3,
        vehicle_width_m=1.0, source="synthetic wide clearance",
    )
    narrow = TrackCorridor(
        left_width_m=(3.0, 1.6, 3.0),
        right_width_m=(3.0, 1.6, 3.0),
        vehicle_width_m=1.0, source="synthetic narrow source cell",
    )
    assert _audit_curvature_path(shifted, reference, source_stations, wide).valid
    audit = _audit_curvature_path(shifted, reference, source_stations, narrow)
    assert not audit.valid
    assert audit.maximum_corridor_excess_m > 0.4
    assert audit.seam_position_error_m < 1e-9


def test_shipped_assumed_corridor_marks_both_paths_diagnostic(
    monkeypatch,
) -> None:
    track = load_team_endurance_track()
    corridor = TrackCorridor.constant(
        track, left_width_m=2.0, right_width_m=2.0,
        vehicle_width_m=1.78308, safety_margin_m=0.3,
        source="synthetic assumed Prius clearance",
    )
    plan = RacingLinePlanner().plan(track, corridor)
    assert plan.status == "candidate"

    def fake_lap(vehicle, active_track, *, torque_request_fraction):
        del vehicle, torque_request_fraction
        time_s = 100.0 if active_track is plan.baseline_track else (
            99.0 if active_track is plan.candidate_track else 98.0
        )
        return SimpleNamespace(
            completed=True, driving_time_s=time_s, failure_reason=None,
        )

    monkeypatch.setattr("lapsim.ui.simulation.run_one_lap", fake_lap)
    comparison = compare_lines_with_lap_model(
        object(), plan, torque_request_fraction=0.8,
    )
    assert comparison.rank_status == "invalid_processed_baseline"
    assert comparison.baseline_path_audit is not None
    assert comparison.baseline_path_audit.maximum_corridor_excess_m > 0.09
    assert comparison.baseline_time_s is None
    assert comparison.baseline_diagnostic_time_s == 100.0
    assert comparison.baseline_run is not None
    assert comparison.candidate_time_s is None
    assert comparison.candidate_diagnostic_time_s == 98.0
    assert comparison.candidate_run is not None
    assert comparison.selected_mode == "centerline"
    assert comparison.selected_run is None
    assert all(trial.lap_time_s is None for trial in comparison.trials)
    assert tuple(trial.diagnostic_lap_time_s for trial in comparison.trials) == (
        99.0, 98.0, 98.0,
    )
    assert all(trial.path_audit is not None for trial in comparison.trials)
    assert all(not trial.path_audit.valid for trial in comparison.trials)
    wide_corridor = TrackCorridor.constant(
        track, left_width_m=4.0, right_width_m=4.0,
        vehicle_width_m=1.78308, safety_margin_m=0.3,
        source="wide synthetic closure check",
    )
    seam_only = _audit_curvature_path(
        plan.baseline_track, plan.baseline_track,
        track.distance_m, wide_corridor,
    )
    assert seam_only.maximum_corridor_excess_m == 0.0
    assert seam_only.seam_position_error_m > 0.7
    assert seam_only.allowed_seam_position_error_m == 0.01
    assert not seam_only.valid


def test_missing_corridor_audit_cannot_select_candidate(
    _adaptive_plan, monkeypatch,
) -> None:
    plan = replace(_adaptive_plan, corridor=None, source_station_m=None)

    def fake_lap(vehicle, track, *, torque_request_fraction):
        del vehicle, torque_request_fraction
        return SimpleNamespace(
            completed=True,
            driving_time_s=(100.0 if track is plan.baseline_track else 90.0),
            failure_reason=None,
        )

    monkeypatch.setattr("lapsim.ui.simulation.run_one_lap", fake_lap)
    comparison = compare_lines_with_lap_model(
        object(), plan, torque_request_fraction=0.7,
    )
    assert comparison.rank_status == "path_audit_unavailable"
    assert comparison.baseline_time_s is None
    assert comparison.candidate_time_s is None
    assert comparison.baseline_diagnostic_time_s == 100.0
    assert comparison.candidate_diagnostic_time_s == 90.0
    assert comparison.selected_run is None
    assert "audit unavailable" in comparison.baseline_error


@pytest.fixture(scope="module")
def _adaptive_plan():
    track = _rounded_rectangle()
    plan = RacingLinePlanner().plan(track, _corridor(track))
    assert plan.status == "candidate"
    # These timing-policy tests need a clearance that also contains the
    # full-strength *integrated* arc, not only the proposed polygon vertices.
    comparison_corridor = TrackCorridor.constant(
        track, left_width_m=3.1, right_width_m=3.1,
        vehicle_width_m=1.4, safety_margin_m=0.2,
        source="synthetic comparison clearance",
    )
    return replace(
        plan, corridor=comparison_corridor,
        corridor_source=comparison_corridor.source,
    )


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
    assert len(calls) == 4
    assert comparison.baseline_time_s == 100.0
    assert comparison.candidate_time_s == 98.0
    assert comparison.candidate_strength == 0.5
    assert tuple(trial.strength for trial in comparison.trials) == (1.0, 0.5, 0.375)
    assert tuple(trial.lap_time_s for trial in comparison.trials) == (102.0, 98.0, 98.0)
    assert comparison.candidate_track is calls[2]
    assert comparison.selected_mode == "candidate"
    assert comparison.selected_track is calls[2]
    assert comparison.selected_run is comparison.candidate_run


def test_fourth_strength_adapts_to_car_times_with_four_path_budget(
    _adaptive_plan, monkeypatch,
) -> None:
    plan = _adaptive_plan
    baseline_xy = np.r_[plan.baseline_track.x_m, plan.baseline_track.y_m]
    full_offset_xy = np.r_[plan.candidate_track.x_m, plan.candidate_track.y_m] - baseline_xy
    full_offset_norm2 = float(np.dot(full_offset_xy, full_offset_xy))
    calls = []

    def strength_of(track):
        if track is plan.baseline_track:
            return 0.0
        if track is plan.candidate_track:
            return 1.0
        offset_xy = np.r_[track.x_m, track.y_m] - baseline_xy
        return float(np.dot(offset_xy, full_offset_xy) / full_offset_norm2)

    def fake_periodic(vehicle, track, **kwargs):
        strength = strength_of(track)
        calls.append((vehicle.optimum, strength, kwargs["maximum_lap_passes"]))
        if "progress_callback" in kwargs:
            kwargs["progress_callback"](object())
        run = SimpleNamespace(
            completed=True,
            driving_time_s=100.0 + 8.0 * (strength - vehicle.optimum) ** 2,
            failure_reason=None,
        )
        return SimpleNamespace(run=run, converged=True, failure_reason=None)

    monkeypatch.setattr("lapsim.ui.simulation.run_speed_periodic_lap", fake_periodic)
    for optimum, expected_fourth in ((0.3, 0.25), (0.65, 0.625)):
        phases = []
        comparison = compare_lines_with_lap_model(
            SimpleNamespace(optimum=optimum), plan,
            torque_request_fraction=0.7, speed_periodic=True,
            progress_callback=lambda phase, track, snapshot: phases.append(phase),
        )
        car_calls = [item for item in calls if item[0] == optimum]
        assert len(car_calls) == 4
        assert [item[1] for item in car_calls] == pytest.approx(
            (0.0, 1.0, 0.5, expected_fourth)
        )
        assert all(item[2] == 2 for item in car_calls)
        assert phases == ["baseline", "full", "half", "adaptive"]
        assert tuple(trial.strength for trial in comparison.trials) == (
            1.0, 0.5, expected_fourth,
        )
        assert comparison.trials[2].path_audit is not None
        assert comparison.trials[2].path_audit.valid
        assert comparison.candidate_strength == expected_fourth
        assert comparison.candidate_time_s < comparison.trials[1].lap_time_s
        assert comparison.selected_run is comparison.candidate_run
    assert len(calls) == 8  # four paths per car, at most two full-model passes each


def test_full_strength_win_is_retained_after_interior_trials(_adaptive_plan, monkeypatch) -> None:
    plan = _adaptive_plan
    calls = []

    def fake_lap(vehicle, track, *, torque_request_fraction):
        calls.append(track)
        time_s = 100.0 if track is plan.baseline_track else (
            99.0 if track is plan.candidate_track else 99.5
        )
        return SimpleNamespace(completed=True, driving_time_s=time_s, failure_reason=None)

    monkeypatch.setattr("lapsim.ui.simulation.run_one_lap", fake_lap)
    comparison = compare_lines_with_lap_model(object(), plan, torque_request_fraction=0.7)
    assert calls[:2] == [plan.baseline_track, plan.candidate_track]
    assert len(calls) == 4
    assert comparison.candidate_strength == 1.0
    assert comparison.candidate_track is plan.candidate_track
    assert tuple(trial.lap_time_s for trial in comparison.trials) == (99.0, 99.5, 99.5)


@pytest.mark.parametrize(
    ("candidate_time_s", "rank_status", "selected_mode"),
    [
        (100.0, "candidate_not_faster", "centerline"),
        (99.991, "unresolved_close_gain", "centerline"),
        (99.95, "unresolved_close_gain", "centerline"),
        (99.949, "candidate_selected", "candidate"),
    ],
)
def test_close_candidate_retains_its_result_but_uses_selection_margin(
    _adaptive_plan, monkeypatch, candidate_time_s, rank_status, selected_mode,
) -> None:
    plan = _adaptive_plan

    def fake_lap(vehicle, track, *, torque_request_fraction):
        assert torque_request_fraction == 0.7
        time_s = 100.0 if track is plan.baseline_track else (
            candidate_time_s if track is plan.candidate_track else 101.0
        )
        return SimpleNamespace(completed=True, driving_time_s=time_s, failure_reason=None)

    monkeypatch.setattr("lapsim.ui.simulation.run_one_lap", fake_lap)
    comparison = compare_lines_with_lap_model(
        object(), plan, torque_request_fraction=0.7,
    )

    assert comparison.baseline_time_s == 100.0
    assert comparison.candidate_time_s == candidate_time_s
    assert comparison.candidate_strength == 1.0
    assert comparison.candidate_run is not None
    assert comparison.candidate_track is plan.candidate_track
    assert comparison.selection_margin_s == 0.05
    assert comparison.rank_status == rank_status
    assert comparison.selected_mode == selected_mode
    assert comparison.selected_track is (
        plan.candidate_track if selected_mode == "candidate" else plan.baseline_track
    )


@pytest.mark.parametrize(
    "bad_margin", [-0.001, float("nan"), float("inf"), True, False],
)
def test_selection_margin_must_be_finite_and_nonnegative(
    _adaptive_plan, bad_margin,
) -> None:
    with pytest.raises(ValueError, match="minimum_selection_gain_s"):
        compare_lines_with_lap_model(
            object(), _adaptive_plan, torque_request_fraction=0.7,
            minimum_selection_gain_s=bad_margin,
        )


def test_zero_margin_allows_any_positive_gain(_adaptive_plan, monkeypatch) -> None:
    plan = _adaptive_plan

    def fake_lap(vehicle, track, *, torque_request_fraction):
        time_s = 100.0 if track is plan.baseline_track else (
            99.999 if track is plan.candidate_track else 101.0
        )
        return SimpleNamespace(completed=True, driving_time_s=time_s, failure_reason=None)

    monkeypatch.setattr("lapsim.ui.simulation.run_one_lap", fake_lap)
    comparison = compare_lines_with_lap_model(
        object(), plan, torque_request_fraction=0.7,
        minimum_selection_gain_s=0.0,
    )
    assert comparison.rank_status == "candidate_selected"
    assert comparison.selection_margin_s == 0.0
    assert comparison.selected_mode == "candidate"


def test_opt_in_speed_periodic_comparison_uses_converged_lap_only(
    _adaptive_plan, monkeypatch,
) -> None:
    plan = _adaptive_plan
    calls = []

    def fake_periodic(vehicle, track, **kwargs):
        calls.append((track, kwargs))
        time_s = 100.0 if track is plan.baseline_track else (
            99.0 if track is plan.candidate_track else 98.0
        )
        run = SimpleNamespace(completed=True, driving_time_s=time_s,
                              failure_reason=None)
        return SimpleNamespace(run=run, converged=True, failure_reason=None)

    monkeypatch.setattr("lapsim.ui.simulation.run_speed_periodic_lap", fake_periodic)
    comparison = compare_lines_with_lap_model(
        object(), plan, torque_request_fraction=0.7, speed_periodic=True,
    )

    assert len(calls) == 4
    assert [track for track, _ in calls[:2]] == [
        plan.baseline_track, plan.candidate_track,
    ]
    assert all(options == {
        "torque_request_fraction": 0.7,
        "maximum_lap_passes": 2,
        "speed_tolerance_mps": 0.005,
    } for _, options in calls)
    assert comparison.baseline_time_s == 100.0
    assert comparison.candidate_time_s == 98.0
    assert comparison.candidate_strength == 0.5
    assert comparison.selected_mode == "candidate"


def test_opt_in_speed_periodic_rejects_nonconverged_trials_but_keeps_runs(
    _adaptive_plan, monkeypatch,
) -> None:
    plan = _adaptive_plan
    received = []

    def fake_periodic(vehicle, track, **kwargs):
        del vehicle
        assert kwargs["maximum_lap_passes"] == 2
        snapshot = object()
        kwargs["progress_callback"](snapshot)
        received.append((track, snapshot))
        time_s = 100.0 if track is plan.baseline_track else (
            90.0 if track is plan.candidate_track else 99.0
        )
        run = SimpleNamespace(completed=True, driving_time_s=time_s,
                              failure_reason=None)
        converged = track is not plan.candidate_track
        return SimpleNamespace(
            run=run, converged=converged,
            failure_reason=None if converged else "seam delta +0.050 m/s",
        )

    monkeypatch.setattr("lapsim.ui.simulation.run_speed_periodic_lap", fake_periodic)
    phases = []
    comparison = compare_lines_with_lap_model(
        object(), plan, torque_request_fraction=0.7, speed_periodic=True,
        progress_callback=lambda phase, track, snapshot: phases.append(
            (phase, track, snapshot)
        ),
    )

    assert [phase for phase, _, _ in phases] == [
        "baseline", "full", "half", "three_quarter",
    ]
    assert all(observed_track is emitted_track and observed_snapshot is snapshot
               for (_, observed_track, observed_snapshot), (emitted_track, snapshot)
               in zip(phases, received, strict=True))
    assert comparison.baseline_time_s == 100.0
    assert comparison.trials[0].lap_time_s is None
    assert comparison.trials[0].error == "seam delta +0.050 m/s"
    assert comparison.trials[0].track is plan.candidate_track
    assert comparison.trials[0].run is not None
    assert comparison.candidate_time_s == 99.0
    assert comparison.candidate_strength == 0.5
    assert comparison.selected_mode == "candidate"


def test_faster_adaptive_run_needs_speed_seam_convergence(
    _adaptive_plan, monkeypatch,
) -> None:
    calls = []
    runs = []

    def fake_periodic(vehicle, track, **kwargs):
        del vehicle, kwargs
        calls.append(track)
        time_s = (100.0, 99.0, 98.0, 90.0)[len(calls) - 1]
        run = SimpleNamespace(
            completed=True, driving_time_s=time_s, failure_reason=None,
        )
        runs.append(run)
        converged = len(calls) < 4
        return SimpleNamespace(
            run=run, converged=converged,
            failure_reason=None if converged else "adaptive seam not periodic",
        )

    monkeypatch.setattr("lapsim.ui.simulation.run_speed_periodic_lap", fake_periodic)
    comparison = compare_lines_with_lap_model(
        object(), _adaptive_plan, torque_request_fraction=0.7,
        speed_periodic=True,
    )

    assert len(calls) == 4
    assert comparison.trials[2].lap_time_s is None
    assert comparison.trials[2].diagnostic_lap_time_s == 90.0
    assert comparison.trials[2].error == "adaptive seam not periodic"
    assert comparison.candidate_strength == 0.5
    assert comparison.candidate_time_s == 98.0
    assert comparison.candidate_track is calls[2]
    assert comparison.candidate_run is runs[2]
    assert comparison.selected_run is runs[2]
    assert all(
        trial.track is calls[index] and trial.run is runs[index]
        for index, trial in enumerate(comparison.trials, start=1)
    )


def test_opt_in_speed_periodic_requires_converged_baseline_for_selection(
    _adaptive_plan, monkeypatch,
) -> None:
    plan = _adaptive_plan

    def fake_periodic(vehicle, track, **kwargs):
        del vehicle, kwargs
        run = SimpleNamespace(completed=True, driving_time_s=95.0,
                              failure_reason=None)
        converged = track is not plan.baseline_track
        return SimpleNamespace(
            run=run, converged=converged,
            failure_reason=None if converged else "baseline seam not periodic",
        )

    monkeypatch.setattr("lapsim.ui.simulation.run_speed_periodic_lap", fake_periodic)
    comparison = compare_lines_with_lap_model(
        object(), plan, torque_request_fraction=0.7, speed_periodic=True,
    )

    assert comparison.baseline_run is not None
    assert comparison.baseline_time_s is None
    assert comparison.baseline_error == "baseline seam not periodic"
    assert comparison.candidate_time_s == 95.0
    assert comparison.selected_mode == "centerline"
    assert comparison.selected_run is None


def test_opt_in_speed_periodic_real_short_path_reports_closed_seam(
    _adaptive_plan,
) -> None:
    plan = replace(
        _adaptive_plan,
        status="centerline",
        candidate_track=_adaptive_plan.baseline_track,
    )
    comparison = compare_lines_with_lap_model(
        make_prius_benchmark(VehicleSetup()), plan,
        torque_request_fraction=0.8, speed_periodic=True,
    )

    assert comparison.baseline_error is None
    assert comparison.baseline_time_s is not None
    assert comparison.baseline_run is comparison.selected_run
    assert comparison.baseline_run.seam_speed_delta_mps is not None
    assert abs(comparison.baseline_run.seam_speed_delta_mps) <= 0.005
    assert comparison.trials == ()


def test_half_trial_can_improve_even_when_full_beats_baseline(
    _adaptive_plan, monkeypatch,
) -> None:
    plan = _adaptive_plan
    calls = []

    def fake_lap(vehicle, track, *, torque_request_fraction):
        calls.append(track)
        time_s = 100.0 if track is plan.baseline_track else (
            99.0 if track is plan.candidate_track else 98.5
        )
        return SimpleNamespace(completed=True, driving_time_s=time_s, failure_reason=None)

    monkeypatch.setattr("lapsim.ui.simulation.run_one_lap", fake_lap)
    comparison = compare_lines_with_lap_model(object(), plan, torque_request_fraction=0.7)
    assert len(calls) == 4
    assert comparison.candidate_strength == 0.5
    assert comparison.candidate_time_s == 98.5
    assert comparison.selected_track is calls[2]
    assert tuple(trial.lap_time_s for trial in comparison.trials) == (99.0, 98.5, 98.5)


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
    calls = []
    runs = []

    def fake_lap(vehicle, track, *, torque_request_fraction):
        calls.append(track)
        run = SimpleNamespace(completed=False, driving_time_s=0.0, failure_reason="stalled")
        runs.append(run)
        return run

    monkeypatch.setattr("lapsim.ui.simulation.run_one_lap", fake_lap)
    comparison = compare_lines_with_lap_model(object(), plan, torque_request_fraction=0.7)
    assert comparison.baseline_time_s is None
    assert comparison.candidate_time_s is None
    assert comparison.candidate_strength == 1.0
    assert comparison.selected_mode == "centerline"
    assert comparison.selected_run is None
    assert comparison.candidate_run is not None
    assert len(comparison.trials) == 3
    assert all(
        trial.track is calls[index] and trial.run is runs[index]
        for index, trial in enumerate(comparison.trials, start=1)
    )
    assert "1x: stalled" in comparison.candidate_error
    assert "0.5x: stalled" in comparison.candidate_error
    assert "0.75x: stalled" in comparison.candidate_error


def test_progress_callback_identifies_phase_and_exact_trial_track(
    _adaptive_plan, monkeypatch,
) -> None:
    plan = _adaptive_plan
    emitted = []
    received = []

    def fake_lap(vehicle, track, *, torque_request_fraction, progress_callback):
        snapshot = object()
        emitted.append((track, snapshot))
        progress_callback(snapshot)
        time_s = 100.0 if track is plan.baseline_track else (
            102.0 if track is plan.candidate_track else 98.0
        )
        return SimpleNamespace(completed=True, driving_time_s=time_s, failure_reason=None)

    monkeypatch.setattr("lapsim.ui.simulation.run_one_lap", fake_lap)
    comparison = compare_lines_with_lap_model(
        object(), plan, torque_request_fraction=0.7,
        progress_callback=lambda phase, track, snapshot: received.append((phase, track, snapshot)),
    )
    assert tuple(phase for phase, _, _ in received) == (
        "baseline", "full", "half", "adaptive",
    )
    for (track, snapshot), (_, callback_track, callback_snapshot) in zip(
        emitted, received, strict=True,
    ):
        assert callback_track is track
        assert callback_snapshot is snapshot
    assert comparison.selected_track is emitted[2][0]
