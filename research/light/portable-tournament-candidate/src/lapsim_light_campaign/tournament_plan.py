"""UNTESTED frozen seven-policy field construction; no worker or model calls.

Frozen behavior: canonical input declares every existing AWD/OFF policy's exact
identity and fresh origin. Only controller_policy may differ between contexts;
only config_id/context/context_sha256 may differ between initial checkpoints.
All state, memory, driver, line, source, environment and limits stay matched.
The plan fixes membership/order and finite mission request ceilings. It neither
creates origins nor proves physical validity, single-use execution or admission.
No I/O, provider lookup, bridge import, plant evolution or execution occurs here.
"""

from hashlib import sha256
from math import isfinite

from lapsim_light_policies import core_registry

from . import raw_journal as journal
from .input_contracts import decode, digest, encode, exact, is_sha256, require
from .stepping import MAX_MISSION_TICKS, MAX_MISSION_WORK


SCHEMA = "lapsim.light-seven-policy-field-plan.v1"
MAX_PLAN_BYTES = 2 * 1024 * 1024
CHECKPOINT_FIELDS = frozenset({
    "schema", "config_id", "context", "context_sha256", "state", "memory", "tick", "segment",
    "parent_chunk_sha256", "status", "violation", "finish", "rejected_state", "lap_crossings",
})


def _finite(value):
    return type(value) in (int, float) and isfinite(value)


def _fresh_memory():
    """Canonical defaults of this pinned bridge's Memory, without importing it."""
    value = {name: [0.] * 4 for name in ("requested", "proposed", "held", "steer", "friction")}
    value.update({name: 0. for name in (
        "total_brake", "raw_regen", "integral", "previous_progress", "source_progress_m",
        "sampled_draw_j", "sampled_recovery_j", "maximum_slip", "maximum_utilization", "maximum_yaw",
        "maximum_brake_overshoot_nm",
    )})
    value.update({name: 0 for name in (
        "load_interventions", "energy_interventions", "feedforward_interventions", "driver_updates",
        "allocator_updates", "blend_updates", "slip_interventions", "electrical_limit_ticks", "generating_boundaries",
        "yaw_interventions", "reserve_interventions", "regen_inhibited_updates", "brake_redistribution_ticks",
    )})
    return {**value, "driver_command": None, "last_allocation": None}


def _unused_state(state, memory):
    """Known initial clocks/ledgers only; not numerical model reconstruction."""
    thermal, drs = state["thermal"], state["drs"]
    light, heat = thermal["light"], thermal["thermal"]
    power = light["powered"]
    counters = (drs["ticks"], drs["pending_open_ticks"], heat["ticks"], light["feedback_ticks"],
                power["integration_substeps"], power["integration_trials"], power["wheel_stop_events"])
    require(all(type(value) is int and value == 0 for value in counters), "Initial component/work clocks must all be zero")
    ledger = [power[name] for name in (
        "wheel_work_j", "conversion_loss_j", "contact_dissipation_j", "friction_brake_work_j", "external_work_j",
        "driver_proxy_impulse_ns", "tire_longitudinal_impulse_ns", "absolute_contact_force_error_ns", "wheel_stop_dissipation_j",
    )]
    ledger += [light["load_longitudinal_mps2"], light["load_lateral_mps2"],
               heat["absorbed_slip_heat_j"], heat["heat_to_ambient_j"], thermal["last_contact_slip_energy_j"]]
    require(all(_finite(value) and value == 0 for value in ledger) and
            state["automatic_drs_enabled"] is True and state["last_signals"] is None and
            drs["commanded_mode"] == drs["actual_mode"] == light["aero_mode"] == "closed" and
            drs["reason"] == "initialized_closed" and heat["temperature_c"] == 70. and
            encode(memory) == encode(_fresh_memory()), "Exact unused controller memory and initial component ledgers required")


