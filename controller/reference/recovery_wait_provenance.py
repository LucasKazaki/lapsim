"""TC-02CS: JSON-safe evidence about IID recovery-wait overflow.

Synthetic, offline postprocessing only. Does not alter the frozen TC-02CE model,
choose fault recovery policies, or emit vehicle commands. A positive Bernoulli
qualification probability implies a finite mathematical expected wait for a
finite required run, even when that number exceeds Python float range.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict

from recovery_latency_tradeoff import expected_samples_to_qualify


@dataclass(frozen=True)
class WaitEstimateEvidence:
    schema: str
    qualification_probability: float
    required_consecutive_observations: int
    expected_observations: float | None
    log10_expected_observations: float | None
    classification: str

    def as_json_record(self) -> dict[str, str | int | float | None]:
        """Strict JSON-compatible with no NaN, infinity or silent null meaning."""
        return asdict(self)


def classify_wait_estimate(p: float, required: int) -> WaitEstimateEvidence:
    """Classify true impossibility separately from float-range overflow.

    Let E = sum_{k=1}^required p^(-k) for 0 < p <= 1.
    log10(E) is computed via base-10 log-sum-exp to avoid overflowing the
    intermediate powers. All quantities are dimensionless observation counts.
    """
    estimate = expected_samples_to_qualify(p, required)  # original validation
    p = float(p)
    if p == 0.0:
        return WaitEstimateEvidence(
            "enme408-tc02cs-wait-evidence/v1", p, required,
            None, None, "impossible_when_probability_zero",
        )

    logp = -math.log10(p)
    exponents = [k * logp for k in range(1, required + 1)]
    largest = exponents[-1]
    log10_wait = largest + math.log10(math.fsum(10.0 ** (e - largest) for e in exponents))
    finite = math.isfinite(estimate)
    return WaitEstimateEvidence(
        "enme408-tc02cs-wait-evidence/v1", p, required,
        estimate if finite else None, log10_wait,
        "finite_representable" if finite else "finite_float_overflow",
    )
