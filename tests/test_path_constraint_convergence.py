"""Cyclic braking ceilings remain safe under user-selected solver tolerances."""

import pytest

from lapsim.courses.spatial_track import SpatialTrack
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
