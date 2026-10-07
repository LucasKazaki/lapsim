"""World-fixed synthetic grip is mapped separately onto modeled path arcs."""

from math import atan2, cos, hypot, pi, sin
from time import perf_counter

import pytest

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Straight, Track
from lapsim.dynamics.conditions import PlanarRoad, RectangularGripPatch, RoadDomain
from lapsim.optimization.road_grip_schedule import (
    modeled_entry_heading_rad, world_patch_grip_schedule,
)
from vehicle_model import Vehicle


def _rounded_rectangle(step_m: float = 5.0) -> SpatialTrack:
    return SpatialTrack.from_track(
        Track.from_segments([
            Straight(40.0), Curve(12.0, pi / 2),
            Straight(20.0), Curve(12.0, pi / 2),
            Straight(40.0), Curve(12.0, pi / 2),
            Straight(20.0), Curve(12.0, pi / 2),
        ]),
        maximum_cell_length_m=step_m,
    )


def _patch(
    x_min: float, x_max: float, y_min: float, y_max: float,
    factor: float = 0.3,
) -> PlanarRoad:
    return PlanarRoad(patches=(RectangularGripPatch(
        x_min, x_max, y_min, y_max, factor,
    ),))


def test_no_patch_is_exact_uniform_reference_and_base_factor() -> None:
    track = _rounded_rectangle()
    vehicle = Vehicle()
    vehicle.tire.road_grip_multiplier = 0.7
    reference = vehicle.tire.road_grip_multiplier

    assert world_patch_grip_schedule(track, vehicle, PlanarRoad()) == (
        reference,
    ) * track.cell_count
    assert world_patch_grip_schedule(
        track, vehicle, PlanarRoad(base_friction_multiplier=0.8),
    ) == (reference * 0.8,) * track.cell_count
    assert vehicle.tire.road_grip_multiplier == reference


def test_narrow_patch_between_cell_samples_and_path_specific_map() -> None:
    track = _rounded_rectangle()
    vehicle = Vehicle()
    road = _patch(7.225, 7.235, -0.62, -0.57)
    schedule = world_patch_grip_schedule(track, vehicle, road)
    assert schedule[1] == 0.3
    assert schedule[0] == schedule[2] == 1.0
    assert schedule.count(0.3) == 1

    # Same station indices with distinct world x/y must be remapped, not
    # assigned the reference line's already computed schedule.
    translated = SpatialTrack(
        distance_m=track.distance_m,
        x_m=tuple(x + 100.0 for x in track.x_m),
        y_m=track.y_m,
        curvature_per_m=track.curvature_per_m,
        closed=True,
    )
    assert world_patch_grip_schedule(translated, vehicle, road) == (
        1.0,
    ) * track.cell_count


def test_refined_coherent_arc_keeps_original_world_heading() -> None:
    source = _rounded_rectangle()
    source.validate_coherent_arcs()
    refined = source.refine(2.5)
    vehicle = Vehicle()
    road = _patch(1.0, 1.01, -0.62, -0.57)

    original_heading = modeled_entry_heading_rad(source)
    assert original_heading == pytest.approx(0.0, abs=1e-12)
    assert modeled_entry_heading_rad(refined) == pytest.approx(-pi / 32.0)
    assert world_patch_grip_schedule(source, vehicle, road)[0] == 0.3
    # Chord interpolation in refine makes the same prescribed arcs appear
    # polygonal to automatic heading inference, rotating the road frame.
    assert world_patch_grip_schedule(refined, vehicle, road) == (
        1.0,
    ) * refined.cell_count
    frozen = world_patch_grip_schedule(
        refined, vehicle, road, initial_heading_rad=original_heading,
    )
    assert frozen[0] == 0.3
    assert frozen[1] == 1.0
    assert sum(value < 1.0 for value in frozen) == 1


@pytest.mark.parametrize("heading", (True, float("nan"), float("inf"), "0"))
def test_world_road_mapping_rejects_invalid_explicit_heading(heading: object) -> None:
    with pytest.raises(ValueError, match="initial_heading_rad must be finite"):
        world_patch_grip_schedule(
            _rounded_rectangle(), Vehicle(), PlanarRoad(),
            initial_heading_rad=heading,
        )


def test_patch_factor_multiplies_run_reference_tire_grip() -> None:
    track = _rounded_rectangle()
    vehicle = Vehicle()
    vehicle.tire.road_grip_multiplier = 0.7
    schedule = world_patch_grip_schedule(
        track, vehicle, _patch(7.225, 7.235, -0.62, -0.57),
    )
    assert schedule[1] == 0.7 * 0.3
    assert schedule[0] == 0.7
    assert vehicle.tire.road_grip_multiplier == 0.7


def test_patch_touching_closed_seam_marks_both_physical_sides() -> None:
    track = _rounded_rectangle()
    schedule = world_patch_grip_schedule(
        track, Vehicle(), _patch(0.80, 0.84, -0.63, -0.59),
    )
    assert schedule[0] == schedule[-1] == 0.3


def test_nominal_wheel_center_not_only_cg_controls_contact() -> None:
    track = _rounded_rectangle()
    road = _patch(2.0, 3.0, -0.62, -0.59)
    wide = Vehicle()
    narrow = Vehicle()
    narrow.chassis.front_track_width_m = 0.4
    narrow.chassis.rear_track_width_m = 0.4
    narrow.validate()

    assert world_patch_grip_schedule(track, wide, road)[0] == 0.3
    assert world_patch_grip_schedule(track, narrow, road)[0] == 1.0


