"""Sequential four-controller synthetic skidpad field with explicit shared caps.

Fresh-only development execution. Raw checkpoints retain their real session
status; aggregate pauses never become fabricated terminal/admission evidence.
No native worker, authentication, lease, official scoring or winner is supplied.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import json
import sys
import time

from .powered_skidpad import (
    MAX_TICKS, MAX_WORK, PHILOSOPHIES, Controller, PoweredSkidpadRequest,
    _finite, _integer, _raw, fresh_session, advance_session,
    require_new_output, write_session_binding, publish_session,
)
from .skidpad_sequence import standard_skidpad_sequence


def _write(path, value):
    raw = _raw(value)
    with path.open("xb") as stream:
        stream.write(raw)
    return {"bytes": len(raw), "sha256": sha256(raw).hexdigest()}


def _common(binding):
    result = json.loads(_raw(binding))
    del result["request"]["controller"]
    return result


def run_field(output, *, course, total_step_budget, wall_seconds,
              maximum_ticks=MAX_TICKS, maximum_work=MAX_WORK, chunk_steps=100):
    """Run at most one cell per fixed philosophy; preserve every distinct outcome.

    Reserve whole chunks BEFORE dispatch and never refund unused reservations.
    Count actual attempted intervals separately, including rejected intervals.
    The wall check is cooperative BETWEEN chunks, not an OS-owned deadline.
    Aggregate resume is deliberately unsupported; child checkpoints are data,
    never standalone native continuation authority.
    """
    _integer(total_step_budget, "total_step_budget", 1, len(PHILOSOPHIES)*MAX_TICKS)
    _integer(chunk_steps, "chunk_steps", 1, 100)
    if not 0 < _finite(wall_seconds, "wall_seconds") <= 300:
        raise ValueError("wall_seconds must be in (0, 300]")
    output = require_new_output(output)
    start = time.monotonic()
    requests = [PoweredSkidpadRequest(course, Controller(name), maximum_ticks, maximum_work)
                for name in PHILOSOPHIES]
    sessions = [fresh_session(request) for request in requests]
    common = _raw(_common(sessions[0].binding))
    initial = _raw(asdict(sessions[0].initial_state))
    if any(_raw(_common(s.binding)) != common or _raw(asdict(s.initial_state)) != initial
           for s in sessions):
        raise ValueError("Field cells require exactly matched inputs and initial state")
    output.mkdir(parents=True, exist_ok=False)
    (output / "cells").mkdir()
    (output / "reservations").mkdir()
    _write(output / "common-binding.json", json.loads(common))
    _write(output / "initial-state.json", json.loads(initial))
    result = {"schema": "lapsim.powered-skidpad-field.v1", "status": "planned",
              "controller_order": list(PHILOSOPHIES), "total_step_budget": total_step_budget,
              "reserved_steps": 0, "attempted_steps": 0, "wall_seconds": wall_seconds,
              "wall_scope": "COOPERATIVE_BETWEEN_AT_MOST_100_TICK_CHUNKS_NOT_OS_DEADLINE",
              "common_binding_sha256": sha256(common).hexdigest(),
              "initial_state_sha256": sha256(initial).hexdigest(),
              "backend": "SYNTHETIC_POWERED_RWD_FOUR_ORDINARY_ALLOCATORS",
              "native_guard_or_worker_invoked": False,
              "qualification_or_execution_authority": False, "qualified_tournament_result": False,
              "winner": None, "official_points": None, "aggregate_resume_supported": False,
              "cells": [{"controller": name, "status": "unrun", "session_status": None,
                         "reserved_steps": 0, "attempted_steps": 0, "accepted_steps": 0,
                         "failure_reason": None, "execution_error": None,
                         "timed_average_s": None, "artifacts": None,
                         "binding_sha256": sha256(_raw(s.binding)).hexdigest()}
                        for name, s in zip(PHILOSOPHIES, sessions)]}
    _write(output / "plan.json", result)
    serial = 0
    stop = None
    for cell, session in zip(result["cells"], sessions):
        if result["reserved_steps"] >= total_step_budget:
            stop = "paused_aggregate_budget"
            break
        if time.monotonic()-start >= wall_seconds:
            stop = "paused_wall_budget"
            break
        directory = output / "cells" / cell["controller"]
        directory.mkdir()
        write_session_binding(directory, session)
        cell["status"] = "running"
        while session.status == "running":
            if result["reserved_steps"] >= total_step_budget:
                stop = "paused_aggregate_budget"
                break
            if time.monotonic()-start >= wall_seconds:
                stop = "paused_wall_budget"
                break
            amount = min(chunk_steps, total_step_budget-result["reserved_steps"],
                         maximum_ticks-session.attempted_steps)
            if amount <= 0:
                raise ValueError("Running cell has no remaining per-cell allocation")
            result["reserved_steps"] += amount
            cell["reserved_steps"] += amount
            serial += 1
            _write(output / "reservations" / f"{serial:05d}.json", {
                "controller": cell["controller"], "reserved_chunk_steps": amount,
                "aggregate_reserved_steps": result["reserved_steps"],
                "cell_reserved_steps": cell["reserved_steps"],
                "before_attempted_steps": session.attempted_steps,
                "qualification_or_execution_authority": False})
            if time.monotonic()-start >= wall_seconds:
                # Reservation I/O may consume the remaining allowance. Keep
                # its full charge, but do not dispatch a new expired chunk.
                stop = "paused_wall_budget"
                break
            try:
                advance_session(session, amount)
            except KeyboardInterrupt:
                stop = "interrupted"
                cell["execution_error"] = "KeyboardInterrupt; retained actual session state"
                break
            except Exception as error:
                stop = "execution_error"
                cell["execution_error"] = (str(error) or type(error).__name__)[:4096]
                break
        # Retain actual state BEFORE another policy. Any publication failure
        # propagates; no further cells execute and partial files remain intact.
        publish_session(directory, session)
        index = directory / "files.json"
        raw = index.read_bytes()
        cell.update(status=stop if session.status == "running" and stop else session.status,
                    session_status=session.status, attempted_steps=session.attempted_steps,
                    accepted_steps=session.tick, failure_reason=session.failure_reason,
                    timed_average_s=session.result().get("timed_average_s") if session.status == "completed" else None,
                    artifacts={"path": index.relative_to(output).as_posix(),
                               "bytes": len(raw), "sha256": sha256(raw).hexdigest()})
        result["attempted_steps"] = sum(s.attempted_steps for s in sessions)
        if stop:
            break
    result["status"] = stop or (
        "completed_development_field" if all(c["status"] == "completed" for c in result["cells"])
        else "finished_with_failures")
    result["elapsed_wall_s"] = time.monotonic()-start
    _write(output / "field-index.json", result)
    return result


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry-length-m", required=True, type=float)
    parser.add_argument("--exit-length-m", required=True, type=float)
    parser.add_argument("--total-step-budget", required=True, type=int)
    parser.add_argument("--wall-seconds", required=True, type=float)
    parser.add_argument("--maximum-ticks", default=MAX_TICKS, type=int)
    parser.add_argument("--maximum-work", default=MAX_WORK, type=int)
    parser.add_argument("--chunk-steps", default=100, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = run_field(args.output, course=standard_skidpad_sequence(
            entry_length_m=args.entry_length_m, exit_length_m=args.exit_length_m),
            total_step_budget=args.total_step_budget, wall_seconds=args.wall_seconds,
            maximum_ticks=args.maximum_ticks, maximum_work=args.maximum_work,
            chunk_steps=args.chunk_steps)
        print(json.dumps({"output": str(args.output), "status": result["status"],
                          "reserved_steps": result["reserved_steps"],
                          "attempted_steps": result["attempted_steps"],
                          "winner": None, "qualified_tournament_result": False}, sort_keys=True))
        return 0 if result["status"] == "completed_development_field" else 3
    except (ValueError, OSError) as error:
        print(f"powered skidpad field: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
