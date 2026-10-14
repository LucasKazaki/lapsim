"""Generated contract checks; independent of team-private vehicle parameters."""
from dataclasses import fields
import math

from hypothesis import given, settings, strategies as st
import pytest

from lapsim.core.controls import Controls
from lapsim.core.profiles import ConstantControlsProfile, PiecewiseLinearControlsProfile

settings.register_profile('quality', max_examples=200, derandomize=True, deadline=None)
settings.load_profile('quality')
NONNEGATIVE = st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False)
DISTANCE = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)


@given(distance=DISTANCE, torque=NONNEGATIVE)
def test_constant_profile_preserves_controls(distance, torque):
    controls = Controls(motor_torque_request_nm=torque)
    assert ConstantControlsProfile(controls).controls_at(distance) is controls


@given(lower=NONNEGATIVE, upper=NONNEGATIVE, fraction=st.floats(0, 1))
def test_drive_interpolation_is_finite_and_bounded(lower, upper, fraction):
    profile = PiecewiseLinearControlsProfile((0.0, 100.0), (Controls(motor_torque_request_nm=lower), Controls(motor_torque_request_nm=upper)))
    result = profile.controls_at(100*fraction)
    assert math.isfinite(result.motor_torque_request_nm)
    assert min(lower, upper)-1e-9 <= result.motor_torque_request_nm <= max(lower, upper)+1e-9


@given(distance=st.floats(0, 1000), laps=st.integers(-10, 10))
def test_periodic_profile_repeats(distance, laps):
    profile = PiecewiseLinearControlsProfile((0.0, 50.0), (Controls(motor_torque_request_nm=20), Controls(motor_torque_request_nm=80)), period_m=100)
    assert profile.controls_at(distance).motor_torque_request_nm == pytest.approx(profile.controls_at(distance + laps*100).motor_torque_request_nm, abs=1e-9)


@given(field=st.sampled_from([f.name for f in fields(Controls)]), invalid=st.sampled_from([float('nan'), float('inf'), -float('inf')]))
def test_nonfinite_controls_are_rejected(field, invalid):
    with pytest.raises(ValueError):
        Controls(**{field: invalid})


@given(torque=st.floats(1, 1000), regen=st.floats(1, 1000), fraction=st.floats(0.01, 0.99))
def test_accepted_profile_is_sampleable_across_drive_regen_transition(torque, regen, fraction):
    # Reject an unsupported transition at construction, or return valid Controls.
    # Accepting a profile and crashing only when the solver samples it is unsafe.
    try:
        profile = PiecewiseLinearControlsProfile((0.0, 100.0), (Controls(motor_torque_request_nm=torque), Controls(rear_regenerative_brake_force_request_n=regen)))
    except ValueError:
        return
    result = profile.controls_at(100*fraction)
    assert not (result.motor_torque_request_nm > 0 and result.rear_regenerative_brake_force_request_n > 0)
