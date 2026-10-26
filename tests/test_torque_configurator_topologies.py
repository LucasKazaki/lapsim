"""Shared one-motor constraints, reset and source/plant equivalence contracts."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from lapsim.dynamics.actuation import TOPOLOGY_ID,SINGLE_MOTOR_RWD_TOPOLOGY_ID,AWD_TOPOLOGY_ID
from lapsim.torque_configurator import ControlSession,VehicleProfile,example_profile
from lapsim.torque_configurator.adapter import validate
from lapsim.torque_configurator.api import action
from lapsim.torque_configurator.export import export_source
from lapsim.torque_configurator.session import replay
from lapsim.torque_configurator.verify import verify_package

SUPPORTED=(TOPOLOGY_ID,SINGLE_MOTOR_RWD_TOPOLOGY_ID,AWD_TOPOLOGY_ID)


def frame(profile,now=0):
    return {'now_ms':now,'timestamp_ms':now,'accelerator_fraction':1.,'brake_fraction':0.,
            'steering_rad':0.,'wheel_speeds_rad_s':[25.,25.,20.,40.],
            'pack_energy_j':profile.actuation.pack_capacity_j*.7,'valid':True,'enabled':True,
            'restart_requested':False,'wheel_available':[True]*4 if profile.actuation.topology_id==AWD_TOPOLOGY_ID else [False,False,True,True]}


def changed(**changes):
    value=example_profile(SINGLE_MOTOR_RWD_TOPOLOGY_ID).to_dict()
    value['actuation'].update(changes)
    value['policy']['maximum_drive_request_nm']=1000.
    return VehicleProfile.from_dict(value)


def drive_trace(profile,count=10):
    values=[frame(profile,i*10) for i in range(count)]
    # The existing fault policy requires two unsaturated valid recovery samples.
    for value in values[:2]:value['accelerator_fraction']=0.
    return values


def test_examples_are_distinct_explicit_unvalidated_architectures():
    old=example_profile();single=example_profile(SINGLE_MOTOR_RWD_TOPOLOGY_ID)
    assert old.sha256=='a3d0dbed73480abf04b2854c96b10bea79f41fe311305be9c724008439d776df'
    assert single.sha256!=old.sha256
    assert single.to_dict()['evidence_status']=='synthetic_unvalidated'
    assert 'unverified' in single.to_dict()['provenance']
    assert single.actuation.topology_id==SINGLE_MOTOR_RWD_TOPOLOGY_ID


@pytest.mark.parametrize('architecture',SUPPORTED)
def test_declared_architecture_and_actuator_topology_must_agree(architecture):
    value=example_profile(architecture).to_dict()
    value['actuation']['topology_id']=SINGLE_MOTOR_RWD_TOPOLOGY_ID if architecture==TOPOLOGY_ID else TOPOLOGY_ID
    with pytest.raises(ValueError,match='topology must match'):VehicleProfile.from_dict(value)


@pytest.mark.parametrize('architecture',['unknown_awd_adapter',{},'team_real_rwd'])
def test_unsupported_architecture_never_reaches_export(architecture,tmp_path,monkeypatch):
    import lapsim.torque_configurator.api as api
    value=example_profile().to_dict();value['architecture']=architecture
    called=[];monkeypatch.setattr(api,'export_source',lambda *a:called.append(a))
    with pytest.raises(ValueError,match='architecture'):action('export',{'profile':value})
    assert not called


def test_single_motor_cap_mean_speed_and_electrical_budget_are_not_doubled():
    profile=changed()
    outputs=replay(profile,drive_trace(profile,12))
    pack=profile.actuation
    axle_cap=min(pack.motor_peak_torque_nm,min(pack.motor_current_limit_a,
        pack.inverter_current_limit_a)*pack.torque_constant_nm_per_a)*pack.gear_ratio*pack.gear_efficiency
    assert any(sum(row['limited']['wheel_torques_nm'])>0 for row in outputs)
    assert any(row['controller']['allocator']['status']=='saturated' and row['controller']['command_allowed'] for row in outputs)
    for row in outputs:
        raw=row['controller']['allocator']['wheel_torque_nm'];limited=row['limited']
        assert raw[:2]==(0.,0.) and raw[2]==raw[3]
        assert sum(raw)<=axle_cap+1e-10
        assert limited['motor_currents_a'][3]==0
        assert sum(abs(v) for v in limited['motor_currents_a'])<=pack.inverter_current_limit_a+1e-10
        assert limited['motor_speeds_rad_s']==(0.,0.,120.,0.)
        assert limited['wheel_power_w']==pytest.approx(limited['wheel_torques_nm'][2]*60)


def test_single_motor_shared_pack_power_current_limit():
    profile=changed(pack_discharge_power_limit_w=15.,pack_discharge_current_limit_a=.02)
    outputs=replay(profile,drive_trace(profile))
    assert any(row['limited']['pack_power_w']>0 for row in outputs)
    assert all(row['limited']['pack_power_w']<=11.6+1e-9 for row in outputs)


def test_saturated_start_does_not_bypass_reference_recovery_policy():
    profile=changed()
    outputs=replay(profile,[frame(profile,i*10) for i in range(5)])
    assert all(row['controller']['allocator']['status']=='saturated' for row in outputs)
    assert all(not row['controller']['command_allowed'] for row in outputs)
    assert all(sum(row['limited']['wheel_torques_nm'])==0 for row in outputs)


@pytest.mark.parametrize('availability',[(True,False),(False,True),(False,False)])
def test_either_missing_output_inhibits_shared_motor_without_asymmetric_candidate(availability):
    profile=changed();frames=[frame(profile,i*10) for i in range(10)]
    for value in frames:value['wheel_available'][2:]=availability
    outputs=replay(profile,frames)
    for row in outputs:
        assert row['controller']['allocator']['wheel_torque_nm']==(0.,)*4
        assert row['limited']['wheel_torques_nm']==(0.,)*4


@pytest.mark.parametrize('architecture',SUPPORTED)
def test_reset_clears_guard_clock_fault_and_sequence_without_changing_profile(architecture):
    profile=example_profile(architecture);session=ControlSession(profile)
    frames=drive_trace(profile)
    try:
        for value in frames:session.step(value)
        bad=frame(profile,100);bad.update(brake_fraction=.5)
        session.step(bad);old=session.backend
        session.reset()
        assert old.closed and session.backend.sequence==0
        assert [session.step(value) for value in frames]==replay(profile,frames)
    finally:session.close()


def test_one_axle_slew_budget_in_shared_guard_and_existing_plant():
    profile=changed(actuator_slew_nm_per_s=60.)
    report=validate(profile,300);rows=report['integration']['plant']
    assert report['equivalent'] and report['repeat_exact']
    commands=[sum(row['controller']['command_nm']) for row in report['integration']['outputs']]
    assert any(value>0 for value in commands)
    assert all(b-a<=.6+1e-9 for a,b in zip(commands,commands[1:]))
    for row in rows:
        assert row['actuator_memory_nm'][2]==row['actuator_memory_nm'][3]
        assert sum(abs(v) for v in row['actuator_rate_nm_per_s'])<=60.+1e-9
        assert row['motor_currents_a'][3]==0.
        assert row['achieved_pack_power_w']<=profile.actuation.pack_discharge_power_limit_w
    for a,b in zip(rows,rows[1:]):
        assert abs(sum(b['actuator_memory_nm'])-sum(a['actuator_memory_nm']))<=.6+1e-7
    assert abs(report['energy_residual_j'])<.5


@pytest.mark.parametrize('architecture',SUPPORTED)
def test_integrated_output_matches_fresh_standalone_sessions(architecture):
    profile=example_profile(architecture);report=validate(profile,100)
    assert report['integration']['outputs']==replay(profile,report['integration']['frames'])
    assert report['equivalent'] and report['repeat_exact']


def test_exported_single_motor_reproduces_control_and_plant_slew_evidence(tmp_path):
    profile=changed(actuator_slew_nm_per_s=60.)
    target=tmp_path/'single-source';export_source(profile,target,100)
    assert verify_package(target)['recorded_outputs_match']
    expected=validate(profile,100)
    env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'}
    env['LAPSIM_DATA_BUNDLE']=str(tmp_path/'nonexistent-private-bundle')
    output=tmp_path/'external-validation.json'
    result=subprocess.run([sys.executable,'-I',str(target/'run_controller.py'),'validate',
        '--profile',str(target/'profile.json'),'--duration-ms','100','--output',str(output)],
        cwd=tmp_path,env=env,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    assert json.loads(output.read_bytes())==json.loads(json.dumps(expected))


def awd_profile(**changes):
    value=example_profile(AWD_TOPOLOGY_ID).to_dict()
    value['actuation'].update(changes);value['policy']['maximum_drive_request_nm']=1000.
    return VehicleProfile.from_dict(value)


def test_four_motor_currents_have_individual_limits_and_one_shared_pack_budget():
    profile=awd_profile(motor_current_limit_a=3.,inverter_current_limit_a=2.,
                        pack_discharge_power_limit_w=15.,pack_discharge_current_limit_a=.02)
    outputs=replay(profile,drive_trace(profile))
    assert any(all(t>0 for t in row['limited']['wheel_torques_nm']) for row in outputs)
    for row in outputs:
        actual=row['limited']
        assert all(abs(current)<=2.+1e-10 for current in actual['motor_currents_a'])
        assert actual['pack_power_w']<=11.6+1e-9
        assert sum(actual['motor_currents_a'])<=8.+1e-10
        assert actual['motor_speeds_rad_s']==(100.,100.,80.,160.)


def test_awd_availability_does_not_impersonate_a_shared_rear_motor():
    profile=awd_profile();frames=drive_trace(profile)
    for value in frames:value['wheel_available'][0]=False
    outputs=replay(profile,frames)
    assert any(row['limited']['wheel_torques_nm'][1]>0 for row in outputs)
    assert all(row['limited']['wheel_torques_nm'][0]==0 for row in outputs)


def test_awd_per_channel_guard_and_plant_slew_and_pack_power_are_shared_by_both_paths():
    profile=awd_profile(actuator_slew_nm_per_s=60.,pack_discharge_power_limit_w=150.,
                        pack_discharge_current_limit_a=.2)
    report=validate(profile,300)
    assert report['equivalent'] and report['repeat_exact']
    rows=report['integration']['plant'];outputs=report['integration']['outputs']
    assert any(all(t>0 for t in row['achieved_nm']) for row in rows)
    for row in rows:
        assert all(abs(rate)<=60.+1e-9 for rate in row['actuator_rate_nm_per_s'])
        assert row['achieved_pack_power_w']<=116.+1e-9
    for a,b in zip(rows,rows[1:]):
        assert all(abs(y-x)<=.6+1e-7 for x,y in zip(a['actuator_memory_nm'],b['actuator_memory_nm']))
    for a,b in zip(outputs,outputs[1:]):
        assert all(y-x<=.6+1e-9 for x,y in zip(a['controller']['command_nm'],b['controller']['command_nm']))
    assert abs(report['energy_residual_j'])<.5


@pytest.mark.parametrize('architecture',SUPPORTED)
def test_calibrated_team_claims_are_rejected_before_export(architecture,monkeypatch):
    import lapsim.torque_configurator.api as api
    value=example_profile(architecture).to_dict();value['evidence_status']='team_calibrated'
    called=[];monkeypatch.setattr(api,'export_source',lambda *a:called.append(a))
    with pytest.raises(ValueError,match='synthetic'):action('export',{'profile':value})
    assert not called


def test_awd_export_reproduces_control_sensor_trace_and_plant_report(tmp_path):
    profile=example_profile(AWD_TOPOLOGY_ID);target=tmp_path/'awd-source'
    export_source(profile,target,100)
    assert verify_package(target)['recorded_outputs_match']
    output=tmp_path/'external-awd-validation.json'
    env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'}
    env['LAPSIM_DATA_BUNDLE']=str(tmp_path/'unavailable-private-bundle')
    result=subprocess.run([sys.executable,'-I',str(target/'run_controller.py'),'validate',
        '--profile',str(target/'profile.json'),'--duration-ms','100','--output',str(output)],
        cwd=tmp_path,env=env,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    assert json.loads(output.read_bytes())==json.loads(json.dumps(validate(profile,100)))
