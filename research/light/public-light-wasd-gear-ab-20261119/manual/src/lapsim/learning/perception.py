"""Environment-side virtual cone perception with explicit clean/noisy setups.

TruthFrame/Cone stay inside the environment. Current policies receive cone-only
DriverObservation; historical feedback schemas are offline compatibility only.
These are synthetic models, not validated camera/lidar perception.
"""

import json
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from itertools import pairwise
from math import atan2, cos, hypot, pi, remainder, sin
from random import Random

from lapsim.driver_runtime import (
    CONE_ONLY_SCHEMA,
    CONE_STATE_SCHEMA,
    FRONT_OBSERVATION_SCHEMA,
    LEGACY_OBSERVATION_SCHEMA,
    OBSERVATION_SCHEMA,
    SIDE_OBSERVATION_SCHEMA,
)

from .contracts import Action, DriverObservation, finite


@dataclass(frozen=True, slots=True)
class SensorConfig:
    range_m: float = 30.0
    half_fov_rad: float = pi / 3.0
    range_noise_m: float = 0.15
    range_noise_fraction: float = 0.03
    bearing_noise_rad: float = pi / 180.0
    range_resolution_m: float = 0.25
    bearing_resolution_rad: float = pi / 360.0
    dropout: float = 0.1
    speed_noise_mps: float = 0.1
    yaw_noise_rad_s: float = 0.01
    # Driver clock remains 50 ms; legacy/noisy presets delay feedback one frame.
    frame_period_s: float = 0.05
    observation_schema: str = OBSERVATION_SCHEMA
    quantize: bool = True
    latency_frames: int = 1

    @classmethod
    def initial_michigan(cls):
        """Ideal front-and-side cones, excluding the rear half-plane."""
        return replace(
            cls.front_cones_clean(),
            observation_schema=CONE_ONLY_SCHEMA,
            half_fov_rad=pi / 2,
        )

    @classmethod
    def initial_michigan_state(cls):
        """Ideal explicit local feedback; slip proxy is not true friction."""
        return replace(cls.initial_michigan(),observation_schema=CONE_STATE_SCHEMA)

    @classmethod
    def side_cones_noisy(cls):
        return cls(observation_schema=CONE_ONLY_SCHEMA)

    @classmethod
    def front_cones_clean(cls):
        """Retained r05 color/side-agnostic v2 starter, explicitly selected."""
        return cls(
            observation_schema=FRONT_OBSERVATION_SCHEMA,
            range_noise_m=0.0,
            range_noise_fraction=0.0,
            bearing_noise_rad=0.0,
            dropout=0.0,
            speed_noise_mps=0.0,
            yaw_noise_rad_s=0.0,
            quantize=False,
            latency_frames=0,
        )

    @classmethod
    def front_cones_noisy(cls):
        """Same color-agnostic layout with configurable noisy perception later."""
        return cls(observation_schema=FRONT_OBSERVATION_SCHEMA)

    def __post_init__(self) -> None:
        if self.observation_schema not in (
            OBSERVATION_SCHEMA,
            LEGACY_OBSERVATION_SCHEMA,
            FRONT_OBSERVATION_SCHEMA,
            SIDE_OBSERVATION_SCHEMA,
            CONE_ONLY_SCHEMA,
            CONE_STATE_SCHEMA,
        ):
            raise ValueError("unsupported observation schema")
        for name in (
            "range_m",
            "half_fov_rad",
            "range_resolution_m",
            "bearing_resolution_rad",
            "frame_period_s",
        ):
            finite(getattr(self, name), name)
            if getattr(self, name) <= 0.0:
                raise ValueError(
                    "sensor range, field, resolution and timing must be positive"
                )
        for name in (
            "range_noise_m",
            "range_noise_fraction",
            "bearing_noise_rad",
            "speed_noise_mps",
            "yaw_noise_rad_s",
        ):
            finite(getattr(self, name), name)
            if getattr(self, name) < 0.0 or (
                self.observation_schema == LEGACY_OBSERVATION_SCHEMA
                and getattr(self, name) == 0.0
            ):
                raise ValueError(
                    "nonnegative current noise (positive legacy v1 noise) required"
                )
        finite(self.dropout, "dropout")
        if (
            type(self.quantize) is not bool
            or type(self.latency_frames) is not int
            or self.latency_frames not in (0, 1)
        ):
            raise ValueError("explicit quantization and 0/1 frame latency required")
        if not 0.0 <= self.dropout <= 1.0 or not 0.0 < self.half_fov_rad <= pi / 2.0:
            raise ValueError("invalid dropout or forward field of view")
        if not 1.0 <= self.range_m <= 100.0 or self.frame_period_s != 0.05:
            raise ValueError("bounded range and fixed 50 ms driver clock required")

    @property
    def sha256(self) -> str:
        return sha256(
            json.dumps(
                asdict(self), sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class Cone:
    x_m: float
    y_m: float
    color: str | None = None
    side: str | None = None

    def __post_init__(self) -> None:
        finite(self.x_m, "cone x")
        finite(self.y_m, "cone y")
        if self.color not in (None, "blue", "yellow"):
            raise ValueError("marking may be unknown, blue or yellow")
        if self.side not in (None, "left", "right"):
            raise ValueError("side must be explicitly left, right or unknown")


@dataclass(frozen=True, slots=True)
class TruthFrame:
    x_m: float
    y_m: float
    heading_rad: float
    speed_mps: float
    yaw_rate_rad_s: float
    applied_steering_rad: float = 0.0
    rear_left_slip_proxy: float = 0.0
    rear_right_slip_proxy: float = 0.0

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            finite(getattr(self, name), name)


def clip(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class Perception:
    def __init__(self, settings: SensorConfig, *, seed: int):
        if type(settings) is not SensorConfig or type(seed) is not int:
            raise TypeError("explicit sensor config and integer seed required")
        self.settings = settings
        self._random = Random(seed)
        self._pending = DriverObservation(
            (settings.range_m,) * 8 + ((0.,)*5 if settings.observation_schema==CONE_STATE_SCHEMA else ()) if settings.observation_schema in (CONE_ONLY_SCHEMA,CONE_STATE_SCHEMA)
            else (1.0, 0.0, 0.0) * 8 + (0.0,) * 5,
            observation_schema=settings.observation_schema,
        )

    def observe(
        self, cones: tuple[Cone, ...], truth: TruthFrame, previous: Action
    ) -> DriverObservation:
        if type(truth) is not TruthFrame or type(previous) is not Action:
            raise TypeError("environment truth and previous driver request required")
        if (
            type(cones) is not tuple
            or len(cones) > 4096
            or any(type(c) is not Cone for c in cones)
        ):
            raise ValueError("bounded immutable virtual cone map required")
        cfg, rng = self.settings, self._random
        if cfg.observation_schema in (CONE_ONLY_SCHEMA,CONE_STATE_SCHEMA) and cfg.range_m != 30.0:
            raise ValueError("distance-only v5 fixes a30m censoring range")
        front_only = cfg.observation_schema == FRONT_OBSERVATION_SCHEMA
        side_labeled = cfg.observation_schema in (
            SIDE_OBSERVATION_SCHEMA,
            CONE_ONLY_SCHEMA,
            CONE_STATE_SCHEMA,
        )
        detections: dict[str, list[tuple[float, float]]] = (
            {"left": [], "right": []}
            if side_labeled
            else ({"all": []} if front_only else {"blue": [], "yellow": []})
        )
        for cone in cones:
            if side_labeled and cone.side is None:
                raise ValueError(
                    "side-cone inputs require explicit course-side labels; color/bearing cannot substitute"
                )
            if not front_only and not side_labeled and cone.color is None:
                raise ValueError(
                    "legacy v1 requires explicit markings; use front-cones v2 for unlabeled cones"
                )
            dx, dy = cone.x_m - truth.x_m, cone.y_m - truth.y_m
            distance = hypot(dx, dy)
            bearing = remainder(atan2(dy, dx) - truth.heading_rad, 2 * pi)
            if (
                distance > cfg.range_m
                or abs(bearing) > cfg.half_fov_rad
                or rng.random() < cfg.dropout
            ):
                continue
            estimate_range = distance + rng.gauss(
                0.0, cfg.range_noise_m + cfg.range_noise_fraction * distance
            )
            estimate_bearing = bearing + rng.gauss(0.0, cfg.bearing_noise_rad)
            # The initial v2 profile deliberately bypasses added noise and quantization.
            if cfg.quantize:
                estimate_range = (
                    round(estimate_range / cfg.range_resolution_m)
                    * cfg.range_resolution_m
                )
                estimate_bearing = (
                    round(estimate_bearing / cfg.bearing_resolution_rad)
                    * cfg.bearing_resolution_rad
                )
            group = cone.side if side_labeled else ("all" if front_only else cone.color)
            detections[group].append(
                (
                    (clip(estimate_range, 0.0, cfg.range_m) if cfg.observation_schema in (CONE_ONLY_SCHEMA,CONE_STATE_SCHEMA)
                     else clip(estimate_range / cfg.range_m, 0.0, 1.0)),
                    clip(estimate_bearing / cfg.half_fov_rad),
                )
            )
        features: list[float] = []
        groups = (
            (("left", 4), ("right", 4))
            if side_labeled
            else ((("all", 8),) if front_only else (("blue", 4), ("yellow", 4)))
        )
        for group, count in groups:
            visible = sorted(detections[group])[:count]
            if cfg.observation_schema in (CONE_ONLY_SCHEMA,CONE_STATE_SCHEMA):
                # No bearing, presence, speed, action history, station or preview.
                # A missing slot is right-censored at30m, not a surveyed cone.
                features.extend(distance for distance, bearing in visible)
                features.extend((cfg.range_m,) * (count - len(visible)))
            else:
                for distance, bearing in visible:
                    features.extend((distance, bearing, 1.0))
                features.extend((1.0, 0.0, 0.0) * (count - len(visible)))
        if cfg.observation_schema == CONE_STATE_SCHEMA:
            features.extend((clip((truth.speed_mps+rng.gauss(0.,cfg.speed_noise_mps))/30.),
                             clip((truth.yaw_rate_rad_s+rng.gauss(0.,cfg.yaw_noise_rad_s))/2.),
                             clip(truth.applied_steering_rad/.4),clip(truth.rear_left_slip_proxy),clip(truth.rear_right_slip_proxy)))
        elif cfg.observation_schema != CONE_ONLY_SCHEMA:
            features.extend(
                (
                    clip(
                        (truth.speed_mps + rng.gauss(0.0, cfg.speed_noise_mps)) / 30.0
                    ),
                    clip(
                        (truth.yaw_rate_rad_s + rng.gauss(0.0, cfg.yaw_noise_rad_s))
                        / 2.0
                    ),
                    previous.steering,
                    previous.throttle,
                    previous.brake,
                )
            )
        current = DriverObservation(
            tuple(features), observation_schema=cfg.observation_schema
        )
        if cfg.latency_frames == 0:
            return current
        delivered, self._pending = self._pending, current
        return delivered


def assumed_cones(
    distance_m: tuple[float, ...],
    x_m: tuple[float, ...],
    y_m: tuple[float, ...],
    *,
    half_width_m: float,
    spacing_m: float = 4.0,
    marking_colors: tuple[str | None, str | None] = (None, None),
) -> tuple[Cone, ...]:
    """Virtual marks on the assumed corridor, not recovered/surveyed cones.

    Inputs must already be a validated closed course. Default marks are unlabeled;
    no historical Michigan color semantics are inferred. Explicit legacy/overlay
    labels require separate provenance. No generated global map reaches the policy.
    """
    from bisect import bisect_right

    finite(half_width_m, "half width")
    finite(spacing_m, "cone spacing")
    if (
        type(marking_colors) is not tuple
        or len(marking_colors) != 2
        or any(c not in (None, "blue", "yellow") for c in marking_colors)
    ):
        raise ValueError("two explicit or unknown marking colors required")
    if not 0.0 < half_width_m <= 20.0 or not 1.0 <= spacing_m <= 20.0:
        raise ValueError("invalid virtual cone spacing or width")
    if not 3 <= len(distance_m) <= 100001 or not len(distance_m) == len(x_m) == len(
        y_m
    ):
        raise ValueError("bounded closed course channels required")
    for channel in (distance_m, x_m, y_m):
        for value in channel:
            finite(value, "course geometry")
    if distance_m[0] != 0.0 or any(b <= a for a, b in pairwise(distance_m)):
        raise ValueError("strictly increasing course station required")
    if (
        hypot(x_m[-1] - x_m[0], y_m[-1] - y_m[0]) > 1e-6
        or distance_m[-1] / spacing_m > 2048
    ):
        raise ValueError("closed course or cone count bound violated")
    result: list[Cone] = []
    station = 0.0
    while station < distance_m[-1]:
        i = min(bisect_right(distance_m, station) - 1, len(distance_m) - 2)
        fraction = (station - distance_m[i]) / (distance_m[i + 1] - distance_m[i])
        heading = atan2(y_m[i + 1] - y_m[i], x_m[i + 1] - x_m[i])
        x = x_m[i] + fraction * (x_m[i + 1] - x_m[i])
        y = y_m[i] + fraction * (y_m[i + 1] - y_m[i])
        for sign, color in zip((1.0, -1.0), marking_colors, strict=True):
            result.append(
                Cone(
                    x - sign * half_width_m * sin(heading),
                    y + sign * half_width_m * cos(heading),
                    color,
                )
            )
        station += spacing_m
    return tuple(result)


def rear_wheel_slip_proxies(*,forward_speed_mps,yaw_rate_rad_s,left_lateral_m,right_lateral_m,wheel_radius_m,left_omega_rad_s,right_omega_rad_s):
    """Unsteered rear encoder/ground-speed mismatch, NOT measured friction.

    All coordinates are body-local. The explicit1m/s low-speed denominator is
    an observation-model assumption, not a change to the tire slip law.
    """
    values=(forward_speed_mps,yaw_rate_rad_s,left_lateral_m,right_lateral_m,wheel_radius_m,left_omega_rad_s,right_omega_rad_s)
    for value in values:finite(value,'explicit observed wheel geometry/state')
    if wheel_radius_m<=0 or left_lateral_m<=right_lateral_m:raise ValueError('positive radius and ordered lateral wheel positions required')
    result=[]
    for y,omega in ((left_lateral_m,left_omega_rad_s),(right_lateral_m,right_omega_rad_s)):
        contact=forward_speed_mps-yaw_rate_rad_s*y
        result.append(clip((wheel_radius_m*omega-contact)/max(abs(contact),1.)))
    return tuple(result)
