"""Ordered skidpad geometry/timing contracts and one ordinary numerical smoke.

Synthetic telemetry fixtures test bookkeeping only. The numerical smoke uses
the actual prescribed-path Vehicle model, not a native/portable torque worker.
"""

from dataclasses import replace
from math import fsum, pi
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from lapsim import ConstantControlsProfile, Controls
from lapsim.core.telemetry import Telemetry
from lapsim.courses.spatial_track import SpatialTrack
from lapsim.events.skidpad_sequence import (
    CIRCLE_CENTRE_SEPARATION_M,
    INNER_DIAMETER_M,
    LANE_WIDTH_M,
    NOMINAL_PATH_RADIUS_M,
    OUTER_DIAMETER_M,
    SkidpadSequenceConfig,
    simulate_skidpad_sequence,
    standard_skidpad_sequence,
)
from vehicle_model import Vehicle


def _course(step=2.0):
    return standard_skidpad_sequence(
        entry_length_m=2.0, exit_length_m=3.0, maximum_cell_length_m=step,
    )


def _profile():
    return ConstantControlsProfile(Controls(motor_torque_request_nm=5.0))


def _run_fixture(course, phase_durations=(1.0, 2.0, 4.0, 6.0, 8.0, 10.0), *, completed=True, samples=None):
    """Deliberately synthetic per-cell telemetry, never a qualified receipt."""

    times = []
    now = 0.0
    for phase, duration in zip(course.phases, phase_durations, strict=True):
        start = now
        cells = phase.end_cell - phase.first_cell
        times.extend(start + duration * index / cells for index in range(1, cells + 1))
        now += duration
    if samples is None:
        samples = course.track.cell_count
    times = tuple(times[:samples])
    telemetry = Telemetry({
        "vehicle.time_s": times,
        "event.cell_index": tuple(range(samples)),
        "event.lap_index": (0.0,) * samples,
        "event.lap_distance_m": course.track.distance_m[1:samples + 1],
    })
    return SimpleNamespace(
        completed=completed,
        failure_reason=None if completed else "UNTRUSTED fixture interrupted",
        elapsed_time_s=times[-1] if times else 0.0,
        distance_m=course.track.distance_m[samples],
        energy_kwh=0.012,
        completed_laps=1 if completed else 0,
        telemetry=telemetry,
    )


def test_ordered_open_geometry_matches_rule_dimensions_and_phase_boundaries():
    course = _course(0.73)
    assert not course.track.closed
    assert INNER_DIAMETER_M == 15.25
    assert OUTER_DIAMETER_M == 21.25
    assert LANE_WIDTH_M == 3.0
    assert CIRCLE_CENTRE_SEPARATION_M == 2.0 * NOMINAL_PATH_RADIUS_M == 18.25
    assert tuple(phase.name for phase in course.phases) == (
        "entry", "right_untimed", "right_timed", "left_untimed", "left_timed", "exit",
    )
    assert tuple(phase.timed for phase in course.phases) == (False, False, True, False, True, False)
    for phase in course.phases:
        curvatures = course.track.curvature_per_m[phase.first_cell:phase.end_cell]
        lengths = course.track.cell_length_m[phase.first_cell:phase.end_cell]
        assert all(value == phase.turn_direction / NOMINAL_PATH_RADIUS_M for value in curvatures)
        assert phase.start_distance_m == course.track.distance_m[phase.first_cell]
        assert phase.end_distance_m == course.track.distance_m[phase.end_cell]
        expected_turn = phase.turn_direction * 2.0 * pi
        assert fsum(k * length for k, length in zip(curvatures, lengths, strict=True)) == pytest.approx(expected_turn)
    assert course.track.x_m[0] == -2.0
    assert course.track.y_m[0] == 0.0
    for phase in course.phases[:-1]:
        assert course.track.x_m[phase.end_cell] == pytest.approx(0.0, abs=1e-9)
        assert course.track.y_m[phase.end_cell] == pytest.approx(0.0, abs=1e-9)
    assert course.track.x_m[-1] == pytest.approx(3.0, abs=1e-9)
    assert course.track.y_m[-1] == pytest.approx(0.0, abs=1e-9)
    # Repeated physical positions remain distinct in ordered station/cell space.
    assert len({phase.end_distance_m for phase in course.phases}) == 6
    assert max(course.track.cell_length_m) <= 0.73 + 1e-12
    course.track.validate_coherent_arcs()


def test_course_identity_binds_grid_and_explicit_entry_exit_scenarios():
    first = _course()
    assert first.course_sha256 == _course().course_sha256
    assert first.geometry_sha256 == _course().geometry_sha256
    other_entry = standard_skidpad_sequence(entry_length_m=3.0, exit_length_m=3.0, maximum_cell_length_m=2.0)
    assert first.course_sha256 != other_entry.course_sha256
    assert first.course_sha256 != _course(0.73).course_sha256
    manifest = first.to_dict()
    assert manifest["entry_and_exit_lengths_are_scenario_inputs"]
    assert not manifest["surveyed_boundaries_or_racing_line_qualification"]
    assert not manifest["qualification_or_execution_authority"]
    assert not manifest["shared_canonical_imported_course_artifact"]
    assert manifest["geometry"]["closed"] is False


