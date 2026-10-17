"""Cancellation interrupts checked replay without returning partial evidence."""

import json
from threading import Event

import pytest

from lapsim.experiments import closed_loop, control_study


@pytest.fixture(scope="module")
def comparison():
    scenario = control_study.study_scenario(
        dict(control_study.DEFAULT_REQUEST, duration_s=0.1)
    )
    return control_study.run_control_comparison(scenario)


def test_single_run_replay_stops_at_next_plant_boundary_and_can_restart(
    comparison, monkeypatch
):
    record = comparison["runs"]["A"]
    before = json.dumps(record, sort_keys=True)
    cancelled = Event()
    original = closed_loop.advance_powered
    steps = 0

    def advance_then_cancel(*args, **kwargs):
        nonlocal steps
        result = original(*args, **kwargs)
        steps += 1
        if steps == 7:
            cancelled.set()
        return result

    monkeypatch.setattr(closed_loop, "advance_powered", advance_then_cancel)
    with pytest.raises(RuntimeError, match="cancelled"):
        closed_loop.replay_closed_loop(record, cancel=cancelled.is_set)
    assert steps == 7
    assert json.dumps(record, sort_keys=True) == before
    monkeypatch.setattr(closed_loop, "advance_powered", original)
    assert closed_loop.replay_closed_loop(record)["model_agreement"]


def test_paired_replay_cancelled_after_a_does_not_start_b(comparison, monkeypatch):
    cancelled = Event()
    started = []
    original = control_study.replay_closed_loop

    def replay_then_cancel(run, *args, **kwargs):
        started.append(run["scenario"]["strategy"])
        result = original(run, *args, **kwargs)
        cancelled.set()
        return result

    monkeypatch.setattr(control_study, "replay_closed_loop", replay_then_cancel)
    with pytest.raises(RuntimeError, match="cancelled"):
        control_study.replay_control_comparison(comparison, cancel=cancelled.is_set)
    assert started == ["equal_split"]


def test_already_cancelled_replay_starts_no_controller(comparison, monkeypatch):
    def unexpected_run(*args, **kwargs):
        pytest.fail("A cancelled import must not begin a controller simulation")

    monkeypatch.setattr(closed_loop, "run_closed_loop", unexpected_run)
    with pytest.raises(RuntimeError, match="cancelled"):
        control_study.replay_control_comparison(comparison, cancel=lambda: True)


def test_cancel_after_simulation_finishes_stops_result_verification(
    comparison, monkeypatch
):
    cancelled = Event()
    original = closed_loop.run_closed_loop

    def run_then_cancel(*args, **kwargs):
        result = original(*args, **kwargs)
        cancelled.set()
        return result

    monkeypatch.setattr(closed_loop, "run_closed_loop", run_then_cancel)
    with pytest.raises(RuntimeError, match="cancelled"):
        closed_loop.replay_closed_loop(
            comparison["runs"]["A"], cancel=cancelled.is_set
        )
