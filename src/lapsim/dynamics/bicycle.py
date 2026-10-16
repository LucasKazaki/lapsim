"""Six-state dynamic single-track plant with explicit synthetic assumptions.

See docs/dynamic_bicycle_contract.md. Contact-force requests are axle lumped;
this plant has no independent wheel speeds, motor/battery or controller state.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, ceil, cos, hypot, isfinite, pi, sin
from numbers import Real

MODEL_ID = "dynamic_bicycle_v1"
SYNTHETIC_PROFILE_ID = "synthetic_bicycle_v1"
TOPOLOGY_ID = "rwd_axle_lumped_force_input"
MAX_INTERNAL_STEPS = 50_000


def _finite(value: object, name: str) -> None:
    try:
        valid = (
            not isinstance(value, bool) and isinstance(value, Real) and isfinite(value)
        )
    except (OverflowError, TypeError):
        valid = False
    if not valid:
        raise ValueError(f"{name} must be a finite number")


@dataclass(frozen=True, slots=True)
class BicycleConfig:
    """SI parameters of an uncalibrated synthetic two-axle vehicle."""

    mass_kg: float = 300.0
    yaw_inertia_kgm2: float = 160.0
    cg_to_front_axle_m: float = 0.8
    cg_to_rear_axle_m: float = 0.8
    front_cornering_stiffness_n_per_rad: float = 16_000.0
    rear_cornering_stiffness_n_per_rad: float = 16_000.0
    friction_coefficient: float = 1.2
    low_speed_regularization_mps: float = 0.5
    gravity_mps2: float = 9.80665
    maximum_integration_step_s: float = 0.002

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            _finite(value, name)
            if value < 0 or (value == 0 and name != "friction_coefficient"):
                raise ValueError(f"{name} must be positive (friction may be zero)")
        if self.maximum_integration_step_s > 0.01:
            raise ValueError("maximum_integration_step_s must be at most 0.01 s")
        try:
            derived = (
                self.wheelbase_m,
                *self.static_axle_loads_n,
                self.integration_step_limit_s,
            )
        except (OverflowError, ZeroDivisionError) as error:
            raise ValueError(
                "configuration exceeds the finite numerical domain"
            ) from error
        if any(not isfinite(value) or value <= 0 for value in derived):
            raise ValueError("configuration exceeds the finite numerical domain")
        if any(
            not isfinite(self.friction_coefficient * load)
            for load in self.static_axle_loads_n
        ):
            raise ValueError("friction capacity exceeds the finite numerical domain")

    @property
    def wheelbase_m(self) -> float:
        return self.cg_to_front_axle_m + self.cg_to_rear_axle_m

    @property
    def static_axle_loads_n(self) -> tuple[float, float]:
        weight = self.mass_kg * self.gravity_mps2
        return (
            weight * (self.cg_to_rear_axle_m / self.wheelbase_m),
            weight * (self.cg_to_front_axle_m / self.wheelbase_m),
        )

    @property
    def integration_step_limit_s(self) -> float:
        """Conservative lateral/yaw stiffness bound for explicit held-input RK4."""
        front, rear = (
            self.front_cornering_stiffness_n_per_rad,
            self.rear_cornering_stiffness_n_per_rad,
        )
        rate = (front + rear) / (self.mass_kg * self.low_speed_regularization_mps)
        rate += (
            front * self.cg_to_front_axle_m**2 + rear * self.cg_to_rear_axle_m**2
        ) / (self.yaw_inertia_kgm2 * self.low_speed_regularization_mps)
        if not isfinite(rate) or rate <= 0:
            raise ValueError("invalid lateral/yaw integration rate")
        return min(self.maximum_integration_step_s, 0.5 / rate)


@dataclass(frozen=True, slots=True)
class BicycleState:
    x_m: float = 0.0
    y_m: float = 0.0
    heading_rad: float = 0.0
    u_mps: float = 0.0
    v_mps: float = 0.0
    yaw_rate_rad_s: float = 0.0

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _finite(getattr(self, name), name)
        if self.u_mps < 0:
            raise ValueError("reverse is outside the bicycle model domain")


@dataclass(frozen=True, slots=True)
class BicycleControls:
    steering_angle_rad: float = 0.0
    front_force_request_n: float = 0.0
    rear_force_request_n: float = 0.0
    normal_loads_n: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        for name in (
            "steering_angle_rad",
            "front_force_request_n",
            "rear_force_request_n",
        ):
            _finite(getattr(self, name), name)
        if abs(self.steering_angle_rad) >= pi / 2:
            raise ValueError("steering must be strictly within +/- pi/2")
        if self.normal_loads_n is not None:
            if (
                not isinstance(self.normal_loads_n, (tuple, list))
                or len(self.normal_loads_n) != 2
            ):
                raise ValueError("normal_loads_n must contain front and rear loads")
            for value in self.normal_loads_n:
                _finite(value, "normal load")
                if value < 0:
                    raise ValueError("normal loads cannot be negative")
            object.__setattr__(self, "normal_loads_n", tuple(self.normal_loads_n))


@dataclass(frozen=True, slots=True)
class BicycleDerivative:
    """Rates in state order; velocity field rates are accelerations."""

    x_dot_mps: float
    y_dot_mps: float
    heading_dot_rad_s: float
    u_dot_mps2: float
    v_dot_mps2: float
    yaw_rate_dot_rad_s2: float

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _finite(getattr(self, name), "derivative " + name)


@dataclass(frozen=True, slots=True)
class BicycleEvaluation:
    derivative: BicycleDerivative
    front_slip_angle_rad: float
    rear_slip_angle_rad: float
    front_longitudinal_force_n: float
    front_lateral_force_n: float
    rear_longitudinal_force_n: float
    rear_lateral_force_n: float
    front_force_x_body_n: float
    front_force_y_body_n: float
    total_force_x_n: float
    total_force_y_n: float
    yaw_moment_nm: float
    front_limited: bool
    rear_limited: bool
    small_slip_domain: bool


def _contact_force(fx: float, fy: float, limit: float) -> tuple[float, float, bool]:
    _finite(fy, "linear tire force")
    _finite(limit, "tire force capacity")
    magnitude = hypot(fx, fy)
    if not isfinite(magnitude):
        raise ValueError("tire force exceeds the finite numerical domain")
    if limit == 0:
        return 0.0, 0.0, magnitude > 0
    scale = min(1.0, limit / magnitude) if magnitude else 1.0
    return scale * fx, scale * fy, scale < 1


def evaluate_bicycle(
    config: BicycleConfig, state: BicycleState, controls: BicycleControls
) -> BicycleEvaluation:
    """Pure tire/rigid-body balance query; no state is advanced."""
    if (
        not isinstance(config, BicycleConfig)
        or not isinstance(state, BicycleState)
        or not isinstance(controls, BicycleControls)
    ):
        raise ValueError("bicycle evaluation requires typed config, state and controls")
    a, b = config.cg_to_front_axle_m, config.cg_to_rear_axle_m
    delta = controls.steering_angle_rad
    c, s = cos(delta), sin(delta)
    front_v = state.v_mps + a * state.yaw_rate_rad_s
    front_x, front_y = state.u_mps * c + front_v * s, -state.u_mps * s + front_v * c
    alpha_f = atan2(-front_y, max(front_x, config.low_speed_regularization_mps))
    alpha_r = atan2(
        -(state.v_mps - b * state.yaw_rate_rad_s),
        max(state.u_mps, config.low_speed_regularization_mps),
    )
    loads = (
        controls.normal_loads_n
        if controls.normal_loads_n is not None
        else config.static_axle_loads_n
    )
    fxf, fyf, limited_f = _contact_force(
        controls.front_force_request_n,
        config.front_cornering_stiffness_n_per_rad * alpha_f,
        config.friction_coefficient * loads[0],
    )
    fxr, fyr, limited_r = _contact_force(
        controls.rear_force_request_n,
        config.rear_cornering_stiffness_n_per_rad * alpha_r,
        config.friction_coefficient * loads[1],
    )
    front_fx, front_fy = fxf * c - fyf * s, fxf * s + fyf * c
    fx, fy = front_fx + fxr, front_fy + fyr
    moment = a * front_fy - b * fyr
    ch, sh = cos(state.heading_rad), sin(state.heading_rad)
    derivative = BicycleDerivative(
        state.u_mps * ch - state.v_mps * sh,
        state.u_mps * sh + state.v_mps * ch,
        state.yaw_rate_rad_s,
        fx / config.mass_kg + state.yaw_rate_rad_s * state.v_mps,
        fy / config.mass_kg - state.yaw_rate_rad_s * state.u_mps,
        moment / config.yaw_inertia_kgm2,
    )
    return BicycleEvaluation(
        derivative,
        alpha_f,
        alpha_r,
        fxf,
        fyf,
        fxr,
        fyr,
        front_fx,
        front_fy,
        fx,
        fy,
        moment,
        limited_f,
        limited_r,
        abs(alpha_f) <= 0.2 and abs(alpha_r) <= 0.2,
    )


def integrate_bicycle(
    config: BicycleConfig,
    state: BicycleState,
    controls: BicycleControls,
    timestep_s: float,
) -> BicycleState:
    """Advance held force inputs; trial stages cannot tick any controller."""
    if (
        not isinstance(config, BicycleConfig)
        or not isinstance(state, BicycleState)
        or not isinstance(controls, BicycleControls)
    ):
        raise ValueError(
            "bicycle integration requires typed config, state and controls"
        )
    _finite(timestep_s, "timestep_s")
    if timestep_s <= 0:
        raise ValueError("timestep_s must be positive")
    count_float = timestep_s / config.integration_step_limit_s
    if not isfinite(count_float) or count_float > MAX_INTERNAL_STEPS:
        raise ValueError("bicycle integration exceeds the work budget")
    count = max(1, ceil(count_float))
    h = timestep_s / count
    names = tuple(state.__dataclass_fields__)
    rates = dict(
        zip(
            names,
            (
                "x_dot_mps",
                "y_dot_mps",
                "heading_dot_rad_s",
                "u_dot_mps2",
                "v_dot_mps2",
                "yaw_rate_dot_rad_s2",
            ),
            strict=True,
        )
    )

    def shifted(
        base: BicycleState, rate: BicycleDerivative, scale: float
    ) -> BicycleState:
        return BicycleState(
            **{
                name: getattr(base, name) + scale * getattr(rate, rates[name])
                for name in names
            }
        )

    for _ in range(count):
        k1 = evaluate_bicycle(config, state, controls).derivative
        k2 = evaluate_bicycle(config, shifted(state, k1, h / 2), controls).derivative
        k3 = evaluate_bicycle(config, shifted(state, k2, h / 2), controls).derivative
        k4 = evaluate_bicycle(config, shifted(state, k3, h), controls).derivative
        state = BicycleState(
            **{
                name: getattr(state, name)
                + h
                / 6
                * (
                    getattr(k1, rates[name])
                    + 2 * getattr(k2, rates[name])
                    + 2 * getattr(k3, rates[name])
                    + getattr(k4, rates[name])
                )
                for name in names
            }
        )
    return state
