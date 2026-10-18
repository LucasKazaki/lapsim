"""Recipient self-test must exercise the real imported-course desktop route."""

from collections.abc import Iterator
from hashlib import sha256
import json
from math import cos, pi, sin
import os
from pathlib import Path
import tkinter as tk

import pytest

from lapsim import desktop
from lapsim.courses.course_bundle import CourseBundle
from lapsim.courses.solver_grid import resample_track
from lapsim.experiments import RunRecord, default_run_directory
from lapsim.profiles import build_vehicle
from lapsim.ui.app import LapSimDesktop
from test_course_bundle import _manifest


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[LapSimDesktop]:
    for name in ("LOCALAPPDATA", "XDG_DATA_HOME"):
        monkeypatch.setenv(name, str(tmp_path / "user-data"))
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    try:
        yield LapSimDesktop(root)
    finally:
        root.destroy()


def test_recipient_imported_grid_uses_actual_save_and_replay(
    app: LapSimDesktop,
    tmp_path: Path,
) -> None:
    report = desktop._check_imported_course_grid(app, tmp_path / "case")
    assert report["status"] == "passed"
    source = report["fixture"]["geometry"]
    assert len(source["curvature_per_m"]) == 32
    assert source["distance_m"] == [20.0 * pi * index / 32 for index in range(33)]
    cases = report["cases"]
    assert [row["requested_maximum_cell_length_m"] for row in cases] == [5.0, 0.5]
    assert [row["cell_count"] for row in cases] == [32, 128]
    for row, subdivisions in zip(cases, (1, 4), strict=True):
        geometry = row["geometry"]
        assert geometry["closed"] is True
        assert geometry["curvature_per_m"] == [0.1] * row["cell_count"]
        for field in ("distance_m", "x_m", "y_m"):
            assert geometry[field][::subdivisions] == source[field]
        for distance, x, y in zip(
            geometry["distance_m"],
            geometry["x_m"],
            geometry["y_m"],
            strict=True,
        ):
            assert x == pytest.approx(10.0 * sin(distance / 10.0), rel=0.0, abs=1e-12)
            assert y == pytest.approx(
                10.0 * (1.0 - cos(distance / 10.0)), rel=0.0, abs=1e-12
            )
        assert row["expected_inputs_sha256"] == row["recorded_inputs_sha256"]
        expected = row["expected_inputs"]
        assert expected["settings"]["profile_id"] == "repository_baseline"
        assert expected["settings"]["driver"] == {"torque_request_fraction": 0.8}
        assert expected["settings"]["conditions"]["road_grip_multiplier"] == 1.0
        assert (
            expected["settings"]["solver"]["path_constraint_settings"]["maximum_passes"]
            == 120
        )
        assert expected["settings"]["endurance_config"]["starting_speed_mps"] is None
        record_path = default_run_directory() / f"{row['record_run_id']}.json"
        raw = record_path.read_bytes()
        assert len(raw) == row["record_bytes"]
        assert sha256(raw).hexdigest() == row["record_sha256"]
        loaded = RunRecord.load(record_path).to_dict()
        assert loaded["settings"]["track"]["geometry"] == geometry
        assert (
            loaded["settings"]["track"]["source_course"]["bundle_sha256"]
            == report["fixture"]["bundle_sha256"]
        )
        assert (
            loaded["configuration"]["effective_vehicle_config"]
            == expected["effective_vehicle_config"]
        )
        assert row["record_unchanged"] is True
        assert row["replay"]["model_agreement"] is True
        assert row["replay"]["replay_completed"] is True
    assert cases[0]["geometry_sha256"] != cases[1]["geometry_sha256"]
    assert cases[0]["expected_inputs_sha256"] != cases[1]["expected_inputs_sha256"]


def test_recipient_self_test_rejects_generic_resampler(
    app: LapSimDesktop,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "lapsim.ui.app.solver_track_for_course",
        lambda _course, track, step: resample_track(track, step),
    )
    with pytest.raises(
        RuntimeError, match="Recipient grid cell count or curvature is incorrect"
    ):
        desktop._check_imported_course_grid(app, tmp_path / "wrong-grid")


