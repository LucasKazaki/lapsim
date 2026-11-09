"""Cooperative raw-worker cancellation, with explicitly UNTRUSTED predicates.

Real short numerical ticks and deterministic injected races are separate test
fixtures. No original predicate, native Stop, resource/lease or cleanup is used.
"""
from hashlib import sha256
from importlib import resources
from pathlib import Path
from threading import Event,Thread
from unittest.mock import patch
import json,unittest
from lapsim_light_campaign import fsg_event as ev,fsg_checkpoint as cp,fsg_worker as w
ROOT=Path(__file__).resolve().parents[1]
CANCEL_RECORDS=[]
class UntrustedRule:
    implementation_sha256='e'*64
    value=False
    def residual_low_speed_regen(self,u,e):return self.value

def pin(raw):return sha256(raw).hexdigest()

class WorkerCancellationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data=resources.files('lapsim_light_course').joinpath('data')
        cls.course=ev.FsgNumericalCourse((ROOT/'tests/data/fsg_smoothed_phase_unqualified.json').read_bytes(),
            (ROOT/'tests/data/fsg_periodic_bspline64_unqualified.json').read_bytes(),
            data.joinpath('amz_fssim_fsg_approx.json').read_bytes(),data.joinpath('FSG.yaml').read_bytes(),work_wall_s=40.)
        cls.identity=cp.identity_for(cls.course,source_manifest_sha256='a'*64,environment_sha256='b'*64,residual_rule_sha256='e'*64)
        c=ev.FsgDevelopmentConsumer(cls.course,policy_id=ev.core_registry.IDS[0],residual_regen_rule=UntrustedRule(),
            residual_regen_rule_sha256='e'*64,maximum_ticks=100,maximum_work=800)
        cls.origin=cp.origin_checkpoint(c,cls.identity)
        rec=c.advance_with_snapshots(ticks=5,maximum_new_work=40,work_wall_s=5.)
        cls.parent=cp.extend_checkpoint(cls.origin,rec,expected_parent_raw_sha256=pin(cls.origin),expected_identity=cls.identity)
    def program(self,*,parent=None,wall=5.):
        raw=self.origin if parent is None else parent
        request=w.prepare_request(raw,expected_identity=self.identity,expected_checkpoint_raw_sha256=pin(raw),
            requested_ticks=5,extension_work_cap=40,maximum_total_plant_work=200,maximum_wall_s=wall)
        return w.FsgReplayWorker(request,raw,expected_request_raw_sha256=pin(request))
    def execute(self,program,rule=None):return program.execute(course=self.course,residual_regen_rule=UntrustedRule() if rule is None else rule)
    def test_pending_cancel_consumes_attempt_without_initialization_or_plant(self):
        p=self.program();self.assertTrue(p.request_cancel())
        with patch.object(ev,'initialize_combined_light') as init,patch.object(ev,'advance_tick') as plant:
            with self.assertRaises(w.FsgReplayCancelled):self.execute(p)
        init.assert_not_called();plant.assert_not_called();s=p.snapshot()
        self.assertEqual(s['phase'],'cancelled');self.assertTrue(s['finished']);self.assertEqual(s['actual_worker_work'],0)
        self.assertIsNone(s['last_record']);self.assertIsNone(s['child_checkpoint_raw']);self.assertIsNone(p._active_consumer)
    def test_cancel_during_initialization_is_forwarded_when_consumer_attaches(self):
        p=self.program();accepted=[]
        class DuringInit(UntrustedRule):
            def residual_low_speed_regen(self,u,e):accepted.append(p.request_cancel());return False
        with patch.object(ev,'advance_tick') as plant:
            with self.assertRaises(w.FsgReplayCancelled):self.execute(p,DuringInit())
        plant.assert_not_called();s=p.snapshot();self.assertTrue(all(accepted));self.assertEqual(s['phase'],'cancelled')
        self.assertEqual(s['actual_worker_work'],0);self.assertTrue(json.loads(s['last_snapshot_raw'])['cancellation_requested'])
    def cancelled_tick(self,*,replaying):
        p=self.program(parent=self.parent if replaying else self.origin);original=ev.advance_tick;accepted=[]
        def tick(*args,**kw):
            value=original(*args,**kw);accepted.append(p.request_cancel());return value
        with patch.object(ev,'advance_tick',side_effect=tick):
            with self.assertRaises(w.FsgReplayCancelled):self.execute(p)
        s=p.snapshot();self.assertEqual(accepted,[True]);self.assertEqual(s['phase'],'cancelled');self.assertTrue(s['finished'])
        self.assertIsNone(s['child_checkpoint_raw']);self.assertIsNotNone(s['last_record']);self.assertGreater(s['actual_worker_work'],0)
        self.assertFalse(s['actual_work_is_lower_bound']);self.assertIsNone(p._active_consumer)
        after=json.loads(s['last_record'].after_raw);self.assertTrue(after['cancellation_requested']);self.assertEqual(after['tick'],1)
        self.assertEqual(pin(s['last_record'].after_raw),json.loads(s['last_record'].interval_raw)['end_snapshot_sha256'])
        CANCEL_RECORDS.append({'role':'cooperative_inflight_cancel_with_UNTRUSTED_predicate_not_native_Stop',
            'during_replay':replaying,'actual_worker_work':s['actual_worker_work'],'replay_work':s['replay_work'],
            'extension_work':s['extension_work'],'after_snapshot':after,'qualification_or_execution_authority':False})
        return s
    def test_cancel_during_replay_retains_work_and_never_extends(self):
        s=self.cancelled_tick(replaying=True);self.assertGreater(s['replay_work'],0);self.assertEqual(s['extension_work'],0)
    def test_cancel_during_extension_retains_literal_partial_output(self):
        s=self.cancelled_tick(replaying=False);self.assertEqual(s['replay_work'],0);self.assertGreater(s['extension_work'],0)
    def test_accepted_cancel_before_seal_quarantines_computed_child(self):
        p=self.program();original=cp.extend_checkpoint;accepted=[]
        def extend(*args,**kw):raw=original(*args,**kw);accepted.append(p.request_cancel());return raw
        with patch.object(cp,'extend_checkpoint',side_effect=extend):
            with self.assertRaises(w.FsgReplayCancelled):self.execute(p)
        s=p.snapshot();self.assertEqual(accepted,[True]);self.assertIsNone(s['child_checkpoint_raw']);self.assertIsNotNone(s['quarantined_child_checkpoint_raw'])
        self.assertEqual(s['phase'],'cancelled');self.assertIsNotNone(s['last_record'])
    def test_cancel_racing_publication_is_ordered_by_the_same_lifecycle_lock(self):
        p=self.program();inside=Event();release=Event();attempted=Event();results=[];errors=[];cancel=[];original=p._publish_child
        def publish(raw):
            original(raw);inside.set()
            if not release.wait(2.):raise RuntimeError('bounded publication test timed out')
        def run():
            try:results.append(self.execute(p))
            except BaseException as e:errors.append(e)
        def request():attempted.set();cancel.append(p.request_cancel())
        t=Thread(target=run);ct=Thread(target=request)
        try:
            with patch.object(p,'_publish_child',side_effect=publish):
                t.start();self.assertTrue(inside.wait(3.));ct.start();self.assertTrue(attempted.wait(1.));release.set();t.join(3.);ct.join(3.)
        finally:
            release.set()
            if t.ident is not None:t.join(3.)
            if ct.ident is not None:ct.join(3.)
        self.assertFalse(t.is_alive());self.assertFalse(ct.is_alive());self.assertEqual(errors,[]);self.assertEqual(len(results),1)
        self.assertEqual(cancel,[False]);before=p.snapshot();self.assertFalse(p.request_cancel());self.assertEqual(p.snapshot(),before)
    def test_cancel_after_return_and_refused_retry_leave_result_immutable(self):
        p=self.program();result=self.execute(p);before=p.snapshot();self.assertFalse(p.request_cancel())
        self.assertEqual(p.snapshot(),before);self.assertIsNotNone(result.child_checkpoint_raw)
        with self.assertRaises(ValueError):self.execute(p)
        self.assertEqual(p.snapshot(),before);self.assertIsNone(p._active_consumer)
    def test_genuine_failure_wins_over_simultaneous_cancel_and_keeps_unknown_work(self):
        p=self.program();error=RuntimeError('injected real-call failure and cancellation')
        def tick(*args,**kw):p.request_cancel();raise error
        with patch.object(ev,'advance_tick',side_effect=tick):
            with self.assertRaises(RuntimeError) as result:self.execute(p)
        self.assertIs(result.exception,error);s=p.snapshot();self.assertEqual(s['phase'],'failed');self.assertTrue(s['cancellation_requested'])
        self.assertTrue(s['actual_work_is_lower_bound']);self.assertIsNone(s['child_checkpoint_raw'])
    def test_deadline_crossing_during_publication_cannot_seal_success(self):
        p=self.program(wall=1.);clock=[0.];original=p._publish_child
        def publish(raw):original(raw);clock[0]=2.
        with patch.object(w,'monotonic',side_effect=lambda:clock[0]),patch.object(p,'_publish_child',side_effect=publish):
            with self.assertRaises(w.ReplayWorkerDeadlineExceeded):self.execute(p)
        s=p.snapshot();self.assertIsNone(s['child_checkpoint_raw']);self.assertIsNotNone(s['quarantined_child_checkpoint_raw'])
        self.assertEqual(s['phase'],'quarantined_finalization');self.assertTrue(s['finished'])
    def test_cancel_accepted_during_identity_check_stops_before_initialization(self):
        p=self.program();original=cp.identity_for
        def identity(*args,**kw):value=original(*args,**kw);self.assertTrue(p.request_cancel());return value
        with patch.object(cp,'identity_for',side_effect=identity),patch.object(ev,'initialize_combined_light',wraps=ev.initialize_combined_light) as init:
            with self.assertRaises(w.FsgReplayCancelled):self.execute(p)
        init.assert_not_called();self.assertEqual(p.snapshot()['actual_worker_work'],0)
    def test_returned_numerical_rejection_wins_over_simultaneous_cancellation(self):
        p=self.program();rule=UntrustedRule();original=ev.advance_tick
        def tick(*args,**kw):
            result=original(*args,**kw);p.request_cancel();rule.value=True;return result
        with patch.object(ev,'advance_tick',side_effect=tick):
            with self.assertRaises(RuntimeError) as error:self.execute(p,rule)
        self.assertNotIsInstance(error.exception,w.FsgReplayCancelled);s=p.snapshot();self.assertEqual(s['phase'],'failed')
        self.assertTrue(s['cancellation_requested']);self.assertGreater(s['actual_worker_work'],0);self.assertFalse(s['actual_work_is_lower_bound'])
        self.assertEqual(json.loads(s['last_record'].after_raw)['status'],'invalid');self.assertIsNone(s['child_checkpoint_raw'])
if __name__=='__main__':unittest.main()
