"""Matched synthetic equal-split/traction comparisons, with checked replay."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import asdict, replace
from math import isclose, radians
from pathlib import Path
from typing import Any

from lapsim.dynamics.bicycle import _finite
from lapsim.dynamics.conditions import (
    PlanarEnvironment,
    PlanarRoad,
    RectangularGripPatch,
)
from lapsim.dynamics.planar import PlanarState

from .basic_dynamics import decode_json
from .closed_loop import (
    ClosedLoopScenario,
    DriverPoint,
    replay_closed_loop,
    run_closed_loop,
)
from .dynamics_record import _canonical_json, _content_id

SCHEMA = "lapsim.control-comparison.v1"
CASES = {
    "launch": "Launch",
    "corner_exit": "Corner exit",
    "split_grip": "Split grip",
    "actuator_loss": "Rear actuator loss",
    "near_empty": "Near-empty pack",
    "full_braking": "Full-pack braking",
    "overlap": "Pedal overlap",
    "stale": "Stale sensors",
    "reordered": "Delayed and reordered",
    "restart": "Controller restart",
}
DEFAULT_REQUEST = {
    "case_id": "launch",
    "duration_s": 1.0,
    "speed_mps": 0.0,
    "steering_deg": 0.0,
}
COMPARISON_POLICY = "Identical driver, plant, sensor realization, limits and clocks; only allocation strategy changes. Compare motion, slip, unmet demand and energy together; no preferred winner is presumed."


def study_scenario(value: Any) -> ClosedLoopScenario:
    if not isinstance(value, dict) or set(value) != set(DEFAULT_REQUEST):
        raise ValueError(
            "study requires its exact case, duration, speed and steering fields"
        )
    if type(value["case_id"]) is not str or value["case_id"] not in CASES:
        raise ValueError("unknown synthetic study case")
    for name in ("duration_s", "speed_mps", "steering_deg"):
        _finite(value[name], name)
    if (
        not 0.1 <= value["duration_s"] <= 2
        or not 0 <= value["speed_mps"] <= 30
        or abs(value["steering_deg"]) > 10
    ):
        raise ValueError("study supports 0.1–2 s, 0–30 m/s and +/-10 degrees")
    duration = round(value["duration_s"] * 1e6)
    if duration % 10_000 or not isclose(
        duration / 1e6, value["duration_s"], abs_tol=1e-12, rel_tol=0
    ):
        raise ValueError("duration must resolve 10 ms control periods")
    speed = value["speed_mps"]
    steer = radians(value["steering_deg"])
    case = value["case_id"]
    if case in ("corner_exit", "split_grip", "full_braking") and speed == 0:
        speed = 6.0
    if case == "corner_exit" and steer == 0:
        steer = 0.06
    driver = (
        DriverPoint(0, steering_rad=steer),
        DriverPoint(duration // 2, 0.8, steering_rad=steer),
        DriverPoint(duration, 0.8, steering_rad=steer),
    )
    scenario = ClosedLoopScenario(
        duration_us=duration,
        initial_state=PlanarState(
            u_mps=speed,
            wheel_speeds_rad_s=(speed / 0.2, speed / 0.2, speed / 0.2, speed / 0.2),
        ),
        driver=driver,
    )
    if case == "split_grip":
        scenario = replace(
            scenario,
            environment=PlanarEnvironment(
                road=PlanarRoad(
                    patches=(RectangularGripPatch(-1000, 1000, 0, 1000, 0.2),)
                )
            ),
        )
    if case == "actuator_loss":
        scenario = replace(
            scenario, failed_rear_index=2, failure_time_us=(duration // 20_000) * 10_000
        )
    if case == "near_empty":
        scenario = replace(scenario, initial_soc=1e-8)
    if case == "full_braking":
        scenario = replace(
            scenario,
            initial_soc=1,
            driver=(
                DriverPoint(0, brake_fraction=0.2, steering_rad=steer),
                DriverPoint(duration, brake_fraction=0.2, steering_rad=steer),
            ),
        )
    if case == "overlap":
        scenario = replace(
            scenario,
            driver=(
                DriverPoint(0, 0.5, steering_rad=steer),
                DriverPoint(duration // 3, 0.5, 0.2, steer),
                DriverPoint(2 * duration // 3, 0, steering_rad=steer),
                DriverPoint(duration, 0.5, steering_rad=steer),
            ),
        )
    if case == "stale":
        scenario = replace(
            scenario, dropped_sequences=tuple(range(3, duration // 10_000 + 1))
        )
    if case == "reordered":
        scenario = replace(
            scenario,
            sensor_delay_us=0,
            extra_delays_us=((0, 30_000), (4, 80_000)),
            duplicate_sequences=(2,),
        )
    if case == "restart":
        scenario = replace(scenario, restart_times_us=((duration // 20_000) * 10_000,))
    return scenario


def metrics(record: dict) -> dict:
    result = record["result"]
    observations = result["observations"]
    events = result["controller_events"]
    p = result["final_state"]["plant"]
    dt = record["scenario"]["controller_period_us"] / 1e6
    return {
        "distance_x_m": p["x_m"],
        "final_speed_mps": p["u_mps"],
        "peak_observed_rear_slip": max(
            abs(w["slip_ratio"])
            for row in observations
            for w in row["plant"]["wheels"][2:]
        ),
        "pack_draw_j": result["pack_draw_j"],
        "unmet_command_impulse_nm_s": sum(e["unmet_command_torque_nm"] for e in events)
        * dt,
        "unmet_regen_impulse_nm_s": sum(e["unmet_regen_torque_nm"] for e in events)
        * dt,
        "limited_control_ticks": sum(
            bool(e["constraints"]) or e["core"]["allocator"]["status"] == "saturated"
            for e in events
        ),
        "inhibited_control_ticks": sum(
            not e["core"]["command_allowed"] for e in events
        ),
        "absolute_contact_force_error_ns": result["final_state"][
            "absolute_contact_force_error_ns"
        ],
        "energy_residual_j": result["energy_balance_residual_j"],
    }


def run_control_comparison(
    scenario: ClosedLoopScenario, *, cancel: Callable[[], bool] | None = None
) -> dict:
    if scenario.controller_backend_id != "python_reference":
        raise ValueError(
            "the paired UI study currently executes Python reference; other backends use the explicit single-run CLI"
        )
    base = replace(scenario, strategy="equal_split")
    a = run_closed_loop(base, cancel=cancel)
    b = run_closed_loop(replace(base, strategy="traction_limited"), cancel=cancel)
    record = {
        "schema": SCHEMA,
        "base_scenario": asdict(base),
        "runs": {"A": a, "B": b},
        "metrics": {"A": metrics(a), "B": metrics(b)},
        "comparison_policy": COMPARISON_POLICY,
    }
    record["run_id"] = _content_id(record)
    return record


def replay_control_comparison(record: Any) -> dict:
    if (
        not isinstance(record, dict)
        or set(record)
        != {"schema", "base_scenario", "runs", "metrics", "comparison_policy", "run_id"}
        or record["schema"] != SCHEMA
    ):
        raise ValueError("unsupported control comparison record")
    if record["run_id"] != _content_id(
        {k: v for k, v in record.items() if k != "run_id"}
    ):
        raise ValueError("comparison content identity mismatch")
    if record["comparison_policy"] != COMPARISON_POLICY:
        raise ValueError("comparison policy mismatch")
    base = ClosedLoopScenario.from_dict(record["base_scenario"])
    if (
        base.strategy != "equal_split"
        or base.controller_backend_id != "python_reference"
        or set(record["runs"]) != {"A", "B"}
        or set(record["metrics"]) != {"A", "B"}
    ):
        raise ValueError("unsupported paired strategy/backend")
    for label, strategy in (("A", "equal_split"), ("B", "traction_limited")):
        run = record["runs"][label]
        if ClosedLoopScenario.from_dict(run["scenario"]) != replace(
            base, strategy=strategy
        ):
            raise ValueError("comparison does not hold inputs constant")
        replay_closed_loop(run)
        expected = metrics(run)
        observed = record["metrics"][label]
        if not isinstance(observed, dict) or set(observed) != set(expected):
            raise ValueError("comparison metric fields mismatch")
        for key, value in expected.items():
            actual = observed[key]
            if (
                type(actual) not in (int, float)
                or (type(value) is int and (type(actual) is not int or actual != value))
                or not isclose(actual, value, rel_tol=1e-8, abs_tol=1e-8)
            ):
                raise ValueError("comparison metrics do not describe the stored run")
    return {
        "model_agreement": True,
        "run_id": record["run_id"],
        "runs_replayed": 2,
        "backend_id": "python_reference",
    }


def run_control_comparison_json(raw: str) -> str:
    return _canonical_json(
        run_control_comparison(study_scenario(decode_json(raw, maximum_bytes=4096)))
    )


def replay_control_comparison_json(raw: str) -> str:
    record = decode_json(raw, maximum_bytes=40_000_000)
    replay_control_comparison(record)
    return _canonical_json(record)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=tuple(CASES), default="launch")
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.replay:
            if args.output and (
                args.output.resolve() == args.replay.resolve()
                or (args.output.exists() and args.output.samefile(args.replay))
            ):
                raise ValueError("output must not overwrite input")
            if args.replay.stat().st_size > 40_000_000:
                raise ValueError("comparison file exceeds size limit")
            result = replay_control_comparison(
                decode_json(args.replay.read_bytes(), maximum_bytes=40_000_000)
            )
        else:
            result = run_control_comparison(
                study_scenario(dict(DEFAULT_REQUEST, case_id=args.case))
            )
        encoded = _canonical_json(result) + "\n"
        if args.output:
            args.output.write_text(encoded, encoding="utf-8")
        else:
            print(encoded)
    except (ValueError, OSError, TypeError) as error:
        parser.exit(2, "control study: " + str(error) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
