"""Headless access to local evidence and reproducible profile smoke runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lapsim import ConstantControlsProfile, Controls, SpatialTrack, simulate_acceleration
from lapsim.events.api import AccelerationConfig

from . import (
    browse_records, build_vehicle, import_intake, list_profiles, load_intake,
    preview_profile,
)


def _smoke(profile_id: str, data_dir: str | None, distance_m: int, torque_nm: float) -> dict:
    vehicle, manifest = build_vehicle(profile_id, data_dir)
    track = SpatialTrack.from_cells(
        cell_length_m=(1.0,) * distance_m,
        curvature_per_m=(0.0,) * distance_m,
        closed=False,
    )
    result = simulate_acceleration(
        vehicle, track,
        ConstantControlsProfile(Controls(motor_torque_request_nm=torque_nm)),
        config=AccelerationConfig(rollout_distance_m=0.0),
    )
    manifest = manifest.with_run_context(
        event="acceleration", track="straight synthetic track",
        distance_m=distance_m, cell_length_m=1.0,
        controller="constant motor torque request", torque_request_nm=torque_nm,
        starting_speed_mps=0.0, rollout_distance_m=0.0,
        random_seed=None,
    )
    return {
        "profile_id": profile_id,
        "completed": result.completed,
        "elapsed_time_s": result.elapsed_time_s,
        "energy_kwh": result.energy_kwh,
        "failure_reason": result.failure_reason,
        "manifest": manifest.to_dict(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="LapSim vehicle profiles and local evidence")
    parser.add_argument("--data-dir", help="External ENME408 data bundle")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("profiles", help="List available vehicle profiles")
    validate = commands.add_parser("validate", help="Validate registry and source artifacts")
    validate.add_argument("bundle", type=Path)
    imported = commands.add_parser("import", help="Copy an immutable bundle to private local storage")
    imported.add_argument("bundle", type=Path)
    imported.add_argument("private_store", type=Path)
    records = commands.add_parser("records", help="Browse source records")
    records.add_argument("--profile")
    records.add_argument("--subsystem")
    records.add_argument("--configuration")
    records.add_argument("--source-id")
    records.add_argument("--model-use")
    records.add_argument("--query")
    preview = commands.add_parser("preview", help="Show selected, inherited, and unused inputs")
    preview.add_argument("profile")
    preview.add_argument("--output", type=Path)
    smoke = commands.add_parser("smoke", help="Run a short fixed straight acceleration scenario")
    smoke.add_argument("profiles", nargs="+", help="One or more profile IDs to compare")
    smoke.add_argument("--distance-m", type=int, default=20)
    smoke.add_argument("--torque-nm", type=float, default=80.0)
    smoke.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "profiles":
        output = [vars(item) if hasattr(item, "__dict__") else {
            "profile_id": item.profile_id, "name": item.name,
            "description": item.description, "source": item.source,
            "available": item.available,
        } for item in list_profiles(args.data_dir)]
    elif args.command == "validate":
        registry = load_intake(args.bundle, verify_artifacts=True)
        output = {
            "dataset_id": registry.dataset_id,
            "parameters": len(registry.parameters),
            "sources": len(registry.source_records),
            "questions": len(registry.open_questions),
            "registry_sha256": registry.fingerprint,
        }
    elif args.command == "import":
        output = {"private_bundle": str(import_intake(args.bundle, args.private_store))}
    elif args.command == "records":
        output = browse_records(
            args.data_dir, profile_id=args.profile, subsystem=args.subsystem,
            configuration=args.configuration, source_id=args.source_id,
            model_use=args.model_use, query=args.query,
        )
    elif args.command == "preview":
        output = preview_profile(args.profile, args.data_dir).to_dict()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    elif args.command == "smoke":
        if args.distance_m <= 0:
            parser.error("--distance-m must be positive")
        output = [_smoke(item, args.data_dir, args.distance_m, args.torque_nm) for item in args.profiles]
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    else:
        raise AssertionError(args.command)
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
