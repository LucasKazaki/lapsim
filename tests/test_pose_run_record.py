"""Portable, versioned evidence for the bounded synthetic pose experiment."""

from dataclasses import replace
import json

import pytest

from lapsim.dynamics.conditions import (
    PlanarEnvironment, PlanarRoad, RectangularGripPatch, RoadDomain,
)
from lapsim.experiments import pose_run_record
from lapsim.experiments.pose_run_record import (
    POSE_CONTROLLER_ALGORITHM_ID,
    POSE_CONTROLLER_ALGORITHM_VERSION,
    POSE_RUN_RECORD_SCHEMA_VERSION,
    PoseRunRecord,
)
from lapsim.optimization.pose_driver import PoseDriverSettings, run_pose_driver
from lapsim.ui.pose_driver_playback import PoseDriverPlayback


@pytest.fixture(scope="module")
def short_run():
    return run_pose_driver(settings=replace(
        PoseDriverSettings(), maximum_control_steps=5,
    ))


def _write_changed_record(path, record, change):
    payload = record.to_dict()
    payload.pop("content_id")
    change(payload)
    payload["content_id"] = pose_run_record._content_id(payload)
    path.write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")


def test_uniform_record_round_trip_preserves_exact_inputs_and_replay(
    short_run, tmp_path,
):
    record = PoseRunRecord.capture(short_run)
    path = record.save(tmp_path / "uniform.json")
    loaded = PoseRunRecord.load(path)

    assert loaded.content_id == record.content_id
    assert loaded.to_dict() == record.to_dict()
    assert loaded.run == short_run
    assert loaded.replay_report.passed
    assert loaded.replay().passed
    assert loaded.run.track is not short_run.track
    assert len(loaded.run.evaluations) == len(loaded.run.controls)
    assert (
        PoseDriverPlayback(loaded.run).frame_at(loaded.run.times_s[1]).x_m
        == pytest.approx(short_run.states[1].x_m)
    )
    assert (
        loaded.run.evaluations[0].cg_lateral_acceleration_mps2
        == short_run.evaluations[0].cg_lateral_acceleration_mps2
    )
    payload = loaded.to_dict()
    assert payload["schema_version"] == POSE_RUN_RECORD_SCHEMA_VERSION
    assert payload["controller"] == {
        "algorithm_id": POSE_CONTROLLER_ALGORITHM_ID,
        "algorithm_version": POSE_CONTROLLER_ALGORITHM_VERSION,
    }
    assert payload["runtime"]["source"].keys() == {
        "code_commit", "dirty_worktree", "source_files_sha256",
    }
    assert payload["runtime"]["source"]["source_files_sha256"][
        "optimization/pose_driver.py"
    ]
    assert payload["inputs"]["track"]["x_m"] == list(short_run.track.x_m)
    assert payload["inputs"]["settings"]["maximum_control_steps"] == 5


def test_assumed_grip_patch_and_interrupted_road_are_replayable(tmp_path):
    patch = RectangularGripPatch(-5.0, 5.0, -5.0, 5.0, 0.3)
    environment = PlanarEnvironment(road=PlanarRoad(patches=(patch,)))
    run = run_pose_driver(
        environment=environment,
        settings=replace(PoseDriverSettings(), maximum_control_steps=3),
    )
    assert min(sample.local_grip_multiplier for sample in run.samples) == 0.3
    loaded = PoseRunRecord.load(
        PoseRunRecord.capture(run).save(tmp_path / "patch.json")
    )
    assert loaded.run.environment == environment
    assert loaded.run.controls == run.controls
    assert loaded.run.evaluations == run.evaluations
    assert loaded.replay_report.passed

    limited = PlanarEnvironment(road=PlanarRoad(
        valid_domain=RoadDomain(-1.0, 1.0, -0.5, 0.5),
    ))
    stopped = run_pose_driver(environment=limited)
    assert stopped.status == "road_domain_invalid"
    assert not stopped.controls
    loaded_stopped = PoseRunRecord.load(
        PoseRunRecord.capture(stopped).save(tmp_path / "stopped.json")
    )
    assert loaded_stopped.run.status == "road_domain_invalid"
    assert len(loaded_stopped.run.states) == 1
    assert not loaded_stopped.run.road_valid
    assert loaded_stopped.replay_report.passed


