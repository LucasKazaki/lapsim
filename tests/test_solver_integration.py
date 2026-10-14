"""Small end-to-end test across track, vehicle, and both lap solvers."""

from math import pi
from unittest import TestCase

from lapsim import LapTimeSolver, SpeedLimitSolver
from lapsim.courses.track import Curve, Straight, Track
from vehicle_model import OCVPackBattery, Vehicle


class SolverIntegrationTests(TestCase):
    def test_depleted_pack_cannot_create_a_lap_from_rest(self) -> None:
        vehicle = Vehicle(battery=OCVPackBattery(initial_state_of_charge=0.0))
        track = Track.from_segments([Straight(length_m=5.0)])
        limits = SpeedLimitSolver(vehicle).solve(track)

        with self.assertRaisesRegex(ValueError, "cannot traverse cell"):
            LapTimeSolver(vehicle).solve(limits, starting_speed_mps=0.0)

    def test_corner_exit_respects_current_cell_speed_limit(self) -> None:
        track = Track.from_segments(
            [Curve(radius_m=10.0, span_rad=pi / 2.0), Straight(length_m=50.0)]
            * 4
        )
        vehicle = Vehicle()
        speed_limits = SpeedLimitSolver(vehicle, max_step_m=10.0).solve(track)

        lap = LapTimeSolver(vehicle).solve(speed_limits, starting_speed_mps=8.0)

        corner_exit_indices = [
            index
            for index, curvature_per_m in enumerate(speed_limits.curvature_per_m)
            if curvature_per_m != 0.0
            and index + 1 < len(speed_limits.curvature_per_m)
            and speed_limits.curvature_per_m[index + 1] == 0.0
        ]
        self.assertEqual(len(corner_exit_indices), 4)
        for index in corner_exit_indices:
            with self.subTest(cell_index=index):
                self.assertLessEqual(
                    lap.speed_mps[index + 1],
                    speed_limits.speed_limit_mps[index] + 1e-9,
                )

    def test_corner_exit_force_stays_within_driven_tires_combined_grip(self) -> None:
        speed_mps = 8.0
        curvature_per_m = 0.06
        for driven_axle, indices in (
            ("front", (0, 1)),
            ("rear", (2, 3)),
            ("all", (0, 1, 2, 3)),
        ):
            with self.subTest(driven_axle=driven_axle):
                vehicle = Vehicle()
                vehicle.drivetrain.driven_axle = driven_axle
                solver = LapTimeSolver(vehicle)
                acceleration_mps2 = solver._forward_acceleration_mps2(
                    speed_mps,
                    curvature_per_m,
                )
                drag_and_cornering_n, rolling_n, _ = (
                    solver._resistance_and_downforce(speed_mps, curvature_per_m)
                )
                inferred_drive_force_n = (
                    vehicle.effective_longitudinal_mass_kg * acceleration_mps2
                    + drag_and_cornering_n
                    + rolling_n
                )
                lateral_acceleration_mps2 = speed_mps**2 * curvature_per_m
                aero = vehicle.aero_forces_n(
                    speed_mps,
                    lateral_acceleration_mps2,
                    curvature_per_m=curvature_per_m,
                )
                normal_loads = vehicle.suspension.tire_normal_loads_n(
                    vehicle.mass_kg,
                    vehicle.gravity_mps2,
                    aero,
                    vehicle.chassis,
                    longitudinal_acceleration_mps2=acceleration_mps2,
                    lateral_acceleration_mps2=lateral_acceleration_mps2,
                )
                lateral_forces = vehicle.tire.lateral_forces_n(
                    normal_loads,
                    vehicle.mass_kg * lateral_acceleration_mps2,
                )
                driven_grip_n = sum(
                    vehicle.tire.combined_longitudinal_force_capacity_n(
                        normal_loads.all_n[index],
                        lateral_forces.all_n[index],
                    )
                    for index in indices
                )
                self.assertLessEqual(inferred_drive_force_n, driven_grip_n + 0.01)

    def test_minimum_time_profile_runs_with_composed_vehicle(self) -> None:
        quarter_turn = Curve(radius_m=10.0, span_rad=pi / 2.0)
        track = Track.from_segments(
            [
                Straight(length_m=20.0),
                quarter_turn,
                Straight(length_m=20.0),
                quarter_turn,
                Straight(length_m=20.0),
                quarter_turn,
                Straight(length_m=20.0),
                quarter_turn,
            ]
        )
        vehicle = Vehicle()

        speed_limits = SpeedLimitSolver(vehicle, max_step_m=2.0).solve(track)
        lap = LapTimeSolver(vehicle).solve(
            speed_limits,
            starting_speed_mps=5.0,
        )
        self.assertGreater(lap.lap_time_s, 0.0)
        self.assertEqual(len(lap.speed_mps), len(speed_limits.distance_m))
        self.assertTrue(
            all(
                speed_mps <= limit_mps
                for speed_mps, limit_mps in zip(
                    lap.speed_mps,
                    speed_limits.speed_limit_mps,
                    strict=True,
                )
            )
        )
