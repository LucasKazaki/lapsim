"""Frozen passive CSV contract; ClockPlant records are not native evidence."""

import builtins
import copy
import csv
import importlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
from hashlib import sha256

import pytest

from lapsim.experiments import suspension_study as study
from test_suspension_study import ClockPlant


CSV_SCHEMA = "lapsim.native-telemetry-csv.v1"
CONTEXT_SCOPE = "supplied read-only inspection context; not attestation"
FRAME = "right-handed world X initially forward, Y left, Z up; chassis COM"
UNITS = "SI; steering request normalized, tire slip ratio dimensionless"
WHEELS = ("FL", "FR", "RL", "RR")
WHEEL_COLUMNS = (
    "center_world_x_m", "center_world_y_m", "center_world_z_m",
    "wheel_omega_local_y_rad_s", "native_axle_shaft_omega_rad_s",
    "computed_force_world_x_n", "computed_force_world_y_n", "computed_force_world_z_n",
    "applied_force_world_x_n", "applied_force_world_y_n", "applied_force_world_z_n",
    "tire_slip_ratio_dimensionless", "tire_slip_angle_rad",
    "suspension_spring_length_m", "suspension_spring_force_n",
    "suspension_damper_force_n", "driveline_wheel_torque_nm",
)
EXPECTED_HEADER = (
    "row_kind", "record_content_id", "record_receipt_id",
    "sample_index", "controller_event_index", "sample_time_s", "controller_event_time_s",
    "tire_force_source_time_s", "tire_kinematics_source_time_s",
    "applied_tire_force_source_time_s", "applied_tire_force_geometry_time_s",
    "com_world_x_m", "com_world_y_m", "com_world_z_m",
    "velocity_world_x_mps", "velocity_world_y_mps", "velocity_world_z_mps",
    "cardan_xyz_x_rad", "cardan_xyz_y_rad", "cardan_xyz_z_rad",
    "heading_world_xy_rad",
    "angular_velocity_world_x_rad_s", "angular_velocity_world_y_rad_s",
    "angular_velocity_world_z_rad_s", "mass_kg",
    "completed_interval_driveshaft_torque_nm", "completed_interval_steering_normalized",
    "completed_interval_braking_normalized", "event_driveshaft_torque_nm",
    "event_steering_normalized", "event_braking_normalized",
) + tuple(f"{wheel}_{name}" for wheel in WHEELS for name in WHEEL_COLUMNS) + (
    "metadata_json",
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def reseal(record):
    record["content_id"] = sha256(canonical(record["payload"]).encode()).hexdigest()
    record["receipt_id"] = sha256(canonical({
        key: value for key, value in record.items() if key != "receipt_id"
    }).encode()).hexdigest()


@pytest.fixture(scope="module")
def originals():
    package = Path(study.__file__).parents[1]
    source = {
        "code_commit": "a" * 40,
        "dirty_worktree": False,
        "hash_scope": "three study implementation files; UTF-8 bytes with CRLF normalized to LF",
        "files_sha256": {
            name: sha256((package / relative).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for name, relative in (
                ("native_plant.py", "dynamics/native_plant.py"),
                ("chrono_vehicle.py", "dynamics/chrono_vehicle.py"),
                ("suspension_study.py", "experiments/suspension_study.py"),
            )
        },
    }
    settings = {
        "short": dict(settle_s=1.0, maneuver_s=0.1, plant_step_s=0.001),
        "noncoincident": dict(settle_s=6.003, maneuver_s=0.101, logging_period_s=0.025),
        "dense": {},
        "sparse": dict(logging_period_s=0.05),
    }
    with pytest.MonkeyPatch.context() as patch:
        # Avoid Git entirely even while constructing portable clock fixtures.
        patch.setattr(study, "_source", lambda: copy.deepcopy(source))
        return {
            name: json.loads(json.dumps(study.run_study(
                study.SuspensionScenario(**options), plant_factory=ClockPlant,
            )))
            for name, options in settings.items()
        }


@pytest.fixture
def record(originals):
    return copy.deepcopy(originals["short"])


@pytest.fixture(autouse=True)
def forbid_engine_process_and_git(monkeypatch):
    original_import = builtins.__import__

    def checked_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith(("pychrono", "tkinter", "lapsim.dynamics.chrono_vehicle")):
            pytest.fail("CSV export imported a physics or GUI runtime")
        if name == "lapsim.dynamics" and "chrono_vehicle" in (fromlist or ()):
            pytest.fail("CSV export imported the native backend")
        return original_import(name, globals, locals, fromlist, level)

    def forbidden(*args, **kwargs):
        pytest.fail("CSV export started simulation, replay, Git or another process")

    monkeypatch.setattr(builtins, "__import__", checked_import)
    for name in ("Popen", "run", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    for name in ("run_study", "replay_study", "_source", "_code_identity"):
        monkeypatch.setattr(study, name, forbidden)


@pytest.fixture
def exporter():
    # Missing public module is an ordinary failing baseline, never a skip.
    return importlib.import_module("lapsim.experiments.suspension_export")


def parse_csv(text):
    reader = csv.DictReader(io.StringIO(text, newline=""))
    rows = list(reader)
    assert tuple(reader.fieldnames) == EXPECTED_HEADER
    assert all(set(row) == set(EXPECTED_HEADER) for row in rows)
    assert all(None not in row.values() for row in rows)
    return rows


def context(record):
    return study.inspect_study_record(record)


def number(value):
    return "" if value is None else repr(value)


def empty_row(record, kind):
    row = dict.fromkeys(EXPECTED_HEADER, "")
    row.update(row_kind=kind, record_content_id=record["content_id"],
               record_receipt_id=record["receipt_id"])
    return row


def expected_sample(record, index):
    sample = record["payload"]["samples"][index]
    expected = empty_row(record, "sample")
    expected.update(sample_index=str(index), sample_time_s=number(sample["time_s"]))
    for name in (
        "tire_force_source_time_s", "tire_kinematics_source_time_s",
        "applied_tire_force_source_time_s", "applied_tire_force_geometry_time_s",
    ):
        expected[name] = number(sample[name])
    for column, field, component in (
        ("com_world_x_m", "position_m", 0),
        ("com_world_y_m", "position_m", 1),
        ("com_world_z_m", "position_m", 2),
        ("velocity_world_x_mps", "velocity_mps", 0),
        ("velocity_world_y_mps", "velocity_mps", 1),
        ("velocity_world_z_mps", "velocity_mps", 2),
        ("cardan_xyz_x_rad", "cardan_xyz_rad", 0),
        ("cardan_xyz_y_rad", "cardan_xyz_rad", 1),
        ("cardan_xyz_z_rad", "cardan_xyz_rad", 2),
        ("angular_velocity_world_x_rad_s", "angular_velocity_rad_s", 0),
        ("angular_velocity_world_y_rad_s", "angular_velocity_rad_s", 1),
        ("angular_velocity_world_z_rad_s", "angular_velocity_rad_s", 2),
    ):
        expected[column] = number(sample[field][component])
    expected["heading_world_xy_rad"] = number(sample["heading_rad"])
    expected["mass_kg"] = number(sample["mass_kg"])
    expected["completed_interval_driveshaft_torque_nm"] = number(sample["command"]["driveshaft_torque_nm"])
    expected["completed_interval_steering_normalized"] = number(sample["command"]["steering"])
    expected["completed_interval_braking_normalized"] = number(sample["command"]["braking"])
    for index, wheel in enumerate(WHEELS):
        scalars = {
            "wheel_omega_local_y_rad_s": sample["wheel_omega_rad_s"][index],
            "native_axle_shaft_omega_rad_s": sample["native_axle_shaft_omega_rad_s"][index],
            "tire_slip_ratio_dimensionless": sample["tire_slip_ratio"][index],
            "tire_slip_angle_rad": sample["tire_slip_angle_rad"][index],
            "suspension_spring_length_m": sample["suspension_spring_length_m"][index],
            "suspension_spring_force_n": sample["suspension_spring_force_n"][index],
            "suspension_damper_force_n": sample["suspension_damper_force_n"][index],
            "driveline_wheel_torque_nm": sample["driveline_wheel_torque_nm"][index],
        }
        for axis, component in (("x", 0), ("y", 1), ("z", 2)):
            scalars[f"center_world_{axis}_m"] = sample["wheel_position_m"][index][component]
            scalars[f"computed_force_world_{axis}_n"] = sample["wheel_force_world_n"][index][component]
            scalars[f"applied_force_world_{axis}_n"] = sample["applied_wheel_force_world_n"][index][component]
        expected.update({f"{wheel}_{name}": number(value) for name, value in scalars.items()})
    return expected


def expected_event(record, index):
    event = record["payload"]["commands"][index]
    expected = empty_row(record, "controller_event")
    expected.update(
        controller_event_index=str(index), controller_event_time_s=number(event["time_s"]),
        event_driveshaft_torque_nm=number(event["request"]["driveshaft_torque_nm"]),
        event_steering_normalized=number(event["request"]["steering"]),
        event_braking_normalized=number(event["request"]["braking"]),
    )
    return expected


def test_noncoincident_streams_keep_original_order_and_all_recorded_fields(exporter, originals):
    record = copy.deepcopy(originals["noncoincident"])
    assert record["payload"]["frame"] == FRAME
    assert record["payload"]["units"] == UNITS
    supplied = context(record)
    before = copy.deepcopy((record, supplied))
    text = exporter.format_study_csv(record, inspection=supplied)
    rows = parse_csv(text)
    assert len(EXPECTED_HEADER) == len(set(EXPECTED_HEADER)) == 100
    assert [row["row_kind"] for row in rows] == ["metadata"] + ["sample"] * 247 + ["controller_event"] * 611
    assert rows[1:248] == [expected_sample(record, index) for index in range(247)]
    assert rows[248:] == [expected_event(record, index) for index in range(611)]
    expected_meta = empty_row(record, "metadata")
    expected_meta["metadata_json"] = canonical({
        "schema": CSV_SCHEMA, "inspection_scope": CONTEXT_SCOPE, "inspection": supplied,
    })
    assert rows[0] == expected_meta
    assert "\r" not in text and text.endswith("\n")
    # Forced boundaries are retained by their stored indices, not rounded log positions.
    assert float(rows[242]["sample_time_s"]) == record["payload"]["samples"][241]["time_s"]
    assert float(rows[247]["sample_time_s"]) == record["payload"]["samples"][246]["time_s"]
    assert float(rows[242]["sample_time_s"]) == pytest.approx(6.003)
    assert float(rows[247]["sample_time_s"]) == pytest.approx(6.104)
    assert (record, supplied) == before


def test_all_scalar_vector_and_wheel_slots_are_distinguishable_in_saved_json(exporter, record):
    sample = record["payload"]["samples"][1]
    sample.update(
        tire_force_source_time_s=0.001, tire_kinematics_source_time_s=0.002,
        applied_tire_force_source_time_s=0.003, applied_tire_force_geometry_time_s=0.004,
        position_m=[-0.0, 0.012345678901234567, 1.25], velocity_mps=[-3.5, 4.75, 6.125],
        cardan_xyz_rad=[-0.125, 0.25, 0.375], heading_rad=0.4567890123456789,
        angular_velocity_rad_s=[-7.25, 8.5, 9.75], mass_kg=17.125,
    )
    for field_index, field in enumerate((
        "wheel_omega_rad_s", "native_axle_shaft_omega_rad_s", "tire_slip_ratio",
        "tire_slip_angle_rad", "suspension_spring_length_m", "suspension_spring_force_n",
        "suspension_damper_force_n", "driveline_wheel_torque_nm",
    ), start=1):
        sample[field] = [field_index * 10.0 + wheel / 8 for wheel in range(4)]
    for field_index, field in enumerate((
        "wheel_position_m", "wheel_force_world_n", "applied_wheel_force_world_n",
    ), start=1):
        sample[field] = [[field_index * 100.0 + wheel * 10 + axis / 4
                          for axis in range(3)] for wheel in range(4)]
    reseal(record)
    # Independent JSON roundtrip freezes the actual saved representation being projected.
    record = json.loads(canonical(record))
    assert parse_csv(exporter.format_study_csv(record, inspection=context(record)))[2] == expected_sample(record, 1)


def test_dense_completed_interval_command_is_not_same_time_event_and_sparse_has_no_sample(exporter, originals):
    dense = originals["dense"]
    rows = parse_csv(exporter.format_study_csv(dense, inspection=context(dense)))
    samples = [row for row in rows if row["row_kind"] == "sample"]
    events = [row for row in rows if row["row_kind"] == "controller_event"]
    assert float(samples[301]["sample_time_s"]) == pytest.approx(6.02)
    assert float(samples[301]["completed_interval_driveshaft_torque_nm"]) == pytest.approx(0.8)
    assert events[602]["controller_event_time_s"] == repr(dense["payload"]["commands"][602]["time_s"])
    assert float(events[602]["event_driveshaft_torque_nm"]) == pytest.approx(1.6)
    assert samples[301]["controller_event_time_s"] == ""
    assert events[602]["sample_time_s"] == ""
    assert float(samples[300]["completed_interval_braking_normalized"]) == 0.2
    assert float(events[600]["event_braking_normalized"]) == 0.0
    sparse = originals["sparse"]
    sparse_rows = parse_csv(exporter.format_study_csv(sparse, inspection=context(sparse)))
    sparse_times = [float(row["sample_time_s"]) for row in sparse_rows if row["row_kind"] == "sample"]
    assert len(sparse_times) == 161
    assert all(abs(time_s - 6.02) > 0.001 for time_s in sparse_times)


def test_null_true_zero_and_finite_extremes_are_not_replaced_or_converted(exporter, record):
    sample = record["payload"]["samples"][1]
    sample["tire_force_source_time_s"] = 0.0
    sample["tire_kinematics_source_time_s"] = 0.001
    sample["applied_tire_force_source_time_s"] = 0.002
    sample["applied_tire_force_geometry_time_s"] = 0.003
    sample["position_m"] = [-0.0, 1e308, -1e308]
    sample["wheel_force_world_n"][0] = [1e308, -1e308, 1e-308]
    reseal(record)
    rows = parse_csv(exporter.format_study_csv(record, inspection=context(record)))
    first, next_sample = rows[1:3]
    assert first["tire_force_source_time_s"] == ""
    assert first["tire_kinematics_source_time_s"] == ""
    assert first["applied_tire_force_source_time_s"] == ""
    assert first["applied_tire_force_geometry_time_s"] == "0.0"
    assert next_sample["tire_force_source_time_s"] == "0.0"
    assert math.copysign(1, float(next_sample["com_world_x_m"])) == -1
    for column, value in (("com_world_y_m", 1e308), ("com_world_z_m", -1e308),
                          ("FL_computed_force_world_x_n", 1e308),
                          ("FL_computed_force_world_y_n", -1e308),
                          ("FL_computed_force_world_z_n", 1e-308)):
        assert float(next_sample[column]) == value
        assert math.isfinite(float(next_sample[column]))


def test_valid_stored_clock_offsets_are_copied_without_normalization(exporter, record):
    record["payload"]["samples"][1]["time_s"] += 1e-10
    record["payload"]["commands"][1]["time_s"] += 2e-10
    reseal(record)
    rows = parse_csv(exporter.format_study_csv(record, inspection=context(record)))
    sample = next(row for row in rows if row["sample_index"] == "1")
    event = next(row for row in rows if row["controller_event_index"] == "1")
    assert sample["sample_time_s"] == repr(record["payload"]["samples"][1]["time_s"])
    assert event["controller_event_time_s"] == repr(record["payload"]["commands"][1]["time_s"])
    assert float(sample["sample_time_s"]) != 0.02
    assert float(event["controller_event_time_s"]) != 0.01


@pytest.mark.parametrize("status", ("match", "mismatch", "unavailable"))
def test_supplied_inspection_scope_and_historical_status_are_retained(exporter, record, monkeypatch, status):
    if status == "mismatch":
        record["payload"]["source"]["files_sha256"]["suspension_study.py"] = "0" * 64
        reseal(record)
    if status == "unavailable":
        def unavailable():
            raise OSError("no source beside frozen module")
        monkeypatch.setattr(study, "_implementation_source", unavailable)
    supplied = context(record)
    # Pure projection must not look for current files again after context was supplied.
    monkeypatch.setattr(study, "_implementation_source", lambda: pytest.fail("formatter read source files"))
    with pytest.MonkeyPatch.context() as pure:
        for name in ("open", "read_bytes", "read_text"):
            pure.setattr(Path, name, lambda *a, **k: pytest.fail("formatter performed file I/O"))
        text = exporter.format_study_csv(record, inspection=supplied)
    metadata = json.loads(parse_csv(text)[0]["metadata_json"])
    assert metadata["inspection_scope"] == CONTEXT_SCOPE
    assert metadata["inspection"] == supplied
    assert metadata["inspection"]["checks"]["current_implementation_files"].startswith(status)
    assert metadata["inspection"]["checks"]["fresh_native_replay"] == "not run"
    assert metadata["inspection"]["checks"]["historical_timing"] == "recorded claims; not validated"


@pytest.mark.parametrize("change", ("context", "content_id", "receipt_id", "checks", "status", "replay", "timing"))
def test_formatter_rejects_unbound_or_malformed_inspection_context(exporter, record, change):
    supplied = context(record)
    if change == "context":
        supplied = None
    elif change in ("content_id", "receipt_id"):
        supplied["saved_" + change] = "0" * 64
    elif change == "checks":
        supplied["checks"] = None
    elif change == "status":
        supplied["checks"]["current_implementation_files"] = "physically validated"
    elif change == "replay":
        supplied["checks"]["fresh_native_replay"] = "passed"
    else:
        supplied["checks"]["historical_timing"] = None
    with pytest.raises(ValueError, match="inspection"):
        exporter.format_study_csv(record, inspection=supplied)


@pytest.mark.parametrize("changed_part", ("payload", "execution"))
def test_formatter_checks_record_integrity_even_when_context_ids_still_match(exporter, record, changed_part):
    supplied = context(record)
    if changed_part == "payload":
        record["payload"]["samples"][1]["mass_kg"] += 1
    else:
        record["execution"]["process_cpu_s"] += 1
    before = copy.deepcopy(record)
    with pytest.raises(ValueError, match="hash|integrity"):
        exporter.format_study_csv(record, inspection=supplied)
    assert record == before


@pytest.mark.parametrize("attack", ("=1+1", "+SUM(A1:A2)", "-2+3", "@SUM(A1)", "\t=1+1", "\r\n=1,2\"x"))
def test_untrusted_claim_text_stays_inside_json_object_metadata(exporter, record, attack):
    record["payload"]["model"] = {"profile_id": attack, "note": attack}
    record["payload"]["controller"] = attack
    record["payload"]["capabilities"]["backend_id"] = attack
    reseal(record)
    supplied = context(record)
    rows = parse_csv(exporter.format_study_csv(record, inspection=supplied))
    cell = rows[0]["metadata_json"]
    assert cell.startswith("{") and cell.endswith("}")
    assert "\r" not in cell and "\n" not in cell
    metadata = json.loads(cell)
    assert metadata["inspection"]["saved_provenance"]["model"]["profile_id"] == attack
    assert metadata["inspection"]["saved_provenance"]["controller"] == attack
    assert metadata["inspection"]["saved_capabilities_and_topology"]["backend_id"] == attack
    assert all(attack != value for row in rows for name, value in row.items() if name != "metadata_json")
    assert all(row["metadata_json"] == "" for row in rows[1:])


def test_cli_writes_atomic_csv_then_reports_actual_bytes(exporter, record, tmp_path, capsys):
    source, destination = tmp_path / "native.json", tmp_path / "native.csv"
    source.write_text(canonical(record), encoding="utf-8")
    before = source.read_bytes(), source.stat().st_mtime_ns
    destination.write_bytes(b"older evidence\n")
    assert exporter.main([str(source), "--output", str(destination)]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert json.loads(output.out) == {
        "schema": CSV_SCHEMA, "input_schema": "lapsim.native-suspension-study.v1",
        "input_content_id": record["content_id"], "input_receipt_id": record["receipt_id"],
        "row_counts": {"metadata": 1, "sample": 56, "controller_event": 110},
        "csv_sha256": sha256(destination.read_bytes()).hexdigest(),
    }
    assert parse_csv(destination.read_text(encoding="utf-8"))[1] == expected_sample(record, 0)
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["native.csv", "native.json"]


@pytest.mark.parametrize("claim,value", (("frame", "left-handed unknown frame"), ("units", "imperial")))
def test_unknown_frame_or_units_never_receive_fixed_si_headers_or_replace_output(exporter, record, tmp_path, capsys, claim, value):
    record["payload"][claim] = value
    reseal(record)
    supplied = context(record)  # Reader accepts recorded claims without a conversion promise.
    with pytest.raises(ValueError, match=claim):
        exporter.format_study_csv(record, inspection=supplied)
    source, destination = tmp_path / "native.json", tmp_path / "native.csv"
    source.write_text(canonical(record), encoding="utf-8")
    destination.write_bytes(b"preserved old CSV\n")
    before = source.read_bytes(), source.stat().st_mtime_ns, destination.read_bytes(), destination.stat().st_mtime_ns
    assert exporter.main([str(source), "--output", str(destination)]) == 1
    error = capsys.readouterr()
    assert claim in error.err and "Traceback" not in error.err and error.out == ""
    assert (source.read_bytes(), source.stat().st_mtime_ns, destination.read_bytes(), destination.stat().st_mtime_ns) == before


@pytest.mark.parametrize("failure", ("bad_json", "duplicate_key", "corrupt_hash", "nonfinite", "wheel_order", "oversize"))
def test_cli_invalid_record_preserves_input_and_destination(exporter, record, tmp_path, capsys, failure):
    source, destination = tmp_path / "native.json", tmp_path / "native.csv"
    if failure == "bad_json":
        raw = b"{broken"
    elif failure == "duplicate_key":
        raw = b'{"schema":1,"schema":2}'
    elif failure == "oversize":
        raw = b" " * 8_000_001
    else:
        if failure == "corrupt_hash":
            record["payload"]["samples"][1]["mass_kg"] += 1
        elif failure == "nonfinite":
            record["payload"]["samples"][1]["velocity_mps"][0] = float("nan")
        else:
            record["payload"]["wheel_order"] = ["RR", "RL", "FR", "FL"]
            reseal(record)
        raw = json.dumps(record).encode()
    source.write_bytes(raw)
    destination.write_bytes(b"old complete CSV\n")
    before = source.read_bytes(), source.stat().st_mtime_ns, destination.read_bytes(), destination.stat().st_mtime_ns
    assert exporter.main([str(source), "--output", str(destination)]) == 1
    output = capsys.readouterr()
    assert output.out == "" and output.err and "Traceback" not in output.err
    assert (source.read_bytes(), source.stat().st_mtime_ns, destination.read_bytes(), destination.stat().st_mtime_ns) == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["native.csv", "native.json"]


def test_cli_bounds_actual_read_even_when_source_changes_after_metadata(exporter, tmp_path, capsys):
    source, destination = tmp_path / "native.json", tmp_path / "native.csv"
    source.write_bytes(b"original evidence")
    destination.write_bytes(b"prior CSV")
    before = source.read_bytes(), source.stat().st_mtime_ns, destination.read_bytes()
    requested = []
    original_open = Path.open

    class ChangedSource(io.BytesIO):
        def read(self, size=-1):
            requested.append(size)
            return super().read(size)

    def changed_open(path, *args, **kwargs):
        if path == source:
            return ChangedSource(b"{invalid")
        return original_open(path, *args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "open", changed_open)
        assert exporter.main([str(source), "--output", str(destination)]) == 1
    assert requested == [8_000_001]
    output = capsys.readouterr()
    assert output.out == "" and output.err and "Traceback" not in output.err
    assert (source.read_bytes(), source.stat().st_mtime_ns, destination.read_bytes()) == before


def test_cli_missing_input_leaves_existing_destination_intact(exporter, tmp_path, capsys):
    destination = tmp_path / "native.csv"
    destination.write_bytes(b"prior CSV")
    before = destination.read_bytes(), destination.stat().st_mtime_ns
    assert exporter.main([str(tmp_path / "missing.json"), "--output", str(destination)]) == 1
    output = capsys.readouterr()
    assert output.out == "" and output.err and "Traceback" not in output.err
    assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before


@pytest.mark.parametrize("alias", ("same_path", "hardlink"))
def test_cli_rejects_alias_before_reading_or_writing(exporter, tmp_path, monkeypatch, capsys, alias):
    source = tmp_path / "input.json"
    source.write_bytes(b"preserved evidence even if not JSON")
    destination = source if alias == "same_path" else tmp_path / "alias.csv"
    if alias == "hardlink":
        os.link(source, destination)
    before = source.read_bytes(), source.stat().st_mtime_ns

    def forbidden(*args, **kwargs):
        pytest.fail("Aliased input reached reader, formatter, inspection or writer")

    for name in ("read_study_record", "inspect_study_record", "format_study_csv", "write_text_atomic"):
        monkeypatch.setattr(exporter, name, forbidden)
    assert exporter.main([str(source), "--output", str(destination)]) == 1
    output = capsys.readouterr()
    assert output.out == "" and "input" in output.err.lower() and "output" in output.err.lower()
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before
    assert destination.read_bytes() == before[0]


@pytest.mark.parametrize("failure", ("partial_write", "replace"))
def test_cli_failed_atomic_write_preserves_old_output_and_cleans_own_temp(exporter, record, tmp_path, monkeypatch, capsys, failure):
    source, destination = tmp_path / "native.json", tmp_path / "native.csv"
    source.write_text(canonical(record), encoding="utf-8")
    destination.write_bytes(b"old complete CSV\n")
    before = source.read_bytes(), source.stat().st_mtime_ns, destination.read_bytes(), destination.stat().st_mtime_ns
    original_write = Path.write_text

    def interrupted(path, text, **kwargs):
        original_write(path, text[:11], **kwargs)
        raise OSError("full disk after partial temp write")

    def failed_replace(*args):
        raise OSError("replace denied")

    if failure == "partial_write":
        monkeypatch.setattr(Path, "write_text", interrupted)
    else:
        monkeypatch.setattr(os, "replace", failed_replace)
    assert exporter.main([str(source), "--output", str(destination)]) == 1
    output = capsys.readouterr()
    assert output.out == "" and "Traceback" not in output.err
    assert ("full disk" if failure == "partial_write" else "replace denied") in output.err
    assert (source.read_bytes(), source.stat().st_mtime_ns, destination.read_bytes(), destination.stat().st_mtime_ns) == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["native.csv", "native.json"]


@pytest.mark.parametrize("argv,exit_code", ((["--help"], 0), ([], 2), (["input.json"], 2)))
def test_cli_help_and_required_output_do_no_file_work(exporter, monkeypatch, capsys, argv, exit_code):
    def forbidden(*args, **kwargs):
        pytest.fail("Help or incomplete command reached file I/O")

    for name in ("read_study_record", "inspect_study_record", "format_study_csv", "write_text_atomic"):
        monkeypatch.setattr(exporter, name, forbidden)
    with pytest.raises(SystemExit) as error:
        exporter.main(argv)
    assert error.value.code == exit_code
    output = capsys.readouterr()
    if exit_code == 0:
        assert "--output" in output.out and "CSV" in output.out
    else:
        assert output.err and "Traceback" not in output.err
