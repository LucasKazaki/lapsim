"""Generic, cell-discretized racing-line geometry."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import atan2, ceil, copysign, cos, fsum, hypot, isfinite, sin
from os import PathLike
from pathlib import Path
import csv

from .track import Curve, Straight, Track


_MAX_REFINED_CELL_COUNT = 100_000


@dataclass(frozen=True, slots=True)
class TrackGeometryAudit:
    """Observable distance and closure checks for a track's plotted coordinates.

    A straight chord cannot be longer than the distance travelled along its
    cell.  Positive chord excess therefore proves that at least one of the
    station or x/y channels is inconsistent; it does not identify which one.
    Closed-course turn and integrated-arc checks compare the saved curvature
    with the plotted chord directions. They are diagnostics, not corrections.
    The x/y winding sums turns between listed chord directions, including
    the seam; ``endpoint_separation_m`` independently reports a map gap.
    A zero-length first chord makes the integration heading undefined; any
    zero-length chord makes the x/y winding undefined. The dependent fields
    are then ``None``.
    """

    station_length_m: float
    xy_chord_length_m: float
    endpoint_separation_m: float
    cells_with_chord_excess: int
    total_chord_excess_m: float
    maximum_chord_excess_m: float
    curvature_signed_turn_rad: float | None = None
    xy_signed_winding_rad: float | None = None
    curvature_minus_xy_turn_rad: float | None = None
    curvature_integrated_closure_gap_m: float | None = None
    maximum_arc_chord_mismatch_m: float = 0.0


@dataclass(frozen=True, slots=True)
class SpatialTrack:
    """Cell-based racing line independent of any vehicle or scoring rules.

    Point channels contain ``cell_count + 1`` entries. Cell curvature contains
    one entry per interval. A closed track repeats its start point at the end;
    distance remains strictly increasing through the complete lap.
    """

    distance_m: tuple[float, ...]
    x_m: tuple[float, ...]
    y_m: tuple[float, ...]
    curvature_per_m: tuple[float, ...]
    closed: bool = True

    def __post_init__(self) -> None:
        point_count = len(self.distance_m)
        if point_count < 2:
            raise ValueError("A spatial track needs at least two points")
        if len(self.x_m) != point_count or len(self.y_m) != point_count:
            raise ValueError("x_m and y_m must match distance_m")
        if len(self.curvature_per_m) != point_count - 1:
            raise ValueError("curvature_per_m must contain one value per cell")
        channels = (
            self.distance_m,
            self.x_m,
            self.y_m,
            self.curvature_per_m,
        )
        if any(not all(isfinite(value) for value in channel) for channel in channels):
            raise ValueError("Spatial-track channels must be finite")
        if abs(self.distance_m[0]) > 1e-9:
            raise ValueError("distance_m must start at zero")
        if any(
            upper <= lower for lower, upper in zip(self.distance_m, self.distance_m[1:])
        ):
            raise ValueError("distance_m must be strictly increasing")

    @property
    def cell_count(self) -> int:
        return len(self.curvature_per_m)

    @property
    def length_m(self) -> float:
        return self.distance_m[-1]

    @property
    def cell_length_m(self) -> tuple[float, ...]:
        return tuple(
            upper - lower for lower, upper in zip(self.distance_m, self.distance_m[1:])
        )

    @property
    def cell_center_distance_m(self) -> tuple[float, ...]:
        return tuple(
            0.5 * (lower + upper)
            for lower, upper in zip(self.distance_m, self.distance_m[1:])
        )

    def refine(self, maximum_cell_length_m: float) -> "SpatialTrack":
        """Subdivide cells without changing their piecewise-constant curvature.

        Original cell boundaries and point coordinates remain exact members of
        the refined grid. Interior points lie on each original x/y chord. This
        preserves path length and each cell's integrated turn and curvature
        squared, unlike a new global grid that averages across boundaries.
        """

        if (
            isinstance(maximum_cell_length_m, bool)
            or not isfinite(maximum_cell_length_m)
            or maximum_cell_length_m <= 0.0
        ):
            raise ValueError("maximum_cell_length_m must be finite and positive")
        cell_lengths_m = self.cell_length_m
        if all(length <= maximum_cell_length_m for length in cell_lengths_m):
            return self

        subdivision_counts: list[int] = []
        total_cells = 0
        for length_m in cell_lengths_m:
            ratio = length_m / maximum_cell_length_m
            remaining = _MAX_REFINED_CELL_COUNT - total_cells
            if not isfinite(ratio) or ratio > remaining:
                raise ValueError("refined track exceeds the 100000-cell compute cap")
            count = ceil(ratio)
            total_cells += count
            subdivision_counts.append(count)

        distance_m = [self.distance_m[0]]
        x_m = [self.x_m[0]]
        y_m = [self.y_m[0]]
        curvature_per_m: list[float] = []
        for index, (lower_m, upper_m, curvature) in enumerate(
            zip(
                self.distance_m[:-1],
                self.distance_m[1:],
                self.curvature_per_m,
                strict=True,
            )
        ):
            count = subdivision_counts[index]
            delta_x_m = self.x_m[index + 1] - self.x_m[index]
            delta_y_m = self.y_m[index + 1] - self.y_m[index]
            for subdivision in range(1, count):
                fraction = subdivision / count
                distance_m.append(lower_m + fraction * (upper_m - lower_m))
                x_m.append(self.x_m[index] + fraction * delta_x_m)
                y_m.append(self.y_m[index] + fraction * delta_y_m)
            distance_m.append(upper_m)
            x_m.append(self.x_m[index + 1])
            y_m.append(self.y_m[index + 1])
            curvature_per_m.extend((curvature,) * count)

        return SpatialTrack(
            distance_m=tuple(distance_m),
            x_m=tuple(x_m),
            y_m=tuple(y_m),
            curvature_per_m=tuple(curvature_per_m),
            closed=self.closed,
        )

    def geometry_audit(self) -> TrackGeometryAudit:
        """Compare plotted x/y with solver distance and prescribed curvature.

        A small relative and absolute tolerance excludes ordinary floating
        point roundoff. This audit intentionally does not infer a new track or
        replace the source curvature used by the default lap model. The
        curvature-integrated gap follows exact constant-curvature arcs from
        the first plotted chord tangent without forcing the endpoint closed.
        It is therefore a geometric discrepancy, not a simulated car pose.
        """

        deltas = tuple(
            (upper_x - lower_x, upper_y - lower_y)
            for lower_x, upper_x, lower_y, upper_y in zip(
                self.x_m[:-1], self.x_m[1:],
                self.y_m[:-1], self.y_m[1:], strict=True
            )
        )
        chords = tuple(
            hypot(delta_x, delta_y) for delta_x, delta_y in deltas
        )
        cell_lengths_m = self.cell_length_m
        excess = tuple(
            max(chord - length, 0.0)
            for chord, length in zip(chords, cell_lengths_m, strict=True)
        )
        above_tolerance = tuple(
            amount > max(1e-6, 1e-6 * length)
            for amount, length in zip(excess, cell_lengths_m, strict=True)
        )
        signed_turn_rad = fsum(
            curvature * length
            for curvature, length in zip(
                self.curvature_per_m, cell_lengths_m, strict=True
            )
        )
        arc_chords: list[float] = []
        for length_m, curvature_per_m in zip(
            cell_lengths_m, self.curvature_per_m, strict=True
        ):
            half_turn_rad = 0.5 * curvature_per_m * length_m
            if abs(half_turn_rad) < 1e-6:
                half_turn_squared = half_turn_rad * half_turn_rad
                sinc = 1.0 - half_turn_squared / 6.0 + (
                    half_turn_squared * half_turn_squared / 120.0
                )
            else:
                sinc = sin(half_turn_rad) / half_turn_rad
            arc_chords.append(length_m * sinc)
        maximum_arc_chord_mismatch_m = max(
            abs(chord - abs(arc_chord))
            for chord, arc_chord in zip(chords, arc_chords, strict=True)
        )
        xy_winding_rad: float | None = None
        turn_difference_rad: float | None = None
        integrated_gap_m: float | None = None
        if self.closed and self.cell_count >= 3 and all(
            chord > 0.0 for chord in chords
        ):
            xy_winding_rad = fsum(
                atan2(
                    previous_x * current_y - previous_y * current_x,
                    previous_x * current_x + previous_y * current_y,
                )
                for (previous_x, previous_y), (current_x, current_y) in zip(
                    (deltas[-1], *deltas[:-1]), deltas, strict=True
                )
            )
            turn_difference_rad = signed_turn_rad - xy_winding_rad
        if self.closed and chords[0] > 0.0:
            heading_rad = atan2(deltas[0][1], deltas[0][0])
            arc_deltas_x: list[float] = []
            arc_deltas_y: list[float] = []
            for length_m, curvature_per_m, arc_chord_m in zip(
                cell_lengths_m, self.curvature_per_m, arc_chords, strict=True
            ):
                half_turn_rad = 0.5 * curvature_per_m * length_m
                mid_heading_rad = heading_rad + half_turn_rad
                arc_deltas_x.append(arc_chord_m * cos(mid_heading_rad))
                arc_deltas_y.append(arc_chord_m * sin(mid_heading_rad))
                heading_rad += 2.0 * half_turn_rad
            integrated_gap_m = hypot(fsum(arc_deltas_x), fsum(arc_deltas_y))
        return TrackGeometryAudit(
            station_length_m=self.length_m,
            xy_chord_length_m=sum(chords),
            endpoint_separation_m=hypot(
                self.x_m[-1] - self.x_m[0], self.y_m[-1] - self.y_m[0]
            ),
            cells_with_chord_excess=sum(above_tolerance),
            total_chord_excess_m=sum(
                amount for amount, counted in zip(excess, above_tolerance, strict=True)
                if counted
            ),
            maximum_chord_excess_m=max(excess),
            curvature_signed_turn_rad=signed_turn_rad,
            xy_signed_winding_rad=xy_winding_rad,
            curvature_minus_xy_turn_rad=turn_difference_rad,
            curvature_integrated_closure_gap_m=integrated_gap_m,
            maximum_arc_chord_mismatch_m=maximum_arc_chord_mismatch_m,
        )

    def wrap_distance_m(self, distance_m: float) -> float:
        """Wrap a station onto a closed lap, preserving an exact zero."""

        if not isfinite(distance_m):
            raise ValueError("distance_m must be finite")
        if not self.closed:
            if not 0.0 <= distance_m <= self.length_m:
                raise ValueError("distance is outside the open track")
            return distance_m
        return distance_m % self.length_m

    @classmethod
    def from_csv(
        cls,
        path: str | PathLike[str],
        *,
        closed: bool = True,
    ) -> "SpatialTrack":
        """Load point geometry and per-cell curvature from a portable CSV.

        Each row contains ``distance_m``, ``x_m``, and ``y_m``. The
        ``curvature_per_m`` value belongs to the cell beginning at that row;
        it must therefore be blank on the final endpoint row.
        """

        input_path = Path(path)
        with input_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        required = {"distance_m", "x_m", "y_m", "curvature_per_m"}
        if not rows:
            raise ValueError("Spatial-track CSV contains no rows")
        if not required.issubset(rows[0]):
            missing = ", ".join(sorted(required.difference(rows[0])))
            raise ValueError(f"Spatial-track CSV is missing columns: {missing}")
        if rows[-1]["curvature_per_m"].strip():
            raise ValueError("Final spatial-track CSV curvature must be blank")

        return cls(
            distance_m=tuple(float(row["distance_m"]) for row in rows),
            x_m=tuple(float(row["x_m"]) for row in rows),
            y_m=tuple(float(row["y_m"]) for row in rows),
            curvature_per_m=tuple(
                float(row["curvature_per_m"]) for row in rows[:-1]
            ),
            closed=closed,
        )

    def to_csv(self, path: str | PathLike[str]) -> Path:
        """Write the generic point/cell representation consumed by `from_csv`."""

        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(("distance_m", "x_m", "y_m", "curvature_per_m"))
            for index, (distance_m, x_m, y_m) in enumerate(
                zip(self.distance_m, self.x_m, self.y_m, strict=True)
            ):
                curvature = (
                    self.curvature_per_m[index]
                    if index < self.cell_count
                    else ""
                )
                writer.writerow((distance_m, x_m, y_m, curvature))
        return output_path.resolve()

    def to_track(self) -> Track:
        """Convert cells to the legacy straight/constant-curvature segments."""

        segments: list[Straight | Curve] = []
        for length_m, curvature in zip(
            self.cell_length_m,
            self.curvature_per_m,
            strict=True,
        ):
            if abs(curvature) <= 1e-15:
                segments.append(Straight(length_m))
            else:
                segments.append(
                    Curve(
                        radius_m=1.0 / abs(curvature),
                        span_rad=curvature * length_m,
                    )
                )
        return Track.from_segments(segments)

    @classmethod
    def from_track(
        cls,
        track: Track,
        *,
        maximum_cell_length_m: float = 2.0,
        closed: bool = True,
        close_geometry: bool = True,
    ) -> "SpatialTrack":
        """Discretize any straight/constant-curvature :class:`Track`.

        ``close_geometry`` distributes a small source-centerline closure error
        over the plotted x/y coordinates. It does not change distance or
        curvature and therefore does not change the physics.
        """

        if maximum_cell_length_m <= 0:
            raise ValueError("maximum_cell_length_m must be positive")

        cell_lengths_m: list[float] = []
        curvatures_per_m: list[float] = []
        for segment in track.segments:
            if segment.length_m <= 0:
                raise ValueError("Track segment lengths must be positive")
            cell_count = ceil(segment.length_m / maximum_cell_length_m)
            cell_length_m = segment.length_m / cell_count
            if isinstance(segment, Straight):
                curvature_per_m = 0.0
            elif isinstance(segment, Curve):
                if segment.radius_m <= 0 or segment.span_rad == 0:
                    raise ValueError("Curve radius and span must be nonzero")
                curvature_per_m = copysign(1.0 / segment.radius_m, segment.span_rad)
            else:
                raise TypeError(f"Unsupported segment type: {type(segment).__name__}")
            cell_lengths_m.extend([cell_length_m] * cell_count)
            curvatures_per_m.extend([curvature_per_m] * cell_count)

        distance_m = [0.0]
        x_m = [0.0]
        y_m = [0.0]
        heading_rad = 0.0
        for cell_length_m, curvature_per_m in zip(
            cell_lengths_m, curvatures_per_m, strict=True
        ):
            distance_m.append(distance_m[-1] + cell_length_m)
            if abs(curvature_per_m) <= 1e-15:
                x_m.append(x_m[-1] + cell_length_m * cos(heading_rad))
                y_m.append(y_m[-1] + cell_length_m * sin(heading_rad))
                continue
            next_heading_rad = heading_rad + curvature_per_m * cell_length_m
            x_m.append(
                x_m[-1] + (sin(next_heading_rad) - sin(heading_rad)) / curvature_per_m
            )
            y_m.append(
                y_m[-1] - (cos(next_heading_rad) - cos(heading_rad)) / curvature_per_m
            )
            heading_rad = next_heading_rad

        if closed and close_geometry:
            end_x_m = x_m[-1] - x_m[0]
            end_y_m = y_m[-1] - y_m[0]
            total_length_m = distance_m[-1]
            for index, station_m in enumerate(distance_m):
                fraction = station_m / total_length_m
                x_m[index] -= fraction * end_x_m
                y_m[index] -= fraction * end_y_m

        return cls(
            distance_m=tuple(distance_m),
            x_m=tuple(x_m),
            y_m=tuple(y_m),
            curvature_per_m=tuple(curvatures_per_m),
            closed=closed,
        )

    @classmethod
    def from_cells(
        cls,
        *,
        cell_length_m: Sequence[float],
        curvature_per_m: Sequence[float],
        closed: bool = True,
    ) -> "SpatialTrack":
        """Build generic geometry directly from cell lengths and curvature."""

        if len(cell_length_m) != len(curvature_per_m) or not cell_length_m:
            raise ValueError(
                "Cell lengths and curvature must have equal nonzero length"
            )
        segments: list[Straight | Curve] = []
        for length_m, curvature in zip(cell_length_m, curvature_per_m, strict=True):
            if length_m <= 0:
                raise ValueError("Cell lengths must be positive")
            if abs(curvature) <= 1e-15:
                segments.append(Straight(float(length_m)))
            else:
                segments.append(
                    Curve(
                        radius_m=1.0 / abs(float(curvature)),
                        span_rad=float(curvature) * float(length_m),
                    )
                )
        return cls.from_track(
            Track.from_segments(segments),
            maximum_cell_length_m=max(float(value) for value in cell_length_m),
            closed=closed,
        )


__all__ = ["SpatialTrack", "TrackGeometryAudit"]
