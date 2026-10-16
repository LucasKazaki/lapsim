"""Exercise the real desktop worker and browser boundary with identical inputs."""

from math import pi
from pathlib import Path
from queue import Queue
import sys
from types import SimpleNamespace

import pytest

from lapsim.courses.course_bundle import CourseBundle, course_geometry_sha256
from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Track
from lapsim.experiments.lap_replay import replay_lap_record
from lapsim.experiments.run_record import RunRecord
from lapsim.profiles import build_vehicle
from lapsim.ui.app import LapSimDesktop
from lapsim.ui.course_catalog import COURSE_OPTIONS, imported_course_spec, load_course

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import bridge


def synthetic_import():
    track = SpatialTrack.from_track(Track.from_segments([Curve(10.0, 2 * pi)]), maximum_cell_length_m=2.0)
    return CourseBundle.from_dict({
        "schema_version": 1, "course_id": "synthetic_circle", "revision": "v1",
        "label": "Synthetic circle", "description": "Public analytic adapter fixture",
        "source_kind": "synthetic", "boundary_status": "absent",
        "provenance": {"source_name": "Analytic circle", "source_sha256": None,
                       "processing_method": "Exact circular arcs", "review_note": "No measured data"},
        "coordinate_frame": {"type": "local_cartesian_right_handed_xy", "units": "m",
                             "origin": "Start", "x_axis": "east", "y_axis": "north"},
        "travel_direction": "counterclockwise",
        "ai_defaults": {"width_source": "assumed_uniform", "half_width_m": 2.5,
                        "vehicle_width_m": 1.8, "safety_margin_m": 0.2},
        "geometry": {"model": "piecewise_constant_curvature_arcs", "closed": True,
                     "distance_m": list(track.distance_m), "x_m": list(track.x_m),
                     "y_m": list(track.y_m), "curvature_per_m": list(track.curvature_per_m)},
        "geometry_sha256": course_geometry_sha256(track),
    })


@pytest.mark.parametrize("course_id", [
    "synthetic_rounded_rectangle_v1", "team_endurance_fused_gnss_imu", "imported:synthetic_circle@v1",
])
@pytest.mark.parametrize("step_m", [0.5, 5.0])
def test_real_desktop_worker_and_browser_match_geometry_and_physics(course_id, step_m, tmp_path):
    bundle = synthetic_import() if course_id.startswith("imported:") else None
    if bundle is not None:
        # The same serialized public import crosses both actual execution adapters.
        bundle = CourseBundle.load(bundle.save(tmp_path / "synthetic-circle.json"))
    saved = []
    app = SimpleNamespace(
        course_spec=imported_course_spec(bundle) if bundle else next(spec for spec in COURSE_OPTIONS if spec.course_id == course_id),
        track=bundle.track if bundle else load_course(course_id), result_queue=Queue(),
        _vehicle_for_profile=lambda profile, setup: build_vehicle(profile),
        _queue_live_progress=lambda *args: None,
        _save_run_record=lambda **kwargs: saved.append(kwargs) or "captured",
    )
    LapSimDesktop._calculate_single(app, "repository_baseline", "Synthetic baseline", None, step_m, 0.8)
    kind, payload, error = app.result_queue.get_nowait()
    assert error is None, error
    assert kind == "single"
    track = payload[4]
    actual = bridge.run_simulation({
        "courseId": course_id, "vehicleProfile": "repository_baseline", "maxCellLengthM": step_m,
    }, course_bundle=bundle)
    geometry = actual["courseGeometry"]
    assert geometry["distanceM"] == list(track.distance_m)
    assert geometry["xM"] == list(track.x_m)
    assert geometry["yM"] == list(track.y_m)
    assert geometry["curvaturePerM"] == list(track.curvature_per_m)
    assert actual["cellCount"] == track.cell_count
    assert actual["runRecord"]["settings"]["track"]["geometry_sha256"] == course_geometry_sha256(track)
    result = payload[2]
    assert actual["status"] == ("completed" if result.completed else "failed")
    assert actual["elapsedTimeS"] == pytest.approx(result.driving_time_s, abs=1e-10)
    assert actual["energyKwh"] == pytest.approx(result.pack_energy_kwh, abs=1e-12)
    assert actual["socFinal"] == pytest.approx(result.final_state_of_charge, abs=1e-12)
    assert saved[0]["solver_track"] == track
    source = actual["runRecord"]["settings"]["track"]["source_course"]
    assert source["source_geometry_sha256"] == course_geometry_sha256(app.track)
    if bundle:
        assert source["bundle_sha256"] == bundle.bundle_sha256


def test_legacy_browser_record_replays_embedded_coarse_geometry():
    path = Path(__file__).parent / "fixtures/legacy_browser_grid_v2.json"
    record = RunRecord.load(path).to_dict()
    assert record["settings"]["track"]["cell_count"] == 98
    assert replay_lap_record(path).model_agreement


def test_mismatched_import_identity_is_rejected_before_solver(monkeypatch):
    monkeypatch.setattr(bridge.PathConstraintSolver, "solve", lambda *args, **kwargs: pytest.fail("solver executed"))
    with pytest.raises(ValueError, match="does not match"):
        bridge.run_simulation({}, course_bundle=synthetic_import())
