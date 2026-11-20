"""An episode loop and an explicit port into the existing RWD owner.

No numerical implementation is copied here. The private live candidate binds
these ports to its original 50/10/1 ms driver/allocator/plant clocks, preserve
guards, and check continuous footprint/cone collisions and ordered finish gates.
Only prior fixture ports have been exercised. The private live candidate remains unexecuted.
"""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Protocol

from .contracts import (
    DRIVER_FRAME_PERIOD_S,
    TIME_TOLERANCE_S,
    Action,
    DriverObservation,
    EpisodeResult,
    Trial,
    driver_frame_budget,
    finite,
    pin,
)
from .perception import Cone, Perception, SensorConfig, TruthFrame
from .reward import LapScorer, ScoreFrame, GateLapScorer


@dataclass(frozen=True, slots=True)
class EnvironmentStep:
    observation: DriverObservation
    scoring: ScoreFrame


class EpisodeBackend(Protocol):
    course_sha256: str
    vehicle_sha256: str
    backend_name: str
    length_m: float
    sensor_sha256: str
    scenario_sha256: str | None

    def reset(self, seed: int) -> DriverObservation: ...
    def advance(self, action: Action) -> EnvironmentStep: ...
    def close(self) -> None:
        """Disable this adapter locally; never release/clean up original ownership."""
        ...


class RolloutFailure(RuntimeError):
    def __init__(
        self,
        primary: Exception,
        *,
        trial: Trial,
        steps: int,
        elapsed_s: float,
        reward: float,
    ):
        super().__init__(f"{type(primary).__name__}: {primary}")
        self.partial = {
            "trial_id": trial.trial_id,
            "policy_sha256": trial.policy_sha256,
            "completed_steps": steps,
            "elapsed_s": elapsed_s,
            "reward": reward,
            "valid_lap": False,
            "primary_error": str(self),
        }


def rollout(trial: Trial, backend: EpisodeBackend, *, execution_stop=None) -> EpisodeResult:
    """Run only inside the already admitted owner, never from the plan CLI.

    Policy code is handed the narrow observation object only. Privileged score
    frames never enter act(). A baseline trial belongs to its existing driver.
    Every return/refusal/error closes the local adapter. This is not a receipt
    for original process/handle/lease cleanup, which remains the owner's job.
    """
    try:
        result = _rollout_episode(trial, backend, execution_stop=execution_stop)
    except BaseException as primary:
        try:
            backend.close()
        except RuntimeError as secondary:
            # An ordinary local-close refusal must not mask the primary.
            # Unexpected/fatal close errors propagate; original ownership
            # cleanup is never performed or authenticated by this latch.
            primary.add_note(
                f"local backend close also failed: {type(secondary).__name__}: {secondary}"
            )
        raise
    backend.close()
    return result


