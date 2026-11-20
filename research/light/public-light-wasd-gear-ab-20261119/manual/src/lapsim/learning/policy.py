"""A small tanh policy and bounded, identity-bound JSON checkpoints."""

import json
from dataclasses import asdict
from hashlib import sha256

from lapsim.driver_runtime import (
    CONE_ONLY_SCHEMA,
    HIDDEN,
    SIDE_OBSERVATION_SCHEMA,
    WEIGHT_COUNT,
    Policy,
)

from .contracts import (
    pin,
)
from .perception import SensorConfig

__all__ = ["HIDDEN", "WEIGHT_COUNT", "Policy", "canonical", "checkpoint", "restore"]


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def checkpoint(
    policy: Policy,
    *,
    course_sha256: str,
    vehicle_sha256: str,
    sensor: SensorConfig,
    generation: int,
    cones_sha256: str | None = None,
    cone_labeling_sha256: str | None = None,
) -> dict:
    pin(course_sha256)
    pin(vehicle_sha256)
    if (
        type(policy) is not Policy
        or type(sensor) is not SensorConfig
        or type(generation) is not int
        or generation < 0
    ):
        raise ValueError("invalid checkpoint context")
    if policy.observation_schema != sensor.observation_schema:
        raise ValueError("policy and checkpoint sensor observation schemas differ")
    side_context = sensor.observation_schema in (
        SIDE_OBSERVATION_SCHEMA,
        CONE_ONLY_SCHEMA,
    )
    if side_context or cones_sha256 is not None or cone_labeling_sha256 is not None:
        pin(cones_sha256)
        pin(cone_labeling_sha256)
        side_context = True
    data = {
        "schema": "lapsim.learned-driver-checkpoint.v2"
        if side_context
        else "lapsim.learned-driver-checkpoint.v1",
        "observation_schema": policy.observation_schema,
        "course_sha256": course_sha256,
        "vehicle_sha256": vehicle_sha256,
        "sensor": asdict(sensor),
        "generation": generation,
        "policy": {"weights": list(policy.weights), "sha256": policy.sha256},
        "evaluation_status": "UNEVALUATED_REQUIRES_FROZEN_HELDOUT_EVALUATION",
    }
    if side_context:
        data.update(
            cones_sha256=cones_sha256, cone_labeling_sha256=cone_labeling_sha256
        )
    return {**data, "checkpoint_sha256": sha256(canonical(data)).hexdigest()}


def restore(
    data: dict,
    *,
    course_sha256: str,
    vehicle_sha256: str,
    sensor: SensorConfig,
    cones_sha256: str | None = None,
    cone_labeling_sha256: str | None = None,
) -> Policy:
    if type(sensor) is not SensorConfig:
        raise TypeError("SensorConfig required")
    if type(data) is not dict or len(canonical(data)) > 65536:
        raise ValueError("bounded JSON checkpoint required")
    expected = {
        "schema",
        "observation_schema",
        "course_sha256",
        "vehicle_sha256",
        "sensor",
        "generation",
        "policy",
        "evaluation_status",
        "checkpoint_sha256",
    }
    side_context = data.get("schema") == "lapsim.learned-driver-checkpoint.v2"
    if side_context:
        expected.update(("cones_sha256", "cone_labeling_sha256"))
        pin(cones_sha256)
        pin(cone_labeling_sha256)
        if (
            data.get("cones_sha256") != cones_sha256
            or data.get("cone_labeling_sha256") != cone_labeling_sha256
        ):
            raise ValueError("checkpoint cone map/labeling context differs")
    elif (
        sensor.observation_schema in (SIDE_OBSERVATION_SCHEMA, CONE_ONLY_SCHEMA)
        or cones_sha256 is not None
        or cone_labeling_sha256 is not None
    ):
        raise ValueError("side-labeled policies require a map-bound v2 checkpoint")
    if set(data) != expected:
        raise ValueError("unsupported checkpoint fields")
    body = {k: v for k, v in data.items() if k != "checkpoint_sha256"}
    if data["checkpoint_sha256"] != sha256(canonical(body)).hexdigest():
        raise ValueError("checkpoint bytes differ")
    pin(course_sha256)
    pin(vehicle_sha256)
    if (
        data["schema"]
        not in (
            "lapsim.learned-driver-checkpoint.v1",
            "lapsim.learned-driver-checkpoint.v2",
        )
        or data["observation_schema"] != sensor.observation_schema
        or data["course_sha256"] != course_sha256
        or data["vehicle_sha256"] != vehicle_sha256
        or data["sensor"] != asdict(sensor)
        or set(data["policy"]) != {"weights", "sha256"}
    ):
        raise ValueError("checkpoint observation/course/vehicle context differs")
    if (
        type(data["generation"]) is not int
        or data["generation"] < 0
        or data["evaluation_status"] != "UNEVALUATED_REQUIRES_FROZEN_HELDOUT_EVALUATION"
    ):
        raise ValueError("checkpoint generation or evaluation status differs")
    policy = Policy(
        tuple(data["policy"]["weights"]), observation_schema=data["observation_schema"]
    )
    if policy.sha256 != data["policy"]["sha256"]:
        raise ValueError("policy identity differs")
    return policy
