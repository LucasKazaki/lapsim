"""Exact digital predicates; no clock fixture or geometric hit is a receipt."""
from pathlib import Path
from fractions import Fraction as F
from copy import deepcopy
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from lapsim_light_course import fsg_phase as phase
from lapsim_light_course import _fsi_geometry as g

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'src/lapsim_light_course/data'
BUNDLE=(DATA/'amz_fssim_fsg_approx.json').read_bytes()
CONES=(DATA/'FSG.yaml').read_bytes()
BASE=(ROOT/'tests/data/fsg_periodic_bspline64_unqualified.json').read_bytes()
RAW=(ROOT/'tests/data/fsg_smoothed_phase_unqualified.json').read_bytes()
VALUE=json.loads(RAW)
BASE_VALUE=json.loads(BASE)
PHASE_RECORDS=[]


def view(raw=RAW):
    return phase.FsgSmoothedPhaseView(raw,phase.sm.FsgSmoothedCandidate(BASE))


def linear_bezier(y=F(0)):
    return ((F(-1),y),(F(-1,3),y),(F(1,3),y),(F(1),y))


def roots(points,ends=((0.,1.),(0.,-1.)),**limits):
    return phase._isolate_beziers((points,),ends,1,phase.sm._Budget(5.),**limits)


def circle_controls():
    return [[1.5,0.],[0.,1.5],[-1.5,0.],[0.,-1.5]]


