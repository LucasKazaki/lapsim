"""Canonical stdlib-only inference runtime; exact mirror shipped in Light.

No trainer, numerical plant, GUI, executor, lease or admission provider belongs
here. Catalog pins identify configured data; they do not authenticate a run.
"""

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from math import isfinite, tanh

FEATURE_COUNT = 8
LEGACY_OBSERVATION_SCHEMA = "lapsim.driver-perception.v1"
FRONT_OBSERVATION_SCHEMA = "lapsim.driver-front-cones.v2"
SIDE_OBSERVATION_SCHEMA = "lapsim.driver-side-cones.v3"
CONE_ONLY_SCHEMA = "lapsim.driver-cone-distances-metres.v5"
CONE_STATE_SCHEMA = "lapsim.driver-cones-vehicle-state.v1"
STATE_FEATURE_NAMES=("speed_over30mps","yaw_rate_over2radps","applied_steer_over0p4rad","rear_left_slip_proxy","rear_right_slip_proxy")
OBSERVATION_SCHEMA = CONE_ONLY_SCHEMA
OBSERVATION_SCHEMAS = frozenset(
    (
        LEGACY_OBSERVATION_SCHEMA,
        FRONT_OBSERVATION_SCHEMA,
        SIDE_OBSERVATION_SCHEMA,
        CONE_ONLY_SCHEMA,
        CONE_STATE_SCHEMA,
    )
)
HIDDEN = 8
WEIGHT_COUNT = (FEATURE_COUNT + 1) * HIDDEN + (HIDDEN + 1) * 2


def feature_count(schema):
    if schema not in OBSERVATION_SCHEMAS:
        raise ValueError("unsupported observation schema")
    return 13 if schema == CONE_STATE_SCHEMA else (FEATURE_COUNT if schema == CONE_ONLY_SCHEMA else 29)


def weight_count(schema):
    if schema == CONE_STATE_SCHEMA:return 194  # existing154 +8x5state-input weights
    return (feature_count(schema) + 1) * HIDDEN + (HIDDEN + 1) * 2


def digest(value) -> str:
    raw = (
        value
        if type(value) is bytes
        else json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    )
    return sha256(raw).hexdigest()


def _finite(value, name):
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError(name + " must be finite")


