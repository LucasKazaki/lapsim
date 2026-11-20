"""Bounded side-labeled cone data; source coordinates and colors stay distinct.

This module does not load the plant or qualify geometry. Michigan derivation is
an explicit synthetic training fixture, never a surveyed course edit.
"""

import json
from dataclasses import asdict, dataclass, replace
from math import fsum, pi

from lapsim.driver_runtime import digest

from .contracts import finite, pin
from .perception import Cone, assumed_cones

SCHEMA = "lapsim.driver-side-cone-map.v1"


def _text(value):
    if type(value) is not str or not 1 <= len(value) <= 512:
        raise ValueError("explicit bounded source metadata required")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate source JSON field")
        result[key] = value
    return result


def _decode(raw):
    if type(raw) is not bytes or len(raw) > 1048576:
        raise ValueError("bounded source bytes required")
    data = json.loads(raw, object_pairs_hook=_object)
    if type(data) is not dict:
        raise ValueError("source JSON object required")
    return data


@dataclass(frozen=True, slots=True)
class SideConeMap:
    course_id: str
    source_name: str
    source_sha256: str
    reference_course_sha256: str | None
    coordinate_frame: str
    direction: str
    label_origin: str
    method: str
    cones: tuple[Cone, ...]
    reversed: bool = False

    def __post_init__(self):
        for name in ("course_id", "source_name", "coordinate_frame", "method"):
            _text(getattr(self, name))
        pin(self.source_sha256)
        if self.reference_course_sha256 is not None:
            pin(self.reference_course_sha256)
        if (
            self.direction
            not in ("clockwise", "counterclockwise", "source_declared_forward")
            or type(self.reversed) is not bool
        ):
            raise ValueError("explicit source direction and reverse flag required")
        if self.label_origin not in (
            "source_provided_side_labels",
            "inferred_assumed_corridor_training_fixture",
        ):
            raise ValueError("side-label provenance required")
        if (
            type(self.cones) is not tuple
            or not 2 <= len(self.cones) <= 4096
            or any(type(c) is not Cone or c.side is None for c in self.cones)
        ):
            raise ValueError("bounded explicitly side-labeled cone tuple required")
        sides = {
            s: {(c.x_m, c.y_m) for c in self.cones if c.side == s}
            for s in ("left", "right")
        }
        if not all(sides.values()) or sides["left"] & sides["right"]:
            raise ValueError(
                "both sides required; same coordinate cannot have conflicting side labels"
            )

    def _metadata(self):
        return {k: v for k, v in asdict(self).items() if k != "cones"}

    @property
    def labeling_sha256(self):
        return digest(
            {
                "schema": "lapsim.cone-side-labeling.v1",
                **self._metadata(),
                "sides_in_source_order": [c.side for c in self.cones],
            }
        )

    def to_dict(self):
        return {
            "schema": SCHEMA,
            **asdict(self),
            "labeling_sha256": self.labeling_sha256,
        }

    @property
    def sha256(self):
        return digest(self.to_dict())

    @classmethod
    def from_bytes(cls, raw):
        data = _decode(raw)
        if (
            set(data) != {"schema", "labeling_sha256", *cls.__dataclass_fields__}
            or data["schema"] != SCHEMA
        ):
            raise ValueError("explicit side-cone map schema required")
        if type(data["cones"]) is not list or len(data["cones"]) > 4096:
            raise ValueError("bounded cone list required")
        values = {
            k: v
            for k, v in data.items()
            if k not in ("schema", "labeling_sha256", "cones")
        }
        layout = cls(**values, cones=tuple(Cone(**row) for row in data["cones"]))
        if layout.labeling_sha256 != data["labeling_sha256"]:
            raise ValueError("cone labeling provenance differs")
        return layout


def reverse_sides(layout):
    """Explicit data-only reverse view: swap side labels, retain all positions.

    This does not reverse or enable a simulator course session.
    """
    if type(layout) is not SideConeMap:
        raise TypeError("SideConeMap required")
    return replace(
        layout,
        reversed=not layout.reversed,
        cones=tuple(
            replace(c, side="right" if c.side == "left" else "left")
            for c in layout.cones
        ),
    )