class FsgPhaseTests(unittest.TestCase):
    def test_tangent_or_overlap_cannot_produce_transverse_phase(self):
        with self.assertRaises(ValueError):
            phase._digital_roots([[0.,0.]]*4,((0.,-1.),(0.,1.)),1,phase.sm._Budget(5.))

    def test_exact_interior_split_root_is_owned_once(self):
        result=roots(linear_bezier())
        self.assertEqual(len(result['roots']),1)
        root=result['roots'][0]
        self.assertEqual([phase._ratio_value(v) for v in root['parameter_bracket']],[F(1,2),F(1,2)])
        self.assertEqual(root['direction'],1)
        self.assertTrue(root['exact_dyadic_parameter_known'])

    def test_infinite_plane_crossing_outside_finite_gate_is_not_counted(self):
        self.assertEqual(roots(linear_bezier(F(2)))['roots'],[])

    def test_finite_gate_endpoint_root_is_refused(self):
        with self.assertRaisesRegex(ValueError,'endpoint'):roots(linear_bezier(F(1)))

    def test_shared_knot_crossing_and_reverse_direction_are_not_hidden(self):
        result=phase._digital_roots(circle_controls(),((0.,1.5),(0.,.5)),1,phase.sm._Budget(5.))
        self.assertEqual(len(result['roots']),1)
        self.assertEqual(phase._ratio_value(result['roots'][0]['parameter_bracket'][0]),F(1))
        self.assertEqual(result['roots'][0]['direction'],-1)
        self.assertGreaterEqual(result['identical_endpoint_roots_deduplicated'],1)

    def test_periodic_seam_root_is_canonical_zero_once(self):
        result=phase._digital_roots(circle_controls(),((.5,0.),(1.5,0.)),1,phase.sm._Budget(5.))
        self.assertEqual(len(result['roots']),1)
        self.assertEqual(phase._ratio_value(result['roots'][0]['parameter_bracket'][0]),F(0))
        self.assertEqual(result['roots'][0]['direction'],1)
        self.assertGreaterEqual(result['identical_endpoint_roots_deduplicated'],1)

    def test_two_roots_closer_than_bracket_tolerance_are_never_merged(self):
        d=F(1,4)-F(1,2**80)
        points=((d,F(-1,2)),(d-F(1,3),F(-1,6)),
                (d-F(1,3),F(1,6)),(d,F(1,2)))
        result=roots(points)
        self.assertEqual(len(result['roots']),2)
        parameters=[phase._ratio_value(v['parameter_bracket'][0]) for v in result['roots']]
        self.assertEqual(parameters,[F(1,2)-F(1,2**40),F(1,2)+F(1,2**40)])
        self.assertLess(parameters[1]-parameters[0],phase.ROOT_WIDTH)
        self.assertEqual([v['direction'] for v in result['roots']],[-1,1])

    def test_multiple_finite_roots_are_preserved(self):
        result=phase._digital_roots(circle_controls(),((0.,2.),(0.,-2.)),1,phase.sm._Budget(5.))
        self.assertEqual(len(result['roots']),2)

    def test_deep_exact_root_radius_includes_float_representative_rounding(self):
        local=F(1,2)+F(1,2**48)
        points=(( -local,F(0)),(F(1,3)-local,F(0)),
                (F(2,3)-local,F(0)),(F(1)-local,F(0)))
        outside=((F(10),F(10)),)*4
        with patch.object(phase,'ROOT_WIDTH',F(1,2**48)):
            result=phase._isolate_beziers((outside,)*63+(points,),((0.,1.),(0.,-1.)),
                1,phase.sm._Budget(5.))
        root=result['roots'][0];exact=F(63)+local
        self.assertEqual([phase._ratio_value(v) for v in root['parameter_bracket']],[exact,exact])
        self.assertNotEqual(F(root['representative_parameter_index']),exact)
        self.assertGreaterEqual(F(root['parameter_radius_index']),abs(F(root['representative_parameter_index'])-exact))

    def test_non_dyadic_tangency_stays_unresolved_at_depth_cap(self):
        # x=(t-1/3)^2, y=t-1/2. The tangent parameter is not dyadic.
        points=((F(1,9),F(-1,2)),(F(-1,9),F(-1,6)),
                (F(0),F(1,6)),(F(4,9),F(1,2)))
        with self.assertRaises(ValueError):roots(points,max_depth=16)

    def test_gate_node_and_depth_exhaustion_cannot_return_partial_roots(self):
        for limits in ({'max_nodes':1},{'max_depth':0}):
            with self.subTest(limits=limits),self.assertRaises(ValueError):roots(linear_bezier(),**limits)

    def test_invalid_exact_gate_inputs_are_refused(self):
        for controls,ends,orientation in (([[True,0.]]*4,((0.,1.),(0.,-1.)),1),
                (circle_controls(),((0.,0.),(0.,0.)),1),
                (circle_controls(),((0.,1.),(0.,-1.)),True)):
            with self.subTest(orientation=orientation),self.assertRaises(ValueError):
                phase._digital_roots(controls,ends,orientation,phase.sm._Budget(5.))

    def test_phase_endpoints_and_derivatives_use_identical_offset(self):
        value=view()
        for derivative in range(4):self.assertEqual(value.evaluate(0.,derivative),value.evaluate(64.,derivative))
        for progress in (-1.,65.,True,float('nan')):
            with self.subTest(progress=progress),self.assertRaises(ValueError):value.evaluate(progress)

    def test_source_device_and_phase_units_are_not_old_source_station(self):
        self.assertEqual(VALUE['gate']['upstream_endpoints_xy_m'],[[6.,3.],[6.,-3.]])
        self.assertEqual(VALUE['gate']['orientation_source_cell'],14)
        self.assertFalse(VALUE['gate']['front_wing_pose_used_as_vehicle_state'])
        self.assertFalse(VALUE['root_midpoint_is_exact_machine_gate_pose'])
        self.assertGreater(VALUE['root']['representative_parameter_index'],1.)
        self.assertLess(VALUE['root']['representative_parameter_index'],2.)
        self.assertNotIn('source_station_m',VALUE['root'])

    def test_directed_geometric_hit_supplies_no_lap_clock_or_energy(self):
        value=view();gate=value.payload()['gate'];p=value.evaluate(0.);n=gate['forward_unit']
        before=tuple(x-.1*d for x,d in zip(p,n));after=tuple(x+.1*d for x,d in zip(p,n))
        hit=value.finite_segment_crossing(before,after)
        self.assertAlmostEqual(hit['fraction'],.5,places=8)
        self.assertFalse(hit['lap_completion_or_initial_departure_verified'])
        self.assertIsNone(hit['awards']);self.assertNotIn('lap_time_s',hit);self.assertNotIn('pack_energy_j',hit)
        self.assertIsNone(value.finite_segment_crossing(after,before))
        self.assertIsNone(value.finite_segment_crossing(gate['endpoints_xy_m'][0],after))
        tangent=(-n[1],n[0]);outside=tuple(x+4*d for x,d in zip(gate['origin_xy_m'],tangent))
        self.assertIsNone(value.finite_segment_crossing(tuple(x-.1*d for x,d in zip(outside,n)),
                                                      tuple(x+.1*d for x,d in zip(outside,n))))

    def test_margin_partition_covers_every_cell_and_keeps_max_not_sample_peak(self):
        audit=VALUE['curvature_margin'];cover=audit['covering_intervals']
        for i in range(64):
            row=[v for v in cover if v['cell_index']==i]
            self.assertEqual(row[0]['left_index'],0.);self.assertEqual(row[-1]['right_index'],1.)
            self.assertTrue(all(a['right_index']==b['left_index'] for a,b in zip(row,row[1:])))
        self.assertEqual(max(v['upper_bound_per_m'] for v in cover),audit['refined_upper_bound_per_m'])
        self.assertGreaterEqual(audit['refined_upper_bound_per_m']+audit['guard_per_m'],
                                audit['maximum_observed_point_curvature_per_m'])
        self.assertLess(audit['refined_upper_bound_per_m'],audit['coarse_upper_bound_per_m'])
        self.assertEqual(audit['unchanged_limit_per_m'],BASE_VALUE['screens']['curvature']['limit_per_m'])
        self.assertEqual(sha256(BASE).hexdigest(),VALUE['base_reference_sha256'])

    def test_margin_exhaustion_cannot_replace_old_certificate_with_partial_max(self):
        for limits in ({'max_nodes':1},{'max_depth':0}):
            with self.subTest(limits=limits),self.assertRaises(ValueError):
                phase._curvature_margin(BASE_VALUE,phase.sm._Budget(5.),**limits)
        self.assertEqual(phase.sm.FsgSmoothedCandidate(BASE).raw,BASE)

    def test_phase_transport_identity_scope_and_ratios_are_strict(self):
        for raw in (bytearray(RAW),RAW+b' ',b'x'*(phase.MAX_BYTES+1)):
            with self.subTest(kind=type(raw)),self.assertRaises(ValueError):view(raw)
        for change in (lambda v:v.update(base_reference_sha256='0'*64),
                       lambda v:v.update(qualification_or_execution_authority=True),
                       lambda v:v.update(old_fsi_gate_ledger_or_worker_compatible=True),
                       lambda v:v.update(root_midpoint_is_exact_machine_gate_pose=True),
                       lambda v:v.update(status='ADMITTED'),lambda v:v.update(phase_units='m')):
            value=deepcopy(VALUE);change(value)
            with self.subTest(change=change),self.assertRaises(ValueError):view(g.canonical(value).encode())
        for ratio in ({'numerator':'01','denominator':'2'},{'numerator':'1','denominator':'0'},
                      {'numerator':1,'denominator':'2'},{'numerator':'2','denominator':'4'}):
            with self.subTest(ratio=ratio),self.assertRaises(ValueError):phase._ratio_value(ratio)

    def test_real_fsg_phase_complete_readback_preserves_reference(self):
        self.assertEqual(sha256(RAW).hexdigest(),'20c2f7d5102fd0bcd34058fc449f2b85679eda745a71c7f97d88c73d444294ab')
        result=phase.verify_fsg_gate_phase(RAW,BASE,BUNDLE,CONES,work_wall_s=40.)
        self.assertEqual(result.reference.raw,BASE)
        self.assertEqual(result.raw,RAW)
        lo,hi=[phase._ratio_value(v) for v in result.payload()['root']['parameter_bracket']]
        self.assertLessEqual(hi-lo,phase.ROOT_WIDTH)
        self.assertEqual(result.payload()['root_search']['cells_resolved'],64)
        self.assertFalse(result.payload()['actual_car_or_native_or_mission_qualified'])
        PHASE_RECORDS.append(result.payload())

    def test_rehashed_or_inflated_margin_claim_rejected_by_readback(self):
        value=deepcopy(VALUE);value['curvature_margin']['guarded_margin_per_m']*=2
        with self.assertRaisesRegex(ValueError,'readback'):
            phase.verify_fsg_gate_phase(g.canonical(value).encode(),BASE,BUNDLE,CONES)

    def test_stale_reference_transport_is_refused(self):
        base=deepcopy(BASE_VALUE);base['screens']['geometry']['x_m'][10]+=.1
        base['geometry_sha256']=g.digest(base['screens']['geometry'])
        stale=phase.sm.FsgSmoothedCandidate(g.canonical(base).encode())
        with self.assertRaises(ValueError):phase.FsgSmoothedPhaseView(RAW,stale)

    def test_untrusted_clock_fixture_catches_late_phase_transport(self):
        now=[0.];original=phase.FsgSmoothedPhaseView
        def late(raw,reference):
            result=original(raw,reference);now[0]=41.;return result
        with patch.object(phase.sm,'monotonic',lambda:now[0]), \
             patch.object(phase,'_verified_base',return_value=phase.sm.FsgSmoothedCandidate(BASE)), \
             patch.object(phase,'FsgSmoothedPhaseView',side_effect=late):
            with self.assertRaisesRegex(ValueError,'deadline'):
                phase.construct_fsg_gate_phase(BASE,BUNDLE,CONES,work_wall_s=40.)

    def test_existing_fsi_gate_ledger_rejects_fsg_phase_gate(self):
        from lapsim_light_campaign import gate_ledger
        with self.assertRaisesRegex(ValueError,'Pinned source physical gate'):
            gate_ledger.crossing((),tick=1,before_pose=(-.1,0.),after_pose=(.1,0.),
                before_pack=9e6,after_pack=9e6,state={},memory={},before_state={},source_sha256='0'*64,
                source_length_m=306.,source_before_m=305.9,source_after_m=306.,gate=VALUE['gate'])


if __name__=='__main__':unittest.main()
