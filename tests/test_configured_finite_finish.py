"""Configured physical-finish admission and terminal-cause regressions.

Only the existing synthetic AWD example and built-in stadium are used.
No recorded vehicle geometry, hardware, or external driver artifact.
"""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from lapsim.dynamics.actuation import AWD_TOPOLOGY_ID
from lapsim.dynamics.planar import PlanarControls
from lapsim.experiments import tournament_rollout as runner
from lapsim.experiments.finite_gate_observer import FiniteGateObserver, validate_canonical_contract
from lapsim.torque_configurator import example_profile
from test_finite_observer import PREFIX, contract as toy_contract


def configured(laps=1, duration=None):
    p = example_profile(AWD_TOPOLOGY_ID)
    c = runner.Case("synthetic-physical-finish", laps=laps, duration_s=duration,
                    regen_available=False, pack_voltage_v=p.actuation.pack_voltage_v,
                    initial_soc=p.policy["initial_soc"])
    return c, p


def options(c, p):
    return {"profile": "synthetic_awd", "configured_profile": p,
            "configured_full_lap": True, "physical_finish": True,
            "finite_gate_contract": runner.physical_finish_contract(c, p),
            "stop_requested": lambda: False}


def simulate(c, kw):
    return runner.rollout(runner.Controller(runner.CONFIGURED_REFERENCE), c, **kw)


def nested_wrong_gate(g):
    """Malformed Python input must fail as a schema error before runtime."""
    value = []
    for _ in range(1200):
        value = [value]
    g["gates"][0]["center"] = value
    return g


def test_canonical_gates_are_body_shrunk_and_at_exact_source_seam():
    c, p = configured()
    g = runner.physical_finish_contract(c, p)
    track = runner.course_for(c)
    _, _, settings = runner.fixture()
    assert g["source_geometry_sha256"] == runner.course_geometry_sha256(track)
    assert len(g["gates"]) == 20
    assert [x["index"] for x in g["gates"]] == list(range(1, 21))
    assert g["gates"][-1]["station_m"] == track.length_m
    assert g["gates"][-1]["center"] == [track.x_m[0], track.y_m[0]]
    assert all(0. < x["center_half_width_m"] < settings.assumed_half_width_m
               for x in g["gates"])
    assert g == runner.physical_finish_contract(c, p)
    assert validate_canonical_contract(json.loads(json.dumps(g)), g) is g


@pytest.mark.parametrize("change", [
    lambda g: None,
    lambda g: {k: x for k, x in g.items() if k != "gates"},
    lambda g: {**g, "gates": []},
    lambda g: {**g, "gates": g["gates"][:-1]},
    lambda g: {**g, "gates": list(reversed(g["gates"]))},
    lambda g: {**g, "source_geometry_sha256": "0" * 64},
    lambda g: {**g, "corridor_sha256": "0" * 64},
    lambda g: {**g, "source_length_m": g["source_length_m"] + .01},
    lambda g: {**g, "gates": [{**g["gates"][0], "center_half_width_m": 3.}] + g["gates"][1:]},
    lambda g: {**g, "gates": [{**g["gates"][0], "center": [4.9, 0.]}] + g["gates"][1:]},
    lambda g: {**g, "gates": [{**g["gates"][0], "tangent": [-1., 0.]}] + g["gates"][1:]},
    lambda g: {**g, "gates": [{**g["gates"][0], "center": [5., False]}] + g["gates"][1:]},
    lambda g: {**g, "gates": [{**g["gates"][0], "center_half_width_m": float("nan")}] + g["gates"][1:]},
    lambda g: {**g, "gates": [{**g["gates"][0], "center": tuple(g["gates"][0]["center"])}] + g["gates"][1:]},
    lambda g: {**g, "gates": g["gates"] + [g["gates"][-1]]},
    nested_wrong_gate,
])
def test_missing_or_invalid_gate_contract_fails_before_session_or_plant(change, monkeypatch):
    c, p = configured(2)
    kw = options(c, p)
    kw["finite_gate_contract"] = change(deepcopy(kw["finite_gate_contract"]))

    def no_runtime(*args, **kwargs):
        pytest.fail("invalid gate contract reached controller session or plant")

    monkeypatch.setattr("lapsim.torque_configurator.ControlSession", no_runtime)
    monkeypatch.setattr(runner, "advance_powered", no_runtime)
    with pytest.raises(ValueError, match="finite|gate"):
        simulate(c, kw)


@pytest.mark.parametrize("change", [
    {"course": "reverse_stadium"}, {"course": "autocross"},
    {"mirror": True}, {"reverse": True}, {"initial_offset_m": .1},
])
def test_unreviewed_course_or_spawn_does_not_acquire_canonical_gates(change):
    c, p = configured()
    with pytest.raises(ValueError, match="original synthetic stadium"):
        runner.physical_finish_contract(replace(c, **change), p)


