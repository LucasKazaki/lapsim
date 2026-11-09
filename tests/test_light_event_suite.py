"""Role/budget tests use doubles; one bounded smoke uses the actual models."""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

import pytest

from lapsim.courses.library import COURSE_IDS
from lapsim.experiments import light_event_suite as suite
from lapsim.experiments.light_policy_scope import portable_policy_scope, SOURCE_PINS


def fake_rollout(controller, case, *, profile):
    return {'controller':asdict(controller),'case':asdict(case),'profile':profile,
            'status':'completed','eligible':True,'violations':[],
            'metrics':{'fitness':123.},'telemetry':[]}


def test_zero_allocations_preserve_all_ten_events_without_selection(tmp_path,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('No allocated model work')
    monkeypatch.setattr(suite,'rollout',forbidden)
    monkeypatch.setattr(suite,'run_skidpad_field',forbidden)
    r=suite.run_suite(tmp_path/'suite',catalog_rollouts=0,skidpad_steps=0,wall_seconds=30,
                      maximum_cell_seconds=.1,entry_length_m=5.,exit_length_m=5.)
    assert len(r['events'])==10
    assert [x['event_id'] for x in r['events'][:9]]==list(COURSE_IDS)
    assert all(x['status']=='unrun' for x in r['events'])
    assert len(r['catalog_cells'])==36
    assert all(c['status']=='unrun' for c in r['catalog_cells'])
    assert r['winner'] is None and r['official_points'] is None
    assert r['heldout_used'] is False
    assert len(r['portable_policy_scope']['policies'])==7
    assert all(not p['implemented_in_this_suite'] for p in r['portable_policy_scope']['policies'])


def test_nominal_budget_has_no_tuning_holdout_or_cross_event_scores(tmp_path,monkeypatch):
    calls=[]
    def record(controller,case,*,profile):
        calls.append((controller,case,profile))
        return fake_rollout(controller,case,profile=profile)
    monkeypatch.setattr(suite,'rollout',record)
    r=suite.run_suite(tmp_path/'suite',catalog_rollouts=2,skidpad_steps=0,wall_seconds=30,
                      maximum_cell_seconds=.1,entry_length_m=5.,exit_length_m=5.)
    assert len(calls)==2 and r['reserved_catalog_rollouts']==2
    assert [c.philosophy for c,_,_ in calls]==['fixed','traction']
    assert calls[0][1]==calls[1][1]
    assert all(case.name.startswith('development_nominal:') and not case.patch and not case.reverse
               and case.grip==1. and profile=='synthetic_rwd' for _,case,profile in calls)
    assert r['catalog_cells'][0]['status']=='completed_development_cell'
    assert r['events'][0]['status']=='partial_development_cells'
    assert r['winner'] is None
    assert 'best' not in r and 'fitness' not in r


def test_returned_failure_raw_record_retained_and_next_distinct_cell_runs(tmp_path,monkeypatch):
    def record(controller,case,*,profile):
        r=fake_rollout(controller,case,profile=profile)
        if controller.philosophy=='fixed':r.update(status='model_error',eligible=False,violations=['kept'])
        return r
    monkeypatch.setattr(suite,'rollout',record)
    r=suite.run_suite(tmp_path/'suite',catalog_rollouts=2,skidpad_steps=0,wall_seconds=30,
                      maximum_cell_seconds=.1,entry_length_m=5.,exit_length_m=5.)
    cell=r['catalog_cells'][0]
    assert cell['status']=='returned_failure' and cell['model_status']=='model_error'
    raw=json.loads((tmp_path/'suite'/cell['raw_result']['path']).read_bytes())
    assert raw['violations']==['kept']
    assert r['catalog_cells'][1]['status']=='completed_development_cell'
    assert r['reserved_catalog_rollouts']==2


def test_unreturned_exception_stops_with_consumed_slot_and_unknown_state(tmp_path,monkeypatch):
    def fail(*args,**kwargs):raise RuntimeError('unreturned state')
    monkeypatch.setattr(suite,'rollout',fail)
    r=suite.run_suite(tmp_path/'suite',catalog_rollouts=4,skidpad_steps=2,wall_seconds=30,
                      maximum_cell_seconds=.1,entry_length_m=5.,exit_length_m=5.)
    assert r['status']=='execution_error'
    assert r['reserved_catalog_rollouts']==1
    assert r['catalog_cells'][0]['status']=='uncertain_unreturned'
    assert r['catalog_cells'][0]['raw_result'] is None
    assert all(c['status']=='unrun' for c in r['catalog_cells'][1:])
    assert r['events'][-1]['status']=='unrun'


def test_real_short_models_keep_partial_catalog_and_skidpad_separate(tmp_path):
    r=suite.run_suite(tmp_path/'suite',catalog_rollouts=1,skidpad_steps=2,wall_seconds=30,
                      maximum_cell_seconds=.1,entry_length_m=5.,exit_length_m=5.)
    assert r['reserved_catalog_rollouts']==1
    assert r['catalog_cells'][0]['raw_result'] is not None
    assert r['catalog_cells'][0]['status']!='completed_development_cell'
    assert all(c['status']=='unrun' for c in r['catalog_cells'][1:])
    assert r['events'][-1]['status']=='paused_aggregate_budget'
    child=json.loads((tmp_path/'suite/skidpad/field-index.json').read_bytes())
    assert child['attempted_steps']==2
    assert child['cells'][0]['session_status']=='running'
    assert r['closed_course_checkpoint_scope']=='BETWEEN_ROLLOUTS_ONLY_NOT_MID_LAP_STATE'
    assert r['heldout_used'] is False and r['winner'] is None


def test_pinned_seven_policy_snapshot_is_data_only_and_cannot_be_promoted():
    a=portable_policy_scope()
    assert len({p['id'] for p in a['policies']})==7
    assert all(not p['source_declared_campaign_eligible'] for p in a['policies'])
    assert a['schema']=='lapsim.portable-policy-source-audit.v2'
    assert a['distribution_version']=='0.0.0.dev28'
    assert a['runtime_availability']=='UNVERIFIED_BY_THIS_ORDINARY_SUITE'
    assert all(p['implemented_in_this_suite'] is False and
               p['source_declared_native_qualification']=='UNRUN' for p in a['policies'])
    assert a['bounded_component_tests']['source_and_installed_cases']==110
    assert a['bounded_component_tests']['course_or_native_qualification'] is False
    assert a['bounded_component_tests']['campaign_eligibility_promoted'] is False
    assert a['source_course_preparation']['fsg_local_source_frame_constructed'] is True
    assert a['source_course_preparation']['fsg_source_test_cases']==15
    assert a['source_course_preparation']['fsg_source_chord_reference_candidate_available'] is True
    assert a['source_course_preparation']['fsg_source_tk_device_gate_candidate_available'] is True
    assert a['source_course_preparation']['fsg_gate_semantics_or_exact_arc_phase_qualified'] is False
    assert a['source_course_preparation']['fsg_numerical_path_enabled'] is False
    assert a['source_course_preparation']['fsg_admissible_driving_reference_available'] is False
    assert a['source_course_preparation']['source_preparation_is_campaign_eligibility'] is False
    a['source_course_preparation']['fsg_numerical_path_enabled']=True
    assert portable_policy_scope()['source_course_preparation']['fsg_numerical_path_enabled'] is False
    a['policies'][0]['source_declared_campaign_eligible']=True
    assert portable_policy_scope()['policies'][0]['source_declared_campaign_eligible'] is False


def test_pinned_portable_snapshot_manifest_version_and_module_bytes():
    a=portable_policy_scope()
    root=Path(__file__).resolve().parents[1]/'research/light/portable-tournament-candidate'
    if not root.exists():
        pytest.skip('Portable snapshot bytes are separate; the ordinary descriptor does not assert their installation')
    raw=(root/'SOURCE_MANIFEST.json').read_bytes()
    assert sha256(raw).hexdigest()==a['source_manifest_sha256']
    manifest=json.loads(raw)
    files={row['path']:row['sha256'] for row in manifest['files']}
    assert json.loads((root/'INSTALL_CONTRACT.json').read_bytes())['project']['version']==a['distribution_version']
    assert a['source_commit']=='0d4b19290931e100819169930079427e95e100a5'
    assert len(SOURCE_PINS)==11
    assert all(files[name]==digest for name,digest in SOURCE_PINS.items())
    for name,digest in SOURCE_PINS.items():assert sha256((root/name).read_bytes()).hexdigest()==digest


def test_source_change_after_return_preserves_raw_but_stops(tmp_path,monkeypatch):
    changed=False
    def source():return {'same':not changed}
    def record(*args,**kwargs):
        nonlocal changed
        r=fake_rollout(*args,**kwargs)
        changed=True
        return r
    monkeypatch.setattr(suite,'_source',source)
    monkeypatch.setattr(suite,'rollout',record)
    r=suite.run_suite(tmp_path/'suite',catalog_rollouts=4,skidpad_steps=2,wall_seconds=30,
                      maximum_cell_seconds=.1,entry_length_m=5.,exit_length_m=5.)
    assert r['status']=='execution_error'
    assert r['catalog_cells'][0]['status']=='rejected_source_change'
    assert r['catalog_cells'][0]['raw_result'] is not None
    assert all(c['status']=='unrun' for c in r['catalog_cells'][1:])
    assert r['events'][-1]['status']=='unrun'


def test_changed_result_identity_is_retained_without_followup(tmp_path,monkeypatch):
    def record(*args,**kwargs):
        r=fake_rollout(*args,**kwargs);r['profile']='synthetic_awd';return r
    monkeypatch.setattr(suite,'rollout',record)
    r=suite.run_suite(tmp_path/'suite',catalog_rollouts=4,skidpad_steps=2,wall_seconds=30,
                      maximum_cell_seconds=.1,entry_length_m=5.,exit_length_m=5.)
    assert r['catalog_cells'][0]['status']=='rejected_result_identity'
    assert r['reserved_catalog_rollouts']==1
    assert r['events'][-1]['status']=='unrun'


def test_catalog_publication_failure_propagates_and_preserves_reservation(tmp_path,monkeypatch):
    calls=[]
    def record(*args,**kwargs):calls.append(1);return fake_rollout(*args,**kwargs)
    original=suite._write
    def write(path,value):
        if path.parent.name=='raw':raise OSError('output failed')
        return original(path,value)
    monkeypatch.setattr(suite,'rollout',record)
    monkeypatch.setattr(suite,'_write',write)
    with pytest.raises(OSError,match='output'):
        suite.run_suite(tmp_path/'suite',catalog_rollouts=4,skidpad_steps=2,wall_seconds=30,
                         maximum_cell_seconds=.1,entry_length_m=5.,exit_length_m=5.)
    assert len(calls)==1
    latest=sorted((tmp_path/'suite').glob('checkpoint-*.json'))[-1]
    checkpoint=json.loads(latest.read_bytes())
    assert checkpoint['reserved_catalog_rollouts']==1
    assert checkpoint['catalog_cells'][0]['status']=='running_unreturned'
    assert not (tmp_path/'suite/suite-index.json').exists()


def test_reservation_wall_expiry_never_refunds_or_calls_model(tmp_path,monkeypatch):
    clock=iter([0.,0.,11.])
    monkeypatch.setattr(suite.time,'monotonic',lambda:next(clock,11.))
    monkeypatch.setattr(suite,'rollout',lambda *a,**k:pytest.fail('expired'))
    r=suite.run_suite(tmp_path/'suite',catalog_rollouts=4,skidpad_steps=2,wall_seconds=10,
                      maximum_cell_seconds=.1,entry_length_m=5.,exit_length_m=5.)
    assert r['reserved_catalog_rollouts']==1
    assert r['catalog_cells'][0]['status']=='paused_wall_before_dispatch'
    assert r['catalog_cells'][0]['raw_result'] is None
    assert r['events'][-1]['status']=='unrun'


@pytest.mark.parametrize('bad_common',[{'source':{'wrong':True},'runtime':{},'request':{'course':{}}},[]])
def test_retained_skidpad_binding_cannot_silently_differ_from_suite(tmp_path,monkeypatch,bad_common):
    def child(output,**kwargs):
        output.mkdir()
        common=bad_common
        raw=suite._raw(common)
        (output/'common-binding.json').write_bytes(raw)
        result={'common_binding_sha256':sha256(raw).hexdigest(),
                'controller_order':['fixed','traction','yaw_pi','tire_reserve'],
                'status':'completed_development_field','qualification_or_execution_authority':False,
                'qualified_tournament_result':False,'winner':None,'official_points':None}
        result['cells']=[{'controller':name,'status':'completed','session_status':'completed'}
                         for name in result['controller_order']]
        (output/'field-index.json').write_bytes(suite._raw(result))
        return result
    monkeypatch.setattr(suite,'run_skidpad_field',child)
    r=suite.run_suite(tmp_path/'suite',catalog_rollouts=0,skidpad_steps=2,wall_seconds=30,
                      maximum_cell_seconds=.1,entry_length_m=5.,exit_length_m=5.)
    assert r['status']=='execution_error'
    assert r['events'][-1]['status']=='rejected_child_binding'
    assert r['events'][-1]['child_index'] is not None
    assert r['reserved_catalog_rollouts']==0


def test_skidpad_reservation_io_expiry_is_unrun_not_a_failed_dispatch(tmp_path,monkeypatch):
    clock=iter([0.,0.,11.])
    monkeypatch.setattr(suite.time,'monotonic',lambda:next(clock,11.))
    monkeypatch.setattr(suite,'run_skidpad_field',lambda *a,**k:pytest.fail('expired'))
    r=suite.run_suite(tmp_path/'suite',catalog_rollouts=0,skidpad_steps=2,wall_seconds=10,
                      maximum_cell_seconds=.1,entry_length_m=5.,exit_length_m=5.)
    assert r['events'][-1]['status']=='unrun'
    assert r['events'][-1]['reason']=='wall_expired_before_dispatch'


def test_post_skidpad_source_change_is_not_rebound_to_outer_snapshot(tmp_path,monkeypatch):
    changed=False
    monkeypatch.setattr(suite,'_source',lambda:{'same':not changed})
    def child(output,**kwargs):
        nonlocal changed
        binding=json.loads((output.parent/'suite-binding.json').read_bytes())
        output.mkdir()
        common={'source':binding['source'],'runtime':binding['runtime'],
                'request':{'course':binding['skidpad_course']}}
        raw=suite._raw(common)
        (output/'common-binding.json').write_bytes(raw)
        result={'common_binding_sha256':sha256(raw).hexdigest(),
                'controller_order':['fixed','traction','yaw_pi','tire_reserve'],
                'status':'completed_development_field','qualification_or_execution_authority':False,
                'qualified_tournament_result':False,'winner':None,'official_points':None}
        result['cells']=[{'controller':name,'status':'completed','session_status':'completed'}
                         for name in result['controller_order']]
        (output/'field-index.json').write_bytes(suite._raw(result))
        changed=True
        return result
    monkeypatch.setattr(suite,'run_skidpad_field',child)
    r=suite.run_suite(tmp_path/'suite',catalog_rollouts=0,skidpad_steps=2,wall_seconds=30,
                      maximum_cell_seconds=.1,entry_length_m=5.,exit_length_m=5.)
    assert r['status']=='execution_error'
    assert r['events'][-1]['status']=='rejected_child_binding'


def test_cli_rejects_resume_and_portable_policy_execution(tmp_path):
    base=['--catalog-rollouts','0','--skidpad-steps','0','--wall-seconds','10',
          '--maximum-cell-seconds','.1','--entry-length-m','5','--exit-length-m','5',
          '--output',str(tmp_path/'suite')]
    for extra in (['--resume','previous'],['--policy','awd7-equal-off-v4']):
        with pytest.raises(SystemExit) as error:suite.main(base+extra)
        assert error.value.code==2


def test_request_read_expiry_cannot_start_a_late_rollout(tmp_path,monkeypatch):
    clock=[0.]
    monkeypatch.setattr(suite.time,'monotonic',lambda:clock[0])
    original=Path.read_bytes
    def read(path):
        raw=original(path)
        if path.parent.name=='requests':clock[0]=11.
        return raw
    monkeypatch.setattr(Path,'read_bytes',read)
    monkeypatch.setattr(suite,'rollout',lambda *a,**k:pytest.fail('Late rollout dispatched'))
    r=suite.run_suite(tmp_path/'suite',catalog_rollouts=1,skidpad_steps=2,wall_seconds=10,
                      maximum_cell_seconds=.1,entry_length_m=5.,exit_length_m=5.)
    assert r['reserved_catalog_rollouts']==1
    assert r['returned_catalog_rollouts']==0
    assert r['catalog_cells'][0]['status']=='paused_wall_before_dispatch'
    assert r['events'][-1]['status']=='unrun'


@pytest.mark.parametrize('runs,steps,wall,sim',[(True,0,30,.1),(37,0,30,.1),(0,-1,30,.1),(0,40001,30,.1),(0,0,0,.1),(0,0,30,61)])
def test_invalid_caps_create_nothing(tmp_path,runs,steps,wall,sim):
    with pytest.raises(ValueError):
        suite.run_suite(tmp_path/'bad',catalog_rollouts=runs,skidpad_steps=steps,wall_seconds=wall,
                        maximum_cell_seconds=sim,entry_length_m=5.,exit_length_m=5.)
    assert not (tmp_path/'bad').exists()
