"""Driver control inputs for distance-domain vehicle simulation."""

from dataclasses import dataclass
from math import isfinite, pi


@dataclass(frozen=True, slots=True)
class Controls:
    """Driver requests held across one spatial simulation cell."""

    motor_torque_request_nm: float = 0.0
    front_brake_pressure_psi: float = 0.0
    rear_brake_pressure_psi: float = 0.0
    rear_regenerative_brake_force_request_n: float = 0.0
    steering_angle_rad: float = 0.0
    front_regenerative_brake_force_request_n: float = 0.0

    def __post_init__(self) -> None:
        if not all(
            isfinite(value)
            for value in (
                self.motor_torque_request_nm,
                self.front_brake_pressure_psi,
                self.rear_brake_pressure_psi,
                self.front_regenerative_brake_force_request_n,
                self.rear_regenerative_brake_force_request_n,
                self.steering_angle_rad,
            )
        ):
            raise ValueError("control requests must be finite")
        if self.motor_torque_request_nm < 0:
            raise ValueError(
                "motor_torque_request_nm cannot be negative; use an axle regen request"
            )
        if self.front_brake_pressure_psi < 0:
            raise ValueError("front_brake_pressure_psi cannot be negative")
        if self.rear_brake_pressure_psi < 0:
            raise ValueError("rear_brake_pressure_psi cannot be negative")
        if self.front_regenerative_brake_force_request_n < 0:
            raise ValueError(
                "front_regenerative_brake_force_request_n cannot be negative"
            )
        if self.rear_regenerative_brake_force_request_n < 0:
            raise ValueError(
                "rear_regenerative_brake_force_request_n cannot be negative"
            )
        if self.motor_torque_request_nm > 0 and (
            self.front_regenerative_brake_force_request_n > 0
            or self.rear_regenerative_brake_force_request_n > 0
        ):
            raise ValueError("one motor cannot drive and regenerate simultaneously")
        if not -pi / 2 < self.steering_angle_rad < pi / 2:
            raise ValueError(
                "steering_angle_rad must be strictly between -pi/2 and pi/2"
            )
