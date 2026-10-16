"""Portable TC-02C board/firmware evidence contract.

This module validates *evidence records*, not vehicle control parameters. Unknown values
remain explicit and no performance/safety threshold is encoded here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

SCHEMA = "enme408-board-firmware-evidence/v1"


class EvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class EvidenceSummary:
    schema: str
    evidence_revision: str
    complete_fields: int
    unknown_fields: int
    unsupported_claims: tuple[str, ...]


def _require_dict(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise EvidenceError(f"{path} must be an object")
    return value


def _require_str(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise EvidenceError(f"{path} must be a string")
    if not allow_empty and not value.strip():
        raise EvidenceError(f"{path} must not be empty")
    return value


def _nullable_str(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _require_str(value, path)


def _nullable_nonnegative_int(value: Any, path: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise EvidenceError(f"{path} must be null or a non-negative integer")
    return value


def _nullable_bool(value: Any, path: str) -> bool | None:
    if value is None:
        return None
    if type(value) is not bool:
        raise EvidenceError(f"{path} must be null or boolean")
    return value


def _require_exact_keys(obj: dict[str, Any], required: Iterable[str], path: str) -> None:
    expected = set(required)
    actual = set(obj)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        parts: list[str] = []
        if missing:
            parts.append("missing=" + ",".join(missing))
        if extra:
            parts.append("unknown=" + ",".join(extra))
        raise EvidenceError(f"{path} keys invalid ({'; '.join(parts)})")


def _validate_source(value: Any, path: str) -> None:
    src = _require_dict(value, path)
    _require_exact_keys(src, ("kind", "reference", "observed_at_utc", "sha256"), path)
    kind = _require_str(src["kind"], f"{path}.kind")
    if kind not in {"team_file", "team_observation", "build_output", "datasheet", "manual", "unknown"}:
        raise EvidenceError(f"{path}.kind has unsupported value")
    _nullable_str(src["reference"], f"{path}.reference")
    _nullable_str(src["observed_at_utc"], f"{path}.observed_at_utc")
    sha = _nullable_str(src["sha256"], f"{path}.sha256")
    if sha is not None and (len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha.lower())):
        raise EvidenceError(f"{path}.sha256 must be a 64-character hexadecimal digest")


def validate_record(record: Any) -> EvidenceSummary:
    root = _require_dict(record, "record")
    _require_exact_keys(
        root,
        (
            "schema",
            "evidence_revision",
            "target_car",
            "mcu",
            "build",
            "clock",
            "startup_reset",
            "timing_instrumentation",
            "memory",
            "can",
            "logging",
            "watchdog",
            "firmware_files",
            "sources",
            "claims",
        ),
        "record",
    )
    if root["schema"] != SCHEMA:
        raise EvidenceError(f"record.schema must equal {SCHEMA}")
    revision = _require_str(root["evidence_revision"], "record.evidence_revision")
    if root["target_car"] != "2027-28":
        raise EvidenceError("record.target_car must remain 2027-28 for this project contract")

    field_specs = {
        "mcu": ("part_number", "package", "silicon_revision", "board_revision"),
        "build": ("toolchain", "compiler_version", "optimization", "cpu_flags", "linker_script", "build_system", "firmware_revision"),
        "clock": ("sysclk_hz", "hclk_hz", "apb1_hz", "apb2_hz", "source", "pll_config_evidence"),
        "startup_reset": ("startup_file", "system_init_file", "reset_flag_capture_file", "reset_flags_captured_before_clear"),
        "timing_instrumentation": ("counter_kind", "counter_frequency_hz", "enable_location", "sample_points", "interrupt_masking_policy"),
        "memory": ("flash_bytes", "ram_bytes", "stack_measurement_method", "heap_measurement_method", "map_file"),
        "logging": ("sink", "format", "retention", "timestamp_source"),
        "watchdog": ("independent_watchdog_used", "window_watchdog_used", "configuration_file", "ownership"),
    }
    values: list[Any] = []
    for section, keys in field_specs.items():
        obj = _require_dict(root[section], f"record.{section}")
        _require_exact_keys(obj, keys, f"record.{section}")
        for key in keys:
            value = obj[key]
            path = f"record.{section}.{key}"
            if key.endswith("_hz") or key.endswith("_bytes"):
                _nullable_nonnegative_int(value, path)
            elif key.startswith("independent_") or key.startswith("window_") or key == "reset_flags_captured_before_clear":
                _nullable_bool(value, path)
            elif key in {"sample_points", "cpu_flags"}:
                if value is not None:
                    if type(value) is not list or any(type(x) is not str or not x.strip() for x in value):
                        raise EvidenceError(f"{path} must be null or a list of non-empty strings")
            else:
                _nullable_str(value, path)
            values.append(value)

    can = _require_dict(root["can"], "record.can")
    _require_exact_keys(can, ("controllers",), "record.can")
    controllers = can["controllers"]
    if type(controllers) is not list:
        raise EvidenceError("record.can.controllers must be a list")
    seen: set[str] = set()
    for i, controller in enumerate(controllers):
        path = f"record.can.controllers[{i}]"
        obj = _require_dict(controller, path)
        _require_exact_keys(obj, ("name", "used", "bitrate_bps", "pins", "transceiver", "message_map_reference"), path)
        name = _require_str(obj["name"], f"{path}.name")
        if name in seen:
            raise EvidenceError("record.can.controllers names must be unique")
        seen.add(name)
        _nullable_bool(obj["used"], f"{path}.used")
        _nullable_nonnegative_int(obj["bitrate_bps"], f"{path}.bitrate_bps")
        for key in ("pins", "transceiver", "message_map_reference"):
            _nullable_str(obj[key], f"{path}.{key}")
            values.append(obj[key])
        values.extend((obj["used"], obj["bitrate_bps"]))

    firmware_files = root["firmware_files"]
    if type(firmware_files) is not list or any(type(x) is not str or not x.strip() for x in firmware_files):
        raise EvidenceError("record.firmware_files must be a list of non-empty strings")
    if len(firmware_files) != len(set(firmware_files)):
        raise EvidenceError("record.firmware_files must not contain duplicates")

    sources = root["sources"]
    if type(sources) is not list:
        raise EvidenceError("record.sources must be a list")
    for i, source in enumerate(sources):
        _validate_source(source, f"record.sources[{i}]")

    claims = _require_dict(root["claims"], "record.claims")
    _require_exact_keys(claims, ("vehicle_specific_thresholds_verified", "hardware_test_executed", "rule_compliance_verified"), "record.claims")
    unsupported: list[str] = []
    for key, value in claims.items():
        if type(value) is not bool:
            raise EvidenceError(f"record.claims.{key} must be boolean")
        if value:
            unsupported.append(key)

    if unsupported:
        raise EvidenceError("portable record may not assert: " + ", ".join(sorted(unsupported)))

    unknown = sum(v is None for v in values)
    complete = len(values) - unknown
    return EvidenceSummary(SCHEMA, revision, complete, unknown, tuple())
