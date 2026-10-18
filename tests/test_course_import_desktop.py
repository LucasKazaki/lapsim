"""Desktop import of a versioned, numerically coherent course bundle."""

from __future__ import annotations

from dataclasses import replace
from math import pi
from pathlib import Path
import tkinter as tk
from unittest.mock import patch

import pytest

from lapsim.courses.course_bundle import CourseBundle, course_geometry_sha256
from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Track
from lapsim.experiments import RunRecord, replay_lap_record
from lapsim.ui.app import LapSimDesktop
from lapsim.ui.course_catalog import (
    SYNTHETIC_DEMO_COURSE_ID, load_course, load_imported_course_catalog,
)
from lapsim.ui.presets import VehicleSetup


def _bundle() -> CourseBundle:
    track = SpatialTrack.from_track(
        Track.from_segments([Curve(radius_m=10.0, span_rad=2.0 * pi)]),
        maximum_cell_length_m=2.0,
    )
    return CourseBundle.from_dict({
        "schema_version": 1,
        "course_id": "practice_circle",
        "revision": "r1",
        "label": "Practice circle",
        "description": "Synthetic import exercise for course provenance.",
        "source_kind": "synthetic",
        "provenance": {
            "source_name": "Analytic circle",
            "source_sha256": None,
            "processing_method": "Exact circular arcs",
            "review_note": "No measured course or boundaries",
        },
        "coordinate_frame": {
            "type": "local_cartesian_right_handed_xy",
            "units": "m",
            "origin": "Start",
            "x_axis": "east",
            "y_axis": "north",
        },
        "travel_direction": "counterclockwise",
        "boundary_status": "absent",
        "ai_defaults": {
            "width_source": "assumed_uniform",
            "half_width_m": 2.5,
            "vehicle_width_m": 1.8,
            "safety_margin_m": 0.2,
        },
        "geometry": {
            "model": "piecewise_constant_curvature_arcs",
            "closed": True,
            "distance_m": list(track.distance_m),
            "x_m": list(track.x_m),
            "y_m": list(track.y_m),
            "curvature_per_m": list(track.curvature_per_m),
        },
        "geometry_sha256": course_geometry_sha256(track),
    })


def _rounded_rectangle_bundle() -> CourseBundle:
    """A coherent imported course that exercises nonzero AI offset trials."""

    track = load_course(SYNTHETIC_DEMO_COURSE_ID)
    manifest = _bundle().to_dict()
    manifest["course_id"] = "practice_rounded_rectangle"
    manifest["label"] = "Imported rounded rectangle"
    manifest["description"] = "Analytic closed import for optional AI integration."
    manifest["provenance"]["source_name"] = "Analytic rounded rectangle"
    manifest["ai_defaults"]["half_width_m"] = 3.0
    manifest["geometry"] = {
        "model": "piecewise_constant_curvature_arcs",
        "closed": True,
        "distance_m": list(track.distance_m),
        "x_m": list(track.x_m),
        "y_m": list(track.y_m),
        "curvature_per_m": list(track.curvature_per_m),
    }
    manifest["geometry_sha256"] = course_geometry_sha256(track)
    return CourseBundle.from_dict(manifest)


