"""State-machine regressions: synthetic geometry/accepted sample fixtures.
The separate archived + full-terminal harness tests actual plant evidence.
"""
import copy,math,unittest
from lapsim.experiments.finite_gate_observer import FiniteGateObserver,SCHEMA

def gate(i,s,xy,t,n,w=.3):return {'index':i,'station_m':s,'center':list(xy),'tangent':list(t),'normal':list(n),'center_half_width_m':w}
def contract():
    return {'schema':SCHEMA,'source_geometry_sha256':'1'*64,'corridor_sha256':'2'*64,'source_length_m':12.,'gates':[gate(1,1.,(1,0),(1,0),(0,1)),gate(2,3.,(2,1),(0,1),(-1,0)),gate(3,6.,(0,2),(-1,0),(0,-1)),gate(4,9.,(-2,1),(0,-1),(1,0)),gate(5,12.,(0,0),(1,0),(0,1))]}

PREFIX=[((0.,0.),0.),((.6,0.),.6),((1.4,0.),1.4),((2.,0.),2.),((2.,.6),2.6),((2.,1.4),3.4),((2.,2.),4.),((.5,2.),5.5),((-.5,2.),6.5),((-2.,2.),8.),((-2.,1.5),8.5),((-2.,.5),9.5),((-2.,0.),10.),((-.2,0.),11.8)]

def run(seq,c=None):
    a=FiniteGateObserver(c or contract())
    for i,(xy,progress) in enumerate(seq):
        a.observe(i,xy,1000.-i,progress)
        if a.done or a.failure:break
    return a