@pytest.mark.parametrize("change", [
    {"physical_finish": False}, {"physical_finish": 1},
    {"configured_full_lap": False}, {"configured_profile": None},
    {"stop_requested": None}, {"stop_requested": True},
])
def test_explicit_mode_cannot_fall_back_to_legacy(change):
    c, p = configured()
    with pytest.raises(ValueError):
        simulate(c, {**options(c, p), **change})


@pytest.mark.parametrize("laps", [1, 10])
def test_off_by_default_keeps_original_legacy_result_shape(laps):
    c, p = configured(laps, .1)
    kw = {"profile": "synthetic_awd", "configured_profile": p, "configured_full_lap": True}
    result = simulate(c, kw)
    assert result == simulate(c, {**kw, "physical_finish": False})
    assert "finite_terminal" not in result
    assert "completion_owner" not in result["configuration"]
    assert result["configuration"]["mode"] == ("ten_lap_acceptance_v1" if laps == 10 else "full_lap_acceptance_v1")
    assert result["status"] == "time_limit"
    assert result["metrics"]["lap_time_s"] is None
    if laps == 10:
        assert result["round"]["completed_laps"] == 0


def test_timed_and_two_lap_cases_cannot_implicitly_switch_mode():
    c, p = configured()
    kw = options(c, p)
    with pytest.raises(ValueError):
        simulate(replace(c, duration_s=1.), kw)
    with pytest.raises(ValueError):
        simulate(replace(c, duration_s=1.), {**kw, "physical_finish": False})
    with pytest.raises(ValueError):
        replace(c, laps=2, duration_s=1.)
    with pytest.raises(ValueError):
        replace(c, laps=10)


def test_external_cancellation_at_accepted_boundary_does_not_create_a_lap():
    c, p = configured(2)
    r = simulate(c, {**options(c, p), "stop_requested": lambda: True})
    f = r["finite_terminal"]
    assert r["status"] == "external_stop"
    assert f["accepted_ticks"] == 0
    assert r["round"]["completed_laps"] == 0
    assert not f["finite_completion"]["accepted_completion"]
    assert f["finite_completion"]["finish_event"] is None
    assert r["metrics"]["round_time_s"] is None


@pytest.mark.parametrize("laps", [1, 2])
def test_actual_residual_drive_brake_shortfall_is_stock_not_gate_violation(laps, monkeypatch):
    # The plant and original configured brake blend actually run. This
    # deliberately faulty synthetic driver changes from drive to maximal
    # braking while drive torque is still stored. No fake state/progress.
    c, p = configured(laps)
    calls = 0

    def driver(track, car, env, settings, state, projection, slack):
        nonlocal calls
        calls += 1
        if calls <= 2:
            return PlanarControls(drive_torques_nm=(0., 0., settings.maximum_rear_drive_torque_nm,
                                                   settings.maximum_rear_drive_torque_nm)), 1.
        return PlanarControls(brake_torques_nm=(settings.maximum_wheel_brake_torque_nm,)*4), 1.

    monkeypatch.setattr(runner, "_controller", driver)
    # A cancellation fallback bounds this negative regression if its
    # intended stock failure ever stops occurring; a cancellation is a
    # failed test, not a completed lap.
    r = simulate(c, {**options(c, p), "stop_requested": lambda: calls > 10})
    terminal = r["finite_terminal"]
    f = terminal["finite_completion"]
    assert r["status"] == "invalid"
    assert "brake_shortfall" in r["violations"]
    assert r["telemetry"][-1]["brake_shortfall_nm"] > 1e-6
    assert terminal["detail"] == "Existing stock rollout violation"
    assert not any(x.startswith("finite_gate:") for x in r["violations"])
    assert f["failure"]["reason"] == "stock_boundary_rejected"
    assert f["finish_event"] is None and not f["accepted_completion"]
    assert r["metrics"]["lap_time_s"] is None
    assert not r["configuration"]["acceptance"]["passed"]
    assert terminal["accepted_ticks"] > 0


def test_single_final_physical_event_cannot_earn_lap_on_stock_invalid_boundary():
    a = FiniteGateObserver(toy_contract())
    seq = PREFIX + [((.2, 0.), 12.2)]
    for tick, (xy, station) in enumerate(seq):
        a.observe(tick, xy, 1000.-tick, station, boundary_ok=tick < len(seq)-1)
    assert not a.done
    assert a.failure["reason"] == "stock_boundary_rejected"
    assert a.receipt()["finish_event"] is None
    assert len(a.events) == a.n  # physical event remains diagnostic only


def test_legacy_comparison_cannot_mislabel_a_finite_finish_record():
    from lapsim.torque_configurator import comparison
    c, p = configured()
    with pytest.raises(ValueError, match="physical_finish"):
        comparison.execute(p, c, full_lap=True)
    with pytest.raises(ValueError, match="legacy comparison"):
        comparison.assemble([p], c, [], {}, full_lap=True)
