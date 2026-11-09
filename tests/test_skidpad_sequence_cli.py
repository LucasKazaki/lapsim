"""Existing skidpad command integration; doubles never establish run evidence."""

import csv
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from analysis.events import skidpad_points as cli
from lapsim.core.telemetry import Telemetry
from lapsim.events import skidpad_sequence
from lapsim.profiles import adapter
from vehicle_model import Vehicle


def _args(output, *extra):
    return [
        "--sequence", "--entry-length-m", "2", "--exit-length-m", "3",
        "--cell-length-m", "2", "--starting-speed-mps", "5",
        "--cone-penalty-policy", "raw-only", "--output-dir", str(output),
        *extra,
    ]


@pytest.mark.parametrize("selection", ["missing", "resource", "existing", "installation_sibling"])
def test_installed_circle_rejects_unsafe_output_before_computation(tmp_path, monkeypatch, selection):
    root = tmp_path / "installed/lapsim/_resources"
    root.mkdir(parents=True)
    (root / "build-info.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", root)
    runner = Mock(side_effect=AssertionError("Invalid installed output must stop before computation"))
    monkeypatch.setattr(cli, "run", runner)
    args = []
    if selection == "resource":
        args = ["--output-dir", str(root / "new-output")]
    elif selection == "installation_sibling":
        args = ["--output-dir", str(root.parent.parent / "new-output")]
    elif selection == "existing":
        output = tmp_path / "retained-output"
        output.mkdir()
        (output / "keep.txt").write_text("retained evidence", encoding="utf-8")
        args = ["--output-dir", str(output)]
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2
    runner.assert_not_called()
    assert not (root / "new-output").exists()


def _untrusted_result(*, completed=False, declared_dnf=None):
    """Only tests output/control flow; not the actual numerical model."""

    body = {
        "schema": "UNTRUSTED_TEST_SKIDPAD_RESULT",
        "numerical_path_completed": completed,
        "declared_dnf_reason": declared_dnf,
        "qualification_or_execution_authority": False,
    }
    return SimpleNamespace(
        numerical_path_completed=completed,
        unpenalized_average_s=6.0 if completed else None,
        corrected_time_s=None,
        declared_dnf_reason=declared_dnf,
        telemetry=Telemetry({"vehicle.time_s": (0.1,), "vehicle.speed_mps": (5.0,)}),
        to_dict=lambda: dict(body),
    )


def _assert_payload_inventory(output):
    index = json.loads((output / "artifact_index.json").read_bytes())
    assert index["status"] == "LOCAL_OUTPUTS_WRITTEN"
    assert index["official_points"] is None
    assert not index["qualification_or_execution_authority"]
    assert {entry["path"] for entry in index["files"]} == {
        "course.json", "resolved_vehicle.json", "request.json", "result.json", "telemetry.csv",
    }
    for entry in index["files"]:
        raw = (output / entry["path"]).read_bytes()
        assert len(raw) == entry["bytes"]
        assert sha256(raw).hexdigest() == entry["sha256"]
    return index


