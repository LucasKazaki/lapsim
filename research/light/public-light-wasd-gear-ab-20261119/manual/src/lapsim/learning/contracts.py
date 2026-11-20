"""Small immutable contracts shared by training, evaluation and adapters."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite
from typing import TYPE_CHECKING

from lapsim.driver_runtime import (
    FEATURE_COUNT,
    OBSERVATION_SCHEMA,
    Action,
    DriverObservation,
)

__all__ = [
    "DRIVER_FRAME_PERIOD_S",
    "FEATURE_COUNT",
    "MICHIGAN_COURSE_ID",
    "OBSERVATION_SCHEMA",
    "RWD_PROFILE_ID",
    "TIME_TOLERANCE_S",
    "Action",
    "DriverObservation",
    "EpisodeResult",
    "TrainingConfig",
    "Trial",
    "driver_frame_budget",
    "finite",
    "pin",
]

if TYPE_CHECKING:
    from .perception import SensorConfig
    from .policy import Policy

MICHIGAN_COURSE_ID = "fsae_michigan_electric_2026_endurance_image"
RWD_PROFILE_ID = "mi26-rwd-lsd-source-family-r41"
DRIVER_FRAME_PERIOD_S = 0.05
TIME_TOLERANCE_S = 1e-9


def finite(value: float, name: str) -> None:
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError(name + " must be a finite number")


def pin(value: str) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError("expected a lowercase SHA256 identity")


def driver_frame_budget(maximum_time_s: float) -> int:
    """Whole fixed-clock frames within the cap; tolerance covers roundoff only.

    A fractional final frame is not executed. Budgets shorter than one driver
    frame are refused before owner entry instead of creating zero-step results.
    """
    finite(maximum_time_s, "maximum_time_s")
    if not DRIVER_FRAME_PERIOD_S <= maximum_time_s <= 350.0:
        raise ValueError("maximum_time_s must be between one 50 ms frame and 300 s")
    return floor((maximum_time_s + TIME_TOLERANCE_S) / DRIVER_FRAME_PERIOD_S)


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    """runs_per_generation is episodes per candidate, per generation.

    These are algorithmic ceilings, never an execution allocation. The owner
    must admit each batch and account for all concurrent workers in one lease.
    """

    course_id: str = MICHIGAN_COURSE_ID
    profile_id: str = RWD_PROFILE_ID
    runs_per_generation: int = 2
    generations: int = 5
    candidates: int = 8
    max_parallel: int = 2
    evaluation_runs: int = 8
    maximum_steps: int = 6000
    maximum_time_s: float = 300.0
    seed: int = 467
    initial_sigma: float = 0.25

    def __post_init__(self) -> None:
        limits = {
            "runs_per_generation": (1, 32),
            "generations": (1, 1000),
            "candidates": (4, 64),
            "max_parallel": (1, 8),
            "evaluation_runs": (4, 64),
            "maximum_steps": (1, 10000),
            "seed": (0, 100_000_000),
        }
        for name, (low, high) in limits.items():
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer in [{low}, {high}]")
        if self.max_parallel > self.candidates:
            raise ValueError("max_parallel cannot exceed candidate count")
        for name in ("maximum_time_s", "initial_sigma"):
            finite(getattr(self, name), name)
        if (
            not 0.0 < self.maximum_time_s <= 350.0
            or not 0.01 <= self.initial_sigma <= 1.0
        ):
            raise ValueError("invalid finite time or search spread")
        driver_frame_budget(self.maximum_time_s)
        if any(
            type(value) is not str or not value or len(value) > 128
            for value in (self.course_id, self.profile_id)
        ):
            raise ValueError("explicit course and RWD profile required")
        if (
            self.total_training_trials > 8192
            or self.total_control_step_ceiling > 10_000_000
        ):
            raise ValueError("configured campaign exceeds the source algorithm cap")

    @property
    def total_training_trials(self) -> int:
        return self.runs_per_generation * self.generations * self.candidates

    @property
    def total_control_step_ceiling(self) -> int:
        return (
            self.total_training_trials + 2 * self.evaluation_runs
        ) * self.maximum_steps


@dataclass(frozen=True, slots=True)
class Trial:
    trial_id: str
    phase: str
    generation: int
    candidate: int
    run: int
    seed: int
    policy: Policy | None
    policy_sha256: str
    course_sha256: str
    vehicle_sha256: str
    maximum_steps: int
    maximum_time_s: float
    sensor: SensorConfig
    scenario_sha256: str | None = None

    def __post_init__(self) -> None:
        from .perception import SensorConfig
        from .policy import Policy

        if self.phase not in ("train", "evaluate", "baseline") or not self.trial_id:
            raise ValueError("explicit trial identity and phase required")
        for name in ("generation", "candidate", "run", "seed"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError("nonnegative integer trial coordinates required")
        if type(self.maximum_steps) is not int or not 1 <= self.maximum_steps <= 10000:
            raise ValueError("bounded integer trial step cap required")
        finite(self.maximum_time_s, "trial time cap")
        if (
            not 0.0 < self.maximum_time_s <= 350.0
            or type(self.sensor) is not SensorConfig
        ):
            raise ValueError("bounded trial time and explicit sensor contract required")
        driver_frame_budget(self.maximum_time_s)
        for value in (self.course_sha256, self.vehicle_sha256, self.policy_sha256):
            pin(value)
        if self.scenario_sha256 is not None:
            pin(self.scenario_sha256)
        if self.phase == "baseline":
            if self.policy is not None:
                raise ValueError("baseline must retain its existing driver")
        elif (
            type(self.policy) is not Policy or self.policy.sha256 != self.policy_sha256
        ):
            raise ValueError("learned trial requires matching frozen policy bytes")
        elif self.policy.observation_schema != self.sensor.observation_schema:
            raise ValueError("trial policy and sensor observation schemas differ")

    @property
    def sensor_sha256(self) -> str:
        return self.sensor.sha256


@dataclass(frozen=True, slots=True)
class EpisodeResult:
    trial_id: str
    policy_sha256: str
    course_sha256: str
    vehicle_sha256: str
    reward: float
    progress_m: float
    elapsed_s: float
    valid_lap: bool
    termination: str
    steps: int
    backend: str
    sensor_sha256: str
    scenario_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.scenario_sha256 is not None:
            pin(self.scenario_sha256)
        for name in (
            "policy_sha256",
            "course_sha256",
            "vehicle_sha256",
            "sensor_sha256",
        ):
            pin(getattr(self, name))
        for name in ("reward", "progress_m", "elapsed_s"):
            finite(getattr(self, name), name)
        if (
            self.progress_m < 0.0
            or self.elapsed_s <= 0.0
            or type(self.steps) is not int
            or self.steps < 1
        ):
            raise ValueError("invalid episode accounting")
        if type(self.valid_lap) is not bool or self.valid_lap != (
            self.termination == "lap_complete"
        ):
            raise ValueError("valid lap and terminal reason disagree")
        if not self.trial_id or not self.backend or not self.termination:
            raise ValueError("explicit trial, backend and terminal reason required")
