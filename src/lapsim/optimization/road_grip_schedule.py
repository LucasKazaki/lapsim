"""Bounded world-fixed low-grip sensitivity for prescribed-path lap cells.

The distance-domain car follows each cell's prescribed constant curvature,
which need not visit the separately saved x/y polygon vertex.  This module
integrates those arcs with the same initial-heading policy as the racing-line
clearance audit.  It places four *nominal* wheel centers on that path, but the
lap model still has only one grip scalar per cell: any lower-grip contact
reduces the entire cell's tire capacity.  This conservative approximation is
not four independent wheel/road friction states or a vehicle-pose simulation.

Only positive reductions from the road's uniform base factor are supported.
An adaptive interval bound detects even a patch narrower than the solver
cell; an unresolved contact within 1 cm is treated as touching.  A fixed
work budget raises an explicit error instead of silently missing a patch.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, hypot, isfinite, pi, remainder, sin

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.dynamics.conditions import PlanarRoad, RectangularGripPatch
from vehicle_model import Vehicle


_MAX_CELLS = 5_000
_MAX_PATCHES = 128
_MAX_INTERVAL_CHECKS = 2_000_000
_CONTACT_RESOLUTION_M = 0.01
_SEAM_TOLERANCE_M = 0.01
_HEADING_SEAM_TOLERANCE_RAD = 1e-3
ROAD_GRIP_SCHEDULE_MAPPING_VERSION = "integrated_arc_nominal_wheel_min_cell_v1"


def _sinc(value: float) -> float:
    if abs(value) < 1e-5:
        squared = value * value
        return 1.0 - squared / 6.0 + squared * squared / 120.0
    return sin(value) / value


@dataclass(frozen=True, slots=True)
class _ModeledCell:
    entry_x_m: float
    entry_y_m: float
    entry_heading_rad: float
    length_m: float
    curvature_per_m: float

    def wheel_position(
        self, station_in_cell_m: float, longitudinal_m: float, lateral_m: float,
    ) -> tuple[float, float]:
        half_turn = 0.5 * self.curvature_per_m * station_in_cell_m
        displacement = station_in_cell_m * _sinc(half_turn)
        midpoint_heading = self.entry_heading_rad + half_turn
        heading = self.entry_heading_rad + 2.0 * half_turn
        return (
            self.entry_x_m + displacement * cos(midpoint_heading)
            + longitudinal_m * cos(heading) - lateral_m * sin(heading),
            self.entry_y_m + displacement * sin(midpoint_heading)
            + longitudinal_m * sin(heading) + lateral_m * cos(heading),
        )


def _modeled_cells(track: SpatialTrack) -> tuple[_ModeledCell, ...]:
    """Use the racing-line audit's coherent-arc or polygon-tangent seed."""

    lengths = track.cell_length_m
    first_dx = track.x_m[1] - track.x_m[0]
    first_dy = track.y_m[1] - track.y_m[0]
    previous_dx = track.x_m[-1] - track.x_m[-2]
    previous_dy = track.y_m[-1] - track.y_m[-2]
    if hypot(first_dx, first_dy) <= 1e-12 or hypot(previous_dx, previous_dy) <= 1e-12:
        raise ValueError("world road mapping needs nonzero first and final chords")
    first_turn = atan2(
        previous_dx * first_dy - previous_dy * first_dx,
        previous_dx * first_dx + previous_dy * first_dy,
    )
    coherent_arc_chords = all(
        abs(length * _sinc(0.5 * length * curvature) - hypot(
            track.x_m[index + 1] - track.x_m[index],
            track.y_m[index + 1] - track.y_m[index],
        )) <= max(1e-8, 1e-8 * hypot(
            track.x_m[index + 1] - track.x_m[index],
            track.y_m[index + 1] - track.y_m[index],
        ))
        for index, (length, curvature) in enumerate(
            zip(lengths, track.curvature_per_m, strict=True)
        )
    )
    heading = atan2(first_dy, first_dx) - 0.5 * (
        lengths[0] * track.curvature_per_m[0]
        if coherent_arc_chords else first_turn
    )
    x_m = track.x_m[0]
    y_m = track.y_m[0]
    cells: list[_ModeledCell] = []
    total_turn = 0.0
    for length, curvature in zip(lengths, track.curvature_per_m, strict=True):
        cells.append(_ModeledCell(x_m, y_m, heading, length, curvature))
        half_turn = 0.5 * length * curvature
        displacement = length * _sinc(half_turn)
        x_m += displacement * cos(heading + half_turn)
        y_m += displacement * sin(heading + half_turn)
        heading += 2.0 * half_turn
        total_turn += 2.0 * half_turn
    if max(
        hypot(x_m - track.x_m[0], y_m - track.y_m[0]),
        hypot(track.x_m[-1] - track.x_m[0], track.y_m[-1] - track.y_m[0]),
    ) > _SEAM_TOLERANCE_M:
        raise ValueError("world road mapping needs a closed modeled path within 1 cm")
    if abs(remainder(total_turn, 2.0 * pi)) > _HEADING_SEAM_TOLERANCE_RAD:
        raise ValueError("world road mapping needs a closed modeled heading")
    return tuple(cells)


