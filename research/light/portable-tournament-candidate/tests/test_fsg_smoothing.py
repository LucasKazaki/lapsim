"""Pure spline geometry; clock fixtures never represent native admission."""
from pathlib import Path
from copy import deepcopy
from hashlib import sha256
from math import cos,sin,pi,hypot
import json
import unittest
from unittest.mock import patch

from lapsim_light_course import fsg_smoothing as smoothing, _fsi_geometry as g

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'src/lapsim_light_course/data'
BUNDLE=(DATA/'amz_fssim_fsg_approx.json').read_bytes()
CONES=(DATA/'FSG.yaml').read_bytes()
RAW=(ROOT/'tests/data/fsg_periodic_bspline64_unqualified.json').read_bytes()
VALUE=json.loads(RAW)
PROPOSAL=g.canonical(VALUE['proposal']).encode()
SMOOTH_RECORDS=[]


def circle_controls():
    return [[1.5,0.],[0.,1.5],[-1.5,0.],[0.,-1.5]]


def octagon(radius):
    return [[radius*cos(i*pi/4),radius*sin(i*pi/4)] for i in range(8)]


def small_screen(parameters=None):
    p=dict(smoothing.PARAMETERS,front_m=.1,rear_m=.1,width_m=.1,
        safety_margin_m=.01,map_uncertainty_m=.01,tracking_allowance_m=.01,
        wheelbase_m=.1,maximum_steering_rad=1.)
    p.update(parameters or {})
    return smoothing._screen_chain([0.,1.,2.,3.,4.],
        smoothing._controls_to_coefficients([[3*x,3*y] for x,y in circle_controls()]),
        {'left_xy_m':octagon(.2),'right_xy_m':octagon(10.)},p,smoothing._Budget(10.))


