"""UNTESTED reduction of one frozen field's pinned RAW journal exports.

Frozen behavior: preserve all seven slots, failed/incomplete/missing outcomes and
original artifact identities. Verify storage chains and the exact frozen origin,
not caller summary booleans. A closed completed checkpoint needs consistent
finish/state/memory joins before extracting interpolated time/pack metrics.
Only a complete positive-metric RAW field gets descriptive exact-tie/Pareto
orders. These are not physically validated results, awards or authentication.
No numerical bridge, I/O, runtime provider, worker, retry or resume is invoked.
"""

from dataclasses import dataclass
from hashlib import sha256
from itertools import combinations
from math import isfinite

from . import gate_ledger
from .input_contracts import decode, digest, encode, is_sha256, require
from .raw_evidence import MAX_EXPORT_BYTES, replay_raw_bundle
from .tournament_plan import validate_tournament_plan


SCHEMA = "lapsim.light-seven-policy-raw-field-report.v1"
MAX_REPORT_BYTES = 4 * 1024 * 1024
MAX_FIELD_EXPORT_BYTES = 7 * MAX_EXPORT_BYTES


@dataclass(frozen=True, slots=True)
class RawCellExport:
    bundle_raw: bytes
    bundle_sha256: str
    manifest_sha256: str


def _number(value, name):
    require(type(value) in (int, float) and isfinite(value), "Finite raw " + name + " required")
    return value


def _pack(state):
    return _number(state["thermal"]["light"]["powered"]["pack_energy_j"], "pack energy")


def _completed_metrics(checkpoint, origin):
    """Check stored finish joins only; no trajectory/physical revalidation."""
    finish, events, tick = checkpoint["finish"], checkpoint["lap_crossings"], checkpoint["tick"]
    require(type(tick) is int and tick > 0 and type(finish) is dict and
            type(events) is list and len(events) == 1 and checkpoint["violation"] is None and
            checkpoint["rejected_state"] is None, "A clean one-lap finish and sole physical-gate record are required")
    event = events[0]
    require(type(event["lap"]) is int and event["lap"] == 1 and
            type(event["boundary_tick"]) is int and event["boundary_tick"] == tick and
            event["previous_lap_sha256"] is None and
            event["source_sha256"] == origin["context"]["source"]["sha256"] and
            encode(event["crossing"]) == encode(finish) and
            encode(event["accepted_state"]) == encode(checkpoint["state"]) and
            encode(event["accepted_memory"]) == encode(checkpoint["memory"]),
            "Finish must bind the final accepted state/memory and exact source gate event")
    for name in ("accepted_state", "accepted_memory", "before_state"):
        require(event[name + "_sha256"] == digest(event[name]), "Stored finish record object hash differs")
    for state, expected_tick in ((event["before_state"], tick - 1), (checkpoint["state"], tick)):
        clocks = (state["drs"]["ticks"], state["thermal"]["thermal"]["ticks"],
                  state["thermal"]["light"]["feedback_ticks"])
        require(all(type(value) is int and value == expected_tick for value in clocks),
                "Stored gate states must bind the adjacent actual component clocks")
    require(type(checkpoint["memory"]["blend_updates"]) is int and checkpoint["memory"]["blend_updates"] == tick,
            "Stored gate memory must bind the accepted blend clock")
    # Exact fixed source gate from numerical_inputs.raw_reference_inputs. This
    # rebuilds stored-event metadata; it never advances or validates a trajectory.
    gate = {"origin_xy_m": [0., 0.], "forward_unit": [1., 0.], "finite_half_width_m": 3.,
            "scope": "Source physical gate;not moved with reference distance"}
    gate_ledger.validate(events, source_sha256=origin["context"]["source"]["sha256"], current_tick=tick,
                         current_source_progress_m=checkpoint["memory"]["source_progress_m"],
                         source_length_m=origin["context"]["course"]["length_m"], gate=gate)
    fraction = _number(finish["fraction"], "finish fraction")
    time = _number(finish["time_s"], "finish time")
    pack = _number(finish["pack_energy_j"], "finish pack energy")
    interval = [(tick - 1) * .001, tick * .001]
    endpoints = finish["pack_endpoints_j"]
    require(type(endpoints) is list and len(endpoints) == 2 and
            all(type(value) in (int, float) and isfinite(value) for value in endpoints), "Finite finish pack endpoints required")
    require(0 <= fraction <= 1 and time > 0 and encode(finish["accepted_interval_s"]) == encode(interval) and
            time == interval[0] + fraction * (interval[1] - interval[0]) and
            pack == endpoints[0] + fraction * (endpoints[1] - endpoints[0]) and
            endpoints[0] == _pack(event["before_state"]) and endpoints[1] == _pack(checkpoint["state"]),
            "Finish interpolation differs from the stored accepted interval and pack endpoints")
    capacity = _number(origin["context"]["actuation"]["pack_capacity_j"], "pack capacity")
    require(capacity > 0 and 0 <= pack <= capacity and all(0 <= value <= capacity for value in endpoints),
            "Completed raw finish pack is outside its declared domain")
    return time, (_pack(origin["state"]) - pack) / 3600


