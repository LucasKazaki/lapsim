"""TC-02CV: finite-horizon IID recovery probability evidence in log space.

Offline analysis, not a torque command generator or real sensor reliability model.
The probability of a qualified sample is hypothetical and IID; the first
observation begins at a streak length of zero. Inputs match TC-02CE bounds.
This is an additive numerical diagnostic: the published reference is unchanged.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math

from recovery_latency_tradeoff import probability_qualified_by

NEG_INF = -math.inf
LN10 = math.log(10.0)


def _logadd(a: float, b: float) -> float:
    """Stable log(exp(a)+exp(b)), including zero-mass (-inf) terms."""
    if a == NEG_INF:
        return b
    if b == NEG_INF:
        return a
    if a < b:
        a, b = b, a
    return a + math.log1p(math.exp(b - a))


def _logsum(values: list[float]) -> float:
    total = NEG_INF
    for value in values:
        total = _logadd(total, value)
    return total


@dataclass(frozen=True)
class HorizonProbabilityEvidence:
    schema: str
    model: str
    qualification_probability: float
    required_consecutive_observations: int
    horizon_observations: int
    baseline_float_probability: float
    log10_hit_probability: float | None
    log10_no_hit_probability: float | None
    classification: str

    def as_json_record(self) -> dict[str, str | int | float | None]:
        """Strict-JSON-safe probabilities with explicit impossibility markers."""
        return asdict(self)


def classify_horizon_probability(p: float, required: int, horizon: int) -> HorizonProbabilityEvidence:
    """Report log10 probability of >=1 r-success streak within n observations.

    Uses a finite-state absorbing-chain DP in log space. Float log outputs are
    approximations (not exact rational values). If p is strictly between zero
    and one and n>=r, the mathematical event and its complement are both
    possible even when the baseline binary64 representation is 0.0 or 1.0.
    """
    baseline = probability_qualified_by(p, required, horizon)  # validates inputs
    p = float(p)
    prefix = dict(
        schema="enme408-tc02cv-horizon-probability-evidence/v1",
        model="iid_bernoulli_synthetic",
        qualification_probability=p,
        required_consecutive_observations=required,
        horizon_observations=horizon,
        baseline_float_probability=baseline,
    )
    if horizon < required or p == 0.0:
        return HorizonProbabilityEvidence(**prefix, log10_hit_probability=None,
                                          log10_no_hit_probability=0.0,
                                          classification="mathematically_impossible")
    if p == 1.0:
        return HorizonProbabilityEvidence(**prefix, log10_hit_probability=0.0,
                                          log10_no_hit_probability=None,
                                          classification="mathematically_certain")

    log_p = math.log(p)
    log_not_p = math.log1p(-p)
    states = [NEG_INF] * required
    states[0] = 0.0
    log_hit = NEG_INF
    for _ in range(horizon):
        next_states = [NEG_INF] * required
        next_states[0] = _logsum(states) + log_not_p
        for streak, weight in enumerate(states):
            if weight == NEG_INF:
                continue
            hit_weight = weight + log_p
            if streak == required - 1:
                log_hit = _logadd(log_hit, hit_weight)
            else:
                next_states[streak + 1] = _logadd(next_states[streak + 1], hit_weight)
        states = next_states
    log_no_hit = _logsum(states)
    if log_hit == NEG_INF or log_no_hit == NEG_INF:
        raise ArithmeticError("positive-mass event lost despite interior probability")
    # Floating-point addition can make a value slightly above log(1)=0.
    log_hit = min(log_hit, 0.0)
    log_no_hit = min(log_no_hit, 0.0)
    if baseline == 0.0:
        category = "positive_but_float_underflow"
    elif baseline == 1.0:
        category = "not_certain_but_float_rounded_to_one"
    else:
        category = "finite_float_representable"
    return HorizonProbabilityEvidence(
        **prefix,
        log10_hit_probability=log_hit / LN10,
        log10_no_hit_probability=log_no_hit / LN10,
        classification=category,
    )
