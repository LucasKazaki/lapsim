"""Causal fixed-clock controller -> constrained actuator -> four-wheel plant."""

from __future__ import annotations

import argparse
import heapq
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
from math import ceil, isclose
from pathlib import Path
from typing import Any

from lapsim.dynamics.actuation import TOPOLOGY_ID, ActuationConfig, constrain_actuation
from lapsim.dynamics.bicycle import _finite
from lapsim.dynamics.conditions import (
    PlanarEnvironment,
    PlanarRoad,
    RectangularGripPatch,
    RoadDomain,
)
from lapsim.dynamics.planar import PlanarState, PlanarVehicleConfig
from lapsim.dynamics.powered_planar import (
    PoweredState,
    advance_powered,
    energy_residual_j,
    evaluate_powered,
)
from lapsim.resources import build_identity, repository_root

from .basic_dynamics import decode_json
from .controller_backend import PythonController, controller_source_identity
from .dynamics_record import _canonical_json, _content_id, _runtime_identity

SCHEMA = "lapsim.closed-loop.record.v3"
MODEL_ID = "independent_wheel_planar_v1"
PROFILE_ID = "synthetic_rear_drive_control_v1"
ZERO = (0.0, 0.0, 0.0, 0.0)


def _physical_values(value: Any, name: str) -> None:
    """Reject booleans in the new runner without changing legacy records."""
    if isinstance(value, dict):
        for key, item in value.items():
            _physical_values(item, name + "." + key)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _physical_values(item, name)
    elif value is not None and not isinstance(value, str):
        _finite(value, name)


def synthetic_car() -> PlanarVehicleConfig:
    return PlanarVehicleConfig(300, 160, 0.8, 0.8, 1.2, 1.2, 0.2, 0.3, 1.2, 7000, 8000)


