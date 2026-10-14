"""Browser boundary parity, input rejection, and source archive evidence."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import importlib.util
import json
from math import isnan
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import bridge
from lapsim.events.endurance import EnduranceSimulator
from lapsim.experiments.lap_replay import replay_lap_record
from lapsim.experiments.run_record import RunRecord
from lapsim.optimization.torque_profile import PeriodicPiecewiseLinearTorqueProfile
from lapsim.profiles import build_vehicle
from lapsim.ui.course_catalog import load_course
from lapsim.ui.simulation import apply_uniform_road_grip, endurance_run_config, path_solver_settings, resample_track, run_one_lap
from lapsim.solvers.path_constraints import PathConstraintSolver


def _builder():
    spec = importlib.util.spec_from_file_location("build_web", ROOT / "scripts/build_web.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("profile", bridge.PROFILE_IDS)
def test_web_default_matches_desktop_lap_and_all_telemetry(profile):
    settings = {"vehicleProfile": profile}
    actual = bridge.run_simulation(settings)
    vehicle, _ = build_vehicle(profile)
    track = resample_track(load_course(bridge.DEFAULTS["courseId"]), 2.0)
    expected = run_one_lap(vehicle, track, torque_request_fraction=0.8)
    assert actual["status"] == ("completed" if expected.completed else "failed")
    assert actual["elapsedTimeS"] == pytest.approx(expected.driving_time_s, abs=1e-10)
    assert actual["energyKwh"] == pytest.approx(expected.pack_energy_kwh, abs=1e-12)
    assert actual["socFinal"] == pytest.approx(expected.final_state_of_charge, abs=1e-12)
    assert actual["cellCount"] == track.cell_count
    assert actual["courseGeometry"]["distanceM"] == list(track.distance_m)
    assert actual["telemetry"]["sampleTimeS"] == list(expected.telemetry.time_s)
    for name, values in expected.telemetry.items():
        normalized = [None if isnan(value) else value for value in values]
        assert actual["telemetry"]["channels"][name]["values"] == normalized


def test_brake_and_regen_controls_reach_real_engine_and_saved_configuration(tmp_path):
    settings = {"vehicleProfile": "repository_baseline", "brakePressurePsi": 80.0, "regenEnabled": True, "gripMultiplier": 0.7}
    actual = bridge.run_simulation(settings)
    vehicle, _ = build_vehicle("repository_baseline")
    vehicle.brakes.maximum_pressure_psi = 80.0
    apply_uniform_road_grip(vehicle, 0.7)
    track = resample_track(load_course(bridge.DEFAULTS["courseId"]), 2.0)
    limits = PathConstraintSolver(**path_solver_settings(vehicle)).solve(track, vehicle)
    config = replace(endurance_run_config(vehicle), regenerative_braking_soc_threshold=1.0, maximum_driving_time_s=600.0)
    controls = PeriodicPiecewiseLinearTorqueProfile(track.length_m, (0.0, track.length_m * 0.5), (0.8, 0.8))
    expected = EnduranceSimulator().run(vehicle, limits, controls, config, record_telemetry=True)
    assert actual["elapsedTimeS"] == pytest.approx(expected.driving_time_s, abs=1e-10)
    saved = actual["runRecord"]
    assert saved["settings"]["solver"]["path_constraint_settings"]["maximum_brake_pressure_psi"] == 80.0
    assert saved["settings"]["endurance_config"]["regenerative_braking_soc_threshold"] == 1.0
    assert saved["settings"]["conditions"]["road_grip_multiplier"] == 0.7
    record_path = tmp_path / "web-run.json"
    record_path.write_text(json.dumps(saved, allow_nan=False), encoding="utf-8")
    record = RunRecord.load(record_path)
    assert record.run_id == saved["run_id"]
    replay = replay_lap_record(record_path)
    assert replay.model_agreement, replay


def test_exact_record_text_survives_javascript_roundtrip_and_replays(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed for the JavaScript number-format boundary regression")
    response = bridge.run_simulation({})
    serialized_response = json.dumps(response, allow_nan=False)
    process = subprocess.run(
        [node, "-e", "let input='';process.stdin.setEncoding('utf8');process.stdin.on('data',s=>input+=s);process.stdin.on('end',()=>process.stdout.write(JSON.stringify(JSON.parse(input))));"],
        input=serialized_response, capture_output=True, text=True, timeout=15,
    )
    assert process.returncode == 0, process.stderr
    browser_response = json.loads(process.stdout)
    assert browser_response["runRecordJson"] == response["runRecordJson"]
    record_path = tmp_path / "exact-browser-record.json"
    record_path.write_text(browser_response["runRecordJson"], encoding="utf-8")
    loaded = RunRecord.load(record_path)
    assert loaded.run_id == response["runRecord"]["run_id"]
    assert replay_lap_record(record_path).model_agreement


@pytest.mark.parametrize("settings", [
    {"torqueFraction": float("nan")}, {"torqueFraction": float("inf")},
    {"torqueFraction": True}, {"torqueFraction": "0.8"}, {"torqueFraction": -0.1},
    {"gripMultiplier": 0.0}, {"gripMultiplier": 1.6},
    {"brakePressurePsi": 0.0}, {"maxCellLengthM": 0.01},
    {"initialSpeedMps": float("inf")}, {"initialSpeedMps": 41.0},
    {"regenEnabled": 1}, {"courseId": "../../private"}, {"courseId": {}},
    {"vehicleProfile": "unknown"}, {"vehicleProfile": []}, {"surprise": 1},
])
def test_invalid_inputs_are_rejected_before_physics(settings):
    with pytest.raises(ValueError):
        bridge.run_simulation(settings)


def test_browser_grid_cap_is_checked_before_solver(monkeypatch):
    def should_not_run(*args, **kwargs):
        raise AssertionError("solver should not run for an oversized request")
    monkeypatch.setattr(bridge.PathConstraintSolver, "solve", should_not_run)
    with pytest.raises(ValueError, match="1200 browser cells"):
        bridge.run_simulation({"courseId": "team_endurance_fused_gnss_imu", "maxCellLengthM": 0.5})


def test_failed_start_reports_accepted_prefix_and_finite_json():
    actual = bridge.run_simulation({"torqueFraction": 0.0, "initialSpeedMps": 0.0})
    assert actual["status"] == "failed"
    assert actual["failureReason"]
    assert actual["acceptedDistanceM"] == 0.0
    assert actual["acceptedTimeS"] == 0.0
    assert actual["runRecord"]["result"]["status"] == "failed"
    assert json.loads(json.dumps(actual, allow_nan=False)) == actual


def test_progress_only_reports_observed_constraint_and_accepted_lap_work():
    messages = []
    actual = bridge.run_simulation({}, progress=messages.append)
    assert any(update["phase"].startswith("constraints/") for update in messages)
    lap = [update for update in messages if update["phase"] == "lap"]
    assert len(lap) == actual["cellCount"]
    assert [update["completedCells"] for update in lap] == list(range(1, actual["cellCount"] + 1))
    assert lap[-1]["elapsedTimeS"] == actual["acceptedTimeS"]
    assert lap[-1]["distanceM"] == actual["acceptedDistanceM"]
    assert all("estimatedPercent" not in update for update in messages)


@pytest.mark.parametrize("raw", ['{"torqueFraction":NaN}', '{"torqueFraction":0.8,"torqueFraction":0.2}', '[]', 'x' * 8193])
def test_json_boundary_rejects_nonfinite_duplicate_and_oversized_input(raw):
    with pytest.raises(ValueError):
        bridge.run_simulation_json(raw)


def test_source_runtime_archive_matches_manifest_and_runs_without_gui_or_git(tmp_path):
    manifest = _builder().build(tmp_path / "site", runtime_only=True)
    archive = tmp_path / "site/assets/lapsim-runtime.zip"
    assert sha256(archive.read_bytes()).hexdigest() == manifest["archiveSha256"]
    assert archive.stat().st_size == manifest["archiveBytes"]
    extraction = tmp_path / "runtime"
    with ZipFile(archive) as package:
        assert "bundle/analysis/data/track/gnss_imu_endurance_track.csv" in package.namelist()
        assert "bundle/web/bridge.py" in package.namelist()
        assert "bundle/vendor/openpyxl/__init__.py" in package.namelist()
        assert "bundle/vendor/openpyxl-3.1.5.dist-info/METADATA" in package.namelist()
        assert "bundle/vendor/et_xmlfile-2.0.0.dist-info/METADATA" in package.namelist()
        for name in package.namelist():
            assert not name.startswith("/") and ".." not in Path(name).parts
        package.extractall(extraction)
    code = """
import sys, json
from pathlib import Path
root = Path(sys.argv[1])
sys.frozen = True
sys._MEIPASS = str(root)
sys.path[:0] = [str(root / 'bundle/vendor'), str(root / 'bundle/src'), str(root / 'bundle/web')]
import bridge
result = bridge.run_simulation({})
assert result['status'] == 'completed'
assert result['provenance']['sourceIdentity']['source_sha256'] == sys.argv[2]
assert 'tkinter' not in sys.modules and 'matplotlib' not in sys.modules
print(json.dumps({'time': result['elapsedTimeS'], 'cells': result['cellCount']}))
"""
    process = subprocess.run([sys.executable, "-c", code, str(extraction), manifest["sourceIdentity"]["source_sha256"]], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)["cells"] == 98
