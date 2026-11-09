"""Run the legacy circle study or an explicit ordered skidpad candidate."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from hashlib import sha256
import json
from math import pi
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from analysis.events.common import print_result, write_event_outputs  # noqa: E402
from lapsim import (  # noqa: E402
    ConstantControlsProfile,
    Controls,
    ControlsProfile,
    EventResult,
    FSAE_2026_MI_SKIDPAD_SCORING,
    SkidpadConfig,
    SpatialTrack,
    TimedEventScoring,
    simulate_skidpad,
)
from lapsim import Curve, Track  # noqa: E402
from vehicle_model import Vehicle  # noqa: E402


DEFAULT_OUTPUT = ROOT / "outputs/events/skidpad"
STANDARD_SKIDPAD_RACING_LINE_RADIUS_M = 9.125
MAX_SEQUENCE_JSON_BYTES = 4 * 1024 * 1024
MAX_SEQUENCE_CSV_BYTES = 64 * 1024 * 1024
MAX_SEQUENCE_OUTPUT_BYTES = 80 * 1024 * 1024
PUBLIC_PROFILE_IDS = ("repository_baseline", "prius_2026_le")
CONE_POLICY_CHOICES = (
    "raw-only", "fsae_2026_rulebook", "fsae_2027_v1_rulebook",
    "fsae_2026_event_handbook",
)


def standard_skidpad_circle(cell_length_m: float = 0.25) -> SpatialTrack:
    """Return the centerline between the 15.25 m and 21.25 m circles."""

    return SpatialTrack.from_track(
        Track.from_segments(
            [Curve(radius_m=STANDARD_SKIDPAD_RACING_LINE_RADIUS_M, span_rad=2.0 * pi)]
        ),
        maximum_cell_length_m=cell_length_m,
        closed=True,
    )


def run(
    profile: ControlsProfile,
    track: SpatialTrack,
    *,
    vehicle: Vehicle | None = None,
    config: SkidpadConfig | None = None,
    scoring: TimedEventScoring = FSAE_2026_MI_SKIDPAD_SCORING,
) -> EventResult:
    """Programmatic entry point used by analysis sweeps."""

    return simulate_skidpad(
        vehicle if vehicle is not None else Vehicle(),
        track,
        profile,
        config=config,
        scoring=scoring,
    )


def _json_bytes(value: object) -> bytes:
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(raw) > MAX_SEQUENCE_JSON_BYTES:
        raise ValueError("Ordered skidpad JSON exceeds its 4 MiB output bound")
    return raw


def _write_new_bytes(path: Path, raw: bytes, *, maximum_bytes: int) -> dict:
    if len(raw) > maximum_bytes:
        raise ValueError("Ordered skidpad output exceeds its remaining byte bound")
    # Create-only output; a failure leaves a partial file rather than replacing
    # earlier evidence. File fsync is not a platform power-loss certificate.
    with path.open("xb") as stream:
        if stream.write(raw) != len(raw):
            raise OSError("Ordered skidpad output write was incomplete")
        stream.flush()
        os.fsync(stream.fileno())
    return {"path": path.name, "bytes": len(raw), "sha256": sha256(raw).hexdigest()}


class _BoundedCsvWriter:
    def __init__(self, stream, maximum_bytes: int):
        self.stream = stream
        self.maximum_bytes = maximum_bytes
        self.byte_count = 0
        self.hash = sha256()

    def write(self, text: str) -> int:
        raw = text.encode("utf-8")
        if self.byte_count + len(raw) > self.maximum_bytes:
            raise ValueError("Ordered skidpad CSV exceeds its explicit output bound")
        if self.stream.write(raw) != len(raw):
            raise OSError("Ordered skidpad CSV write was incomplete")
        self.byte_count += len(raw)
        self.hash.update(raw)
        return len(text)


def _write_sequence_telemetry(path: Path, telemetry, *, maximum_bytes: int) -> dict:
    names = tuple(telemetry)
    if (
        telemetry.sample_count > 5000 or len(names) > 2048
        or any(type(name) is not str or len(name) > 512 for name in names)
    ):
        raise ValueError("Ordered skidpad telemetry exceeds its bounded cell/channel shape")
    with path.open("xb") as stream:
        bounded = _BoundedCsvWriter(stream, min(maximum_bytes, MAX_SEQUENCE_CSV_BYTES))
        writer = csv.writer(bounded, lineterminator="\n")
        writer.writerow(names)
        for index in range(telemetry.sample_count):
            writer.writerow(telemetry[name][index] for name in names)
        stream.flush()
        os.fsync(stream.fileno())
    return {"path": path.name, "bytes": bounded.byte_count, "sha256": bounded.hash.hexdigest()}


def _sequence_output_directory(value: Path, data_dir: Path | None) -> Path:
    output = value.expanduser().resolve()
    if output.is_relative_to(ROOT.resolve()):
        raise ValueError("Ordered skidpad output must be outside the source or installed resource tree")
    if (ROOT / "build-info.json").is_file() and ROOT.name == "_resources":
        if output.is_relative_to(ROOT.resolve().parent.parent):
            raise ValueError("Skidpad output must be outside installed site-packages")
    if data_dir is not None and output.is_relative_to(data_dir.expanduser().resolve()):
        raise ValueError("Ordered skidpad output cannot modify the selected input-data directory")
    if output.exists() or value.is_symlink():
        raise ValueError("Ordered skidpad output already exists; choose a new directory")
    return output


def _build_sequence_vehicle(profile_id: str, data_dir: Path | None):
    from lapsim.profiles.adapter import build_vehicle

    if data_dir is not None:
        if not data_dir.is_dir():
            raise ValueError("The explicit profile data directory must exist")
        vehicle, manifest = build_vehicle(profile_id, data_dir)
        return vehicle, manifest, "explicit_data_directory"
    if profile_id not in PUBLIC_PROFILE_IDS:
        raise ValueError("A nonpublic vehicle profile requires an explicit --data-dir")
    # Passing None to build_vehicle would discover an ambient private intake.
    # A deliberate empty directory keeps public-profile selection independent
    # of environment variables and private home-directory contents.
    with TemporaryDirectory(prefix="lapsim-public-skidpad-intake-") as empty:
        vehicle, manifest = build_vehicle(profile_id, Path(empty))
    return vehicle, manifest, "public_profile_without_private_intake_discovery"


def _run_sequence(args) -> int:
    from lapsim.events.skidpad_sequence import (
        SkidpadSequenceConfig, simulate_skidpad_sequence, standard_skidpad_sequence,
    )
    from lapsim.profiles.adapter import snapshot_vehicle_config

    output = _sequence_output_directory(args.output_dir, args.data_dir)
    course = standard_skidpad_sequence(
        entry_length_m=args.entry_length_m, exit_length_m=args.exit_length_m,
        maximum_cell_length_m=args.cell_length_m,
    )
    config = SkidpadSequenceConfig(
        starting_speed_mps=args.starting_speed_mps,
        maximum_driving_time_s=120.0 if args.maximum_driving_time_s is None else args.maximum_driving_time_s,
        cone_count=0 if args.cone_count is None else args.cone_count,
        cone_penalty_policy=None if args.cone_penalty_policy == "raw-only" else args.cone_penalty_policy,
        declared_dnf_reason=args.declared_dnf_reason,
    )
    controls = Controls(motor_torque_request_nm=args.motor_torque_nm)
    profile = ConstantControlsProfile(controls)
    profile_id = "repository_baseline" if args.vehicle_profile is None else args.vehicle_profile
    vehicle, manifest, data_selection = _build_sequence_vehicle(profile_id, args.data_dir)
    model_before = snapshot_vehicle_config(vehicle)
    if model_before != manifest.to_dict()["model_config"]:
        raise ValueError("Resolved profile does not match the constructed vehicle configuration")
    model_hash = sha256(_json_bytes(model_before)).hexdigest()
    course_raw = _json_bytes(course.to_dict())
    control_description = {
        "kind": "ConstantControlsProfile", "controls": asdict(controls),
        "steering_field_usage": "Overridden by ordered track curvature; longitudinal requests retained",
    }
    control_hash = sha256(_json_bytes(control_description)).hexdigest()
    context = {
        "schema": "lapsim.ordered-skidpad-cli-context.v1",
        "event": "fsae_skidpad_sequence_candidate",
        "course_sha256": course.course_sha256,
        "course_raw_sha256": sha256(course_raw).hexdigest(),
        "geometry_sha256": course.geometry_sha256,
        "scenario": asdict(config),
        "controls_profile": control_description,
        "controls_profile_description_sha256": control_hash,
        "vehicle_model_config_sha256": model_hash,
        "data_selection": data_selection,
        "source_identity_scope": "Profile adapter reports captured build identity or checkout commit; no complete loaded-code authentication",
        "configuration_snapshot_scope": "Constructor fields before and after the run; not continuous observation",
        "qualification_or_execution_authority": False,
    }
    manifest = manifest.with_run_context(**context)
    manifest_raw = _json_bytes(manifest.to_dict())
    request_raw = _json_bytes({
        "schema": "lapsim.ordered-skidpad-cli-request.v1", "context": context,
        "profile_id": profile_id,
        "resolved_vehicle_raw_sha256": sha256(manifest_raw).hexdigest(),
        "raw_artifact_hashes_are_authentication": False,
    })
    output.mkdir(parents=True, exist_ok=False)
    artifacts = []

    def save(name: str, raw: bytes) -> None:
        remaining = MAX_SEQUENCE_OUTPUT_BYTES - sum(item["bytes"] for item in artifacts)
        artifacts.append(_write_new_bytes(output / name, raw, maximum_bytes=remaining))

    save("course.json", course_raw)
    save("resolved_vehicle.json", manifest_raw)
    save("request.json", request_raw)
    result = simulate_skidpad_sequence(vehicle, course, profile, config=config)
    model_after = None
    model_check_error = None
    try:
        model_after = snapshot_vehicle_config(vehicle)
        config_matches = model_after == model_before
        if not config_matches:
            model_check_error = "Vehicle configuration differs between endpoint snapshots"
    except (ValueError, TypeError, ArithmeticError) as error:
        config_matches = None
        model_check_error = "Post-run configuration snapshot unavailable: " + str(error)
    # A failed configuration check invalidates comparison, but must not discard
    # the model's already-returned raw result and telemetry.
    summary = {
        "schema": "lapsim.profiled-skidpad-sequence-run.v1",
        "request_raw_sha256": sha256(request_raw).hexdigest(),
        "resolved_vehicle_raw_sha256": sha256(manifest_raw).hexdigest(),
        "vehicle_model_config_sha256": model_hash,
        "vehicle_config_matches_before_after": config_matches,
        "vehicle_configuration_check_error": model_check_error,
        "vehicle_configuration_after_if_different": model_after if config_matches is False else None,
        "controls_profile_description_sha256": control_hash,
        "result": result.to_dict(),
        "manifest_and_constant_control_declarations_retained": True,
        "independent_authentication_or_matched_campaign_established": False,
        "qualification_or_execution_authority": False,
    }
    save("result.json", _json_bytes(summary))
    remaining = MAX_SEQUENCE_OUTPUT_BYTES - sum(item["bytes"] for item in artifacts)
    artifacts.append(_write_sequence_telemetry(output / "telemetry.csv", result.telemetry, maximum_bytes=remaining))
    index_raw = _json_bytes({
        "schema": "lapsim.ordered-skidpad-cli-artifacts.v1",
        "status": "LOCAL_OUTPUTS_WRITTEN",
        "files": artifacts,
        "index_hash_scope": "All completed payload files; excludes this index's own bytes",
        "numerical_path_completed": result.numerical_path_completed,
        "caller_declared_dnf": result.declared_dnf_reason is not None,
        "vehicle_config_matches_before_after": config_matches,
        "vehicle_configuration_check_error": model_check_error,
        "official_points": None, "event_ranking": None,
        "power_loss_durability_or_native_cleanup_verified": False,
        "qualification_or_execution_authority": False,
    })
    save("artifact_index.json", index_raw)
    print(json.dumps({
        "output_directory": str(output),
        "numerical_path_completed": result.numerical_path_completed,
        "unpenalized_average_s": result.unpenalized_average_s,
        "corrected_time_s": result.corrected_time_s,
        "vehicle_config_matches_before_after": config_matches,
        "artifact_index_sha256": sha256(index_raw).hexdigest(),
        "official_points": None, "qualification_or_execution_authority": False,
    }, sort_keys=True, allow_nan=False))
    if config_matches is not True:
        print(str(model_check_error) + "; raw outputs are preserved.", file=sys.stderr)
        return 2
    return 0 if result.numerical_path_completed and result.declared_dnf_reason is None else 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--motor-torque-nm", type=float, default=5.0)
    parser.add_argument("--starting-speed-mps", type=float, default=9.0)
    parser.add_argument("--cell-length-m", type=float, default=0.25)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--sequence", action="store_true", help="Run entry, right twice, left twice, then exit; no points")
    parser.add_argument("--entry-length-m", type=float)
    parser.add_argument("--exit-length-m", type=float)
    parser.add_argument("--cone-count", type=int)
    parser.add_argument("--cone-penalty-policy", choices=CONE_POLICY_CHOICES)
    parser.add_argument("--declared-dnf-reason")
    parser.add_argument("--vehicle-profile", help="Sequence mode: explicit profile ID, default repository_baseline")
    parser.add_argument("--data-dir", type=Path, help="Explicit optional source-profile intake directory")
    parser.add_argument("--maximum-driving-time-s", type=float)
    args = parser.parse_args(argv)
    if not args.sequence and (ROOT / "build-info.json").is_file():
        if args.output_dir is None:
            parser.error("Installed circle mode requires a new external --output-dir")
        try:
            args.output_dir = _sequence_output_directory(args.output_dir, None)
        except (OSError, ValueError) as error:
            parser.error(str(error))
    if args.sequence:
        if any(value is None for value in (
            args.entry_length_m, args.exit_length_m, args.cone_penalty_policy, args.output_dir,
        )):
            parser.error("--sequence requires --entry-length-m, --exit-length-m, --cone-penalty-policy and a new external --output-dir")
        try:
            return _run_sequence(args)
        except (OSError, ValueError, TypeError, ArithmeticError) as error:
            print("Ordered skidpad command stopped: " + str(error), file=sys.stderr)
            return 2
    if any(value is not None for value in (
        args.entry_length_m, args.exit_length_m, args.cone_count,
        args.cone_penalty_policy, args.declared_dnf_reason, args.vehicle_profile, args.data_dir,
    )):
        parser.error("Sequence/profile options require --sequence; legacy circle mode is unchanged")
    result = run(
        ConstantControlsProfile(
            Controls(motor_torque_request_nm=args.motor_torque_nm)
        ),
        standard_skidpad_circle(args.cell_length_m),
        config=SkidpadConfig(
            starting_speed_mps=args.starting_speed_mps,
            **({} if args.maximum_driving_time_s is None else {"maximum_driving_time_s": args.maximum_driving_time_s}),
        ),
    )
    print_result(result)
    summary_path, telemetry_path = write_event_outputs(result, args.output_dir or DEFAULT_OUTPUT)
    print(summary_path)
    print(telemetry_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
