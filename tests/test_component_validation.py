"""Reject nonfinite engineering configurations before numerical integration."""

from dataclasses import fields
from unittest import TestCase

from vehicle_model import Vehicle
from vehicle_model.aero import Aero
from vehicle_model.electrical import Battery, Inverter, OCVPackBattery, RCTheveninBattery
from vehicle_model.mech import Brakes, Chassis, Suspension, Tire
from vehicle_model.powertrain import ChainDrive, Drivetrain, Motor


class ComponentValidationTests(TestCase):
    def test_nonfinite_scalar_configuration_is_rejected(self) -> None:
        # Discover public floating constructor parameters so newly introduced
        # scalar configuration fields receive the same guardrail coverage.
        for component_type in (
            Vehicle, Aero, Battery, OCVPackBattery, RCTheveninBattery,
            Inverter, Brakes, Chassis, Suspension, Tire, ChainDrive, Drivetrain, Motor,
        ):
            baseline = component_type()
            for parameter in fields(baseline):
                if not parameter.init or not isinstance(getattr(baseline, parameter.name), float):
                    continue
                for invalid in (float("nan"), float("inf"), -float("inf")):
                    with self.subTest(component=component_type.__name__, parameter=parameter.name, value=invalid):
                        with self.assertRaises(ValueError):
                            component_type(**{parameter.name: invalid})

    def test_nonfinite_optional_configuration_is_rejected(self) -> None:
        for component_type, parameter in (
            (Tire, "constant_friction_coefficient"),
            (Brakes, "maximum_force_request_n"),
        ):
            for invalid in (float("nan"), float("inf"), -float("inf")):
                with self.subTest(component=component_type.__name__, parameter=parameter, value=invalid):
                    with self.assertRaises(ValueError):
                        component_type(**{parameter: invalid})

    def test_nonfinite_tire_and_motor_tables_are_rejected(self) -> None:
        for component_type, parameter in (
            (Tire, "normal_loads_n"), (Tire, "lateral_coefficients"),
            (Tire, "longitudinal_coefficients"), (Motor, "torque_curve_rpm"),
            (Motor, "torque_curve_nm"), (Motor, "continuous_torque_curve_rpm"),
            (Motor, "continuous_torque_curve_nm"),
        ):
            for invalid in (float("nan"), float("inf"), -float("inf")):
                with self.subTest(component=component_type.__name__, parameter=parameter, value=invalid):
                    values = list(getattr(component_type(), parameter))
                    values[1] = invalid
                    with self.assertRaises(ValueError):
                        component_type(**{parameter: values})

    def test_mutated_component_is_revalidated_by_vehicle(self) -> None:
        vehicle = Vehicle()
        vehicle.tire.rolling_radius_m = float("nan")
        with self.assertRaisesRegex(ValueError, "rolling_radius_m.*finite"):
            vehicle.validate()
