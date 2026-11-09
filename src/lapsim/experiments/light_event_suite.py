"""Fixed nominal development screen: nine circuits and a separate skidpad field.

No search, tuning, holdout consumption, winner or official score is performed.
Closed-course rollouts have only between-attempt checkpoints; an unreturned
single-lap state cannot be reconstructed or silently retried here.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import json
import sys
import time

from lapsim.courses.library import COURSE_IDS, course_library
from lapsim.events.powered_skidpad import _finite, _integer, _raw, _source, _runtime, require_new_output
from lapsim.events.powered_skidpad_field import run_field as run_skidpad_field
from lapsim.events.skidpad_sequence import standard_skidpad_sequence
from .tournament_rollout import Case, Controller, PHILOSOPHIES, rollout
from .light_policy_scope import portable_policy_scope

MAX_JSON = 32 * 1024 * 1024


def _write(path, value):
    raw = _raw(value)
    if len(raw) > MAX_JSON:
        raise ValueError("Suite JSON payload exceeds its byte bound")
    with path.open("xb") as stream:
        stream.write(raw)
    return {"bytes": len(raw), "sha256": sha256(raw).hexdigest()}


def run_suite(output, *, catalog_rollouts, skidpad_steps, wall_seconds,
              maximum_cell_seconds, entry_length_m, exit_length_m):
    """Fresh fixed-order dispatch with different, explicit accounting units.

    Whole closed-course attempts are reserved before calls. Their soft wall
    check cannot interrupt a single-lap rollout. Skidpad retains its genuine
    interval/state checkpoints. Neither is an original native guard/lease.
    """
    _integer(catalog_rollouts, "catalog_rollouts", 0, len(COURSE_IDS)*len(PHILOSOPHIES))
    _integer(skidpad_steps, "skidpad_steps", 0, 40_000)
    if not 0 < _finite(wall_seconds, "wall_seconds") <= 300:
        raise ValueError("wall_seconds must be in (0, 300]")
    if not .01 <= _finite(maximum_cell_seconds, "maximum_cell_seconds") <= 60:
        raise ValueError("maximum_cell_seconds must be in [.01, 60]")
    # Fixed 10 ms closed-course clocks; do not silently round a user's budget.
    ticks = round(maximum_cell_seconds/.01)
    if abs(ticks*.01-maximum_cell_seconds) > 1e-12:
        raise ValueError("maximum_cell_seconds must be on the 10 ms clock")
    output = require_new_output(output)
    started = time.monotonic()
    deadline = started + wall_seconds
    skidpad = standard_skidpad_sequence(entry_length_m=entry_length_m, exit_length_m=exit_length_m)
    library = course_library()["courses"]
    if [entry["id"] for entry in library] != list(COURSE_IDS):
        raise ValueError("Exact nine-course catalog required")
    source = _source()
    binding = {"schema": "lapsim.light-event-suite-binding.v1", "source": source,
               "runtime": _runtime(), "profile": "synthetic_rwd", "heldout_used": False,
               "role": "development_nominal", "portable_policy_scope": portable_policy_scope(),
               "catalog_bundles": {e["id"]: sha256(_raw(e["bundle"])).hexdigest() for e in library},
               "skidpad_course": skidpad.to_dict(), "qualification_or_execution_authority": False}
    calls = []
    cells = []
    for entry in library:
        case = Case("development_nominal:" + entry["id"], course="bundle",
                    course_bundle=entry["bundle"], laps=1, long_course=entry["length_m"] > 400,
                    duration_s=maximum_cell_seconds)
        for philosophy in PHILOSOPHIES:
            controller = Controller(philosophy)
            name = entry["id"] + "--" + philosophy
            request = {"role": "development_nominal", "heldout_used": False,
                       "case": asdict(case), "controller": asdict(controller),
                       "profile": "synthetic_rwd", "suite_binding_sha256": sha256(_raw(binding)).hexdigest(),
                       "qualification_or_execution_authority": False}
            cells.append({"course_id": entry["id"], "controller": philosophy, "status": "unrun",
                          "model_status": None, "reservation_consumed": False,
                          "request_path": "catalog/requests/" + name + ".json",
                          "raw_result": None, "failure": None, "numerical_state_resumable": False})
            calls.append((controller, case, request, name))
    result = {"schema": "lapsim.light-event-suite.v1", "status": "planned",
              "role": "development_nominal", "heldout_used": False, "search_or_tuning_performed": False,
              "heldout_scope": "No existing heldout results or phase-selected cases loaded; shared geometry is not an unseen-course or qualification claim",
              "catalog_rollout_budget": catalog_rollouts, "reserved_catalog_rollouts": 0,
              "returned_catalog_rollouts": 0,
              "requested_skidpad_step_budget": skidpad_steps, "maximum_cell_seconds": maximum_cell_seconds,
              "wall_seconds": wall_seconds,
              "wall_scope": "COOPERATIVE_BETWEEN_CLOSED_ROLLOUTS_AND_SKIDPAD_CHUNKS_NOT_OS_DEADLINE",
              "closed_course_checkpoint_scope": "BETWEEN_ROLLOUTS_ONLY_NOT_MID_LAP_STATE",
              "resume_supported": False, "winner": None, "official_points": None,
              "qualification_or_execution_authority": False,
              "portable_policy_scope": portable_policy_scope(),
              "events": [{"event_id": e["id"], "kind": "closed_course_nominal", "status": "unrun"}
                         for e in library] + [{"event_id": "fsae_skidpad_nominal_rrll", "kind": "ordered_skidpad",
                                               "status": "unrun", "child_index": None}],
              "catalog_cells": cells}
    output.mkdir(parents=True, exist_ok=False)
    (output/"catalog/requests").mkdir(parents=True)
    (output/"catalog/raw").mkdir()
    _write(output/"suite-binding.json", binding)
    for row, (_, _, request, _) in zip(cells, calls):
        row["request_identity"] = _write(output/row["request_path"], request)
    serial = 0

    def save():
        nonlocal serial
        events()
        serial += 1
        _write(output/f"checkpoint-{serial:05d}.json", result)

    def events():
        for event in result["events"][:-1]:
            group = [c for c in cells if c["course_id"] == event["event_id"]]
            statuses = [c["status"] for c in group]
            event["status"] = ("unrun" if all(s == "unrun" for s in statuses) else
                               "completed_development_cells" if all(s == "completed_development_cell" for s in statuses)
                               else "partial_development_cells")

    save()
    stopped = False
    for row, (controller, case, request, name) in zip(cells, calls):
        if result["reserved_catalog_rollouts"] >= catalog_rollouts or time.monotonic() >= deadline:
            break
        if _source() != source or _runtime() != binding["runtime"]:
            raise ValueError("Suite source/runtime changed before dispatch")
        # The request already exists; consume the attempt before calling code.
        result["reserved_catalog_rollouts"] += 1
        row["reservation_consumed"] = True
        row["status"] = "running_unreturned"
        save()
        if time.monotonic() >= deadline:
            row["status"] = "paused_wall_before_dispatch"
            save()
            break  # Do not refund the persisted reservation.
        request_raw = (output/row["request_path"]).read_bytes()
        if (len(request_raw) != row["request_identity"]["bytes"] or
                sha256(request_raw).hexdigest() != row["request_identity"]["sha256"]):
            row["status"] = "rejected_request_record"
            result["status"] = "execution_error"
            stopped = True
            save()
            break
        if time.monotonic() >= deadline:
            row["status"] = "paused_wall_before_dispatch"
            save()
            break  # Request verification I/O is inside the dispatch fence too.
        try:
            record = rollout(controller, case, profile="synthetic_rwd")
        except (Exception, KeyboardInterrupt) as error:
            row["status"] = "uncertain_unreturned"
            row["failure"] = {"type": type(error).__name__, "message": str(error)[:1024],
                              "state_available": False, "automatic_retry": False}
            result["status"] = "execution_error"
            stopped = True
            save()
            break
        # Publish exact returned JSON before considering its identity/status.
        # A serialization/publication failure propagates and stops all work.
        result["returned_catalog_rollouts"] += 1
        path = "catalog/raw/" + name + ".json"
        row["raw_result"] = {"path": path, **_write(output/path, record)}
        if _source() != source or _runtime() != binding["runtime"]:
            row["status"] = "rejected_source_change"
            row["failure"] = {"type": "SourceRuntimeChanged", "automatic_retry": False}
            result["status"] = "execution_error"
            stopped = True
            save()
            break
        if (type(record) is not dict or _raw(record.get("case")) != _raw(request["case"])
                or _raw(record.get("controller")) != _raw(request["controller"])
                or record.get("profile") != request["profile"] or type(record.get("eligible")) is not bool
                or type(record.get("status")) is not str):
            row["status"] = "rejected_result_identity"
            result["status"] = "execution_error"
            stopped = True
            save()
            break
        row["model_status"] = record["status"]
        row["status"] = ("completed_development_cell" if record["status"] == "completed" and record["eligible"]
                         else "returned_failure")
        events()
        save()
    events()
    if not stopped and skidpad_steps > 0 and time.monotonic() < deadline:
        event = result["events"][-1]
        if _source() != source or _runtime() != binding["runtime"]:
            raise ValueError("Suite source/runtime changed before skidpad dispatch")
        event["status"] = "running_unreturned"
        save()
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            event["status"] = "unrun"
            event["reason"] = "wall_expired_before_dispatch"
        else:
            try:
                child = run_skidpad_field(output/"skidpad", course=skidpad, total_step_budget=skidpad_steps,
                                          wall_seconds=min(300., remaining))
            except (Exception, KeyboardInterrupt) as error:
                event["status"] = "uncertain_failed_child"
                event["failure"] = {"type": type(error).__name__, "message": str(error)[:1024],
                                    "partial_files_are_not_success": True}
                result["status"] = "execution_error"
                stopped = True
                save()
            else:
                # Retain the child first; do not silently rebind a changed
                # source/runtime to the earlier suite snapshot.
                path = output/"skidpad/field-index.json"
                raw = path.read_bytes()
                common_raw = (output/"skidpad/common-binding.json").read_bytes()
                if len(raw) > MAX_JSON or len(common_raw) > MAX_JSON:
                    raise ValueError("Skidpad child binding/index exceeds byte bound")
                common = json.loads(common_raw)
                child_cells = child.get("cells") if type(child) is dict else None
                cell_shape = (type(child_cells) is list and len(child_cells) == len(PHILOSOPHIES) and
                              all(type(c) is dict for c in child_cells) and
                              [c.get("controller") for c in child_cells] == list(PHILOSOPHIES))
                completed_cells = (cell_shape and all(c.get("status") == "completed" and
                    c.get("session_status") == "completed" for c in child_cells))
                valid = (type(child) is dict and _raw(child) == raw and
                         type(common) is dict and type(common.get("request")) is dict and
                         _raw(common) == common_raw and
                         sha256(common_raw).hexdigest() == child.get("common_binding_sha256") and
                         _raw(common.get("source")) == _raw(source) and
                         _raw(common.get("runtime")) == _raw(binding["runtime"]) and
                         _raw(common.get("request", {}).get("course")) == _raw(binding["skidpad_course"]) and
                         child.get("controller_order") == list(PHILOSOPHIES) and
                         child.get("qualification_or_execution_authority") is False and
                         child.get("qualified_tournament_result") is False and child.get("winner") is None and
                         child.get("official_points") is None and cell_shape and
                         (child.get("status") != "completed_development_field" or completed_cells) and
                         _source() == source and
                         _runtime() == binding["runtime"])
                event["child_index"] = {"path": "skidpad/field-index.json", "bytes": len(raw),
                                         "sha256": sha256(raw).hexdigest()}
                if not valid:
                    event["status"] = "rejected_child_binding"
                    result["status"] = "execution_error"
                    stopped = True
                else:
                    event["status"] = child["status"]
    if not stopped:
        result["status"] = ("completed_development_suite" if all(
            c["status"] == "completed_development_cell" for c in cells) and
            result["events"][-1]["status"] == "completed_development_field" else "partial_development_suite")
    result["elapsed_wall_s"] = time.monotonic()-started
    save()
    _write(output/"suite-index.json", result)
    return result


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-rollouts", type=int, required=True)
    parser.add_argument("--maximum-cell-seconds", type=float, required=True)
    parser.add_argument("--skidpad-steps", type=int, required=True)
    parser.add_argument("--wall-seconds", type=float, required=True)
    parser.add_argument("--entry-length-m", type=float, required=True)
    parser.add_argument("--exit-length-m", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run_suite(args.output, catalog_rollouts=args.catalog_rollouts, skidpad_steps=args.skidpad_steps,
                           wall_seconds=args.wall_seconds, maximum_cell_seconds=args.maximum_cell_seconds,
                           entry_length_m=args.entry_length_m, exit_length_m=args.exit_length_m)
        print(json.dumps({"output": str(args.output), "status": result["status"],
                          "reserved_catalog_rollouts": result["reserved_catalog_rollouts"],
                          "heldout_used": False, "winner": None, "official_points": None}, sort_keys=True))
        return 0 if result["status"] == "completed_development_suite" else 3
    except (ValueError, OSError) as error:
        print(f"light event suite: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