def test_content_hash_and_numerical_gate_reject_tampering(short_run, tmp_path):
    record = PoseRunRecord.capture(short_run)
    path = record.save(tmp_path / "changed.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["trace"]["states"][1]["x_m"] += 0.01
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="content hash"):
        PoseRunRecord.load(path)

    _write_changed_record(path, record, lambda data: data["trace"]["states"][-1].__setitem__(
        "x_m", data["trace"]["states"][-1]["x_m"] + 0.01,
    ))
    with pytest.raises(ValueError, match="numerical recorded-control replay"):
        PoseRunRecord.load(path)

    _write_changed_record(path, record, lambda data: data["trace"]["evaluations"][0].__setitem__(
        "cg_lateral_acceleration_mps2", 99.0,
    ))
    with pytest.raises(ValueError, match="evaluation 0 disagrees"):
        PoseRunRecord.load(path)

    _write_changed_record(path, record, lambda data: data["trace"]["controls"][0].__setitem__(
        "drive_torques_nm", [10.0, 10.0, 10.0, 10.0],
    ))
    with pytest.raises(ValueError, match="evaluation 0 disagrees"):
        PoseRunRecord.load(path)

    _write_changed_record(path, record, lambda data: data["inputs"]["settings"].__setitem__(
        "initial_lateral_offset_m", 0.2,
    ))
    with pytest.raises(ValueError, match="initial state disagrees"):
        PoseRunRecord.load(path)


def test_evaluation_float_drift_has_bounded_tolerance(short_run, tmp_path):
    record = PoseRunRecord.capture(short_run)
    path = tmp_path / "evaluation_drift.json"

    def add_small_drift(payload):
        evaluation = payload["trace"]["evaluations"][0]
        original = evaluation["mechanical_energy_j"]
        evaluation["mechanical_energy_j"] = original + max(
            5e-10, abs(original) * 5e-11,
        )

    _write_changed_record(path, record, add_small_drift)
    loaded = PoseRunRecord.load(path)
    assert loaded.replay_report.passed
    assert loaded.run.evaluations[0] == short_run.evaluations[0]

    def add_material_drift(payload):
        evaluation = payload["trace"]["evaluations"][0]
        original = evaluation["mechanical_energy_j"]
        evaluation["mechanical_energy_j"] = original + max(
            1e-5, abs(original) * 1e-6,
        )

    _write_changed_record(path, record, add_material_drift)
    with pytest.raises(ValueError, match="evaluation 0 disagrees"):
        PoseRunRecord.load(path)

    def change_discrete_material(payload):
        payload["trace"]["evaluations"][0]["wheels"][0][
            "road_material_id"
        ] = "tampered_material"

    _write_changed_record(path, record, change_discrete_material)
    with pytest.raises(ValueError, match="evaluation 0 disagrees"):
        PoseRunRecord.load(path)


def test_schema_alignment_and_json_limits(short_run, tmp_path):
    record = PoseRunRecord.capture(short_run)
    path = tmp_path / "unsupported.json"

    _write_changed_record(
        path, record, lambda data: data.__setitem__("schema_version", 999),
    )
    with pytest.raises(ValueError, match="unsupported pose-run record schema"):
        PoseRunRecord.load(path)

    _write_changed_record(
        path, record, lambda data: data["trace"]["states"].pop(),
    )
    with pytest.raises(ValueError, match="not aligned"):
        PoseRunRecord.load(path)

    _write_changed_record(
        path, record, lambda data: data.__setitem__("unreviewed_field", 1),
    )
    with pytest.raises(ValueError, match="unexpected fields"):
        PoseRunRecord.load(path)

    # Strict JSON parsing rejects nonfinite constants before hash validation.
    path.write_text('{"schema_version":NaN}', encoding="utf-8")
    with pytest.raises(ValueError, match="nonfinite JSON constant"):
        PoseRunRecord.load(path)

    path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        PoseRunRecord.load(path)

    with path.open("wb") as stream:
        stream.seek(pose_run_record._MAX_RECORD_BYTES)
        stream.write(b" ")
    with pytest.raises(ValueError, match="32 MiB load cap"):
        PoseRunRecord.load(path)


def test_projection_loss_slack_has_strict_json_null_sentinel(short_run):
    invalid = replace(
        short_run.samples[0], projection_valid=False,
        minimum_assumed_boundary_slack_m=float("-inf"),
    )
    saved = pose_run_record._saved_sample(invalid)
    assert saved["minimum_assumed_boundary_slack_m"] is None
    assert json.dumps(saved, allow_nan=False)
    assert pose_run_record._parse_sample(saved) == invalid
    with pytest.raises(ValueError, match="invalid projection requires null"):
        pose_run_record._parse_sample({
            **saved, "minimum_assumed_boundary_slack_m": -1.0,
        })
