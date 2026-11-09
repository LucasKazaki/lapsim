"""Bounded, resumable controller tournament and genetic tuning CLI."""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
import platform
import random
import statistics
import time

from lapsim.experiments.record_io import read_json_bounded, write_text_atomic
from lapsim.courses.course_bundle import CourseBundle
from lapsim.courses.library import COURSE_IDS, course_library
from .tournament_rollout import BOUNDS, PHILOSOPHIES, PROFILES, Case, Controller, number, rollout

SCHEMA = "lapsim.controller-tournament.v1"
UPSTREAM = "b25774c7c9a6ca749a0e2fa8cc11cf53392be83c"
TRAIN = (Case("train_dry"), Case("train_patch", patch=True))
HOLDOUT = (Case("holdout_reverse", course="reverse_stadium", grip=.85, initial_offset_m=.15),
           Case("holdout_full_pack", course="reverse_stadium", initial_soc=1.0))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def identity(value):
    return sha256(canonical(value).encode()).hexdigest()[:20]


def sources():
    root = Path(__file__).resolve().parents[1]
    names = ("experiments/controller_tournament.py", "experiments/tournament_rollout.py",
             "optimization/pose_driver.py", "dynamics/planar.py", "dynamics/powered_planar.py",
             "dynamics/actuation.py", "dynamics/conditions.py", "courses/spatial_track.py")
    names += ("qmc_sampler.py", "courses/track.py", "courses/course_bundle.py", "experiments/closed_loop.py", "experiments/lap_ledger.py",
              "courses/library.py","experiments/ten_lap_campaign.py","experiments/record_io.py")
    return {p: sha256((root / p).read_bytes()).hexdigest() for p in names}


def specification(seed=4082025, population=6, generations=3, profile="synthetic_awd",
                  *, course="stadium", course_bundle=None, reverse=False, mirror=False,laps=10):
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("seed must be an unsigned 32-bit integer")
    if type(population) is not int or not 4 <= population <= 10:
        raise ValueError("population must be 4–10")
    if type(generations) is not int or not 1 <= generations <= 6:
        raise ValueError("generations must be 1–6")
    if profile not in PROFILES:
        raise ValueError("2025 unknowns prevent execution of the source-backed derived AWD baseline")
    long_course=False
    if course=='bundle':
        if course_bundle is None:raise ValueError('Bundle course requires its geometry')
        long_course=laps==1 and CourseBundle.from_dict(course_bundle).track.length_m>400
    base = Case("train_dry", course=course, course_bundle=course_bundle,laps=laps,long_course=long_course,
                reverse=reverse, mirror=mirror, duration_s=600 if laps==10 else 300 if long_course else 30 if course == "stadium" else 60)
    if laps==1 and course == "stadium" and not reverse and not mirror:
        train, holdout = TRAIN, HOLDOUT
    else:
        train = (base, replace(base, name="train_patch", patch=True))
        holdout = (replace(base, name="holdout_reverse", reverse=not reverse, grip=.85, initial_offset_m=.15),
                   replace(base, name="holdout_full_pack", reverse=not reverse, initial_soc=1.0))
    return {"seed": seed, "population": population, "generations": generations, "profile": profile,
        "competition":{"laps":laps,"reset_between_candidates":True,"state_carry":"Continuous plant/pack/actuator/controller state across seams; static temperature only",'metric_scope':'Total round time and energy; lap_time_s is the retained metric alias'},
        "training": [asdict(c) for c in train], "holdout": [asdict(c) for c in holdout],
        "scenario_inputs": {"battery_capacity_kwh": 5.5, "maximum_voltage_v": 600,
            "initial_voltage_v": 580, "endurance_energy_weights": [275, 100],
            "status": "user-requested scenario assumptions; not verified hardware or rule compliance"},
        "bounds": BOUNDS, "upstream": UPSTREAM,
        "objective": {"name": "engineering_proxy", "expression": "lap_time_s + 120 * net_energy_kwh",
            "lower_is_better": True, "fsae_points_enabled": False,
            "reason": "Official rule edition and fixed opposition/reference data are not verified; 275:100 is not a seconds/kWh conversion"},
        "resources": {"workers": 1, "gpu_physics": False, "maximum_runs": 2 * (4 + population * generations) + 8,
                      "maximum_simulated_run_s": base.duration_s, "maximum_checkpoint_mb": 120}}


