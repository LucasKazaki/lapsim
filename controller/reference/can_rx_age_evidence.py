"""TC-02X portable CAN receive-age evidence contract.

Synthetic host-side reference only. It does not read a CAN peripheral, define
Terps Racing CAN IDs or timeouts, command torque, or establish vehicle safety.

The target-specific fact encoded here is limited to the public STM32F405/407 and
STM32F415/417 erratum: bxCAN time-triggered communication mode is unsupported,
so its Rx-header timestamp must not be used as receive-time evidence on those
families.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json

COUNTER_BITS = 32
MODULUS = 1 << COUNTER_BITS
MAX_COUNTER = MODULUS - 1
HALF_RANGE = 1 << (COUNTER_BITS - 1)

TARGET_ERRATA_FAMILIES = {
    "STM32F405",
    "STM32F407",
    "STM32F415",
    "STM32F417",
}
CAPTURE_KINDS = {
    "software_isr_entry",
    "software_fifo_dequeue",
    "bxcan_ttcm_rxheader",
}
SOURCE_KINDS = {"scenario", "team_verified"}


class RxAgeEvidenceError(ValueError):
    pass


def _nonempty(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RxAgeEvidenceError(f"{path} must be a non-empty string")
    return value.strip()


def _u32(value: object, path: str) -> int:
    if type(value) is not int or not (0 <= value <= MAX_COUNTER):
        raise RxAgeEvidenceError(f"{path} must be an unsigned 32-bit integer")
    return value


def _age_bound(value: object, path: str, *, allow_none: bool) -> int | None:
    if value is None and allow_none:
        return None
    if type(value) is not int or not (0 <= value < HALF_RANGE):
        raise RxAgeEvidenceError(f"{path} must be an integer in [0, {HALF_RANGE})")
    return value


def _source_kind(value: object, path: str) -> str:
    if value not in SOURCE_KINDS:
        raise RxAgeEvidenceError(f"{path} must be scenario or team_verified")
    return str(value)


@dataclass(frozen=True)
class CaptureEvidence:
    mcu_family: str
    capture_kind: str
    capture_location: str
    capture_tick: int
    now_tick: int
    max_signal_age_ticks: int
    max_capture_lag_ticks: int | None
    timebase_domain: str
    timebase_source_kind: str
    lag_bound_source_kind: str
    target_car: str = "2027-28"

    def validated(self) -> "CaptureEvidence":
        family = _nonempty(self.mcu_family, "mcu_family")
        kind = _nonempty(self.capture_kind, "capture_kind")
        if kind not in CAPTURE_KINDS:
            raise RxAgeEvidenceError(f"unsupported capture_kind: {kind}")
        return CaptureEvidence(
            mcu_family=family,
            capture_kind=kind,
            capture_location=_nonempty(self.capture_location, "capture_location"),
            capture_tick=_u32(self.capture_tick, "capture_tick"),
            now_tick=_u32(self.now_tick, "now_tick"),
            max_signal_age_ticks=_age_bound(
                self.max_signal_age_ticks, "max_signal_age_ticks", allow_none=False
            ),
            max_capture_lag_ticks=_age_bound(
                self.max_capture_lag_ticks, "max_capture_lag_ticks", allow_none=True
            ),
            timebase_domain=_nonempty(self.timebase_domain, "timebase_domain"),
            timebase_source_kind=_source_kind(
                self.timebase_source_kind, "timebase_source_kind"
            ),
            lag_bound_source_kind=_source_kind(
                self.lag_bound_source_kind, "lag_bound_source_kind"
            ),
            target_car=_nonempty(self.target_car, "target_car"),
        )


@dataclass(frozen=True)
class ReceiveAgeResult:
    schema: str
    status: str
    reason: str
    observed_age_since_capture_ticks: int | None
    actual_age_min_ticks: int | None
    actual_age_max_ticks: int | None
    max_signal_age_ticks: int
    capture_kind: str
    target_erratum_blocks_timestamp: bool
    evidence_team_verified: bool
    ready_for_team_freshness_use: bool
    vehicle_acceptance_proven: bool = False
    action_authority: bool = False

    def to_json(self) -> str:
        return json.dumps(
            asdict(self), sort_keys=True, separators=(",", ":"), allow_nan=False
        )


def _wrapped_age(now_tick: int, capture_tick: int) -> int | None:
    delta = (now_tick - capture_tick) & MAX_COUNTER
    if delta >= HALF_RANGE:
        return None
    return delta


def evaluate_receive_age(evidence: CaptureEvidence) -> ReceiveAgeResult:
    """Evaluate an interval for true message age at `now_tick`.

    Software capture happens at or after physical frame reception. If capture lag
    is bounded by L, true age is therefore in [observed_age, observed_age + L].
    This can prove freshness only when the worst-case age remains within the
    reviewed signal-age limit.
    """

    e = evidence.validated()
    erratum_block = (
        e.mcu_family in TARGET_ERRATA_FAMILIES
        and e.capture_kind == "bxcan_ttcm_rxheader"
    )
    verified = (
        e.timebase_source_kind == "team_verified"
        and e.lag_bound_source_kind == "team_verified"
    )

    if erratum_block:
        return ReceiveAgeResult(
            schema="enme408-tc02x-can-rx-age/v1",
            status="invalid_timestamp_source",
            reason="stm32f405_407_415_417_bxcan_ttcm_timestamp_unavailable_by_erratum",
            observed_age_since_capture_ticks=None,
            actual_age_min_ticks=None,
            actual_age_max_ticks=None,
            max_signal_age_ticks=e.max_signal_age_ticks,
            capture_kind=e.capture_kind,
            target_erratum_blocks_timestamp=True,
            evidence_team_verified=False,
            ready_for_team_freshness_use=False,
        )

    observed = _wrapped_age(e.now_tick, e.capture_tick)
    if observed is None:
        return ReceiveAgeResult(
            schema="enme408-tc02x-can-rx-age/v1",
            status="ambiguous",
            reason="capture_to_now_half_range_or_future_ambiguity",
            observed_age_since_capture_ticks=None,
            actual_age_min_ticks=None,
            actual_age_max_ticks=None,
            max_signal_age_ticks=e.max_signal_age_ticks,
            capture_kind=e.capture_kind,
            target_erratum_blocks_timestamp=False,
            evidence_team_verified=verified,
            ready_for_team_freshness_use=False,
        )

    if e.max_capture_lag_ticks is None:
        return ReceiveAgeResult(
            schema="enme408-tc02x-can-rx-age/v1",
            status="unproven",
            reason="capture_lag_bound_missing",
            observed_age_since_capture_ticks=observed,
            actual_age_min_ticks=observed,
            actual_age_max_ticks=None,
            max_signal_age_ticks=e.max_signal_age_ticks,
            capture_kind=e.capture_kind,
            target_erratum_blocks_timestamp=False,
            evidence_team_verified=False,
            ready_for_team_freshness_use=False,
        )

    worst = observed + e.max_capture_lag_ticks
    if worst >= HALF_RANGE:
        return ReceiveAgeResult(
            schema="enme408-tc02x-can-rx-age/v1",
            status="ambiguous",
            reason="age_interval_crosses_half_range",
            observed_age_since_capture_ticks=observed,
            actual_age_min_ticks=observed,
            actual_age_max_ticks=None,
            max_signal_age_ticks=e.max_signal_age_ticks,
            capture_kind=e.capture_kind,
            target_erratum_blocks_timestamp=False,
            evidence_team_verified=verified,
            ready_for_team_freshness_use=False,
        )

    if observed > e.max_signal_age_ticks:
        status = "stale"
        reason = "even_minimum_age_exceeds_limit"
    elif worst <= e.max_signal_age_ticks:
        status = "fresh"
        reason = "worst_case_age_within_limit"
    else:
        status = "ambiguous"
        reason = "capture_lag_interval_crosses_freshness_limit"

    ready = status in {"fresh", "stale"} and verified
    return ReceiveAgeResult(
        schema="enme408-tc02x-can-rx-age/v1",
        status=status,
        reason=reason,
        observed_age_since_capture_ticks=observed,
        actual_age_min_ticks=observed,
        actual_age_max_ticks=worst,
        max_signal_age_ticks=e.max_signal_age_ticks,
        capture_kind=e.capture_kind,
        target_erratum_blocks_timestamp=False,
        evidence_team_verified=verified,
        ready_for_team_freshness_use=ready,
    )


def naive_dequeue_age(now_tick: int, dequeue_tick: int, max_age_ticks: int) -> bool:
    """Counterexample helper: freshness if dequeue time is mistaken for arrival time."""
    now = _u32(now_tick, "now_tick")
    dequeue = _u32(dequeue_tick, "dequeue_tick")
    limit = _age_bound(max_age_ticks, "max_age_ticks", allow_none=False)
    age = _wrapped_age(now, dequeue)
    return age is not None and age <= limit