def _read_cell(cell, exported):
    require(type(exported) is RawCellExport, "Exact immutable raw cell transport required")
    raw, bundle_pin, manifest_pin = exported.bundle_raw, exported.bundle_sha256, exported.manifest_sha256
    require(type(raw) is bytes and is_sha256(bundle_pin) and is_sha256(manifest_pin),
            "Immutable raw export and independent content pins required")
    bundle = decode(raw, MAX_EXPORT_BYTES, canonical=True)
    tail = replay_raw_bundle(bundle, expected_bundle_sha256=bundle_pin, expected_manifest_sha256=manifest_pin)
    manifest = bundle["bundle"]["manifest"]
    require(encode(manifest["identity"]) == encode(cell["identity"]) and
            encode(manifest["origin"]) == encode(cell["origin"]), "Raw field cell differs from its frozen identity/origin")
    checkpoint = tail["checkpoint"]["checkpoint"]
    origin = cell["origin"]["checkpoint"]
    require(encode(checkpoint["context"]) == encode(origin["context"]), "Field cell changed its frozen context")
    tick = checkpoint["tick"]
    require(type(tick) is int and 0 <= tick <= origin["context"]["limits"]["maximum_ticks"], "Raw field clock exceeds mission")
    terminal = tail["terminal"]
    storage_status = None if terminal is None else terminal["terminal"]["status"]
    row = {
        "policy_id": cell["policy_id"], "submission": "raw_export", "storage_status": storage_status,
        "numerical_status": checkpoint["status"], "violation": checkpoint["violation"],
        "bundle_sha256": bundle_pin, "export_raw_sha256": sha256(raw).hexdigest(),
        "manifest_sha256": manifest_pin, "checkpoint_sha256": tail["checkpoint"]["checkpoint_sha256"],
        "terminal_sha256": None if terminal is None else terminal["terminal_sha256"],
        "committed_records": tail["records"], "tick": tick, "elapsed_s": tick * .001,
        "lap_time_s": None, "net_battery_wh": (_pack(origin["state"]) - _pack(checkpoint["state"])) / 3600,
        "metric_scope": "LAST_ACCEPTED_TICK_INCOMPLETE_NO_LAP_TIME",
        "raw_closed_completion": False, "raw_comparison_usable": False, "comparison_exclusion_reasons": [],
        "stored_gate_metadata_consistent": False, "physical_trajectory_validation_performed": False,
        "owned_execution_and_cleanup_authenticated": False,
        "campaign_eligible": False, "official_points": None,
    }
    reasons = row["comparison_exclusion_reasons"]
    if storage_status != "raw_completed":
        reasons.append("Journal is open or closed with a non-completion status; partial energy is not a completed result")
    if checkpoint["status"] != "completed":
        reasons.append("Numerical checkpoint did not complete the frozen lap")
    if tail["records"] == 0:
        reasons.append("No committed numerical chunks")
    if not reasons:
        try:
            lap_time, energy = _completed_metrics(checkpoint, origin)
            row.update(lap_time_s=lap_time, net_battery_wh=energy,
                       metric_scope="STORED_FINISH_INTERPOLATED_TIME_AND_PACK_RAW_ONLY", raw_closed_completion=True,
                       stored_gate_metadata_consistent=True)
            if not isfinite(energy) or energy <= 0:
                reasons.append("Completed net energy is nonpositive or nonfinite; no free-energy rank or clipping")
        except (ValueError, KeyError, TypeError, IndexError, OverflowError) as error:
            reasons.append("Stored completion metadata rejected: " + str(error))
    row["raw_comparison_usable"] = not reasons
    return row


