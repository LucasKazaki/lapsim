"""Actual resident GPU state/limit/event parity; never a CPU substitute."""
from dataclasses import replace
import os

import numpy as np
import pytest

from lapsim.backends.opencl_runtime import OpenCLError
from lapsim.dynamics.actuation import AWD_TOPOLOGY_ID,SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID
from lapsim.dynamics.conditions import PlanarEnvironment,PlanarRoad,RectangularGripPatch
from lapsim.dynamics.planar import PlanarState
from lapsim.dynamics.powered_opencl import PoweredInterval
from lapsim.dynamics.powered_planar import PoweredState,advance_powered,_vector
from lapsim.dynamics.resident_powered import ResidentPowered
from lapsim.experiments.tournament_rollout import fixture


@pytest.fixture
def device():
    name=os.environ.get('LAPSIM_TEST_GPU')
    if not name:pytest.skip('Explicit actual GPU required')
    return name


def sample(topology=AWD_TOPOLOGY_ID,regen=False):
    car,pack,_=fixture();pack=replace(pack,topology_id=topology)
    available=(True,)*4 if topology==AWD_TOPOLOGY_ID else (False,False,True,True)
    command=tuple((-80. if regen else 120.) if value else 0. for value in available)
    state=PoweredState(PlanarState(u_mps=8,wheel_speeds_rad_s=(40.,)*4),command,.7*pack.pack_capacity_j)
    return PoweredInterval(car,pack,state,command,(.04,.04,0.,0.),(3.,)*4,available,.01,maximum_work=200000)


def cpu(r):
    return advance_powered(r.config,r.actuation,r.state,r.command_nm,r.steering,r.brakes,
        r.available,r.timestep_s,r.environment,maximum_work=r.maximum_work,wheel_radii_m=r.wheel_radii_m)


def compare(actual,expected):
    np.testing.assert_allclose(_vector(actual),_vector(expected),rtol=1e-10,atol=1e-8)
    for field in ('integration_substeps','integration_trials','wheel_stop_events'):
        assert getattr(actual,field)==getattr(expected,field)
    assert actual.wheel_stop_dissipation_j==pytest.approx(expected.wheel_stop_dissipation_j,abs=1e-20)


def test_resident_gpu_all_topologies_regen_empty_full_and_radius_mismatch(device):
    rows=[sample(topology,regen) for topology in (AWD_TOPOLOGY_ID,SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID)
          for regen in (False,True)]
    rows.append(replace(rows[0],state=replace(rows[0].state,pack_energy_j=0.)))
    rows.append(replace(rows[1],state=replace(rows[1].state,pack_energy_j=rows[1].actuation.pack_capacity_j)))
    rows.append(replace(rows[4],wheel_radii_m=(.2,.2,.194,.206)))
    with ResidentPowered(rows,device_name=device) as backend:
        actual,evidence=backend.step()
        for r,a in zip(rows,actual,strict=True):compare(a,cpu(r))
        assert evidence['device_kernel_s']>0 and evidence['kernel_launches']==1
        assert evidence['cpu_fallback'] is False and evidence['state_uploaded_this_step'] is False


def test_resident_gpu_carries_state_and_changed_commands_without_reset(device):
    rows=[sample(),sample(SINGLE_MOTOR_RWD_TOPOLOGY_ID)]
    rows=[replace(r,state=replace(r.state,actuator_memory_nm=(0.,)*4)) for r in rows]
    with ResidentPowered(rows,device_name=device) as backend:
        for step in range(10):
            commands=[tuple((-60. if step>=5 else 90.) if v else 0. for v in r.available) for r in rows]
            actual,_=backend.step(commands=commands)
            expected=[cpu(replace(r,command_nm=command)) for r,command in zip(rows,commands,strict=True)]
            for a,e in zip(actual,expected,strict=True):compare(a,e)
            rows=[replace(r,state=e,command_nm=command) for r,e,command in zip(rows,expected,commands,strict=True)]
        assert actual[0].integration_substeps>1


def test_resident_gpu_brake_stop_events_equal_cpu(device):
    rows=[]
    for topology in (AWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID):
        r=sample(topology)
        rows.append(replace(r,command_nm=(0.,)*4,steering=(0.,)*4,brakes=(40.,)*4,
            state=PoweredState(PlanarState(u_mps=.01,wheel_speeds_rad_s=(.05,)*4),(0.,)*4,r.state.pack_energy_j)))
    with ResidentPowered(rows,device_name=device) as backend:
        actual,_=backend.step()
        for r,a in zip(rows,actual,strict=True):
            compare(a,cpu(r));assert a.wheel_stop_events==4
            assert min(a.plant.wheel_speeds_rad_s)>=0


def test_resident_gpu_shared_limits_and_interval_energy_headroom(device):
    rows=[]
    for topology in (AWD_TOPOLOGY_ID,SINGLE_MOTOR_RWD_TOPOLOGY_ID,SPOOL_RWD_TOPOLOGY_ID):
        r=sample(topology)
        rows.append(replace(r,actuation=replace(r.actuation,pack_discharge_power_limit_w=50)))
        rows.append(replace(r,state=replace(r.state,pack_energy_j=.001)))
        r=sample(topology,True)
        rows.append(replace(r,state=replace(r.state,pack_energy_j=r.actuation.pack_capacity_j-.001)))
    with ResidentPowered(rows,device_name=device) as backend:
        actual,_=backend.step()
        for r,a in zip(rows,actual,strict=True):
            compare(a,cpu(r));assert 0<=a.pack_energy_j<=r.actuation.pack_capacity_j


def test_resident_gpu_work_failure_is_latched_and_state_not_published(device):
    r=sample();r=replace(r,maximum_work=1,state=replace(r.state,integration_trials=1))
    with ResidentPowered([r],device_name=device) as backend:
        with pytest.raises(OpenCLError,match='cumulative powered work'):backend.step()
        assert tuple(backend.host[0,:23])==_vector(r.state)
        with pytest.raises(OpenCLError,match='latched'):backend.step()


def test_resident_gpu_rejects_unsupported_patch_and_invalid_command(device):
    r=sample(SINGLE_MOTOR_RWD_TOPOLOGY_ID)
    with pytest.raises(ValueError,match='uniform road'):
        ResidentPowered([replace(r,environment=PlanarEnvironment(road=PlanarRoad(patches=(RectangularGripPatch(0,1,0,1,.3),))))],device_name=device)
    with ResidentPowered([r],device_name=device) as backend:
        with pytest.raises(ValueError,match='equal rear'):backend.step(commands=[(0.,0.,100.,90.)])


def test_resident_gpu_explicit_new_session_repeats_exactly_and_closes(device):
    r=sample()
    with ResidentPowered([r],device_name=device) as first:a,_=first.step()
    with ResidentPowered([r],device_name=device) as second:b,_=second.step()
    assert a==b
    with pytest.raises(OpenCLError,match='closed'):first.step()


def test_resident_gpu_inactive_finished_lane_is_frozen_without_reset(device):
    rows=[sample(),sample()]
    with ResidentPowered(rows,device_name=device) as backend:
        first,_=backend.step()
        second,_=backend.step(active=[False,True])
        assert second[0]==first[0]
        compare(second[1],cpu(replace(rows[1],state=first[1])))
