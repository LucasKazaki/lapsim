"""Export validated saved native telemetry as passive, unit-labeled CSV."""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
from typing import Any

from .record_io import write_text_atomic
from .suspension_study import (
    inspect_study_record,
    read_study_record,
    validate_study_record,
)

SCHEMA = "lapsim.native-telemetry-csv.v1"
_CONTEXT_SCOPE = "supplied read-only inspection context; not attestation"
_FRAME = "right-handed world X initially forward, Y left, Z up; chassis COM"
_UNITS = "SI; steering request normalized, tire slip ratio dimensionless"
_WHEELS = ("FL", "FR", "RL", "RR")
_IDENTITY_COLUMNS = (
    "row_kind",
    "record_content_id",
    "record_receipt_id",
    "sample_index",
    "controller_event_index",
    "sample_time_s",
    "controller_event_time_s",
)
# Fixed projections only: (CSV column, stored field, optional component).
_SAMPLE_FIELDS = (
    ("tire_force_source_time_s", "tire_force_source_time_s", None),
    ("tire_kinematics_source_time_s", "tire_kinematics_source_time_s", None),
    ("applied_tire_force_source_time_s", "applied_tire_force_source_time_s", None),
    ("applied_tire_force_geometry_time_s", "applied_tire_force_geometry_time_s", None),
    ("com_world_x_m", "position_m", 0),
    ("com_world_y_m", "position_m", 1),
    ("com_world_z_m", "position_m", 2),
    ("velocity_world_x_mps", "velocity_mps", 0),
    ("velocity_world_y_mps", "velocity_mps", 1),
    ("velocity_world_z_mps", "velocity_mps", 2),
    ("cardan_xyz_x_rad", "cardan_xyz_rad", 0),
    ("cardan_xyz_y_rad", "cardan_xyz_rad", 1),
    ("cardan_xyz_z_rad", "cardan_xyz_rad", 2),
    ("heading_world_xy_rad", "heading_rad", None),
    ("angular_velocity_world_x_rad_s", "angular_velocity_rad_s", 0),
    ("angular_velocity_world_y_rad_s", "angular_velocity_rad_s", 1),
    ("angular_velocity_world_z_rad_s", "angular_velocity_rad_s", 2),
    ("mass_kg", "mass_kg", None),
    ("completed_interval_driveshaft_torque_nm", "command", "driveshaft_torque_nm"),
    ("completed_interval_steering_normalized", "command", "steering"),
    ("completed_interval_braking_normalized", "command", "braking"),
)
_EVENT_FIELDS = (
    ("event_driveshaft_torque_nm", "driveshaft_torque_nm"),
    ("event_steering_normalized", "steering"),
    ("event_braking_normalized", "braking"),
)
_WHEEL_FIELDS = (
    ("center_world_x_m", "wheel_position_m", 0),
    ("center_world_y_m", "wheel_position_m", 1),
    ("center_world_z_m", "wheel_position_m", 2),
    ("wheel_omega_local_y_rad_s", "wheel_omega_rad_s", None),
    ("native_axle_shaft_omega_rad_s", "native_axle_shaft_omega_rad_s", None),
    ("computed_force_world_x_n", "wheel_force_world_n", 0),
    ("computed_force_world_y_n", "wheel_force_world_n", 1),
    ("computed_force_world_z_n", "wheel_force_world_n", 2),
    ("applied_force_world_x_n", "applied_wheel_force_world_n", 0),
    ("applied_force_world_y_n", "applied_wheel_force_world_n", 1),
    ("applied_force_world_z_n", "applied_wheel_force_world_n", 2),
    ("tire_slip_ratio_dimensionless", "tire_slip_ratio", None),
    ("tire_slip_angle_rad", "tire_slip_angle_rad", None),
    ("suspension_spring_length_m", "suspension_spring_length_m", None),
    ("suspension_spring_force_n", "suspension_spring_force_n", None),
    ("suspension_damper_force_n", "suspension_damper_force_n", None),
    ("driveline_wheel_torque_nm", "driveline_wheel_torque_nm", None),
)
_HEADER = (
    _IDENTITY_COLUMNS
    + tuple(column for column, _, _ in _SAMPLE_FIELDS)
    + tuple(column for column, _ in _EVENT_FIELDS)
    + tuple(f"{wheel}_{column}" for wheel in _WHEELS for column, _, _ in _WHEEL_FIELDS)
    + ("metadata_json",)
)


def _number(value: int | float | None) -> str:
    return "" if value is None else repr(value)


