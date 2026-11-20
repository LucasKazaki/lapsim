"""Deterministic two-state automatic DRS over the powered light plant.

Synthetic experiment policy, not a calibrated vehicle controller or rules
approval. Opening has a declared tick-quantized delay; closing is idealized as
instantaneous. Policy samples once per held-input load tick, never in RK stages.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from math import ceil, isfinite

from .actuation import four_numbers
from .torque_light_powered import (
    LightPoweredState, advance_light_powered, evaluate_light_powered,
    initialize_light_powered, model_identity,
)

FAMILY = "lapsim.torque-light-automatic-drs.v1"
MAX_OPENING_DELAY_TICKS = 50_000


def _finite(*values):
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in values):
        raise ValueError("DRS inputs must be finite numbers")


def _hash(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _valid_hash(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


@dataclass(frozen=True, slots=True)
class AutomaticDrsPolicy:
    """Required experiment thresholds; SI units, slip ratio dimensionless.

    Open thresholds are more restrictive than hold thresholds. Opening can be
    commanded only on clear samples throughout the opening delay. Once actually
    open it can persist in the hysteresis band. A hold-limit crossing or braking
    request closes immediately. These
    thresholds are declared assumptions, never inferred from team-car data.
    """
    min_open_speed_mps: float
    min_hold_speed_mps: float
    max_open_abs_steer_rad: float
    max_hold_abs_steer_rad: float
    max_open_abs_yaw_rad_s: float
    max_hold_abs_yaw_rad_s: float
    max_open_abs_lateral_mps2: float
    max_hold_abs_lateral_mps2: float
    max_open_abs_slip: float
    max_hold_abs_slip: float
    opening_delay_s: float
    provenance: str

    def __post_init__(self):
        pairs = ((self.min_hold_speed_mps, self.min_open_speed_mps),
                 (self.max_open_abs_steer_rad, self.max_hold_abs_steer_rad),
                 (self.max_open_abs_yaw_rad_s, self.max_hold_abs_yaw_rad_s),
                 (self.max_open_abs_lateral_mps2, self.max_hold_abs_lateral_mps2),
                 (self.max_open_abs_slip, self.max_hold_abs_slip))
        _finite(self.opening_delay_s, *(value for pair in pairs for value in pair))
        if self.opening_delay_s < 0 or any(not 0 <= lower < upper for lower, upper in pairs):
            raise ValueError("nonnegative opening delay and distinct ordered hysteresis thresholds required")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("DRS threshold provenance/uncertainty must be declared")


@dataclass(frozen=True, slots=True)
class DrsSignals:
    forward_speed_mps: float
    abs_steer_rad: float
    abs_yaw_rad_s: float
    abs_lateral_mps2: float
    max_abs_slip: float
    braking_requested: bool

    def __post_init__(self):
        _finite(self.forward_speed_mps, self.abs_steer_rad, self.abs_yaw_rad_s,
                self.abs_lateral_mps2, self.max_abs_slip)
        if min(self.abs_steer_rad, self.abs_yaw_rad_s, self.abs_lateral_mps2, self.max_abs_slip) < 0:
            raise ValueError("absolute DRS signal magnitudes cannot be negative")
        if type(self.braking_requested) is not bool:
            raise ValueError("explicit boolean braking request required")


@dataclass(frozen=True, slots=True)
class DrsState:
    policy_sha256: str
    commanded_mode: str = "closed"
    actual_mode: str = "closed"
    pending_open_ticks: int = 0
    ticks: int = 0
    reason: str = "initialized_closed"

    def __post_init__(self):
        if not _valid_hash(self.policy_sha256):
            raise ValueError("DRS state requires a policy/clock SHA256 binding")
        if self.commanded_mode not in ("closed", "open") or self.actual_mode not in ("closed", "open"):
            raise ValueError("two-state closed/open DRS required")
        if any(type(value) is not int or value < 0 for value in (self.pending_open_ticks, self.ticks)):
            raise ValueError("DRS counters must be nonnegative integers")
        if self.pending_open_ticks > min(MAX_OPENING_DELAY_TICKS, self.ticks):
            raise ValueError("DRS pending timer exceeds bounded domain")
        if ((self.commanded_mode == "closed" and (self.actual_mode != "closed" or self.pending_open_ticks)) or
                (self.actual_mode == "open" and self.pending_open_ticks)):
            raise ValueError("DRS actual/command/timer state is inconsistent")
        if not isinstance(self.reason, str) or not self.reason:
            raise ValueError("DRS transition reason required")


def _delay_ticks(policy, period_s):
    if not isinstance(policy, AutomaticDrsPolicy):
        raise TypeError("explicit AutomaticDrsPolicy required")
    _finite(period_s)
    if not 0 < period_s <= .01:
        raise ValueError("DRS period must match light load clock in (0, .01] s")
    count = policy.opening_delay_s / period_s
    if not isfinite(count) or count > MAX_OPENING_DELAY_TICKS:
        raise ValueError("DRS opening delay exceeds bounded tick domain")
    return ceil(count)


def policy_identity(policy, period_s):
    _delay_ticks(policy, period_s)
    return _hash({"family": FAMILY, "policy": asdict(policy), "period_s": period_s,
                  "closing": "instantaneous_idealization", "opening": "completed_clear_ticks_ceil"})


def initialize_drs(policy, period_s):
    return DrsState(policy_identity(policy, period_s))


def advance_drs(policy, state, signals, period_s):
    """Prospective one-tick state; commit only if the corresponding plant succeeds.

    At tick start choose the mode held through that tick. A two-tick delay holds
    closed for the first two successful clear plant ticks and opens on the third.
    Zero delay opens on the first clear tick. Braking/hold-limit veto cancels the
    pending timer. No hidden wall-clock, prior run or rejected-trial state exists.
    """
    if not isinstance(state, DrsState) or not isinstance(signals, DrsSignals):
        raise TypeError("explicit DRS state and signals required")
    if state.policy_sha256 != policy_identity(policy, period_s):
        raise ValueError("DRS policy/clock changed; explicitly initialize/reset")
    veto = next((reason for condition, reason in (
        (signals.braking_requested, "braking"),
        (signals.forward_speed_mps <= policy.min_hold_speed_mps, "low_speed"),
        (signals.abs_steer_rad >= policy.max_hold_abs_steer_rad, "steering"),
        (signals.abs_yaw_rad_s >= policy.max_hold_abs_yaw_rad_s, "yaw"),
        (signals.abs_lateral_mps2 >= policy.max_hold_abs_lateral_mps2, "lateral"),
        (signals.max_abs_slip >= policy.max_hold_abs_slip, "slip")) if condition), None)
    if veto is not None:
        return replace(state, commanded_mode="closed", actual_mode="closed", pending_open_ticks=0,
                       ticks=state.ticks+1, reason=veto)
    clear = (signals.forward_speed_mps >= policy.min_open_speed_mps and
             signals.abs_steer_rad <= policy.max_open_abs_steer_rad and
             signals.abs_yaw_rad_s <= policy.max_open_abs_yaw_rad_s and
             signals.abs_lateral_mps2 <= policy.max_open_abs_lateral_mps2 and
             signals.max_abs_slip <= policy.max_open_abs_slip)
    if state.actual_mode != "open" and not clear:
        return replace(state, commanded_mode="closed", actual_mode="closed", pending_open_ticks=0,
                       ticks=state.ticks+1, reason="awaiting_clear")
    if state.actual_mode == "open" or state.pending_open_ticks >= _delay_ticks(policy, period_s):
        return replace(state, commanded_mode="open", actual_mode="open", pending_open_ticks=0,
                       ticks=state.ticks+1, reason="open")
    return replace(state, commanded_mode="open", actual_mode="closed",
                   pending_open_ticks=state.pending_open_ticks+1, ticks=state.ticks+1, reason="opening_delay")


@dataclass(frozen=True, slots=True)
class AutomaticDrsPoweredState:
    light: LightPoweredState
    drs: DrsState
    model_sha256: str
    last_signals: DrsSignals | None = None

    def __post_init__(self):
        if not isinstance(self.light, LightPoweredState) or not isinstance(self.drs, DrsState):
            raise TypeError("explicit light powered and DRS states required")
        if not _valid_hash(self.model_sha256) or self.light.aero_mode != self.drs.actual_mode:
            raise ValueError("automatic DRS model/state binding is inconsistent")
        if self.last_signals is not None and not isinstance(self.last_signals, DrsSignals):
            raise TypeError("recorded policy signals must be DrsSignals or initial None")
        if self.light.feedback_ticks != self.drs.ticks:
            raise ValueError("DRS must advance exactly once per light load tick")


def automatic_model_identity(settings, policy, actuation, environment, wheel_radii_m=None):
    return _hash({"family": FAMILY, "plant_sha256": model_identity(settings, actuation, environment, wheel_radii_m),
                  "policy_sha256": policy_identity(policy, settings.feedback_period_s)})


def initialize_automatic_drs(settings, policy, actuation, powered, environment, *, wheel_radii_m=None,
                             load_longitudinal_mps2=0., load_lateral_mps2=0.):
    identity = automatic_model_identity(settings, policy, actuation, environment, wheel_radii_m)
    light = initialize_light_powered(settings, actuation, powered, environment, aero_mode="closed",
        wheel_radii_m=wheel_radii_m, load_longitudinal_mps2=load_longitudinal_mps2,
        load_lateral_mps2=load_lateral_mps2)
    return AutomaticDrsPoweredState(light, initialize_drs(policy, settings.feedback_period_s), identity)


def advance_automatic_drs(settings, policy, actuation, state, command_nm, steering, brakes, available,
                          environment, *, braking_requested, wheel_radii_m=None, maximum_work=50_000,
                          driver_proxy_n=0.):
    """Observe previous actual mode, choose next mode, evolve, then commit both.

    Driver braking intent is required even if pack constraints suppress regen.
    Negative requested/feasible wheel torque or supplied friction brake also
    vetoes opening. Tire slips/CG lateral acceleration come from the feasible
    tick-start sample; contact-load lateral memory supplies an additional veto.
    Inputs remain held, and no controller/regen allocator is invented here.
    """
    if not isinstance(state, AutomaticDrsPoweredState):
        raise TypeError("AutomaticDrsPoweredState required")
    if state.model_sha256 != automatic_model_identity(settings, policy, actuation, environment, wheel_radii_m):
        raise ValueError("automatic DRS model changed; explicitly initialize/reset")
    if type(braking_requested) is not bool:
        raise ValueError("explicit boolean braking request required")
    command = four_numbers(command_nm, "command")
    steer = four_numbers(steering, "steering")
    brake = four_numbers(brakes, "brakes")
    if any(value < 0 for value in brake):
        raise ValueError("friction brake magnitudes must be nonnegative")
    _, physical, electrical = evaluate_light_powered(settings, actuation, state.light, command,
        steer, brake, available, environment, aero_mode=state.drs.actual_mode, wheel_radii_m=wheel_radii_m,
        driver_proxy_n=driver_proxy_n)
    signals = DrsSignals(state.light.powered.plant.u_mps, max(abs(value) for value in steer),
        abs(state.light.powered.plant.yaw_rate_rad_s),
        max(abs(physical.cg_lateral_acceleration_mps2), abs(state.light.load_lateral_mps2)),
        max(abs(wheel.slip_ratio) for wheel in physical.wheels),
        braking_requested or any(value < 0 for value in (*command, *electrical.wheel_torques_nm)) or
        any(value > 0 for value in brake))
    drs = advance_drs(policy, state.drs, signals, settings.feedback_period_s)
    light = advance_light_powered(settings, actuation, state.light, command, steer, brake,
        available, environment, aero_mode=drs.actual_mode, wheel_radii_m=wheel_radii_m,
        maximum_work=maximum_work, driver_proxy_n=driver_proxy_n)
    return replace(state, light=light, drs=drs, last_signals=signals)
