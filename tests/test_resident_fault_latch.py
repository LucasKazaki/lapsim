"""Host protocol fault injection; these tests do not claim GPU physics parity."""
from dataclasses import replace
from types import SimpleNamespace
import ctypes as ct

import numpy as np
import pytest

from lapsim.backends.opencl_runtime import OpenCLError
from lapsim.dynamics.actuation import AWD_TOPOLOGY_ID
from lapsim.dynamics.planar import PlanarState
from lapsim.dynamics.powered_opencl import PoweredInterval
from lapsim.dynamics.powered_planar import PoweredState,_vector
from lapsim.dynamics.resident_powered import ResidentPowered,_parameters
from lapsim.experiments.tournament_rollout import fixture


class FaultAPI:
    def __init__(self,stage):
        self.stage=stage;self.calls=[];self.device_intervals=0;self.profiles=0

    def result(self,stage):
        self.calls.append(stage)
        return -5 if stage==self.stage else 0

    def clEnqueueWriteBuffer(self,*args):return self.result('write')

    def clEnqueueNDRangeKernel(self,*args):
        if self.stage!='launch':
            self.device_intervals+=1
            ct.cast(args[-1],ct.POINTER(ct.c_void_p))[0]=ct.c_void_p(1)
        return self.result('launch')

    def clEnqueueReadBuffer(self,*args):return self.result('read')

    def clGetEventProfilingInfo(self,*args):
        self.profiles+=1
        return self.result('profile-start' if self.profiles==1 else 'profile-end')

    def clFinish(self,*args):return self.result('finish')
    def clReleaseEvent(self,*args):return self.result('release')


def session(stage):
    car,pack,_=fixture();pack=replace(pack,topology_id=AWD_TOPOLOGY_ID)
    command=(20.,)*4
    state=PoweredState(PlanarState(u_mps=8,wheel_speeds_rad_s=(40.,)*4),command,.7*pack.pack_capacity_j)
    request=PoweredInterval(car,pack,state,command,(0.,)*4,(0.,)*4,(True,)*4,.01)
    # Inject only the OpenCL transport. No constructor/device, numerical solve
    # or fallback is used; device_intervals models an already queued advance.
    backend=ResidentPowered.__new__(ResidentPowered)
    backend.requests=(request,);backend.parameters=_parameters([request]);backend.faulted=False
    backend.host=np.asarray([(*_vector(state),0.,0.,0.,0.,0.)],dtype=np.float64)
    backend.parameter_buffer=1;backend.state_buffer=2
    api=FaultAPI(stage)
    backend.runtime=SimpleNamespace(api=api,queue=1,kernel=2,device=SimpleNamespace(name='injected transport'),source_sha256='test')
    return backend,api


@pytest.mark.parametrize('stage',['write','launch','read','profile-start','profile-end','finish','release'])
def test_transport_failure_latches_session_and_blocks_retry_before_enqueue(stage):
    backend,api=session(stage)
    with pytest.raises(OpenCLError):backend.step()
    assert backend.faulted is True
    calls=api.calls.copy();advances=api.device_intervals
    with pytest.raises(OpenCLError,match='latched'):backend.step()
    assert api.calls==calls and api.device_intervals==advances
    if stage in ('read','profile-start','profile-end','finish','release'):
        assert advances==1
        assert 'finish' in calls and 'release' in calls
