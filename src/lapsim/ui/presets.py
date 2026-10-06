"""Starter vehicle data and the deliberately simple Prius benchmark model."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi

from vehicle_model import (
    Aero,
    ChainDrive,
    Chassis,
    Drivetrain,
    Inverter,
    Motor,
    Tire,
    Vehicle,
)
from vehicle_model.electrical import OCVPackBattery


TOYOTA_2026_PRIUS_SPECS = {
    "year": 2026,
    "trim": "LE FWD",
    "net_system_power_hp": 194,
    "engine": "2.0 L 4-cylinder hybrid",
    "length_m": 181.1 * 0.0254,
    "width_m": 70.2 * 0.0254,
    "height_m": 55.9 * 0.0254,
    "wheelbase_m": 108.3 * 0.0254,
    "curb_mass_kg": 3097 * 0.45359237,
    "tire_size": "195/60R17",
    "tire_nominal_radius_m": (17 * 0.0254 + 2 * 0.195 * 0.60) / 2,
    "sources": (
        "https://pressroom.toyota.com/vehicle/2026-toyota-prius/",
        "https://www.toyota.com/prius/2026/compare/summary/",
        "https://www.toyota.com/content/dam/toyota/brochures/pdf/2026/prius_ebrochure.pdf",
    ),
}


@dataclass(frozen=True, slots=True)
class VehicleSetup:
    """Editable run inputs; fields without Toyota data are explicit estimates."""

    mass_kg: float = TOYOTA_2026_PRIUS_SPECS["curb_mass_kg"]
    peak_power_kw: float = TOYOTA_2026_PRIUS_SPECS["net_system_power_hp"] * 0.745699872
    wheelbase_m: float = TOYOTA_2026_PRIUS_SPECS["wheelbase_m"]
    tire_radius_m: float = TOYOTA_2026_PRIUS_SPECS["tire_nominal_radius_m"]
    tire_mu: float = 0.95
    drag_area_m2: float = 0.59
    top_speed_kph: float = 180.0
    torque_request_fraction: float = 1.0

    def __post_init__(self) -> None:
        positive = (
            self.mass_kg,
            self.peak_power_kw,
            self.wheelbase_m,
            self.tire_radius_m,
            self.tire_mu,
            self.drag_area_m2,
            self.top_speed_kph,
        )
        if any(not isfinite(value) or value <= 0.0 for value in positive):
            raise ValueError("Vehicle setup values must be finite and positive")
        if not isfinite(self.torque_request_fraction) or not 0.0 <= self.torque_request_fraction <= 1.0:
            raise ValueError("torque_request_fraction must be in [0, 1]")


def make_prius_benchmark(setup: VehicleSetup) -> Vehicle:
    """Build a low-order FWD power-equivalent model from the Prius LE baseline.

    Toyota publishes net combined system power, rather than a single traction
    motor curve. The simulator uses that rating as an idealized power source;
    it does not claim to reproduce the Prius hybrid transaxle or battery.
    Tire friction and several chassis values are editable engineering starts,
    not manufacturer specifications.
    """

    peak_power_w = setup.peak_power_kw * 1_000.0
    equivalent_knee_rpm = 4_200.0
    torque_at_knee_nm = peak_power_w / (equivalent_knee_rpm * 2.0 * pi / 60.0)
    torque_curve_rpm = [0.0, equivalent_knee_rpm, 8_000.0, 10_000.0]
    torque_curve_nm = [
        torque_at_knee_nm,
        torque_at_knee_nm,
        torque_at_knee_nm * equivalent_knee_rpm / 8_000.0,
        torque_at_knee_nm * equivalent_knee_rpm / 10_000.0,
    ]
    motor = Motor(
        torque_curve_rpm=torque_curve_rpm,
        torque_curve_nm=torque_curve_nm,
        continuous_torque_curve_rpm=torque_curve_rpm.copy(),
        continuous_torque_curve_nm=torque_curve_nm.copy(),
        peak_power_w=peak_power_w,
        continuous_power_w=peak_power_w,
        max_speed_rpm=10_000.0,
        efficiency=1.0,
        rotor_inertia_kgm2=0.0,
    )
    tire = Tire(
        rolling_radius_m=setup.tire_radius_m,
        constant_friction_coefficient=setup.tire_mu,
    )
    top_speed_mps = setup.top_speed_kph / 3.6
    reduction_ratio = (
        10_000.0 * 2.0 * pi / 60.0 * setup.tire_radius_m / top_speed_mps
    )
    drivetrain = Drivetrain(
        motor=motor,
        inverter=Inverter(efficiency=1.0),
        chain_drive=ChainDrive(ratio=reduction_ratio, efficiency=1.0),
        tire=tire,
        driven_wheel_inertia_kgm2=0.0,
        configured_speed_limit_mps=top_speed_mps,
        driven_axle="front",
    )
    return Vehicle(
        mass_kg=setup.mass_kg,
        tire=tire,
        drivetrain=drivetrain,
        aero=Aero(
            frontal_area_m2=1.0,
            drag_coefficient=setup.drag_area_m2,
            lift_coefficient=0.0,
            front_downforce_fraction=0.60,
        ),
        battery=OCVPackBattery(
            cell_capacity_ah=25.0,
            max_discharge_power_w=peak_power_w,
            max_charge_power_w=0.0,
            cell_internal_resistance_ohm=0.0005,
        ),
        chassis=Chassis(
            wheelbase_m=setup.wheelbase_m,
            cg_height_m=0.53,
            front_track_width_m=1.56,
            rear_track_width_m=1.58,
            static_front_weight_fraction=0.60,
        ),
        rolling_resistance_coefficient=0.012,
        cornering_drag_coefficient=0.025,
    )
