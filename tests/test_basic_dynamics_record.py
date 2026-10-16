"""Clock ownership, capability identity and checked bicycle replay."""

from copy import deepcopy
from dataclasses import asdict, replace
import json

import pytest

from lapsim.dynamics.bicycle import BicycleConfig, BicycleControls
from lapsim.experiments.basic_dynamics import (
    BicycleScenario,
    decode_json,
    replay_bicycle_record,
    run_basic_json,
    run_bicycle_scenario,
)
from lapsim.experiments.dynamics_record import _content_id


def test_logging_rate_cannot_change_physics_and_export_keeps_model_identity():
    scenario = BicycleScenario(duration_s=0.2)
    first = run_bicycle_scenario(scenario)
    second = run_bicycle_scenario(replace(scenario, logging_period_s=0.04))
    assert first["result"]["states"][::2] == second["result"]["states"]
    assert first["result"]["evaluations"][::2] == second["result"]["evaluations"]
    assert first["scenario"]["model_id"] == "dynamic_bicycle_v1"
    assert first["scenario"]["vehicle_profile_id"] == "synthetic_bicycle_v1"
    assert first["scenario"]["controller_backend_id"] == "none_prescribed_force"
    encoded = run_basic_json(json.dumps(asdict(scenario)))
    assert replay_bicycle_record(decode_json(encoded))["model_agreement"]


def test_valid_hash_does_not_hide_fabricated_dynamics():
    record = run_bicycle_scenario(BicycleScenario(duration_s=0.1))
    record["result"]["states"][1]["y_m"] += 1
    record["run_id"] = _content_id(
        {key: value for key, value in record.items() if key != "run_id"}
    )
    with pytest.raises(ValueError, match="numeric mismatch"):
        replay_bicycle_record(record)


def test_replay_rejects_forged_units_even_with_a_valid_hash():
    record = run_bicycle_scenario(BicycleScenario(duration_s=0.1))
    record["units"]["force"] = "lbf"
    record["run_id"] = _content_id(
        {key: value for key, value in record.items() if key != "run_id"}
    )
    with pytest.raises(ValueError, match="units"):
        replay_bicycle_record(record)


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"a":NaN}', "x" * 8193])
def test_invalid_json_is_rejected(raw):
    with pytest.raises(ValueError):
        decode_json(raw, maximum_bytes=8192)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"model_id": "four_wheel"},
        {"controller_backend_id": "native_c"},
        {"schema_version": True},
        {"plant_step_s": True},
        {"logging_period_s": 0.003},
        {"controls": BicycleControls(front_force_request_n=1)},
        {"config": replace(BicycleConfig(), front_cornering_stiffness_n_per_rad=1e9)},
    ],
)
def test_unsupported_identity_clock_and_work_are_rejected(kwargs):
    with pytest.raises(ValueError):
        BicycleScenario(**kwargs)


def test_scenario_round_trip_rejects_missing_identity_and_bad_configuration():
    value = asdict(BicycleScenario())
    assert BicycleScenario.from_dict(value) == BicycleScenario()
    for change in (
        lambda v: v.pop("model_id"),
        lambda v: v["config"].update(mass_kg=False),
    ):
        invalid = deepcopy(value)
        change(invalid)
        with pytest.raises(ValueError):
            BicycleScenario.from_dict(invalid)


def test_dense_logging_is_bounded_before_a_large_record_is_allocated():
    with pytest.raises(ValueError, match="sample budget"):
        BicycleScenario(duration_s=20, logging_period_s=0.002)
