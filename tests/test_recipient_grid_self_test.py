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
from lapsim.courses.solver_grid import resample_track
from lapsim.experiments import RunRecord, default_run_directory
from lapsim.profiles import build_vehicle
from lapsim.ui.app import LapSimDesktop


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
    with pytest.raises(RuntimeError, match="grid|cell"):
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
