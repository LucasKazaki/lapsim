"""Atomic composition of automatic DRS and the common tire-thermal plant.

One sampled policy decision, one powered/load/thermal step, one joint commit.
Component sources are unchanged. Synthetic calibration and instantaneous DRS
closing remain assumptions; this module adds no per-wheel thermal physics.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json

from .actuation import four_numbers
from .torque_light_drs import DrsSignals, DrsState, advance_drs, initialize_drs, policy_identity
from .torque_light_thermal import (
    ThermalLightPoweredState, advance_thermal_light, evaluate_thermal_light,
    initialize_thermal_light, thermal_model_identity,
)

FAMILY = "lapsim.torque-light-combined-drs-common-thermal.v1"


def _valid_hash(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def combined_model_identity(settings, thermal, policy, actuation, environment, *, automatic_drs_enabled,
                              wheel_radii_m=None):
    if type(automatic_drs_enabled) is not bool:
        raise ValueError("explicit boolean automatic DRS enable required")
    value = {"family": FAMILY,
        "thermal_plant_sha256": thermal_model_identity(settings, thermal, actuation, environment, wheel_radii_m),
        "policy_sha256": policy_identity(policy, settings.feedback_period_s),
        "automatic_drs_enabled": automatic_drs_enabled,
        "update_order": "observe_previous_actual_and_temperature;choose;advance;commit"}
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class CombinedLightState:
    thermal: ThermalLightPoweredState
    drs: DrsState
    model_sha256: str
    automatic_drs_enabled: bool
    last_signals: DrsSignals | None = None

    def __post_init__(self):
        if not isinstance(self.thermal, ThermalLightPoweredState) or not isinstance(self.drs, DrsState):
            raise TypeError("explicit thermal-powered and DRS states required")
        if type(self.automatic_drs_enabled) is not bool or not _valid_hash(self.model_sha256):
            raise ValueError("combined model identity and explicit DRS enable required")
        if self.thermal.light.aero_mode != self.drs.actual_mode or self.drs.ticks != self.thermal.thermal.ticks:
            raise ValueError("combined actual aero state and all component clocks must agree")
        if not self.automatic_drs_enabled and (self.drs.actual_mode != "closed" or self.drs.commanded_mode != "closed"):
            raise ValueError("disabled automatic DRS must remain commanded/actually closed")
        if self.last_signals is not None and not isinstance(self.last_signals, DrsSignals):
            raise TypeError("combined policy observation must be DrsSignals")
        if (self.last_signals is None) != (self.drs.ticks == 0):
            raise ValueError("initial state has no sample; every committed tick records its observation")


def initialize_combined_light(settings, thermal, policy, actuation, powered, environment, *,
                               initial_temperature_c, automatic_drs_enabled, wheel_radii_m=None,
                               load_longitudinal_mps2=0., load_lateral_mps2=0.):
    identity = combined_model_identity(settings, thermal, policy, actuation, environment,
        automatic_drs_enabled=automatic_drs_enabled, wheel_radii_m=wheel_radii_m)
    state = initialize_thermal_light(settings, thermal, actuation, powered, environment,
        initial_temperature_c=initial_temperature_c, aero_mode="closed", wheel_radii_m=wheel_radii_m,
        load_longitudinal_mps2=load_longitudinal_mps2, load_lateral_mps2=load_lateral_mps2)
    return CombinedLightState(state, initialize_drs(policy, settings.feedback_period_s), identity, automatic_drs_enabled)


def advance_combined_light(settings, thermal, policy, actuation, state, command_nm, steering, brakes,
                            available, environment, *, braking_requested, wheel_radii_m=None,
                            maximum_work=50_000, driver_proxy_n=0.):
    """One load-clock tick with held caller controls and no mid-step mutation.

    The policy sample uses PREVIOUS actual aero and temperature-adjusted grip.
    The prospective actual mode then feeds the current powered step/normal loads.
    That plant step still holds previous temperature; actual slip heat determines
    the next temperature and therefore the next grip tick. No policy or thermal
    commit occurs inside an RK callback/rejected trial, nor on a failed step.
    """
    if not isinstance(state, CombinedLightState):
        raise TypeError("CombinedLightState required")
    expected = combined_model_identity(settings, thermal, policy, actuation, environment,
        automatic_drs_enabled=state.automatic_drs_enabled, wheel_radii_m=wheel_radii_m)
    if state.model_sha256 != expected:
        raise ValueError("combined model changed; explicitly initialize/reset")
    if state.drs.policy_sha256 != policy_identity(policy, settings.feedback_period_s):
        raise ValueError("combined DRS state has a mismatched policy/clock binding")
    if type(braking_requested) is not bool:
        raise ValueError("explicit boolean braking request required")
    command = four_numbers(command_nm, "command")
    steer = four_numbers(steering, "steering")
    brake = four_numbers(brakes, "brakes")
    if any(value < 0 for value in brake):
        raise ValueError("friction brake magnitudes must be nonnegative")
    _, physical, electrical = evaluate_thermal_light(settings, thermal, actuation, state.thermal,
        command, steer, brake, available, environment, aero_mode=state.drs.actual_mode,
        wheel_radii_m=wheel_radii_m, driver_proxy_n=driver_proxy_n)
    point = state.thermal.light
    # Same definitions as the qualified DRS wrapper, now from thermal-adjusted
    # feasible forces. Equivalence regressions protect against observation drift.
    signals = DrsSignals(point.powered.plant.u_mps, max(abs(value) for value in steer),
        abs(point.powered.plant.yaw_rate_rad_s),
        max(abs(physical.cg_lateral_acceleration_mps2), abs(point.load_lateral_mps2)),
        max(abs(wheel.slip_ratio) for wheel in physical.wheels),
        braking_requested or any(value < 0 for value in (*command, *electrical.wheel_torques_nm)) or
        any(value > 0 for value in brake))
    if state.automatic_drs_enabled:
        drs = advance_drs(policy, state.drs, signals, settings.feedback_period_s)
    else:
        drs = replace(state.drs, commanded_mode="closed", actual_mode="closed", pending_open_ticks=0,
                      ticks=state.drs.ticks+1, reason="disabled")
    updated = advance_thermal_light(settings, thermal, actuation, state.thermal, command, steer,
        brake, available, environment, aero_mode=drs.actual_mode, wheel_radii_m=wheel_radii_m,
        maximum_work=maximum_work, driver_proxy_n=driver_proxy_n)
    return replace(state, thermal=updated, drs=drs, last_signals=signals)