def test_imported_course_runs_and_saves_source_identity(tmp_path: Path) -> None:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    try:
        app = LapSimDesktop(root)
        app._last_result = object()
        source_file = _bundle().save(tmp_path / "practice.json")
        expected = CourseBundle.load(source_file)
        run_dir = tmp_path / "runs"
        with patch("lapsim.ui.app.default_run_directory", return_value=run_dir):
            app._import_course_bundle(source_file)
            assert app.course_spec.course_id == "imported:practice_circle@r1"
            assert app._last_result is None
            assert app.track == expected.track
            assert app.course_var.get().startswith("Imported · Practice circle")
            assert "No measured boundaries" in app._course_notice_text()
            assert (run_dir.parent / "courses" / f"{expected.bundle_sha256}.json").exists()
            assert app._read_run_settings()[1] > 0.0

            app._calculate_single(
                "prius_2026_le", "Prius imported circle",
                VehicleSetup(torque_request_fraction=0.8), 1.0, 0.8,
            )
            kind, payload, error = app.result_queue.get_nowait()
            assert error is None, error
            assert kind == "single"
            assert payload[2].completed

        record_path = run_dir / f"{payload[3]}.json"
        record = RunRecord.load(record_path).to_dict()
        source = record["settings"]["track"]["source_course"]
        assert source["selected_course_id"] == "imported:practice_circle@r1"
        assert source["revision"] == "r1"
        assert source["bundle_sha256"] == expected.bundle_sha256
        assert source["source_geometry_sha256"] == expected.geometry_sha256
        assert source["boundary_status"] == "absent"
        assert record["settings"]["track"]["geometry_sha256"] != expected.geometry_sha256
        assert replay_lap_record(record_path).model_agreement

        changed = expected.to_dict()
        changed["description"] = "Different content under the same revision"
        changed_file = CourseBundle.from_dict(changed).save(tmp_path / "changed.json")
        with patch("lapsim.ui.app.default_run_directory", return_value=run_dir):
            with pytest.raises(ValueError, match="new revision"):
                app._import_course_bundle(changed_file)
    finally:
        root.destroy()


def test_imported_coherent_course_ai_trials_save_and_replay(
    tmp_path: Path,
) -> None:
    bundle = _rounded_rectangle_bundle()
    source_file = bundle.save(tmp_path / "source.json")
    run_dir = tmp_path / "runs"
    with patch("lapsim.ui.app.default_run_directory", return_value=run_dir):
        try:
            root = tk.Tk()
        except tk.TclError as error:
            pytest.skip(f"Tk display unavailable: {error}")
        root.withdraw()
        try:
            app = LapSimDesktop(root)
            app._import_course_bundle(source_file)
            assert app.driving_mode_var.get() == "Centerline (default)"
            assert app.track == bundle.track
            app._calculate_ai_single(
                "prius_2026_le", "Prius imported AI exercise",
                VehicleSetup(torque_request_fraction=0.8), 1.0, 0.8,
                (3.0, 1.8, 0.2),
            )
            kind, payload, error = app.result_queue.get_nowait()
            assert error is None, error
            assert kind == "ai_single"
            comparison = payload[5]
            assert comparison.rank_status == "candidate_selected"
            assert len(comparison.trials) == 3
            completed_trials = [
                trial for trial in comparison.trials
                if trial.run is not None and trial.run.completed
            ]
            skipped_trials = [
                trial for trial in comparison.trials if trial.run is None
            ]
            assert len(completed_trials) == 2
            assert len(skipped_trials) == 1
            assert skipped_trials[0].path_audit is not None
            assert not skipped_trials[0].path_audit.valid
            app._set_busy(True)
            app.result_queue.put((kind, payload, error))
            app._poll_result()
            assert app.driver_replay_menu is not None
            assert app.driver_replay_menu["state"] == "normal"

            primary_path = run_dir / f"{payload[7]}.json"
            primary = RunRecord.load(primary_path).to_dict()
            planning = primary["settings"]["path_planning"]
            source = primary["settings"]["track"]["source_course"]
            assert planning["trial_record_manifest_version"] == 1
            assert planning["selected_mode"] == "candidate"
            assert len(planning["candidate_trials"]) == 3
            assert source["selected_course_id"] == (
                "imported:practice_rounded_rectangle@r1"
            )
            assert source["bundle_sha256"] == bundle.bundle_sha256
            assert source["source_geometry_sha256"] == bundle.geometry_sha256
            assert len(list(run_dir.glob("*.json"))) == 3
            assert planning["baseline_record"]["run_id"] is not None
            assert sum(row["record_role"] == "selected_result"
                       for row in planning["candidate_trials"]) == 1
            for path in run_dir.glob("*.json"):
                record = RunRecord.load(path).to_dict()
                assert record["settings"]["track"]["source_course"] == source
                assert replay_lap_record(path).model_agreement
            for row in planning["candidate_trials"]:
                if row["record_role"] == "no_run":
                    assert row["run_id"] is None
                    assert row["model_run_completed"] is None
                    assert "Model run skipped" in row["error"]
                elif row["record_role"] != "selected_result":
                    assert (run_dir / f"{row['run_id']}.json").exists()
        finally:
            root.destroy()


