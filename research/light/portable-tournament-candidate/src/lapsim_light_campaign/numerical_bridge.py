"""UNTESTED complete one-lap numerical source; no guard/provider registration.

The original residual-regeneration predicate and source/runtime observer remain
mandatory external dependencies. This library is not execution authority.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import asdict, dataclass, fields, replace
import json
from math import atan2, ceil, cos, isfinite, sin

from lapsim_light_core.planar import PlanarControls, PlanarState
from lapsim_light_core.powered_planar import PoweredState, energy_residual_j
from lapsim_light_core.torque_light_combined import CombinedLightState, FAMILY as COMBINED_FAMILY, initialize_combined_light
from lapsim_light_core.torque_light_drs import DrsSignals, DrsState
from lapsim_light_core.torque_light_powered import LightPoweredState
from lapsim_light_core.torque_light_thermal import LumpedTireThermalState, ThermalLightPoweredState, evaluate_thermal_light
from lapsim_light_course.course import SourceCourse, GEOMETRY_SHA256
from lapsim_light_course import racing_geometry
from lapsim_light_guidance.driver import _controller, _project_local, _reference_start_heading
from lapsim_light_policies import core_adapter, core_registry
from lapsim_light_policies import awd_contracts as awd_fixture
from . import gate_ledger, raw_journal
from .fixture import (StandingFixture, BASELINE_CONFIGURATION_SHA256, PARTIAL_PROFILE_FAMILY,
                      validate_standing_fixture)
from .input_contracts import digest, encode, exact, is_sha256, require
from .numerical_inputs import (NumericalBindings, NumericalReference, NumericalDependencyUnavailable,
                               raw_reference_inputs, require_native_source_course, require_native_track)
from .plant_tick import advance_tick
from .raw_failures import RawOutputQuarantined
from .stepping import (ALLOCATOR_INTERVENTION_FIELDS, boundary_counts,
                       require_committed_work_transition, require_clocked_counter_transition)

BRIDGE_FAMILY = "lapsim.portable-awd-standing-numerical-bridge.v1"
CHECKPOINT_SCHEMA = raw_journal.CHECKPOINT_SCHEMA
CHUNK_SCHEMA = raw_journal.CHUNK_SCHEMA
MAX_CHUNK_TICKS = 10000
MAX_CHUNK_WORK = 50000
MAX_MISSION_TICKS = 1030000
MAX_MISSION_WORK = 8240000
MAX_CHUNK_ROWS = 502
MAX_CHUNK_BYTES = raw_journal.MAX_CHUNK_BODY
MAX_CHECKPOINT_BYTES = raw_journal.MAX_CHECKPOINT_BODY
ENERGY_RECORD_TOLERANCE_WH = 1e-9
REJECTED_ATTEMPT_SCHEMA = "lapsim.portable-light-rejected-attempt.raw.v1"
REJECTION_STAGES = ("post_step_domain_validation", "physical_gate_validation")
ZERO = (0., 0., 0., 0.)
AVAILABLE = awd_fixture.AVAILABLE

def canonical(value):
    return encode(value).decode("utf-8")

@dataclass(frozen=True)
class Memory:
    requested: tuple = ZERO
    proposed: tuple = ZERO
    held: tuple = ZERO
    steer: tuple = ZERO
    friction: tuple = ZERO
    total_brake: float = 0.
    raw_regen: float = 0.
    integral: float = 0.
    driver_command: PlanarControls | None = None
    previous_progress: float = 0.
    source_progress_m: float = 0.
    load_interventions: int = 0
    energy_interventions: int = 0
    feedforward_interventions: int = 0
    last_allocation: dict | None = None
    sampled_draw_j: float = 0.
    sampled_recovery_j: float = 0.
    maximum_slip: float = 0.
    maximum_utilization: float = 0.
    maximum_yaw: float = 0.
    driver_updates: int = 0
    allocator_updates: int = 0
    blend_updates: int = 0
    slip_interventions: int = 0
    electrical_limit_ticks: int = 0
    generating_boundaries: int = 0
    yaw_interventions: int = 0
    reserve_interventions: int = 0
    regen_inhibited_updates: int = 0
    brake_redistribution_ticks: int = 0
    maximum_brake_overshoot_nm: float = 0.


@dataclass(frozen=True)
class Session:
    config_id: str
    context: dict
    context_sha256: str
    state: CombinedLightState
    memory: Memory
    tick: int = 0
    segment: int = 0
    parent_chunk_sha256: str | None = None
    status: str = "running"
    violation: str | None = None
    finish: dict | None = None
    rejected_state: dict | None = None
    lap_crossings: tuple = ()

def _construct(cls, value, **changes):
    require(type(value) is dict and set(value) == {f.name for f in fields(cls)}, "Exact checkpoint state fields required")
    return cls(**{**value, **changes})

def decode_state(value):
    """Only these explicit dataclasses; no pickle, dynamic class or import name."""
    thermal = value["thermal"]
    light = thermal["light"]
    powered = light["powered"]
    plant = _construct(PlanarState, powered["plant"], wheel_speeds_rad_s=tuple(powered["plant"]["wheel_speeds_rad_s"]))
    power = _construct(PoweredState, powered, plant=plant, actuator_memory_nm=tuple(powered["actuator_memory_nm"]))
    light_state = _construct(LightPoweredState, light, powered=power)
    heat_state = _construct(LumpedTireThermalState, thermal["thermal"])
    wrapper = _construct(ThermalLightPoweredState, thermal, light=light_state, thermal=heat_state)
    signals = None if value["last_signals"] is None else _construct(DrsSignals, value["last_signals"])
    return _construct(CombinedLightState, value, thermal=wrapper, drs=_construct(DrsState, value["drs"]), last_signals=signals)

def decode_memory(value):
    changes = {name: tuple(value[name]) for name in ("requested", "proposed", "held", "steer", "friction")}
    command = value["driver_command"]
    if command is not None:
        vectors = {name: None if command[name] is None else tuple(command[name])
                   for name in ("steering_angles_rad", "drive_torques_nm", "brake_torques_nm", "normal_loads_n", "wheel_radii_m")}
        command = _construct(PlanarControls, command, **vectors)
    return _construct(Memory, value, **changes, driver_command=command)

def checkpoint(session):
    body = {"schema": CHECKPOINT_SCHEMA, **asdict(session)}
    text = canonical(body)
    require(len(text.encode()) <= MAX_CHECKPOINT_BYTES, "Checkpoint exceeds bound")
    return {"checkpoint": body, "checkpoint_sha256": digest(body)}


def _rejected_attempt(accepted, state, memory, stage):
    """Retain provisional controls without committing the rejected interval."""
    require(stage in REJECTION_STAGES, "Explicit rejection stage required")
    record = {
        "schema": REJECTED_ATTEMPT_SCHEMA, "stage": stage,
        "interval_start_tick": accepted.tick, "candidate_tick": accepted.tick + 1,
        "accepted_state_sha256": digest(asdict(accepted.state)),
        "accepted_memory_sha256": digest(asdict(accepted.memory)),
        "state": asdict(state), "memory": asdict(memory),
        "committed": False, "qualification_or_execution_authority": False,
    }
    require(len(encode(record)) <= MAX_CHECKPOINT_BYTES, "Rejected attempt exceeds raw diagnostic bound")
    return record


def _validate_rejected_attempt(session):
    record = session.rejected_state
    require(session.status == "invalid" or record is None, "Successful/non-invalid state cannot carry rejection evidence")
    if record is None:
        return  # No candidate need exist when an earlier operation failed.
    exact(record, {"schema", "stage", "interval_start_tick", "candidate_tick", "accepted_state_sha256",
                   "accepted_memory_sha256", "state", "memory", "committed",
                   "qualification_or_execution_authority"}, "versioned raw rejected attempt")
    require(len(encode(record)) <= MAX_CHECKPOINT_BYTES and record["schema"] == REJECTED_ATTEMPT_SCHEMA and
            record["stage"] in REJECTION_STAGES and record["committed"] is False and
            record["qualification_or_execution_authority"] is False and
            type(record["interval_start_tick"]) is int and record["interval_start_tick"] == session.tick and
            type(record["candidate_tick"]) is int and record["candidate_tick"] == session.tick + 1 and
            record["candidate_tick"] <= session.context["limits"]["maximum_ticks"] and
            record["accepted_state_sha256"] == digest(asdict(session.state)) and
            record["accepted_memory_sha256"] == digest(asdict(session.memory)),
            "Rejected attempt differs from exact accepted boundary or diagnostic scope")
    state, memory = decode_state(record["state"]), decode_memory(record["memory"])
    require(state.drs.ticks == state.thermal.thermal.ticks == state.thermal.light.feedback_ticks == record["candidate_tick"] and
            state.model_sha256 == session.state.model_sha256 and
            state.automatic_drs_enabled is session.state.automatic_drs_enabled and
            state.drs.policy_sha256 == session.state.drs.policy_sha256 and
            state.thermal.model_sha256 == session.state.thermal.model_sha256 and
            state.thermal.light.model_sha256 == session.state.thermal.light.model_sha256 and
            state.thermal.thermal.config_sha256 == session.state.thermal.thermal.config_sha256,
            "Rejected typed state clock/configuration differs")
    old_power, new_power = asdict(session.state.thermal.light.powered), asdict(state.thermal.light.powered)
    remaining = session.context["limits"]["maximum_work"] - old_power["integration_trials"] - old_power["wheel_stop_events"]
    require_committed_work_transition(old_power, new_power, start_tick=session.tick, end_tick=record["candidate_tick"],
                                      maximum_new_work=min(MAX_CHUNK_WORK, remaining))
    require_clocked_counter_transition(asdict(session.memory), asdict(memory),
                                       start_tick=session.tick, end_tick=record["candidate_tick"])
    for name in ("requested", "proposed", "held", "steer", "friction"):
        awd_fixture.four(getattr(memory, name), "rejected " + name)
    require(memory.driver_command is not None and type(memory.last_allocation) is dict,
            "Complete provisional driver/allocation evidence required")
    awd_fixture.validate_driver_command(memory.driver_command)
    require(memory.steer == memory.driver_command.steering_angles_rad and
            memory.requested == (sum(memory.driver_command.drive_torques_nm) / 4,) * 4,
            "Rejected control evidence contradicts its common driver demand")
    for name in ("total_brake", "raw_regen", "integral", "previous_progress", "sampled_draw_j", "sampled_recovery_j",
                 "maximum_slip", "maximum_utilization", "maximum_yaw", "maximum_brake_overshoot_nm", "source_progress_m"):
        require(type(getattr(memory, name)) in (int, float) and isfinite(getattr(memory, name)),
                "Finite provisional memory value required")
    # Intentionally no _observe/domain/clearance/energy acceptance of the
    # rejected physical candidate. Its raw bad values are retained as evidence.

ROW_FIELDS = frozenset(["tick","t_s","x_m","y_m","heading_rad","u_mps","v_mps","yaw_rad_s","progress_m","completed_laps","lap_distance_m","launch_override_active","cross_track_m","pack_energy_j","net_wh","pack_power_w","wheel_omega_rad_s","slip","utilization","normal_load_n","source_progress_m","reference_progress_m","reference_geometry_sha256","controller_diagnostics","requested_nm","proposed_nm","limited_nm","achieved_nm","friction_nm","constraints","held_total_brake_request_nm","held_raw_regen_request_nm","braking_observation","tire_temperature_c","drs_commanded","drs_actual","mechanical_residual_j","work","controller_policy","topology_id","configuration_sha256","base_configuration_sha256","motor_count","drive_availability","steering_rad","baseline_weights","driver_total_drive_request_nm","driver_total_brake_request_nm","motor_current_a","motor_torque_nm","interventions"])
INTERVENTION_FIELDS = ("slip_interventions", "yaw_interventions", "reserve_interventions",
    "regen_inhibited_updates", "brake_redistribution_ticks", "maximum_brake_overshoot_nm",
    "load_interventions", "energy_interventions", "feedforward_interventions")

def _validate_row_schema(row, session, car):
    exact(row, ROW_FIELDS, "complete numerical telemetry row")
    for name in ("t_s", "x_m", "y_m", "heading_rad", "u_mps", "v_mps", "yaw_rad_s",
                 "progress_m", "lap_distance_m", "cross_track_m", "pack_energy_j", "net_wh", "pack_power_w",
                 "source_progress_m", "reference_progress_m", "held_total_brake_request_nm",
                 "held_raw_regen_request_nm", "tire_temperature_c", "mechanical_residual_j",
                 "driver_total_drive_request_nm", "driver_total_brake_request_nm"):
        require(type(row[name]) in (int, float) and isfinite(row[name]), "Finite nonboolean row scalar required: " + name)
    for name in ("tick", "completed_laps", "work", "motor_count"):
        require(type(row[name]) is int and row[name] >= 0, "Nonnegative integer row field required: " + name)
    require(row["completed_laps"] <= 1 and type(row["launch_override_active"]) is bool and
            row["launch_override_active"] is False, "Exact one-lap/no-launch row required")
    for name in ("wheel_omega_rad_s", "slip", "utilization", "normal_load_n", "requested_nm",
                 "proposed_nm", "limited_nm", "achieved_nm", "friction_nm", "steering_rad",
                 "motor_current_a", "motor_torque_nm", "baseline_weights"):
        require(type(row[name]) is list and len(row[name]) == 4 and
                all(type(v) in (int, float) and isfinite(v) for v in row[name]),
                "Four finite nonboolean row values required: " + name)
    require(row["u_mps"] >= 0 and abs(row["yaw_rad_s"]) <= 2 and
            all(v >= 0 for v in row["wheel_omega_rad_s"]) and
            all(abs(v) <= 1 for v in row["slip"]) and
            all(0 <= v <= 1 + 32 * 2.220446049250313e-16 for v in row["utilization"]) and
            all(v >= 0 for v in row["normal_load_n"]) and all(0 <= v <= 80 for v in row["friction_nm"]),
            "Saved telemetry exceeds existing physical/actuator domain")
    require(row["progress_m"] == row["reference_progress_m"], "Saved reference progress aliases disagree")
    for index, (x, y) in enumerate(car.wheel_positions_m):
        steer = row["steering_rad"][index]
        local_u = (cos(steer) * (row["u_mps"] - row["yaw_rad_s"] * y) +
                   sin(steer) * (row["v_mps"] + row["yaw_rad_s"] * x))
        slip = (0. if row["normal_load_n"][index] == 0. else
                (car.wheel_radius_m * row["wheel_omega_rad_s"][index] - local_u) /
                max(abs(local_u), car.low_speed_regularization_mps))
        require(row["slip"][index] == slip, "Saved wheel speed/slip/pose/steering disagree")
    thermal = session.context["thermal"]
    require(thermal["minimum_temperature_c"] <= row["tire_temperature_c"] <= thermal["maximum_temperature_c"],
            "Saved tire temperature exceeds declared model domain")
    require(row["drs_commanded"] in ("open", "closed") and row["drs_actual"] in ("open", "closed"),
            "Explicit DRS row modes required")
    require(type(row["constraints"]) is list and all(type(v) is str and v for v in row["constraints"]),
            "Explicit constraint labels required")
    require((row["controller_diagnostics"] is None) if row["tick"] == 0
            else type(row["controller_diagnostics"]) is dict, "Controller diagnostic phase differs")
    require(row["base_configuration_sha256"] == BASELINE_CONFIGURATION_SHA256,
            "Saved baseline configuration differs")
    exact(row["braking_observation"], {"state_tick", "held_request_update_tick",
          "friction_interval_start_tick", "actual_net_braking_nm", "excess_over_held_request_nm", "scope"},
          "braking observation")
    brake = row["braking_observation"]
    tick = row["tick"]
    for name in ("actual_net_braking_nm", "excess_over_held_request_nm"):
        require(type(brake[name]) in (int, float) and isfinite(brake[name]), "Finite braking observation required")
    require(type(brake["state_tick"]) is int and brake["state_tick"] == tick and
            brake["held_request_update_tick"] == (None if tick == 0 else ((tick-1)//10)*10) and
            brake["friction_interval_start_tick"] == (None if tick == 0 else tick-1) and
            (tick == 0 or (type(brake["held_request_update_tick"]) is int and
                           type(brake["friction_interval_start_tick"]) is int)),
            "Braking observation clocks differ")
    net = -sum(row["achieved_nm"]) + sum(row["friction_nm"])
    require(brake["actual_net_braking_nm"] == net and
            brake["excess_over_held_request_nm"] == max(0., net-row["held_total_brake_request_nm"]) and
            brake["scope"] == "Post-state instantaneous torque with prior1ms friction and held100Hz request; not the pre-integration cumulative peak sample",
            "Braking row observation contradicts its saved torque/state clocks")

class NumericalBridge:
    """RAW numerical program; object/type/hash matches grant no permission."""

    def __init__(self, *, fixture, source_course, reference, bindings,
                 expected_identity, reviewed_source_manifest_sha256):
        require(type(bindings) is NumericalBindings, "Explicit reviewed numerical bindings required")
        bindings.require_available()
        require(type(fixture) is StandingFixture and type(source_course) is SourceCourse and
                type(reference) is NumericalReference, "Exact portable numerical inputs required")
        require_native_source_course(source_course)
        require_native_track(reference.track)
        require_native_track(reference.source_track)
        raw_journal._validate_identity(expected_identity)
        require(is_sha256(reviewed_source_manifest_sha256), "Externally reviewed source manifest pin required")
        record = validate_standing_fixture(fixture)
        source_payload = source_course.metadata_dict()
        source_payload["geometry"] = {"model": "piecewise_constant_curvature_arcs",
                                      **source_course.source_track.geometry_dict()}
        require(digest(source_payload) == source_course.bundle_payload_sha256,
                "Live source-course metadata/geometry differs from its bundle payload")
        rebuilt = raw_reference_inputs(reference.artifact_raw, source_course,
                    producer_audit_sha256=reference.provenance["producer_audit_sha256"],
                    reviewed_promotion_sha256=reference.provenance["reviewed_promotion_sha256"])
        require(reference.metadata_json == rebuilt.metadata_json and
                canonical(reference.track.geometry_dict()) == canonical(rebuilt.track.geometry_dict()) and
                canonical(reference.source_track.geometry_dict()) == canonical(rebuilt.source_track.geometry_dict()),
                "Live numerical reference differs from its exact raw artifact")
        reference = rebuilt
        actual = {"settings": asdict(fixture.settings), "thermal": asdict(fixture.thermal),
                  "drs_policy": asdict(fixture.drs_policy), "actuation": asdict(fixture.actuation),
                  "environment": asdict(fixture.environment), "driver": asdict(fixture.driver)}
        require(canonical(actual) == canonical(record["values"]), "Fixture objects differ from configuration")
        p = reference.provenance
        require(expected_identity["configuration_sha256"] == fixture.configuration_sha256 and
                expected_identity["course_bundle_sha256"] == source_course.bundle_raw_sha256 and
                expected_identity["line_artifact_sha256"] == p["artifact_sha256"],
                "Reviewed numerical input identity differs")
        require(digest(reference.source_track.geometry_dict()) == GEOMETRY_SHA256 ==
                digest(source_course.source_track.geometry_dict()) and
                canonical(reference.frame) == canonical(source_course.frame_dict()),
                "Reference/source cone frame differs")
        require(record["reference"] == {"geometry_sha256": p["reference_geometry_sha256"],
                                        "length_m": reference.length_m},
                "Fixture/reference geometry differs")
        self.fixture, self.course, self.reference, self.bindings = fixture, source_course, reference, bindings
        self.reviewed_source_manifest_sha256 = reviewed_source_manifest_sha256
        self._identity_json = encode(expected_identity)

    @property
    def identity(self):
        return json.loads(self._identity_json)

    def source_identity(self):
        self.bindings.require_available()
        source = json.loads(canonical(self.bindings.source_observer.observe_source_identity()))
        exact(source, {"family", "source_manifest_sha256", "numerical_environment_sha256",
                       "external_bindings", "sha256"}, "observed numerical source identity")
        expected = self.identity
        require(source["family"] == BRIDGE_FAMILY and source["sha256"] == expected["source_sha256"] and
                digest({k:v for k,v in source.items() if k != "sha256"}) == source["sha256"] and
                source["source_manifest_sha256"] == self.reviewed_source_manifest_sha256 and
                source["numerical_environment_sha256"] == expected["environment_sha256"] and
                source["external_bindings"] == {
                    "source_observer_sha256": self.bindings.source_observer_sha256,
                    "residual_regen_rule_sha256": self.bindings.residual_regen_rule_sha256},
                "Actual source/runtime observation differs from reviewed pins")
        return source

    def residual_low_speed_regen(self, u_mps, electrical):
        self.bindings.require_available()
        result = self.bindings.residual_regen_rule.residual_low_speed_regen(u_mps, electrical)
        if type(result) is not bool:
            raise NumericalDependencyUnavailable("Original residual-regeneration predicate did not return a boolean")
        return result

    def make_context(self, course_id, mode, source, config_id, *, expected_source_sha256):
        require(course_id == "amz_fssim_fsi_approx" and mode == "one_lap" and
                config_id == self.identity["policy_id"], "Exact nominal one-lap AWD policy required")
        require(source["sha256"] == expected_source_sha256 == self.identity["source_sha256"] and
                digest({k:v for k,v in source.items() if k != "sha256"}) == expected_source_sha256,
                "Reviewed source identity required")
        f, track = self.fixture, self.reference
        core_adapter.ensure_topology(f.actuation, AVAILABLE)
        ticks = (ceil(track.length_m / 3.) + 30) * 1000
        require(ticks <= MAX_MISSION_TICKS, "Mission horizon exceeds fixed bound")
        limits = {"maximum_ticks": ticks, "maximum_work": min(8*ticks, MAX_MISSION_WORK), "logging_ticks": 20}
        require(f.driver.initial_speed_mps == 0. and f.driver.reference_geometry == "sampled_polyline" and
                f.driver.target_progress_m == track.length_m and f.driver.maximum_simulated_time_s == ticks*.001 and
                f.driver.maximum_internal_substeps == MAX_CHUNK_WORK, "Standing driver/reference/horizon differs")
        point = PlanarState(x_m=track.x_m[0], y_m=track.y_m[0],
                            heading_rad=_reference_start_heading(track, f.driver),
                            u_mps=0., wheel_speeds_rad_s=ZERO)
        state = initialize_combined_light(f.settings, f.thermal, f.drs_policy, f.actuation,
                    PoweredState(point, ZERO, 9000000.), f.environment, initial_temperature_c=70.,
                    automatic_drs_enabled=True, load_longitudinal_mps2=0., load_lateral_mps2=0.)
        metadata = self.course.metadata_dict()
        course = {"id": course_id, "label": metadata["label"], "length_m": self.course.source_track.length_m,
                  "geometry_sha256": self.course.geometry_sha256, "bundle_sha256": self.course.bundle_raw_sha256,
                  "classification": "map_derived_approximation", "source_url": metadata["provenance"]["source_name"],
                  "assumed_half_width_m": metadata["ai_defaults"]["half_width_m"],
                  "description": metadata["description"], "provenance": metadata["provenance"]}
        context = {
            "family": BRIDGE_FAMILY, "component_family": COMBINED_FAMILY, "component_model_sha256": state.model_sha256,
            "source": source, "mode": mode, "course": course, "reference_line": track.provenance, "limits": limits,
            "clocks": {"plant_period_s": .001, "driver_interval_ticks": 50,
                       "allocator_interval_ticks": 10, "logging_interval_ticks": 20}, "laps_target": 1,
            "experiment_scope": {"kind": "portable_four_independent_AWD_FSI_development", "regeneration_enabled": False,
                                 "receipt_boundary": "RAW until original owned execution/cleanup admission"},
            "standing_start": {"vehicle_u_mps": 0., "vehicle_v_mps": 0., "yaw_rate_rad_s": 0.,
                               "wheel_omega_rad_s": [0.]*4, "actuator_memory_nm": [0.]*4, "clock_s": 0.},
            "development_condition": {"surface_friction_multiplier": f.environment.road.base_friction_multiplier,
                                      "launch_ticks": 0},
            "settings": asdict(f.settings), "thermal": asdict(f.thermal), "drs_policy": asdict(f.drs_policy),
            "controller_policy": core_registry.entry(config_id), "actuation": asdict(f.actuation),
            "brake_adapter": {"version": core_adapter.BLEND_VERSION, "per_wheel_capacity_nm": [80.]*4,
                              "preferred_shares": list(core_adapter.SHARES),
                              "drive_availability": list(AVAILABLE), "friction_availability": [True]*4},
            "environment": asdict(f.environment), "driver": asdict(f.driver),
            "initial_state": asdict(state), "initial_temperature_c": 70., "profile": json.loads(f.configuration_json)["family"],
            "configuration_sha256": f.configuration_sha256, "base_configuration_sha256": BASELINE_CONFIGURATION_SHA256,
            "motor_count": 4, "drive_availability": list(AVAILABLE), "steering_model": "parallel_front_v1",
            "campaign_eligible": False, "qualification_or_execution_authority": False,
            "clearance_scope": "Instantaneous actual rectangle at 10ms samples; continuous swept clearance unverified",
        }
        record = json.loads(f.configuration_json)
        if record["family"] == PARTIAL_PROFILE_FAMILY:
            from .profile_projection import MAX_PROFILE_CONTEXT_BYTES
            context["partial_profile_projection"] = record["partial_profile_projection"]
            require(len(encode(context)) <= MAX_PROFILE_CONTEXT_BYTES,
                    "Complete profiled context exceeds bounded checkpoint metadata budget")
        return json.loads(canonical(context)), state, (f.settings, f.thermal, f.drs_policy,
                                                      f.actuation, f.environment, track, f.driver)

    def initialize(self, course_id, config_id, mode, *, expected_source_sha256):
        core_adapter.controller_for(config_id)
        source = self.source_identity()
        require(source["sha256"] == expected_source_sha256, "Unreviewed bridge source")
        context, state, _ = self.make_context(course_id, mode, source, config_id,
                                             expected_source_sha256=expected_source_sha256)
        return Session(config_id, context, digest(context), state, Memory())

    def resume(self, value, *, expected_checkpoint_sha256, expected_source_sha256):
        require(type(value) is dict and set(value) == {"checkpoint", "checkpoint_sha256"}, "Exact checkpoint envelope required")
        body = deepcopy(value["checkpoint"])
        require(value["checkpoint_sha256"] == expected_checkpoint_sha256 == digest(body), "Checkpoint provenance hash mismatch")
        require(len(canonical(body).encode()) <= MAX_CHECKPOINT_BYTES and body.pop("schema") == CHECKPOINT_SCHEMA, "Checkpoint size/schema differs")
        session = _construct(Session, body, state=decode_state(body["state"]), memory=decode_memory(body["memory"]), lap_crossings=tuple(body["lap_crossings"]))
        expected = self.initialize(session.context["course"]["id"], session.config_id, session.context["mode"],
                              expected_source_sha256=expected_source_sha256)
        require(canonical(session.context) == canonical(expected.context) and digest(session.context) == session.context_sha256,
                "Checkpoint mission/source/course/conditions changed")
        require(type(session.tick) is int and 0 <= session.tick <= session.context["limits"]["maximum_ticks"] and
                session.tick == session.state.drs.ticks == session.state.thermal.thermal.ticks == session.state.thermal.light.feedback_ticks,
                "Checkpoint clocks disagree")
        require(type(session.segment) is int and 0 <= session.segment <= 750 and
                ((session.segment == 0) == (session.parent_chunk_sha256 is None)), "Checkpoint chain position differs")
        require(session.segment == 0 or is_sha256(session.parent_chunk_sha256), "Checkpoint parent must be an exact SHA256")
        require(session.state.model_sha256 == expected.state.model_sha256 and session.status in
                ("running", "completed", "diagnostic_complete", "time_limit", "invalid"), "Checkpoint model/status differs")
        require(session.state.automatic_drs_enabled is expected.state.automatic_drs_enabled and
                session.state.drs.policy_sha256 == expected.state.drs.policy_sha256 and
                session.state.thermal.model_sha256 == expected.state.thermal.model_sha256 and
                session.state.thermal.light.model_sha256 == expected.state.thermal.light.model_sha256 and
                session.state.thermal.thermal.config_sha256 == expected.state.thermal.thermal.config_sha256,
                "Checkpoint combined/DRS/thermal/light configuration bindings differ")
        memory = session.memory
        saved_steer = awd_fixture.steering(memory.steer)
        if memory.driver_command is not None:
            awd_fixture.validate_driver_command(memory.driver_command)
            require(saved_steer == memory.driver_command.steering_angles_rad,
                    "Saved steering differs from the common driver command")
            expected_request = (sum(memory.driver_command.drive_torques_nm) / 4,) * 4
            require(memory.requested == expected_request,
                    "Saved request differs from the equal four-wheel demand baseline")
        for name in ("requested", "proposed", "held", "steer", "friction"):
            require(len(getattr(memory, name)) == 4 and all(type(v) in (int, float) and isfinite(v) for v in getattr(memory, name)),
                            "Four finite saved wheel controls required")
        require(all(type(getattr(memory, name)) is int and 0 <= getattr(memory, name) <= session.tick
                    for name in ("driver_updates", "allocator_updates", "blend_updates", "slip_interventions", "electrical_limit_ticks", "generating_boundaries",
                        "yaw_interventions", "reserve_interventions", "regen_inhibited_updates", "brake_redistribution_ticks",
                        "load_interventions", "energy_interventions", "feedforward_interventions")),
                "Checkpoint counters disagree")
        require((memory.driver_command is None) == (session.tick == 0) and abs(memory.integral) <= 1 and
                0 <= memory.total_brake <= 320 and 0 <= memory.raw_regen <= 320 and
                memory.sampled_draw_j >= 0 and memory.sampled_recovery_j >= 0, "Checkpoint controller/energy memory differs")
        for name in ("total_brake", "raw_regen", "integral", "previous_progress", "sampled_draw_j", "sampled_recovery_j",
                     "maximum_slip", "maximum_utilization", "maximum_yaw", "maximum_brake_overshoot_nm", "source_progress_m"):
            require(type(getattr(memory, name)) in (int, float) and isfinite(getattr(memory, name)), "Finite checkpoint memory required")
        require(memory.blend_updates == session.tick and memory.driver_updates == ceil(session.tick / 50) and
                memory.allocator_updates == ceil(session.tick / 10), "Global controller phase/counters disagree")
        require(all(getattr(memory, name) <= memory.allocator_updates for name in
                    ("slip_interventions", "yaw_interventions", "reserve_interventions", "regen_inhibited_updates",
                     "load_interventions", "energy_interventions", "feedforward_interventions")) and
                memory.maximum_brake_overshoot_nm >= 0, "Saved policy interventions exceed allocator clock or are negative")
        if not core_registry.entry(session.config_id)["regen_enabled"]:
            require(memory.raw_regen == 0 and all(value >= 0 for value in
                    (*memory.requested, *memory.proposed, *memory.held, *session.state.thermal.light.powered.actuator_memory_nm)),
                    "An off checkpoint cannot import a generating-policy state")
        require(0 <= memory.maximum_slip <= 1 and 0 <= memory.maximum_utilization <= 1 + 32 * 2.220446049250313e-16 and
                0 <= memory.maximum_yaw <= 2 and -.5 <= memory.previous_progress <= session.context["reference_line"]["reference_length_m"] + 1.,
                "Saved observable outside declared domain")
        require(all(0 <= value <= 80 for value in memory.friction), "Saved friction authority differs")
        pack = session.state.thermal.light.powered.pack_energy_j
        powered = session.state.thermal.light.powered
        require(session.tick <= powered.integration_substeps <= powered.integration_trials and
                powered.integration_trials + powered.wheel_stop_events <= session.context["limits"]["maximum_work"],
                "Checkpoint cumulative work/counters exceed mission or contradict clock")
        require(0 <= pack <= 18_000_000 and
                abs(memory.sampled_draw_j - memory.sampled_recovery_j - (9_000_000. - pack)) <= 1e-6 + 1e-10 * session.tick,
                "Checkpoint pack/net-increment energy mismatch")
        if session.tick == 0:
            require(canonical(asdict(session.state)) == canonical(session.context["initial_state"]), "Initial physical state changed")
            require(canonical(asdict(memory)) == canonical(asdict(Memory())), "Initial controller memory changed")
        if session.segment == 0:
            require(session.tick == 0 and session.status == "running" and session.violation is None and
                    session.finish is None and session.rejected_state is None and session.lap_crossings==(), "Segment zero must be the exact initialized origin")
        require((session.violation is not None) == (session.status == "invalid"), "Failure/status mismatch")
        _validate_rejected_attempt(session)
        if session.violation is not None:
            require(type(session.violation) is str and 0 < len(session.violation) <= 1024, "Bounded failure text required")
        if session.status == "running":
            require(session.tick < session.context["limits"]["maximum_ticks"] and session.finish is None,
                    "A running cell must be before its mission horizon")
        if session.status == "time_limit":
            require(session.context["mode"] in ("one_lap", "ten_laps_nominal", "ten_laps_low_grip") and session.tick == session.context["limits"]["maximum_ticks"] and
                    session.finish is None, "Time-limit state must match the full-lap mission horizon")
        if session.status == "diagnostic_complete":
            require(session.context["mode"] == "start_qualification" and
                    (session.tick == session.context["limits"]["maximum_ticks"] or session.finish is not None),
                    "Diagnostic completion must match the qualification mission")
        if session.status == "completed":
            require(session.context["mode"] in ("one_lap", "ten_laps_nominal", "ten_laps_low_grip") and session.finish is not None, "Completed lap needs a finish")
        require(-.5<=memory.source_progress_m<=session.context['course']['length_m']+1.,'Physical source progress domain')
        _,_,dependencies=self.make_context(session.context['course']['id'],session.context['mode'],self.source_identity(),session.config_id,
            expected_source_sha256=expected_source_sha256)
        gate_ledger.validate(session.lap_crossings,source_sha256=expected_source_sha256,current_tick=session.tick,
            current_source_progress_m=memory.source_progress_m,source_length_m=session.context['course']['length_m'],gate=dependencies[5].gate)
        require((session.status=='completed')==(len(session.lap_crossings)==1),'Completed physical gate/status differs')
        if session.finish is not None:
            event=session.lap_crossings[-1]
            require(session.finish==event['crossing'] and session.tick==event['boundary_tick'] and
                canonical(asdict(session.state))==canonical(event['accepted_state']) and
                canonical(asdict(session.memory))==canonical(event['accepted_memory']),
                'Terminal tick/state/memory/finish must exactly match the accepted physical gate event')
        return session

    def _observe(self, session, dependencies):
        settings, heat, _, act, env, track, driver = dependencies
        p = session.state.thermal.light.powered
        point = p.plant
        projection = _project_local(track, point.x_m, point.y_m, session.memory.previous_progress, 12.)
        require(abs(projection.station_m - session.memory.previous_progress) <= .5, "Projection discontinuity exceeds1ms gate")
        source_projection = _project_local(track.source_track, point.x_m, point.y_m, session.memory.source_progress_m, 12.)
        require(abs(source_projection.station_m-session.memory.source_progress_m)<=.5,"Source projection discontinuity")
        _, physical, electrical = evaluate_thermal_light(settings, heat, act, session.state.thermal,
            session.memory.held, session.memory.steer, ZERO, AVAILABLE, env, aero_mode=session.state.drs.actual_mode)
        require(physical.road_valid and all(w.road_valid and w.normal_load_n >= 0 for w in physical.wheels), "Invalid road/normal load")
        slip = max(abs(w.slip_ratio) for w in physical.wheels)
        util = max(w.force_utilization for w in physical.wheels)
        require(slip <= 1 and util <= 1 + 32 * 2.220446049250313e-16, "Slip/combined-force domain exceeded")
        require(point.u_mps >= 0 and abs(point.yaw_rate_rad_s) <= 2 and
                abs(atan2(point.v_mps, max(.5, point.u_mps))) <= .5, "Velocity/yaw/sideslip domain exceeded")
        require(0 <= p.pack_energy_j <= act.pack_capacity_j, "Pack outside domain")
        if session.tick % 10 == 0:
            require(racing_geometry.footprint_clearance(track.frame,(point.x_m,point.y_m,point.heading_rad),
                    front_m=track.parameters["front_extent_m"],rear_m=track.parameters["rear_extent_m"],
                    width_m=track.parameters["vehicle_width_m"],
                    margin_m=track.parameters["safety_margin_m"]+track.parameters["map_uncertainty_m"])>=0,
                    "Physical approximate cone corridor violated;not a moved reference corridor")
        require(not self.residual_low_speed_regen(point.u_mps, electrical), "Unmodeled low-speed residual regen; cell ineligible")
        initial = decode_state(session.context["initial_state"]).thermal.light.powered
        residual = energy_residual_j(settings.forces.plant, initial, p)
        require(p.integration_trials + p.wheel_stop_events <= session.context["limits"]["maximum_work"], "Mission work budget exceeded")
        require(abs(residual) <= .002 + 128 * 2.220446049250313e-16 * act.pack_capacity_j * (p.integration_trials + session.tick + 1),
                "Mechanical energy residual exceeded")
        return projection, physical, electrical, residual, source_projection

    def _row(self, session, observation):
        projection, physical, electrical, residual, source_projection = observation
        p = session.state.thermal.light.powered
        point = p.plant
        return {"tick": session.tick, "t_s": session.tick * .001, "x_m": point.x_m, "y_m": point.y_m,
                "heading_rad": point.heading_rad, "u_mps": point.u_mps, "v_mps": point.v_mps,
                "yaw_rad_s": point.yaw_rate_rad_s, "progress_m": projection.station_m,
                "completed_laps":len(session.lap_crossings),
                "lap_distance_m":source_projection.station_m%session.context['course']['length_m'],
                "launch_override_active":0<session.tick<=session.context['development_condition']['launch_ticks'],
                "cross_track_m": projection.cross_track_m, "pack_energy_j": p.pack_energy_j,
                "net_wh": (9_000_000. - p.pack_energy_j) / 3600, "pack_power_w": electrical.pack_power_w,
                "wheel_omega_rad_s": list(point.wheel_speeds_rad_s), "slip": [w.slip_ratio for w in physical.wheels],
                "utilization": [w.force_utilization for w in physical.wheels], "normal_load_n": [w.normal_load_n for w in physical.wheels],
                "source_progress_m":source_projection.station_m,"reference_progress_m":projection.station_m,
                "reference_geometry_sha256":session.context["reference_line"]["reference_geometry_sha256"],
                "controller_diagnostics":session.memory.last_allocation,
                "requested_nm": list(session.memory.requested), "proposed_nm": list(session.memory.proposed),
                "limited_nm": list(session.memory.held), "achieved_nm": list(electrical.wheel_torques_nm),
                "friction_nm": list(session.memory.friction), "constraints": list(electrical.constraints),
                "held_total_brake_request_nm": session.memory.total_brake,
                "held_raw_regen_request_nm": session.memory.raw_regen,
                "braking_observation": {
                    "state_tick": session.tick,
                    "held_request_update_tick": None if session.tick == 0 else ((session.tick - 1) // 10) * 10,
                    "friction_interval_start_tick": None if session.tick == 0 else session.tick - 1,
                    "actual_net_braking_nm": -sum(electrical.wheel_torques_nm) + sum(session.memory.friction),
                    "excess_over_held_request_nm": max(0., -sum(electrical.wheel_torques_nm) + sum(session.memory.friction) - session.memory.total_brake),
                    "scope": "Post-state instantaneous torque with prior1ms friction and held100Hz request; not the pre-integration cumulative peak sample"},
                "tire_temperature_c": session.state.thermal.thermal.temperature_c,
                "drs_commanded": session.state.drs.commanded_mode, "drs_actual": session.state.drs.actual_mode,
                "mechanical_residual_j": residual, "work": p.integration_trials + p.wheel_stop_events,
                "controller_policy": core_registry.entry(session.config_id),
                "topology_id":core_registry.TOPOLOGY,"configuration_sha256":session.context['configuration_sha256'],
                "base_configuration_sha256":BASELINE_CONFIGURATION_SHA256,
                "motor_count":4,"drive_availability":list(AVAILABLE),
                "steering_rad":list(session.memory.steer),"baseline_weights":[.25]*4,
                "driver_total_drive_request_nm":0. if session.memory.driver_command is None else sum(session.memory.driver_command.drive_torques_nm),
                "driver_total_brake_request_nm":0. if session.memory.driver_command is None else sum(session.memory.driver_command.brake_torques_nm),
                "motor_current_a":list(electrical.motor_currents_a),"motor_torque_nm":list(electrical.motor_torques_nm),
                "interventions": {name: getattr(session.memory, name) for name in
                    ("slip_interventions", "yaw_interventions", "reserve_interventions", "regen_inhibited_updates",
                     "brake_redistribution_ticks", "maximum_brake_overshoot_nm", "load_interventions", "energy_interventions", "feedforward_interventions")}}

    def advance_chunk(self, session, *, ticks, expected_source_sha256, progress_callback=None):
        """At most10 simulated seconds. NO admission/lease/process calls here.

        The fixed future worker must bind ticks and the already admitted parent
        checkpoint to its reviewed manifest. A timeout loses only this staged chunk;
        it never automatically imports a partial file or advances coverage.
        """
        require(type(ticks) is int and 1 <= ticks <= MAX_CHUNK_TICKS, "Chunk tick bound exceeded")
        require(progress_callback is None or callable(progress_callback), "Progress callback must be callable")
        before = checkpoint(session)
        session = self.resume(before, expected_checkpoint_sha256=before["checkpoint_sha256"], expected_source_sha256=expected_source_sha256)
        require(session.status == "running", "A terminal course cell cannot resume")
        require(session.segment < 750, "No remaining chunk/checkpoint chain slots")
        source_before = self.source_identity()
        require(source_before["sha256"] == expected_source_sha256, "Source differs from reviewed action")
        _, _, dependencies = self.make_context(session.context["course"]["id"], session.context["mode"], source_before, session.config_id,
            expected_source_sha256=expected_source_sha256)
        settings, heat, policy, act, env, track, driver = dependencies
        # allocate() reads only this case's policy constraints, never its duration.
        # Describe one fixed10ms allocator period, NOT the full mission in this
        # legacy rollout DTO. The unchanged mission horizon/work limits above and
        # original wall-clock guards still bound actual integration independently.
        case = core_adapter.case_for(session.config_id)
        start_tick = session.tick
        start_work = session.state.thermal.light.powered.integration_trials + session.state.thermal.light.powered.wheel_stop_events
        end_tick = min(start_tick + ticks, session.context["limits"]["maximum_ticks"])
        rows = []
        observation = None
        try:
            observation = self._observe(session, dependencies)
            rows.append(self._row(session, observation))  # Explicit boundary row; fixed20ms logging still uses GLOBAL ticks.
            while session.tick < end_tick:
                old = session
                projection, physical, _, _, source_projection = observation
                m = old.memory
                point = old.state.thermal.light.powered.plant
                if old.tick % 50 == 0:
                    slack = racing_geometry.footprint_clearance(track.frame,(point.x_m,point.y_m,point.heading_rad),
                        front_m=track.parameters["front_extent_m"],rear_m=track.parameters["rear_extent_m"],
                        width_m=track.parameters["vehicle_width_m"],margin_m=track.parameters["safety_margin_m"]+track.parameters["map_uncertainty_m"])
                    command, _ = _controller(track, settings.forces.plant, env, driver, point, projection, slack)
                    command=awd_fixture.normalize_driver_command(command)
                    m = replace(m, driver_command=command, driver_updates=m.driver_updates + 1)
                require(m.driver_command is not None, "Missing saved fixed-clock driver command")
                m = replace(m, steer=m.driver_command.steering_angles_rad)
                if old.tick % 10 == 0:
                    allocation = core_adapter.allocate_core(session.config_id,
                        old.state.thermal.light.powered, physical, m.steer, sum(m.driver_command.drive_torques_nm),
                        sum(m.driver_command.brake_torques_nm), m.integral, settings.forces.plant, act, case, .01)
                    audit = allocation.diagnostics
                    m=replace(m,last_allocation=audit,
                        load_interventions=m.load_interventions+int(audit.get("load_changed",False)),
                        energy_interventions=m.energy_interventions+int(audit.get("energy_changed",False)),
                        feedforward_interventions=m.feedforward_interventions+int(session.context["controller_policy"]["torque"]=="feedforward_off" and audit.get("yaw_changed",False)))
                    m = replace(m, requested=allocation.requested, proposed=allocation.proposed, held=allocation.limited.wheel_torques_nm,
                                integral=allocation.integral, raw_regen=allocation.raw_regen, total_brake=allocation.total_brake,
                                allocator_updates=m.allocator_updates + 1,
                                slip_interventions=m.slip_interventions + int(audit.get("slip_binding", False)),
                                yaw_interventions=m.yaw_interventions + int(audit.get("yaw_changed", False)),
                                reserve_interventions=m.reserve_interventions + int(audit.get("reserve_binding", False)),
                                regen_inhibited_updates=m.regen_inhibited_updates + int(audit["regen_inhibited"]))
                if point.u_mps <= 2:
                    m = replace(m, held=tuple(max(0., v) for v in m.held))
                _, _, electrical = evaluate_thermal_light(settings, heat, act, old.state.thermal, m.held, m.steer,
                    ZERO, AVAILABLE, env, aero_mode=old.state.drs.actual_mode)
                friction, blend = core_adapter.brake_blend(m.total_brake, m.raw_regen, electrical)
                require(blend["shortfall_nm"] <= 1e-6, "Common friction authority cannot meet demanded braking; no candidate-only relaxation")
                m = replace(m, friction=friction, blend_updates=m.blend_updates + 1,
                            electrical_limit_ticks=m.electrical_limit_ticks + int(bool(electrical.constraints)),
                            generating_boundaries=m.generating_boundaries + int(electrical.pack_power_w < 0),
                            brake_redistribution_ticks=m.brake_redistribution_ticks + int(blend["redistributed"]),
                            maximum_brake_overshoot_nm=max(m.maximum_brake_overshoot_nm, blend["overshoot_nm"]),
                            previous_progress=projection.station_m)
                previous_work = old.state.thermal.light.powered.integration_trials + old.state.thermal.light.powered.wheel_stop_events
                remaining_work = min(MAX_CHUNK_WORK - (previous_work - start_work),
                                     session.context["limits"]["maximum_work"] - previous_work)
                updated = advance_tick(settings, heat, policy, act, old.state, m.held, m.steer,
                    friction, env, braking_requested=m.total_brake > 0, maximum_work=remaining_work)
                prospective = replace(old, state=updated, memory=m, tick=old.tick + 1)
                try:
                    require(prospective.tick == updated.drs.ticks == updated.thermal.thermal.ticks == updated.thermal.light.feedback_ticks,
                            "Plant/controller state clock disagreement")
                    work = updated.thermal.light.powered.integration_trials + updated.thermal.light.powered.wheel_stop_events
                    require(work - start_work <= MAX_CHUNK_WORK, "Chunk work ceiling exceeded")
                    next_observation = self._observe(prospective, dependencies)
                except (ValueError, ArithmeticError) as error:
                    session = replace(old, status="invalid", violation=str(error),
                                      rejected_state=_rejected_attempt(old, updated, m, "post_step_domain_validation"))
                    break
                pack0 = old.state.thermal.light.powered.pack_energy_j
                pack1 = updated.thermal.light.powered.pack_energy_j
                new_projection, new_physical, _, _, new_source_projection = next_observation
                m = replace(m, previous_progress=new_projection.station_m, source_progress_m=new_source_projection.station_m,
                            sampled_draw_j=m.sampled_draw_j + max(0., pack0 - pack1),
                            sampled_recovery_j=m.sampled_recovery_j + max(0., pack1 - pack0),
                            maximum_slip=max(m.maximum_slip, max(abs(w.slip_ratio) for w in new_physical.wheels)),
                            maximum_utilization=max(m.maximum_utilization, max(w.force_utilization for w in new_physical.wheels)),
                            maximum_yaw=max(m.maximum_yaw, abs(updated.thermal.light.powered.plant.yaw_rate_rad_s)))
                prospective = replace(prospective, memory=m)
                try:
                    events=gate_ledger.crossing(old.lap_crossings,tick=prospective.tick,
                        before_pose=(point.x_m,point.y_m),after_pose=(updated.thermal.light.powered.plant.x_m,updated.thermal.light.powered.plant.y_m),
                        before_pack=pack0,after_pack=pack1,state=asdict(updated),memory=asdict(m),before_state=asdict(old.state),source_sha256=expected_source_sha256,
                        source_length_m=track.source_track.length_m,source_before_m=source_projection.station_m,
                        source_after_m=new_source_projection.station_m,gate=track.gate)
                    prospective=replace(prospective,lap_crossings=events)
                except (ValueError,ArithmeticError) as error:
                    session = replace(old, status="invalid", violation=str(error),
                                      rejected_state=_rejected_attempt(old, updated, m, "physical_gate_validation"))
                    break
                session = prospective
                observation = next_observation
                if len(session.lap_crossings)==session.context['laps_target']:
                    seam=session.lap_crossings[-1]['crossing']
                    session = replace(session, status="diagnostic_complete" if session.context["mode"] == "start_qualification" else "completed", finish=seam)
                elif session.tick == session.context["limits"]["maximum_ticks"]:
                    session = replace(session, status="diagnostic_complete" if session.context["mode"] == "start_qualification" else "time_limit")
                if session.tick % 20 == 0 or session.status != "running":
                    rows.append(self._row(session, observation))
                if progress_callback is not None and session.tick % 100 == 0:
                    progress_callback({"tick": session.tick, "progress_m": new_projection.station_m})
                if session.status != "running":
                    break
        except (ValueError, ArithmeticError) as error:
            session = replace(session, status="invalid", violation=str(error))
        if observation is not None and (not rows or rows[-1]["tick"] != session.tick):
            rows.append(self._row(session, observation))
        require(len(rows) <= MAX_CHUNK_ROWS, "Chunk logging row cap exceeded")
        after = checkpoint(replace(session, segment=session.segment + 1, parent_chunk_sha256=None))
        # Acyclic chain: checkpoint names the preceding chunk, not its own digest.
        # The next call receives the hash of THIS chunk explicitly via accept_chunk.
        body = {"schema": CHUNK_SCHEMA, "source_sha256": expected_source_sha256,
                "config_id": session.config_id, "course_id": session.context["course"]["id"],
                "context_sha256": session.context_sha256, "start_tick": start_tick, "end_tick": session.tick,
                "parent_chunk_sha256": session.parent_chunk_sha256, "input_checkpoint_sha256": before["checkpoint_sha256"],
                "output_checkpoint": after, "telemetry": rows,
                "status": session.status, "execution_evidence": "RAW_STAGED_REQUIRES_SEPARATE_OWNED_RECEIPT_ADMISSION",
                "awards": {"points": None, "overall_winner": None}}
        require(len(canonical(body).encode()) <= MAX_CHUNK_BYTES, "Chunk output cap exceeded")
        value = {"chunk": body, "chunk_sha256": digest(body)}
        try:
            require(self.source_identity() == source_before, "Source drift: do not accept this chunk")
        except Exception as error:
            raise RawOutputQuarantined(artifact_kind="raw_chunk", artifact=value,
                                       expected_source_sha256=expected_source_sha256, error=error) from error
        return value

    def accept_chunk(self, value, *, expected_input_checkpoint, expected_source_sha256):
        """Numerical consistency/linking inside an externally admitted operation.

        The genuine owner must admit inputs/operation and own the live allocation
        before calling this validator, including during exact replay. The linked
        Session is still RAW: successful original execution/cleanup receipt
        admission is required before adopting it as an authorised next parent or
        campaign result. Do not perform numerical validation in a post-cleanup
        receipt callback. This method verifies no OS/tool permission or receipt.
        """
        require(type(value) is dict and set(value) == {"chunk", "chunk_sha256"} and
                digest(value["chunk"]) == value["chunk_sha256"], "Chunk hash mismatch")
        body = value["chunk"]
        require(type(body) is dict and set(body) == {"schema", "source_sha256", "config_id", "course_id", "context_sha256",
                "start_tick", "end_tick", "parent_chunk_sha256", "input_checkpoint_sha256", "output_checkpoint", "telemetry",
                "status", "execution_evidence", "awards"} and
                body["execution_evidence"] == "RAW_STAGED_REQUIRES_SEPARATE_OWNED_RECEIPT_ADMISSION" and
                body["awards"] == {"points": None, "overall_winner": None}, "Exact raw-only chunk schema required")
        prior = self.resume(expected_input_checkpoint, expected_checkpoint_sha256=expected_input_checkpoint["checkpoint_sha256"],
                       expected_source_sha256=expected_source_sha256)
        require(prior.status == "running", "A failed or terminal course cell cannot be revived")
        require(body["schema"] == CHUNK_SCHEMA and body["source_sha256"] == expected_source_sha256 and
                body["input_checkpoint_sha256"] == expected_input_checkpoint["checkpoint_sha256"] and
                body["parent_chunk_sha256"] == prior.parent_chunk_sha256 and body["start_tick"] == prior.tick and
                body["course_id"] == prior.context["course"]["id"] and body["config_id"] == prior.config_id and
                body["context_sha256"] == prior.context_sha256, "Chunk course/source/order/parent mismatch")
        output = deepcopy(body["output_checkpoint"])
        require(output["checkpoint_sha256"] == digest(output["checkpoint"]), "Output checkpoint digest differs")
        require(type(body["start_tick"]) is int and type(body["end_tick"]) is int and
                output["checkpoint"]["parent_chunk_sha256"] is None,
                "Exact integer chunk clocks and unlinked raw output required")
        require(output["checkpoint"]["segment"] == prior.segment + 1 and output["checkpoint"]["tick"] == body["end_tick"] and
                prior.tick <= body["end_tick"] <= prior.tick + MAX_CHUNK_TICKS, "Chunk extent differs")
        require(output["checkpoint"]["config_id"] == prior.config_id and
                output["checkpoint"]["context_sha256"] == prior.context_sha256 and
                output["checkpoint"]["status"] == body["status"], "Output checkpoint identity/status differs")
        require(body["end_tick"] > prior.tick or body["status"] == "invalid", "Zero-work running chunk refused")
        require(type(body["telemetry"]) is list and len(body["telemetry"]) <= MAX_CHUNK_ROWS and
                len(canonical(body).encode()) <= MAX_CHUNK_BYTES, "Chunk trace bound exceeded")
        old_power = asdict(prior.state.thermal.light.powered)
        new_power = output["checkpoint"]["state"]["thermal"]["light"]["powered"]
        require_committed_work_transition(old_power, new_power, start_tick=prior.tick,
            end_tick=body["end_tick"], maximum_new_work=MAX_CHUNK_WORK)
        require(canonical(output['checkpoint']['lap_crossings'][:len(prior.lap_crossings)])==canonical(prior.lap_crossings),
                'Historical lap receipts were changed or reset')
        prior_memory = asdict(prior.memory)
        new_memory = output["checkpoint"]["memory"]
        require_clocked_counter_transition(prior_memory, new_memory, start_tick=prior.tick,
                                            end_tick=body["end_tick"])
        cumulative = ("driver_updates", "allocator_updates", "blend_updates", "slip_interventions",
            "electrical_limit_ticks", "generating_boundaries", "yaw_interventions", "reserve_interventions",
            "regen_inhibited_updates", "brake_redistribution_ticks", "sampled_draw_j", "sampled_recovery_j",
            "maximum_slip", "maximum_utilization", "maximum_yaw", "maximum_brake_overshoot_nm", "load_interventions", "energy_interventions", "feedforward_interventions")
        for name in cumulative:
            require(type(new_memory[name]) in (int, float) and isfinite(new_memory[name]) and
                    new_memory[name] >= prior_memory[name], "Chunk cumulative memory rolled back: " + name)
        expected_ticks = [prior.tick] + [tick for tick in range(prior.tick + 1, body["end_tick"] + 1) if tick % 20 == 0]
        if expected_ticks[-1] != body["end_tick"]:
            expected_ticks.append(body["end_tick"])
        if not body["telemetry"]:
            require(body["status"] == "invalid" and body["end_tick"] == prior.tick and
                    canonical(output["checkpoint"]["state"]) == canonical(asdict(prior.state)) and
                    canonical(output["checkpoint"]["memory"]) == canonical(asdict(prior.memory)),
                    "Only an explicit no-observation/no-advance invalid chunk can omit telemetry")
        else:
            require([row["tick"] for row in body["telemetry"]] == expected_ticks, "Exact global20ms plus boundary trace inventory required")
        previous = prior.tick - 1
        intervention_fields = ("slip_interventions", "yaw_interventions", "reserve_interventions", "regen_inhibited_updates",
                               "brake_redistribution_ticks", "maximum_brake_overshoot_nm", "load_interventions", "energy_interventions", "feedforward_interventions")
        previous_interventions = {name: prior_memory[name] for name in intervention_fields}
        previous_work = old_power["integration_trials"] + old_power["wheel_stop_events"]
        previous_sample_tick = prior.tick
        final_work = new_power["integration_trials"] + new_power["wheel_stop_events"]
        for row in body["telemetry"]:
            _validate_row_schema(row, prior, self.fixture.settings.forces.plant)
            row_ticks = row["tick"] - previous_sample_tick
            require(row_ticks >= 0 and previous_work + row_ticks <= row["work"] <= final_work,
                    "Telemetry new work contradicts committed tick spacing or output")
            previous_work = row["work"]
            require(type(row) is dict and type(row["tick"]) is int and previous < row["tick"] <= body["end_tick"] and
                    row["t_s"] == row["tick"] * .001, "Chunk trace clocks/order differ")
            require(all(type(row[key]) in (int, float) and isfinite(row[key]) for key in
                        ("x_m", "y_m", "heading_rad", "u_mps", "v_mps", "progress_m", "pack_energy_j", "net_wh")),
                    "Nonfinite trace values")
            require(0 <= row["pack_energy_j"] <= 18_000_000 and
                    abs(row["net_wh"] - (9_000_000. - row["pack_energy_j"]) / 3600) <= ENERGY_RECORD_TOLERANCE_WH,
                    "Trace netWh contradicts its pack-energy sample")
            core_adapter.validate_awd_row(row,expected_configuration_sha256=prior.context['configuration_sha256'])
            require(canonical(row["controller_policy"]) == canonical(prior.context["controller_policy"]),
                    "Trace controller policy differs from exact selected registry entry")
            require(type(row['source_progress_m']) in (int,float) and isfinite(row['source_progress_m']) and
                type(row['reference_progress_m']) in (int,float) and isfinite(row['reference_progress_m']) and
                row['reference_geometry_sha256']==prior.context['reference_line']['reference_geometry_sha256'] and
                row['lap_distance_m']==row['source_progress_m']%prior.context['course']['length_m'],
                'Separate finite source/reference coordinates required;no mixed-distance replay')
            require(type(row["interventions"]) is dict and set(row["interventions"]) == set(intervention_fields),
                    "Exact intervention row fields required")
            for name in intervention_fields:
                observed_intervention = row["interventions"][name]
                numeric = type(observed_intervention) in (int, float) if name == "maximum_brake_overshoot_nm" else type(observed_intervention) is int
                require(numeric and isfinite(observed_intervention) and previous_interventions[name] <= observed_intervention <= new_memory[name],
                        "Trace intervention counter/maximum is invalid or nonmonotonic")
                if name in ALLOCATOR_INTERVENTION_FIELDS:
                    updates = (boundary_counts(row["tick"])["allocator_updates"] -
                               boundary_counts(previous_sample_tick)["allocator_updates"])
                    require(observed_intervention - previous_interventions[name] <= updates,
                            "Trace policy intervention increased without an allocator event")
                elif name == "brake_redistribution_ticks":
                    require(observed_intervention - previous_interventions[name] <= row_ticks,
                            "Trace brake redistribution exceeds committed intervals")
            previous_interventions = row["interventions"]
            previous_sample_tick = row["tick"]
            previous = row["tick"]
        if body["telemetry"]:
            point = output["checkpoint"]["state"]["thermal"]["light"]["powered"]
            row = body["telemetry"][-1]
            require(row["tick"] == body["end_tick"] and row["pack_energy_j"] == point["pack_energy_j"] and
                    all(row[key] == point["plant"][key] for key in ("x_m", "y_m", "heading_rad", "u_mps", "v_mps")),
                    "Trace endpoint disagrees with accepted state")
            first = body["telemetry"][0]
            require(first['source_progress_m']==prior.memory.source_progress_m and
                row['source_progress_m']==new_memory['source_progress_m'] and
                first['reference_progress_m']==prior.memory.previous_progress and
                row['reference_progress_m']==new_memory['previous_progress'],'Coordinate row endpoints differ from complete controller state')
            require(first["interventions"] == {name: prior_memory[name] for name in intervention_fields} and
                    row["interventions"] == {name: new_memory[name] for name in intervention_fields},
                    "Trace intervention endpoints disagree with saved checkpoint memory")
            require(first["pack_energy_j"] == old_power["pack_energy_j"] and
                    all(first[key] == old_power["plant"][key] for key in ("x_m", "y_m", "heading_rad", "u_mps", "v_mps")) and
                    first["work"] == old_power["integration_trials"] + old_power["wheel_stop_events"] and
                    row["work"] == new_power["integration_trials"] + new_power["wheel_stop_events"],
                    "Trace start/work disagrees with parent checkpoint")
        output["checkpoint"]["parent_chunk_sha256"] = value["chunk_sha256"]
        output["checkpoint_sha256"] = digest(output["checkpoint"])
        accepted = self.resume(output, expected_checkpoint_sha256=output["checkpoint_sha256"],
                               expected_source_sha256=expected_source_sha256)
        if body["telemetry"]:
            _, _, dependencies = self.make_context(prior.context["course"]["id"], prior.context["mode"],
                                                   self.source_identity(), prior.config_id,
                                                   expected_source_sha256=expected_source_sha256)
            expected_first = self._row(prior, self._observe(prior, dependencies))
            expected_last = self._row(accepted, self._observe(accepted, dependencies))
            require(canonical(body["telemetry"][0]) == canonical(expected_first) and
                    canonical(body["telemetry"][-1]) == canonical(expected_last),
                    "Complete telemetry endpoints differ from accepted state/memory/observations")
            for row in body["telemetry"]:
                expected_laps = sum(event["boundary_tick"] <= row["tick"] for event in accepted.lap_crossings)
                require(row["completed_laps"] == expected_laps, "Saved lap count differs from physical gate history")
        return accepted

    def cell_summary(self, initial_checkpoint, chunks, *, expected_source_sha256):
        """Assemble one RAW course cell; independent receipt admission still required."""
        require(type(chunks) is list and 1 <= len(chunks) <= 750, "Finite ordered chunks required")
        session = self.resume(initial_checkpoint, expected_checkpoint_sha256=initial_checkpoint["checkpoint_sha256"],
                         expected_source_sha256=expected_source_sha256)
        require(session.tick == session.segment == 0 and session.context["mode"] in ("one_lap","ten_laps_nominal","ten_laps_low_grip"), "Fresh continuous trajectory origin required")
        hashes = []
        for record in chunks:
            session = self.accept_chunk(record, expected_input_checkpoint=checkpoint(session), expected_source_sha256=expected_source_sha256)
            hashes.append(record["chunk_sha256"])
        powered = session.state.thermal.light.powered
        complete = session.status == "completed" and session.finish is not None
        pack = session.finish["pack_energy_j"] if complete else powered.pack_energy_j
        return {"family": BRIDGE_FAMILY, "source_sha256": expected_source_sha256,
                "course_id": session.context["course"]["id"], "geometry_sha256": session.context["course"]["geometry_sha256"],
                "config_id": session.config_id, "context_sha256": session.context_sha256,
                "status": session.status, "completed": complete, "violation": session.violation,
                "campaign_eligible": False, "official_scoring_eligible": False,
                "clearance_scope": "Actual vehicle footprint sampled at10ms;continuous swept clearance UNVERIFIED",
                "lap_time_s": session.finish["time_s"] if complete and session.context['laps_target']==1 else None,
                "total_time_s":session.finish["time_s"] if complete else None,
                "completed_laps":len(session.lap_crossings),"required_laps":session.context['laps_target'],
                "lap_crossings":deepcopy(session.lap_crossings),
                "elapsed_s": session.tick * .001, "net_battery_wh": (9_000_000. - pack) / 3600,
                "sampled_draw_wh_1ms": session.memory.sampled_draw_j / 3600,
                "sampled_recovered_wh_1ms": session.memory.sampled_recovery_j / 3600,
                "sampled_energy_scope": "1ms net increments,not exact separate gross energy integrals",
                "chunk_sha256": hashes, "execution_evidence": "RAW_COMPLETE_PENDING_RECEIPTS" if complete else "RAW_INCOMPLETE",
                "awards": {"points": None, "fastest": None, "least_energy": None, "overall_winner": None}}
