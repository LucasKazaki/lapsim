"""Deterministic flat-road and wind inputs for the planar vehicle model.

These inputs are deliberately limited to a flat road.  A grip multiplier
changes the tire force cap, not tire stiffness, geometry, or normal load.
The constants and patch shapes are scenario assumptions, not measured data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite


def _valid_bounds(
    x_min_m: float, x_max_m: float, y_min_m: float, y_max_m: float
) -> None:
    if not all(isfinite(value) for value in (x_min_m, x_max_m, y_min_m, y_max_m)):
        raise ValueError("road bounds must be finite")
    if x_min_m >= x_max_m or y_min_m >= y_max_m:
        raise ValueError("road bounds must have positive width and height")


@dataclass(frozen=True, slots=True)
class RoadDomain:
    """Inclusive world-coordinate rectangle with reviewed road data."""

    x_min_m: float
    x_max_m: float
    y_min_m: float
    y_max_m: float

    def __post_init__(self) -> None:
        _valid_bounds(self.x_min_m, self.x_max_m, self.y_min_m, self.y_max_m)

    def contains(self, x_m: float, y_m: float) -> bool:
        return (
            self.x_min_m <= x_m <= self.x_max_m
            and self.y_min_m <= y_m <= self.y_max_m
        )


@dataclass(frozen=True, slots=True)
class RectangularGripPatch:
    """A world-fixed flat-road region with a local peak-friction multiplier."""

    x_min_m: float
    x_max_m: float
    y_min_m: float
    y_max_m: float
    friction_multiplier: float
    material_id: str = "grip_patch"

    def __post_init__(self) -> None:
        _valid_bounds(self.x_min_m, self.x_max_m, self.y_min_m, self.y_max_m)
        if not isfinite(self.friction_multiplier) or self.friction_multiplier < 0.0:
            raise ValueError("friction_multiplier must be finite and nonnegative")
        if not isinstance(self.material_id, str) or not self.material_id.strip():
            raise ValueError("material_id must be a nonempty string")

    def contains(self, x_m: float, y_m: float) -> bool:
        return (
            self.x_min_m <= x_m <= self.x_max_m
            and self.y_min_m <= y_m <= self.y_max_m
        )


@dataclass(frozen=True, slots=True)
class RoadSample:
    """Material sampled at one world-frame wheel contact center.

    If ``valid`` is false, the base-road multiplier is used as an explicit
    diagnostic fallback.  The resulting run must not be ranked as validated.
    """

    x_m: float
    y_m: float
    material_id: str
    friction_multiplier: float
    valid: bool


@dataclass(frozen=True, slots=True)
class PlanarRoad:
    """Flat road with uniform default grip and deterministic world-fixed patches.

    Patches are searched in tuple order, so the first patch owns a shared
    boundary.  No random draw, history update, or interpolation occurs during
    a numerical derivative evaluation.
    """

    base_material_id: str = "reference_pavement"
    base_friction_multiplier: float = 1.0
    patches: tuple[RectangularGripPatch, ...] = ()
    valid_domain: RoadDomain | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.base_material_id, str) or not self.base_material_id.strip():
            raise ValueError("base_material_id must be a nonempty string")
        if not isfinite(self.base_friction_multiplier) or self.base_friction_multiplier < 0.0:
            raise ValueError("base_friction_multiplier must be finite and nonnegative")
        if not isinstance(self.patches, tuple) or any(
            not isinstance(patch, RectangularGripPatch) for patch in self.patches
        ):
            raise ValueError("patches must be a tuple of RectangularGripPatch")
        if self.valid_domain is not None and not isinstance(self.valid_domain, RoadDomain):
            raise ValueError("valid_domain must be RoadDomain or None")

    def query(self, x_m: float, y_m: float) -> RoadSample:
        if not isfinite(x_m) or not isfinite(y_m):
            raise ValueError("road query coordinates must be finite")
        if self.valid_domain is not None and not self.valid_domain.contains(x_m, y_m):
            return RoadSample(
                x_m=x_m,
                y_m=y_m,
                material_id="outside_road_domain",
                friction_multiplier=self.base_friction_multiplier,
                valid=False,
            )
        for patch in self.patches:
            if patch.contains(x_m, y_m):
                return RoadSample(
                    x_m=x_m,
                    y_m=y_m,
                    material_id=patch.material_id,
                    friction_multiplier=patch.friction_multiplier,
                    valid=True,
                )
        return RoadSample(
            x_m=x_m,
            y_m=y_m,
            material_id=self.base_material_id,
            friction_multiplier=self.base_friction_multiplier,
            valid=True,
        )


@dataclass(frozen=True, slots=True)
class PlanarEnvironment:
    """Uniform world-frame wind, air density, drag area, and flat road.

    ``drag_area_m2=0`` disables aerodynamic force exactly.  Density has no
    effect on the motor or tires.  The drag law is an isotropic first model;
    it does not claim a measured crosswind side-force coefficient or downforce.
    """

    wind_world_x_mps: float = 0.0
    wind_world_y_mps: float = 0.0
    air_density_kgpm3: float = 1.225
    drag_area_m2: float = 0.0
    road: PlanarRoad = field(default_factory=PlanarRoad)

    def __post_init__(self) -> None:
        if not all(isfinite(value) for value in (
            self.wind_world_x_mps,
            self.wind_world_y_mps,
            self.air_density_kgpm3,
            self.drag_area_m2,
        )):
            raise ValueError("environment values must be finite")
        if self.air_density_kgpm3 <= 0.0:
            raise ValueError("air_density_kgpm3 must be positive")
        if self.drag_area_m2 < 0.0:
            raise ValueError("drag_area_m2 cannot be negative")
        if not isinstance(self.road, PlanarRoad):
            raise ValueError("road must be PlanarRoad")


DEFAULT_PLANAR_ENVIRONMENT = PlanarEnvironment()
