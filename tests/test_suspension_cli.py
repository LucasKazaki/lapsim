"""Pure normal-CLI contracts; clock fixtures are not native-physics evidence."""

import builtins
import json
from dataclasses import asdict

import pytest

from lapsim.experiments import suspension_study as study
from test_suspension_study import ClockPlant


@pytest.fixture(scope="module")
def original_record():
    result = study.run_study(
        study.SuspensionScenario(settle_s=1.0, maneuver_s=0.1, plant_step_s=0.001),
        plant_factory=ClockPlant,
    )
    return json.loads(json.dumps(result))


@pytest.fixture
def record(original_record):
    return json.loads(json.dumps(original_record))


@pytest.fixture(autouse=True)
def forbid_optional_engine_import(monkeypatch):
    original_import = builtins.__import__

    def checked_import(name, *args, **kwargs):
        if name.startswith("pychrono") or name == "lapsim.dynamics.chrono_vehicle":
            pytest.fail("CLI contract imported the optional native backend")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", checked_import)


def unexpected_work(*args, **kwargs):
    pytest.fail("Invalid CLI options reached file I/O or simulation work")


@pytest.fixture
def forbid_work(monkeypatch):
    for name in (
        "read_json_bounded",
        "run_study",
        "replay_study",
        "inspect_study_record",
        "write_text_atomic",
    ):
        monkeypatch.setattr(study, name, unexpected_work)


def expected_stdout(record):
    return {
        "content_id": record["content_id"],
        "metrics": record["payload"]["metrics"],
        "execution": record["execution"],
    }


@pytest.mark.parametrize(
    "options,expected",
    [
        (
            [
                "--scenario", "drive", "--settle", "6.003", "--maneuver", "0.101",
                "--plant-step", "0.0005", "--controller-period", "0.01",
                "--logging-period", "0.025", "--driveshaft-torque", "40",
                "--steering", "0.06", "--settle-braking", "0.2",
            ],
            {
                "scenario_id": "drive", "settle_s": 6.003, "maneuver_s": 0.101,
                "plant_step_s": 0.0005, "controller_period_s": 0.01,
                "logging_period_s": 0.025, "driveshaft_torque_nm": 40.0,
                "steering": 0.06, "settle_braking": 0.2,
            },
        ),
        (
            [
                "--scenario", "steer", "--settle", "1.003", "--maneuver", "0.203",
                "--plant-step", "0.001", "--controller-period", "0.007",
                "--logging-period", "0.025", "--driveshaft-torque", "73.5",
                "--steering", "-0.12", "--settle-braking", "0.35",
            ],
            {
                "scenario_id": "steer", "settle_s": 1.003, "maneuver_s": 0.203,
                "plant_step_s": 0.001, "controller_period_s": 0.007,
                "logging_period_s": 0.025, "driveshaft_torque_nm": 73.5,
                "steering": -0.12, "settle_braking": 0.35,
            },
        ),
    ],
)
def test_fresh_cli_routes_all_nine_scenario_fields_and_keeps_output_contract(
    options, expected, record, tmp_path, monkeypatch, capsys
):
    calls = []

    def run(scenario, *, cancel, progress):
        assert isinstance(scenario, study.SuspensionScenario)
        calls.append(asdict(scenario))
        assert cancel is None
        progress(0.5)
        return record

    monkeypatch.setattr(study, "run_study", run)
    destination = tmp_path / "new-study.json"
    assert study.main([*options, "--output", str(destination)]) == 0
    assert calls == [expected]
    output = capsys.readouterr()
    assert json.loads(output.out) == expected_stdout(record)
    assert "Native suspension study: 50%" in output.err
    assert json.loads(destination.read_text(encoding="utf-8")) == record


def test_fresh_cli_defaults_remain_the_existing_scenario(record, monkeypatch, capsys):
    calls = []

    def run(scenario, **kwargs):
        calls.append(asdict(scenario))
        return record

    monkeypatch.setattr(study, "run_study", run)
    assert study.main([]) == 0
    assert calls == [{
        "scenario_id": "drive", "settle_s": 6.0, "maneuver_s": 2.0,
        "plant_step_s": 0.0005, "controller_period_s": 0.01,
        "logging_period_s": 0.02, "driveshaft_torque_nm": 40.0,
        "steering": 0.06, "settle_braking": 0.2,
    }]
    assert json.loads(capsys.readouterr().out) == expected_stdout(record)


@pytest.mark.parametrize(
    "options,error_field",
    [
        (["--settle", "nan"], "settle_s"),
        (["--maneuver", "0.0995"], "maneuver_s"),
        (["--driveshaft-torque", "inf"], "driveshaft_torque_nm"),
        (["--steering", "0.251"], "steering"),
        (["--settle-braking", "1.001"], "settle_braking"),
        (["--controller-period", "0.01025"], "controller_period_s"),
        (["--logging-period", "0.02525"], "logging_period_s"),
        (["--plant-step", "nan"], "plant_step_s"),
        (
            ["--settle", "10", "--maneuver", "10", "--plant-step", "0.0001"],
            "plant-step budget",
        ),
        (
            [
                "--settle", "1.0005", "--maneuver", "0.9995",
                "--plant-step", "0.0005", "--controller-period", "0.001",
                "--logging-period", "0.001",
            ],
            "sample budget",
        ),
    ],
)
def test_fresh_cli_validates_before_any_file_or_engine_work(
    options, error_field, forbid_work, capsys
):
    assert study.main(options) == 1
    output = capsys.readouterr()
    assert error_field in output.err and "Traceback" not in output.err
    assert output.out == ""


