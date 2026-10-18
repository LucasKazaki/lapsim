"""Cyclic braking ceilings remain safe under user-selected solver tolerances."""

from typing import Any

import numpy as np
import pytest

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Straight, Track
from lapsim.solvers.path_constraints import PathConstraintSolver
from vehicle_model import Vehicle


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), True])
def test_rejects_nonfinite_or_boolean_convergence_tolerance(value: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        PathConstraintSolver(convergence_tolerance_mps=value)


def test_loose_tolerance_cannot_accept_unsafe_cyclic_seam() -> None:
    # The curved cell appears before the closing straight in sweep order.
    # An initial backward pass updates cell 0 after it has already used the
    # old cell-0 ceiling for cell 3, so an early exit would miss its braking.
    track = SpatialTrack.from_cells(
        cell_length_m=(10.0, 10.0, 10.0, 10.0),
        curvature_per_m=(0.0, 0.1, 0.0, 0.0),
    )
    vehicle = Vehicle()
    reference = PathConstraintSolver().solve(track, vehicle)
    loose_solver = PathConstraintSolver(convergence_tolerance_mps=100.0)
    loose = loose_solver.solve(track, vehicle)

    assert loose.passes >= 2
    assert loose.braking_speed_ceiling_mps == pytest.approx(
        reference.braking_speed_ceiling_mps, abs=1e-6
    )
    assert loose.braking_speed_ceiling_mps[-1] < 30.0
    seam_reachable = loose_solver._maximum_entry_speed_mps(
        vehicle=vehicle,
        next_speed_mps=loose.braking_speed_ceiling_mps[0],
        local_speed_limit_mps=loose.local_corner_speed_mps[-1],
        curvature_per_m=track.curvature_per_m[-1],
        cell_length_m=track.cell_length_m[-1],
    )
    assert loose.braking_speed_ceiling_mps[-1] <= seam_reachable + 1e-6


def test_pass_limit_cannot_certify_an_unsafe_seam() -> None:
    track = SpatialTrack.from_cells(
        cell_length_m=(10.0, 10.0, 10.0, 10.0),
        curvature_per_m=(0.0, 0.1, 0.0, 0.0),
    )
    solver = PathConstraintSolver(
        convergence_tolerance_mps=100.0, maximum_passes=1,
    )
    with pytest.raises(RuntimeError, match="did not converge"):
        solver.solve(track, Vehicle())


@pytest.mark.parametrize(
    "field",
    [
        "maximum_passes",
        "maximum_entry_iterations",
        "steady_state_iterations",
    ],
)
@pytest.mark.parametrize(
    "value",
    [
        pytest.param(True, id="bool-true"),
        pytest.param(False, id="bool-false"),
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(1.0, id="integral-float"),
        pytest.param(1.5, id="fractional-float"),
        pytest.param(float("nan"), id="nan"),
        pytest.param(float("inf"), id="positive-infinity"),
        pytest.param(float("-inf"), id="negative-infinity"),
        pytest.param(None, id="none"),
        pytest.param("2", id="string"),
        pytest.param(1 + 0j, id="complex"),
        pytest.param(np.bool_(True), id="numpy-bool-true"),
        pytest.param(np.bool_(False), id="numpy-bool-false"),
        pytest.param(np.float32(1.0), id="numpy-integral-float"),
        pytest.param(np.float64(1.5), id="numpy-fractional-float"),
        pytest.param(np.float64("nan"), id="numpy-nan"),
        pytest.param(np.float64("inf"), id="numpy-positive-infinity"),
        pytest.param(np.float64("-inf"), id="numpy-negative-infinity"),
    ],
)
def test_iteration_limits_reject_nonpositive_or_noninteger_inputs(
    field: str,
    value: Any,
) -> None:
    # Any is intentional here: the public runtime boundary receives bad types.
    with pytest.raises(ValueError, match=rf"^{field} must be a positive integer$"):
        PathConstraintSolver(**{field: value})


@pytest.mark.parametrize(
    "field",
    [
        "maximum_passes",
        "maximum_entry_iterations",
        "steady_state_iterations",
    ],
)
@pytest.mark.parametrize(
    "value",
    [
        pytest.param(1, id="int-one"),
        pytest.param(2, id="int-two"),
        pytest.param(100, id="int-hundred"),
        pytest.param(np.int32(3), id="numpy-int32"),
        pytest.param(np.int64(4), id="numpy-int64"),
        pytest.param(np.uint64(5), id="numpy-uint64"),
    ],
)
def test_positive_integral_iteration_limits_are_retained_without_coercion(
    field: str,
    value: Any,
) -> None:
    solver = PathConstraintSolver(**{field: value})
    assert getattr(solver, field) is value


def test_default_iteration_limits_are_unchanged() -> None:
    solver = PathConstraintSolver()
    assert solver.maximum_passes == 500
    assert solver.maximum_entry_iterations == 40
    assert solver.steady_state_iterations == 50
    assert all(
        type(value) is int
        for value in (
            solver.maximum_passes,
            solver.maximum_entry_iterations,
            solver.steady_state_iterations,
        )
    )


@pytest.mark.parametrize(
    "field",
    [
        "maximum_passes",
        "maximum_entry_iterations",
        "steady_state_iterations",
    ],
)
@pytest.mark.parametrize(
    "scalar_type",
    [
        pytest.param(int, id="int"),
        pytest.param(np.int32, id="numpy-int32"),
        pytest.param(np.int64, id="numpy-int64"),
        pytest.param(np.uint64, id="numpy-uint64"),
    ],
)
def test_positive_integral_iteration_limits_solve_like_python_int(
    field: str,
    scalar_type: Any,
) -> None:
    # A stadium provides coherent straight/curve/straight transitions without
    # the legacy plotted-coordinate closure correction or from_cells roundtrip.
    track = SpatialTrack.from_track(
        Track.from_segments(
            [Straight(10.0), Curve(25.0, np.pi), Straight(10.0), Curve(25.0, np.pi)]
        ),
        maximum_cell_length_m=20.0,
        close_geometry=False,
    )
    track.validate_coherent_arcs()
    value = scalar_type(5)
    solver = PathConstraintSolver(**{field: value})
    reference = PathConstraintSolver(**{field: 5}).solve(track, Vehicle())

    actual = solver.solve(track, Vehicle())

    assert reference.local_corner_speed_mps[0] > reference.local_corner_speed_mps[1]
    assert reference.braking_speed_ceiling_mps[0] < reference.local_corner_speed_mps[0]
    assert actual == reference
    assert getattr(solver, field) is value


def test_uint64_maximum_passes_converges_on_first_pass_without_overflow() -> None:
    # Two coherent semicircles and a low speed cap form a one-pass fixed point;
    # the Python-int reference proves bounded work before using the huge cap.
    track = SpatialTrack.from_track(
        Track.from_segments([Curve(10.0, 2.0 * np.pi)]),
        maximum_cell_length_m=40.0,
        close_geometry=False,
    )
    track.validate_coherent_arcs()
    value: Any = np.uint64((1 << 64) - 1)
    solver = PathConstraintSolver(maximum_passes=value)
    vehicle = Vehicle()
    vehicle.drivetrain.configured_speed_limit_mps = 1.0
    reference_vehicle = Vehicle()
    reference_vehicle.drivetrain.configured_speed_limit_mps = 1.0
    reference = PathConstraintSolver(maximum_passes=1).solve(track, reference_vehicle)
    assert reference.passes == 1

    actual = solver.solve(track, vehicle)

    assert track.cell_count == 2
    assert actual == reference
    assert actual.passes == 1
    assert all(0.0 < speed <= 1.0 for speed in actual.local_corner_speed_mps)
    assert actual.braking_speed_ceiling_mps == actual.local_corner_speed_mps
    assert solver.maximum_passes is value
