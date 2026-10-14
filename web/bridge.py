"""Finite JSON boundary for the unchanged Python lap engine in a browser.

This module is also importable on CPython for parity tests. It imports no Tk
or Matplotlib UI. A worker owns each fresh vehicle and all mutable run state.
"""
from __future__ import annotations

from dataclasses import replace
from math import ceil, isfinite
from numbers import Real
from typing import Callable, Mapping, Any
import json

from lapsim.events.endurance import EnduranceSimulator
from lapsim.experiments.run_record import LapRunSettings, capture_lap_run
from lapsim.optimization.torque_profile import PeriodicPiecewiseLinearTorqueProfile
from lapsim.profiles import build_vehicle
from lapsim.resources import build_identity
from lapsim.solvers.path_constraints import PathConstraintSolver
from lapsim.ui.course_catalog import COURSE_OPTIONS, course_source_metadata, load_course
from lapsim.ui.simulation import (
    apply_uniform_road_grip, endurance_run_config, path_solver_settings, resample_track,
)

PROTOCOL_VERSION = 1
MAXIMUM_CELLS = 1200
PYODIDE_VERSION = "314.0.7"
PROFILE_IDS = ("prius_2026_le", "repository_baseline")
DEFAULTS = {
    "vehicleProfile": "prius_2026_le",
    "courseId": "synthetic_rounded_rectangle_v1",
    "gripMultiplier": 1.0,
    "torqueFraction": 0.8,
    "brakePressurePsi": 300.0,
    "regenEnabled": False,
    "maxCellLengthM": 2.0,
    "initialSpeedMps": None,
}
RANGES = {
    "gripMultiplier": (0.2, 1.5),
    "torqueFraction": (0.0, 1.0),
    "brakePressurePsi": (10.0, 500.0),
    "maxCellLengthM": (0.5, 10.0),
    "initialSpeedMps": (0.0, 40.0),
}
Progress = Callable[[dict[str, Any]], None]


def normalize_settings(settings: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(settings, Mapping):
        raise ValueError("settings must be an object")
    unknown = set(settings) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown settings: {', '.join(sorted(map(str, unknown)))}")
    result = DEFAULTS | dict(settings)
    if not isinstance(result["vehicleProfile"], str) or result["vehicleProfile"] not in PROFILE_IDS:
        raise ValueError("choose an available built-in vehicle profile")
    if not isinstance(result["courseId"], str) or result["courseId"] not in {spec.course_id for spec in COURSE_OPTIONS}:
        raise ValueError("choose an available built-in course")
    if type(result["regenEnabled"]) is not bool:
        raise ValueError("regenEnabled must be a Boolean")
    for name, (lower, upper) in RANGES.items():
        value = result[name]
        if name == "initialSpeedMps" and value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
            raise ValueError(f"{name} must be a finite number")
        if not lower <= value <= upper:
            raise ValueError(f"{name} must be between {lower:g} and {upper:g}")
        result[name] = float(value)
    return result


def capabilities() -> dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "pyodideVersion": PYODIDE_VERSION,
        "defaults": dict(DEFAULTS),
        "limits": {"maximumCells": MAXIMUM_CELLS, "ranges": RANGES},
        "profiles": [
            {"id": "prius_2026_le", "label": "Prius LE benchmark", "description": "Simplified power-equivalent benchmark; hybrid transaxle is not modeled."},
            {"id": "repository_baseline", "label": "Repository car baseline", "description": "Repository component defaults; not an as-built team vehicle."},
        ],
        "courses": [
            {"id": spec.course_id, "label": spec.label, "description": spec.description,
             "synthetic": spec.synthetic, "lengthM": load_course(spec.course_id).length_m}
            for spec in COURSE_OPTIONS
        ],
        "units": {"elapsedTimeS": "s", "distanceM": "m", "energyKwh": "kWh", "socFinal": "fraction", "speedMps": "m/s", "brakePressurePsi": "psi"},
        "model": "prescribed_path_distance_domain",
        "evidenceLevel": "simulation_model_estimate",
        "sourceIdentity": build_identity(),
        "limitations": [
            "Flat-road, prescribed-curvature lap model with automatic longitudinal control; no interactive vehicle pose.",
            "Uniform grip is an assumed sensitivity, not measured surface calibration.",
            "Fused team course x/y and curvature disagree; its display is a reference map and no racing-line feasibility is established.",
            "Speed and battery state need not be periodic across the lap seam.",
            "Regeneration remains limited by the selected pack and drivetrain; enabling it does not add hardware capacity.",
        ],
    }


def _notify(progress: Progress | None, payload: dict[str, Any]) -> None:
    if progress is not None:
        progress(payload)


