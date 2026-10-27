"""Frozen spool angular constraint, unequal-radius scrub and energy oracles."""
from dataclasses import replace
from math import isclose

import pytest

from lapsim.dynamics.actuation import ActuationConfig, SPOOL_RWD_TOPOLOGY_ID, SINGLE_MOTOR_RWD_TOPOLOGY_ID, constrain_actuation
from lapsim.dynamics.conditions import PlanarEnvironment
from lapsim.dynamics.planar import PlanarControls, PlanarState, evaluate_planar_dynamics
from lapsim.dynamics.powered_planar import PoweredState, advance_powered, evaluate_powered, energy_residual_j
from lapsim.torque_configurator import example_profile

ZERO=(0.,)*4
AVAILABLE=(False,False,True,True)
RADII=(.2,.2,.196,.204)


def car():return example_profile().vehicle
def pack():return replace(example_profile().actuation,topology_id=SPOOL_RWD_TOPOLOGY_ID)
def rolling(speed=5.):return PlanarState(u_mps=speed,wheel_speeds_rad_s=(speed/.2,)*4)


def test_spool_electrical_unit_is_one_motor_and_requires_one_shaft_speed():
    p=pack()
    value=constrain_actuation(p,(0,0,1000,1000),(25,25,25,25),9000,.01,AVAILABLE)
    assert value.wheel_torques_nm[2]==value.wheel_torques_nm[3]
    assert value.motor_currents_a[3]==0
    assert sum(abs(v) for v in value.motor_currents_a)<=p.inverter_current_limit_a+1e-10
    with pytest.raises(ValueError,match='angular'):
        constrain_actuation(p,(0,0,20,20),(25,25,24,26),9000,.01,AVAILABLE)
    open_pack=replace(p,topology_id=SINGLE_MOTOR_RWD_TOPOLOGY_ID)
    assert constrain_actuation(open_pack,(0,0,20,20),(25,25,24,26),9000,.01,AVAILABLE).wheel_torques_nm[2]>0


def test_unequal_effective_radii_do_not_mean_equal_ground_or_surface_speed():
    p=rolling()
    physical=evaluate_planar_dynamics(car(),p,PlanarControls(wheel_radii_m=RADII))
    left,right=physical.wheels[2:]
    assert left.slip_ratio==pytest.approx(-.02)
    assert right.slip_ratio==pytest.approx(.02)
    assert left.local_force_x_n<0<right.local_force_x_n
    assert p.wheel_speeds_rad_s[2]==p.wheel_speeds_rad_s[3]
    assert RADII[2]*p.wheel_speeds_rad_s[2]!=RADII[3]*p.wheel_speeds_rad_s[3]
    assert physical.contact_dissipation_w>0
    assert abs(physical.energy_balance_residual_w)<1e-8


def test_constraint_reaction_is_opposite_and_has_zero_power_at_equal_omega():
    state=PoweredState(rolling(),(0,0,30,30),9000.)
    rate,physical,electrical=evaluate_powered(car(),pack(),state,(0,0,30,30),ZERO,ZERO,AVAILABLE,.01,PlanarEnvironment(),wheel_radii_m=RADII)
    assert rate[8]==rate[9]
    reactions=physical.axle_constraint_reactions_nm
    assert reactions[2]==pytest.approx(-reactions[3]) and abs(reactions[2])>0
    assert sum(t*w for t,w in zip(reactions,state.plant.wheel_speeds_rad_s))==pytest.approx(0,abs=1e-10)
    free=evaluate_planar_dynamics(car(),state.plant,PlanarControls(drive_torques_nm=electrical.wheel_torques_nm,wheel_radii_m=RADII))
    expected=(free.derivative.wheel_accelerations_rad_s2[2]+free.derivative.wheel_accelerations_rad_s2[3])/2
    assert rate[8]==pytest.approx(expected)


def test_asymmetric_brake_at_rest_can_hold_the_entire_coupled_shaft():
    state=PoweredState(PlanarState(),(0,0,30,30),9000.)
    rate,physical,_=evaluate_powered(car(),pack(),state,(0,0,30,30),ZERO,(0,0,80,0),AVAILABLE,.01,PlanarEnvironment())
    assert rate[8]==rate[9]==0
    assert physical.wheels[2].applied_brake_torque_nm==pytest.approx(-60)
    assert physical.wheels[3].applied_brake_torque_nm==0


def test_unequal_speed_initial_state_rejects_without_an_energy_projection():
    state=PoweredState(replace(rolling(),wheel_speeds_rad_s=(25,25,24,26)),ZERO,9000.)
    with pytest.raises(ValueError,match='angular'):
        advance_powered(car(),pack(),state,ZERO,ZERO,ZERO,AVAILABLE,.01)


@pytest.mark.parametrize('speed',[.00017,.00123,.00001337])
def test_static_shaft_balance_has_exact_zero_acceleration_when_one_brake_can_hold(speed):
    state=PoweredState(PlanarState(u_mps=speed),ZERO,9000.)
    rate,_,_=evaluate_powered(car(),pack(),state,ZERO,ZERO,(0,0,40,0),AVAILABLE,.01,PlanarEnvironment(),wheel_radii_m=RADII)
    assert rate[8]==rate[9]==0


def test_locked_shaft_stays_equal_through_all_rk_stages_with_scrub_and_energy_balance():
    initial=PoweredState(rolling(),ZERO,9000.)
    state=initial
    for _ in range(10):
        state=advance_powered(car(),pack(),state,(0,0,30,30),(.03,.03,0,0),ZERO,AVAILABLE,.01,wheel_radii_m=RADII)
        assert state.plant.wheel_speeds_rad_s[2]==state.plant.wheel_speeds_rad_s[3]
    assert state.contact_dissipation_j>0
    assert abs(energy_residual_j(car(),initial,state))<.01
    assert state.pack_energy_j<initial.pack_energy_j


def test_one_rear_brake_stops_both_coupled_wheels_without_reverse_or_energy_creation():
    initial=PoweredState(rolling(.01),ZERO,9000.)
    state=initial
    for _ in range(10):
        state=advance_powered(car(),pack(),state,ZERO,ZERO,(0,0,40,0),AVAILABLE,.01)
        assert state.plant.wheel_speeds_rad_s[2]==state.plant.wheel_speeds_rad_s[3]>=0
    assert state.plant.u_mps<initial.plant.u_mps
    assert state.wheel_stop_events>=2
    assert state.pack_energy_j==initial.pack_energy_j
    assert abs(energy_residual_j(car(),initial,state))<.01


@pytest.mark.parametrize('radii',[(.2,.2,0,.2),(.2,.2,float('nan'),.2),(.2,.2,True,.2),(.2,.2,.2)])
def test_invalid_contact_radii_are_rejected(radii):
    with pytest.raises((ValueError,TypeError)):
        evaluate_planar_dynamics(car(),rolling(),PlanarControls(wheel_radii_m=radii))


def test_default_effective_radius_path_preserves_existing_planar_result():
    state=rolling()
    a=evaluate_planar_dynamics(car(),state,PlanarControls())
    b=evaluate_planar_dynamics(car(),state,PlanarControls(wheel_radii_m=(.2,)*4))
    assert a==b
