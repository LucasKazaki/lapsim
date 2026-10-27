"""Actual-device parity of hybrid powered stages, including shaft/brake events."""
from dataclasses import replace
import os

import numpy as np
import pytest

from lapsim.dynamics.actuation import (ActuationConfig,AWD_TOPOLOGY_ID,
    SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID)
from lapsim.dynamics.planar import PlanarState
from lapsim.dynamics.planar_opencl import PlanarOpenCL
from lapsim.dynamics.powered_planar import PoweredState,advance_powered,energy_residual_j,_vector
from lapsim.dynamics.powered_opencl import PoweredInterval,advance_powered_batch
from lapsim.experiments.tournament_rollout import fixture


@pytest.fixture(scope='module')
def gpu():
    name=os.environ.get('LAPSIM_TEST_GPU')
    if not name:pytest.skip('Explicit GPU required; no CPU substitute')
    with PlanarOpenCL(device_name=name) as backend:yield backend


def request(topology=AWD_TOPOLOGY_ID,energy=None,regen=False,stop=False):
    car,act,_=fixture()
    act=replace(act,topology_id=topology)
    speed=.01 if stop else 8.
    plant=PlanarState(u_mps=speed,wheel_speeds_rad_s=(speed/car.wheel_radius_m,)*4)
    available=(True,)*4 if topology==AWD_TOPOLOGY_ID else (False,False,True,True)
    amount=-80. if regen else 120.
    command=tuple(amount if v else 0. for v in available)
    state=PoweredState(plant,command,act.pack_capacity_j*.7 if energy is None else energy)
    return PoweredInterval(car,act,state,command,(0.,)*4,(40.,)*4 if stop else (3.,)*4,
        available,.001,maximum_work=200000)


def reference(r):
    return advance_powered(r.config,r.actuation,r.state,r.command_nm,r.steering,r.brakes,
        r.available,r.timestep_s,r.environment,driver_proxy_n=r.driver_proxy_n,
        maximum_work=r.maximum_work,wheel_radii_m=r.wheel_radii_m)


def assert_parity(r,actual,expected):
    np.testing.assert_allclose(_vector(actual),_vector(expected),rtol=1e-10,atol=1e-8)
    assert actual.integration_substeps==expected.integration_substeps
    assert actual.integration_trials==expected.integration_trials
    assert actual.wheel_stop_events==expected.wheel_stop_events
    assert actual.wheel_stop_dissipation_j==pytest.approx(expected.wheel_stop_dissipation_j,abs=1e-20)
    assert 0<=actual.pack_energy_j<=r.actuation.pack_capacity_j
    assert min(actual.plant.wheel_speeds_rad_s)>=0
    assert abs(energy_residual_j(r.config,r.state,actual)-
        energy_residual_j(r.config,r.state,expected))<1e-7


def test_actual_gpu_powered_topologies_pack_limits_regen_and_unequal_radii(gpu):
    requests=[request(t,regen=regen) for t in
        (AWD_TOPOLOGY_ID,SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID)
        for regen in (False,True)]
    empty=request(energy=0.)
    full=request(regen=True)
    full=replace(full,state=replace(full.state,pack_energy_j=full.actuation.pack_capacity_j))
    mismatch=replace(request(SPOOL_RWD_TOPOLOGY_ID),wheel_radii_m=(.2,.2,.194,.206),
        steering=(.15,.15,0.,0.))
    requests += [empty,full,mismatch]
    actual,evidence=advance_powered_batch(gpu,requests)
    for r,a in zip(requests,actual,strict=True):assert_parity(r,a,reference(r))
    assert actual[-1].plant.wheel_speeds_rad_s[2]==actual[-1].plant.wheel_speeds_rad_s[3]
    assert actual[-3].pack_energy_j==0
    assert actual[-2].pack_energy_j==full.actuation.pack_capacity_j
    assert evidence['device_kernel_s']>0
    assert evidence['cpu_force_fallback'] is False


def test_actual_gpu_near_stop_events_do_not_reverse_or_hide_energy(gpu):
    requests=[replace(request(t,stop=True),command_nm=(0.,)*4,
        state=replace(request(t,stop=True).state,actuator_memory_nm=(0.,)*4),timestep_s=.01)
        for t in (AWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID)]
    actual,_=advance_powered_batch(gpu,requests)
    for r,a in zip(requests,actual,strict=True):
        assert_parity(r,a,reference(r))
        assert a.wheel_stop_events==4
        assert abs(energy_residual_j(r.config,r.state,a))<1e-5


def test_actual_gpu_continuous_intervals_repeat_and_state_is_not_reset(gpu):
    requests=[request(AWD_TOPOLOGY_ID),request(SINGLE_MOTOR_RWD_TOPOLOGY_ID,regen=True)]
    cpu=[r.state for r in requests];original=requests
    for _ in range(5):
        actual,_=advance_powered_batch(gpu,requests)
        for i,r in enumerate(requests):
            cpu[i]=reference(replace(r,state=cpu[i]))
            assert_parity(replace(r,state=original[i].state),actual[i],cpu[i])
        requests=[replace(r,state=a) for r,a in zip(requests,actual,strict=True)]
    assert actual[0].pack_energy_j<original[0].state.pack_energy_j
    assert actual[1].pack_energy_j>original[1].state.pack_energy_j
    first,_=advance_powered_batch(gpu,original)
    repeated,_=advance_powered_batch(gpu,original)
    for a,b in zip(first,repeated,strict=True):assert a==b


@pytest.mark.parametrize('kind',['topology','work','time','negative_brake','spool_speed'])
def test_actual_gpu_invalid_interval_rejected(gpu,kind):
    r=request(SPOOL_RWD_TOPOLOGY_ID)
    if kind=='topology':r=replace(r,command_nm=(1.,0.,10.,10.))
    elif kind=='work':r=replace(r,maximum_work=1,state=replace(r.state,integration_trials=1))
    elif kind=='time':r=replace(r,timestep_s=.02)
    elif kind=='negative_brake':r=replace(r,brakes=(-1.,0.,0.,0.))
    else:r=replace(r,state=replace(r.state,plant=replace(r.state.plant,wheel_speeds_rad_s=(40.,40.,39.,41.))))
    with pytest.raises(ValueError):reference(r)
    with pytest.raises(ValueError):advance_powered_batch(gpu,[r])
