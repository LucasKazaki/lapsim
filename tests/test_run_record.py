"""Synthetic evidence and replay checks for saved lap records."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from importlib.metadata import version as distribution_version
import json
from math import nan
from pathlib import Path
import platform
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from lapsim.core.telemetry import Telemetry
from lapsim.courses.spatial_track import SpatialTrack
from lapsim.events.endurance import EnduranceRunConfig, EnduranceRunResult
from lapsim.experiments import LapRunSettings, RunRecord, capture_lap_run
from lapsim.experiments.run_record import RUN_RECORD_SCHEMA_VERSION
from lapsim.profiles import build_vehicle


class RunRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.vehicle, self.manifest = build_vehicle("repository_baseline")
        self.track = SpatialTrack(
            distance_m=(0.0, 1.0, 2.0),
            x_m=(0.0, 1.0, 0.0),
            y_m=(0.0, 0.0, 0.0),
            curvature_per_m=(0.0, 0.0),
            closed=True,
        )
        self.settings = LapRunSettings.from_track(
            self.track,
            track_id="synthetic_loop",
            solver_step_m=1.0,
            solver_settings={"convergence_tolerance_mps": 0.005, "maximum_passes": 120},
            torque_request_fraction=0.8,
            endurance_config=EnduranceRunConfig(laps=1),
            profile_id="synthetic_saved_setup",
            profile_label="Synthetic baseline",
        )

    def _result(self, telemetry: Telemetry | None = None) -> EnduranceRunResult:
        return EnduranceRunResult(
            completed_laps=1,
            driving_time_s=1.5,
            lap_times_s=(1.5,),
            pack_energy_kwh=0.002,
            final_state_of_charge=0.9,
            failure_reason=None,
            telemetry=telemetry,
        )

    def _telemetry(self) -> Telemetry:
        return Telemetry({
            "vehicle.time_s": (0.5, 1.5),
            "vehicle.distance_m": (1.0, 2.0),
            "vehicle.speed_mps": (2.0, 3.0),
            "controls.motor_torque_request_nm": (0.0, 10.0),
            "component.late_value_w": (nan, 5.0),
        })

    @staticmethod
    def _write_payload(path: Path, payload: dict) -> None:
        content = dict(payload)
        content.pop("run_id", None)
        canonical = json.dumps(
            content, sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
        content["run_id"] = sha256(canonical.encode("utf-8")).hexdigest()
        path.write_text(json.dumps(content, allow_nan=False), encoding="utf-8")

    def test_record_is_deterministic_detached_and_round_trips(self) -> None:
        record = capture_lap_run(
            self._result(self._telemetry()), self.manifest, self.settings,
            actual_vehicle=self.vehicle,
        )
        self.assertEqual(
            record.run_id,
            capture_lap_run(
                self._result(self._telemetry()), self.manifest, self.settings,
                actual_vehicle=self.vehicle,
            ).run_id,
        )
        original_mass = record.to_dict()["configuration"]["effective_vehicle_config"]["fields"]["mass_kg"]
        self.vehicle.mass_kg += 10.0
        changed_copy = record.to_dict()
        changed_copy["configuration"]["effective_vehicle_config"]["fields"]["mass_kg"] = 0.0
        self.assertEqual(
            record.to_dict()["configuration"]["effective_vehicle_config"]["fields"]["mass_kg"],
            original_mass,
        )
        with TemporaryDirectory() as directory:
            path = record.save(Path(directory) / "lap.json")
            self.assertEqual(record.to_dict(), RunRecord.load(path).to_dict())
            self.assertEqual(record.run_id, RunRecord.load(path).run_id)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("NaN", text)
            self.assertIn('"run_id"', text)

    def test_assumed_grip_is_separate_from_source_profile_and_recorded(self) -> None:
        self.vehicle.tire.road_grip_multiplier = 0.7
        settings = LapRunSettings.from_track(
            self.track, track_id="synthetic_loop", solver_step_m=1.0,
            solver_settings={"maximum_passes": 120},
            torque_request_fraction=0.8,
            endurance_config=EnduranceRunConfig(laps=1),
            road_grip_multiplier=0.7,
        )
        payload = capture_lap_run(
            self._result(), self.manifest, settings, actual_vehicle=self.vehicle,
        ).to_dict()
        self.assertEqual(payload["settings"]["conditions"], {
            "road_grip_multiplier": 0.7,
            "source": "assumed_uniform_surface_sensitivity",
        })
        self.assertIsNone(payload["configuration"]["user_overrides"])
        self.assertTrue(payload["configuration"]["effective_config_differs_from_base"])
        self.assertFalse(payload["configuration"]["profile_fields_differ_from_base"])
        self.assertEqual(
            payload["configuration"]["base_profile_manifest"]["model_config"]
            ["fields"]["tire"]["fields"]["road_grip_multiplier"], 1.0,
        )
        self.assertEqual(
            payload["configuration"]["effective_vehicle_config"]
            ["fields"]["tire"]["fields"]["road_grip_multiplier"], 0.7,
        )
        with self.assertRaisesRegex(ValueError, "road grip disagrees"):
            capture_lap_run(
                self._result(), self.manifest, self.settings,
                actual_vehicle=self.vehicle,
            )

    def test_assumed_grip_setting_rejects_invalid_factor(self) -> None:
        for invalid in (False, "bad", 0.0, -1.0, float("nan"), float("inf")):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                ValueError, "road_grip_multiplier"
            ):
                LapRunSettings.from_track(
                    self.track, track_id="synthetic_loop", solver_step_m=1.0,
                    solver_settings={"maximum_passes": 120},
                    torque_request_fraction=0.8,
                    endurance_config=EnduranceRunConfig(laps=1),
                    road_grip_multiplier=invalid,
                )

    def test_cell_grip_settings_are_absolute_grid_aligned_and_frozen(self) -> None:
        schedule = (0.9, 0.7)
        settings = LapRunSettings.from_track(
            self.track, track_id="synthetic_loop", solver_step_m=1.0,
            solver_settings={"maximum_passes": 120},
            torque_request_fraction=0.8,
            endurance_config=EnduranceRunConfig(laps=1),
            road_grip_multiplier=0.85,
            cell_road_grip_multiplier=schedule,
        )
        saved = settings.to_dict()["conditions"]
        self.assertEqual(saved, {
            "road_grip_multiplier": 0.85,
            "source": "assumed_cellwise_surface_sensitivity",
            "cell_road_grip_multiplier": [0.9, 0.7],
        })
        saved["cell_road_grip_multiplier"][0] = 0.1
        self.assertEqual(
            settings.to_dict()["conditions"]["cell_road_grip_multiplier"],
            [0.9, 0.7],
        )

        for invalid in (
            [0.9, 0.7], (0.9,), (0.9, 0.7, 1.0),
            (True, 0.7), (0.0, 0.7), (-1.0, 0.7),
            (float("nan"), 0.7), (float("inf"), 0.7),
        ):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                ValueError, "cell road grip",
            ):
                LapRunSettings.from_track(
                    self.track, track_id="synthetic_loop", solver_step_m=1.0,
                    solver_settings={"maximum_passes": 120},
                    torque_request_fraction=0.8,
                    endurance_config=EnduranceRunConfig(laps=1),
                    cell_road_grip_multiplier=invalid,
                )

    def test_scheduled_completed_record_requires_full_grip_trace(self) -> None:
        settings = LapRunSettings.from_track(
            self.track, track_id="synthetic_loop", solver_step_m=1.0,
            solver_settings={"maximum_passes": 120},
            torque_request_fraction=0.8,
            endurance_config=EnduranceRunConfig(laps=1),
            cell_road_grip_multiplier=(0.9, 0.7),
        )
        with self.assertRaisesRegex(ValueError, "one grip sample per cell"):
            capture_lap_run(
                self._result(), self.manifest, settings,
                actual_vehicle=self.vehicle,
            )

    def test_scheduled_failed_record_checks_only_accepted_grip_prefix(self) -> None:
        settings = LapRunSettings.from_track(
            self.track, track_id="synthetic_loop", solver_step_m=1.0,
            solver_settings={"maximum_passes": 120},
            torque_request_fraction=0.8,
            endurance_config=EnduranceRunConfig(laps=1),
            cell_road_grip_multiplier=(0.9, 0.7),
        )

        def failed_result(grip: float) -> EnduranceRunResult:
            return EnduranceRunResult(
                completed_laps=0, driving_time_s=0.5, lap_times_s=(),
                pack_energy_kwh=0.001, final_state_of_charge=0.9,
                failure_reason="second cell rejected",
                telemetry=Telemetry({
                    "vehicle.time_s": (0.5,),
                    "vehicle.distance_m": (1.0,),
                    "tire.road_grip_multiplier": (grip,),
                }),
            )

        saved = capture_lap_run(
            failed_result(0.9), self.manifest, settings,
            actual_vehicle=self.vehicle,
        ).to_dict()
        self.assertEqual(saved["result"]["status"], "failed")
        self.assertEqual(saved["telemetry"]["sample_count"], 1)
        with self.assertRaisesRegex(ValueError, "saved tire grip telemetry disagrees"):
            capture_lap_run(
                failed_result(0.8), self.manifest, settings,
                actual_vehicle=self.vehicle,
            )

    def test_load_rejects_duplicate_keys_and_oversized_input(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "lap.json"
            path.write_text('{"schema_version":2,"schema_version":2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                RunRecord.load(path)
            path.write_bytes(b" " * 65)
            with patch("lapsim.experiments.run_record._MAX_RUN_RECORD_BYTES", 64):
                with self.assertRaisesRegex(ValueError, "file cap"):
                    RunRecord.load(path)
                record = capture_lap_run(
                    self._result(), self.manifest, self.settings,
                    actual_vehicle=self.vehicle,
                )
                with self.assertRaisesRegex(ValueError, "file cap"):
                    record.save(path)

    def test_measured_seam_speeds_are_in_the_saved_result(self) -> None:
        observed = replace(
            self._result(self._telemetry()),
            starting_speed_mps=4.0,
            ending_speed_mps=3.0,
        )
        record = capture_lap_run(
            observed, self.manifest, self.settings,
            actual_vehicle=self.vehicle,
        )
        saved = record.to_dict()["result"]
        self.assertEqual(saved["starting_speed_mps"], 4.0)
        self.assertEqual(saved["ending_speed_mps"], 3.0)
        self.assertEqual(saved["seam_speed_delta_mps"], -1.0)

        legacy = capture_lap_run(
            self._result(self._telemetry()), self.manifest, self.settings,
            actual_vehicle=self.vehicle,
        ).to_dict()["result"]
        self.assertNotIn("seam_speed_delta_mps", legacy)

    def test_v2_embeds_exact_solver_grid_and_resolved_runtime(self) -> None:
        record = capture_lap_run(
            self._result(self._telemetry()), self.manifest, self.settings,
            actual_vehicle=self.vehicle,
        )
        payload = record.to_dict()
        self.assertEqual(payload["schema_version"], RUN_RECORD_SCHEMA_VERSION)
        track = payload["settings"]["track"]
        self.assertEqual(track["geometry"], {
            "closed": self.track.closed,
            "distance_m": list(self.track.distance_m),
            "x_m": list(self.track.x_m),
            "y_m": list(self.track.y_m),
            "curvature_per_m": list(self.track.curvature_per_m),
        })
        runtime = payload["runtime"]
        self.assertEqual(runtime["python"]["version"], platform.python_version())
        self.assertEqual(runtime["python"]["implementation"], platform.python_implementation())
        for dependency in ("numpy", "scipy", "matplotlib"):
            self.assertEqual(
                runtime["dependencies"][dependency], distribution_version(dependency),
            )

    def test_optional_path_planning_assumptions_round_trip(self) -> None:
        planning = {
            "mode": "experimental_racing_line",
            "corridor": {"assumed_half_width_m": 3.0, "measured": False},
            "candidate_count": 12,
        }
        settings = LapRunSettings.from_track(
            self.track,
            track_id="synthetic_loop",
            solver_step_m=1.0,
            solver_settings={"maximum_passes": 120},
            torque_request_fraction=0.8,
            endurance_config=EnduranceRunConfig(laps=1),
            path_planning=planning,
        )
        planning["corridor"]["assumed_half_width_m"] = 9.0
        self.assertEqual(
            settings.to_dict()["path_planning"]["corridor"]["assumed_half_width_m"],
            3.0,
        )
        record = capture_lap_run(
            self._result(self._telemetry()), self.manifest, settings,
            actual_vehicle=self.vehicle,
        )
        with TemporaryDirectory() as directory:
            path = record.save(Path(directory) / "planned.json")
            self.assertEqual(
                RunRecord.load(path).to_dict()["settings"]["path_planning"]["mode"],
                "experimental_racing_line",
            )
        with self.assertRaisesRegex(ValueError, "finite JSON"):
            LapRunSettings.from_track(
                self.track,
                track_id="synthetic_loop",
                solver_step_m=1.0,
                solver_settings={"maximum_passes": 120},
                torque_request_fraction=0.8,
                endurance_config=EnduranceRunConfig(laps=1),
                path_planning={"bad": float("nan")},
            )

    def test_optional_source_course_round_trip_and_content_hash(self) -> None:
        source = {
            "bundle_id": "team_endurance_fused_gnss_imu",
            "bundle_version": "1",
            "bundle_sha256": "a" * 64,
            "source_geometry_sha256": "b" * 64,
            "hash_scope": "source course bundle files",
            "provenance": {"synthetic": False},
        }
        settings = LapRunSettings.from_track(
            self.track,
            track_id="synthetic_loop",
            solver_step_m=1.0,
            solver_settings={"maximum_passes": 120},
            torque_request_fraction=0.8,
            endurance_config=EnduranceRunConfig(laps=1),
            source_course=source,
        )
        source["provenance"]["synthetic"] = True
        self.assertFalse(
            settings.to_dict()["track"]["source_course"]["provenance"]["synthetic"]
        )
        record = capture_lap_run(
            self._result(self._telemetry()), self.manifest, settings,
            actual_vehicle=self.vehicle,
        )
        with TemporaryDirectory() as directory:
            path = record.save(Path(directory) / "source.json")
            self.assertEqual(
                RunRecord.load(path).to_dict()["settings"]["track"]["source_course"],
                settings.to_dict()["track"]["source_course"],
            )
            altered = record.to_dict()
            altered["settings"]["track"]["source_course"]["bundle_version"] = "2"
            path.write_text(json.dumps(altered, allow_nan=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "content hash does not match"):
                RunRecord.load(path)

        changed = LapRunSettings.from_track(
            self.track,
            track_id="synthetic_loop",
            solver_step_m=1.0,
            solver_settings={"maximum_passes": 120},
            torque_request_fraction=0.8,
            endurance_config=EnduranceRunConfig(laps=1),
            source_course={**source, "bundle_version": "2"},
        )
        changed_record = capture_lap_run(
            self._result(self._telemetry()), self.manifest, changed,
            actual_vehicle=self.vehicle,
        )
        self.assertNotEqual(record.run_id, changed_record.run_id)

        for invalid in ({}, {"bundle_sha256": float("nan")}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                LapRunSettings.from_track(
                    self.track,
                    track_id="synthetic_loop",
                    solver_step_m=1.0,
                    solver_settings={"maximum_passes": 120},
                    torque_request_fraction=0.8,
                    endurance_config=EnduranceRunConfig(laps=1),
                    source_course=invalid,
                )

    def test_load_accepts_an_intact_legacy_v1_record(self) -> None:
        record = capture_lap_run(
            self._result(self._telemetry()), self.manifest, self.settings,
            actual_vehicle=self.vehicle,
        )
        legacy = record.to_dict()
        legacy["schema_version"] = 1
        legacy.pop("runtime")
        legacy["settings"]["track"].pop("geometry")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.json"
            self._write_payload(path, legacy)
            loaded = RunRecord.load(path)
        self.assertEqual(loaded.to_dict()["schema_version"], 1)
        self.assertNotIn("geometry", loaded.to_dict()["settings"]["track"])

    def test_load_rejects_embedded_grid_or_hash_tampering_even_with_new_record_id(self) -> None:
        record = capture_lap_run(
            self._result(self._telemetry()), self.manifest, self.settings,
            actual_vehicle=self.vehicle,
        )
        for mutation in ("geometry", "geometry_sha256", "length_m", "cell_count"):
            with self.subTest(mutation=mutation), TemporaryDirectory() as directory:
                payload = record.to_dict()
                track = payload["settings"]["track"]
                if mutation == "geometry":
                    track["geometry"]["x_m"][1] += 0.1
                elif mutation == "geometry_sha256":
                    track["geometry_sha256"] = "0" * 64
                elif mutation == "length_m":
                    track["length_m"] += 0.1
                else:
                    track["cell_count"] += 1
                path = Path(directory) / "tampered.json"
                self._write_payload(path, payload)
                with self.assertRaisesRegex(ValueError, "embedded track geometry"):
                    RunRecord.load(path)

    def test_missing_optional_sample_keeps_alignment_and_unit_metadata(self) -> None:
        record = capture_lap_run(
            self._result(self._telemetry()), self.manifest, self.settings,
            actual_vehicle=self.vehicle,
        )
        trace = record.to_dict()["telemetry"]
        self.assertEqual(trace["sample_time_s"], [0.5, 1.5])
        self.assertEqual(trace["sample_distance_m"], [1.0, 2.0])
        self.assertEqual(trace["channels"]["component.late_value_w"]["values"], [None, 5.0])
        self.assertEqual(trace["channels"]["component.late_value_w"]["validity"], "missing_samples")
        self.assertEqual(trace["channels"]["controls.motor_torque_request_nm"]["unit"], "N*m")
        self.assertEqual(trace["channels"]["controls.motor_torque_request_nm"]["origin"], "driver_command")

    def test_edited_vehicle_must_be_disclosed_as_effective_configuration(self) -> None:
        self.vehicle.mass_kg += 10.0
        with self.assertRaisesRegex(ValueError, "user_overrides"):
            capture_lap_run(self._result(), self.manifest, self.settings, actual_vehicle=self.vehicle)
        record = capture_lap_run(
            self._result(), self.manifest, self.settings,
            actual_vehicle=self.vehicle, user_overrides={"mass_kg": self.vehicle.mass_kg},
        )
        config = record.to_dict()["configuration"]
        self.assertTrue(config["effective_config_differs_from_base"])
        self.assertEqual(config["selected_profile_id"], "synthetic_saved_setup")
        self.assertEqual(config["user_overrides"]["mass_kg"], self.vehicle.mass_kg)
        self.assertNotEqual(
            config["base_profile_manifest"]["model_config"]["fields"]["mass_kg"],
            config["effective_vehicle_config"]["fields"]["mass_kg"],
        )

    def test_bad_alignment_is_rejected(self) -> None:
        trace = Telemetry({
            "vehicle.time_s": (0.5, 0.5),
            "vehicle.distance_m": (1.0, 2.0),
        })
        with self.assertRaisesRegex(ValueError, "time must increase"):
            capture_lap_run(self._result(trace), self.manifest, self.settings, actual_vehicle=self.vehicle)
        no_distance = Telemetry({"vehicle.time_s": (0.5,)})
        with self.assertRaisesRegex(ValueError, "vehicle.distance_m"):
            capture_lap_run(self._result(no_distance), self.manifest, self.settings, actual_vehicle=self.vehicle)

    def test_interrupted_run_retains_failure_without_fake_lap(self) -> None:
        failed = EnduranceRunResult(
            completed_laps=0,
            driving_time_s=0.4,
            lap_times_s=(),
            pack_energy_kwh=0.0,
            final_state_of_charge=0.95,
            failure_reason="vehicle stalled on the endurance path",
            telemetry=None,
        )
        payload = capture_lap_run(
            failed, self.manifest, self.settings, actual_vehicle=self.vehicle,
        ).to_dict()
        self.assertEqual(payload["result"]["status"], "failed")
        self.assertEqual(payload["result"]["completed_laps"], 0)
        self.assertEqual(payload["telemetry"]["status"], "not_recorded")

    def test_failed_run_record_separates_checked_prefix_from_attempted_state(self) -> None:
        failed = EnduranceRunResult(
            completed_laps=0,
            driving_time_s=0.8,
            lap_times_s=(),
            pack_energy_kwh=0.0001,
            final_state_of_charge=0.89,
            failure_reason="supplied controls exceeded the path ceiling",
            telemetry=Telemetry({
                "vehicle.time_s": (0.5,),
                "vehicle.distance_m": (1.0,),
                "vehicle.speed_mps": (2.0,),
            }),
            ending_speed_mps=3.0,
            accepted_time_s=0.5,
            accepted_distance_m=1.0,
            accepted_speed_mps=2.0,
            accepted_state_of_charge=0.9,
            failed_lap_index=0,
            failed_cell_index=1,
            failed_cell_update_completed=True,
        )
        payload = capture_lap_run(
            failed, self.manifest, self.settings, actual_vehicle=self.vehicle,
        ).to_dict()
        saved = payload["result"]
        self.assertEqual(saved["driving_time_s"], 0.8)
        self.assertEqual(saved["accepted_time_s"], 0.5)
        self.assertEqual(saved["accepted_distance_m"], 1.0)
        self.assertEqual(saved["accepted_speed_mps"], 2.0)
        self.assertEqual(saved["accepted_state_of_charge"], 0.9)
        self.assertEqual(saved["failed_lap_index"], 0)
        self.assertEqual(saved["failed_cell_index"], 1)
        self.assertTrue(saved["failed_cell_update_completed"])
        self.assertEqual(payload["telemetry"]["sample_count"], 1)
        self.assertTrue(any(
            "advanced the vehicle" in warning
            for warning in payload["validity"]["warnings"]
        ))
        with self.assertRaisesRegex(ValueError, "accepted_time_s must match"):
            capture_lap_run(
                replace(failed, accepted_time_s=0.4),
                self.manifest, self.settings, actual_vehicle=self.vehicle,
            )
        with self.assertRaisesRegex(ValueError, "accepted_speed_mps must match"):
            capture_lap_run(
                replace(failed, accepted_speed_mps=2.1),
                self.manifest, self.settings, actual_vehicle=self.vehicle,
            )
        with self.assertRaisesRegex(ValueError, "failure location and update status"):
            capture_lap_run(
                replace(failed, failed_cell_update_completed=None),
                self.manifest, self.settings, actual_vehicle=self.vehicle,
            )
        with self.assertRaisesRegex(ValueError, "cannot contain failure location"):
            capture_lap_run(
                replace(
                    failed, completed_laps=1, lap_times_s=(0.8,),
                    failure_reason=None, accepted_time_s=0.8,
                    accepted_speed_mps=3.0,
                    accepted_state_of_charge=0.89,
                ),
                self.manifest, self.settings, actual_vehicle=self.vehicle,
            )


if __name__ == "__main__":
    unittest.main()
