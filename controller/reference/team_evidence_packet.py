"""TC-03A team evidence packet for build-only instrumentation handoff.

This schema records the minimum evidence needed to prepare a source-specific,
build-only instrumentation patch. It does not encode vehicle thresholds,
CAN message values, control parameters, or rule-compliance claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

SCHEMA = "enme408-team-evidence-request/v1"


class EvidencePacketError(ValueError):
    pass


@dataclass(frozen=True)
class Readiness:
    schema: str
    ready_for_source_specific_patch: bool
    missing: tuple[str, ...]
    populated: int
    total_required: int


_REQUIRED_SCALARS = (
    "mcu.part_number",
    "mcu.package",
    "mcu.board_revision",
    "firmware.repository_reference",
    "firmware.revision",
    "firmware.build_working_directory",
    "firmware.build_command",
    "firmware.toolchain",
    "firmware.compiler_version",
    "firmware.linker_script",
    "clock.sysclk_hz",
    "clock.hclk_hz",
    "clock.apb1_hz",
    "clock.apb2_hz",
    "clock.configuration_source",
    "reset.startup_file",
    "reset.system_init_file",
    "reset.reset_cause_owner",
    "watchdog.ownership",
    "logging.sink",
    "logging.timestamp_source",
    "can.message_map_reference",
)


def _dict(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise EvidencePacketError(f"{path} must be an object")
    return value


def _exact(obj: dict[str, Any], keys: Iterable[str], path: str) -> None:
    expected = set(keys)
    actual = set(obj)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if extra:
            details.append("unknown=" + ",".join(extra))
        raise EvidencePacketError(f"{path} keys invalid ({'; '.join(details)})")


def _nullable_str(value: Any, path: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not value.strip():
        raise EvidencePacketError(f"{path} must be null or a non-empty string")
    return value


def _nullable_positive_int(value: Any, path: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise EvidencePacketError(f"{path} must be null or a positive integer")
    return value


def _nullable_bool(value: Any, path: str) -> bool | None:
    if value is None:
        return None
    if type(value) is not bool:
        raise EvidencePacketError(f"{path} must be null or boolean")
    return value


def _path(record: dict[str, Any], dotted: str) -> Any:
    current: Any = record
    for part in dotted.split("."):
        current = current[part]
    return current


def validate_packet(packet: Any) -> Readiness:
    root = _dict(packet, "packet")
    _exact(
        root,
        (
            "schema", "evidence_revision", "target_car", "mcu", "firmware",
            "clock", "reset", "watchdog", "logging", "can",
            "control_path_files", "sources", "claims",
        ),
        "packet",
    )
    if root["schema"] != SCHEMA:
        raise EvidencePacketError(f"packet.schema must equal {SCHEMA}")
    _nullable_str(root["evidence_revision"], "packet.evidence_revision")
    if root["target_car"] != "2027-28":
        raise EvidencePacketError("packet.target_car must equal 2027-28")

    mcu = _dict(root["mcu"], "packet.mcu")
    _exact(mcu, ("part_number", "package", "silicon_revision", "board_revision"), "packet.mcu")
    for key in mcu:
        _nullable_str(mcu[key], f"packet.mcu.{key}")

    firmware = _dict(root["firmware"], "packet.firmware")
    _exact(
        firmware,
        (
            "repository_reference", "revision", "build_working_directory",
            "build_command", "toolchain", "compiler_version", "optimization",
            "cpu_flags", "linker_script",
        ),
        "packet.firmware",
    )
    for key in (
        "repository_reference", "revision", "build_working_directory",
        "build_command", "toolchain", "compiler_version", "optimization",
        "linker_script",
    ):
        _nullable_str(firmware[key], f"packet.firmware.{key}")
    flags = firmware["cpu_flags"]
    if flags is not None:
        if type(flags) is not list or any(type(x) is not str or not x.strip() for x in flags):
            raise EvidencePacketError("packet.firmware.cpu_flags must be null or a list of non-empty strings")

    clock = _dict(root["clock"], "packet.clock")
    _exact(clock, ("sysclk_hz", "hclk_hz", "apb1_hz", "apb2_hz", "configuration_source"), "packet.clock")
    for key in ("sysclk_hz", "hclk_hz", "apb1_hz", "apb2_hz"):
        _nullable_positive_int(clock[key], f"packet.clock.{key}")
    _nullable_str(clock["configuration_source"], "packet.clock.configuration_source")

    reset = _dict(root["reset"], "packet.reset")
    _exact(reset, ("startup_file", "system_init_file", "reset_cause_owner"), "packet.reset")
    for key in reset:
        _nullable_str(reset[key], f"packet.reset.{key}")

    watchdog = _dict(root["watchdog"], "packet.watchdog")
    _exact(
        watchdog,
        ("independent_watchdog_used", "window_watchdog_used", "configuration_file", "ownership"),
        "packet.watchdog",
    )
    _nullable_bool(watchdog["independent_watchdog_used"], "packet.watchdog.independent_watchdog_used")
    _nullable_bool(watchdog["window_watchdog_used"], "packet.watchdog.window_watchdog_used")
    _nullable_str(watchdog["configuration_file"], "packet.watchdog.configuration_file")
    _nullable_str(watchdog["ownership"], "packet.watchdog.ownership")

    logging = _dict(root["logging"], "packet.logging")
    _exact(logging, ("sink", "format", "timestamp_source"), "packet.logging")
    for key in logging:
        _nullable_str(logging[key], f"packet.logging.{key}")

    can = _dict(root["can"], "packet.can")
    _exact(can, ("controllers", "message_map_reference"), "packet.can")
    _nullable_str(can["message_map_reference"], "packet.can.message_map_reference")
    controllers = can["controllers"]
    if type(controllers) is not list:
        raise EvidencePacketError("packet.can.controllers must be a list")
    names: set[str] = set()
    for i, item in enumerate(controllers):
        obj = _dict(item, f"packet.can.controllers[{i}]")
        _exact(obj, ("name", "used", "bitrate_bps", "pins", "transceiver"), f"packet.can.controllers[{i}]")
        name = _nullable_str(obj["name"], f"packet.can.controllers[{i}].name")
        if name is None:
            raise EvidencePacketError(f"packet.can.controllers[{i}].name must be populated when a controller entry exists")
        if name in names:
            raise EvidencePacketError("packet.can.controllers names must be unique")
        names.add(name)
        _nullable_bool(obj["used"], f"packet.can.controllers[{i}].used")
        _nullable_positive_int(obj["bitrate_bps"], f"packet.can.controllers[{i}].bitrate_bps")
        _nullable_str(obj["pins"], f"packet.can.controllers[{i}].pins")
        _nullable_str(obj["transceiver"], f"packet.can.controllers[{i}].transceiver")

    files = root["control_path_files"]
    if type(files) is not list or any(type(x) is not str or not x.strip() for x in files):
        raise EvidencePacketError("packet.control_path_files must be a list of non-empty strings")
    if len(files) != len(set(files)):
        raise EvidencePacketError("packet.control_path_files must not contain duplicates")

    sources = root["sources"]
    if type(sources) is not list:
        raise EvidencePacketError("packet.sources must be a list")
    for i, item in enumerate(sources):
        obj = _dict(item, f"packet.sources[{i}]")
        _exact(obj, ("kind", "reference", "sha256"), f"packet.sources[{i}]")
        kind = _nullable_str(obj["kind"], f"packet.sources[{i}].kind")
        if kind not in {"team_file", "team_observation", "build_output", "board_schematic", "manual"}:
            raise EvidencePacketError(f"packet.sources[{i}].kind has unsupported value")
        _nullable_str(obj["reference"], f"packet.sources[{i}].reference")
        sha = obj["sha256"]
        if sha is not None:
            if type(sha) is not str or len(sha) != 64 or any(c not in "0123456789abcdefABCDEF" for c in sha):
                raise EvidencePacketError(f"packet.sources[{i}].sha256 must be null or a 64-character hexadecimal digest")

    claims = _dict(root["claims"], "packet.claims")
    _exact(
        claims,
        ("vehicle_specific_thresholds_verified", "hardware_test_executed", "rule_compliance_verified"),
        "packet.claims",
    )
    for key, value in claims.items():
        if type(value) is not bool:
            raise EvidencePacketError(f"packet.claims.{key} must be boolean")
        if value:
            raise EvidencePacketError(f"portable evidence request may not assert {key}=true")

    missing = [name for name in _REQUIRED_SCALARS if _path(root, name) is None]
    if not files:
        missing.append("control_path_files")
    if not sources:
        missing.append("sources")

    total = len(_REQUIRED_SCALARS) + 2
    return Readiness(
        schema=SCHEMA,
        ready_for_source_specific_patch=not missing,
        missing=tuple(missing),
        populated=total - len(missing),
        total_required=total,
    )
