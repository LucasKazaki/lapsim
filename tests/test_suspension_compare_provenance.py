"""Comparison identity oracles use stdlib JSON and hashes, without physics."""

import builtins
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess

import pytest

from test_suspension_compare import fixture_record


SCHEMA = "lapsim.native-suspension-comparison.v1"
RECIPE_SCHEMA = "lapsim.native-suspension-comparison-recipe.v1"
FILES = (
    "experiments/suspension_compare.py",
    "experiments/suspension_study.py",
    "dynamics/native_plant.py",
    "dynamics/chrono_vehicle.py",
    "experiments/dynamics_record.py",
    "experiments/record_io.py",
    "experiments/basic_dynamics.py",
)


def independent_id(value):
    return sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def calculation_projection(report):
    return {
        "schema": report["schema"],
        "comparison_kind": report["comparison_kind"],
        "scope": report["scope"],
        "input_content_ids": {
            role: report["inputs"][role]["inspection"]["saved_content_id"]
            for role in ("left", "right")
        },
        "comparison_recipe": report["comparison_recipe"],
        "status": report["status"],
        "compatibility": {
            key: (
                sorted(report["compatibility"][key])
                if key == "reasons"
                else report["compatibility"][key]
            )
            for key in (
                "compatible_recorded_claims",
                "reasons",
                "allowed_scenario_field",
                "selected_field",
            )
        },
        "result": report["result"],
    }