def run_simulation(settings: Mapping[str, Any], progress: Progress | None = None) -> dict[str, Any]:
    selected = normalize_settings(settings)
    source = load_course(selected["courseId"])
    if ceil(source.length_m / selected["maxCellLengthM"]) > MAXIMUM_CELLS:
        minimum_step = source.length_m / MAXIMUM_CELLS
        raise ValueError(f"requested grid exceeds {MAXIMUM_CELLS} browser cells; use at least {minimum_step:.3f} m per cell")
    track = resample_track(source, selected["maxCellLengthM"])
    if track.cell_count > MAXIMUM_CELLS:
        raise ValueError("resampled grid exceeds the browser compute cap")
    vehicle, manifest = build_vehicle(selected["vehicleProfile"])
    vehicle.brakes.maximum_pressure_psi = selected["brakePressurePsi"]
    apply_uniform_road_grip(vehicle, selected["gripMultiplier"])
    vehicle.reset_state()
    solver_settings = path_solver_settings(vehicle)
    config = replace(
        endurance_run_config(vehicle),
        starting_speed_mps=selected["initialSpeedMps"],
        regenerative_braking_soc_threshold=1.0 if selected["regenEnabled"] else None,
        maximum_driving_time_s=600.0,
    )
    spec = next(spec for spec in COURSE_OPTIONS if spec.course_id == selected["courseId"])
    frozen_settings = LapRunSettings.from_track(
        track, track_id=spec.course_id, solver_step_m=selected["maxCellLengthM"],
        solver_settings=solver_settings, torque_request_fraction=selected["torqueFraction"],
        endurance_config=config, road_grip_multiplier=selected["gripMultiplier"],
        profile_id=manifest.profile_id, profile_label=manifest.profile_name,
        source_course=course_source_metadata(spec, source),
    )

    def constraint_update(sample: Any) -> None:
        _notify(progress, {
            "phase": f"constraints/{sample.phase}", "completedCells": sample.completed_cells,
            "totalCells": sample.cell_count, "passNumber": sample.pass_number,
            "maximumPasses": sample.maximum_passes,
        })

    constraints = PathConstraintSolver(**solver_settings).solve(
        track, vehicle, progress_callback=constraint_update if progress else None,
    )
    profile = PeriodicPiecewiseLinearTorqueProfile(
        track_length_m=track.length_m, knot_distance_m=(0.0, track.length_m * 0.5),
        request_fraction_values=(selected["torqueFraction"],) * 2,
    )

    def lap_update(sample: Any) -> None:
        _notify(progress, {
            "phase": "lap", "completedCells": sample.cell_index + 1,
            "totalCells": sample.cell_count, "elapsedTimeS": sample.elapsed_time_s,
            "distanceM": sample.total_distance_m, "speedMps": sample.speed_mps,
        })

    result = EnduranceSimulator().run(
        vehicle, constraints, profile, config, record_telemetry=True,
        progress_callback=lap_update if progress else None,
    )
    record = capture_lap_run(
        result, manifest, frozen_settings, actual_vehicle=vehicle,
        user_overrides={"brakes.maximum_pressure_psi": selected["brakePressurePsi"]},
    ).to_dict()
    trace = record["telemetry"]
    response = {
        "status": "completed" if result.completed else "failed",
        "elapsedTimeS": result.driving_time_s,
        "distanceM": vehicle.distance_m,
        "energyKwh": result.pack_energy_kwh,
        "socFinal": result.final_state_of_charge,
        "failureReason": result.failure_reason,
        "acceptedTimeS": result.accepted_time_s,
        "acceptedDistanceM": result.accepted_distance_m,
        "acceptedSpeedMps": result.accepted_speed_mps,
        "startingSpeedMps": result.starting_speed_mps,
        "endingSpeedMps": result.ending_speed_mps,
        "seamSpeedDeltaMps": result.seam_speed_delta_mps,
        "cellCount": track.cell_count,
        "settings": selected,
        "telemetry": {"sampleTimeS": trace["sample_time_s"], "sampleDistanceM": trace["sample_distance_m"], "channels": trace["channels"]},
        "courseGeometry": {"distanceM": track.distance_m, "xM": track.x_m, "yM": track.y_m, "curvaturePerM": track.curvature_per_m},
        "runRecord": record,
        # Preserve Python float spelling across JavaScript JSON.parse/stringify.
        # The standard record content hash depends on its canonical Python JSON.
        "runRecordJson": json.dumps(record, indent=2, allow_nan=False),
        "provenance": {"course": frozen_settings.to_dict()["track"], "profile": manifest.to_dict(), "sourceIdentity": build_identity(), "runtime": record["runtime"]},
        "warnings": record["validity"]["warnings"],
    }
    # Fail rather than passing NaN/Infinity into charts or a downloadable record.
    return json.loads(json.dumps(response, allow_nan=False))


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON value is forbidden: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def run_simulation_json(raw: str, progress: Progress | None = None) -> str:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > 8192:
        raise ValueError("settings JSON must be a string of at most 8192 bytes")
    settings = json.loads(raw, parse_constant=_reject_constant, object_pairs_hook=_reject_duplicate_keys)
    return json.dumps(run_simulation(settings, progress), allow_nan=False, separators=(",", ":"))
