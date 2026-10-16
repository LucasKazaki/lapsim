"""Replay an explicit synthetic/normalized capture into JSON + CSV evidence.

Usage: python bench_replay.py scenario.json --output receipt.json --csv trace.csv
Only local files are read/written. There is deliberately no live IO adapter.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import hashlib
from itertools import combinations
import json
from pathlib import Path

from allocator import AllocationInput, AllocatorConfig
from command_guard import CommandGuardConfig, CommandGuardInput
from control_pipeline import ControlSample, PipelineConfig, replay_control_pipeline
from fault_state import FaultPolicy
from torque_numeric import NUMERIC_CONTRACT_VERSION
from cycle_clock import CLOCK_CONTRACT_VERSION

SCHEMA = "enme408-bench-replay/v1"
MAX_INPUT_BYTES = 2_000_000
SOURCE_FILES = ("allocation_contract.py", "allocator.py", "bench_replay.py",
                "command_guard.py", "control_pipeline.py", "fault_state.py",
                "guard_request_contract.py", "guard_overlap_observation.py", "guard_trusted_clear.py",
                "torque_numeric.py", "cycle_clock.py")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f"nonfinite JSON constant: {value}")


def _construct(cls, value, label):
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    try:
        return cls(**value)
    except TypeError as exc:
        raise ValueError(f"invalid {label} fields: {exc}") from exc


def load_scenario(raw: bytes):
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("scenario exceeds 2000000 bytes")
    value = json.loads(raw, object_pairs_hook=_object, parse_constant=_constant)
    if type(value) is not dict or set(value) != {"schema", "label", "provenance", "config", "samples"}:
        raise ValueError("scenario fields must be schema, label, provenance, config, samples")
    if value["schema"] != "enme408-control-scenario/v1":
        raise ValueError("unsupported scenario schema")
    if type(value["label"]) is not str or not value["label"].strip():
        raise ValueError("label must be a nonempty string")
    if type(value["provenance"]) is not str or not value["provenance"].strip():
        raise ValueError("provenance must identify synthetic data or a normalized capture source")
    # json.loads accepts exponent-overflow (1e999) as inf. Strict re-encoding
    # rejects it, including any nested field, before allocator execution.
    json.dumps(value, allow_nan=False)
    config = value["config"]
    if type(config) is not dict or set(config) != {"allocator", "guard", "fault", "period_ms"}:
        raise ValueError("invalid config fields")
    cfg = PipelineConfig(_construct(AllocatorConfig, config["allocator"], "allocator config"),
                         _construct(CommandGuardConfig, config["guard"], "guard config"),
                         _construct(FaultPolicy, config["fault"], "fault config"), config["period_ms"])
    if type(value["samples"]) is not list or not 1 <= len(value["samples"]) <= 4096:
        raise ValueError("samples must contain 1 to 4096 cycles")
    samples = []
    for index, item in enumerate(value["samples"]):
        if type(item) is not dict or set(item) - {"allocation", "guard", "restart_requested"}:
            raise ValueError(f"invalid sample {index} fields")
        if "allocation" not in item or "guard" not in item:
            raise ValueError(f"sample {index} requires allocation and guard")
        samples.append(ControlSample(_construct(AllocationInput, item["allocation"], "allocation input"),
                                      _construct(CommandGuardInput, item["guard"], "guard input"),
                                      item.get("restart_requested", False)))
    return value, cfg, samples


def make_receipt(raw: bytes) -> dict:
    value, cfg, samples = load_scenario(raw)
    records = replay_control_pipeline(samples, cfg)
    root = Path(__file__).resolve().parent
    return {
        "schema": SCHEMA,
        "numeric_contract_version": NUMERIC_CONTRACT_VERSION,
        "clock_contract_version": CLOCK_CONTRACT_VERSION,
        "label": value["label"],
        "provenance": value["provenance"],
        "scope": "host-only proposed commands; no hardware IO or vehicle validation",
        "torque_unit": "N*m",
        "wheel_order": ["slot_0", "slot_1", "slot_2", "slot_3"],
        "wheel_order_note": "Abstract slots; physical wheel mapping requires team evidence.",
        "scenario_sha256": hashlib.sha256(raw).hexdigest(),
        "source_sha256": {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                          for name in SOURCE_FILES},
        "config": asdict(cfg),
        "summary": {
            "cycles": len(records),
            "allowed_cycles": sum(row["command_allowed"] for row in records),
            "zero_command_cycles": sum(not any(row["command_nm"]) for row in records),
            "inhibited_cycles": sum(row["fault"]["next_state"] == "inhibited" for row in records),
            "recovery_pending_cycles": sum(row["fault"]["next_state"] == "recovery_pending" for row in records),
        },
        "records": records,
    }


def write_csv(receipt: dict, path: Path) -> None:
    fields = ["sequence", "now_ms", "allocator_status", "allocator_fault", "fault_state",
              "guard_status", "guard_reason", "clock_fault", "command_allowed", "command_reason",
              "requested_nm", "delivered_nm", "command_0_nm", "command_1_nm", "command_2_nm", "command_3_nm"]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in receipt["records"]:
            writer.writerow({
                "sequence": row["sequence"], "now_ms": row["now_ms"],
                "allocator_status": row["allocator"]["status"], "allocator_fault": row["allocator"]["fault"],
                "fault_state": row["fault"]["next_state"], "guard_status": row["guard"]["status"],
                "guard_reason": row["guard"]["reason"], "clock_fault": row["clock_fault"],
                "command_allowed": row["command_allowed"], "command_reason": row["command_reason"],
                "requested_nm": row["allocator"]["requested_nm"], "delivered_nm": row["allocator"]["delivered_nm"],
                **{f"command_{index}_nm": value for index, value in enumerate(row["command_nm"])},
            })


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args(argv)
    try:
        with args.scenario.open("rb") as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
        receipt = make_receipt(raw)
        encoded = json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n"
        paths = [args.scenario.resolve(), args.output.resolve()]
        if args.csv:
            paths.append(args.csv.resolve())
        if len(set(paths)) != len(paths):
            raise ValueError("scenario, output and CSV paths must be distinct")
        if any(a.exists() and b.exists() and a.samefile(b)
               for a, b in combinations(paths, 2)):
            raise ValueError("scenario, output and CSV paths must be distinct files")
        args.output.write_text(encoded, encoding="utf-8")
        if args.csv:
            write_csv(receipt, args.csv)
    except (ValueError, OSError, UnicodeError, RecursionError) as exc:
        parser.exit(2, f"bench replay: {exc}\n")
    print(json.dumps(receipt["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
