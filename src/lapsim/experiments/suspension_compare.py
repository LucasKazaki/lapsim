"""Compare two saved native studies without an engine, replay, or input writes."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import sys

from .dynamics_record import _canonical_json, _content_id
from .suspension_export import require_native_world_si_claims
from .suspension_study import (
    SOURCE_HASH_SCOPE,
    SuspensionScenario,
    inspect_study_record,
    read_study_record,
)

KINDS = {"plant-step": "plant_step_s", "logging-period": "logging_period_s"}
MAX_LISTED_TIMES = 2003  # Existing 2,001 regular samples plus two forced boundaries.
CLOCKS = (
    "time_s",
    "tire_force_source_time_s",
    "tire_kinematics_source_time_s",
    "applied_tire_force_source_time_s",
    "applied_tire_force_geometry_time_s",
)
CRITERION = "quality/test_chrono_native.py::test_timestep_refinement_changes_small_physical_quantities_by_less_than_one_percent"
# Accepted synthetic fixture's stored model/input/initial-observation claims.
# Git identity and historical execution measurements do not enter this digest.
REFERENCE_PHYSICAL_CLAIM_SHA256 = (
    "1670f90e9defdd392372e4952e632a085dcd66d01f292edea17a0f90f7e6a6d9"
)
SCOPE = (
    "Comparison of untrusted saved observations and recorded claims only; "
    "no fresh native replay, authenticity, vehicle calibration, physical validation, "
    "performance winner, or historical timing verification."
)
REPORT_SCHEMA = "lapsim.native-suspension-comparison.v1"
RECIPE_SCHEMA = "lapsim.native-suspension-comparison-recipe.v1"
RECIPE_HASH_SCOPE = (
    "Explicit comparison/validation/source-match files; source bytes with CRLF "
    "normalized to LF only; not a complete transitive environment fingerprint"
)
RECIPE_FILES = (
    "experiments/suspension_compare.py",
    "experiments/suspension_study.py",
    "dynamics/native_plant.py",
    "dynamics/chrono_vehicle.py",
    "experiments/dynamics_record.py",
    "experiments/record_io.py",
    "experiments/basic_dynamics.py",
    "experiments/suspension_export.py",
)


def _comparison_recipe() -> dict:
    """Identify observed source files, without importing a backend or using Git."""
    package = Path(__file__).parent.parent
    hashes: dict[str, str | None] = {}
    statuses: dict[str, str] = {}
    for name in RECIPE_FILES:
        try:
            raw = (package / name).read_bytes()
        except FileNotFoundError:
            hashes[name], statuses[name] = None, "missing"
        except OSError:
            hashes[name], statuses[name] = None, "unreadable"
        else:
            hashes[name] = sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
            statuses[name] = "readable"
    complete = all(status == "readable" for status in statuses.values())
    recipe: dict = {
        "schema": RECIPE_SCHEMA,
        "hash_scope": RECIPE_HASH_SCOPE,
        "status": "complete" if complete else "incomplete",
        "files_sha256": hashes,
        "file_status": statuses,
        "criterion_reference": CRITERION,
        "reference_physical_claim_sha256": REFERENCE_PHYSICAL_CLAIM_SHA256,
    }
    recipe["recipe_id"] = _content_id(recipe) if complete else None
    return recipe


def _calculation_projection(report) -> dict:
    """Exclude historical receipts/timing and ambient identity from calculation ID."""
    return {
        "schema": report["schema"],
        "comparison_kind": report["comparison_kind"],
        "scope": report["scope"],
        "input_content_ids": {
            role: report["inputs"][role]["inspection"]["saved_content_id"]
            for role in ("left", "right")
        },
        "comparison_recipe": report["comparison_recipe"],
        "status": report["status"],
        "compatibility": {
            key: (
                sorted(report["compatibility"][key])
                if key == "reasons"
                else report["compatibility"][key]
            )
            for key in (
                "compatible_recorded_claims",
                "reasons",
                "allowed_scenario_field",
                "selected_field",
            )
        },
        "result": report["result"],
    }


def _saved_equal(left, right):
    """Match recorded JSON values, independent of Python list/tuple storage."""
    return _canonical_json(left) == _canonical_json(right)


def _compatibility(left, right, field):
    reasons = []
    for name in (
        "model",
        "capabilities",
        "frame",
        "units",
        "wheel_order",
        "controller",
        "commands",
    ):
        if not _saved_equal(left[name], right[name]):
            reasons.append("payload." + name + " differs")
    for label, payload in (("left", left), ("right", right)):
        model = payload["model"]
        if not isinstance(model.get("profile_id"), str) or not model["profile_id"]:
            reasons.append(label + " recorded model.profile_id is missing")
        for name in ("engine", "assets_sha256"):
            if not isinstance(model.get(name), dict) or not model[name]:
                reasons.append(label + " recorded model." + name + " is missing")
        if payload["source"]["hash_scope"] != SOURCE_HASH_SCOPE:
            reasons.append(label + " implementation hash scope is unsupported")
    for name in ("hash_scope", "files_sha256"):
        if not _saved_equal(left["source"][name], right["source"][name]):
            reasons.append("payload.source." + name + " differs")
    for name in left["scenario"]:
        if name != field and left["scenario"][name] != right["scenario"][name]:
            reasons.append("payload.scenario." + name + " differs")
    if not _saved_equal(left["samples"][0], right["samples"][0]):
        reasons.append("initial recorded observation differs")
    return reasons


def _clocks(sample):
    return {key: sample[key] for key in CLOCKS}


def _times(values):
    return {
        "count": len(values),
        "times_s": values[:MAX_LISTED_TIMES],
        "truncated": len(values) > MAX_LISTED_TIMES,
    }


def _logging_result(left, right):
    a, b = left["samples"], right["samples"]
    i = j = 0
    shared, left_only, right_only = [], [], []
    differences = Counter()
    mismatch_count = 0
    examples = []
    while i < len(a) and j < len(b):
        if a[i]["time_s"] < b[j]["time_s"]:
            left_only.append(a[i]["time_s"])
            i += 1
        elif b[j]["time_s"] < a[i]["time_s"]:
            right_only.append(b[j]["time_s"])
            j += 1
        else:
            shared.append(a[i]["time_s"])
            fields = sorted(
                key for key in a[i] if not _saved_equal(a[i][key], b[j][key])
            )
            if fields:
                mismatch_count += 1
                differences.update(fields)
                if len(examples) < 5:
                    examples.append(
                        {
                            "left_clocks": _clocks(a[i]),
                            "right_clocks": _clocks(b[j]),
                            "different_fields": fields,
                        }
                    )
            i += 1
            j += 1
    left_only.extend(sample["time_s"] for sample in a[i:])
    right_only.extend(sample["time_s"] for sample in b[j:])
    return {
        "alignment": "exact stored state timestamps; no rounding, tolerance, index alignment or interpolation",
        "time_listing_limit": MAX_LISTED_TIMES,
        "shared": _times(shared),
        "left_unmatched": _times(left_only),
        "right_unmatched": _times(right_only),
        "all_shared_observations_equal": mismatch_count == 0,
        "different_shared_observations": mismatch_count,
        "different_field_counts": dict(sorted(differences.items())),
        "first_five_mismatch_examples": examples,
        "stored_metric_claims_equal": _saved_equal(left["metrics"], right["metrics"]),
        "settling_scope": "stored streaming metrics are claims; sparse exports do not revalidate dense settling",
    }


def _delta(left, right, name):
    try:
        value = right - left
        finite = isfinite(value)
    except OverflowError as error:
        raise ValueError(
            "Finite saved values overflow comparison delta at " + name
        ) from error
    if not finite:
        raise ValueError("Finite saved values overflow comparison delta at " + name)
    return {
        "left": left,
        "right": right,
        "right_minus_left": value,
        "absolute_difference": abs(value),
    }


def _criterion_checks(quantities, fine):
    velocity = quantities["world_x_velocity_mps"]
    checks: list[dict] = [
        {
            "quantity": "world_x_velocity_mps",
            "absolute_difference": velocity["absolute_difference"],
            "limit": max(1e-12, 0.01 * abs(velocity[fine])),
        }
    ]
    checks.append(
        {
            "quantity": "chassis_com_height_m",
            "absolute_difference": quantities["chassis_com_height_m"][
                "absolute_difference"
            ],
            "limit": 0.001,
        }
    )
    checks.extend(
        {
            "quantity": "spring_length_m." + item["wheel"],
            "absolute_difference": item["absolute_difference"],
            "limit": 0.001,
        }
        for item in quantities["spring_lengths_m"]
    )
    for check in checks:
        check["passed"] = check["absolute_difference"] <= check["limit"]
    return checks


def _criterion(left, right, inspections, quantities):
    reference = asdict(SuspensionScenario())
    stock = all(
        payload["scenario"][name] == value
        for payload in (left, right)
        for name, value in reference.items()
        if name != "plant_step_s"
    )
    steps = {left["scenario"]["plant_step_s"], right["scenario"]["plant_step_s"]}
    claim = {
        key: left[key]
        for key in (
            "model",
            "capabilities",
            "frame",
            "units",
            "wheel_order",
            "controller",
            "commands",
        )
    }
    claim["initial_observation"] = left["samples"][0]
    claim_id = sha256(_canonical_json(claim).encode("utf-8")).hexdigest()
    current = all(
        summary["checks"]["current_implementation_files"] == "match"
        for summary in inspections
    )
    scope = "Static fixture endpoint criterion on saved claims; not a new native acceptance run, convergence proof or physical validation."
    reasons = []
    if not stock:
        reasons.append("Recorded scenario differs from the default drive fixture")
    if steps != {0.0005, 0.00025}:
        reasons.append("Requires the 0.0005/0.00025 s plant-step pair")
    if claim_id != REFERENCE_PHYSICAL_CLAIM_SHA256:
        reasons.append(
            "Recorded physical inputs/model/commands/initial state differ from the reference fixture claim"
        )
    if not current:
        reasons.append(
            "Current implementation-file matching is unavailable or does not match; see each input's inspection checks"
        )
    if reasons:
        return {
            "name": CRITERION,
            "status": "not applied",
            "scope": scope,
            "reasons": reasons,
        }
    fine = (
        "left"
        if left["scenario"]["plant_step_s"] < right["scenario"]["plant_step_s"]
        else "right"
    )
    checks = _criterion_checks(quantities, fine)
    return {
        "name": CRITERION,
        "status": "applied to recorded fixture claims",
        "scope": scope,
        "fine_reference": fine,
        "reference_physical_claim_sha256": REFERENCE_PHYSICAL_CLAIM_SHA256,
        "velocity_policy": "abs(coarse - fine) <= max(0.01 * abs(fine), 1e-12); height and springs use absolute 0.001 m only",
        "checks": checks,
        "passed": all(check["passed"] for check in checks),
    }


def _plant_result(left, right, inspections):
    a, b = left["samples"][-1], right["samples"][-1]
    quantities = {
        "world_x_velocity_mps": _delta(
            a["velocity_mps"][0], b["velocity_mps"][0], "final world-X velocity"
        ),
        "chassis_com_height_m": _delta(
            a["position_m"][2], b["position_m"][2], "final COM height"
        ),
        "spring_lengths_m": [
            {"wheel": wheel, **_delta(x, y, "final spring length " + wheel)}
            for wheel, x, y in zip(
                left["wheel_order"],
                a["suspension_spring_length_m"],
                b["suspension_spring_length_m"],
                strict=True,
            )
        ],
    }
    context = {}
    for label, sample in (("left", a), ("right", b)):
        context[label] = {
            "clocks": _clocks(sample),
            "completed_interval_command": sample["command"],
            "computed_world_fz_n": [
                force[2] for force in sample["wheel_force_world_n"]
            ],
            "applied_world_fz_n": [
                force[2] for force in sample["applied_wheel_force_world_n"]
            ],
        }
    return {
        "alignment": "each record's validated final scenario endpoint; actual accumulated timestamps retained, no interpolation or same-time force inference",
        "final_observation_context": context,
        "quantities": quantities,
        "criterion": _criterion(left, right, inspections, quantities),
    }


def compare_study_records(left, right, *, kind):
    """Validate two saved inputs and compare only a declared scenario axis.

    Incompatible recorded claims return a report with no numerical result.
    Corrupt/unsupported inputs and unrepresentable differences raise ValueError.
    Neither input is mutated; this function executes no native physics or replay.
    """
    if kind not in KINDS:
        raise ValueError("Comparison kind must be plant-step or logging-period")
    inspections = [inspect_study_record(record) for record in (left, right)]
    a, b = left["payload"], right["payload"]
    field = KINDS[kind]
    reasons = _compatibility(a, b, field)
    if kind == "plant-step":
        for label, record in (("left", left), ("right", right)):
            try:
                require_native_world_si_claims(record, context="plant-step quantities")
            except ValueError as error:
                reasons.append(f"{label}: {error}")
    git = [
        {key: payload["source"][key] for key in ("code_commit", "dirty_worktree")}
        for payload in (a, b)
    ]
    report = {
        "schema": REPORT_SCHEMA,
        "kind": "saved native suspension comparison",
        "comparison_kind": kind,
        "scope": SCOPE,
        "status": "incompatible" if reasons else "compared",
        "inputs": {
            label: {
                "inspection": summary,
                "initial_observation_clocks": _clocks(payload["samples"][0]),
            }
            for label, summary, payload in zip(
                ("left", "right"), inspections, (a, b), strict=True
            )
        },
        "compatibility": {
            "compatible_recorded_claims": not reasons,
            "reasons": reasons,
            "allowed_scenario_field": field,
            "selected_field": {
                "left": a["scenario"][field],
                "right": b["scenario"][field],
            },
            "git_identity_claims": {
                "left": git[0],
                "right": git[1],
                "equal": git[0] == git[1],
            },
            "git_policy": "Git claims are shown separately; recorded implementation hash scope/files must match",
        },
        "result": None,
    }
    if not reasons:
        report["result"] = (
            _plant_result(a, b, inspections)
            if kind == "plant-step"
            else _logging_result(a, b)
        )
    report["comparison_recipe"] = _comparison_recipe()
    report["report_id"] = _content_id(_calculation_projection(report))
    report["receipt_id"] = _content_id(report)
    return report


def compare_study_files(left: str | Path, right: str | Path, *, kind: str) -> dict:
    """Use the existing 8 MB-per-input reader; never write either input."""
    if kind not in KINDS:
        raise ValueError("Comparison kind must be plant-step or logging-period")
    return compare_study_records(
        read_study_record(left), read_study_record(right), kind=kind
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--kind", required=True, choices=tuple(KINDS))
    args = parser.parse_args(argv)
    try:
        report = compare_study_files(args.left, args.right, kind=args.kind)
        print(json.dumps(report, indent=2, allow_nan=False))
        return 0 if report["status"] == "compared" else 1
    except (OSError, ValueError, TypeError, OverflowError) as error:
        print("Saved native comparison: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