def test_car_comparison_records_share_the_selected_source(tmp_path: Path) -> None:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    try:
        app = LapSimDesktop(root)
        app._select_course(app.course_options[1].label)
        setup_a = VehicleSetup(torque_request_fraction=0.8)
        setup_b = replace(setup_a, mass_kg=setup_a.mass_kg + 25.0)
        with patch("lapsim.ui.app.default_run_directory", return_value=tmp_path):
            app._calculate_comparison((
                ("user:car_a", "Car A", setup_a),
                ("user:car_b", "Car B", setup_b),
            ), 5.0, 0.8)
        kind, payload, error = app.result_queue.get_nowait()
        assert error is None, error
        assert kind == "comparison"
        source_a = RunRecord.load(tmp_path / f"{payload[3][0]}.json").to_dict()[
            "settings"
        ]["track"]["source_course"]
        source_b = RunRecord.load(tmp_path / f"{payload[3][1]}.json").to_dict()[
            "settings"
        ]["track"]["source_course"]
        assert source_a == source_b
        assert source_a["selected_course_id"] == app.course_spec.course_id
        assert source_a["source_kind"] == "synthetic"
    finally:
        root.destroy()


def test_imported_course_survives_restart_and_rejects_revision_reuse(
    tmp_path: Path,
) -> None:
    source_file = _bundle().save(tmp_path / "source.json")
    run_dir = tmp_path / "local" / "runs"
    with patch("lapsim.ui.app.default_run_directory", return_value=run_dir):
        first_root = tk.Tk()
        first_root.withdraw()
        try:
            first = LapSimDesktop(first_root)
            first._import_course_bundle(source_file)
            selected_id = first.course_spec.course_id
            bundle_hash = first.imported_courses[selected_id].bundle_sha256
        finally:
            first_root.destroy()

        second_root = tk.Tk()
        second_root.withdraw()
        try:
            second = LapSimDesktop(second_root)
            assert second.course_spec.course_id != selected_id
            assert selected_id in second.imported_courses
            assert second.imported_courses[selected_id].bundle_sha256 == bundle_hash
            second._select_course(next(
                option.label for option in second.course_options
                if option.course_id == selected_id
            ))
            assert second.course_spec.course_id == selected_id
            changed = _bundle().to_dict()
            changed["description"] = "Different content under the same revision"
            changed_file = CourseBundle.from_dict(changed).save(
                tmp_path / "changed-revision.json"
            )
            with pytest.raises(ValueError, match="new revision"):
                second._import_course_bundle(changed_file)
        finally:
            second_root.destroy()


def test_saved_catalog_skips_tampered_and_conflicting_files(tmp_path: Path) -> None:
    bundle = _bundle()
    bundle.save(tmp_path / f"{bundle.bundle_sha256}.json")
    (tmp_path / ("0" * 64 + ".json")).write_text("{}", encoding="utf-8")
    changed = bundle.to_dict()
    changed["description"] = "Conflicting same ID and revision"
    conflict = CourseBundle.from_dict(changed)
    conflict.save(tmp_path / f"{conflict.bundle_sha256}.json")
    catalog, warnings = load_imported_course_catalog(tmp_path)
    assert catalog[f"imported:{bundle.catalog_id}"].bundle_sha256 in {
        bundle.bundle_sha256, conflict.bundle_sha256,
    }
    assert any("conflicts" in warning for warning in warnings)

    saved = tmp_path / f"{bundle.bundle_sha256}.json"
    saved.write_text("{}", encoding="utf-8")
    catalog, warnings = load_imported_course_catalog(tmp_path)
    assert not catalog or catalog[f"imported:{bundle.catalog_id}"].bundle_sha256 == conflict.bundle_sha256
    assert any("bundle" in warning for warning in warnings)


