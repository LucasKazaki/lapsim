"""Bounded CPU checks of the spatial vehicle cell; no hardware or model calls."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def cases(family="cells"):
    dimensions = (
        (
            (35.0, 40.0, 42.5, 44.0),
            (5.0, 10.0, 25.0, 50.0, 75.0),
            ("drive", "hard_drive"),
            (0.0, 0.02),
            ("default", "relaxation"),
        )
        if family == "rpm"
        else (
            (0.0, 1.0e-6, 0.1, 5.0, 20.0, 42.5),
            (0.0001, 0.01, 0.5, 5.0, 50.0),
            ("coast", "small_drive", "drive", "hard_drive", "brake", "regen"),
            (0.0, 0.1, 1.55),
            ("default", "low_grip", "low_soc", "relaxation"),
        )
    )
    for index, values in enumerate(itertools.product(*dimensions)):
        yield dict(
            zip(
                ("speed", "distance", "control", "steering", "configuration"),
                values,
                strict=True,
            ),
            id=index,
        )


def peak_memory_bytes():
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(Counters),
        wintypes.DWORD,
    )
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    process = kernel.GetCurrentProcess()
    if not psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
        return None
    return counters.PeakWorkingSetSize


def run_case(case):
    from lapsim import Controls
    from vehicle_model import Vehicle

    vehicle = Vehicle(initial_speed_mps=case["speed"])
    if case["configuration"] == "low_grip":
        vehicle.tire.constant_friction_coefficient = 0.05
    if case["configuration"] == "low_soc":
        vehicle.battery.initial_state_of_charge = 0.000001
    if case["configuration"] == "relaxation":
        vehicle.tire.longitudinal_slip_relaxation_length_m = 1.0
    if case["control"] == "regen":
        vehicle.battery.initial_state_of_charge = 0.5
        vehicle.battery.max_charge_power_w = 80000.0
    vehicle.validate()
    vehicle.reset_state()
    controls = {"steering_angle_rad": case["steering"]}
    if case["control"] in {"small_drive", "drive", "hard_drive"}:
        controls["motor_torque_request_nm"] = {
            "small_drive": 1.0,
            "drive": 100.0,
            "hard_drive": 1.0e6,
        }[case["control"]]
    elif case["control"] == "brake":
        controls.update(front_brake_pressure_psi=300.0, rear_brake_pressure_psi=300.0)
    elif case["control"] == "regen":
        controls["rear_regenerative_brake_force_request_n"] = 1000.0
    before = vehicle.telemetry_snapshot()
    initial_soc = vehicle.battery.state_of_charge
    limit = vehicle.battery.discharge_power_limit_w
    try:
        vehicle.update_state(Controls(**controls), case["distance"])
    except (ValueError, RuntimeError) as error:
        after = vehicle.telemetry_snapshot()
        return {
            "case": case,
            "status": "rejected",
            "reason": str(error),
            "state_changed": before != after,
        }

    after = vehicle.telemetry_snapshot()
    failures = []
    if any(not math.isfinite(value) for value in after.values()):
        failures.append("nonfinite_telemetry")
    if not math.isclose(
        vehicle.distance_m, case["distance"], rel_tol=1e-10, abs_tol=1e-10
    ):
        failures.append("distance_mismatch")
    force = (
        vehicle.current_drive_force_n
        - vehicle.current_friction_braking_force_n
        - vehicle.current_regenerative_braking_force_n
        - vehicle.current_resistance_force_n
    )
    residual = (
        vehicle.effective_longitudinal_mass_kg * vehicle.longitudinal_acceleration_mps2
        - force
    )
    if abs(residual) > 1e-5:
        failures.append("force_balance")
    if vehicle.battery.current_power_w > limit + 1e-5:
        failures.append("dc_discharge_limit")
    power_residual = (
        vehicle.battery.current_power_w
        - vehicle.battery.current_a * vehicle.battery.terminal_voltage_v
    )
    if abs(power_residual) > 1e-5:
        failures.append("terminal_power_balance")
    expected_dc = (
        vehicle.drivetrain.inverter.current_motor_output_power_w
        / vehicle.drivetrain.inverter.efficiency
    )
    conversion_residual = (
        expected_dc - vehicle.drivetrain.inverter.current_dc_input_power_w
    )
    if conversion_residual > max(1e-4, expected_dc * 1e-7):
        failures.append("unpowered_motor_output")
    for state in vehicle.current_tire_states.all:
        if (
            state.normal_load_n < -1e-8
            or state.drive_force_n + state.braking_force_n
            > state.longitudinal_capacity_n + 1e-5
            or abs(state.lateral_force_n) > state.lateral_capacity_n + 1e-5
        ):
            failures.append("tire_capacity")
            break
    raw_soc = initial_soc - vehicle.battery.current_a * vehicle.time_s / (
        3600 * vehicle.battery.pack_capacity_ah
    )
    # Diagnostic only: interval-exhaustion is distinct from instantaneous limits.
    return {
        "case": case,
        "status": "failed" if failures else "passed",
        "failures": failures,
        "force_residual_n": residual,
        "terminal_power_residual_w": power_residual,
        "conversion_residual_w": conversion_residual,
        "interval_soc_unclamped": raw_soc,
        "final_speed_mps": vehicle.speed_mps,
        "timestep_s": vehicle.time_s,
        "battery_power_w": vehicle.battery.current_power_w,
    }


def run_chunk(chunk):
    started = time.process_time()
    results = [run_case(case) for case in chunk]
    return {
        "pid": os.getpid(),
        "cpu_seconds": time.process_time() - started,
        "peak_working_set_bytes": peak_memory_bytes(),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8, choices=range(1, 9))
    parser.add_argument("--family", choices=("cells", "rpm"), default="cells")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if (args.out / "protocol.json").exists():
        raise SystemExit(
            "choose a new output directory; retained sweeps are create-only"
        )
    # Keep native scientific libraries to one thread inside each CPU worker.
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"
    sys.path.insert(0, str(ROOT / "src"))
    requested = list(cases(args.family))
    source_files = [
        Path(__file__),
        ROOT / "src/vehicle_model/vehicle.py",
        ROOT / "src/vehicle_model/mech/tire.py",
        ROOT / "src/vehicle_model/powertrain/drivetrain.py",
        ROOT / "src/vehicle_model/electrical/battery.py",
    ]
    protocol = {
        "schema": "lapsim.cell-invariant-sweep.v1",
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_base": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "sources": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source_files
        },
        "python": sys.version,
        "platform": platform.platform(),
        "logical_cpus": os.cpu_count(),
        "workers": args.workers,
        "native_threads_per_worker": 1,
        "requested_cases": len(requested),
        "family": args.family,
        "case_dimensions": {
            name: sorted({row[name] for row in requested})
            for name in requested[0]
            if name != "id"
        },
        "checks": [
            "finite telemetry",
            "exact distance",
            "longitudinal force balance",
            "entry DC discharge limit",
            "terminal P=VI",
            "inverter power conversion",
            "nonnegative normal loads and tire combined capacity",
            "rejected cell leaves state unchanged",
        ],
        "diagnostics_only": [
            "unclamped Coulomb-count SOC may reveal interval exhaustion; not part of present instantaneous power contract"
        ],
        "boundaries": [
            "Synthetic parameter checks only; no real-car calibration or hardware actuation.",
            "Extreme but valid steering/cell sizes deliberately exercise limits; untraversable cells are expected rejections.",
        ],
    }
    (args.out / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    (args.out / "executed-sweep.py").write_bytes(Path(__file__).read_bytes())
    started = time.perf_counter()
    rows, resources = [], []
    chunks = [requested[index : index + 24] for index in range(0, len(requested), 24)]
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(run_chunk, chunk) for chunk in chunks]
        for future in as_completed(futures):
            result = future.result()
            rows.extend(result.pop("results"))
            resources.append(result)
            if len(rows) % 240 == 0:
                print(
                    json.dumps({"completed": len(rows), "requested": len(requested)}),
                    flush=True,
                )
    rows.sort(key=lambda row: row["case"]["id"])
    report = {
        "schema": "lapsim.cell-invariant-sweep.result.v1",
        "protocol_sha256": hashlib.sha256(
            (args.out / "protocol.json").read_bytes()
        ).hexdigest(),
        "elapsed_seconds": time.perf_counter() - started,
        "requested_cases": len(requested),
        "completed_cases": len(rows),
        "outcomes": dict(Counter(row["status"] for row in rows)),
        "failed_checks": dict(
            Counter(name for row in rows for name in row.get("failures", []))
        ),
        "rejected_state_mutations": sum(
            row.get("state_changed", False) for row in rows
        ),
        "rejection_reasons": dict(
            Counter(row["reason"] for row in rows if row["status"] == "rejected")
        ),
        "interval_soc_outside_bounds": sum(
            not 0 <= row["interval_soc_unclamped"] <= 1
            for row in rows
            if "interval_soc_unclamped" in row
        ),
        "resources": resources,
        "results": rows,
    }
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: value
                for key, value in report.items()
                if key not in {"resources", "results"}
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
