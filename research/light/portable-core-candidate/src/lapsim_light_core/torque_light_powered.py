"""Powered light-mode slice with causal sampled acceleration/load feedback.

Each tick samples feasible tire contact force at the start, holds the load-feedback state
during the existing powered RK evolution, then commits one exact-ZOH first-order
feedback update. Aero still follows stage speed. The relaxation time is an
explicit uncalibrated model input, not measured suspension/roll dynamics.
Controller, driver, torque allocation and regen policy are held caller inputs;
none are advanced by a force callback or rejected RK trial.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from math import expm1, isfinite

from .actuation import ActuationConfig, four_numbers
from .conditions import PlanarEnvironment
from .powered_planar import PoweredState, _substep_plan, advance_powered, evaluate_powered
from .torque_light_forces import AeroMode, LightForceConfig, evaluate_light_forces

FAMILY = "lapsim.torque-light-powered-contact-feedback.v1"


def _finite(*values):
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in values):
        raise ValueError("light powered values must be finite numbers")


def _mode(mode):
    if mode not in ("closed", "open"):
        raise ValueError("explicit closed/open aero state required; automatic DRS is not implemented")


@dataclass(frozen=True, slots=True)
class LightPoweredConfig:
    forces: LightForceConfig
    load_feedback_time_constant_s: float
    provenance: str
    feedback_period_s: float = .001

    def __post_init__(self):
        if not isinstance(self.forces, LightForceConfig):
            raise TypeError("explicit light force configuration required")
        _finite(self.load_feedback_time_constant_s, self.feedback_period_s)
        if self.load_feedback_time_constant_s <= 0 or not 0 < self.feedback_period_s <= .01:
            raise ValueError("positive feedback relaxation and period in (0, .01] s required")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("feedback provenance/uncertainty must be declared")


@dataclass(frozen=True, slots=True)
class LightPoweredState:
    """Load memory is equivalent contact force/mass, not total CG acceleration.

    Aero body forces act at CG and produce no pitch/roll moment in this model;
    declared front/rear downforce enters loads directly. Tire forces act at the
    road and drive the filtered overturning-moment load-transfer approximation.
    """
    powered: PoweredState
    model_sha256: str
    aero_mode: AeroMode
    load_longitudinal_mps2: float = 0.
    load_lateral_mps2: float = 0.
    feedback_ticks: int = 0

    def __post_init__(self):
        if not isinstance(self.powered, PoweredState):
            raise TypeError("light state must wrap PoweredState")
        _finite(self.load_longitudinal_mps2, self.load_lateral_mps2)
        if type(self.feedback_ticks) is not int or self.feedback_ticks < 0:
            raise ValueError("feedback ticks must be a nonnegative integer")
        if not isinstance(self.model_sha256, str) or len(self.model_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.model_sha256):
            raise ValueError("source-independent model/settings binding must be a SHA256 identity")
        _mode(self.aero_mode)


def model_identity(settings, actuation, environment, wheel_radii_m=None):
    """Plant/settings identity, including hardware and feedback clock.

    Both aero states are bound; current selected state is a recorded control
    input. A complete future run must also bind source, driver/controller,
    DRS policy/sequence, initial state and logging/sensor clocks.
    """
    if not isinstance(settings, LightPoweredConfig) or not isinstance(actuation, ActuationConfig):
        raise TypeError("light configuration and explicit actuator configuration required")
    if not isinstance(environment, PlanarEnvironment) or environment.drag_area_m2 != 0:
        raise ValueError("base environment must have zero drag area; light forces own CdA")
    if wheel_radii_m is not None:
        wheel_radii_m = four_numbers(wheel_radii_m, "wheel radii")
        if any(radius <= 0 for radius in wheel_radii_m): raise ValueError("wheel radii must be positive")
    value = {"family": FAMILY, "settings": asdict(settings), "actuation": asdict(actuation),
             "environment": asdict(environment), "wheel_radii_m": wheel_radii_m}
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def initialize_light_powered(settings, actuation, powered, environment, *, aero_mode,
                             load_longitudinal_mps2=0., load_lateral_mps2=0., wheel_radii_m=None):
    """Explicit reset/init; zero initial feedback is a declared transient state."""
    identity = model_identity(settings, actuation, environment, wheel_radii_m)
    if not isinstance(powered, PoweredState): raise TypeError("PoweredState required")
    if not 0 <= powered.pack_energy_j <= actuation.pack_capacity_j:
        raise ValueError("initial pack energy outside declared pack bounds")
    if any(w < 0 for w in powered.plant.wheel_speeds_rad_s):
        raise ValueError("negative wheel speed is outside the powered domain")
    return LightPoweredState(powered, identity, aero_mode, load_longitudinal_mps2, load_lateral_mps2)


def _provider(settings, state, aero_mode):
    _mode(aero_mode)

    def force(plant, point, controls, environment):
        if plant != settings.forces.plant:
            raise ValueError("force callback received mismatched vehicle geometry")
        return evaluate_light_forces(settings.forces, point, controls, aero_mode=aero_mode,
            longitudinal_acceleration_mps2=state.load_longitudinal_mps2,
            lateral_acceleration_mps2=state.load_lateral_mps2, environment=environment).physical
    return force


def evaluate_light_powered(settings, actuation, state, command_nm, steering, brakes, available,
                           environment, *, aero_mode, wheel_radii_m=None, driver_proxy_n=0.):
    """Feasible tick-start evaluation at the same first RK horizon as the plant."""
    if not isinstance(state, LightPoweredState): raise TypeError("LightPoweredState required")
    if state.model_sha256 != model_identity(settings, actuation, environment, wheel_radii_m):
        raise ValueError("model changed; explicitly initialize/reset light feedback state")
    _, horizon = _substep_plan(settings.forces.plant, actuation, settings.feedback_period_s, wheel_radii_m)
    return evaluate_powered(settings.forces.plant, actuation, state.powered,
        four_numbers(command_nm, "command"), four_numbers(steering, "steering"), four_numbers(brakes, "brakes"),
        available, horizon, environment, driver_proxy_n, wheel_radii_m=wheel_radii_m,
        force_evaluator=_provider(settings, state, aero_mode))


def advance_light_powered(settings, actuation, state, command_nm, steering, brakes, available,
                          environment, *, aero_mode, wheel_radii_m=None, maximum_work=50_000, driver_proxy_n=0.):
    """One load-clock tick; one feedback commit after successful plant evolution.

    Loads use current feedback memory; its target is feasible sum of tire body
    forces / mass at tick start. CG-applied aero must not invent pitch/roll
    transfer; ground contact reacting against crosswind must still contribute.
    The filter stores no mechanical/suspension energy. It changes normal-load
    distribution; all in-plane force/work and electrical accounting remain in
    the existing powered core. No mutation survives a rejected integration.
    """
    _, initial_physical, _ = evaluate_light_powered(settings, actuation, state, command_nm,
        steering, brakes, available, environment, aero_mode=aero_mode,
        wheel_radii_m=wheel_radii_m, driver_proxy_n=driver_proxy_n)
    powered = advance_powered(settings.forces.plant, actuation, state.powered,
        command_nm, steering, brakes, available, settings.feedback_period_s, environment,
        maximum_work=maximum_work, wheel_radii_m=wheel_radii_m, driver_proxy_n=driver_proxy_n,
        force_evaluator=_provider(settings, state, aero_mode))
    weight = -expm1(-settings.feedback_period_s / settings.load_feedback_time_constant_s)
    contact_ax = sum(w.body_force_x_n for w in initial_physical.wheels) / settings.forces.plant.mass_kg
    contact_ay = sum(w.body_force_y_n for w in initial_physical.wheels) / settings.forces.plant.mass_kg
    longitudinal = (1-weight) * state.load_longitudinal_mps2 + weight * contact_ax
    lateral = (1-weight) * state.load_lateral_mps2 + weight * contact_ay
    _finite(weight, longitudinal, lateral)
    return replace(state, powered=powered, aero_mode=aero_mode,
                   load_longitudinal_mps2=longitudinal, load_lateral_mps2=lateral,
                   feedback_ticks=state.feedback_ticks+1)