class FsgSmoothingTests(unittest.TestCase):
    def test_wrong_coefficient_shape_is_rejected(self):
        with self.assertRaises(ValueError):
            smoothing._validate_chain([0.,1.,2.,3.,4.],[[[0.,0.]]]*4)

    def test_cyclic_solver_matches_independent_harmonic_solution(self):
        nodes=[[cos(2*pi*i/64),sin(2*pi*i/64)] for i in range(64)]
        controls=smoothing._interpolating_controls(nodes,smoothing._Budget(5.))
        factor=6/(4+2*cos(2*pi/64))
        for p,s in zip(controls,nodes):
            self.assertLess(hypot(p[0]-factor*s[0],p[1]-factor*s[1]),1e-13)

    def test_shared_basis_matches_analytic_quarter_and_periodic_derivatives(self):
        controls=circle_controls()
        for t in (0.,.1,.5,.9):
            expected=(1-1.5*t*t+.5*t**3,1.5*t-.5*t**3)
            self.assertLess(hypot(*g.sub(smoothing.evaluate_periodic_controls(controls,t),expected)),1e-14)
        for derivative in range(3):
            self.assertEqual(smoothing.evaluate_periodic_controls(controls,0.,derivative),
                smoothing.evaluate_periodic_controls(controls,4.,derivative))

    def test_control_perturbation_cannot_create_independent_join_gap(self):
        controls=[[cos(2*pi*i/16)+.03*(i%3),sin(2*pi*i/16)] for i in range(16)]
        coeff=smoothing._controls_to_coefficients(controls)
        joins=smoothing._validate_chain([float(i) for i in range(17)],coeff)
        self.assertLess(joins['maximum_position_residual_m'],1e-13)
        self.assertLess(joins['maximum_parameter_velocity_residual'],1e-13)
        self.assertLess(joins['maximum_parameter_acceleration_residual'],1e-13)
        for i in range(16):
            for derivative in range(3):
                self.assertLess(hypot(*g.sub(smoothing._eval(coeff,i,0.,derivative),
                    smoothing.evaluate_periodic_controls(controls,float(i),derivative))),1e-13)

    def test_nonfinite_controls_parameters_and_derivatives_refused(self):
        for controls,param,derivative in (([[float('nan'),0.]]*4,0.,0),
                (circle_controls(),True,0),(circle_controls(),float('inf'),0),
                (circle_controls(),0.,True),(circle_controls(),0.,4)):
            with self.subTest(param=param),self.assertRaises(ValueError):
                smoothing.evaluate_periodic_controls(controls,param,derivative)

    def test_small_shared_curve_complete_screens_are_not_node_only(self):
        result=small_screen()
        self.assertGreater(result['curvature']['minimum_parameter_speed_bound'],0.)
        self.assertGreater(result['clearance']['minimum_floating_bound_m'],0.)
        self.assertGreater(result['sampling']['sample_cells'],4)
        self.assertGreater(result['topology']['adjacent_interval_count'],4)

    def test_interval_sample_and_topology_exhaustion_never_return_partial_pass(self):
        for values in ({'maximum_curvature_intervals':0},{'maximum_clearance_intervals':0},
                       {'maximum_samples':2},{'maximum_topology_pairs':0}):
            with self.subTest(values=values),self.assertRaises(ValueError):small_screen(values)

    def test_structural_C2_does_not_bypass_zero_speed_rejection(self):
        coeff=smoothing._controls_to_coefficients([[0.,0.]]*4)
        with self.assertRaises(ValueError):smoothing._validate_chain([0.,1.,2.,3.,4.],coeff)

    def test_fixed_projection_rejects_boolean_and_number_aliases(self):
        def frame(v):v['frame']['source_to_course_SE2']['scale']=True
        def zero(v):v['frame']['runtime_or_corridor_admission']=0
        def recipe(v):v['parameters']['front_m']=True
        def knots(v):v['parameter_knots'][0]=0
        def stations(v):v['source_fit_stations_m'][0]=0
        for change in (frame,zero,recipe,knots,stations):
            proposal=deepcopy(VALUE['proposal']);change(proposal)
            # Python equality is insufficient for exact typed projections.
            self.assertEqual(proposal,VALUE['proposal'])
            self.assertNotEqual(g.canonical(proposal),g.canonical(VALUE['proposal']))
            with self.subTest(change=change),self.assertRaises(smoothing.SplineScreenFailure):
                smoothing.screen_fsg_spline_proposal(g.canonical(proposal).encode(),BUNDLE,CONES)

    def test_independent_piece_or_duplicate_control_override_refused(self):
        for change in (lambda v:v.update(coefficients=[]),
                       lambda v:v['control_points_xy_m'].append(v['control_points_xy_m'][0])):
            proposal=deepcopy(VALUE['proposal']);change(proposal)
            with self.subTest(change=change),self.assertRaises(smoothing.SplineScreenFailure):
                smoothing.screen_fsg_spline_proposal(g.canonical(proposal).encode(),BUNDLE,CONES)

    def test_rejected_curve_retains_complete_proposal_bytes(self):
        proposal=deepcopy(VALUE['proposal']);proposal['control_points_xy_m'][20][0]+=.1
        raw=g.canonical(proposal).encode()
        with self.assertRaises(smoothing.SplineScreenFailure) as error:
            smoothing.screen_fsg_spline_proposal(raw,BUNDLE,CONES)
        self.assertEqual(error.exception.proposal_raw,raw)

    def test_source_pins_and_frame_digest_cannot_be_replaced(self):
        for b,c in ((BUNDLE+b' ',CONES),(BUNDLE,CONES+b' ')):
            with self.subTest(b=len(b)),self.assertRaises(smoothing.SplineScreenFailure):
                smoothing.screen_fsg_spline_proposal(PROPOSAL,b,c)
        proposal=deepcopy(VALUE['proposal']);proposal['frame_sha256']='0'*64
        with self.assertRaises(smoothing.SplineScreenFailure):
            smoothing.screen_fsg_spline_proposal(g.canonical(proposal).encode(),BUNDLE,CONES)

    def test_immutable_canonical_transport_and_false_authority_required(self):
        for raw in (bytearray(RAW),b'',RAW+b' ',b'x'*(smoothing.MAX_BYTES+1),
                    b'{"schema":1,"schema":2}',b'{"schema":NaN}'):
            with self.subTest(kind=type(raw)),self.assertRaises(ValueError):smoothing.FsgSmoothedCandidate(raw)
        value=deepcopy(VALUE);value['qualification_or_execution_authority']=True
        with self.assertRaises(ValueError):smoothing.FsgSmoothedCandidate(g.canonical(value).encode())

    def test_previous_independent_coefficient_schema_cannot_be_reinterpreted(self):
        proposal=deepcopy(VALUE['proposal']);proposal['schema']='lapsim.fsg-fixed-periodic-cubic-proposal.v1'
        with self.assertRaises(smoothing.SplineScreenFailure):
            smoothing.screen_fsg_spline_proposal(g.canonical(proposal).encode(),BUNDLE,CONES)

    def test_real_fixture_full_readback_and_original_failures_preserved(self):
        self.assertEqual(sha256(RAW).hexdigest(),'d6cf0b81bd04edcb41f4cedc6c73720f6709e58dd81a06d8d5b245859470cdc8')
        result=smoothing.verify_fsg_smoothed_candidate(RAW,BUNDLE,CONES,work_wall_s=40.)
        value=result.payload();screens=value['screens']
        self.assertLess(screens['curvature']['maximum_floating_bound_per_m'],screens['curvature']['limit_per_m'])
        self.assertGreater(screens['clearance']['minimum_floating_bound_m'],0.)
        self.assertEqual(screens['sampling']['sample_cells'],4096)
        self.assertEqual(len(value['original_source_steering_proxy']['margin_violations']),9)
        self.assertEqual(len(value['original_source_steering_proxy']['hard_limit_violations']),4)
        self.assertEqual(len(value['original_source_steering_proxy']['curvature_jump_records']),192)
        self.assertTrue(value['analytic_model_periodic_C2_by_shared_cyclic_basis'])
        self.assertFalse(value['qualification_or_execution_authority'])
        self.assertFalse(value['gate_phase_or_mission_semantics_supplied'])
        self.assertEqual(result.evaluate(0.),result.evaluate(64.))
        SMOOTH_RECORDS.append(value)

    def test_rehashed_sample_geometry_forgery_rejected_by_complete_readback(self):
        value=deepcopy(VALUE);value['screens']['geometry']['x_m'][10]+=.01
        value['geometry_sha256']=g.digest(value['screens']['geometry'])
        with self.assertRaisesRegex(ValueError,'readback'):
            smoothing.verify_fsg_smoothed_candidate(g.canonical(value).encode(),BUNDLE,CONES)

    def test_untrusted_clock_fixture_retains_proposal_on_late_finalization(self):
        now=[0.];original=smoothing.FsgSmoothedCandidate
        def late(raw):
            result=original(raw);now[0]=41.;return result
        with patch.object(smoothing,'monotonic',lambda:now[0]), \
             patch.object(smoothing,'_screen_chain',return_value=deepcopy(VALUE['screens'])), \
             patch.object(smoothing,'FsgSmoothedCandidate',side_effect=late):
            with self.assertRaises(smoothing.SplineScreenFailure) as error:
                smoothing.screen_fsg_spline_proposal(PROPOSAL,BUNDLE,CONES,work_wall_s=40.)
        self.assertEqual(error.exception.proposal_raw,PROPOSAL)

    def test_untrusted_clock_fixture_producer_does_not_restart_its_budget(self):
        now=[0.]
        def expired(nodes,budget):
            now[0]=41.;return deepcopy(VALUE['proposal']['control_points_xy_m'])
        with patch.object(smoothing,'monotonic',lambda:now[0]), \
             patch.object(smoothing,'_interpolating_controls',side_effect=expired):
            with self.assertRaises(smoothing.SplineScreenFailure) as error:
                smoothing.produce_fsg_smoothed_candidate(BUNDLE,CONES,work_wall_s=40.)
        self.assertEqual(error.exception.proposal_raw,PROPOSAL)

    def test_invalid_or_unbounded_geometry_windows_refused(self):
        for seconds in (True,0.,41.,float('nan')):
            with self.subTest(seconds=seconds),self.assertRaises(ValueError):smoothing._Budget(seconds)

    def test_existing_native_fsi_reference_reader_refuses_new_schema(self):
        from lapsim_light_campaign.numerical_inputs import raw_reference_inputs
        from lapsim_light_course.course import construct_fsi_course
        source=construct_fsi_course((DATA/'amz_fssim_fsi_approx.json').read_bytes(),(DATA/'FSI.yaml').read_bytes())
        with self.assertRaisesRegex(ValueError,'Exact development reference input'):
            raw_reference_inputs(RAW,source,producer_audit_sha256='0'*64,reviewed_promotion_sha256='0'*64)


if __name__=='__main__':
    unittest.main()
