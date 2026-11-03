"""Isolated UNQUALIFIED four-independent-motor AWD FSI bridge, version1.

The existing stadium core and frozen campaign are read-only dependencies.
Only metadata commands are exposed here. An independently reviewed owned worker
must supply admission, the original lease, deadlines and receipt-bound checkpoint
provenance before calling advance_chunk. Hashes establish consistency, not trust.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, dataclass, fields, replace
from hashlib import sha256
import json
from math import atan2, ceil, isfinite
from pathlib import Path

from lapsim.courses.course_bundle import CourseBundle, course_geometry_sha256
from lapsim.dynamics.planar import PlanarControls, PlanarState
from lapsim.dynamics.powered_planar import PoweredState, energy_residual_j
from lapsim.dynamics.torque_light_combined import CombinedLightState, advance_combined_light, initialize_combined_light
from lapsim.dynamics.torque_light_drs import DrsSignals, DrsState
from lapsim.dynamics.torque_light_powered import LightPoweredState
from lapsim.dynamics.torque_light_thermal import LumpedTireThermalState, ThermalLightPoweredState, evaluate_thermal_light
from lapsim.experiments import torque_light_demo as stadium
import core_adapter
import awd_fixture
import core_registry
import gate_ledger
import line_binding
import racing_geometry
from lapsim.optimization.pose_driver import _assumed_footprint_slack, _controller, _project_local, _reference_start_heading

BRIDGE_FAMILY = "lapsim.torque-light-awd-racingline-standing-development.v1"
PLAN_SCHEMA = "lapsim.torque-light-awd-plan.v1"
CHECKPOINT_SCHEMA = "lapsim.torque-light-awd-racingline-standing-checkpoint.v1"
CHUNK_SCHEMA = "lapsim.torque-light-awd-racingline-standing-chunk.v1"
BASE_SOURCE_SHA256 = "066ad8c951973f33c1f5c30d77d9054d700c3e3a52785c229355b646bb57b6e5"
COURSE_IDS = ("amz_fssim_fsi_approx",)

POLICY_IDS = core_registry.IDS
MAX_CHUNK_TICKS = 10_000  # ten simulated seconds, not a wall-time allowance
MAX_CHUNK_WORK = 50_000
MAX_MISSION_TICKS = 1_030_000
MAX_MISSION_WORK = 8_240_000
MAX_CHUNK_ROWS = 502
MAX_CHUNK_BYTES = 2 * 1024 * 1024
MAX_CHECKPOINT_BYTES = 256 * 1024
ENERGY_RECORD_TOLERANCE_WH = 1e-9  # Serialized arithmetic consistency,not physical accuracy.
MODES = ("one_lap",)  # Short qualification/smoke chunks use the same frozen FSI mission profile.
TEN_LAP_CONFIGS = core_registry.IDS
ZERO = stadium.ZERO
AVAILABLE = awd_fixture.AVAILABLE


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def is_sha256(value):
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def read_json(path, limit):
    path = Path(path)
    require(not path.is_symlink(), "File alias refused")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, "Bounded JSON input exceeded")
    value = json.loads(raw, object_pairs_hook=_unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    canonical(value)  # also rejects overflow-to-infinity numeric literals
    return raw, value


def registry():
    _, value = read_json(Path(__file__).with_name("registry-core.json"), 128 * 1024)
    core_registry.validate(value)
    require(tuple(row["id"] for row in value["courses"]) == COURSE_IDS, "Exact one-course development inventory required")
    require(tuple(row["id"] for row in value["policies"]) == POLICY_IDS, "Exact four-policy development inventory required")
    require(len({row["geometry_sha256"] for row in value["courses"]}) == 1, "Duplicate geometry")
    return value


def source_identity():
    base = stadium.source_identity()
    require(base["sha256"] == BASE_SOURCE_SHA256, "Qualified stadium dependency changed; do not transplant evidence")
    local = {}
    for name in ("light_core_bridge.py", "core_registry.py", "core_adapter.py", "registry-core.json", "awd_fixture.py", "policy_layers.py", "racing_geometry.py", "line_generator.py", "line_binding.py", "producer_receipts.py", "numeric_evidence.py", "gate_ledger.py", "baseline-configuration.json", "line-artifact.json", "line-artifact-admission.json", "producer-promotion-manifest.json"):
        path=Path(__file__).with_name(name)
        bound=2*1024*1024 if name=='line-artifact.json' else 1024*1024 if name=='line-artifact-admission.json' else 256*1024
        if name in ('line-artifact.json','line-artifact-admission.json','producer-promotion-manifest.json') and not path.exists():raise line_binding.LineUnavailable('Independently reviewed producer bundle missing;no centreline fallback')
        with path.open("rb") as stream:raw=stream.read(bound+1)
        require(len(raw) <= bound, "Bridge source exceeds explicit file bound")
        local[name] = sha256(raw).hexdigest()
    content = {"family": BRIDGE_FAMILY, "base_source_sha256": base["sha256"], "parent_bridge_sha256":"7755a5d52112ca2cb21b6beca4103e532d18b7ec833b6999db99870ebaa4b7b9", "bridge_files_sha256": local}
    return {**content, "sha256": digest(content)}


def load_course(course_id):
    require(type(course_id) is str and course_id in COURSE_IDS, "Course is outside the finite registry")
    row = next(row for row in registry()["courses"] if row["id"] == course_id)
    path = stadium.ROOT / "configs" / "courses" / (course_id + ".json")
    raw, _ = read_json(path, 4 * 1024 * 1024)
    require(sha256(raw).hexdigest() == row["bundle_sha256"], "Course bundle bytes differ from pinned registry")
    bundle = CourseBundle.load(path)
    require(bundle.source_file_sha256 == row["bundle_sha256"] and bundle.course_id == course_id and bundle.track.closed and
            bundle.geometry_sha256 == row["geometry_sha256"] == course_geometry_sha256(bundle.track),
            "Course identity/closed geometry mismatch")
    require(abs(bundle.track.length_m - row["length_m"]) <= 1e-9 and 0 < bundle.track.length_m <= 2200,
            "Course length differs or exceeds mission domain")
    # No smoothing, generic loop substitution, direction reversal, or new scale.
    return bundle, row


def mission_limits(length_m, mode):
    require(type(length_m) in (int, float) and isfinite(length_m) and 0 < length_m <= 2200,
            "Finite supported length required")
    require(mode in MODES, "Unsupported mission mode")
    if mode == "start_qualification":
        return {"maximum_ticks": 250, "maximum_work": 5000, "logging_ticks": 20}
    # A declared timeout heuristic, not a prediction or a guaranteed minimum speed.
    ticks = (ceil(length_m / 3.) + 30) * 1000 * (10 if mode.startswith("ten_laps_") else 1)
    require(ticks <= MAX_MISSION_TICKS, "Mission horizon exceeds fixed bound")
    return {"maximum_ticks": ticks, "maximum_work": min(8 * ticks, MAX_MISSION_WORK), "logging_ticks": 20}


def make_context(course_id, mode, source, config_id, *, expected_source_sha256):
    require(type(source) is dict and source.get('sha256')==expected_source_sha256 and
        digest({key:value for key,value in source.items() if key!='sha256'})==expected_source_sha256,
        'Reviewed consumer source identity required before line binding')
    require(course_id=="amz_fssim_fsi_approx" and config_id in TEN_LAP_CONFIGS, "Finite nominal FSI four-independent AWD OFF candidate only")
    settings, heat, policy, act, env, _, original_driver = awd_fixture.fixture()
    laps_target=10 if mode.startswith('ten_laps_') else 1
    friction_multiplier=.35 if mode=='ten_laps_low_grip' else 1.
    env=replace(env,road=replace(env.road,base_friction_multiplier=friction_multiplier))
    core_adapter.ensure_topology(act, AVAILABLE)
    selected_policy = core_registry.entry(config_id)
    bundle, row = load_course(course_id)
    # initialize() has already compared the entire source identity, including
    # this promotion digest, to the independently reviewed consumer action.
    track = line_binding.load(bundle.track,reviewed_promotion_sha256=source['bridge_files_sha256']['producer-promotion-manifest.json'])
    limits = mission_limits(track.length_m, mode)
    driver = replace(awd_fixture.standing_driver(original_driver), target_progress_m=track.length_m*laps_target,
                     maximum_simulated_time_s=limits["maximum_ticks"] * .001,
                     # Legacy DTO is a bounded chunk view, not the independent cumulative mission/controller clock.
                     maximum_control_steps=500 if mode.startswith('ten_laps_') else max(1,ceil(limits['maximum_ticks']/10)),
                     # This existing settings field is a per-chunk work ceiling;
                     # the independent cumulative mission ceiling is below.
                     maximum_internal_substeps=MAX_CHUNK_WORK,
                     reference_geometry="sampled_polyline",
                     assumed_half_width_m=bundle.default_ai_half_width_m,
                     vehicle_width_m=bundle.default_ai_vehicle_width_m,
                     safety_margin_m=bundle.default_ai_margin_m)
    racing_configuration_sha256=awd_fixture.verify_racing_configuration(settings,heat,policy,act,env,driver,track.provenance)
    point = PlanarState(x_m=track.x_m[0], y_m=track.y_m[0],
                        heading_rad=_reference_start_heading(track, driver),
                        u_mps=0., wheel_speeds_rad_s=(0.,) * 4)
    initial = PoweredState(point, ZERO, 9_000_000.)
    state = initialize_combined_light(settings, heat, policy, act, initial, env,
                                     initial_temperature_c=70., automatic_drs_enabled=True,
                                     load_longitudinal_mps2=0., load_lateral_mps2=0.)
    course = {"id": course_id, "label": bundle.label, "length_m": bundle.track.length_m,
              "geometry_sha256": bundle.geometry_sha256, "bundle_sha256": row["bundle_sha256"],
              "classification": row["classification"], "source_url": row["source_url"],
              "assumed_half_width_m": bundle.default_ai_half_width_m,
              "description": bundle.description, "provenance": bundle.to_dict()["provenance"]}
    context = {"family": BRIDGE_FAMILY, "component_family": stadium.FAMILY,
               "component_model_sha256": state.model_sha256, "source": source, "mode": mode,
               "course": course, "reference_line":track.provenance, "limits": limits, "clocks": dict(stadium.CLOCKS),
               "laps_target": laps_target,
               "experiment_scope": {
                   "kind": "separate_four_independent_AWD_FSI_development",
                   "original_regen_enabled_cell_status": "UNSUPPORTED_BELOW_2_MPS_WITH_RESIDUAL_GENERATION",
                   "not_a_repair_or_continuation_of_t01": True,
                   "regeneration_enabled": False,
                   "starting_state_rule": "Every policy starts at exact vehicle and wheel standstill with zero actuator/controller memory; never import flying-start or partial outputs",
                   "friction_authority": "Provisional simulated four-wheel friction brakes, not verified team hydraulic actuator authority",
                   "energy_rule": "Original powered plant owns energy and actuator lag; no discarded residuals or posthoc correction",
                   "eligibility_rule": "Original residual_low_speed_regen and every other physical-domain check are unchanged"},
               "standing_start": {"vehicle_u_mps":0.,"vehicle_v_mps":0.,"yaw_rate_rad_s":0.,
                   "wheel_omega_rad_s":[0.]*4,"actuator_memory_nm":[0.]*4,"clock_s":0.,
                   "gate_rule":"Initial departure at the source gate is not a finish; a later forward finite-gate crossing after source progress >=75 percent is required",
                   "scope":"Synthetic stationary start; no measured driver reaction or car calibration"},
               "development_condition": {"surface_friction_multiplier":friction_multiplier,
                   "launch_ticks":200 if mode.startswith('ten_laps_') else 0,
                   "launch_requested_total_wheel_nm":190.,"launch_requested_friction_total_nm":0.,
                   "launch_scope":"No override;common explicit AWD total-wheel-torque demand.",
                   "provenance":"Synthetic sensitivity inputs;not measured tire mu or actual-car validation"},
               "settings": asdict(settings), "thermal": asdict(heat), "drs_policy": asdict(policy),
               "controller_policy": selected_policy,
               "brake_adapter": {"version": core_adapter.BLEND_VERSION, "per_wheel_capacity_nm": [80.] * 4,
                   "preferred_shares": list(core_adapter.SHARES), "redistribution": "Common weighted free-capacity; honest shortfall/overshoot",
                   "drive_availability": list(AVAILABLE), "friction_availability": [True] * 4},
               "actuation": asdict(act), "environment": asdict(env), "driver": asdict(driver),
               "initial_state": asdict(state), "initial_temperature_c": 70.,
               "profile": awd_fixture.RACING_PROFILE_ID, "configuration_sha256":racing_configuration_sha256,
               "base_configuration_sha256":awd_fixture.PROFILE_CONFIGURATION_SHA256,
               "base_configuration_scope":"Historical physical/driver parameter snapshot;its 5 m/s initializer is not the actual standing start",
               "motor_count":4, "drive_availability":list(AVAILABLE),
               "steering_model":"parallel_front_v1",
               "demand_contract":"Total wheel Nm,0..190;equal baseline four0.25 weights;one shared battery",
               "provenance": "New synthetic 4:1 four-independent-motor AWD fixture; provisional parameters,no measured-car fit",
               "team_ratio": "12.48:1 tentative, unknown efficiency/speed/topology, not substituted",
               "numerics": "1ms global load/DRS/thermal;50ms driver;10ms allocator;20ms log. Chunk boundaries do not reset clocks.",
               "counter_adapter": "Per-feedback-call work-counter view only; cumulative trials/substeps/stops restored exactly. Physical,energy,controller,thermal and DRS state never reset.",
               "energy": "Plant owns debit once; regen credit in net pack energy.1ms draw/recovery are net-increment sums.",
               "clearance_scope": "Actual vehicle rectangle checked at 10ms samples only;continuous swept clearance is not established.",
               "campaign_eligible": False,
               "receipt_boundary": "Checkpoint/trace is RAW until exact owned-worker/tool/cleanup provenance is independently admitted"}
    # Context is serialized metadata, not a physical dataclass. Normalize it at
    # creation so JSON roundtrips cannot change tuple/list equality. Explicit
    # physical/control tuple reconstruction remains in decode_state/decode_memory.
    context = json.loads(canonical(context))
    return context, state, (settings, heat, policy, act, env, track, driver)


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


def initialize(course_id, config_id, mode, *, expected_source_sha256):
    core_adapter.controller_for(config_id)
    source = source_identity()
    require(source["sha256"] == expected_source_sha256, "Unreviewed bridge source")
    context, state, _ = make_context(course_id, mode, source, config_id,expected_source_sha256=expected_source_sha256)
    return Session(config_id, context, digest(context), state, Memory())


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
    return {"checkpoint": body, "checkpoint_sha256": sha256(text.encode()).hexdigest()}


def resume(value, *, expected_checkpoint_sha256, expected_source_sha256):
    require(type(value) is dict and set(value) == {"checkpoint", "checkpoint_sha256"}, "Exact checkpoint envelope required")
    body = deepcopy(value["checkpoint"])
    require(value["checkpoint_sha256"] == expected_checkpoint_sha256 == digest(body), "Checkpoint provenance hash mismatch")
    require(len(canonical(body).encode()) <= MAX_CHECKPOINT_BYTES and body.pop("schema") == CHECKPOINT_SCHEMA, "Checkpoint size/schema differs")
    session = _construct(Session, body, state=decode_state(body["state"]), memory=decode_memory(body["memory"]), lap_crossings=tuple(body["lap_crossings"]))
    expected = initialize(session.context["course"]["id"], session.config_id, session.context["mode"],
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
        stadium.require(len(getattr(memory, name)) == 4 and all(type(v) in (int, float) and isfinite(v) for v in getattr(memory, name)),
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
    _,_,dependencies=make_context(session.context['course']['id'],session.context['mode'],source_identity(),session.config_id,
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


def _observe(session, dependencies):
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
    require(not stadium.residual_low_speed_regen(point.u_mps, electrical), "Unmodeled low-speed residual regen; cell ineligible")
    initial = decode_state(session.context["initial_state"]).thermal.light.powered
    residual = energy_residual_j(settings.forces.plant, initial, p)
    require(p.integration_trials + p.wheel_stop_events <= session.context["limits"]["maximum_work"], "Mission work budget exceeded")
    require(abs(residual) <= .002 + 128 * 2.220446049250313e-16 * act.pack_capacity_j * (p.integration_trials + session.tick + 1),
            "Mechanical energy residual exceeded")
    return projection, physical, electrical, residual, source_projection


def _row(session, observation):
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
            "base_configuration_sha256":awd_fixture.PROFILE_CONFIGURATION_SHA256,
            "motor_count":4,"drive_availability":list(AVAILABLE),
            "steering_rad":list(session.memory.steer),"baseline_weights":[.25]*4,
            "driver_total_drive_request_nm":0. if session.memory.driver_command is None else sum(session.memory.driver_command.drive_torques_nm),
            "driver_total_brake_request_nm":0. if session.memory.driver_command is None else sum(session.memory.driver_command.brake_torques_nm),
            "motor_current_a":list(electrical.motor_currents_a),"motor_torque_nm":list(electrical.motor_torques_nm),
            "interventions": {name: getattr(session.memory, name) for name in
                ("slip_interventions", "yaw_interventions", "reserve_interventions", "regen_inhibited_updates",
                 "brake_redistribution_ticks", "maximum_brake_overshoot_nm", "load_interventions", "energy_interventions", "feedforward_interventions")}}


def advance_tick(settings, heat, policy, act, state, held, steer, friction, env, *, braking_requested, maximum_work):
    """Local WORK-counter view for the unchanged integrator's absolute cap.

    Only three diagnostic counters are rebased; no integrated state, energy,
    clock, event dissipation or controller input is reset. A rejected interval
    returns nothing and cannot commit its provisional counters. This is an
    isolated new adapter requiring parity and high-counter regressions.
    """
    require(type(maximum_work) is int and 1 <= maximum_work <= MAX_CHUNK_WORK, "Per-call work remainder exceeded")
    previous = state.thermal.light.powered
    local_power = replace(previous, integration_trials=0, integration_substeps=0, wheel_stop_events=0)
    local_state = replace(state, thermal=replace(state.thermal, light=replace(state.thermal.light, powered=local_power)))
    updated = advance_combined_light(settings, heat, policy, act, local_state, held, steer, friction,
        AVAILABLE, env, braking_requested=braking_requested, maximum_work=maximum_work)
    power = updated.thermal.light.powered
    restored = replace(power, integration_trials=previous.integration_trials + power.integration_trials,
                       integration_substeps=previous.integration_substeps + power.integration_substeps,
                       wheel_stop_events=previous.wheel_stop_events + power.wheel_stop_events)
    return replace(updated, thermal=replace(updated.thermal, light=replace(updated.thermal.light, powered=restored)))


def advance_chunk(session, *, ticks, expected_source_sha256, progress_callback=None):
    """At most10 simulated seconds. NO admission/lease/process calls here.

    The fixed future worker must bind ticks and the already admitted parent
    checkpoint to its reviewed manifest. A timeout loses only this staged chunk;
    it never automatically imports a partial file or advances coverage.
    """
    require(type(ticks) is int and 1 <= ticks <= MAX_CHUNK_TICKS, "Chunk tick bound exceeded")
    require(progress_callback is None or callable(progress_callback), "Progress callback must be callable")
    before = checkpoint(session)
    session = resume(before, expected_checkpoint_sha256=before["checkpoint_sha256"], expected_source_sha256=expected_source_sha256)
    require(session.status == "running", "A terminal course cell cannot resume")
    source_before = source_identity()
    require(source_before["sha256"] == expected_source_sha256, "Source differs from reviewed action")
    _, _, dependencies = make_context(session.context["course"]["id"], session.context["mode"], source_before, session.config_id,
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
        observation = _observe(session, dependencies)
        rows.append(_row(session, observation))  # Explicit boundary row; fixed20ms logging still uses GLOBAL ticks.
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
                next_observation = _observe(prospective, dependencies)
            except (ValueError, ArithmeticError) as error:
                session = replace(old, status="invalid", violation=str(error), rejected_state=asdict(updated))
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
                session=replace(old,status='invalid',violation=str(error),rejected_state=asdict(updated));break
            session = prospective
            observation = next_observation
            if len(session.lap_crossings)==session.context['laps_target']:
                seam=session.lap_crossings[-1]['crossing']
                session = replace(session, status="diagnostic_complete" if session.context["mode"] == "start_qualification" else "completed", finish=seam)
            elif session.tick == session.context["limits"]["maximum_ticks"]:
                session = replace(session, status="diagnostic_complete" if session.context["mode"] == "start_qualification" else "time_limit")
            if session.tick % 20 == 0 or session.status != "running":
                rows.append(_row(session, observation))
            if progress_callback is not None and session.tick % 100 == 0:
                progress_callback({"tick": session.tick, "progress_m": new_projection.station_m})
            if session.status != "running":
                break
    except (ValueError, ArithmeticError) as error:
        session = replace(session, status="invalid", violation=str(error))
    if observation is not None and (not rows or rows[-1]["tick"] != session.tick):
        rows.append(_row(session, observation))
    require(len(rows) <= MAX_CHUNK_ROWS, "Chunk logging row cap exceeded")
    require(source_identity() == source_before, "Source drift: preserve staged output, do not accept this chunk")
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
    return {"chunk": body, "chunk_sha256": digest(body)}


def accept_chunk(value, *, expected_input_checkpoint, expected_source_sha256):
    """Consistency-only bridge AFTER an external owned-receipt admission.

    This function neither verifies OS/tool permissions nor promotes campaign
    coverage. Its caller must pin value's hash in an admitted successful receipt.
    """
    require(type(value) is dict and set(value) == {"chunk", "chunk_sha256"} and
            digest(value["chunk"]) == value["chunk_sha256"], "Chunk hash mismatch")
    body = value["chunk"]
    require(type(body) is dict and set(body) == {"schema", "source_sha256", "config_id", "course_id", "context_sha256",
            "start_tick", "end_tick", "parent_chunk_sha256", "input_checkpoint_sha256", "output_checkpoint", "telemetry",
            "status", "execution_evidence", "awards"} and
            body["execution_evidence"] == "RAW_STAGED_REQUIRES_SEPARATE_OWNED_RECEIPT_ADMISSION" and
            body["awards"] == {"points": None, "overall_winner": None}, "Exact raw-only chunk schema required")
    prior = resume(expected_input_checkpoint, expected_checkpoint_sha256=expected_input_checkpoint["checkpoint_sha256"],
                   expected_source_sha256=expected_source_sha256)
    require(prior.status == "running", "A failed or terminal course cell cannot be revived")
    require(body["schema"] == CHUNK_SCHEMA and body["source_sha256"] == expected_source_sha256 and
            body["input_checkpoint_sha256"] == expected_input_checkpoint["checkpoint_sha256"] and
            body["parent_chunk_sha256"] == prior.parent_chunk_sha256 and body["start_tick"] == prior.tick and
            body["course_id"] == prior.context["course"]["id"] and body["config_id"] == prior.config_id and
            body["context_sha256"] == prior.context_sha256, "Chunk course/source/order/parent mismatch")
    output = deepcopy(body["output_checkpoint"])
    require(output["checkpoint_sha256"] == digest(output["checkpoint"]), "Output checkpoint digest differs")
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
    for name in ("integration_trials", "integration_substeps", "wheel_stop_events"):
        require(type(new_power[name]) is int and new_power[name] >= old_power[name], "Chunk cumulative work counters rolled back")
    require(canonical(output['checkpoint']['lap_crossings'][:len(prior.lap_crossings)])==canonical(prior.lap_crossings),
            'Historical lap receipts were changed or reset')
    prior_memory = asdict(prior.memory)
    new_memory = output["checkpoint"]["memory"]
    cumulative = ("driver_updates", "allocator_updates", "blend_updates", "slip_interventions",
        "electrical_limit_ticks", "generating_boundaries", "yaw_interventions", "reserve_interventions",
        "regen_inhibited_updates", "brake_redistribution_ticks", "sampled_draw_j", "sampled_recovery_j",
        "maximum_slip", "maximum_utilization", "maximum_yaw", "maximum_brake_overshoot_nm", "load_interventions", "energy_interventions", "feedforward_interventions")
    for name in cumulative:
        require(type(new_memory[name]) in (int, float) and isfinite(new_memory[name]) and
                new_memory[name] >= prior_memory[name], "Chunk cumulative memory rolled back: " + name)
    delta_work = new_power["integration_trials"] + new_power["wheel_stop_events"] - old_power["integration_trials"] - old_power["wheel_stop_events"]
    require(0 <= delta_work <= MAX_CHUNK_WORK, "Accepted chunk exceeds its work allowance")
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
    for row in body["telemetry"]:
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
        previous_interventions = row["interventions"]
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
    return resume(output, expected_checkpoint_sha256=output["checkpoint_sha256"], expected_source_sha256=expected_source_sha256)


def cell_summary(initial_checkpoint, chunks, *, expected_source_sha256):
    """Assemble one RAW course cell; independent receipt admission still required."""
    require(type(chunks) is list and 1 <= len(chunks) <= 750, "Finite ordered chunks required")
    session = resume(initial_checkpoint, expected_checkpoint_sha256=initial_checkpoint["checkpoint_sha256"],
                     expected_source_sha256=expected_source_sha256)
    require(session.tick == session.segment == 0 and session.context["mode"] in ("one_lap","ten_laps_nominal","ten_laps_low_grip"), "Fresh continuous trajectory origin required")
    hashes = []
    for record in chunks:
        session = accept_chunk(record, expected_input_checkpoint=checkpoint(session), expected_source_sha256=expected_source_sha256)
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


