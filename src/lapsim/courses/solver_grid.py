"""UI-independent effective-grid policy for prescribed-path experiments.

Coherent sources retain their exact arc boundaries; fused distance-indexed
sources use the legacy weighted-curvature resampler. Saved runs embed the
resolved geometry and replay it without re-resolving this policy.
"""
from math import ceil, isfinite
from numbers import Real

import numpy as np

from .spatial_track import SpatialTrack

MAXIMUM_SOLVER_CELLS = 5000
GRID_POLICY_VERSION = "course-grid-v1"


def solver_grid_cell_count(track: SpatialTrack, maximum_cell_length_m: float, *, coherent_arcs: bool) -> int:
    """Count effective cells before allocating/solving the bounded grid."""
    if (isinstance(maximum_cell_length_m, bool)
        or not isinstance(maximum_cell_length_m, Real)
        or not isfinite(maximum_cell_length_m) or maximum_cell_length_m <= 0):
        raise ValueError("maximum_cell_length_m must be finite and positive")
    requested = track.length_m / maximum_cell_length_m
    if not isfinite(requested) or requested > MAXIMUM_SOLVER_CELLS:
        raise ValueError("requested solver grid exceeds the 5000-cell compute cap")
    if coherent_arcs:
        track.validate_coherent_arcs()
        count = (track.cell_count if maximum_cell_length_m >= max(track.cell_length_m) - 1e-10
                 else sum(ceil(length / maximum_cell_length_m) for length in track.cell_length_m))
    else:
        count = ceil(requested)
    return count


def resolve_solver_grid(track: SpatialTrack, maximum_cell_length_m: float, *, coherent_arcs: bool) -> SpatialTrack:
    """Resolve the shared geometry policy without consulting an interface."""
    if solver_grid_cell_count(track, maximum_cell_length_m, coherent_arcs=coherent_arcs) > MAXIMUM_SOLVER_CELLS:
        raise ValueError("requested solver grid exceeds the 5000-cell compute cap")
    if not coherent_arcs:
        return resample_track(track, maximum_cell_length_m)
    if maximum_cell_length_m >= max(track.cell_length_m) - 1e-10:
        return track
    return track.refine_arcs(maximum_cell_length_m)


def resample_track(track: SpatialTrack, maximum_cell_length_m: float = 1.0) -> SpatialTrack:
    """Build a solver grid while preserving each cell's integrated curvature.

    The measured centerline remains in the course view. Each solver cell gets
    the distance-weighted mean curvature of the source cells it overlaps, so
    the signed curvature integral is preserved over the full lap. Coordinates
    are interpolated to the solver-cell boundaries.
    """

    if (
        isinstance(maximum_cell_length_m, bool)
        or not isinstance(maximum_cell_length_m, Real)
        or not isfinite(maximum_cell_length_m)
        or maximum_cell_length_m <= 0.0
    ):
        raise ValueError("maximum_cell_length_m must be finite and positive")
    requested_cells = track.length_m / maximum_cell_length_m
    if not isfinite(requested_cells) or requested_cells > 5000:
        raise ValueError("requested solver grid exceeds the 5000-cell compute cap")
    cell_count = ceil(requested_cells)
    distances = [
        min(index * maximum_cell_length_m, track.length_m)
        for index in range(cell_count + 1)
    ]
    source_distance = np.asarray(track.distance_m, dtype=float)
    source_curvature = np.asarray(track.curvature_per_m, dtype=float)
    averaged_curvature: list[float] = []
    for lower_m, upper_m in zip(distances, distances[1:]):
        source_index = max(
            0,
            int(np.searchsorted(source_distance, lower_m, side="right") - 1),
        )
        weighted_curvature = 0.0
        while source_index < track.cell_count and source_distance[source_index] < upper_m:
            overlap_m = max(
                0.0,
                min(upper_m, source_distance[source_index + 1])
                - max(lower_m, source_distance[source_index]),
            )
            weighted_curvature += source_curvature[source_index] * overlap_m
            source_index += 1
        averaged_curvature.append(weighted_curvature / (upper_m - lower_m))
    return SpatialTrack(
        distance_m=tuple(distances),
        x_m=tuple(np.interp(distances, source_distance, track.x_m)),
        y_m=tuple(np.interp(distances, source_distance, track.y_m)),
        curvature_per_m=tuple(averaged_curvature),
        closed=track.closed,
    )


