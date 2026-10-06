"""Boundary-preserving refinement of prescribed spatial curvature."""

from __future__ import annotations

from math import fsum

import pytest

from lapsim.courses.spatial_track import SpatialTrack


def _integrals(track: SpatialTrack) -> tuple[float, float]:
    cells = zip(track.cell_length_m, track.curvature_per_m, strict=True)
    contributions = [(length, curvature) for length, curvature in cells]
    return (
        fsum(length * curvature for length, curvature in contributions),
        fsum(length * curvature**2 for length, curvature in contributions),
    )


def test_refine_preserves_source_boundaries_and_cell_curvature() -> None:
    source = SpatialTrack(
        distance_m=(0.0, 2.5, 3.5),
        x_m=(0.0, 2.0, 2.0),
        y_m=(0.0, 0.0, 1.0),
        curvature_per_m=(0.4, -0.2),
        closed=False,
    )

    refined = source.refine(1.0)

    assert refined.closed is False
    assert refined.cell_count == 4
    assert refined.length_m == source.length_m
    assert refined.distance_m == pytest.approx((0.0, 2.5 / 3, 5.0 / 3, 2.5, 3.5))
    assert refined.x_m == pytest.approx((0.0, 2.0 / 3, 4.0 / 3, 2.0, 2.0))
    assert refined.y_m == pytest.approx((0.0, 0.0, 0.0, 0.0, 1.0))
    assert refined.curvature_per_m == (0.4, 0.4, 0.4, -0.2)
    assert max(refined.cell_length_m) <= 1.0
    assert _integrals(refined) == pytest.approx(_integrals(source), abs=1e-14)
    assert source.refine(2.5) is source


def test_refine_closed_path_keeps_each_cell_integral_and_geometry() -> None:
    source = SpatialTrack(
        distance_m=(0.0, 2.0, 3.0, 5.0, 6.0),
        x_m=(0.0, 2.0, 2.0, 0.0, 0.0),
        y_m=(0.0, 0.0, 1.0, 1.0, 0.0),
        curvature_per_m=(0.0, 0.2, -0.3, 0.1),
        closed=True,
    )

    refined = source.refine(0.6)

    assert refined.closed is True
    assert refined.cell_count == 12
    assert refined.distance_m[-1] == source.length_m
    assert refined.x_m[-1] == refined.x_m[0]
    assert refined.y_m[-1] == refined.y_m[0]
    assert max(refined.cell_length_m) <= 0.6 + 1e-14
    assert _integrals(refined) == pytest.approx(_integrals(source), abs=1e-14)
    for cell_index, (lower, upper, curvature) in enumerate(
        zip(source.distance_m[:-1], source.distance_m[1:], source.curvature_per_m, strict=True)
    ):
        lower_index = refined.distance_m.index(lower)
        upper_index = refined.distance_m.index(upper)
        assert refined.x_m[lower_index] == source.x_m[cell_index]
        assert refined.y_m[lower_index] == source.y_m[cell_index]
        assert refined.x_m[upper_index] == source.x_m[cell_index + 1]
        assert refined.y_m[upper_index] == source.y_m[cell_index + 1]
        assert all(value == curvature for value in refined.curvature_per_m[lower_index:upper_index])
        assert fsum(refined.cell_length_m[lower_index:upper_index]) == pytest.approx(upper - lower)


@pytest.mark.parametrize(
    "maximum_cell_length_m", [0.0, -0.5, float("nan"), float("inf"), True]
)
def test_refine_rejects_nonpositive_or_nonfinite_maximum(maximum_cell_length_m: float) -> None:
    source = SpatialTrack(
        distance_m=(0.0, 1.0),
        x_m=(0.0, 1.0),
        y_m=(0.0, 0.0),
        curvature_per_m=(0.0,),
        closed=False,
    )

    with pytest.raises(ValueError, match="finite and positive"):
        source.refine(maximum_cell_length_m)


@pytest.mark.parametrize("maximum_cell_length_m", [1e-6, 1e-309])
def test_refine_rejects_pathological_grid_before_allocating(
    maximum_cell_length_m: float,
) -> None:
    source = SpatialTrack(
        distance_m=(0.0, 1.0),
        x_m=(0.0, 1.0),
        y_m=(0.0, 0.0),
        curvature_per_m=(0.2,),
        closed=False,
    )

    with pytest.raises(ValueError, match="100000-cell compute cap"):
        source.refine(maximum_cell_length_m)