def _orders(rows):
    """Exact comparisons; display rounding never selects a rank or Pareto set."""
    result = {}
    for metric in ("lap_time_s", "net_battery_wh"):
        groups = []
        for row in sorted(rows, key=lambda value: value[metric]):
            if groups and row[metric] == groups[-1]["value"]:
                groups[-1]["policy_ids"].append(row["policy_id"])
            else:
                groups.append({"rank": 1 + sum(len(group["policy_ids"]) for group in groups),
                               "value": row[metric], "policy_ids": [row["policy_id"]]})
        result[metric] = groups
    result["time_energy_pareto_policy_ids"] = [row["policy_id"] for row in rows if not any(
        other["lap_time_s"] <= row["lap_time_s"] and other["net_battery_wh"] <= row["net_battery_wh"] and
        (other["lap_time_s"] < row["lap_time_s"] or other["net_battery_wh"] < row["net_battery_wh"])
        for other in rows)]
    result["display_collisions_at_three_decimals"] = [
        {"metric": metric, "policy_ids": [left["policy_id"], right["policy_id"]],
         "display_value": format(left[metric], ".3f")}
        for left, right in combinations(rows, 2) for metric in ("lap_time_s", "net_battery_wh")
        if left[metric] != right[metric] and format(left[metric], ".3f") == format(right[metric], ".3f")]
    return result


def _summarize(plan, exports, plan_sha256):
    require(type(exports) is dict, "Native policy-keyed export dictionary required")
    exports = exports.copy()
    require(exports.keys() <= set(plan["policy_order"]), "Only frozen field policy submissions allowed")
    require(all(type(value) is RawCellExport and type(value.bundle_raw) is bytes for value in exports.values()) and
            sum(len(value.bundle_raw) for value in exports.values()) <= MAX_FIELD_EXPORT_BYTES,
            "Bounded immutable field exports required")
    rows = []
    for cell in plan["cells"]:
        if cell["policy_id"] not in exports:
            rows.append({"policy_id": cell["policy_id"], "submission": "missing", "storage_status": None,
                         "numerical_status": None, "lap_time_s": None, "net_battery_wh": None,
                         "raw_closed_completion": False, "raw_comparison_usable": False,
                         "comparison_exclusion_reasons": ["Frozen field cell has not been submitted"]})
        else:
            rows.append(_read_cell(cell, exports[cell["policy_id"]]))
    complete = all(row["raw_comparison_usable"] for row in rows)
    missing = [row["policy_id"] for row in rows if row["submission"] == "missing"]
    excluded = [row["policy_id"] for row in rows if row["submission"] != "missing" and not row["raw_comparison_usable"]]
    next_proposal = None
    if missing and not excluded:
        index = next(i for i, row in enumerate(rows) if row["submission"] == "missing")
        if all(row["raw_comparison_usable"] for row in rows[:index]) and all(
                row["submission"] == "missing" for row in rows[index:]):
            cell = plan["cells"][index]
            next_proposal = {"policy_id": cell["policy_id"], "origin_checkpoint_sha256": cell["origin"]["checkpoint_sha256"],
                             "status": "FRESH_ORIGIN_PROPOSAL_ORIGINAL_ADMISSION_AND_CLEANUP_REQUIRED",
                             "qualification_or_execution_authority": False}
    report = {
        "schema": SCHEMA, "plan_sha256": plan_sha256, "rows": rows,
        "coverage": {"frozen_cells": len(rows), "submitted_cells": len(exports), "missing_policy_ids": missing,
                     "excluded_policy_ids": excluded, "all_raw_cells_comparable": complete},
        "descriptive_raw_orders": _orders(rows) if complete else None,
        "next_cell_proposal": next_proposal,
        "comparison_scope": "UNAUTHENTICATED_RAW_STORAGE_AND_FINISH_METADATA_ONLY_NOT_NUMERICAL_VALIDATION",
        "source_runtime_or_original_input_authentication_performed": False,
        "single_attempt_exclusivity_authenticated": False, "owned_execution_and_cleanup_authenticated": False,
        "qualification_or_execution_authority": False, "campaign_eligible": False,
        "awards": {"points": None, "fastest": None, "least_energy": None, "overall_winner": None},
    }
    require(len(encode(report)) <= MAX_REPORT_BYTES, "Field report exceeds explicit bound; original artifacts remain unchanged")
    return report


def summarize_tournament(plan_raw, exports, *, expected_plan_sha256):
    """Reduce raw artifacts, retaining failures and complete frozen membership.

    exports maps policy IDs to immutable RawCellExport values, at most one
    supplied artifact per slot. That does not prove single-attempt execution or
    forbid hidden/cherry-picked attempts; original admission must establish it.
    No source receipt, hash, raw rank or next-cell proposal supplies authority.
    """
    plan = validate_tournament_plan(plan_raw, expected_plan_sha256=expected_plan_sha256)
    try:
        return _summarize(plan, exports, expected_plan_sha256)
    except (KeyError, TypeError, IndexError, OverflowError) as error:
        raise ValueError("Malformed raw tournament field evidence") from error
