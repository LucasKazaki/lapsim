"""Saved-record inspection is independent of the optional physics runtime."""

import builtins
import json
import subprocess

import pytest

from lapsim.experiments import suspension_study as study
from test_suspension_study import ClockPlant


@pytest.fixture(scope="module")
def original_record():
    # Instrumentation only: this fixture establishes no native vehicle evidence.
    return study.run_study(
        study.SuspensionScenario(settle_s=1.0, maneuver_s=0.1, plant_step_s=0.001),
        plant_factory=ClockPlant,
    )


@pytest.fixture
def record(original_record):
    return json.loads(json.dumps(original_record))


def reseal(record):
    record["content_id"] = study._content_id(record["payload"])
    record["receipt_id"] = study._content_id(
        {key: value for key, value in record.items() if key != "receipt_id"}
    )


def test_inspect_cli_reads_a_saved_result_without_replay(tmp_path, record, monkeypatch, capsys):
    path = tmp_path / "saved-study.json"
    path.write_text(json.dumps(record), encoding="utf-8")

    def unexpected(*args, **kwargs):
        pytest.fail("Opening a saved result must not reproduce native physics")

    monkeypatch.setattr(study, "run_study", unexpected)
    monkeypatch.setattr(study, "replay_study", unexpected)
    assert study.main(["--inspect", str(path)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["checks"]["fresh_native_replay"] == "not run"
    assert summary["saved_content_id"] == record["content_id"]


def test_reader_and_summary_launch_no_backend_or_subprocess(
    tmp_path, record, monkeypatch
):
    path = tmp_path / "saved-study.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    before = path.read_bytes()
    original_import = builtins.__import__

    def checked_import(name, *args, **kwargs):
        assert not name.startswith("pychrono"), "Inspection imported optional physics"
        return original_import(name, *args, **kwargs)

    def unexpected(*args, **kwargs):
        pytest.fail("Inspection started reproduction, Git, or another subprocess")

    monkeypatch.setattr(builtins, "__import__", checked_import)
    monkeypatch.setattr(subprocess, "Popen", unexpected)
    for name in ("run_study", "replay_study", "_source", "_code_identity"):
        monkeypatch.setattr(study, name, unexpected)
    loaded = study.read_study_record(str(path))
    summary = study.inspect_study_record(loaded)
    assert loaded == record
    assert path.read_bytes() == before
    assert summary["checks"]["current_implementation_files"] == "match"
    assert summary["checks"]["historical_timing"] == "recorded claims; not validated"
    assert summary["historical_execution_claims"] == record["execution"]
    assert summary["stored_metrics_claims"] == record["payload"]["metrics"]
    assert summary["saved_capabilities_and_topology"] == record["payload"]["capabilities"]
    assert summary["saved_clocks"]["exported_samples"] == len(record["payload"]["samples"])


def test_historical_implementation_is_inspectable_but_cannot_replay(record, monkeypatch):
    record["payload"]["source"]["files_sha256"]["suspension_study.py"] = "0" * 64
    record["payload"]["source"]["code_commit"] = "a" * 40
    # Earlier v1 records measured settling only on logging samples.
    record["payload"]["metrics"].pop("settle_sampling")
    record["payload"]["metrics"]["settle_samples"] = 26
    reseal(record)
    summary = study.inspect_study_record(record)
    assert summary["checks"]["current_implementation_files"].startswith("mismatch")
    assert summary["saved_clocks"]["settling_sampling_claim"].startswith("not recorded")
    assert summary["checks"]["fresh_native_replay"] == "not run"
    monkeypatch.setattr(study, "run_study", lambda *a, **k: pytest.fail("Replay ignored source mismatch"))
    with pytest.raises(ValueError, match="implementation changed"):
        study.replay_study(record)


def test_unavailable_current_implementation_does_not_hide_a_saved_record(record, monkeypatch):
    def unavailable():
        raise OSError("implementation source unavailable")

    monkeypatch.setattr(study, "_implementation_source", unavailable)
    assert study.inspect_study_record(record)["checks"]["current_implementation_files"].startswith("unavailable")


def test_missing_saved_scenario_field_cannot_be_filled_from_current_defaults(record):
    record["payload"]["scenario"].pop("steering")
    reseal(record)
    with pytest.raises(ValueError, match="scenario fields"):
        study.inspect_study_record(record)


@pytest.mark.parametrize(
    "path,value",
    [
        (("payload", "capabilities"), {"device": "CPU"}),
        (("payload", "capabilities", "device"), "CUDA"),
        (("payload", "model"), []),
        (("payload", "metrics"), {}),
        (("payload", "metrics", "final_speed_mps"), True),
        (("payload", "metrics", "settle_samples"), False),
        (("payload", "metrics", "settle_sampling", "period_s"), 0),
        (("payload", "source", "files_sha256", "native_plant.py"), "bad hash"),
        (("payload", "wheel_order"), ["FR", "FL", "RL", "RR"]),
        (("payload", "samples", 1, "position_m"), [0, 0]),
        (("payload", "samples", 1, "wheel_force_world_n"), [[0, 0]] * 4),
        (("payload", "samples", 1, "wheel_omega_rad_s"), [0] * 3),
        (("payload", "samples", 1, "velocity_mps"), [True, 0, 0]),
        (("payload", "samples", 1, "mass_kg"), 0),
        (("payload", "samples", 1, "time_s"), 0.021),
        (("payload", "samples", 1, "tire_force_source_time_s"), 1.0),
        (("payload", "samples", 1, "applied_tire_force_geometry_time_s"), -0.1),
        (("payload", "samples", 0, "command", "braking"), False),
        (("payload", "samples", 1, "command", "braking"), 0.0),
        (("payload", "commands", 1, "time_s"), False),
        (("payload", "commands", 1, "request"), {}),
        (("execution", "logging_samples"), 1),
    ],
)
def test_resealed_malformed_saved_structure_is_rejected_without_physics(
    record, monkeypatch, path, value
):
    parent = record
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    reseal(record)
    monkeypatch.setattr(study, "run_study", lambda *a, **k: pytest.fail("Invalid inspection ran physics"))
    with pytest.raises(ValueError):
        study.inspect_study_record(record)


@pytest.mark.parametrize("collection", ("samples", "commands"))
def test_saved_array_counts_are_checked_independently_of_the_receipt(record, collection):
    record["payload"][collection].pop()
    reseal(record)
    with pytest.raises(ValueError, match="count"):
        study.inspect_study_record(record)


def test_unsealed_edit_and_nonfinite_data_are_rejected(record):
    record["payload"]["samples"][1]["position_m"][0] = 999
    with pytest.raises(ValueError, match="receipt hash"):
        study.inspect_study_record(record)
    record["payload"]["samples"][1]["position_m"][0] = float("nan")
    with pytest.raises(ValueError, match="finite JSON"):
        study.inspect_study_record(record)


def test_bounded_reader_rejects_oversize_data(tmp_path):
    path = tmp_path / "oversized.json"
    path.write_bytes(b" " * (study.MAX_BYTES + 1))
    with pytest.raises(ValueError, match="size limit"):
        study.read_study_record(path)


def test_inspection_cli_cannot_replace_input_or_write_an_output(tmp_path, record, capsys):
    path = tmp_path / "saved-study.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    before = path.read_bytes()
    assert study.main(["--inspect", str(path), "--output", str(path)]) == 1
    assert "--inspect" in capsys.readouterr().err
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_bad_inspection_reports_a_cli_error_without_traceback(tmp_path, capsys):
    path = tmp_path / "invalid.json"
    path.write_text("{invalid", encoding="utf-8")
    assert study.main(["--inspect", str(path)]) == 1
    message = capsys.readouterr().err
    assert "Suspension study:" in message and "Traceback" not in message


def test_replay_retains_fresh_full_payload_comparison_and_cancel_propagation(record, monkeypatch):
    actual = json.loads(json.dumps(record))
    actual["payload"]["model"]["fixture"] = "different fresh model"
    calls = []
    cancel = lambda: False

    def reproduce(scenario, *, cancel):
        calls.append(cancel)
        return actual

    monkeypatch.setattr(study, "run_study", reproduce)
    with pytest.raises(ValueError, match="Replay differs at model"):
        study.replay_study(record, cancel=cancel)
    assert calls == [cancel]


def test_run_and_replay_cli_summaries_remain_unchanged(tmp_path, record, monkeypatch, capsys):
    path = tmp_path / "saved-study.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    monkeypatch.setattr(study, "run_study", lambda *a, **k: record)
    monkeypatch.setattr(study, "replay_study", lambda *a, **k: record)
    expected = {
        "content_id": record["content_id"],
        "metrics": record["payload"]["metrics"],
        "execution": record["execution"],
    }
    assert study.main([]) == 0
    assert json.loads(capsys.readouterr().out) == expected
    assert study.main(["--replay", str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == expected


def test_implementation_hash_scope_remains_the_same_three_files():
    identity = study._implementation_source()
    assert identity["hash_scope"] == "three study implementation files; UTF-8 bytes with CRLF normalized to LF"
    assert set(identity["files_sha256"]) == {"native_plant.py", "chrono_vehicle.py", "suspension_study.py"}
