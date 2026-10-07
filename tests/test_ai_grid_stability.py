"""Bounded, opt-in resolution checks for an already eligible AI path pair."""

from __future__ import annotations

from math import ceil, pi
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Straight, Track
from lapsim.dynamics.conditions import PlanarRoad, RectangularGripPatch, RoadDomain
from lapsim.optimization.grid_stability import diagnose_paired_grid_stability
from lapsim.optimization.road_grip_schedule import world_patch_grip_schedule
from lapsim.ui.simulation import run_one_lap
from vehicle_model import Vehicle


def _circle() -> SpatialTrack:
    return SpatialTrack.from_track(
        Track.from_segments([Curve(25.0, 2.0 * pi)]),
        maximum_cell_length_m=5.0,
    )


def _rounded_rectangle() -> SpatialTrack:
    return SpatialTrack.from_track(
        Track.from_segments([
            Straight(40.0), Curve(12.0, pi / 2.0),
            Straight(20.0), Curve(12.0, pi / 2.0),
            Straight(40.0), Curve(12.0, pi / 2.0),
            Straight(20.0), Curve(12.0, pi / 2.0),
        ]),
        maximum_cell_length_m=5.0,
    )


def _periodic(time_s: float, *, converged: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        converged=converged,
        failure_reason=None if converged else "speed seam did not converge",
        run=SimpleNamespace(
            completed=True, driving_time_s=time_s, failure_reason=None,
        ),
    )


def test_default_grid_check_uses_one_pass_laps() -> None:
    source = _circle()

    def completed(time_s: float) -> SimpleNamespace:
        return SimpleNamespace(
            completed=True, driving_time_s=time_s, failure_reason=None,
        )

    with (
        patch("lapsim.ui.simulation.run_one_lap",
              side_effect=(completed(90.0), completed(89.0))) as one_pass,
        patch("lapsim.ui.simulation.run_speed_periodic_lap",
              side_effect=AssertionError("default must stay one-pass")) as periodic,
    ):
        report = diagnose_paired_grid_stability(
            Vehicle(), source, source,
            original_baseline_time_s=100.0,
            original_candidate_time_s=99.0,
            torque_request_fraction=0.8,
        )
    assert report.status == "completed"
    assert report.refined_candidate_minus_baseline_s == -1.0
    assert one_pass.call_count == 2
    periodic.assert_not_called()


def test_explicit_periodic_grid_check_uses_periodic_laps() -> None:
    source = _circle()
    with (
        patch("lapsim.ui.simulation.run_one_lap",
              side_effect=AssertionError("periodic check must use periodic laps")) as one_pass,
        patch("lapsim.ui.simulation.run_speed_periodic_lap",
              side_effect=(_periodic(90.0), _periodic(89.0))) as periodic,
    ):
        report = diagnose_paired_grid_stability(
            Vehicle(), source, source,
            original_baseline_time_s=100.0,
            original_candidate_time_s=99.0,
            torque_request_fraction=0.8,
            speed_periodic=True,
        )
    assert report.status == "completed"
    assert report.refined_candidate_minus_baseline_s == -1.0
    assert periodic.call_count == 2
    one_pass.assert_not_called()


@pytest.mark.parametrize(
    ("refined_times", "expected_sign_stable", "expected_margin_stable"),
    (
        ((90.0, 90.01), False, False),
        ((90.0, 89.99), True, False),
        ((90.0, 89.8), True, True),
    ),
)
def test_paired_grid_report_keeps_sign_and_margin_separate(
    refined_times: tuple[float, float], expected_sign_stable: bool,
    expected_margin_stable: bool,
) -> None:
    source = _circle()
    vehicle = Vehicle()
    observed: list[tuple[Vehicle, SpatialTrack, dict[str, object]]] = []

    def fake_run(car: Vehicle, track: SpatialTrack, **kwargs: object) -> SimpleNamespace:
        observed.append((car, track, kwargs))
        return _periodic(refined_times[len(observed) - 1])

    with patch("lapsim.ui.simulation.run_speed_periodic_lap", side_effect=fake_run):
        report = diagnose_paired_grid_stability(
            vehicle, source, source,
            original_baseline_time_s=100.0,
            original_candidate_time_s=99.9,
            torque_request_fraction=0.8,
            speed_periodic=True,
        )

    assert report.status == "completed"
    assert report.original_candidate_minus_baseline_s == pytest.approx(-0.1)
    assert report.refined_candidate_minus_baseline_s == pytest.approx(
        refined_times[1] - refined_times[0]
    )
    assert report.sign_stable is expected_sign_stable
    assert report.selection_margin_stable is expected_margin_stable
    assert report.maximum_refined_cell_length_m == pytest.approx(
        max(source.cell_length_m) / 2.0
    )
    assert len(observed) == 2
    for car, track, kwargs in observed:
        assert car is not vehicle
        assert track is not source
        assert track.cell_count == report.refined_baseline_cells
        assert track.cell_count <= 5_000
        assert kwargs["torque_request_fraction"] == 0.8
        assert kwargs["maximum_lap_passes"] == 2
        assert kwargs["speed_tolerance_mps"] == 0.005


