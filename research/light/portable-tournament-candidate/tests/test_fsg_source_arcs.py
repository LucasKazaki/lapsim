"""Source-arc pose geometry and synthetic steering proxy, not vehicle evidence."""
from pathlib import Path
from dataclasses import replace
from math import cos, sin, pi, hypot, atan2, tan
import unittest

from lapsim_light_course import fsg_source_arcs as arcs
from lapsim_light_course.course import SourceTrack

DATA = Path(__file__).resolve().parents[1] / 'src/lapsim_light_course/data'
BUNDLE = (DATA/'amz_fssim_fsg_approx.json').read_bytes()
CONES = (DATA/'FSG.yaml').read_bytes()
ARC_RECORDS = []
PARAMETERS = dict(front_m=1.,rear_m=1.,width_m=1.4,safety_margin_m=.2,
    map_uncertainty_m=.1,tracking_allowance_m=.1,wheelbase_m=1.6,
    maximum_steering_rad=.4,curvature_limit_fraction=.95)


def circle():
    # Independent closed-form clockwise unit circle, initial tangent +x.
    stations = tuple(i*pi/4 for i in range(9))
    return SourceTrack(stations,tuple(sin(s) for s in stations),
        tuple(cos(s)-1 for s in stations),(-1.,)*8,True)


