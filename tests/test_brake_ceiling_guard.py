"""Regression coverage for pressure-limited automatic path braking."""

from unittest import TestCase

from lapsim.events.endurance import EnduranceSimulator
from lapsim.profiles import build_vehicle, default_bundle_dir
from lapsim.ui.simulation import load_team_endurance_track, resample_track, run_one_lap


class BrakeCeilingGuardTests(TestCase):
    def test_unsaturated_prius_braking_keeps_nominal_pressure(self) -> None:
        vehicle, _ = build_vehicle("prius_2026_le")
        vehicle.speed_mps = 10.0

        front, rear, front_regen, rear_regen = (
            EnduranceSimulator._brake_controls_for_target_force(
                vehicle,
                brake_force_request_n=1000.0,
                target_acceleration_mps2=-3.0,
                lateral_force_n=0.0,
                curvature_per_m=0.0,
            )
        )

        self.assertAlmostEqual(front, 189.85272744083107, places=6)
        self.assertAlmostEqual(rear, 189.85272744083102, places=6)
        self.assertEqual((front_regen, rear_regen), (0.0, 0.0))

    def test_one_saturated_axle_uses_both_bounded_actuators(self) -> None:
        vehicle, _ = build_vehicle("prius_2026_le")
        vehicle.speed_mps = 10.0
        curvature_per_m = 0.05
        front, rear, _, _ = EnduranceSimulator._brake_controls_for_target_force(
            vehicle,
            brake_force_request_n=2000.0,
            target_acceleration_mps2=-10.0,
            lateral_force_n=vehicle.mass_kg * vehicle.speed_mps**2 * curvature_per_m,
            curvature_per_m=curvature_per_m,
        )

        self.assertEqual(front, vehicle.brakes.maximum_pressure_psi)
        self.assertEqual(rear, vehicle.brakes.maximum_pressure_psi)

        reduced_limit_psi = 295.0
        front, rear, _, _ = EnduranceSimulator._brake_controls_for_target_force(
            vehicle,
            brake_force_request_n=2000.0,
            target_acceleration_mps2=-10.0,
            lateral_force_n=vehicle.mass_kg * vehicle.speed_mps**2 * curvature_per_m,
            curvature_per_m=curvature_per_m,
            maximum_brake_pressure_psi=reduced_limit_psi,
        )
        self.assertEqual((front, rear), (reduced_limit_psi, reduced_limit_psi))

    def test_default_prius_lap_stays_within_brake_and_speed_limits(self) -> None:
        vehicle, _ = build_vehicle("prius_2026_le")
        track = resample_track(load_team_endurance_track(), 2.0)

        result = run_one_lap(vehicle, track, torque_request_fraction=1.0)

        self.assertTrue(result.completed, result.failure_reason)
        # The automatic controller now keeps each curved cell's exit within
        # that cell's corner-speed limit, so this lap is slightly slower than
        # the historical next-cell-ceiling-only controller result.
        self.assertAlmostEqual(result.driving_time_s, 78.7867124559307, delta=0.002)
        assert result.telemetry is not None
        self.assertLessEqual(
            max(result.telemetry["brakes.front_pressure_psi"]),
            vehicle.brakes.maximum_pressure_psi,
        )
        self.assertLessEqual(
            max(result.telemetry["brakes.rear_pressure_psi"]),
            vehicle.brakes.maximum_pressure_psi,
        )

    def test_trev5_geometric_baseline_and_candidate_complete_if_data_available(self) -> None:
        if default_bundle_dir() is None:
            self.skipTest("optional ENME408 local evidence bundle is unavailable")

        from lapsim.optimization.racing_line import RacingLinePlanner, TrackCorridor

        source_track = load_team_endurance_track()
        corridor = TrackCorridor.constant(
            source_track,
            left_width_m=2.0,
            right_width_m=2.0,
            vehicle_width_m=1.8,
            safety_margin_m=0.2,
            source="test assumed corridor",
        )
        plan = RacingLinePlanner().plan(source_track, corridor)
        self.assertEqual(plan.status, "candidate")
        for label, track in (
            ("geometric centerline", plan.baseline_track),
            ("candidate", plan.candidate_track),
        ):
            with self.subTest(path=label):
                vehicle, _ = build_vehicle("trev5_working_geometry")
                result = run_one_lap(vehicle, track, torque_request_fraction=1.0)
                self.assertTrue(result.completed, result.failure_reason)
                self.assertEqual(result.completed_laps, 1)
                assert result.telemetry is not None
                self.assertLessEqual(
                    max(result.telemetry["brakes.front_pressure_psi"]),
                    vehicle.brakes.maximum_pressure_psi,
                )
                self.assertLessEqual(
                    max(result.telemetry["brakes.rear_pressure_psi"]),
                    vehicle.brakes.maximum_pressure_psi,
                )
                self.assertLessEqual(
                    max(
                        speed - ceiling
                        for speed, ceiling in zip(
                            result.telemetry["vehicle.speed_mps"],
                            result.telemetry["endurance.path_speed_ceiling_mps"],
                            strict=True,
                        )
                    ),
                    0.06,
                )
