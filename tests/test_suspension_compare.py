"""Saved-pair contracts use serialized analytic fixtures, never native physics."""

import builtins
from dataclasses import asdict
from hashlib import sha256
import json
import subprocess

import pytest

from lapsim.experiments import suspension_study as study
from test_suspension_study import ClockPlant


def seal(record):
    record["content_id"] = study._content_id(record["payload"])
    record["receipt_id"] = study._content_id(
        {key: value for key, value in record.items() if key != "receipt_id"}
    )
    return record


def fingerprint(record):
    return sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()


def fixture_record(*, step=0.001, logging=0.02, stock=False):
    """Hand-author valid saved shapes and clocks; no run_study/advance calls."""
    scenario = study.SuspensionScenario(
        plant_step_s=step,
        logging_period_s=logging,
        **({} if stock else {"settle_s": 1.0, "maneuver_s": 0.1}),
    )
    ticks = round((scenario.settle_s + scenario.maneuver_s) / step)
    controller_ticks = round(scenario.controller_period_s / step)
    logging_ticks = round(logging / step)
    zero = {"driveshaft_torque_nm": 0.0, "steering": 0.0, "braking": 0.0}
    commands = [
        {"time_s": index * controller_ticks * step, "request": zero.copy()}
        for index in range((ticks - 1) // controller_ticks + 1)
    ]
    template = json.loads(json.dumps(asdict(ClockPlant().observe())))
    samples = []
    for tick in sorted(
        {*range(0, ticks + 1, logging_ticks), round(scenario.settle_s / step), ticks}
    ):
        t = tick * step
        sample = json.loads(json.dumps(template))
        sample.update(
            time_s=t,
            position_m=[t, 2 * t, 1 + t],
            velocity_mps=[t / 10, 0.0, 0.0],
            tire_force_source_time_s=t - step if tick else None,
            tire_kinematics_source_time_s=t - step if tick else None,
            applied_tire_force_source_time_s=t - 2 * step if tick else None,
            applied_tire_force_geometry_time_s=t - step if tick else 0.0,
            suspension_spring_length_m=[
                0.5 + wheel / 10 + t / 100 for wheel in range(4)
            ],
            wheel_force_world_n=[[0.0, 0.0, 10 + wheel + t] for wheel in range(4)],
            applied_wheel_force_world_n=[
                [0.0, 0.0, 20 + wheel + t] for wheel in range(4)
            ],
            command=zero.copy(),
        )
        samples.append(sample)
    record = {
        "schema": study.SCHEMA,
        "payload": {
            "scenario": asdict(scenario),
            "capabilities": asdict(ClockPlant.capabilities),
            "model": {
                "profile_id": "serialized_analytic_fixture",
                "engine": {"name": "unit fixture"},
                "assets_sha256": {"fixture": "0" * 64},
            },
            "source": {
                "code_commit": None,
                "dirty_worktree": None,
                **study._implementation_source(),
            },
            "wheel_order": ["FL", "FR", "RL", "RR"],
            "frame": "right-handed world; analytic fixture",
            "units": "SI",
            "controller": "explicit zero command fixture; no physics",
            "commands": commands,
            "samples": samples,
            "metrics": {
                "settle_window_s": [scenario.settle_s - 0.5, scenario.settle_s],
                "settle_samples": round(0.5 / step) + 1,
                "settle_max_vertical_force_relative_error": 0.0,
                "settle_max_left_right_load_relative_difference": 0.0,
                "settle_max_vertical_speed_mps": 0.0,
                "settle_acceptance": {
                    "passed": True,
                    "force_relative_limit": 0.01,
                    "left_right_relative_limit": 0.01,
                    "vertical_speed_limit_mps": 0.01,
                },
                "final_speed_mps": samples[-1]["velocity_mps"][0],
                "final_heading_rad": samples[-1]["heading_rad"],
                "final_chassis_com_height_m": samples[-1]["position_m"][2],
            },
        },
        "execution": {
            "python": "fixture",
            "platform": "fixture",
            "initialization_wall_s": 0.01,
            "stepping_and_record_wall_s": 0.02,
            "total_wall_s": 0.03,
            "process_cpu_s": 0.01,
            "process_lifetime_peak_working_set_bytes": None,
            "plant_steps": ticks,
            "simulated_time_s": scenario.settle_s + scenario.maneuver_s,
            "controller_calls": len(commands),
            "logging_samples": len(samples),
            "device": "CPU",
            "gpu_physics": False,
            "timing_scope": study.TIMING_SCOPE,
        },
    }
    seal(record)
    study.validate_study_record(record)
    return record


@pytest.fixture
def records():
    return fixture_record(), fixture_record(logging=0.05)


def test_public_saved_pair_cli_contract_is_passive(
    records, tmp_path, capsys, monkeypatch
):
    from lapsim.experiments.suspension_compare import main

    paths = [tmp_path / name for name in ("left.json", "right.json")]
    for path, record in zip(paths, records, strict=True):
        path.write_text(json.dumps(record))
    before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
    original_import = builtins.__import__

    def checked_import(name, *args, **kwargs):
        assert not name.startswith("pychrono") and "chrono_vehicle" not in name
        return original_import(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("Saved comparison launched physics, replay, or a process")

    monkeypatch.setattr(builtins, "__import__", checked_import)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(study, "run_study", forbidden)
    monkeypatch.setattr(study, "replay_study", forbidden)
    assert main([str(paths[0]), str(paths[1]), "--kind", "logging-period"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "compared"
    assert (
        report["inputs"]["left"]["inspection"]["saved_content_id"]
        == records[0]["content_id"]
    )
    assert (
        report["inputs"]["right"]["initial_observation_clocks"][
            "tire_force_source_time_s"
        ]
        is None
    )
    assert (
        report["inputs"]["left"]["inspection"]["checks"]["fresh_native_replay"]
        == "not run"
    )
    assert [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths] == before


def test_logging_matches_actual_time_intersection_and_reports_missing_samples(records):
    from lapsim.experiments.suspension_compare import compare_study_records

    left, right = records
    before = [fingerprint(record) for record in records]
    result = compare_study_records(left, right, kind="logging-period")["result"]
    expected_times = sorted(
        {item["time_s"] for item in left["payload"]["samples"]}
        & {item["time_s"] for item in right["payload"]["samples"]}
    )
    assert result["shared"]["times_s"] == expected_times
    assert result["shared"]["count"] == 12
    assert result["left_unmatched"]["count"] == 44
    assert result["right_unmatched"]["count"] == 11
    assert 0.02 in result["left_unmatched"]["times_s"]
    assert result["all_shared_observations_equal"] is True
    assert result["different_shared_observations"] == 0
    assert not result["shared"]["truncated"]
    assert [fingerprint(record) for record in records] == before


def test_logging_detects_shared_observable_difference_without_index_alignment(records):
    from lapsim.experiments.suspension_compare import compare_study_records

    left, right = records
    sample = next(item for item in right["payload"]["samples"] if item["time_s"] == 0.1)
    sample["velocity_mps"][0] = 7.0
    seal(right)
    result = compare_study_records(left, right, kind="logging-period")["result"]
    assert result["different_shared_observations"] == 1
    assert result["different_field_counts"] == {"velocity_mps": 1}
    assert result["first_five_mismatch_examples"][0]["left_clocks"]["time_s"] == 0.1


def test_logging_does_not_snap_nearby_valid_timestamps(records):
    from lapsim.experiments.suspension_compare import compare_study_records

    left, right = records
    sample = next(item for item in right["payload"]["samples"] if item["time_s"] == 0.1)
    sample["time_s"] += 1e-10
    changed_time = sample["time_s"]
    seal(right)
    study.validate_study_record(right)
    result = compare_study_records(left, right, kind="logging-period")["result"]
    assert result["shared"]["count"] == 11
    assert 0.1 in result["left_unmatched"]["times_s"]
    assert changed_time in result["right_unmatched"]["times_s"]


def test_null_force_clock_stays_unknown_and_counts_as_shared_difference(records):
    from lapsim.experiments.suspension_compare import compare_study_records

    left, right = records
    sample = next(item for item in right["payload"]["samples"] if item["time_s"] == 0.1)
    sample["applied_tire_force_source_time_s"] = None
    seal(right)
    result = compare_study_records(left, right, kind="logging-period")["result"]
    assert result["different_field_counts"] == {"applied_tire_force_source_time_s": 1}
    example = result["first_five_mismatch_examples"][0]
    assert example["left_clocks"]["applied_tire_force_source_time_s"] is not None
    assert example["right_clocks"]["applied_tire_force_source_time_s"] is None


def test_plant_step_reports_signed_deltas_and_distinct_cached_origins():
    from lapsim.experiments.suspension_compare import compare_study_records

    left, right = fixture_record(), fixture_record(step=0.0005)
    final = right["payload"]["samples"][-1]
    final["velocity_mps"][0] += 0.02
    final["position_m"][2] -= 0.003
    final["suspension_spring_length_m"][2] += 0.0007
    seal(right)
    report = compare_study_records(left, right, kind="plant-step")
    result = report["result"]
    assert report["status"] == "compared"
    assert result["quantities"]["world_x_velocity_mps"][
        "right_minus_left"
    ] == pytest.approx(0.02)
    assert result["quantities"]["chassis_com_height_m"][
        "right_minus_left"
    ] == pytest.approx(-0.003)
    assert result["quantities"]["spring_lengths_m"][2][
        "right_minus_left"
    ] == pytest.approx(0.0007)
    a, b = (result["final_observation_context"][name] for name in ("left", "right"))
    assert a["clocks"]["tire_force_source_time_s"] == pytest.approx(1.099)
    assert a["clocks"]["applied_tire_force_source_time_s"] == pytest.approx(1.098)
    assert b["clocks"]["applied_tire_force_source_time_s"] == pytest.approx(1.099)
    assert a["computed_world_fz_n"] == [11.1, 12.1, 13.1, 14.1]
    assert a["applied_world_fz_n"] == [21.1, 22.1, 23.1, 24.1]
    assert result["criterion"]["status"] == "not applied"


def claimed_stock_record(step):
    """Claim metadata for testing criterion arithmetic; not native evidence."""
    record = fixture_record(step=step, stock=True)
    record["payload"]["model"]["profile_id"] = (
        "chrono10_synthetic_sedan_shafts_brakes_v1"
    )
    record["payload"]["capabilities"]["backend_id"] = "chrono_vehicle_10_cpu_v1"
    record["payload"]["capabilities"]["topology_id"] = (
        "synthetic_rear_driveshaft_open_differential"
    )
    return seal(record)


@pytest.mark.parametrize(
    "fine,coarse,expected",
    ((0.0, 5e-13, True), (0.0, 2e-12, False), (0.001, 0.00101005, False)),
)
def test_named_criterion_uses_fine_reference_and_nearzero_absolute_floor(
    fine, coarse, expected
):
    from lapsim.experiments.suspension_compare import _criterion_checks

    quantities = {
        "world_x_velocity_mps": {
            "left": fine,
            "right": coarse,
            "absolute_difference": abs(coarse - fine),
        },
        "chassis_com_height_m": {"absolute_difference": 0.0},
        "spring_lengths_m": [
            {"wheel": wheel, "absolute_difference": 0.0}
            for wheel in ("FL", "FR", "RL", "RR")
        ],
    }
    checks = _criterion_checks(quantities, "left")
    assert checks[0]["passed"] is expected
    assert checks[0]["limit"] == max(1e-12, 0.01 * abs(fine))


def test_height_criterion_is_absolute_only_even_at_large_saved_height():
    from lapsim.experiments.suspension_compare import _criterion_checks

    quantities = {
        "world_x_velocity_mps": {"left": 0.0, "right": 0.0, "absolute_difference": 0.0},
        "chassis_com_height_m": {
            "absolute_difference": abs(1_000_000.002 - 1_000_000.0)
        },
        "spring_lengths_m": [],
    }
    checks = _criterion_checks(quantities, "right")
    assert checks[1]["limit"] == 0.001
    assert checks[1]["passed"] is False


@pytest.mark.parametrize(
    "field",
    (
        "model",
        "capabilities",
        "frame",
        "units",
        "controller",
        "commands",
        "source",
        "initial",
        "scenario",
    ),
)
def test_undeclared_physical_or_implementation_change_blocks_numerical_result(
    records, field
):
    from lapsim.experiments.suspension_compare import compare_study_records

    left, right = records
    payload = right["payload"]
    if field == "model":
        payload["model"]["assets_sha256"]["fixture"] = "1" * 64
    elif field == "capabilities":
        payload["capabilities"]["topology_id"] = "different"
    elif field in {"frame", "units", "controller"}:
        payload[field] = "different"
    elif field == "commands":
        payload["commands"][0]["request"]["steering"] = 0.01
    elif field == "source":
        payload["source"]["files_sha256"]["native_plant.py"] = "0" * 64
    elif field == "initial":
        payload["samples"][0]["position_m"][0] += 1
    else:
        payload["scenario"]["driveshaft_torque_nm"] += 1
    seal(right)
    report = compare_study_records(left, right, kind="logging-period")
    assert report["status"] == "incompatible"
    assert report["compatibility"]["reasons"]
    assert report["result"] is None


def test_git_claims_do_not_replace_implementation_compatibility(records):
    from lapsim.experiments.suspension_compare import compare_study_records

    left, right = records
    right["payload"]["source"].update(code_commit="1" * 40, dirty_worktree=True)
    right["execution"].update(
        initialization_wall_s=1.0, stepping_and_record_wall_s=2.0, total_wall_s=3.0
    )
    seal(right)
    report = compare_study_records(left, right, kind="logging-period")
    assert report["status"] == "compared"
    assert report["compatibility"]["git_identity_claims"]["equal"] is False
    assert (
        report["inputs"]["right"]["inspection"]["historical_execution_claims"][
            "total_wall_s"
        ]
        == 3.0
    )
    assert "performance winner" in report["scope"]
    assert (
        report["inputs"]["right"]["inspection"]["checks"]["historical_timing"]
        == "recorded claims; not validated"
    )


def test_missing_current_source_keeps_recorded_pair_comparable_but_no_criterion(
    monkeypatch,
):
    from lapsim.experiments.suspension_compare import compare_study_records

    left, right = claimed_stock_record(0.0005), claimed_stock_record(0.00025)

    def unavailable():
        raise OSError("source is unavailable in this runtime")

    monkeypatch.setattr(study, "_implementation_source", unavailable)
    report = compare_study_records(left, right, kind="plant-step")
    assert report["status"] == "compared"
    assert (
        "unavailable"
        in report["inputs"]["left"]["inspection"]["checks"][
            "current_implementation_files"
        ]
    )
    assert report["result"]["criterion"]["status"] == "not applied"


@pytest.mark.parametrize(
    "missing", ("profile_id", "engine", "assets_sha256", "hash_scope")
)
def test_missing_identity_or_unknown_scope_blocks_comparison(records, missing):
    from lapsim.experiments.suspension_compare import compare_study_records

    left, right = records
    for record in records:
        if missing == "hash_scope":
            record["payload"]["source"]["hash_scope"] = "unsupported recorded scope"
        else:
            del record["payload"]["model"][missing]
        seal(record)
    report = compare_study_records(left, right, kind="logging-period")
    assert report["status"] == "incompatible"
    assert report["result"] is None


def test_profile_name_alone_does_not_apply_reference_fixture_criterion():
    from lapsim.experiments.suspension_compare import compare_study_records

    left, right = claimed_stock_record(0.0005), claimed_stock_record(0.00025)
    report = compare_study_records(left, right, kind="plant-step")
    criterion = report["result"]["criterion"]
    assert report["status"] == "compared"
    assert criterion["status"] == "not applied"
    assert any("physical inputs" in reason for reason in criterion["reasons"])


@pytest.mark.parametrize("number", (1e308, 10**308))
def test_finite_subtraction_overflow_is_explicit(number):
    from lapsim.experiments.suspension_compare import compare_study_records

    left, right = fixture_record(), fixture_record(step=0.0005)
    left["payload"]["samples"][-1]["position_m"][2] = number
    right["payload"]["samples"][-1]["position_m"][2] = -number
    seal(left)
    seal(right)
    with pytest.raises(ValueError, match=r"overflow.*COM height"):
        compare_study_records(left, right, kind="plant-step")


def test_corrupt_oversized_and_invalid_order_inputs_publish_no_result(
    records, tmp_path, capsys
):
    from lapsim.experiments.suspension_compare import compare_study_files, main

    good = tmp_path / "good.json"
    bad = tmp_path / "bad.json"
    good.write_text(json.dumps(records[0]))
    bad.write_text("{bad")
    assert main([str(good), str(bad), "--kind", "logging-period"]) == 1
    assert not capsys.readouterr().out
    bad.write_bytes(b" " * (study.MAX_BYTES + 1))
    with pytest.raises(ValueError, match="exceeds"):
        compare_study_files(good, bad, kind="logging-period")
    records[1]["payload"]["wheel_order"] = ["FR", "FL", "RL", "RR"]
    seal(records[1])
    bad.write_text(json.dumps(records[1]))
    with pytest.raises(ValueError, match="wheel order"):
        compare_study_files(good, bad, kind="logging-period")


def test_only_two_declared_kinds_are_accepted_before_file_reads(capsys):
    from lapsim.experiments.suspension_compare import compare_study_files, main

    with pytest.raises(ValueError, match="plant-step or logging-period"):
        compare_study_files("missing", "missing", kind="arbitrary")
    with pytest.raises(SystemExit) as error:
        main(["missing", "missing", "--kind", "arbitrary"])
    assert error.value.code == 2
    assert not capsys.readouterr().out