@pytest.mark.parametrize("mode", ("--replay", "--inspect"))
@pytest.mark.parametrize(
    "run_options",
    [
        ["--scenario", "drive"],
        ["--plant-step", "0.0005"],
        ["--settle", "6"],
        ["--maneuver", "2"],
        ["--controller-period", "0.01"],
        ["--logging-period", "0.02"],
        ["--driveshaft-torque", "40"],
        ["--steering", "0.06"],
        ["--settle-braking", "0.2"],
    ],
)
def test_saved_modes_reject_explicit_fresh_options_even_when_they_equal_defaults(
    mode, run_options, forbid_work, capsys
):
    assert study.main([mode, "must-not-be-read.json", *run_options]) == 1
    assert mode in capsys.readouterr().err


def test_replay_keeps_saved_scenario_output_and_live_stop_callback(
    record, tmp_path, monkeypatch, capsys
):
    source = tmp_path / "saved.json"
    source.write_text(json.dumps(record), encoding="utf-8")
    before = source.read_bytes(), source.stat().st_mtime_ns
    destination = tmp_path / "replayed.json"
    stop = tmp_path / "STOP"
    calls = []

    def replay(saved, *, cancel):
        calls.append((saved, cancel))
        assert not cancel()
        return saved

    monkeypatch.setattr(study, "run_study", unexpected_work)
    monkeypatch.setattr(study, "replay_study", replay)
    assert study.main([
        "--replay", str(source), "--output", str(destination), "--stop-file", str(stop)
    ]) == 0
    assert calls[0][0] == record
    assert calls[0][0]["payload"]["scenario"]["settle_s"] == 1.0
    assert calls[0][0]["payload"]["scenario"]["plant_step_s"] == 0.001
    stop.touch()
    assert calls[0][1]()
    assert json.loads(destination.read_text(encoding="utf-8")) == record
    assert json.loads(capsys.readouterr().out) == expected_stdout(record)
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before


@pytest.mark.parametrize("replay_mode", (False, True))
def test_cancelled_cli_preserves_existing_destination_and_returns_130(
    replay_mode, record, tmp_path, monkeypatch, capsys
):
    source = tmp_path / "saved.json"
    source.write_text(json.dumps(record), encoding="utf-8")
    before = source.read_bytes(), source.stat().st_mtime_ns
    destination = tmp_path / "old-result.json"
    destination.write_bytes(b"keep the old completed result")
    stop = tmp_path / "STOP"
    stop.touch()

    def cancel(*args, cancel, **kwargs):
        assert cancel()
        raise study.StudyCancelled("requested stop")

    monkeypatch.setattr(study, "run_study", cancel)
    monkeypatch.setattr(study, "replay_study", cancel)
    options = ["--output", str(destination), "--stop-file", str(stop)]
    if replay_mode:
        options.extend(["--replay", str(source)])
    assert study.main(options) == 130
    assert destination.read_bytes() == b"keep the old completed result"
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before
    output = capsys.readouterr()
    assert output.out == "" and "requested stop" in output.err


@pytest.mark.parametrize("alias_kind", ("same", "hardlink"))
def test_replay_input_aliases_are_rejected_before_any_read_or_write(
    alias_kind, record, tmp_path, forbid_work, capsys
):
    source = tmp_path / "saved.json"
    source.write_text(json.dumps(record), encoding="utf-8")
    before = source.read_bytes(), source.stat().st_mtime_ns
    destination = source
    if alias_kind == "hardlink":
        destination = tmp_path / "alias.json"
        destination.hardlink_to(source)
    assert study.main(["--replay", str(source), "--output", str(destination)]) == 1
    assert "input" in capsys.readouterr().err
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before


def test_inspect_stays_passive_and_leaves_input_unchanged(
    record, tmp_path, monkeypatch, capsys
):
    source = tmp_path / "saved.json"
    source.write_text(json.dumps(record), encoding="utf-8")
    before = source.read_bytes(), source.stat().st_mtime_ns
    for name in ("run_study", "replay_study", "write_text_atomic"):
        monkeypatch.setattr(study, name, unexpected_work)
    assert study.main(["--inspect", str(source)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["saved_content_id"] == record["content_id"]
    assert output["checks"]["fresh_native_replay"] == "not run"
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before


def test_replay_and_inspect_remain_mutually_exclusive(forbid_work):
    with pytest.raises(SystemExit) as error:
        study.main(["--replay", "a.json", "--inspect", "b.json"])
    assert error.value.code == 2


def test_help_lists_every_current_scenario_setting_without_native_work(
    forbid_work, capsys
):
    with pytest.raises(SystemExit) as error:
        study.main(["--help"])
    assert error.value.code == 0
    help_text = capsys.readouterr().out
    for option in (
        "--scenario", "--plant-step", "--settle", "--maneuver",
        "--controller-period", "--logging-period", "--driveshaft-torque",
        "--steering", "--settle-braking",
    ):
        assert option in help_text
