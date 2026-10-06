"""Numerical invariants for the desktop vehicle setup and solver grid."""

from math import atan, isclose
from unittest import TestCase

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.core.controls import Controls
from lapsim.solvers.path_constraints import PathConstraintSolver
from lapsim.ui.presets import TOYOTA_2026_PRIUS_SPECS, VehicleSetup, make_prius_benchmark
from lapsim.ui.simulation import resample_track
from vehicle_model.mech.loads import TireNormalLoads
from vehicle_model.mech.tire import Tire


class DesktopSimulationMathTests(TestCase):
    def test_prius_conversion_and_reduction_ratio_reach_rated_motor_speed(self) -> None:
        setup = VehicleSetup()
        vehicle = make_prius_benchmark(setup)

        expected_power_kw = 194.0 * 0.745699872
        self.assertAlmostEqual(setup.peak_power_kw, expected_power_kw, places=9)
        self.assertAlmostEqual(
            vehicle.drivetrain.motor_speed_rpm(setup.top_speed_kph / 3.6),
            vehicle.drivetrain.motor.max_speed_rpm,
            places=8,
        )
        self.assertEqual(vehicle.drivetrain.driven_axle, "front")
        self.assertAlmostEqual(
            setup.tire_radius_m,
            (17 * 0.0254 + 2 * 0.195 * 0.60) / 2,
            places=12,
        )
        self.assertAlmostEqual(
            setup.mass_kg,
            TOYOTA_2026_PRIUS_SPECS["curb_mass_kg"],
            places=12,
        )

    def test_front_drive_request_is_not_assigned_to_rear_tires(self) -> None:
        tire = Tire(constant_friction_coefficient=0.9)
        normal_loads = TireNormalLoads.from_iterable((3_000.0,) * 4)

        states = tire.calculate_forces(
            normal_loads,
            total_lateral_force_n=0.0,
            drive_force_request_n=1_000.0,
            front_brake_force_request_n=0.0,
            rear_brake_force_request_n=0.0,
            vehicle_speed_mps=10.0,
            timestep_s=0.1,
            drive_axle="front",
        )

        self.assertAlmostEqual(states.drive_force_n, 1_000.0, places=8)
        self.assertAlmostEqual(states.front[0].drive_force_n, 500.0, places=8)
        self.assertAlmostEqual(states.front[1].drive_force_n, 500.0, places=8)
        self.assertEqual(states.rear[0].drive_force_n, 0.0)
        self.assertEqual(states.rear[1].drive_force_n, 0.0)

    def test_curvature_resampling_preserves_integral_and_course_length(self) -> None:
        track = SpatialTrack.from_cells(
            cell_length_m=(0.5, 1.5, 2.0, 1.0),
            curvature_per_m=(0.02, -0.01, 0.03, 0.0),
        )

        solver_track = resample_track(track, maximum_cell_length_m=0.8)
        source_integral = sum(
            curvature * length
            for curvature, length in zip(
                track.curvature_per_m, track.cell_length_m, strict=True
            )
        )
        solver_integral = sum(
            curvature * length
            for curvature, length in zip(
                solver_track.curvature_per_m,
                solver_track.cell_length_m,
                strict=True,
            )
        )

        self.assertTrue(solver_track.closed is track.closed)
        self.assertAlmostEqual(solver_track.length_m, track.length_m, places=10)
        self.assertTrue(isclose(solver_integral, source_integral, abs_tol=1e-12))
        self.assertLessEqual(max(solver_track.cell_length_m), 0.8 + 1e-12)

    def test_path_solver_rejects_invalid_environment_values(self) -> None:
        for invalid_value in (0.0, -1.0, float("inf"), float("nan")):
            with self.subTest(invalid_value=invalid_value):
                with self.assertRaises(ValueError):
                    PathConstraintSolver(gravity_mps2=invalid_value)
                with self.assertRaises(ValueError):
                    PathConstraintSolver(air_density_kgpm3=invalid_value)

    def test_path_braking_prediction_matches_vehicle_cell_update(self) -> None:
        maximum_pressure_psi = 300.0
        for entry_speed_mps, curvature_per_m in ((20.0, 0.0), (15.0, 0.04)):
            with self.subTest(entry_speed_mps=entry_speed_mps, curvature_per_m=curvature_per_m):
                distance_step_m = 0.5
                reference_vehicle = make_prius_benchmark(VehicleSetup())
                reference_vehicle.speed_mps = entry_speed_mps
                reference_vehicle.update_state(
                    Controls(
                        front_brake_pressure_psi=maximum_pressure_psi,
                        rear_brake_pressure_psi=maximum_pressure_psi,
                        steering_angle_rad=atan(
                            curvature_per_m * reference_vehicle.chassis.wheelbase_m
                        ),
                    ),
                    distance_step_m,
                )
                expected_exit_speed_mps = reference_vehicle.speed_mps

                solver_vehicle = make_prius_benchmark(VehicleSetup())
                predicted_entry_speed_mps = PathConstraintSolver(
                    maximum_brake_pressure_psi=maximum_pressure_psi
                )._maximum_entry_speed_mps(
                    vehicle=solver_vehicle,
                    next_speed_mps=expected_exit_speed_mps,
                    local_speed_limit_mps=25.0,
                    curvature_per_m=curvature_per_m,
                    cell_length_m=distance_step_m,
                )

                self.assertAlmostEqual(
                    predicted_entry_speed_mps,
                    entry_speed_mps,
                    places=5,
                )
