"""Bounded headless native suspension study with checked replay and cancellation."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from hashlib import sha256
from math import ceil, isclose, isfinite, sqrt
from pathlib import Path
from time import perf_counter, process_time
from typing import Any

from lapsim.dynamics.native_plant import (
    WHEEL_ORDER,
    AxleCommand,
    NativePlant,
    PlantCapabilities,
    PlantObservation,
)

from .dynamics_record import _canonical_json, _code_identity, _content_id
from .record_io import read_json_bounded, write_text_atomic

SCHEMA = "lapsim.native-suspension-study.v1"
MAX_BYTES = 8_000_000
SOURCE_HASH_SCOPE = "three study implementation files; UTF-8 bytes with CRLF normalized to LF"
TIMING_SCOPE = "engine construction through deterministic payload hashing; excludes interpreter/import startup, receipt envelope, and disk export"
PAYLOAD_KEYS = {
    "scenario",
    "capabilities",
    "model",
    "source",
    "wheel_order",
    "frame",
    "units",
    "controller",
    "commands",
    "samples",
    "metrics",
}


class StudyCancelled(RuntimeError):
    """A cancelled study has no completed or exportable result."""


@dataclass(frozen=True, slots=True)
class SuspensionScenario:
    scenario_id: str = "drive"
    settle_s: float = 6.0
    maneuver_s: float = 2.0
    plant_step_s: float = 0.0005
    controller_period_s: float = 0.01
    logging_period_s: float = 0.02
    driveshaft_torque_nm: float = 40.0
    steering: float = 0.06
    settle_braking: float = 0.2

    def __post_init__(self) -> None:
        if self.scenario_id not in ("settle", "drive", "steer"):
            raise ValueError("scenario_id must be settle, drive or steer")
        for name, low, high in (
            ("settle_s", 1, 10),
            ("maneuver_s", 0.1, 10),
            ("plant_step_s", 0.0001, 0.002),
            ("controller_period_s", 0.001, 0.1),
            ("logging_period_s", 0.001, 0.1),
            ("driveshaft_torque_nm", 0, 400),
            ("steering", -0.25, 0.25),
            ("settle_braking", 0, 1),
        ):
            value = getattr(self, name)
            if (
                type(value) not in (int, float)
                or not low <= value <= high
                or not isfinite(value)
            ):
                raise ValueError(f"{name} outside the bounded study domain")
        for name in (
            "settle_s",
            "maneuver_s",
            "controller_period_s",
            "logging_period_s",
        ):
            ticks = getattr(self, name) / self.plant_step_s
            if ticks < 1 or not isclose(ticks, round(ticks), rel_tol=0, abs_tol=1e-8):
                raise ValueError(
                    f"{name} must contain an integer number of plant ticks"
                )
        if (self.settle_s + self.maneuver_s) / self.plant_step_s > 100_000:
            raise ValueError("study exceeds the 100,000 plant-step budget")
        if (self.settle_s + self.maneuver_s) / self.logging_period_s > 2_000:
            raise ValueError("study exceeds the 2,001 sample budget")


def _implementation_source() -> dict:
    """Read implementation hashes without importing the engine or launching Git."""
    from lapsim import dynamics

    files = {
        "native_plant.py": Path(dynamics.__file__).parent / "native_plant.py",
        "chrono_vehicle.py": Path(dynamics.__file__).parent / "chrono_vehicle.py",
        "suspension_study.py": Path(__file__),
    }
    return {
        "hash_scope": SOURCE_HASH_SCOPE,
        "files_sha256": {
            name: sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for name, path in files.items()
        },
    }


def _source() -> dict:
    return {**_code_identity(), **_implementation_source()}


def _peak_memory_bytes() -> int | None:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class MemoryCounters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t)
                for name in (
                    "PeakWorkingSetSize",
                    "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage",
                    "PagefileUsage",
                    "PeakPagefileUsage",
                )
            ]

        counters = MemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(MemoryCounters),
            wintypes.DWORD,
        ]
        if psapi.GetProcessMemoryInfo(
            kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            return int(counters.PeakWorkingSetSize)
        return None
    try:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(peak if sys.platform == "darwin" else peak * 1024)
    except ImportError:
        return None


def _command(scenario: SuspensionScenario, time_s: float) -> AxleCommand:
    if time_s < scenario.settle_s or scenario.scenario_id == "settle":
        return AxleCommand(braking=scenario.settle_braking)
    ramp = min(1.0, (time_s - scenario.settle_s) / 0.5)
    return AxleCommand(
        driveshaft_torque_nm=scenario.driveshaft_torque_nm * ramp,
        steering=scenario.steering * ramp if scenario.scenario_id == "steer" else 0.0,
    )


@dataclass(slots=True)
class _SettlingMeasurements:
    """Streaming plant-boundary maxima; exported logging owns no acceptance clock."""

    count: int = 0
    first_time_s: float | None = None
    last_time_s: float | None = None
    force_relative_error: float = 0.0
    left_right_relative_difference: float = 0.0
    vertical_speed_mps: float = 0.0

    def add(self, sample: dict) -> None:
        weight = sample["mass_kg"] * 9.81
        if not isfinite(weight) or weight <= 0:
            raise ValueError("Native plant mass must be finite and positive")
        loads = sample["applied_wheel_force_world_n"]
        force_error = abs(sum(force[2] for force in loads) - weight) / weight
        left_right = max(
            abs(loads[2 * axle][2] - loads[2 * axle + 1][2]) / max(1.0, weight / 2)
            for axle in range(2)
        )
        vertical_speed = abs(sample["velocity_mps"][2])
        if not all(
            isfinite(value) for value in (force_error, left_right, vertical_speed)
        ):
            raise ValueError("Nonfinite native settling measurement")
        self.force_relative_error = max(self.force_relative_error, force_error)
        self.left_right_relative_difference = max(
            self.left_right_relative_difference, left_right
        )
        self.vertical_speed_mps = max(self.vertical_speed_mps, vertical_speed)
        if self.count == 0:
            self.first_time_s = sample["time_s"]
        self.last_time_s = sample["time_s"]
        self.count += 1

    def metrics(self, scenario: SuspensionScenario) -> dict:
        if self.count == 0:
            raise RuntimeError("No plant observations in the settling window")
        return {
            "settle_window_s": [scenario.settle_s - 0.5, scenario.settle_s],
            "settle_samples": self.count,
            "settle_sampling": {
                "clock": "every plant-tick boundary in the inclusive settling window",
                "period_s": scenario.plant_step_s,
                "first_time_s": self.first_time_s,
                "last_time_s": self.last_time_s,
                "force_channel": "applied_wheel_force_world_n",
            },
            "settle_max_vertical_force_relative_error": self.force_relative_error,
            "settle_max_left_right_load_relative_difference": self.left_right_relative_difference,
            "settle_max_vertical_speed_mps": self.vertical_speed_mps,
            "settle_acceptance": {
                "passed": self.force_relative_error <= 0.01
                and self.left_right_relative_difference <= 0.01
                and self.vertical_speed_mps <= 0.01,
                "force_relative_limit": 0.01,
                "left_right_relative_limit": 0.01,
                "vertical_speed_limit_mps": 0.01,
            },
        }


def _metrics(
    samples: list[dict], scenario: SuspensionScenario, settling: _SettlingMeasurements
) -> dict:
    return {
        **settling.metrics(scenario),
        "final_speed_mps": sqrt(
            sum(value * value for value in samples[-1]["velocity_mps"])
        ),
        "final_heading_rad": samples[-1]["heading_rad"],
        "final_chassis_com_height_m": samples[-1]["position_m"][2],
    }


def run_study(
    scenario: SuspensionScenario,
    *,
    cancel: Callable[[], bool] | None = None,
    progress: Callable[[float], None] | None = None,
    plant_factory: Callable[[], NativePlant] | None = None,
) -> dict:
    """Run an integer clock. Cancellation raises and always closes the plant."""
    if not isinstance(scenario, SuspensionScenario):
        raise TypeError("run_study requires a SuspensionScenario")
    if cancel and cancel():
        raise StudyCancelled("Study cancelled before initialization")
    if plant_factory is None:
        from lapsim.dynamics.chrono_vehicle import ChronoVehiclePlant

        plant_factory = ChronoVehiclePlant
    started = perf_counter()
    cpu_started = process_time()
    plant = plant_factory()
    initialized = perf_counter()
    try:
        samples: list[dict] = []
        commands: list[dict] = []
        ticks = round((scenario.settle_s + scenario.maneuver_s) / scenario.plant_step_s)
        controller_ticks = round(scenario.controller_period_s / scenario.plant_step_s)
        logging_ticks = round(scenario.logging_period_s / scenario.plant_step_s)
        settle_tick = round(scenario.settle_s / scenario.plant_step_s)
        # A window edge need not fall on the plant grid. Include only its
        # integer boundaries, with tolerance for division at an exact boundary.
        settle_start_tick = ceil(
            (scenario.settle_s - 0.5) / scenario.plant_step_s - 1e-8
        )
        settling = _SettlingMeasurements()
        model = plant.provenance()
        capabilities = asdict(plant.capabilities)
        for tick in range(ticks + 1):
            if cancel and cancel():
                raise StudyCancelled(f"Study cancelled at plant tick {tick}")
            # Observe before setting the next command: command telemetry belongs
            # to the interval that produced this state, not a future request.
            log_sample = tick % logging_ticks == 0 or tick in (settle_tick, ticks)
            measure_settling = settle_start_tick <= tick <= settle_tick
            if log_sample or measure_settling:
                sample = asdict(plant.observe())
                expected = tick * scenario.plant_step_s
                if not isclose(sample["time_s"], expected, rel_tol=0, abs_tol=1e-9):
                    raise RuntimeError("Native plant clock diverged from the runner")
                # Also rejects a solver NaN before it can become saved evidence.
                _canonical_json(sample)
                if measure_settling:
                    settling.add(sample)
                if log_sample:
                    samples.append(sample)
            if tick == ticks:
                break
            if (
                tick == settle_tick
                and not settling.metrics(scenario)["settle_acceptance"]["passed"]
            ):
                raise RuntimeError(
                    "Vehicle has not settled under gravity; increase settle_s or inspect the recorded native model"
                )
            if tick % controller_ticks == 0:
                command = _command(scenario, tick * scenario.plant_step_s)
                plant.set_command(command)
                commands.append(
                    {"time_s": tick * scenario.plant_step_s, "request": asdict(command)}
                )
                if progress:
                    progress(tick / ticks)
            plant.advance(scenario.plant_step_s)
        payload = {
            "scenario": asdict(scenario),
            "capabilities": capabilities,
            "model": model,
            "source": _source(),
            "wheel_order": list(WHEEL_ORDER),
            "frame": "right-handed world X initially forward, Y left, Z up; chassis COM",
            "units": "SI; steering request normalized, tire slip ratio dimensionless",
            "controller": "bounded open-loop rear-driveshaft ramp; 0.5 s ramp, zero-order hold",
            "commands": commands,
            "samples": samples,
            "metrics": _metrics(samples, scenario, settling),
        }
        deterministic_id = _content_id(payload)
        cpu_finished = process_time()
        finished = perf_counter()
        if progress:
            progress(1.0)
        record = {
            "schema": SCHEMA,
            "content_id": deterministic_id,
            "payload": payload,
            "execution": {
                "python": platform.python_version(),
                "platform": platform.system(),
                "initialization_wall_s": initialized - started,
                "stepping_and_record_wall_s": finished - initialized,
                "total_wall_s": finished - started,
                "process_cpu_s": cpu_finished - cpu_started,
                "process_lifetime_peak_working_set_bytes": _peak_memory_bytes(),
                "plant_steps": ticks,
                "simulated_time_s": ticks * scenario.plant_step_s,
                "controller_calls": len(commands),
                "logging_samples": len(samples),
                "device": "CPU",
                "gpu_physics": False,
                "timing_scope": TIMING_SCOPE,
            },
        }
        record["receipt_id"] = _content_id(record)
        if len(_canonical_json(record).encode("utf-8")) > MAX_BYTES:
            raise ValueError(
                "Completed suspension record exceeds the replay byte budget"
            )
        return record
    finally:
        plant.close()


def _compare(expected: Any, actual: Any, path: str = "payload") -> None:
    if type(expected) in (int, float) and type(actual) in (int, float):
        try:
            equal = (
                isfinite(expected)
                and isfinite(actual)
                and isclose(expected, actual, rel_tol=1e-7, abs_tol=1e-8)
            )
        except OverflowError:
            equal = False
        if not equal:
            raise ValueError(f"Replay differs at {path}")
    elif (
        isinstance(expected, dict)
        and isinstance(actual, dict)
        and expected.keys() == actual.keys()
    ):
        for key in expected:
            _compare(expected[key], actual[key], f"{path}.{key}")
    elif (
        isinstance(expected, (list, tuple))
        and isinstance(actual, (list, tuple))
        and len(expected) == len(actual)
    ):
        for index, (left, right) in enumerate(zip(expected, actual)):
            _compare(left, right, f"{path}[{index}]")
    elif type(expected) is not type(actual) or expected != actual:
        raise ValueError(f"Replay differs at {path}")


def validate_study_record(record: Any) -> SuspensionScenario:
    """Check saved structure and integrity; do not reproduce or authenticate it."""
    try:
        encoded = _canonical_json(record).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError("Native suspension record must contain finite JSON") from exc
    if len(encoded) > MAX_BYTES:
        raise ValueError("Native suspension record exceeds the replay byte budget")
    if (
        not isinstance(record, dict)
        or set(record) != {"schema", "content_id", "payload", "execution", "receipt_id"}
        or record["schema"] != SCHEMA
    ):
        raise ValueError("Unsupported native suspension record")
    if record["receipt_id"] != _content_id(
        {key: value for key, value in record.items() if key != "receipt_id"}
    ):
        raise ValueError("Native suspension receipt hash does not match")
    payload = record["payload"]
    if (
        not isinstance(payload, dict)
        or set(payload) != PAYLOAD_KEYS
        or _content_id(payload) != record["content_id"]
    ):
        raise ValueError("Native suspension record content hash does not match")
    if not isinstance(payload["scenario"], dict) or set(payload["scenario"]) != {
        field.name for field in fields(SuspensionScenario)
    }:
        raise ValueError("Invalid suspension scenario fields")
    try:
        scenario = SuspensionScenario(**payload["scenario"])
    except (KeyError, TypeError) as exc:
        raise ValueError("Invalid suspension scenario") from exc
    source = payload["source"]
    if not isinstance(source, dict) or set(source) != {
        "code_commit", "dirty_worktree", "hash_scope", "files_sha256"
    }:
        raise ValueError("Invalid study source identity")
    commit = source["code_commit"]
    if (
        (
            commit is not None
            and (
                not isinstance(commit, str)
                or len(commit) != 40
                or any(c not in "0123456789abcdef" for c in commit)
            )
        )
        or source["dirty_worktree"] is not None
        and type(source["dirty_worktree"]) is not bool
    ):
        raise ValueError("Invalid study Git identity")
    hashes = source["files_sha256"]
    if (
        not isinstance(source["hash_scope"], str)
        or not 1 <= len(source["hash_scope"]) <= 256
        or not isinstance(hashes, dict)
        or set(hashes) != {"native_plant.py", "chrono_vehicle.py", "suspension_study.py"}
        or any(
            not isinstance(value, str)
            or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
            for value in hashes.values()
        )
    ):
        raise ValueError("Invalid study implementation identity")
    _validate_execution(record["execution"], scenario)
    _validate_saved_channels(payload, record["execution"], scenario)
    return scenario


def read_study_record(path: str | Path) -> dict:
    """Load a bounded saved record without starting the optional native backend."""
    record = read_json_bounded(Path(path), maximum_bytes=MAX_BYTES)
    validate_study_record(record)
    return record


def inspect_study_record(record: Any) -> dict:
    """Summarize saved claims separately from checks performed while opening."""
    scenario = validate_study_record(record)
    payload = record["payload"]
    try:
        current = _implementation_source()
    except OSError:
        implementation_status = "unavailable; current implementation files could not be read"
    else:
        implementation_matches = all(
            payload["source"][key] == current[key] for key in current
        )
        implementation_status = (
            "match" if implementation_matches
            else "mismatch; recorded source required for replay"
        )
    return {
        "kind": "saved native suspension record; stored model and metrics are claims",
        "schema": record["schema"],
        "saved_content_id": record["content_id"],
        "saved_receipt_id": record["receipt_id"],
        "checks": {
            "receipt_and_content_integrity": "checked",
            "stored_structure": "checked; finite channels, counts and sample/command clocks",
            "current_implementation_files": implementation_status,
            "authenticity": "not established by content hashes",
            "fresh_native_replay": "not run",
            "historical_timing": "recorded claims; not validated",
            "vehicle_calibration": "not established",
        },
        "saved_scenario": payload["scenario"],
        "saved_clocks": {
            "plant_step_s": scenario.plant_step_s,
            "controller_period_s": scenario.controller_period_s,
            "logging_period_s": scenario.logging_period_s,
            "plant_steps": record["execution"]["plant_steps"],
            "command_events": len(payload["commands"]),
            "exported_samples": len(payload["samples"]),
            "sample_command_phase": "completed interval; same-time command event begins the next hold",
            "settling_sampling_claim": payload["metrics"].get("settle_sampling", "not recorded by this implementation"),
        },
        "saved_capabilities_and_topology": payload["capabilities"],
        "saved_provenance": {
            key: payload[key]
            for key in ("model", "source", "frame", "units", "controller", "wheel_order")
        },
        "stored_metrics_claims": payload["metrics"],
        "historical_execution_claims": record["execution"],
    }


def replay_study(record: dict, *, cancel: Callable[[], bool] | None = None) -> dict:
    scenario = validate_study_record(record)
    payload = record["payload"]
    source = payload["source"]
    actual_source = _implementation_source()
    if (
        source["hash_scope"] != actual_source["hash_scope"]
        or source["files_sha256"] != actual_source["files_sha256"]
    ):
        raise ValueError(
            "Study implementation changed; use the recorded source revision for replay"
        )
    actual = run_study(scenario, cancel=cancel)
    # A documentation-only commit may change the repository SHA, but the exact
    # three implementation hashes must match. Never compare runtime wall times.
    for key in PAYLOAD_KEYS - {"source"}:
        _compare(payload[key], actual["payload"][key], key)
    return actual


def _numeric_shape(value: Any, shape: tuple[int, ...], path: str) -> None:
    if shape:
        if not isinstance(value, (list, tuple)) or len(value) != shape[0]:
            raise ValueError(f"Invalid saved channel shape: {path}")
        for item in value:
            _numeric_shape(item, shape[1:], path)
    else:
        try:
            valid = type(value) in (int, float) and isfinite(value)
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError(f"Invalid saved numeric channel: {path}")


def _validate_saved_command(request: Any) -> None:
    if not isinstance(request, dict) or set(request) != {
        field.name for field in fields(AxleCommand)
    }:
        raise ValueError("Invalid saved command fields")
    try:
        AxleCommand(**request)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid saved command request") from exc


def _validate_metrics_claims(metrics: dict) -> None:
    """Check known stored metric shapes, without claiming their reproduction."""
    numeric = {
        "settle_max_vertical_force_relative_error",
        "settle_max_left_right_load_relative_difference",
        "settle_max_vertical_speed_mps",
        "final_speed_mps", "final_heading_rad", "final_chassis_com_height_m",
    }
    required = numeric | {"settle_window_s", "settle_samples", "settle_acceptance"}
    if not required <= metrics.keys():
        raise ValueError("Missing saved metric fields")
    for name in numeric:
        _numeric_shape(metrics[name], (), name)
    _numeric_shape(metrics["settle_window_s"], (2,), "settling window")
    if (
        type(metrics["settle_samples"]) is not int
        or not 1 <= metrics["settle_samples"] <= 100_001
    ):
        raise ValueError("Invalid saved settling observation count")
    acceptance = metrics["settle_acceptance"]
    limits = {"force_relative_limit", "left_right_relative_limit", "vertical_speed_limit_mps"}
    if (
        not isinstance(acceptance, dict)
        or set(acceptance) != limits | {"passed"}
        or type(acceptance["passed"]) is not bool
    ):
        raise ValueError("Invalid saved settling acceptance claim")
    for name in limits:
        _numeric_shape(acceptance[name], (), name)
        if acceptance[name] < 0:
            raise ValueError("Invalid saved settling limit")
    if "settle_sampling" in metrics:
        sampling = metrics["settle_sampling"]
        if (
            not isinstance(sampling, dict)
            or set(sampling) != {
                "clock", "period_s", "first_time_s", "last_time_s", "force_channel"
            }
            or any(
                not isinstance(sampling[key], str) or not sampling[key]
                for key in ("clock", "force_channel")
            )
        ):
            raise ValueError("Invalid saved settling clock claim")
        for name in ("period_s", "first_time_s", "last_time_s"):
            _numeric_shape(sampling[name], (), name)
        if (
            sampling["period_s"] <= 0
            or not 0 <= sampling["first_time_s"] <= sampling["last_time_s"]
        ):
            raise ValueError("Invalid saved settling clock claim")


def _validate_saved_channels(
    payload: dict, execution: dict, scenario: SuspensionScenario
) -> None:
    """Validate stored shapes/clock relationships, not native model assertions."""
    capabilities = payload["capabilities"]
    if (
        not isinstance(capabilities, dict)
        or set(capabilities) != {field.name for field in fields(PlantCapabilities)}
        or any(
            not isinstance(value, str) or not 1 <= len(value) <= 256
            for value in capabilities.values()
        )
        or capabilities["device"] != execution["device"]
        or payload["wheel_order"] not in (list(WHEEL_ORDER), WHEEL_ORDER)
    ):
        raise ValueError("Invalid saved capabilities or wheel order")
    if any(
        not isinstance(payload[key], dict) or not payload[key]
        for key in ("model", "metrics")
    ):
        raise ValueError("Stored model and metrics claims must be objects")
    _validate_metrics_claims(payload["metrics"])
    if any(
        not isinstance(payload[key], str) or not payload[key]
        for key in ("frame", "units", "controller")
    ):
        raise ValueError("Invalid saved frame, units or controller description")
    commands, samples = payload["commands"], payload["samples"]
    if (
        not isinstance(commands, (list, tuple))
        or len(commands) != execution["controller_calls"]
        or not isinstance(samples, (list, tuple))
        or len(samples) != execution["logging_samples"]
    ):
        raise ValueError("Saved sample/command count disagrees with execution receipt")
    controller_ticks = round(scenario.controller_period_s / scenario.plant_step_s)
    logging_ticks = round(scenario.logging_period_s / scenario.plant_step_s)
    ticks = execution["plant_steps"]
    for index, event in enumerate(commands):
        if not isinstance(event, dict) or set(event) != {"time_s", "request"}:
            raise ValueError("Invalid saved command event")
        _numeric_shape(event["time_s"], (), "command time")
        if not isclose(
            event["time_s"], index * controller_ticks * scenario.plant_step_s,
            rel_tol=0, abs_tol=1e-9,
        ):
            raise ValueError("Saved command clock disagrees with scenario")
        _validate_saved_command(event["request"])
    sample_ticks = sorted({
        *range(0, ticks + 1, logging_ticks),
        round(scenario.settle_s / scenario.plant_step_s), ticks,
    })
    shapes = {
        **{name: (3,) for name in (
            "position_m", "velocity_mps", "cardan_xyz_rad", "angular_velocity_rad_s"
        )},
        **{name: (4, 3) for name in (
            "wheel_position_m", "wheel_force_world_n", "applied_wheel_force_world_n"
        )},
        **{name: (4,) for name in (
            "wheel_omega_rad_s", "native_axle_shaft_omega_rad_s", "tire_slip_ratio",
            "tire_slip_angle_rad", "suspension_spring_length_m",
            "suspension_spring_force_n", "suspension_damper_force_n",
            "driveline_wheel_torque_nm",
        )},
    }
    nullable_times = {
        "tire_force_source_time_s", "tire_kinematics_source_time_s",
        "applied_tire_force_source_time_s",
    }
    sample_fields = {field.name for field in fields(PlantObservation)}
    for tick, sample in zip(sample_ticks, samples, strict=True):
        if not isinstance(sample, dict) or set(sample) != sample_fields:
            raise ValueError("Invalid saved observation fields")
        for name, value in sample.items():
            if name == "command" or name in nullable_times and value is None:
                continue
            _numeric_shape(value, shapes.get(name, ()), name)
        time_s = sample["time_s"]
        if (
            not isclose(time_s, tick * scenario.plant_step_s, rel_tol=0, abs_tol=1e-9)
            or sample["mass_kg"] <= 0
        ):
            raise ValueError("Invalid saved observation clock or mass")
        for name in nullable_times | {"applied_tire_force_geometry_time_s"}:
            if sample[name] is not None and not 0 <= sample[name] <= time_s + 1e-9:
                raise ValueError("Saved force/kinematics clock lies outside its observation")
        prior_command = (
            asdict(AxleCommand()) if tick == 0
            else commands[(tick - 1) // controller_ticks]["request"]
        )
        _validate_saved_command(sample["command"])
        if sample["command"] != prior_command:
            raise ValueError("Saved observation command does not describe its completed interval")


def _validate_execution(execution: Any, scenario: SuspensionScenario) -> None:
    """Validate historical measurement structure; replay does not prove its timing."""
    fields = {
        "python",
        "platform",
        "initialization_wall_s",
        "stepping_and_record_wall_s",
        "total_wall_s",
        "process_cpu_s",
        "process_lifetime_peak_working_set_bytes",
        "plant_steps",
        "simulated_time_s",
        "controller_calls",
        "logging_samples",
        "device",
        "gpu_physics",
        "timing_scope",
    }
    if not isinstance(execution, dict) or set(execution) != fields:
        raise ValueError("Invalid execution receipt fields")
    for field in (
        "initialization_wall_s",
        "stepping_and_record_wall_s",
        "total_wall_s",
        "process_cpu_s",
    ):
        value = execution[field]
        if (
            type(value) not in (float, int)
            or not 0 <= value <= 86400
            or not isfinite(value)
        ):
            raise ValueError(f"Invalid execution measurement: {field}")
    if not isclose(
        execution["initialization_wall_s"] + execution["stepping_and_record_wall_s"],
        execution["total_wall_s"],
        rel_tol=1e-10,
        abs_tol=1e-10,
    ):
        raise ValueError("Execution wall-time components do not sum to total")
    for field in ("python", "platform"):
        if (
            not isinstance(execution[field], str)
            or not 1 <= len(execution[field]) <= 64
        ):
            raise ValueError(f"Invalid execution environment: {field}")
    peak = execution["process_lifetime_peak_working_set_bytes"]
    if peak is not None and (type(peak) is not int or not 0 < peak <= 2**64 - 1):
        raise ValueError("Invalid peak working-set measurement")
    ticks = round((scenario.settle_s + scenario.maneuver_s) / scenario.plant_step_s)
    logging_ticks = round(scenario.logging_period_s / scenario.plant_step_s)
    controller_ticks = round(scenario.controller_period_s / scenario.plant_step_s)
    counts = {
        "plant_steps": ticks,
        "controller_calls": (ticks - 1) // controller_ticks + 1,
        "logging_samples": ticks // logging_ticks
        + 1
        + int(ticks % logging_ticks != 0)
        + int(round(scenario.settle_s / scenario.plant_step_s) % logging_ticks != 0),
    }
    for field, expected in counts.items():
        if type(execution[field]) is not int or execution[field] != expected:
            raise ValueError(f"Execution count disagrees with scenario: {field}")
    if (
        type(execution["simulated_time_s"]) not in (float, int)
        or not isclose(
            execution["simulated_time_s"],
            ticks * scenario.plant_step_s,
            rel_tol=0,
            abs_tol=1e-12,
        )
        or execution["device"] != "CPU"
        or execution["gpu_physics"] is not False
        or execution["timing_scope"] != TIMING_SCOPE
    ):
        raise ValueError(
            "Execution device, time or measurement scope disagrees with this backend"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario", choices=("settle", "drive", "steer"), default="drive"
    )
    parser.add_argument("--plant-step", type=float, default=0.0005)
    parser.add_argument("--output", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--replay", type=Path)
    mode.add_argument("--inspect", type=Path, help="inspect a saved result without native physics")
    parser.add_argument("--stop-file", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.inspect:
            if args.output:
                raise ValueError("--inspect cannot be combined with --output")
            summary = inspect_study_record(
                read_json_bounded(args.inspect, maximum_bytes=MAX_BYTES)
            )
            print(json.dumps(summary, indent=2))
            return 0
        if (
            args.replay
            and args.output
            and (
                args.replay.resolve() == args.output.resolve()
                or (args.output.exists() and args.replay.samefile(args.output))
            )
        ):
            raise ValueError("Replay output must differ from its input")
        cancel = (lambda: args.stop_file.exists()) if args.stop_file else None
        last_percent = -1

        def report_progress(fraction: float) -> None:
            nonlocal last_percent
            percent = int(fraction * 10) * 10
            if percent != last_percent:
                print(f"Native suspension study: {percent}%", file=sys.stderr)
                last_percent = percent

        if args.replay:
            record = replay_study(
                read_json_bounded(args.replay, maximum_bytes=MAX_BYTES), cancel=cancel
            )
        else:
            record = run_study(
                SuspensionScenario(
                    scenario_id=args.scenario, plant_step_s=args.plant_step
                ),
                cancel=cancel,
                progress=report_progress,
            )
        if args.output:
            write_text_atomic(args.output, _canonical_json(record) + "\n")
        print(
            json.dumps(
                {
                    "content_id": record["content_id"],
                    "metrics": record["payload"]["metrics"],
                    "execution": record["execution"],
                },
                indent=2,
            )
        )
        return 0
    except (
        OSError,
        ValueError,
        TypeError,
        RuntimeError,
        OverflowError,
        KeyboardInterrupt,
    ) as exc:
        print(f"Suspension study: {exc}", file=sys.stderr)
        return 130 if isinstance(exc, (StudyCancelled, KeyboardInterrupt)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