def _rollout_episode(trial: Trial, backend: EpisodeBackend, *, execution_stop=None) -> EpisodeResult:
    if trial.policy is None:
        raise ValueError("baseline trials must use the existing racing-line runner")
    if (backend.course_sha256, backend.vehicle_sha256) != (
        trial.course_sha256,
        trial.vehicle_sha256,
    ):
        raise ValueError("backend course/profile differs from the trial")
    if backend.sensor_sha256 != trial.sensor_sha256:
        raise ValueError("backend observation/sensor contract differs from the trial")
    if getattr(backend, "scenario_sha256", None) != trial.scenario_sha256:
        raise ValueError("backend complete scenario differs from the trial")
    if getattr(backend,'mission_kind','lap')=='segment':
        raise ValueError('segment task uses explicit RL/reference segment runner, never EpisodeResult.valid_lap')
    score_type = GateLapScorer if getattr(backend,"earned_gate_spacing_m",None)==5. else LapScorer
    scorer = score_type(length_m=backend.length_m, maximum_time_s=trial.maximum_time_s)
    time_frames = driver_frame_budget(trial.maximum_time_s)
    steps = 0
    execution_termination=None
    if execution_stop is not None and not callable(execution_stop):raise TypeError('fixed owner stop callback required')
    try:
        observation = backend.reset(trial.seed)
        actor = trial.policy.new_actor()
        for _ in range(min(trial.maximum_steps, time_frames)):
            if execution_stop is not None and steps:
                stop=execution_stop()
                if type(stop) is not bool:raise TypeError('owner stop decision must be bool')
                if stop:
                    execution_termination='execution_window_limit'
                    break
            action = actor.act(observation)
            frame = backend.advance(action)
            if (
                type(frame) is not EnvironmentStep
                or type(frame.observation) is not DriverObservation
            ):
                raise TypeError(
                    "backend must return the narrow observation and separate scoring frame"
                )
            scorer.step(frame.scoring)
            steps += 1
            observation = frame.observation
            if scorer.termination is not None:
                break
        return EpisodeResult(
            trial.trial_id,
            trial.policy_sha256,
            trial.course_sha256,
            trial.vehicle_sha256,
            scorer.total_reward,
            scorer.progress_m,
            scorer.elapsed_s,
            scorer.valid_lap,
            scorer.termination
            or execution_termination
            or ("time_limit" if steps >= time_frames else "step_limit"),
            steps,
            backend.backend_name,
            trial.sensor_sha256,
            trial.scenario_sha256,
        )
    except Exception as primary:
        raise RolloutFailure(
            primary,
            trial=trial,
            steps=steps,
            elapsed_s=scorer.elapsed_s,
            reward=scorer.total_reward,
        ) from primary


@dataclass(frozen=True, slots=True)
class DriverDemand:
    """Driver intent for the existing controller, not applied wheel torque."""

    steering_rad: float
    total_drive_request_nm: float
    wheel_friction_brake_request_nm: float


@dataclass(frozen=True, slots=True)
class RwdDriverLimits:
    maximum_steering_rad: float
    maximum_drive_request_nm: float
    maximum_wheel_brake_nm: float
    maximum_steering_rate_rad_s: float

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            finite(getattr(self, name), name)
            if getattr(self, name) <= 0.0:
                raise ValueError("positive explicitly selected driver limits required")
        if self.maximum_steering_rad >= 1.0:
            raise ValueError("unsupported driver steering limit")


# BEGIN ideal-egomotion value bridge v1
@dataclass(frozen=True, slots=True)
class EgoMotionEvidence:
    """Ideal body-frame velocities from an accepted plant state, in m/s.

    Both velocity components retain their sign. accepted_tick is the owner's
    accepted physical endpoint tick, for freshness auditing only; it is never
    a policy feature and need not equal an interpolated terminal scoring time.
    This metadata does not establish hardware sensor availability or accuracy.
    """

    body_forward_mps: float
    body_lateral_mps: float
    accepted_tick: int

    def __post_init__(self) -> None:
        for name in ("body_forward_mps", "body_lateral_mps"):
            value = getattr(self, name)
            try:
                finite(value, name)
            except OverflowError as exc:
                raise ValueError(name + " must be a finite number") from exc
            object.__setattr__(self, name, float(value))
        if type(self.accepted_tick) is not int or self.accepted_tick < 0:
            raise ValueError("accepted_tick must be a nonnegative integer")


def _copy_ego_motion_evidence(
    evidence: EgoMotionEvidence | None,
) -> EgoMotionEvidence | None:
    if evidence is None:
        return None
    if type(evidence) is not EgoMotionEvidence:
        raise TypeError("typed ideal egomotion evidence or None required")
    return EgoMotionEvidence(
        evidence.body_forward_mps, evidence.body_lateral_mps, evidence.accepted_tick
    )


# END ideal-egomotion value bridge v1
@dataclass(frozen=True, slots=True)
class OwnerFrame:
    """Environment-only truth, not a policy observation or authority receipt."""

    truth: TruthFrame
    scoring: ScoreFrame
    private_reward_evidence: dict | None = None
