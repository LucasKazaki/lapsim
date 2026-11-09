"""Approximate polygon/rectangle diagnostics, never native course admission."""
from pathlib import Path
from copy import deepcopy
from math import hypot, pi
import unittest

from lapsim_light_course import fsg_clearance as screen, fsg_reference as ref, racing_geometry as rg

DATA = Path(__file__).resolve().parents[1] / 'src/lapsim_light_course/data'
BUNDLE = (DATA/'amz_fssim_fsg_approx.json').read_bytes()
CONES = (DATA/'FSG.yaml').read_bytes()
CLEARANCE_RECORDS = []


def square(radius):
    return ((-radius,-radius),(0.,-radius),(radius,-radius),(radius,0.),
            (radius,radius),(0.,radius),(-radius,radius),(-radius,0.))


FRAME = {'left_xy_m': square(1.), 'right_xy_m': square(8.)}
ROUTE = square(4.)
BODY = dict(front_m=1.,rear_m=1.,width_m=1.4,safety_margin_m=.2,
            map_uncertainty_m=.1,tracking_allowance_m=.1,source_arc_allowance_m=0.)


class FsgClearanceTests(unittest.TestCase):
    def test_analytic_whole_chord_disk_bound_and_swept_rectangles(self):
        value = screen.screen_closed_route(ROUTE,FRAME,**BODY)
        self.assertTrue(value['route_inside_approximate_corridor'])
        self.assertAlmostEqual(value['minimum_route_boundary_distance_m'],3.)
        self.assertAlmostEqual(value['disk_radius_m'],hypot(1.,.7))
        self.assertAlmostEqual(value['disk_envelope_slack_m'],3.-hypot(1.,.7)-.4-1e-9)
        self.assertTrue(value['all_heading_disk_envelope_clear'])
        self.assertTrue(value['tangent_translation_envelopes_clear'])
        self.assertFalse(value['qualification_or_execution_authority'])

    def test_vertices_inside_do_not_hide_between_vertex_boundary_crossing(self):
        route = ((-4.,0.),(4.,0.),(4.,4.),(-4.,4.))
        value = screen.screen_closed_route(route,FRAME,**BODY)
        self.assertFalse(value['route_inside_approximate_corridor'])
        self.assertEqual(value['minimum_route_boundary_distance_m'],0.)
        self.assertFalse(value['all_heading_disk_envelope_clear'])
        self.assertFalse(value['tangent_translation_envelopes_clear'])

    def test_all_outside_vertices_are_rejected_as_route_evidence(self):
        value = screen.screen_closed_route(square(9.),FRAME,**BODY)
        self.assertFalse(value['route_inside_approximate_corridor'])
        self.assertFalse(value['all_heading_disk_envelope_clear'])

    def test_conservative_disk_failure_is_not_rectangle_collision_claim(self):
        # Wide outer square: a long thin body stays inside under tangent
        # translation, though its all-heading disk cannot fit at each corner.
        body = dict(BODY,front_m=2.,rear_m=2.,width_m=.2,
                    safety_margin_m=0.,map_uncertainty_m=0.,tracking_allowance_m=0.)
        route = ((0.,-6.),(3.,-3.),(6.,0.),(3.,3.),(0.,6.),(-3.,3.),(-6.,0.),(-3.,-3.))
        value = screen.screen_closed_route(route,FRAME,**body)
        self.assertFalse(value['all_heading_disk_envelope_clear'])
        self.assertTrue(value['tangent_translation_envelopes_clear'])
        self.assertTrue(value['specified_junction_rotations_clear'])
        self.assertEqual(value['status'],'TANGENT_TRANSLATION_AND_SPECIFIED_YAW_FAMILY_CLEAR_FLOAT_SCREEN')
        self.assertFalse(value['collision_proven_by_disk_bound_failure'])

    def test_swept_rectangle_enclosure_is_not_corner_only_acceptance(self):
        frame = {'left_xy_m':square(.5),'right_xy_m':square(20.)}
        # All corners/edges look clear, yet the entire inner island is
        # enclosed by this rectangle. A corners+edge-hits-only test is wrong.
        vertices = ((-7.,1.),(7.,1.),(7.,-5.),(-7.,-5.))
        self.assertTrue(all(rg.point_clearance(frame,p) > .4 for p in vertices))
        self.assertTrue(all(not rg._hit(a,b,c,d) for a,b in rg.segments(vertices)
            for polygon in frame.values() for c,d in rg.segments(polygon)))
        body = dict(BODY,front_m=6.,rear_m=6.,width_m=6.)
        value = screen.screen_closed_route(square(2.),frame,**body)
        self.assertFalse(value['tangent_translation_envelopes_clear'])
        self.assertLess(value['minimum_tangent_translation_slack_m'],0.)

    def test_exact_boundary_contact_never_passes(self):
        value = screen.screen_closed_route(square(8.),FRAME,**BODY)
        self.assertFalse(value['route_inside_approximate_corridor'])
        self.assertFalse(value['all_heading_disk_envelope_clear'])

    def test_disjoint_crossing_or_degenerate_corridors_are_refused(self):
        shifted = tuple((x+20.,y) for x,y in square(1.))
        for frame in ({'left_xy_m':square(1.),'right_xy_m':shifted},
                      {'left_xy_m':square(8.),'right_xy_m':tuple((x+2.,y) for x,y in square(8.))},
                      {'left_xy_m':[(0.,0.)]*8,'right_xy_m':square(8.)}):
            with self.subTest(frame=frame),self.assertRaises(ValueError):
                screen.screen_closed_route(ROUTE,frame,**BODY)

    def test_nonfinite_mutable_shapes_degenerate_route_and_dimensions_refused(self):
        for key,value in (('front_m',True),('rear_m',0.),('width_m',float('nan')),
                          ('map_uncertainty_m',-.1),('source_arc_allowance_m',float('inf'))):
            with self.subTest(key=key),self.assertRaises(ValueError):
                screen.screen_closed_route(ROUTE,FRAME,**dict(BODY,**{key:value}))
        for route in ([(0.,0.)]*8,((0.,0.),(float('inf'),0.),(1.,1.)),ROUTE+(ROUTE[0],)):
            with self.subTest(route=route),self.assertRaises(ValueError):
                screen.screen_closed_route(route,FRAME,**BODY)

    def test_pair_budget_exhaustion_refuses_without_partial_pass(self):
        with self.assertRaisesRegex(ValueError,'pair budget'):
            screen.screen_closed_route(ROUTE,FRAME,**BODY,maximum_pairs=1)
        for cap in (True,0,300001):
            with self.subTest(cap=cap),self.assertRaises(ValueError):
                screen.screen_closed_route(ROUTE,FRAME,**BODY,maximum_pairs=cap)

    def test_rotation_midpoint_failure_not_hidden_by_clear_endpoint_poses(self):
        body = (2.,2.,1.4)
        result = screen._rotation_screen(FRAME,(6.2,0.),-pi/2,pi/2,body,.01,
                                        maximum_intervals=64,maximum_depth=10)
        self.assertEqual(result['status'],'STATIC_POSE_SCREEN_FAILED')
        self.assertFalse(result['clear'])
        self.assertAlmostEqual(result['witness_pose_xy_yaw'][2],0.)

    def test_rotation_interval_bound_refines_and_accounts_for_every_leaf(self):
        result = screen._rotation_screen(FRAME,(6.,0.),0.,1.5,(1.,1.,1.4),.4,
                                        maximum_intervals=64,maximum_depth=10)
        self.assertTrue(result['clear'])
        self.assertGreater(result['intervals_checked'],1)
        self.assertGreater(result['minimum_certified_slack_bound_m'],0.)

    def test_rotation_work_or_depth_exhaustion_is_unresolved(self):
        for count,depth,status in ((1,10,'INTERVAL_BUDGET_EXHAUSTED'),(64,0,'DEPTH_EXHAUSTED')):
            result = screen._rotation_screen(FRAME,(6.,0.),0.,1.5,(1.,1.,1.4),.4,
                                            maximum_intervals=count,maximum_depth=depth)
            self.assertFalse(result['clear'])
            self.assertEqual(result['status'],status)
            self.assertLessEqual(result['intervals_checked'],count)

    def test_shared_route_rotation_budget_does_not_certify_remaining_joins(self):
        route = ((0.,-6.),(3.,-3.),(6.,0.),(3.,3.),(0.,6.),(-3.,3.),(-6.,0.),(-3.,-3.))
        body = dict(BODY,front_m=2.,rear_m=2.,width_m=.2,
                    safety_margin_m=0.,map_uncertainty_m=0.,tracking_allowance_m=0.)
        value = screen.screen_closed_route(route,FRAME,**body,maximum_rotation_intervals=1)
        self.assertFalse(value['specified_junction_rotations_clear'])
        self.assertEqual(value['status'],'ROTATION_ENVELOPE_UNRESOLVED')
        self.assertEqual(value['rotation_intervals_checked'],1)
        for cap in (True,0,8193):
            with self.subTest(cap=cap),self.assertRaises(ValueError):
                screen.screen_closed_route(ROUTE,FRAME,**BODY,maximum_rotation_intervals=cap)

    def test_ambiguous_half_turn_is_unresolved_without_selecting_a_yaw_path(self):
        route = ((0.,-6.),(6.,0.),(3.,-3.),(0.,6.),(-6.,0.))
        body = dict(BODY,front_m=2.,rear_m=2.,width_m=.2,
                    safety_margin_m=0.,map_uncertainty_m=0.,tracking_allowance_m=0.)
        value = screen.screen_closed_route(route,FRAME,**body)
        self.assertFalse(value['specified_junction_rotations_clear'])
        self.assertEqual(value['junction_rotation_records'][-1]['status'],'AMBIGUOUS_HALF_TURN')

    def test_real_fsg_reference_exact_sources_and_explicit_synthetic_body(self):
        reference = ref.construct_fsg_source_chord_reference(BUNDLE,CONES)
        value = screen.screen_fsg_source_chord_reference(reference.raw,BUNDLE,CONES,
            **{k:v for k,v in BODY.items() if k!='source_arc_allowance_m'})
        self.assertEqual(value['scope'],'APPROXIMATE_CONE_POLYLINE_CHORD_ROUTE_DIAGNOSTIC_ONLY')
        self.assertEqual(value['source_geometry_sha256'],reference.payload()['source_geometry_sha256'])
        self.assertEqual(value['reference_geometry_sha256'],reference.payload()['geometry_sha256'])
        self.assertEqual(value['body_dimensions_scope'],'CALLER_DECLARED_NOT_MEASURED_OR_PROFILE_QUALIFIED')
        self.assertFalse(value['source_arc_or_dynamics_qualified'])
        self.assertFalse(value['heldout_results_used'])
        self.assertFalse(value['qualification_or_execution_authority'])
        self.assertFalse(value['cone_base_radius_or_survey_accuracy_verified'])
        self.assertEqual(value['source_arc_allowance_m'],reference.payload()['recipe']['source_arc_to_saved_chord_floating_bound_m'])
        self.assertEqual(value['sampled_reference_cells_checked'],3339)
        self.assertLess(value['maximum_sample_to_parent_chord_residual_m'],1e-9)
        self.assertEqual(value['route_chords_checked'],725)
        self.assertEqual(value['route_boundary_pairs_checked'],131950)
        self.assertTrue(value['tangent_translation_envelopes_clear'])
        self.assertFalse(value['all_heading_disk_envelope_clear'])
        self.assertTrue(value['specified_junction_rotations_clear'])
        self.assertEqual(value['tangent_and_junction_heading_basis'],
                         'PARENT_CHORD_HEADINGS_NOT_FLOATING_SUBDIVISION_HEADINGS')
        self.assertEqual(len(value['junction_rotation_records']),725)
        self.assertTrue(all(r['clear'] for r in value['junction_rotation_records']))
        CLEARANCE_RECORDS.append(value)

    def test_altered_reference_or_source_cannot_gain_screen(self):
        reference = ref.construct_fsg_source_chord_reference(BUNDLE,CONES)
        for raw,b,c in ((reference.raw+b' ',BUNDLE,CONES),(reference.raw,BUNDLE+b' ',CONES),
                        (reference.raw,BUNDLE,CONES+b' ')):
            with self.subTest(bytes=len(raw)),self.assertRaises(ValueError):
                screen.screen_fsg_source_chord_reference(raw,b,c,
                    **{k:v for k,v in BODY.items() if k!='source_arc_allowance_m'})

    def test_report_mutation_does_not_modify_reference_or_inputs(self):
        before = deepcopy(FRAME)
        report = screen.screen_closed_route(ROUTE,FRAME,**BODY)
        report['status']='FAKE'
        self.assertEqual(FRAME,before)
        self.assertNotEqual(screen.screen_closed_route(ROUTE,FRAME,**BODY)['status'],'FAKE')


if __name__ == '__main__':
    unittest.main()