@pytest.mark.parametrize("name,value", [
    ("entry_length_m", 0.0), ("entry_length_m", -1.0),
    ("exit_length_m", float("inf")), ("exit_length_m", True),
    ("maximum_cell_length_m", float("nan")), ("maximum_cell_length_m", 0.0),
    ("entry_length_m", 10 ** 1000),
])
def test_constructor_rejects_invalid_inputs_before_grid_allocation(name, value):
    kwargs = dict(entry_length_m=2.0, exit_length_m=3.0, maximum_cell_length_m=2.0)
    kwargs[name] = value
    with pytest.raises(ValueError):
        standard_skidpad_sequence(**kwargs)


def test_grid_budget_and_tampered_phase_order_are_rejected():
    with pytest.raises(ValueError, match="compute cap"):
        _course(0.00001)
    course = _course()
    changed = list(course.phases)
    changed[1], changed[3] = changed[3], changed[1]
    with pytest.raises(ValueError, match="ordered cell ranges"):
        replace(course, phases=tuple(changed))
    with pytest.raises(ValueError, match="actual grid boundaries"):
        replace(course, phases=(replace(course.phases[0], end_distance_m=2.1), *course.phases[1:]))


@pytest.mark.parametrize("channel", ["distance_m", "x_m", "y_m", "curvature_per_m"])
def test_mutable_geometry_channels_cannot_change_course_during_a_run(channel):
    course = _course()
    channels = {
        name: getattr(course.track, name)
        for name in ("distance_m", "x_m", "y_m", "curvature_per_m")
    }
    channels[channel] = list(channels[channel])
    mutable_track = SpatialTrack(**channels, closed=False)
    with pytest.raises(ValueError, match="immutable tuples"):
        replace(course, track=mutable_track)


@pytest.mark.parametrize("name", ["entry_length_m", "exit_length_m"])
def test_subnormal_length_ratio_cannot_create_a_zero_cell_segment(name):
    kwargs = dict(entry_length_m=2.0, exit_length_m=3.0, maximum_cell_length_m=1000.0)
    kwargs[name] = float.fromhex("0x0.0000000000001p-1022")
    with pytest.raises(ValueError, match="compute cap"):
        standard_skidpad_sequence(**kwargs)


def test_timing_uses_only_second_right_and_second_left_then_adds_rulebook_penalty():
    course = _course()
    run = _run_fixture(course)
    with patch("lapsim.events.skidpad_sequence._run_prescribed_path", return_value=run) as runner:
        result = simulate_skidpad_sequence(
            object(), course, _profile(),
            config=SkidpadSequenceConfig(cone_count=2, cone_penalty_policy="fsae_2027_v1_rulebook"),
        )
    assert runner.call_count == 1
    assert runner.call_args.kwargs["laps"] == 1
    assert runner.call_args.args[1] is course.track
    assert tuple(t.observed_elapsed_time_s for t in result.phase_timings) == pytest.approx((1, 2, 4, 6, 8, 10))
    assert result.elapsed_time_s == 31.0
    assert result.unpenalized_average_s == 6.0
    assert result.cone_penalty_s == 0.25
    assert result.corrected_time_s == 6.25
    assert result.telemetry is run.telemetry
    serialized = result.to_dict(include_telemetry=True)
    assert serialized["official_points"] is None
    assert serialized["event_ranking"] is None
    assert not serialized["official_eligibility_established"]
    assert not serialized["qualification_or_execution_authority"]
    assert serialized["scenario"]["starting_speed_mps"] == 0.0
    assert serialized["scenario"]["maximum_driving_time_s"] == 120.0
    assert serialized["scenario"]["cone_count"] == 2
    assert not serialized["vehicle_configuration_identity_bound"]
    assert not serialized["control_profile_identity_bound"]
    assert not serialized["matched_policy_or_vehicle_comparison_established"]
    assert not serialized["shared_canonical_imported_course_artifact"]
    assert "telemetry" in serialized


def test_handbook_policy_is_distinct_and_unspecified_policy_does_not_drop_cones():
    course = _course()
    run = _run_fixture(course)
    with patch("lapsim.events.skidpad_sequence._run_prescribed_path", return_value=run):
        handbook = simulate_skidpad_sequence(
            object(), course, _profile(),
            config=SkidpadSequenceConfig(cone_count=2, cone_penalty_policy="fsae_2026_event_handbook"),
        )
        unresolved = simulate_skidpad_sequence(
            object(), course, _profile(), config=SkidpadSequenceConfig(cone_count=2),
        )
    assert handbook.corrected_time_s == 6.5
    assert handbook.cone_penalty_s == 0.5
    assert unresolved.unpenalized_average_s == 6.0
    assert unresolved.declared_cone_count == 2
    assert unresolved.cone_penalty_s is None
    assert unresolved.corrected_time_s is None
    assert "0.125" in handbook.to_dict()["penalty_discrepancy"]
    assert "0.25" in handbook.to_dict()["penalty_discrepancy"]


