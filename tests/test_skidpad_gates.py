"""Synthetic CG traces test measurements only, never physical/official completion."""
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
import json
from math import cos, pi, sin
import unittest

from lapsim.events.skidpad_gates import (
    GatePose, OrderedSkidpadGates, PHASES, RADIUS_M, MAX_OBSERVATIONS,
    WINDING_CLOSURE_TOLERANCE_RAD,
)


def pose(tick, x, y, *, time_s=None):
    return GatePose(tick, tick*.01 if time_s is None else time_s, x, y,
                    18_000_000.-tick, sha256(('SYNTHETIC-NOT-PHYSICAL-'+str(tick)).encode()).hexdigest())


def correct_trace(*, exit_length=5., exit_step=.25, y_offset=0., first_side='right'):
    points = [(-5.+.25*i,y_offset) for i in range(20)]
    # Half-step samples straddle shared gates: no cell endpoint is substituted
    # for the actual endpoint-chord intersection, including the right/left join.
    for side in (first_side, 'left' if first_side=='right' else 'right'):
        for i in range(720):
            angle=(i+.5)*2*pi/360
            x=RADIUS_M*sin(angle)
            y=RADIUS_M*(1-cos(angle))
            points.append((x, (-y if side=='right' else y)+y_offset))
    count=max(1,int(exit_length/exit_step))
    points.extend((exit_step*i,y_offset) for i in range(1,count+1))
    if points[-1][0] < exit_length:
        points.append((exit_length,y_offset))
    return [pose(i,x,y) for i,(x,y) in enumerate(points)]


def feed(ledger, trace):
    for value in trace:
        ledger.observe(value)
        if ledger.completed or ledger.failure_reason is not None:
            break
    return ledger


