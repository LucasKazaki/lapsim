"""Small state-ownership boundary for optional native vehicle plants.

All observations use SI and a right-handed world frame (X forward initially,
Y left, Z up). Wheel slots are FL, FR, RL, RR. A runner owns the integer clock;
one backend alone owns all physical state. Observations never advance physics.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol

WHEEL_ORDER = ("FL", "FR", "RL", "RR")


@dataclass(frozen=True, slots=True)
class PlantCapabilities:
    backend_id: str
    topology_id: str
    device: str
    physical_state_owner: str
    suspension: str
    tire: str


@dataclass(frozen=True, slots=True)
class AxleCommand:
    """A held driveshaft request; the rear differential allocates wheel torque.

    Steering is a normalized driver request, not a wheel angle. The v1 study
    has no powertrain, electrical model, regeneration or independent motors.
    """

    driveshaft_torque_nm: float = 0.0
    steering: float = 0.0
    braking: float = 0.0

    def __post_init__(self) -> None:
        for name, low, high in (
            ("driveshaft_torque_nm", 0, 400),
            ("steering", -0.25, 0.25),
            ("braking", 0, 1),
        ):
            value = getattr(self, name)
            if (
                type(value) not in (float, int)
                or not low <= value <= high
                or not isfinite(value)
            ):
                raise ValueError(f"{name} outside the synthetic study domain")


@dataclass(frozen=True, slots=True)
class PlantObservation:
    time_s: float
    tire_force_source_time_s: float | None
    tire_kinematics_source_time_s: float | None
    applied_tire_force_source_time_s: float | None
    applied_tire_force_geometry_time_s: float
    position_m: tuple[float, float, float]
    velocity_mps: tuple[float, float, float]
    cardan_xyz_rad: tuple[float, float, float]
    heading_rad: float
    angular_velocity_rad_s: tuple[float, float, float]
    mass_kg: float
    wheel_position_m: tuple[tuple[float, float, float], ...]
    wheel_omega_rad_s: tuple[float, ...]
    native_axle_shaft_omega_rad_s: tuple[float, ...]
    wheel_force_world_n: tuple[tuple[float, float, float], ...]
    applied_wheel_force_world_n: tuple[tuple[float, float, float], ...]
    tire_slip_ratio: tuple[float, ...]
    tire_slip_angle_rad: tuple[float, ...]
    suspension_spring_length_m: tuple[float, ...]
    suspension_spring_force_n: tuple[float, ...]
    suspension_damper_force_n: tuple[float, ...]
    driveline_wheel_torque_nm: tuple[float, ...]
    command: AxleCommand


class NativePlant(Protocol):
    """A backend owns state between reset and close; advancing is explicit."""

    capabilities: PlantCapabilities

    def reset(self) -> None: ...

    def set_command(self, command: AxleCommand) -> None: ...

    def advance(self, step_s: float) -> None: ...

    def observe(self) -> PlantObservation: ...

    def provenance(self) -> dict: ...

    def close(self) -> None: ...
