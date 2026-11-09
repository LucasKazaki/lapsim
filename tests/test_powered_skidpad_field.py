"""Field lifecycle/accounting tests with explicit numerical session doubles."""
import json
from types import SimpleNamespace

import pytest

import lapsim.events.powered_skidpad_field as field
from lapsim.events.skidpad_sequence import standard_skidpad_sequence
from lapsim.dynamics.planar import PlanarState


@pytest.fixture
def course():
    return standard_skidpad_sequence(entry_length_m=5., exit_length_m=5.)


def fake_numerics(monkeypatch, *, fail=None, mismatch=False, exception=None):
    sessions=[]
    def fresh(request):
        name=request.controller.philosophy
        binding={'request':{'controller':{'philosophy':name},'common':1},'runtime':{'same':True}}
        if mismatch and name=='traction':binding['runtime']['same']=False
        s=SimpleNamespace(request=request,binding=binding,initial_state=PlanarState(),
                          status='running',tick=0,attempted_steps=0,failure_reason=None)
        s.result=lambda:{'status':s.status,'qualified_tournament_result':False}
        sessions.append(s)
        return s
    def advance(s,steps):
        if exception and s.request.controller.philosophy==exception:
            raise RuntimeError('unexpected control-flow error')
        n=min(steps,3-s.attempted_steps)
        s.attempted_steps+=n
        if s.request.controller.philosophy==fail:
            s.status='model_error';s.failure_reason='explicit injected failed interval'
        else:
            s.tick+=n
            if s.tick==3:s.status='completed'
    def binding(output,s):
        (output/'binding.json').write_text(json.dumps(s.binding))
    def publish(output,s):
        data={'checkpoint.json':json.dumps({'status':s.status,'tick':s.tick,'attempted':s.attempted_steps}).encode(),
              'result.json':json.dumps(s.result()).encode()}
        for name,raw in data.items():(output/name).write_bytes(raw)
        (output/'files.json').write_text(json.dumps({'files':{}}))
        return {'checkpoint':str(output/'checkpoint.json')}
    monkeypatch.setattr(field,'fresh_session',fresh)
    monkeypatch.setattr(field,'advance_session',advance)
    monkeypatch.setattr(field,'write_session_binding',binding)
    monkeypatch.setattr(field,'publish_session',publish)
    return sessions


def test_field_runs_all_fixed_order_and_consumes_reservations(tmp_path,monkeypatch,course):
    sessions=fake_numerics(monkeypatch)
    r=field.run_field(tmp_path/'field',course=course,total_step_budget=20,wall_seconds=10,chunk_steps=2)
    assert r['status']=='completed_development_field'
    assert [c['controller'] for c in r['cells']]==['fixed','traction','yaw_pi','tire_reserve']
    assert all(c['status']=='completed' for c in r['cells'])
    assert r['reserved_steps']==16 and r['attempted_steps']==12
    assert r['winner'] is None and r['official_points'] is None
    assert r['qualified_tournament_result'] is False
    assert len(sessions)==4


def test_aggregate_pause_preserves_running_checkpoint_and_unrun_cells(tmp_path,monkeypatch,course):
    fake_numerics(monkeypatch)
    r=field.run_field(tmp_path/'field',course=course,total_step_budget=2,wall_seconds=10,chunk_steps=2)
    assert r['status']=='paused_aggregate_budget'
    assert r['cells'][0]['status']=='paused_aggregate_budget'
    assert r['cells'][0]['session_status']=='running'
    assert [c['status'] for c in r['cells'][1:]]==['unrun']*3
    raw=json.loads((tmp_path/'field/cells/fixed/checkpoint.json').read_bytes())
    assert raw['status']=='running'


def test_failed_interval_consumes_reservation_and_does_not_create_a_winner(tmp_path,monkeypatch,course):
    fake_numerics(monkeypatch,fail='fixed')
    r=field.run_field(tmp_path/'field',course=course,total_step_budget=20,wall_seconds=10,chunk_steps=2)
    assert r['status']=='finished_with_failures'
    assert r['cells'][0]['status']=='model_error'
    assert r['cells'][0]['attempted_steps']==2 and r['cells'][0]['accepted_steps']==0
    assert r['reserved_steps']==14 and r['attempted_steps']==11
    assert r['winner'] is None


def test_common_binding_mismatch_is_rejected_before_any_step(tmp_path,monkeypatch,course):
    sessions=fake_numerics(monkeypatch,mismatch=True)
    with pytest.raises(ValueError,match='matched'):
        field.run_field(tmp_path/'field',course=course,total_step_budget=20,wall_seconds=10)
    assert all(s.attempted_steps==0 for s in sessions)