def test_complete_timed_circle_samples_do_not_accept_an_aborted_exit():
    course = _course()
    run = _run_fixture(course, completed=False, samples=course.phases[4].end_cell)
    with patch("lapsim.events.skidpad_sequence._run_prescribed_path", return_value=run):
        result = simulate_skidpad_sequence(
            object(), course, _profile(),
            config=SkidpadSequenceConfig(cone_penalty_policy="fsae_2026_rulebook"),
        )
    assert not result.numerical_path_completed
    assert result.phase_timings[2].end_boundary_observed
    assert result.phase_timings[4].end_boundary_observed
    assert result.phase_timings[4].observed_elapsed_time_s == 8.0
    assert not result.phase_timings[5].end_boundary_observed
    assert result.unpenalized_average_s is None
    assert result.corrected_time_s is None
    assert result.path_failure_reason == run.failure_reason


def test_post_step_failure_with_final_sample_retains_observations_but_no_average():
    course = _course()
    run = _run_fixture(course, completed=False)
    with patch("lapsim.events.skidpad_sequence._run_prescribed_path", return_value=run):
        result = simulate_skidpad_sequence(object(), course, _profile())
    assert all(t.end_boundary_observed for t in result.phase_timings)
    assert result.unpenalized_average_s is None
    assert result.corrected_time_s is None


def test_declared_dnf_preserves_raw_run_and_prevents_corrected_result():
    course = _course()
    run = _run_fixture(course)
    with patch("lapsim.events.skidpad_sequence._run_prescribed_path", return_value=run):
        result = simulate_skidpad_sequence(
            object(), course, _profile(),
            config=SkidpadSequenceConfig(
                cone_count=1, cone_penalty_policy="fsae_2026_rulebook",
                declared_dnf_reason="Declared off course by external observer",
            ),
        )
    assert result.numerical_path_completed
    assert result.unpenalized_average_s == 6.0
    assert result.cone_penalty_s == 0.125
    assert result.corrected_time_s is None
    assert result.declared_dnf_reason
    assert result.telemetry is run.telemetry


@pytest.mark.parametrize("mutation", ["cell_order", "station", "time", "truncation"])
def test_inconsistent_cell_telemetry_cannot_create_complete_timing(mutation):
    course = _course()
    run = _run_fixture(course)
    channels = {key: list(values) for key, values in run.telemetry.items()}
    if mutation == "cell_order":
        channels["event.cell_index"][1] = 0.0
    elif mutation == "station":
        channels["event.lap_distance_m"][1] += 0.1
    elif mutation == "time":
        channels["vehicle.time_s"][1] = channels["vehicle.time_s"][0]
    else:
        channels = {key: values[:-1] for key, values in channels.items()}
    run.telemetry = Telemetry(channels)
    with patch("lapsim.events.skidpad_sequence._run_prescribed_path", return_value=run):
        with pytest.raises(ValueError):
            simulate_skidpad_sequence(object(), course, _profile())


@pytest.mark.parametrize("kwargs", [
    {"starting_speed_mps": True}, {"starting_speed_mps": -1},
    {"maximum_driving_time_s": 0}, {"cone_count": True},
    {"cone_count": -1}, {"cone_penalty_policy": "automatic"},
    {"declared_dnf_reason": "  "},
    {"starting_speed_mps": 10 ** 1000},
    {"maximum_driving_time_s": 10 ** 1000},
])
def test_config_rejects_invalid_or_implicit_policy_inputs(kwargs):
    with pytest.raises(ValueError):
        SkidpadSequenceConfig(**kwargs)


def test_actual_ordinary_vehicle_traverses_all_phases_without_state_reset():
    """Actual prescribed-path numerical smoke; no native worker or points."""

    course = _course()
    vehicle = Vehicle()
    original_reset = Vehicle.reset_state
    with patch.object(Vehicle, "reset_state", autospec=True, side_effect=original_reset) as reset:
        result = simulate_skidpad_sequence(
            vehicle, course, _profile(),
            config=SkidpadSequenceConfig(
                starting_speed_mps=5.0, maximum_driving_time_s=120.0,
                cone_penalty_policy="fsae_2027_v1_rulebook",
            ),
        )
    assert result.numerical_path_completed, result.path_failure_reason
    assert reset.call_count == 1
    assert result.telemetry.sample_count == course.track.cell_count
    assert result.elapsed_time_s == result.telemetry["vehicle.time_s"][-1]
    assert result.distance_m == pytest.approx(course.track.length_m)
    assert all(t.end_boundary_observed for t in result.phase_timings)
    assert result.unpenalized_average_s > 0.0
    assert result.corrected_time_s == result.unpenalized_average_s
    assert result.phase_timings[1].end_time_s == result.phase_timings[2].start_time_s
    assert result.phase_timings[2].end_time_s == result.phase_timings[3].start_time_s
    curvature = result.telemetry["vehicle.requested_curvature_per_m"]
    right = course.phases[1]
    left = course.phases[3]
    assert all(value < 0.0 for value in curvature[right.first_cell:right.end_cell])
    assert all(value > 0.0 for value in curvature[left.first_cell:left.end_cell])
