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
    app: LapSimDesktop, tmp_path: Path,
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
            geometry["distance_m"], geometry["x_m"], geometry["y_m"], strict=True,
        ):
            assert x == pytest.approx(10.0 * sin(distance / 10.0), rel=0.0, abs=1e-12)
            assert y == pytest.approx(10.0 * (1.0 - cos(distance / 10.0)), rel=0.0, abs=1e-12)
        assert row["expected_inputs_sha256"] == row["recorded_inputs_sha256"]
        expected = row["expected_inputs"]
        assert expected["settings"]["profile_id"] == "repository_baseline"
        assert expected["settings"]["driver"] == {"torque_request_fraction": 0.8}
        assert expected["settings"]["conditions"]["road_grip_multiplier"] == 1.0
        assert expected["settings"]["solver"]["path_constraint_settings"]["maximum_passes"] == 120
        assert expected["settings"]["endurance_config"]["starting_speed_mps"] is None
        record_path = default_run_directory() / f"{row['record_run_id']}.json"
        raw = record_path.read_bytes()
        assert len(raw) == row["record_bytes"]
        assert sha256(raw).hexdigest() == row["record_sha256"]
        loaded = RunRecord.load(record_path).to_dict()
        assert loaded["settings"]["track"]["geometry"] == geometry
        assert loaded["settings"]["track"]["source_course"]["bundle_sha256"] == report["fixture"]["bundle_sha256"]
        assert loaded["configuration"]["effective_vehicle_config"] == expected["effective_vehicle_config"]
        assert row["record_unchanged"] is True
        assert row["replay"]["model_agreement"] is True
        assert row["replay"]["replay_completed"] is True
    assert cases[0]["geometry_sha256"] != cases[1]["geometry_sha256"]
    assert cases[0]["expected_inputs_sha256"] != cases[1]["expected_inputs_sha256"]


def test_recipient_self_test_rejects_generic_resampler(
    app: LapSimDesktop, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "lapsim.ui.app.solver_track_for_course",
        lambda _course, track, step: resample_track(track, step),
    )
    with pytest.raises(RuntimeError, match="Recipient grid cell count or curvature is incorrect"):
        desktop._check_imported_course_grid(app, tmp_path / "wrong-grid")


def test_recipient_self_test_rejects_different_effective_profile(
    app: LapSimDesktop, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        app, "_vehicle_for_profile", lambda *_args: build_vehicle("prius_2026_le"),
    )
    with pytest.raises(RuntimeError, match="inputs|configuration|profile"):
        desktop._check_imported_course_grid(app, tmp_path / "wrong-profile")


@pytest.mark.parametrize("raise_inside", [False, True])
def test_self_test_user_storage_restores_environment_and_existing_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raise_inside: bool,
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
    tmp_path: Path, artifact_kind: str,
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
    assert 10 <= leaf_length and leaf_length + 37 <= 255
    destination = parent / ("s" * (leaf_length - len(".json")) + ".json")
    assert len(str(destination)) == 245
    assert not str(destination).startswith("\\\\?\\")
    prospective_temporary = destination.with_name(
        f"{destination.name}.{'0' * 32}.tmp"
    )
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
