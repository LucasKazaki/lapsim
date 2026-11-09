"""Uncalibrated light-mode force layer over the existing four-wheel core.

This is a force-evaluation slice, not a new lap runner or powered integrator.
Air-relative coefficient-area aero and quasi-static transfer have ONE load
owner. Ax/ay are explicit imposed body-axis accelerations, not solved implicitly.
No tire thermal state, automatic DRS, actuator, controller or pack is advanced.
Rendering has no input to this module. Frozen tournament code never imports it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from hashlib import sha256
import json
from math import cos, hypot, isfinite, sin
from typing import Literal

from .conditions import PlanarEnvironment
from .planar import PlanarControls, PlanarEvaluation, PlanarState, PlanarVehicleConfig, WheelValues, evaluate_planar_dynamics

FAMILY = "lapsim.torque-light-force.v1"
AeroMode = Literal["closed", "open"]


def _finite(*values: float) -> None:
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in values):
        raise ValueError("force-layer values must be finite numbers")


def _finite_physical(physical: PlanarEvaluation) -> None:
    """Reject nonfinite diagnostics/derivatives from the reused force core.

    Booleans, material labels and nested containers are not numeric fields.
    Checking all numeric dataclass members also covers wheel/slip diagnostics,
    rather than validating only the forces returned separately by this adapter.
    """
    skip = {"derivative", "wheels", "road_valid", "road_material_id"}
    values = []
    for obj in (physical, physical.derivative, *physical.wheels):
        for item in fields(obj):
            if item.name not in skip:
                value = getattr(obj, item.name)
                values.extend(value if isinstance(value, tuple) else (value,))
    _finite(*values)


@dataclass(frozen=True, slots=True)
class AeroAreas:
    """Coefficient-areas in m²; downward-positive ClA, front balance in [0,1]."""
    drag_area_m2: float
    downforce_area_m2: float
    front_downforce_fraction: float

    def __post_init__(self) -> None:
        _finite(self.drag_area_m2, self.downforce_area_m2, self.front_downforce_fraction)
        if min(self.drag_area_m2, self.downforce_area_m2) < 0 or not 0 <= self.front_downforce_fraction <= 1:
            raise ValueError("aero areas must be nonnegative and balance must be in [0,1]")


@dataclass(frozen=True, slots=True)
class LightForceConfig:
    """Explicit provisional inputs; no team-car coefficients/default profile.

    CG height is m; front_roll_moment_fraction assigns m*ay*h between axles.
    This neglects pitch/roll transients, drag height and aero side/yaw moments.
    """
    plant: PlanarVehicleConfig
    closed: AeroAreas
    open: AeroAreas
    cg_height_m: float
    front_roll_moment_fraction: float
    provenance: str

    def __post_init__(self) -> None:
        if not isinstance(self.plant, PlanarVehicleConfig) or not all(isinstance(v, AeroAreas) for v in (self.closed, self.open)):
            raise TypeError("explicit planar plant and both aero states are required")
        _finite(self.cg_height_m, self.front_roll_moment_fraction)
        if self.cg_height_m < 0 or not 0 <= self.front_roll_moment_fraction <= 1:
            raise ValueError("invalid CG height or roll-moment fraction")
        if self.open.drag_area_m2 > self.closed.drag_area_m2 or self.open.downforce_area_m2 > self.closed.downforce_area_m2:
            raise ValueError("open state must declare lower/equal drag and downforce; balance may differ")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("provenance and uncertainty must be declared")


@dataclass(frozen=True, slots=True)
class LightForceResult:
    physical: PlanarEvaluation
    physics_identity: str
    aero_mode: AeroMode
    normal_loads_n: WheelValues
    air_speed_mps: float
    drag_body_x_n: float
    drag_body_y_n: float
    downforce_n: float
    front_downforce_n: float
    rear_downforce_n: float


def physics_identity(config: LightForceConfig, environment: PlanarEnvironment) -> str:
    """Versioned force-model/settings identity, not a complete run identity.

    The eventual runner must additionally bind topology, DRS policy/initial state,
    clocks, thermal model, controller, starting state and scenario. No UI fields.
    """
    data = {"family": FAMILY, "config": asdict(config), "environment": asdict(environment)}
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def evaluate_light_forces(
    config: LightForceConfig, state: PlanarState, controls: PlanarControls, *,
    aero_mode: AeroMode, longitudinal_acceleration_mps2: float,
    lateral_acceleration_mps2: float, environment: PlanarEnvironment,
) -> LightForceResult:
    """Compute aero/loads then reuse combined-slip tire/wheel force evaluation.

    Body x forward/y left, positive yaw left. Positive ax transfers load rear;
    positive ay transfers load to right wheels. Reject negative corner loads
    rather than silently clipping transfer and granting unsupported traction.
    The base environment MUST have zero drag area: this layer owns selected CdA.
    """
    if not isinstance(environment, PlanarEnvironment) or not isinstance(config, LightForceConfig):
        raise TypeError("explicit force config and planar environment required")
    if aero_mode not in ("closed", "open"):
        raise ValueError("aero mode must be explicit closed/open; automatic policy is not implemented")
    if controls.normal_loads_n is not None or environment.drag_area_m2 != 0:
        raise ValueError("light force layer exclusively owns normal loads and drag area")
    _finite(longitudinal_acceleration_mps2, lateral_acceleration_mps2)
    areas = config.closed if aero_mode == "closed" else config.open
    c, s = cos(state.heading_rad), sin(state.heading_rad)
    vx = state.u_mps - (c * environment.wind_world_x_mps + s * environment.wind_world_y_mps)
    vy = state.v_mps - (-s * environment.wind_world_x_mps + c * environment.wind_world_y_mps)
    air_speed = hypot(vx, vy)
    q = .5 * environment.air_density_kgpm3 * air_speed * air_speed
    _finite(air_speed, q)
    down = q * areas.downforce_area_m2
    front_aero = down * areas.front_downforce_fraction
    rear_aero = down - front_aero
    plant = config.plant
    wheelbase = plant.cg_to_front_axle_m + plant.cg_to_rear_axle_m
    rearward = plant.mass_kg * longitudinal_acceleration_mps2 * config.cg_height_m / wheelbase
    front = sum(plant.static_normal_loads_n[:2]) + front_aero - rearward
    rear = sum(plant.static_normal_loads_n[2:]) + rear_aero + rearward
    roll_moment = plant.mass_kg * lateral_acceleration_mps2 * config.cg_height_m
    front_delta = config.front_roll_moment_fraction * roll_moment / plant.front_track_m
    rear_delta = (1 - config.front_roll_moment_fraction) * roll_moment / plant.rear_track_m
    loads = (front / 2 - front_delta, front / 2 + front_delta,
             rear / 2 - rear_delta, rear / 2 + rear_delta)
    scale = -.5 * environment.air_density_kgpm3 * areas.drag_area_m2 * air_speed
    drag_x, drag_y = scale * vx, scale * vy
    aero_power = drag_x * state.u_mps + drag_y * state.v_mps
    _finite(down, front_aero, rear_aero, scale, drag_x, drag_y, aero_power, *loads)
    if any(value < 0 for value in loads):
        raise ValueError("negative corner load: outside supported quasi-static contact domain")
    physical = evaluate_planar_dynamics(plant, state, replace(controls, normal_loads_n=loads),
                                       environment=replace(environment, drag_area_m2=areas.drag_area_m2))
    _finite_physical(physical)
    return LightForceResult(physical, physics_identity(config, environment), aero_mode, loads,
                            air_speed, drag_x, drag_y, down, front_aero, rear_aero)