def parse_fssim_cones(raw, *, source_name, course_id):
    """Read the checked-in FSSIM numeric point-list subset, not general YAML.

    Source labels are authoritative only within that source's declared forward
    convention. No color, global winding or approximate-course frame is guessed.
    Repeated source coordinates are retained; nothing is fit/resampled/deduped.
    """
    if type(raw) is not bytes or len(raw) > 1048576:
        raise ValueError("bounded FSSIM bytes required")
    result = {"cones_left": [], "cones_right": []}
    seen, key, pending = set(), None, None
    for line in raw.decode("utf-8").splitlines():
        if line and not line.startswith((" ", "-")):
            if pending is not None or ":" not in line:
                raise ValueError("incomplete coordinate or unsupported YAML field")
            key, _, inline = line.partition(":")
            if key in result and inline.strip():
                raise ValueError("cone fields require explicit point-list syntax")
            if key in seen:
                raise ValueError("duplicate YAML field")
            seen.add(key)
        elif key in result:
            if line.startswith("- - ") and pending is None:
                pending = float(line[4:])
            elif line.startswith("  - ") and pending is not None:
                result[key].append((pending, float(line[4:])))
                pending = None
            elif line.strip():
                raise ValueError("unsupported cone point-list syntax")
            if sum(map(len, result.values())) > 4096:
                raise ValueError("cone count exceeds bound")
    if pending is not None or any(not result[key] for key in result):
        raise ValueError("both complete labeled cone fields required")
    cones = tuple(
        Cone(x, y, side=side)
        for side, key in (("left", "cones_left"), ("right", "cones_right"))
        for x, y in result[key]
    )
    return SideConeMap(
        course_id,
        source_name,
        digest(raw),
        None,
        "source_native_xy_meters_assumed_by_existing_importer",
        "source_declared_forward",
        "source_provided_side_labels",
        "reuse_source_labels_and_all_coordinates_untransformed.v1",
        cones,
    )


def derive_training_fixture(raw, *, allow_synthetic=False):
    """Label the existing assumed-corridor fixture, preserving its coordinates.

    Refuse any existing/ambiguous boundary data instead of silently replacing it.
    Explicit direction must agree with the retained curvature/station order.
    The original course bytes and direction remain unchanged.
    """
    if allow_synthetic is not True:
        raise ValueError("explicit synthetic training fixture opt-in required")
    data = _decode(raw)
    if data.get("course_id") != "fsae_michigan_electric_2026_endurance_image":
        raise ValueError(
            "this derived fixture is scoped to the retained Michigan course"
        )
    if (
        any(
            k in data
            for k in (
                "cones",
                "cones_left",
                "cones_right",
                "boundaries",
                "left_boundary",
                "right_boundary",
            )
        )
        or data.get("boundary_status") != "absent"
    ):
        raise ValueError(
            "provided or ambiguous boundary/cone data must be inspected, never replaced"
        )
    frame = data.get("coordinate_frame", {})
    if (
        frame.get("type") != "local_cartesian_right_handed_xy"
        or frame.get("units") != "m"
    ):
        raise ValueError("declared metric right-handed frame required")
    direction = data.get("travel_direction")
    if direction not in ("clockwise", "counterclockwise"):
        raise ValueError("explicit course travel direction required")
    g, ai = data["geometry"], data["ai_defaults"]
    if (
        g.get("closed") is not True
        or g.get("model") != "piecewise_constant_curvature_arcs"
        or ai.get("width_source") != "assumed_uniform"
    ):
        raise ValueError("explicit closed geometry and assumed width required")
    d, x, y, k = (tuple(g[n]) for n in ("distance_m", "x_m", "y_m", "curvature_per_m"))
    if not 3 <= len(d) <= 100001 or len(k) != len(d) - 1:
        raise ValueError("bounded curvature/station geometry required")
    for value in k:
        finite(value, "course curvature")
    plain = assumed_cones(d, x, y, half_width_m=ai["half_width_m"])
    turn = fsum(c * (b - a) for a, b, c in zip(d[:-1], d[1:], k, strict=True))
    if abs(turn - (2 * pi if direction == "counterclockwise" else -2 * pi)) > 1e-6:
        raise ValueError("declared direction conflicts with ordered signed turn")
    cones = tuple(
        replace(c, side="left" if i % 2 == 0 else "right") for i, c in enumerate(plain)
    )
    return SideConeMap(
        data["course_id"],
        "configs/learning/michigan-2026-course.json",
        digest(raw),
        digest(raw),
        "retained_course_geometry_xy:" + digest(frame),
        direction,
        "inferred_assumed_corridor_training_fixture",
        "r05_assumed_cones_4m_unchanged_coordinates_left_normal_along_declared_order.v1",
        cones,
    )
