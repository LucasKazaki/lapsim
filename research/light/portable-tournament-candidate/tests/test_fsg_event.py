"""Real plant probes with an UNTRUSTED predicate double; no native admission.

Fabricated gate intervals and injected failure tests are labeled separately.
"""
from hashlib import sha256
from importlib import resources
from pathlib import Path
import json,unittest
from unittest.mock import patch
from lapsim_light_campaign import fsg_event as ev
from lapsim_light_policies import core_registry
ROOT=Path(__file__).resolve().parents[1]
BASE=(ROOT/'tests/data/fsg_periodic_bspline64_unqualified.json').read_bytes()
PHASE=(ROOT/'tests/data/fsg_smoothed_phase_unqualified.json').read_bytes()
DATA=resources.files('lapsim_light_course').joinpath('data')
BUNDLE=DATA.joinpath('amz_fssim_fsg_approx.json').read_bytes();CONES=DATA.joinpath('FSG.yaml').read_bytes()
EVENT_RECORDS=[]
class UntrustedPredicateDouble:
    implementation_sha256='e'*64
    def residual_low_speed_regen(self,u,electrical):return False
class FsgEventTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.course=ev.FsgNumericalCourse(PHASE,BASE,BUNDLE,CONES,work_wall_s=40.)
    def consumer(self,policy=None,**limits):
        return ev.FsgDevelopmentConsumer(self.course,policy_id=policy or core_registry.IDS[0],residual_regen_rule=UntrustedPredicateDouble(),residual_regen_rule_sha256='e'*64,maximum_ticks=limits.get('maximum_ticks',100),maximum_work=limits.get('maximum_work',800))
    def test_metric_geometry_unchanged_and_offsets_are_projected_metres(self):
        c=self.course;v=json.loads(BASE);g=v['screens']['geometry'];m=c.metadata()
        self.assertEqual(list(c.track.x_m),g['x_m']);self.assertEqual(list(c.track.distance_m),g['distance_m']);self.assertEqual(c.track.cell_count,4096)
        self.assertGreater(m['source_station_offset_m'],5.);self.assertGreater(m['reference_station_offset_m'],5.)
        self.assertNotEqual(m['reference_station_offset_m'],json.loads(PHASE)['root']['representative_parameter_index'])
        self.assertFalse(m['progress_is_exact_new_curve_arclength']);self.assertEqual(m['base_reference_sha256'],sha256(BASE).hexdigest());self.assertEqual(m['phase_sha256'],sha256(PHASE).hexdigest())
    def test_initial_cg_tangent_standing_state_and_progress_zero(self):
        c=self.consumer();s=json.loads(c.snapshot());p=s['state']['thermal']['light']['powered'];m=s['memory']
        self.assertEqual([p['plant']['x_m'],p['plant']['y_m']],self.course.metadata()['initial_cg_xy_m']);self.assertEqual(p['plant']['u_mps'],0.);self.assertEqual(p['plant']['wheel_speeds_rad_s'],[0.]*4);self.assertEqual(p['pack_energy_j'],9000000.)
        self.assertEqual(m['previous_progress'],self.course.metadata()['reference_station_offset_m']);self.assertEqual(m['source_progress_m'],self.course.metadata()['source_station_offset_m']);self.assertEqual(s['relative_reference_progress_m'],0.);self.assertEqual(s['relative_source_progress_m'],0.);self.assertIsNone(s['finish'])
        self.assertEqual(s['context']['guidance_driver']['target_progress_m'],self.course.metadata()['reference_station_offset_m']+self.course.track.length_m)
    def test_missing_or_wrong_pinned_predicate_refused(self):
        for rule,pin in [(None,'e'*64),(UntrustedPredicateDouble(),'d'*64)]:
            with self.subTest(rule=rule),self.assertRaises(ValueError):ev.FsgDevelopmentConsumer(self.course,policy_id=core_registry.IDS[0],residual_regen_rule=rule,residual_regen_rule_sha256=pin,maximum_ticks=10,maximum_work=80)
    def test_unknown_policy_and_noninteger_or_unbounded_caps_refused(self):
        for kw in [dict(policy_id='unknown',maximum_ticks=10,maximum_work=80),dict(policy_id=core_registry.IDS[0],maximum_ticks=True,maximum_work=80),dict(policy_id=core_registry.IDS[0],maximum_ticks=10,maximum_work=81)]:
            with self.subTest(kw=kw),self.assertRaises(ValueError):ev.FsgDevelopmentConsumer(self.course,residual_regen_rule=UntrustedPredicateDouble(),residual_regen_rule_sha256='e'*64,**kw)
    def test_all_seven_real_twenty_tick_probes_with_untrusted_predicate(self):
        records=[]
        for policy in core_registry.IDS:
            c=self.consumer(policy);before=json.loads(c.snapshot());packet=json.loads(c.advance(ticks=20,work_wall_s=10.));after=json.loads(c.snapshot())
            self.assertEqual(after['tick'],20,after.get('violation'));self.assertEqual(after['status'],'running',after.get('violation'));self.assertEqual(after['memory']['driver_updates'],1);self.assertEqual(after['memory']['allocator_updates'],2);self.assertEqual(after['memory']['blend_updates'],20);self.assertEqual(after['state']['thermal']['light']['feedback_ticks'],20)
            self.assertEqual(after['memory']['regen_inhibited_updates'],2)
            self.assertLess(after['state']['thermal']['light']['powered']['pack_energy_j'],9000000.);self.assertFalse(after['qualification_or_execution_authority']);self.assertIsNone(after['finish']);self.assertEqual(packet['end_snapshot_sha256'],sha256(c.snapshot()).hexdigest())
            records.append({'policy':policy,'initial_snapshot':before,'packet':packet,'final_snapshot':after})
        self.assertEqual(len({r['initial_snapshot']['state_sha256'] for r in records}),1)
        EVENT_RECORDS.append({'role':'real_seven_policy_20ms_plant_probes_with_untrusted_predicate_not_course_laps','records':records,'qualification_or_execution_authority':False})
    def test_split_call_fixed_clocks_and_state_match_single_call(self):
        one=self.consumer();two=self.consumer();one.advance(ticks=20,work_wall_s=10.);two.advance(ticks=7,work_wall_s=10.);two.advance(ticks=13,work_wall_s=10.);self.assertEqual(one.snapshot(),two.snapshot())
    def test_time_limit_does_not_report_finish_or_allow_retry(self):
        c=self.consumer(maximum_ticks=1,maximum_work=8);c.advance(ticks=2,work_wall_s=10.);s=json.loads(c.snapshot());self.assertEqual(s['status'],'time_limit');self.assertEqual(s['tick'],1);self.assertIsNone(s['finish'])
        with self.assertRaises(ValueError):c.advance(ticks=1,work_wall_s=1.)
    def test_cancellation_retains_state_and_is_terminal_without_tick(self):
        c=self.consumer();old=json.loads(c.snapshot())['state'];c.request_cancel();c.advance(ticks=1,work_wall_s=1.);s=json.loads(c.snapshot());self.assertEqual(s['status'],'cancelled');self.assertEqual(s['tick'],0);self.assertEqual(s['state'],old);self.assertIsNone(s['finish'])
    def test_failed_provisional_step_retained_without_committing_state(self):
        c=self.consumer();old=json.loads(c.snapshot())['state']
        with patch.object(ev,'advance_tick',side_effect=ValueError('injected plant failure; not a numerical result')):packet=json.loads(c.advance(ticks=1,work_wall_s=1.))
        s=json.loads(c.snapshot());self.assertEqual(s['status'],'invalid');self.assertEqual(s['tick'],0);self.assertEqual(s['state'],old);self.assertTrue(s['rejected_attempt']['unreturned_numerical_work_unknown']);self.assertEqual(s['rejected_attempt']['stage'],'plant');self.assertIsNone(s['finish']);self.assertEqual(packet['status'],'invalid')
    def test_post_step_failure_retains_raw_trial_and_last_accepted_state(self):
        c=self.consumer();old=json.loads(c.snapshot())['state'];original=c._observe
        def observe(state,memory,tick):
            if tick:raise ValueError('injected post-step refusal')
            return original(state,memory,tick)
        with patch.object(c,'_observe',side_effect=observe):c.advance(ticks=1,work_wall_s=2.)
        s=json.loads(c.snapshot());self.assertEqual(s['status'],'invalid');self.assertEqual(s['state'],old);self.assertEqual(s['tick'],0);self.assertEqual(s['rejected_attempt']['stage'],'post_step');self.assertIsNotNone(s['rejected_attempt']['provisional_state']);self.assertGreater(s['attempted_numerical_work'],0);self.assertFalse(s['rejected_attempt']['committed'])
    def gate_case(self,**overrides):
        c=self.course;g=json.loads(PHASE)['gate'];o=g['origin_xy_m'];n=g['forward_unit'];a=tuple(o[i]-.01*n[i] for i in (0,1));b=tuple(o[i]+.01*n[i] for i in (0,1))
        args=dict(departed=True,armed=True,tick=100,before_xy=a,after_xy=b,before_pack_j=8999900.,after_pack_j=8999898.,before_relative_reference_m=c.track.length_m-.01,after_relative_reference_m=c.track.length_m+.01,before_relative_source_m=c.source.source_track.length_m-.01,after_relative_source_m=c.source.source_track.length_m+.01);args.update(overrides);return ev.event_transition(c,**args)
    def test_metric_progress_cannot_alone_finish(self):
        g=json.loads(PHASE)['gate'];o=g['origin_xy_m'];n=g['forward_unit'];a=tuple(o[i]+.1*n[i] for i in (0,1));b=tuple(o[i]+.11*n[i] for i in (0,1));self.assertIsNone(self.gate_case(before_xy=a,after_xy=b)[1])
    def test_initial_forward_crossing_not_a_finished_lap(self):
        flags,finish=self.gate_case(departed=False,armed=False,before_relative_reference_m=0.,after_relative_reference_m=.02,before_relative_source_m=0.,after_relative_source_m=.02);self.assertEqual(flags,(False,False));self.assertIsNone(finish)
    def test_finish_requires_both_windings_and_departure(self):
        with self.assertRaises(ValueError):self.gate_case(armed=False,before_relative_source_m=10.,after_relative_source_m=10.02)
        with self.assertRaises(ValueError):self.gate_case(armed=False)
        flags,finish=self.gate_case();self.assertEqual(flags,(True,True));self.assertTrue(.099<finish['time_s']<.1);self.assertTrue(8999898.<finish['pack_energy_j']<8999900.);self.assertFalse(finish['qualification_or_execution_authority']);self.assertIsNone(finish['awards']);EVENT_RECORDS.append({'role':'fabricated_gate_interval_unit_case_not_completed_physical_lap','finish':finish,'qualification_or_execution_authority':False})
    def test_changed_phase_bytes_rejected_by_complete_readback(self):
        raw=PHASE.replace(b'GEOMETRIC_GATE_PHASE_DEVELOPMENT_ONLY',b'GEOMETRIC_GATE_PHASE_DEVELOPMENT_FAIL')
        with self.assertRaises(ValueError):ev.FsgNumericalCourse(raw,BASE,BUNDLE,CONES,work_wall_s=1.)
    def test_unexpected_plant_error_is_terminal_and_work_total_is_lower_bound(self):
        c=self.consumer();old=json.loads(c.snapshot())['state']
        with patch.object(ev,'advance_tick',side_effect=RuntimeError('injected unexpected plant error')):
            with self.assertRaises(RuntimeError):c.advance(ticks=1,work_wall_s=2.)
        s=json.loads(c.snapshot());self.assertEqual(s['status'],'invalid');self.assertEqual(s['state'],old)
        self.assertTrue(s['attempted_numerical_work_is_lower_bound']);self.assertTrue(s['rejected_attempt']['unreturned_numerical_work_unknown'])
        with self.assertRaises(ValueError):c.advance(ticks=1,work_wall_s=1.)
    def test_late_post_step_predicate_cannot_commit_last_requested_tick(self):
        c=self.consumer();old=json.loads(c.snapshot())['state'];clock=[0.];original=c._observe
        def observe(state,memory,tick):
            result=original(state,memory,tick)
            if tick:clock[0]=2.
            return result
        with patch.object(ev,'monotonic',side_effect=lambda:clock[0]),patch.object(c,'_observe',side_effect=observe):
            with self.assertRaises(ev.FsgDevelopmentDeadlineExceeded) as result:c.advance(ticks=1,work_wall_s=1.)
        s=json.loads(c.snapshot());self.assertEqual(s['status'],'wall_limit');self.assertEqual(s['tick'],0);self.assertEqual(s['state'],old);self.assertIsNone(s['finish'])
        self.assertIsNotNone(s['rejected_attempt']['provisional_state']);self.assertEqual(s['quarantined_interval_sha256'],sha256(result.exception.raw_interval).hexdigest())
    def test_late_final_serialization_quarantines_bytes_and_keeps_accepted_state(self):
        c=self.consumer();clock=[0.];original=ev.encode
        def encode(value):
            raw=original(value)
            if type(value) is dict and value.get('schema')==ev.INTERVAL_SCHEMA:clock[0]=2.
            return raw
        with patch.object(ev,'monotonic',side_effect=lambda:clock[0]),patch.object(ev,'encode',side_effect=encode):
            with self.assertRaises(ev.FsgDevelopmentDeadlineExceeded) as error:c.advance(ticks=1,work_wall_s=1.)
        s=json.loads(c.snapshot());self.assertEqual(s['status'],'wall_limit');self.assertEqual(s['tick'],1);self.assertIsNone(s['finish']);self.assertEqual(s['rejected_attempt']['stage'],'finalization')
        self.assertFalse(error.exception.qualification_or_execution_authority)
    def test_snapshot_nonblocking_lock_owned_during_serialization(self):
        c=self.consumer();original=c._snapshot;seen=[]
        def snap():seen.append(c._lock.locked());return original()
        with patch.object(c,'_snapshot',side_effect=snap):c.snapshot()
        self.assertEqual(seen,[True]);self.assertFalse(c._lock.locked())
        c._lock.acquire()
        try:
            with self.assertRaises(ValueError):c.snapshot()
        finally:c._lock.release()
    def test_reverse_finite_gate_crossing_after_departure_is_invalid(self):
        g=json.loads(PHASE)['gate'];o=g['origin_xy_m'];n=g['forward_unit'];a=tuple(o[i]+.01*n[i] for i in (0,1));b=tuple(o[i]-.01*n[i] for i in (0,1))
        with self.assertRaisesRegex(ValueError,'Reverse'):self.gate_case(before_xy=a,after_xy=b)
    def test_late_controls_cannot_start_new_plant_work(self):
        c=self.consumer();clock=[0.];original=ev._controller
        def controller(*args):
            value=original(*args);clock[0]=2.;return value
        with patch.object(ev,'monotonic',side_effect=lambda:clock[0]),patch.object(ev,'_controller',side_effect=controller),patch.object(ev,'advance_tick') as plant:
            with self.assertRaises(ev.FsgDevelopmentDeadlineExceeded):c.advance(ticks=1,work_wall_s=1.)
        s=json.loads(c.snapshot());plant.assert_not_called();self.assertEqual(s['tick'],0);self.assertEqual(s['attempted_numerical_work'],0)
        self.assertFalse(s['attempted_numerical_work_is_lower_bound']);self.assertEqual(s['rejected_attempt']['stage'],'pre_plant')
    def test_refused_retry_keeps_fabricated_completed_fixture_exact(self):
        # Lifecycle fixture ONLY, not a completed physical lap or result receipt.
        c=self.consumer();c._status='development_completed';c._finish={'role':'fabricated_terminal_lifecycle_fixture_only'}
        before=c.snapshot()
        with self.assertRaises(ValueError):c.advance(ticks=1,work_wall_s=1.)
        self.assertEqual(c.snapshot(),before)
    def test_interrupted_publication_restores_entire_accepted_record(self):
        c=self.consumer();before=json.loads(c.snapshot());original=c._publish_boundary
        def publish(boundary):original(boundary);raise KeyboardInterrupt('injected publication interruption')
        with patch.object(c,'_publish_boundary',side_effect=publish):
            with self.assertRaises(KeyboardInterrupt):c.advance(ticks=1,work_wall_s=2.)
        after=json.loads(c.snapshot());self.assertEqual(after['status'],'invalid')
        for key in ('state','memory','tick','departed','armed','finish'):self.assertEqual(after[key],before[key])
        self.assertEqual(after['rejected_attempt']['stage'],'publication');self.assertIsNotNone(after['rejected_attempt']['provisional_state'])
        self.assertGreater(after['attempted_numerical_work'],0);self.assertFalse(after['attempted_numerical_work_is_lower_bound'])
if __name__=='__main__':unittest.main()