def _wheel_offsets(vehicle: Vehicle) -> tuple[tuple[float, float], ...]:
    chassis = vehicle.chassis
    front_m = chassis.wheelbase_m * (1.0 - chassis.static_front_weight_fraction)
    rear_m = -chassis.wheelbase_m * chassis.static_front_weight_fraction
    return (
        (front_m, 0.5 * chassis.front_track_width_m),
        (front_m, -0.5 * chassis.front_track_width_m),
        (rear_m, 0.5 * chassis.rear_track_width_m),
        (rear_m, -0.5 * chassis.rear_track_width_m),
    )


def _rectangles_overlap(
    x_min: float, x_max: float, y_min: float, y_max: float,
    patch: RectangularGripPatch,
) -> bool:
    return (
        x_min <= patch.x_max_m and x_max >= patch.x_min_m
        and y_min <= patch.y_max_m and y_max >= patch.y_min_m
    )


def _wheel_touches_patch(
    cell: _ModeledCell,
    offset: tuple[float, float],
    patch: RectangularGripPatch,
    work: list[int],
) -> bool:
    """Conservatively resolve a wheel-center arc against one rectangle."""

    longitudinal_m, lateral_m = offset
    # |d wheel position / ds| <= 1 + |curvature| * |wheel offset|.
    speed_bound = 1.0 + abs(cell.curvature_per_m) * hypot(*offset)
    intervals = [(0.0, cell.length_m)]
    while intervals:
        lower, upper = intervals.pop()
        work[0] += 1
        if work[0] > _MAX_INTERVAL_CHECKS:
            raise ValueError("world road mapping exceeded its interval-work budget")
        midpoint = 0.5 * (lower + upper)
        x_m, y_m = cell.wheel_position(
            midpoint, longitudinal_m, lateral_m,
        )
        if patch.contains(x_m, y_m):
            return True
        uncertainty = 0.5 * (upper - lower) * speed_bound
        if not _rectangles_overlap(
            x_m - uncertainty, x_m + uncertainty,
            y_m - uncertainty, y_m + uncertainty, patch,
        ):
            continue
        if uncertainty <= _CONTACT_RESOLUTION_M:
            # A false positive is at most this spatial uncertainty. Never
            # silently lose a possibly lower-grip contact between samples.
            return True
        intervals.append((midpoint, upper))
        intervals.append((lower, midpoint))
    return False


def world_patch_grip_schedule(
    track: SpatialTrack, vehicle: Vehicle, road: PlanarRoad,
) -> tuple[float, ...]:
    """Map assumed world-fixed low-grip rectangles onto one modeled path.

    Values are *absolute* tire-grip multipliers, ready for the per-cell path
    solver.  The road's base and patch factors multiply the vehicle's current
    reference multiplier.  The result is tied to this track and this car's
    nominal wheelbase/track widths; recompute for every AI trial and profile.
    No-patch roads return the exact uniform value without arc integration.
    """

    if not isinstance(track, SpatialTrack) or not track.closed:
        raise ValueError("world road mapping requires a closed SpatialTrack")
    if not isinstance(vehicle, Vehicle):
        raise TypeError("world road mapping requires a Vehicle")
    if not isinstance(road, PlanarRoad):
        raise TypeError("world road mapping requires a PlanarRoad")
    if track.cell_count > _MAX_CELLS:
        raise ValueError("world road mapping exceeds the 5000-cell compute cap")
    if len(road.patches) > _MAX_PATCHES:
        raise ValueError("world road mapping exceeds the 128-patch compute cap")
    if road.valid_domain is not None:
        raise ValueError("world road mapping cannot certify a bounded road domain")
    reference = vehicle.tire.road_grip_multiplier
    base = road.base_friction_multiplier
    if not isfinite(reference) or reference <= 0.0 or base <= 0.0:
        raise ValueError("world road grip factors must be finite and positive")
    if any(
        patch.friction_multiplier <= 0.0
        or patch.friction_multiplier > base
        for patch in road.patches
    ):
        raise ValueError("world road patches must be positive grip reductions")
    uniform = reference * base
    if not isfinite(uniform) or uniform <= 0.0:
        raise ValueError("world road schedule contains an invalid grip factor")
    if not road.patches:
        return (uniform,) * track.cell_count

    cells = _modeled_cells(track)
    wheel_offsets = _wheel_offsets(vehicle)
    maximum_offset = max(hypot(*offset) for offset in wheel_offsets)
    work = [0]
    schedule: list[float] = []
    for cell in cells:
        # A midpoint-centered circle conservatively contains the complete
        # CG arc and every nominal wheel center in this cell.
        middle_x, middle_y = cell.wheel_position(0.5 * cell.length_m, 0.0, 0.0)
        broad_radius = 0.5 * cell.length_m + maximum_offset
        local = base
        for patch in road.patches:
            if patch.friction_multiplier >= local or not _rectangles_overlap(
                middle_x - broad_radius, middle_x + broad_radius,
                middle_y - broad_radius, middle_y + broad_radius, patch,
            ):
                continue
            if any(
                _wheel_touches_patch(cell, offset, patch, work)
                for offset in wheel_offsets
            ):
                local = patch.friction_multiplier
        absolute = reference * local
        if not isfinite(absolute) or absolute <= 0.0:
            raise ValueError("world road schedule contains an invalid grip factor")
        schedule.append(absolute)
    return tuple(schedule)


__all__ = [
    "ROAD_GRIP_SCHEDULE_MAPPING_VERSION", "world_patch_grip_schedule",
]