def test_cell_cap_returns_before_refinement_or_physics() -> None:
    source = _circle()
    with (
        patch.object(SpatialTrack, "refine", side_effect=AssertionError("must not refine")),
        patch("lapsim.ui.simulation.run_speed_periodic_lap",
              side_effect=AssertionError("must not run physics")),
    ):
        report = diagnose_paired_grid_stability(
            Vehicle(), source, source,
            original_baseline_time_s=100.0,
            original_candidate_time_s=99.0,
            torque_request_fraction=0.8,
            maximum_refined_cell_length_m=0.01,
        )
    assert report.status == "cell_cap_exceeded"
    assert report.refined_baseline_cells is None
    assert report.refined_candidate_cells is None
    assert report.refined_candidate_minus_baseline_s is None
    assert report.sign_stable is None
    assert report.selection_margin_stable is None


def test_original_cell_grip_is_held_over_its_exact_subdivisions() -> None:
    source = _circle()
    baseline_grip = tuple(0.8 if i % 2 else 1.0 for i in range(source.cell_count))
    candidate_grip = tuple(0.7 if i % 3 else 0.9 for i in range(source.cell_count))
    seen: list[tuple[SpatialTrack, tuple[float, ...]]] = []

    def fake_run(_car: Vehicle, track: SpatialTrack, **kwargs: object) -> SimpleNamespace:
        seen.append((track, kwargs["cell_road_grip_multiplier"]))
        return _periodic(90.0 - len(seen))

    with patch("lapsim.ui.simulation.run_speed_periodic_lap", side_effect=fake_run):
        report = diagnose_paired_grid_stability(
            Vehicle(), source, source,
            original_baseline_time_s=100.0,
            original_candidate_time_s=99.0,
            torque_request_fraction=0.8,
            baseline_cell_road_grip_multiplier=baseline_grip,
            candidate_cell_road_grip_multiplier=candidate_grip,
            speed_periodic=True,
        )
    assert report.status == "completed"
    assert len(seen) == 2
    for (_, observed), original in zip(seen, (baseline_grip, candidate_grip), strict=True):
        expected = tuple(
            value
            for value, length_m in zip(original, source.cell_length_m, strict=True)
            for _ in range(ceil(length_m / report.maximum_refined_cell_length_m))
        )
        assert observed == expected


def test_world_patch_is_remapped_on_each_refined_path_with_original_heading() -> None:
    source = _rounded_rectangle()
    vehicle = Vehicle()
    road = PlanarRoad(patches=(
        RectangularGripPatch(1.0, 1.01, -0.62, -0.57, 0.3),
    ))
    coarse = world_patch_grip_schedule(source, vehicle, road)
    assert coarse[0] == 0.3
    assert coarse[1] == 1.0
    seen: list[tuple[SpatialTrack, tuple[float, ...]]] = []

    def fake_run(_car: Vehicle, track: SpatialTrack, **kwargs: object) -> SimpleNamespace:
        seen.append((track, kwargs["cell_road_grip_multiplier"]))
        return _periodic(90.0 - len(seen))

    with patch("lapsim.ui.simulation.run_speed_periodic_lap", side_effect=fake_run):
        report = diagnose_paired_grid_stability(
            vehicle, source, source,
            original_baseline_time_s=100.0,
            original_candidate_time_s=99.0,
            torque_request_fraction=0.8,
            maximum_refined_cell_length_m=2.5,
            road=road,
            speed_periodic=True,
        )

    assert report.status == "completed"
    assert len(seen) == 2
    for refined, mapped in seen:
        assert refined.cell_count == 2 * source.cell_count
        assert len(mapped) == refined.cell_count
        assert mapped[0] == 0.3
        assert mapped[1] == 1.0
        assert sum(value < 1.0 for value in mapped) == 1
        assert mapped != tuple(value for value in coarse for _ in range(2))


