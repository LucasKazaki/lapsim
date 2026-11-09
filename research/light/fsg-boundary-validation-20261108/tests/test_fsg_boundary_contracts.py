"""Additional dev33 boundary validation, never original/native admission evidence.

All predicate objects below are explicitly UNTRUSTED interface test doubles.
Only the short in-memory continuation probes execute real plant ticks. The
legacy-worker test uses the already frozen UNTRUSTED FSI metadata fixture.
"""
from hashlib import sha256
from importlib import resources,util,metadata
from pathlib import Path
from types import SimpleNamespace,MethodType
from unittest.mock import patch
import json,sys,unittest

from lapsim_light_campaign import fsg_event as ev,raw_journal,continuation
from lapsim_light_campaign.chunk_worker import create_chunk_worker
from lapsim_light_campaign.guarded_dispatch import GuardProviderUnavailable,NUMERICAL_BACKEND_FAMILY
from lapsim_light_campaign.input_contracts import encode,digest
from lapsim_light_campaign.numerical_inputs import ResidualRegenRule,NumericalDependencyUnavailable

PORTABLE=Path(__file__).resolve().parents[2]/'portable-tournament-candidate'
SOURCE_COMMIT='907f094047120bbe75c5906f4c9ff16d15fa43db'
MANIFEST_SHA256='a7f83912c1f0f39d33e97628113040da77949d6ae8b25887faf2b847789a223f'
MODULE_SHA256='0fd2802806b0885c6ab8afc51c941af340a46f1def6bed6e111c5226a9fcaac8'
PIN='e'*64
RECORDS=[]

class UntrustedPredicateDouble:
    """Not the original formula, not authenticated, not a production adapter."""
    implementation_sha256=PIN
    def __init__(self):self.value=False;self.error=None
    def residual_low_speed_regen(self,u,electrical):
        if self.error is not None:raise self.error
        return self.value

class BoundaryContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert metadata.version('lapsim-light-tournament-source-candidate')=='0.0.0.dev33'
        assert Path(ev.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
        assert sha256(Path(ev.__file__).read_bytes()).hexdigest()==MODULE_SHA256
        assert sha256((PORTABLE/'SOURCE_MANIFEST.json').read_bytes()).hexdigest()==MANIFEST_SHA256
        data=resources.files('lapsim_light_course').joinpath('data')
        cls.course=ev.FsgNumericalCourse((PORTABLE/'tests/data/fsg_smoothed_phase_unqualified.json').read_bytes(),
            (PORTABLE/'tests/data/fsg_periodic_bspline64_unqualified.json').read_bytes(),
            data.joinpath('amz_fssim_fsg_approx.json').read_bytes(),data.joinpath('FSG.yaml').read_bytes(),work_wall_s=40.)

    def consumer(self,*,ticks=100,work=800,rule=None):
        rule=UntrustedPredicateDouble() if rule is None else rule
        return ev.FsgDevelopmentConsumer(self.course,policy_id=ev.core_registry.IDS[0],
            residual_regen_rule=rule,residual_regen_rule_sha256=PIN,maximum_ticks=ticks,maximum_work=work),rule

    def test_exact_protocol_placeholder_cannot_initialize_even_with_matching_pin(self):
        placeholder=SimpleNamespace(implementation_sha256=PIN)
        placeholder.residual_low_speed_regen=MethodType(ResidualRegenRule.residual_low_speed_regen,placeholder)
        with patch.object(ev,'initialize_combined_light') as plant:
            with self.assertRaises(NumericalDependencyUnavailable):self.consumer(rule=placeholder)
        plant.assert_not_called()

    def test_pin_drift_after_initialization_refuses_before_any_new_plant_work(self):
        c,rule=self.consumer();before=json.loads(c.snapshot());rule.implementation_sha256='d'*64
        with patch.object(ev,'advance_tick') as plant:result=json.loads(c.advance(ticks=1,work_wall_s=1.))
        plant.assert_not_called();after=json.loads(c.snapshot())
        self.assertEqual(result['status'],'invalid');self.assertEqual(after['state'],before['state']);self.assertEqual(after['memory'],before['memory'])
        self.assertEqual(after['attempted_numerical_work'],0);self.assertFalse(after['attempted_numerical_work_is_lower_bound'])
        self.assertEqual(after['rejected_attempt']['stage'],'controls')

    def test_true_or_nonboolean_predicate_result_refuses_before_plant(self):
        for value in (True,0,1,None,'False'):
            with self.subTest(value=value):
                c,rule=self.consumer();rule.value=value;before=json.loads(c.snapshot())['state']
                with patch.object(ev,'advance_tick') as plant:c.advance(ticks=1,work_wall_s=1.)
                plant.assert_not_called();after=json.loads(c.snapshot());self.assertEqual(after['status'],'invalid');self.assertEqual(after['state'],before)
                self.assertEqual(after['tick'],0);self.assertIsNone(after['finish'])

    def test_unexpected_predicate_exception_is_terminal_without_fake_work(self):
        c,rule=self.consumer();before=json.loads(c.snapshot())['state'];error=RuntimeError('UNTRUSTED predicate failure injection');rule.error=error
        with patch.object(ev,'advance_tick') as plant:
            with self.assertRaises(RuntimeError) as raised:c.advance(ticks=1,work_wall_s=1.)
        self.assertIs(raised.exception,error);plant.assert_not_called();after=json.loads(c.snapshot())
        self.assertEqual(after['status'],'invalid');self.assertEqual(after['state'],before);self.assertEqual(after['attempted_numerical_work'],0)
        self.assertFalse(after['attempted_numerical_work_is_lower_bound'])
        with self.assertRaises(ValueError):c.advance(ticks=1,work_wall_s=1.)

    def test_hash_and_provider_authentication_claims_do_not_grant_authority(self):
        rule=UntrustedPredicateDouble();rule.authenticated=True;rule.campaign_eligible=True;rule.native_qualified=True
        c,_=self.consumer(rule=rule);raw=json.loads(c.snapshot())
        self.assertFalse(raw['qualification_or_execution_authority']);self.assertFalse(raw['checkpoint_restore_or_continuation_authority'])
        self.assertFalse(raw['context']['source_environment_or_rule_authenticated']);self.assertFalse(raw['context']['native_or_campaign_registered'])
        self.assertFalse(raw['context']['course']['source_or_environment_or_line_authenticated'])

    def test_postplant_pin_or_result_drift_retains_real_trial_without_committing(self):
        for mode in ('pin','boolean'):
            with self.subTest(mode=mode):
                c,rule=self.consumer();before=json.loads(c.snapshot());original=ev.advance_tick
                def step(*args,**kw):
                    candidate=original(*args,**kw)
                    if mode=='pin':rule.implementation_sha256='d'*64
                    else:rule.value=True
                    return candidate
                with patch.object(ev,'advance_tick',side_effect=step):c.advance(ticks=1,work_wall_s=2.)
                after=json.loads(c.snapshot());self.assertEqual(after['status'],'invalid');self.assertEqual(after['tick'],0)
                self.assertEqual(after['state'],before['state']);self.assertEqual(after['memory'],before['memory'])
                self.assertEqual(after['rejected_attempt']['stage'],'post_step');self.assertIsNotNone(after['rejected_attempt']['provisional_state'])
                self.assertGreater(after['attempted_numerical_work'],0);self.assertFalse(after['attempted_numerical_work_is_lower_bound']);self.assertIsNone(after['finish'])

    def test_in_memory_continuation_crosses_driver_and_allocator_boundaries_exactly(self):
        one,_=self.consumer(ticks=65,work=520);split,_=self.consumer(ticks=65,work=520)
        initial=json.loads(one.snapshot());whole=json.loads(one.advance(ticks=65,work_wall_s=10.));parts=[]
        for ticks in (31,19,15):parts.append(json.loads(split.advance(ticks=ticks,work_wall_s=10.)))
        self.assertEqual(one.snapshot(),split.snapshot());final=json.loads(one.snapshot())
        self.assertEqual(final['status'],'time_limit');self.assertEqual(final['tick'],65);self.assertIsNone(final['finish'])
        self.assertEqual(final['memory']['driver_updates'],2);self.assertEqual(final['memory']['allocator_updates'],7);self.assertEqual(final['memory']['blend_updates'],65)
        self.assertEqual(final['state']['thermal']['light']['feedback_ticks'],65)
        self.assertEqual([p['start_tick'] for p in parts],[0,31,50]);self.assertEqual([p['end_tick'] for p in parts],[31,50,65])
        RECORDS.append({'role':'real_65ms_in_memory_carry_with_untrusted_predicate_not_process_checkpoint_resume_or_lap',
            'initial_snapshot':initial,'single_interval':whole,'split_intervals':parts,'final_snapshot':final,'qualification_or_execution_authority':False})

    def test_global_work_cap_is_not_refunded_between_calls(self):
        measure,_=self.consumer();measure.advance(ticks=1,work_wall_s=2.)
        work=json.loads(measure.snapshot())['attempted_numerical_work'];self.assertGreater(work,0)
        limited,_=self.consumer(work=work);limited.advance(ticks=1,work_wall_s=2.);before=json.loads(limited.snapshot())
        packet=json.loads(limited.advance(ticks=1,work_wall_s=1.));after=json.loads(limited.snapshot())
        self.assertEqual(packet['status'],'work_limit');self.assertEqual(packet['attempted_work_delta'],0)
        self.assertEqual(after['state'],before['state']);self.assertEqual(after['tick'],1);self.assertEqual(after['attempted_numerical_work'],work)
        self.assertIsNone(after['finish'])

    def test_cancelled_in_memory_sequence_cannot_be_restarted(self):
        c,_=self.consumer();c.advance(ticks=7,work_wall_s=2.);before=json.loads(c.snapshot());c.request_cancel()
        packet=json.loads(c.advance(ticks=10,work_wall_s=1.));after=c.snapshot();decoded=json.loads(after)
        self.assertEqual(packet['status'],'cancelled');self.assertEqual(decoded['state'],before['state']);self.assertEqual(decoded['memory'],before['memory']);self.assertEqual(decoded['tick'],7)
        with self.assertRaises(ValueError):c.advance(ticks=1,work_wall_s=1.)
        self.assertEqual(c.snapshot(),after)

    def test_fsg_raw_snapshot_cannot_become_a_legacy_checkpoint_by_wrapping_and_hashing(self):
        c,_=self.consumer();raw=json.loads(c.snapshot());wrapped={'checkpoint':raw,'checkpoint_sha256':digest(raw)}
        with self.assertRaisesRegex(ValueError,'schema'):raw_journal._checkpoint(wrapped)
        raw['status']='paused_budget';wrapped={'checkpoint':raw,'checkpoint_sha256':digest(raw)}
        with self.assertRaises(ValueError):raw_journal._checkpoint(wrapped)

    def test_legacy_fixed_worker_family_has_no_fsg_fallback(self):
        with self.assertRaisesRegex(ValueError,'family'):
            create_chunk_worker(b'UNTRUSTED rejected request',b'UNTRUSTED rejected checkpoint',expected_request_sha256='0'*64,numerical_backend_family=ev.FAMILY)

    def test_actual_legacy_worker_rejects_fsg_consumer_before_any_step(self):
        # Reuse the exact frozen no-auth metadata fixture, not native evidence.
        fixture_path=PORTABLE/'tests/test_campaign.py'
        manifest=json.loads((PORTABLE/'SOURCE_MANIFEST.json').read_bytes())
        expected=next(row['sha256'] for row in manifest['files'] if row['path']=='tests/test_campaign.py')
        self.assertEqual(sha256(fixture_path.read_bytes()).hexdigest(),expected)
        spec=util.spec_from_file_location('_frozen_fsi_metadata_fixture_907f094',fixture_path);fixture=util.module_from_spec(spec);spec.loader.exec_module(fixture)
        plan_raw,_=fixture.plan_fixture();cell=json.loads(plan_raw)['plan']['cells'][0];parent=encode(cell['origin'])
        request=fixture.RequestSource(plan_raw)(cell['policy_id'],parent,requested_ticks=1,remaining_requested_wall_time_ms=1000)
        program=create_chunk_worker(request,parent,expected_request_sha256=json.loads(request)['request_sha256'],numerical_backend_family=NUMERICAL_BACKEND_FAMILY)
        c,_=self.consumer();before=c.snapshot()
        with patch.object(ev,'advance_tick') as plant:
            with self.assertRaisesRegex(ValueError,'bridge'):program.execute(bridge=c)
        plant.assert_not_called();self.assertEqual(c.snapshot(),before);snapshot=program.snapshot()
        self.assertTrue(snapshot.local_attempt_finished);self.assertIsNone(snapshot.raw_chunk_json);self.assertIsNone(snapshot.linked_checkpoint_json)

    def test_no_original_continuation_provider_means_no_fallback_execution(self):
        c,_=self.consumer();before=c.snapshot()
        with patch.object(ev,'advance_tick') as plant:
            with self.assertRaises(GuardProviderUnavailable):
                continuation.dispatch_continuation(before,before,b'UNTRUSTED not historical receipts',expected_continuation_sha256='0'*64,expected_provider_sha256='0'*64,provider=None)
        plant.assert_not_called();self.assertEqual(c.snapshot(),before)

    def test_later_cancellation_snapshot_is_not_the_interval_endpoint_bytes(self):
        # This documents the current RAW-data boundary, not a checkpoint defect:
        # a future worker must retain literal endpoint bytes, not fetch them later.
        c,_=self.consumer();interval=json.loads(c.advance(ticks=1,work_wall_s=2.))
        endpoint=c.snapshot();self.assertEqual(sha256(endpoint).hexdigest(),interval['end_snapshot_sha256'])
        c.request_cancel();later=c.snapshot();before,after=json.loads(endpoint),json.loads(later)
        self.assertEqual(before['state'],after['state']);self.assertEqual(before['memory'],after['memory'])
        self.assertEqual(before['tick'],after['tick']);self.assertTrue(after['cancellation_requested'])
        self.assertNotEqual(sha256(later).hexdigest(),interval['end_snapshot_sha256'])
        self.assertFalse(after['checkpoint_restore_or_continuation_authority'])
        RECORDS.append({'role':'literal_raw_endpoint_retention_requirement_not_checkpoint_restore',
            'interval_end_snapshot_sha256':interval['end_snapshot_sha256'],
            'retained_endpoint_sha256':sha256(endpoint).hexdigest(),'later_cancelled_snapshot_sha256':sha256(later).hexdigest(),
            'physical_state_unchanged':True,'qualification_or_execution_authority':False})

if __name__=='__main__':unittest.main()