def _origin_parts(declaration, policy_id):
    exact(declaration, {"identity", "origin"}, "field origin declaration")
    identity, origin = declaration["identity"], declaration["origin"]
    journal._validate_identity(identity)
    journal._origin(origin, identity)
    body = origin["checkpoint"]
    exact(body, CHECKPOINT_FIELDS, "field initial checkpoint")
    context, state, memory = body["context"], body["state"], body["memory"]
    require(identity["policy_id"] == policy_id and body["config_id"] == policy_id and
            encode(context["controller_policy"]) == encode(core_registry.entry(policy_id)),
            "Exact source registry policy required; no per-cell retuning")
    require(body["violation"] is None and body["finish"] is None and body["rejected_state"] is None and
            type(body["lap_crossings"]) is list and not body["lap_crossings"] and
            encode(state) == encode(context["initial_state"]), "Unused initial state/history required")
    require(context["family"] == "lapsim.portable-awd-standing-numerical-bridge.v1" and
            context["course"]["id"] == "amz_fssim_fsi_approx" and context["mode"] == "one_lap" and
            type(context["laps_target"]) is int and context["laps_target"] == 1 and
            context["qualification_or_execution_authority"] is False,
            "Only the existing FSI nominal one-lap development mission is supported")
    require(context["source"]["numerical_environment_sha256"] == identity["environment_sha256"] and
            is_sha256(context["source"]["source_manifest_sha256"]), "Source/environment declarations differ")
    expected_standing = {"vehicle_u_mps": 0., "vehicle_v_mps": 0., "yaw_rate_rad_s": 0.,
                         "wheel_omega_rad_s": [0.] * 4, "actuator_memory_nm": [0.] * 4, "clock_s": 0.}
    require(encode(context["standing_start"]) == encode(expected_standing) and
            encode(context["clocks"]) == encode({"plant_period_s": .001, "driver_interval_ticks": 50,
                                                "allocator_interval_ticks": 10, "logging_interval_ticks": 20}),
            "Existing standing-start and independent clock declarations required")
    power = state["thermal"]["light"]["powered"]
    _unused_state(state, memory)
    plant = power["plant"]
    require(all(_finite(plant[name]) and plant[name] == 0 for name in ("u_mps", "v_mps", "yaw_rate_rad_s")) and
            encode(plant["wheel_speeds_rad_s"]) == encode([0.] * 4) and
            encode(power["actuator_memory_nm"]) == encode([0.] * 4) and memory["driver_command"] is None,
            "No moving-start or pre-existing held driver command")
    require(_finite(power["pack_energy_j"]) and power["pack_energy_j"] == 9_000_000.,
            "Existing standing-origin pack energy required; no per-policy reset change")
    limits = context["limits"]
    exact(limits, {"maximum_ticks", "maximum_work", "logging_ticks"}, "field mission limits")
    require(type(limits["maximum_ticks"]) is int and 1 <= limits["maximum_ticks"] <= MAX_MISSION_TICKS and
            type(limits["maximum_work"]) is int and 1 <= limits["maximum_work"] <= MAX_MISSION_WORK and
            type(limits["logging_ticks"]) is int and limits["logging_ticks"] == 20,
            "Finite existing mission ceilings required")
    common_identity = {key: value for key, value in identity.items() if key != "policy_id"}
    common_context = {key: value for key, value in context.items() if key != "controller_policy"}
    common_origin = {key: value for key, value in body.items()
                     if key not in ("config_id", "context", "context_sha256")}
    return common_identity, common_context, common_origin


