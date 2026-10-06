"""Synthetic evidence and replay checks for saved lap records."""

from __future__ import annotations

from math import nan
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from lapsim.core.telemetry import Telemetry
from lapsim.courses.spatial_track import SpatialTrack
from lapsim.events.endurance import EnduranceRunConfig, EnduranceRunResult
from lapsim.experiments import LapRunSettings, RunRecord, capture_lap_run
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
