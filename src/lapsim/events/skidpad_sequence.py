"""Ordered Formula SAE skidpad development event with explicit rule selection.

The existing single-circle ``simulate_skidpad`` API remains unchanged. This
module runs one open prescribed path: entry, two right circles, two left
circles, exit. Repeated world positions have distinct ordered stations and
phase boundaries. This is not a pose-driver, admitted tournament worker or
official event result.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import ceil, fsum, hypot, isclose, isfinite, pi
from typing import Literal

from vehicle_model.vehicle import Vehicle

from ..core.profiles import ControlsProfile
from ..core.telemetry import Telemetry
from ..courses.course_bundle import course_geometry_sha256
from ..courses.spatial_track import SpatialTrack
from ..courses.track import Curve, Straight, Track
from .api import _require_controls_profile, _run_prescribed_path


INNER_DIAMETER_M = 15.25
OUTER_DIAMETER_M = 21.25
CIRCLE_CENTRE_SEPARATION_M = 18.25
LANE_WIDTH_M = 3.0
# A reproducible nominal route, not a rule requiring the car to use this line.
NOMINAL_PATH_RADIUS_M = (INNER_DIAMETER_M + OUTER_DIAMETER_M) / 4.0
MAX_SEQUENCE_CELLS = 5000
MAX_DECLARED_CONES = 1_000_000  # Software input bound, not an event-rule limit.

RULEBOOK_2026_URL = (
    "https://www.fsaeonline.com/cdsweb/gen/DownloadDocument.aspx?"
    "DocumentID=7de1794b-82d2-4ccd-ad4d-92fd2745bb89"
)
RULEBOOK_2027_V1_URL = (
    "https://www.fsaeonline.com/cdsweb/gen/DownloadDocument.aspx?"
    "DocumentID=da79bcb4-0935-4f7b-83d7-0dbb8ce68d38"
)
PENALTY_DISCREPANCY = (
    "The 2026 rulebook specifies 0.125 s/cone after averaging the timed laps; "
    "the 2026 event handbook reports 0.25 s/cone. Precedence is not resolved "
    "by this simulator. Select and record a policy explicitly."
)
ConePenaltyPolicy = Literal[
    "fsae_2026_rulebook",
    "fsae_2027_v1_rulebook",
    "fsae_2026_event_handbook",
]
_PENALTY_RATES = {
    "fsae_2026_rulebook": 0.125,
    "fsae_2027_v1_rulebook": 0.125,
    "fsae_2026_event_handbook": 0.25,
}
_PHASES = (
    ("entry", False, 0),
    ("right_untimed", False, -1),
    ("right_timed", True, -1),
    ("left_untimed", False, 1),
    ("left_timed", True, 1),
    ("exit", False, 0),
)


def _positive_number(value: float, name: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite positive number")
    try:
        number = float(value)
    except OverflowError as error:
        raise ValueError(f"{name} must be a finite positive number") from error
    if not isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be a finite positive number")
    return number


@dataclass(frozen=True, slots=True)
class SkidpadPhase:
    name: str
    timed: bool
    turn_direction: int
    first_cell: int
    end_cell: int
    start_distance_m: float
    end_distance_m: float


@dataclass(frozen=True, slots=True)
class SkidpadSequenceCourse:
    """Open nominal path with six contiguous, immutable cell ranges."""

    track: SpatialTrack
    phases: tuple[SkidpadPhase, ...]
    entry_length_m: float
    exit_length_m: float
    maximum_cell_length_m: float

    def __post_init__(self) -> None:
        entry = _positive_number(self.entry_length_m, "entry_length_m")
        exit_length = _positive_number(self.exit_length_m, "exit_length_m")
        step = _positive_number(self.maximum_cell_length_m, "maximum_cell_length_m")
        if type(self.track) is not SpatialTrack or self.track.closed is not False:
            raise ValueError("The ordered skidpad requires one open SpatialTrack")
        if any(
            type(channel) is not tuple
            for channel in (
                self.track.distance_m, self.track.x_m,
                self.track.y_m, self.track.curvature_per_m,
            )
        ):
            raise ValueError("Skidpad geometry channels must be immutable tuples")
        if not 6 <= self.track.cell_count <= MAX_SEQUENCE_CELLS:
            raise ValueError("Skidpad grid exceeds its bounded cell range")
        if type(self.phases) is not tuple or len(self.phases) != len(_PHASES):
            raise ValueError("Six immutable ordered skidpad phases are required")
        self.track.validate_coherent_arcs()
        cursor = 0
        for phase, (name, timed, direction) in zip(self.phases, _PHASES, strict=True):
            if (
                not isinstance(phase, SkidpadPhase)
                or phase.name != name
                or type(phase.timed) is not bool
                or phase.timed != timed
                or type(phase.turn_direction) is not int
                or phase.turn_direction != direction
                or type(phase.first_cell) is not int
                or type(phase.end_cell) is not int
                or phase.first_cell != cursor
                or not cursor < phase.end_cell <= self.track.cell_count
            ):
                raise ValueError("Skidpad phases must preserve the exact ordered cell ranges")
            if (
                phase.start_distance_m != self.track.distance_m[cursor]
                or phase.end_distance_m != self.track.distance_m[phase.end_cell]
            ):
                raise ValueError("Phase stations must be actual grid boundaries")
            lengths = self.track.cell_length_m[cursor:phase.end_cell]
            expected_length = (
                entry if name == "entry" else exit_length if name == "exit"
                else 2.0 * pi * NOMINAL_PATH_RADIUS_M
            )
            if not isclose(fsum(lengths), expected_length, rel_tol=1e-12, abs_tol=1e-9):
                raise ValueError("Skidpad phase length differs from its declared route")
            if any(length > step + 1e-9 for length in lengths):
                raise ValueError("Skidpad cells exceed the declared maximum length")
            expected_curvature = direction / NOMINAL_PATH_RADIUS_M
            if any(
                not isclose(value, expected_curvature, rel_tol=0.0, abs_tol=1e-14)
                for value in self.track.curvature_per_m[cursor:phase.end_cell]
            ):
                raise ValueError("Skidpad phase curvature or direction differs")
            if direction and phase.end_cell - cursor < 4:
                raise ValueError("Each full circle requires at least four nondegenerate cells")
            cursor = phase.end_cell
        if cursor != self.track.cell_count:
            raise ValueError("Skidpad phases must cover the whole path")
        if hypot(self.track.x_m[0] + entry, self.track.y_m[0]) > 1e-6:
            raise ValueError("Skidpad entry must approach the central tangent along +x")
        for phase in self.phases[:-1]:
            if hypot(self.track.x_m[phase.end_cell], self.track.y_m[phase.end_cell]) > 1e-6:
                raise ValueError("Each circle must return to the central tangent")
        if hypot(self.track.x_m[-1] - exit_length, self.track.y_m[-1]) > 1e-6:
            raise ValueError("Skidpad exit must continue forward along +x")

    @property
    def geometry_sha256(self) -> str:
        return course_geometry_sha256(self.track)

    @property
    def course_sha256(self) -> str:
        raw = json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        return sha256(raw).hexdigest()

    def to_dict(self) -> dict:
        """Return exact generated geometry and scenario/provenance declarations."""

        return {
            "schema": "lapsim.fsae-skidpad-sequence-course.v1",
            "classification": "RULE_DIMENSIONS_WITH_CHOSEN_NOMINAL_PRESCRIBED_ROUTE",
            "rule_sources": [RULEBOOK_2026_URL, RULEBOOK_2027_V1_URL],
            "rule_sections": "D.10.1-D.10.4",
            "dimensions_m": {
                "inner_diameter": INNER_DIAMETER_M,
                "outer_diameter": OUTER_DIAMETER_M,
                "circle_centre_separation": CIRCLE_CENTRE_SEPARATION_M,
                "lane_width": LANE_WIDTH_M,
                "chosen_nominal_path_radius": NOMINAL_PATH_RADIUS_M,
            },
            "coordinate_frame": "Central tangent at (0,0); entry/exit +x; left circle +y",
            "entry_and_exit_lengths_are_scenario_inputs": True,
            "entry_length_m": self.entry_length_m,
            "exit_length_m": self.exit_length_m,
            "maximum_cell_length_m": self.maximum_cell_length_m,
            "phases": [asdict(phase) for phase in self.phases],
            "geometry_sha256": self.geometry_sha256,
            "geometry": {
                "closed": False,
                "distance_m": list(self.track.distance_m),
                "x_m": list(self.track.x_m),
                "y_m": list(self.track.y_m),
                "curvature_per_m": list(self.track.curvature_per_m),
            },
            "surveyed_boundaries_or_racing_line_qualification": False,
            "shared_canonical_imported_course_artifact": False,
            "qualification_or_execution_authority": False,
        }


def standard_skidpad_sequence(
    *, entry_length_m: float, exit_length_m: float,
    maximum_cell_length_m: float = 0.5,
) -> SkidpadSequenceCourse:
    """Construct the ordered nominal path using rule-based circle dimensions.

    Entry/exit lengths are supplied scenario choices. The nominal 9.125 m
    radius is the midpoint of the rule diameters, not a prescribed racing line.
    Each circle remains a separate segment even when world coordinates repeat.
    """

    entry = _positive_number(entry_length_m, "entry_length_m")
    exit_length = _positive_number(exit_length_m, "exit_length_m")
    requested_step = _positive_number(maximum_cell_length_m, "maximum_cell_length_m")
    step = min(requested_step, 0.5 * pi * NOMINAL_PATH_RADIUS_M)
    circumference = 2.0 * pi * NOMINAL_PATH_RADIUS_M
    lengths = (entry, circumference, circumference, circumference, circumference, exit_length)
    ratios = tuple(length / step for length in lengths)
    if any(not isfinite(ratio) or not 0.0 < ratio <= MAX_SEQUENCE_CELLS for ratio in ratios):
        raise ValueError("Skidpad grid exceeds the 5000-cell compute cap")
    counts = tuple(ceil(ratio) for ratio in ratios)
    if sum(counts) > MAX_SEQUENCE_CELLS:
        raise ValueError("Skidpad grid exceeds the 5000-cell compute cap")
    track = SpatialTrack.from_track(
        Track.from_segments([
            Straight(entry),
            Curve(NOMINAL_PATH_RADIUS_M, -2.0 * pi),
            Curve(NOMINAL_PATH_RADIUS_M, -2.0 * pi),
            Curve(NOMINAL_PATH_RADIUS_M, 2.0 * pi),
            Curve(NOMINAL_PATH_RADIUS_M, 2.0 * pi),
            Straight(exit_length),
        ]),
        maximum_cell_length_m=step, closed=False, close_geometry=False,
    )
    # Move the explicit entry boundary to the central tangent frame. No
    # quantization or geometry-hash tolerance is introduced.
    track = SpatialTrack(
        distance_m=track.distance_m,
        x_m=tuple(value - entry for value in track.x_m),
        y_m=track.y_m,
        curvature_per_m=track.curvature_per_m,
        closed=False,
    )
    phases = []
    cursor = 0
    for (name, timed, direction), count in zip(_PHASES, counts, strict=True):
        end = cursor + count
        phases.append(SkidpadPhase(
            name, timed, direction, cursor, end,
            track.distance_m[cursor], track.distance_m[end],
        ))
        cursor = end
    return SkidpadSequenceCourse(track, tuple(phases), entry, exit_length, requested_step)


@dataclass(frozen=True, slots=True)
class SkidpadSequenceConfig:
    starting_speed_mps: float = 0.0
    maximum_driving_time_s: float = 120.0
    cone_count: int = 0
    cone_penalty_policy: ConePenaltyPolicy | None = None
    declared_dnf_reason: str | None = None

    def __post_init__(self) -> None:
        if type(self.starting_speed_mps) not in (int, float):
            raise ValueError("starting_speed_mps must be finite and nonnegative")
        try:
            speed = float(self.starting_speed_mps)
        except OverflowError as error:
            raise ValueError("starting_speed_mps must be finite and nonnegative") from error
        if not isfinite(speed) or speed < 0.0:
            raise ValueError("starting_speed_mps must be finite and nonnegative")
        _positive_number(self.maximum_driving_time_s, "maximum_driving_time_s")
        if type(self.cone_count) is not int or not 0 <= self.cone_count <= MAX_DECLARED_CONES:
            raise ValueError("cone_count must be an integer in the bounded recorded range")
        if self.cone_penalty_policy is not None and (
            type(self.cone_penalty_policy) is not str
            or self.cone_penalty_policy not in _PENALTY_RATES
        ):
            raise ValueError("Select an explicit supported cone-penalty policy or None")
        if self.declared_dnf_reason is not None and (
            type(self.declared_dnf_reason) is not str
            or not self.declared_dnf_reason.strip()
            or len(self.declared_dnf_reason) > 512
        ):
            raise ValueError("declared_dnf_reason must be nonempty bounded text or None")


@dataclass(frozen=True, slots=True)
class SkidpadPhaseTiming:
    name: str
    timed: bool
    start_time_s: float | None
    end_time_s: float | None
    observed_elapsed_time_s: float | None
    end_boundary_observed: bool


@dataclass(frozen=True, slots=True)
class SkidpadSequenceResult:
    """Raw prescribed-path timing; no event ranking or official points."""

    course_sha256: str
    geometry_sha256: str
    numerical_path_completed: bool
    path_failure_reason: str | None
    elapsed_time_s: float
    distance_m: float
    energy_kwh: float
    phase_timings: tuple[SkidpadPhaseTiming, ...]
    unpenalized_average_s: float | None
    corrected_time_s: float | None
    declared_cone_count: int
    cone_penalty_policy: ConePenaltyPolicy | None
    cone_penalty_s: float | None
    declared_dnf_reason: str | None
    scenario: SkidpadSequenceConfig
    telemetry: Telemetry

    def to_dict(self, *, include_telemetry: bool = False) -> dict:
        result = {
            "schema": "lapsim.fsae-skidpad-sequence-result.v1",
            "event": "fsae_skidpad_sequence_candidate",
            "course_sha256": self.course_sha256,
            "geometry_sha256": self.geometry_sha256,
            "numerical_path_completed": self.numerical_path_completed,
            "path_failure_reason": self.path_failure_reason,
            "elapsed_time_s": self.elapsed_time_s,
            "distance_m": self.distance_m,
            "energy_kwh": self.energy_kwh,
            "phase_timings": [asdict(phase) for phase in self.phase_timings],
            "unpenalized_average_s": self.unpenalized_average_s,
            "corrected_time_s": self.corrected_time_s,
            "declared_cone_count": self.declared_cone_count,
            "cone_penalty_policy": self.cone_penalty_policy,
            "cone_penalty_s": self.cone_penalty_s,
            "penalty_discrepancy": PENALTY_DISCREPANCY,
            "declared_dnf_reason": self.declared_dnf_reason,
            "scenario": asdict(self.scenario),
            "declarations_are_independently_verified": False,
            "vehicle_configuration_identity_bound": False,
            "control_profile_identity_bound": False,
            "matched_policy_or_vehicle_comparison_established": False,
            "shared_canonical_imported_course_artifact": False,
            "timing_scope": "ORDERED_PRESCRIBED_PATH_CELL_BOUNDARIES_NOT_PHYSICAL_GATE_RECEIPTS",
            "official_points": None,
            "event_ranking": None,
            "official_eligibility_established": False,
            "qualification_or_execution_authority": False,
        }
        if include_telemetry:
            result["telemetry"] = self.telemetry.as_dict()
        return result


def _phase_timings(
    course: SkidpadSequenceCourse, telemetry: Telemetry, *, completed: bool,
) -> tuple[SkidpadPhaseTiming, ...]:
    count = telemetry.sample_count
    if count == 0:
        if completed:
            raise ValueError("A completed skidpad path must retain every cell sample")
        return tuple(SkidpadPhaseTiming(p.name, p.timed, None, None, None, False) for p in course.phases)
    required = ("vehicle.time_s", "event.cell_index", "event.lap_index", "event.lap_distance_m")
    if any(name not in telemetry for name in required) or count > course.track.cell_count:
        raise ValueError("Skidpad phase timing requires complete aligned cell telemetry")
    times = telemetry["vehicle.time_s"]
    previous_time = 0.0
    for index in range(count):
        if (
            not isfinite(times[index]) or times[index] <= previous_time
            or telemetry["event.cell_index"][index] != index
            or telemetry["event.lap_index"][index] != 0.0
            or telemetry["event.lap_distance_m"][index] != course.track.distance_m[index + 1]
        ):
            raise ValueError("Skidpad telemetry cell order, station or time differs")
        previous_time = times[index]
    if completed and count != course.track.cell_count:
        raise ValueError("A completed skidpad path cannot omit cells")
    timings = []
    for phase in course.phases:
        start = 0.0 if phase.first_cell == 0 else (
            times[phase.first_cell - 1] if count >= phase.first_cell else None
        )
        end = times[phase.end_cell - 1] if count >= phase.end_cell else None
        latest = times[min(count, phase.end_cell) - 1] if count > phase.first_cell else start
        elapsed = None if start is None or latest is None else latest - start
        timings.append(SkidpadPhaseTiming(phase.name, phase.timed, start, end, elapsed, end is not None))
    return tuple(timings)


def simulate_skidpad_sequence(
    vehicle: Vehicle, course: SkidpadSequenceCourse, profile: ControlsProfile, *,
    config: SkidpadSequenceConfig | None = None,
) -> SkidpadSequenceResult:
    """Run the actual ordinary prescribed-path model once without phase resets.

    Cone count and DNF are explicit caller declarations, not detected events.
    An unselected penalty policy leaves corrected time unset, even with zero
    declared cones. No averages are accepted from an incomplete numerical run.
    """

    if not isinstance(course, SkidpadSequenceCourse):
        raise TypeError("course must be a SkidpadSequenceCourse")
    setup = config if config is not None else SkidpadSequenceConfig()
    if not isinstance(setup, SkidpadSequenceConfig):
        raise TypeError("config must be a SkidpadSequenceConfig")
    run = _run_prescribed_path(
        vehicle, course.track, _require_controls_profile(profile), laps=1,
        starting_speed_mps=setup.starting_speed_mps,
        maximum_driving_time_s=setup.maximum_driving_time_s,
    )
    timings = _phase_timings(course, run.telemetry, completed=run.completed)
    average = None
    if run.completed:
        durations = tuple(p.observed_elapsed_time_s for p in timings if p.timed)
        if len(durations) != 2 or any(value is None or value <= 0.0 for value in durations):
            raise ValueError("Both ordered timed circle boundaries are required")
        average = 0.5 * fsum(durations)
    rate = None if setup.cone_penalty_policy is None else _PENALTY_RATES[setup.cone_penalty_policy]
    penalty = None if rate is None else rate * setup.cone_count
    corrected = (
        average + penalty
        if average is not None and penalty is not None and setup.declared_dnf_reason is None
        else None
    )
    return SkidpadSequenceResult(
        course.course_sha256, course.geometry_sha256, run.completed,
        run.failure_reason, run.elapsed_time_s, run.distance_m, run.energy_kwh,
        timings, average, corrected, setup.cone_count, setup.cone_penalty_policy,
        penalty, setup.declared_dnf_reason, setup, run.telemetry,
    )


__all__ = [
    "SkidpadPhase", "SkidpadPhaseTiming", "SkidpadSequenceConfig",
    "SkidpadSequenceCourse", "SkidpadSequenceResult",
    "simulate_skidpad_sequence", "standard_skidpad_sequence",
]
