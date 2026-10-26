"""One/two-axis bounded synthetic sweeps and PlotJuggler-compatible CSV export."""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, replace
import io
from itertools import product
import json
from pathlib import Path
import time

from .controller_tournament import canonical, identity, sources
from .record_io import read_json_bounded, write_text_atomic
from .tournament_rollout import BOUNDS, PROFILES, Case, Controller, number, rollout

PARAMETERS = {
    "mass_kg": {"unit": "kg", "low": 200, "high": 500, "owner": "physical"},
    "drag_area_m2": {"unit": "m^2", "low": 0, "high": 2, "owner": "physical"},
    "gear_ratio": {"unit": "ratio", "low": 2, "high": 8, "owner": "physical"},
    "grip": {"unit": "multiplier", "low": .2, "high": 1.3, "owner": "case"},
    "initial_soc": {"unit": "fraction", "low": 0, "high": 1, "owner": "case"},
    **{key: {"unit": "fraction" if key not in ("yaw_kp", "yaw_ki") else "N*m/(rad/s)",
             "low": lo, "high": hi, "owner": "controller"} for key, (lo, hi) in BOUNDS.items()},
}
PARAMETERS["yaw_ki"]["unit"] = "N*m/rad"


def axes_from(config):
    axes = config.get("axes")
    if not isinstance(axes, list) or not 1 <= len(axes) <= 2:
        raise ValueError("choose one or two sweep axes")
    result = []
    names = set()
    for axis in axes:
        key = axis["parameter"]
        if key not in PARAMETERS or key in names:
            raise ValueError("unknown or duplicate sweep axis")
        names.add(key)
        spec = PARAMETERS[key]
        lo, hi, count = axis["minimum"], axis["maximum"], axis["count"]
        number(lo, key, spec["low"], spec["high"])
        number(hi, key, spec["low"], spec["high"])
        if lo > hi or type(count) is not int or not 2 <= count <= 5:
            raise ValueError("each axis requires an ordered range and 2â€“5 points")
        result.append((key, [lo + (hi - lo) * i / (count - 1) for i in range(count)]))
    return result


def export_timeseries(record, path):
    """One monotonic simulation time axis; no synthetic padding or alignment."""
    fields = ["time_s", "x_m", "y_m", "u_mps", "v_mps", "heading_rad", "yaw_rad_s",
              "progress_m", "cross_track_m", "pack_energy_j", "pack_power_w", "brake_shortfall_nm"]
    for wheel in ("fl", "fr", "rl", "rr"):
        fields += [f"{stage}_{wheel}_nm" for stage in ("requested", "proposed", "limited", "achieved", "friction")]
        fields += [f"slip_{wheel}_ratio", f"utilization_{wheel}_ratio"]
    extras=('policy_mode_code','brake_pedal_fraction','regen_request_nm','pack_soc_ratio')
    if any(any(key in row for key in extras) for row in record['telemetry']):
        if not all(all(key in row for key in extras) for row in record['telemetry']):raise ValueError('Incomplete optional policy telemetry')
        fields+=list(extras)
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=fields)
    writer.writeheader()
    previous = -1.0
    for sample in record["telemetry"]:
        assert sample["t_s"] > previous
        previous = sample["t_s"]
        row = {key: sample[key] for key in fields if key in sample}
        row["time_s"] = sample["t_s"]
        for i, wheel in enumerate(("fl", "fr", "rl", "rr")):
            for stage in ("requested", "proposed", "limited", "achieved", "friction"):
                row[f"{stage}_{wheel}_nm"] = sample[f"{stage}_nm"][i]
            row[f"slip_{wheel}_ratio"] = sample["slip"][i]
            row[f"utilization_{wheel}_ratio"] = sample["utilization"][i]
        writer.writerow(row)
    write_text_atomic(path, text.getvalue(), newline="")
    # Independently parse exported numbers and check sample/time/pose parity.
    loaded = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
    assert len(loaded) == len(record["telemetry"])
    assert all(float(a["time_s"]) == b["t_s"] and float(a["x_m"]) == b["x_m"]
               for a, b in zip(loaded, record["telemetry"], strict=True))


def run_sweep(config, output, *, cancel=lambda: False, rollout_fn=rollout, wall_seconds=180):
    axes = axes_from(config)
    profile = config.get("profile", "synthetic_awd")
    if profile not in PROFILES:
        raise ValueError("source-backed 2025-derived AWD profile is awaiting data review")
    controller = Controller(config.get("philosophy", "traction"))
    course = config.get("course", "stadium")
    base_case = Case("sweep", course=course, course_bundle=config.get("course_bundle"),
        reverse=config.get("reverse", False), mirror=config.get("mirror", False),
        duration_s=30 if course == "stadium" else 60)
    output.mkdir(parents=True, exist_ok=True)
    cache = output.parent / "sweep-cache"
    cache.mkdir(exist_ok=True)
    source = sources()
    started = time.perf_counter()
    result = {"schema": "lapsim.sweep.v1", "configuration": config,
        "parameters": PARAMETERS, "sources": source, "rows": [], "status": "running",
        "total": len(axes[0][1]) * (len(axes[1][1]) if len(axes) == 2 else 1)}

    def save():
        write_text_atomic(output / "sweep.json", canonical(result))
        fields = [a[0] for a in axes] + ["eligible", "lap_time_s", "net_energy_kwh", "max_tire_utilization", "max_slip", "max_sideslip_rad", "limited_ticks", "brake_shortfall_nm_s", "constraint_violations", "cached", "run_id"]
        text = io.StringIO(newline="")
        writer = csv.DictWriter(text, fieldnames=fields)
        writer.writeheader()
        for row in result["rows"]:
            writer.writerow({key: row.get(key) for key in fields})
        write_text_atomic(output / "sweep.csv", text.getvalue(), newline="")
    save()
    for values in product(*(a[1] for a in axes)):
        if cancel() or time.perf_counter() - started >= wall_seconds:
            result["status"] = "cancelled" if cancel() else "paused_budget"
            save()
            return result
        c, case, overrides = controller, base_case, {}
        parameters = dict(zip((a[0] for a in axes), values, strict=True))
        for key, value in parameters.items():
            owner = PARAMETERS[key]["owner"]
            if owner == "controller":
                c = replace(c, **{key: value})
            elif owner == "case":
                case = replace(case, **{key: value})
            else:
                overrides[key] = value
        key = identity({"sources": source, "controller": asdict(c), "case": asdict(case),
                        "overrides": overrides, "profile": profile})
        cached = (cache / f"{key}.json").exists()
        if cached:
            record = read_json_bounded(cache / f"{key}.json", maximum_bytes=5_000_000)
        else:
            record = rollout_fn(c, case, profile=profile, parameter_overrides=overrides)
            write_text_atomic(cache / f"{key}.json", canonical(record))
        export_timeseries(record, output / f"timeseries-{key}.csv")
        row = {**parameters, **record["metrics"], "eligible": record["eligible"],
               "constraint_violations": ";".join(record["violations"]), "cached": cached, "run_id": key}
        result["rows"].append(row)
        save()
        print(f"sweep {len(result['rows'])}/{result['total']} {parameters} {record['status']} cached={cached}", flush=True)
    result["status"] = "completed"
    save()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_sweep(read_json_bounded(args.config, maximum_bytes=10000), args.output)
    print(result["status"])


if __name__ == "__main__":
    main()
