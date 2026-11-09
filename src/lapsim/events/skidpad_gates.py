"""Ordered finite CG gates from accepted model poses, not nominal stations.

This is a bounded development measurement. Between saved poses the CG follows
the endpoint chord; time and pack energy are interpolated on that chord only.
No full physical state is interpolated. Signed winding disambiguates repeated
central crossings. These are not authenticated receipts, track-bound checks,
body/cone clearance, or official skidpad eligibility.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import atan2, hypot, isfinite, pi


SCHEMA = "lapsim.ordered-skidpad-model-gates.v1"
RADIUS_M = 9.125
PHASES = ("ENTRY", "RIGHT_UNTIMED", "RIGHT_TIMED", "LEFT_UNTIMED", "LEFT_TIMED", "EXIT")
MAX_OBSERVATIONS = 10_001
MAX_STEP_DISTANCE_M = 1.0
MAX_STEP_ANGLE_RAD = pi / 4
# A directed finite central-plane intersection has x=0 and |y|<R, hence
# exactly the same polar angle at the start/end of each full-circle phase.
# 1e-6 rad covers accumulated binary64 angle sums over <=10000 intervals;
# it is not a path-width allowance, physical calibration, or hash rounding.
WINDING_CLOSURE_TOLERANCE_RAD = 1e-6
_MAX_COORDINATE_M = 10_000.0
_MAX_TIME_S = 10_000.0
_MAX_PACK_ENERGY_J = 1e12  # Software representation bound, not battery capacity.


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _number(value: object) -> bool:
    return type(value) in (int, float) and isfinite(value)


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class GatePose:
    tick: int
    time_s: float
    x_m: float
    y_m: float
    pack_energy_j: float
    state_sha256: str

    def __post_init__(self) -> None:
        _require(type(self.tick) is int and 0 <= self.tick < MAX_OBSERVATIONS,
                 "Gate pose tick is outside the bounded observation range")
        _require(_number(self.time_s) and 0 <= self.time_s <= _MAX_TIME_S,
                 "Gate pose time must be finite and bounded")
        _require(all(_number(v) and abs(v) <= _MAX_COORDINATE_M for v in (self.x_m, self.y_m)),
                 "Gate pose coordinates must be finite bounded metres")
        _require(_number(self.pack_energy_j) and 0 <= self.pack_energy_j <= _MAX_PACK_ENERGY_J,
                 "Gate pose pack energy must be finite and bounded")
        _require(type(self.state_sha256) is str and len(self.state_sha256) == 64 and
                 all(c in "0123456789abcdef" for c in self.state_sha256),
                 "Gate pose must retain an exact full-state SHA256 declaration")


class OrderedSkidpadGates:
    """Single ordered attempt; replay reconstructs measurements, not authority."""

    def __init__(self, exit_length_m: float, half_width_m: float = 1.5):
        _require(_number(exit_length_m) and 0 < exit_length_m <= _MAX_COORDINATE_M,
                 "Finite positive bounded exit length required")
        _require(_number(half_width_m) and 0 < half_width_m < RADIUS_M,
                 "Finite gate half-width must be positive and below the circle radius")
        self.exit_length_m = float(exit_length_m)
        self.half_width_m = float(half_width_m)
        self._trace: list[GatePose] = []
        self._crossings: list[dict] = []
        self._phase_index = 0
        self._winding = 0.0
        self._failure: str | None = None

    @property
    def completed(self) -> bool:
        return self._failure is None and self._phase_index == len(PHASES)

    @property
    def failure_reason(self) -> str | None:
        return self._failure

    @property
    def trace(self) -> tuple[GatePose, ...]:
        return tuple(self._trace)

    @property
    def crossings(self) -> tuple[dict, ...]:
        return tuple(deepcopy(self._crossings))

    def _fail(self, message: str) -> None:
        self._failure = message

    def _angle(self, a: tuple[float, float], b: tuple[float, float], centre_y: float) -> float | None:
        ax, ay = a[0], a[1] - centre_y
        bx, by = b[0], b[1] - centre_y
        if hypot(ax, ay) <= 1e-9 or hypot(bx, by) <= 1e-9:
            self._fail("Ambiguous winding at an active circle centre")
            return None
        angle = atan2(ax * by - ay * bx, ax * bx + ay * by)
        if abs(angle) > MAX_STEP_ANGLE_RAD:
            self._fail("Ambiguous excessive per-step winding angle")
            return None
        return angle

    def _add_winding(self, a: tuple[float, float], b: tuple[float, float]) -> bool:
        right = self._phase_index in (1, 2)
        angle = self._angle(a, b, -RADIUS_M if right else RADIUS_M)
        if angle is None:
            return False
        self._winding += angle
        signed = -self._winding if right else self._winding
        if signed < -MAX_STEP_ANGLE_RAD:
            self._fail("Wrong signed direction around the active circle")
        elif signed > 2*pi + MAX_STEP_ANGLE_RAD:
            self._fail("Required finite central gate was missed before another winding")
        return self._failure is None

    def _intersection(self, a: tuple[float, float], b: tuple[float, float], gate_x: float,
                      *, forward: bool = True) -> tuple[float, tuple[float, float]] | None:
        d0, d1 = a[0] - gate_x, b[0] - gate_x
        # Forward receipts stay half-open to avoid counting the departure from
        # a just-recorded plane twice. A reverse violation also includes an
        # exact on-plane start departing backwards; otherwise an accepted gate
        # endpoint could hide a reversal before the next required phase.
        crosses = d0 < 0 <= d1 if forward else (d0 > 0 >= d1 or d0 == 0 > d1)
        if not crosses:
            return None
        fraction = -d0 / (d1-d0)
        point = (gate_x, a[1] + fraction*(b[1]-a[1]))
        return (fraction, point) if abs(point[1]) <= self.half_width_m else None

    def _record(self, before: GatePose, after: GatePose, fraction: float) -> None:
        event = {
            "phase": PHASES[self._phase_index], "fraction": fraction,
            "time_s": before.time_s + fraction*(after.time_s-before.time_s),
            "pack_energy_j": before.pack_energy_j + fraction*(after.pack_energy_j-before.pack_energy_j),
            "before": asdict(before), "after": asdict(after),
            "signed_winding_rad": self._winding if self._phase_index in (1,2,3,4) else None,
            "gate_x_m": self.exit_length_m if self._phase_index == 5 else 0.0,
            "gate_half_width_m": self.half_width_m,
            "scope": "CG endpoint-chord intersection; time/pack interpolation only; full states retained by caller",
        }
        event["crossing_sha256"] = _digest(event)
        self._crossings.append(event)
        self._phase_index += 1
        self._winding = 0.0

    def observe(self, pose: GatePose) -> None:
        _require(type(pose) is GatePose, "Exact immutable GatePose required")
        _require(not self.completed and self._failure is None, "Gate attempt is terminal; no further observations")
        if not self._trace:
            _require(pose.tick == 0 and pose.x_m < 0, "Fresh gate trace must start at tick zero before ENTRY")
            self._trace.append(pose)
            return
        before = self._trace[-1]
        _require(pose.tick == before.tick + 1 and pose.time_s > before.time_s,
                 "Gate trace requires consecutive ticks and strictly increasing time")
        _require(len(self._trace) < MAX_OBSERVATIONS, "Gate trace observation bound exceeded")
        self._trace.append(pose)  # Keep the failure-triggering valid observation.
        a, b = (before.x_m, before.y_m), (pose.x_m, pose.y_m)
        if hypot(b[0]-a[0], b[1]-a[1]) > MAX_STEP_DISTANCE_M:
            self._fail("Ambiguous excessive per-step CG displacement")
            return
        start_fraction = 0.0
        if self._phase_index == 0:
            entry = self._intersection(a, b, 0.0)
            if entry is None:
                return
            start_fraction, a = entry
            self._record(before, pose, start_fraction)
        if self._phase_index in (1, 2, 3, 4):
            centre_y = -RADIUS_M if self._phase_index in (1, 2) else RADIUS_M
            if self._angle(a, b, centre_y) is None:
                return
            if self._intersection(a, b, 0.0, forward=False) is not None:
                self._fail("Wrong direction through the finite central gate")
                return
            central = self._intersection(a, b, 0.0)
            if central is None:
                self._add_winding(a, b)
                return
            local_fraction, intersection = central
            if not self._add_winding(a, intersection):
                return
            expected = -2*pi if self._phase_index in (1, 2) else 2*pi
            if abs(self._winding-expected) > WINDING_CLOSURE_TOLERANCE_RAD:
                self._fail("Finite central gate crossed without the required full ordered winding")
                return
            start_fraction += local_fraction*(1-start_fraction)
            self._record(before, pose, start_fraction)
            a = intersection
            if self._phase_index in (1, 2, 3, 4):
                self._add_winding(a, b)
                return
        if self._phase_index == 5:
            if self._intersection(a, b, 0.0, forward=False) is not None:
                self._fail("Returned through the central gate instead of taking EXIT")
                return
            exit_crossing = self._intersection(a, b, self.exit_length_m)
            if exit_crossing is not None:
                fraction, _ = exit_crossing
                self._record(before, pose, start_fraction + fraction*(1-start_fraction))

    def to_dict(self) -> dict:
        trace = [asdict(pose) for pose in self._trace]
        value = {
            "schema": SCHEMA, "radius_m": RADIUS_M,
            "circle_centres_xy_m": [[0.0, -RADIUS_M], [0.0, RADIUS_M]],
            "central_gate_origin_xy_m": [0.0, 0.0], "gate_forward_normal_xy": [1.0, 0.0],
            "exit_length_m": self.exit_length_m, "half_width_m": self.half_width_m,
            "phase_order": list(PHASES), "completed": self.completed,
            "failure_reason": self._failure,
            "next_phase": None if self.completed else PHASES[self._phase_index],
            "active_signed_winding_rad": self._winding,
            "trace": trace, "trace_sha256": _digest(trace),
            "crossings": list(self.crossings),
            "measurement_bounds": {"observations": MAX_OBSERVATIONS,
                "step_displacement_m": MAX_STEP_DISTANCE_M, "step_angle_rad": MAX_STEP_ANGLE_RAD,
                "winding_closure_tolerance_rad": WINDING_CLOSURE_TOLERANCE_RAD},
            "measurement_scope": "Ordered CG nominal gates and winding from accepted model poses using endpoint chords",
            "official_track_bound_or_cone_clearance_checked": False,
            "state_hashes_independently_authenticated": False,
            "qualification_or_execution_authority": False,
        }
        value["ledger_sha256"] = _digest(value)
        return value

    @classmethod
    def from_trace(cls, trace, *, exit_length_m: float, half_width_m: float = 1.5):
        _require(type(trace) in (tuple, list) and len(trace) <= MAX_OBSERVATIONS,
                 "Bounded complete gate-pose trace required")
        ledger = cls(exit_length_m, half_width_m)
        keys = set(GatePose.__dataclass_fields__)
        for item in trace:
            if type(item) is dict:
                _require(set(item) == keys, "Exact serialized GatePose fields required")
                item = GatePose(**item)
            ledger.observe(item)
        return ledger


__all__ = ["GatePose", "OrderedSkidpadGates"]
