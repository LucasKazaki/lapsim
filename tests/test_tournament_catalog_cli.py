"""Catalog selection and cooperative batch bookkeeping, not physics acceptance.

Zero-rollout tests use the real catalog/specification/checkpoint code. Other
tests deliberately substitute rollout records or a child search to exercise
accounting and failures without running a numerical field or native provider.
"""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from lapsim.courses.library import COURSE_IDS
from lapsim.experiments import controller_tournament as search


def fake_rollout(controller, case, **kwargs):
    return {"eligible": True, "status": "completed", "telemetry": [{"t_s": 0.}],
        "metrics": {"elapsed_s": 10., "fitness": 11., "lap_time_s": 10., "net_energy_kwh": .01}}


class TournamentCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def main(self, *args):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return search.main(list(args))

    def batch(self, name='batch', **kwargs):
        return search.run_catalog_batch(self.root/name, maximum_new_runs=kwargs.pop('maximum_new_runs', 0),
            wall_seconds=kwargs.pop('wall_seconds', 30), population=4, generations=1, **kwargs)

    def test_one_catalog_selection_uses_existing_bundle_and_long_course_rules(self):
        fsi = search.catalog_specification('amz_fssim_fsi_approx', population=4, generations=1, laps=1)
        long = search.catalog_specification('fsae_michigan_2019_image', population=4, generations=1, laps=1)
        for spec in (fsi,long):
            self.assertEqual(spec['training'][0]['course'], 'bundle')
            self.assertEqual(spec['competition']['laps'], 1)
            self.assertFalse(spec['objective']['fsae_points_enabled'])
            self.assertTrue(set(c['name'] for c in spec['training']).isdisjoint(c['name'] for c in spec['holdout']))
        self.assertEqual(fsi['training'][0]['duration_s'],60)
        self.assertEqual(long['training'][0]['duration_s'],300)
        self.assertTrue(long['training'][0]['long_course'])

    def test_actual_cli_catalog_zero_rollout_checkpoint(self):
        output = self.root/'single'
        self.assertEqual(self.main('--output',str(output),'--course-id','amz_fssim_fsi_approx',
                                   '--laps','1','--maximum-new-runs','0'),2)
        state=json.loads((output/'checkpoint.json').read_text())
        self.assertEqual(state['schema'],search.SCHEMA)
        self.assertEqual(state['status'],'paused_budget')
        self.assertFalse(state['runs'])
        self.assertEqual(state['specification']['training'][0]['course_bundle']['course_id'],
                         'amz_fssim_fsi_approx')

    def test_legacy_default_course_and_lap_count_are_preserved(self):
        output=self.root/'legacy'
        self.assertEqual(self.main('--output',str(output),'--maximum-new-runs','0'),2)
        state=json.loads((output/'checkpoint.json').read_text())
        self.assertEqual(state['specification']['training'][0]['course'],'stadium')
        self.assertEqual(state['specification']['competition']['laps'],10)

    def test_legacy_pause_resume_retains_schema_and_deterministic_search(self):
        spec=search.specification(population=4,generations=1,laps=1)
        with redirect_stdout(io.StringIO()):
            complete=search.run_search(self.root/'full',spec,rollout_fn=fake_rollout,wall_seconds=30)
            paused=search.run_search(self.root/'resume',spec,rollout_fn=fake_rollout,
                                     maximum_new_runs=2,wall_seconds=30)
            resumed=search.run_search(self.root/'resume',spec,resume=True,rollout_fn=fake_rollout,wall_seconds=30)
        self.assertEqual(paused['schema'],search.SCHEMA)
        self.assertEqual(paused['status'],'paused_budget')
        for key in ('runs','candidates','generations','baselines','holdout','round_robin',
                    'best_so_far','rng_state','status','diagnostic_ids'):
            self.assertEqual(json.loads(search.canonical(complete[key])),
                             json.loads(search.canonical(resumed[key])),key)
        with patch.object(search,'sources',return_value={'different':'source'}), \
             self.assertRaisesRegex(ValueError,'config/source mismatch'):
            search.run_search(self.root/'resume',spec,resume=True,rollout_fn=fake_rollout,wall_seconds=30)

    def test_actual_all_nine_zero_budget_keeps_provenance_and_unrun_rows(self):
        result=self.batch()
        self.assertEqual(result['course_order'],list(COURSE_IDS))
        self.assertEqual(len(result['courses']),9)
        self.assertEqual(result['status'],'paused_budget')
        self.assertEqual(result['budget']['reserved_rollout_slots'],0)
        self.assertTrue(all(row['status']=='unrun' and not row['checkpoint_present'] for row in result['courses']))
        for row in result['courses']:
            self.assertEqual(row['catalog']['id'],row['course_id'])
            self.assertIn('classification',row['catalog'])
            self.assertIn('description',row['catalog'])
            self.assertEqual(len(row['specification_sha256']),64)
        self.assertEqual(result['supported_controller_philosophies'],list(search.PHILOSOPHIES))
        self.assertEqual(result['portable_seven_policy_comparison'],'UNSUPPORTED_BY_THIS_BACKEND')
        self.assertIsNone(result['cross_course_winner'])
        self.assertIsNone(result['official_points'])
        self.assertFalse(result['qualification_or_execution_authority'])
        self.assertEqual(list((self.root/'batch').iterdir()),[self.root/'batch'/'catalog-search.json'])

    def test_actual_search_double_rollouts_share_one_outer_run_cap(self):
        calls=[]
        def record(*args,**kwargs):
            calls.append(args[1].course_bundle['course_id'])
            return fake_rollout(*args,**kwargs)
        result=self.batch(maximum_new_runs=2,course_ids=COURSE_IDS[:2],rollout_fn=record)
        self.assertEqual(calls,[COURSE_IDS[0]]*2)
        self.assertEqual(result['budget']['reserved_rollout_slots'],2)
        self.assertEqual([row['status'] for row in result['courses']],['paused_budget','unrun'])
        checkpoint=json.loads((self.root/'batch'/COURSE_IDS[0]/'checkpoint.json').read_text())
        self.assertEqual(len(checkpoint['runs']),2)
        self.assertTrue(result['courses'][0]['checkpoint_present'])

    def test_failed_rollout_reservation_is_not_refunded_or_retried(self):
        error=RuntimeError('SYNTHETIC ROLLOUT FAILURE')
        calls=[]
        def fail(*args,**kwargs):
            calls.append(1)
            raise error
        with self.assertRaises(RuntimeError) as caught:
            self.batch(maximum_new_runs=3,course_ids=COURSE_IDS[:2],rollout_fn=fail)
        self.assertIs(caught.exception,error)
        self.assertEqual(len(calls),1)
        state=json.loads((self.root/'batch'/'catalog-search.json').read_text())
        self.assertEqual(state['status'],'failed')
        self.assertEqual(state['budget']['reserved_rollout_slots'],1)
        self.assertEqual([row['status'] for row in state['courses']],['failed','unrun'])
        self.assertEqual(state['courses'][0]['failure']['type'],'RuntimeError')

    def test_failure_after_a_saved_record_reports_unknown_count_not_zero(self):
        error=RuntimeError('SYNTHETIC SECOND ROLLOUT FAILURE')
        calls=[]
        def record(*args,**kwargs):
            calls.append(1)
            if len(calls)==2:
                raise error
            return fake_rollout(*args,**kwargs)
        with self.assertRaises(RuntimeError):
            self.batch(maximum_new_runs=3,course_ids=COURSE_IDS[:2],rollout_fn=record)
        state=json.loads((self.root/'batch'/'catalog-search.json').read_text())
        child=json.loads((self.root/'batch'/COURSE_IDS[0]/'checkpoint.json').read_text())
        self.assertEqual(len(child['runs']),1)
        self.assertEqual(state['budget']['reserved_rollout_slots'],2)
        self.assertIsNone(state['courses'][0]['checkpoint_runs'])
        self.assertTrue(state['courses'][0]['checkpoint_present'])
        self.assertEqual(state['courses'][1]['status'],'unrun')

    def test_outer_boundary_after_a_saved_record_retains_unknown_count(self):
        clock=[0.]
        def child(output,spec,**kwargs):
            output.mkdir()
            record=kwargs['rollout_fn'](search.Controller(),search.Case(**spec['training'][0]),profile=spec['profile'])
            (output/'checkpoint.json').write_text(json.dumps({'runs':{'explicit-test-double':record}}))
            clock[0]=2.
            kwargs['rollout_fn'](search.Controller(),search.Case(**spec['training'][1]),profile=spec['profile'])
            self.fail('Outer boundary must stop before another rollout')
        with patch.object(search.time,'perf_counter',side_effect=lambda:clock[0]), \
             patch.object(search,'run_search',side_effect=child):
            result=self.batch(maximum_new_runs=3,wall_seconds=2,course_ids=COURSE_IDS[:2],rollout_fn=fake_rollout)
        self.assertEqual(result['status'],'paused_budget')
        self.assertEqual(result['budget']['reserved_rollout_slots'],1)
        self.assertIsNone(result['courses'][0]['checkpoint_runs'])
        self.assertTrue(result['courses'][0]['checkpoint_present'])

    def test_wall_cap_is_cooperative_and_not_renewed_for_next_course(self):
        clock=[0.]
        calls=[]
        def record(*args,**kwargs):
            calls.append(1)
            clock[0]=10.
            return fake_rollout(*args,**kwargs)
        with patch.object(search.time,'perf_counter',side_effect=lambda:clock[0]):
            result=self.batch(maximum_new_runs=20,wall_seconds=2,course_ids=COURSE_IDS[:2],rollout_fn=record)
        self.assertEqual(len(calls),1)
        self.assertEqual(result['status'],'paused_budget')
        self.assertEqual(result['budget']['elapsed_wall_seconds'],10.)
        self.assertEqual(result['courses'][1]['status'],'unrun')

    def test_less_than_one_second_remaining_does_not_round_up_child_budget(self):
        values=iter([0.,1.5])
        with patch.object(search.time,'perf_counter',side_effect=lambda:next(values,1.5)), \
             patch.object(search,'run_search') as child:
            result=self.batch(maximum_new_runs=1,wall_seconds=2,course_ids=COURSE_IDS[:1])
        child.assert_not_called()
        self.assertEqual(result['status'],'paused_budget')
        self.assertEqual(result['courses'][0]['status'],'unrun')

    def test_terminal_failed_search_is_preserved_without_skipping_later_course(self):
        statuses=iter(['no_eligible_parent','completed'])
        def child(output,spec,**kwargs):
            output.mkdir()
            record=kwargs['rollout_fn'](search.Controller(),search.Case(**spec['training'][0]),profile=spec['profile'])
            state={'status':next(statuses),'runs':{'explicit-test-double':record}}
            (output/'checkpoint.json').write_text(json.dumps(state))
            return state
        with patch.object(search,'run_search',side_effect=child):
            result=self.batch(maximum_new_runs=3,course_ids=COURSE_IDS[:2],rollout_fn=fake_rollout)
        self.assertEqual(result['status'],'completed_with_failures')
        self.assertEqual([r['status'] for r in result['courses']],['no_eligible_parent','completed'])
        self.assertEqual(result['budget']['reserved_rollout_slots'],2)

    def test_unknown_duplicate_or_unsupported_inputs_fail_before_output(self):
        invalid=({'course_ids':('unknown',)}, {'course_ids':(COURSE_IDS[0],)*2},
                 {'maximum_new_runs':True}, {'maximum_new_runs':-1},
                 {'maximum_new_runs':1_000_000}, {'wall_seconds':float('nan')},
                 {'wall_seconds':901}, {'laps':10}, {'profile':'real_2025'})
        for index,kwargs in enumerate(invalid):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                self.batch(name=str(index),**kwargs)
            self.assertFalse((self.root/str(index)).exists())

    def test_cli_conflicts_unknown_ids_and_batch_resume_fail_before_output(self):
        output=self.root/'invalid'
        variants=(('--course-id','unknown'),
            ('--course-id',COURSE_IDS[0],'--course','autocross'),
            ('--course-id',COURSE_IDS[0],'--course-bundle','missing.json'),
            ('--all-courses','--resume','--laps','1','--maximum-new-runs','0'),
            ('--all-courses','--maximum-new-runs','0'), ('--all-courses','--laps','1'))
        for args in variants:
            with self.subTest(args=args),self.assertRaises(SystemExit) as caught:
                self.main('--output',str(output),*args)
            self.assertEqual(caught.exception.code,2)
            self.assertFalse(output.exists())

    def test_batch_never_overwrites_an_existing_namespace(self):
        output=self.root/'batch'
        output.mkdir()
        (output/'catalog-search.json').write_text('KEEP PREVIOUS EVIDENCE')
        with self.assertRaises(FileExistsError):
            self.batch(course_ids=COURSE_IDS[:1])
        self.assertEqual((output/'catalog-search.json').read_text(),'KEEP PREVIOUS EVIDENCE')


if __name__=='__main__':
    unittest.main()
