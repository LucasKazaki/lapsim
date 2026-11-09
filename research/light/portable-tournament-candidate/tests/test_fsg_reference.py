"""Development source-chord and source-metadata gate checks, never admission."""
from pathlib import Path
from copy import deepcopy
from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
from math import hypot, cos, sin
import unittest
from unittest.mock import patch

from lapsim_light_course import fsg_reference as ref, _fsi_geometry as g, course

DATA = Path(__file__).resolve().parents[1] / 'src/lapsim_light_course/data'
BUNDLE = (DATA/'amz_fssim_fsg_approx.json').read_bytes()
CONES = (DATA/'FSG.yaml').read_bytes()
REFERENCE_RECORDS = []


class FsgReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = ref.construct_fsg_source_chord_reference(BUNDLE, CONES)
        cls.source = course.construct_fsg_course(BUNDLE, CONES)

    def test_vertex_touch_is_not_a_source_gate_crossing(self):
        from lapsim_light_course.fsg_reference import source_crossing
        with self.assertRaisesRegex(ValueError, 'vertex touch'):
            source_crossing(((-1.,-1.),(0.,0.),(-1.,1.),(-2.,0.)), ((0.,-2.),(0.,2.)))

    def test_real_gate_aligned_source_chord_candidate(self):
        result = self.reference
        value = result.payload()
        self.assertEqual(value['status'], 'SOURCE_CHORD_DIAGNOSTIC_UNQUALIFIED')
        self.assertFalse(value['qualification_or_execution_authority'])
        self.assertEqual(value['gate_candidate']['upstream_endpoints_xy_m'], [[6.,3.],[6.,-3.]])
        self.assertFalse(value['gate_candidate']['official_or_vehicle_start_semantics_verified'])
        self.assertTrue(value['geometry']['closed'])
        self.assertLessEqual(len(value['geometry']['curvature_per_m']), 5000)
        REFERENCE_RECORDS.append(value)

    def test_geometry_owns_chord_stations_and_new_identity(self):
        v = self.reference.payload();geo = v['geometry'];s = geo['distance_m']
        self.assertEqual(s[0], 0.)
        self.assertEqual((geo['x_m'][0],geo['y_m'][0]), (geo['x_m'][-1],geo['y_m'][-1]))
        self.assertNotEqual((geo['x_m'][0],geo['y_m'][0]), (0.,0.))
        for i,(a,b) in enumerate(zip(s,s[1:])):
            chord=hypot(geo['x_m'][i+1]-geo['x_m'][i],geo['y_m'][i+1]-geo['y_m'][i])
            self.assertGreater(chord, 1e-5)
            self.assertAlmostEqual(b-a,chord,places=11)
            self.assertLessEqual(chord,.1+1e-10)
        self.assertEqual(v['geometry_sha256'], g.digest(geo))
        self.assertNotEqual(v['geometry_sha256'],v['source_geometry_sha256'])
        self.assertNotEqual(s[-1],self.source.source_track.length_m)

    def test_all_original_distinct_vertices_are_retained(self):
        geo=self.reference.payload()['geometry'];points=set(zip(geo['x_m'],geo['y_m']))
        original=self.source.source_track
        self.assertTrue(set(zip(original.x_m[:-1],original.y_m[:-1])).issubset(points))

    def test_actual_gate_segment_and_orientation_use_own_source_frame(self):
        v=self.reference.payload();gate=v['gate_candidate'];frame=self.source.frame_dict()
        expected=[list(ref.map_point(frame,p)) for p in ((6.,3.),(6.,-3.))]
        self.assertEqual(gate['endpoints_xy_m'],expected)
        transform=frame['source_to_course_SE2'];angle=transform['rotation_rad']
        for mapped,original in zip(gate['endpoints_xy_m'],gate['upstream_endpoints_xy_m']):
            x=mapped[0]-transform['translation_x_m'];y=mapped[1]-transform['translation_y_m']
            self.assertAlmostEqual(cos(angle)*x+sin(angle)*y,original[0],places=11)
            self.assertAlmostEqual(-sin(angle)*x+cos(angle)*y,original[1],places=11)
        geo=v['geometry'];direction=(geo['x_m'][1]-geo['x_m'][0],geo['y_m'][1]-geo['y_m'][0])
        self.assertGreater(g.dot(direction,gate['forward_unit']),0.)
        self.assertAlmostEqual(2*gate['finite_half_width_m'],6.)
        self.assertNotEqual(gate['origin_xy_m'],[0.,0.])
        self.assertEqual(gate['source_starting_pose_front_wing_raw'],[0.,0.,0.])
        self.assertFalse(gate['front_wing_pose_used_as_vehicle_state'])
        self.assertEqual(gate['orientation_basis'],'ORDERED_SAVED_SOURCE_CHORD_AT_UNIQUE_TRANSVERSAL_CROSSING')

    def test_curved_source_cell_phase_is_explicitly_an_unbounded_station_estimate(self):
        phase=self.reference.payload()['phase'];track=self.source.source_track;i=phase['source_cell_index']
        self.assertNotEqual(track.curvature_per_m[i],0.)
        self.assertFalse(phase['source_gate_cell_is_straight'])
        self.assertFalse(phase['source_arc_phase_is_exact'])
        self.assertFalse(phase['source_arc_station_error_bound_supplied'])
        self.assertEqual(phase['source_gate_cell_curvature_per_m'],track.curvature_per_m[i])
        self.assertEqual(phase['source_gate_cell_arc_length_m'],track.cell_length_m[i])
        estimate=track.distance_m[i]+phase['source_cell_fraction']*track.cell_length_m[i]
        self.assertEqual(phase['source_arc_station_estimate_at_chord_crossing_m'],estimate)
        self.assertFalse(phase['source_seam_is_timing_gate'])

    def test_densification_does_not_claim_better_source_arc_accuracy(self):
        coarse=ref.construct_fsg_source_chord_reference(BUNDLE,CONES,maximum_step_m=.25).payload()
        fine=self.reference.payload()
        self.assertLess(len(coarse['geometry']['curvature_per_m']),len(fine['geometry']['curvature_per_m']))
        self.assertEqual(coarse['recipe']['source_arc_to_saved_chord_floating_bound_m'],
                         fine['recipe']['source_arc_to_saved_chord_floating_bound_m'])
        self.assertGreater(fine['recipe']['source_arc_to_saved_chord_floating_bound_m'],0.)
        self.assertFalse(fine['recipe']['subdivision_improves_source_arc_error_bound'])
        self.assertAlmostEqual(coarse['geometry']['distance_m'][-1],fine['geometry']['distance_m'][-1],places=10)
        self.assertTrue(all(value is False for value in fine['qualification'].values()))

    def test_directed_finite_intersection_is_not_a_lap_receipt(self):
        gate=self.reference.payload()['gate_candidate'];o=gate['origin_xy_m'];n=gate['forward_unit'];t=(-n[1],n[0])
        def position(forward,lateral=0.):return (o[0]+forward*n[0]+lateral*t[0],o[1]+forward*n[1]+lateral*t[1])
        crossing=self.reference.forward_crossing(position(-.5),position(.5))
        self.assertAlmostEqual(crossing['fraction'],.5)
        self.assertEqual(set(crossing),{'fraction','point_xy_m','scope'})
        self.assertIsNone(self.reference.forward_crossing(position(.5),position(-.5)))
        self.assertIsNone(self.reference.forward_crossing(position(-.5,3.1),position(.5,3.1)))
        self.assertIsNone(self.reference.forward_crossing(position(.1),position(.5)))
        with self.assertRaises(ValueError):self.reference.forward_crossing((float('nan'),0.),(0.,0.))

    def test_unique_true_vertex_crossing_is_counted_once(self):
        result=ref.source_crossing(((-1.,-1.),(0.,0.),(1.,1.),(1.,-1.)),((0.,-.25),(0.,.25)))
        self.assertEqual(result,(1,0.,(0.,0.)))

    def test_missing_multiple_and_overlapping_crossings_are_refused(self):
        square=((-1.,-1.),(1.,-1.),(1.,1.),(-1.,1.))
        for gate in (((5.,-2.),(5.,2.)),((0.,-2.),(0.,2.)),((-1.,-2.),(-1.,2.))):
            with self.subTest(gate=gate),self.assertRaises(ValueError):ref.source_crossing(square,gate)

    def test_sample_and_pair_limits_fail_without_fallback(self):
        with self.assertRaisesRegex(ValueError,'Sample cap exceeded'):
            ref.construct_fsg_source_chord_reference(BUNDLE,CONES,maximum_step_m=.05)
        with patch.object(ref,'MAX_COARSE_PAIRS',0),self.assertRaisesRegex(ValueError,'pair budget'):
            ref.construct_fsg_source_chord_reference(BUNDLE,CONES)
        for value in (True,0.,.049,.501,float('nan'),float('inf'),'0.1'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                ref.construct_fsg_source_chord_reference(BUNDLE,CONES,maximum_step_m=value)

    def test_foldbacks_and_nonlocal_source_intersections_are_refused(self):
        for points in (((0.,0.),(1.,0.),(.5,0.),(.5,1.)),((0.,0.),(1.,1.),(0.,1.),(1.,0.))):
            with self.subTest(points=points),self.assertRaises(ValueError):ref.screen_coarse_loop(points)

    def test_complete_source_pin_is_required_without_fsi_fallback(self):
        fsi=(DATA/'amz_fssim_fsi_approx.json').read_bytes();fsi_cones=(DATA/'FSI.yaml').read_bytes()
        for b,c in ((BUNDLE+b' ',CONES),(BUNDLE,CONES+b' '),(fsi,fsi_cones),(BUNDLE,fsi_cones)):
            with self.subTest(bundle=len(b),cones=len(c)),self.assertRaises(ValueError):
                ref.construct_fsg_source_chord_reference(b,c)

    def test_exact_readback_rebuilds_only_data_consistency(self):
        result=ref.verify_fsg_source_chord_reference(self.reference.raw,BUNDLE,CONES)
        self.assertEqual(result.raw,self.reference.raw)
        before=sha256(result.raw).hexdigest();view=result.payload();view['geometry']['x_m'][0]=999.
        self.assertEqual(sha256(result.raw).hexdigest(),before)
        with self.assertRaises(FrozenInstanceError):result.raw=b'{}'

    def test_rehashed_geometry_gate_phase_or_claim_changes_are_rejected(self):
        def geometry(v):
            v['geometry']['x_m'][20]+=.01;v['geometry_sha256']=g.digest(v['geometry'])
        for mutate in (geometry,lambda v:v['gate_candidate']['origin_xy_m'].__setitem__(0,0.),
                       lambda v:v['phase'].update(source_arc_phase_is_exact=True),
                       lambda v:v['qualification'].update(native_reference_compatible=True)):
            value=deepcopy(self.reference.payload());mutate(value)
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):
                ref.verify_fsg_source_chord_reference(g.canonical(value).encode(),BUNDLE,CONES)

    def test_mutable_excessive_noncanonical_and_nonfinite_transport_is_rejected(self):
        for raw in (None,b'',bytearray(self.reference.raw),memoryview(self.reference.raw),b'x'*(ref.MAX_BYTES+1)):
            with self.subTest(kind=type(raw)),self.assertRaises(ValueError):ref.FsgSourceChordReference(raw)
        for raw in (self.reference.raw+b' ',b'{"schema":1,"schema":2}',b'{"x":NaN}',b'{"x":1e999}'):
            with self.subTest(raw=len(raw)),self.assertRaises(ValueError):ref.verify_fsg_source_chord_reference(raw,BUNDLE,CONES)

    def test_existing_fsi_reference_and_gate_consumers_reject_candidate(self):
        from lapsim_light_campaign.numerical_inputs import raw_reference_inputs, NumericalReference
        from lapsim_light_campaign import gate_ledger
        self.assertIsNot(type(self.reference),NumericalReference)
        fsi=course.construct_fsi_course((DATA/'amz_fssim_fsi_approx.json').read_bytes(),(DATA/'FSI.yaml').read_bytes())
        with self.assertRaisesRegex(ValueError,'Exact development reference input'):
            raw_reference_inputs(self.reference.raw,fsi,producer_audit_sha256='0'*64,reviewed_promotion_sha256='0'*64)
        with self.assertRaisesRegex(ValueError,'Pinned source physical gate'):
            gate_ledger.crossing((),tick=1,before_pose=(-.1,0.),after_pose=(.1,0.),before_pack=9e6,after_pack=9e6,
                state={},memory={},before_state={},source_sha256='0'*64,source_length_m=306.,
                source_before_m=305.9,source_after_m=306.,gate=self.reference.payload()['gate_candidate'])


if __name__ == '__main__':
    unittest.main()