class OrderedModelGateTests(unittest.TestCase):
    def test_complete_synthetic_right_right_left_left_trace_in_exact_order(self):
        ledger=feed(OrderedSkidpadGates(5.),correct_trace())
        self.assertTrue(ledger.completed)
        self.assertIsNone(ledger.failure_reason)
        self.assertEqual([c['phase'] for c in ledger.crossings],list(PHASES))
        self.assertEqual(len(ledger.crossings),6)
        for crossing in ledger.crossings:
            before,after=crossing['before'],crossing['after']
            f=crossing['fraction']
            self.assertLessEqual(0.,f)
            self.assertLessEqual(f,1.)
            self.assertEqual(after['tick'],before['tick']+1)
            self.assertEqual(crossing['time_s'],before['time_s']+f*(after['time_s']-before['time_s']))
            self.assertEqual(crossing['pack_energy_j'],before['pack_energy_j']+f*(after['pack_energy_j']-before['pack_energy_j']))
            self.assertIn('state_sha256',before)
            self.assertIn('state_sha256',after)
            self.assertNotIn('interpolated_state',crossing)
        report=ledger.to_dict()
        self.assertFalse(report['qualification_or_execution_authority'])
        self.assertFalse(report['official_track_bound_or_cone_clearance_checked'])
        self.assertFalse(report['state_hashes_independently_authenticated'])
        self.assertEqual(json.loads(json.dumps(report)),report)

    def test_shared_central_crossings_split_winding_and_change_active_circle(self):
        ledger=feed(OrderedSkidpadGates(5.),correct_trace())
        for crossing in ledger.crossings[1:5]:
            self.assertGreater(crossing['fraction'],0.)
            self.assertLess(crossing['fraction'],1.)
            expected=-2*pi if crossing['phase'].startswith('RIGHT') else 2*pi
            self.assertLessEqual(abs(crossing['signed_winding_rad']-expected),WINDING_CLOSURE_TOLERANCE_RAD)

    def test_final_central_and_short_exit_can_share_one_accepted_interval(self):
        trace=correct_trace(exit_length=.25,exit_step=.5)
        ledger=feed(OrderedSkidpadGates(.25),trace)
        self.assertTrue(ledger.completed)
        central,exit_crossing=ledger.crossings[-2:]
        self.assertEqual(central['before'],exit_crossing['before'])
        self.assertEqual(central['after'],exit_crossing['after'])
        self.assertLess(central['fraction'],exit_crossing['fraction'])
        self.assertLess(central['time_s'],exit_crossing['time_s'])

    def test_exact_final_central_endpoint_cannot_reverse_return_and_then_exit(self):
        original=correct_trace()
        complete=feed(OrderedSkidpadGates(5.),original)
        before_tick=complete.crossings[-2]['before']['tick']
        prefix=original[:before_tick+1]
        boundary=pose(before_tick+1,0.,0.)
        ledger=feed(OrderedSkidpadGates(5.),prefix+[boundary])
        self.assertEqual([c['phase'] for c in ledger.crossings],list(PHASES[:-1]))
        self.assertIsNone(ledger.failure_reason)
        ledger.observe(pose(boundary.tick+1,-.25,0.))
        self.assertIn('Returned through the central gate',ledger.failure_reason)
        self.assertFalse(ledger.completed)
        self.assertEqual(ledger.trace[-1].x_m,-.25)
        self.assertNotIn('EXIT',[c['phase'] for c in ledger.crossings])
        # Once the backward departure is observed, returning to the plane or
        # later reaching EXIT cannot revive this attempt.
        for x in (0.,5.):
            with self.subTest(return_or_exit=x),self.assertRaises(ValueError):
                ledger.observe(pose(boundary.tick+2,x,0.))
        self.assertFalse(ledger.completed)

    def test_exact_entry_and_circle_endpoints_cannot_depart_backwards(self):
        entry=OrderedSkidpadGates(5.)
        feed(entry,[pose(0,-.25,0.),pose(1,0.,0.)])
        original=correct_trace()
        complete=feed(OrderedSkidpadGates(5.),original)
        before_tick=complete.crossings[1]['before']['tick']
        circle=feed(OrderedSkidpadGates(5.),original[:before_tick+1]+[pose(before_tick+1,0.,0.)])
        for ledger in (entry,circle):
            with self.subTest(next_phase=ledger.to_dict()['next_phase']):
                previous_count=len(ledger.crossings)
                boundary=ledger.trace[-1]
                ledger.observe(pose(boundary.tick+1,-.25,0.))
                self.assertIn('Wrong direction',ledger.failure_reason)
                self.assertEqual(len(ledger.crossings),previous_count)
                self.assertFalse(ledger.completed)

    def test_forward_departure_from_exact_plane_does_not_duplicate_a_receipt(self):
        ledger=OrderedSkidpadGates(5.)
        feed(ledger,[pose(0,-.25,0.),pose(1,0.,0.),pose(2,.25,0.)])
        self.assertEqual([c['phase'] for c in ledger.crossings],['ENTRY'])
        self.assertIsNone(ledger.failure_reason)

    def test_wrong_first_circle_never_receives_a_timed_gate(self):
        ledger=feed(OrderedSkidpadGates(5.),correct_trace(first_side='left'))
        self.assertFalse(ledger.completed)
        self.assertIsNotNone(ledger.failure_reason)
        self.assertEqual([c['phase'] for c in ledger.crossings],['ENTRY'])

    def test_shortcut_back_through_central_gate_fails_closed(self):
        ledger=OrderedSkidpadGates(5.)
        feed(ledger,[pose(0,-.25,0.),pose(1,.25,0.),pose(2,-.25,0.)])
        self.assertFalse(ledger.completed)
        self.assertIn('Wrong direction',ledger.failure_reason)
        self.assertEqual(len(ledger.trace),3)
        self.assertEqual(len(ledger.crossings),1)

    def test_forward_shortcut_without_full_winding_fails_closed(self):
        ledger=OrderedSkidpadGates(5.)
        points=[(-.25,0.),(.25,0.),(.25,-1.),(-.25,-1.)]
        # Move behind the plane outside the finite central gate, then return
        # through its forward face without winding around the circle centre.
        points=[(-.25,0.),(.25,0.),(.25,-.75),(.25,-1.5),(.25,-2.),
                (-.25,-2.),(-.25,-1.5),(-.25,-.75),(-.25,0.),(.25,0.)]
        feed(ledger,[pose(i,x,y) for i,(x,y) in enumerate(points)])
        self.assertFalse(ledger.completed)
        self.assertIn('full ordered winding',ledger.failure_reason)
        self.assertEqual(len(ledger.crossings),1)

    def test_finite_gate_miss_does_not_become_a_station_or_exit_completion(self):
        ledger=feed(OrderedSkidpadGates(5.),correct_trace(y_offset=2.))
        self.assertFalse(ledger.completed)
        self.assertEqual(ledger.crossings,())
        self.assertEqual(ledger.to_dict()['next_phase'],'ENTRY')

    def test_excessive_displacement_retains_failure_triggering_observation(self):
        ledger=OrderedSkidpadGates(5.)
        feed(ledger,[pose(0,-3.,0.),pose(1,-1.,0.)])
        self.assertIn('displacement',ledger.failure_reason)
        self.assertEqual(ledger.trace[-1].tick,1)
        self.assertFalse(ledger.completed)

    def test_excessive_angular_step_near_centre_is_rejected(self):
        points=[(-.1,0.),(.01,0.)]
        points.extend((.01,-.1*i) for i in range(1,92))
        points.extend([(.01,-RADIUS_M+.01),(.01,-RADIUS_M-.01)])
        ledger=feed(OrderedSkidpadGates(5.),[pose(i,x,y) for i,(x,y) in enumerate(points)])
        self.assertIsNotNone(ledger.failure_reason)
        self.assertIn('angle',ledger.failure_reason)
        self.assertFalse(ledger.completed)

    def test_replay_reconstructs_identical_gate_measurements_from_full_trace(self):
        ledger=feed(OrderedSkidpadGates(5.),correct_trace())
        restored=OrderedSkidpadGates.from_trace(ledger.to_dict()['trace'],exit_length_m=5.)
        self.assertEqual(restored.to_dict(),ledger.to_dict())
        self.assertEqual(OrderedSkidpadGates.from_trace(ledger.trace,exit_length_m=5.).to_dict(),ledger.to_dict())

    def test_changed_trace_is_not_the_same_measurement_or_authentication(self):
        ledger=feed(OrderedSkidpadGates(5.),correct_trace())
        altered=deepcopy(ledger.to_dict()['trace'])
        tick=ledger.crossings[0]['after']['tick']
        altered[tick]['state_sha256']='0'*64
        replayed=OrderedSkidpadGates.from_trace(altered,exit_length_m=5.)
        self.assertNotEqual(replayed.to_dict()['trace_sha256'],ledger.to_dict()['trace_sha256'])
        self.assertNotEqual(replayed.to_dict()['ledger_sha256'],ledger.to_dict()['ledger_sha256'])
        self.assertNotEqual(replayed.crossings[0]['crossing_sha256'],ledger.crossings[0]['crossing_sha256'])
        # The geometry alone cannot authenticate a declared full-state hash.
        self.assertFalse(replayed.to_dict()['state_hashes_independently_authenticated'])

    def test_scalar_completion_or_extra_pose_fields_cannot_authorize_replay(self):
        with self.assertRaises(ValueError):
            OrderedSkidpadGates.from_trace({'completed':True},exit_length_m=5.)
        with self.assertRaises(ValueError):
            OrderedSkidpadGates.from_trace([{**asdict(pose(0,-1.,0.)),'completed':True}],exit_length_m=5.)
        with self.assertRaises(ValueError):
            OrderedSkidpadGates.from_trace((pose(0,-1.,0.) for _ in range(2)),exit_length_m=5.)

    def test_constructor_and_pose_domains_reject_nonfinite_boolean_and_oversized_values(self):
        for value in (0.,-1.,True,float('nan'),float('inf'),10_001.):
            with self.subTest(exit=value),self.assertRaises(ValueError):
                OrderedSkidpadGates(value)
        for width in (0.,-1.,True,float('nan'),RADIUS_M):
            with self.subTest(width=width),self.assertRaises(ValueError):
                OrderedSkidpadGates(5.,width)
        for changes in ({'tick':True},{'tick':-1},{'tick':MAX_OBSERVATIONS},
                        {'time_s':float('nan')},{'time_s':True},{'x_m':float('inf')},
                        {'x_m':10_001.},{'pack_energy_j':-1.},{'pack_energy_j':True},
                        {'state_sha256':'not-a-state-hash'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                replace(pose(0,-1.,0.),**changes)

    def test_first_pose_and_clock_order_are_checked_without_losing_valid_prefix(self):
        for first in (pose(1,-1.,0.),pose(0,0.,0.),pose(0,1.,0.)):
            ledger=OrderedSkidpadGates(5.)
            with self.assertRaises(ValueError):
                ledger.observe(first)
            self.assertEqual(ledger.trace,())
        ledger=OrderedSkidpadGates(5.)
        ledger.observe(pose(0,-1.,0.))
        for other in (pose(2,-.9,0.),pose(1,-.9,0.,time_s=0.)):
            with self.assertRaises(ValueError):
                ledger.observe(other)
            self.assertEqual(len(ledger.trace),1)

    def test_terminal_attempt_and_returned_crossings_cannot_be_mutated(self):
        ledger=feed(OrderedSkidpadGates(5.),correct_trace())
        original=ledger.to_dict()
        ledger.crossings[0]['phase']='FORGED'
        self.assertEqual(ledger.to_dict(),original)
        last=ledger.trace[-1]
        with self.assertRaises(ValueError):
            ledger.observe(pose(last.tick+1,last.x_m+.1,last.y_m))
        self.assertEqual(ledger.to_dict(),original)

    def test_exact_10001_observation_bound_is_retained(self):
        ledger=OrderedSkidpadGates(5.)
        for tick in range(MAX_OBSERVATIONS):
            ledger.observe(pose(tick,-1.+tick*1e-5,0.))
        self.assertEqual(len(ledger.trace),MAX_OBSERVATIONS)
        self.assertFalse(ledger.completed)
        with self.assertRaises(ValueError):
            OrderedSkidpadGates.from_trace([pose(0,-1.,0.)]*(MAX_OBSERVATIONS+1),exit_length_m=5.)


if __name__=='__main__':
    unittest.main()
