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
from .tournament_rollout import BOUNDS, PHILOSOPHIES, PROFILES, Case, Controller, rollout

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
    parser.add_argument("--course", choices=("stadium", "autocross", "bundle"), default="stadium")
    parser.add_argument("--course-bundle", type=Path)
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument("--mirror", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--laps", type=int, choices=(1,10), default=10)
    args = parser.parse_args(argv)
    bundle = read_json_bounded(args.course_bundle, maximum_bytes=4_194_304) if args.course_bundle else None
    state = run_search(args.output, specification(args.seed, args.population, args.generations, args.profile,
                       course=args.course, course_bundle=bundle, reverse=args.reverse, mirror=args.mirror,laps=args.laps),
                       resume=args.resume, wall_seconds=args.wall_seconds)
    print(canonical({"status": state["status"], "runs": len(state["runs"]),
                     "generations": len(state["generations"]), "best": state["best_so_far"]}))
    return 0 if state["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