def test_recipient_self_test_rejects_different_effective_profile(
    app: LapSimDesktop,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        app,
        "_vehicle_for_profile",
        lambda *_args: build_vehicle("prius_2026_le"),
    )
    with pytest.raises(RuntimeError, match=r"inputs|configuration|profile"):
        desktop._check_imported_course_grid(app, tmp_path / "wrong-profile")


@pytest.mark.parametrize("raise_inside", [False, True])
def test_self_test_user_storage_restores_environment_and_existing_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raise_inside: bool,
) -> None:
    previous = tmp_path / "existing user"
    previous.mkdir()
    saved = previous / "saved.json"
    saved.write_text(json.dumps({"user": "preserve"}), encoding="utf-8")
    before = saved.read_bytes(), saved.stat().st_mtime_ns
    monkeypatch.setenv("LOCALAPPDATA", str(previous))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    original_cwd = Path.cwd()
    visited = None
    caught = False
    try:
        with desktop._self_test_user_storage() as storage:
            visited = storage
            assert storage.is_dir()
            for name in ("LOCALAPPDATA", "XDG_DATA_HOME"):
                assert Path(os.environ[name]).is_relative_to(storage)
            assert default_run_directory().is_relative_to(storage)
            if raise_inside:
                raise RuntimeError("injected failure")
    except RuntimeError as error:
        caught = True
        assert raise_inside and str(error) == "injected failure"
    assert caught == raise_inside
    assert visited is not None and not visited.exists()
    assert os.environ["LOCALAPPDATA"] == str(previous)
    assert "XDG_DATA_HOME" not in os.environ
    assert Path.cwd() == original_cwd
    assert (saved.read_bytes(), saved.stat().st_mtime_ns) == before


@pytest.mark.parametrize("artifact_kind", ["course_bundle", "run_record"])
def test_atomic_save_keeps_normal_destination_when_temporary_path_is_long(
    tmp_path: Path,
    artifact_kind: str,
) -> None:
    if artifact_kind == "course_bundle":
        source = tmp_path / "short-course.json"
        source.write_text(json.dumps(_manifest(), allow_nan=False), encoding="utf-8")
    else:
        source = Path(__file__).parent / "fixtures" / "legacy_browser_grid_v2.json"
    source_before = source.read_bytes(), source.stat().st_mtime_ns
    if artifact_kind == "course_bundle":
        artifact = CourseBundle.load(source)
        loader = CourseBundle.load
    else:
        artifact = RunRecord.load(source)
        loader = RunRecord.load
    expected = artifact.to_dict()

    # Bound the owned parent and filename components on POSIX as well as Windows.
    root = tmp_path.resolve()
    parent = root / ("p" * max(1, 80 - len(str(root)) - 1))
    parent.mkdir()
    leaf_length = 245 - len(str(parent)) - 1
    assert leaf_length >= 10 and leaf_length + 37 <= 255
    destination = parent / ("s" * (leaf_length - len(".json")) + ".json")
    assert len(str(destination)) == 245
    assert not str(destination).startswith("\\\\?\\")
    prospective_temporary = destination.with_name(f"{destination.name}.{'0' * 32}.tmp")
    assert len(str(prospective_temporary)) == 282
    assert parent.is_dir() and not destination.exists()

    saved = artifact.save(destination)
    assert saved == destination
    assert not str(saved).startswith("\\\\?\\")
    loaded = loader(saved)
    assert loaded.to_dict() == expected
    if isinstance(artifact, CourseBundle):
        assert isinstance(loaded, CourseBundle)
        assert loaded.bundle_sha256 == artifact.bundle_sha256
        assert loaded.geometry_sha256 == artifact.geometry_sha256
    else:
        assert isinstance(loaded, RunRecord)
        assert loaded.run_id == artifact.run_id
    assert not tuple(parent.glob(destination.name + ".*.tmp"))
    assert (source.read_bytes(), source.stat().st_mtime_ns) == source_before


