"""TC-03B35 portable command-publication age evidence.

Offline/synthetic reference only.

Purpose:
- measure intent-to-terminal-transmit age in one verified wrapping timebase;
- keep command age and command supersession as separate evidence dimensions;
- preserve STM32-style 32-bit wrap semantics without assuming a Terps Racing
  timeout or clock implementation.

The current STM32F4 HAL uses a uint32_t global `uwTick`; HAL_GetTick() returns
that value, and HAL_Delay() computes elapsed time with unsigned subtraction:
    HAL_GetTick() - tickstart
The default HAL timebase is documented as milliseconds, but HAL timebase
functions are weak/overridable and the tick interrupt can be suspended.

This model therefore requires explicit timebase provenance rather than assuming
the target firmware uses an uninterrupted default HAL tick.

It does not:
- define a Terps Racing command deadline;
- select abort/retransmission behavior;
- prove inverter receipt/application;
- command torque;
- replace an independent shutdown/safety system;
- establish vehicle acceptance.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math

COUNTER_BITS = 32
MODULUS = 1 << COUNTER_BITS
MAX_COUNTER = MODULUS - 1
HALF_RANGE = 1 << (COUNTER_BITS - 1)

TERMINAL_RESULTS = {
    "transmitted",
    "arbitration_lost",
    "transmit_error",
    "aborted",
}
SOURCE_KINDS = {"scenario", "team_verified"}


class TxAgeEvidenceError(ValueError):
    pass


def _u32(value: object, name: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_COUNTER:
        raise TxAgeEvidenceError(f"{name} must be an unsigned 32-bit integer")
    return value


def _positive_seq(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise TxAgeEvidenceError(f"{name} must be a positive integer")
    return value


def _strict_bool(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise TxAgeEvidenceError(f"{name} must be boolean")
    return value


def _finite_positive(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TxAgeEvidenceError(f"{name} must be a positive finite number")
    x = float(value)
    if not math.isfinite(x) or x <= 0.0:
        raise TxAgeEvidenceError(f"{name} must be a positive finite number")
    return x


def _source_kind(value: object, name: str) -> str:
    if value not in SOURCE_KINDS:
        raise TxAgeEvidenceError(f"{name} must be scenario or team_verified")
    return str(value)


@dataclass(frozen=True)
class TimebaseEvidence:
    domain: str
    width_bits: int
    ticks_per_second: float
    monotonic: bool
    can_pause: bool
    source_kind: str = "scenario"

    def checked(self) -> "TimebaseEvidence":
        if not isinstance(self.domain, str) or not self.domain.strip():
            raise TxAgeEvidenceError("timebase domain must be non-empty")
        if type(self.width_bits) is not int or self.width_bits != COUNTER_BITS:
            raise TxAgeEvidenceError("timebase width_bits must be 32")
        return TimebaseEvidence(
            domain=self.domain.strip(),
            width_bits=self.width_bits,
            ticks_per_second=_finite_positive(
                self.ticks_per_second, "ticks_per_second"
            ),
            monotonic=_strict_bool(self.monotonic, "monotonic"),
            can_pause=_strict_bool(self.can_pause, "can_pause"),
            source_kind=_source_kind(
                self.source_kind, "timebase source_kind"
            ),
        )


@dataclass(frozen=True)
class TxPublicationAgeObservation:
    command_seq: int
    latest_intent_seq_at_terminal: int
    intent_tick: int
    terminal_tick: int
    max_age_ticks: int
    terminal_result: str
    command_bound_terminal_evidence: bool
    timebase: TimebaseEvidence
    max_age_source_kind: str = "scenario"

    def checked(self) -> "TxPublicationAgeObservation":
        seq = _positive_seq(self.command_seq, "command_seq")
        latest = _positive_seq(
            self.latest_intent_seq_at_terminal,
            "latest_intent_seq_at_terminal",
        )
        if seq > latest:
            raise TxAgeEvidenceError(
                "command_seq cannot exceed latest_intent_seq_at_terminal"
            )
        if type(self.max_age_ticks) is not int or not (
            0 <= self.max_age_ticks < HALF_RANGE
        ):
            raise TxAgeEvidenceError(
                f"max_age_ticks must be an integer in [0, {HALF_RANGE})"
            )
        if self.terminal_result not in TERMINAL_RESULTS:
            raise TxAgeEvidenceError("unsupported terminal_result")
        return TxPublicationAgeObservation(
            command_seq=seq,
            latest_intent_seq_at_terminal=latest,
            intent_tick=_u32(self.intent_tick, "intent_tick"),
            terminal_tick=_u32(self.terminal_tick, "terminal_tick"),
            max_age_ticks=self.max_age_ticks,
            terminal_result=self.terminal_result,
            command_bound_terminal_evidence=_strict_bool(
                self.command_bound_terminal_evidence,
                "command_bound_terminal_evidence",
            ),
            timebase=self.timebase.checked()
            if isinstance(self.timebase, TimebaseEvidence)
            else (_ for _ in ()).throw(
                TxAgeEvidenceError("timebase must be TimebaseEvidence")
            ),
            max_age_source_kind=_source_kind(
                self.max_age_source_kind, "max_age_source_kind"
            ),
        )


@dataclass(frozen=True)
class TxPublicationAgeAssessment:
    schema: str
    command_seq: int
    latest_intent_seq_at_terminal: int
    terminal_result: str
    status: str
    age_ticks: int | None
    age_seconds: float | None
    max_age_ticks: int
    publication_within_age_limit: bool | None
    superseded_publication_observed: bool
    command_bound_terminal_evidence: bool
    timebase_source_kind: str
    max_age_source_kind: str
    ready_for_team_timing_use: bool
    reason: str

    abort_policy_selected: bool = False
    retransmission_policy_change_selected: bool = False
    inverter_delivery_proven: bool = False
    inverter_application_proven: bool = False
    torque_response_selected: bool = False
    shutdown_response_selected: bool = False
    vehicle_acceptance_proven: bool = False
    action_authority: bool = False

    def to_json(self) -> str:
        return json.dumps(
            asdict(self),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )


def _wrap_age(now_tick: int, start_tick: int) -> int | None:
    delta = (now_tick - start_tick) & MAX_COUNTER
    if delta >= HALF_RANGE:
        return None
    return delta


def assess_publication_age(
    observation: TxPublicationAgeObservation,
) -> TxPublicationAgeAssessment:
    o = observation.checked()
    tb = o.timebase
    superseded = (
        o.command_bound_terminal_evidence
        and o.terminal_result == "transmitted"
        and o.command_seq < o.latest_intent_seq_at_terminal
    )

    if not o.command_bound_terminal_evidence:
        return TxPublicationAgeAssessment(
            schema="enme408-tc03b35-tx-publication-age/v1",
            command_seq=o.command_seq,
            latest_intent_seq_at_terminal=o.latest_intent_seq_at_terminal,
            terminal_result=o.terminal_result,
            status="terminal_event_unbound_to_command",
            age_ticks=None,
            age_seconds=None,
            max_age_ticks=o.max_age_ticks,
            publication_within_age_limit=None,
            superseded_publication_observed=False,
            command_bound_terminal_evidence=False,
            timebase_source_kind=tb.source_kind,
            max_age_source_kind=o.max_age_source_kind,
            ready_for_team_timing_use=False,
            reason="terminal_evidence_not_bound_to_command_sequence",
        )

    if o.terminal_result != "transmitted":
        return TxPublicationAgeAssessment(
            schema="enme408-tc03b35-tx-publication-age/v1",
            command_seq=o.command_seq,
            latest_intent_seq_at_terminal=o.latest_intent_seq_at_terminal,
            terminal_result=o.terminal_result,
            status="terminal_nonpublication",
            age_ticks=None,
            age_seconds=None,
            max_age_ticks=o.max_age_ticks,
            publication_within_age_limit=None,
            superseded_publication_observed=False,
            command_bound_terminal_evidence=True,
            timebase_source_kind=tb.source_kind,
            max_age_source_kind=o.max_age_source_kind,
            ready_for_team_timing_use=False,
            reason="terminal_result_is_not_transmitted",
        )

    if not tb.monotonic:
        reason = "timebase_not_monotonic"
    elif tb.can_pause:
        reason = "timebase_can_pause"
    else:
        reason = ""

    if reason:
        return TxPublicationAgeAssessment(
            schema="enme408-tc03b35-tx-publication-age/v1",
            command_seq=o.command_seq,
            latest_intent_seq_at_terminal=o.latest_intent_seq_at_terminal,
            terminal_result=o.terminal_result,
            status="invalid_timebase",
            age_ticks=None,
            age_seconds=None,
            max_age_ticks=o.max_age_ticks,
            publication_within_age_limit=None,
            superseded_publication_observed=superseded,
            command_bound_terminal_evidence=True,
            timebase_source_kind=tb.source_kind,
            max_age_source_kind=o.max_age_source_kind,
            ready_for_team_timing_use=False,
            reason=reason,
        )

    age = _wrap_age(o.terminal_tick, o.intent_tick)
    if age is None:
        return TxPublicationAgeAssessment(
            schema="enme408-tc03b35-tx-publication-age/v1",
            command_seq=o.command_seq,
            latest_intent_seq_at_terminal=o.latest_intent_seq_at_terminal,
            terminal_result=o.terminal_result,
            status="ambiguous_age",
            age_ticks=None,
            age_seconds=None,
            max_age_ticks=o.max_age_ticks,
            publication_within_age_limit=None,
            superseded_publication_observed=superseded,
            command_bound_terminal_evidence=True,
            timebase_source_kind=tb.source_kind,
            max_age_source_kind=o.max_age_source_kind,
            ready_for_team_timing_use=False,
            reason="intent_to_terminal_delta_reaches_half_range",
        )

    within = age <= o.max_age_ticks
    ready = (
        tb.source_kind == "team_verified"
        and o.max_age_source_kind == "team_verified"
    )

    return TxPublicationAgeAssessment(
        schema="enme408-tc03b35-tx-publication-age/v1",
        command_seq=o.command_seq,
        latest_intent_seq_at_terminal=o.latest_intent_seq_at_terminal,
        terminal_result=o.terminal_result,
        status="publication_within_age_limit"
        if within
        else "publication_age_exceeds_limit",
        age_ticks=age,
        age_seconds=age / tb.ticks_per_second,
        max_age_ticks=o.max_age_ticks,
        publication_within_age_limit=within,
        superseded_publication_observed=superseded,
        command_bound_terminal_evidence=True,
        timebase_source_kind=tb.source_kind,
        max_age_source_kind=o.max_age_source_kind,
        ready_for_team_timing_use=ready,
        reason="age_within_limit" if within else "age_exceeds_limit",
    )


def frozen_wrap_counterexample() -> dict[str, object]:
    """Naive integer ordering fails across 32-bit tick wrap."""
    o = TxPublicationAgeObservation(
        command_seq=8,
        latest_intent_seq_at_terminal=8,
        intent_tick=0xFFFFFFF0,
        terminal_tick=0x00000020,
        max_age_ticks=50,
        terminal_result="transmitted",
        command_bound_terminal_evidence=True,
        timebase=TimebaseEvidence(
            domain="scenario_hal_tick_ms",
            width_bits=32,
            ticks_per_second=1000.0,
            monotonic=True,
            can_pause=False,
            source_kind="scenario",
        ),
        max_age_source_kind="scenario",
    )
    r = assess_publication_age(o)
    return {
        "schema": "enme408-tc03b35-wrap-counterexample/v1",
        "scenario_only": True,
        "intent_tick": o.intent_tick,
        "terminal_tick": o.terminal_tick,
        "naive_terminal_ge_intent": o.terminal_tick >= o.intent_tick,
        "modular_age_ticks": r.age_ticks,
        "modular_age_seconds": r.age_seconds,
        "publication_within_age_limit": r.publication_within_age_limit,
        "team_deadline_proven": False,
        "action_authority": False,
    }


def frozen_fresh_but_superseded_counterexample() -> dict[str, object]:
    """A time-fresh publication can still be older than the latest intent."""
    o = TxPublicationAgeObservation(
        command_seq=1,
        latest_intent_seq_at_terminal=2,
        intent_tick=1000,
        terminal_tick=1020,
        max_age_ticks=50,
        terminal_result="transmitted",
        command_bound_terminal_evidence=True,
        timebase=TimebaseEvidence(
            domain="scenario_hal_tick_ms",
            width_bits=32,
            ticks_per_second=1000.0,
            monotonic=True,
            can_pause=False,
            source_kind="scenario",
        ),
        max_age_source_kind="scenario",
    )
    r = assess_publication_age(o)
    return {
        "schema": "enme408-tc03b35-fresh-but-superseded/v1",
        "scenario_only": True,
        "age_ticks": r.age_ticks,
        "publication_within_age_limit": r.publication_within_age_limit,
        "superseded_publication_observed": r.superseded_publication_observed,
        "latest_intent_seq": o.latest_intent_seq_at_terminal,
        "published_seq": o.command_seq,
        "abort_policy_selected": False,
        "action_authority": False,
    }
