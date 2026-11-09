"""Short replay tests use REAL physics and explicitly UNTRUSTED predicate inputs.

No original source/environment authentication or native ownership/cleanup is
provided. The 1000-tick replay profile is not a full-course tournament interface.
"""
from copy import deepcopy
from hashlib import sha256
from importlib import resources
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
import json,unittest
from lapsim_light_campaign import fsg_event as ev,fsg_checkpoint as cp,fsg_worker as worker
from lapsim_light_campaign.input_contracts import encode,digest
ROOT=Path(__file__).resolve().parents[1]
REPLAY_RECORDS=[]
class UntrustedRule:
    implementation_sha256='e'*64
    def residual_low_speed_regen(self,u,e):return False

class BrokenMessage(RuntimeError):
    def __str__(self):raise RuntimeError('injected diagnostic formatting failure')

def pin(raw):return sha256(raw).hexdigest()

def reseal(value):return encode({'checkpoint':value,'checkpoint_sha256':digest(value)})

class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data=resources.files('lapsim_light_course').joinpath('data')
        cls.course=ev.FsgNumericalCourse((ROOT/'tests/data/fsg_smoothed_phase_unqualified.json').read_bytes(),
            (ROOT/'tests/data/fsg_periodic_bspline64_unqualified.json').read_bytes(),
            data.joinpath('amz_fssim_fsg_approx.json').read_bytes(),data.joinpath('FSG.yaml').read_bytes(),work_wall_s=40.)
        cls.identity=cp.identity_for(cls.course,source_manifest_sha256='a'*64,environment_sha256='b'*64,residual_rule_sha256='e'*64)
        cls.initial=cls.consumer();cls.origin=cp.origin_checkpoint(cls.initial,cls.identity)
        cls.first=cls.initial.advance_with_snapshots(ticks=31,maximum_new_work=248,work_wall_s=10.)
        cls.parent=cp.extend_checkpoint(cls.origin,cls.first,expected_parent_raw_sha256=pin(cls.origin),expected_identity=cls.identity)
    @classmethod
    def consumer(cls,*,maximum_ticks=100):
        return ev.FsgDevelopmentConsumer(cls.course,policy_id=ev.core_registry.IDS[0],residual_regen_rule=UntrustedRule(),
            residual_regen_rule_sha256='e'*64,maximum_ticks=maximum_ticks,maximum_work=800 if maximum_ticks==100 else 8*maximum_ticks)
    def program(self,parent=None,identity=None,**kw):
        raw=self.parent if parent is None else parent;identity=self.identity if identity is None else identity
        request=worker.prepare_request(raw,expected_identity=identity,expected_checkpoint_raw_sha256=pin(raw),requested_ticks=kw.get('ticks',34),
            extension_work_cap=kw.get('cap',272),maximum_total_plant_work=kw.get('total',2000),maximum_wall_s=kw.get('wall',20.))
        return worker.FsgReplayWorker(request,raw,expected_request_raw_sha256=pin(request))
    def test_exact_replay_and_extension_match_real_uninterrupted_state_and_charge_replay(self):
        program=self.program();result=program.execute(course=self.course,residual_regen_rule=UntrustedRule())
        end=cp.snapshot(result.record.after_raw,clean=True);reference=self.consumer();reference.advance(ticks=65,work_wall_s=10.)
        self.assertEqual(result.record.after_raw,reference.snapshot());self.assertEqual(end['tick'],65)
        self.assertEqual(end['memory']['driver_updates'],2);self.assertEqual(end['memory']['allocator_updates'],7)
        self.assertEqual(result.replay_ticks,31);self.assertEqual(result.new_ticks,34)
        self.assertEqual(result.actual_worker_work,result.replay_work+result.extension_work)
        self.assertEqual(result.replay_work,cp.snapshot(self.first.after_raw)['attempted_numerical_work'])
        self.assertGreater(result.replay_work,0);self.assertIsNotNone(result.child_checkpoint_raw)
        child=cp.validate_checkpoint(result.child_checkpoint_raw,expected_raw_sha256=pin(result.child_checkpoint_raw),expected_identity=self.identity)
        self.assertEqual(child['logical_tick'],65);self.assertEqual(child['segment_count'],2)
        REPLAY_RECORDS.append({'role':'real_short_replay_and_extension_with_UNTRUSTED_predicate_not_native_continuation',
            'checkpoint':json.loads(result.child_checkpoint_raw),'replay_work':result.replay_work,'extension_work':result.extension_work,
            'actual_worker_work':result.actual_worker_work,'replay_ticks':31,'new_ticks':34,'qualification_or_execution_authority':False})
    def test_worker_refused_retry_preserves_previous_result(self):
        program=self.program(ticks=1,cap=8);program.execute(course=self.course,residual_regen_rule=UntrustedRule());before=program.snapshot()
        with self.assertRaises(ValueError):program.execute(course=self.course,residual_regen_rule=UntrustedRule())
        self.assertEqual(program.snapshot(),before)
    def test_endpoint_bytes_stay_exact_after_later_cancel(self):
        c=self.consumer();record=c.advance_with_snapshots(ticks=1,maximum_new_work=8,work_wall_s=2.)
        c.request_cancel();self.assertNotEqual(record.after_raw,c.snapshot())
        self.assertEqual(pin(record.after_raw),json.loads(record.interval_raw)['end_snapshot_sha256']);cp.segment(record)
    def test_tampered_state_or_event_flags_are_not_imported_or_extended(self):
        for mutation in ('state','departed'):
            b=json.loads(self.parent)['checkpoint'];item=b['segments'][0];after=json.loads(item['after_utf8'])
            if mutation=='state':after['state']['thermal']['light']['powered']['pack_energy_j']-=1.;after['state_sha256']=digest(after['state'])
            else:after['departed']=True
            after_raw=encode(after);interval=json.loads(item['interval_utf8']);interval['end_snapshot_sha256']=pin(after_raw)
            item.update(after_utf8=after_raw.decode(),interval_utf8=encode(interval).decode());b['tip_snapshot_sha256']=pin(after_raw)
            raw=reseal(b);program=self.program(raw,ticks=1,cap=8)
            with self.assertRaisesRegex(ValueError,'Replay diverged'):program.execute(course=self.course,residual_regen_rule=UntrustedRule())
            snapshot=program.snapshot();self.assertTrue(snapshot['finished']);self.assertIsNotNone(snapshot['last_record']);self.assertIsNone(snapshot['child_checkpoint_raw'])
            self.assertGreater(snapshot['actual_worker_work'],0)
    def test_changed_identity_or_parent_lineage_refused_before_worker_creation(self):
        b=json.loads(self.parent)['checkpoint'];b['parent_checkpoint_raw_sha256']='d'*64
        with self.assertRaises(ValueError):self.program(reseal(b))
        for field in ('source_manifest_sha256','environment_sha256','residual_rule_sha256','course_record_sha256'):
            identity=dict(self.identity);identity[field]='d'*64
            with self.subTest(field=field),self.assertRaises(ValueError):self.program(identity=identity)
    def test_terminal_cancelled_quarantined_unknown_work_prefixes_are_ineligible(self):
        for key,value in [('status','time_limit'),('cancellation_requested',True),('quarantined_interval_sha256','d'*64),('attempted_numerical_work_is_lower_bound',True),('rejected_attempt',{'role':'fabricated_refusal_test'})]:
            b=json.loads(self.parent)['checkpoint'];item=b['segments'][0];after=json.loads(item['after_utf8']);after[key]=value
            after_raw=encode(after);interval=json.loads(item['interval_utf8']);interval.update(end_snapshot_sha256=pin(after_raw),status=after['status'])
            item.update(after_utf8=after_raw.decode(),interval_utf8=encode(interval).decode());b['tip_snapshot_sha256']=pin(after_raw)
            with self.subTest(key=key),self.assertRaises(ValueError):self.program(reseal(b))
    def test_replay_work_cannot_be_spent_again_on_extension(self):
        program=self.program(ticks=1,cap=248,total=248)
        # The first31tick prefix consumes work, so a248cap extension cannot fit.
        with self.assertRaisesRegex(ValueError,'remaining aggregate'):program.execute(course=self.course,residual_regen_rule=UntrustedRule())
        snapshot=program.snapshot();self.assertGreater(snapshot['replay_work'],0);self.assertEqual(snapshot['extension_work'],0)
        self.assertIsNone(snapshot['child_checkpoint_raw'])
    def test_missing_predicate_fails_and_consumes_attempt(self):
        program=self.program(ticks=1,cap=8)
        with self.assertRaises(ValueError):program.execute(course=self.course,residual_regen_rule=None)
        before=program.snapshot();self.assertTrue(before['finished']);self.assertEqual(before['actual_worker_work'],0)
        with self.assertRaises(ValueError):program.execute(course=self.course,residual_regen_rule=UntrustedRule())
        self.assertEqual(program.snapshot(),before)
    def test_profile_tick_and_byte_caps_are_checked_without_numerical_work(self):
        with self.assertRaises(ValueError):self.program(ticks=1000,cap=8)
        with self.assertRaises(ValueError):cp.validate_checkpoint(b' '* (cp.MAX_BYTES+1),expected_raw_sha256=pin(b' '* (cp.MAX_BYTES+1)),expected_identity=self.identity)
    def test_terminal_extension_returns_raw_evidence_without_an_eligible_checkpoint(self):
        c=self.consumer(maximum_ticks=1);origin=cp.origin_checkpoint(c,self.identity)
        result=self.program(origin,ticks=1,cap=8).execute(course=self.course,residual_regen_rule=UntrustedRule())
        self.assertEqual(result.outcome,'raw_terminal');self.assertIsNone(result.child_checkpoint_raw)
        self.assertEqual(cp.snapshot(result.record.after_raw)['status'],'time_limit')
    def test_late_consumer_serialization_retains_all_literal_endpoints_as_quarantined(self):
        c=self.consumer();clock=[0.];original=ev.encode
        def serialize(v):
            raw=original(v)
            if type(v) is dict and v.get('schema')==ev.INTERVAL_SCHEMA:clock[0]=2.
            return raw
        with patch.object(ev,'monotonic',side_effect=lambda:clock[0]),patch.object(ev,'encode',side_effect=serialize):
            with self.assertRaises(ev.FsgDevelopmentDeadlineExceeded) as caught:c.advance_with_snapshots(ticks=1,maximum_new_work=8,work_wall_s=1.)
        self.assertIsNotNone(caught.exception.raw_record);self.assertEqual(caught.exception.raw_record.interval_raw,caught.exception.raw_interval)
        self.assertEqual(cp.snapshot(c.snapshot())['status'],'wall_limit')
    def test_boolean_schedule_alias_is_refused(self):
        b=json.loads(self.parent)['checkpoint'];b['segments'][0]['requested_ticks']=True
        with self.assertRaises(ValueError):self.program(reseal(b))
    def test_multi_segment_parent_chain_and_replay_remain_exact(self):
        c=self.consumer();raw=cp.origin_checkpoint(c,self.identity)
        for _ in range(3):
            record=c.advance_with_snapshots(ticks=1,maximum_new_work=8,work_wall_s=2.)
            raw=cp.extend_checkpoint(raw,record,expected_parent_raw_sha256=pin(raw),expected_identity=self.identity)
        result=self.program(raw,ticks=1,cap=8,total=100).execute(course=self.course,residual_regen_rule=UntrustedRule())
        body=cp.validate_checkpoint(result.child_checkpoint_raw,expected_raw_sha256=pin(result.child_checkpoint_raw),expected_identity=self.identity)
        self.assertEqual(body['segment_count'],4);self.assertEqual(body['logical_tick'],4);self.assertEqual(result.replay_ticks,3);self.assertEqual(result.new_ticks,1)
    def test_failed_recovery_preserves_original_error_and_incomplete_work(self):
        program=self.program(self.origin,ticks=1,cap=8);error=RuntimeError('injected post-plant serialization failure')
        original=ev.FsgDevelopmentConsumer._snapshot
        def snapshot(c):
            if c._tick:raise error
            return original(c)
        with patch.object(ev.FsgDevelopmentConsumer,'_snapshot',new=snapshot):
            with self.assertRaises(RuntimeError) as raised:program.execute(course=self.course,residual_regen_rule=UntrustedRule())
        self.assertIs(raised.exception,error);state=program.snapshot();self.assertEqual(state['phase'],'failed');self.assertTrue(state['finished'])
        self.assertTrue(state['actual_work_is_lower_bound']);self.assertEqual(state['capture_error'],'RuntimeError');self.assertIsNone(state['child_checkpoint_raw'])
    def test_interrupted_child_publication_never_exposes_eligible_checkpoint(self):
        program=self.program(self.origin,ticks=1,cap=8);original=program._publish_child
        def publish(value):original(value);raise KeyboardInterrupt('injected after child publication')
        with patch.object(program,'_publish_child',side_effect=publish):
            with self.assertRaises(KeyboardInterrupt):program.execute(course=self.course,residual_regen_rule=UntrustedRule())
        state=program.snapshot();self.assertTrue(state['finished']);self.assertEqual(state['phase'],'failed')
        self.assertIsNone(state['child_checkpoint_raw']);self.assertIsNotNone(state['quarantined_child_checkpoint_raw'])
    def test_worker_late_finalization_keeps_raw_data_but_returns_no_checkpoint(self):
        program=self.program(self.origin,ticks=1,cap=8,wall=1.);clock=[0.];original=cp.extend_checkpoint
        def extend(*args,**kw):value=original(*args,**kw);clock[0]=2.;return value
        with patch.object(worker,'monotonic',side_effect=lambda:clock[0]),patch.object(cp,'extend_checkpoint',side_effect=extend):
            with self.assertRaises(worker.ReplayWorkerDeadlineExceeded):program.execute(course=self.course,residual_regen_rule=UntrustedRule())
        state=program.snapshot();self.assertEqual(state['phase'],'quarantined_finalization');self.assertIsNone(state['child_checkpoint_raw'])
        self.assertIsNotNone(state['quarantined_child_checkpoint_raw']);self.assertIsNotNone(state['last_record'])
    def test_unformattable_publication_error_cannot_skip_child_quarantine(self):
        program=self.program(self.origin,ticks=1,cap=8);original=program._publish_child;error=BrokenMessage()
        def publish(value):original(value);raise error
        with patch.object(program,'_publish_child',side_effect=publish):
            with self.assertRaises(BrokenMessage) as raised:program.execute(course=self.course,residual_regen_rule=UntrustedRule())
        self.assertIs(raised.exception,error);state=program.snapshot();self.assertIsNone(state['child_checkpoint_raw'])
        self.assertIsNotNone(state['quarantined_child_checkpoint_raw']);self.assertTrue(state['finished'])
    def test_unformattable_plant_error_keeps_unknown_work_and_original_error(self):
        program=self.program(self.origin,ticks=1,cap=8);error=BrokenMessage()
        with patch.object(ev,'advance_tick',side_effect=error):
            with self.assertRaises(BrokenMessage) as raised:program.execute(course=self.course,residual_regen_rule=UntrustedRule())
        self.assertIs(raised.exception,error);state=program.snapshot();self.assertTrue(state['actual_work_is_lower_bound'])
        self.assertIsNone(state['child_checkpoint_raw']);self.assertTrue(state['finished'])
if __name__=='__main__':unittest.main()