class FsgSourceArcTests(unittest.TestCase):
    def test_stable_constant_curvature_pose_has_correct_units_and_turn_sign(self):
        x,y,h = arcs._pose_at((0.,0.,0.),1.,pi/2)
        self.assertAlmostEqual(x,1.);self.assertAlmostEqual(y,1.);self.assertAlmostEqual(h,pi/2)
        x,y,h = arcs._pose_at((0.,0.,0.),-1.,pi/2)
        self.assertAlmostEqual(x,1.);self.assertAlmostEqual(y,-1.);self.assertAlmostEqual(h,-pi/2)
        self.assertEqual(arcs._pose_at((2.,3.,0.),0.,4.),(6.,3.,0.))
        x,y,h = arcs._pose_at((0.,0.,0.),1e-20,4.)
        self.assertAlmostEqual(x,4.);self.assertGreater(y,0.);self.assertAlmostEqual(y/8e-20,1.)

    def test_global_arc_integration_matches_independent_circle_and_signed_winding(self):
        value = arcs._arc_bounds(circle(),radius_m=1.2)
        self.assertAlmostEqual(value['integrated_signed_turn_rad'],-2*pi)
        self.assertLess(value['maximum_saved_grid_position_error_m'],1e-13)
        self.assertLess(value['closure_position_gap_m'],1e-13)
        self.assertLess(abs(value['wrapped_heading_seam_error_rad']),1e-13)
        self.assertEqual(len(value['cells']),8)
        self.assertNotEqual(value['integrated_terminal_pose_xy_yaw'][2],0.)

    def test_transfer_bound_covers_interior_arc_and_rotated_body_corners(self):
        track = circle();radius=hypot(1.,.7)
        value = arcs._arc_bounds(track,radius_m=radius)
        for row in value['cells']:
            i=row['cell_index'];start=track.distance_m[i];ds=track.cell_length_m[i]
            a=(track.x_m[i],track.y_m[i]);b=(track.x_m[(i+1)%8],track.y_m[(i+1)%8])
            angle=atan2(b[1]-a[1],b[0]-a[0])
            for fraction in (.1,.25,.5,.75,.9):
                s=start+fraction*ds;xy=(sin(s),cos(s)-1);heading=-s
                centre=(a[0]+fraction*(b[0]-a[0]),a[1]+fraction*(b[1]-a[1]))
                for u,v in ((1.,.7),(1.,-.7),(-1.,.7),(-1.,-.7)):
                    pose=(xy[0]+cos(heading)*u-sin(heading)*v,xy[1]+sin(heading)*u+cos(heading)*v)
                    proxy=(centre[0]+cos(angle)*u-sin(angle)*v,centre[1]+sin(angle)*u+cos(angle)*v)
                    self.assertLessEqual(hypot(pose[0]-proxy[0],pose[1]-proxy[1]),
                        row['pose_transfer_bound_m']+1e-12)

    def test_interior_saved_grid_tamper_rejected_despite_same_closure(self):
        track=circle();x=list(track.x_m);x[4]+=.01
        with self.assertRaisesRegex(ValueError,'Full saved source grid'):
            arcs._arc_bounds(replace(track,x_m=tuple(x)),radius_m=1.2)

    def test_nonfinite_boolean_or_inconsistent_arc_channels_are_refused(self):
        track=circle()
        for bad in (replace(track,curvature_per_m=(float('nan'),)+track.curvature_per_m[1:]),
                    replace(track,distance_m=(True,)+track.distance_m[1:]),
                    replace(track,x_m=track.x_m[:-1]),replace(track,closed=False)):
            with self.subTest(bad=bad),self.assertRaises(ValueError):arcs._arc_bounds(bad,radius_m=1.2)

    def test_proxy_margin_is_applied_to_curvature_not_steering_angle(self):
        track=circle()
        value=arcs._steering_proxy(track,wheelbase_m=.2,maximum_steering_rad=.4,curvature_limit_fraction=.95)
        self.assertAlmostEqual(value['margin_curvature_limit_per_m'],.95*tan(.4)/.2)
        self.assertNotAlmostEqual(value['margin_curvature_limit_per_m'],tan(.95*.4)/.2)
        self.assertTrue(value['margin_amplitude_screen_passed'])
        self.assertEqual(len(value['curvature_jump_records']),0)
        self.assertFalse(value['actual_vehicle_steering_qualified'])

    def test_proxy_retains_signed_failures_and_seam_curvature_jumps(self):
        track=replace(circle(),curvature_per_m=(-1.,-2.,-2.,-2.,-2.,-2.,-2.,-2.))
        value=arcs._steering_proxy(track,wheelbase_m=1.6,maximum_steering_rad=.4,curvature_limit_fraction=.95)
        self.assertFalse(value['margin_amplitude_screen_passed'])
        self.assertEqual(len(value['margin_violations']),8)
        self.assertLess(value['margin_violations'][0]['signed_proxy_angle_rad'],0.)
        self.assertEqual([r['to_cell_index'] for r in value['curvature_jump_records']],[0,1])

    def test_missing_or_invalid_steering_recipe_is_not_inferred_from_car(self):
        for name,value in (('wheelbase_m',True),('wheelbase_m',0.),('maximum_steering_rad',pi/2),
                           ('maximum_steering_rad',float('inf')),('curvature_limit_fraction',0.),
                           ('curvature_limit_fraction',1.01)):
            args=dict(wheelbase_m=1.6,maximum_steering_rad=.4,curvature_limit_fraction=.95);args[name]=value
            with self.subTest(name=name),self.assertRaises(ValueError):arcs._steering_proxy(circle(),**args)

    def test_nonpositive_or_unestablished_clearance_cannot_transfer_to_arc(self):
        for valid,slack,bound,expected in ((True,.4,.1,True),(True,.1,.4,False),
                                           (False,.4,.1,False),(True,.1,.1,False)):
            result=arcs._clearance_transfer(valid,slack,bound)
            self.assertEqual(result['continuous_arc_pose_clearance_float_screen_passed'],expected)
            self.assertFalse(result['actual_vehicle_or_native_qualified'])

    def test_derived_nonfinite_or_underflowed_proxy_limits_are_refused(self):
        for args in (dict(wheelbase_m=5e-324,maximum_steering_rad=.4,curvature_limit_fraction=.95),
                     dict(wheelbase_m=1.6,maximum_steering_rad=.4,curvature_limit_fraction=5e-324)):
            with self.subTest(args=args),self.assertRaisesRegex(ValueError,'Derived finite positive'):
                arcs._steering_proxy(circle(),**args)

    def test_pinned_real_fsg_clearance_and_proxy_failures_remain_separate(self):
        value=arcs.screen_fsg_source_arcs(BUNDLE,CONES,**PARAMETERS)
        self.assertEqual(value['status'],'SOURCE_ARC_DIAGNOSTIC_UNQUALIFIED_STEERING_PROXY_FAILED')
        self.assertTrue(value['clearance_transfer']['continuous_arc_pose_clearance_float_screen_passed'])
        self.assertGreater(value['clearance_transfer']['minimum_arc_pose_clearance_lower_bound_m'],0.)
        proxy=value['steering_proxy']
        self.assertEqual([v['cell_index'] for v in proxy['margin_violations']],
                         [442,443,444,445,447,448,449,450,451])
        self.assertEqual([v['cell_index'] for v in proxy['hard_limit_violations']],[442,443,444,445])
        self.assertEqual(len(proxy['curvature_jump_records']),192)
        self.assertAlmostEqual(proxy['maximum_absolute_proxy_angle_rad'],.41168341485150256)
        self.assertEqual(len(value['arc_geometry']['cells']),724)
        self.assertFalse(value['existing_guidance_arc_following_verified'])
        self.assertFalse(value['arc_gate_phase_verified'])
        self.assertFalse(value['qualification_or_execution_authority'])
        self.assertFalse(value['heldout_results_used'])
        ARC_RECORDS.append(value)

    def test_source_pin_tamper_and_wrong_course_are_rejected(self):
        fsi=(DATA/'amz_fssim_fsi_approx.json').read_bytes()
        for b,c in ((BUNDLE+b' ',CONES),(BUNDLE,CONES+b' '),(fsi,CONES)):
            with self.subTest(length=len(b)),self.assertRaises(ValueError):
                arcs.screen_fsg_source_arcs(b,c,**PARAMETERS)


if __name__=='__main__':
    unittest.main()