def test_front_wheel_enters_patch_before_cell_cg() -> None:
    track = _rounded_rectangle()
    # CG in cell 0 ranges only from x=0 to x=5; the front tire reaches
    # beyond that boundary before the prescribed-path cell has ended.
    road = _patch(5.55, 5.60, -0.62, -0.59)
    schedule = world_patch_grip_schedule(track, Vehicle(), road)
    assert schedule[0] == 0.3


def test_world_patch_follows_integrated_arc_not_saved_polygon_chord() -> None:
    original = _rounded_rectangle()
    modified_y = list(original.y_m)
    modified_y[10] += 3.0  # Local polygon discrepancy away from the first seam.
    distorted = SpatialTrack(
        distance_m=original.distance_m,
        x_m=original.x_m,
        y_m=tuple(modified_y),
        curvature_per_m=original.curvature_per_m,
        closed=True,
    )
    with pytest.raises(ValueError, match="arc"):
        distorted.validate_coherent_arcs()

    # The racing-line audit's polygon-tangent seed rotates this straight
    # modeled cell. Its nominal front-right wheel is well below plotted y=0.
    previous_dx = distorted.x_m[-1] - distorted.x_m[-2]
    previous_dy = distorted.y_m[-1] - distorted.y_m[-2]
    first_dx = distorted.x_m[1] - distorted.x_m[0]
    first_dy = distorted.y_m[1] - distorted.y_m[0]
    vertex_turn = atan2(
        previous_dx * first_dy - previous_dy * first_dx,
        previous_dx * first_dx + previous_dy * first_dy,
    )
    heading = atan2(first_dy, first_dx) - 0.5 * vertex_turn
    vehicle = Vehicle()
    forward = vehicle.chassis.wheelbase_m * (
        1.0 - vehicle.chassis.static_front_weight_fraction
    )
    right = -0.5 * vehicle.chassis.front_track_width_m
    station = 2.5
    wheel_x = (station + forward) * cos(heading) - right * sin(heading)
    wheel_y = (station + forward) * sin(heading) + right * cos(heading)
    assert wheel_y < -0.8
    road = _patch(wheel_x - 0.01, wheel_x + 0.01,
                  wheel_y - 0.01, wheel_y + 0.01)
    assert world_patch_grip_schedule(distorted, vehicle, road)[0] == 0.3


def test_negative_arc_chord_maps_patch_on_valid_coarse_circle() -> None:
    # The first 3*pi arc has a negative signed chord. Its saved first point
    # still lies on the modeled circle, and the world frame must not rotate.
    angles = (0.0, 3.0 * pi, 10.0 * pi / 3.0, 11.0 * pi / 3.0, 4.0 * pi)
    track = SpatialTrack(
        distance_m=angles,
        x_m=tuple(sin(angle) for angle in angles),
        y_m=tuple(1.0 - cos(angle) for angle in angles),
        curvature_per_m=(1.0,) * 4,
    )
    track.validate_coherent_arcs()
    vehicle = Vehicle()
    front_axle_m = vehicle.chassis.wheelbase_m * (
        1.0 - vehicle.chassis.static_front_weight_fraction
    )
    front_right_radius_m = hypot(
        1.0 + 0.5 * vehicle.chassis.front_track_width_m, front_axle_m,
    )
    road = _patch(
        front_right_radius_m - 0.005, front_right_radius_m + 0.005,
        0.995, 1.005,
    )
    assert world_patch_grip_schedule(track, vehicle, road)[0] == 0.3


def test_rejects_unsupported_or_unphysical_surface_inputs() -> None:
    track = _rounded_rectangle()
    vehicle = Vehicle()
    with pytest.raises(ValueError, match="positive grip reductions"):
        world_patch_grip_schedule(
            track, vehicle, _patch(2.0, 3.0, -1.0, 1.0, 0.0),
        )
    with pytest.raises(ValueError, match="positive grip reductions"):
        world_patch_grip_schedule(
            track, vehicle, _patch(2.0, 3.0, -1.0, 1.0, 1.2),
        )
    with pytest.raises(ValueError, match="bounded road domain"):
        world_patch_grip_schedule(
            track, vehicle, PlanarRoad(valid_domain=RoadDomain(-5, 50, -5, 50)),
        )
    with pytest.raises(ValueError, match="positive"):
        world_patch_grip_schedule(
            track, vehicle, PlanarRoad(base_friction_multiplier=0.0),
        )


def test_single_patch_mapping_stays_bounded_on_near_5000_cell_grid() -> None:
    track = _rounded_rectangle(0.04)
    assert 4_000 < track.cell_count <= 5_000
    start = perf_counter()
    schedule = world_patch_grip_schedule(
        track, Vehicle(), _patch(7.225, 7.235, -0.62, -0.57),
    )
    elapsed_s = perf_counter() - start
    assert len(schedule) == track.cell_count
    assert min(schedule) == 0.3
    # A generous ceiling catches an accidental unbounded scan without
    # making normal slower CI machines depend on this host's timing.
    assert elapsed_s < 15.0