def _catalog_selection(course_ids):
    """Load only exact shipped IDs through the existing catalog/bundle checks."""
    ids = tuple(course_ids)
    if (not ids or any(type(cid) is not str or cid not in COURSE_IDS for cid in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("Choose distinct supported course catalog IDs")
    entries = {entry["id"]: entry for entry in course_library()["courses"]}
    return [entries[cid] for cid in ids]


def catalog_specification(course_id, seed=4082025, population=6, generations=3,
                          profile="synthetic_awd", *, reverse=False, mirror=False, laps=10):
    """Select one shipped bundle; preserve the existing specification format."""
    entry = _catalog_selection((course_id,))[0]
    return specification(seed, population, generations, profile, course="bundle",
        course_bundle=entry["bundle"], reverse=reverse, mirror=mirror, laps=laps)


class _CatalogBudgetBoundary(Exception):
    """Internal cooperative stop before starting another rollout."""


def run_catalog_batch(output: Path, *, maximum_new_runs, wall_seconds,
                      seed=4082025, population=6, generations=3, profile="synthetic_awd",
                      reverse=False, mirror=False, laps=1, course_ids=COURSE_IDS,
                      rollout_fn=rollout):
    """Fresh sequential per-course searches under ONE cooperative outer budget.

    This is the ordinary synthetic four-philosophy backend, not the portable
    seven-policy/native-admission runner. Each child retains its own unmodified
    search specification/checkpoint and held-out separation. The batch never
    retries or resumes a child and has no cross-course winner. Slots are reserved
    before calls, including failed or uncertain calls, without refunds.

    Wall time is checked at rollout boundaries; an in-flight rollout and file
    finalization may exceed it. This is not an OS deadline or resource lease.
    """
    started = time.perf_counter()
    number(wall_seconds, "batch wall_seconds", 1, 900)
    if type(maximum_new_runs) is not int or maximum_new_runs < 0:
        raise ValueError("maximum_new_runs must be an explicit nonnegative integer")
    if type(laps) is not int or laps != 1:
        raise ValueError("Catalog batches support explicit one-lap searches only")
    entries = _catalog_selection(course_ids)
    specs = [specification(seed, population, generations, profile, course="bundle",
                course_bundle=entry["bundle"], reverse=reverse, mirror=mirror, laps=1)
             for entry in entries]
    declared_runs = sum(spec["resources"]["maximum_runs"] for spec in specs)
    if maximum_new_runs > declared_runs:
        raise ValueError("Batch run budget exceeds the selected searches' declared bounds")
    source = sources()
    deadline = started + wall_seconds
    result = {
        "schema": "lapsim.catalog-search-batch.v1", "status": "running",
        "sources": source, "course_order": [entry["id"] for entry in entries],
        "configuration": {"seed": seed, "population": population, "generations": generations,
            "profile": profile, "reverse": reverse, "mirror": mirror, "laps": 1},
        "budget": {"maximum_new_runs": maximum_new_runs, "maximum_wall_seconds": wall_seconds,
            "reserved_rollout_slots": 0, "elapsed_wall_seconds": 0.,
            "wall_enforcement": "COOPERATIVE_ROLLOUT_BOUNDARIES_NOT_OS_DEADLINE",
            "failed_or_uncertain_slots_refunded": False},
        "supported_controller_philosophies": list(PHILOSOPHIES),
        "portable_seven_policy_comparison": "UNSUPPORTED_BY_THIS_BACKEND",
        "events": {"closed_course_one_lap": "SYNTHETIC_DEVELOPMENT_SEARCH",
                   "skidpad_sequence": "UNSUPPORTED_BY_THIS_RUNNER"},
        "official_points": None, "cross_course_winner": None,
        "qualification_or_execution_authority": False, "batch_resume_supported": False,
        "checkpoint_runs_scope": "UNRUN_ZERO_RETURNED_STATE_COUNT_OR_NULL_IF_STARTED_BUT_NOT_RETURNED",
        "child_output_scope": "RETAINED_FILES_MAY_INCLUDE_STALE_REPLAY_AFTER_FAILURE_NOT_REVALIDATED_BY_BATCH",
        "courses": [
            {"course_id": entry["id"], "catalog": {k:v for k,v in entry.items() if k != "bundle"},
             "bundle_payload_sha256": sha256(canonical(entry["bundle"]).encode()).hexdigest(),
             "specification_sha256": sha256(canonical(spec).encode()).hexdigest(),
             "output_directory": entry["id"], "checkpoint": entry["id"] + "/checkpoint.json",
             "status": "unrun", "reserved_rollout_slots": 0, "checkpoint_runs": 0,
             "checkpoint_present": False, "failure": None}
            for entry,spec in zip(entries,specs,strict=True)]}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)  # Never overwrite an earlier batch or child artifact.

    def save():
        result["budget"]["elapsed_wall_seconds"] = time.perf_counter() - started
        write_text_atomic(output / "catalog-search.json", canonical(result))

    save()
    for row,spec in zip(result["courses"],specs,strict=True):
        remaining_runs = maximum_new_runs - result["budget"]["reserved_rollout_slots"]
        remaining_wall = deadline - time.perf_counter()
        if remaining_runs <= 0 or remaining_wall < 1:
            result["status"] = "paused_budget"
            save()
            return result
        child = output / row["output_directory"]
        row["status"] = "running"
        row["checkpoint_runs"] = None
        save()

        def counted_rollout(*args, **kwargs):
            if (result["budget"]["reserved_rollout_slots"] >= maximum_new_runs
                    or time.perf_counter() >= deadline):
                raise _CatalogBudgetBoundary()
            result["budget"]["reserved_rollout_slots"] += 1
            row["reserved_rollout_slots"] += 1
            save()  # Reserve first: failure or process death must not imply a free retry.
            if time.perf_counter() >= deadline:
                raise _CatalogBudgetBoundary()
            return rollout_fn(*args, **kwargs)

        try:
            if sources() != source:
                raise ValueError("Source changed during catalog batch; do not update an active study")
            state = run_search(child, spec, resume=False, wall_seconds=remaining_wall,
                maximum_new_runs=remaining_runs, rollout_fn=counted_rollout)
            row["checkpoint_runs"] = len(state["runs"])
            row["checkpoint_present"] = (child / "checkpoint.json").is_file()
            row["status"] = state["status"]
        except _CatalogBudgetBoundary:
            row["status"] = "paused_budget"
            row["checkpoint_runs"] = None
            row["checkpoint_present"] = (child / "checkpoint.json").is_file()
            result["status"] = "paused_budget"
            save()
            return result
        except BaseException as error:
            row["status"] = "failed"
            row["checkpoint_runs"] = None
            row["checkpoint_present"] = (child / "checkpoint.json").is_file()
            row["failure"] = {"type": type(error).__name__, "message": str(error)[:1024]}
            result["status"] = "failed"
            try:
                save()
            except BaseException as save_error:
                if hasattr(error, "add_note"):
                    error.add_note("Catalog failure-index write also failed: " + repr(save_error))
            raise
        save()
        if row["status"] == "paused_budget":
            result["status"] = "paused_budget"
            save()
            return result
    result["status"] = ("completed" if all(row["status"] == "completed" for row in result["courses"])
                        else "completed_with_failures")
    save()
    return result


def nested_tuple(value):
    return tuple(nested_tuple(v) for v in value) if isinstance(value, list) else value


def mutate(parent, rng):
    child = dict(parent)
    if rng.random() < .15:
        child["philosophy"] = rng.choice(PHILOSOPHIES)
    active = ["drive_scale", "regen_fraction", "regen_region"]
    if child["philosophy"] != "fixed":
        active.append("slip_target")
    if child["philosophy"] == "yaw_pi":
        active += ["yaw_kp", "yaw_ki"]
    for key in active:
        lo, hi = BOUNDS[key]
        if rng.random() < .75:
            child[key] = max(lo, min(hi, child[key] + rng.gauss(0, .18 * (hi - lo))))
    return asdict(Controller(**child))


def aggregate(records):
    eligible = all(r["eligible"] for r in records)
    return {"eligible": eligible,
        "fitness": statistics.mean(r["metrics"]["fitness"] for r in records) if eligible else None,
        "mean_lap_time_s": statistics.mean(r["metrics"]["lap_time_s"] for r in records) if eligible else None,
        "mean_net_energy_kwh": statistics.mean(r["metrics"]["net_energy_kwh"] for r in records),
        "failures": sum(not r["eligible"] for r in records)}


def ordering(summary):
    return (not summary["eligible"], summary["fitness"] if summary["eligible"] else float("inf"))


def run_search(output: Path, spec: dict, *, resume=False, wall_seconds=600.0,
               rollout_fn=rollout, maximum_new_runs=None):
    """Checkpoint only at deterministic rollout boundaries; no wall-time fitness."""
    if not 1 <= wall_seconds <= 900:
        raise ValueError("wall_seconds must be 1–900")
    source = sources()
    training_cases = tuple(Case(**c) for c in spec["training"])
    holdout_cases = tuple(Case(**c) for c in spec["holdout"])
    fingerprint = identity({"spec": spec, "sources": source})
    checkpoint = output / "checkpoint.json"
    output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(spec["seed"])
    started = time.perf_counter()
    new_runs = 0
    if checkpoint.exists():
        if not resume:
            raise ValueError("output already contains a checkpoint; use --resume or a fresh output")
        state = read_json_bounded(checkpoint, maximum_bytes=120_000_000)
        if state["schema"] != SCHEMA or state["fingerprint"] != fingerprint:
            raise ValueError("checkpoint config/source mismatch")
        rng.setstate(nested_tuple(state["rng_state"]))
    else:
        state = {"schema": SCHEMA, "fingerprint": fingerprint, "specification": spec,
            "sources": source, "rng_state": rng.getstate(), "runs": {}, "candidates": {},
            "baselines": [], "generations": [], "pending": None, "holdout": {},
            "round_robin": [], "best_so_far": None, "status": "running",
            "runtime": {"python": platform.python_version(), "platform": platform.platform()},
            "timings": [], "benchmark": []}

    def save():
        state["rng_state"] = rng.getstate()
        write_text_atomic(checkpoint, canonical(state))

    def within_budget():
        return time.perf_counter() - started < wall_seconds and (maximum_new_runs is None or new_runs < maximum_new_runs)

    def evaluate(controller, cases):
        nonlocal new_runs
        ids = []
        for case in cases:
            key = identity({"controller": controller, "case": asdict(case)})
            if key not in state["runs"]:
                if not within_budget():
                    return None
                began = time.perf_counter()
                record = rollout_fn(Controller(**controller), case, profile=spec["profile"])
                state["runs"][key] = record
                elapsed = time.perf_counter() - began
                state["benchmark"].append({"run_id": key, "wall_s": elapsed,
                    "simulated_s": record["metrics"]["elapsed_s"], "samples": len(record["telemetry"]),
                    "integration_substeps": record.get("work", {}).get("integration_substeps"),
                    "backend": "python_cpu_single_worker"})
                new_runs += 1
                save()
                print(f"run {len(state['runs']):02d} {controller['philosophy']} {case.name}: {record['status']} ({elapsed:.2f}s)", flush=True)
            ids.append(key)
        return ids

    def training(controller):
        cid = identity(controller)
        if cid not in state["candidates"]:
            ids = evaluate(controller, training_cases)
            if ids is None:
                return None
            state["candidates"][cid] = {"controller": controller, "run_ids": ids,
                "summary": aggregate([state["runs"][k] for k in ids])}
            save()
        return cid

    def paused():
        state["status"] = "paused_budget"
        state["timings"].append({"wall_s": time.perf_counter() - started, "new_runs": new_runs})
        save()
        export_replay(state, output)
        return state

    for philosophy in PHILOSOPHIES:
        cid = training(asdict(Controller(philosophy)))
        if cid is None:
            return paused()
        if cid not in state["baselines"]:
            state["baselines"].append(cid)
            save()
    if not state["round_robin"]:
        for i, left in enumerate(state["baselines"]):
            for right in state["baselines"][i + 1:]:
                a, b = (state["candidates"][x]["summary"] for x in (left, right))
                winner = left if ordering(a) < ordering(b) else right if ordering(b) < ordering(a) else None
                state["round_robin"].append({"left": left, "right": right, "winner": winner,
                                            "both_invalid": not a["eligible"] and not b["eligible"]})
    while len(state["generations"]) < spec["generations"]:
        if state["pending"] is None:
            parents=[]
            if not state["generations"]:
                population = [state["candidates"][c]["controller"] for c in state["baselines"]]
            else:
                previous = state["generations"][-1]["candidate_ids"]
                ranked = sorted(previous, key=lambda c: ordering(state["candidates"][c]["summary"]))
                parents = [state["candidates"][c]["controller"] for c in ranked[:3]
                           if state["candidates"][c]["summary"]["eligible"]]
                if not parents:
                    state["status"] = "no_eligible_parent"
                    save()
                    export_replay(state, output)
                    return state
                population = [parents[0]]
            while len(population) < spec["population"]:
                parent = rng.choice(population[:4] if not state["generations"] else parents)
                population.append(mutate(parent, rng))
            state["pending"] = population
            save()
        ids = []
        for controller in state["pending"]:
            cid = training(controller)
            if cid is None:
                return paused()
            ids.append(cid)
        summaries = [state["candidates"][c]["summary"] for c in ids]
        valid = [s["fitness"] for s in summaries if s["eligible"]]
        ranked = sorted(ids, key=lambda c: ordering(state["candidates"][c]["summary"]))
        leader = ranked[0] if valid else None
        old = state["best_so_far"]
        if leader and (old is None or ordering(state["candidates"][leader]["summary"]) < ordering(state["candidates"][old]["summary"])):
            state["best_so_far"] = leader
        state["generations"].append({"generation": len(state["generations"]), "candidate_ids": ids,
            "best": min(valid) if valid else None, "mean": statistics.mean(valid) if valid else None,
            "median": statistics.median(valid) if valid else None, "worst": max(valid) if valid else None,
            "invalid_count": sum(not s["eligible"] for s in summaries),
            "best_so_far_id": state["best_so_far"],
            "best_so_far": state["candidates"][state["best_so_far"]]["summary"]["fitness"] if state["best_so_far"] else None})
        state["pending"] = None
        save()
        export_replay(state, output)
    ranked = sorted(state["candidates"], key=lambda c: ordering(state["candidates"][c]["summary"]))
    selected = list(dict.fromkeys([state["baselines"][0]] + ranked[:2]))
    for cid in selected:
        if cid not in state["holdout"]:
            ids = evaluate(state["candidates"][cid]["controller"], holdout_cases)
            if ids is None:
                return paused()
            state["holdout"][cid] = {"run_ids": ids, "summary": aggregate([state["runs"][k] for k in ids])}
            save()
    diagnostic = replace(training_cases[0], name="diagnostic_no_regen_no_fallback",
                         regen_available=False, friction_fallback=False)
    diagnostic_ids = evaluate(asdict(Controller()), (diagnostic,))
    if diagnostic_ids is None:
        return paused()
    state["diagnostic_ids"] = diagnostic_ids
    state["status"] = "completed"
    state["timings"].append({"wall_s": time.perf_counter() - started, "new_runs": new_runs})
    save()
    export_replay(state, output)
    return state


def export_replay(state, output):
    text = canonical(state)
    write_text_atomic(output / "replay.json", text)
    # External JS keeps the viewer usable directly from a local file too.
    write_text_atomic(output / "replay-data.js", "window.LAPSIM_TOURNAMENT=" + text + ";\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("work/tournament-4082025"))
    parser.add_argument("--seed", type=int, default=4082025)
    parser.add_argument("--population", type=int, default=6)
    parser.add_argument("--generations", type=int, default=3)
    parser.add_argument("--wall-seconds", type=float, default=600)
    parser.add_argument("--profile", default="synthetic_awd")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--course", choices=("stadium", "autocross", "bundle"), default=None)
    selection.add_argument("--course-id", choices=COURSE_IDS)
    selection.add_argument("--all-courses", action="store_true",
        help="Fresh sequential one-lap searches for all nine shipped courses")
    parser.add_argument("--course-bundle", type=Path)
    parser.add_argument("--maximum-new-runs", type=int, default=None,
        help="Maximum new rollout calls; required as a shared budget with --all-courses")
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument("--mirror", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--laps", type=int, choices=(1,10), default=10)
    args = parser.parse_args(argv)
    if args.maximum_new_runs is not None and args.maximum_new_runs < 0:
        parser.error("--maximum-new-runs must be nonnegative")
    if (args.course_id or args.all_courses) and args.course_bundle is not None:
        parser.error("Catalog selection cannot also specify --course-bundle")
    if args.all_courses:
        if args.resume:
            parser.error("Catalog batches are fresh-only; --resume is supported for individual course checkpoints")
        if args.laps != 1 or args.maximum_new_runs is None:
            parser.error("--all-courses requires --laps 1 and explicit --maximum-new-runs")
        result = run_catalog_batch(args.output, maximum_new_runs=args.maximum_new_runs,
            wall_seconds=args.wall_seconds, seed=args.seed, population=args.population,
            generations=args.generations, profile=args.profile, reverse=args.reverse, mirror=args.mirror)
        print(canonical({"status": result["status"], "reserved_rollout_slots": result["budget"]["reserved_rollout_slots"],
                         "courses": [{"id":row["course_id"],"status":row["status"]} for row in result["courses"]]}))
        return 0 if result["status"] == "completed" else 2
    bundle = read_json_bounded(args.course_bundle, maximum_bytes=4_194_304) if args.course_bundle else None
    spec = (catalog_specification(args.course_id, args.seed, args.population, args.generations, args.profile,
                reverse=args.reverse, mirror=args.mirror, laps=args.laps) if args.course_id else
            specification(args.seed, args.population, args.generations, args.profile,
                course=args.course or "stadium", course_bundle=bundle, reverse=args.reverse, mirror=args.mirror,laps=args.laps))
    state = run_search(args.output, spec, resume=args.resume, wall_seconds=args.wall_seconds,
                       maximum_new_runs=args.maximum_new_runs)
    print(canonical({"status": state["status"], "runs": len(state["runs"]),
                     "generations": len(state["generations"]), "best": state["best_so_far"]}))
    return 0 if state["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