def test_publishing_failure_stops_later_policies(tmp_path,monkeypatch,course):
    sessions=fake_numerics(monkeypatch)
    def fail(*args):raise OSError('injected writer failure')
    monkeypatch.setattr(field,'publish_session',fail)
    with pytest.raises(OSError,match='writer'):
        field.run_field(tmp_path/'field',course=course,total_step_budget=20,wall_seconds=10)
    assert sessions[0].tick==3
    assert all(s.attempted_steps==0 for s in sessions[1:])


def test_outer_wall_pause_keeps_inner_running(tmp_path,monkeypatch,course):
    sessions=fake_numerics(monkeypatch)
    values=iter([0.,0.,0.,0.,11.])
    monkeypatch.setattr(field.time,'monotonic',lambda:next(values,11.))
    r=field.run_field(tmp_path/'field',course=course,total_step_budget=20,wall_seconds=10,chunk_steps=2)
    assert r['status']=='paused_wall_budget'
    assert r['cells'][0]['session_status']=='running'
    assert r['cells'][0]['attempted_steps']==2
    assert all(s.attempted_steps==0 for s in sessions[1:])


def test_reservation_io_can_expire_wall_without_dispatch_or_refund(tmp_path,monkeypatch,course):
    sessions=fake_numerics(monkeypatch)
    values=iter([0.,0.,0.,11.])
    monkeypatch.setattr(field.time,'monotonic',lambda:next(values,11.))
    r=field.run_field(tmp_path/'field',course=course,total_step_budget=20,wall_seconds=10,chunk_steps=2)
    assert r['status']=='paused_wall_budget'
    assert r['reserved_steps']==2 and r['attempted_steps']==0
    assert r['cells'][0]['session_status']=='running'
    assert all(s.attempted_steps==0 for s in sessions)


def test_unexpected_exception_retains_actual_session_then_stops(tmp_path,monkeypatch,course):
    sessions=fake_numerics(monkeypatch,exception='fixed')
    r=field.run_field(tmp_path/'field',course=course,total_step_budget=20,wall_seconds=10,chunk_steps=2)
    assert r['status']=='execution_error'
    assert r['cells'][0]['session_status']=='running'
    assert 'unexpected' in r['cells'][0]['execution_error']
    assert all(s.attempted_steps==0 for s in sessions)


@pytest.mark.parametrize('budget,wall,chunk',[(True,10,2),(0,10,2),(40001,10,2),(10,float('nan'),2),(10,0,2),(10,10,0)])
def test_invalid_bounds_fail_before_creating_output(tmp_path,course,budget,wall,chunk):
    with pytest.raises(ValueError):
        field.run_field(tmp_path/'bad',course=course,total_step_budget=budget,wall_seconds=wall,chunk_steps=chunk)
    assert not (tmp_path/'bad').exists()


def test_real_aggregate_pause_checkpoint_restores_without_budget_rewrite(tmp_path,course):
    from hashlib import sha256
    from lapsim.events.powered_skidpad import resume, PoweredSkidpadRequest, Controller
    output=tmp_path/'real'
    result=field.run_field(output,course=course,total_step_budget=2,wall_seconds=10,chunk_steps=2)
    assert result['status']=='paused_aggregate_budget'
    assert result['attempted_steps']==result['reserved_steps']==2
    raw=(output/'cells/fixed/checkpoint.json').read_bytes()
    session=resume(raw,expected_sha256=sha256(raw).hexdigest(),
                   request=PoweredSkidpadRequest(course,Controller('fixed')))
    assert session.status=='running' and session.tick==2
    assert session.request.maximum_ticks==10000
    assert all(c['status']=='unrun' for c in result['cells'][1:])
    common=json.loads((output/'common-binding.json').read_bytes())
    assert 'controller' not in common['request']
    assert (output/'reservations/00001.json').exists()
    with pytest.raises(ValueError,match='new'):
        field.run_field(output,course=course,total_step_budget=2,wall_seconds=10)


def test_cli_does_not_accept_fresh_field_resume_flags(tmp_path):
    with pytest.raises(SystemExit) as error:
        field.main(['--entry-length-m','5','--exit-length-m','5','--total-step-budget','10',
                    '--wall-seconds','10','--output',str(tmp_path/'field'),
                    '--resume-checkpoint','old.json'])
    assert error.value.code==2
