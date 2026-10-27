"""CPU contracts always run; actual GPU tests require an explicit device name."""
from dataclasses import replace
import os

import numpy as np
import pytest

from lapsim.backends.opencl_runtime import OpenCLError
from lapsim.dynamics.conditions import (PlanarEnvironment, PlanarRoad,
    RectangularGripPatch, RoadDomain)
from lapsim.dynamics.planar import PlanarControls, PlanarState
from lapsim.dynamics.planar_opencl import (FIELDS, PlanarOpenCL, PlanarSample,
    evaluate_cpu, pack_samples,unpack_evaluation)
from lapsim.dynamics.planar import evaluate_planar_dynamics
from lapsim.experiments.closed_loop import synthetic_car


def samples():
    car = synthetic_car()
    rolling = PlanarState(u_mps=12, wheel_speeds_rad_s=(60.,)*4)
    environment = PlanarEnvironment(wind_world_x_mps=3, wind_world_y_mps=-2,
        drag_area_m2=.8, road=PlanarRoad(patches=(RectangularGripPatch(-2,2,0,4,.2),),
        valid_domain=RoadDomain(-5,5,-5,5)))
    states = [rolling, PlanarState(), replace(rolling, x_m=10),
        replace(rolling, u_mps=.1, wheel_speeds_rad_s=(0.,1.,-1.,0.)),
        replace(rolling, v_mps=4, yaw_rate_rad_s=.8, heading_rad=2.8),
        replace(rolling, u_mps=-3, wheel_speeds_rad_s=(-20.,)*4)]
    controls = [PlanarControls(),
        PlanarControls(steering_angles_rad=(.3,.25,0.,0.), drive_torques_nm=(100.,-80.,0.,40.),
            brake_torques_nm=(150.,30.,20.,100.), wheel_radii_m=(.18,.19,.20,.21),
            external_force_x_n=150,external_force_y_n=-50,external_yaw_moment_nm=20),
        PlanarControls(normal_loads_n=(0.,300.,800.,0.))]
    return [PlanarSample(car, state, control, environment) for state in states for control in controls]


def test_packing_units_and_independent_rows():
    values = samples()
    packed = pack_samples(values)
    assert packed.shape == (18,60)
    assert packed.dtype == np.float64
    assert len(FIELDS) == 89
    assert packed[0,0] == values[0].config.mass_kg
    assert packed[1,33:37] == pytest.approx((.18,.19,.20,.21))
    assert packed[0,45:49] == pytest.approx((.2,1.,.2,1.))
    assert not packed[6,49:53].any()
    assert evaluate_cpu(values).shape == (18,89)


@pytest.mark.parametrize('bad', [[], [None]])
def test_invalid_packing_rejected(bad):
    with pytest.raises((TypeError,ValueError)):
        pack_samples(bad)


def test_invalid_sample_type_rejected():
    with pytest.raises(TypeError):
        PlanarSample(synthetic_car(),None,PlanarControls())


def test_uniform_road_fast_path_preserves_zero_grip_and_parameter_identity():
    original=samples()[0]
    values=[replace(original,environment=PlanarEnvironment(road=PlanarRoad(base_friction_multiplier=v)))
            for v in (0.,.3,1.7)]
    packed=pack_samples(values)
    np.testing.assert_array_equal(packed[:,45:49],np.asarray([[0.]*4,[.3]*4,[1.7]*4]))
    assert packed[:,49:53].all()


def test_typed_output_reconstruction_preserves_every_numeric_and_material_field():
    values=samples()
    for sample,row in zip(values,evaluate_cpu(values),strict=True):
        expected=evaluate_planar_dynamics(sample.config,sample.state,sample.controls,
            environment=sample.environment)
        assert unpack_evaluation(sample,row)==expected


@pytest.fixture(scope='module')
def gpu():
    name = os.environ.get('LAPSIM_TEST_GPU')
    if not name:
        pytest.skip('Actual GPU checks require explicit LAPSIM_TEST_GPU; no CPU substitute')
    with PlanarOpenCL(device_name=name) as backend:
        yield backend


def test_actual_gpu_all_fields_against_independent_cpu(gpu):
    values = samples()
    actual, evidence = gpu.evaluate(values)
    expected = evaluate_cpu(values)
    np.testing.assert_allclose(actual,expected,rtol=1e-10,atol=1e-8)
    assert evidence['device_kernel_s'] > 0
    assert evidence['backend'] == 'OpenCL GPU FP64'
    assert evidence['cpu_fallback'] is False
    assert evidence['device'] == gpu.runtime.device.name
    assert np.max(np.abs(actual[:,FIELDS.index('energy_balance_residual_w')])) < 1e-8
    for wheel in ('FL','FR','RL','RR'):
        fx = actual[:,FIELDS.index(wheel+'.local_force_x_n')]
        fy = actual[:,FIELDS.index(wheel+'.local_force_y_n')]
        cap = actual[:,FIELDS.index(wheel+'.friction_limit_n')]
        assert np.all(np.hypot(fx,fy) <= cap+1e-9)


def test_actual_gpu_repeat_and_reordered_batch_are_identical(gpu):
    values = samples()
    first, _ = gpu.evaluate(values)
    second, _ = gpu.evaluate(values)
    reversed_values, _ = gpu.evaluate(list(reversed(values)))
    np.testing.assert_array_equal(first,second)
    np.testing.assert_array_equal(first,reversed_values[::-1])


def test_actual_gpu_changed_parameters_reach_physics(gpu):
    sample = samples()[1]
    changed = replace(sample, config=replace(sample.config,mass_kg=420,
        wheel_inertia_kgm2=.7,tire_mu=.3,cornering_stiffness_n_per_rad=3500))
    actual,_ = gpu.evaluate([sample,changed])
    expected=evaluate_cpu([sample,changed])
    np.testing.assert_allclose(actual,expected,rtol=1e-10,atol=1e-8)
    assert actual[0,FIELDS.index('u_dot_mps2')] != actual[1,FIELDS.index('u_dot_mps2')]


def test_actual_gpu_rejects_nonfinite_and_wrong_shape(gpu):
    bad = pack_samples(samples())
    bad[0,0] = np.nan
    with pytest.raises(ValueError,match='finite'):
        gpu.runtime.execute(bad,len(FIELDS))
    with pytest.raises(ValueError,match='float64'):
        gpu.runtime.execute(np.zeros((1,60),dtype=np.float32),len(FIELDS))


def test_actual_gpu_closed_context_never_falls_back():
    name = os.environ.get('LAPSIM_TEST_GPU')
    if not name:
        pytest.skip('Explicit GPU device required')
    backend = PlanarOpenCL(device_name=name)
    backend.close()
    backend.close()
    with pytest.raises(OpenCLError,match='closed'):
        backend.evaluate(samples())
