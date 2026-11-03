"""Provisional one-lump tire heat/grip sensitivity, source-only candidate.

One temperature represents the four-tire set, not measured tread/carcass nodes
or per-wheel thermal state. Slip heat is partitioned from existing mechanical
loss, never added again to battery use. Grip can only reduce reference mu.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from math import expm1, isfinite

from .actuation import four_numbers
from .powered_planar import _substep_plan, advance_powered, evaluate_powered
from .torque_light_forces import evaluate_light_forces
from .torque_light_powered import (
    LightPoweredState, initialize_light_powered, model_identity,
)

FAMILY = "lapsim.torque-light-common-tire-thermal.v1"


def _finite(*values):
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) for value in values):
        raise ValueError("thermal values must be finite numbers")


def _hash(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _valid_hash(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


@dataclass(frozen=True, slots=True)
class LumpedTireThermalConfig:
    """Required synthetic inputs; C is for the entire four-tire lump.

    C [J/K], H [W/K], temperatures [degC], slip heat fraction dimensionless.
    Constant H includes an assumed combined ambient/road heat exchange. No
    pressure, wear, brake heat, rolling loss, speed dependence or radiation.
    Grip is a bounded piecewise-linear sensitivity, not a fitted tire map.
    """
    heat_capacity_j_per_k: float
    cooling_w_per_k: float
    slip_heat_fraction: float
    ambient_temperature_c: float
    minimum_temperature_c: float
    maximum_temperature_c: float
    cold_temperature_c: float
    peak_temperature_c: float
    hot_temperature_c: float
    cold_grip_fraction: float
    hot_grip_fraction: float
    grip_sensitivity_enabled: bool
    provenance: str

    def __post_init__(self):
        _finite(self.heat_capacity_j_per_k, self.cooling_w_per_k, self.slip_heat_fraction,
                self.ambient_temperature_c, self.minimum_temperature_c, self.maximum_temperature_c,
                self.cold_temperature_c, self.peak_temperature_c, self.hot_temperature_c,
                self.cold_grip_fraction, self.hot_grip_fraction)
        if self.heat_capacity_j_per_k <= 0 or self.cooling_w_per_k < 0 or not 0 <= self.slip_heat_fraction <= 1:
            raise ValueError("positive heat capacity, nonnegative cooling and heat fraction in [0,1] required")
        if not (-273.15 < self.minimum_temperature_c <= self.cold_temperature_c < self.peak_temperature_c <
                self.hot_temperature_c <= self.maximum_temperature_c):
            raise ValueError("ordered finite supported/cold/peak/hot temperature domain required")
        if not self.minimum_temperature_c <= self.ambient_temperature_c <= self.maximum_temperature_c:
            raise ValueError("ambient must be in the declared supported temperature domain")
        if not (0 < self.cold_grip_fraction <= 1 and 0 < self.hot_grip_fraction <= 1):
            raise ValueError("thermal grip fractions must be in (0,1]; no boost above reference mu")
        if type(self.grip_sensitivity_enabled) is not bool:
            raise ValueError("explicit boolean grip-sensitivity choice required")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("thermal provenance and uncertainty must be declared")


def thermal_config_identity(config):
    if not isinstance(config, LumpedTireThermalConfig):
        raise TypeError("explicit LumpedTireThermalConfig required")
    return _hash({"family": FAMILY, "thermal": asdict(config), "contact_heat": "integrated_slip_loss",
                  "cooling": "constant_power_exact_ZOH", "temperature_nodes": "one_common_four_tire_lump"})


@dataclass(frozen=True, slots=True)
class LumpedTireThermalState:
    config_sha256: str
    temperature_c: float
    absorbed_slip_heat_j: float = 0.
    heat_to_ambient_j: float = 0.
    ticks: int = 0

    def __post_init__(self):
        _finite(self.temperature_c, self.absorbed_slip_heat_j, self.heat_to_ambient_j)
        if not _valid_hash(self.config_sha256) or self.absorbed_slip_heat_j < 0:
            raise ValueError("thermal configuration binding and nonnegative absorbed heat required")
        if type(self.ticks) is not int or self.ticks < 0:
            raise ValueError("thermal ticks must be a nonnegative integer")


def _temperature(config, value):
    _finite(value)
    if not config.minimum_temperature_c <= value <= config.maximum_temperature_c:
        raise ValueError("temperature outside declared supported domain; no silent thermal clipping")


def initialize_tire_thermal(config, *, initial_temperature_c):
    identity = thermal_config_identity(config)
    _temperature(config, initial_temperature_c)
    return LumpedTireThermalState(identity, initial_temperature_c)


def tire_grip_fraction(config, temperature_c):
    thermal_config_identity(config)
    _temperature(config, temperature_c)
    if not config.grip_sensitivity_enabled:
        return 1.
    if temperature_c <= config.cold_temperature_c:
        return config.cold_grip_fraction
    if temperature_c >= config.hot_temperature_c:
        return config.hot_grip_fraction
    if temperature_c <= config.peak_temperature_c:
        fraction = (temperature_c-config.cold_temperature_c)/(config.peak_temperature_c-config.cold_temperature_c)
        return config.cold_grip_fraction+(1-config.cold_grip_fraction)*fraction
    fraction = (temperature_c-config.peak_temperature_c)/(config.hot_temperature_c-config.peak_temperature_c)
    return 1+(config.hot_grip_fraction-1)*fraction


def advance_tire_thermal(config, state, *, contact_slip_energy_j, timestep_s):
    """Partition nonnegative integrated slip loss and solve one exact ZOH step.

    C*dT/dt = Qabsorbed/dt - H*(T-Tambient). Slip power is its interval average;
    cooling exchange is signed positive OUT of the tire, negative when ambient
    warms it. This subledger partitions an existing loss, not a new power sink.
    """
    if not isinstance(state, LumpedTireThermalState):
        raise TypeError("LumpedTireThermalState required")
    if state.config_sha256 != thermal_config_identity(config):
        raise ValueError("thermal configuration changed; explicitly initialize/reset")
    _temperature(config, state.temperature_c)
    _finite(contact_slip_energy_j, timestep_s)
    if contact_slip_energy_j < 0 or not 0 < timestep_s <= 1:
        raise ValueError("nonnegative integrated slip loss and timestep in (0,1] s required")
    absorbed = config.slip_heat_fraction*contact_slip_energy_j
    rise_without_cooling = absorbed/config.heat_capacity_j_per_k
    if config.cooling_w_per_k == 0:
        temperature = state.temperature_c+rise_without_cooling
        cooling_exchange = 0.
    else:
        z = (config.cooling_w_per_k/config.heat_capacity_j_per_k)*timestep_s
        _finite(z)
        if z <= 0:
            raise ValueError("positive cooling rate underflows supported temporal resolution")
        weight = -expm1(-z)
        # a/z avoids overflow in Q/(H*dt) and is well-conditioned near zero.
        temperature = (state.temperature_c + weight*(config.ambient_temperature_c-state.temperature_c) +
                       rise_without_cooling*(weight/z))
        cooling_exchange = absorbed-config.heat_capacity_j_per_k*(temperature-state.temperature_c)
    _finite(absorbed, rise_without_cooling, temperature, cooling_exchange)
    _temperature(config, temperature)
    return replace(state, temperature_c=temperature,
        absorbed_slip_heat_j=state.absorbed_slip_heat_j+absorbed,
        heat_to_ambient_j=state.heat_to_ambient_j+cooling_exchange, ticks=state.ticks+1)


@dataclass(frozen=True, slots=True)
class ThermalLightPoweredState:
    light: LightPoweredState
    thermal: LumpedTireThermalState
    model_sha256: str
    applied_grip_fraction: float
    last_contact_slip_energy_j: float = 0.

    def __post_init__(self):
        if not isinstance(self.light, LightPoweredState) or not isinstance(self.thermal, LumpedTireThermalState):
            raise TypeError("explicit light and common thermal states required")
        _finite(self.applied_grip_fraction, self.last_contact_slip_energy_j)
        if not _valid_hash(self.model_sha256) or not 0 < self.applied_grip_fraction <= 1 or self.last_contact_slip_energy_j < 0:
            raise ValueError("valid thermal model binding, grip and nonnegative slip energy required")
        if self.light.feedback_ticks != self.thermal.ticks:
            raise ValueError("thermal state must commit once per successful light tick")


def thermal_model_identity(settings, thermal, actuation, environment, wheel_radii_m=None):
    return _hash({"family": FAMILY, "plant_sha256": model_identity(settings, actuation, environment, wheel_radii_m),
                  "thermal_sha256": thermal_config_identity(thermal)})


def initialize_thermal_light(settings, thermal, actuation, powered, environment, *, initial_temperature_c,
                             aero_mode, wheel_radii_m=None, load_longitudinal_mps2=0., load_lateral_mps2=0.):
    identity = thermal_model_identity(settings, thermal, actuation, environment, wheel_radii_m)
    light = initialize_light_powered(settings, actuation, powered, environment, aero_mode=aero_mode,
        wheel_radii_m=wheel_radii_m, load_longitudinal_mps2=load_longitudinal_mps2, load_lateral_mps2=load_lateral_mps2)
    temperature = initialize_tire_thermal(thermal, initial_temperature_c=initial_temperature_c)
    return ThermalLightPoweredState(light, temperature, identity, tire_grip_fraction(thermal, initial_temperature_c))


def _provider(settings, state, grip_fraction, aero_mode):
    # Only mu changes. Geometry, inertia, stiffness, road provenance and normal
    # load ownership remain explicit and unchanged. Do not disguise tire heat
    # as a road patch or reset the vehicle profile on every dynamic tick.
    effective = replace(settings.forces, plant=replace(settings.forces.plant,
                        tire_mu=settings.forces.plant.tire_mu*grip_fraction))
    def force(plant, point, controls, environment):
        if plant != settings.forces.plant:
            raise ValueError("thermal force callback received mismatched plant")
        return evaluate_light_forces(effective, point, controls, aero_mode=aero_mode,
            longitudinal_acceleration_mps2=state.light.load_longitudinal_mps2,
            lateral_acceleration_mps2=state.light.load_lateral_mps2, environment=environment).physical
    return force


def evaluate_thermal_light(settings, thermal, actuation, state, command_nm, steering, brakes, available,
                            environment, *, aero_mode, wheel_radii_m=None, driver_proxy_n=0.):
    if not isinstance(state, ThermalLightPoweredState):
        raise TypeError("ThermalLightPoweredState required")
    if state.model_sha256 != thermal_model_identity(settings, thermal, actuation, environment, wheel_radii_m):
        raise ValueError("thermal powered model changed; explicitly initialize/reset")
    if state.thermal.config_sha256 != thermal_config_identity(thermal):
        raise ValueError("thermal state configuration mismatch")
    if state.light.model_sha256 != model_identity(settings, actuation, environment, wheel_radii_m):
        raise ValueError("light structural settings mismatch")
    fraction = tire_grip_fraction(thermal, state.thermal.temperature_c)
    _, horizon = _substep_plan(settings.forces.plant, actuation, settings.feedback_period_s, wheel_radii_m)
    return evaluate_powered(settings.forces.plant, actuation, state.light.powered,
        four_numbers(command_nm, "command"), four_numbers(steering, "steering"), four_numbers(brakes, "brakes"),
        available, horizon, environment, driver_proxy_n, wheel_radii_m=wheel_radii_m,
        force_evaluator=_provider(settings, state, fraction, aero_mode))


def advance_thermal_light(settings, thermal, actuation, state, command_nm, steering, brakes, available,
                           environment, *, aero_mode, wheel_radii_m=None, maximum_work=50_000, driver_proxy_n=0.):
    """Held temperature/grip per tick; commit powered/load/thermal states together.

    Caller supplies aero state; this is not the separate automatic-DRS wrapper.
    The reference tire_mu and thermal parameters are hardware assumptions and
    must be frozen equally for controller comparisons, never optimizer genes.
    """
    _, initial_physical, _ = evaluate_thermal_light(settings, thermal, actuation, state, command_nm,
        steering, brakes, available, environment, aero_mode=aero_mode, wheel_radii_m=wheel_radii_m,
        driver_proxy_n=driver_proxy_n)
    fraction = tire_grip_fraction(thermal, state.thermal.temperature_c)
    powered = advance_powered(settings.forces.plant, actuation, state.light.powered,
        command_nm, steering, brakes, available, settings.feedback_period_s, environment,
        maximum_work=maximum_work, wheel_radii_m=wheel_radii_m, driver_proxy_n=driver_proxy_n,
        force_evaluator=_provider(settings, state, fraction, aero_mode))
    slip_energy = powered.contact_dissipation_j-state.light.powered.contact_dissipation_j
    updated_thermal = advance_tire_thermal(thermal, state.thermal, contact_slip_energy_j=slip_energy,
                                          timestep_s=settings.feedback_period_s)
    weight = -expm1(-settings.feedback_period_s/settings.load_feedback_time_constant_s)
    ax = sum(wheel.body_force_x_n for wheel in initial_physical.wheels)/settings.forces.plant.mass_kg
    ay = sum(wheel.body_force_y_n for wheel in initial_physical.wheels)/settings.forces.plant.mass_kg
    light = replace(state.light, powered=powered, aero_mode=aero_mode,
        load_longitudinal_mps2=(1-weight)*state.light.load_longitudinal_mps2+weight*ax,
        load_lateral_mps2=(1-weight)*state.light.load_lateral_mps2+weight*ay,
        feedback_ticks=state.light.feedback_ticks+1)
    return replace(state, light=light, thermal=updated_thermal, applied_grip_fraction=fraction,
                   last_contact_slip_energy_j=slip_energy)