def plant_source_identity() -> dict:
    names = (
        "dynamics/planar.py",
        "dynamics/conditions.py",
        "dynamics/actuation.py",
        "dynamics/powered_planar.py",
        "experiments/closed_loop.py",
        "experiments/controller_backend.py",
    )
    root = repository_root()
    return {
        "hash_scope": "Python source bytes with CRLF normalized to LF only",
        "files_sha256": {
            "src/lapsim/" + name: sha256(
                (root / "src/lapsim" / name).read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest()
            for name in names
        },
    }


@dataclass(frozen=True, slots=True)
class DriverPoint:
    time_us: int
    accelerator_fraction: float = 0.0
    brake_fraction: float = 0.0
    steering_rad: float = 0.0
    valid: bool = True
    enabled: bool = True

    def __post_init__(self) -> None:
        if type(self.time_us) is not int or self.time_us < 0:
            raise ValueError("driver time must be nonnegative integer microseconds")
        for name in ("accelerator_fraction", "brake_fraction", "steering_rad"):
            _finite(getattr(self, name), name)
        if (
            not 0 <= self.accelerator_fraction <= 1
            or not 0 <= self.brake_fraction <= 1
            or abs(self.steering_rad) > 0.26
        ):
            raise ValueError("driver inputs exceed the synthetic domain")
        if type(self.valid) is not bool or type(self.enabled) is not bool:
            raise ValueError("driver validity and enable must be booleans")


@dataclass(frozen=True, slots=True)
class ClosedLoopScenario:
    schema_version: int = 1
    model_id: str = MODEL_ID
    vehicle_profile_id: str = PROFILE_ID
    drivetrain_topology_id: str = TOPOLOGY_ID
    controller_backend_id: str = "python_reference"
    strategy: str = "equal_split"
    vehicle: PlanarVehicleConfig = field(default_factory=synthetic_car)
    actuation: ActuationConfig = field(default_factory=ActuationConfig)
    environment: PlanarEnvironment = field(default_factory=PlanarEnvironment)
    initial_state: PlanarState = field(default_factory=PlanarState)
    initial_soc: float = 0.5
    duration_us: int = 1_000_000
    plant_step_us: int = 1000
    controller_period_us: int = 10_000
    sensor_period_us: int = 10_000
    sensor_delay_us: int = 10_000
    logging_period_us: int = 20_000
    maximum_sensor_age_ms: int = 50
    maximum_driver_request_nm: float = 400.0
    maximum_friction_brake_nm: float = 40.0
    maximum_regen_request_nm: float = 120.0
    driver: tuple[DriverPoint, ...] = field(
        default_factory=lambda: (
            DriverPoint(0),
            DriverPoint(300_000, 1.0),
            DriverPoint(1_000_000, 1.0),
        )
    )
    dropped_sequences: tuple[int, ...] = ()
    duplicate_sequences: tuple[int, ...] = ()
    extra_delays_us: tuple[tuple[int, int], ...] = ()
    restart_times_us: tuple[int, ...] = ()
    failed_rear_index: int | None = None
    failure_time_us: int = 0

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("unknown closed-loop scenario version")
        for name, expected in (
            ("model_id", MODEL_ID),
            ("vehicle_profile_id", PROFILE_ID),
            ("drivetrain_topology_id", TOPOLOGY_ID),
        ):
            if getattr(self, name) != expected:
                raise ValueError("unsupported " + name)
        if self.controller_backend_id not in (
            "python_reference",
            "native_c",
            "qemu_stm32f405",
        ):
            raise ValueError("unsupported controller backend")
        if self.strategy not in ("equal_split", "traction_limited"):
            raise ValueError("unsupported controller strategy")
        for name, kind in (
            ("vehicle", PlanarVehicleConfig),
            ("actuation", ActuationConfig),
            ("initial_state", PlanarState),
            ("environment", PlanarEnvironment),
        ):
            if not isinstance(getattr(self, name), kind):
                raise TypeError("expected typed " + name)
        for value in asdict(self.vehicle).values():
            _finite(value, "vehicle parameter")
        _physical_values(asdict(self.initial_state), "initial state")
        _physical_values(asdict(self.environment), "environment")
        for name in (
            "initial_soc",
            "maximum_driver_request_nm",
            "maximum_friction_brake_nm",
            "maximum_regen_request_nm",
        ):
            _finite(getattr(self, name), name)
        if (
            not 0 <= self.initial_soc <= 1
            or not 0 < self.maximum_driver_request_nm <= 1000
            or not 0 <= self.maximum_friction_brake_nm <= 100
            or not 0 <= self.maximum_regen_request_nm <= 500
        ):
            raise ValueError("scenario energy/demand is outside the synthetic domain")
        if self.initial_state.u_mps < 0 or any(
            w < 0 for w in self.initial_state.wheel_speeds_rad_s
        ):
            raise ValueError("reverse is outside the powered scenario domain")
        for name in (
            "duration_us",
            "plant_step_us",
            "controller_period_us",
            "sensor_period_us",
            "logging_period_us",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError("clocks must be positive integer microseconds")
        if self.duration_us > 4_000_000 or not 100 <= self.plant_step_us <= 2000:
            raise ValueError(
                "scenario supports at most four seconds and 100–2000 us plant steps"
            )
        if any(
            getattr(self, n) % self.plant_step_us
            for n in (
                "duration_us",
                "controller_period_us",
                "sensor_period_us",
                "logging_period_us",
            )
        ):
            raise ValueError("scenario clocks must be exact plant-step multiples")
        if self.controller_period_us % 1000 or self.sensor_period_us % 1000:
            raise ValueError(
                "controller and sensor periods must resolve whole milliseconds"
            )
        if (
            type(self.sensor_delay_us) is not int
            or self.sensor_delay_us < 0
            or self.sensor_delay_us % self.plant_step_us
        ):
            raise ValueError("sensor delay must be a nonnegative plant-step multiple")
        if (
            type(self.maximum_sensor_age_ms) is not int
            or not 0 <= self.maximum_sensor_age_ms <= 1000
        ):
            raise ValueError("sensor age policy must be integer milliseconds")
        count = self.duration_us // self.plant_step_us
        internal_limit = min(
            self.vehicle.integration_step_limit_s,
            self.actuation.actuator_time_constant_s / 4,
        )
        if internal_limit <= 0:
            raise ValueError(
                "internal integration limit underflows the supported domain"
            )
        ratio = (self.plant_step_us / 1e6) / internal_limit
        _finite(ratio, "integration subdivision count")
        subdivisions = ceil(ratio)
        if (
            count * subdivisions > 50_000
            or self.duration_us // self.controller_period_us > 4096
            or self.duration_us // self.logging_period_us > 2000
        ):
            raise ValueError(
                "scenario exceeds the plant/controller/logging work budget"
            )
        if (
            not isinstance(self.driver, tuple)
            or not 2 <= len(self.driver) <= 64
            or any(type(p) is not DriverPoint for p in self.driver)
        ):
            raise ValueError("driver requires 2–64 typed program points")
        if (
            self.driver[0].time_us != 0
            or self.driver[-1].time_us != self.duration_us
            or any(a.time_us >= b.time_us for a, b in zip(self.driver, self.driver[1:]))
        ):
            raise ValueError(
                "driver program must span the duration in strict time order"
            )
        for values in (
            self.dropped_sequences,
            self.duplicate_sequences,
            self.restart_times_us,
        ):
            if (
                not isinstance(values, tuple)
                or len(values) > 4096
                or any(type(v) is not int or v < 0 for v in values)
                or len(set(values)) != len(values)
            ):
                raise ValueError(
                    "injection indices must be distinct nonnegative integers"
                )
        if any(
            t >= self.duration_us or t % self.controller_period_us
            for t in self.restart_times_us
        ):
            raise ValueError("restart must occur at an interior controller boundary")
        if (
            not isinstance(self.extra_delays_us, tuple)
            or len(self.extra_delays_us) > 4096
        ):
            raise ValueError("extra delays must be a bounded tuple")
        for pair in self.extra_delays_us:
            if (
                not isinstance(pair, (tuple, list))
                or len(pair) != 2
                or any(type(v) is not int or v < 0 for v in pair)
                or pair[1] % self.plant_step_us
            ):
                raise ValueError(
                    "extra delays require sequence and whole plant-step delay"
                )
        if len({pair[0] for pair in self.extra_delays_us}) != len(self.extra_delays_us):
            raise ValueError("duplicate extra-delay sequence")
        if self.failed_rear_index is not None and (
            type(self.failed_rear_index) is not int
            or self.failed_rear_index not in (2, 3)
        ):
            raise ValueError("failed actuator must identify RL or RR")
        if (
            type(self.failure_time_us) is not int
            or self.failure_time_us < 0
            or self.failure_time_us % self.plant_step_us
        ):
            raise ValueError("actuator fault must occur on a plant boundary")

    @classmethod
    def from_dict(cls, value: Any) -> ClosedLoopScenario:
        if not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__):
            raise ValueError("scenario must contain exact versioned fields")
        value = dict(value)
        try:
            value["vehicle"] = PlanarVehicleConfig(**value["vehicle"])
            value["actuation"] = ActuationConfig(**value["actuation"])
            initial = dict(value["initial_state"])
            initial["wheel_speeds_rad_s"] = tuple(initial["wheel_speeds_rad_s"])
            value["initial_state"] = PlanarState(**initial)
            env = dict(value["environment"])
            road = dict(env["road"])
            road["patches"] = tuple(RectangularGripPatch(**p) for p in road["patches"])
            if road["valid_domain"] is not None:
                road["valid_domain"] = RoadDomain(**road["valid_domain"])
            env["road"] = PlanarRoad(**road)
            value["environment"] = PlanarEnvironment(**env)
            value["driver"] = tuple(DriverPoint(**p) for p in value["driver"])
            for key in ("dropped_sequences", "duplicate_sequences", "restart_times_us"):
                value[key] = tuple(value[key])
            value["extra_delays_us"] = tuple(tuple(p) for p in value["extra_delays_us"])
            return cls(**value)
        except (TypeError, KeyError, OverflowError) as error:
            raise ValueError("invalid closed-loop scenario") from error


def driver_at(scenario: ClosedLoopScenario, time_us: int) -> DriverPoint:
    for left, right in zip(scenario.driver, scenario.driver[1:]):
        if time_us <= right.time_us:
            if time_us == right.time_us:
                return right
            alpha = (time_us - left.time_us) / (right.time_us - left.time_us)
            return DriverPoint(
                time_us,
                accelerator_fraction=left.accelerator_fraction
                + alpha * (right.accelerator_fraction - left.accelerator_fraction),
                brake_fraction=left.brake_fraction
                + alpha * (right.brake_fraction - left.brake_fraction),
                steering_rad=left.steering_rad
                + alpha * (right.steering_rad - left.steering_rad),
                valid=left.valid,
                enabled=left.enabled,
            )
    return scenario.driver[-1]


def run_closed_loop(
    scenario: ClosedLoopScenario,
    backend: Any = None,
    *,
    cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if not isinstance(scenario, ClosedLoopScenario):
        raise TypeError("expected ClosedLoopScenario")
    if backend is None:
        if scenario.controller_backend_id != "python_reference":
            raise ValueError(
                "requested backend must be explicitly supplied; no Python fallback"
            )
        backend = PythonController(
            scenario.controller_period_us // 1000, scenario.maximum_sensor_age_ms
        )
    if backend.backend_id != scenario.controller_backend_id or backend.sequence != 0:
        raise ValueError(
            "backend identity mismatch or previously used controller state"
        )
    if (
        backend.config.period_ms * 1000 != scenario.controller_period_us
        or backend.config.allocator.max_input_age_ms != scenario.maximum_sensor_age_ms
    ):
        raise ValueError("backend clock/freshness policy mismatch")
    state = PoweredState(
        scenario.initial_state,
        ZERO,
        scenario.initial_soc * scenario.actuation.pack_capacity_j,
    )
    initial = state
    queued = []
    accepted = None
    last_sequence = -1
    epoch = 0
    sensor_sequence = 0
    events = []
    arrivals = []
    observations = []
    command = ZERO
    guarded = ZERO
    latest = None
    extra = dict(scenario.extra_delays_us)

    def availability(now):
        return (
            False,
            False,
            not (scenario.failed_rear_index == 2 and now >= scenario.failure_time_us),
            not (scenario.failed_rear_index == 3 and now >= scenario.failure_time_us),
        )

    nominal = min(
        scenario.actuation.motor_peak_torque_nm,
        scenario.actuation.torque_constant_nm_per_a
        * min(
            scenario.actuation.motor_current_limit_a,
            scenario.actuation.inverter_current_limit_a,
        ),
    )
    nominal *= scenario.actuation.gear_ratio * scenario.actuation.gear_efficiency
    count = scenario.duration_us // scenario.plant_step_us
    for tick in range(count + 1):
        if cancel is not None and cancel():
            raise RuntimeError("Closed-loop calculation cancelled")
        now = tick * scenario.plant_step_us
        driver = driver_at(scenario, now)
        requested_regen = (
            scenario.maximum_regen_request_nm * driver.brake_fraction
            if driver.accelerator_fraction <= 0.05
            else 0.0
        )
        driver_proxy_n = (
            driver.accelerator_fraction * scenario.maximum_driver_request_nm
            - 4 * scenario.maximum_friction_brake_nm * driver.brake_fraction
            - requested_regen
        ) / scenario.vehicle.wheel_radius_m
        available = availability(now)
        if tick < count:
            restart = now in scenario.restart_times_us
            if restart:
                epoch += 1
                accepted = None
                last_sequence = -1
            if now % scenario.sensor_period_us == 0:
                snapshot = {
                    "epoch": epoch,
                    "sequence": sensor_sequence,
                    "timestamp_us": now,
                    "driver": asdict(driver),
                    "u_mps": state.plant.u_mps,
                    "v_mps": state.plant.v_mps,
                    "yaw_rate_rad_s": state.plant.yaw_rate_rad_s,
                    "wheel_speeds_rad_s": state.plant.wheel_speeds_rad_s,
                    "available": available,
                    "sensor_model": "ideal_sampled_body_and_wheel_sensors_v1",
                }
                arrival = now + scenario.sensor_delay_us + extra.get(sensor_sequence, 0)
                if sensor_sequence not in scenario.dropped_sequences:
                    heapq.heappush(queued, (arrival, sensor_sequence, 0, snapshot))
                    if sensor_sequence in scenario.duplicate_sequences:
                        heapq.heappush(
                            queued,
                            (
                                arrival + scenario.plant_step_us,
                                sensor_sequence,
                                1,
                                snapshot,
                            ),
                        )
                sensor_sequence += 1
            while queued and queued[0][0] <= now:
                arrival, sequence, _, snapshot = heapq.heappop(queued)
                reason = (
                    "wrong_epoch"
                    if snapshot["epoch"] != epoch
                    else "out_of_order_or_duplicate"
                    if sequence <= last_sequence
                    else "future_timestamp"
                    if snapshot["timestamp_us"] > now
                    else None
                )
                if reason is None:
                    accepted = snapshot
                    last_sequence = sequence
                arrivals.append(
                    {
                        "arrival_us": arrival,
                        "source_us": snapshot["timestamp_us"],
                        "sequence": sequence,
                        "epoch": snapshot["epoch"],
                        "accepted": reason is None,
                        "reason": reason,
                    }
                )
            if now % scenario.controller_period_us == 0:
                measured = accepted
                measured_driver = (
                    DriverPoint(**measured["driver"])
                    if measured
                    else DriverPoint(0, valid=False, enabled=False)
                )
                limits = [0.0, 0.0, nominal, nominal]
                estimated_slips = [0.0] * 4
                if measured:
                    for i, (_, y) in enumerate(scenario.vehicle.wheel_positions_m):
                        local = measured["u_mps"] - measured["yaw_rate_rad_s"] * y
                        estimated_slips[i] = (
                            scenario.vehicle.wheel_radius_m
                            * measured["wheel_speeds_rad_s"][i]
                            - local
                        ) / max(
                            abs(local), scenario.vehicle.low_speed_regularization_mps
                        )
                        if i >= 2 and scenario.strategy == "traction_limited":
                            limits[i] /= 1 + 20 * max(0.0, estimated_slips[i] - 0.1)
                request = (
                    measured_driver.accelerator_fraction
                    * scenario.maximum_driver_request_nm
                )
                braking_request = (
                    measured_driver.brake_fraction > 0
                    and measured_driver.accelerator_fraction <= 0.05
                )
                raw_regen = (
                    -scenario.maximum_regen_request_nm * measured_driver.brake_fraction
                    if braking_request
                    else 0.0
                )
                raw_regen_candidate = (0.0, 0.0, raw_regen / 2, raw_regen / 2)
                sample = backend.sample(
                    now // 1000,
                    measured["timestamp_us"] // 1000 if measured else 0,
                    request,
                    tuple(limits),
                    tuple(measured["available"]) if measured else (False,) * 4,
                    measured_driver.accelerator_fraction,
                    measured_driver.brake_fraction > 0,
                    measured_driver.valid and measured is not None,
                    measured_driver.enabled,
                    restart,
                )
                latest = backend.step(sample)
                response_reset = not latest["command_allowed"] and any(
                    state.actuator_memory_nm
                )
                if not latest["command_allowed"]:
                    # The supervisor's inhibit bypasses ordinary response lag.
                    # This memory is an abstract torque-response state, with no
                    # stored magnetic energy; wheel/pack states do not change.
                    state = replace(state, actuator_memory_nm=ZERO)
                guarded = tuple(latest["command_nm"])
                if latest["command_allowed"] and braking_request:
                    guarded = raw_regen_candidate
                feasible = constrain_actuation(
                    scenario.actuation,
                    guarded,
                    state.plant.wheel_speeds_rad_s,
                    state.pack_energy_j,
                    scenario.controller_period_us / 1e6,
                    available,
                )
                command = feasible.wheel_torques_nm
                events.append(
                    {
                        "time_us": now,
                        "snapshot": measured,
                        "estimated_slips": estimated_slips,
                        "requested_propulsive_nm": request,
                        "requested_regen_nm": raw_regen,
                        "raw_regen_candidate_nm": raw_regen_candidate,
                        "core": latest,
                        "actuator_response_reset": response_reset,
                        "guarded_request_nm": guarded,
                        "limited_command_nm": command,
                        "constraints": feasible.constraints,
                        "unmet_command_torque_nm": request
                        - sum(max(0.0, v) for v in command),
                        "unmet_regen_torque_nm": max(
                            0.0,
                            -raw_regen + sum(min(0.0, v) for v in command),
                        ),
                    }
                )
        if now % scenario.logging_period_us == 0 or tick == count:
            _, physical, electrical = evaluate_powered(
                scenario.vehicle,
                scenario.actuation,
                state,
                command,
                (driver.steering_rad, driver.steering_rad, 0.0, 0.0),
                (scenario.maximum_friction_brake_nm * driver.brake_fraction,) * 4,
                available,
                scenario.plant_step_us / 1e6,
                scenario.environment,
                driver_proxy_n=driver_proxy_n,
            )
            observations.append(
                {
                    "time_us": now,
                    "driver": asdict(driver),
                    "state": asdict(state),
                    "raw_driver_contact_force_proxy_n": driver_proxy_n,
                    "guarded_request_nm": guarded,
                    "limited_command_nm": command,
                    "actual_actuator": asdict(electrical),
                    "plant": asdict(physical),
                    "soc": state.pack_energy_j / scenario.actuation.pack_capacity_j,
                }
            )
        if tick < count:
            state = advance_powered(
                scenario.vehicle,
                scenario.actuation,
                state,
                command,
                (driver.steering_rad, driver.steering_rad, 0.0, 0.0),
                (scenario.maximum_friction_brake_nm * driver.brake_fraction,) * 4,
                available,
                scenario.plant_step_us / 1e6,
                scenario.environment,
                driver_proxy_n=driver_proxy_n,
            )
    result = {
        "status": "completed",
        "controller_calls": backend.sequence,
        "plant_ticks": count,
        "controller_events": events,
        "sensor_arrivals": arrivals,
        "observations": observations,
        "energy_balance_residual_j": energy_residual_j(
            scenario.vehicle, initial, state
        ),
        "pack_draw_j": initial.pack_energy_j - state.pack_energy_j,
        "final_state": asdict(state),
        "pending_sensor_messages": len(queued),
    }
    inputs = asdict(scenario)
    runtime = _runtime_identity()
    build = build_identity()
    if build is not None:
        runtime["source"]["source_sha256"] = build.get("source_sha256")
    record = {
        "schema": SCHEMA,
        "scenario": inputs,
        "configuration_sha256": _content_id(inputs),
        "runtime": runtime,
        "plant_source": plant_source_identity(),
        "solver": {
            "family": "held-command augmented RK4",
            "version": 2,
            "internal_step_policy": "minimum of planar tire-stiffness limit and actuator time constant / 4",
            "diagnostic_quadrature": "same RK stages; physical driver/steering/brake input held for each base plant tick",
            "brake_stops": "reject/subdivide negative brake-stop trials; static stop at <=1e-9 rad/s with separate residual kinetic-energy dissipation",
        },
        "frames": {
            "body": "x forward, y left, yaw counterclockwise",
            "world": "fixed ground X/Y",
            "wheel_order": ["FL", "FR", "RL", "RR"],
        },
        "controller_source": getattr(backend, "identity", None)
        or controller_source_identity(),
        "clock_policy": "integer us; reset, sample, arrival, controller, observe, held-command augmented RK4",
        "units": {
            "position": "m",
            "velocity": "m/s",
            "angle": "rad",
            "yaw_rate": "rad/s",
            "wheel_speed": "rad/s",
            "torque": "N*m",
            "force": "N",
            "impulse": "N*s",
            "energy": "J",
            "power": "W",
            "current": "A",
            "voltage": "V",
            "time": "us",
        },
        "assumptions": [
            "Synthetic independent-rear RWD; two rear actuators are a study assumption, not the confirmed car topology.",
            "Ideal sampled body/wheel sensors; controller receives no plant object, true grip or tire forces.",
            "Constant-voltage pack, static loads, regularized synthetic tire law; no measured car/thermal calibration.",
            "Driver directly operates prescribed steering/friction brakes; propulsion supervision does not erase friction braking.",
            "Reflected motor/drive inertia is included once in the declared wheel inertia.",
            "Common signed-power scaling is feasible and conservative; no optimal allocation or real-time deadline claim.",
        ],
        "result": result,
    }
    record["run_id"] = _content_id(record)
    return record


def replay_closed_loop(record: Any, backend: Any = None) -> dict:
    if (
        isinstance(record, dict)
        and record.get("schema") == "lapsim.closed-loop.record.v1"
    ):
        raise ValueError(
            "Development record v1 uses solver policy 1; replay with its recorded source. Current brake-stop solver is policy 2."
        )
    if (
        isinstance(record, dict)
        and record.get("schema") == "lapsim.closed-loop.record.v2"
    ):
        raise ValueError(
            "Development record v2 requires its recorded source; v3 adds explicit rejected-regeneration and verified native-build provenance."
        )
    if (
        not isinstance(record, dict)
        or record.get("schema") != SCHEMA
        or record.get("run_id")
        != _content_id({k: v for k, v in record.items() if k != "run_id"})
    ):
        raise ValueError("closed-loop record identity mismatch")
    scenario = ClosedLoopScenario.from_dict(record.get("scenario"))
    if _content_id(asdict(scenario)) != record.get("configuration_sha256"):
        raise ValueError("configuration identity mismatch")
    actual = run_closed_loop(scenario, backend)
    for key in (
        "binary_sha256",
        "native_build",
        "firmware_build_id",
        "firmware_elf_sha256",
    ):
        if record.get("controller_source", {}).get(key) != actual[
            "controller_source"
        ].get(key):
            raise ValueError("recorded backend artifact identity mismatch: " + key)

    def compare(a, b, path):
        if type(b) in (int, float):
            if type(a) not in (int, float) or not isclose(
                a, b, rel_tol=1e-8, abs_tol=1e-8
            ):
                raise ValueError("replay numeric mismatch at " + path)
        elif isinstance(b, dict):
            if not isinstance(a, dict) or set(a) != set(b):
                raise ValueError("replay fields mismatch at " + path)
            for k in b:
                compare(a[k], b[k], path + "." + k)
        elif isinstance(b, (tuple, list)):
            if not isinstance(a, (tuple, list)) or len(a) != len(b):
                raise ValueError("replay sequence mismatch at " + path)
            for i, (x, y) in enumerate(zip(a, b, strict=True)):
                compare(x, y, path + f"[{i}]")
        elif type(a) is not type(b) or a != b:
            raise ValueError("replay value mismatch at " + path)

    if set(record) != set(actual):
        raise ValueError("closed-loop record fields mismatch")
    for key in ("result", "units", "clock_policy", "assumptions", "solver", "frames"):
        compare(record[key], actual[key], key)
    return {
        "model_agreement": True,
        "backend_id": scenario.controller_backend_id,
        "run_id": record["run_id"],
        "relative_tolerance": 1e-8,
        "absolute_tolerance_si": 1e-8,
        "plant_source_agreement": record["plant_source"] == actual["plant_source"],
        "controller_source_agreement": record["controller_source"]
        == actual["controller_source"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--backend", choices=("python_reference", "native_c", "qemu_stm32f405")
    )
    parser.add_argument("--native-library", type=Path)
    parser.add_argument("--qemu", type=Path)
    parser.add_argument("--firmware", type=Path)
    args = parser.parse_args()
    if args.scenario and args.replay:
        parser.error("choose scenario or replay")
    backend = None
    try:
        source = args.scenario or args.replay
        if (
            args.output
            and source
            and (
                args.output.resolve() == source.resolve()
                or (args.output.exists() and args.output.samefile(source))
            )
        ):
            raise ValueError("output must not overwrite input")
        if source and source.stat().st_size > 20_000_000:
            raise ValueError("closed-loop input exceeds the size limit")
        value = decode_json(source.read_bytes()) if source else None
        if args.replay:
            if not isinstance(value, dict):
                raise ValueError("closed-loop replay requires a record object")
            scenario = ClosedLoopScenario.from_dict(value.get("scenario"))
        else:
            scenario = (
                ClosedLoopScenario.from_dict(value)
                if value is not None
                else ClosedLoopScenario()
            )
        if args.backend:
            if args.replay and args.backend != scenario.controller_backend_id:
                raise ValueError("replay must execute its recorded backend")
            scenario = replace(scenario, controller_backend_id=args.backend)
        if scenario.controller_backend_id == "native_c":
            if args.native_library is None:
                raise ValueError(
                    "native execution requires --native-library; no fallback"
                )
            from .native_controller import NativeController

            backend = NativeController(
                args.native_library,
                scenario.controller_period_us // 1000,
                scenario.maximum_sensor_age_ms,
            )
        elif args.native_library:
            raise ValueError(
                "--native-library requires the explicitly selected native_c backend"
            )
        if scenario.controller_backend_id == "qemu_stm32f405":
            if args.qemu is None or args.firmware is None:
                raise ValueError(
                    "QEMU execution requires --qemu and --firmware; no fallback"
                )
            from .stm32_backend import QemuController

            backend = QemuController(
                args.qemu,
                args.firmware,
                scenario.controller_period_us // 1000,
                scenario.maximum_sensor_age_ms,
            )
        elif args.qemu or args.firmware:
            raise ValueError(
                "emulator paths require the explicitly selected qemu_stm32f405 backend"
            )
        result = (
            replay_closed_loop(value, backend)
            if args.replay
            else run_closed_loop(scenario, backend)
        )
        encoded = _canonical_json(result) + "\n"
        if args.output:
            args.output.write_text(encoded, encoding="utf-8")
        else:
            print(encoded)
    except (ValueError, OSError, TypeError) as error:
        parser.exit(2, "closed loop: " + str(error) + "\n")
    finally:
        if backend is not None and hasattr(backend, "close"):
            backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
