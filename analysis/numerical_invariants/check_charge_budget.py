"""Source-bound Coulomb-budget observations; never actuates or loads a model."""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from lapsim import Controls
from vehicle_model import OCVPackBattery, RCTheveninBattery, Vehicle


def state_hash(value):
    return hashlib.sha256(pickle.dumps(value, protocol=5)).hexdigest()


def battery_case(model, charging):
    initial = 1.0 - 1e-6 if charging else 1e-6
    battery = model(initial_state_of_charge=initial, max_charge_power_w=10000.0)
    power = -1000.0 if charging else 100.0
    current = battery.current_for_terminal_power_a(power)
    before = state_hash(battery)
    reason = None
    try:
        battery.update_state(power, 1.0)
    except ValueError as exc:
        reason = str(exc)
    return {
        "kind": model.__name__,
        "charging": charging,
        "power_w": power,
        "timestep_s": 1.0,
        "initial_soc": initial,
        "current_for_request_a": current,
        "requested_delta_ah": current / 3600.0,
        "capacity_ah": battery.pack_capacity_ah,
        "unclamped_expected_soc": initial
        - current / (3600.0 * battery.pack_capacity_ah),
        "stored_soc": battery.state_of_charge,
        "net_charge_removed_ah": battery.net_charge_removed_ah,
        "rejected": reason is not None,
        "reason": reason,
        "state_changed": before != state_hash(battery),
    }


def vehicle_case(initial_soc):
    vehicle = Vehicle(initial_speed_mps=5.0)
    vehicle.battery.initial_state_of_charge = initial_soc
    vehicle.validate()
    vehicle.reset_state()
    before = state_hash(vehicle)
    reason = None
    try:
        vehicle.update_state(Controls(motor_torque_request_nm=100.0), 0.5)
    except ValueError as exc:
        reason = str(exc)
    battery = vehicle.battery
    telemetry = vehicle.telemetry_snapshot()
    return {
        "initial_soc": initial_soc,
        "initial_speed_mps": 5.0,
        "distance_request_m": 0.5,
        "torque_request_nm": 100.0,
        "rejected": reason is not None,
        "reason": reason,
        "state_changed": before != state_hash(vehicle),
        "elapsed_s": vehicle.time_s,
        "current_a": battery.current_a,
        "power_w": battery.current_power_w,
        "net_charge_removed_ah": battery.net_charge_removed_ah,
        "capacity_ah": battery.pack_capacity_ah,
        "unclamped_soc_from_applied_current": initial_soc
        - battery.current_a * vehicle.time_s / (3600.0 * battery.pack_capacity_ah),
        "stored_soc": battery.state_of_charge,
        "telemetry": telemetry,
        "telemetry_sha256": hashlib.sha256(
            json.dumps(telemetry, sort_keys=True, allow_nan=False).encode()
        ).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("choose a new output; observation receipts are create-only")
    sources = (
        "src/vehicle_model/electrical/battery.py",
        "src/vehicle_model/vehicle.py",
        "src/vehicle_model/interfaces.py",
        "src/vehicle_model/mech/suspension.py",
        "tests/test_battery_charge_budget.py",
        "analysis/numerical_invariants/charge-budget-protocol-2026-10-15.json",
        "analysis/numerical_invariants/check_charge_budget.py",
    )
    result = {
        "schema": "lapsim.charge-budget-observation.v1",
        "head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "sources": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in sources
        },
        "direct_batteries": [
            battery_case(model, charging)
            for model in (OCVPackBattery, RCTheveninBattery)
            for charging in (False, True)
        ],
        "vehicle_exhausted_case1250": vehicle_case(1e-6),
        "vehicle_valid_control": vehicle_case(0.5),
        "scope": "Synthetic held-operating-point model observations; no real battery or vehicle validation",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "direct_accepted": sum(
                    not row["rejected"] for row in result["direct_batteries"]
                ),
                "vehicle_rejected": result["vehicle_exhausted_case1250"]["rejected"],
                "vehicle_unclamped_soc": result["vehicle_exhausted_case1250"][
                    "unclamped_soc_from_applied_current"
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
