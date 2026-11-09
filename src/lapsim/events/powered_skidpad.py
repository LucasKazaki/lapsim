"""Restartable synthetic powered skidpad experiment with integrated-pose gates.

This development backend reuses the ordinary four-wheel plant and its four
implemented torque allocators. It is not the portable AWD7/native worker and
does not supply admission, authenticated evidence or a qualified event score.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from math import atan2, isfinite
from pathlib import Path
import platform
import sys

from lapsim.dynamics.conditions import PlanarEnvironment
from lapsim.dynamics.planar import PlanarControls, PlanarState, evaluate_planar_dynamics
from lapsim.dynamics.powered_planar import (
    PoweredState, advance_powered, energy_residual_j, evaluate_powered,
)
from lapsim.events.skidpad_gates import GatePose, OrderedSkidpadGates
from lapsim.events.skidpad_sequence import SkidpadSequenceCourse
from lapsim.experiments.tournament_rollout import (
    AVAILABLE, PHILOSOPHIES, ZERO, Controller, allocate, fixture,
)
from lapsim.optimization.pose_driver import (
    _assumed_footprint_slack, _controller, _project_local,
)

SCHEMA = "lapsim.powered-skidpad-checkpoint.v1"
DT_S = .01
DRIVER_STRIDE = 5
MAX_TICKS = 10_000
MAX_WORK = 200_000
MAX_CHECKPOINT_BYTES = 32 * 1024 * 1024
TERMINAL = {"completed", "invalid", "model_error", "budget_exhausted", "cancelled"}


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value):
    return sha256(_raw(value)).hexdigest()


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in [{low}, {high}]")
    return value


def _finite(value, name):
    if type(value) not in (float, int) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


def _object(value, keys, name):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError(f"Unexpected {name} fields")
    return value


def _numbers(value, name):
    if type(value) is not list or len(value) != 4:
        raise ValueError(f"{name} requires four numbers")
    return tuple(_finite(v, name) for v in value)


def _hash(value):
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Expected exact state hash")


_VECTORS = ("requested_nm", "proposed_nm", "limited_nm", "achieved_at_start_nm",
            "steering_rad", "friction_nm")


def _attempt(value, *, accepted):
    if type(value) is not dict or type(value.get("stage")) is not str:
        raise ValueError("Expected a typed raw attempt")
    stage = value["stage"]
    if stage not in ("started", "allocated", "accepted") or (accepted and stage != "accepted"):
        raise ValueError("Invalid raw attempt stage")
    keys = {"tick", "before_state_sha256", "stage"}
    if stage in ("allocated", "accepted"):
        keys.update((*_VECTORS, "brake_shortfall_nm", "raw_regen_request_nm", "held_command",
                     "integral_before", "integral_after", "projection_before_m", "projection_after_m"))
    if stage == "accepted":
        keys.add("after_state_sha256")
    _object(value, keys, "raw attempt")
    _integer(value["tick"], "raw attempt tick", 0, MAX_TICKS)
    _hash(value["before_state_sha256"])
    if stage == "accepted":
        _hash(value["after_state_sha256"])
    if stage in ("allocated", "accepted"):
        _ordinary_command(value["held_command"])
        for key in _VECTORS:
            _numbers(value[key], key)
        for key in ("integral_before", "integral_after", "projection_before_m", "projection_after_m"):
            _finite(value[key], key)
        if any(not -1 <= value[key] <= 1 for key in ("integral_before", "integral_after")):
            raise ValueError("Raw integral memory out of range")
        for key in ("brake_shortfall_nm", "raw_regen_request_nm"):
            if _finite(value[key], key) < 0:
                raise ValueError("Negative raw brake request/shortfall")
        if any(v < 0 for v in value["friction_nm"]):
            raise ValueError("Negative raw friction command")
        if (value["requested_nm"] != value["held_command"]["drive_torques_nm"]
                or value["steering_rad"] != value["held_command"]["steering_angles_rad"]):
            raise ValueError("Raw requested command conflicts with held ordinary command")


def _state(raw):
    _object(raw, (f.name for f in fields(PoweredState)), "powered state")
    p = _object(raw["plant"], (f.name for f in fields(PlanarState)), "plant state")
    plant = PlanarState(**{
        k: _numbers(v, k) if k == "wheel_speeds_rad_s" else _finite(v, k)
        for k, v in p.items()
    })
    values = {k: v for k, v in raw.items() if k != "plant"}
    for k, v in values.items():
        if k == "actuator_memory_nm":
            values[k] = _numbers(v, k)
        elif k in ("integration_substeps", "integration_trials", "wheel_stop_events"):
            _integer(v, k, 0, MAX_WORK)
        else:
            _finite(v, k)
    return PoweredState(plant=plant, **values)


def _command(raw):
    if raw is None:
        return None
    _object(raw, (f.name for f in fields(PlanarControls)), "held command")
    result = {}
    for k, v in raw.items():
        if k in ("normal_loads_n", "wheel_radii_m"):
            result[k] = None if v is None else _numbers(v, k)
        elif k in ("steering_angles_rad", "drive_torques_nm", "brake_torques_nm"):
            result[k] = _numbers(v, k)
        else:
            result[k] = _finite(v, k)
    return PlanarControls(**result)


def _ordinary_command(raw):
    command = _command(raw)
    if command is None:
        raise ValueError("Missing held ordinary driver command")
    _, _, driver = fixture()
    s, d, b = command.steering_angles_rad, command.drive_torques_nm, command.brake_torques_nm
    if (s[0] != s[1] or s[2:] != (0., 0.) or abs(s[0]) > driver.maximum_steering_rad
            or d[:2] != (0., 0.) or d[2] != d[3] or not 0 <= d[2] <= driver.maximum_rear_drive_torque_nm
            or len(set(b)) != 1 or not 0 <= b[0] <= driver.maximum_wheel_brake_torque_nm
            or command.normal_loads_n is not None or command.wheel_radii_m is not None
            or command.external_force_x_n != 0 or command.external_force_y_n != 0
            or command.external_yaw_moment_nm != 0):
        raise ValueError("Held command violates fixed ordinary driver shape")
    return command


@dataclass(frozen=True)
class PoweredSkidpadRequest:
    course: SkidpadSequenceCourse
    controller: Controller = Controller()
    maximum_ticks: int = MAX_TICKS
    maximum_work: int = MAX_WORK

    def __post_init__(self):
        if type(self.course) is not SkidpadSequenceCourse:
            raise ValueError("An exact ordered skidpad course is required")
        if type(self.controller) is not Controller or self.controller.philosophy not in PHILOSOPHIES:
            raise ValueError("Only the four implemented ordinary controllers are supported")
        _integer(self.maximum_ticks, "maximum_ticks", 1, MAX_TICKS)
        _integer(self.maximum_work, "maximum_work", 1, MAX_WORK)
        # These bounds are software/measurement limits, not rulebook dimensions.
        if not .1 <= self.course.entry_length_m <= 100 or not .1 <= self.course.exit_length_m <= 100:
            raise ValueError("Powered event entry/exit lengths must be in [.1, 100] m")


@dataclass(frozen=True)
class _AllocationScenario:
    # Same explicit nominal scenario as the existing synthetic rollout fixture.
    regen_available: bool = True
    pack_voltage_v: float = 580.
    motor_temperature_c: float = 40.
    friction_fallback: bool = True


def _source():
    """Bounded raw Python source inventory; not loaded-code authentication."""
    root = Path(__file__).resolve().parents[2]
    sources = {}
    total = 0
    for package in ("lapsim", "vehicle_model"):
        paths = sorted((root / package).rglob("*.py"))
        for path in paths:
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
                raise ValueError("Aliased source cannot bind a development checkpoint")
            size = path.stat().st_size
            total += size
            if size > 2 * 1024 * 1024 or total > 20 * 1024 * 1024 or len(sources) >= 2000:
                raise ValueError("Development source inventory exceeds bounds")
            sources[path.relative_to(root).as_posix()] = sha256(path.read_bytes()).hexdigest()
    if not sources:
        raise ValueError("Development source inventory is unavailable")
    return {"scope": "RAW_PYTHON_DISK_BYTES_NOT_LOADED_NATIVE_OR_AUTHENTICATED_CLOSURE", "files": sources}


def _runtime():
    # An exact limited comparison only; this does NOT implement environment-v2.
    return {"python": sys.version, "implementation": sys.implementation.name,
            "cache_tag": sys.implementation.cache_tag, "system": platform.system(),
            "machine": platform.machine(), "byteorder": sys.byteorder,
            "float": list(sys.float_info),
            "scope": "LIMITED_DEVELOPMENT_COMPARISON_NOT_ENVIRONMENT_V2_OR_ADMISSION"}


def _binding(request):
    car, pack, driver = fixture()
    return {"request": {"course": request.course.to_dict(),
                         "controller": asdict(request.controller),
                         "maximum_ticks": request.maximum_ticks,
                         "maximum_work": request.maximum_work},
            "fixture": {"car": asdict(car), "pack": asdict(pack), "driver": asdict(driver),
                        "environment": asdict(PlanarEnvironment(drag_area_m2=.5)),
                        "allocation_scenario": asdict(_AllocationScenario()),
                        "plant_allocator_step_s": DT_S, "driver_stride": DRIVER_STRIDE,
                        "initial_soc": .7, "gate_half_width_m": 1.5},
            "source": _source(), "runtime": _runtime()}


def _initial(request):
    car, pack, driver = fixture()
    track = request.course.track
    return PoweredState(PlanarState(
        x_m=track.x_m[0], y_m=track.y_m[0], heading_rad=0.,
        u_mps=driver.initial_speed_mps,
        wheel_speeds_rad_s=(driver.initial_speed_mps / car.wheel_radius_m,) * 4,
    ), ZERO, .7 * pack.pack_capacity_j)


def _pose(tick, state):
    return GatePose(tick, tick * DT_S, state.plant.x_m, state.plant.y_m,
                    state.pack_energy_j, _digest(asdict(state)))


def _endpoint_limit(request, state, previous_station_m, command):
    """Pure accepted-endpoint screen; no driver/allocator clock or state update."""
    car, _, driver = fixture()
    track = request.course.track
    p = state.plant
    projection = _project_local(track, p.x_m, p.y_m, previous_station_m,
                                driver.local_projection_window_m)
    slack = _assumed_footprint_slack(track, car, driver, p, projection.station_m)
    physical = evaluate_planar_dynamics(car, p, PlanarControls(
        steering_angles_rad=ZERO if command is None else command.steering_angles_rad),
        environment=PlanarEnvironment(drag_area_m2=.5))
    if (slack < 0 or abs(atan2(p.v_mps, max(.5, p.u_mps))) > .5
            or abs(p.yaw_rate_rad_s) > 2
            or max(abs(w.slip_ratio) for w in physical.wheels) > 1):
        return "development endpoint corridor/sideslip/yaw/wheel slip limit"
    return None


class PoweredSkidpadSession:
    """Mutable development session; checkpoint bytes need an external hash pin."""

    def __init__(self, request):
        self.request = request
        self.binding = _binding(request)
        self.initial_state = self.state = _initial(request)
        self.tick = self.attempted_steps = 0
        self.driver_updates = self.allocator_updates = 0
        self.command = None
        self.integral = self.previous_station_m = 0.
        self.gross_pack_draw_j = self.recovered_pack_j = 0.
        self.status = "running"
        self.failure_reason = None
        self.rejected_attempt = None
        self.records = []
        self.crossing_states = []
        self.gates = OrderedSkidpadGates(exit_length_m=request.course.exit_length_m)
        self.gates.observe(_pose(0, self.state))

    def result(self):
        timed_average = None
        if self.status == "completed":
            # Explicit sequence: entry, R untimed, R timed, L untimed, L timed, exit.
            times = [c["time_s"] for c in self.gates.crossings]
            timed_average = ((times[2] - times[1]) + (times[4] - times[3])) / 2
        car, _, _ = fixture()
        return {"schema": "lapsim.powered-skidpad-result.v1", "status": self.status,
                "failure_reason": self.failure_reason, "tick": self.tick,
                "attempted_steps": self.attempted_steps,
                "time_s": self.tick * DT_S, "controller": asdict(self.request.controller),
                "course_sha256": self.request.course.course_sha256,
                "binding_sha256": _digest(self.binding), "gates": self.gates.to_dict(),
                "timed_average_s": timed_average, "corrected_time_s": None,
                "official_points": None, "qualified_tournament_result": False,
                "qualification_or_execution_authority": False,
                "backend": "SYNTHETIC_POWERED_RWD_FOUR_ORDINARY_ALLOCATORS",
                "timing_scope": "NOMINAL_CG_GATES_ACCEPTED_POSE_CHORD_INTERPOLATION",
                "net_pack_draw_j": self.initial_state.pack_energy_j - self.state.pack_energy_j,
                "gross_pack_draw_j": self.gross_pack_draw_j,
                "recovered_pack_j": self.recovered_pack_j,
                "pack_energy_accounting_scope": "SUM_OF_SIGNED_10MS_NET_PACK_DELTAS_NOT_CONTINUOUS_GROSS_INTEGRATION",
                "energy_residual_j": energy_residual_j(car, self.initial_state, self.state),
                "driver_updates": self.driver_updates, "allocator_updates": self.allocator_updates,
                "initial_state": asdict(self.initial_state), "final_state": asdict(self.state),
                "crossing_states": self.crossing_states, "raw_steps": self.records,
                "rejected_attempt": self.rejected_attempt}


def fresh_session(request):
    if type(request) is not PoweredSkidpadRequest:
        raise ValueError("A validated powered skidpad request is required")
    return PoweredSkidpadSession(request)


def advance_session(session, steps, *, cancelled=None):
    """Advance at most steps accepted intervals, preserving total event budgets.

    Cancellation is cooperative between 10 ms model intervals; it is not an OS
    watchdog or the original owned-process cleanup proof. Terminal sessions may
    be inspected but cannot be automatically retried or resumed into execution.
    """
    if type(session) is not PoweredSkidpadSession:
        raise ValueError("Expected a powered skidpad session")
    _integer(steps, "steps", 1, MAX_TICKS)
    if session.status != "running":
        raise ValueError("Cannot execute a terminal event")
    if cancelled is not None and not callable(cancelled):
        raise ValueError("Cancellation must be callable")
    if session.binding != _binding(session.request):
        raise ValueError("Session binding changed before execution")
    car, pack, driver = fixture()
    environment = PlanarEnvironment(drag_area_m2=.5)
    track = session.request.course.track
    for _ in range(steps):
        if session.attempted_steps >= session.request.maximum_ticks:
            session.status = "budget_exhausted"
            break
        if cancelled is not None:
            try:
                cancel = cancelled()
                if type(cancel) is not bool:
                    raise ValueError("Cancellation callback must return bool")
            except Exception as error:
                session.status, session.failure_reason = "model_error", f"cancellation: {error}"[:4096]
                raise
            if cancel:
                session.status = "cancelled"
                break
        before = session.state
        session.attempted_steps += 1
        attempt = {"tick": session.tick, "before_state_sha256": _digest(asdict(before)),
                   "stage": "started"}
        try:
            p = before.plant
            projection = _project_local(track, p.x_m, p.y_m, session.previous_station_m,
                                        driver.local_projection_window_m)
            slack = _assumed_footprint_slack(track, car, driver, p, projection.station_m)
            # Real model limits inherited from the ordinary rollout, not official DNF rules.
            if slack < 0 or abs(atan2(p.v_mps, max(.5, p.u_mps))) > .5 or abs(p.yaw_rate_rad_s) > 2:
                raise ValueError("development corridor/sideslip/yaw limit")
            if session.tick % DRIVER_STRIDE == 0:
                session.command, _ = _controller(track, car, PlanarEnvironment(), driver, p, projection, slack)
                session.driver_updates += 1
            command = session.command
            if command is None:
                raise ValueError("Held driver command is unavailable")
            physical = evaluate_planar_dynamics(car, p,
                PlanarControls(steering_angles_rad=command.steering_angles_rad), environment=environment)
            requested, proposed, limited, brakes, integral, shortfall, raw_regen = allocate(
                session.request.controller, before, physical, command.steering_angles_rad[0],
                command.drive_torques_nm[2], command.brake_torques_nm[0], session.integral,
                car, pack, _AllocationScenario(), dt=DT_S)
            session.allocator_updates += 1
            _, _, achieved = evaluate_powered(car, pack, before, limited.wheel_torques_nm,
                command.steering_angles_rad, brakes, AVAILABLE, DT_S, environment)
            attempt.update(requested_nm=list(requested), proposed_nm=list(proposed),
                           limited_nm=list(limited.wheel_torques_nm),
                           achieved_at_start_nm=list(achieved.wheel_torques_nm),
                           steering_rad=list(command.steering_angles_rad),
                           friction_nm=list(brakes), brake_shortfall_nm=shortfall,
                           raw_regen_request_nm=raw_regen, stage="allocated",
                           held_command=asdict(command), integral_before=session.integral,
                           integral_after=integral, projection_before_m=session.previous_station_m,
                           projection_after_m=projection.station_m)
            if shortfall > 1e-6 or max(abs(w.slip_ratio) for w in physical.wheels) > 1:
                raise ValueError("development brake shortfall/wheel slip limit")
            after = advance_powered(car, pack, before, limited.wheel_torques_nm,
                command.steering_angles_rad, brakes, AVAILABLE, DT_S, environment,
                maximum_work=session.request.maximum_work)
            # Commit the actual returned state even if a subsequent validity screen fails.
            session.state = after
            session.tick += 1
            session.integral = integral
            session.previous_station_m = projection.station_m
            delta = before.pack_energy_j - after.pack_energy_j
            session.gross_pack_draw_j += max(0., delta)
            session.recovered_pack_j += max(0., -delta)
            attempt.update(after_state_sha256=_digest(asdict(after)), tick=session.tick, stage="accepted")
            session.records.append(attempt)
            count = len(session.gates.crossings)
            session.gates.observe(_pose(session.tick, after))
            for index in range(count, len(session.gates.crossings)):
                session.crossing_states.append({"crossing_index": index,
                    "before_state": asdict(before), "after_state": asdict(after)})
            residual = energy_residual_j(car, session.initial_state, after)
            endpoint_failure = _endpoint_limit(session.request, after,
                                               session.previous_station_m, session.command)
            if not 0 <= after.pack_energy_j <= pack.pack_capacity_j or abs(residual) > .5:
                session.status, session.failure_reason = "invalid", "pack bounds/energy residual"
            elif endpoint_failure:
                session.status, session.failure_reason = "invalid", endpoint_failure
            elif session.gates.failure_reason:
                session.status, session.failure_reason = "invalid", session.gates.failure_reason
            elif session.gates.completed:
                session.status = "completed"
            elif session.tick == session.request.maximum_ticks:
                session.status = "budget_exhausted"
            if session.status != "running":
                break
        except KeyboardInterrupt:
            session.status, session.failure_reason = "cancelled", "Interrupted during numerical attempt"
            session.rejected_attempt = attempt
            raise
        except Exception as error:
            session.status, session.failure_reason = "model_error", (str(error) or type(error).__name__)[:4096]
            session.rejected_attempt = attempt
            if not isinstance(error, (ValueError, ArithmeticError)):
                raise
            break
    return session


def _payload(session):
    return {"schema": SCHEMA, "binding": session.binding,
            "tick": session.tick, "attempted_steps": session.attempted_steps,
            "driver_updates": session.driver_updates, "allocator_updates": session.allocator_updates,
            "state": asdict(session.state), "initial_state": asdict(session.initial_state),
            "command": None if session.command is None else asdict(session.command),
            "integral": session.integral, "previous_station_m": session.previous_station_m,
            "gross_pack_draw_j": session.gross_pack_draw_j, "recovered_pack_j": session.recovered_pack_j,
            "status": session.status, "failure_reason": session.failure_reason,
            "rejected_attempt": session.rejected_attempt,
            "gate_trace": [asdict(p) for p in session.gates.trace],
            "crossing_states": session.crossing_states, "records": session.records}


def checkpoint(session):
    raw = _raw(_payload(session))
    if len(raw) > MAX_CHECKPOINT_BYTES:
        raise ValueError("Development checkpoint exceeds byte bound")
    return raw


def _pairs(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError("Duplicate checkpoint field")
        result[k] = v
    return result


def resume(raw, *, expected_sha256, request):
    """Verify externally pinned bytes and exact inputs; reconstruct without stepping.

    Hash equality is integrity/comparability only, not external authentication.
    This API deliberately does not register an original native worker or Start.
    """
    if type(raw) is not bytes or len(raw) > MAX_CHECKPOINT_BYTES:
        raise ValueError("Expected bounded checkpoint bytes")
    if type(expected_sha256) is not str or sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Checkpoint digest mismatch")
    try:
        saved = json.loads(raw, object_pairs_hook=_pairs,
                           parse_float=lambda value: _finite(float(value), "checkpoint float"),
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeError, RecursionError, json.JSONDecodeError) as error:
        raise ValueError("Malformed checkpoint") from error
    session = fresh_session(request)
    _object(saved, _payload(session), "checkpoint")
    if saved["schema"] != SCHEMA or _raw(saved["binding"]) != _raw(session.binding):
        raise ValueError("Checkpoint schema/binding mismatch")
    tick = _integer(saved["tick"], "tick", 0, request.maximum_ticks)
    attempted = _integer(saved["attempted_steps"], "attempted_steps", tick, min(tick + 1, request.maximum_ticks))
    status = saved["status"]
    if type(status) is not str or status not in {"running", *TERMINAL}:
        raise ValueError("Unsupported checkpoint status")
    state = _state(saved["state"])
    if _state(saved["initial_state"]) != session.initial_state:
        raise ValueError("Initial state mismatch")
    if state.integration_trials + state.wheel_stop_events > request.maximum_work:
        raise ValueError("Checkpoint exceeds cumulative numerical work")
    if state.integration_substeps > state.integration_trials:
        raise ValueError("Checkpoint numerical counters mismatch")
    session.state, session.tick, session.attempted_steps = state, tick, attempted
    session.command = None if saved["command"] is None else _ordinary_command(saved["command"])
    for name in ("driver_updates", "allocator_updates"):
        setattr(session, name, _integer(saved[name], name, 0, attempted))
    for name in ("integral", "previous_station_m", "gross_pack_draw_j", "recovered_pack_j"):
        setattr(session, name, _finite(saved[name], name))
    if not -1 <= session.integral <= 1 or not 0 <= session.previous_station_m <= request.course.track.length_m:
        raise ValueError("Controller/projection memory out of range")
    if session.gross_pack_draw_j < 0 or session.recovered_pack_j < 0:
        raise ValueError("Negative cumulative energy accounting")
    _, pack, _ = fixture()
    if not 0 <= state.pack_energy_j <= pack.pack_capacity_j:
        raise ValueError("Checkpoint pack bounds")
    if abs((session.gross_pack_draw_j - session.recovered_pack_j) -
           (session.initial_state.pack_energy_j - state.pack_energy_j)) > 1e-6:
        raise ValueError("Checkpoint energy accounting mismatch")
    if type(saved["gate_trace"]) is not list or len(saved["gate_trace"]) != tick + 1:
        raise ValueError("Checkpoint pose trace length mismatch")
    trace = []
    for row in saved["gate_trace"]:
        _object(row, (f.name for f in fields(GatePose)), "gate pose")
        trace.append(GatePose(**row))
    if trace[0] != _pose(0, session.initial_state) or trace[-1] != _pose(tick, state):
        raise ValueError("Checkpoint pose/state mismatch")
    if any(p.time_s != p.tick * DT_S for p in trace):
        raise ValueError("Checkpoint pose clock mismatch")
    draw = sum(max(0., a.pack_energy_j-b.pack_energy_j) for a, b in zip(trace, trace[1:]))
    recovered = sum(max(0., b.pack_energy_j-a.pack_energy_j) for a, b in zip(trace, trace[1:]))
    if draw != session.gross_pack_draw_j or recovered != session.recovered_pack_j:
        raise ValueError("Checkpoint interval energy accounting mismatch")
    session.gates = OrderedSkidpadGates.from_trace(trace, exit_length_m=request.course.exit_length_m)
    session.status, session.failure_reason = status, saved["failure_reason"]
    session.rejected_attempt = saved["rejected_attempt"]
    if session.failure_reason is not None and (type(session.failure_reason) is not str
                                               or not 1 <= len(session.failure_reason) <= 4096):
        raise ValueError("Invalid failure reason")
    records = saved["records"]
    if type(records) is not list or len(records) != tick:
        raise ValueError("Checkpoint raw record count mismatch")
    for i, row in enumerate(records, 1):
        _attempt(row, accepted=True)
        if type(row) is not dict or row.get("tick") != i or type(row.get("tick")) is not int:
            raise ValueError("Checkpoint raw record clock mismatch")
        if row.get("before_state_sha256") != trace[i-1].state_sha256 or row.get("after_state_sha256") != trace[i].state_sha256:
            raise ValueError("Checkpoint raw record/pose state mismatch")
        before_memory = (0., 0.) if i == 1 else (
            records[i-2]["integral_after"], records[i-2]["projection_after_m"])
        if (row["integral_before"], row["projection_before_m"]) != before_memory:
            raise ValueError("Checkpoint raw controller memory lineage mismatch")
        if any(not 0 <= row[k] <= request.course.track.length_m for k in ("projection_before_m", "projection_after_m")):
            raise ValueError("Checkpoint raw projection out of range")
        if (i-1) % DRIVER_STRIDE != 0 and _raw(row["held_command"]) != _raw(records[i-2]["held_command"]):
            raise ValueError("Checkpoint held command changed outside driver clock")
        if row["steering_rad"] != row["held_command"]["steering_angles_rad"]:
            raise ValueError("Checkpoint raw steering/held command mismatch")
    session.records = records
    crossing_states = saved["crossing_states"]
    if type(crossing_states) is not list or len(crossing_states) != len(session.gates.crossings):
        raise ValueError("Checkpoint crossing state count mismatch")
    for i, (row, crossing) in enumerate(zip(crossing_states, session.gates.crossings)):
        _object(row, ("crossing_index", "before_state", "after_state"), "crossing states")
        if type(row["crossing_index"]) is not int or row["crossing_index"] != i:
            raise ValueError("Checkpoint crossing index mismatch")
        for key in ("before", "after"):
            state_row = _state(row[key + "_state"])
            if asdict(_pose(crossing[key]["tick"], state_row)) != crossing[key]:
                raise ValueError("Checkpoint crossing pose/full state mismatch")
    session.crossing_states = crossing_states
    if status == "completed" and (not session.gates.completed or session.gates.failure_reason):
        raise ValueError("Checkpoint cannot claim completion without all ordered gates")
    if status in ("running", "completed", "budget_exhausted"):
        if (session.gates.failure_reason or session.failure_reason is not None
                or session.rejected_attempt is not None or attempted != tick
                or session.allocator_updates != tick or session.driver_updates != (tick + 4) // 5
                or (tick > 0) != (session.command is not None)):
            raise ValueError("Checkpoint execution/accounting status mismatch")
        if status == "running" and (session.gates.completed or tick >= request.maximum_ticks):
            raise ValueError("Checkpoint running status mismatch")
        if status == "budget_exhausted" and session.gates.completed:
            raise ValueError("Checkpoint budget/completion ordering mismatch")
        if records and ((session.integral, session.previous_station_m) !=
                        (records[-1]["integral_after"], records[-1]["projection_after_m"])
                        or _raw(asdict(session.command)) != _raw(records[-1]["held_command"])):
            raise ValueError("Checkpoint held controller memory mismatch")
        if not records and (session.integral != 0 or session.previous_station_m != 0):
            raise ValueError("Fresh checkpoint controller memory mismatch")
        if abs(energy_residual_j(fixture()[0], session.initial_state, state)) > .5:
            raise ValueError("Checkpoint energy residual exceeds development limit")
        if _endpoint_limit(request, state, session.previous_station_m, session.command):
            raise ValueError("Checkpoint endpoint exceeds development limits")
    if status == "budget_exhausted" and attempted != request.maximum_ticks:
        raise ValueError("Checkpoint budget state mismatch")
    if status in ("completed", "running", "budget_exhausted") and (
            session.failure_reason is not None or session.rejected_attempt is not None):
        raise ValueError("Checkpoint terminal reason/attempt mismatch")
    if status in ("invalid", "model_error") and session.failure_reason is None:
        raise ValueError("Checkpoint failure must retain its reason")
    rejected = session.rejected_attempt
    if rejected is not None:
        if status not in ("model_error", "cancelled"):
            raise ValueError("Checkpoint rejection status mismatch")
        _attempt(rejected, accepted=False)
        if rejected["stage"] == "accepted":
            if not records or rejected != records[-1] or attempted != tick:
                raise ValueError("Checkpoint rejected accepted attempt mismatch")
        elif (attempted != tick + 1 or rejected["tick"] != tick
              or rejected["before_state_sha256"] != _digest(asdict(state))):
            raise ValueError("Checkpoint rejected attempt lineage mismatch")
    elif status == "model_error" and not session.failure_reason.startswith("cancellation:"):
        raise ValueError("Checkpoint model failure lost rejected attempt")
    return session


def require_new_output(output):
    """Validate an external create-only destination without creating it."""
    from lapsim.resources import repository_root
    output = Path(output)
    if not output.is_absolute() or output.exists() or output.is_symlink():
        raise ValueError("Output must be a new absolute external directory")
    protected = (Path(__file__).resolve().parents[2], repository_root().resolve())
    if any(output.resolve().is_relative_to(root) for root in protected):
        raise ValueError("Output cannot be inside source/installed resource directories")
    return output


def write_session_binding(output, session):
    with (output / "binding.json").open("xb") as stream:
        stream.write(_raw(session.binding))


def publish_session(output, session):
    """Create existing CLI payloads; no native output ownership/durability claim."""
    binding = output / "binding.json"
    if binding.is_symlink() or binding.read_bytes() != _raw(session.binding):
        raise ValueError("Retained session binding changed before publication")
    files = {"checkpoint.json": checkpoint(session), "result.json": _raw(session.result())}
    for name, raw in files.items():
        with (output / name).open("xb") as stream:
            stream.write(raw)
    inventory = {name: {"bytes": len(raw), "sha256": sha256(raw).hexdigest()}
                 for name, raw in {"binding.json": _raw(session.binding), **files}.items()}
    with (output / "files.json").open("xb") as stream:
        stream.write(_raw({"schema": "lapsim.powered-skidpad-files.v1", "files": inventory,
                           "qualified_tournament_result": False}))
    return inventory


def main(argv=None):
    """Run one bounded development chunk; publish fresh, inspectable local files."""
    import argparse
    from lapsim.events.skidpad_sequence import standard_skidpad_sequence

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry-length-m", type=float, required=True)
    parser.add_argument("--exit-length-m", type=float, required=True)
    parser.add_argument("--controller", choices=PHILOSOPHIES, default="fixed")
    parser.add_argument("--maximum-ticks", type=int, default=MAX_TICKS)
    parser.add_argument("--maximum-work", type=int, default=MAX_WORK)
    parser.add_argument("--chunk-ticks", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="New absolute external directory; existing output is never replaced")
    parser.add_argument("--resume-checkpoint", type=Path)
    parser.add_argument("--resume-sha256")
    args = parser.parse_args(argv)
    try:
        _integer(args.chunk_ticks, "chunk_ticks", 1, MAX_TICKS)
        request = PoweredSkidpadRequest(standard_skidpad_sequence(
            entry_length_m=args.entry_length_m, exit_length_m=args.exit_length_m),
            Controller(args.controller), args.maximum_ticks, args.maximum_work)
        if bool(args.resume_checkpoint) != bool(args.resume_sha256):
            raise ValueError("Resume requires both checkpoint and independently pinned SHA256")
        output = require_new_output(args.output)
        if args.resume_checkpoint:
            with args.resume_checkpoint.open("rb") as stream:
                saved = stream.read(MAX_CHECKPOINT_BYTES + 1)
            session = resume(saved, expected_sha256=args.resume_sha256, request=request)
        else:
            session = fresh_session(request)
        if session.status != "running":
            raise ValueError("Cannot execute a terminal event")
        output.mkdir(parents=True, exist_ok=False)
        # Files are create-only. This does not promise power-loss durability or
        # act as the native owned-output writer/retention contract.
        write_session_binding(output, session)
        try:
            advance_session(session, args.chunk_ticks)
        except KeyboardInterrupt:
            session.status = "cancelled"
            session.failure_reason = "Interrupted; unreturned numerical work is not recoverable"
        except Exception as error:
            # The API has already marked terminal failure and retained the last
            # accepted state. Publish that raw outcome before returning failure.
            if session.status not in TERMINAL:
                session.status = "model_error"
                session.failure_reason = (str(error) or type(error).__name__)[:4096]
        inventory = publish_session(output, session)
        print(json.dumps({"output": str(output), "status": session.status,
                          "accepted_ticks": session.tick,
                          "checkpoint_sha256": inventory["checkpoint.json"]["sha256"],
                          "qualified_tournament_result": False}, sort_keys=True))
        return 0 if session.status in ("running", "completed") else 3
    except (ValueError, OSError) as error:
        print(f"powered skidpad: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
