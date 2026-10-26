"""Simulation-only shared-core configurator acceptance contracts."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from lapsim.dynamics.actuation import AWD_TOPOLOGY_ID,SINGLE_MOTOR_RWD_TOPOLOGY_ID
from lapsim.torque_configurator import ControlSession,VehicleProfile,example_profile
from lapsim.torque_configurator.adapter import simulate,validate
from lapsim.torque_configurator.session import replay


def frame(profile,now=0):
    return {'now_ms':now,'timestamp_ms':now,'accelerator_fraction':.5,'brake_fraction':0.,
            'steering_rad':0.,'wheel_speeds_rad_s':[25.]*4,'pack_energy_j':profile.actuation.pack_capacity_j*.7,
            'valid':True,'enabled':True,'restart_requested':False,'wheel_available':[False,False,True,True]}


def test_versioned_profile_snapshot_is_complete_and_immutable():
    p=example_profile();copy=p.to_dict();copy['policy']['maximum_drive_request_nm']=5
    assert p.policy['maximum_drive_request_nm']==400
    assert VehicleProfile.from_dict(p.to_dict()).sha256==p.sha256
    assert p.to_dict()['units']['torque']=='N*m'
    assert p.actuation.pack_capacity_j==5.5*3_600_000


def test_profile_identity_survives_browser_integer_number_serialization():
    p=example_profile()
    def javascript_numbers(value):
        if isinstance(value,dict):return {k:javascript_numbers(v) for k,v in value.items()}
        if isinstance(value,list):return [javascript_numbers(v) for v in value]
        if type(value) is float and value.is_integer():return int(value)
        return value
    transported=javascript_numbers(p.to_dict())
    assert VehicleProfile.from_dict(transported).sha256==p.sha256


@pytest.mark.parametrize('change',[
    lambda p:p.update(schema='v2'),lambda p:p.update(revision=True),
    lambda p:p.update(unknown_field=1),lambda p:p['vehicle'].pop('mass_kg'),
    lambda p:p['vehicle'].update(mass_kg=True),lambda p:p['actuation'].update(pack_voltage_v=float('nan')),
    lambda p:p['units'].update(torque='N*mm'),lambda p:p['units'].update(mass='lb'),
    lambda p:p['policy'].update(period_ms=10.),lambda p:p['policy'].update(maximum_drive_request_nm=-1),
    lambda p:p.update(evidence_status='road_ready'),lambda p:p['actuation'].update(pack_voltage_v=601),
    lambda p:p['vehicle'].update(mass_kg=10**400),
])
def test_invalid_or_ambiguous_profile_is_rejected(change):
    value=example_profile().to_dict();change(value)
    with pytest.raises(ValueError):VehicleProfile.from_dict(value)


@pytest.mark.parametrize('topology',[AWD_TOPOLOGY_ID,SINGLE_MOTOR_RWD_TOPOLOGY_ID])
def test_architecture_variants_are_not_parameter_changes(topology):
    value=example_profile().to_dict();value['actuation']['topology_id']=topology
    with pytest.raises(ValueError,match='topology must match'):VehicleProfile.from_dict(value)


@pytest.mark.parametrize('change',[
    lambda f:f.update(now_ms=True),lambda f:f.update(timestamp_ms=1.5),
    lambda f:f.update(accelerator_fraction=1.1),lambda f:f.update(pack_energy_j=-1),
    lambda f:f.update(valid=1),lambda f:f.update(wheel_speeds_rad_s=[25,25,True,25]),
    lambda f:f.update(wheel_available=[True,False,True,True]),lambda f:f.update(steering_rad=float('inf')),
])
def test_invalid_snapshot_does_not_advance_controller(change):
    profile=example_profile();session=ControlSession(profile);value=frame(profile);change(value)
    try:
        with pytest.raises(ValueError):session.step(value)
        assert session.backend.sequence==0
    finally:session.close()


def test_standalone_equal_split_and_repeat_preserve_all_stages_and_limits():
    profile=example_profile();frames=[frame(profile,i*10) for i in range(10)]
    a=replay(profile,frames);b=replay(profile,frames)
    assert a==b
    assert any(r['controller']['command_allowed'] for r in a)
    for result in a:
        raw=result['controller'];limited=result['limited']
        assert raw['allocator']['requested_nm']==200.
        assert raw['allocator']['wheel_torque_nm']==(0.,0.,100.,100.)
        assert limited['wheel_torques_nm'][:2]==(0.,0.)
        assert limited['wheel_torques_nm'][2]==limited['wheel_torques_nm'][3]
        assert sum(limited['wheel_torques_nm'])<=200.
        assert 0<=limited['pack_power_w']<=profile.actuation.pack_discharge_power_limit_w


@pytest.mark.parametrize('mode',('empty_pack','overspeed','stale','disabled','braking'))
def test_inhibition_or_physical_limits_leave_no_positive_command(mode):
    profile=example_profile();values=[]
    for i in range(10):
        value=frame(profile,(i+10)*10)
        if mode=='empty_pack':value['pack_energy_j']=0.
        elif mode=='overspeed':value['wheel_speeds_rad_s']=[2000.]*4
        elif mode=='stale':value['timestamp_ms']=0
        elif mode=='disabled':value['enabled']=False
        else:value['brake_fraction']=.25
        values.append(value)
    out=replay(profile,values)
    assert all(sum(item['limited']['wheel_torques_nm'])==0. for item in out)
    assert all(item['controller']['allocator']['requested_nm']==200. for item in out)


def test_power_and_current_parameter_change_limits_effort_without_changing_architecture():
    value=example_profile().to_dict();value['revision']=2
    value['actuation']['pack_discharge_power_limit_w']=15.
    value['actuation']['pack_discharge_current_limit_a']=.02
    profile=VehicleProfile.from_dict(value)
    out=replay(profile,[frame(profile,i*10) for i in range(10)])
    assert any(0<r['limited']['pack_power_w']<=11.6+1e-9 for r in out)
    assert all(r['limited']['pack_power_w']<=11.6+1e-9 for r in out)
    assert profile.to_dict()['architecture']==example_profile().to_dict()['architecture']


def test_real_plant_adapter_equals_standalone_exact_snapshot_replay():
    profile=example_profile();report=validate(profile,100)
    assert report['equivalent'] and report['repeat_exact'] and report['cycles']==10
    assert abs(report['energy_residual_j'])<.5
    integrated=report['integration']
    assert replay(profile,integrated['frames'])==integrated['outputs']
    assert any(sum(row['achieved_nm'])>0 for row in integrated['plant'])
    assert report['source']['backend']=='python_reference'


def test_standalone_serve_uses_the_simulator_lifecycle(monkeypatch):
    from lapsim.experiments import tournament_server
    from lapsim.torque_configurator.__main__ import main
    seen=[]
    monkeypatch.setattr(tournament_server,'main',lambda argv,**kw:seen.append((argv,kw)))
    assert main(['serve','--port','8768'])==0
    assert seen==[(['--port','8768'],{'page':'web/torque-configurator.html'})]