class OrderedFiniteTests(unittest.TestCase):
    def reason(self,a,x):self.assertIsNotNone(a.failure);self.assertEqual(a.failure['reason'],x);self.assertFalse(a.done);self.assertIsNone(a.receipt()['finish_event'])
    def test_real_finish_without_projection_terminal(self):
        a=run(PREFIX+[((.2,0.),11.99)]);self.assertTrue(a.done);self.assertIsNone(a.projected);self.assertEqual([e['gate'] for e in a.events],list(range(1,6)));self.assertEqual(a.finish['interval_end_tick'],14);self.assertEqual(a.finish['alpha'],.5);self.assertEqual(a.finish['time_s'],.135);self.assertEqual(a.finish['interpolated_pack_energy_j'],986.5)
    def test_projection_is_not_crossing_then_actual_finish(self):
        seq=PREFIX[:-1]+[((-.2,0.),12.)];a=run(seq);self.assertFalse(a.done);self.assertIsNone(a.failure);self.assertEqual(a.next_gate,5);self.assertLess(a.projected['signed_finish_m'],0);a.observe(len(seq),(.2,0),986.,12.1);self.assertTrue(a.done);self.assertEqual(a.finish['alpha'],.5)
    def test_projected_seam_with_missing_prior_rejected(self):
        a=run([((0,0),0.),((.2,0),12.)]);self.reason(a,'projected_seam_missing_prior_ordered_gate')
    def test_missed_expected_outside(self):
        self.reason(run([((0,0),0.),((.6,.7),.6),((1.4,.7),1.4)]),'missed_expected_gate_outside_aperture')
    def test_missed_final_outside(self):
        self.reason(run(PREFIX[:-1]+[((-.3,.7),11.7),((.3,.7),12.)]),'missed_expected_gate_outside_aperture')
    def test_reverse_finite_gate(self):
        self.reason(run(PREFIX[:3]+[((.6,0.),1.1)]),'backward_finite_gate')
    def test_repeat_forward_gate_after_reverse_outside_aperture(self):
        self.reason(run(PREFIX[:3]+[((1.4,.6),1.4),((.6,.6),1.4),((.6,0),1.4),((1.4,0),1.5)]),'repeated_finite_gate')
    def test_premature_final_gate(self):
        self.reason(run([((0,0),0.),((.5,0),.5),((.5,.7),.7),((-.5,.7),.8),((-.5,0),.9),((.5,0),1.)]),'premature_finite_finish')
    def test_out_of_order_later_gate(self):
        c=contract();c['gates'][1]=gate(2,3.,(.5,1),(0,1),(-1,0));self.reason(run([((0,0),0.),((.5,.5),.5),((.5,1.5),.8)],c),'missed_or_out_of_order_finite_gate')
    def test_spawn_only_not_finish(self):
        a=run([((0,0),0.),((.6,0),.6)]);self.assertFalse(a.done);self.assertFalse(a.events);self.assertIsNone(a.failure)
    def test_backward_initial_departure(self):self.reason(run([((0,0),0.),((-.1,0),0.)]),'backward_seam_departure')
    def test_spawn_off_seam_invalid(self):self.reason(run([((-.01,0),0.)]),'invalid_seam_spawn')
    def test_exact_landing_not_finish_until_confirms(self):
        a=run(PREFIX+[((0.,0.),12.)]);self.assertFalse(a.done);self.assertIsNone(a.failure);self.assertEqual(a.next_gate,5);self.assertEqual(a.receipt()['pending_exact_plane_touches'][0]['alpha'],1.)
        a.observe(15,(.01,0.),985.,12.01);self.assertTrue(a.done);self.assertEqual(a.finish['interval_end_tick'],14);self.assertEqual(a.finish['confirmed_tick'],15);self.assertEqual(a.finish['time_s'],.14)
    def test_exact_touch_reversal_does_not_credit(self):
        self.reason(run(PREFIX+[((0,0),12.),((-.1,0),12.)]),'finite_gate_touch_reversed')
    def test_leaving_aperture_while_exactly_on_plane(self):
        self.reason(run(PREFIX+[((0,0),12.),((0,.5),12.)]),'left_aperture_while_on_gate')
    def test_multiple_chronological_finite_crossings_in_one_interval(self):
        c=contract();c['gates'][1]=gate(2,3.,(1.5,0),(1,0),(0,1));a=run([((0,0),0.),((.6,0),.6),((1.9,0),2.)],c);self.assertIsNone(a.failure);self.assertEqual([e['gate'] for e in a.events],[1,2]);self.assertLess(a.events[0]['alpha'],a.events[1]['alpha'])
    def test_simultaneous_order_cannot_be_fabricated(self):
        c=contract();c['gates'][1]=gate(2,3.,(1.,0),(1,0),(0,1));self.reason(run([((0,0),0.),((.4,0),.4),((1.4,0),1.4)],c),'ambiguous_simultaneous_finite_gates')
    def test_rejected_state_absorbing(self):
        a=run([((0,0),0.),((-.1,0),0.)]);self.assertRaises(ValueError,a.observe,2,(.1,0),950.,.1)
    def test_completed_state_absorbing(self):
        a=run(PREFIX+[((.2,0),12.2)]);self.assertTrue(a.done);self.assertRaises(ValueError,a.observe,15,(.3,0),950.,12.3)
    def test_nonconsecutive_tick_rejected(self):
        a=run(PREFIX[:2]);self.assertRaises(ValueError,a.observe,3,(1.4,0),950.,1.4);self.assertRaises(ValueError,a.observe,1,(1.4,0),950.,1.4)
    def test_nonfinite_sample_rejected(self):
        a=run(PREFIX[:2]);self.assertRaises(ValueError,a.observe,2,(float('nan'),0),950.,1.4)
    def test_geometry_identity_and_width_validation(self):
        c=contract();c['gates'][0]['center_half_width_m']=0.;self.assertRaises(ValueError,FiniteGateObserver,c);c=contract();c['gates'][0]['tangent']=[2,0];self.assertRaises(ValueError,FiniteGateObserver,c);c=contract();c['gates'][-1]['station_m']=11.;self.assertRaises(ValueError,FiniteGateObserver,c)
    def test_no_arbitrary_elapsed_cut_or_success(self):
        seq=PREFIX[:-1]+[((-.2,0),12.)];a=run(seq)
        for i in range(len(seq),len(seq)+1100):a.observe(i,(-.2,0),900.,12.)
        self.assertFalse(a.done);self.assertIsNone(a.failure);self.assertEqual(a.next_gate,5) # Original runner owns true stall/host/resource failure.

if __name__=='__main__':unittest.main(verbosity=2)
