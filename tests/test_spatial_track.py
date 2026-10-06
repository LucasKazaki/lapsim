"""Tests for generic vehicle-independent spatial tracks."""

from math import pi
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
