"""E17 numerical and orchestration counterexamples, no car-validation claim."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import random

import pytest

from lapsim.experiments import controller_tournament as search
from lapsim.experiments.tournament_rollout import (
    BOUNDS, Case, Controller, allocate, brake_request, course_for, fixture, rollout,
)
from lapsim.dynamics.planar import PlanarControls, PlanarState, evaluate_planar_dynamics
from lapsim.dynamics.powered_planar import PoweredState
from lapsim.dynamics.actuation import AWD_TOPOLOGY_ID, constrain_actuation


def braking(case):
    car, pack, _ = fixture()
    pack = replace(pack, pack_voltage_v=case.pack_voltage_v)
    p = PlanarState(u_mps=10, wheel_speeds_rad_s=(50.0,) * 4)
    state = PoweredState(p, (0.0,) * 4, case.initial_soc * pack.pack_capacity_j)
    physical = evaluate_planar_dynamics(car, p, PlanarControls())
    return allocate(Controller(), state, physical, 0, 0, 20, 0, car, pack, case)


@pytest.mark.parametrize("case", [Case("full", initial_soc=1), Case("voltage", pack_voltage_v=600),
    Case("offline", regen_available=False), Case("hot", motor_temperature_c=95)])
def test_unavailable_regen_is_not_credited_and_friction_fills(case):
    _, proposed, limited, brakes, _, shortfall, raw = braking(case)
    assert raw == 80
    assert sum(limited.wheel_torques_nm) == 0
    assert sum(brakes) == pytest.approx(80)
    assert shortfall == 0


def test_regen_only_region_exposes_loss_without_modeled_friction_actuator():
    _, _, limited, brakes, _, shortfall, _ = braking(Case("lost", regen_available=False, friction_fallback=False))
    assert sum(brakes) == 0
    assert limited.pack_power_w == 0
    assert shortfall == 80


def test_initial_region_requests_regen_only_and_stage_two_adds_friction():
    c = Controller()
    total, regen = brake_request(.1, c)
    assert total == regen == 32
    total, regen = brake_request(.8, c)
    assert 0 < regen < total


def test_short_run_is_not_a_completed_lap_and_repeats_exactly():
    case = Case("short", duration_s=.12)
    a, b = rollout(Controller(), case), rollout(Controller(), case)
    assert a == b
    assert not a["eligible"] and a["metrics"]["fitness"] is None
    assert a["status"] == "time_limit"
    assert [p["t_s"] for p in a["telemetry"]] == [0, .05, .1, .12]
    assert all(p["achieved_nm"][:2] == [0, 0] for p in a["telemetry"])


def test_actual_complete_lap_and_coherent_closed_track():
    record = rollout(Controller(), Case("complete"))
    assert record["eligible"] and record["status"] == "completed"
    assert record["metrics"]["completion_fraction"] == 1
    assert abs(record["metrics"]["energy_residual_j"]) < .001
    assert record["telemetry"][-1]["progress_m"] >= record["course"]["length_m"]
    for course in ("stadium", "reverse_stadium"):
        track = course_for(Case("geometry", course=course))
        track.validate_coherent_arcs()
        assert abs(track.x_m[-1] - track.x_m[0]) < 1e-10
        assert abs(track.y_m[-1] - track.y_m[0]) < 1e-10


@pytest.mark.parametrize("profile", ["real_2025", "hypothetical_awd"])
def test_unknown_real_parameters_and_unimplemented_topology_fail_closed(profile):
    with pytest.raises(ValueError):
        rollout(Controller(), Case("gate"), profile=profile)
    with pytest.raises(ValueError):
        search.specification(profile=profile)


def fake_rollout(controller, case, **kwargs):
    # A deliberate non-monotone landscape tests search bookkeeping independent
    # of physics, which is exercised above and in the upstream plant tests.
    fitness = 15 + (controller.drive_scale - .83) ** 2 * 10 + (.3 if case.patch else 0)
    valid = controller.drive_scale > .61
    return {"eligible": valid, "status": "completed" if valid else "invalid",
        "telemetry": [{"t_s": 0}], "metrics": {"elapsed_s": 10, "fitness": fitness if valid else None,
            "lap_time_s": fitness if valid else None, "net_energy_kwh": .01}}


def numerical_state(value):
    return {k: value[k] for k in ("runs", "candidates", "generations", "baselines", "holdout",
        "round_robin", "best_so_far", "rng_state", "status", "diagnostic_ids")}


def test_checkpoint_resume_matches_uninterrupted_and_rejects_source_change(tmp_path, monkeypatch):
    spec = search.specification(population=4, generations=3)
    full = search.run_search(tmp_path / "full", spec, rollout_fn=fake_rollout)
    paused = search.run_search(tmp_path / "resumed", spec, rollout_fn=fake_rollout, maximum_new_runs=3)
    assert paused["status"] == "paused_budget" and len(paused["runs"]) == 3
    resumed = search.run_search(tmp_path / "resumed", spec, resume=True, rollout_fn=fake_rollout)
    assert json.loads(search.canonical(numerical_state(full))) == json.loads(search.canonical(numerical_state(resumed)))
    assert len(resumed["round_robin"]) == 6
    assert resumed["holdout"]
    assert {c["name"] for c in spec["training"]}.isdisjoint({c["name"] for c in spec["holdout"]})
    with pytest.raises(ValueError, match="already contains"):
        search.run_search(tmp_path / "full", spec, rollout_fn=fake_rollout)
    monkeypatch.setattr(search, "sources", lambda: {"different": "hash"})
    with pytest.raises(ValueError, match="mismatch"):
        search.run_search(tmp_path / "resumed", spec, resume=True, rollout_fn=fake_rollout)


def test_mutation_stays_bounded_and_invalid_run_never_wins():
    rng = random.Random(408)
    genes = asdict(Controller())
    for _ in range(1000):
        genes = search.mutate(genes, rng)
        for key, (lo, hi) in BOUNDS.items():
            assert lo <= genes[key] <= hi
    invalid = {"eligible": False, "fitness": None}
    valid = {"eligible": True, "fitness": 100000}
    assert search.ordering(valid) < search.ordering(invalid)
    assert search.aggregate([{"eligible": False, "metrics": {"fitness": None, "lap_time_s": None, "net_energy_kwh": .01}}])["fitness"] is None


def test_awd_uses_four_actuators_but_retains_one_shared_pack_limit():
    _, pack, _ = fixture()
    awd = replace(pack, topology_id=AWD_TOPOLOGY_ID)
    with pytest.raises(ValueError, match="front drive"):
        constrain_actuation(pack, (10, 10, 10, 10), (50,) * 4, 1_000_000, .01)
    applied = constrain_actuation(awd, (200,) * 4, (100,) * 4, 1_000_000, .01, (True,) * 4)
    assert all(t > 0 for t in applied.wheel_torques_nm)
    assert applied.pack_power_w <= pack.pack_discharge_power_limit_w + 1e-8
    assert applied.pack_current_a <= pack.pack_discharge_current_limit_a
    assert applied.shared_power_scale < 1
    from lapsim.experiments.closed_loop import ClosedLoopScenario
    with pytest.raises(ValueError, match="topology"):
        ClosedLoopScenario(actuation=awd)


def test_friction_fallback_also_compensates_residual_positive_actuator_torque():
    car, pack, _ = fixture()
    p = PlanarState(u_mps=10, wheel_speeds_rad_s=(50,) * 4)
    state = PoweredState(p, (0, 0, 20, 20), 1_000_000)
    physical = evaluate_planar_dynamics(car, p, PlanarControls())
    values = allocate(Controller(), state, physical, 0, 0, 20, 0, car, pack, Case("residual"))
    assert sum(values[3]) == pytest.approx(120)
    assert values[5] == 0


def test_friction_capacity_shortfall_is_exposed_instead_of_inventing_brake_authority():
    car, pack, _ = fixture()
    p = PlanarState(u_mps=10, wheel_speeds_rad_s=(50,) * 4)
    state = PoweredState(p, (0, 0, 200, 200), 1_000_000)
    physical = evaluate_planar_dynamics(car, p, PlanarControls())
    values = allocate(Controller(), state, physical, 0, 0, 80, 0, car, pack, Case("capacity"))
    assert max(values[3]) <= 80
    assert values[5] > 0


def test_tire_reserve_controller_does_not_receive_heldout_true_grip():
    controller = Controller('tire_reserve')
    nominal = rollout(controller, Case('nominal', duration_s=.01), profile='synthetic_awd')
    low = rollout(controller, Case('unknown_surface', grip=.2, duration_s=.01), profile='synthetic_awd')
    assert nominal['telemetry'][0]['proposed_nm'] == low['telemetry'][0]['proposed_nm']


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), -1])
def test_gene_numeric_domain(bad):
    with pytest.raises(ValueError):
        Controller(drive_scale=bad)