def test_sequence_cli_runs_actual_public_baseline_and_exports_exact_inputs(tmp_path, monkeypatch, capsys):
    """One real ordinary Vehicle run; no native worker or AWD policy execution."""

    output = tmp_path / "run"
    monkeypatch.setenv("LAPSIM_DATA_BUNDLE", str(tmp_path / "ambient-private-intake"))

    def no_ambient_intake():
        raise AssertionError("Public sequence mode must not discover private data")

    monkeypatch.setattr(adapter, "default_bundle_dir", no_ambient_intake)
    assert cli.main(_args(output)) == 0
    printed = json.loads(capsys.readouterr().out)
    index = _assert_payload_inventory(output)
    assert printed["artifact_index_sha256"] == sha256((output / "artifact_index.json").read_bytes()).hexdigest()
    assert index["numerical_path_completed"]
    assert not index["caller_declared_dnf"]
    request = json.loads((output / "request.json").read_bytes())
    course = json.loads((output / "course.json").read_bytes())
    manifest = json.loads((output / "resolved_vehicle.json").read_bytes())
    summary = json.loads((output / "result.json").read_bytes())
    context = manifest["run_context"]
    assert manifest["profile_id"] == "repository_baseline"
    assert manifest["registry_dataset_id"] is None
    assert manifest["registry_sha256"] is None
    assert manifest["model_config"] == adapter.snapshot_vehicle_config(Vehicle())
    assert context == request["context"]
    assert context["data_selection"] == "public_profile_without_private_intake_discovery"
    assert context["course_raw_sha256"] == sha256((output / "course.json").read_bytes()).hexdigest()
    assert context["controls_profile"]["controls"]["motor_torque_request_nm"] == 5.0
    assert context["scenario"]["starting_speed_mps"] == 5.0
    assert context["scenario"]["maximum_driving_time_s"] == 120.0
    assert summary["request_raw_sha256"] == sha256((output / "request.json").read_bytes()).hexdigest()
    assert summary["resolved_vehicle_raw_sha256"] == sha256((output / "resolved_vehicle.json").read_bytes()).hexdigest()
    assert summary["vehicle_config_matches_before_after"]
    assert not summary["independent_authentication_or_matched_campaign_established"]
    assert summary["result"]["numerical_path_completed"]
    assert summary["result"]["unpenalized_average_s"] > 0.0
    assert summary["result"]["corrected_time_s"] is None
    assert summary["result"]["official_points"] is None
    assert not summary["result"]["vehicle_configuration_identity_bound"]
    assert not course["geometry"]["closed"]
    assert not course["shared_canonical_imported_course_artifact"]
    with (output / "telemetry.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len(course["geometry"]["curvature_per_m"])
    assert float(rows[-1]["vehicle.time_s"]) == summary["result"]["elapsed_time_s"]


def test_explicit_data_directory_is_passed_without_fallback(tmp_path, monkeypatch):
    intake = tmp_path / "intake"
    intake.mkdir()
    original = adapter.build_vehicle
    seen = []

    def build(profile_id, data_dir):
        seen.append((profile_id, Path(data_dir)))
        return original(profile_id, data_dir)

    monkeypatch.setattr(adapter, "build_vehicle", build)
    monkeypatch.setattr(skidpad_sequence, "simulate_skidpad_sequence", lambda *a, **k: _untrusted_result())
    output = tmp_path / "run"
    assert cli.main(_args(output, "--data-dir", str(intake))) == 3
    assert seen == [("repository_baseline", intake)]
    manifest = json.loads((output / "resolved_vehicle.json").read_bytes())
    assert manifest["run_context"]["data_selection"] == "explicit_data_directory"


@pytest.mark.parametrize("profile_id,data_dir", [
    ("trev5_working_geometry", None),
    ("", None),
    ("repository_baseline", "missing-intake"),
])
def test_missing_external_input_never_discovers_or_substitutes_data(tmp_path, monkeypatch, profile_id, data_dir):
    build = Mock(side_effect=AssertionError("Missing explicit inputs must fail before build_vehicle"))
    monkeypatch.setattr(adapter, "build_vehicle", build)
    output = tmp_path / "run"
    extra = ["--vehicle-profile", profile_id]
    if data_dir is not None:
        extra += ["--data-dir", str(tmp_path / data_dir)]
    assert cli.main(_args(output, *extra)) == 2
    assert not output.exists()
    build.assert_not_called()


@pytest.mark.parametrize("flag", [
    "--entry-length-m", "--exit-length-m", "--cone-penalty-policy", "--output-dir",
])
def test_sequence_mode_requires_explicit_scenario_policy_and_output(tmp_path, monkeypatch, flag):
    args = _args(tmp_path / "run")
    index = args.index(flag)
    del args[index:index + 2]
    run = Mock(side_effect=AssertionError("Incomplete command must not start a run"))
    monkeypatch.setattr(cli, "_run_sequence", run)
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2
    run.assert_not_called()


def test_existing_output_is_preserved_before_any_vehicle_or_model_work(tmp_path, monkeypatch):
    output = tmp_path / "run"
    output.mkdir()
    sentinel = output / "earlier-result"
    sentinel.write_bytes(b"keep earlier raw results")
    build = Mock(side_effect=AssertionError("Existing output must fail first"))
    monkeypatch.setattr(cli, "_build_sequence_vehicle", build)
    assert cli.main(_args(output)) == 2
    assert sentinel.read_bytes() == b"keep earlier raw results"
    assert list(output.iterdir()) == [sentinel]
    build.assert_not_called()


def test_sequence_output_cannot_write_inside_source_or_input_data(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "ROOT", tmp_path / "installed-resources")
    build = Mock(side_effect=AssertionError("Protected output must fail before profile work"))
    monkeypatch.setattr(cli, "_build_sequence_vehicle", build)
    assert cli.main(_args(cli.ROOT / "new-output")) == 2
    intake = tmp_path / "intake"
    intake.mkdir()
    assert cli.main(_args(intake / "new-output", "--data-dir", str(intake))) == 2
    assert not (cli.ROOT / "new-output").exists()
    assert not (intake / "new-output").exists()
    build.assert_not_called()


def test_incomplete_run_preserves_result_telemetry_and_exits_three(tmp_path, monkeypatch):
    monkeypatch.setattr(skidpad_sequence, "simulate_skidpad_sequence", lambda *a, **k: _untrusted_result())
    output = tmp_path / "run"
    assert cli.main(_args(output)) == 3
    index = _assert_payload_inventory(output)
    assert not index["numerical_path_completed"]
    summary = json.loads((output / "result.json").read_bytes())
    assert summary["result"]["schema"] == "UNTRUSTED_TEST_SKIDPAD_RESULT"
    assert not summary["result"]["numerical_path_completed"]


def test_declared_dnf_is_not_returned_as_command_success(tmp_path, monkeypatch):
    result = _untrusted_result(completed=True, declared_dnf="External declared DNF")
    monkeypatch.setattr(skidpad_sequence, "simulate_skidpad_sequence", lambda *a, **k: result)
    output = tmp_path / "run"
    assert cli.main(_args(output, "--declared-dnf-reason", "External declared DNF")) == 3
    index = _assert_payload_inventory(output)
    assert index["numerical_path_completed"]
    assert index["caller_declared_dnf"]


def test_configuration_difference_retains_returned_raw_result_and_marks_mismatch(tmp_path, monkeypatch):
    def change_vehicle(vehicle, *args, **kwargs):
        vehicle.mass_kg *= 1.1
        return _untrusted_result(completed=True)

    monkeypatch.setattr(skidpad_sequence, "simulate_skidpad_sequence", change_vehicle)
    output = tmp_path / "run"
    assert cli.main(_args(output)) == 2
    index = _assert_payload_inventory(output)
    assert index["vehicle_config_matches_before_after"] is False
    summary = json.loads((output / "result.json").read_bytes())
    assert summary["result"]["numerical_path_completed"]
    assert summary["vehicle_config_matches_before_after"] is False
    assert summary["vehicle_configuration_check_error"]
    assert summary["vehicle_configuration_after_if_different"]["fields"]["mass_kg"] > 0
    assert (output / "telemetry.csv").is_file()


def test_unavailable_postrun_snapshot_does_not_discard_raw_failure_output(tmp_path, monkeypatch):
    original = adapter.snapshot_vehicle_config
    calls = 0

    def snapshot(vehicle):
        nonlocal calls
        calls += 1
        if calls == 1:
            return original(vehicle)
        raise ValueError("UNTRUSTED test post-run invalid configuration")

    monkeypatch.setattr(adapter, "snapshot_vehicle_config", snapshot)
    monkeypatch.setattr(skidpad_sequence, "simulate_skidpad_sequence", lambda *a, **k: _untrusted_result())
    output = tmp_path / "run"
    assert cli.main(_args(output)) == 2
    index = _assert_payload_inventory(output)
    assert index["vehicle_config_matches_before_after"] is None
    assert index["vehicle_configuration_check_error"]
    assert not index["numerical_path_completed"]


def test_csv_quota_failure_retains_raw_summary_and_partial_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(skidpad_sequence, "simulate_skidpad_sequence", lambda *a, **k: _untrusted_result())
    monkeypatch.setattr(cli, "MAX_SEQUENCE_CSV_BYTES", 10)
    output = tmp_path / "run"
    assert cli.main(_args(output)) == 2
    assert (output / "result.json").is_file()
    assert (output / "telemetry.csv").is_file()
    assert (output / "telemetry.csv").stat().st_size <= 10
    assert not (output / "artifact_index.json").exists()


def test_create_only_writer_preserves_prior_bytes_and_enforces_bound(tmp_path):
    path = tmp_path / "payload.json"
    path.write_bytes(b"prior")
    with pytest.raises(FileExistsError):
        cli._write_new_bytes(path, b"new", maximum_bytes=10)
    assert path.read_bytes() == b"prior"
    other = tmp_path / "other.json"
    with pytest.raises(ValueError):
        cli._write_new_bytes(other, b"too large", maximum_bytes=2)
    assert not other.exists()


def test_legacy_circle_cli_defaults_and_helpers_are_preserved(monkeypatch):
    sentinel = object()
    run = Mock(return_value=sentinel)
    print_result = Mock()
    outputs = Mock(return_value=(Path("summary"), Path("telemetry")))
    monkeypatch.setattr(cli, "run", run)
    monkeypatch.setattr(cli, "print_result", print_result)
    monkeypatch.setattr(cli, "write_event_outputs", outputs)
    assert cli.main([]) == 0
    profile, track = run.call_args.args
    assert profile.controls.motor_torque_request_nm == 5.0
    assert track.closed
    assert all(value > 0.0 for value in track.curvature_per_m)
    assert run.call_args.kwargs["config"].starting_speed_mps == 9.0
    assert run.call_args.kwargs["config"].maximum_driving_time_s == 60.0
    print_result.assert_called_once_with(sentinel)
    outputs.assert_called_once_with(sentinel, cli.DEFAULT_OUTPUT)


def test_circle_mode_rejects_sequence_options_instead_of_ignoring_them(monkeypatch):
    run = Mock(side_effect=AssertionError("Wrong-mode options cannot start a run"))
    monkeypatch.setattr(cli, "run", run)
    with pytest.raises(SystemExit) as error:
        cli.main(["--vehicle-profile", "prius_2026_le"])
    assert error.value.code == 2
    run.assert_not_called()
