"""TC-01P aggregate DC-power budget for the portable torque allocator.

Synthetic/offline reference only.

This module adds one system-level constraint that is not represented by
independent per-wheel torque limits: a shared DC-side propulsion power budget.

For forward propulsion only:

    P_wheel_candidate = sum(tau_i * omega_i)

A scenario/source-backed DC budget is converted to a wheel-mechanical budget:

    P_wheel_budget = eta_dc_to_wheel * P_dc_available

If the candidate allocation exceeds the mechanical budget, all nonnegative
wheel-torque commands are multiplied by one common scale:

    alpha = P_wheel_budget / P_wheel_candidate

This preserves the base allocator's torque distribution ratios while reducing
total delivered torque enough to satisfy the portable aggregate power bound.

Scope and limits:
- four synthetic wheel channels because the current portable allocator has four;
- forward propulsion only: negative wheel speed / regen are unsupported;
- constant aggregate efficiency is a scenario simplification, not a motor map;
- no battery voltage/current/SOC/temperature model;
- no inverter current or motor thermal constraints;
- no tire/slip/yaw control;
- no firmware, CAN, shutdown or vehicle authority.

The common-scale policy is intentionally conservative and simple. It is not an
energy-optimal control allocation algorithm.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math

from allocator import (
    AllocationInput,
    AllocationResult,
    AllocatorConfig,
    allocate_propulsive_torque,
)

CHANNEL_COUNT = 4
SOURCE_KINDS = {"scenario", "team_verified"}


class AggregatePowerBudgetError(ValueError):
    pass


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AggregatePowerBudgetError(f"{name} must be a finite number")
    out = float(value)
    if not math.isfinite(out):
        raise AggregatePowerBudgetError(f"{name} must be a finite number")
    return out


def _nonnegative(value: object, name: str) -> float:
    out = _finite(value, name)
    if out < 0.0:
        raise AggregatePowerBudgetError(f"{name} must be nonnegative")
    return out


def _efficiency(value: object) -> float:
    out = _finite(value, "dc_to_wheel_efficiency")
    if not 0.0 < out <= 1.0:
        raise AggregatePowerBudgetError(
            "dc_to_wheel_efficiency must be in (0, 1]"
        )
    return out


def _source_kind(value: object) -> str:
    if value not in SOURCE_KINDS:
        raise AggregatePowerBudgetError(
            "source_kind must be scenario or team_verified"
        )
    return str(value)


@dataclass(frozen=True)
class AggregatePowerConfig:
    dc_power_available_w: float
    dc_to_wheel_efficiency: float
    source_kind: str = "scenario"

    def checked(self) -> "AggregatePowerConfig":
        return AggregatePowerConfig(
            dc_power_available_w=_nonnegative(
                self.dc_power_available_w, "dc_power_available_w"
            ),
            dc_to_wheel_efficiency=_efficiency(
                self.dc_to_wheel_efficiency
            ),
            source_kind=_source_kind(self.source_kind),
        )


@dataclass(frozen=True)
class AggregatePowerResult:
    schema: str
    base_allocation: AllocationResult
    wheel_omega_rad_s: tuple[float, float, float, float]

    dc_power_available_w: float
    dc_to_wheel_efficiency: float
    wheel_mechanical_power_budget_w: float

    candidate_wheel_mechanical_power_w: float
    final_wheel_mechanical_power_w: float
    estimated_final_dc_power_w: float
    power_scale: float

    final_wheel_torque_nm: tuple[float, float, float, float]
    final_delivered_nm: float
    status: str
    fault: str | None
    power_limit_active: bool
    source_kind: str

    battery_soc_limit_proven: bool = False
    battery_current_limit_proven: bool = False
    dc_voltage_limit_proven: bool = False
    inverter_current_limit_proven: bool = False
    thermal_limit_proven: bool = False
    traction_limit_proven: bool = False
    regen_limit_proven: bool = False
    vehicle_acceptance_proven: bool = False
    action_authority: bool = False

    def to_json(self) -> str:
        payload = asdict(self)
        payload["base_allocation"] = asdict(self.base_allocation)
        payload["wheel_omega_rad_s"] = list(self.wheel_omega_rad_s)
        payload["final_wheel_torque_nm"] = list(
            self.final_wheel_torque_nm
        )
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )


def _zero_result(
    *,
    base: AllocationResult,
    wheel_omega_rad_s: tuple[float, float, float, float],
    cfg: AggregatePowerConfig,
    fault: str,
) -> AggregatePowerResult:
    checked = cfg.checked()
    return AggregatePowerResult(
        schema="enme408-tc01p-aggregate-power-budget/v1",
        base_allocation=base,
        wheel_omega_rad_s=wheel_omega_rad_s,
        dc_power_available_w=checked.dc_power_available_w,
        dc_to_wheel_efficiency=checked.dc_to_wheel_efficiency,
        wheel_mechanical_power_budget_w=(
            checked.dc_power_available_w
            * checked.dc_to_wheel_efficiency
        ),
        candidate_wheel_mechanical_power_w=0.0,
        final_wheel_mechanical_power_w=0.0,
        estimated_final_dc_power_w=0.0,
        power_scale=0.0,
        final_wheel_torque_nm=(0.0, 0.0, 0.0, 0.0),
        final_delivered_nm=0.0,
        status="fault",
        fault=fault,
        power_limit_active=False,
        source_kind=checked.source_kind,
    )


def allocate_with_aggregate_power_budget(
    *,
    allocation_input: AllocationInput,
    allocator_config: AllocatorConfig,
    wheel_omega_rad_s: tuple[float, float, float, float],
    power_config: AggregatePowerConfig,
) -> AggregatePowerResult:
    """Apply a shared DC-power budget after the current reference allocator.

    The base allocator establishes its existing distribution and wheel torque
    bounds first. This wrapper then applies at most one common scalar, preserving
    every wheel-to-wheel torque ratio produced by the base allocator.
    """
    cfg = power_config.checked()

    if len(wheel_omega_rad_s) != CHANNEL_COUNT:
        raise AggregatePowerBudgetError(
            "exactly four wheel angular speeds are required"
        )

    try:
        omega = tuple(
            _nonnegative(x, "wheel_omega_rad_s")
            for x in wheel_omega_rad_s
        )
    except AggregatePowerBudgetError:
        base = allocate_propulsive_torque(
            allocation_input, allocator_config
        )
        safe_omega = tuple(
            float(x)
            if isinstance(x, (int, float))
            and not isinstance(x, bool)
            and math.isfinite(float(x))
            and float(x) >= 0.0
            else 0.0
            for x in wheel_omega_rad_s
        )
        return _zero_result(
            base=base,
            wheel_omega_rad_s=safe_omega,
            cfg=cfg,
            fault="invalid_wheel_speed",
        )

    base = allocate_propulsive_torque(
        allocation_input, allocator_config
    )

    if base.status == "fault":
        return AggregatePowerResult(
            schema="enme408-tc01p-aggregate-power-budget/v1",
            base_allocation=base,
            wheel_omega_rad_s=omega,
            dc_power_available_w=cfg.dc_power_available_w,
            dc_to_wheel_efficiency=cfg.dc_to_wheel_efficiency,
            wheel_mechanical_power_budget_w=(
                cfg.dc_power_available_w
                * cfg.dc_to_wheel_efficiency
            ),
            candidate_wheel_mechanical_power_w=0.0,
            final_wheel_mechanical_power_w=0.0,
            estimated_final_dc_power_w=0.0,
            power_scale=0.0,
            final_wheel_torque_nm=base.wheel_torque_nm,
            final_delivered_nm=base.delivered_nm,
            status=base.status,
            fault=base.fault,
            power_limit_active=False,
            source_kind=cfg.source_kind,
        )

    candidate_power = sum(
        tau * w
        for tau, w in zip(base.wheel_torque_nm, omega)
    )
    wheel_budget = (
        cfg.dc_power_available_w
        * cfg.dc_to_wheel_efficiency
    )

    epsilon = 1e-12
    if candidate_power <= wheel_budget + epsilon:
        final_torque = base.wheel_torque_nm
        final_power = candidate_power
        scale = 1.0
        power_active = False
        status = base.status
        fault = base.fault
    elif candidate_power <= epsilon:
        final_torque = base.wheel_torque_nm
        final_power = candidate_power
        scale = 1.0
        power_active = False
        status = base.status
        fault = base.fault
    else:
        scale = wheel_budget / candidate_power
        final_torque = tuple(
            tau * scale for tau in base.wheel_torque_nm
        )
        final_power = sum(
            tau * w for tau, w in zip(final_torque, omega)
        )
        power_active = True
        status = "saturated"
        fault = "aggregate_dc_power_limit"

    final_delivered = sum(final_torque)
    final_dc = (
        final_power / cfg.dc_to_wheel_efficiency
        if final_power > 0.0
        else 0.0
    )

    return AggregatePowerResult(
        schema="enme408-tc01p-aggregate-power-budget/v1",
        base_allocation=base,
        wheel_omega_rad_s=omega,
        dc_power_available_w=cfg.dc_power_available_w,
        dc_to_wheel_efficiency=cfg.dc_to_wheel_efficiency,
        wheel_mechanical_power_budget_w=wheel_budget,
        candidate_wheel_mechanical_power_w=candidate_power,
        final_wheel_mechanical_power_w=final_power,
        estimated_final_dc_power_w=final_dc,
        power_scale=scale,
        final_wheel_torque_nm=final_torque,
        final_delivered_nm=final_delivered,
        status=status,
        fault=fault,
        power_limit_active=power_active,
        source_kind=cfg.source_kind,
    )


def frozen_aggregate_power_counterexample() -> AggregatePowerResult:
    """Scenario-only example: per-wheel torque bounds pass but shared power does not."""
    inp = AllocationInput(
        now_ms=1_000,
        input_timestamp_ms=1_000,
        request_nm=400.0,
        wheel_limits_nm=(200.0, 200.0, 200.0, 200.0),
        wheel_enabled=(True, True, True, True),
        external_interlock=True,
    )
    return allocate_with_aggregate_power_budget(
        allocation_input=inp,
        allocator_config=AllocatorConfig(max_input_age_ms=50),
        wheel_omega_rad_s=(20.0, 40.0, 60.0, 80.0),
        power_config=AggregatePowerConfig(
            dc_power_available_w=12_000.0,
            dc_to_wheel_efficiency=0.90,
            source_kind="scenario",
        ),
    )
