"""A road-aware geometric proposal is screened before one optional lap trial."""

from __future__ import annotations

from dataclasses import replace
from math import pi
from types import SimpleNamespace

import pytest
import numpy as np

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Straight, Track
from lapsim.dynamics.conditions import PlanarRoad, RectangularGripPatch
from lapsim.optimization.grip_detour import (
    _quintic_plateau_pulse, propose_grip_detour,
)
from lapsim.optimization.racing_line import (
    RacingLinePlanner, TrackCorridor, _audit_curvature_path,
    compare_lines_with_lap_model,
)
from lapsim.optimization.road_grip_schedule import world_patch_grip_schedule
from vehicle_model import Vehicle


@pytest.fixture(scope="module")
def planned_loop():
    source = SpatialTrack.from_track(
        Track.from_segments([
            Straight(40.0), Curve(12.0, pi / 2.0),
            Straight(20.0), Curve(12.0, pi / 2.0),
            Straight(40.0), Curve(12.0, pi / 2.0),
            Straight(20.0), Curve(12.0, pi / 2.0),
        ]),
        maximum_cell_length_m=1.0,
    )
    corridor = TrackCorridor.constant(
        source,
        left_width_m=3.0,
        right_width_m=3.0,
        vehicle_width_m=1.4,
        safety_margin_m=0.2,
        source="assumed synthetic corridor",
    )
    return RacingLinePlanner(maximum_cell_length_m=1.0).plan(
        source, corridor,
    )


def _road(
    x_min_m: float = 17.0, x_max_m: float = 25.0,
    y_min_m: float = -0.8, y_max_m: float = 0.8,
) -> PlanarRoad:
    return PlanarRoad(patches=(RectangularGripPatch(
        x_min_m, x_max_m, y_min_m, y_max_m, 0.2,
    ),))


def test_quintic_shoulders_join_plateau_with_continuous_curvature() -> None:
    def pulse(position_m: float) -> float:
        return float(_quintic_plateau_pulse(
            np.asarray((position_m,)), start_m=20.0, width_m=10.0,
            transition_m=10.0, lap_length_m=100.0,
        )[0])

    for station_m, expected in ((10.0, 0.0), (20.0, 1.0),
                                (30.0, 1.0), (40.0, 0.0)):
        assert pulse(station_m) == pytest.approx(expected, abs=1e-12)
        delta_m = 0.01
        first = (pulse(station_m + delta_m)
                 - pulse(station_m - delta_m)) / (2.0 * delta_m)
        second = (pulse(station_m + delta_m)
                  - 2.0 * pulse(station_m)
                  + pulse(station_m - delta_m)) / delta_m**2
        assert abs(first) < 1e-4
        assert abs(second) < 1e-3

    assert pulse(0.0) == pulse(100.0)


def test_local_detour_reduces_path_specific_wheel_exposure(planned_loop) -> None:
    vehicle = Vehicle()
    road = _road()
    proposal = propose_grip_detour(
        planned_loop, vehicle, road, maximum_cell_length_m=1.0,
    )

    assert proposal.status == "candidate"
    assert proposal.track is not None
    assert proposal.side in {"left", "right"}
    assert proposal.candidate_count <= 12
    assert 0 < proposal.mapped_candidate_count <= proposal.candidate_count
    assert proposal.max_offset_m is not None and 0.0 < proposal.max_offset_m <= 3.0
    assert proposal.baseline_exposure_m is not None
    assert proposal.candidate_exposure_m is not None
    assert proposal.baseline_exposure_m - proposal.candidate_exposure_m >= 0.01
    assert proposal.baseline_reduced_grip_cells > proposal.candidate_reduced_grip_cells
    assert proposal.baseline_reduced_grip_distance_m > (
        proposal.candidate_reduced_grip_distance_m
    )
    assert proposal.track.cell_count == planned_loop.baseline_track.cell_count
    assert max(proposal.track.cell_length_m) <= 1.0 + 1e-10
    candidate_schedule = world_patch_grip_schedule(
        proposal.track, vehicle, road,
    )
    assert sum(value < 1.0 for value in candidate_schedule) == (
        proposal.candidate_reduced_grip_cells
    )
    audit = _audit_curvature_path(
        proposal.track, planned_loop.baseline_track,
        planned_loop.source_station_m, planned_loop.corridor,
    )
    assert audit.valid
    assert audit.continuous_clearance_certified


def test_no_patch_and_no_contact_do_not_offer_detour(planned_loop) -> None:
    vehicle = Vehicle()
    no_patch = propose_grip_detour(planned_loop, vehicle, PlanarRoad())
    assert no_patch.status == "no_patch"
    assert no_patch.track is None
    assert no_patch.candidate_count == 0

    away = propose_grip_detour(
        planned_loop, vehicle, _road(1000.0, 1001.0),
    )
    assert away.status == "no_patch_contact"
    assert away.baseline_exposure_m == 0.0
    assert away.track is None


