from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Iterable

from timebase_freshness import FreshnessResult

NOMINAL = "nominal"
DEGRADED = "degraded"
FAULT = "fault"
_ALLOWED_FRESHNESS = {"fresh", "stale", "future", "ambiguous", "invalid_timebase"}


@dataclass(frozen=True)
class CanControllerObservation:
    """Portable observation of one CAN controller.

    These booleans are normalized observations, not a claim that the target
    firmware uses STM32 HAL or any specific register-access API.
    """

    label: str
    error_warning: bool = False
    error_passive: bool = False
    bus_off: bool = False
    rx_fifo0_overrun: bool = False
    rx_fifo1_overrun: bool = False


@dataclass(frozen=True)
class CriticalSignalObservation:
    """Synthetic evidence about one decoded critical input."""

    label: str
    freshness: FreshnessResult
    decode_ok: bool
    unit_ok: bool
    sign_ok: bool


@dataclass(frozen=True)
class CommunicationHealth:
    status: str
    reasons: tuple[str, ...]
    controller_count: int
    signal_count: int

    def as_record(self) -> dict[str, object]:
        record = asdict(self)
        record["reasons"] = list(self.reasons)
        return record

    def to_json(self) -> str:
        return json.dumps(
            self.as_record(),
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )


def _require_label(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def _require_bool(value: object, path: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{path} must be boolean")
    return value


def _validate_freshness(result: object, signal_label: str) -> FreshnessResult:
    if not isinstance(result, FreshnessResult):
        raise ValueError(f"signal {signal_label} freshness must be FreshnessResult")
    if result.status not in _ALLOWED_FRESHNESS:
        raise ValueError(f"signal {signal_label} freshness status is unsupported")
    if not isinstance(result.label, str) or not result.label.strip():
        raise ValueError(f"signal {signal_label} freshness label must be non-empty")
    if result.label != signal_label:
        raise ValueError(f"signal {signal_label} freshness label mismatch")
    return result


def evaluate_communication_health(
    controllers: Iterable[CanControllerObservation],
    signals: Iterable[CriticalSignalObservation],
) -> CommunicationHealth:
    """Classify portable CAN/signal evidence without defining vehicle recovery.

    "fault" means the synthetic snapshot contains evidence that should not be
    treated as nominal input health. "degraded" records warning/passive CAN
    observations when no stronger fault is present. The result is not actuator
    authority and does not define Terps Racing inhibit/recovery policy.
    """

    controller_list = tuple(controllers)
    signal_list = tuple(signals)
    if not signal_list:
        return CommunicationHealth(FAULT, ("no_critical_signal_evidence",), len(controller_list), 0)

    controller_labels: list[str] = []
    reasons: list[str] = []
    faulted = False
    degraded = False

    for controller in controller_list:
        if not isinstance(controller, CanControllerObservation):
            raise ValueError("controllers must contain CanControllerObservation")
        label = _require_label(controller.label, "controller.label")
        controller_labels.append(label)
        for field_name in (
            "error_warning",
            "error_passive",
            "bus_off",
            "rx_fifo0_overrun",
            "rx_fifo1_overrun",
        ):
            _require_bool(getattr(controller, field_name), f"controller {label}.{field_name}")

        if controller.bus_off:
            faulted = True
            reasons.append(f"controller:{label}:bus_off")
        if controller.rx_fifo0_overrun:
            faulted = True
            reasons.append(f"controller:{label}:rx_fifo0_overrun")
        if controller.rx_fifo1_overrun:
            faulted = True
            reasons.append(f"controller:{label}:rx_fifo1_overrun")
        if controller.error_passive:
            degraded = True
            reasons.append(f"controller:{label}:error_passive")
        if controller.error_warning:
            degraded = True
            reasons.append(f"controller:{label}:error_warning")

    if len(controller_labels) != len(set(controller_labels)):
        raise ValueError("duplicate controller labels")

    signal_labels: list[str] = []
    for signal in signal_list:
        if not isinstance(signal, CriticalSignalObservation):
            raise ValueError("signals must contain CriticalSignalObservation")
        label = _require_label(signal.label, "signal.label")
        signal_labels.append(label)
        freshness = _validate_freshness(signal.freshness, label)
        for field_name in ("decode_ok", "unit_ok", "sign_ok"):
            _require_bool(getattr(signal, field_name), f"signal {label}.{field_name}")

        if freshness.status != "fresh":
            faulted = True
            reasons.append(f"signal:{label}:freshness_{freshness.status}")
        if not signal.decode_ok:
            faulted = True
            reasons.append(f"signal:{label}:decode_invalid")
        if not signal.unit_ok:
            faulted = True
            reasons.append(f"signal:{label}:unit_invalid")
        if not signal.sign_ok:
            faulted = True
            reasons.append(f"signal:{label}:sign_invalid")

    if len(signal_labels) != len(set(signal_labels)):
        raise ValueError("duplicate signal labels")

    status = FAULT if faulted else DEGRADED if degraded else NOMINAL
    return CommunicationHealth(status, tuple(reasons), len(controller_list), len(signal_list))