def _build(origins, policy_order):
    exact(origins, journal.POLICIES, "complete seven-policy field")
    require(type(policy_order) in (list, tuple), "Explicit native policy order required")
    order = tuple(policy_order)
    require(len(order) == len(journal.POLICIES) and all(type(policy) is str for policy in order) and
            set(order) == set(journal.POLICIES), "Each source policy must appear once in the frozen order")
    baseline = None
    cells = []
    for policy_id in order:
        parts = _origin_parts(origins[policy_id], policy_id)
        if baseline is None:
            baseline = parts
        require(all(encode(part) == encode(expected) for part, expected in zip(parts, baseline)),
                "Unmatched field: source/car/line/driver/environment/limits/state/memory differ")
        declaration = origins[policy_id]
        cells.append({"policy_id": policy_id, "identity": declaration["identity"], "origin": declaration["origin"]})
    common_identity, common_context, common_origin = baseline
    limits = common_context["limits"]
    body = {
        "schema": SCHEMA, "origins_raw_sha256": sha256(encode(origins)).hexdigest(),
        "policy_order": list(order), "cells": cells, "shared_identity": common_identity,
        "shared_context_sha256": digest(common_context), "shared_initial_checkpoint_sha256": digest(common_origin),
        "request_ceilings": {"cells": len(cells), "parallel_workers": 1,
                             "maximum_total_simulated_ticks": len(cells) * limits["maximum_ticks"],
                             "maximum_total_work": len(cells) * limits["maximum_work"],
                             "scope": "CONSERVATIVE_MISSION_REQUEST_NOT_ALLOCATION_OR_MEASURED_COST"},
        "status": "FROZEN_RAW_ORIGIN_FIELD_PENDING_ORIGINAL_VALIDATION",
        "physical_validation_performed": False, "single_attempt_exclusivity_authenticated": False,
        "qualification_or_execution_authority": False, "campaign_eligible": False,
        "official_points": None, "overall_winner": None,
    }
    envelope = {"plan": body, "plan_sha256": digest(body)}
    require(len(encode(envelope)) <= MAX_PLAN_BYTES, "Frozen field exceeds its explicit transport bound")
    return envelope


def freeze_tournament(origins_raw, *, expected_origins_raw_sha256, policy_order=journal.POLICIES):
    """Freeze actual supplied origins; never create or numerically validate them.

    origins_raw is canonical JSON mapping all seven policy IDs to exactly
    {identity, origin}. The returned digest identifies content, not a new lease,
    fresh challenge, launch permit or proof that only one attempt ever occurred.
    """
    origins = decode(origins_raw, MAX_PLAN_BYTES, canonical=True)
    require(is_sha256(expected_origins_raw_sha256) and
            sha256(origins_raw).hexdigest() == expected_origins_raw_sha256, "Origin input byte identity differs")
    try:
        return _build(origins, policy_order)
    except (KeyError, TypeError, IndexError, OverflowError) as error:
        raise ValueError("Malformed frozen field origin metadata") from error


def validate_tournament_plan(plan_raw, *, expected_plan_sha256):
    """Reconstruct the exact plan from its original inputs, without any work."""
    value = decode(plan_raw, MAX_PLAN_BYTES, canonical=True)
    exact(value, {"plan", "plan_sha256"}, "frozen field envelope")
    require(is_sha256(expected_plan_sha256) and value["plan_sha256"] == expected_plan_sha256 and
            digest(value["plan"]) == expected_plan_sha256, "Frozen field digest differs")
    try:
        body = value["plan"]
        require(type(body) is dict and type(body["cells"]) is list and len(body["cells"]) == 7,
                "Exactly seven frozen policy cells required")
        origins = {}
        for cell in body["cells"]:
            exact(cell, {"policy_id", "identity", "origin"}, "frozen policy cell")
            require(type(cell["policy_id"]) is str and cell["policy_id"] not in origins, "Duplicate field cell")
            origins[cell["policy_id"]] = {"identity": cell["identity"], "origin": cell["origin"]}
        rebuilt = _build(origins, body["policy_order"])
        require(encode(rebuilt) == plan_raw, "Frozen field content differs from its exact origin reconstruction")
        return rebuilt["plan"]
    except (KeyError, TypeError, IndexError, OverflowError) as error:
        raise ValueError("Malformed frozen field plan") from error