# BEGIN ideal-egomotion optional frame v1
    ego_motion_evidence: EgoMotionEvidence | None = None

    def __post_init__(self) -> None:
        if self.ego_motion_evidence is not None and type(self.ego_motion_evidence) is not EgoMotionEvidence:
            raise TypeError("typed ideal egomotion evidence or None required")
# END ideal-egomotion optional frame v1


class RwdPortBackend:
    """Thin adapter for a fresh, source-bound original RWD episode owner.

    start(seed) must apply declared seed-based sensor/start perturbations, use a
    fresh complete vehicle/controller state and return at t=0/station=0.
    step(demand) must run the unchanged control/physics and return exactly one
    50 ms driver frame later, or at a genuine earlier terminal crossing. It must propagate owner cancellation and refusals.
    Supplying callbacks alone does not prove ownership or numerical fidelity.
    """

    def __init__(
        self,
        *,
        course_sha256: str,
        vehicle_sha256: str,
        length_m: float,
        cones: tuple[Cone, ...],
        sensor: SensorConfig,
        limits: RwdDriverLimits,
        start: Callable[[int], OwnerFrame],
        step: Callable[[DriverDemand], OwnerFrame],
        require_owner_live: Callable[[], None],
        backend_name: str,
        scenario_sha256: str | None = None,
        earned_gate_spacing_m: float | None = None,
        mission_kind: str = 'lap',
    ):
        pin(course_sha256)
        pin(vehicle_sha256)
        if scenario_sha256 is not None:
            pin(scenario_sha256)
        self.scenario_sha256 = scenario_sha256
        if mission_kind not in ('lap','segment'):raise ValueError('explicit task kind required')
        self.mission_kind=mission_kind
        if earned_gate_spacing_m is not None and (type(earned_gate_spacing_m) not in (int,float) or earned_gate_spacing_m != 5.):
            raise ValueError("fixed Michigan gate-earned spacing required")
        self.earned_gate_spacing_m = earned_gate_spacing_m
        finite(length_m, "course length")
        if length_m <= 0.0 or not backend_name:
            raise ValueError(
                "explicit positive course length and backend name required"
            )
        if type(sensor) is not SensorConfig or type(limits) is not RwdDriverLimits:
            raise TypeError("explicit sensor and RWD driver limits required")
        self.course_sha256, self.vehicle_sha256 = course_sha256, vehicle_sha256
        self.length_m, self.backend_name = length_m, backend_name
        self._cones, self._sensor, self._limits = cones, sensor, limits
        self._start, self._step, self._require_owner_live = (
            start,
            step,
            require_owner_live,
        )
        self._private_reward_evidence = None
# BEGIN ideal-egomotion cache initialization v1
        self._ideal_ego_motion_evidence: EgoMotionEvidence | None = None
# END ideal-egomotion cache initialization v1
        self._perception: Perception | None = None
        self._cone_detections_evidence = None
        self._previous = Action(0.0, 0.0, 0.0)
        self._time_s = 0.0
        self._steering_rad = 0.0
        self._used = False
        self._failed = False
        self._terminal = False
        self._closed = False

    @property
    def private_reward_evidence(self):
        """Evaluator-only copied evidence; never part of DriverObservation."""
        return deepcopy(self._private_reward_evidence)

# BEGIN ideal-egomotion readonly property v1
    @property
    def ideal_ego_motion_evidence(self) -> EgoMotionEvidence | None:
        """Copied ideal endpoint metadata; missing evidence remains None.

        Consumers explicitly select/mask velocity channels in their observer.
        This property does not alter the existing DriverObservation contract.
        """
        return _copy_ego_motion_evidence(self._ideal_ego_motion_evidence)

