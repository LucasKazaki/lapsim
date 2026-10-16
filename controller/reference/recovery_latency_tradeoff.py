"""TC-02CE: sample-count recovery latency sensitivity, synthetic/offline only.

This is a probability model to aid *review*, not a fitted vehicle reliability
model or a torque-output algorithm. Successive samples are assumed IID Bernoulli
trials. ``p`` is the per-cycle chance that the *chosen* recovery contract is met.
No CAN, clock, driver request, firmware or safety-system interface is modeled.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

MAX_REQUIRED_SAMPLES = 16
MAX_HORIZON = 256


def _probability(p: object, name: str) -> float:
    if type(p) not in (int, float):
        raise ValueError(f"{name} must be an ordinary finite probability")
    try:
        value = float(p)
    except (ValueError, OverflowError):
        raise ValueError(f"{name} must be an ordinary finite probability") from None
    if not math.isfinite(value) or not (0.0 <= value <= 1.0):
        raise ValueError(f"{name} must be in [0, 1]")
    return value


def _count(value: object, name: str, maximum: int, *, allow_zero: bool = False) -> int:
    low = 0 if allow_zero else 1
    if type(value) is not int or not (low <= value <= maximum):
        raise ValueError(f"{name} must be an integer in [{low}, {maximum}]")
    return value


def expected_samples_to_qualify(p: float, required_samples: int) -> float:
    """Expected IID trials to get r consecutive successes, *in sample counts*.

    Derivation: E_r = 1/p + 1/p**2 + ... + 1/p**r.
    At p=0 this is infinite; at p=1 it is r. Overflow is represented by inf.
    """
    p = _probability(p, "p")
    required_samples = _count(required_samples, "required_samples", MAX_REQUIRED_SAMPLES)
    if p == 0.0:
        return math.inf
    term = 1.0
    total = 0.0
    for _ in range(required_samples):
        term /= p
        total += term
        if not math.isfinite(total):
            return math.inf
    return total


def probability_qualified_by(p: float, required_samples: int, horizon: int) -> float:
    """Exact finite-state IID probability of first run by horizon samples.

    States 0..r-1 retain the current consecutive-success streak; an r-th
    success is absorbed. No unbounded input traces or samples are allocated.
    """
    p = _probability(p, "p")
    r = _count(required_samples, "required_samples", MAX_REQUIRED_SAMPLES)
    horizon = _count(horizon, "horizon", MAX_HORIZON, allow_zero=True)
    states = [0.0] * r
    states[0] = 1.0
    absorbed = 0.0
    for _ in range(horizon):
        remaining = math.fsum(states)
        nxt = [0.0] * r
        nxt[0] = remaining * (1.0 - p)
        for k, weight in enumerate(states):
            if k + 1 == r:
                absorbed += weight * p
            else:
                nxt[k + 1] += weight * p
        states = nxt
    return max(0.0, min(1.0, absorbed))


@dataclass(frozen=True)
class RecoveryTradeoff:
    schema: str
    required_samples: int
    horizon_samples: int
    allocator_valid_probability: float
    end_to_end_valid_probability: float
    allocator_expected_samples: float
    qualified_expected_samples: float
    allocator_probability_by_horizon: float
    qualified_probability_by_horizon: float

    def as_json_record(self) -> dict[str, int | float | str | None]:
        """Strict-JSON-safe; infinite means recovery may never occur."""
        return {
            key: (None if type(value) is float and not math.isfinite(value) else value)
            for key, value in vars(self).items()
        }


def compare_recovery_latency(*, allocator_valid_probability: float,
                             end_to_end_valid_probability: float,
                             required_samples: int = 2,
                             horizon_samples: int = 10) -> RecoveryTradeoff:
    """Parameter sensitivity only, not a claim of measured event rates.

    The end-to-end-qualified event is a subset of the allocator-valid event,
    so its per-cycle probability cannot exceed allocator validity. Each policy
    is separately approximated by IID samples, *without* assuming independence
    between allocator and guard signals within a cycle.
    """
    a = _probability(allocator_valid_probability, "allocator_valid_probability")
    q = _probability(end_to_end_valid_probability, "end_to_end_valid_probability")
    r = _count(required_samples, "required_samples", MAX_REQUIRED_SAMPLES)
    h = _count(horizon_samples, "horizon_samples", MAX_HORIZON, allow_zero=True)
    if q > a:
        raise ValueError("end-to-end qualified event cannot be more probable than allocator validity")
    return RecoveryTradeoff(
        schema="enme408-tc02ce-recovery-latency-sensitivity/v1",
        required_samples=r, horizon_samples=h,
        allocator_valid_probability=a, end_to_end_valid_probability=q,
        allocator_expected_samples=expected_samples_to_qualify(a, r),
        qualified_expected_samples=expected_samples_to_qualify(q, r),
        allocator_probability_by_horizon=probability_qualified_by(a, r, h),
        qualified_probability_by_horizon=probability_qualified_by(q, r, h),
    )