def test_ordinary_run_button_finishes_async_and_replays_imported_grid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise real worker/polling; the withdrawn root is not a render check."""
    from hashlib import sha256
    from itertools import pairwise
    import json
    from math import cos, isfinite, sin
    import threading
    import traceback
    from typing import Any

    from lapsim.experiments import LapRunSettings, default_run_directory
    from lapsim.profiles import build_vehicle, snapshot_vehicle_config
    import lapsim.ui.app as app_module
    from lapsim.ui.course_catalog import solver_track_for_course
    from lapsim.ui.simulation import (
        apply_uniform_road_grip,
        endurance_run_config,
        path_solver_settings,
    )

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    run_directory = default_run_directory()
    assert run_directory.resolve().is_relative_to(tmp_path.resolve())
    assert not list(run_directory.glob("*.json"))
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    owner_thread = threading.get_ident()
    worker_threads: list[threading.Thread] = []
    worker_events: list[tuple[str, int]] = []
    callback_errors: list[str] = []
    dialog_errors: list[tuple[str, str]] = []
    observer_threads: set[int] = set()
    timed_out = False
    run_attempted = False
    cleanup_requested = False
    original_worker = LapSimDesktop._calculate_single

    def observe_worker(
        self: LapSimDesktop,
        profile_id: str,
        profile_name: str,
        setup: VehicleSetup | None,
        step_m: float,
        torque_fraction: float,
        road_grip_multiplier: float = 1.0,
    ) -> None:
        worker_threads.append(threading.current_thread())
        worker_events.append(("entry", threading.get_ident()))
        try:
            return original_worker(
                self,
                profile_id,
                profile_name,
                setup,
                step_m,
                torque_fraction,
                road_grip_multiplier,
            )
        finally:
            worker_events.append(("exit", threading.get_ident()))

    def callback_failed(
        exception_type: type[BaseException],
        error: BaseException,
        trace: Any,
    ) -> None:
        callback_errors.append(
            "".join(traceback.format_exception(exception_type, error, trace))
        )

    def observe_error(
        title: str,
        message: str,
        *_args: Any,
        **_kwargs: Any,
    ) -> None:
        # Test-only observation prevents modal hangs; no native-dialog claim.
        dialog_errors.append((title, str(message)))

    def observe_terminal() -> None:
        observer_threads.add(threading.get_ident())
        finished = bool(worker_threads) and all(
            not thread.is_alive() for thread in worker_threads
        )
        if (
            finished
            and (
                not app.run_in_progress
                or timed_out
                or callback_errors
                or cleanup_requested
            )
        ) or ((timed_out or callback_errors) and not run_attempted):
            root.quit()
        else:
            root.after(10, observe_terminal)

    monkeypatch.setattr(root, "report_callback_exception", callback_failed)
    monkeypatch.setattr(app_module.messagebox, "showerror", observe_error)
    try:
        app = LapSimDesktop(root)
        assert app.profile_store.path.resolve().is_relative_to(tmp_path.resolve())
        source_file = _bundle().save(tmp_path / "async-circle.json")
        source_before = (source_file.read_bytes(), source_file.stat().st_mtime_ns)
        bundle = CourseBundle.load(source_file)
        source_track = bundle.track
        assert source_track.cell_count == 32
        assert source_track.curvature_per_m == (0.1,) * 32
        assert source_track.length_m == pytest.approx(20.0 * pi, rel=0, abs=1e-12)
        for station, x_m, y_m in zip(
            source_track.distance_m,
            source_track.x_m,
            source_track.y_m,
            strict=True,
        ):
            assert x_m == pytest.approx(
                10.0 * sin(station / 10.0),
                rel=0,
                abs=1e-12,
            )
            assert y_m == pytest.approx(
                10.0 * (1.0 - cos(station / 10.0)),
                rel=0,
                abs=1e-12,
            )

        app._import_course_bundle(source_file)
        app._select_profile("repository_baseline")
        app.driving_mode_var.set("Centerline (default)")
        app.inputs["solver_step_m"].set("0.5")
        app.inputs["torque_request_percent"].set("80")
        app.inputs["road_grip_percent"].set("100")
        pre_run_inputs = app._read_run_inputs()
        pre_run_grip = app._read_road_grip_multiplier()
        assert pre_run_inputs == (None, 0.5, 0.8)
        assert pre_run_grip == 1.0
        assert app.course_spec.course_id == "imported:practice_circle@r1"
        assert not app._displayed_run_records and not app.run_in_progress
        source_metadata = json.loads(app.course_source_json)

        # Four subarcs per declared source cell, with every source end retained.
        stations = [source_track.distance_m[0]]
        for lower, upper in zip(
            source_track.distance_m[:-1],
            source_track.distance_m[1:],
            strict=True,
        ):
            stations.extend(
                lower + fraction * (upper - lower) for fraction in (0.25, 0.5, 0.75)
            )
            stations.append(upper)

        def check_geometry(geometry: dict[str, Any]) -> None:
            assert geometry["closed"] is True
            assert geometry["distance_m"] == stations and len(stations) == 129
            assert geometry["curvature_per_m"] == [0.1] * 128
            assert all(
                0.0 < upper - lower <= 0.5 for lower, upper in pairwise(stations)
            )
            for key, source_values in (
                ("distance_m", source_track.distance_m),
                ("x_m", source_track.x_m),
                ("y_m", source_track.y_m),
            ):
                assert len(geometry[key]) == 129
                assert geometry[key][::4] == list(source_values)
            for station, x_m, y_m in zip(
                stations,
                geometry["x_m"],
                geometry["y_m"],
                strict=True,
            ):
                assert x_m == pytest.approx(
                    10.0 * sin(station / 10.0),
                    rel=0,
                    abs=1e-12,
                )
                assert y_m == pytest.approx(
                    10.0 * (1.0 - cos(station / 10.0)),
                    rel=0,
                    abs=1e-12,
                )

        expected_track = solver_track_for_course(
            app.course_spec.course_id,
            source_track,
            0.5,
        )
        vehicle, profile = build_vehicle("repository_baseline")
        apply_uniform_road_grip(vehicle, 1.0)
        settings = LapRunSettings.from_track(
            expected_track,
            track_id=app.course_spec.course_id,
            solver_step_m=0.5,
            solver_settings=path_solver_settings(vehicle),
            torque_request_fraction=0.8,
            road_grip_multiplier=1.0,
            endurance_config=endurance_run_config(vehicle),
            profile_id="repository_baseline",
            profile_label=app.profile_id_to_display["repository_baseline"],
            source_course=source_metadata,
        ).to_dict()
        check_geometry(settings["track"]["geometry"])
        expected_inputs = json.loads(
            json.dumps(
                {
                    "settings": settings,
                    "effective_vehicle_config": snapshot_vehicle_config(vehicle),
                    "base_vehicle_config": profile.to_dict()["model_config"],
                    "selected_profile_id": "repository_baseline",
                },
                allow_nan=False,
            )
        )
        expected_hash = sha256(
            json.dumps(
                expected_inputs,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()

        def deadline() -> None:
            nonlocal timed_out
            timed_out = True
            # Do not cancel/join the model or retire its storage while it runs.
            if not run_attempted or (
                worker_threads
                and all(not thread.is_alive() for thread in worker_threads)
            ):
                root.quit()

        monkeypatch.setattr(LapSimDesktop, "_calculate_single", observe_worker)
        root.after(60_000, deadline)
        run_attempted = True
        app.run_button.invoke()
        assert app.run_in_progress
        assert app.run_button.cget("state") == "disabled"
        assert app.entry_by_key["solver_step_m"].cget("state") == "disabled"
        assert app.course_menu is not None
        assert app.course_menu.cget("state") == "disabled"
        root.after(0, observe_terminal)
        root.mainloop()

        assert not timed_out, (
            "Ordinary asynchronous Run exceeded its diagnostic deadline"
        )
        assert not callback_errors, callback_errors
        assert not dialog_errors, dialog_errors
        assert observer_threads == {owner_thread}
        assert len(worker_threads) == 1 and not worker_threads[0].is_alive()
        worker_id = worker_threads[0].ident
        assert worker_id is not None and worker_id != owner_thread
        assert worker_events == [("entry", worker_id), ("exit", worker_id)]
        assert not app.run_in_progress and app.run_button.cget("state") == "normal"
        assert app._calculation_progress_mode == "complete"
        assert app._calculation_progress_fraction == 1.0
        assert app._last_result is not None and app._last_result.completed
        assert app.driver_playback is not None
        assert app.driver_playback.track == expected_track
        assert app.saved_runs_button is not None
        assert app.saved_runs_button.cget("state") == "normal"
        ((label, run_id),) = app._displayed_run_records
        assert label == "Lap result" and len(run_id) == 64
        assert set(run_directory.glob("*.json")) == {run_directory / f"{run_id}.json"}

        saved = run_directory / f"{run_id}.json"
        saved_before = (saved.read_bytes(), saved.stat().st_mtime_ns)
        record = RunRecord.load(saved)
        document = record.to_dict()
        assert record.run_id == run_id
        check_geometry(document["settings"]["track"]["geometry"])
        recorded_inputs = {
            "settings": document["settings"],
            "effective_vehicle_config": document["configuration"][
                "effective_vehicle_config"
            ],
            "base_vehicle_config": document["configuration"]["base_profile_manifest"][
                "model_config"
            ],
            "selected_profile_id": document["configuration"]["selected_profile_id"],
        }
        assert recorded_inputs == expected_inputs
        assert (
            sha256(
                json.dumps(
                    recorded_inputs,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode()
            ).hexdigest()
            == expected_hash
        )
        assert document["settings"]["track"]["source_course"] == source_metadata
        assert document["result"]["starting_speed_mps"] == (
            app._last_result.starting_speed_mps
        )
        assert document["settings"]["endurance_config"]["starting_speed_mps"] is None
        replay = replay_lap_record(saved).to_dict()
        assert replay["run_id"] == run_id
        assert replay["model_agreement"] is True and replay["replay_completed"] is True
        assert replay["recorded_sample_count"] == replay["replayed_sample_count"] == 128
        assert not replay["mismatch_reasons"]
        tolerances = {
            "driving_time_s": 0.01,
            "lap_time_s": 0.01,
            "starting_speed_mps": 0.01,
            "ending_speed_mps": 0.01,
            "pack_energy_kwh": 1e-5,
            "final_state_of_charge": 1e-5,
            "sample_time_s": 0.01,
            "sample_distance_m": 1e-8,
            "speed_trace_mps": 0.01,
            "path_speed_ceiling_mps": 0.01,
            "controls.motor_torque_request_nm": 0.0,
            "controls.front_brake_pressure_psi": 0.0,
            "controls.rear_brake_pressure_psi": 0.0,
            "controls.rear_regenerative_brake_force_request_n": 0.0,
            "controls.steering_angle_rad": 0.0,
            "controls.front_regenerative_brake_force_request_n": 0.0,
            "tire.road_grip_multiplier": 0.0,
        }
        assert len(replay["metrics"]) == 17
        assert {metric["name"] for metric in replay["metrics"]} == set(tolerances)
        for metric in replay["metrics"]:
            assert metric["passed"] is True
            assert metric["tolerance"] == tolerances[metric["name"]]
            for value in (metric["maximum_absolute_error"], metric["tolerance"]):
                assert isinstance(value, (float, int)) and not isinstance(value, bool)
                assert isfinite(value) and value >= 0.0
            assert metric["maximum_absolute_error"] <= metric["tolerance"]
        # Provenance warnings remain truthful; they are not numerical failures.
        assert all(
            isinstance(warning, str) for warning in replay["provenance_warnings"]
        )
        assert (saved.read_bytes(), saved.stat().st_mtime_ns) == saved_before
        assert (
            source_file.read_bytes(),
            source_file.stat().st_mtime_ns,
        ) == source_before
    finally:
        cleanup_requested = True
        # Invocation may have started a thread whose delegate has not entered.
        # Only an observed exit proves it is safe to retire Tk and storage.
        while run_attempted and (
            not worker_threads or any(thread.is_alive() for thread in worker_threads)
        ):
            root.after(0, observe_terminal)
            root.mainloop()
        assert not run_attempted or (
            worker_threads and all(not thread.is_alive() for thread in worker_threads)
        )
        root.destroy()