def test_report_provenance_matches_independent_canonical_oracle():
    from lapsim.experiments.suspension_compare import compare_study_records

    left, right = fixture_record(), fixture_record(logging=0.05)
    report = compare_study_records(left, right, kind="logging-period")
    assert report["schema"] == SCHEMA
    recipe = report["comparison_recipe"]
    assert recipe["schema"] == RECIPE_SCHEMA
    assert recipe["status"] == "complete"
    package = Path(__file__).resolve().parents[1] / "src" / "lapsim"
    expected = {
        name: sha256((package / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for name in FILES
    }
    assert recipe["files_sha256"] == expected
    assert recipe["file_status"] == {name: "readable" for name in FILES}
    assert recipe["recipe_id"] == independent_id(
        {key: value for key, value in recipe.items() if key != "recipe_id"}
    )
    assert report["report_id"] == independent_id(calculation_projection(report))
    assert report["receipt_id"] == independent_id(
        {key: value for key, value in report.items() if key != "receipt_id"}
    )


def reseal(record):
    record["content_id"] = independent_id(record["payload"])
    record["receipt_id"] = independent_id(
        {key: value for key, value in record.items() if key != "receipt_id"}
    )


def copy_recipe_sources(destination, *, crlf=False):
    package = Path(__file__).resolve().parents[1] / "src" / "lapsim"
    for name in FILES:
        raw = (package / name).read_bytes().replace(b"\r\n", b"\n")
        if crlf:
            raw = raw.replace(b"\n", b"\r\n")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return destination / "experiments" / "suspension_compare.py"


def test_historical_timing_changes_only_the_complete_receipt():
    from lapsim.experiments.suspension_compare import compare_study_records

    left, right = fixture_record(), fixture_record(logging=0.05)
    before = compare_study_records(left, right, kind="logging-period")
    previous_content = right["content_id"]
    right["execution"].update(
        initialization_wall_s=1.0,
        stepping_and_record_wall_s=2.0,
        total_wall_s=3.0,
        process_cpu_s=1.5,
        process_lifetime_peak_working_set_bytes=32_000_000,
    )
    reseal(right)
    after = compare_study_records(left, right, kind="logging-period")
    assert right["content_id"] == previous_content
    assert after["report_id"] == before["report_id"]
    assert after["receipt_id"] != before["receipt_id"]
    assert (
        after["inputs"]["right"]["inspection"]["historical_execution_claims"]
        == right["execution"]
    )


def test_key_order_does_not_change_calculation_identity_for_incompatible_inputs():
    from lapsim.experiments.suspension_compare import compare_study_records

    left, right = fixture_record(), fixture_record(logging=0.05)
    right["payload"]["scenario"].update(driveshaft_torque_nm=41.0, steering=0.07)
    reseal(right)
    before = compare_study_records(left, right, kind="logging-period")
    reordered_left = json.loads(json.dumps(left, sort_keys=True))
    after = compare_study_records(reordered_left, right, kind="logging-period")
    assert before["status"] == after["status"] == "incompatible"
    assert before["result"] is after["result"] is None
    assert sorted(before["compatibility"]["reasons"]) == sorted(
        after["compatibility"]["reasons"]
    )
    assert before["report_id"] == after["report_id"]
    assert after["report_id"] == independent_id(calculation_projection(after))


def test_valid_object_key_order_does_not_change_any_identity():
    from lapsim.experiments.suspension_compare import compare_study_records

    left, right = fixture_record(), fixture_record(logging=0.05)
    before = compare_study_records(left, right, kind="logging-period")
    after = compare_study_records(
        json.loads(json.dumps(left, sort_keys=True)),
        json.loads(json.dumps(right, sort_keys=True)),
        kind="logging-period",
    )
    assert (after["report_id"], after["receipt_id"]) == (
        before["report_id"],
        before["receipt_id"],
    )


def test_relocated_lf_and_crlf_source_trees_have_the_same_recipe(tmp_path, monkeypatch):
    from lapsim.experiments import suspension_compare as comparison

    left, right = fixture_record(), fixture_record(logging=0.05)
    lf = copy_recipe_sources(tmp_path / "first-package")
    crlf = copy_recipe_sources(tmp_path / "relocated-package", crlf=True)
    monkeypatch.setattr(comparison, "__file__", str(lf))
    before = comparison.compare_study_records(left, right, kind="logging-period")
    monkeypatch.setattr(comparison, "__file__", str(crlf))
    after = comparison.compare_study_records(left, right, kind="logging-period")
    assert before["comparison_recipe"] == after["comparison_recipe"]
    assert before["report_id"] == after["report_id"]
    assert before["receipt_id"] == after["receipt_id"]
    assert str(tmp_path) not in json.dumps(after)


@pytest.mark.parametrize("name", FILES)
def test_every_explicit_source_file_changes_the_observed_recipe(
    name, tmp_path, monkeypatch
):
    from lapsim.experiments import suspension_compare as comparison

    left, right = fixture_record(), fixture_record(logging=0.05)
    entry = copy_recipe_sources(tmp_path / "package")
    monkeypatch.setattr(comparison, "__file__", str(entry))
    before = comparison.compare_study_records(left, right, kind="logging-period")
    changed = tmp_path / "package" / name
    changed.write_bytes(
        changed.read_bytes() + b"\n# independent source counterexample\n"
    )
    after = comparison.compare_study_records(left, right, kind="logging-period")
    assert (
        after["comparison_recipe"]["files_sha256"][name]
        == sha256(changed.read_bytes()).hexdigest()
    )
    assert (
        after["comparison_recipe"]["recipe_id"]
        != before["comparison_recipe"]["recipe_id"]
    )
    assert after["report_id"] != before["report_id"]
    assert after["result"] == before["result"]


def test_unlisted_document_is_outside_the_declared_recipe_scope(tmp_path, monkeypatch):
    from lapsim.experiments import suspension_compare as comparison

    left, right = fixture_record(), fixture_record(logging=0.05)
    entry = copy_recipe_sources(tmp_path / "package")
    monkeypatch.setattr(comparison, "__file__", str(entry))
    before = comparison.compare_study_records(left, right, kind="logging-period")
    entry.with_name("README.md").write_text(
        "Unlisted documentation changed.", encoding="utf-8"
    )
    after = comparison.compare_study_records(left, right, kind="logging-period")
    assert before["comparison_recipe"] == after["comparison_recipe"]
    assert before["report_id"] == after["report_id"]


@pytest.mark.parametrize("status", ("missing", "unreadable"))
def test_incomplete_source_is_explicit_and_does_not_block_comparison(
    status, tmp_path, monkeypatch
):
    from lapsim.experiments import suspension_compare as comparison

    left, right = fixture_record(), fixture_record(logging=0.05)
    entry = copy_recipe_sources(tmp_path / "package")
    monkeypatch.setattr(comparison, "__file__", str(entry))
    target = tmp_path / "package" / "dynamics" / "chrono_vehicle.py"
    if status == "missing":
        target.unlink()
    else:
        read_bytes = Path.read_bytes

        def denied(path):
            if path == target:
                raise PermissionError("C:/private/location must not leak")
            return read_bytes(path)

        monkeypatch.setattr(Path, "read_bytes", denied)
    report = comparison.compare_study_records(left, right, kind="logging-period")
    recipe = report["comparison_recipe"]
    assert report["status"] == "compared"
    assert recipe["status"] == "incomplete"
    assert recipe["recipe_id"] is None
    assert recipe["files_sha256"]["dynamics/chrono_vehicle.py"] is None
    assert recipe["file_status"]["dynamics/chrono_vehicle.py"] == status
    assert sum(value is not None for value in recipe["files_sha256"].values()) == 6
    assert "private/location" not in json.dumps(report)
    assert report["report_id"] == independent_id(calculation_projection(report))
    assert report["receipt_id"] == independent_id(
        {key: value for key, value in report.items() if key != "receipt_id"}
    )


def test_frozen_like_absent_sources_do_not_borrow_recorded_hashes(
    tmp_path, monkeypatch
):
    from lapsim.experiments import suspension_compare as comparison
    from lapsim.experiments import suspension_study as study

    left, right = fixture_record(), fixture_record(step=0.0005)

    def unavailable():
        raise OSError("source not present")

    monkeypatch.setattr(study, "_implementation_source", unavailable)
    monkeypatch.setattr(
        comparison,
        "__file__",
        str(tmp_path / "absent" / "experiments" / "suspension_compare.py"),
    )
    report = comparison.compare_study_records(left, right, kind="plant-step")
    assert report["status"] == "compared"
    assert report["comparison_recipe"]["files_sha256"] == dict.fromkeys(FILES)
    assert report["comparison_recipe"]["file_status"] == dict.fromkeys(FILES, "missing")
    assert report["comparison_recipe"]["recipe_id"] is None
    assert report["result"]["criterion"]["status"] == "not applied"


def test_role_order_result_and_comparison_kind_are_bound():
    from lapsim.experiments.suspension_compare import compare_study_records

    left, right = fixture_record(), fixture_record(step=0.0005)
    right["payload"]["samples"][-1]["velocity_mps"][0] += 0.02
    reseal(right)
    before = compare_study_records(left, right, kind="plant-step")
    reverse = compare_study_records(right, left, kind="plant-step")
    other_kind = compare_study_records(left, right, kind="logging-period")
    assert (
        len({before["report_id"], reverse["report_id"], other_kind["report_id"]}) == 3
    )
    assert before["result"]["quantities"]["world_x_velocity_mps"][
        "right_minus_left"
    ] == pytest.approx(
        -reverse["result"]["quantities"]["world_x_velocity_mps"]["right_minus_left"]
    )
    right["payload"]["samples"][-1]["velocity_mps"][0] += 0.01
    reseal(right)
    after = compare_study_records(left, right, kind="plant-step")
    assert after["report_id"] != before["report_id"]
    tampered = deepcopy(before)
    tampered["result"]["quantities"]["world_x_velocity_mps"]["right_minus_left"] += 1
    assert independent_id(calculation_projection(tampered)) != before["report_id"]
    assert (
        independent_id(
            {key: value for key, value in tampered.items() if key != "receipt_id"}
        )
        != before["receipt_id"]
    )


def test_receipt_binds_displayed_claims_excluded_from_calculation():
    from lapsim.experiments.suspension_compare import compare_study_records

    report = compare_study_records(
        fixture_record(), fixture_record(logging=0.05), kind="logging-period"
    )
    report["inputs"]["left"]["inspection"]["historical_execution_claims"][
        "process_cpu_s"
    ] += 1
    assert independent_id(calculation_projection(report)) == report["report_id"]
    assert (
        independent_id(
            {key: value for key, value in report.items() if key != "receipt_id"}
        )
        != report["receipt_id"]
    )


def test_additive_fields_preserve_passivity_and_legacy_report_contents(monkeypatch):
    from lapsim.experiments import suspension_compare as comparison
    from lapsim.experiments import suspension_study as study

    left, right = fixture_record(), fixture_record(logging=0.05)
    before = independent_id([left, right])
    original_import = builtins.__import__

    def checked_import(name, *args, **kwargs):
        assert not name.startswith("pychrono") and "chrono_vehicle" not in name
        return original_import(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail(
            "Provenance collected Git/environment, ran physics, or launched a process"
        )

    monkeypatch.setattr(builtins, "__import__", checked_import)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    for name in ("run_study", "replay_study", "_code_identity", "_source"):
        monkeypatch.setattr(study, name, forbidden)
    report = comparison.compare_study_records(left, right, kind="logging-period")
    assert set(report) == {
        "kind",
        "comparison_kind",
        "scope",
        "status",
        "inputs",
        "compatibility",
        "result",
        "schema",
        "comparison_recipe",
        "report_id",
        "receipt_id",
    }
    assert report["status"] == "compared"
    assert report["result"]["all_shared_observations_equal"]
    assert independent_id([left, right]) == before
    assert set(study._implementation_source()["files_sha256"]) == {
        "native_plant.py",
        "chrono_vehicle.py",
        "suspension_study.py",
    }