def _catalog_demo_expected_geometry() -> dict:
    # Independent declared segments: 240 straight cells and four 38-cell arcs.
    counts = (80, 38, 40, 38, 80, 38, 40, 38)
    lengths = (40.0, 6 * pi, 20.0, 6 * pi, 40.0, 6 * pi, 20.0, 6 * pi)
    points = (
        lambda u: (u, 0.0),
        lambda u: (40 + 12 * sin(u / 12), 12 - 12 * cos(u / 12)),
        lambda u: (52.0, 12 + u),
        lambda u: (40 + 12 * cos(u / 12), 32 + 12 * sin(u / 12)),
        lambda u: (40 - u, 44.0),
        lambda u: (-12 * sin(u / 12), 32 + 12 * cos(u / 12)),
        lambda u: (-12.0, 32 - u),
        lambda u: (-12 * cos(u / 12), 12 - 12 * sin(u / 12)),
    )
    distance, x, y, curvature = [0.0], [0.0], [0.0], []
    offset = 0.0
    for segment, (count, length, point) in enumerate(
        zip(counts, lengths, points, strict=True)
    ):
        for index in range(1, count + 1):
            local = index * length / count
            distance.append(offset + local)
            px, py = point(local)
            x.append(px)
            y.append(py)
        curvature.extend([0.0 if segment % 2 == 0 else 1 / 12] * count)
        offset += length
    return {
        "closed": True,
        "distance_m": distance,
        "x_m": x,
        "y_m": y,
        "curvature_per_m": curvature,
    }