def test_world_road_and_explicit_cell_grip_cannot_be_combined() -> None:
    source = _circle()
    with pytest.raises(ValueError, match="cannot be combined"):
        diagnose_paired_grid_stability(
            Vehicle(), source, source,
            original_baseline_time_s=100.0,
            original_candidate_time_s=99.0,
            torque_request_fraction=0.8,
            road=PlanarRoad(),
            baseline_cell_road_grip_multiplier=(1.0,) * source.cell_count,
        )


def test_world_road_mapping_failure_never_runs_refined_physics() -> None:
    source = _circle()
    road = PlanarRoad(valid_domain=RoadDomain(-30.0, 30.0, -30.0, 30.0))
    with patch(
        "lapsim.ui.simulation.run_speed_periodic_lap",
        side_effect=AssertionError("mapping must fail before physics"),
    ):
        report = diagnose_paired_grid_stability(
            Vehicle(), source, source,
            original_baseline_time_s=100.0,
            original_candidate_time_s=99.0,
            torque_request_fraction=0.8,
            road=road,
        )
    assert report.status == "road_mapping_failed"
    assert "bounded road domain" in report.failure_reason
    assert report.refined_baseline_time_s is None
    assert report.refined_candidate_time_s is None
    assert report.sign_stable is None


def test_refined_candidate_failure_is_not_reported_as_stable() -> None:
    source = _circle()
    with patch(
        "lapsim.ui.simulation.run_speed_periodic_lap",
        side_effect=(_periodic(90.0), _periodic(90.0, converged=False)),
    ):
        report = diagnose_paired_grid_stability(
            Vehicle(), source, source,
            original_baseline_time_s=100.0,
            original_candidate_time_s=99.0,
            torque_request_fraction=0.8,
            speed_periodic=True,
        )
    assert report.status == "candidate_failed"
    assert report.refined_baseline_time_s == 90.0
    assert report.refined_candidate_time_s is None
    assert report.sign_stable is None
    assert report.selection_margin_stable is None
    assert "seam" in report.failure_reason


@pytest.mark.parametrize(
    "bad_grip",
    ((1.0,), tuple(float("nan") for _ in range(_circle().cell_count))),
)
def test_bad_original_grip_schedule_is_rejected(bad_grip: tuple[float, ...]) -> None:
    source = _circle()
    with pytest.raises(ValueError, match="baseline_cell_road_grip_multiplier"):
        diagnose_paired_grid_stability(
            Vehicle(), source, source,
            original_baseline_time_s=100.0,
            original_candidate_time_s=99.0,
            torque_request_fraction=0.8,
            baseline_cell_road_grip_multiplier=bad_grip,
        )


def test_real_one_pass_same_path_has_zero_refined_delta_and_preserves_car() -> None:
    source = _circle()
    vehicle = Vehicle()
    base_grip = vehicle.tire.road_grip_multiplier
    original = run_one_lap(
        Vehicle(), source, torque_request_fraction=0.8,
    )
    assert original.completed, original.failure_reason

    report = diagnose_paired_grid_stability(
        vehicle, source, source,
        original_baseline_time_s=original.driving_time_s,
        original_candidate_time_s=original.driving_time_s,
        torque_request_fraction=0.8,
        speed_periodic=False,
    )
    assert report.status == "completed"
    assert report.refined_baseline_time_s == report.refined_candidate_time_s
    assert report.refined_candidate_minus_baseline_s == 0.0
    assert report.sign_stable is True
    assert report.selection_margin_stable is True
    assert vehicle.speed_mps == 0.0
    assert vehicle.tire.road_grip_multiplier == base_grip
