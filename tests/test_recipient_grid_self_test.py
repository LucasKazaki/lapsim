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
        report = check_fused(app, maximum_cell_lengths_m=(5.0,))
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
            check_fused(app, maximum_cell_lengths_m=(5.0,))
    assert injected == [wrong_curvature]
    assert worker_calls == [True]
    assert {
        source: (source.read_bytes(), source.stat().st_mtime_ns) for source in files
    } == source_before


def _fused_consumer_report() -> dict:
    from copy import deepcopy

    path, source_geometry, geometry, _wrong = _fused_coarse_source_oracle()

    def digest(value):
        return sha256(
            json.dumps(
                value, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()

    source = {
        "metadata_version": 1,
        "selected_course_id": "team_endurance_fused_gnss_imu",
        "source_geometry_sha256": digest(source_geometry),
        "source_geometry_hash_scope": (
            "canonical loaded closed/distance_m/x_m/y_m/curvature_per_m"
        ),
        "source_kind": "recorded_fusion_unverified",
        "revision": "legacy_unversioned",
        "coordinate_frame": "legacy_map_registered_xy_unknown_origin",
        "boundary_status": "absent",
        "bundle_id": None,
        "bundle_sha256": None,
        "bundle_hash_scope": None,
        "source_artifact_sha256": {
            "fused_csv": sha256(path.read_bytes()).hexdigest(),
            "fusion_metadata_json": sha256(
                path.with_suffix(".json").read_bytes()
            ).hexdigest(),
        },
    }
    inputs = {
        "settings": {
            "track": {
                "id": source["selected_course_id"],
                "cell_count": 198,
                "length_m": 989.0,
                "closed": True,
                "geometry": deepcopy(geometry),
                "geometry_sha256": digest(geometry),
                "source_course": deepcopy(source),
            },
            "solver": {
                "requested_maximum_cell_length_m": 5.0,
                "future_solver_key": {"value": 7},
            },
            "endurance_config": {"laps": 1},
            "driver": {"torque_request_fraction": 0.8},
            "conditions": {"road_grip_multiplier": 1.0},
        },
        "effective_vehicle_config": {"future_effective_key": [1, 2]},
        "base_vehicle_config": {"future_base_key": {"tag": "fixture"}},
        "selected_profile_id": "repository_baseline",
        "future_top_level_key": {"do_not_drop": True},
    }
    report = {
        "status": "passed",
        "checks": {"fused_course_grid": True},
        "build": None,
        "frozen": False,
        "recipient_fused_grid": {
            "status": "passed",
            "course_id": source["selected_course_id"],
            "source": source,
            "source_geometry": source_geometry,
            "cases": [
                {
                    "requested_maximum_cell_length_m": 5.0,
                    "cell_count": 198,
                    "geometry": geometry,
                    "geometry_sha256": digest(geometry),
                    "expected_inputs": inputs,
                    "expected_inputs_sha256": digest(inputs),
                    "recorded_inputs_sha256": digest(inputs),
                    "record_unchanged": True,
                    "record_run_id": "1" * 64,
                    "replay": {
                        "run_id": "1" * 64,
                        "model_agreement": True,
                        "replay_completed": True,
                        "recorded_sample_count": 198,
                        "replayed_sample_count": 198,
                        "mismatch_reasons": [],
                        "provenance_warnings": ["Synthetic report fixture only"],
                        "metrics": [
                            {
                                "name": name,
                                "maximum_absolute_error": (
                                    0.005 if name == "driving_time_s" else 0.0
                                ),
                                "tolerance": tolerance,
                                "passed": True,
                            }
                            for name, tolerance in (
                                ("driving_time_s", 0.01),
                                ("lap_time_s", 0.01),
                                ("starting_speed_mps", 0.01),
                                ("ending_speed_mps", 0.01),
                                ("pack_energy_kwh", 1e-5),
                                ("final_state_of_charge", 1e-5),
                                ("sample_time_s", 0.01),
                                ("sample_distance_m", 1e-8),
                                ("speed_trace_mps", 0.01),
                                ("path_speed_ceiling_mps", 0.01),
                                ("controls.motor_torque_request_nm", 0.0),
                                ("controls.front_brake_pressure_psi", 0.0),
                                ("controls.rear_brake_pressure_psi", 0.0),
                                (
                                    "controls.rear_regenerative_brake_force_request_n",
                                    0.0,
                                ),
                                ("controls.steering_angle_rad", 0.0),
                                (
                                    "controls.front_regenerative_brake_force_request_n",
                                    0.0,
                                ),
                                ("tire.road_grip_multiplier", 0.0),
                            )
                        ],
                    },
                }
            ],
        },
    }
    fine = deepcopy(report["recipient_fused_grid"]["cases"][0])
    fine.update(
        requested_maximum_cell_length_m=0.5,
        cell_count=1978,
        geometry=deepcopy(source_geometry),
        record_run_id="3" * 64,
    )
    fine["expected_inputs"]["settings"]["track"]["cell_count"] = 1978
    fine["expected_inputs"]["settings"]["solver"]["requested_maximum_cell_length_m"] = (
        0.5
    )
    fine["replay"].update(
        run_id=fine["record_run_id"],
        recorded_sample_count=1978,
        replayed_sample_count=1978,
    )
    report["recipient_fused_grid"]["cases"].append(fine)
    _reseal_fused_consumer_report(report)
    return report


def _fused_consumer():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "quality/run_package_runtime.py"
    spec = importlib.util.spec_from_file_location("recipient_package_consumer", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._fused_grid_identity


def _reseal_fused_consumer_report(report: dict) -> None:
    def digest(value):
        return sha256(
            json.dumps(
                value, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()

    for row in report["recipient_fused_grid"]["cases"]:
        row["geometry_sha256"] = digest(row["geometry"])
        track = row["expected_inputs"]["settings"]["track"]
        track["geometry"] = json.loads(json.dumps(row["geometry"]))
        track["geometry_sha256"] = row["geometry_sha256"]
        track["source_course"] = json.loads(
            json.dumps(report["recipient_fused_grid"]["source"])
        )
        row["expected_inputs_sha256"] = row["recorded_inputs_sha256"] = digest(
            row["expected_inputs"]
        )


@pytest.mark.parametrize("frozen", [False, True])
def test_fused_consumer_context_hashes_stay_local_and_inputs_are_not_mutated(
    frozen: bool,
) -> None:
    from copy import deepcopy
    from math import nextafter

    consume = _fused_consumer()
    first = _fused_consumer_report()
    original = deepcopy(first)
    baseline = consume(first)
    assert first == original
    second = deepcopy(first)
    source = second["recipient_fused_grid"]["source"]
    source["source_artifact_sha256"] = {
        "fused_csv": "a" * 64,
        "fusion_metadata_json": "b" * 64,
    }
    resource_hashes = {
        "analysis/data/track/gnss_imu_endurance_track.csv": "a" * 64,
        "analysis/data/track/gnss_imu_endurance_track.json": "b" * 64,
    }
    second["build"] = {
        "files_sha256": resource_hashes,
        "source_sha256": sha256(
            (
                json.dumps(resource_hashes, sort_keys=True)
                if frozen
                else json.dumps(resource_hashes, sort_keys=True, separators=(",", ":"))
            ).encode()
        ).hexdigest(),
    }
    second["frozen"] = frozen
    row = second["recipient_fused_grid"]["cases"][0]
    row["geometry"]["curvature_per_m"][0] = nextafter(
        row["geometry"]["curvature_per_m"][0], float("inf")
    )
    row["record_run_id"] = "2" * 64
    row["replay"]["run_id"] = row["record_run_id"]
    _reseal_fused_consumer_report(second)
    observed = consume(second)
    assert observed["identity"] == baseline["identity"]
    assert observed["observed"] != baseline["observed"]
    assert (
        observed["observed"]["expected_inputs_sha256"]
        != baseline["observed"]["expected_inputs_sha256"]
    )


@pytest.mark.parametrize("channel", ["distance_m", "x_m", "y_m", "curvature_per_m"])
def test_fused_consumer_rejects_truthfully_rehashed_wrong_geometry(
    channel: str,
) -> None:
    report = _fused_consumer_report()
    report["recipient_fused_grid"]["cases"][0]["geometry"][channel][1] += 0.01
    _reseal_fused_consumer_report(report)
    with pytest.raises(RuntimeError, match="independent cell oracle"):
        _fused_consumer()(report)


@pytest.mark.parametrize(
    "section",
    [
        "settings",
        "effective_vehicle_config",
        "base_vehicle_config",
        "future_top_level_key",
    ],
)
def test_fused_consumer_compares_unknown_configuration_keys(section: str) -> None:
    consume = _fused_consumer()
    report = _fused_consumer_report()
    before = consume(report)
    row = report["recipient_fused_grid"]["cases"][0]
    row["expected_inputs"][section]["new_unknown_key"] = {"must_compare": 42}
    _reseal_fused_consumer_report(report)
    assert consume(report)["identity"] != before["identity"]


@pytest.mark.parametrize(
    "fault",
    [
        "check",
        "recorded_hash",
        "resource_hash",
        "replay",
        "record_changed",
        "partial_count",
        "failed_metric",
        "null_error",
        "run_id",
        "mismatch",
        "no_metrics",
        "truncated_metrics",
        "duplicate_metric",
        "altered_tolerance",
    ],
)
def test_fused_consumer_rejects_incomplete_local_evidence(fault: str) -> None:
    report = _fused_consumer_report()
    row = report["recipient_fused_grid"]["cases"][0]
    if fault == "check":
        report["checks"].clear()
    elif fault == "recorded_hash":
        row["recorded_inputs_sha256"] = "0" * 64
    elif fault == "resource_hash":
        report["recipient_fused_grid"]["source"]["source_artifact_sha256"][
            "fused_csv"
        ] = "a" * 64
    elif fault == "replay":
        row["replay"]["model_agreement"] = False
    elif fault == "record_changed":
        row["record_unchanged"] = False
    elif fault == "partial_count":
        row["replay"]["replayed_sample_count"] = 197
    elif fault == "failed_metric":
        row["replay"]["metrics"][0]["passed"] = False
    elif fault == "null_error":
        row["replay"]["metrics"][0]["maximum_absolute_error"] = None
    elif fault == "run_id":
        row["replay"]["run_id"] = "another-run"
    elif fault == "mismatch":
        row["replay"]["mismatch_reasons"] = ["Contradictory local report"]
    elif fault == "no_metrics":
        row["replay"]["metrics"] = []
    elif fault == "truncated_metrics":
        row["replay"]["metrics"] = [row["replay"]["metrics"][2]]
    elif fault == "duplicate_metric":
        row["replay"]["metrics"].append(dict(row["replay"]["metrics"][0]))
    else:
        row["replay"]["metrics"][0].update(
            maximum_absolute_error=100.0, tolerance=1000.0
        )
    with pytest.raises(RuntimeError, match="Recipient fused-grid report is invalid"):
        _fused_consumer()(report)


def test_fused_consumer_binds_actual_source_root_before_normalizing(
    tmp_path: Path,
) -> None:
    consume = _fused_consumer()
    report = _fused_consumer_report()
    baseline = consume(report)
    path, _source, _geometry, _wrong = _fused_coarse_source_oracle()
    target = tmp_path / "analysis/data/track"
    target.mkdir(parents=True)
    for source in (path, path.with_suffix(".json")):
        original = source.read_bytes()
        lf = original.replace(b"\r\n", b"\n")
        changed = lf if original != lf else lf.replace(b"\n", b"\r\n")
        (target / source.name).write_bytes(changed)
    raw = report["recipient_fused_grid"]["source"]["source_artifact_sha256"]
    raw["fused_csv"] = sha256((target / path.name).read_bytes()).hexdigest()
    raw["fusion_metadata_json"] = sha256(
        (target / path.with_suffix(".json").name).read_bytes()
    ).hexdigest()
    _reseal_fused_consumer_report(report)
    with pytest.raises(RuntimeError, match="raw source hashes"):
        consume(report)
    observed = consume(report, source_root=tmp_path)
    assert observed["identity"] == baseline["identity"]
    assert (
        observed["observed"]["raw_source_sha256"]
        != baseline["observed"]["raw_source_sha256"]
    )


@pytest.mark.parametrize("field", ["curvature_per_m", "x_m"])
def test_fused_consumer_rejects_semantic_source_root_with_truthful_raw_hashes(
    field: str,
    tmp_path: Path,
) -> None:
    import csv

    path, _source, _geometry, _wrong = _fused_coarse_source_oracle()
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[0][field] = str(float(rows[0][field]) + 0.01)
    target = tmp_path / "analysis/data/track"
    target.mkdir(parents=True)
    with (target / path.name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    metadata = target / path.with_suffix(".json").name
    metadata.write_bytes(path.with_suffix(".json").read_bytes())
    report = _fused_consumer_report()
    raw = report["recipient_fused_grid"]["source"]["source_artifact_sha256"]
    raw["fused_csv"] = sha256((target / path.name).read_bytes()).hexdigest()
    raw["fusion_metadata_json"] = sha256(metadata.read_bytes()).hexdigest()
    _reseal_fused_consumer_report(report)
    # Raw hashes and full input hashes are truthful; the claimed264e source is not.
    with pytest.raises(RuntimeError, match="source geometry differs"):
        _fused_consumer()(report, source_root=tmp_path)


def test_recipient_fused_fine_preserves_source_and_replays_saved_record(
    app: LapSimDesktop,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from math import isfinite

    from lapsim.experiments import lap_replay

    path, source_geometry, _coarse, _wrong = _fused_coarse_source_oracle()
    files = (path, path.with_suffix(".json"))
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files}
    replay_reports = []
    original_replay = lap_replay.replay_lap_record

    def replay(record_path):
        saved = Path(record_path)
        unchanged = saved.read_bytes(), saved.stat().st_mtime_ns
        result = original_replay(record_path)
        assert (saved.read_bytes(), saved.stat().st_mtime_ns) == unchanged
        replay_reports.append(result.to_dict())
        return result

    app._select_course("Synthetic loop · AI demo")
    with monkeypatch.context() as patch:
        patch.setattr(lap_replay, "replay_lap_record", replay)
        report = desktop._check_fused_course_grid(app)

    assert [c["requested_maximum_cell_length_m"] for c in report["cases"]] == [
        5.0,
        0.5,
    ]
    assert [c["cell_count"] for c in report["cases"]] == [198, 1978]
    assert report["source_geometry"] == source_geometry
    assert len(replay_reports) == 2
    fine = report["cases"][1]
    geometry = fine["geometry"]
    assert geometry["closed"] is True
    for name in ("distance_m", "x_m", "y_m"):
        assert geometry[name] == source_geometry[name]
    assert geometry["distance_m"] == [index * 0.5 for index in range(1979)]
    assert len(geometry["curvature_per_m"]) == 1978
    for value, expected in zip(
        geometry["curvature_per_m"], source_geometry["curvature_per_m"], strict=True
    ):
        assert value == pytest.approx(expected, rel=0.0, abs=1e-12)

    saved = default_run_directory() / f"{fine['record_run_id']}.json"
    record_object = RunRecord.load(saved)
    record = record_object.to_dict()
    inputs = fine["expected_inputs"]
    assert record["settings"] == inputs["settings"]
    assert inputs["settings"]["solver"]["requested_maximum_cell_length_m"] == 0.5
    assert inputs["settings"]["track"]["geometry"] == geometry
    assert inputs["settings"]["track"]["source_course"] == report["source"]
    assert inputs["selected_profile_id"] == "repository_baseline"
    assert (
        record["configuration"]["effective_vehicle_config"]
        == inputs["effective_vehicle_config"]
    )
    assert (
        record["configuration"]["base_profile_manifest"]["model_config"]
        == inputs["base_vehicle_config"]
    )
    assert (
        record["configuration"]["selected_profile_id"] == inputs["selected_profile_id"]
    )
    expected_hash = sha256(
        json.dumps(
            inputs, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()
    assert (
        fine["expected_inputs_sha256"]
        == fine["recorded_inputs_sha256"]
        == expected_hash
    )
    assert fine["record_sha256"] == sha256(saved.read_bytes()).hexdigest()
    assert fine["record_bytes"] == saved.stat().st_size
    assert fine["record_unchanged"] is True
    assert fine["replay"] == replay_reports[1]
    replayed = fine["replay"]
    assert replayed["run_id"] == record_object.run_id == fine["record_run_id"]
    assert replayed["model_agreement"] is replayed["replay_completed"] is True
    assert (
        replayed["recorded_sample_count"] == replayed["replayed_sample_count"] == 1978
    )
    assert not replayed["mismatch_reasons"]
    assert (
        len({m["name"] for m in replayed["metrics"]}) == len(replayed["metrics"]) == 17
    )
    expected_tolerances = {
        metric["name"]: metric["tolerance"]
        for metric in _fused_consumer_report()["recipient_fused_grid"]["cases"][0][
            "replay"
        ]["metrics"]
    }
    assert {
        m["name"]: m["tolerance"] for m in replayed["metrics"]
    } == expected_tolerances
    assert all(
        m["passed"] is True
        and isfinite(m["maximum_absolute_error"])
        and 0.0 <= m["maximum_absolute_error"] <= m["tolerance"]
        for m in replayed["metrics"]
    )
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files} == before


def test_recipient_fused_fine_rejects_refined_coarse_worker_grid(
    app: LapSimDesktop,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lapsim.ui import app as app_module

    path, source_geometry, _coarse, _wrong = _fused_coarse_source_oracle()
    files = (path, path.with_suffix(".json"))
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files}
    original = app_module.solver_track_for_course
    original_worker = LapSimDesktop._calculate_single
    injected = []
    worker_requests = []

    def worker(instance, profile_id, profile_name, setup, step_m, *args):
        worker_requests.append(step_m)
        return original_worker(instance, profile_id, profile_name, setup, step_m, *args)

    def worker_grid(course_id, track, step_m):
        resolved = original(course_id, track, step_m)
        if course_id == "team_endurance_fused_gnss_imu" and step_m == 0.5:
            assert worker_requests == [5.0, 0.5]
            wrong = resample_track(original(course_id, track, 5.0), 0.5)
            assert resolved.cell_count == wrong.cell_count == 1978
            assert list(wrong.distance_m) == source_geometry["distance_m"]
            assert all(
                abs(value - expected) > 1e-12
                for value, expected in zip(
                    wrong.curvature_per_m,
                    source_geometry["curvature_per_m"],
                    strict=True,
                )
            )
            assert list(wrong.x_m) != source_geometry["x_m"]
            injected.append(wrong)
            return wrong
        return resolved

    with monkeypatch.context() as patch:
        patch.setattr(LapSimDesktop, "_calculate_single", worker)
        patch.setattr(app_module, "solver_track_for_course", worker_grid)
        with pytest.raises(
            RuntimeError,
            match="Recipient fused grid cell count or curvature is incorrect",
        ):
            desktop._check_fused_course_grid(app)
    assert len(injected) == 1
    assert worker_requests == [5.0, 0.5]
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files} == before


def test_fused_consumer_dual_grid_validates_each_case_without_mutation() -> None:
    from copy import deepcopy

    report = _fused_consumer_report()
    before = deepcopy(report)
    result = _fused_consumer()(report)
    assert report == before
    assert [
        (row["requested_maximum_cell_length_m"], row["cell_count"])
        for row in result["identity"]["cases"]
    ] == [(5.0, 198), (0.5, 1978)]
    assert len(result["observed"]["cases"]) == 2
    for actual, expected in zip(
        result["observed"]["cases"],
        report["recipient_fused_grid"]["cases"],
        strict=True,
    ):
        assert actual["record_run_id"] == expected["record_run_id"]
        assert actual["replay"] == expected["replay"]
        assert actual["expected_inputs_sha256"] == expected["recorded_inputs_sha256"]


def test_fused_consumer_dual_grid_keeps_fine_rounding_contextual() -> None:
    from math import nextafter

    consume = _fused_consumer()
    report = _fused_consumer_report()
    before = consume(report)
    fine = report["recipient_fused_grid"]["cases"][1]
    fine["geometry"]["curvature_per_m"][0] = nextafter(
        fine["geometry"]["curvature_per_m"][0], float("inf")
    )
    _reseal_fused_consumer_report(report)
    after = consume(report)
    assert after["identity"] == before["identity"]
    assert after["observed"]["cases"][0] == before["observed"]["cases"][0]
    assert after["observed"]["cases"][1] != before["observed"]["cases"][1]


def test_fused_consumer_dual_grid_compares_fine_unknown_inputs() -> None:
    consume = _fused_consumer()
    report = _fused_consumer_report()
    before = consume(report)["identity"]["cases"]
    fine = report["recipient_fused_grid"]["cases"][1]
    fine["expected_inputs"]["settings"]["future_fine_key"] = {"must_compare": 42}
    _reseal_fused_consumer_report(report)
    after = consume(report)["identity"]["cases"]
    assert after[0] == before[0]
    assert after[1] != before[1]


@pytest.mark.parametrize(
    "fault",
    ["missing", "reversed", "extra", "duplicate", "count", "solver", "tolerance"],
)
def test_fused_consumer_dual_grid_rejects_incomplete_fine_evidence(fault: str) -> None:
    from copy import deepcopy

    report = _fused_consumer_report()
    cases = report["recipient_fused_grid"]["cases"]
    if fault == "missing":
        cases.pop()
    elif fault == "reversed":
        cases.reverse()
    elif fault == "extra":
        cases.append(deepcopy(cases[1]))
    elif fault == "duplicate":
        cases[1] = deepcopy(cases[0])
    elif fault == "count":
        cases[1]["replay"]["replayed_sample_count"] = 1977
    elif fault == "solver":
        cases[1]["expected_inputs"]["settings"]["solver"][
            "requested_maximum_cell_length_m"
        ] = 0.75
        _reseal_fused_consumer_report(report)
    elif fault == "tolerance":
        cases[1]["replay"]["metrics"][0]["tolerance"] = 0.02
    with pytest.raises(RuntimeError, match="Recipient fused-grid report is invalid"):
        _fused_consumer()(report)


@pytest.mark.parametrize("channel", ["distance_m", "x_m", "y_m", "curvature_per_m"])
def test_fused_consumer_dual_grid_rejects_resealed_fine_geometry(channel: str) -> None:
    report = _fused_consumer_report()
    report["recipient_fused_grid"]["cases"][1]["geometry"][channel][1] += 0.01
    _reseal_fused_consumer_report(report)
    with pytest.raises(RuntimeError, match="independent cell oracle"):
        _fused_consumer()(report)
