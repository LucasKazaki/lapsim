"""Desktop profile persistence and comparable lap-number extraction."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from lapsim.events.endurance import EnduranceRunResult
from lapsim.ui.comparison import summarize_lap
from lapsim.ui.garage import ProfileStore
from lapsim.ui.presets import VehicleSetup


class DesktopProfileTests(TestCase):
    def test_saved_setup_round_trips_without_run_settings(self) -> None:
        with TemporaryDirectory() as directory:
            store = ProfileStore(Path(directory) / "profiles.json")
            setup = VehicleSetup(mass_kg=1500.0, torque_request_fraction=0.35)
            saved = store.save("Prius load case", setup)

            reloaded = ProfileStore(store.path).list_profiles()
            self.assertEqual(len(reloaded), 1)
            self.assertEqual(reloaded[0].profile_id, saved.profile_id)
            self.assertEqual(reloaded[0].setup(0.8).mass_kg, 1500.0)
            self.assertEqual(reloaded[0].setup(0.8).torque_request_fraction, 0.8)

            with self.assertRaisesRegex(ValueError, "already has that name"):
                store.save("prius load case", setup)
            store.delete(saved.profile_id)
            self.assertEqual(store.list_profiles(), ())

    def test_lap_summary_uses_same_distance_and_telemetry_for_comparison(self) -> None:
        result = EnduranceRunResult(
            completed_laps=1,
            driving_time_s=10.0,
            lap_times_s=(10.0,),
            pack_energy_kwh=0.2,
            final_state_of_charge=0.8,
            failure_reason=None,
            telemetry={
                "vehicle.speed_mps": (0.0, 5.0, 10.0),
                "vehicle.lateral_acceleration_mps2": (0.0, -9.80665, 1.0),
            },
        )
        summary = summarize_lap(result, 100.0)
        self.assertAlmostEqual(summary.lap_time_s, 10.0)
        self.assertAlmostEqual(summary.peak_speed_kph, 36.0)
        self.assertAlmostEqual(summary.average_speed_kph, 36.0)
        self.assertAlmostEqual(summary.distance_m, 100.0)
        self.assertAlmostEqual(summary.pack_energy_kwh, 0.2)
        self.assertAlmostEqual(summary.peak_lateral_g, 1.0)

    def test_lap_summary_includes_rolling_start_in_peak_speed(self) -> None:
        result = EnduranceRunResult(
            completed_laps=1,
            driving_time_s=10.0,
            lap_times_s=(10.0,),
            pack_energy_kwh=0.2,
            final_state_of_charge=0.8,
            failure_reason=None,
            telemetry={
                "vehicle.speed_mps": (10.0, 8.0),
                "vehicle.lateral_acceleration_mps2": (0.0, 0.0),
            },
            starting_speed_mps=20.0,
            ending_speed_mps=8.0,
        )

        summary = summarize_lap(result, 100.0)

        self.assertAlmostEqual(summary.peak_speed_kph, 72.0)