def test_patch_wider_than_declared_corridor_has_no_false_avoidance(
    planned_loop,
) -> None:
    result = propose_grip_detour(
        planned_loop, Vehicle(), _road(y_min_m=-10.0, y_max_m=10.0),
        maximum_cell_length_m=1.0,
    )
    assert result.status == "no_lower_exposure_detour"
    assert result.track is None
    assert result.baseline_exposure_m is not None
    assert result.baseline_exposure_m > 0.0
    assert result.candidate_count <= 12


def test_asymmetric_declared_corridor_blocks_the_narrow_side(
    planned_loop,
) -> None:
    corridor = replace(
        planned_loop.corridor,
        left_width_m=(1.0,) * len(planned_loop.corridor.left_width_m),
    )
    plan = replace(planned_loop, corridor=corridor)
    result = propose_grip_detour(
        plan, Vehicle(), _road(), maximum_cell_length_m=1.0,
    )
    assert result.status == "candidate"
    assert result.side == "right"
    assert result.track is not None
    audit = _audit_curvature_path(
        result.track, plan.baseline_track, plan.source_station_m, corridor,
    )
    assert audit.valid


def test_detour_requires_declared_aligned_corridor(planned_loop) -> None:
    missing = propose_grip_detour(
        replace(planned_loop, corridor=None), Vehicle(), _road(),
    )
    assert missing.status == "missing_corridor"
    assert missing.track is None

    misaligned = propose_grip_detour(
        replace(planned_loop, source_station_m=(0.0, 1.0)),
        Vehicle(), _road(),
    )
    assert misaligned.status == "unaligned_plan"
    assert misaligned.track is None


def test_detour_rejects_invalid_requested_cell_size(planned_loop) -> None:
    with pytest.raises(ValueError, match="maximum_cell_length_m"):
        propose_grip_detour(
            planned_loop, Vehicle(), _road(), maximum_cell_length_m=0.0,
        )
    with pytest.raises(ValueError, match="maximum_cell_length_m"):
        propose_grip_detour(
            planned_loop, Vehicle(), _road(), maximum_cell_length_m=True,
        )


def test_full_model_can_select_detour_when_geometric_planner_stays_centerline(
    planned_loop, monkeypatch,
) -> None:
    vehicle = Vehicle()
    road = _road()
    plan = replace(
        planned_loop, status="centerline",
        candidate_track=planned_loop.baseline_track,
    )
    proposal = propose_grip_detour(plan, vehicle, road, maximum_cell_length_m=1.0)
    assert proposal.track is not None
    monkeypatch.setattr(
        "lapsim.optimization.grip_detour.propose_grip_detour",
        lambda *args, **kwargs: proposal,
    )
    calls = []

    def fake_lap(_vehicle, track, **_kwargs):
        calls.append(track)
        return SimpleNamespace(
            completed=True,
            driving_time_s=99.0 if track is proposal.track else 100.0,
            failure_reason=None,
        )

    monkeypatch.setattr("lapsim.ui.simulation.run_one_lap", fake_lap)
    comparison = compare_lines_with_lap_model(
        vehicle, plan, torque_request_fraction=0.8, road=road,
        maximum_detour_cell_length_m=1.0,
    )

    assert calls == [plan.baseline_track, proposal.track]
    assert comparison.selected_mode == "candidate"
    assert comparison.selected_track is proposal.track
    assert comparison.candidate_strategy == "grip_detour"
    assert comparison.candidate_strength is None
    assert comparison.grip_detour_status == "timed"
    assert comparison.grip_detour_candidate_count <= 12
    assert len(comparison.trials) == 1
    assert comparison.trials[0].strategy == "grip_detour"
    assert comparison.trials[0].cell_road_grip_multiplier is not None


def test_slower_detour_does_not_displace_faster_geometric_trial(
    planned_loop, monkeypatch,
) -> None:
    assert planned_loop.status == "candidate"
    vehicle = Vehicle()
    road = _road()
    proposal = propose_grip_detour(
        planned_loop, vehicle, road, maximum_cell_length_m=1.0,
    )
    assert proposal.track is not None
    monkeypatch.setattr(
        "lapsim.optimization.grip_detour.propose_grip_detour",
        lambda *args, **kwargs: proposal,
    )

    def fake_lap(_vehicle, track, **_kwargs):
        time_s = (
            100.0 if track is planned_loop.baseline_track
            else 101.0 if track is proposal.track else 99.0
        )
        return SimpleNamespace(
            completed=True, driving_time_s=time_s, failure_reason=None,
        )

    monkeypatch.setattr("lapsim.ui.simulation.run_one_lap", fake_lap)
    comparison = compare_lines_with_lap_model(
        vehicle, planned_loop, torque_request_fraction=0.8, road=road,
        maximum_detour_cell_length_m=1.0,
    )

    assert comparison.selected_mode == "candidate"
    assert comparison.candidate_strategy == "geometric_offset"
    assert comparison.candidate_strength is not None
    assert comparison.candidate_time_s == 99.0
    assert comparison.grip_detour_status == "timed"
    assert comparison.trials[-1].strategy == "grip_detour"
    assert comparison.trials[-1].lap_time_s == 101.0
