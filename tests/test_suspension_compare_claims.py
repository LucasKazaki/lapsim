"""Fixed-label eligibility uses independently sealed analytic saved records."""

import builtins
import json
import subprocess

import pytest

from lapsim.experiments import suspension_study as study
from test_suspension_compare import canonical_world_si_claims, fixture_record
from test_suspension_compare_provenance import (
    calculation_projection,
    independent_id,
    reseal,
)


HOSTILE_CLAIM = "=SUM(1,2)\r\n\t\x00\u202e" + "untrusted-claim-" * 128
REASONS = {
    "frame": "Unsupported recorded frame for fixed world-frame plant-step quantities",
    "units": "Unsupported recorded units for fixed SI plant-step quantities",
}


def canonical_bytes(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


@pytest.fixture(autouse=True)
def passive_comparison(monkeypatch):
    """Fail observable engine, replay, process and Git boundaries for every case."""
    original_import = builtins.__import__

    def checked_import(name, *args, **kwargs):
        assert not name.startswith("pychrono") and "chrono_vehicle" not in name
        assert not name.startswith("tkinter")
        return original_import(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("Saved claim comparison launched physics, replay or a process")

    monkeypatch.setattr(builtins, "__import__", checked_import)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    for name in ("run_study", "replay_study", "_code_identity", "_source"):
        monkeypatch.setattr(study, name, forbidden)


def unsupported_pair(field, claim):
    pair = [
        canonical_world_si_claims(fixture_record()),
        canonical_world_si_claims(fixture_record(step=0.0005)),
    ]
    for record in pair:
        record["payload"][field] = claim
        reseal(record)
        study.validate_study_record(record)
    return pair


def assert_ineligible(report, pair, field, claim):
    assert report["status"] == "incompatible"
    assert report["compatibility"]["compatible_recorded_claims"] is False
    assert report["compatibility"]["reasons"] == [
        f"left: {REASONS[field]}",
        f"right: {REASONS[field]}",
    ]
    assert report["result"] is None
    # Inspections retain raw claims; only fixed, bounded reasons describe policy.
    for reason in report["compatibility"]["reasons"]:
        assert len(reason) < 128
        assert claim not in reason
        assert not any(ord(character) < 32 for character in reason)
    for role, record in zip(("left", "right"), pair, strict=True):
        inspection = report["inputs"][role]["inspection"]
        assert inspection["saved_content_id"] == record["content_id"]
        assert inspection["saved_receipt_id"] == record["receipt_id"]
        assert inspection["saved_provenance"][field] == claim
        assert inspection["checks"]["fresh_native_replay"] == "not run"
    assert report["report_id"] == independent_id(calculation_projection(report))
    assert report["receipt_id"] == independent_id(
        {key: value for key, value in report.items() if key != "receipt_id"}
    )


@pytest.mark.parametrize("route", ("records", "files", "cli"))
@pytest.mark.parametrize("field", ("frame", "units"))
@pytest.mark.parametrize(
    "claim",
    (
        pytest.param("matching unsupported claim", id="opaque"),
        pytest.param(HOSTILE_CLAIM, id="controls-long"),
    ),
)
def test_matching_unsupported_claims_have_no_fixed_label_result(
    route, field, claim, tmp_path, capsys
):
    from lapsim.experiments import suspension_compare as comparison

    pair = unsupported_pair(field, claim)
    before_memory = [canonical_bytes(record) for record in pair]
    paths = [tmp_path / "left.json", tmp_path / "right.json"]
    for path, record in zip(paths, pair, strict=True):
        path.write_bytes(canonical_bytes(record))
    before_files = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
    if route == "records":
        report = comparison.compare_study_records(*pair, kind="plant-step")
    elif route == "files":
        report = comparison.compare_study_files(*paths, kind="plant-step")
    else:
        assert comparison.main([*map(str, paths), "--kind", "plant-step"]) == 1
        captured = capsys.readouterr()
        assert captured.err == ""
        report = json.loads(captured.out)
    assert_ineligible(report, pair, field, claim)
    assert [canonical_bytes(record) for record in pair] == before_memory
    assert [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths] == before_files


@pytest.mark.parametrize("field", ("frame", "units"))
def test_ineligible_valid_finite_extremes_are_not_subtracted(field):
    from lapsim.experiments.suspension_compare import compare_study_records

    pair = unsupported_pair(field, "matching unsupported finite-extreme claim")
    for record, value in zip(pair, (1e308, -1e308), strict=True):
        final = record["payload"]["samples"][-1]
        final["velocity_mps"][0] = value
        final["position_m"][2] = value
        final["suspension_spring_length_m"] = [value] * 4
        reseal(record)
        study.validate_study_record(record)
    before = [canonical_bytes(record) for record in pair]
    # Subtraction would overflow. Valid but unsupported claims must return the
    # public null-result contract before endpoint arithmetic, without a mock.
    report = compare_study_records(*pair, kind="plant-step")
    assert_ineligible(report, pair, field, "matching unsupported finite-extreme claim")
    assert [canonical_bytes(record) for record in pair] == before


@pytest.mark.parametrize("field", ("frame", "units"))
def test_equal_opaque_logging_claims_keep_exact_raw_observation_comparison(field):
    from lapsim.experiments.suspension_compare import compare_study_records

    pair = [fixture_record(), fixture_record(logging=0.05)]
    for record in pair:
        record["payload"][field] = HOSTILE_CLAIM
        reseal(record)
        study.validate_study_record(record)
    before = [canonical_bytes(record) for record in pair]
    a, b = (
        {sample["time_s"]: sample for sample in record["payload"]["samples"]}
        for record in pair
    )
    shared = sorted(a.keys() & b.keys())
    left_only, right_only = sorted(a.keys() - b.keys()), sorted(b.keys() - a.keys())
    assert all(canonical_bytes(a[t]) == canonical_bytes(b[t]) for t in shared)
    report = compare_study_records(*pair, kind="logging-period")
    result = report["result"]
    assert report["status"] == "compared"
    assert result["shared"] == {"count": 12, "times_s": shared, "truncated": False}
    assert result["left_unmatched"] == {
        "count": 44, "times_s": left_only, "truncated": False
    }
    assert result["right_unmatched"] == {
        "count": 11, "times_s": right_only, "truncated": False
    }
    assert 0.02 in left_only
    assert result["all_shared_observations_equal"] is True
    assert result["different_shared_observations"] == 0
    assert "quantities" not in result and "criterion" not in result
    for role in ("left", "right"):
        clocks = report["inputs"][role]["initial_observation_clocks"]
        assert clocks["tire_force_source_time_s"] is None
        assert clocks["applied_tire_force_source_time_s"] is None
        assert clocks["applied_tire_force_geometry_time_s"] == 0.0
    assert [canonical_bytes(record) for record in pair] == before


def test_canonical_analytic_endpoints_keep_literal_signed_wheel_deltas():
    from lapsim.experiments.suspension_compare import compare_study_records

    pair = [
        canonical_world_si_claims(fixture_record()),
        canonical_world_si_claims(fixture_record(step=0.0005)),
    ]
    # These explicit binary-exact analytic values are not a physical fixture.
    for record, velocity, height, springs in (
        (pair[0], 0.25, 2.0, [0.5, 0.625, 0.75, 0.875]),
        (pair[1], 0.125, 2.25, [0.625, 0.5, 1.0, 0.375]),
    ):
        sample = record["payload"]["samples"][-1]
        sample["velocity_mps"][0] = velocity
        sample["position_m"][2] = height
        sample["suspension_spring_length_m"] = springs
        reseal(record)
        study.validate_study_record(record)
    before = [canonical_bytes(record) for record in pair]
    report = compare_study_records(*pair, kind="plant-step")
    result = report["result"]
    assert report["status"] == "compared"
    assert result["quantities"]["world_x_velocity_mps"]["right_minus_left"] == -0.125
    assert result["quantities"]["chassis_com_height_m"]["right_minus_left"] == 0.25
    assert [
        (item["wheel"], item["right_minus_left"])
        for item in result["quantities"]["spring_lengths_m"]
    ] == [("FL", 0.125), ("FR", -0.125), ("RL", 0.25), ("RR", -0.5)]
    for role, record in zip(("left", "right"), pair, strict=True):
        final = record["payload"]["samples"][-1]
        context = result["final_observation_context"][role]
        assert context["clocks"] == {
            key: final[key]
            for key in (
                "time_s", "tire_force_source_time_s", "tire_kinematics_source_time_s",
                "applied_tire_force_source_time_s", "applied_tire_force_geometry_time_s",
            )
        }
        assert context["completed_interval_command"] == final["command"]
        assert context["computed_world_fz_n"] == [11.1, 12.1, 13.1, 14.1]
        assert context["applied_world_fz_n"] == [21.1, 22.1, 23.1, 24.1]
    assert result["criterion"]["status"] == "not applied"
    assert report["report_id"] == independent_id(calculation_projection(report))
    assert report["receipt_id"] == independent_id(
        {key: value for key, value in report.items() if key != "receipt_id"}
    )
    assert [canonical_bytes(record) for record in pair] == before
