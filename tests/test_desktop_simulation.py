"""Numerical invariants for the desktop vehicle setup and solver grid."""

from math import atan, isclose, pi
from unittest import TestCase
from unittest.mock import patch

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Track
from lapsim.core.controls import Controls
from lapsim.solvers.path_constraints import PathConstraintSolver
from lapsim.ui.presets import TOYOTA_2026_PRIUS_SPECS, VehicleSetup, make_prius_benchmark
from lapsim.ui.simulation import (
    prepare_one_lap_constraints, resample_track, run_one_lap,
)
from vehicle_model import Vehicle
from vehicle_model.mech.loads import TireNormalLoads
from vehicle_model.mech.tire import Tire


class DesktopSimulationMathTests(TestCase):
    def test_prepared_constraints_reuse_one_grid_with_an_explicit_start(self) -> None:
        track = SpatialTrack.from_track(
            Track.from_segments([Curve(25.0, 2.0 * pi)]),
            maximum_cell_length_m=5.0,
        )
        vehicle = Vehicle(initial_speed_mps=7.0)
        vehicle.speed_mps = 50.0
        constraints = prepare_one_lap_constraints(vehicle, track)
        self.assertIs(constraints.track, track)
        self.assertEqual(vehicle.speed_mps, 7.0)

        shared_start_mps = min(5.0, constraints.braking_speed_ceiling_mps[0])
        with patch("lapsim.ui.simulation.PathConstraintSolver") as solver_type:
            result = run_one_lap(
                vehicle, track, torque_request_fraction=0.3,
                constraints=constraints, starting_speed_mps=shared_start_mps,
            )
            solver_type.assert_not_called()
        self.assertTrue(result.completed, result.failure_reason)
        self.assertEqual(result.starting_speed_mps, shared_start_mps)
        self.assertEqual(result.ending_speed_mps, vehicle.speed_mps)
        self.assertEqual(result.telemetry.sample_count, track.cell_count)

    def test_prepared_constraints_match_the_default_run(self) -> None:
        track = SpatialTrack.from_track(
            Track.from_segments([Curve(25.0, 2.0 * pi)]),
            maximum_cell_length_m=5.0,
        )
        ordinary = run_one_lap(Vehicle(), track, torque_request_fraction=0.3)
        reused_vehicle = Vehicle()
        constraints = prepare_one_lap_constraints(reused_vehicle, track)
        reused = run_one_lap(
            reused_vehicle, track, torque_request_fraction=0.3,
            constraints=constraints,
        )
        self.assertTrue(ordinary.completed, ordinary.failure_reason)
        self.assertEqual(reused.lap_times_s, ordinary.lap_times_s)
        self.assertEqual(reused.pack_energy_kwh, ordinary.pack_energy_kwh)
        self.assertEqual(reused.telemetry, ordinary.telemetry)

    def test_supplied_constraints_reject_a_different_track(self) -> None:
        source_track = SpatialTrack.from_track(
            Track.from_segments([Curve(25.0, 2.0 * pi)]),
            maximum_cell_length_m=5.0,
        )
        other_track = SpatialTrack.from_track(
            Track.from_segments([Curve(30.0, 2.0 * pi)]),
            maximum_cell_length_m=5.0,
        )
        vehicle = Vehicle()
        constraints = prepare_one_lap_constraints(vehicle, source_track)
        with self.assertRaisesRegex(ValueError, "do not match"):
            run_one_lap(
                vehicle, other_track, torque_request_fraction=0.3,
                constraints=constraints,
            )

    def test_supplied_constraints_reject_a_different_vehicle_on_same_track(self) -> None:
        track = SpatialTrack.from_track(
            Track.from_segments([Curve(25.0, 2.0 * pi)]),
            maximum_cell_length_m=5.0,
        )
        prepared_vehicle = Vehicle()
        constraints = prepare_one_lap_constraints(prepared_vehicle, track)
        with self.assertRaisesRegex(ValueError, "different vehicle"):
            run_one_lap(
                Vehicle(), track, torque_request_fraction=0.3,
                constraints=constraints,
            )

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
