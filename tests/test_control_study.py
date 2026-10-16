"""The A/B wrapper holds conditions fixed and checks actual replayed outcomes."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from lapsim.experiments.control_study import (
    CASES,
    DEFAULT_REQUEST,
    replay_control_comparison,
    run_control_comparison,
    study_scenario,
)
from lapsim.experiments.dynamics_record import _content_id


@pytest.mark.parametrize("case", CASES)
def test_every_selectable_case_executes_both_real_loops_and_replays(case):
    scenario = study_scenario(dict(DEFAULT_REQUEST, case_id=case, duration_s=0.1))
    record = run_control_comparison(scenario)
    a, b = record["runs"]["A"], record["runs"]["B"]
    assert {k: v for k, v in a["scenario"].items() if k != "strategy"} == {
        k: v for k, v in b["scenario"].items() if k != "strategy"
    }
    assert a["result"]["controller_calls"] == b["result"]["controller_calls"] == 10
    assert (
        replay_control_comparison(json.loads(json.dumps(record)))["runs_replayed"] == 2
    )
    if case == "launch":
        # No invented gain when neither strategy needs to constrain slip.
        assert a["result"] == b["result"]


def rehash(record):
    record["run_id"] = _content_id({k: v for k, v in record.items() if k != "run_id"})


@pytest.mark.parametrize(
    "tamper", ["conditions", "metrics", "policy", "solver", "frames"]
)
def test_rehashed_comparison_cannot_change_fairness_metrics_or_physics_contract(tamper):
    original = run_control_comparison(
        study_scenario(dict(DEFAULT_REQUEST, duration_s=0.1))
    )
    record = deepcopy(original)
    if tamper == "conditions":
        record["runs"]["B"]["scenario"]["initial_soc"] = 0.4
    elif tamper == "metrics":
        record["metrics"]["A"]["distance_x_m"] += 1
    elif tamper == "policy":
        record["comparison_policy"] = "preferred winner"
    else:
        record["runs"]["A"][tamper][next(iter(record["runs"]["A"][tamper]))] = "changed"
        rehash(record["runs"]["A"])
    rehash(record)
    with pytest.raises(ValueError):
        replay_control_comparison(record)


def test_cancel_and_unavailable_backend_never_return_a_partial_or_relabelled_record():
    scenario = study_scenario(dict(DEFAULT_REQUEST, duration_s=0.1))
    with pytest.raises(RuntimeError, match="cancelled"):
        run_control_comparison(scenario, cancel=lambda: True)
    with pytest.raises(ValueError, match="Python reference"):
        run_control_comparison(replace(scenario, controller_backend_id="native_c"))


@pytest.mark.parametrize(
    "change",
    [
        {"duration_s": True},
        {"duration_s": 0.105},
        {"speed_mps": float("nan")},
        {"case_id": "AWD"},
        {"steering_deg": 11},
        {"extra": 1},
    ],
)
def test_invalid_request_fails_before_work(change):
    with pytest.raises(ValueError):
        study_scenario(dict(DEFAULT_REQUEST, **change))