def test_recipient_catalog_demo_selects_saves_loads_and_replays(
    app: LapSimDesktop,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lapsim.experiments import lap_replay
    from lapsim.experiments.lap_replay import LapReplayReport
    from lapsim.profiles import snapshot_vehicle_config

    vehicle, profile = build_vehicle("repository_baseline")
    expected_config = snapshot_vehicle_config(vehicle)
    expected_model_config = profile.to_dict()["model_config"]
    selected = []
    replay_reports: list[LapReplayReport] = []
    original_replay = lap_replay.replay_lap_record
    original_select = (
        LapSimDesktop._select_course
    )  # Unbound function, no GUI retention.

    def select(instance: LapSimDesktop, label: str) -> None:
        selected.append(label)
        original_select(instance, label)

    def capture_replay(path: str | Path) -> LapReplayReport:
        replay_report = original_replay(path)
        replay_reports.append(replay_report)
        return replay_report

    with monkeypatch.context() as patch:
        patch.setattr(LapSimDesktop, "_select_course", select)
        patch.setattr(lap_replay, "replay_lap_record", capture_replay)
        report = desktop._check_catalog_course_grid(app)
    assert selected == ["Synthetic loop · AI demo"]
    assert len(replay_reports) == 1
    assert (
        app.course_spec.course_id
        == report["course_id"]
        == "synthetic_rounded_rectangle_v1"
    )
    assert report["status"] == "passed"
    source = report["source"]
    assert source["selected_course_id"] == report["course_id"]
    assert source["source_kind"] == "synthetic"
    assert source["revision"] == "generator_v1"
    assert (
        source["source_generator"] == "lapsim.ui.course_catalog._synthetic_demo_track"
    )
    assert source["boundary_status"] == "absent"
    assert source["bundle_id"] is source["bundle_sha256"] is None
    assert source["coordinate_frame"] == "analytic_local_cartesian_xy_m"
    geometry = report["source_geometry"]
    independent = _catalog_demo_expected_geometry()
    assert geometry["closed"] is True
    assert geometry["curvature_per_m"] == independent["curvature_per_m"]
    assert len(geometry["curvature_per_m"]) == 240 + 4 * 38 == 392
    for field in ("distance_m", "x_m", "y_m"):
        assert geometry[field] == pytest.approx(independent[field], rel=0, abs=1e-12)
    encoded = json.dumps(
        geometry, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    source_hash = sha256(encoded.encode()).hexdigest()
    assert source["source_geometry_sha256"] == source_hash
    (row,) = report["cases"]
    assert row["requested_maximum_cell_length_m"] == 5.0
    assert row["cell_count"] == 392
    assert row["geometry"] == geometry
    assert row["geometry_sha256"] == source_hash
    expected = row["expected_inputs"]
    assert expected["settings"]["track"]["id"] == report["course_id"]
    assert expected["settings"]["track"]["source_course"] == source
    assert expected["settings"]["solver"]["requested_maximum_cell_length_m"] == 5.0
    assert expected["settings"]["driver"] == {"torque_request_fraction": 0.8}
    assert expected["settings"]["conditions"]["road_grip_multiplier"] == 1.0
    assert expected["settings"]["endurance_config"]["starting_speed_mps"] is None
    assert expected["selected_profile_id"] == "repository_baseline"
    assert expected["effective_vehicle_config"] == expected_config
    assert expected["base_vehicle_config"] == expected_model_config
    input_hash = sha256(
        json.dumps(
            expected, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()
    assert input_hash == row["expected_inputs_sha256"] == row["recorded_inputs_sha256"]
    path = default_run_directory() / f"{row['record_run_id']}.json"
    before = path.read_bytes(), path.stat().st_mtime_ns
    record = RunRecord.load(path)
    document = record.to_dict()
    assert record.run_id == row["record_run_id"]
    assert len(before[0]) == row["record_bytes"]
    assert sha256(before[0]).hexdigest() == row["record_sha256"]
    assert document["settings"] == expected["settings"]
    assert document["configuration"]["effective_vehicle_config"] == expected_config
    assert (
        document["configuration"]["base_profile_manifest"]["model_config"]
        == expected_model_config
    )
    assert row["record_unchanged"] is True
    replay = row["replay"]
    assert replay["model_agreement"] is replay["replay_completed"] is True
    assert replay["run_id"] == record.run_id
    assert replay["recorded_sample_count"] == replay["replayed_sample_count"] == 392
    assert not replay["mismatch_reasons"]
    assert replay == replay_reports[0].to_dict()
    assert replay["metrics"] and all(
        metric["passed"] and metric["maximum_absolute_error"] == 0
        for metric in replay["metrics"]
    )
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_recipient_catalog_rejects_catalog_only_generic_grid(
    app: LapSimDesktop,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lapsim.ui.course_catalog import solver_track_for_course

    observed_cells = []

    def catalog_only_generic(course_id, track, step):
        if course_id == "synthetic_rounded_rectangle_v1":
            wrong = resample_track(track, step)
            observed_cells.append(wrong.cell_count)
            return wrong
        return solver_track_for_course(course_id, track, step)

    with monkeypatch.context() as patch:
        patch.setattr("lapsim.ui.app.solver_track_for_course", catalog_only_generic)
        imported = desktop._check_imported_course_grid(
            app, tmp_path / "imported-control"
        )
        assert imported["status"] == "passed"
        assert [row["cell_count"] for row in imported["cases"]] == [32, 128]
        with pytest.raises(
            RuntimeError,
            match="Recipient catalog grid cell count or curvature is incorrect",
        ):
            desktop._check_catalog_course_grid(app)
    assert observed_cells == [40]


def _fused_coarse_source_oracle():
    import csv
    from fractions import Fraction

    from lapsim.ui.simulation import ENDURANCE_TRACK_PATH

    path = ENDURANCE_TRACK_PATH
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    stations = [Fraction(row["distance_m"]) for row in rows]
    assert stations == [Fraction(index, 2) for index in range(1979)]
    assert rows[-1]["curvature_per_m"] == ""
    curvature = [Fraction(row["curvature_per_m"]) for row in rows[:-1]]
    coarse_stations = [Fraction(index * 5) for index in range(198)]
    coarse_stations.append(Fraction(989))
    indices = [int(station * 2) for station in coarse_stations]
    weighted = []
    for lower, upper, first, stop in zip(
        coarse_stations[:-1],
        coarse_stations[1:],
        indices[:-1],
        indices[1:],
        strict=True,
    ):
        turn = sum(
            (
                curvature[index] * (stations[index + 1] - stations[index])
                for index in range(first, stop)
            ),
            Fraction(0),
        )
        weighted.append(float(turn / (upper - lower)))
    source_geometry = {
        "closed": True,
        "distance_m": [float(value) for value in stations],
        "x_m": [float(row["x_m"]) for row in rows],
        "y_m": [float(row["y_m"]) for row in rows],
        "curvature_per_m": [float(value) for value in curvature],
    }
    coarse = {
        "closed": True,
        "distance_m": [float(value) for value in coarse_stations],
        "x_m": [float(rows[index]["x_m"]) for index in indices],
        "y_m": [float(rows[index]["y_m"]) for index in indices],
        "curvature_per_m": weighted,
    }
    wrong = tuple(float(curvature[index]) for index in indices[:-1])
    assert len(weighted) == len(wrong) == 198
    assert coarse["distance_m"][-1] - coarse["distance_m"][-2] == 4.0
    assert all(
        abs(start_sample - mean) > 1e-12
        for start_sample, mean in zip(wrong, weighted, strict=True)
    )
    return path, source_geometry, coarse, wrong


def _assert_fused_coarse_channels(geometry, oracle) -> None:
    assert geometry["closed"] is True
    assert len(geometry["curvature_per_m"]) == 198
    for name in ("distance_m", "x_m", "y_m"):
        assert geometry[name] == oracle[name]
    for observed, expected in zip(
        geometry["curvature_per_m"],
        oracle["curvature_per_m"],
        strict=True,
    ):
        assert observed == pytest.approx(expected, rel=0.0, abs=1e-12)


def test_recipient_fused_coarse_selects_saves_loads_and_replays(
    app: LapSimDesktop,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from math import isfinite

    from lapsim.experiments import LapRunSettings, lap_replay
    from lapsim.experiments.lap_replay import LapReplayReport
    from lapsim.profiles import snapshot_vehicle_config
    from lapsim.ui import course_catalog
    from lapsim.ui.simulation import (
        apply_uniform_road_grip,
        endurance_run_config,
        path_solver_settings,
    )

    app._select_course("Synthetic loop · AI demo")
    assert app.course_spec.course_id == "synthetic_rounded_rectangle_v1"
    initial_source = json.loads(app.course_source_json)
    assert initial_source["selected_course_id"] == app.course_spec.course_id
    assert initial_source["source_kind"] == "synthetic"
    assert initial_source["source_generator"] == (
        "lapsim.ui.course_catalog._synthetic_demo_track"
    )
    check_fused = desktop._check_fused_course_grid
    path, source_geometry, oracle, _wrong = _fused_coarse_source_oracle()
    files = (path, path.with_suffix(".json"))
    source_before = {
        source: (source.read_bytes(), source.stat().st_mtime_ns) for source in files
    }
    selected, frozen, policies = [], [], []
    replay_reports: list[LapReplayReport] = []
    original_select = LapSimDesktop._select_course
    original_worker = LapSimDesktop._calculate_single
    original_resolve = course_catalog.resolve_solver_grid
    original_replay = lap_replay.replay_lap_record

    def select(instance: LapSimDesktop, label: str) -> None:
        selected.append(label)
        original_select(instance, label)

    def resolve(track, step_m, *, coherent_arcs):
        policies.append((step_m, coherent_arcs))
        return original_resolve(track, step_m, coherent_arcs=coherent_arcs)

    def worker(instance, profile_id, profile_name, setup, step_m, torque, grip):
        assert profile_id == "repository_baseline" and setup is None
        assert profile_name == "Recipient grid self-test"
        assert (step_m, torque, grip) == (5.0, 0.8, 1.0)
        assert instance.course_spec.course_id == "team_endurance_fused_gnss_imu"
        source = json.loads(instance.course_source_json)
        resolved = course_catalog.solver_track_for_course(
            instance.course_spec.course_id, instance.track, step_m
        )
        geometry = {
            "closed": resolved.closed,
            "distance_m": list(resolved.distance_m),
            "x_m": list(resolved.x_m),
            "y_m": list(resolved.y_m),
            "curvature_per_m": list(resolved.curvature_per_m),
        }
        _assert_fused_coarse_channels(geometry, oracle)
        vehicle, manifest = build_vehicle(profile_id)
        apply_uniform_road_grip(vehicle, grip)
        settings = LapRunSettings.from_track(
            resolved,
            track_id=instance.course_spec.course_id,
            solver_step_m=step_m,
            solver_settings=path_solver_settings(vehicle),
            torque_request_fraction=torque,
            road_grip_multiplier=grip,
            endurance_config=endurance_run_config(vehicle),
            profile_id=profile_id,
            profile_label=profile_name,
            source_course=source,
        ).to_dict()
        inputs = json.loads(
            json.dumps(
                {
                    "settings": settings,
                    "effective_vehicle_config": snapshot_vehicle_config(vehicle),
                    "base_vehicle_config": manifest.to_dict()["model_config"],
                    "selected_profile_id": profile_id,
                },
                allow_nan=False,
            )
        )
        frozen.append((source, geometry, inputs))
        return original_worker(
            instance, profile_id, profile_name, setup, step_m, torque, grip
        )

    def capture_replay(record_path: str | Path) -> LapReplayReport:
        result = original_replay(record_path)
        replay_reports.append(result)
        return result

    with monkeypatch.context() as patch:
        patch.setattr(LapSimDesktop, "_select_course", select)
        patch.setattr(LapSimDesktop, "_calculate_single", worker)
        patch.setattr(course_catalog, "resolve_solver_grid", resolve)
        patch.setattr(lap_replay, "replay_lap_record", capture_replay)
        report = check_fused(app)
    assert selected == ["Fused GNSS/IMU · default"]
    assert policies and all(value == (5.0, False) for value in policies)
    assert len(frozen) == len(replay_reports) == 1
    source, resolved_geometry, inputs = frozen[0]
    assert report["status"] == "passed"
    assert (
        report["course_id"]
        == app.course_spec.course_id
        == "team_endurance_fused_gnss_imu"
    )
    assert report["source"] == source == json.loads(app.course_source_json)
    assert source != initial_source
    assert source["metadata_version"] == 1
    assert source["selected_course_id"] == report["course_id"]
    assert source["source_kind"] == "recorded_fusion_unverified"
    assert source["revision"] == "legacy_unversioned"
    assert source["coordinate_frame"] == "legacy_map_registered_xy_unknown_origin"
    assert source["boundary_status"] == "absent"
    assert source["source_geometry_hash_scope"] == (
        "canonical loaded closed/distance_m/x_m/y_m/curvature_per_m"
    )
    assert (
        source["bundle_id"]
        is source["bundle_sha256"]
        is source["bundle_hash_scope"]
        is None
    )
    assert source["source_artifact_sha256"] == {
        "fused_csv": sha256(source_before[path][0]).hexdigest(),
        "fusion_metadata_json": sha256(
            source_before[path.with_suffix(".json")][0]
        ).hexdigest(),
    }
    assert report["source_geometry"] == source_geometry
    assert (
        source["source_geometry_sha256"]
        == sha256(
            json.dumps(
                source_geometry, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()
    )
    assert {
        "closed": app.track.closed,
        "distance_m": list(app.track.distance_m),
        "x_m": list(app.track.x_m),
        "y_m": list(app.track.y_m),
        "curvature_per_m": list(app.track.curvature_per_m),
    } == source_geometry
    (row,) = report["cases"]
    assert row["requested_maximum_cell_length_m"] == 5.0 and row["cell_count"] == 198
    _assert_fused_coarse_channels(row["geometry"], oracle)
    assert row["geometry"] == resolved_geometry
    assert (
        row["geometry_sha256"]
        == sha256(
            json.dumps(
                resolved_geometry,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
    )
    assert row["expected_inputs"] == inputs
    assert inputs["settings"]["solver"]["requested_maximum_cell_length_m"] == 5.0
    assert inputs["settings"]["driver"] == {"torque_request_fraction": 0.8}
    assert inputs["settings"]["conditions"]["road_grip_multiplier"] == 1.0
    assert inputs["settings"]["endurance_config"]["starting_speed_mps"] is None
    assert inputs["settings"]["track"]["source_course"] == source
    assert (
        row["expected_inputs_sha256"]
        == row["recorded_inputs_sha256"]
        == sha256(
            json.dumps(
                inputs, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()
    )
    record_path = default_run_directory() / f"{row['record_run_id']}.json"
    before = record_path.read_bytes(), record_path.stat().st_mtime_ns
    record = RunRecord.load(record_path)
    document = record.to_dict()
    assert record.run_id == row["record_run_id"]
    assert (
        len(before[0]) == row["record_bytes"]
        and sha256(before[0]).hexdigest() == row["record_sha256"]
    )
    assert document["settings"] == inputs["settings"]
    assert (
        document["configuration"]["effective_vehicle_config"]
        == inputs["effective_vehicle_config"]
    )
    assert (
        document["configuration"]["base_profile_manifest"]["model_config"]
        == inputs["base_vehicle_config"]
    )
    assert (
        document["configuration"]["selected_profile_id"]
        == inputs["selected_profile_id"]
    )
    assert row["record_unchanged"] is True
    assert row["starting_speed"]["configured_override_mps"] is None
    assert (
        isfinite(row["starting_speed"]["resolved_mps"])
        and row["starting_speed"]["resolved_mps"] >= 0.0
    )
    assert (
        row["starting_speed"]["resolved_mps"]
        == document["result"]["starting_speed_mps"]
    )
    replay = row["replay"]
    assert replay == replay_reports[0].to_dict()
    assert replay["model_agreement"] is replay["replay_completed"] is True
    assert replay["run_id"] == record.run_id
    assert replay["recorded_sample_count"] == replay["replayed_sample_count"] == 198
    assert not replay["mismatch_reasons"] and replay["metrics"]
    for metric in replay["metrics"]:
        assert metric["passed"] is True
        assert metric["maximum_absolute_error"] is not None
        assert isfinite(metric["maximum_absolute_error"]) and isfinite(
            metric["tolerance"]
        )
        assert metric["maximum_absolute_error"] == 0.0 <= metric["tolerance"]
    assert (record_path.read_bytes(), record_path.stat().st_mtime_ns) == before
    assert {
        source: (source.read_bytes(), source.stat().st_mtime_ns) for source in files
    } == source_before


def test_recipient_fused_coarse_rejects_worker_start_sample_curvature(
    app: LapSimDesktop,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    from lapsim.ui import app as app_module

    check_fused = desktop._check_fused_course_grid
    path, _source_geometry, oracle, wrong_curvature = _fused_coarse_source_oracle()
    files = (path, path.with_suffix(".json"))
    source_before = {
        source: (source.read_bytes(), source.stat().st_mtime_ns) for source in files
    }
    original = app_module.solver_track_for_course
    original_worker = LapSimDesktop._calculate_single
    injected = []
    worker_calls = []

    def worker(instance, *args, **kwargs):
        worker_calls.append(True)
        return original_worker(instance, *args, **kwargs)

    def wrong_worker_grid(course_id, track, step_m):
        resolved = original(course_id, track, step_m)
        if course_id == "team_endurance_fused_gnss_imu" and step_m == 5.0:
            assert worker_calls == [True]
            assert resolved.cell_count == 198 and resolved.closed is True
            for name in ("distance_m", "x_m", "y_m"):
                assert list(getattr(resolved, name)) == oracle[name]
            changed = replace(resolved, curvature_per_m=wrong_curvature)
            assert changed.distance_m == resolved.distance_m
            assert changed.x_m == resolved.x_m and changed.y_m == resolved.y_m
            assert changed.cell_count == resolved.cell_count
            injected.append(changed.curvature_per_m)
            return changed
        return resolved

    with monkeypatch.context() as patch:
        patch.setattr(LapSimDesktop, "_calculate_single", worker)
        patch.setattr(app_module, "solver_track_for_course", wrong_worker_grid)
        with pytest.raises(
            RuntimeError,
            match="Recipient fused grid cell count or curvature is incorrect",
        ):
            check_fused(app)
    assert injected == [wrong_curvature]
    assert worker_calls == [True]
    assert {
        source: (source.read_bytes(), source.stat().st_mtime_ns) for source in files
    } == source_before
