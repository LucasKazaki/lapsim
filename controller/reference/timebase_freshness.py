from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from typing import Iterable

COUNTER_BITS = 32
MODULUS = 1 << COUNTER_BITS
HALF_RANGE = 1 << (COUNTER_BITS - 1)
MAX_COUNTER = MODULUS - 1


@dataclass(frozen=True)
class TimebaseSpec:
    """Portable provenance for a timestamp domain.

    This is an evidence contract, not Terps Racing firmware configuration.
    """

    domain: str
    width_bits: int
    ticks_per_second: float
    monotonic: bool
    can_pause: bool


@dataclass(frozen=True)
class TimestampSample:
    label: str
    sample_tick: int
    now_tick: int
    max_age_ticks: int
    sample_timebase: TimebaseSpec
    now_timebase: TimebaseSpec


@dataclass(frozen=True)
class FreshnessResult:
    label: str
    status: str
    reason: str | None
    age_ticks: int | None
    future_lead_ticks: int | None
    max_age_ticks: int

    def as_record(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FreshnessSnapshot:
    all_fresh: bool
    results: tuple[FreshnessResult, ...]

    def as_record(self) -> dict[str, object]:
        return {
            "all_fresh": self.all_fresh,
            "results": [result.as_record() for result in self.results],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_record(), allow_nan=False, sort_keys=True, separators=(",", ":"))


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_timebase(spec: object) -> str | None:
    if not isinstance(spec, TimebaseSpec):
        return "invalid_timebase_object"
    if not isinstance(spec.domain, str) or not spec.domain.strip():
        return "invalid_timebase_domain"
    if not _is_int(spec.width_bits) or spec.width_bits != COUNTER_BITS:
        return "unsupported_counter_width"
    if not _is_number(spec.ticks_per_second) or not math.isfinite(float(spec.ticks_per_second)):
        return "invalid_tick_frequency"
    if float(spec.ticks_per_second) <= 0.0:
        return "invalid_tick_frequency"
    if type(spec.monotonic) is not bool or type(spec.can_pause) is not bool:
        return "invalid_timebase_flags"
    if not spec.monotonic:
        return "timebase_not_monotonic"
    if spec.can_pause:
        return "timebase_can_pause"
    return None


def _invalid(sample: TimestampSample, reason: str) -> FreshnessResult:
    max_age = sample.max_age_ticks if _is_int(sample.max_age_ticks) and sample.max_age_ticks >= 0 else 0
    return FreshnessResult(
        sample.label if isinstance(sample.label, str) else "",
        "invalid_timebase",
        reason,
        None,
        None,
        max_age,
    )


def classify_freshness(sample: TimestampSample) -> FreshnessResult:
    """Classify one timestamp only when both endpoints share one proven clock.

    The half-range rule orders wrapping unsigned 32-bit timestamps. Raw values
    from different clock domains or incompatible metadata are never subtracted.
    """

    if not isinstance(sample.label, str) or not sample.label.strip():
        return _invalid(sample, "invalid_label")

    left_fault = _validate_timebase(sample.sample_timebase)
    if left_fault:
        return _invalid(sample, f"sample_{left_fault}")
    right_fault = _validate_timebase(sample.now_timebase)
    if right_fault:
        return _invalid(sample, f"now_{right_fault}")

    if sample.sample_timebase.domain != sample.now_timebase.domain:
        return _invalid(sample, "timebase_domain_mismatch")
    if sample.sample_timebase.width_bits != sample.now_timebase.width_bits:
        return _invalid(sample, "timebase_width_mismatch")
    if not math.isclose(
        float(sample.sample_timebase.ticks_per_second),
        float(sample.now_timebase.ticks_per_second),
        rel_tol=0.0,
        abs_tol=0.0,
    ):
        return _invalid(sample, "timebase_frequency_mismatch")

    for name, value in (("sample_tick", sample.sample_tick), ("now_tick", sample.now_tick)):
        if not _is_int(value) or not 0 <= value <= MAX_COUNTER:
            return _invalid(sample, f"invalid_{name}")
    if not _is_int(sample.max_age_ticks) or not 0 <= sample.max_age_ticks < HALF_RANGE:
        return _invalid(sample, "invalid_max_age_ticks")

    delta = (sample.now_tick - sample.sample_tick) & MAX_COUNTER
    if delta == HALF_RANGE:
        return FreshnessResult(
            sample.label,
            "ambiguous",
            "half_range_ambiguity",
            None,
            None,
            sample.max_age_ticks,
        )
    if delta < HALF_RANGE:
        status = "fresh" if delta <= sample.max_age_ticks else "stale"
        reason = None if status == "fresh" else "age_exceeds_limit"
        return FreshnessResult(
            sample.label,
            status,
            reason,
            delta,
            None,
            sample.max_age_ticks,
        )

    future_lead = MODULUS - delta
    return FreshnessResult(
        sample.label,
        "future",
        "sample_is_future_dated",
        None,
        future_lead,
        sample.max_age_ticks,
    )


def evaluate_snapshot(samples: Iterable[TimestampSample]) -> FreshnessSnapshot:
    """Evaluate a generic critical-signal snapshot for offline replay.

    all_fresh is suitable only as a synthetic boolean input to other reference
    logic. It is not a real CAN-health, watchdog, or vehicle-safety decision.
    """

    sample_list = tuple(samples)
    labels = [sample.label for sample in sample_list]
    if any(not isinstance(label, str) or not label.strip() for label in labels):
        raise ValueError("all sample labels must be non-empty strings")
    if len(set(labels)) != len(labels):
        raise ValueError("duplicate sample labels")

    results = tuple(classify_freshness(sample) for sample in sample_list)
    return FreshnessSnapshot(
        bool(results) and all(result.status == "fresh" for result in results),
        results,
    )