# END ideal-egomotion readonly property v1
    @property
    def sensor_sha256(self) -> str:
        return self._sensor.sha256

    @property
    def closed(self) -> bool:
        """Local adapter state only; it says nothing about original owner cleanup."""
        return self._closed

    @property
    def cone_detections_evidence(self):
        """Copied SAME detector-pass metadata; no extra perception/RNG call."""
        return deepcopy(self._cone_detections_evidence)

    def close(self) -> None:
        """Idempotent local latch; no owner callback, process, file or lease action."""
        self._closed = True

    def reset(self, seed: int) -> DriverObservation:
        if self._used or self._closed:
            raise RuntimeError(
                "an episode backend is single-use; fresh owned state required"
            )
        self._used = True
        try:
            self._require_owner_live()
            frame = self._start(seed)
            if (
                type(frame) is not OwnerFrame
                or frame.scoring.elapsed_s != 0.0
                or frame.scoring.progress_m != 0.0
                or not frame.scoring.footprint_inside
                or frame.scoring.cone_collision
                or frame.scoring.finish_gate_crossed
                or frame.scoring.segment_complete
                or not frame.scoring.ordered_route_valid
            ):
                raise ValueError("valid fresh owner start frame required")
            self._private_reward_evidence = deepcopy(frame.private_reward_evidence)
# BEGIN ideal-egomotion accepted reset cache v1
            self._ideal_ego_motion_evidence = _copy_ego_motion_evidence(frame.ego_motion_evidence)
# END ideal-egomotion accepted reset cache v1
            self._perception = Perception(self._sensor, seed=seed)
            observation=self._perception.observe(self._cones, frame.truth, self._previous)
            self._cone_detections_evidence=deepcopy(self._perception.cone_detections_evidence)
            return observation
        except BaseException:
            self._failed = True
            self.close()
            raise

    def advance(self, action: Action) -> EnvironmentStep:
        if self._perception is None or self._failed or self._terminal or self._closed:
            raise RuntimeError("fresh nonfailed owned episode required")
        try:
            self._require_owner_live()  # never replaced by a local bool/JSON grant
            limits = self._limits
            requested = action.steering * limits.maximum_steering_rad
            delta = limits.maximum_steering_rate_rad_s * self._sensor.frame_period_s
            steering = max(
                self._steering_rad - delta, min(self._steering_rad + delta, requested)
            )
            demand = DriverDemand(
                steering,
                action.throttle * limits.maximum_drive_request_nm,
                action.brake * limits.maximum_wheel_brake_nm,
            )
            frame = self._step(demand)
            if (
                type(frame) is not OwnerFrame
                or not 0.0 < frame.scoring.elapsed_s - self._time_s <= DRIVER_FRAME_PERIOD_S + TIME_TOLERANCE_S
                or (abs(frame.scoring.elapsed_s - self._time_s - DRIVER_FRAME_PERIOD_S) > TIME_TOLERANCE_S
                    and not (frame.scoring.finish_gate_crossed or frame.scoring.segment_complete or frame.scoring.cone_collision
                             or not frame.scoring.footprint_inside or not frame.scoring.ordered_route_valid))
            ):
                raise ValueError("nonterminal50ms clock or genuine early terminal differs")
            self._private_reward_evidence = deepcopy(frame.private_reward_evidence)
# BEGIN ideal-egomotion accepted advance cache v1
            self._ideal_ego_motion_evidence = _copy_ego_motion_evidence(frame.ego_motion_evidence)
# END ideal-egomotion accepted advance cache v1
            self._time_s, self._steering_rad = frame.scoring.elapsed_s, steering
            observation = self._perception.observe(self._cones, frame.truth, action)
            self._cone_detections_evidence=deepcopy(self._perception.cone_detections_evidence)
            self._previous = action
            self._terminal = (
                not frame.scoring.footprint_inside
                or frame.scoring.cone_collision
                or frame.scoring.finish_gate_crossed
                or frame.scoring.segment_complete
                or not frame.scoring.ordered_route_valid
                or frame.scoring.stalled
            )
            if self._terminal:
                self.close()
            return EnvironmentStep(observation, frame.scoring)
        except BaseException:
            self._failed = True
            self.close()
            raise


def connect_live_runner(*args, **kwargs):
    """No substitute launcher, lease, native binder or admission provider."""
    raise RuntimeError(
        "Live learned-driver integration is unbound; original cleanup/admission and exact-source review required"
    )