def _inspection_metadata(record: dict[str, Any], inspection: Any) -> str:
    if (
        not isinstance(inspection, dict)
        or inspection.get("saved_content_id") != record["content_id"]
        or inspection.get("saved_receipt_id") != record["receipt_id"]
    ):
        raise ValueError("inspection context must bind both IDs to the saved record")
    checks = inspection.get("checks")
    if not isinstance(checks, dict):
        raise ValueError("inspection context requires a checks object")
    status = checks.get("current_implementation_files")
    if (
        not isinstance(status, str)
        or not (status == "match" or status.startswith(("mismatch;", "unavailable;")))
        or checks.get("fresh_native_replay") != "not run"
        or checks.get("historical_timing") != "recorded claims; not validated"
    ):
        raise ValueError("inspection context has unsupported check statuses")
    try:
        # The JSON-object prefix keeps arbitrary claims out of formula cells.
        return json.dumps(
            {
                "schema": SCHEMA,
                "inspection_scope": _CONTEXT_SCOPE,
                "inspection": inspection,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError("inspection context must contain finite JSON") from exc


def format_study_csv(record: dict[str, Any], *, inspection: Any) -> str:
    """Project recorded values and supplied context without I/O or reproduction.

    Inspection context is bound to the record's IDs, not authenticated here.
    Its current-source status is retained without observing local files again.
    """
    validate_study_record(record)
    payload = record["payload"]
    if payload["frame"] != _FRAME:
        raise ValueError("Unsupported recorded frame for fixed world-frame CSV columns")
    if payload["units"] != _UNITS:
        raise ValueError("Unsupported recorded units for fixed SI CSV columns")
    metadata = _inspection_metadata(record, inspection)

    def row(kind: str) -> dict[str, str]:
        values = dict.fromkeys(_HEADER, "")
        values.update(
            row_kind=kind,
            record_content_id=record["content_id"],
            record_receipt_id=record["receipt_id"],
        )
        return values

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=_HEADER, lineterminator="\n")
    writer.writeheader()
    metadata_row = row("metadata")
    metadata_row["metadata_json"] = metadata
    writer.writerow(metadata_row)
    for index, sample in enumerate(payload["samples"]):
        sample_row = row("sample")
        sample_row.update(
            sample_index=str(index), sample_time_s=_number(sample["time_s"])
        )
        for column, field, component in _SAMPLE_FIELDS:
            value = sample[field]
            if component is not None:
                value = value[component]
            sample_row[column] = _number(value)
        for wheel_index, wheel in enumerate(_WHEELS):
            for column, field, component in _WHEEL_FIELDS:
                value = sample[field][wheel_index]
                if component is not None:
                    value = value[component]
                sample_row[f"{wheel}_{column}"] = _number(value)
        writer.writerow(sample_row)
    # Event requests begin the next hold; never merge them with sample clocks.
    for index, event in enumerate(payload["commands"]):
        event_row = row("controller_event")
        event_row.update(
            controller_event_index=str(index),
            controller_event_time_s=_number(event["time_s"]),
        )
        for column, field in _EVENT_FIELDS:
            event_row[column] = _number(event["request"][field])
        writer.writerow(event_row)
    return stream.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="validated saved native study JSON")
    parser.add_argument(
        "--output", type=Path, required=True, help="explicit CSV destination"
    )
    args = parser.parse_args(argv)
    try:
        if args.input.resolve() == args.output.resolve() or (
            args.output.exists() and args.input.samefile(args.output)
        ):
            raise ValueError("CSV output must not overwrite the input record")
        record = read_study_record(args.input)
        inspection = inspect_study_record(record)
        text = format_study_csv(record, inspection=inspection)
        write_text_atomic(args.output, text)
        receipt = {
            "schema": SCHEMA,
            "input_schema": record["schema"],
            "input_content_id": record["content_id"],
            "input_receipt_id": record["receipt_id"],
            "row_counts": {
                "metadata": 1,
                "sample": len(record["payload"]["samples"]),
                "controller_event": len(record["payload"]["commands"]),
            },
            # The reused writer can translate LF on Windows: hash actual bytes.
            "csv_sha256": sha256(args.output.read_bytes()).hexdigest(),
        }
        print(json.dumps(receipt, indent=2))
        return 0
    except (
        OSError,
        ValueError,
        TypeError,
        OverflowError,
        RecursionError,
        csv.Error,
    ) as exc:
        print(f"Native telemetry CSV: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
