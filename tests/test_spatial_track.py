"""Tests for generic vehicle-independent spatial tracks."""

from math import hypot, pi, sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from lapsim import TrackGeometryAudit
from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Straight, Track


class SpatialTrackTests(TestCase):
    def test_discretizes_arbitrary_segment_track_and_closes_geometry(self) -> None:
        track = Track.from_segments(
            [
                Straight(20.0),
                Curve(10.0, pi),
                Straight(20.0),
                Curve(10.0, pi),
            ]
        )

        spatial = SpatialTrack.from_track(track, maximum_cell_length_m=2.0)

        self.assertAlmostEqual(spatial.length_m, track.total_length_m)
        self.assertAlmostEqual(spatial.x_m[0], spatial.x_m[-1], places=9)
        self.assertAlmostEqual(spatial.y_m[0], spatial.y_m[-1], places=9)
        self.assertEqual(len(spatial.curvature_per_m), len(spatial.distance_m) - 1)

    def test_closed_distance_wrap_is_periodic(self) -> None:
        spatial = SpatialTrack.from_cells(
            cell_length_m=(10.0, 10.0),
            curvature_per_m=(0.0, 0.0),
        )

        self.assertAlmostEqual(spatial.wrap_distance_m(25.0), 5.0)

    def test_csv_round_trip_preserves_solver_geometry(self) -> None:
        spatial = SpatialTrack(
            distance_m=(0.0, 1.0, 2.0),
            x_m=(0.0, 1.0, 0.0),
            y_m=(0.0, 0.0, 0.0),
            curvature_per_m=(0.1, -0.1),
        )

        with TemporaryDirectory() as directory:
            path = Path(directory) / "track.csv"
            spatial.to_csv(path)
            loaded = SpatialTrack.from_csv(path)

        self.assertEqual(loaded, spatial)

    def test_geometry_audit_detects_impossible_point_to_point_distance(self) -> None:
        spatial = SpatialTrack(
            distance_m=(0.0, 1.0, 2.0),
            x_m=(0.0, 2.0, 0.0),
            y_m=(0.0, 0.0, 0.0),
            curvature_per_m=(0.0, 0.0),
        )

        audit = spatial.geometry_audit()

        self.assertIsInstance(audit, TrackGeometryAudit)
        self.assertEqual(audit.cells_with_chord_excess, 2)
        self.assertAlmostEqual(audit.station_length_m, 2.0)
        self.assertAlmostEqual(audit.xy_chord_length_m, 4.0)
        self.assertAlmostEqual(audit.total_chord_excess_m, 2.0)
        self.assertAlmostEqual(audit.maximum_chord_excess_m, 1.0)
        self.assertAlmostEqual(audit.endpoint_separation_m, 0.0)

    def test_geometry_audit_accepts_shorter_chords_on_curves(self) -> None:
        spatial = SpatialTrack.from_track(
            Track.from_segments([Curve(10.0, 2.0 * pi)]),
            maximum_cell_length_m=1.0,
        )

        audit = spatial.geometry_audit()

        self.assertEqual(audit.cells_with_chord_excess, 0)
        self.assertAlmostEqual(audit.endpoint_separation_m, 0.0, places=8)
        self.assertLess(audit.xy_chord_length_m, audit.station_length_m)
        self.assertAlmostEqual(audit.curvature_signed_turn_rad, 2.0 * pi)
        self.assertAlmostEqual(audit.xy_signed_winding_rad, 2.0 * pi)
        self.assertAlmostEqual(audit.curvature_minus_xy_turn_rad, 0.0, places=10)
        self.assertAlmostEqual(
            audit.curvature_integrated_closure_gap_m, 0.0, places=10
        )

    def test_geometry_audit_detects_curvature_disagreeing_with_closed_map(self) -> None:
        coherent = SpatialTrack.from_track(
            Track.from_segments([Curve(10.0, 2.0 * pi)]),
            maximum_cell_length_m=1.0,
        )
        wrong_curvature = SpatialTrack(
            distance_m=coherent.distance_m,
            x_m=coherent.x_m,
            y_m=coherent.y_m,
            curvature_per_m=(0.0,) * coherent.cell_count,
        )

        audit = wrong_curvature.geometry_audit()

        self.assertEqual(audit.cells_with_chord_excess, 0)
        self.assertAlmostEqual(audit.curvature_signed_turn_rad, 0.0)
        self.assertAlmostEqual(audit.xy_signed_winding_rad, 2.0 * pi)
        self.assertAlmostEqual(audit.curvature_minus_xy_turn_rad, -2.0 * pi)
        self.assertAlmostEqual(
            audit.curvature_integrated_closure_gap_m, coherent.length_m
        )

    def test_geometry_audit_detects_arc_chord_mismatch_with_matching_total_turn(self) -> None:
        square = SpatialTrack(
            distance_m=(0.0, 10.0, 20.0, 30.0, 40.0),
            x_m=(0.0, 10.0, 10.0, 0.0, 0.0),
            y_m=(0.0, 0.0, 10.0, 10.0, 0.0),
            curvature_per_m=(pi / 20.0,) * 4,
        )

        audit = square.geometry_audit()

        self.assertEqual(audit.cells_with_chord_excess, 0)
        self.assertAlmostEqual(audit.curvature_minus_xy_turn_rad, 0.0)
        self.assertAlmostEqual(audit.curvature_integrated_closure_gap_m, 0.0)
        self.assertGreater(audit.maximum_arc_chord_mismatch_m, 0.9)
        with self.assertRaisesRegex(ValueError, "cell 0 arc chord mismatch"):
            square.validate_coherent_arcs()

    def test_geometry_audit_preserves_clockwise_turn_sign(self) -> None:
        clockwise = SpatialTrack.from_track(
            Track.from_segments([Curve(10.0, -2.0 * pi)]),
            maximum_cell_length_m=1.0,
        )

        audit = clockwise.geometry_audit()

        self.assertAlmostEqual(audit.curvature_signed_turn_rad, -2.0 * pi)
        self.assertAlmostEqual(audit.xy_signed_winding_rad, -2.0 * pi)
        self.assertAlmostEqual(audit.curvature_minus_xy_turn_rad, 0.0, places=10)
        self.assertAlmostEqual(
            audit.curvature_integrated_closure_gap_m, 0.0, places=10
        )

    def test_geometry_audit_reports_shipped_curvature_map_disagreement(self) -> None:
        source = Path(__file__).resolve().parents[1]
        spatial = SpatialTrack.from_csv(
            source / "analysis/data/track/gnss_imu_endurance_track.csv"
        )

        audit = spatial.geometry_audit()

        self.assertAlmostEqual(audit.station_length_m, 989.0)
        self.assertEqual(audit.cells_with_chord_excess, 1441)
        self.assertAlmostEqual(audit.curvature_signed_turn_rad, 3.657937, places=5)
        self.assertAlmostEqual(audit.xy_signed_winding_rad, 2.0 * pi, places=5)
        self.assertAlmostEqual(
            audit.curvature_minus_xy_turn_rad, -2.625248, places=5
        )
        self.assertAlmostEqual(
            audit.curvature_integrated_closure_gap_m, 542.633, places=2
        )

    def test_geometry_audit_reports_endpoint_separation_on_open_path(self) -> None:
        spatial = SpatialTrack(
            distance_m=(0.0, 2.0),
            x_m=(0.0, 2.0),
            y_m=(0.0, 0.0),
            curvature_per_m=(0.0,),
            closed=False,
        )

        audit = spatial.geometry_audit()

        self.assertEqual(audit.cells_with_chord_excess, 0)
        self.assertAlmostEqual(audit.endpoint_separation_m, 2.0)
        self.assertAlmostEqual(audit.curvature_signed_turn_rad, 0.0)
        self.assertIsNone(audit.xy_signed_winding_rad)
        self.assertIsNone(audit.curvature_minus_xy_turn_rad)
        self.assertIsNone(audit.curvature_integrated_closure_gap_m)

    def test_geometry_audit_keeps_degenerate_map_diagnostic_read_only(self) -> None:
        spatial = SpatialTrack(
            distance_m=(0.0, 1.0, 2.0),
            x_m=(0.0, 0.0, 0.0),
            y_m=(0.0, 0.0, 0.0),
            curvature_per_m=(0.0, 0.0),
        )

        audit = spatial.geometry_audit()

        self.assertAlmostEqual(audit.curvature_signed_turn_rad, 0.0)
        self.assertIsNone(audit.xy_signed_winding_rad)
        self.assertIsNone(audit.curvature_minus_xy_turn_rad)
        self.assertIsNone(audit.curvature_integrated_closure_gap_m)

        later_zero_chord = SpatialTrack(
            distance_m=(0.0, 1.0, 2.0, 3.0),
            x_m=(0.0, 1.0, 1.0, 0.0),
            y_m=(0.0, 0.0, 0.0, 0.0),
            curvature_per_m=(0.0, 0.0, 0.0),
        ).geometry_audit()
        self.assertIsNone(later_zero_chord.xy_signed_winding_rad)
        self.assertAlmostEqual(
            later_zero_chord.curvature_integrated_closure_gap_m, 3.0
        )

    def test_coherent_arc_gate_and_refinement_accept_analytic_courses(self) -> None:
        courses = (
            SpatialTrack.from_track(
                Track.from_segments([Curve(10.0, 2.0 * pi)]),
                maximum_cell_length_m=0.5,
            ),
            SpatialTrack.from_track(
                Track.from_segments([
                    Straight(40.0), Curve(12.0, pi / 2.0),
                    Straight(20.0), Curve(12.0, pi / 2.0),
                    Straight(40.0), Curve(12.0, pi / 2.0),
                    Straight(20.0), Curve(12.0, pi / 2.0),
                ]),
                maximum_cell_length_m=0.5,
            ),
        )
        for source in courses:
            with self.subTest(source_length_m=source.length_m):
                source.validate_coherent_arcs()
                self.assertIs(source.refine_arcs(1.0), source)
                refined = source.refine_arcs(0.2)
                refined.validate_coherent_arcs()
                self.assertTrue(refined.closed)
                self.assertLessEqual(max(refined.cell_length_m), 0.2 + 1e-12)
                self.assertGreater(refined.cell_count, source.cell_count)
                for index, station_m in enumerate(source.distance_m):
                    refined_index = refined.distance_m.index(station_m)
                    self.assertEqual(refined.x_m[refined_index], source.x_m[index])
                    self.assertEqual(refined.y_m[refined_index], source.y_m[index])
                    if index < source.cell_count:
                        next_index = refined.distance_m.index(source.distance_m[index + 1])
                        self.assertTrue(all(
                            value == source.curvature_per_m[index]
                            for value in refined.curvature_per_m[refined_index:next_index]
                        ))

        circle, _ = courses
        refined_circle = circle.refine_arcs(0.2)
        fraction = refined_circle.distance_m[1] / circle.distance_m[1]
        linear_x = circle.x_m[0] + fraction * (circle.x_m[1] - circle.x_m[0])
        linear_y = circle.y_m[0] + fraction * (circle.y_m[1] - circle.y_m[0])
        self.assertGreater(
            hypot(refined_circle.x_m[1] - linear_x, refined_circle.y_m[1] - linear_y),
            1e-5,
        )

    def test_coherent_arc_gate_rejects_closed_endpoint_mismatch(self) -> None:
        circle = SpatialTrack.from_track(
            Track.from_segments([Curve(10.0, 2.0 * pi)]),
            maximum_cell_length_m=1.0,
        )
        displaced = SpatialTrack(
            distance_m=circle.distance_m,
            x_m=(*circle.x_m[:-1], circle.x_m[-1] + 0.01),
            y_m=circle.y_m,
            curvature_per_m=circle.curvature_per_m,
        )
        with self.assertRaisesRegex(ValueError, "closed endpoint mismatch"):
            displaced.validate_coherent_arcs()

    def test_coherent_arc_gate_rejects_local_error_with_passing_lap_totals(self) -> None:
        radius_m = 10.0
        chord_m = sqrt(2.0) * radius_m
        rise_m = sqrt(3.0) * chord_m / 2.0
        cell_length_m = pi * radius_m / 2.0
        rhombus = SpatialTrack(
            distance_m=tuple(index * cell_length_m for index in range(5)),
            x_m=(0.0, chord_m, 1.5 * chord_m, 0.5 * chord_m, 0.0),
            y_m=(0.0, 0.0, rise_m, rise_m, 0.0),
            curvature_per_m=(1.0 / radius_m,) * 4,
        )
        audit = rhombus.geometry_audit()
        self.assertLess(audit.maximum_arc_chord_mismatch_m, 1e-12)
        self.assertLess(abs(audit.curvature_minus_xy_turn_rad), 1e-12)
        self.assertLess(audit.curvature_integrated_closure_gap_m, 1e-12)
        with self.assertRaisesRegex(ValueError, "cell 1 arc vector endpoint mismatch"):
            rhombus.validate_coherent_arcs()

    def test_coherent_arc_gate_rejects_accumulated_position_drift(self) -> None:
        drifted = SpatialTrack(
            distance_m=tuple(float(index) for index in range(21)),
            x_m=tuple(index * (1.0 + 2e-7) for index in range(21)),
            y_m=(0.0,) * 21,
            curvature_per_m=(0.0,) * 20,
            closed=False,
        )
        with self.assertRaisesRegex(ValueError, "cell 5 cumulative position drift"):
            drifted.validate_coherent_arcs()

    def test_coherent_arc_gate_rejects_heading_seam(self) -> None:
        kinked_seam = SpatialTrack.from_track(
            Track.from_segments([
                Curve(3.0, pi / 2.0),
                Curve(1.0, pi / 2.0),
                Curve(2.0, pi / 2.0),
                Straight(2.0),
            ]),
            maximum_cell_length_m=0.2,
            close_geometry=False,
        )
        self.assertLess(kinked_seam.geometry_audit().endpoint_separation_m, 1e-12)
        with self.assertRaisesRegex(ValueError, "heading seam mismatch"):
            kinked_seam.validate_coherent_arcs()

    def test_coarse_exact_semicircles_do_not_alias_heading_gate(self) -> None:
        circle = SpatialTrack(
            distance_m=(0.0, pi, 2.0 * pi),
            x_m=(1.0, -1.0, 1.0),
            y_m=(0.0, 0.0, 0.0),
            curvature_per_m=(1.0, 1.0),
        )
        circle.validate_coherent_arcs()
        refined = circle.refine_arcs(0.25)
        refined.validate_coherent_arcs()
        self.assertEqual(refined.x_m[refined.distance_m.index(pi)], -1.0)
        self.assertEqual(refined.y_m[refined.distance_m.index(pi)], 0.0)

    def test_coherent_arc_gate_rejects_shipped_fused_course(self) -> None:
        source = Path(__file__).resolve().parents[1]
        fused = SpatialTrack.from_csv(
            source / "analysis/data/track/gnss_imu_endurance_track.csv"
        )
        with self.assertRaisesRegex(ValueError, "closed endpoint mismatch"):
            fused.validate_coherent_arcs()
        with self.assertRaisesRegex(ValueError, "closed endpoint mismatch"):
            fused.refine_arcs(0.25)

    def test_refine_arcs_rejects_bad_step_and_excessive_cells(self) -> None:
        circle = SpatialTrack.from_track(
            Track.from_segments([Curve(10.0, 2.0 * pi)]),
            maximum_cell_length_m=1.0,
        )
        for bad_step in (True, 0.0, -1.0, float("nan"), float("inf")):
            with self.subTest(bad_step=bad_step):
                with self.assertRaisesRegex(ValueError, "finite and positive"):
                    circle.refine_arcs(bad_step)
        with self.assertRaisesRegex(ValueError, "100000-cell compute cap"):
            circle.refine_arcs(1e-6)

    def test_can_convert_cells_to_legacy_segment_track(self) -> None:
        spatial = SpatialTrack(
            distance_m=(0.0, 2.0, 5.0),
            x_m=(0.0, 2.0, 5.0),
            y_m=(0.0, 0.0, 0.0),
            curvature_per_m=(0.0, 0.2),
        )

        legacy = spatial.to_track()

        self.assertAlmostEqual(legacy.total_length_m, spatial.length_m)
        self.assertIsInstance(legacy.segments[0], Straight)
        self.assertIsInstance(legacy.segments[1], Curve)