def _pin(value):
    if (
        type(value) is not str
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError("expected a lowercase SHA256 identity")


def _json_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON object key")
        value[key] = item
    return value


def _decode(raw):
    if type(raw) is not bytes or len(raw) > 65536:
        raise ValueError("bounded JSON bytes required")
    try:
        return json.loads(raw, object_pairs_hook=_json_object)
    except (UnicodeDecodeError, RecursionError) as error:
        raise ValueError("invalid bounded JSON document") from error


class DriverUnavailable(ValueError):
    pass


class CapabilityError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class Action:
    steering: float
    throttle: float
    brake: float

    def __post_init__(self):
        for name in ("steering", "throttle", "brake"):
            _finite(getattr(self, name), name)
        if (
            not -1.0 <= self.steering <= 1.0
            or not 0.0 <= self.throttle <= 1.0
            or not 0.0 <= self.brake <= 1.0
        ):
            raise ValueError("normalized action outside bounds")
        if self.throttle > 0.0 and self.brake > 0.0:
            raise ValueError("simultaneous throttle and brake are not supported")


@dataclass(frozen=True, slots=True)
class DriverObservation:
    """Current v5 is eight range-censored cone distances in metres only."""

    features: tuple[float, ...]
    observation_schema: str = OBSERVATION_SCHEMA

    def __post_init__(self):
        if self.observation_schema not in OBSERVATION_SCHEMAS:
            raise ValueError("unsupported driver observation schema")
        if type(self.features) is not tuple or len(self.features) != feature_count(
            self.observation_schema
        ):
            raise ValueError(
                "immutable driver features must match the observation schema"
            )
        for i,value in enumerate(self.features):
            _finite(value, "driver feature")
            if self.observation_schema == CONE_ONLY_SCHEMA or (self.observation_schema == CONE_STATE_SCHEMA and i<8):
                if not 0.0 <= value <= 30.0:
                    raise ValueError("cone distance outside the declared30m censoring range")
            elif not -1.0 <= value <= 1.0:
                raise ValueError("normalized legacy driver feature outside [-1, 1]")


@dataclass(frozen=True, slots=True)
class Policy:
    weights: tuple[float, ...]
    observation_schema: str = OBSERVATION_SCHEMA

    def __post_init__(self):
        if self.observation_schema not in OBSERVATION_SCHEMAS:
            raise ValueError("unsupported policy observation schema")
        if type(self.weights) is not tuple or (len(self.weights) != weight_count(self.observation_schema)
            and not (self.observation_schema == CONE_ONLY_SCHEMA and len(self.weights) == 154)
            and not (self.observation_schema == CONE_STATE_SCHEMA and len(self.weights) == 195)):
            raise ValueError(
                "immutable network weights must match the observation schema"
            )
        for value in self.weights:
            _finite(value, "policy weight")
            if abs(value) > 10.0:
                raise ValueError("policy weight outside search bounds")

    @classmethod
    def zero(cls, *, observation_schema=OBSERVATION_SCHEMA):
        return cls(
            (0.0,) * weight_count(observation_schema),
            observation_schema=observation_schema,
        )

    @property
    def sha256(self):
        value={"schema": self.observation_schema, "weights": self.weights}
        if len(self.weights)==154:value["model"]={"kind":"cone-only-tanh-RNN-v1","inputs":8,"memory":8,"outputs":2,"period_s":.05}
        if self.observation_schema==CONE_STATE_SCHEMA:value["model"]={"kind":"cones-state-tanh-RNN-v1","inputs":13,"memory":8,"outputs":2,"period_s":.05,"layout":"legacy154+state8x5","state_features":STATE_FEATURE_NAMES}
        if self.observation_schema==CONE_STATE_SCHEMA and len(self.weights)==195:
            value["model"]={"kind":"cones-state-tanh-RNN-speed-pedal-v2","inputs":13,"memory":8,"outputs":2,"period_s":.05,"layout":"legacy154+state8x5+direct_speed_pedal_weight","state_features":STATE_FEATURE_NAMES}
        return digest(value)

    def new_actor(self):
        """Fresh per-episode neural memory; legacy policies remain stateless."""
        if self.observation_schema==CONE_STATE_SCHEMA:return _StateRNNActor(self)
        return _ConeRNNActor(self) if len(self.weights)==154 else self

    def act(self, observation: DriverObservation) -> Action:
        if len(self.weights)==154 or self.observation_schema==CONE_STATE_SCHEMA:raise ValueError("recurrent policy requires a fresh per-episode actor")
        if type(observation) is not DriverObservation:
            raise TypeError("policy accepts only DriverObservation estimates")
        if observation.observation_schema != self.observation_schema:
            raise ValueError("policy observation schema differs from supplied features")
        # Policy-internal scaling adds no observation channel or private state.
        values = (tuple(v / 30.0 for v in observation.features)
                  if self.observation_schema == CONE_ONLY_SCHEMA else observation.features)
        inputs = values + (1.0,)
        width = len(inputs)
        output_start = width * HIDDEN
        hidden = tuple(
            tanh(
                sum(
                    v * w
                    for v, w in zip(
                        inputs, self.weights[i * width : (i + 1) * width], strict=True
                    )
                )
            )
            for i in range(HIDDEN)
        ) + (1.0,)
        outputs = tuple(
            tanh(
                sum(
                    v * w
                    for v, w in zip(
                        hidden,
                        self.weights[output_start + i * 9 : output_start + (i + 1) * 9],
                        strict=True,
                    )
                )
            )
            for i in range(2)
        )
        steer, pedal = outputs
        return Action(steer, max(0.0, pedal), max(0.0, -pedal))

    def infer_cones(self, features):
        """Owner port: plain eight-distance metre tuple in, normalized action tuple out.

        Frontends have distinct Python class origins. No frontend observation
        or action class has to be imported into the common episode owner.
        """
        if self.observation_schema != CONE_ONLY_SCHEMA:
            raise ValueError("live inference port requires distance-only v5 schema")
        action = self.act(
            DriverObservation(features, observation_schema=CONE_ONLY_SCHEMA)
        )
        return action.steering, action.throttle, action.brake


class _ConeRNNActor:
    """Only current eight ranges and bounded prior neural state enter this cell."""
    __slots__=('_policy','_state')
    def __init__(self,policy):
        if type(policy) is not Policy or policy.observation_schema!=CONE_ONLY_SCHEMA or len(policy.weights)!=154:
            raise TypeError('exact recurrent cone-only Policy required')
        self._policy=policy;self._state=(0.,)*8
    def act(self,observation):
        if type(observation) is not DriverObservation or observation.observation_schema!=CONE_ONLY_SCHEMA:
            raise TypeError('exact eight-distance DriverObservation required')
        if type(self._state) is not tuple or len(self._state)!=8 or any(type(x) is not float or not isfinite(x) or abs(x)>1 for x in self._state):
            raise ValueError('bounded private recurrent state changed')
        w=self._policy.weights;inputs=tuple(x/30. for x in observation.features)+(1.,)
        hidden=[]
        for i in range(8):
            z=sum(x*y for x,y in zip(inputs,w[i*9:i*9+9],strict=True))
            recurrent=w[72+i*8:80+i*8]
            if any(recurrent):z+=sum(x*y for x,y in zip(self._state,recurrent,strict=True))
            hidden.append(tanh(z))
        next_state=tuple(hidden);head=next_state+(1.,)
        outputs=tuple(tanh(sum(x*y for x,y in zip(head,w[136+i*9:145+i*9],strict=True))) for i in range(2))
        action=Action(outputs[0],max(0.,outputs[1]),max(0.,-outputs[1]))
        self._state=next_state
        return action
    def infer_cones(self,features):
        a=self.act(DriverObservation(features,observation_schema=CONE_ONLY_SCHEMA))
        return a.steering,a.throttle,a.brake


@dataclass(frozen=True, slots=True)
class ScenarioIdentity:
    """Exact declared compatibility, never original-owner/admission authority."""

    model_family: str
    topology_id: str
    course_id: str
    profile_id: str
    engine_sha256: str
    course_sha256: str
    vehicle_sha256: str
    sensor_sha256: str
    cones_sha256: str
    driver_limits_sha256: str
    gates_sha256: str
    scoring_sha256: str
    baseline_source_sha256: str
    baseline_config_sha256: str
    perturbations_sha256: str
    observation_schema: str = OBSERVATION_SCHEMA
    cone_labeling_sha256: str | None = None

    def __post_init__(self):
        if self.observation_schema not in OBSERVATION_SCHEMAS:
            raise ValueError("unsupported scenario observation schema")
        if any(
            type(v) is not str or not v or len(v) > 128
            for v in (
                self.model_family,
                self.topology_id,
                self.course_id,
                self.profile_id,
            )
        ):
            raise ValueError(
                "explicit model family, topology, course and profile required"
            )
        if self.observation_schema in (SIDE_OBSERVATION_SCHEMA, CONE_ONLY_SCHEMA):
            _pin(self.cone_labeling_sha256)
        for name in self.__dataclass_fields__:
            if name.endswith("_sha256"):
                if name == "cone_labeling_sha256" and self.cone_labeling_sha256 is None:
                    continue
                _pin(getattr(self, name))

    @property
    def sha256(self):
        body = asdict(self)
        if self.cone_labeling_sha256 is None:
            body.pop("cone_labeling_sha256")
        return digest(body)


@dataclass(frozen=True, slots=True)
class RegisteredDriver:
    driver_id: str
    label: str
    artifact_sha256: str
    scenario_sha256: str
    evaluation_receipt_sha256: str

    def __post_init__(self):
        if (
            type(self.driver_id) is not str
            or not 1 <= len(self.driver_id) <= 64
            or self.driver_id in ("baseline", "pretrained")
            or any(
                c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in self.driver_id
            )
        ):
            raise ValueError("explicit registered driver ID required")
        if type(self.label) is not str or not 1 <= len(self.label) <= 128:
            raise ValueError("bounded driver label required")
        for pin in (
            self.artifact_sha256,
            self.scenario_sha256,
            self.evaluation_receipt_sha256,
        ):
            _pin(pin)


@dataclass(frozen=True, slots=True)
class DriverCatalog:
    """Explicit configured registrations; empty by default, no directory scan."""

    entries: tuple[RegisteredDriver, ...] = ()

    @classmethod
    def from_bytes(cls, raw):
        data = _decode(raw)
        if (
            type(data) is not dict
            or set(data) != {"schema", "drivers"}
            or data["schema"] != "lapsim.driver-catalog.v1"
        ):
            raise ValueError("explicit driver catalog schema required")
        if type(data["drivers"]) is not list or len(data["drivers"]) > 64:
            raise ValueError("bounded driver registrations required")
        return cls(tuple(RegisteredDriver(**row) for row in data["drivers"]))

    @property
    def sha256(self):
        return digest(
            {
                "schema": "lapsim.driver-catalog.v1",
                "drivers": [asdict(e) for e in self.entries],
            }
        )

    def __post_init__(self):
        if (
            type(self.entries) is not tuple
            or len(self.entries) > 64
            or any(type(e) is not RegisteredDriver for e in self.entries)
        ):
            raise ValueError("bounded immutable driver registry required")
        if len({e.driver_id for e in self.entries}) != len(self.entries) or len(
            {e.label for e in self.entries}
        ) != len(self.entries):
            raise ValueError("duplicate driver ID/label")
        if any(
            e.label in ("Existing baseline", "Pre-trained driver") for e in self.entries
        ):
            raise ValueError("driver labels must be distinct from built-in choices")

    def entry(self, driver_id):
        for entry in self.entries:
            if entry.driver_id == driver_id:
                return entry
        raise DriverUnavailable(
            "No registered pre-trained driver matches this artifact."
        )


@dataclass(frozen=True, slots=True)
class DriverBinding:
    """Frozen dispatch inputs, not admission credentials or cleanup evidence."""

    driver_id: str
    policy_sha256: str
    artifact_sha256: str
    catalog_sha256: str
    evaluation_receipt_sha256: str
    scenario_sha256: str

    def __post_init__(self):
        if type(self.driver_id) is not str or not self.driver_id:
            raise ValueError("driver ID required")
        for name in self.__dataclass_fields__:
            if name.endswith("_sha256"):
                _pin(getattr(self, name))


@dataclass(frozen=True, slots=True)
class DriverRunResult:
    """Portable retained episode summary; not admission or lap qualification."""

    driver_binding: DriverBinding
    trial_id: str
    termination: str
    elapsed_s: float
    steps: int
    valid_lap: bool
    retained_result_sha256: str

    def __post_init__(self):
        if type(self.driver_binding) is not DriverBinding:
            raise TypeError("frozen DriverBinding required in retained result")
        if type(self.trial_id) is not str or not 1 <= len(self.trial_id) <= 256:
            raise ValueError("bounded owner trial identity required")
        if self.termination not in (
            "lap_complete",
            "off_course",
            "cone_collision",
            "time_limit",
            "step_limit",
            "stopped",
            "failed",
        ):
            raise ValueError("explicit terminal episode status required")
        _finite(self.elapsed_s, "elapsed time")
        if (
            not 0 <= self.elapsed_s <= 300.0 + 1e-9
            or type(self.steps) is not int
            or not 0 <= self.steps <= 10000
        ):
            raise ValueError("bounded episode result accounting required")
        if type(self.valid_lap) is not bool or self.valid_lap != (
            self.termination == "lap_complete"
        ):
            raise ValueError("valid lap and result termination disagree")
        if self.termination not in ("failed", "stopped") and (
            self.elapsed_s <= 0 or self.steps < 1
        ):
            raise ValueError("finished episode needs positive time and steps")
        _pin(self.retained_result_sha256)

    def to_bytes(self):
        return json.dumps(
            {"schema": "lapsim.driver-run-result.v1", **asdict(self)},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()

    @property
    def summary(self):
        return f"Course driver: {self.termination.replace('_', ' ')} ({self.elapsed_s:.3f} s)."

    @classmethod
    def from_bytes(cls, raw):
        data = _decode(raw)
        if (
            type(data) is not dict
            or set(data) != {"schema", *cls.__dataclass_fields__}
            or data["schema"] != "lapsim.driver-run-result.v1"
        ):
            raise ValueError("explicit retained driver result schema required")
        values = {
            k: v for k, v in data.items() if k not in ("schema", "driver_binding")
        }
        return cls(driver_binding=DriverBinding(**data["driver_binding"]), **values)


@dataclass(frozen=True, slots=True)
class FrozenCandidate:
    """An unqualified weight snapshot, never a RegisteredDriver."""

    candidate_id: str
    policy: Policy
    scenario_sha256: str
    provenance_sha256: str

    def __post_init__(self):
        if (
            type(self.candidate_id) is not str
            or not 1 <= len(self.candidate_id) <= 64
            or any(
                c not in "abcdefghijklmnopqrstuvwxyz0123456789-"
                for c in self.candidate_id
            )
            or self.candidate_id in ("baseline", "pretrained")
        ):
            raise ValueError("explicit bounded candidate ID required")
        if (
            type(self.policy) is not Policy
            or self.policy.observation_schema != CONE_ONLY_SCHEMA
        ):
            raise ValueError("frozen cone-only v4 candidate required")
        _pin(self.scenario_sha256)
        _pin(self.provenance_sha256)


@dataclass(frozen=True, slots=True)
class FrozenScreeningRequest:
    """Bounded owner request; identity declarations confer no run authority."""

    request_id: str
    scenario: ScenarioIdentity
    candidates: tuple[FrozenCandidate, ...]
    seeds: tuple[int, ...]
    maximum_steps: int
    maximum_time_s: float
    max_parallel: int = 1

    def __post_init__(self):
        if (
            type(self.request_id) is not str
            or not 1 <= len(self.request_id) <= 64
            or any(
                c not in "abcdefghijklmnopqrstuvwxyz0123456789-"
                for c in self.request_id
            )
        ):
            raise ValueError("bounded original-owner request ID required")
        if (
            type(self.scenario) is not ScenarioIdentity
            or self.scenario.observation_schema != CONE_ONLY_SCHEMA
        ):
            raise ValueError("complete cone-only scenario required")
        if (
            type(self.candidates) is not tuple
            or not 1 <= len(self.candidates) <= 4
            or any(type(c) is not FrozenCandidate for c in self.candidates)
        ):
            raise ValueError("one to four immutable frozen candidates required")
        if len({c.candidate_id for c in self.candidates}) != len(self.candidates):
            raise ValueError("duplicate candidate IDs")
        if any(c.scenario_sha256 != self.scenario.sha256 for c in self.candidates):
            raise ValueError("candidate scenario differs from request")
        if (
            type(self.seeds) is not tuple
            or not 1 <= len(self.seeds) <= 2
            or any(
                type(s) is not int or not 0 <= s <= 2_147_483_647 for s in self.seeds
            )
            or len(set(self.seeds)) != len(self.seeds)
        ):
            raise ValueError("one or two distinct bounded seeds required")
        _finite(self.maximum_time_s, "screening time cap")
        if (
            type(self.maximum_steps) is not int
            or not 1 <= self.maximum_steps <= 6000
            or not 0.05 <= self.maximum_time_s <= 300.0
            or type(self.max_parallel) is not int
            or not 1
            <= self.max_parallel
            <= min(2, len(self.candidates) * len(self.seeds))
        ):
            raise ValueError("bounded screening frames/time/parallelism required")

    def to_bytes(self):
        raw = json.dumps(
            {"schema": "lapsim.frozen-screening-request.v1", **asdict(self)},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        if len(raw) > 65536:
            raise ValueError("screening request exceeds transport cap")
        return raw

    @property
    def sha256(self):
        return digest(self.to_bytes())

    @property
    def trial_specs(self):
        return tuple(
            (f"{self.request_id}-c{i}-r{run}", candidate, seed)
            for i, candidate in enumerate(self.candidates)
            for run, seed in enumerate(self.seeds)
        )

    @classmethod
    def from_bytes(cls, raw):
        data = _decode(raw)
        if (
            type(data) is not dict
            or set(data) != {"schema", *cls.__dataclass_fields__}
            or data["schema"] != "lapsim.frozen-screening-request.v1"
        ):
            raise ValueError("explicit frozen screening request schema required")
        if (
            type(data["candidates"]) is not list
            or not 1 <= len(data["candidates"]) <= 4
            or type(data["seeds"]) is not list
        ):
            raise ValueError("bounded screening collections required")
        candidates = []
        for row in data["candidates"]:
            if (
                type(row) is not dict
                or set(row) != set(FrozenCandidate.__dataclass_fields__)
                or type(row["policy"]) is not dict
                or set(row["policy"]) != {"weights", "observation_schema"}
                or type(row["policy"]["weights"]) is not list
            ):
                raise ValueError("explicit frozen policy snapshot required")
            candidates.append(
                FrozenCandidate(
                    row["candidate_id"],
                    Policy(
                        tuple(row["policy"]["weights"]),
                        row["policy"]["observation_schema"],
                    ),
                    row["scenario_sha256"],
                    row["provenance_sha256"],
                )
            )
        return cls(
            data["request_id"],
            ScenarioIdentity(**data["scenario"]),
            tuple(candidates),
            tuple(data["seeds"]),
            data["maximum_steps"],
            data["maximum_time_s"],
            data["max_parallel"],
        )


@dataclass(frozen=True, slots=True)
class FrozenScreeningResult:
    """Owner-reported outcome; even lap_complete is unqualified evidence."""

    trial_id: str
    candidate_id: str
    policy_sha256: str
    scenario_sha256: str
    seed: int
    termination: str
    elapsed_s: float
    steps: int
    reported_valid_lap: bool
    retained_result_sha256: str

    def __post_init__(self):
        for value in (
            self.policy_sha256,
            self.scenario_sha256,
            self.retained_result_sha256,
        ):
            _pin(value)
        if (
            type(self.trial_id) is not str
            or not 1 <= len(self.trial_id) <= 256
            or type(self.candidate_id) is not str
            or not 1 <= len(self.candidate_id) <= 64
        ):
            raise ValueError("explicit screening trial/candidate IDs required")
        if type(self.seed) is not int or not 0 <= self.seed <= 2_147_483_647:
            raise ValueError("explicit screening seed required")
        if (
            self.termination
            not in (
                "lap_complete",
                "off_course",
                "cone_collision",
                "time_limit",
                "step_limit",
                "stopped",
                "failed",
            )
            or type(self.reported_valid_lap) is not bool
            or self.reported_valid_lap != (self.termination == "lap_complete")
        ):
            raise ValueError("reported screening status/validity disagree")
        _finite(self.elapsed_s, "screening elapsed time")
        if (
            not 0 <= self.elapsed_s <= 300.0 + 1e-9
            or type(self.steps) is not int
            or not 0 <= self.steps <= 6000
        ):
            raise ValueError("bounded screening accounting required")
        if self.termination not in ("failed", "stopped") and (
            self.elapsed_s <= 0 or self.steps < 1
        ):
            raise ValueError("finished screening requires positive accounting")


@dataclass(frozen=True, slots=True)
class FrozenScreeningReport:
    request_sha256: str
    results: tuple[FrozenScreeningResult, ...]

    @property
    def qualification_status(self):
        return "UNQUALIFIED_REQUIRES_FULL_HELDOUT_AND_INDEPENDENT_OWNER_REPLAY"

    @property
    def owner_validation_verified(self):
        return False

    @property
    def replacement_eligible(self):
        return False

    @classmethod
    def from_bytes(cls, raw, request):
        data = _decode(raw)
        if (
            type(data) is not dict
            or set(data) != {"schema", "request_sha256", "results"}
            or data["schema"] != "lapsim.frozen-screening-results.v1"
            or data["request_sha256"] != request.sha256
        ):
            raise ValueError("screening response request identity differs")
        if type(data["results"]) is not list or len(data["results"]) != len(
            request.trial_specs
        ):
            raise ValueError(
                "one explicit screening result per requested trial required"
            )
        rows = tuple(FrozenScreeningResult(**row) for row in data["results"])
        indexed = {row.trial_id: row for row in rows}
        if len(indexed) != len(rows) or set(indexed) != {
            t[0] for t in request.trial_specs
        }:
            raise ValueError("duplicate, unknown or missing screening trial IDs")
        ordered = []
        for trial_id, candidate, seed in request.trial_specs:
            row = indexed[trial_id]
            if (
                (row.candidate_id, row.policy_sha256, row.scenario_sha256, row.seed)
                != (
                    candidate.candidate_id,
                    candidate.policy.sha256,
                    request.scenario.sha256,
                    seed,
                )
                or row.steps > request.maximum_steps
                or row.elapsed_s > request.maximum_time_s + 1e-9
            ):
                raise ValueError("screening result identity or episode budget differs")
            ordered.append(row)
        return cls(request.sha256, tuple(ordered))


class InferenceOnlyService:
    """Light backend: no preference, command or callback can enable training.

    Full provides a different subclass in its own unshipped-in-Light module.
    This is an application capability boundary, not a Python security sandbox.
    """

    def __init__(self, catalog: DriverCatalog | None = None):
        self.catalog = DriverCatalog() if catalog is None else catalog
        if type(self.catalog) is not DriverCatalog:
            raise TypeError("explicit DriverCatalog required")
        self._selected = "baseline"
        self._scenario = None
        self._policy = None

    @property
    def edition(self):
        return "light"

    @property
    def can_train(self):
        return False

    @property
    def selected_driver(self):
        return self._selected

    @property
    def pretrained_available(self):
        return bool(self.catalog.entries)

    @property
    def status(self):
        if self._selected == "baseline":
            return "Existing baseline selected." + (
                " No trained drivers are bundled."
                if not self.pretrained_available
                else ""
            )
        if not self.pretrained_available:
            return "No pre-trained driver is available. Select the existing baseline to continue."
        if self._scenario is None:
            return "Select and bind a compatible course, car and scenario first."
        if self._policy is None:
            return "Open the matching registered driver artifact."
        return "Compatible registered driver loaded. Original runtime admission is still required."

    def describe(self):
        return {
            "schema": "lapsim.driver-options.v1",
            "edition": self.edition,
            "can_train": self.can_train,
            "selected_driver": self._selected,
            "trained_policy_available": self._policy is not None,
            "registered_driver_count": len(self.catalog.entries),
            "inference_ready": self._policy is not None,
            "drivers": [
                {"id": e.driver_id, "label": e.label} for e in self.catalog.entries
            ],
            "status": self.status,
            "runtime_admission": False,
            "winner_claimed": False,
        }

    def select(self, driver_id):
        if driver_id not in ("baseline", "pretrained"):
            self.catalog.entry(driver_id)
        if driver_id != self._selected:
            self._policy = None
        self._selected = driver_id

    def apply_preferences(self, values):
        if type(values) is not dict or set(values) != {"selected_driver"}:
            raise ValueError(
                "driver preferences cannot change edition, training or model capabilities"
            )
        self.select(values["selected_driver"])

    def bind_scenario(self, scenario):
        if scenario is not None and type(scenario) is not ScenarioIdentity:
            raise TypeError("complete ScenarioIdentity required")
        if scenario is not None and scenario.observation_schema != CONE_ONLY_SCHEMA:
            raise ValueError(
                "current driver products require the literal cone-only v4 observation contract"
            )
        self._scenario, self._policy = scenario, None

    def load_catalog(self, raw):
        self._policy = None
        catalog = DriverCatalog.from_bytes(raw)
        self.catalog = catalog
        if self._selected != "baseline" and self._selected not in {
            e.driver_id for e in catalog.entries
        }:
            self._selected = "pretrained"

    def load_artifact(self, raw):
        self._policy = None  # any failed/replaced load invalidates stale inference
        data = _decode(raw)
        if (
            type(data) is not dict
            or set(data)
            != {
                "schema",
                "driver_id",
                "scenario",
                "policy",
                "evaluation_receipt_sha256",
            }
            or data["schema"] != "lapsim.pretrained-driver.v1"
        ):
            raise ValueError(
                "A registered evaluated-driver artifact is required; training checkpoints remain unevaluated."
            )
        entry = self.catalog.entry(data["driver_id"])
        if (
            digest(raw) != entry.artifact_sha256
            or data["evaluation_receipt_sha256"] != entry.evaluation_receipt_sha256
        ):
            raise DriverUnavailable(
                "Artifact or evaluation receipt differs from its registration."
            )
        scenario = ScenarioIdentity(**data["scenario"])
        if (
            self._scenario is None
            or scenario != self._scenario
            or scenario.sha256 != entry.scenario_sha256
        ):
            raise DriverUnavailable(
                "Driver model/course/sensor/cones/limits/gates/scoring/baseline scenario is incompatible."
            )
        if type(data["policy"]) is not dict or set(data["policy"]) != {
            "weights",
            "sha256",
        }:
            raise ValueError("explicit policy weights and identity required")
        policy = Policy(
            tuple(data["policy"]["weights"]),
            observation_schema=scenario.observation_schema,
        )
        if policy.sha256 != data["policy"]["sha256"]:
            raise DriverUnavailable("Policy weights differ from artifact identity.")
        self._selected = entry.driver_id
        self._policy = policy

    def _selected_driver_snapshot(self):
        if (
            self._selected in ("baseline", "pretrained")
            or self._policy is None
            or self._scenario is None
        ):
            raise DriverUnavailable(
                "Load and select a compatible registered driver before tuning."
            )
        scenario, policy = self._scenario, self._policy
        entry = self.catalog.entry(self._selected)
        return (
            scenario,
            policy,
            DriverBinding(
                entry.driver_id,
                policy.sha256,
                entry.artifact_sha256,
                self.catalog.sha256,
                entry.evaluation_receipt_sha256,
                scenario.sha256,
            ),
        )

    def _selection_matches_snapshot(self, scenario, policy, binding):
        return (
            self._scenario is scenario
            and self._policy is policy
            and self._selected == binding.driver_id
            and self.catalog.sha256 == binding.catalog_sha256
        )

    def infer(self, observation):
        if self._selected in ("baseline", "pretrained") or self._policy is None:
            raise DriverUnavailable(self.status)
        return self._policy.act(observation)

    def run_selected(self, owner=None):
        if self._selected == "baseline":
            return False  # caller retains its existing baseline workflow
        if self._policy is None or self._scenario is None:
            raise DriverUnavailable(self.status)
        if owner is None:
            raise RuntimeError(
                "Original supervised driver owner is not bound; no simulation started."
            )
        scenario, policy = self._scenario, self._policy
        entry = self.catalog.entry(self._selected)
        binding = DriverBinding(
            entry.driver_id,
            policy.sha256,
            entry.artifact_sha256,
            self.catalog.sha256,
            entry.evaluation_receipt_sha256,
            scenario.sha256,
        )
        owner.require_current_admission(scenario, driver_binding=binding)
        if (
            self._scenario is not scenario
            or self._policy is not policy
            or self._selected != entry.driver_id
            or self.catalog.sha256 != binding.catalog_sha256
        ):
            raise DriverUnavailable(
                "Driver selection changed during owner admission; no dispatch occurred."
            )
        result = owner.run_pretrained(
            driver_id=entry.driver_id,
            infer=policy.infer_cones,
            inference_contract="lapsim.driver-cone-distance-metres-vector.v2",
            scenario=scenario,
            driver_binding=binding,
        )
        if type(result) is bytes:
            result = DriverRunResult.from_bytes(result)
        if type(result) is not DriverRunResult or result.driver_binding != binding:
            raise DriverUnavailable(
                "Owner returned an unavailable or mismatched retained driver result binding."
            )
        if not self._selection_matches_snapshot(scenario, policy, binding):
            raise DriverUnavailable(
                "Driver binding changed during execution; retained result cannot be shown as current."
            )
        return result

    def screen_frozen_candidates(self, request, *, owner=None):
        """No weight updates/catalog promotion; original owner is sole executor.

        evaluation_batch's explicit bytes overload uses the SAME episode engine
        as Full's Trial tuple overload. No owned runtime/adapter is supplied here.
        The owner must authenticate source, physical validation and admission;
        client-side hashes and returned flags never establish that authority.
        """
        if getattr(self, "_screening_active", False):
            raise RuntimeError("a frozen screening request is already active")
        if type(request) is bytes:
            request = FrozenScreeningRequest.from_bytes(request)
        if type(request) is not FrozenScreeningRequest:
            raise TypeError("FrozenScreeningRequest required")
        if self._scenario is None or self._scenario != request.scenario:
            raise DriverUnavailable(
                "bind the complete current screening scenario first"
            )
        if owner is None:
            raise RuntimeError(
                "Original supervised screening owner is not bound; no run started."
            )
        scenario = self._scenario
        self._screening_active = True
        try:
            raw = request.to_bytes()
            owner.require_current_admission(
                scenario,
                frozen_screening_request=raw,
                screening_request_sha256=request.sha256,
            )
            if self._scenario is not scenario:
                raise DriverUnavailable("screening scenario changed during admission")
            response = owner.evaluation_batch(raw, max_parallel=request.max_parallel)
            report = FrozenScreeningReport.from_bytes(response, request)
            if self._scenario is not scenario:
                raise DriverUnavailable("screening scenario changed during execution")
            return report
        finally:
            self._screening_active = False

    def training_plan(self, *args, **kwargs):
        raise CapabilityError(
            "Driver training/tuning is available only in the full simulator."
        )

    def execute_training(self, *args, **kwargs):
        raise CapabilityError(
            "Light cannot enter a driver-training backend; use the full simulator."
        )

    def execute_tuning(self, *args, **kwargs):
        raise CapabilityError(
            "Light cannot enter driver tuning; use the full simulator."
        )

    def evaluate_driver(self, *args, **kwargs):
        raise CapabilityError(
            "Held-out driver qualification belongs to the full simulator."
        )

    def execute(self, command, **kwargs):
        if command == "evaluate":
            return self.evaluate_driver(**kwargs)
        if command == "tune":
            return self.execute_tuning(**kwargs)
        if command in ("train", "genetic"):
            return self.execute_training(**kwargs)
        raise ValueError("unsupported driver command")


def extend_with_vehicle_state(policy):
    """Zero new channels preserve exact old recurrent math; no new fitness claim."""
    if type(policy) is not Policy or policy.observation_schema!=CONE_ONLY_SCHEMA or len(policy.weights)!=154:
        raise TypeError('exact154-weight cone RNN required')
    return Policy(policy.weights+(0.,)*40,observation_schema=CONE_STATE_SCHEMA)

class _StateRNNActor:
    """Eight cones +5explicit local sensor features; no clock/position input."""
    __slots__=('_policy','_state')
    def __init__(self,policy):
        if type(policy) is not Policy or policy.observation_schema!=CONE_STATE_SCHEMA or len(policy.weights) not in (194,195):
            raise TypeError('exact194/195-weight cone/state RNN required')
        self._policy=policy;self._state=(0.,)*8
    def act(self,observation):
        if type(observation) is not DriverObservation or observation.observation_schema!=CONE_STATE_SCHEMA:
            raise TypeError('exact13-feature cone/state observation required')
        if type(self._state) is not tuple or len(self._state)!=8 or any(type(x) is not float or not isfinite(x) or abs(x)>1 for x in self._state):
            raise ValueError('bounded private recurrent state changed')
        w=self._policy.weights;inputs=tuple(x/30. for x in observation.features[:8])+(1.,);feedback=observation.features[8:]
        hidden=[]
        for i in range(8):
            z=sum(x*y for x,y in zip(inputs,w[i*9:i*9+9],strict=True))
            recurrent=w[72+i*8:80+i*8]
            if any(recurrent):z+=sum(x*y for x,y in zip(self._state,recurrent,strict=True))
            extra=w[154+i*5:159+i*5]
            if any(extra):z+=sum(x*y for x,y in zip(feedback,extra,strict=True))
            hidden.append(tanh(z))
        next_state=tuple(hidden);head=next_state+(1.,)
        outputs=[]
        for i in range(2):
            z=sum(x*y for x,y in zip(head,w[136+i*9:145+i*9],strict=True))
            # Direct observed-speed connection changes only pedal preactivation.
            # Skip exact zero to preserve the old binary64 operation sequence.
            if i==1 and len(w)==195 and w[194]:z+=w[194]*feedback[0]
            outputs.append(tanh(z))
        self._state=next_state
        return Action(outputs[0],max(0.,outputs[1]),max(0.,-outputs[1]))


def with_speed_pedal_skip(policy, *, bias_shift=0., speed_skip=None):
    """Explicit neutral conversion or engineered seed; not backprop/pretraining.

    Existing154cone and194state models retain every old weight. A zero new
    connection preserves their exact actions on the same observed history.
    Old checkpoints/fitness stay separate; this returns numeric policy data.
    """
    if type(policy) is not Policy:raise TypeError('exact Policy required')
    _finite(bias_shift,'pedal bias shift')
    if policy.observation_schema==CONE_ONLY_SCHEMA and len(policy.weights)==154:
        weights=list(policy.weights)+( [0.]*41 )
    elif policy.observation_schema==CONE_STATE_SCHEMA and len(policy.weights) in (194,195):
        weights=list(policy.weights)+( [0.] if len(policy.weights)==194 else [] )
    else:raise ValueError('only exact recurrent cone/state models migrate')
    weights[153]+=bias_shift
    if speed_skip is not None:
        _finite(speed_skip,'direct speed pedal weight');weights[194]=speed_skip
    return Policy(tuple(weights),observation_schema=CONE_STATE_SCHEMA)
