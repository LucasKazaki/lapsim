"""Synthetic evidence and replay checks for saved lap records."""

from __future__ import annotations

from hashlib import sha256
from importlib.metadata import version as distribution_version
import json
from math import nan
from pathlib import Path
import platform
from tempfile import TemporaryDirectory
import unittest

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


if __name__ == "__main__":
    unittest.main()
