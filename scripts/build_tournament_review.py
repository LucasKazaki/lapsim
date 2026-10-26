"""Project completed R11 records into a portable static replay; never run physics."""

import argparse
import hashlib
import json
import re
from datetime import datetime, UTC
from pathlib import Path


def provenance_labels(data):
    """Validate supplied identities and derive the text used by the video HUD."""
    if data.get("schema") != "lapsim.static-tournament-review.v1":
        raise ValueError("Unsupported saved review schema")
    for key in ("acceptance_commit", "numerical_checkpoint"):
        value = data.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{7,40}", value):
            raise ValueError(f"A recorded Git identity is required: {key}")
    evidence = datetime.fromisoformat(data["evidence_utc"].replace("Z", "+00:00"))
    if evidence.utcoffset() is None:
        raise ValueError("Evidence time must include a timezone")
    coverage = data.get("coverage")
    if not isinstance(coverage, str) or not coverage.strip():
        raise ValueError("Recorded coverage is required")
    return {
        "evidence": evidence.astimezone(UTC).strftime("%d %b %Y | evidence %H:%M UTC"),
        "source": f"Source {data['acceptance_commit'][:7]} / numerical {data['numerical_checkpoint'][:7]}",
        "coverage": " ".join(coverage.split()),
    }


def policy_origin(case, index):
    """Report recorded profile/generation ancestry without inferring search success."""
    identity = case["profile"].get("profile_id", "")
    generation = index.get("generation") or {}
    ancestry = generation.get("ancestry", {})
    for row in index["final_selection"].get("heldout", []):
        if row["id"] == case["id"]:
            return {
                "kind": "heldout_reuse",
                "parent": row["parent"],
                "label": f"Held-out reuse of {row['parent']}; historical selection frozen before evaluation",
            }
    if identity == "r11-structured-offspring":
        parents = ancestry.get("parents_used", [])
        return {
            "kind": "crossover_mutation",
            "seed": ancestry.get("seed"),
            "parents_used": parents,
            "label": "Crossover + structural mutation"
            + (
                " of " + " / ".join(parents)
                if parents
                else "; exact parents unavailable"
            ),
        }
    sample = re.fullmatch(r"r11-sample-(\d+)-(\d+)", identity)
    if sample:
        seed, draw = map(int, sample.groups())
        immigrant = (
            case["id"] in generation.get("cases", [])
            and seed == ancestry.get("seed", -2) + 1
        )
        label = "Seeded immigrant" if immigrant else "Seeded Latin-hypercube sample"
        return {
            "kind": "immigrant" if immigrant else "seeded_sample",
            "seed": seed,
            "draw": draw,
            "label": f"{label}; seed {seed}, draw {draw}",
        }
    if identity.startswith("synthetic-"):
        return {
            "kind": "recorded_baseline",
            "label": "Recorded topology bridge"
            if "bridge" in case["id"]
            else "Recorded baseline policy",
        }
    return {
        "kind": "unavailable",
        "label": "Sampling origin not retained in this record",
    }


def build(review_root, output, acceptance_commit, numerical_checkpoint):
    index_path = review_root / "review-index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    groups = {}
    cases = []
    excluded_ids = [
        row["id"] for row in index["final_selection"]["development"]["excluded"]
    ]
    columns = [
        "t_s",
        "x_m",
        "y_m",
        "heading_rad",
        "u_mps",
        "progress_m",
        "pack_energy_j",
        "pack_power_w",
        "regen_request_nm",
        "brake_shortfall_nm",
    ]
    for case in index["cases"]:
        name = case["id"]
        path = review_root / (name + ".viewer.json")
        if not path.is_file():
            raise FileNotFoundError(f"Indexed viewer missing; export stopped: {path}")
        viewer_bytes = path.read_bytes()
        viewer = json.loads(viewer_bytes)
        run = next(iter(viewer["runs"].values()))
        course = run["course"]
        key = course["geometry_sha256"] + ":" + case["hardware_sha256"]
        if key not in groups:
            groups[key] = {
                "id": key,
                "label": course["label"],
                "length_m": course["length_m"],
                "geometry_sha256": course["geometry_sha256"],
                "hardware_sha256": case["hardware_sha256"],
                "xy": list(zip(course["x_m"], course["y_m"], strict=True)),
                "provenance": course.get("input_evidence", {}),
                "runs": [],
            }
        profile = case["profile"]
        record = {
            "id": name,
            "accepted": case["accepted"],
            "status": run["status"],
            "selection_eligible": not any(
                name == ident or name.startswith(ident + "-") for ident in excluded_ids
            ),
            "time_s": case["time_s"],
            "energy_wh": case["net_energy_kwh"] * 1000,
            "completed_laps": case["completed_laps"],
            "target_laps": run["round"]["target_laps"],
            "policy": profile["controller"],
            "profile_id": profile.get("profile_id"),
            "policy_origin": policy_origin(case, index),
            "architecture": profile["architecture"],
            "metrics": case["metrics"],
            "mode_occupancy": case["mode_occupancy"],
            "failure_reasons": case.get("failure_reasons", []),
            "effective_policy_sha256": case["effective_policy_sha256"],
            "viewer_sha256": hashlib.sha256(viewer_bytes).hexdigest(),
            "source_path": path.name,
            "laps": [
                {
                    k: lap[k]
                    for k in ["lap", "finish_time_s", "lap_time_s", "net_energy_kwh"]
                }
                for lap in run["round"]["laps"]
            ],
            "samples": [[row.get(k) for k in columns] for row in run["telemetry"]],
        }
        groups[key]["runs"].append(record)
        cases.append(record)
    if not cases:
        raise ValueError("No indexed records; export stopped")
    data = {
        "schema": "lapsim.static-tournament-review.v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "evidence_utc": index["created_utc"],
        "acceptance_commit": acceptance_commit,
        "numerical_checkpoint": numerical_checkpoint,
        "source_index_sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
        "columns": columns,
        "groups": list(groups.values()),
        "excluded": index["final_selection"]["development"]["excluded"],
        "coverage": (
            f"Saved review snapshot: {sum(bool(case['accepted']) for case in cases)} accepted "
            f"of {len(cases)} indexed records across {len(groups)} matched strata. "
            "Coverage is limited to these indexed records; unrelated or in-flight campaigns are not included."
        ),
        "scope": index["boundaries"],
        "selection": index["final_selection"]["development"]["selection"],
        "projection": "Unmodified saved display samples (500 ms plus seam/terminal samples); linear display interpolation only. Dense 10 ms control frames remain in source records.",
    }
    provenance_labels(data)
    output.mkdir(parents=True, exist_ok=True)
    (output / "data.json").write_text(
        json.dumps(data, separators=(",", ":"), allow_nan=False), encoding="utf-8"
    )
    (output / "data.js").write_text(
        "window.LAPSIM_REVIEW="
        + json.dumps(data, separators=(",", ":"), allow_nan=False)
        + ";\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "groups": len(groups),
                "runs": len(cases),
                "output": str(output),
                "bytes": (output / "data.json").stat().st_size,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("web/tournament-review"))
    parser.add_argument("--acceptance-commit", required=True)
    parser.add_argument("--numerical-checkpoint", required=True)
    args = parser.parse_args()
    build(
        args.review_root, args.output, args.acceptance_commit, args.numerical_checkpoint
    )
