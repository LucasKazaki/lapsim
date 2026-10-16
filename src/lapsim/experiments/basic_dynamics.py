"""Versioned, bounded bicycle experiments and checked recorded-result replay.

The six-state force-input record is separate from distance-domain lap and
ten-state wheel records. It reuses their content hash, JSON guards and runtime
identity; no existing saved model is silently migrated to bicycle physics.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
from math import ceil, isclose
from pathlib import Path
from typing import Any

from lapsim.dynamics.bicycle import (
    MODEL_ID,
    SYNTHETIC_PROFILE_ID,
    TOPOLOGY_ID,
    MAX_INTERNAL_STEPS,
    BicycleConfig,
    BicycleControls,
    BicycleState,
    _finite,
    evaluate_bicycle,
    integrate_bicycle,
)
from .dynamics_record import _canonical_json, _content_id, _runtime_identity
from .run_record import _reject_duplicate_keys, _reject_json_constant

RECORD_SCHEMA = "lapsim.basic-dynamics.record.v1"
MAX_RECORD_BYTES = 20_000_000
MAX_LOG_SAMPLES = 10_000


@dataclass(frozen=True, slots=True)
class BicycleScenario:
    schema_version: int = 1
    model_id: str = MODEL_ID
    vehicle_profile_id: str = SYNTHETIC_PROFILE_ID
    drivetrain_topology_id: str = TOPOLOGY_ID
    controller_backend_id: str = "none_prescribed_force"
    config: BicycleConfig = field(default_factory=BicycleConfig)
    initial_state: BicycleState = field(default_factory=lambda: BicycleState(u_mps=8.0))
    controls: BicycleControls = field(
        default_factory=lambda: BicycleControls(
            steering_angle_rad=0.04, rear_force_request_n=200.0
        )
    )
    duration_s: float = 5.0
    plant_step_s: float = 0.002
    logging_period_s: float = 0.02

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("unsupported bicycle scenario version")
        for name, expected in (
            ("model_id", MODEL_ID),
            ("vehicle_profile_id", SYNTHETIC_PROFILE_ID),
            ("drivetrain_topology_id", TOPOLOGY_ID),
            ("controller_backend_id", "none_prescribed_force"),
        ):
            if getattr(self, name) != expected:
                raise ValueError(
                    f"unsupported {name}; independent wheel allocation requires the four-wheel plant"
                )
        if (
            not isinstance(self.config, BicycleConfig)
            or not isinstance(self.initial_state, BicycleState)
            or not isinstance(self.controls, BicycleControls)
        ):
            raise ValueError(
                "scenario requires typed bicycle config, state and controls"
            )
        if self.controls.front_force_request_n > 0:
            raise ValueError("the RWD scenario cannot request front propulsion")
        for name in ("duration_s", "plant_step_s", "logging_period_s"):
            value = getattr(self, name)
            _finite(value, name)
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.duration_s > 30 or self.plant_step_s > 0.01:
            raise ValueError("scenario supports at most 30 s and a 0.01 s plant step")
        ticks = self.duration_s / self.plant_step_s
        log_ticks = self.logging_period_s / self.plant_step_s
        if not 1 <= ticks <= MAX_INTERNAL_STEPS or not isclose(
            ticks, round(ticks), rel_tol=0, abs_tol=1e-8
        ):
            raise ValueError(
                "duration must contain an integer, bounded number of plant ticks"
            )
        if not 1 <= log_ticks <= MAX_INTERNAL_STEPS or not isclose(
            log_ticks, round(log_ticks), rel_tol=0, abs_tol=1e-8
        ):
            raise ValueError(
                "logging period must be an integer multiple of the plant step"
            )
        substeps = ceil(self.plant_step_s / self.config.integration_step_limit_s)
        if round(ticks) * substeps > MAX_INTERNAL_STEPS:
            raise ValueError("complete scenario exceeds the integration work budget")
        samples = (
            round(ticks) // round(log_ticks)
            + 1
            + int(round(ticks) % round(log_ticks) != 0)
        )
        if samples > MAX_LOG_SAMPLES:
            raise ValueError("scenario exceeds the recorded sample budget")

    @classmethod
    def from_dict(cls, value: Any) -> BicycleScenario:
        if not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__):
            raise ValueError(
                "scenario must contain its exact versioned identity, inputs and clocks"
            )
        decoded = dict(value)
        try:
            for name, constructor in (
                ("config", BicycleConfig),
                ("initial_state", BicycleState),
                ("controls", BicycleControls),
            ):
                if not isinstance(decoded[name], dict):
                    raise ValueError(f"scenario {name} must be an object")
                decoded[name] = constructor(**decoded[name])
            return cls(**decoded)
        except (TypeError, OverflowError) as error:
            raise ValueError("invalid bicycle scenario fields") from error


def run_bicycle_scenario(scenario: BicycleScenario) -> dict[str, Any]:
    """Advance only plant ticks; logging observes without changing integration."""
    if not isinstance(scenario, BicycleScenario):
        raise ValueError("expected a BicycleScenario")
    count = round(scenario.duration_s / scenario.plant_step_s)
    log_ticks = round(scenario.logging_period_s / scenario.plant_step_s)
    state = scenario.initial_state
    times, states, evaluations = [], [], []
    for index in range(count + 1):
        if index % log_ticks == 0 or index == count:
            times.append(index * scenario.plant_step_s)
            states.append(asdict(state))
            evaluations.append(
                asdict(evaluate_bicycle(scenario.config, state, scenario.controls))
            )
        if index < count:
            state = integrate_bicycle(
                scenario.config, state, scenario.controls, scenario.plant_step_s
            )
    inputs = asdict(scenario)
    payload: dict[str, Any] = {
        "schema": RECORD_SCHEMA,
        "scenario": inputs,
        "configuration_sha256": _content_id(inputs),
        "runtime": _runtime_identity(),
        "solver": {
            "family": "RK4",
            "version": 1,
            "substeps": "bounded lateral/yaw stiffness policy",
        },
        "units": {
            "position": "m",
            "heading": "rad",
            "velocity": "m/s",
            "yaw_rate": "rad/s",
            "time": "s",
            "force": "N",
            "yaw_moment": "N*m",
            "acceleration": "m/s^2",
            "yaw_acceleration": "rad/s^2",
        },
        "assumptions": [
            "Synthetic constant static axle loads and regularized linear lateral tires with a common friction circle.",
            "Prescribed axle contact-force requests; no motor, wheel rotation, battery or controller execution.",
            "Forward driving only; no suspension, aero or measured-car calibration.",
            "0.2 rad slip flag is an assumed small-slip diagnostic threshold, not a measured validity boundary.",
        ],
        "result": {
            "status": "completed",
            "plant_ticks": count,
            "time_s": times,
            "states": states,
            "evaluations": evaluations,
        },
    }
    payload["run_id"] = _content_id(payload)
    return payload


def decode_json(raw: str | bytes, *, maximum_bytes: int = MAX_RECORD_BYTES) -> Any:
    size = len(raw.encode("utf-8")) if isinstance(raw, str) else len(raw)
    if size > maximum_bytes:
        raise ValueError("bicycle JSON exceeds the size limit")
    try:
        return json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, UnicodeError, RecursionError) as error:
        raise ValueError("invalid bicycle JSON") from error


def replay_bicycle_record(value: dict[str, Any]) -> dict[str, Any]:
    """Check content identity then execute the stored model and compare all outputs."""
    if not isinstance(value, dict) or value.get("schema") != RECORD_SCHEMA:
        raise ValueError("unsupported basic dynamics record")
    unsigned = {key: item for key, item in value.items() if key != "run_id"}
    if _content_id(unsigned) != value.get("run_id"):
        raise ValueError("bicycle record content hash mismatch")
    scenario = BicycleScenario.from_dict(value.get("scenario"))
    if _content_id(asdict(scenario)) != value.get("configuration_sha256"):
        raise ValueError("bicycle configuration hash mismatch")
    actual = run_bicycle_scenario(scenario)

    def compare(expected: Any, observed: Any, path: str) -> None:
        if type(observed) in (int, float):
            if type(expected) not in (int, float) or not isclose(
                expected, observed, rel_tol=1e-9, abs_tol=1e-9
            ):
                raise ValueError(f"bicycle replay numeric mismatch at {path}")
        elif isinstance(observed, dict):
            if not isinstance(expected, dict) or set(expected) != set(observed):
                raise ValueError(f"bicycle replay fields differ at {path}")
            for key in observed:
                compare(expected[key], observed[key], path + "." + key)
        elif isinstance(observed, list):
            if not isinstance(expected, list) or len(expected) != len(observed):
                raise ValueError(f"bicycle replay sample count differs at {path}")
            for index, (left, right) in enumerate(zip(expected, observed, strict=True)):
                compare(left, right, f"{path}[{index}]")
        elif type(expected) is not type(observed) or expected != observed:
            raise ValueError(f"bicycle replay value differs at {path}")

    if set(value) != set(actual):
        raise ValueError("bicycle record fields differ from its schema")
    for name in ("result", "units", "solver", "assumptions"):
        compare(value.get(name), actual[name], name)
    return {
        "model_id": MODEL_ID,
        "model_agreement": True,
        "run_id": value["run_id"],
        "relative_tolerance": 1e-9,
        "absolute_tolerance_si": 1e-9,
        "scope": "Recorded-input numerical replay only; no physical validation",
    }


def run_basic_json(raw: str) -> str:
    scenario = BicycleScenario.from_dict(decode_json(raw, maximum_bytes=8192))
    return _canonical_json(run_bicycle_scenario(scenario))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.scenario and args.replay:
        parser.error("choose a scenario run or a recorded-result replay")
    if args.output and any(
        args.output.resolve() == path.resolve()
        or (args.output.exists() and args.output.samefile(path))
        for path in (args.scenario, args.replay)
        if path
    ):
        parser.error("output must not overwrite its input")
    try:
        if args.replay:
            if args.replay.stat().st_size > MAX_RECORD_BYTES:
                raise ValueError("bicycle record exceeds the size limit")
            result = replay_bicycle_record(decode_json(args.replay.read_bytes()))
        else:
            if args.scenario and args.scenario.stat().st_size > 8192:
                raise ValueError("scenario exceeds the size limit")
            scenario = (
                BicycleScenario.from_dict(decode_json(args.scenario.read_bytes()))
                if args.scenario
                else BicycleScenario()
            )
            result = run_bicycle_scenario(scenario)
        encoded = _canonical_json(result) + "\n"
        if args.output:
            args.output.write_text(encoded, encoding="utf-8")
        else:
            print(encoded)
    except (ValueError, OSError, TypeError) as error:
        parser.exit(2, f"basic dynamics: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
