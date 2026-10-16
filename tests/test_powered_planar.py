"""Actuator lag, wheel slip and signed energy evolve on the same RK stages."""

from dataclasses import replace

import pytest

from lapsim.dynamics.actuation import ActuationConfig
from lapsim.dynamics.planar import PlanarState, PlanarVehicleConfig
from lapsim.dynamics.powered_planar import (
    PoweredState,
    advance_powered,
    energy_residual_j,
)


def config():
    return PlanarVehicleConfig(300, 160, 0.8, 0.8, 1.2, 1.2, 0.2, 0.3, 1.2, 7000, 8000)


@pytest.mark.parametrize("brake", [4.0, 40.0])
def test_near_stop_braking_resolves_wheel_zero_without_reverse_or_energy_creation(
    brake,
):
    initial = PoweredState(
        PlanarState(u_mps=0.01, wheel_speeds_rad_s=(0.05,) * 4), (0.0,) * 4, 9000.0
    )
    start, final = run(initial=initial, command=(0.0,) * 4, brakes=(brake,) * 4)
    assert all(w >= 0 for w in final.plant.wheel_speeds_rad_s)
    assert 0 <= final.plant.u_mps < initial.plant.u_mps
    assert final.pack_energy_j == initial.pack_energy_j
    assert abs(energy_residual_j(config(), start, final)) < 1e-5
    assert final.wheel_stop_events == 4
    assert (
        final.wheel_stop_dissipation_j <= 4 * 0.5 * config().wheel_inertia_kgm2 * 1e-18
    )
    assert final.integration_trials + final.wheel_stop_events < 50_000


def run(
    step=0.001,
    initial=None,
    actuator=None,
    command=(0, 0, 100, 100),
    duration=0.1,
    brakes=(0,) * 4,
):
    car = config()
    act = actuator or ActuationConfig()
    start = initial or PoweredState(PlanarState(), (0.0,) * 4, 9e6)
    state = start
    for _ in range(round(duration / step)):
        state = advance_powered(
            car, act, state, command, (0,) * 4, brakes, (False, False, True, True), step
        )
    return start, state


def test_launch_contact_force_is_not_torque_over_radius_and_lag_is_real():
    start, final = run()
    assert final.plant.u_mps > 0
    assert 0 < final.actuator_memory_nm[2] < 100
    assert final.plant.wheel_speeds_rad_s[2] * 0.2 > final.plant.u_mps
    assert final.pack_energy_j < start.pack_energy_j
    assert final.conversion_loss_j > 0
    assert final.contact_dissipation_j > 0
    assert abs(energy_residual_j(config(), start, final)) < 0.01


def test_signed_energy_ledger_refines_without_soc_clipping():
    act = replace(ActuationConfig(), actuator_time_constant_s=0.04)
    # 9 MJ leaves a ~1e-8 J subtraction/accumulation floor. A 9 kJ store
    # resolves RK truncation without changing any active power/energy limit.
    initial = PoweredState(
        PlanarState(u_mps=5, wheel_speeds_rad_s=(25,) * 4), (0.0,) * 4, 9000
    )
    a0, a = run(0.0002, initial, act)
    b0, b = run(0.0001, initial, act)
    first, second = (
        abs(energy_residual_j(config(), a0, a)),
        abs(energy_residual_j(config(), b0, b)),
    )
    assert second < first / 8
    assert first < 0.001


def test_empty_pack_never_delivers_lagged_propulsion():
    initial = PoweredState(PlanarState(), (0, 0, 100, 100), 0)
    start, final = run(initial=initial)
    assert final.pack_energy_j == 0
    assert final.plant == start.plant


def test_full_pack_rejects_regen_and_friction_braking_still_works():
    act = ActuationConfig()
    initial = PoweredState(
        PlanarState(u_mps=10, wheel_speeds_rad_s=(50,) * 4),
        (0, 0, -100, -100),
        act.pack_capacity_j,
    )
    _, final = run(
        initial=initial, actuator=act, command=(0, 0, -100, -100), brakes=(5,) * 4
    )
    assert final.pack_energy_j == act.pack_capacity_j
    assert final.plant.u_mps < 10
    assert final.friction_brake_work_j < 0


def test_available_headroom_is_resolved_before_integration():
    act = ActuationConfig()
    initial = PoweredState(
        PlanarState(u_mps=10, wheel_speeds_rad_s=(50,) * 4),
        (0, 0, -100, -100),
        act.pack_capacity_j - 0.001,
    )
    _, final = run(
        initial=initial, actuator=act, command=(0, 0, -100, -100), duration=0.01
    )
    assert initial.pack_energy_j < final.pack_energy_j <= act.pack_capacity_j


def test_braking_stop_energy_residual_reduces_under_refinement():
    initial = PoweredState(
        PlanarState(u_mps=0.01, wheel_speeds_rad_s=(0.05,) * 4), (0.0,) * 4, 9000.0
    )
    coarse = run(step=0.0001, initial=initial, command=(0.0,) * 4, brakes=(40.0,) * 4)
    fine = run(step=0.00005, initial=initial, command=(0.0,) * 4, brakes=(40.0,) * 4)
    assert (
        abs(energy_residual_j(config(), *fine))
        < abs(energy_residual_j(config(), *coarse)) / 4
    )


def test_actual_trial_budget_is_enforced_before_unbounded_event_work():
    initial = PoweredState(PlanarState(), (0.0,) * 4, 9000.0, integration_trials=50_000)
    with pytest.raises(ValueError, match="actual work budget"):
        run(initial=initial)
