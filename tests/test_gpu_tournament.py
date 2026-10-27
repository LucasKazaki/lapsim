"""The resident backend reuses the simulator's controller/driver and records."""
import os
import numpy as np
import pytest

from lapsim.dynamics.powered_planar import advance_powered
from lapsim.experiments.gpu_tournament import GPUJob,rollout_gpu_batch
from lapsim.experiments.tournament_rollout import Controller,Case,rollout


def compare_records(actual,expected):
    for field in ('status','eligible','violations','controller','profile','topology','case','car','actuation','driver','clocks'):
        assert actual[field]==expected[field]
    assert actual['work']==expected['work']
    for key in expected['metrics']:
        a,e=actual['metrics'][key],expected['metrics'][key]
        if e is None or isinstance(e,str):assert a==e
        else:assert a==pytest.approx(e,rel=1e-8,abs=1e-7)
    assert len(actual['telemetry'])==len(expected['telemetry'])
    for a,e in zip(actual['telemetry'],expected['telemetry'],strict=True):
        for key in e:
            if key=='constraints':assert a[key]==e[key]
            else:np.testing.assert_allclose(a[key],e[key],rtol=1e-8,atol=1e-7)


def test_default_and_explicit_cpu_plant_seam_are_identical():
    c=Controller();case=Case('cpu-seam',duration_s=.1,regen_available=False)
    first=rollout(c,case,profile='synthetic_awd')
    second=rollout(c,case,profile='synthetic_awd',plant_step=advance_powered)
    assert first==second


def test_gpu_batch_invalid_scopes_rejected_before_device_creation():
    with pytest.raises(ValueError,match='uniform road'):
        rollout_gpu_batch([GPUJob('patch',Controller(),Case('patch',patch=True))],device_name='unavailable')
    job=GPUJob('same',Controller(),Case('x'))
    with pytest.raises(ValueError,match='Duplicate'):
        rollout_gpu_batch([job,job],device_name='unavailable')


def test_actual_gpu_short_rollouts_match_original_simulator_and_freeze_finished_lane():
    device=os.environ.get('LAPSIM_TEST_GPU')
    if not device:pytest.skip('Actual explicit GPU required')
    jobs=[GPUJob('short',Controller(),Case('short',duration_s=.05,regen_available=False)),
        GPUJob('rwd',Controller('traction',pedal_mode='proportional',yaw_kp=0.,yaw_ki=0.),Case('rwd',duration_s=.15),profile='synthetic_single_motor_rwd'),
        GPUJob('awd',Controller('yaw_pi'),Case('awd',duration_s=.15))]
    actual,evidence=rollout_gpu_batch(jobs,device_name=device)
    for job,record in zip(jobs,actual,strict=True):
        expected=rollout(job.controller,job.case,profile=job.profile)
        compare_records(record,expected)
    assert evidence['kernel_launches']==15
    assert evidence['cpu_physics_fallback'] is False
    assert evidence['owned_threads_exited'] is True
