"""Native, monochrome desktop interface for the LapSim model."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from math import ceil, isfinite
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from dataclasses import asdict, replace
from tkinter import filedialog, messagebox, simpledialog
from typing import Any, Callable

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from lapsim.courses.course_bundle import CourseBundle
from lapsim.courses.spatial_track import SpatialTrack
from lapsim.dynamics.conditions import (
    PlanarEnvironment, PlanarRoad, RectangularGripPatch,
)
from lapsim.dynamics.planar import PlanarState
from lapsim.experiments import LapRunSettings, RunRecord, capture_lap_run, default_run_directory
from lapsim.experiments.pose_run_record import PoseRunRecord, default_pose_run_directory
from lapsim.optimization.pose_driver import (
    PoseDriverRun, PoseDriverSample, PoseDriverSettings, run_pose_driver,
)
from lapsim.profiles import build_vehicle, browse_records, list_profiles
from lapsim.solvers.path_constraints import PathConstraintProgressSnapshot

from .comparison import summarize_lap
from .course_catalog import (
    COURSE_OPTIONS, DEFAULT_COURSE_ID, MAX_SAVED_COURSE_FILES,
    SYNTHETIC_DEMO_COURSE_ID,
    course_source_metadata, imported_course_spec, load_course,
    load_imported_course_catalog, solver_cell_count_for_course,
    solver_track_for_course,
)
from .driver_view import DriverCellDecision, DriverPlayback
from .pose_driver_playback import PoseDriverLivePlayback, PoseDriverPlayback
from .garage import CAR_INPUT_KEYS, ProfileStore, SavedCarProfile
from .presets import VehicleSetup, make_prius_benchmark
from .simulation import (
    SpeedPeriodicPhaseSnapshot,
    apply_uniform_road_grip,
    endurance_run_config,
    path_solver_settings,
    prepare_one_lap_constraints,
    run_one_lap,
)


FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 16, "bold")
AI_SELECTION_MARGIN_S = 0.05
AI_ROAD_UNIFORM = "Uniform (default)"
AI_ROAD_PATCH = "One rectangular low-grip patch (assumed)"
AI_GRID_SENSITIVE_PREFIX = (
    "GRID-SENSITIVE · The fixed paths changed time order or crossed the "
    "selection margin on a finer grid. Their modeled time ranking is "
    "unresolved; the original-grid path and numbers remain displayed. "
    "Original-grid result: "
)


def _ai_road_label(road: PlanarRoad | None, base_grip: float) -> str:
    if road is None or not road.patches:
        return f"Assumed uniform road grip {base_grip * 100:g}%."
    patch = road.patches[0]
    return (
        f"Assumed base grip {base_grip * 100:g}%; rectangle "
        f"x {patch.x_min_m:g}–{patch.x_max_m:g} m, "
        f"y {patch.y_min_m:g}–{patch.y_max_m:g} m at "
        f"{patch.friction_multiplier * 100:g}% of base."
    )
REFERENCE_DRIVER_NOTE = (
    "Reference-map playback: position and heading come from the "
    "distance-aligned x/y map; speed and lateral g come from the "
    "solved run. The ceiling is the next cell's braking limit, not "
    "the complete controller target. Positive battery kW means "
    "discharge; negative means charge. Boxes show accepted-cell "
    "values; the map is not a tracked vehicle pose."
)
POSE_DRIVER_NOTE = (
    "Synthetic four-wheel pose experiment: marker x/y and heading are "
    "integrated vehicle states. Time is only the 80 m pose-model duration. "
    "The reference line and 3 m half-width are assumed; no measured cones, "
    "full body overhang, battery, motor, or thermal model is included. "
    "The optional assumed lower-grip patch covers synthetic world x 36–55 m "
    "and y −3–16 m at 0.3× base grip. Neither condition uses measured dry or "
    "wet-road calibration. "
    "The boxes show recorded pose controls and tracking values; endurance "
    "battery and force channels do not apply to this separate model."
)
POSE_SCENARIO_UNIFORM = "Uniform base grip (1.0×)"
POSE_SCENARIO_PATCH = "Assumed bend patch (0.3×)"
POSE_PREVIEW_MAX_CELL_M = 0.5


def _pose_preview_environment(scenario: str) -> PlanarEnvironment:
    if scenario == POSE_SCENARIO_UNIFORM:
        return PlanarEnvironment()
    if scenario == POSE_SCENARIO_PATCH:
        return PlanarEnvironment(road=PlanarRoad(patches=(
            RectangularGripPatch(36.0, 55.0, -3.0, 16.0, 0.3),
        )))
    raise ValueError(f"Unknown synthetic pose scenario: {scenario!r}")


def _course_geometry_warning(audit: Any) -> str | None:
    """Describe source-map inconsistencies without changing lap inputs."""

    details = []
    if audit.cells_with_chord_excess:
        details.append(
            f"{audit.cells_with_chord_excess:,} map segments exceed their "
            f"assigned travel distance ({audit.total_chord_excess_m:.1f} m "
            "combined excess)."
        )
    if (
        audit.curvature_minus_xy_turn_rad is not None
        and abs(audit.curvature_minus_xy_turn_rad) > 1e-6
    ):
        details.append(
            f"Curvature turns {audit.curvature_signed_turn_rad:.6g} rad versus "
            f"{audit.xy_signed_winding_rad:.6g} rad on the map."
        )
    if audit.maximum_arc_chord_mismatch_m > 1e-6:
        details.append(
            "A prescribed arc chord length differs from its map-cell chord "
            "length by up to "
            f"{audit.maximum_arc_chord_mismatch_m:.6g} m."
        )
    if (
        audit.curvature_integrated_closure_gap_m is not None
        and audit.curvature_integrated_closure_gap_m > 0.01
    ):
        details.append(
            "The integrated curvature path misses closure by "
            f"{audit.curvature_integrated_closure_gap_m:.6g} m."
        )
    if not details:
        return None
    return (
        "Course data mismatch: " + " ".join(details) + " The source map is a "
        "visual reference; default lap physics uses its separate distance "
        "and curvature data."
    )


def _saved_run_path(run_id: str) -> Path:
    """Resolve a content ID inside the local run directory."""

    if len(run_id) != 64 or any(character not in "0123456789abcdef" for character in run_id):
        raise ValueError("Saved run ID is not a SHA-256 content ID")
    return (default_run_directory() / f"{run_id}.json").resolve()


def _ai_trial_label(
    strategy: str | None, strength: float | None, *, ascii_x: bool = False,
) -> str:
    if strategy == "grip_detour":
        return "Grip-aware detour"
    if isinstance(strength, (int, float)) and not isinstance(strength, bool):
        return f"AI offset {strength:g}{'x' if ascii_x else '×'}"
    return "AI trial"


def _linked_ai_run_references(planning: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """Name saved AI trials linked by the primary record."""

    references: list[tuple[str, str]] = []
    baseline = planning.get("baseline_record")
    if isinstance(baseline, dict) and isinstance(baseline.get("run_id"), str):
        references.append(("Geometric baseline", baseline["run_id"]))
    trials = planning.get("candidate_trials")
    if isinstance(trials, list):
        for trial in trials:
            if not isinstance(trial, dict) or not isinstance(trial.get("run_id"), str):
                continue
            label = _ai_trial_label(
                trial.get("strategy"), trial.get("offset_strength"),
            )
            references.append((label, trial["run_id"]))
    return tuple(references)


def _run_evidence_text(label: str, path: Path, record: dict[str, Any]) -> str:
    """Summarize the evidence limits and exact file for a saved run."""

    settings = record.get("settings", {})
    track = settings.get("track", {})
    source = track.get("source_course", {})
    profile = record.get("configuration", {})
    result = record.get("result", {})
    planning = settings.get("path_planning", {})
    conditions = settings.get("conditions", {})
    source_id = source.get("selected_course_id") or track.get("id") or "not recorded"
    source_kind = source.get("source_kind") or "not recorded"
    synthetic = "yes" if source_kind == "synthetic" else "no"
    boundary = source.get("boundary_status") or "not recorded"
    lines = [
        label,
        f"Record ID: {record['run_id']}",
        f"File: {path}",
        "Evidence: simulation model estimate; car validation is not established by this run",
        f"Profile: {profile.get('selected_profile_label') or 'not recorded'}",
        f"Result: {result.get('status') or 'not recorded'}",
        f"Source course: {source_id} ({source_kind}; synthetic: {synthetic})",
        f"Source boundary status: {boundary}",
        f"Solver path: {track.get('id') or 'not recorded'}; "
        f"{track.get('cell_count', 'unknown')} cells",
    ]
    source_corridor = source.get("source_cell_corridor")
    if isinstance(source_corridor, dict):
        lines.append(
            f"Source corridor: {source_corridor.get('status') or 'not recorded'}; "
            f"used by AI planner: {'yes' if source_corridor.get('used_by_ai_planner') else 'no'}"
        )
    if isinstance(conditions, dict):
        schedule = conditions.get("cell_road_grip_multiplier")
        base_grip = conditions.get("road_grip_multiplier")
        if isinstance(schedule, list) and schedule and isinstance(base_grip, (int, float)):
            lines.append(
                f"Road grip: assumed cellwise; base {base_grip:g}×; "
                f"cell range {min(schedule):g}–{max(schedule):g}×"
            )
        elif isinstance(base_grip, (int, float)):
            lines.append(f"Road grip: assumed uniform {base_grip:g}×")
    if isinstance(planning, dict) and planning.get("mode") == "experimental_racing_line":
        corridor = planning.get("corridor") or {}
        lines.append(
            "AI corridor: " + str(corridor.get("source") or "assumption not recorded")
        )
        lines.append(
            f"AI rank status: {planning.get('rank_status') or 'not recorded'}; "
            f"diagnostic only: {'yes' if planning.get('diagnostic_only') else 'no'}"
        )
        strategy = planning.get("selected_strategy") or planning.get("strategy")
        if isinstance(strategy, str):
            lines.append(f"AI path strategy: {strategy}")
        detour = planning.get("grip_detour_search")
        if isinstance(detour, dict) and isinstance(detour.get("status"), str):
            lines.append(
                f"Grip detour search: {detour['status']}; "
                f"{detour.get('reason') or 'no detail recorded'}"
            )
        road_condition = planning.get("road_condition")
        if isinstance(road_condition, dict) and road_condition.get("mode") == (
            "assumed_world_fixed_low_grip_rectangle"
        ):
            patches = road_condition.get("patches")
            if isinstance(patches, list) and patches and isinstance(patches[0], dict):
                patch = patches[0]
                fields = (
                    patch.get("x_min_m"), patch.get("x_max_m"),
                    patch.get("y_min_m"), patch.get("y_max_m"),
                    patch.get("friction_multiplier"),
                )
                if all(type(value) in (int, float) and np.isfinite(value)
                       for value in fields):
                    x_min, x_max, y_min, y_max, fraction = fields
                    lines.append(
                        "AI surface: assumed rectangle X "
                        f"{x_min:g}–{x_max:g} m, Y "
                        f"{y_min:g}–{y_max:g} m, "
                        f"{fraction * 100:g}% of base"
                    )
    return "\n".join(lines)


TRACE_OPTIONS = {
    "Speed": ("vehicle.speed_mps", 3.6, "km/h"),
    "Longitudinal acceleration": (
        "vehicle.longitudinal_acceleration_mps2", 1.0 / 9.80665, "g",
    ),
    "Lateral acceleration": (
        "vehicle.lateral_acceleration_mps2", 1.0 / 9.80665, "g",
    ),
    "Drive force": ("vehicle.drive_force_n", 0.001, "kN"),
    "Friction braking": ("vehicle.friction_braking_force_n", 0.001, "kN"),
    "Regenerative braking": (
        "vehicle.regenerative_braking_force_n", 0.001, "kN",
    ),
    "Driven tire slip": ("tire.driven_slip_percent", 1.0, "%"),
    "Battery power": ("battery.power_w", 0.001, "kW"),
}


DRIVER_CELL_BOXES = (
    ("path_speed_ceiling_mps", "NEXT ENTRY (km/h)", 3.6, ".1f"),
    ("motor_torque_request_nm", "MOTOR REQUEST (N·m)", 1.0, ".1f"),
    ("front_brake_pressure_psi", "FRONT BRAKE (psi)", 1.0, ".1f"),
    ("rear_brake_pressure_psi", "REAR BRAKE (psi)", 1.0, ".1f"),
    ("battery_power_w", "NET BATTERY (kW)", 0.001, "+.2f"),
    ("drive_force_n", "DRIVE FORCE (kN)", 0.001, ".2f"),
    ("friction_braking_force_n", "FRICTION BRAKE (kN)", 0.001, ".2f"),
    ("regenerative_braking_force_n", "REGEN BRAKE (kN)", 0.001, ".2f"),
    ("longitudinal_acceleration_mps2", "LONGITUDINAL (g)", 1.0 / 9.80665, "+.2f"),
)
POSE_DRIVER_BOX_TITLES = (
    "STEER FRONT (°)", "REAR DRIVE (N·m/wheel)",
    "BRAKE FL (N·m)", "BRAKE FR (N·m)", "CROSS-TRACK (m)",
    "HEADING ERROR (°)", "GRIP SAMPLE (×)", "ASSUMED SLACK (m)",
    "YAW RATE (°/s)",
)
POSE_DRIVER_BOX_FORMATS = (
    "+.1f", ".1f", ".1f", ".1f", "+.2f",
    "+.1f", ".2f", ".2f", "+.1f",
)


class LapSimDesktop:
    """Build the Tk desktop application around the shared physics APIs."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("LapSim — Formula SAE Lap Simulator")
        self.root.geometry("1380x900")
        self.root.minsize(1080, 720)

        self.course_options = list(COURSE_OPTIONS)
        self.imported_courses, load_warnings = load_imported_course_catalog(
            default_run_directory().parent / "courses"
        )
        self.course_load_warnings = list(load_warnings)
        for course_id, bundle in tuple(self.imported_courses.items()):
            spec = imported_course_spec(bundle)
            if any(option.label == spec.label for option in self.course_options):
                del self.imported_courses[course_id]
                self.course_load_warnings.append(
                    f"{course_id}: display label conflicts with another saved course"
                )
            else:
                self.course_options.append(spec)
        self.course_spec = COURSE_OPTIONS[0]
        self.course_var = tk.StringVar(value=self.course_spec.label)
        self.track = load_course(self.course_spec.course_id)
        self.course_source_json = json.dumps(
            course_source_metadata(self.course_spec, self.track),
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
        self.course_geometry_audit = self.track.geometry_audit()
        self.result_queue: queue.Queue[tuple[str, Any, BaseException | None]] = (
            queue.Queue()
        )
        self.progress_queue: queue.Queue[tuple[str, str, Any, Any]] = queue.Queue(
            maxsize=1
        )
        self.pose_progress_queue: queue.Queue[
            tuple[Any, PoseDriverSample, PlanarState]
        ] = queue.Queue(maxsize=1)
        self.run_started_at = 0.0
        self.run_in_progress = False
        self.calculation_progress_text = tk.StringVar(value="Calculations · idle")
        self.cell_count_text = tk.StringVar(value="")
        self._calculation_progress_mode = "idle"
        self._calculation_progress_fraction = 0.0
        self._calculation_progress_tick = 0
        self._calculation_progress_after_id: str | None = None
        self.is_dark = tk.BooleanVar(value=False)
        self.profile_store = ProfileStore()
        self.saved_profiles: dict[str, SavedCarProfile] = {
            profile.profile_id: profile
            for profile in self.profile_store.list_profiles()
        }
        self.builtin_profiles = {profile.profile_id: profile for profile in list_profiles()}
        self.profile_var = tk.StringVar()
        self.driving_mode_var = tk.StringVar(value="Centerline (default)")
        self.ai_half_width_var = tk.StringVar(value="2.0")
        self.ai_vehicle_width_var = tk.StringVar(value="1.8")
        self.ai_margin_var = tk.StringVar(value="0.2")
        self.ai_road_condition_var = tk.StringVar(value=AI_ROAD_UNIFORM)
        self.ai_patch_vars = {
            "x_min_m": tk.StringVar(value="36"),
            "x_max_m": tk.StringVar(value="55"),
            "y_min_m": tk.StringVar(value="-3"),
            "y_max_m": tk.StringVar(value="16"),
            "grip_percent_of_base": tk.StringVar(value="30"),
        }
        self.ai_road_menu: tk.OptionMenu | None = None
        self.ai_patch_entries: list[tk.Entry] = []
        self._displayed_ai_road: PlanarRoad | None = None
        self.ai_result_text = tk.StringVar(value="Select AI racing line to compare modeled paths.")
        self.ai_output_values: dict[str, tk.Label] = {}
        self.ai_entries: list[tk.Entry] = []
        self.ai_output_box: tk.LabelFrame | None = None
        self.ai_compare_button: tk.Button | None = None
        self.ai_grid_check_button: tk.Button | None = None
        self.ai_grid_check_text = tk.StringVar(value="")
        self._ai_grid_check_inputs: tuple[Any, float] | None = None
        self._ai_grid_source_signature: tuple[str, ...] | None = None
        self._ai_grid_check_serial = 0
        self._path_comparison: tuple[Any, Any, tuple[float, float, float]] | None = None
        self._selected_path_track: Any = None
        self.compare_a_var = tk.StringVar()
        self.compare_b_var = tk.StringVar()
        self.trace_var = tk.StringVar(value="Speed")
        self.trace_axis_var = tk.StringVar(value="Distance")
        self.profile_display_to_id: dict[str, str] = {}
        self.profile_id_to_display: dict[str, str] = {}
        self.vehicle_label_var = tk.StringVar()
        self.input_help_var = tk.StringVar()
        self.inputs: dict[str, tk.StringVar] = {
            "mass_kg": tk.StringVar(value=f"{VehicleSetup().mass_kg:.1f}"),
            "peak_power_kw": tk.StringVar(value=f"{VehicleSetup().peak_power_kw:.1f}"),
            "wheelbase_m": tk.StringVar(value=f"{VehicleSetup().wheelbase_m:.3f}"),
            "tire_radius_m": tk.StringVar(value=f"{VehicleSetup().tire_radius_m:.3f}"),
            "tire_mu": tk.StringVar(value=f"{VehicleSetup().tire_mu:.2f}"),
            "drag_area_m2": tk.StringVar(value=f"{VehicleSetup().drag_area_m2:.2f}"),
            "top_speed_kph": tk.StringVar(value=f"{VehicleSetup().top_speed_kph:.0f}"),
            "torque_request_percent": tk.StringVar(
                value=f"{VehicleSetup().torque_request_fraction * 100:.0f}"
            ),
            "road_grip_percent": tk.StringVar(value="100"),
            "solver_step_m": tk.StringVar(value="1.0"),
        }
        self.input_entries: list[tk.Entry] = []
        self.entry_by_key: dict[str, tk.Entry] = {}
        self.car_entries: dict[str, tk.Entry] = {}
        self.output_values: dict[str, tk.Label] = {}
        self.canvas: FigureCanvasTkAgg | None = None
        self.course_ax: Any = None
        self.speed_ax: Any = None
        self.figure: Figure | None = None
        self._pan_origin: tuple[
            float, float, tuple[float, float], tuple[float, float]
        ] | None = None
        self._last_result: Any = None
        self._displayed_road_grip_multiplier: float | None = None
        self._comparison_results: tuple[tuple[str, Any], tuple[str, Any]] | None = None
        self._active_tab = "Analysis"
        self.tab_buttons: dict[str, tk.Button] = {}
        self.driver_playback: DriverPlayback | None = None
        self.driver_canvas: tk.Canvas | None = None
        self.driver_play_button: tk.Button | None = None
        self.driver_replay_menu: tk.OptionMenu | None = None
        self.driver_replay_var = tk.StringVar(value="—")
        self._driver_replay_runs: dict[str, tuple[str, Any, str, Any]] = {}
        self.driver_run_label = tk.StringVar(value="Run a lap to load playback")
        self.driver_note_var = tk.StringVar(value=REFERENCE_DRIVER_NOTE)
        self.pose_preview_status = tk.StringVar(value=(
            "Optional 80 m synthetic pose preview has not been run."
        ))
        self.pose_record_status = tk.StringVar(value=(
            "No synthetic trace saved or loaded."
        ))
        self.pose_scenario_var = tk.StringVar(value=POSE_SCENARIO_UNIFORM)
        self.pose_scenario_menu: tk.OptionMenu | None = None
        self._active_pose_scenario = POSE_SCENARIO_UNIFORM
        self.pose_offset_var = tk.StringVar(value="0.0")
        self.pose_offset_entry: tk.Entry | None = None
        self._active_pose_offset_m = 0.0
        self._active_pose_grid_label = ""
        self._active_pose_reference_label = "synthetic centerline (coherent arcs)"
        self.pose_ai_availability = tk.StringVar(value=(
            "Selected AI path preview requires an eligible candidate on the "
            "synthetic demo course."
        ))
        self.pose_preview_button: tk.Button | None = None
        self.pose_ai_preview_button: tk.Button | None = None
        self.pose_save_button: tk.Button | None = None
        self.pose_load_button: tk.Button | None = None
        self._latest_pose_run: PoseDriverRun | None = None
        self.driver_speed_var = tk.StringVar(value="1×")
        self.driver_progress_var = tk.DoubleVar(value=0.0)
        self.driver_values = {
            key: tk.StringVar(value="—")
            for key in ("time", "distance", "speed", "lateral", "heading")
        }
        self.driver_decision_values = {
            key: tk.StringVar(value="—")
            for key, _title, _scale, _format in DRIVER_CELL_BOXES
        }
        self.driver_decision_title_labels: list[tk.Label] = []
        self.driver_heading_title_label: tk.Label | None = None
        self.driver_decision_title = tk.StringVar(value="Solved cell values")
        self._live_decision: DriverCellDecision | None = None
        self._driver_playing = False
        self._driver_playback_time_s = 0.0
        self._driver_last_clock_s = 0.0
        self._driver_after_id: str | None = None
        self._owned_after_ids: set[str] = set()
        self._closed = False
        self._driver_updating_scale = False
        self._driver_look_ahead_m = 80.0
        self._driver_live_mode = False
        self._pose_live_mode = False
        self._driver_stream_active = False
        self._driver_preview_track: Any = None
        self._driver_live_update_serial = 0
        self._pending_input_invalidation = False
        self._result_generation = 0
        self._active_run_input_signature: tuple[str, ...] | None = None
        self._displayed_run_records: tuple[tuple[str, str], ...] = ()
        self.saved_runs_button: tk.Button | None = None
        self._evidence_window: tk.Toplevel | None = None
        self._build_window()
        self.pose_scenario_var.trace_add(
            "write", lambda *_change: self._on_pose_scenario_change(),
        )
        self.pose_offset_var.trace_add(
            "write", lambda *_change: self._on_pose_offset_change(),
        )
        self._refresh_profile_menus()
        self._select_profile("prius_2026_le")
        self._apply_theme()
        self._watch_run_inputs()
        self.root.bind("<Destroy>", self._on_root_destroy, add="+")
        self._schedule_after(100, self._poll_result)
        if self.course_load_warnings:
            self._schedule_after(150, self._show_course_load_warnings)

    def _schedule_after(
        self, delay_ms: int | None, callback: Callable[[], None],
    ) -> str | None:
        """Own a Tk callback so closing this window retires it."""

        if self._closed:
            return None
        after_id: str | None = None

        def invoke() -> None:
            if after_id is not None:
                self._owned_after_ids.discard(after_id)
            if not self._closed:
                callback()

        if delay_ms is None:
            after_id = self.root.after_idle(invoke)
        else:
            after_id = self.root.after(delay_ms, invoke)
        self._owned_after_ids.add(after_id)
        return after_id

    def _on_root_destroy(self, event: tk.Event) -> None:
        if event.widget is not self.root or self._closed:
            return
        self._closed = True
        self._driver_playing = False
        self._driver_after_id = None
        self._pending_input_invalidation = False
        for after_id in tuple(self._owned_after_ids):
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                # Tk may already have retired a callback during destruction.
                pass
        self._owned_after_ids.clear()
        self._calculation_progress_after_id = None

    def _show_course_load_warnings(self) -> None:
        count = len(self.course_load_warnings)
        lines = "\n".join(self.course_load_warnings[:5])
        if count > 5:
            lines += f"\n...and {count - 5} more"
        messagebox.showwarning(
            "Saved courses skipped", lines, parent=self.root,
        )

    def _build_window(self) -> None:
        header = tk.Frame(self.root, padx=10, pady=8)
        header.pack(fill="x")
        tk.Label(header, text="LapSim", font=FONT_TITLE).pack(side="left")
        tk.Label(
            header,
            text="FORMULA SAE · ENDURANCE LAP",
            font=("Segoe UI", 9),
            padx=14,
        ).pack(side="left", anchor="s", pady=3)
        tk.Checkbutton(
            header,
            text="Dark mode",
            variable=self.is_dark,
            command=self._apply_theme,
            font=FONT,
            padx=8,
        ).pack(side="right")
        tk.Button(
            header, text="Four-wheel lab", command=self._open_dynamics_lab,
            relief="raised", bd=1, font=FONT,
        ).pack(side="right", padx=(0, 9))

        main = tk.Frame(self.root, padx=10, pady=4)
        main.pack(fill="both", expand=True)
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(0, weight=1)

        left = tk.Frame(main, width=390)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.grid_propagate(False)
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=1)
        left_canvas = tk.Canvas(left, highlightthickness=0, bd=0)
        left_canvas.grid(row=0, column=0, sticky="nsew")
        left_scroll = tk.Scrollbar(left, orient="vertical", command=left_canvas.yview)
        left_scroll.grid(row=0, column=1, sticky="ns")
        left_canvas.configure(yscrollcommand=left_scroll.set)
        calculation_panel = tk.LabelFrame(
            left, text="Calculate", font=FONT_BOLD, padx=8, pady=6,
            bd=1, relief="solid",
        )
        calculation_panel.grid(row=1, column=0, columnspan=2, sticky="ew")
        input_panel = tk.Frame(left_canvas)
        panel_window = left_canvas.create_window((0, 0), window=input_panel, anchor="nw")
        input_panel.bind(
            "<Configure>",
            lambda _event: left_canvas.configure(scrollregion=left_canvas.bbox("all")),
        )
        left_canvas.bind(
            "<Configure>",
            lambda event: left_canvas.itemconfigure(panel_window, width=event.width),
        )
        right = tk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._build_profiles(input_panel)
        self._build_inputs(input_panel)
        self._build_run_controls(calculation_panel)
        self._build_outputs(input_panel)
        for widget in (left_canvas, input_panel, *self._walk_widgets(input_panel)):
            widget.bind(
                "<MouseWheel>",
                lambda event: left_canvas.yview_scroll(
                    -int(event.delta / 120), "units"
                ),
            )
        self._build_workspace_tabs(right)

        self.footer_label = tk.Label(
            self.root,
            text=self._course_footer_text(),
            anchor="w",
            padx=10,
            pady=5,
            font=("Segoe UI", 9),
        )
        self.footer_label.pack(fill="x")

    def _build_profiles(self, parent: tk.Widget) -> None:
        box = tk.LabelFrame(
            parent, text="Car profile", font=FONT_BOLD, padx=8, pady=7,
            bd=1, relief="solid",
        )
        box.pack(fill="x", pady=(0, 8))
        self.profile_menu = tk.OptionMenu(box, self.profile_var, "Loading profiles")
        self.profile_menu.configure(relief="raised", bd=1, anchor="w", font=FONT)
        self.profile_menu.pack(fill="x")
        buttons = tk.Frame(box)
        buttons.pack(fill="x", pady=(5, 0))
        self.save_profile_button = tk.Button(buttons, text="Save current", command=self._save_profile)
        self.save_profile_button.pack(
            side="left", padx=(0, 4)
        )
        self.delete_profile_button = tk.Button(buttons, text="Delete saved", command=self._delete_profile)
        self.delete_profile_button.pack(
            side="left", padx=(0, 4)
        )
        tk.Button(buttons, text="Source data", command=self._open_source_browser).pack(
            side="right"
        )
        tk.Button(buttons, text="Model notes", command=self._open_model_notes).pack(
            side="right", padx=(0, 4)
        )
        self.profile_description = tk.Label(
            box, textvariable=self.input_help_var, anchor="w", justify="left",
            wraplength=355, font=("Segoe UI", 9),
        )
        self.profile_description.pack(fill="x", pady=(5, 0))

    def _build_inputs(self, parent: tk.Widget) -> None:
        box = tk.LabelFrame(
            parent,
            text="Vehicle inputs",
            font=FONT_BOLD,
            padx=8,
            pady=8,
            bd=1,
            relief="solid",
        )
        box.pack(fill="x", pady=(0, 8))
        tk.Label(box, textvariable=self.vehicle_label_var, anchor="w", font=FONT_BOLD).grid(
            row=0, column=0, columnspan=3, sticky="ew", pady=(0, 3)
        )
        tk.Label(
            box,
            text="Car values are editable for Prius profiles. Run settings apply to all cars.",
            anchor="w",
            justify="left",
            wraplength=350,
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 7))

        rows = (
            ("Mass", "mass_kg", "kg"),
            ("Net system power", "peak_power_kw", "kW"),
            ("Wheelbase", "wheelbase_m", "m"),
            ("Tire radius", "tire_radius_m", "m"),
            ("Tire friction μ", "tire_mu", "—"),
            ("Drag area CdA", "drag_area_m2", "m²"),
            ("Speed limit", "top_speed_kph", "km/h"),
            ("Driver request", "torque_request_percent", "%"),
        )
        self.input_entries.clear()
        for row, (label, key, unit) in enumerate(rows, start=2):
            tk.Label(box, text=label, anchor="w").grid(
                row=row, column=0, sticky="w", padx=(0, 6), pady=2
            )
            entry = tk.Entry(
                box,
                textvariable=self.inputs[key],
                width=13,
                justify="right",
                relief="solid",
                bd=1,
                font=FONT,
            )
            entry.grid(row=row, column=1, sticky="ew", pady=2)
            self.input_entries.append(entry)
            self.entry_by_key[key] = entry
            if key in CAR_INPUT_KEYS:
                self.car_entries[key] = entry
            tk.Label(box, text=unit, width=5, anchor="w").grid(
                row=row, column=2, sticky="w", padx=(5, 0), pady=2
            )
        box.grid_columnconfigure(1, weight=1)

        path_box = tk.LabelFrame(
            parent, text="Driving path", font=FONT_BOLD,
            padx=8, pady=8, bd=1, relief="solid",
        )
        path_box.pack(fill="x", pady=(0, 8), before=box)
        tk.Label(path_box, text="Course", anchor="w").grid(row=0, column=0, sticky="w")
        self.course_menu = tk.OptionMenu(
            path_box, self.course_var, *(option.label for option in self.course_options),
            command=self._select_course,
        )
        self.course_menu.configure(relief="raised", bd=1, anchor="w", font=FONT)
        self.course_menu.grid(row=0, column=1, columnspan=2, sticky="ew", pady=(0, 5))
        self.import_course_button = tk.Button(
            path_box, text="Import course…", command=self._choose_course_bundle,
            relief="raised", bd=1, font=FONT,
        )
        self.import_course_button.grid(row=0, column=3, sticky="ew", padx=(5, 0), pady=(0, 5))
        tk.Label(path_box, text="Mode", anchor="w").grid(row=1, column=0, sticky="w")
        self.driving_mode_menu = tk.OptionMenu(
            path_box, self.driving_mode_var,
            "Centerline (default)", "AI racing line (experimental)",
            command=lambda _value: self._on_driving_mode_change(),
        )
        self.driving_mode_menu.configure(relief="raised", bd=1, anchor="w", font=FONT)
        self.driving_mode_menu.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(0, 5))
        tk.Label(path_box, text="Assumed road grip", anchor="w").grid(
            row=2, column=0, sticky="w", pady=2,
        )
        road_grip_entry = tk.Entry(
            path_box, textvariable=self.inputs["road_grip_percent"],
            width=11, justify="right", relief="solid", bd=1, font=FONT,
        )
        road_grip_entry.grid(row=2, column=1, sticky="ew", pady=2)
        self.entry_by_key["road_grip_percent"] = road_grip_entry
        tk.Label(path_box, text="%").grid(row=2, column=2, sticky="w", padx=(5, 0))
        for row, (label, variable) in enumerate((
            ("Assumed half-width", self.ai_half_width_var),
            ("Vehicle width", self.ai_vehicle_width_var),
            ("Safety margin", self.ai_margin_var),
        ), start=3):
            tk.Label(path_box, text=label, anchor="w").grid(row=row, column=0, sticky="w", pady=2)
            entry = tk.Entry(
                path_box, textvariable=variable, width=11, justify="right",
                relief="solid", bd=1, font=FONT,
            )
            entry.grid(row=row, column=1, sticky="ew", pady=2)
            self.ai_entries.append(entry)
            tk.Label(path_box, text="m").grid(row=row, column=2, sticky="w", padx=(5, 0))
        tk.Label(path_box, text="AI trial surface", anchor="w").grid(
            row=6, column=0, sticky="w", pady=2,
        )
        self.ai_road_menu = tk.OptionMenu(
            path_box, self.ai_road_condition_var,
            AI_ROAD_UNIFORM, AI_ROAD_PATCH,
            command=lambda _value: self._on_driving_mode_change(),
        )
        self.ai_road_menu.configure(relief="raised", bd=1, anchor="w", font=FONT)
        self.ai_road_menu.grid(row=6, column=1, columnspan=3, sticky="ew", pady=2)
        for row, (label, key, unit) in enumerate((
            ("Patch X minimum", "x_min_m", "m"),
            ("Patch X maximum", "x_max_m", "m"),
            ("Patch Y minimum", "y_min_m", "m"),
            ("Patch Y maximum", "y_max_m", "m"),
            ("Patch grip of base", "grip_percent_of_base", "%"),
        ), start=7):
            tk.Label(path_box, text=label, anchor="w").grid(
                row=row, column=0, sticky="w", pady=2,
            )
            entry = tk.Entry(
                path_box, textvariable=self.ai_patch_vars[key], width=11,
                justify="right", relief="solid", bd=1, font=FONT,
            )
            entry.grid(row=row, column=1, sticky="ew", pady=2)
            self.ai_patch_entries.append(entry)
            tk.Label(path_box, text=unit).grid(
                row=row, column=2, sticky="w", padx=(5, 0),
            )
        path_box.grid_columnconfigure(1, weight=1)
        tk.Label(
            path_box,
            text=("AI mode uses a deterministic path optimizer and an assumed "
                  "uniform corridor. No measured course widths are available. "
                  "It uses Cell size (max) in Calculate for its path grid and "
                  "up to four geometry paths, with two "
                  "speed-seam passes per path. Its fourth path can follow "
                  "the selected car's eligible lap times. A lower-grip "
                  "rectangle can add one smooth detour and two more passes. "
                  "The optional rectangular surface reduces whole-cell grip "
                  "when a nominal wheel touches it; it is an assumed "
                  "sensitivity, not measured tire or road data. "
                  "Its rebuilt x/y course has different lap times from the "
                  "default source-curvature course. Smaller cells can take "
                  "longer. Synthetic straights/arcs retain their "
                  "exact geometry at 0.5 m or finer cells."),
            justify="left", anchor="w", wraplength=350, font=("Segoe UI", 9),
        ).grid(row=12, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self._on_driving_mode_change()

    def _build_run_controls(self, parent: tk.Widget) -> None:
        """Keep the run action and its progress visible while inputs scroll."""

        settings = tk.LabelFrame(
            parent, text="Calculation settings", font=FONT_BOLD,
            padx=6, pady=4, bd=1, relief="solid",
        )
        settings.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        tk.Label(settings, text="Cell size (max)").grid(
            row=0, column=0, sticky="w", padx=(0, 5),
        )
        cell_entry = tk.Entry(
            settings, textvariable=self.inputs["solver_step_m"], width=10,
            justify="right", relief="solid", bd=1, font=FONT,
        )
        cell_entry.grid(row=0, column=1, sticky="ew")
        self.entry_by_key["solver_step_m"] = cell_entry
        tk.Label(settings, text="m").grid(row=0, column=2, sticky="w", padx=(5, 0))
        tk.Label(settings, textvariable=self.cell_count_text, anchor="w").grid(
            row=1, column=0, columnspan=3, sticky="ew", pady=(3, 0),
        )
        settings.grid_columnconfigure(1, weight=1)
        self.inputs["solver_step_m"].trace_add(
            "write", lambda *_change: self._update_cell_count_hint(),
        )
        self._update_cell_count_hint()

        self.run_button = tk.Button(
            parent,
            text="Run one lap",
            command=self._start_run,
            relief="raised",
            bd=1,
            padx=8,
            pady=5,
            font=FONT_BOLD,
        )
        self.run_button.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(0, 3))
        self.saved_runs_button = tk.Button(
            parent,
            text="Saved run details",
            command=self._open_saved_run_details,
            state="disabled",
            relief="raised",
            bd=1,
            padx=8,
            pady=5,
            font=FONT,
        )
        self.saved_runs_button.grid(row=1, column=1, sticky="ew", pady=(0, 3))
        tk.Label(parent, text="Calculation progress", anchor="w", font=FONT_BOLD).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(2, 0),
        )
        tk.Label(
            parent, textvariable=self.calculation_progress_text,
            anchor="w", justify="left", wraplength=350,
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(3, 2))
        self.calculation_progress_bar = tk.Canvas(
            parent, height=15, bd=1, relief="solid", highlightthickness=0,
        )
        self.calculation_progress_bar.grid(
            row=4, column=0, columnspan=2, sticky="ew",
        )
        self.calculation_progress_bar.bind(
            "<Configure>", lambda _event: self._draw_calculation_progress(),
        )
        self.status_text = tk.StringVar(value="Ready")
        tk.Label(
            parent,
            textvariable=self.status_text,
            anchor="w",
            justify="left",
            wraplength=350,
        ).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)

    def _update_cell_count_hint(self) -> None:
        try:
            cell_size_m = float(self.inputs["solver_step_m"].get())
            if not np.isfinite(cell_size_m) or not 0.0 < cell_size_m <= self.track.length_m:
                raise ValueError("invalid cell size")
            count = solver_cell_count_for_course(
                self.course_spec.course_id, self.track, cell_size_m,
            )
            if count > 5000:
                raise ValueError("requested solver grid exceeds the compute cap")
        except (ValueError, OverflowError):
            self.cell_count_text.set("Enter a valid size within the 5,000-cell limit")
        else:
            description = f"Centerline grid: {count:,} cells"
            if self._ai_mode_selected():
                description += " · AI grid varies"
            self.cell_count_text.set(description)

    def _set_displayed_run_records(
        self, records: tuple[tuple[str, str], ...],
    ) -> None:
        if records != self._displayed_run_records and self._evidence_window is not None:
            try:
                if self._evidence_window.winfo_exists():
                    self._evidence_window.destroy()
            except tk.TclError:
                pass
            self._evidence_window = None
        self._displayed_run_records = records
        if self.saved_runs_button is not None:
            self.saved_runs_button.configure(
                state="normal" if records and not self.run_in_progress else "disabled"
            )

    def _open_saved_run_details(self) -> None:
        if not self._displayed_run_records or self.run_in_progress:
            return
        if self._evidence_window is not None:
            try:
                if self._evidence_window.winfo_exists():
                    self._evidence_window.lift()
                    return
            except tk.TclError:
                pass
            self._evidence_window = None
        pending = list(self._displayed_run_records)
        displayed: set[str] = set()
        sections: list[str] = []
        while pending:
            label, run_id = pending.pop(0)
            if run_id in displayed:
                continue
            displayed.add(run_id)
            try:
                path = _saved_run_path(run_id)
                record = RunRecord.load(path).to_dict()
            except (OSError, ValueError, TypeError) as error:
                sections.append(f"{label}\nRecord ID: {run_id}\nCould not read saved run: {error}")
                continue
            sections.append(_run_evidence_text(label, path, record))
            if label == "AI result":
                planning = record.get("settings", {}).get("path_planning", {})
                if isinstance(planning, dict):
                    pending.extend(_linked_ai_run_references(planning))

        window = tk.Toplevel(self.root)
        self._evidence_window = window
        window.title("Saved run evidence")
        window.geometry("800x510")
        window.minsize(560, 330)
        body = tk.Frame(window, padx=10, pady=10)
        body.pack(fill="both", expand=True)
        title = tk.Label(
            body, text="Saved run evidence", font=FONT_TITLE, anchor="w",
        )
        title.pack(fill="x", pady=(0, 4))
        guidance = tk.Label(
            body,
            text="Full record IDs and files for the result currently shown. Select text to copy it.",
            anchor="w", justify="left", wraplength=750,
        )
        guidance.pack(fill="x", pady=(0, 8))
        scroll = tk.Scrollbar(body)
        scroll.pack(side="right", fill="y")
        details = tk.Text(
            body, wrap="word", font=("Consolas", 10), relief="solid", bd=1,
            yscrollcommand=scroll.set,
        )
        details.pack(side="left", fill="both", expand=True)
        scroll.configure(command=details.yview)
        details.insert("1.0", "\n\n".join(sections))
        details.configure(state="disabled")
        background, foreground = self._theme_colors()
        for widget in (window, body, title, guidance, details):
            widget.configure(background=background)
        for widget in (title, guidance, details):
            widget.configure(foreground=foreground)
        details.configure(selectbackground=foreground, selectforeground=background)

    def _build_outputs(self, parent: tk.Widget) -> None:
        box = tk.LabelFrame(
            parent,
            text="Lap outputs",
            font=FONT_BOLD,
            padx=7,
            pady=7,
            bd=1,
            relief="solid",
        )
        box.pack(fill="x", pady=(0, 8))
        outputs = (
            ("Lap time", "lap_time", "s"),
            ("Peak speed", "peak_speed", "km/h"),
            ("Average speed", "average_speed", "km/h"),
            ("Distance", "distance", "m"),
            ("Net energy*", "energy", "kWh"),
            ("Peak lateral", "lateral_g", "g"),
            ("Lap entry speed", "entry_speed", "km/h"),
            ("Lap exit speed", "exit_speed", "km/h"),
        )
        for index, (label, key, unit) in enumerate(outputs):
            row, column = divmod(index, 2)
            card = tk.Frame(box, bd=1, relief="solid", padx=5, pady=4)
            card.grid(row=row, column=column, sticky="ew", padx=2, pady=2)
            tk.Label(card, text=f"{label} ({unit})", anchor="w", font=("Segoe UI", 9)).pack(
                fill="x"
            )
            value = tk.Label(
                card,
                text="—",
                anchor="e",
                padx=5,
                pady=3,
                relief="solid",
                bd=1,
                font=("Consolas", 13, "bold"),
            )
            value.pack(fill="x", pady=(2, 0))
            self.output_values[key] = value
        box.grid_columnconfigure(0, weight=1, uniform="output")
        box.grid_columnconfigure(1, weight=1, uniform="output")
        tk.Label(
            box,
            text=(
                "*Equivalent battery model; not measured Prius fuel or battery use. "
                "Default centerline is one initial-condition pass. AI comparison "
                "closes seam speed only; neither is full-state periodic."
            ),
            anchor="w",
            justify="left",
            wraplength=315,
            font=("Segoe UI", 9),
        ).grid(row=4, column=0, columnspan=2, sticky="ew", padx=2, pady=(5, 0))

        self.ai_output_box = tk.LabelFrame(
            parent, text="Experimental path comparison", font=FONT_BOLD,
            padx=7, pady=7, bd=1, relief="solid",
        )
        for index, (label, key, unit) in enumerate((
            ("Geometric centerline", "baseline", "s"),
            ("Best tested AI path", "candidate", "s"),
            ("Candidate − centerline", "difference", "s"),
            ("Displayed path length", "length", "m"),
        )):
            row, column = divmod(index, 2)
            card = tk.Frame(self.ai_output_box, bd=1, relief="solid", padx=5, pady=4)
            card.grid(row=row, column=column, sticky="ew", padx=2, pady=2)
            tk.Label(card, text=f"{label} ({unit})", anchor="w", font=("Segoe UI", 9)).pack(fill="x")
            value = tk.Label(
                card, text="—", anchor="e", padx=5, pady=3,
                relief="solid", bd=1, font=("Consolas", 13, "bold"),
            )
            value.pack(fill="x", pady=(2, 0))
            self.ai_output_values[key] = value
        self.ai_output_box.grid_columnconfigure(0, weight=1, uniform="ai_output")
        self.ai_output_box.grid_columnconfigure(1, weight=1, uniform="ai_output")
        tk.Label(
            self.ai_output_box, textvariable=self.ai_result_text,
            anchor="w", justify="left", wraplength=345,
            font=("Segoe UI", 9),
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=2, pady=(5, 0))
        self.ai_compare_button = tk.Button(
            self.ai_output_box, text="Compare path numbers",
            command=self._show_path_comparison, state="disabled",
            relief="raised", bd=1,
        )
        self.ai_compare_button.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.ai_grid_check_button = tk.Button(
            self.ai_output_box, text="Check finer grid (optional)",
            command=self._start_ai_grid_check, state="disabled",
            relief="raised", bd=1,
        )
        self.ai_grid_check_button.grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(5, 0),
        )
        tk.Label(
            self.ai_output_box, textvariable=self.ai_grid_check_text,
            anchor="w", justify="left", wraplength=345,
            font=("Segoe UI", 9),
        ).grid(row=5, column=0, columnspan=2, sticky="ew", padx=2, pady=(4, 0))

    def _build_workspace_tabs(self, parent: tk.Widget) -> None:
        tab_bar = tk.Frame(parent)
        tab_bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        for index, name in enumerate(("Analysis", "Driver view", "Timed sessions · WIP")):
            button = tk.Button(
                tab_bar,
                text=name,
                command=lambda selected=name: self._switch_tab(selected),
                relief="raised",
                bd=1,
                font=FONT,
                padx=12,
                pady=5,
            )
            button.grid(row=0, column=index, sticky="ew", padx=(0, 5))
            tab_bar.grid_columnconfigure(index, weight=1)
            self.tab_buttons[name] = button

        body = tk.Frame(parent)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        self.tab_panels: dict[str, tk.Frame] = {}
        for name in self.tab_buttons:
            panel = tk.Frame(body)
            panel.grid(row=0, column=0, sticky="nsew")
            self.tab_panels[name] = panel

        analysis = self.tab_panels["Analysis"]
        analysis.grid_rowconfigure(1, weight=1)
        analysis.grid_columnconfigure(0, weight=1)
        self._build_comparison(analysis)
        self._build_plot(analysis)
        self._build_driver_view(self.tab_panels["Driver view"])
        self._build_timed_sessions_tab(self.tab_panels["Timed sessions · WIP"])
        self._switch_tab("Analysis")

    def _switch_tab(self, name: str) -> None:
        if name not in self.tab_panels:
            raise ValueError(f"Unknown workspace tab: {name}")
        if name != "Driver view":
            self._pause_driver_playback()
        self._active_tab = name
        self.tab_panels[name].tkraise()
        background, foreground = self._theme_colors()
        for tab_name, button in self.tab_buttons.items():
            selected = tab_name == name
            button.configure(
                background=foreground if selected else background,
                foreground=background if selected else foreground,
                relief="sunken" if selected else "raised",
                font=FONT_BOLD if selected else FONT,
            )
        if name == "Driver view":
            self._draw_driver_view()

    def _build_comparison(self, parent: tk.Widget) -> None:
        box = tk.LabelFrame(
            parent, text="Compare car profiles", font=FONT_BOLD, padx=8, pady=7,
            bd=1, relief="solid",
        )
        box.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        box.grid_columnconfigure(0, weight=1)
        box.grid_columnconfigure(1, weight=1)
        self.compare_a_menu = tk.OptionMenu(box, self.compare_a_var, "Profile A")
        self.compare_b_menu = tk.OptionMenu(box, self.compare_b_var, "Profile B")
        for column, menu in enumerate((self.compare_a_menu, self.compare_b_menu)):
            menu.configure(relief="raised", bd=1, anchor="w", font=FONT)
            menu.grid(row=0, column=column, sticky="ew", padx=(0, 5), pady=(0, 4))
        self.compare_button = tk.Button(
            box, text="Run comparison", command=self._start_comparison,
            relief="raised", bd=1, font=FONT_BOLD,
        )
        self.compare_button.grid(row=0, column=2, sticky="ew", pady=(0, 4))
        tk.Label(
            box, text=("Comparisons use saved profile values and the standard "
                       "centerline. Save any edits first."),
            anchor="w", font=("Segoe UI", 9),
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(2, 0))

    def _open_model_notes(self) -> None:
        messagebox.showinfo(
            "Model scope",
            f"Selected course: {self.course_spec.description} The Prius "
            "uses an idealized front-drive power source and assumed tire, drag, "
            "and battery values. TREV working profiles contain partial source "
            "inputs; unspecified parameters inherit the repository model. "
            "Lap-time differences are scenario sensitivity, not measured performance.",
            parent=self.root,
        )

    def _course_footer_text(self) -> str:
        return (
            f"Course: {self.course_spec.label} · profiles are modeling scenarios · "
            "lap outputs are estimates"
        )

    def _course_notice_text(self) -> str:
        warning = _course_geometry_warning(self.course_geometry_audit)
        return self.course_spec.description + (f" {warning}" if warning else "")

    def _choose_course_bundle(self) -> None:
        """Ask for one self-contained course file and report validation errors."""

        if self.run_in_progress:
            return
        selected_path = filedialog.askopenfilename(
            parent=self.root, title="Import course bundle",
            filetypes=(("LapSim course bundle", "*.json"), ("All files", "*.*")),
        )
        if not selected_path:
            return
        try:
            self._import_course_bundle(Path(selected_path))
        except (OSError, ValueError, TypeError) as error:
            messagebox.showerror("Course import failed", str(error), parent=self.root)

    def _import_course_bundle(self, path: Path) -> None:
        """Validate and select a versioned course without editing source code."""

        if self.run_in_progress:
            raise ValueError("Wait for the current lap before importing a course")
        bundle = CourseBundle.load(path)
        spec = imported_course_spec(bundle)
        existing = self.imported_courses.get(spec.course_id)
        if existing is not None and existing.bundle_sha256 != bundle.bundle_sha256:
            raise ValueError(
                "This course ID and revision already have different content; "
                "give the revised course a new revision"
            )
        if existing is None and any(
            option.label == spec.label for option in self.course_options
        ):
            raise ValueError("Imported course display label conflicts with an existing course")
        # Keep a portable local copy. Its content hash identifies the revision;
        # no path in the imported file is followed by the loader.
        directory = default_run_directory().parent / "courses"
        stored_path = directory / f"{bundle.bundle_sha256}.json"
        if existing is None and not stored_path.exists() and directory.exists():
            saved_count = sum(
                1 for saved in directory.iterdir()
                if saved.name.lower().endswith(".json")
            )
            if saved_count >= MAX_SAVED_COURSE_FILES:
                raise ValueError(
                    f"Saved course catalog is limited to {MAX_SAVED_COURSE_FILES} JSON files"
                )
        bundle.save(stored_path)
        if existing is None:
            self.imported_courses[spec.course_id] = bundle
            self.course_options.append(spec)
            if self.course_menu is not None:
                menu = self.course_menu.nametowidget(self.course_menu["menu"])
                menu.add_command(
                    label=spec.label,
                    command=lambda choice=spec.label: self._select_course(choice),
                )
        self._select_course(spec.label)

    def _select_course(self, label: str) -> None:
        """Switch the source course and clear results from the old course."""

        if self.run_in_progress:
            self.course_var.set(self.course_spec.label)
            return
        selected = next(
            (option for option in self.course_options if option.label == label), None
        )
        if selected is None:
            self.course_var.set(self.course_spec.label)
            raise ValueError(f"Unknown course choice: {label!r}")
        if selected.course_id == self.course_spec.course_id:
            return
        bundle = self.imported_courses.get(selected.course_id)
        track = bundle.track if bundle is not None else load_course(selected.course_id)
        source_json = json.dumps(
            course_source_metadata(selected, track, bundle=bundle),
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
        self.course_spec = selected
        self.course_var.set(selected.label)
        self.track = track
        self._update_cell_count_hint()
        self.course_source_json = source_json
        self.course_geometry_audit = track.geometry_audit()
        self.ai_half_width_var.set(f"{selected.default_ai_half_width_m:g}")
        self.ai_vehicle_width_var.set(f"{selected.default_ai_vehicle_width_m:g}")
        self.ai_margin_var.set(f"{selected.default_ai_margin_m:g}")
        self._pause_driver_playback()
        self.driver_playback = None
        self._live_decision = None
        self.driver_note_var.set(REFERENCE_DRIVER_NOTE)
        self._set_driver_box_mode(pose=False)
        self.driver_decision_title.set("Solved cell values")
        self._driver_live_mode = False
        self._pose_live_mode = False
        self._driver_stream_active = False
        self._driver_preview_track = None
        self._driver_live_update_serial += 1
        self._driver_playback_time_s = 0.0
        self.driver_progress_var.set(0.0)
        self.driver_progress.configure(state="disabled")
        if self.driver_play_button is not None:
            self.driver_play_button.configure(state="disabled")
        self.driver_run_label.set("Run a lap to load playback")
        for value in self.driver_values.values():
            value.set("—")
        for value in self.driver_decision_values.values():
            value.set("—")
        self._set_driver_replay_options({}, selected="—")
        self._path_comparison = None
        self._clear_ai_grid_check()
        self._selected_path_track = None
        self._update_pose_ai_preview_availability()
        self._last_result = None
        self._set_displayed_run_records(())
        self._displayed_road_grip_multiplier = None
        self._displayed_ai_road = None
        self._comparison_results = None
        self._pan_origin = None
        for value in self.output_values.values():
            value.configure(text="—")
        for value in self.ai_output_values.values():
            value.configure(text="—")
        self.ai_result_text.set(
            "Run the optional AI mode to compare paths on this course."
        )
        if self.ai_compare_button is not None:
            self.ai_compare_button.configure(state="disabled")
        self.course_warning_label.configure(text=self._course_notice_text())
        self.footer_label.configure(text=self._course_footer_text())
        self.status_text.set(f"Selected {selected.label}")
        self._switch_tab("Analysis")
        self._draw_plots()

    def _refresh_profile_menus(self) -> None:
        self.saved_profiles = {
            profile.profile_id: profile
            for profile in self.profile_store.list_profiles()
        }
        choices = [
            (f"Built-in: {info.name}", info.profile_id)
            for info in self.builtin_profiles.values()
            if info.available
        ]
        choices.extend(
            (f"Saved: {profile.name}", profile.profile_id)
            for profile in self.saved_profiles.values()
        )
        self.profile_display_to_id = dict(choices)
        self.profile_id_to_display = {profile_id: label for label, profile_id in choices}
        for widget, variable, is_current in (
            (self.profile_menu, self.profile_var, True),
            (self.compare_a_menu, self.compare_a_var, False),
            (self.compare_b_menu, self.compare_b_var, False),
        ):
            menu = widget["menu"]
            menu.delete(0, "end")
            for label, profile_id in choices:
                if is_current:
                    menu.add_command(
                        label=label,
                        command=lambda selected=profile_id: self._select_profile(selected),
                    )
                else:
                    menu.add_command(
                        label=label,
                        command=lambda selected=label, target=variable: target.set(selected),
                    )
        if self.compare_a_var.get() not in self.profile_display_to_id:
            first = next(
                (label for label, profile_id in choices if profile_id == "prius_2026_le"),
                choices[0][0],
            )
            self.compare_a_var.set(first)
        if self.compare_b_var.get() not in self.profile_display_to_id:
            second = next(
                (label for label, profile_id in choices if profile_id == "repository_baseline"),
                choices[min(1, len(choices) - 1)][0],
            )
            self.compare_b_var.set(second)

    def _select_profile(self, profile_id: str) -> None:
        self.profile_var.set(self.profile_id_to_display[profile_id])
        editable = profile_id == "prius_2026_le" or profile_id in self.saved_profiles
        for entry in self.car_entries.values():
            entry.configure(state="normal")
        if profile_id in self.saved_profiles:
            setup = self.saved_profiles[profile_id].setup()
            self.vehicle_label_var.set("Saved Prius power-equivalent setup")
            self.input_help_var.set(
                "Local custom profile. Its editable car inputs are model assumptions."
            )
        elif profile_id == "prius_2026_le":
            setup = VehicleSetup()
            self.vehicle_label_var.set("Toyota Prius LE · FWD benchmark")
            self.input_help_var.set(
                "Road-car placeholder with an idealized power curve."
            )
        else:
            vehicle, _manifest = build_vehicle(profile_id)
            self.vehicle_label_var.set(self.builtin_profiles[profile_id].name)
            self.input_help_var.set(self.builtin_profiles[profile_id].description)
            tire_mu = getattr(vehicle.tire, "constant_friction_coefficient", None)
            speed_limit = vehicle.drivetrain.configured_speed_limit_mps
            values = {
                "mass_kg": f"{vehicle.mass_kg:.3f}",
                "peak_power_kw": f"{vehicle.drivetrain.motor.peak_power_w / 1000.0:.1f}",
                "wheelbase_m": f"{vehicle.chassis.wheelbase_m:.4f}",
                "tire_radius_m": f"{vehicle.tire.rolling_radius_m:.4f}",
                "tire_mu": f"{tire_mu:.2f}" if tire_mu is not None else "tire fit",
                "drag_area_m2": f"{vehicle.aero.drag_area_m2:.3f}",
                "top_speed_kph": f"{speed_limit * 3.6:.1f}" if speed_limit else "model",
            }
        if editable:
            values = {
                "mass_kg": f"{setup.mass_kg:.3f}",
                "peak_power_kw": f"{setup.peak_power_kw:.1f}",
                "wheelbase_m": f"{setup.wheelbase_m:.4f}",
                "tire_radius_m": f"{setup.tire_radius_m:.4f}",
                "tire_mu": f"{setup.tire_mu:.3f}",
                "drag_area_m2": f"{setup.drag_area_m2:.3f}",
                "top_speed_kph": f"{setup.top_speed_kph:.1f}",
            }
        for key, value in values.items():
            self.inputs[key].set(value)
            if not editable:
                self.car_entries[key].configure(state="disabled")
        self.status_text.set("Ready")

    def _save_profile(self) -> None:
        profile_id = self.profile_display_to_id.get(self.profile_var.get())
        if profile_id != "prius_2026_le" and profile_id not in self.saved_profiles:
            messagebox.showinfo(
                "Save car profile",
                "This source-backed profile is read-only. Prius benchmark edits can be saved "
                "as separate local car profiles.",
                parent=self.root,
            )
            return
        try:
            setup, _step_m, _torque_fraction = self._read_run_inputs()
            if setup is None:
                raise ValueError("Select an editable Prius profile first")
        except ValueError as error:
            messagebox.showerror("Check vehicle inputs", str(error), parent=self.root)
            return
        name = simpledialog.askstring("Save car profile", "Profile name", parent=self.root)
        if name is None:
            return
        try:
            saved = self.profile_store.save(name, setup)
            self._refresh_profile_menus()
            self._select_profile(saved.profile_id)
        except ValueError as error:
            messagebox.showerror("Could not save profile", str(error), parent=self.root)

    def _delete_profile(self) -> None:
        profile_id = self.profile_display_to_id.get(self.profile_var.get())
        if profile_id not in self.saved_profiles:
            return
        name = self.saved_profiles[profile_id].name
        if not messagebox.askyesno(
            "Delete saved profile", f"Delete '{name}' from this computer?", parent=self.root
        ):
            return
        self.profile_store.delete(profile_id)
        self._refresh_profile_menus()
        self._select_profile("prius_2026_le")

    def _open_source_browser(self) -> None:
        try:
            selected_id = self.profile_display_to_id.get(self.profile_var.get())
            source_profile = selected_id if selected_id and selected_id.startswith("trev5_") else None
            records = tuple(browse_records(profile_id=source_profile))
        except (OSError, ValueError) as error:
            messagebox.showerror("Source data", str(error), parent=self.root)
            return
        if not records:
            messagebox.showinfo(
                "Source data",
                "No local engineering intake was found. Place the supplied data package "
                "in Downloads to browse its source records.",
                parent=self.root,
            )
            return
        window = tk.Toplevel(self.root)
        window.title("LapSim source parameters")
        window.geometry("1000x650")
        window.minsize(700, 480)
        top = tk.Frame(window, padx=8, pady=8)
        top.pack(fill="x")
        tk.Label(top, text="Search", font=FONT_BOLD).pack(side="left", padx=(0, 6))
        search = tk.StringVar()
        tk.Entry(top, textvariable=search, font=FONT).pack(side="left", fill="x", expand=True)
        tk.Label(
            window,
            text="Select a record to see its value, evidence, source, model use and caveat.",
            anchor="w", padx=8,
        ).pack(fill="x")
        body = tk.Frame(window, padx=8, pady=6)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=2)
        body.grid_columnconfigure(1, weight=3)
        body.grid_rowconfigure(0, weight=1)
        record_list = tk.Listbox(body, font=("Consolas", 10), exportselection=False)
        record_list.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        details = tk.Text(body, font=("Consolas", 10), wrap="word", state="disabled")
        details.grid(row=0, column=1, sticky="nsew")
        visible: list[dict[str, Any]] = []

        def refresh(*_args: Any) -> None:
            needle = search.get().strip().casefold()
            visible.clear()
            record_list.delete(0, "end")
            for record in records:
                text = " ".join(str(part) for part in record.values())
                if needle not in text.casefold():
                    continue
                visible.append(record)
                record_list.insert(
                    "end",
                    f"{record.get('parameter_id', '?'):15} "
                    f"{str(record.get('name', ''))[:42]}",
                )

        def show_selected(_event: Any) -> None:
            selection = record_list.curselection()
            if not selection:
                return
            record = visible[selection[0]]
            lines = (
                ("Parameter", record.get("name")),
                ("ID", record.get("parameter_id")),
                ("Configuration", record.get("configuration")),
                ("Subsystem", record.get("subsystem")),
                ("Value", record.get("value_text", record.get("value"))),
                ("Unit", record.get("unit")),
                ("Evidence", record.get("evidence")),
                ("Source", record.get("source_id")),
                ("Locator", record.get("source_locator")),
                ("Model use", record.get("model_use")),
                ("Caveat", record.get("caveat")),
            )
            details.configure(state="normal")
            details.delete("1.0", "end")
            details.insert("end", "\n\n".join(f"{label}: {value}" for label, value in lines))
            details.configure(state="disabled")

        search.trace_add("write", refresh)
        record_list.bind("<<ListboxSelect>>", show_selected)
        refresh()
        self._apply_theme()

    def _build_plot(self, parent: tk.Widget) -> None:
        plot_box = tk.LabelFrame(
            parent,
            text="Course and speed",
            font=FONT_BOLD,
            padx=6,
            pady=5,
            bd=1,
            relief="solid",
        )
        plot_box.grid(row=1, column=0, sticky="nsew")
        plot_box.grid_columnconfigure(0, weight=1)
        plot_box.grid_rowconfigure(2, weight=1)

        controls = tk.Frame(plot_box)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        tk.Button(controls, text="Fit course", command=self._fit_course, padx=7).pack(
            side="left", padx=(0, 4)
        )
        tk.Button(controls, text="Zoom +", command=lambda: self._zoom_axes(0.8)).pack(
            side="left", padx=2
        )
        tk.Button(controls, text="Zoom −", command=lambda: self._zoom_axes(1.25)).pack(
            side="left", padx=2
        )
        tk.Label(controls, text="Trace").pack(side="left", padx=(14, 3))
        self.trace_menu = tk.OptionMenu(
            controls, self.trace_var, *TRACE_OPTIONS,
            command=lambda _choice: self._draw_plots(preserve_course_view=True),
        )
        self.trace_menu.configure(relief="raised", bd=1, width=23, anchor="w")
        self.trace_menu.pack(side="left")
        self.trace_axis_menu = tk.OptionMenu(
            controls, self.trace_axis_var, "Distance", "Time",
            command=lambda _choice: self._draw_plots(preserve_course_view=True),
        )
        self.trace_axis_menu.configure(relief="raised", bd=1, width=8, anchor="w")
        self.trace_axis_menu.pack(side="left", padx=(4, 0))
        tk.Label(
            controls,
            text="Drag map to pan · wheel to zoom",
            anchor="e",
        ).pack(side="right", padx=4)

        self.course_warning_label = tk.Label(
            plot_box,
            text=self._course_notice_text(),
            anchor="w", justify="left", wraplength=780, font=("Segoe UI", 9),
        )
        self.course_warning_label.grid(row=1, column=0, sticky="ew", pady=(0, 5))

        self.figure = Figure(figsize=(9.0, 6.5), dpi=100, constrained_layout=True)
        self.course_ax = self.figure.add_subplot(2, 1, 1)
        self.speed_ax = self.figure.add_subplot(2, 1, 2)
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_box)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=2, column=0, sticky="nsew")
        self.canvas.mpl_connect("button_press_event", self._pan_start)
        self.canvas.mpl_connect("motion_notify_event", self._pan_move)
        self.canvas.mpl_connect("button_release_event", self._pan_end)
        self.canvas.mpl_connect("scroll_event", self._wheel_zoom)
        self._draw_plots()

    def _build_driver_view(self, parent: tk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)
        heading = tk.Frame(parent)
        heading.grid(row=0, column=0, sticky="ew", pady=(2, 5))
        tk.Label(
            heading,
            text="Driver-centered course view",
            font=FONT_BOLD,
            anchor="w",
        ).pack(side="left")
        tk.Label(
            heading,
            textvariable=self.driver_run_label,
            anchor="e",
        ).pack(side="right")

        self.driver_canvas = tk.Canvas(
            parent, highlightthickness=1, bd=0, relief="solid",
        )
        self.driver_canvas.grid(row=1, column=0, sticky="nsew")
        self.driver_canvas.bind("<Configure>", lambda _event: self._draw_driver_view())
        self.driver_canvas.bind("<MouseWheel>", self._zoom_driver_view)

        controls = tk.Frame(parent)
        controls.grid(row=2, column=0, sticky="ew", pady=(7, 2))
        self.driver_play_button = tk.Button(
            controls, text="Play", command=self._toggle_driver_playback,
            state="disabled", width=8,
        )
        self.driver_play_button.pack(side="left", padx=(0, 4))
        tk.Button(controls, text="Start", command=self._reset_driver_playback).pack(
            side="left", padx=(0, 8)
        )
        tk.Label(controls, text="Replay lap").pack(side="left", padx=(0, 3))
        self.driver_replay_menu = tk.OptionMenu(
            controls, self.driver_replay_var, "—",
        )
        self.driver_replay_menu.configure(state="disabled")
        self.driver_replay_menu.pack(side="left", padx=(0, 8))
        tk.Label(controls, text="Playback").pack(side="left", padx=(0, 3))
        tk.OptionMenu(
            controls, self.driver_speed_var, "0.25×", "0.5×", "1×", "2×", "4×",
        ).pack(side="left")
        self.driver_progress = tk.Scale(
            parent,
            orient="horizontal",
            from_=0,
            to=1000,
            resolution=1,
            showvalue=False,
            variable=self.driver_progress_var,
            command=self._on_driver_scrub,
            highlightthickness=0,
        )
        self.driver_progress.grid(row=3, column=0, sticky="ew")

        measures = tk.Frame(parent)
        measures.grid(row=4, column=0, sticky="ew", pady=(3, 5))
        for column, (key, title) in enumerate((
            ("time", "TIME (s)"),
            ("distance", "STATION (m)"),
            ("speed", "SPEED (km/h)"),
            ("lateral", "LATERAL (g)"),
            ("heading", "MAP HEADING (°)"),
        )):
            box = tk.Frame(measures, relief="solid", bd=1, padx=7, pady=5)
            box.grid(row=0, column=column, sticky="ew", padx=(0, 4))
            measures.grid_columnconfigure(column, weight=1)
            title_label = tk.Label(box, text=title, font=("Segoe UI", 8))
            title_label.pack(anchor="w")
            if key == "heading":
                self.driver_heading_title_label = title_label
            tk.Label(
                box, textvariable=self.driver_values[key], font=("Consolas", 12),
                anchor="w",
            ).pack(anchor="w")
        tk.Label(
            parent, textvariable=self.driver_decision_title,
            font=FONT_BOLD, anchor="w",
        ).grid(row=5, column=0, sticky="ew", pady=(3, 3))
        decision_boxes = tk.Frame(parent)
        decision_boxes.grid(row=6, column=0, sticky="ew")
        for column in range(5):
            decision_boxes.grid_columnconfigure(column, weight=1)
        for index, (key, title, _scale, _format) in enumerate(DRIVER_CELL_BOXES):
            row, column = divmod(index, 5)
            box = tk.Frame(decision_boxes, relief="solid", bd=1, padx=7, pady=4)
            box.grid(row=row, column=column, sticky="ew", padx=(0, 4), pady=(0, 4))
            title_label = tk.Label(box, text=title, font=("Segoe UI", 8))
            title_label.pack(anchor="w")
            self.driver_decision_title_labels.append(title_label)
            tk.Label(
                box, textvariable=self.driver_decision_values[key],
                font=("Consolas", 12), anchor="w",
            ).pack(anchor="w")
        tk.Label(
            parent,
            textvariable=self.driver_note_var,
            justify="left",
            anchor="w",
            wraplength=820,
            font=("Segoe UI", 9),
        ).grid(row=7, column=0, sticky="ew", pady=(2, 3))

    def _build_timed_sessions_tab(self, parent: tk.Frame) -> None:
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        canvas = tk.Canvas(parent, highlightthickness=0, bd=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)
        content = tk.Frame(canvas)
        content.grid_columnconfigure(0, weight=1)
        content_window = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(content_window, width=event.width),
        )
        parent = content
        tk.Label(
            parent,
            text="Timed sessions and ghost · Work in Progress",
            font=FONT_TITLE,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(10, 12))
        tk.Label(
            parent,
            text=(
                "Planned teammate workflow: choose a versioned Terps vehicle and "
                "controller, drive a timed session against a ghost, save the "
                "complete run, and generate a comparison report. Recorded control "
                "inputs would then replay through the engineering model with "
                "defined numerical agreement tolerances."
            ),
            justify="left",
            anchor="w",
            wraplength=760,
            font=FONT,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 16))
        tk.Label(
            parent,
            text="Current state",
            font=FONT_BOLD,
            anchor="w",
        ).grid(row=2, column=0, sticky="ew", pady=(0, 5))
        tk.Label(
            parent,
            text=(
                "The desktop app can compare car profiles and save modeled lap "
                "records. Interactive driving, a live ghost, a versioned Terps "
                "controller, and full-session comparison remain unavailable. "
                "The bounded synthetic preview can save its own trace and check "
                "recorded-control replay."
            ),
            justify="left",
            anchor="w",
            wraplength=760,
            font=FONT,
        ).grid(row=3, column=0, sticky="ew", pady=(0, 16))
        tk.Button(
            parent, text="Start timed session (not available)", state="disabled",
            relief="raised", bd=1,
        ).grid(row=4, column=0, sticky="w")
        tk.Label(
            parent,
            text="Bounded driving preview",
            font=FONT_BOLD,
            anchor="w",
        ).grid(row=5, column=0, sticky="ew", pady=(22, 5))
        tk.Label(
            parent,
            text=(
                "Drive 80 m on a synthetic rounded rectangle with a synthetic "
                "four-wheel car. Steering and speed react to modeled pose and "
                "local grip. This separate model has no battery, motor, thermal "
                "system, ghost, or Formula SAE timed-lap result. The 3 m half-width "
                "is an assumption, not measured cone clearance. It uses "
                "Cell size (max) from Calculate; requests above 0.5 m keep the "
                "finer synthetic source grid. An eligible selected AI path can "
                "also be tracked for 80 m by this separate synthetic car; the "
                "pose road condition below is selected independently."
            ),
            justify="left", anchor="w", wraplength=760, font=FONT,
        ).grid(row=6, column=0, sticky="ew", pady=(0, 9))
        scenario_controls = tk.Frame(parent)
        scenario_controls.grid(row=7, column=0, sticky="w", pady=(0, 4))
        tk.Label(scenario_controls, text="Road condition").pack(
            side="left", padx=(0, 6),
        )
        self.pose_scenario_menu = tk.OptionMenu(
            scenario_controls, self.pose_scenario_var,
            POSE_SCENARIO_UNIFORM, POSE_SCENARIO_PATCH,
        )
        self.pose_scenario_menu.configure(relief="raised", bd=1, font=FONT)
        self.pose_scenario_menu.pack(side="left")
        tk.Label(scenario_controls, text="Initial lateral offset (m)").pack(
            side="left", padx=(16, 6),
        )
        self.pose_offset_entry = tk.Entry(
            scenario_controls, textvariable=self.pose_offset_var,
            width=8, relief="sunken", bd=1, font=FONT,
        )
        self.pose_offset_entry.pack(side="left")
        tk.Label(
            parent,
            text=("Optional assumed patch on the first synthetic bend: world "
                  "x 36–55 m, y −3–16 m; road grip 0.3× the base. "
                  "No measured dry or wet-road calibration. Initial offset "
                  f"range: ±{PoseDriverSettings().usable_half_width_m:.1f} m "
                  "from center; positive is left of travel."),
            justify="left", anchor="w", wraplength=760,
        ).grid(row=8, column=0, sticky="ew", pady=(0, 8))
        pose_actions = tk.Frame(parent)
        pose_actions.grid(row=9, column=0, sticky="w")
        self.pose_preview_button = tk.Button(
            pose_actions, text="Run 80 m synthetic pose preview",
            command=self._start_pose_preview,
            relief="raised", bd=1,
        )
        self.pose_preview_button.pack(side="left")
        self.pose_save_button = tk.Button(
            pose_actions, text="Save last synthetic trace…",
            command=self._save_pose_record, state="disabled",
            relief="raised", bd=1,
        )
        self.pose_save_button.pack(side="left", padx=(8, 0))
        self.pose_load_button = tk.Button(
            pose_actions, text="Load synthetic trace…",
            command=self._load_pose_record, relief="raised", bd=1,
        )
        self.pose_load_button.pack(side="left", padx=(8, 0))
        self.pose_ai_preview_button = tk.Button(
            parent, text="Preview selected AI path (80 m)",
            command=lambda: self._start_pose_preview(use_selected_ai_path=True),
            state="disabled", relief="raised", bd=1,
        )
        self.pose_ai_preview_button.grid(row=10, column=0, sticky="w", pady=(7, 0))
        tk.Label(
            parent, textvariable=self.pose_ai_availability,
            justify="left", anchor="w", wraplength=760, font=FONT,
        ).grid(row=11, column=0, sticky="ew", pady=(4, 0))
        tk.Label(
            parent, textvariable=self.pose_preview_status,
            justify="left", anchor="w", wraplength=760, font=FONT,
        ).grid(row=12, column=0, sticky="ew", pady=(8, 0))
        tk.Label(
            parent, textvariable=self.pose_record_status,
            justify="left", anchor="w", wraplength=760, font=FONT,
        ).grid(row=13, column=0, sticky="ew", pady=(4, 0))
        for widget in (canvas, content, *self._walk_widgets(content)):
            widget.bind(
                "<MouseWheel>",
                lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"),
            )
        self._update_pose_ai_preview_availability()

    def _on_pose_scenario_change(self) -> None:
        if self.run_in_progress:
            if self.pose_scenario_var.get() != self._active_pose_scenario:
                self.pose_scenario_var.set(self._active_pose_scenario)
            return
        scenario = self.pose_scenario_var.get()
        if scenario not in (POSE_SCENARIO_UNIFORM, POSE_SCENARIO_PATCH):
            return
        try:
            offset_m = self._read_pose_offset_m()
            offset_label = f" · initial offset {offset_m:+.2f} m"
        except ValueError:
            offset_label = " · check initial offset"
        self.pose_preview_status.set(
            f"Selected {scenario}{offset_label}; run the synthetic 80 m pose preview."
        )
        self._clear_pose_preview_playback(
            f"scenario changed · {scenario}{offset_label}"
        )

    def _read_pose_offset_m(self) -> float:
        try:
            offset_m = float(self.pose_offset_var.get())
        except ValueError as error:
            raise ValueError("Initial lateral offset must be a finite number in meters") from error
        limit_m = PoseDriverSettings().usable_half_width_m
        if not isfinite(offset_m) or abs(offset_m) > limit_m:
            raise ValueError(
                f"Initial lateral offset must be finite and within ±{limit_m:.1f} m"
            )
        return offset_m

    def _eligible_selected_ai_pose_track(self) -> SpatialTrack | None:
        """Only a ranked, completed candidate on the demo can enter pose mode."""

        if (
            self.course_spec.course_id != SYNTHETIC_DEMO_COURSE_ID
            or not self._ai_mode_selected()
            or self._path_comparison is None
            or not isinstance(self._selected_path_track, SpatialTrack)
        ):
            return None
        comparison = self._path_comparison[1]
        if (
            comparison.rank_status != "candidate_selected"
            or comparison.selected_mode != "candidate"
            or comparison.baseline_time_s is None
            or comparison.candidate_time_s is None
            or comparison.candidate_run is None
            or not comparison.candidate_run.completed
            or comparison.candidate_path_audit is None
            or not comparison.candidate_path_audit.valid
            or comparison.candidate_track != self._selected_path_track
        ):
            return None
        return self._selected_path_track

    def _update_pose_ai_preview_availability(self) -> None:
        selected = self._eligible_selected_ai_pose_track()
        if self.pose_ai_preview_button is not None:
            self.pose_ai_preview_button.configure(
                state="normal" if selected is not None and not self.run_in_progress
                else "disabled",
            )
        if self.course_spec.course_id != SYNTHETIC_DEMO_COURSE_ID:
            message = "Selected AI path preview is available only on Synthetic loop · AI demo."
        elif not self._ai_mode_selected():
            message = "Select AI racing line and run it to unlock the selected-path preview."
        elif selected is None:
            message = (
                "Run AI racing line on this course. Only an eligible, faster "
                "selected candidate unlocks this preview; diagnostic paths do not."
            )
        else:
            message = (
                "Eligible selected AI path ready for an 80 m synthetic-car pose "
                "preview. Its pose-model time is separate from the lap comparison."
            )
        self.pose_ai_availability.set(message)

    def _read_pose_grid(
        self, selected_ai_track: SpatialTrack | None = None,
    ) -> tuple[float, SpatialTrack]:
        """Freeze a safe synthetic or sampled-path grid from the shared entry."""

        try:
            requested_m = float(self.inputs["solver_step_m"].get())
        except ValueError as error:
            raise ValueError("Cell size (max) must be a finite number in meters") from error
        if not isfinite(requested_m) or requested_m <= 0.0:
            raise ValueError("Cell size (max) must be finite and above 0 m")
        if selected_ai_track is not None:
            target_m = min(requested_m, POSE_PREVIEW_MAX_CELL_M)
            cell_count = 0
            for length_m in selected_ai_track.cell_length_m:
                ratio = length_m / target_m
                if not isfinite(ratio) or ratio > 5000 - cell_count:
                    raise ValueError(
                        "Pose preview Cell size (max) exceeds the 5,000-cell compute cap"
                    )
                cell_count += ceil(ratio)
            return requested_m, selected_ai_track.refine(target_m)
        source = load_course(SYNTHETIC_DEMO_COURSE_ID)
        try:
            track = solver_track_for_course(
                SYNTHETIC_DEMO_COURSE_ID, source, requested_m,
            )
        except ValueError as error:
            if "5000-cell" in str(error):
                raise ValueError(
                    "Pose preview Cell size (max) exceeds the 5,000-cell compute cap"
                ) from error
            raise
        return requested_m, track

    def _on_pose_offset_change(self) -> None:
        if self.run_in_progress:
            if self.pose_offset_var.get() != f"{self._active_pose_offset_m:g}":
                self.pose_offset_var.set(f"{self._active_pose_offset_m:g}")
            return
        scenario = self.pose_scenario_var.get()
        try:
            offset_m = self._read_pose_offset_m()
            self.pose_preview_status.set(
                f"Selected {scenario} · initial offset {offset_m:+.2f} m; "
                "run the synthetic 80 m pose preview."
            )
            change_label = f"initial offset changed · {scenario} · {offset_m:+.2f} m"
        except ValueError as error:
            self.pose_preview_status.set(str(error))
            change_label = f"initial offset changed · {scenario} · invalid value"
        self._clear_pose_preview_playback(change_label)

    def _clear_pose_preview_playback(self, change_label: str) -> None:
        if not isinstance(self.driver_playback,
                          (PoseDriverPlayback, PoseDriverLivePlayback)):
            return
        self._active_pose_grid_label = ""
        self._active_pose_reference_label = "synthetic centerline (coherent arcs)"
        self._pause_driver_playback()
        self.driver_playback = None
        self._driver_live_mode = False
        self._pose_live_mode = False
        self._driver_stream_active = False
        self._driver_playback_time_s = 0.0
        self.driver_run_label.set(f"Synthetic pose {change_label}")
        self.driver_progress_var.set(0.0)
        self.driver_progress.configure(state="disabled")
        if self.driver_play_button is not None:
            self.driver_play_button.configure(state="disabled")
        for value in self.driver_values.values():
            value.set("—")
        for value in self.driver_decision_values.values():
            value.set("—")
        self._draw_driver_view()

    def _set_driver_run(
        self, name: str, result: Any, *, driving_mode: str = "Centerline",
        path_track: Any = None,
    ) -> None:
        """Load a solved lap for station-aligned reference-path playback.

        Completed workers pass the exact solver grid saved with their runs;
        a manual or legacy caller without ``path_track`` uses the source map.
        This displays x/y with solved telemetry, not an integrated car pose.
        """

        self._pause_driver_playback()
        self._live_decision = None
        self.driver_note_var.set(REFERENCE_DRIVER_NOTE)
        self._set_driver_box_mode(pose=False)
        self.driver_decision_title.set("Solved cell values")
        self._driver_live_mode = False
        self._pose_live_mode = False
        self._driver_stream_active = False
        self._driver_preview_track = None
        self._driver_live_update_serial += 1
        self._driver_playback_time_s = 0.0
        try:
            if result.telemetry is None:
                raise ValueError("no lap telemetry was recorded")
            self.driver_playback = DriverPlayback(
                path_track if path_track is not None else self.track,
                result.telemetry,
            )
        except ValueError as error:
            self.driver_playback = None
            self.driver_run_label.set(f"Playback unavailable: {error}")
            for value in self.driver_decision_values.values():
                value.set("—")
            if self.driver_play_button is not None:
                self.driver_play_button.configure(state="disabled")
            self._draw_driver_view()
            return
        self.driver_run_label.set(f"{driving_mode} · {name}")
        if self.driver_play_button is not None:
            self.driver_play_button.configure(state="normal")
        self.driver_progress.configure(state="normal")
        self._render_driver_frame()

    def _set_driver_box_mode(self, *, pose: bool) -> None:
        if self.driver_heading_title_label is not None:
            self.driver_heading_title_label.configure(
                text="VEHICLE HEADING (°)" if pose else "MAP HEADING (°)"
            )
        titles = POSE_DRIVER_BOX_TITLES if pose else tuple(
            item[1] for item in DRIVER_CELL_BOXES
        )
        for label, title in zip(self.driver_decision_title_labels, titles, strict=True):
            label.configure(text=title)

    def _active_pose_description(self) -> str:
        description = (
            f"{self._active_pose_scenario} · "
            f"initial offset {self._active_pose_offset_m:+.2f} m · "
            f"reference {self._active_pose_reference_label}"
        )
        if self._active_pose_grid_label:
            description += f" · {self._active_pose_grid_label}"
        return description

    @staticmethod
    def _pose_road_domain_warning(status: str) -> str:
        if status == "road_domain_invalid":
            return (
                "Local grip may show a base-road fallback outside the declared "
                "road domain; that number is not valid road data."
            )
        return ""

    @staticmethod
    def _pose_reference_note(reference_geometry: str, status: str = "") -> str:
        if reference_geometry == "sampled_polyline":
            note = (
                "Sampled AI-style path reference, driven for 80 m by a separate "
                "synthetic car and controller. Its pose-model time is not a "
                "Prius, TREV, or Formula SAE lap time. " + POSE_DRIVER_NOTE
            )
        else:
            note = POSE_DRIVER_NOTE
        warning = LapSimDesktop._pose_road_domain_warning(status)
        return f"{note} {warning}" if warning else note

    def _activate_pose_preview(self, run: PoseDriverRun) -> None:
        """Show simulated pose while keeping its model separate from lap results."""

        self._pause_driver_playback()
        self._live_decision = None
        self._driver_live_mode = False
        self._pose_live_mode = False
        self._driver_stream_active = False
        self._driver_preview_track = None
        self._driver_live_update_serial += 1
        self._driver_playback_time_s = 0.0
        self.driver_note_var.set(
            self._pose_reference_note(
                getattr(run.settings, "reference_geometry", "coherent_arcs"),
                run.status,
            )
        )
        self._set_driver_box_mode(pose=True)
        self.driver_decision_title.set("Pose model · recorded controls and tracking values")
        self.driver_playback = PoseDriverPlayback(run)
        self.driver_run_label.set(
            f"Synthetic pose model · {self._active_pose_description()} · {run.status} · "
            f"{run.samples[-1].progress_m:.1f} m / {run.settings.target_progress_m:.0f} m · "
            f"{run.elapsed_pose_model_time_s:.2f} s pose-model time"
        )
        if self.driver_play_button is not None:
            self.driver_play_button.configure(state="normal")
        self.driver_progress.configure(state="normal")
        self._render_driver_frame()
        self._switch_tab("Driver view")
        self._toggle_driver_playback()

    def _set_driver_replay_options(
        self, options: dict[str, tuple[str, Any, str, Any]], *, selected: str,
    ) -> None:
        """Offer already solved laps for playback without running physics again."""

        self._driver_replay_runs = dict(options)
        self.driver_replay_var.set(selected if selected in options else "—")
        if self.driver_replay_menu is None:
            return
        menu = self.driver_replay_menu.nametowidget(self.driver_replay_menu["menu"])
        menu.delete(0, "end")
        for label in options:
            menu.add_command(
                label=label,
                command=lambda choice=label: self._select_driver_replay(choice),
            )
        if not options:
            menu.add_command(label="—", state="disabled")
        self.driver_replay_menu.configure(
            state="normal" if len(options) > 1 else "disabled"
        )

    def _select_driver_replay(self, choice: str) -> None:
        if choice not in self._driver_replay_runs or self.run_in_progress:
            return
        name, result, driving_mode, path_track = self._driver_replay_runs[choice]
        was_playing = self._driver_playing
        self.driver_replay_var.set(choice)
        self._set_driver_run(
            name, result, driving_mode=driving_mode, path_track=path_track,
        )
        if was_playing and self.driver_playback is not None:
            self._toggle_driver_playback()

    def _activate_driver_playback(
        self, name: str, result: Any, *, driving_mode: str = "Centerline",
        path_track: Any = None,
    ) -> None:
        """Show and play a just-completed modeled lap at human viewing speed."""

        self._set_driver_run(
            name, result, driving_mode=driving_mode, path_track=path_track,
        )
        if self.driver_playback is not None:
            self._switch_tab("Driver view")
            self._toggle_driver_playback()

    def _toggle_driver_playback(self) -> None:
        if self.driver_playback is None:
            return
        if self._driver_playing:
            self._pause_driver_playback()
            return
        if self._driver_playback_time_s >= self.driver_playback.duration_s:
            self._driver_playback_time_s = 0.0
        self._driver_playing = True
        self._driver_last_clock_s = time.perf_counter()
        if self.driver_play_button is not None:
            self.driver_play_button.configure(text="Pause")
        self._driver_tick()

    def _pause_driver_playback(self) -> None:
        self._driver_playing = False
        if self._driver_after_id is not None:
            self.root.after_cancel(self._driver_after_id)
            self._owned_after_ids.discard(self._driver_after_id)
            self._driver_after_id = None
        if self.driver_play_button is not None:
            self.driver_play_button.configure(text="Play")

    def _driver_tick(self) -> None:
        self._driver_after_id = None
        if not self._driver_playing or self.driver_playback is None:
            return
        current = time.perf_counter()
        playback_rate = float(self.driver_speed_var.get().replace("×", ""))
        self._driver_playback_time_s = min(
            self.driver_playback.duration_s,
            self._driver_playback_time_s
            + max(current - self._driver_last_clock_s, 0.0) * playback_rate,
        )
        self._driver_last_clock_s = current
        self._render_driver_frame()
        if self._driver_playback_time_s >= self.driver_playback.duration_s:
            self._pause_driver_playback()
        else:
            self._driver_after_id = self._schedule_after(50, self._driver_tick)

    def _reset_driver_playback(self) -> None:
        self._pause_driver_playback()
        self._driver_playback_time_s = 0.0
        self._render_driver_frame()

    def _on_driver_scrub(self, value: str) -> None:
        if self._driver_updating_scale or self.driver_playback is None:
            return
        self._pause_driver_playback()
        self._driver_playback_time_s = (
            self.driver_playback.duration_s * float(value) / 1000.0
        )
        self._render_driver_frame()

    def _zoom_driver_view(self, event: Any) -> None:
        factor = 0.8 if event.delta > 0 else 1.25
        self._driver_look_ahead_m = min(
            180.0, max(30.0, self._driver_look_ahead_m * factor)
        )
        self._draw_driver_view()

    def _render_driver_frame(self) -> None:
        playback = self.driver_playback
        if playback is None:
            return
        frame = playback.frame_at(self._driver_playback_time_s)
        self.driver_values["time"].set(
            f"{frame.time_s:.2f} elapsed" if self._driver_live_mode
            else f"{frame.time_s:.2f} / {playback.duration_s:.2f}"
        )
        self.driver_values["distance"].set(
            f"{frame.distance_m:.1f} / {playback.track.length_m:.1f}"
        )
        self.driver_values["speed"].set(f"{frame.speed_mps * 3.6:.1f}")
        self.driver_values["lateral"].set(
            f"{frame.lateral_acceleration_mps2 / 9.80665:+.2f}"
            if np.isfinite(frame.lateral_acceleration_mps2) else "—"
        )
        self.driver_values["heading"].set(
            f"{float(np.degrees(frame.course_heading_rad)):+.1f}"
        )
        if isinstance(playback, (PoseDriverPlayback, PoseDriverLivePlayback)):
            pose_values = playback.control_values_at(self._driver_playback_time_s)
            for index, (key, _title, _scale, _format) in enumerate(DRIVER_CELL_BOXES):
                raw = pose_values[index] if pose_values is not None else None
                self.driver_decision_values[key].set(
                    f"{raw:{POSE_DRIVER_BOX_FORMATS[index]}}"
                    if raw is not None and np.isfinite(raw) else "—"
                )
        else:
            decision = self._live_decision if self._driver_live_mode else frame.decision
            for key, _title, scale, format_spec in DRIVER_CELL_BOXES:
                raw = getattr(decision, key) if decision is not None else None
                self.driver_decision_values[key].set(
                    f"{raw * scale:{format_spec}}"
                    if isinstance(raw, (int, float)) and np.isfinite(raw)
                    else "—"
                )
        self._driver_updating_scale = True
        self.driver_progress_var.set(
            1000.0 * frame.distance_m / playback.track.length_m
            if self._driver_live_mode else
            1000.0 * frame.time_s / playback.duration_s
            if playback.duration_s > 0 else 0.0
        )
        self._driver_updating_scale = False
        self._draw_driver_view()

    def _draw_driver_view(self) -> None:
        canvas = self.driver_canvas
        if canvas is None:
            return
        background, foreground = self._theme_colors()
        canvas.configure(background=background, highlightbackground=foreground)
        canvas.delete("all")
        width = max(canvas.winfo_width(), 200)
        height = max(canvas.winfo_height(), 200)
        if self._driver_live_mode and self._driver_preview_track is not None:
            self._draw_driver_static_preview(
                canvas, self._driver_preview_track, width, height, foreground,
            )
            return
        playback = self.driver_playback
        if playback is None:
            canvas.create_text(
                width / 2, height / 2,
                text=("Waiting for the first synthetic pose step..."
                      if self._pose_live_mode else
                      ("Planning path and speed limits..."
                       if self._driver_stream_active else
                       "No accepted model step is available")
                      if self._driver_live_mode else
                      "Run the synthetic pose preview to view this road condition"
                      if POSE_DRIVER_NOTE in self.driver_note_var.get() else
                      "Run a lap, then play its distance-aligned map view"),
                fill=foreground, font=FONT, width=width - 30,
            )
            return
        frame = playback.frame_at(self._driver_playback_time_s)
        ahead_m = self._driver_look_ahead_m
        behind_m = ahead_m * 0.25
        scale = height * 0.80 / (ahead_m + behind_m)
        origin_x = width / 2.0
        origin_y = height * 0.78
        samples = playback.local_path_m(
            frame, behind_m=behind_m, ahead_m=ahead_m,
            spacing_m=max(0.75, ahead_m / 100.0),
        )
        coords: list[float] = []
        for right_m, forward_m in samples:
            coords.extend((origin_x + right_m * scale, origin_y - forward_m * scale))
        if len(coords) >= 4:
            canvas.create_line(
                *coords, fill=foreground, width=2, smooth=False,
                tags=("driver_live_path",),
            )
        # The triangular marker stays fixed; the displayed course rotates.
        canvas.create_polygon(
            origin_x, origin_y - 13,
            origin_x - 9, origin_y + 11,
            origin_x + 9, origin_y + 11,
            outline=foreground, fill=background, width=2,
        )
        canvas.create_text(
            12, 12, text="FORWARD ↑", anchor="nw", fill=foreground,
            font=FONT_BOLD,
        )
        canvas.create_text(
            width - 12, 12,
            text=("LIVE SYNTHETIC POSE · ASSUMED PATH"
                  if isinstance(playback, PoseDriverLivePlayback) else
                  ("LIVE MODEL STEP" if self._driver_stream_active
                   else "LAST ACCEPTED STEP") + " · REFERENCE PATH"
                  if self._driver_live_mode else
                  "SYNTHETIC POSE MODEL · EXPERIMENT"
                  if isinstance(playback, PoseDriverPlayback) else
                  "MODEL REFERENCE · NOT POSE"),
            anchor="ne", fill=foreground,
            font=("Consolas", 9),
        )
        canvas.create_text(
            12, height - 12,
            text=f"Look-ahead {ahead_m:.0f} m · wheel to zoom",
            anchor="sw", fill=foreground, font=("Consolas", 9),
        )

    def _draw_driver_static_preview(
        self, canvas: tk.Canvas, track: Any, width: int, height: int,
        foreground: str,
    ) -> None:
        """Fit the source map while no accepted solver cell is being shown."""

        x_m = np.asarray(track.x_m, dtype=float)
        y_m = np.asarray(track.y_m, dtype=float)
        if x_m.size > 1500:
            indices = np.linspace(0, x_m.size - 1, 1500, dtype=int)
            x_m = x_m[indices]
            y_m = y_m[indices]
        x_center = 0.5 * (float(np.min(x_m)) + float(np.max(x_m)))
        y_center = 0.5 * (float(np.min(y_m)) + float(np.max(y_m)))
        x_span = float(np.max(x_m) - np.min(x_m))
        y_span = float(np.max(y_m) - np.min(y_m))
        scale = min(
            (width - 60.0) / max(x_span, 1.0),
            (height - 90.0) / max(y_span, 1.0),
        )
        coords: list[float] = []
        for x, y in zip(x_m, y_m, strict=True):
            coords.extend((
                width / 2.0 + (float(x) - x_center) * scale,
                height / 2.0 - (float(y) - y_center) * scale,
            ))
        if len(coords) >= 4:
            canvas.create_line(
                *coords, fill=foreground, width=2, smooth=False,
                tags=("driver_preview_path",),
            )
        start_x, start_y = coords[:2]
        canvas.create_oval(
            start_x - 4, start_y - 4, start_x + 4, start_y + 4,
            outline=foreground, width=2, tags=("driver_preview_start",),
        )
        canvas.create_text(
            12, 12, text="STATIC SOURCE COURSE · NO VEHICLE POSE",
            anchor="nw", fill=foreground, font=FONT_BOLD,
        )
        canvas.create_text(
            12, height - 12,
            text="Start marked · waiting for accepted model cells",
            anchor="sw", fill=foreground, font=("Consolas", 9),
        )

    def _theme_colors(self) -> tuple[str, str]:
        return ("#000000", "#ffffff") if self.is_dark.get() else ("#ffffff", "#000000")

    def _draw_calculation_progress(self) -> None:
        """Draw one plain bar; percentages describe only accepted cells in a pass."""

        canvas = self.calculation_progress_bar
        background, foreground = self._theme_colors()
        canvas.configure(background=background)
        canvas.delete("all")
        width = max(
            canvas.winfo_width() if canvas.winfo_width() > 1
            else int(canvas.cget("width")), 2,
        )
        height = max(
            canvas.winfo_height() if canvas.winfo_height() > 1
            else int(canvas.cget("height")), 2,
        )
        interior_width = max(width - 2, 0)
        if self._calculation_progress_mode in {"determinate", "complete"}:
            fill_width = round(interior_width * self._calculation_progress_fraction)
            if fill_width:
                canvas.create_rectangle(
                    1, 1, 1 + fill_width, height - 1,
                    fill=foreground, outline="",
                )
        elif self._calculation_progress_mode == "indeterminate":
            segment_width = min(interior_width, max(12, round(interior_width * 0.18)))
            span = max(interior_width - segment_width, 0)
            phase = (self._calculation_progress_tick * 8) % max(2 * span, 1)
            left = 1 + (phase if phase <= span else 2 * span - phase)
            canvas.create_rectangle(
                left, 1, left + segment_width, height - 1,
                fill=foreground, outline="",
            )

    def _animate_calculation_progress(self) -> None:
        self._calculation_progress_after_id = None
        if self._closed or not self.run_in_progress or self._calculation_progress_mode != "indeterminate":
            return
        self._calculation_progress_tick += 1
        self._draw_calculation_progress()
        self._calculation_progress_after_id = self._schedule_after(
            80, self._animate_calculation_progress,
        )

    def _set_calculation_progress(
        self, mode: str, description: str, *, fraction: float = 0.0,
    ) -> None:
        if self._calculation_progress_after_id is not None:
            try:
                self.root.after_cancel(self._calculation_progress_after_id)
            except tk.TclError:
                pass
            self._owned_after_ids.discard(self._calculation_progress_after_id)
            self._calculation_progress_after_id = None
        self._calculation_progress_mode = mode
        self._calculation_progress_fraction = min(1.0, max(0.0, fraction))
        self.calculation_progress_text.set(description)
        if mode == "indeterminate":
            self._calculation_progress_tick = 0
            if self.run_in_progress:
                self._calculation_progress_after_id = self._schedule_after(
                    80, self._animate_calculation_progress,
                )
        self._draw_calculation_progress()

    def _walk_widgets(self, parent: tk.Widget):
        for child in parent.winfo_children():
            yield child
            yield from self._walk_widgets(child)

    def _apply_theme(self) -> None:
        background, foreground = self._theme_colors()
        self.root.configure(background=background)
        for widget in self._walk_widgets(self.root):
            options: dict[str, str] = {}
            if widget.winfo_class() == "Scrollbar":
                options = {
                    "background": background,
                    "activebackground": foreground,
                    "troughcolor": background,
                    "highlightbackground": foreground,
                }
            elif widget.winfo_class() in {"Frame", "Canvas", "Toplevel"}:
                options["background"] = background
            else:
                options["background"] = background
                options["foreground"] = foreground
            if widget.winfo_class() in {"Button", "Labelframe", "Entry", "Checkbutton", "Menubutton"}:
                options["highlightbackground"] = foreground
                options["highlightcolor"] = foreground
            if widget.winfo_class() == "Entry":
                options["insertbackground"] = foreground
                options["selectbackground"] = foreground
                options["selectforeground"] = background
                options["disabledbackground"] = background
                options["disabledforeground"] = foreground
            if widget.winfo_class() in {"Button", "Checkbutton"}:
                options["activebackground"] = foreground
                options["activeforeground"] = background
            if widget.winfo_class() == "Button":
                options["disabledforeground"] = foreground
            if widget.winfo_class() == "Checkbutton":
                options["selectcolor"] = background
            if widget.winfo_class() == "Scale":
                options["troughcolor"] = background
                options["activebackground"] = foreground
                options["highlightbackground"] = foreground
            if widget.winfo_class() in {"Listbox", "Text"}:
                options["selectbackground"] = foreground
                options["selectforeground"] = background
            if widget.winfo_class() == "Text":
                options["insertbackground"] = foreground
            if widget.winfo_class() in {"Menu", "Menubutton"}:
                options["activebackground"] = foreground
                options["activeforeground"] = background
            try:
                widget.configure(**options)
            except tk.TclError:
                pass
        self._switch_tab(self._active_tab)
        self._draw_plots(preserve_course_view=True)
        self._draw_driver_view()
        self._draw_calculation_progress()

    def _draw_plots(self, *, preserve_course_view: bool = False) -> None:
        if self.figure is None or self.canvas is None:
            return
        background, foreground = self._theme_colors()
        previous_xlim = self.course_ax.get_xlim() if preserve_course_view else None
        previous_ylim = self.course_ax.get_ylim() if preserve_course_view else None

        self.figure.set_facecolor(background)
        self.course_ax.clear()
        self.speed_ax.clear()
        for axis in (self.course_ax, self.speed_ax):
            axis.set_facecolor(background)
            axis.tick_params(axis="both", colors=foreground, labelsize=9)
            for spine in axis.spines.values():
                spine.set_color(foreground)

        x = np.asarray(self.track.x_m, dtype=float)
        y = np.asarray(self.track.y_m, dtype=float)
        if self._selected_path_track is None:
            self.course_ax.plot(x, y, color=foreground, linewidth=1.4)
        else:
            selected_x = np.asarray(self._selected_path_track.x_m, dtype=float)
            selected_y = np.asarray(self._selected_path_track.y_m, dtype=float)
            self.course_ax.plot(
                x, y, color=foreground, linewidth=1.0, linestyle="--",
                label="Reference course",
            )
            self.course_ax.plot(
                selected_x, selected_y, color=foreground, linewidth=1.7,
                label="Selected model path",
            )
            self.course_ax.legend(
                frameon=False, labelcolor=foreground, facecolor=background,
                fontsize=8,
            )
        if self._displayed_ai_road is not None:
            patch = self._displayed_ai_road.patches[0]
            self.course_ax.add_patch(Rectangle(
                (patch.x_min_m, patch.y_min_m),
                patch.x_max_m - patch.x_min_m,
                patch.y_max_m - patch.y_min_m,
                fill=False, edgecolor=foreground, linewidth=1.1,
                linestyle=":", label="Assumed low-grip rectangle",
            ))
            self.course_ax.legend(
                frameon=False, labelcolor=foreground, facecolor=background,
                fontsize=8,
            )
        self.course_ax.plot(
            [x[0]],
            [y[0]],
            marker="s",
            markersize=6,
            markerfacecolor=background,
            markeredgecolor=foreground,
            linestyle="none",
        )
        self.course_ax.set_title(
            (f"Top-down {self.course_spec.label} · {self.track.length_m:.0f} m"
             if self._selected_path_track is None else
             f"Top-down model path ({self.course_spec.label}) · "
             f"{self._selected_path_track.length_m:.0f} m"),
            color=foreground,
            loc="left",
            fontsize=11,
        )
        self.course_ax.set_xlabel("Map X (m)", color=foreground, fontsize=9)
        self.course_ax.set_ylabel("Map Y (m)", color=foreground, fontsize=9)
        self.course_ax.set_aspect("equal", adjustable="box")
        self.course_ax.grid(False)
        if previous_xlim and previous_ylim:
            self.course_ax.set_xlim(previous_xlim)
            self.course_ax.set_ylim(previous_ylim)
        else:
            self._fit_course()

        trace_label = self.trace_var.get()
        trace_channel, scale, unit = TRACE_OPTIONS[trace_label]
        horizontal_label = self.trace_axis_var.get()
        horizontal_channel = (
            "vehicle.time_s" if horizontal_label == "Time" else "vehicle.distance_m"
        )
        runs = (
            self._comparison_results
            if self._comparison_results is not None
            else (("Current run", self._last_result),)
            if self._last_result is not None
            else ()
        )
        plotted = 0
        for (name, result), line_style in zip(runs, ("-", "--"), strict=False):
            if result.telemetry is None:
                continue
            try:
                horizontal = np.asarray(
                    result.telemetry[horizontal_channel], dtype=float
                )
                values = np.asarray(result.telemetry[trace_channel], dtype=float) * scale
            except KeyError:
                continue
            if horizontal.shape != values.shape or horizontal.size == 0:
                continue
            self.speed_ax.plot(
                horizontal, values, color=foreground, linestyle=line_style,
                linewidth=1.2, label=name,
            )
            plotted += 1
        if self._comparison_results is not None and plotted:
            self.speed_ax.legend(
                frameon=False, labelcolor=foreground, facecolor=background,
                fontsize=8,
            )
        if not plotted:
            self.speed_ax.text(
                0.5,
                0.5,
                "Run a lap to display this trace" if not runs else "Trace unavailable",
                color=foreground,
                ha="center",
                va="center",
                transform=self.speed_ax.transAxes,
            )
        self.speed_ax.set_title(
            f"{trace_label} by {horizontal_label.lower()}", color=foreground,
            loc="left", fontsize=11,
        )
        self.speed_ax.set_xlabel(
            "Time (s)" if horizontal_label == "Time" else "Distance (m)",
            color=foreground, fontsize=9,
        )
        self.speed_ax.set_ylabel(f"{trace_label} ({unit})", color=foreground, fontsize=9)
        self.speed_ax.grid(False)
        self.canvas.draw_idle()

    def _fit_course(self) -> None:
        if self.course_ax is None:
            return
        x = np.asarray(self.track.x_m, dtype=float)
        y = np.asarray(self.track.y_m, dtype=float)
        span = max(float(np.ptp(x)), float(np.ptp(y)), 1.0)
        margin = max(span * 0.04, 2.0)
        self.course_ax.set_xlim(float(np.min(x)) - margin, float(np.max(x)) + margin)
        self.course_ax.set_ylim(float(np.min(y)) - margin, float(np.max(y)) + margin)
        self.course_ax.set_aspect("equal", adjustable="box")
        if self.canvas is not None:
            self.canvas.draw_idle()

    def _zoom_axes(self, factor: float) -> None:
        xlim = self.course_ax.get_xlim()
        ylim = self.course_ax.get_ylim()
        xcenter = sum(xlim) / 2.0
        ycenter = sum(ylim) / 2.0
        self.course_ax.set_xlim(
            xcenter + (xlim[0] - xcenter) * factor,
            xcenter + (xlim[1] - xcenter) * factor,
        )
        self.course_ax.set_ylim(
            ycenter + (ylim[0] - ycenter) * factor,
            ycenter + (ylim[1] - ycenter) * factor,
        )
        self.canvas.draw_idle()

    def _pan_start(self, event: Any) -> None:
        if event.inaxes is not self.course_ax or event.button != 1:
            return
        self._pan_origin = (
            event.x,
            event.y,
            self.course_ax.get_xlim(),
            self.course_ax.get_ylim(),
        )

    def _pan_move(self, event: Any) -> None:
        if self._pan_origin is None or event.inaxes is not self.course_ax:
            return
        start_x, start_y, xlim, ylim = self._pan_origin
        bounds = self.course_ax.bbox
        dx = -(event.x - start_x) / bounds.width * (xlim[1] - xlim[0])
        dy = -(event.y - start_y) / bounds.height * (ylim[1] - ylim[0])
        self.course_ax.set_xlim(xlim[0] - dx, xlim[1] - dx)
        self.course_ax.set_ylim(ylim[0] - dy, ylim[1] - dy)
        self.canvas.draw_idle()

    def _pan_end(self, _event: Any) -> None:
        self._pan_origin = None

    def _wheel_zoom(self, event: Any) -> None:
        if event.inaxes is not self.course_ax or event.xdata is None or event.ydata is None:
            return
        factor = 0.8 if event.button == "up" else 1.25
        xlim, ylim = self.course_ax.get_xlim(), self.course_ax.get_ylim()
        self.course_ax.set_xlim(
            event.xdata + (xlim[0] - event.xdata) * factor,
            event.xdata + (xlim[1] - event.xdata) * factor,
        )
        self.course_ax.set_ylim(
            event.ydata + (ylim[0] - event.ydata) * factor,
            event.ydata + (ylim[1] - event.ydata) * factor,
        )
        self.canvas.draw_idle()

    def _watch_run_inputs(self) -> None:
        """Retire displayed runs after a user changes their defining inputs."""

        variables = (
            *self.inputs.values(), self.profile_var, self.driving_mode_var,
            self.ai_half_width_var, self.ai_vehicle_width_var, self.ai_margin_var,
            self.ai_road_condition_var, *self.ai_patch_vars.values(),
            self.compare_a_var, self.compare_b_var,
        )
        for variable in variables:
            variable.trace_add("write", self._schedule_input_invalidation)

    def _run_input_signature(self) -> tuple[str, ...]:
        return (
            self.course_spec.course_id, self.profile_var.get(),
            self.driving_mode_var.get(), self.compare_a_var.get(),
            self.compare_b_var.get(),
            *(value.get() for value in self.inputs.values()),
            self.ai_half_width_var.get(), self.ai_vehicle_width_var.get(),
            self.ai_margin_var.get(), self.ai_road_condition_var.get(),
            *(value.get() for value in self.ai_patch_vars.values()),
        )

    def _schedule_input_invalidation(self, *_change: str) -> None:
        if self.run_in_progress or self._pending_input_invalidation:
            return
        self._pending_input_invalidation = True
        self._update_ai_grid_check_button()
        # One idle callback observes the final values after a profile or
        # course selector has populated several StringVars programmatically.
        generation = self._result_generation
        self._schedule_after(None,
            lambda: self._invalidate_stale_result(expected_generation=generation)
        )

    def _invalidate_stale_result(
        self, *, force: bool = False, expected_generation: int | None = None,
    ) -> None:
        self._pending_input_invalidation = False
        if expected_generation is not None and expected_generation != self._result_generation:
            return
        if not self.run_in_progress and self._calculation_progress_mode in {"complete", "stopped"}:
            self._set_calculation_progress("idle", "Inputs changed · run again")
        if self.run_in_progress:
            return
        self._active_pose_grid_label = ""
        self._active_pose_reference_label = "synthetic centerline (coherent arcs)"
        if not force and not any((
            self._last_result is not None,
            self._comparison_results is not None,
            self._path_comparison is not None,
            self.driver_playback is not None,
            bool(self._displayed_run_records),
        )):
            return
        self._pause_driver_playback()
        self.driver_playback = None
        self._live_decision = None
        self._driver_live_mode = False
        self._pose_live_mode = False
        self._driver_stream_active = False
        self._last_result = None
        self._set_displayed_run_records(())
        self._displayed_road_grip_multiplier = None
        self._displayed_ai_road = None
        self._comparison_results = None
        self._path_comparison = None
        self._clear_ai_grid_check()
        self._selected_path_track = None
        self._set_driver_replay_options({}, selected="—")
        self._update_pose_ai_preview_availability()
        self._driver_playback_time_s = 0.0
        self.driver_progress_var.set(0.0)
        self.driver_progress.configure(state="disabled")
        if self.driver_play_button is not None:
            self.driver_play_button.configure(state="disabled")
        self.driver_run_label.set("Inputs changed · run a lap to load playback")
        self.driver_decision_title.set("Solved cell values")
        for value in self.driver_values.values():
            value.set("—")
        for value in self.driver_decision_values.values():
            value.set("—")
        for value in self.output_values.values():
            value.configure(text="—")
        for value in self.ai_output_values.values():
            value.configure(text="—")
        self.ai_result_text.set("Inputs changed · run the optional AI mode again.")
        if self.ai_compare_button is not None:
            self.ai_compare_button.configure(state="disabled")
        self.status_text.set("Inputs changed · run again")
        self._draw_plots(preserve_course_view=True)
        self._draw_driver_view()

    def _read_road_grip_multiplier(self) -> float:
        try:
            grip_percent = float(self.inputs["road_grip_percent"].get())
        except ValueError as error:
            raise ValueError("Enter a numeric assumed road grip percent.") from error
        if not np.isfinite(grip_percent) or grip_percent <= 0.0:
            raise ValueError("Assumed road grip must be finite and above 0%.")
        return grip_percent / 100.0

    def _read_run_settings(self) -> tuple[float, float]:
        try:
            torque_fraction = float(self.inputs["torque_request_percent"].get()) / 100.0
            solver_step_m = float(self.inputs["solver_step_m"].get())
        except ValueError as error:
            raise ValueError("Enter numeric driver request and Cell size (max) values.") from error
        if not np.isfinite(torque_fraction) or not 0.0 <= torque_fraction <= 1.0:
            raise ValueError("Driver request must be between 0 and 100%.")
        if not np.isfinite(solver_step_m) or not 0.0 < solver_step_m <= self.track.length_m:
            raise ValueError("Cell size (max) must be finite and within the course length.")
        if solver_cell_count_for_course(
            self.course_spec.course_id, self.track, solver_step_m,
        ) > 5000:
            raise ValueError("This Cell size (max) would exceed the 5000-cell compute cap.")
        return torque_fraction, solver_step_m

    def _read_run_inputs(self) -> tuple[VehicleSetup | None, float, float]:
        torque_fraction, solver_step_m = self._read_run_settings()
        profile_id = self.profile_display_to_id[self.profile_var.get()]
        if profile_id != "prius_2026_le" and profile_id not in self.saved_profiles:
            return None, solver_step_m, torque_fraction
        try:
            values = {key: float(self.inputs[key].get()) for key in CAR_INPUT_KEYS}
            setup = VehicleSetup(**values, torque_request_fraction=torque_fraction)
        except (ValueError, TypeError) as error:
            raise ValueError("Enter valid finite car values in every editable field.") from error
        return setup, solver_step_m, torque_fraction

    def _ai_mode_selected(self) -> bool:
        return self.driving_mode_var.get() == "AI racing line (experimental)"

    def _on_driving_mode_change(self) -> None:
        state = "normal" if self._ai_mode_selected() and not self.run_in_progress else "disabled"
        for entry in self.ai_entries:
            entry.configure(state=state)
        if self.ai_road_menu is not None:
            self.ai_road_menu.configure(state=state)
        patch_state = (
            state if self.ai_road_condition_var.get() == AI_ROAD_PATCH else "disabled"
        )
        for entry in self.ai_patch_entries:
            entry.configure(state=patch_state)
        if not self._ai_mode_selected() and self.ai_output_box is not None:
            self.ai_output_box.pack_forget()
        self._update_cell_count_hint()
        self._update_pose_ai_preview_availability()

    def _read_ai_road(self) -> PlanarRoad | None:
        """Read one explicit assumed rectangle; None retains uniform physics."""

        scenario = self.ai_road_condition_var.get()
        if scenario == AI_ROAD_UNIFORM:
            return None
        if scenario != AI_ROAD_PATCH:
            raise ValueError("Choose a listed AI trial surface.")
        try:
            values = {key: float(variable.get()) for key, variable in self.ai_patch_vars.items()}
        except ValueError as error:
            raise ValueError("Enter numeric rectangular-patch coordinates and grip.") from error
        if not all(np.isfinite(value) for value in values.values()):
            raise ValueError("Rectangular-patch coordinates and grip must be finite.")
        percent = values.pop("grip_percent_of_base")
        if not 0.0 < percent <= 100.0:
            raise ValueError("Patch grip must be above 0% and at most 100% of base.")
        x_span = values["x_max_m"] - values["x_min_m"]
        y_span = values["y_max_m"] - values["y_min_m"]
        if not all(np.isfinite(span) and span > 0.0 for span in (x_span, y_span)):
            raise ValueError("Patch bounds must have finite, positive X and Y spans.")
        try:
            self.track.validate_coherent_arcs()
        except ValueError as error:
            raise ValueError(
                "A world-fixed patch needs a coherent, closed course. "
                "Choose a synthetic course or a validated imported course. "
                f"Current course: {error}"
            ) from error
        return PlanarRoad(patches=(RectangularGripPatch(
            values["x_min_m"], values["x_max_m"],
            values["y_min_m"], values["y_max_m"], percent / 100.0,
            material_id="user_assumed_rectangular_low_grip",
        ),))

    def _read_ai_assumptions(self) -> tuple[float, float, float]:
        try:
            half_width = float(self.ai_half_width_var.get())
            vehicle_width = float(self.ai_vehicle_width_var.get())
            margin = float(self.ai_margin_var.get())
        except ValueError as error:
            raise ValueError("Enter numeric AI corridor and vehicle-width assumptions.") from error
        if not all(np.isfinite(value) for value in (half_width, vehicle_width, margin)):
            raise ValueError("AI corridor assumptions must be finite.")
        if half_width <= 0 or vehicle_width <= 0 or margin < 0:
            raise ValueError("AI half-width and vehicle width must be positive; margin cannot be negative.")
        if half_width <= 0.5 * vehicle_width + margin:
            raise ValueError("Assumed half-width must exceed half the vehicle width plus margin.")
        return half_width, vehicle_width, margin

    def _set_busy(self, busy: bool) -> None:
        self.run_in_progress = busy
        state = "disabled" if busy else "normal"
        self.run_button.configure(state=state)
        if self.pose_preview_button is not None:
            self.pose_preview_button.configure(state=state)
        if self.pose_ai_preview_button is not None:
            self.pose_ai_preview_button.configure(
                state=state if self._eligible_selected_ai_pose_track() is not None
                else "disabled",
            )
        if self.pose_save_button is not None:
            self.pose_save_button.configure(
                state="disabled" if busy or self._latest_pose_run is None else "normal"
            )
        if self.pose_load_button is not None:
            self.pose_load_button.configure(state=state)
        if self.pose_scenario_menu is not None:
            self.pose_scenario_menu.configure(state=state)
        if self.pose_offset_entry is not None:
            self.pose_offset_entry.configure(state=state)
        if self.saved_runs_button is not None:
            self.saved_runs_button.configure(
                state="disabled" if busy or not self._displayed_run_records else "normal"
            )
        self.compare_button.configure(state=state)
        self.profile_menu.configure(state=state)
        self.compare_a_menu.configure(state=state)
        self.compare_b_menu.configure(state=state)
        self.save_profile_button.configure(state=state)
        self.delete_profile_button.configure(state=state)
        self.course_menu.configure(state=state)
        self.import_course_button.configure(state=state)
        self.driving_mode_menu.configure(state=state)
        editable = (
            self.profile_display_to_id.get(self.profile_var.get()) == "prius_2026_le"
            or self.profile_display_to_id.get(self.profile_var.get()) in self.saved_profiles
        )
        for key, entry in self.entry_by_key.items():
            entry.configure(
                state="disabled" if busy or (key in CAR_INPUT_KEYS and not editable) else "normal"
            )
        self._on_driving_mode_change()
        self._update_ai_grid_check_button()

    def _begin_live_calculation(
        self, name: str, *, preparing: str = "Preparing course and speed limits",
    ) -> None:
        """Clear old results before accepted model cells arrive."""

        self.progress_queue = queue.Queue(maxsize=1)
        self._set_calculation_progress(
            "indeterminate", f"{preparing} · pass progress unavailable",
        )
        self._last_result = None
        self._set_displayed_run_records(())
        self._displayed_road_grip_multiplier = None
        self._displayed_ai_road = None
        self._comparison_results = None
        self._selected_path_track = None
        self._path_comparison = None
        self._clear_ai_grid_check()
        self._update_pose_ai_preview_availability()
        if self.ai_compare_button is not None:
            self.ai_compare_button.configure(state="disabled")
        self._draw_plots(preserve_course_view=True)
        self._set_driver_replay_options({}, selected="—")
        self._pause_driver_playback()
        self.driver_playback = None
        self._live_decision = None
        self.driver_note_var.set(REFERENCE_DRIVER_NOTE)
        self._set_driver_box_mode(pose=False)
        self.driver_decision_title.set("Last accepted cell · model values")
        self._driver_playback_time_s = 0.0
        self._driver_live_mode = True
        self._pose_live_mode = False
        self._driver_stream_active = True
        self._driver_preview_track = self.track
        self._driver_live_update_serial += 1
        self.driver_progress_var.set(0.0)
        for value in self.driver_values.values():
            value.set("—")
        for value in self.driver_decision_values.values():
            value.set("—")
        for value in self.output_values.values():
            value.configure(text="—")
        for value in self.ai_output_values.values():
            value.configure(text="—")
        self.driver_run_label.set(f"Preparing {name} · path and speed limits")
        if self.driver_play_button is not None:
            self.driver_play_button.configure(state="disabled")
        self.driver_progress.configure(state="disabled")
        self._switch_tab("Driver view")

    def _queue_live_progress(
        self, name: str, phase: str, track: Any, snapshot: Any,
    ) -> None:
        """Keep only the newest accepted cell when the UI draws more slowly."""

        update = (name, phase, track, snapshot)
        try:
            self.progress_queue.put_nowait(update)
        except queue.Full:
            try:
                self.progress_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.progress_queue.put_nowait(update)
            except queue.Full:
                pass

    def _poll_live_progress(self) -> None:
        latest = None
        while True:
            try:
                latest = self.progress_queue.get_nowait()
            except queue.Empty:
                break
        if latest is None or not self.run_in_progress:
            return
        name, phase, track, snapshot = latest
        if isinstance(snapshot, (PathConstraintProgressSnapshot, SpeedPeriodicPhaseSnapshot)):
            # Constraint preparation and unrecorded seam-speed probes have no
            # accepted vehicle pose or trustworthy overall percentage.
            self._driver_live_update_serial += 1
            self.driver_playback = None
            self._live_decision = None
            self._driver_playback_time_s = 0.0
            self._driver_preview_track = self.track
            for value in self.driver_values.values():
                value.set("—")
            for value in self.driver_decision_values.values():
                value.set("—")
            if isinstance(snapshot, SpeedPeriodicPhaseSnapshot):
                if snapshot.phase == "speed_seam_probe":
                    description = (
                        f"{name}: {phase} · speed-seam probe pass "
                        f"{snapshot.pass_number} (limit {snapshot.maximum_passes}); "
                        "cell progress unavailable"
                    )
                else:
                    description = (
                        f"{name}: {phase} · final lap pass "
                        f"{snapshot.pass_number} (limit {snapshot.maximum_passes}); "
                        "waiting for first accepted cell"
                    )
                self._set_calculation_progress("indeterminate", description)
                self.driver_run_label.set(
                    f"{name} · {phase} · model pass preparing · no vehicle pose"
                )
            elif snapshot.phase == "local_limits":
                fraction = snapshot.completed_cells / snapshot.cell_count
                description = (
                    f"{name}: {phase} · local speed limits · "
                    f"{snapshot.completed_cells}/{snapshot.cell_count} cells "
                    f"({fraction:.0%} of this phase)"
                )
                self._set_calculation_progress(
                    "determinate", description, fraction=fraction,
                )
                self.driver_run_label.set(
                    f"{name} · preparing path speed limits · no vehicle pose"
                )
            else:
                description = (
                    f"{name}: {phase} · cyclic braking pass "
                    f"{snapshot.pass_number} · "
                    f"{snapshot.completed_cells}/{snapshot.cell_count} cells; "
                    "convergence pending"
                )
                self._set_calculation_progress("indeterminate", description)
                self.driver_run_label.set(
                    f"{name} · preparing path speed limits · no vehicle pose"
                )
            self._draw_driver_view()
            return
        try:
            playback = DriverPlayback(
                track,
                {
                    "vehicle.time_s": (snapshot.elapsed_time_s,),
                    "vehicle.distance_m": (snapshot.lap_station_m,),
                    "vehicle.speed_mps": (snapshot.speed_mps,),
                    "vehicle.lateral_acceleration_mps2": (
                        snapshot.lateral_acceleration_mps2,
                    ),
                },
            )
        except ValueError:
            # A malformed progress snapshot must never interrupt the physics
            # worker or turn an incomplete lap into a displayed solution.
            return
        self.driver_playback = playback
        self._driver_preview_track = None
        self._driver_live_update_serial += 1
        update_serial = self._driver_live_update_serial
        self._live_decision = DriverCellDecision(**{
            key: getattr(snapshot, key, None)
            for key, _title, _scale, _format in DRIVER_CELL_BOXES
        })
        self._driver_playback_time_s = snapshot.elapsed_time_s
        self.driver_run_label.set(
            f"{name} · {phase} · accepted cell "
            f"{snapshot.cell_index + 1}/{snapshot.cell_count} · reference path"
        )
        cell_number = snapshot.cell_index + 1
        cell_count = snapshot.cell_count
        if cell_count > 0 and 1 <= cell_number <= cell_count:
            fraction = cell_number / cell_count
            self._set_calculation_progress(
                "determinate",
                f"Current pass · {name}: {phase} · "
                f"{cell_number}/{cell_count} cells ({fraction:.0%})",
                fraction=fraction,
            )
        self._render_driver_frame()
        phase_complete = snapshot.cell_index + 1 == snapshot.cell_count
        # A completed AI trial may start a dry seam-speed pass.  A longer
        # interval without accepted cells may also mean slow or failed model
        # work; in either case do not leave a stale car-fixed frame on screen.
        self._schedule_after(
            100 if phase_complete else 500,
            lambda: self._show_driver_preview_after_phase(
                update_serial, name, phase, phase_complete=phase_complete,
            ),
        )

    def _show_driver_preview_after_phase(
        self, update_serial: int, name: str, phase: str,
        *, phase_complete: bool = True,
    ) -> None:
        if (
            not self.run_in_progress or not self._driver_live_mode
            or update_serial != self._driver_live_update_serial
        ):
            return
        self._driver_preview_track = self.track
        self.driver_run_label.set(
            f"{name} · {phase} complete · model work continuing"
            if phase_complete else
            f"{name} · last accepted {phase} step · waiting for model"
        )
        self._set_calculation_progress(
            "indeterminate",
            (
                f"{name}: {phase} pass complete · preparing next work"
                if phase_complete else
                f"{name}: {phase} · waiting for next accepted cell"
            ),
        )
        self._draw_driver_view()

    def _vehicle_for_profile(
        self, profile_id: str, setup: VehicleSetup | None
    ) -> tuple[Any, Any]:
        if profile_id == "prius_2026_le" or profile_id.startswith("user:"):
            if setup is None:
                raise ValueError("A saved Prius setup is required")
            _, manifest = build_vehicle("prius_2026_le")
            return make_prius_benchmark(setup), manifest
        return build_vehicle(profile_id)

    def _save_run_record(
        self, *, result: Any, vehicle: Any, manifest: Any,
        solver_track: Any, profile_id: str, profile_name: str,
        setup: VehicleSetup | None, step_m: float, torque_fraction: float,
        road_grip_multiplier: float = 1.0,
        cell_road_grip_multiplier: tuple[float, ...] | None = None,
        track_id: str | None = None,
        path_planning: dict[str, Any] | None = None,
        starting_speed_mps: float | None = None,
    ) -> str:
        """Persist the exact effective setup and aligned lap telemetry."""

        settings = LapRunSettings.from_track(
            solver_track,
            track_id=track_id or self.course_spec.course_id,
            solver_step_m=step_m,
            solver_settings=path_solver_settings(vehicle),
            torque_request_fraction=torque_fraction,
            road_grip_multiplier=road_grip_multiplier,
            cell_road_grip_multiplier=cell_road_grip_multiplier,
            endurance_config=replace(
                endurance_run_config(vehicle),
                starting_speed_mps=starting_speed_mps,
            ),
            profile_id=profile_id,
            profile_label=profile_name,
            source_course=json.loads(self.course_source_json),
            path_planning=path_planning,
        )
        default_prius = VehicleSetup(torque_request_fraction=torque_fraction)
        overrides = (
            asdict(setup)
            if setup is not None and (
                profile_id.startswith("user:") or setup != default_prius
            )
            else None
        )
        record = capture_lap_run(
            result, manifest, settings, actual_vehicle=vehicle,
            user_overrides=overrides,
        )
        record.save(default_run_directory() / f"{record.run_id}.json")
        return record.run_id

    def _open_dynamics_lab(self) -> None:
        from .dynamics_lab import DynamicsLab

        DynamicsLab(self.root, dark=self.is_dark.get())

    def _start_pose_preview(self, *, use_selected_ai_path: bool = False) -> None:
        """Run a bounded synthetic control experiment outside the lap model."""

        if self.run_in_progress:
            return
        selected_ai_track = (
            self._eligible_selected_ai_pose_track() if use_selected_ai_path else None
        )
        if use_selected_ai_path and selected_ai_track is None:
            self._update_pose_ai_preview_availability()
            messagebox.showerror(
                "Selected AI path unavailable", self.pose_ai_availability.get(),
                parent=self.root,
            )
            return
        scenario = self.pose_scenario_var.get()
        if scenario not in (POSE_SCENARIO_UNIFORM, POSE_SCENARIO_PATCH):
            raise ValueError(f"Unknown synthetic pose scenario: {scenario!r}")
        try:
            offset_m = self._read_pose_offset_m()
            requested_cell_m, pose_track = self._read_pose_grid(selected_ai_track)
        except ValueError as error:
            messagebox.showerror("Check pose preview inputs", str(error), parent=self.root)
            return
        reference_geometry = (
            "sampled_polyline" if use_selected_ai_path else "coherent_arcs"
        )
        self._active_pose_scenario = scenario
        self._active_pose_offset_m = offset_m
        self._active_pose_reference_label = (
            "eligible selected AI path (sampled polyline)"
            if use_selected_ai_path else "synthetic centerline (coherent arcs)"
        )
        self._active_pose_grid_label = (
            f"requested Cell size (max) {requested_cell_m:g} m · "
            f"effective pose grid {pose_track.cell_count:,} cells, "
            f"max {max(pose_track.cell_length_m):.3g} m"
        )
        self._latest_pose_run = None
        self.pose_record_status.set("Current synthetic trace has not been saved.")
        description = self._active_pose_description()
        self.progress_queue = queue.Queue(maxsize=1)
        self.pose_progress_queue = queue.Queue(maxsize=1)
        self._set_busy(True)
        self._set_driver_replay_options({}, selected="—")
        self._pause_driver_playback()
        self.driver_playback = None
        self._live_decision = None
        self._driver_playback_time_s = 0.0
        self._driver_live_mode = True
        self._pose_live_mode = True
        self._driver_stream_active = True
        self._driver_preview_track = None
        self._driver_live_update_serial += 1
        self.driver_note_var.set(self._pose_reference_note(reference_geometry))
        self._set_driver_box_mode(pose=True)
        self.driver_decision_title.set("Live pose and tracking · controls after replay")
        self.driver_run_label.set(
            f"Synthetic pose model · {description} · preparing 80 m preview"
        )
        self.driver_progress_var.set(0.0)
        self.driver_progress.configure(state="disabled")
        if self.driver_play_button is not None:
            self.driver_play_button.configure(state="disabled")
        for value in self.driver_values.values():
            value.set("—")
        for value in self.driver_decision_values.values():
            value.set("—")
        self._set_calculation_progress(
            "indeterminate",
            f"Synthetic pose preview · {description} · preparing four-wheel model",
        )
        self.pose_preview_status.set(
            f"Running 80 m synthetic pose preview · {description}; "
            "engineering lap outputs are separate."
        )
        self.run_started_at = time.perf_counter()
        self._switch_tab("Driver view")
        self._draw_driver_view()
        threading.Thread(
            target=self._calculate_pose_preview,
            args=(scenario, offset_m, pose_track, reference_geometry), daemon=True,
        ).start()

    def _calculate_pose_preview(
        self, scenario: str, offset_m: float, track: SpatialTrack | None = None,
        reference_geometry: str = "coherent_arcs",
    ) -> None:
        try:
            if track is None:
                track = load_course(SYNTHETIC_DEMO_COURSE_ID)
            environment = _pose_preview_environment(scenario)

            def on_progress(sample: PoseDriverSample, state: PlanarState) -> None:
                latest = (track, sample, state)
                try:
                    self.pose_progress_queue.put_nowait(latest)
                except queue.Full:
                    try:
                        self.pose_progress_queue.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        self.pose_progress_queue.put_nowait(latest)
                    except queue.Full:
                        pass

            run = run_pose_driver(
                track=track, environment=environment,
                settings=PoseDriverSettings(
                    initial_lateral_offset_m=offset_m,
                    reference_geometry=reference_geometry,
                ),
                progress_callback=on_progress,
            )
            self.result_queue.put(("pose_preview", run, None))
        except Exception as error:
            self.result_queue.put(("pose_preview", None, error))

    def _save_pose_record(self) -> None:
        """Save the last frozen synthetic trace, never an endurance lap."""

        if self.run_in_progress or self._latest_pose_run is None:
            return
        record_directory = default_pose_run_directory()
        record_directory.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Save synthetic pose trace",
            initialdir=str(record_directory),
            initialfile="synthetic_pose_trace.json",
            defaultextension=".json",
            filetypes=(("JSON record", "*.json"),),
        )
        if not path:
            return
        run = self._latest_pose_run
        self._set_busy(True)
        self.pose_record_status.set("Checking dynamics and controller; saving trace…")
        self._set_calculation_progress(
            "indeterminate", "Saving synthetic pose trace · checking controls",
        )
        threading.Thread(
            target=self._write_pose_record, args=(run, Path(path)), daemon=True,
        ).start()

    def _write_pose_record(self, run: PoseDriverRun, path: Path) -> None:
        try:
            record = PoseRunRecord.capture(run)
            record.save(path)
            controller_report = getattr(record, "controller_report", None)
            checked_controls = (
                controller_report.checked_controls
                if controller_report is not None else None
            )
            self.result_queue.put((
                "pose_record_saved", (path, record.content_id, checked_controls), None,
            ))
        except Exception as error:
            self.result_queue.put(("pose_record_saved", None, error))

    @staticmethod
    def _pose_controller_check_label(checked_controls: int | None) -> str:
        if checked_controls is None:
            return "legacy controller decisions not checked"
        if checked_controls == 0:
            return "no driven controls; no controller decisions to check"
        return f"declared controller agrees on {checked_controls:,} controls"

    def _load_pose_record(self) -> None:
        if self.run_in_progress:
            return
        record_directory = default_pose_run_directory()
        path = filedialog.askopenfilename(
            parent=self.root, title="Load synthetic pose trace",
            initialdir=str(record_directory if record_directory.is_dir() else Path.home()),
            filetypes=(("JSON record", "*.json"),),
        )
        if not path:
            return
        self._set_busy(True)
        self.pose_record_status.set("Loading and checking synthetic trace…")
        self._set_calculation_progress(
            "indeterminate", "Loading synthetic pose trace · checking controls",
        )
        threading.Thread(
            target=self._read_pose_record, args=(Path(path),), daemon=True,
        ).start()

    def _read_pose_record(self, path: Path) -> None:
        try:
            record = PoseRunRecord.load(path)
            self.result_queue.put(("pose_record_loaded", (path, record), None))
        except Exception as error:
            self.result_queue.put(("pose_record_loaded", None, error))

    def _poll_pose_progress(self) -> None:
        latest = None
        while True:
            try:
                latest = self.pose_progress_queue.get_nowait()
            except queue.Empty:
                break
        if latest is None or not self.run_in_progress or not self._pose_live_mode:
            return
        track, sample, state = latest
        target_m = 80.0
        fraction = min(max(sample.progress_m / target_m, 0.0), 1.0)
        self._set_calculation_progress(
            "determinate",
            f"Synthetic pose preview · {self._active_pose_description()} · "
            f"{sample.progress_m:.1f}/{target_m:.0f} m "
            f"({fraction:.0%} of target distance) · "
            f"{sample.time_s:.2f} s pose-model time",
            fraction=fraction,
        )
        self.driver_playback = PoseDriverLivePlayback(track, sample, state)
        self._driver_playback_time_s = sample.time_s
        self.driver_run_label.set(
            f"Synthetic pose model · {self._active_pose_description()} · live · "
            f"{sample.progress_m:.1f}/{target_m:.0f} m · "
            f"{sample.time_s:.2f} s pose-model time"
        )
        self._render_driver_frame()

    def _start_run(self) -> None:
        if self.run_in_progress:
            return
        try:
            setup, step_m, torque_fraction = self._read_run_inputs()
            road_grip_multiplier = self._read_road_grip_multiplier()
            ai_assumptions = self._read_ai_assumptions() if self._ai_mode_selected() else None
            ai_road = self._read_ai_road() if ai_assumptions is not None else None
        except ValueError as error:
            messagebox.showerror("Check vehicle inputs", str(error), parent=self.root)
            return
        profile_id = self.profile_display_to_id[self.profile_var.get()]
        profile_name = self.profile_id_to_display[profile_id]
        if ai_assumptions is not None:
            self._path_comparison = None
            self.ai_result_text.set(
                "Evaluating geometric centerline and bounded AI path trials…"
            )
            if self.ai_compare_button is not None:
                self.ai_compare_button.configure(state="disabled")
        self._active_run_input_signature = self._run_input_signature()
        self._set_busy(True)
        self._begin_live_calculation(
            profile_name,
            preparing=(
                "Planning AI path and preparing model"
                if ai_assumptions else "Preparing course and speed limits"
            ),
        )
        self.run_started_at = time.perf_counter()
        self.status_text.set(
            f"Calculating {profile_name}"
            + (" with experimental AI path…" if ai_assumptions else f" with Cell size (max) {step_m:g} m…")
        )
        worker = threading.Thread(
            target=self._calculate_ai_single if ai_assumptions else self._calculate_single,
            args=(profile_id, profile_name, setup, step_m, torque_fraction)
                 + ((ai_assumptions,) if ai_assumptions else ())
                 + (road_grip_multiplier,)
                 + ((ai_road,) if ai_assumptions else ()),
            daemon=True,
        )
        worker.start()

    def _start_comparison(self) -> None:
        if self.run_in_progress:
            return
        try:
            torque_fraction, step_m = self._read_run_settings()
            road_grip_multiplier = self._read_road_grip_multiplier()
            first_id = self.profile_display_to_id[self.compare_a_var.get()]
            second_id = self.profile_display_to_id[self.compare_b_var.get()]
            if first_id == second_id:
                raise ValueError("Choose two different car profiles to compare.")
        except (ValueError, KeyError) as error:
            messagebox.showerror("Check comparison", str(error), parent=self.root)
            return
        plans = []
        for profile_id in (first_id, second_id):
            saved = self.saved_profiles.get(profile_id)
            setup = saved.setup(torque_fraction) if saved else (
                VehicleSetup(torque_request_fraction=torque_fraction)
                if profile_id == "prius_2026_le" else None
            )
            plans.append((profile_id, self.profile_id_to_display[profile_id], setup))
        self._active_run_input_signature = self._run_input_signature()
        self._set_busy(True)
        self._begin_live_calculation(
            "Car comparison", preparing="Preparing two cars and common speed limits",
        )
        self.run_started_at = time.perf_counter()
        self.status_text.set(
            f"Comparing two cars on the same course with Cell size (max) {step_m:g} m…"
        )
        threading.Thread(
            target=self._calculate_comparison,
            args=(tuple(plans), step_m, torque_fraction, road_grip_multiplier),
            daemon=True,
        ).start()

    def _calculate_single(
        self,
        profile_id: str,
        profile_name: str,
        setup: VehicleSetup | None,
        step_m: float,
        torque_fraction: float,
        road_grip_multiplier: float = 1.0,
    ) -> None:
        try:
            solver_track = solver_track_for_course(
                self.course_spec.course_id, self.track, step_m,
            )
            vehicle, manifest = self._vehicle_for_profile(profile_id, setup)
            apply_uniform_road_grip(vehicle, road_grip_multiplier)
            last_progress_post_s = float("-inf")

            def on_progress(snapshot: Any) -> None:
                nonlocal last_progress_post_s
                now = time.perf_counter()
                if (
                    now - last_progress_post_s >= 0.1
                    or snapshot.cell_index + 1 == snapshot.cell_count
                ):
                    self._queue_live_progress(
                        profile_name, "Centerline model", solver_track, snapshot
                    )
                    last_progress_post_s = now

            result = run_one_lap(
                vehicle,
                solver_track,
                torque_request_fraction=torque_fraction,
                progress_callback=on_progress,
                constraint_progress_callback=lambda snapshot: self._queue_live_progress(
                    profile_name, "Centerline model", None, snapshot,
                ),
            )
            if result.completed:
                summarize_lap(result, self.track.length_m)
            run_id = self._save_run_record(
                result=result, vehicle=vehicle, manifest=manifest,
                solver_track=solver_track, profile_id=profile_id,
                profile_name=profile_name, setup=setup, step_m=step_m,
                torque_fraction=torque_fraction,
                road_grip_multiplier=road_grip_multiplier,
            )
            self.result_queue.put(
                ("single", (
                    profile_name, step_m, result, run_id, solver_track,
                    road_grip_multiplier,
                ), None)
            )
        except Exception as error:
            self.result_queue.put(("single", None, error))

    def _calculate_ai_single(
        self,
        profile_id: str,
        profile_name: str,
        setup: VehicleSetup | None,
        step_m: float,
        torque_fraction: float,
        assumptions: tuple[float, float, float],
        road_grip_multiplier: float = 1.0,
        road: PlanarRoad | None = None,
    ) -> None:
        """Compare geometry-derived paths without changing the default lap."""

        try:
            # Lazy import keeps the centerline button free of optimization work.
            from lapsim.optimization.racing_line import (
                RacingLinePlanner, TrackCorridor, compare_lines_with_lap_model,
            )

            if road is not None and len(road.patches) != 1:
                raise ValueError("Desktop AI road scenario needs exactly one rectangle")

            half_width_m, vehicle_width_m, safety_margin_m = assumptions
            vehicle, manifest = self._vehicle_for_profile(profile_id, setup)
            apply_uniform_road_grip(vehicle, road_grip_multiplier)
            # Freeze the exact effective pre-run car for optional sensitivity QA.
            grid_check_vehicle = deepcopy(vehicle)
            corridor = TrackCorridor.constant(
                self.track,
                left_width_m=half_width_m,
                right_width_m=half_width_m,
                vehicle_width_m=vehicle_width_m,
                safety_margin_m=safety_margin_m,
                source="user-assumed uniform half-width; no surveyed boundaries",
            )
            planner = RacingLinePlanner(maximum_cell_length_m=step_m)
            plan = planner.plan(self.track, corridor)
            last_progress_post_s = float("-inf")
            last_progress_phase = ""
            phase_labels = {
                "baseline": "Geometric centerline",
                "full": "Full AI line",
                "half": "Half AI line",
                "three_quarter": "Three-quarter AI line",
                "adaptive": "Car-adaptive AI line",
                "grip_detour": "Grip-aware detour",
            }

            def on_progress(phase: str, phase_track: Any, snapshot: Any) -> None:
                nonlocal last_progress_post_s, last_progress_phase
                now = time.perf_counter()
                if phase != last_progress_phase:
                    last_progress_post_s = float("-inf")
                    last_progress_phase = phase
                if (
                    now - last_progress_post_s >= 0.1
                    or snapshot.cell_index + 1 == snapshot.cell_count
                ):
                    label = phase_labels.get(phase, phase)
                    self._queue_live_progress(
                        profile_name, label, phase_track, snapshot
                    )
                    last_progress_post_s = now

            comparison = compare_lines_with_lap_model(
                vehicle, plan, torque_request_fraction=torque_fraction,
                progress_callback=on_progress,
                constraint_progress_callback=lambda phase, snapshot: self._queue_live_progress(
                    profile_name, phase_labels.get(phase, phase), None, snapshot,
                ),
                phase_progress_callback=lambda phase, snapshot: self._queue_live_progress(
                    profile_name, phase_labels.get(phase, phase), None, snapshot,
                ),
                speed_periodic=True,
                minimum_selection_gain_s=AI_SELECTION_MARGIN_S,
                road=road,
                maximum_detour_cell_length_m=step_m,
            )
            selected_mode = comparison.selected_mode
            selected_run = comparison.selected_run
            selected_track = comparison.selected_track
            baseline_valid = comparison.baseline_time_s is not None
            if (
                not baseline_valid
                and comparison.candidate_run is not None
                and comparison.candidate_time_s is not None
            ):
                # Show the completed candidate, but never call it a time gain.
                selected_mode = "candidate_only_baseline_failed"
                selected_run = comparison.candidate_run
                selected_track = comparison.candidate_track
            if selected_run is None:
                # Preserve a failed attempt for diagnosis when the simulator
                # returned a run object for at least one path.
                selected_run = next(
                    (
                        run for run in (
                            comparison.baseline_run, comparison.candidate_run
                        )
                        if run is not None and run.completed
                    ),
                    None,
                ) or comparison.baseline_run or comparison.candidate_run
                selected_track = (
                    plan.baseline_track if selected_run is comparison.baseline_run
                    else comparison.candidate_track
                )
                selected_mode = "no_comparable_path"
            if selected_run is None:
                raise ValueError(
                    "Neither geometric path returned a lap record: "
                    f"centerline={comparison.baseline_error}; "
                    f"candidate={comparison.candidate_error}"
                )
            source_geometry = {
                "distance_m": self.track.distance_m,
                "x_m": self.track.x_m,
                "y_m": self.track.y_m,
                "curvature_per_m": self.track.curvature_per_m,
            }
            source_hash = sha256(
                json.dumps(source_geometry, sort_keys=True, separators=(",", ":"),
                           allow_nan=False).encode("utf-8")
            ).hexdigest()
            ai_track_id = (
                "team_endurance_xy_derived_assumed_corridor"
                if self.course_spec.course_id == DEFAULT_COURSE_ID else
                f"{self.course_spec.course_id}_xy_derived_assumed_corridor"
            )
            if road is None:
                road_condition = {"mode": "assumed_uniform_surface"}
            else:
                from lapsim.optimization.road_grip_schedule import (
                    ROAD_GRIP_SCHEDULE_MAPPING_VERSION,
                )

                road_condition = {
                    "mode": "assumed_world_fixed_low_grip_rectangle",
                    "mapping_version": ROAD_GRIP_SCHEDULE_MAPPING_VERSION,
                    "base_material_id": road.base_material_id,
                    "base_friction_multiplier": road.base_friction_multiplier,
                    "patches": [asdict(patch) for patch in road.patches],
                    "policy": "minimum_nominal_wheel_contact_grip_for_whole_cell",
                    "contact_resolution_m": 0.01,
                    "measured": False,
                }
            path_planning = {
                "mode": "experimental_racing_line",
                "algorithm": "periodic_cubic_minimum_curvature_slsqp_v7_continuous_scalar_clearance",
                "fourth_strength_policy": "eligible_quadratic_or_certified_clearance_probe_v3_fallback_0.75",
                "record_role": "selected_result",
                "source_course_id": self.course_spec.course_id,
                "source_course_label": self.course_spec.label,
                "source_course_description": self.course_spec.description,
                "synthetic_course": self.course_spec.synthetic,
                "road_condition": road_condition,
                "lap_start_policy": "speed_only_periodic_fixed_initial_vehicle_state",
                "speed_seam_tolerance_mps": 0.005,
                "maximum_lap_passes_per_trial": 2,
                "selected_mode": selected_mode,
                "diagnostic_only": selected_mode in (
                    "no_comparable_path", "candidate_only_baseline_failed"
                ),
                "rank_status": comparison.rank_status,
                "selection_margin_s": comparison.selection_margin_s,
                "candidate_strategy": comparison.candidate_strategy,
                "selected_strategy": (
                    comparison.candidate_strategy
                    if selected_mode.startswith("candidate")
                    else "geometric_centerline" if selected_mode == "centerline"
                    else None
                ),
                "candidate_offset_strength": comparison.candidate_strength,
                "selected_offset_strength": (
                    comparison.candidate_strength
                    if selected_mode.startswith("candidate")
                    else 0.0 if selected_mode == "centerline" else None
                ),
                "candidate_trials": [
                    {
                        "strategy": trial.strategy,
                        "offset_strength": trial.strength,
                        "path_length_m": trial.path_length_m,
                        "lap_time_s": trial.lap_time_s,
                        "diagnostic_lap_time_s": trial.diagnostic_lap_time_s,
                        "sampled_path_audit": (
                            asdict(trial.path_audit)
                            if trial.path_audit is not None else None
                        ),
                        "error": trial.error,
                        "reduced_grip_cells": (
                            sum(value < road_grip_multiplier
                                for value in trial.cell_road_grip_multiplier)
                            if trial.cell_road_grip_multiplier is not None else None
                        ),
                    }
                    for trial in comparison.trials
                ],
                "grip_detour_search": {
                    "version": "bounded_c2_two_sides_three_amplitudes_v1",
                    "status": comparison.grip_detour_status,
                    "reason": comparison.grip_detour_reason,
                    "side": comparison.grip_detour_side,
                    "maximum_offset_m": comparison.grip_detour_max_offset_m,
                    "baseline_weighted_exposure_m": (
                        comparison.grip_detour_baseline_exposure_m
                    ),
                    "candidate_weighted_exposure_m": (
                        comparison.grip_detour_candidate_exposure_m
                    ),
                    "constructed_geometry_count": (
                        comparison.grip_detour_candidate_count
                    ),
                    "mapped_geometry_count": (
                        comparison.grip_detour_mapped_candidate_count
                    ),
                    "compute_time_s": comparison.grip_detour_compute_time_s,
                    "extra_lap_model_trials_cap": 1,
                } if road is not None else None,
                "comparison_is_valid": (
                    baseline_valid and comparison.candidate_time_s is not None
                ),
                "source_geometry_sha256": source_hash,
                "source_geometry_audit": asdict(self.course_geometry_audit),
                "processed_baseline_geometry_audit": asdict(
                    plan.baseline_track.geometry_audit()
                ),
                "selected_solver_geometry_audit": asdict(
                    selected_track.geometry_audit()
                ),
                "user_requested_centerline_step_m": step_m,
                "user_requested_maximum_cell_length_m": step_m,
                "planner_sample_spacing_m": planner.sample_spacing_m,
                "planner_actual_sample_count": len(plan.offset_m),
                "planner_actual_sample_spacing_m": (
                    self.track.length_m / len(plan.offset_m)
                ),
                "actual_maximum_cell_length_m": max(selected_track.cell_length_m),
                "planner_control_count": planner.control_count,
                "planner_smoothing_m": planner.smoothing_m,
                "planner_maximum_iterations": planner.maximum_iterations,
                "planner_length_penalty": planner.length_penalty,
                "corridor": {
                    "source": corridor.source,
                    "left_half_width_m": half_width_m,
                    "right_half_width_m": half_width_m,
                    "vehicle_width_m": vehicle_width_m,
                    "safety_margin_m": safety_margin_m,
                },
                "baseline_lap_time_s": comparison.baseline_time_s,
                "candidate_lap_time_s": comparison.candidate_time_s,
                "baseline_diagnostic_lap_time_s": (
                    comparison.baseline_diagnostic_time_s
                ),
                "candidate_diagnostic_lap_time_s": (
                    comparison.candidate_diagnostic_time_s
                ),
                "baseline_sampled_path_audit": (
                    asdict(comparison.baseline_path_audit)
                    if comparison.baseline_path_audit is not None else None
                ),
                "candidate_sampled_path_audit": (
                    asdict(comparison.candidate_path_audit)
                    if comparison.candidate_path_audit is not None else None
                ),
                "baseline_error": comparison.baseline_error,
                "candidate_error": comparison.candidate_error,
                "baseline_length_m": plan.baseline_track.length_m,
                "candidate_length_m": comparison.candidate_track.length_m,
                "max_abs_offset_m": plan.max_abs_offset_m,
                "selected_max_abs_offset_m": (
                    plan.max_abs_offset_m * comparison.candidate_strength
                    if selected_mode.startswith("candidate")
                    and comparison.candidate_strength is not None
                    else comparison.grip_detour_max_offset_m
                    if selected_mode.startswith("candidate")
                    and comparison.candidate_strategy == "grip_detour"
                    else 0.0 if selected_mode == "centerline" else None
                ),
                "max_constraint_violation_m": plan.max_constraint_violation_m,
                "corridor_fold_ratio_max": plan.corridor_fold_ratio_max,
                "source_closure_error_m": plan.source_closure_error_m,
                "source_vs_processed_length_m": plan.source_vs_processed_length_m,
                "source_vs_processed_length_fraction": plan.source_vs_processed_length_fraction,
                "processing_shift_max_m": plan.processing_shift_max_m,
                "planner_status": plan.status,
                "planner_message": plan.message,
                "planner_objective_evaluations": plan.objective_evaluations,
                "planner_compute_time_s": plan.compute_time_s,
                "lap_comparison_compute_time_s": comparison.compute_time_s,
            }
            if selected_run is comparison.baseline_run:
                counterpart_run = comparison.candidate_run
                counterpart_track = comparison.candidate_track
                counterpart_role = "candidate_trial"
                counterpart_strength = comparison.candidate_strength
                counterpart_strategy = comparison.candidate_strategy
            else:
                counterpart_run = comparison.baseline_run
                counterpart_track = plan.baseline_track
                counterpart_role = "geometric_centerline"
                counterpart_strength = 0.0
                counterpart_strategy = "geometric_centerline"
            # Keep every returned trial on its exact solver grid. Save the
            # selected run last so its content-addressed record can link to
            # the other records without a self-referential content hash.
            saved_trial_ids: dict[int, str] = {}

            def cell_grip_for_result(result: Any) -> tuple[float, ...] | None:
                if result is None:
                    return None
                if result is comparison.baseline_run:
                    schedule = comparison.baseline_cell_road_grip_multiplier
                else:
                    schedule = next(
                    (trial.cell_road_grip_multiplier for trial in comparison.trials
                     if trial.run is result),
                    None,
                )
                if road is not None and schedule is None:
                    raise ValueError(
                        "A patch-mode AI model run has no matching cell grip schedule"
                    )
                return schedule

            def save_other_path(
                result: Any, track: Any, *, role: str, strength: float | None,
                strategy: str | None,
                audit: Any, eligible_time_s: float | None,
                diagnostic_time_s: float | None, trial_error: str | None,
            ) -> str | None:
                if result is None or result is selected_run or track is None:
                    return None
                if not result.completed and result is not counterpart_run:
                    # An aborted extra probe may have no accepted-cell trace.
                    # Keep its failure in candidate_trials, not a replay file.
                    return None
                existing = saved_trial_ids.get(id(result))
                if existing is not None:
                    return existing
                record_role = (
                    "comparison_counterpart"
                    if result is counterpart_run else role
                )
                saved_id = self._save_run_record(
                    result=result, vehicle=vehicle, manifest=manifest,
                    solver_track=track, profile_id=profile_id,
                    profile_name=profile_name, setup=setup,
                    step_m=step_m,
                    torque_fraction=torque_fraction,
                    road_grip_multiplier=road_grip_multiplier,
                    cell_road_grip_multiplier=cell_grip_for_result(result),
                    track_id=ai_track_id,
                    path_planning={
                        "mode": "experimental_racing_line",
                        "algorithm": path_planning["algorithm"],
                        "fourth_strength_policy": path_planning["fourth_strength_policy"],
                        "record_role": record_role,
                        "source_course_id": self.course_spec.course_id,
                        "source_course_label": self.course_spec.label,
                        "source_course_description": self.course_spec.description,
                        "synthetic_course": self.course_spec.synthetic,
                        "road_condition": road_condition,
                        "comparison_role": role,
                        "strategy": strategy,
                        "offset_strength": strength,
                        "user_requested_maximum_cell_length_m": step_m,
                        "actual_maximum_cell_length_m": max(track.cell_length_m),
                        "lap_start_policy": path_planning["lap_start_policy"],
                        "speed_seam_tolerance_mps": path_planning["speed_seam_tolerance_mps"],
                        "maximum_lap_passes_per_trial": path_planning["maximum_lap_passes_per_trial"],
                        "rank_status": comparison.rank_status,
                        "comparison_rank_status": comparison.rank_status,
                        "eligible_lap_time_s": eligible_time_s,
                        "diagnostic_lap_time_s": diagnostic_time_s,
                        "trial_error": trial_error,
                        "comparable_with_baseline": (
                            eligible_time_s is not None
                            and comparison.baseline_time_s is not None
                        ),
                        "diagnostic_only": (
                            eligible_time_s is None
                            or comparison.baseline_time_s is None
                        ),
                        "selection_margin_s": comparison.selection_margin_s,
                        "sampled_path_audit": (
                            asdict(audit) if audit is not None else None
                        ),
                        "source_geometry_sha256": source_hash,
                        "source_geometry_audit": asdict(self.course_geometry_audit),
                        "solver_geometry_audit": asdict(
                            track.geometry_audit()
                        ),
                        "corridor": path_planning["corridor"],
                    },
                    starting_speed_mps=result.starting_speed_mps,
                )
                saved_trial_ids[id(result)] = saved_id
                return saved_id

            counterpart_trial = next(
                (trial for trial in comparison.trials
                 if trial.run is counterpart_run and counterpart_run is not None),
                None,
            )
            if counterpart_track is plan.baseline_track:
                counterpart_audit = comparison.baseline_path_audit
                counterpart_eligible_time = comparison.baseline_time_s
                counterpart_diagnostic_time = comparison.baseline_diagnostic_time_s
                counterpart_error = comparison.baseline_error
            else:
                counterpart_audit = comparison.candidate_path_audit
                counterpart_eligible_time = (
                    counterpart_trial.lap_time_s
                    if counterpart_trial is not None else comparison.candidate_time_s
                )
                counterpart_diagnostic_time = (
                    counterpart_trial.diagnostic_lap_time_s
                    if counterpart_trial is not None
                    else comparison.candidate_diagnostic_time_s
                )
                counterpart_error = (
                    counterpart_trial.error
                    if counterpart_trial is not None else comparison.candidate_error
                )
            counterpart_run_id = save_other_path(
                counterpart_run, counterpart_track, role=counterpart_role,
                strength=counterpart_strength,
                strategy=counterpart_strategy,
                audit=counterpart_audit,
                eligible_time_s=counterpart_eligible_time,
                diagnostic_time_s=counterpart_diagnostic_time,
                trial_error=counterpart_error,
            )
            for trial, trial_row in zip(
                comparison.trials, path_planning["candidate_trials"], strict=True,
            ):
                trial_run = getattr(trial, "run", None)
                trial_track = getattr(trial, "track", None)
                trial_id = save_other_path(
                    trial_run, trial_track, role="candidate_trial",
                    strength=trial.strength, strategy=trial.strategy,
                    audit=trial.path_audit,
                    eligible_time_s=trial.lap_time_s,
                    diagnostic_time_s=trial.diagnostic_lap_time_s,
                    trial_error=trial.error,
                )
                trial_row["run_id"] = trial_id
                if trial_run is selected_run:
                    trial_row["record_role"] = "selected_result"
                elif trial_run is counterpart_run and trial_run is not None:
                    trial_row["record_role"] = "comparison_counterpart"
                elif trial_id is not None:
                    trial_row["record_role"] = "candidate_trial"
                elif trial_run is not None:
                    trial_row["record_role"] = "unsaved_incomplete"
                else:
                    trial_row["record_role"] = "no_run"
                trial_row["model_run_completed"] = (
                    trial_run.completed if trial_run is not None else None
                )
            baseline_run_id = save_other_path(
                comparison.baseline_run, plan.baseline_track,
                role="geometric_centerline", strength=0.0,
                strategy="geometric_centerline",
                audit=comparison.baseline_path_audit,
                eligible_time_s=comparison.baseline_time_s,
                diagnostic_time_s=comparison.baseline_diagnostic_time_s,
                trial_error=comparison.baseline_error,
            )
            if comparison.baseline_run is selected_run:
                baseline_record_role = "selected_result"
            elif comparison.baseline_run is counterpart_run and counterpart_run is not None:
                baseline_record_role = "comparison_counterpart"
            elif comparison.baseline_run is None:
                baseline_record_role = "no_run"
            else:
                baseline_record_role = "geometric_centerline"
            path_planning["baseline_record"] = {
                "run_id": baseline_run_id,
                "record_role": baseline_record_role,
                "model_run_completed": (
                    comparison.baseline_run.completed
                    if comparison.baseline_run is not None else None
                ),
            }
            path_planning["trial_record_manifest_version"] = 1
            path_planning["comparison_counterpart_run_id"] = counterpart_run_id
            path_planning["comparison_counterpart_role"] = (
                counterpart_role if counterpart_run_id is not None else None
            )
            run_id = self._save_run_record(
                result=selected_run, vehicle=vehicle, manifest=manifest,
                solver_track=selected_track, profile_id=profile_id,
                profile_name=profile_name, setup=setup,
                step_m=step_m,
                torque_fraction=torque_fraction,
                road_grip_multiplier=road_grip_multiplier,
                cell_road_grip_multiplier=cell_grip_for_result(selected_run),
                track_id=ai_track_id,
                path_planning=path_planning,
                starting_speed_mps=selected_run.starting_speed_mps,
            )
            self.result_queue.put((
                "ai_single",
                (profile_name, selected_run, selected_track, selected_mode,
                 plan, comparison, assumptions, run_id, road_grip_multiplier,
                 road, grid_check_vehicle, torque_fraction),
                None,
            ))
        except Exception as error:
            self.result_queue.put(("ai_single", None, error))

    def _calculate_comparison(
        self,
        plans: tuple[tuple[str, str, VehicleSetup | None], ...],
        step_m: float,
        torque_fraction: float,
        road_grip_multiplier: float = 1.0,
    ) -> None:
        try:
            solver_track = solver_track_for_course(
                self.course_spec.course_id, self.track, step_m,
            )
            prepared = []
            for profile_id, name, setup in plans:
                vehicle, manifest = self._vehicle_for_profile(profile_id, setup)
                apply_uniform_road_grip(vehicle, road_grip_multiplier)
                constraints = prepare_one_lap_constraints(
                    vehicle, solver_track,
                    constraint_progress_callback=lambda snapshot, label=name:
                        self._queue_live_progress(
                            label, "Centerline comparison", None, snapshot,
                        ),
                )
                prepared.append((
                    profile_id, name, setup, vehicle, manifest, constraints,
                ))
            common_start_mps = min(
                constraints.braking_speed_ceiling_mps[0]
                for _, _, _, _, _, constraints in prepared
            )
            outcomes = []
            run_ids = []
            for profile_id, name, setup, vehicle, manifest, constraints in prepared:
                last_progress_post_s = float("-inf")

                def on_progress(snapshot: Any) -> None:
                    nonlocal last_progress_post_s
                    now = time.perf_counter()
                    if (
                        now - last_progress_post_s >= 0.1
                        or snapshot.cell_index + 1 == snapshot.cell_count
                    ):
                        self._queue_live_progress(
                            name, "Centerline comparison", solver_track, snapshot
                        )
                        last_progress_post_s = now

                result = run_one_lap(
                    vehicle, solver_track,
                    torque_request_fraction=torque_fraction,
                    constraints=constraints,
                    starting_speed_mps=common_start_mps,
                    progress_callback=on_progress,
                )
                run_id = self._save_run_record(
                    result=result, vehicle=vehicle, manifest=manifest,
                    solver_track=solver_track, profile_id=profile_id,
                    profile_name=name, setup=setup, step_m=step_m,
                    torque_fraction=torque_fraction,
                    road_grip_multiplier=road_grip_multiplier,
                    starting_speed_mps=common_start_mps,
                )
                if not result.completed:
                    raise ValueError(
                        f"{name} did not complete: {result.failure_reason}. "
                        f"Saved run {run_id[:12]}"
                    )
                summarize_lap(result, self.track.length_m)
                outcomes.append((name, result))
                run_ids.append(run_id)
            self.result_queue.put((
                "comparison", (
                    step_m, torque_fraction, tuple(outcomes), tuple(run_ids),
                    solver_track, road_grip_multiplier,
                ),
                None,
            ))
        except Exception as error:
            self.result_queue.put(("comparison", None, error))

    def _poll_result(self) -> None:
        self._poll_live_progress()
        self._poll_pose_progress()
        try:
            kind, payload, error = self.result_queue.get_nowait()
        except queue.Empty:
            self._schedule_after(100, self._poll_result)
            return

        if kind == "ai_grid_check":
            serial, comparison, report = payload
            if (
                serial != self._ai_grid_check_serial
                or self._path_comparison is None
                or self._path_comparison[1] is not comparison
            ):
                self._schedule_after(100, self._poll_result)
                return
            self._result_generation += 1
            self._set_busy(False)
            stale_inputs = (
                self._active_run_input_signature != self._run_input_signature()
            )
            self._active_run_input_signature = None
            if stale_inputs:
                self._set_calculation_progress("idle", "Inputs changed · run again")
                self._invalidate_stale_result(force=True)
            elif error is not None:
                self._set_calculation_progress("stopped", "Finer-grid check failed")
                self.ai_grid_check_text.set(f"Finer-grid check failed: {error}")
                self.status_text.set("Finer-grid check failed; displayed runs are unchanged")
            else:
                self.ai_grid_check_text.set(self._ai_grid_check_summary(
                    report, world_road=self._displayed_ai_road is not None,
                ))
                grid_sensitive = (
                    report.status == "completed"
                    and (report.sign_stable is False
                         or report.selection_margin_stable is False)
                )
                if grid_sensitive:
                    current_result = self.ai_result_text.get()
                    if not current_result.startswith(AI_GRID_SENSITIVE_PREFIX):
                        self.ai_result_text.set(
                            AI_GRID_SENSITIVE_PREFIX + current_result
                        )
                self._set_calculation_progress(
                    "complete" if report.status == "completed" else "stopped",
                    ("Finer-grid check finished" if report.status == "completed"
                     else "Finer-grid check could not compare both paths"),
                    fraction=1.0 if report.status == "completed" else 0.0,
                )
                self.status_text.set(
                    "Finer-grid timing is grid-sensitive; ranking unresolved; "
                    "original-grid path remains displayed"
                    if grid_sensitive else
                    "Finer-grid sensitivity checked; displayed path selection unchanged"
                    if report.status == "completed" else
                    "Finer-grid sensitivity unavailable; displayed runs unchanged"
                )
            self._update_ai_grid_check_button()
            self._schedule_after(100, self._poll_result)
            return

        if kind in ("pose_record_saved", "pose_record_loaded"):
            if kind == "pose_record_loaded" and error is None:
                self._latest_pose_run = payload[1].run
            self._set_busy(False)
            if error is not None:
                action = "save" if kind == "pose_record_saved" else "load"
                self._set_calculation_progress(
                    "stopped", f"Synthetic pose trace · {action} failed",
                )
                self.pose_record_status.set(
                    f"Could not {action} synthetic trace: {error}"
                )
                self.status_text.set(f"Synthetic trace {action} failed: {error}")
            elif kind == "pose_record_saved":
                path, content_id, checked_controls = payload
                self._set_calculation_progress(
                    "complete", "Synthetic pose trace saved and checked",
                    fraction=1.0,
                )
                self.pose_record_status.set(
                    f"Saved {path.name} · ID {content_id[:12]} · numerical replay passed · "
                    f"{self._pose_controller_check_label(checked_controls)}"
                )
                self.status_text.set("Synthetic pose trace saved and checked")
            else:
                path, record = payload
                run = record.run
                road_warning = self._pose_road_domain_warning(run.status)
                scenario = next((
                    name for name in (POSE_SCENARIO_UNIFORM, POSE_SCENARIO_PATCH)
                    if run.environment == _pose_preview_environment(name)
                ), "Recorded custom synthetic road")
                if scenario in (POSE_SCENARIO_UNIFORM, POSE_SCENARIO_PATCH):
                    self.pose_scenario_var.set(scenario)
                self.pose_offset_var.set(f"{run.settings.initial_lateral_offset_m:g}")
                self._active_pose_scenario = scenario
                self._active_pose_offset_m = run.settings.initial_lateral_offset_m
                reference_geometry = getattr(
                    run.settings, "reference_geometry", "coherent_arcs",
                )
                self._active_pose_reference_label = (
                    "recorded sampled polyline"
                    if reference_geometry == "sampled_polyline" else
                    "synthetic centerline (coherent arcs)"
                )
                recorded_track = getattr(run, "track", None)
                self._active_pose_grid_label = (
                    f"recorded pose grid {recorded_track.cell_count:,} cells, "
                    f"max {max(recorded_track.cell_length_m):.3g} m"
                    if isinstance(recorded_track, SpatialTrack) else ""
                )
                self._set_calculation_progress(
                    "complete", "Synthetic pose trace loaded and checked",
                    fraction=1.0,
                )
                controller_report = getattr(record, "controller_report", None)
                self.pose_record_status.set(
                    f"Loaded {path.name} · ID {record.content_id[:12]} · "
                    "numerical replay passed · "
                    + self._pose_controller_check_label(
                        controller_report.checked_controls
                        if controller_report is not None else None
                    )
                    + (f" · {road_warning}" if road_warning else "")
                )
                self.pose_preview_status.set(
                    f"Recorded {self._active_pose_description()} · {run.status}: "
                    f"{run.samples[-1].progress_m:.1f} m in "
                    f"{run.elapsed_pose_model_time_s:.2f} s pose-model time. "
                    "This is not an engineering lap time."
                    + (f" {road_warning}" if road_warning else "")
                )
                self.status_text.set(
                    "Synthetic pose trace loaded and checked"
                    + (f" · {road_warning}" if road_warning else "")
                )
                if len(run.states) > 1:
                    self._activate_pose_preview(run)
                else:
                    self._pause_driver_playback()
                    self.driver_playback = None
                    self._live_decision = None
                    self._driver_live_mode = False
                    self._pose_live_mode = False
                    self._driver_stream_active = False
                    self._driver_preview_track = None
                    self._driver_live_update_serial += 1
                    self._driver_playback_time_s = 0.0
                    self.driver_note_var.set(
                        self._pose_reference_note(reference_geometry, run.status)
                    )
                    self._set_driver_box_mode(pose=True)
                    self.driver_decision_title.set("Pose model · no driven controls")
                    self.driver_progress_var.set(0.0)
                    self.driver_progress.configure(state="disabled")
                    if self.driver_play_button is not None:
                        self.driver_play_button.configure(state="disabled")
                    for value in self.driver_values.values():
                        value.set("—")
                    for value in self.driver_decision_values.values():
                        value.set("—")
                    self.driver_run_label.set(
                        f"Synthetic pose model · {self._active_pose_description()} · "
                        f"{run.status} · no driven step"
                    )
                    self._switch_tab("Driver view")
                    self._draw_driver_view()
            self._schedule_after(100, self._poll_result)
            return

        if kind == "pose_preview":
            self._latest_pose_run = payload if error is None else None
            self._set_busy(False)
            self._pose_live_mode = False
            self._driver_stream_active = False
            description = self._active_pose_description()
            if error is not None:
                self._driver_live_mode = False
                self.driver_playback = None
                self.driver_run_label.set(
                    f"Synthetic pose preview · {description} · failed"
                )
                self._draw_driver_view()
                self._set_calculation_progress(
                    "stopped",
                    f"Synthetic pose preview · {description} · stopped",
                )
                self.pose_preview_status.set(
                    f"Pose preview · {description} · failed: {error}"
                )
                self.status_text.set(f"Pose preview · {description} · failed: {error}")
            else:
                run: PoseDriverRun = payload
                completed = run.completed
                road_warning = self._pose_road_domain_warning(run.status)
                self._set_calculation_progress(
                    "complete" if completed else "stopped",
                    (f"Synthetic pose preview · {description} · finished"
                     if completed else
                     f"Synthetic pose preview · {description} · "
                     f"stopped: {run.status}"),
                    fraction=1.0 if completed else min(
                        max(run.samples[-1].progress_m / run.settings.target_progress_m,
                            0.0), 1.0,
                    ),
                )
                self.pose_preview_status.set(
                    f"{description} · {run.status}: "
                    f"{run.samples[-1].progress_m:.1f} m in "
                    f"{run.elapsed_pose_model_time_s:.2f} s pose-model time; "
                    f"maximum center error {run.maximum_absolute_cross_track_error_m:.2f} m; "
                    f"minimum assumed footprint slack "
                    f"{run.minimum_assumed_boundary_slack_m:.2f} m. "
                    "This is not an engineering lap time."
                    + (f" {road_warning}" if road_warning else "")
                )
                self.status_text.set(
                    f"Synthetic pose preview · {description} · "
                    f"{run.status} · separate four-wheel model"
                    + (f" · {road_warning}" if road_warning else "")
                )
                if len(run.states) > 1:
                    self._activate_pose_preview(run)
                else:
                    self._driver_live_mode = False
                    self.driver_playback = None
                    self.driver_run_label.set(
                        f"Synthetic pose model · {description} · "
                        f"{run.status} · no driven step"
                    )
                    self.driver_note_var.set(self._pose_reference_note(
                        getattr(run.settings, "reference_geometry", "coherent_arcs"),
                        run.status,
                    ))
                    self._draw_driver_view()
            self._schedule_after(100, self._poll_result)
            return

        self._result_generation += 1
        self._set_busy(False)
        stale_inputs = (
            self._active_run_input_signature is not None
            and self._active_run_input_signature != self._run_input_signature()
        )
        completed_input_signature = self._active_run_input_signature
        self._active_run_input_signature = None
        if stale_inputs:
            self._set_calculation_progress("idle", "Inputs changed · run again")
            self._invalidate_stale_result(force=True)
            self.status_text.set(
                "Inputs changed during calculation · saved run is not displayed; run again"
            )
            self._schedule_after(100, self._poll_result)
            return
        if self._driver_live_mode:
            self._driver_stream_active = False
            self._driver_preview_track = None
            self._driver_live_update_serial += 1
            if self.driver_playback is None:
                self.driver_run_label.set("No accepted model step · calculation ended")
            else:
                self.driver_run_label.set(
                    f"Last accepted step · {self.driver_run_label.get()}"
                )
            self._draw_driver_view()
        elapsed_s = time.perf_counter() - self.run_started_at
        if error is not None or (
            kind == "single" and not payload[2].completed
        ) or (
            kind == "ai_single" and not payload[1].completed
        ) or (
            kind == "comparison"
            and any(not result.completed for _, result in payload[2])
        ):
            self._set_calculation_progress("stopped", "Calculation stopped · see status")
        else:
            self._set_calculation_progress(
                "complete", "Calculation finished", fraction=1.0,
            )
        if error is not None:
            self._set_driver_replay_options({}, selected="—")
            self._set_displayed_run_records(())
            self.status_text.set(f"Calculation failed: {error}")
            messagebox.showerror("Lap calculation failed", str(error), parent=self.root)
        elif kind == "single":
            profile_name, step_m, result, run_id, solver_track, *grip_setting = payload
            self._set_displayed_run_records((("Lap result", run_id),))
            road_grip_multiplier = grip_setting[0] if grip_setting else 1.0
            self._set_driver_replay_options({}, selected="—")
            if result.completed:
                self._displayed_road_grip_multiplier = road_grip_multiplier
                self._comparison_results = None
                self._last_result = result
                self._selected_path_track = None
                self._show_result(result)
                self._activate_driver_playback(
                    profile_name, result, path_track=solver_track,
                )
                self.status_text.set(
                    f"{profile_name} completed in {elapsed_s:.1f} s · "
                    f"requested Cell size (max) {step_m:g} m · assumed grip "
                    f"{road_grip_multiplier * 100:g}% · saved run {run_id[:12]}"
                )
            else:
                self.status_text.set(
                    f"Lap did not complete: {result.failure_reason} · "
                    f"saved run {run_id[:12]}"
                )
                messagebox.showerror(
                    "Lap did not complete", str(result.failure_reason), parent=self.root
                )
        elif kind == "ai_single":
            (profile_name, result, selected_track, selected_mode,
             plan, comparison, assumptions, run_id, *grip_setting) = payload
            candidate_strategy = getattr(comparison, "candidate_strategy", None)
            self._set_displayed_run_records((("AI result", run_id),))
            road_grip_multiplier = grip_setting[0] if grip_setting else 1.0
            self._displayed_road_grip_multiplier = road_grip_multiplier
            self._displayed_ai_road = grip_setting[1] if len(grip_setting) > 1 else None
            self._path_comparison = (plan, comparison, assumptions)
            self._ai_grid_check_inputs = (
                (grip_setting[2], grip_setting[3])
                if len(grip_setting) >= 4 else None
            )
            self._ai_grid_source_signature = completed_input_signature
            self.ai_grid_check_text.set(
                ("Optional finer-grid check is available; the assumed world "
                 "patch will be remapped on each fixed path."
                 if self._displayed_ai_road is not None else
                 "Optional finer-grid check is available for eligible paths.")
                if self._ai_grid_check_eligible() else
                "Finer-grid check requires two eligible completed paths."
            )
            self._update_ai_grid_check_button()
            if self.ai_compare_button is not None:
                self.ai_compare_button.configure(
                    state=("normal" if comparison.baseline_time_s is not None
                           and comparison.candidate_time_s is not None else "disabled")
                )
            if self.ai_output_box is not None and not self.ai_output_box.winfo_manager():
                self.ai_output_box.pack(fill="x", pady=(0, 8))
            baseline_time = comparison.baseline_time_s
            candidate_time = comparison.candidate_time_s
            baseline_diagnostic_time = comparison.baseline_diagnostic_time_s
            candidate_diagnostic_time = comparison.candidate_diagnostic_time_s

            def time_box(valid_time: float | None, diagnostic_time: float | None) -> str:
                if valid_time is not None:
                    return f"{valid_time:.3f}"
                if diagnostic_time is not None:
                    return f"{diagnostic_time:.3f}*"
                return "—"

            values = {
                "baseline": time_box(baseline_time, baseline_diagnostic_time),
                "candidate": time_box(
                    candidate_time if baseline_time is not None else None,
                    candidate_diagnostic_time if baseline_time is not None
                    else candidate_time or candidate_diagnostic_time,
                ),
                "difference": (
                    f"{candidate_time - baseline_time:+.3f}"
                    if baseline_time is not None and candidate_time is not None else "—"
                ),
                "length": f"{selected_track.length_m:.1f}",
            }
            for key, value in values.items():
                self.ai_output_values[key].configure(text=value)
            half_width_m, vehicle_width_m, margin_m = assumptions
            if (
                selected_mode == "no_comparable_path"
                and comparison.rank_status == "invalid_candidate_path"
            ):
                selection = (
                    "No eligible path is selected: the modeled AI path fails "
                    "the modeled-path clearance or closure check, and the geometric "
                    "centerline did not produce an eligible timed lap. Starred "
                    "times are diagnostic only."
                )
            elif comparison.rank_status == "invalid_processed_baseline":
                selection = (
                    "AI paths cannot be ranked: the modeled geometric centerline "
                    "fails the modeled-path clearance or closure check. "
                    "Starred times are diagnostic only."
                )
            elif comparison.rank_status == "invalid_candidate_path":
                selection = (
                    "The modeled AI path fails the modeled-path clearance or "
                    "closure check; geometric centerline selected. "
                    "A starred candidate time is diagnostic only."
                )
            elif comparison.rank_status == "path_audit_unavailable":
                selection = (
                    "AI paths cannot be ranked because the modeled-path audit "
                    "could not run. Starred times are diagnostic only."
                )
            elif selected_mode == "no_comparable_path":
                selection = "Neither geometric path produced a valid timed lap. A diagnostic run was saved."
            elif selected_mode == "candidate":
                selection = (
                    "Faster grip-aware detour selected after full-model timing."
                    if candidate_strategy == "grip_detour"
                    else f"Faster AI path selected at {comparison.candidate_strength:g}× "
                         "of the proposed offset."
                )
            elif selected_mode == "candidate_only_baseline_failed":
                selection = (
                    "Grip-aware detour completed; geometric centerline failed, "
                    "so no time gain is established."
                    if candidate_strategy == "grip_detour"
                    else f"AI path at {comparison.candidate_strength:g}× offset completed; "
                         "geometric centerline failed, so no time gain is established."
                )
            elif comparison.rank_status == "unresolved_close_gain":
                selection = (
                    "Best tested AI path was numerically faster, but its gain is "
                    f"at most the {comparison.selection_margin_s:.2f} s provisional "
                    "selection margin. Geometric centerline selected; a finer-grid "
                    "study is needed before ranking these paths."
                )
            elif candidate_time is not None:
                selection = "Best tested AI path was slower; geometric centerline selected."
            else:
                selection = "No valid faster AI candidate; geometric centerline selected."
            if (
                baseline_time is not None and candidate_time is not None
                and comparison.rank_status == "candidate_not_faster"
                and abs(candidate_time - baseline_time) <= comparison.selection_margin_s
            ):
                selection += (
                    " This small difference does not establish a reliable "
                    "time ranking; a finer-grid study is needed."
                )
            audit_notes = []
            for label, audit in (
                ("centerline", comparison.baseline_path_audit),
                ("AI path", comparison.candidate_path_audit),
            ):
                if audit is not None and not audit.valid:
                    audit_notes.append(
                        f"{label}: sampled excess "
                        f"{audit.maximum_corridor_excess_m:.3f} m, "
                        f"seam gap {audit.seam_position_error_m:.3f} m"
                    )
            audit_text = (
                " Modeled-path audit: " + "; ".join(audit_notes) + "."
                if audit_notes else ""
            )
            comparison_note = (
                "Compare only eligible x/y-derived times."
                if baseline_time is not None and candidate_time is not None
                else "Diagnostic numbers do not establish a path ranking."
            )
            source_curvature_note = (
                " The default lap uses different source curvature."
                if not self.course_spec.synthetic else ""
            )
            surface_error_note = ""
            if self._displayed_ai_road is not None:
                surface_errors = tuple(dict.fromkeys(
                    message for message in (
                        comparison.baseline_error if baseline_time is None else None,
                        comparison.candidate_error if candidate_time is None else None,
                    ) if message is not None
                ))
                if surface_errors:
                    surface_error_note = " Trial error: " + "; ".join(surface_errors) + "."
                if getattr(comparison, "grip_detour_status", None) is not None:
                    surface_error_note += (
                        f" Grip detour: {comparison.grip_detour_status}."
                    )
            self.ai_result_text.set(
                (f"SYNTHETIC COURSE: {self.course_spec.label}. "
                 if self.course_spec.synthetic else "")
                + f"{selection} Assumed ±{half_width_m:g} m corridor, "
                f"{vehicle_width_m:g} m car, {margin_m:g} m margin. "
                f"{_ai_road_label(self._displayed_ai_road, road_grip_multiplier)} "
                f"Proposed max offset {plan.max_abs_offset_m:.2f} m; "
                f"{len(comparison.trials)} candidate trial(s). "
                f"source map length differs by {plan.source_vs_processed_length_fraction:+.1%}."
                f"{audit_text}{surface_error_note} {comparison_note}{source_curvature_note} "
                "A trial receives a comparison time only when "
                "its rolling-start speed closes within 0.005 m/s and its "
                "modeled path passes its continuous scalar-clearance and closure "
                "checks. This is not a swept-body collision proof. "
                "This uses a fixed initial car and pack state; other states "
                "need not be periodic."
            )
            if result.completed:
                eligible_selection = selected_mode not in (
                    "no_comparable_path", "candidate_only_baseline_failed"
                )
                runs = []
                if comparison.baseline_time_s is not None and comparison.baseline_run is not None:
                    runs.append(("Geometric centerline", comparison.baseline_run))
                if comparison.candidate_time_s is not None and comparison.candidate_run is not None:
                    runs.append(("Best tested AI path", comparison.candidate_run))
                self._comparison_results = (
                    tuple(runs) if eligible_selection and len(runs) == 2 else None
                )
                self._selected_path_track = selected_track if eligible_selection else None
                self._last_result = result if eligible_selection else None
                if eligible_selection:
                    self._show_result(result, track_length_m=selected_track.length_m)
                else:
                    self._draw_plots(preserve_course_view=True)
                self._activate_driver_playback(
                    profile_name, result,
                    driving_mode=(
                        "Diagnostic reference · path not cleared"
                        if not eligible_selection else
                        "AI path" if selected_mode.startswith("candidate")
                        else "Geometric centerline"
                    ),
                    path_track=selected_track,
                )
                replay_options: dict[str, tuple[str, Any, str, Any]] = {}
                baseline_replay_label = (
                    "Geometric centerline" if comparison.baseline_time_s is not None
                    else "Geometric centerline · diagnostic"
                )
                candidate_replay_label = "Best tested AI path"
                candidate_replay_label += (
                    " · grip-aware detour"
                    if candidate_strategy == "grip_detour"
                    else f" · {comparison.candidate_strength:g}x offset"
                    if comparison.candidate_strength is not None else ""
                )
                if (
                    comparison.baseline_time_s is None
                    or comparison.candidate_time_s is None
                ):
                    candidate_replay_label += " · diagnostic"
                if comparison.baseline_run is not None and comparison.baseline_run.completed:
                    replay_options[baseline_replay_label] = (
                        profile_name, comparison.baseline_run,
                        baseline_replay_label, plan.baseline_track,
                    )
                if comparison.candidate_run is not None and comparison.candidate_run.completed:
                    replay_options[candidate_replay_label] = (
                        profile_name, comparison.candidate_run,
                        candidate_replay_label, comparison.candidate_track,
                    )
                for trial in comparison.trials:
                    trial_run = getattr(trial, "run", None)
                    trial_track = getattr(trial, "track", None)
                    if (
                        trial_run is None or not trial_run.completed
                        or trial_track is None
                        or trial_run is comparison.candidate_run
                    ):
                        continue
                    trial_label = _ai_trial_label(
                        getattr(trial, "strategy", None),
                        getattr(trial, "strength", None), ascii_x=True,
                    )
                    if comparison.baseline_time_s is None or trial.lap_time_s is None:
                        trial_label += " · diagnostic"
                    replay_options[trial_label] = (
                        profile_name, trial_run, trial_label, trial_track,
                    )
                self._set_driver_replay_options(
                    replay_options,
                    selected=(
                        candidate_replay_label
                        if result is comparison.candidate_run
                        else baseline_replay_label
                    ),
                )
                self.status_text.set(
                    f"Experimental path calculation: {selection} "
                    f"{elapsed_s:.1f} s · saved run {run_id[:12]}"
                )
            else:
                self._set_driver_replay_options({}, selected="—")
                detail = (
                    comparison.baseline_error or comparison.candidate_error
                    or result.failure_reason or "No valid timed lap"
                )
                self.status_text.set(
                    f"Experimental path had no valid timed lap: {detail} · saved run {run_id[:12]}"
                )
                messagebox.showerror("No valid timed lap", str(detail), parent=self.root)
        else:
            step_m, torque_fraction, outcomes, run_ids, solver_track, *grip_setting = payload
            self._set_displayed_run_records((
                ("Car A", run_ids[0]), ("Car B", run_ids[1]),
            ))
            road_grip_multiplier = grip_setting[0] if grip_setting else 1.0
            self._displayed_road_grip_multiplier = road_grip_multiplier
            self._comparison_results = outcomes
            self._last_result = outcomes[0][1]
            self._selected_path_track = None
            self._show_result(outcomes[0][1])
            self._set_driver_run(
                outcomes[0][0], outcomes[0][1], path_track=solver_track,
            )
            replay_options = {
                f"{letter} · {name}": (name, result, "Centerline", solver_track)
                for letter, (name, result) in zip("AB", outcomes, strict=True)
            }
            self._set_driver_replay_options(
                replay_options, selected=next(iter(replay_options)),
            )
            self._show_comparison(
                outcomes, step_m, torque_fraction, run_ids,
                road_grip_multiplier=road_grip_multiplier,
            )
            self.status_text.set(
                f"Comparison completed in {elapsed_s:.1f} s · "
                f"assumed grip {road_grip_multiplier * 100:g}% · "
                f"saved A {run_ids[0][:10]}, B {run_ids[1][:10]}"
            )
        self._update_pose_ai_preview_availability()
        self._schedule_after(100, self._poll_result)

    def _show_result(self, result: Any, *, track_length_m: float | None = None) -> None:
        summary = summarize_lap(
            result, self.track.length_m if track_length_m is None else track_length_m
        )
        values = {
            "lap_time": f"{summary.lap_time_s:.2f}",
            "peak_speed": f"{summary.peak_speed_kph:.1f}",
            "average_speed": f"{summary.average_speed_kph:.1f}",
            "distance": f"{summary.distance_m:.0f}",
            "energy": f"{summary.pack_energy_kwh:.3f}",
            "lateral_g": f"{summary.peak_lateral_g:.2f}",
            "entry_speed": (
                f"{result.starting_speed_mps * 3.6:.1f}"
                if result.starting_speed_mps is not None else "—"
            ),
            "exit_speed": (
                f"{result.ending_speed_mps * 3.6:.1f}"
                if result.ending_speed_mps is not None else "—"
            ),
        }
        for key, value in values.items():
            self.output_values[key].configure(text=value)
        self._draw_plots(preserve_course_view=True)

    def _ai_grid_check_eligible(self) -> bool:
        if (
            not self._ai_mode_selected()
            or self._path_comparison is None
            or self._ai_grid_check_inputs is None
            or self._pending_input_invalidation
            or self._ai_grid_source_signature is None
            or self._ai_grid_source_signature != self._run_input_signature()
        ):
            return False
        plan, comparison, _assumptions = self._path_comparison
        return bool(
            isinstance(plan.baseline_track, SpatialTrack)
            and isinstance(comparison.candidate_track, SpatialTrack)
            and comparison.baseline_time_s is not None
            and comparison.candidate_time_s is not None
            and comparison.baseline_run is not None
            and comparison.baseline_run.completed
            and comparison.candidate_run is not None
            and comparison.candidate_run.completed
            and comparison.baseline_path_audit is not None
            and comparison.baseline_path_audit.valid
            and comparison.candidate_path_audit is not None
            and comparison.candidate_path_audit.valid
        )

    def _update_ai_grid_check_button(self) -> None:
        if self.ai_grid_check_button is not None:
            self.ai_grid_check_button.configure(
                state=("normal" if not self.run_in_progress
                       and self._ai_grid_check_eligible() else "disabled"),
            )

    def _clear_ai_grid_check(self) -> None:
        self._ai_grid_check_serial += 1
        self._ai_grid_check_inputs = None
        self._ai_grid_source_signature = None
        self.ai_grid_check_text.set("")
        self._update_ai_grid_check_button()

    def _start_ai_grid_check(self) -> None:
        """Optionally test fixed eligible paths at a finer numerical grid."""

        if self.run_in_progress or not self._ai_grid_check_eligible():
            return
        assert self._path_comparison is not None
        assert self._ai_grid_check_inputs is not None
        assert self._ai_grid_source_signature is not None
        plan, comparison, _assumptions = self._path_comparison
        vehicle, torque_fraction = self._ai_grid_check_inputs
        self._ai_grid_check_serial += 1
        serial = self._ai_grid_check_serial
        self._active_run_input_signature = self._ai_grid_source_signature
        self._set_busy(True)
        self._set_calculation_progress(
            "indeterminate",
            "Finer-grid check · two fixed paths · pass progress unavailable",
        )
        road = deepcopy(self._displayed_ai_road)
        self.ai_grid_check_text.set(
            "Checking two fixed paths with the world patch remapped on each finer path…"
            if road is not None else
            "Checking numerical sensitivity on the same fixed paths…"
        )
        self.status_text.set("Checking eligible AI path times on a finer grid…")
        threading.Thread(
            target=self._calculate_ai_grid_check,
            args=(
                serial, comparison, deepcopy(vehicle), plan.baseline_track,
                comparison.candidate_track, comparison.baseline_time_s,
                comparison.candidate_time_s, torque_fraction,
                comparison.selection_margin_s, road,
            ),
            daemon=True,
        ).start()

    def _calculate_ai_grid_check(
        self, serial: int, comparison: Any, vehicle: Any,
        baseline_track: SpatialTrack, candidate_track: SpatialTrack,
        baseline_time_s: float, candidate_time_s: float,
        torque_fraction: float, selection_margin_s: float,
        road: PlanarRoad | None,
    ) -> None:
        try:
            from lapsim.optimization.grid_stability import diagnose_paired_grid_stability

            report = diagnose_paired_grid_stability(
                vehicle, baseline_track, candidate_track,
                original_baseline_time_s=baseline_time_s,
                original_candidate_time_s=candidate_time_s,
                torque_request_fraction=torque_fraction,
                speed_periodic=True,
                selection_margin_s=selection_margin_s,
                road=road,
            )
            self.result_queue.put(("ai_grid_check", (serial, comparison, report), None))
        except Exception as error:
            self.result_queue.put(("ai_grid_check", (serial, comparison, None), error))

    @staticmethod
    def _ai_grid_check_summary(
        report: Any, *, world_road: bool = False,
    ) -> str:
        if report.status != "completed":
            return (
                f"Finer-grid check {report.status.replace('_', ' ')}: "
                f"{report.failure_reason or 'no refined comparison available'}. "
                "Displayed path is unchanged."
            )
        sign = "yes" if report.sign_stable else "no"
        margin = "yes" if report.selection_margin_stable else "no"
        road_note = (
            "World-fixed patch remapped on each refined path. "
            if world_road else "Uniform road held fixed. "
        )
        return (
            "Fixed-path grid sensitivity: candidate − centerline "
            f"{report.original_candidate_minus_baseline_s:+.3f} s original, "
            f"{report.refined_candidate_minus_baseline_s:+.3f} s at "
            f"max {report.maximum_refined_cell_length_m:.3g} m "
            f"({report.refined_baseline_cells:,}/{report.refined_candidate_cells:,} cells). "
            f"Sign stable: {sign}; {report.selection_margin_s:.2f} s selection "
            f"margin stable: {margin}. {road_note}Displayed path is unchanged. One refinement "
            "does not certify convergence, corridor clearance, or real-car time."
        )

    def _show_path_comparison(self) -> None:
        if self._path_comparison is None:
            return
        plan, comparison, assumptions = self._path_comparison
        if (
            comparison.baseline_time_s is None
            or comparison.candidate_time_s is None
            or comparison.baseline_run is None
            or not comparison.baseline_run.completed
            or comparison.candidate_run is None or not comparison.candidate_run.completed
        ):
            return
        baseline = summarize_lap(
            comparison.baseline_run, plan.baseline_track.length_m
        )
        candidate = summarize_lap(
            comparison.candidate_run, comparison.candidate_track.length_m
        )
        course_label = self.course_spec.label
        synthetic_course = self.course_spec.synthetic
        window = tk.Toplevel(self.root)
        window.title("LapSim path comparison")
        window.geometry("800x475")
        body = tk.Frame(window, padx=12, pady=12)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="Experimental path comparison", font=FONT_TITLE).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 5)
        )
        tk.Label(
            body,
            text=(f"Course: {course_label}. One car, one geometric source, "
                  f"assumed ±{assumptions[0]:g} m "
                  f"corridor. {_ai_road_label(self._displayed_ai_road, self._displayed_road_grip_multiplier or 1.0)} "
                  + (
                      "Best tested AI path is a grip-aware detour. "
                      if getattr(comparison, "candidate_strategy", None) == "grip_detour"
                      else f"Best tested AI path uses {comparison.candidate_strength:g}× proposed offset. "
                  )
                  + "Candidate − centerline; negative lap-time Δ is faster."),
            anchor="w", justify="left", wraplength=755,
        ).grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        for column, heading in enumerate((
            "Measure", "Geometric centerline", "Best tested AI path", "Δ candidate − centerline",
        )):
            tk.Label(
                body, text=heading, font=FONT_BOLD, anchor="w", wraplength=180,
            ).grid(row=2, column=column, sticky="ew", padx=3, pady=3)
        rows = (
            ("Lap time (s)", "lap_time_s", 3),
            ("Path length (m)", "distance_m", 1),
            ("Peak speed (km/h)", "peak_speed_kph", 1),
            ("Average speed (km/h)", "average_speed_kph", 1),
            ("Equivalent energy (kWh)", "pack_energy_kwh", 3),
            ("Peak lateral (g)", "peak_lateral_g", 2),
        )
        for row, (label, field, places) in enumerate(rows, start=3):
            base_value = getattr(baseline, field)
            candidate_value = getattr(candidate, field)
            cells = (
                label, f"{base_value:.{places}f}",
                f"{candidate_value:.{places}f}",
                f"{candidate_value - base_value:+.{places}f}",
            )
            for column, value in enumerate(cells):
                tk.Label(
                    body, text=value, anchor="w" if column == 0 else "e",
                    relief="solid", bd=1, padx=6, pady=5,
                    font=FONT if column == 0 else ("Consolas", 10),
                ).grid(row=row, column=column, sticky="ew", padx=3, pady=2)
        baseline_seam = comparison.baseline_run.seam_speed_delta_mps
        candidate_seam = comparison.candidate_run.seam_speed_delta_mps
        seam_cells = (
            "Seam speed Δ (km/h)",
            f"{baseline_seam * 3.6:+.1f}" if baseline_seam is not None else "—",
            f"{candidate_seam * 3.6:+.1f}" if candidate_seam is not None else "—",
            f"{(candidate_seam - baseline_seam) * 3.6:+.1f}"
            if baseline_seam is not None and candidate_seam is not None else "—",
        )
        for column, value in enumerate(seam_cells):
            tk.Label(
                body, text=value, anchor="w" if column == 0 else "e",
                relief="solid", bd=1, padx=6, pady=5,
                font=FONT if column == 0 else ("Consolas", 10),
            ).grid(row=9, column=column, sticky="ew", padx=3, pady=2)
        for column in range(4):
            body.grid_columnconfigure(column, weight=1)
        tk.Label(
            body,
            text=(
                "Widths and vehicle envelope are assumptions. This synthetic "
                "course demonstrates the model and optimizer; it is not a "
                "surveyed Formula SAE course or a validated Terps prediction. "
                if synthetic_course else
                "Widths and vehicle envelope are assumptions. The source x/y "
                "map and recorded curvature disagree; these are model "
                "scenarios, not validated Terps lap predictions. "
            ) + (
                "Seam speed Δ is finish minus start; the timed AI trials "
                "close it within 0.005 m/s at a fixed initial car and pack state."
            ),
            anchor="w", justify="left", wraplength=755,
        ).grid(row=10, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        self._apply_theme()

    def _show_comparison(
        self, outcomes: tuple[tuple[str, Any], ...], step_m: float,
        torque_fraction: float, run_ids: tuple[str, ...],
        road_grip_multiplier: float = 1.0,
    ) -> None:
        first_name, first_result = outcomes[0]
        second_name, second_result = outcomes[1]
        first = summarize_lap(first_result, self.track.length_m)
        second = summarize_lap(second_result, self.track.length_m)
        window = tk.Toplevel(self.root)
        window.title("LapSim car comparison")
        window.geometry("760x585")
        box = tk.Frame(window, padx=12, pady=12)
        box.pack(fill="both", expand=True)
        tk.Label(box, text="Same course, run settings and rolling start", font=FONT_TITLE).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 5)
        )
        tk.Label(
            box,
            text=f"Course: {self.course_spec.label} · Cell size (max): {step_m:g} m · driver request: "
                 f"{torque_fraction * 100:g}% · assumed uniform road grip: "
                 f"{road_grip_multiplier * 100:g}% · "
                 "Δ = B − A; positive lap-time Δ is slower",
            anchor="w", justify="left", wraplength=720,
        ).grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 12))
        headings = (
            "Measure",
            f"A · {first_name.removeprefix('Built-in: ').removeprefix('Saved: ')}",
            f"B · {second_name.removeprefix('Built-in: ').removeprefix('Saved: ')}",
            "Δ B − A",
        )
        for column, heading in enumerate(headings):
            tk.Label(
                box, text=heading, font=FONT_BOLD, anchor="w",
                justify="left", wraplength=180,
            ).grid(
                row=2, column=column, sticky="ew", padx=4, pady=4
            )
        rows = (
            ("Lap time (s)", "lap_time_s", 2),
            ("Peak speed (km/h)", "peak_speed_kph", 1),
            ("Average speed (km/h)", "average_speed_kph", 1),
            ("Distance (m)", "distance_m", 0),
            ("Net energy* (kWh)", "pack_energy_kwh", 3),
            ("Peak lateral (g)", "peak_lateral_g", 2),
        )
        for row_number, (label, field, places) in enumerate(rows, start=3):
            a_value = getattr(first, field)
            b_value = getattr(second, field)
            for column, value in enumerate((label, f"{a_value:.{places}f}", f"{b_value:.{places}f}", f"{b_value - a_value:+.{places}f}")):
                tk.Label(
                    box, text=value, anchor="w" if column == 0 else "e",
                    relief="solid", bd=1, padx=6, pady=5,
                    font=("Consolas", 10) if column else FONT,
                ).grid(row=row_number, column=column, sticky="ew", padx=2, pady=2)
        for row_number, label, a_speed, b_speed in (
            (9, "Shared start speed (km/h)", first_result.starting_speed_mps,
             second_result.starting_speed_mps),
            (10, "Finish speed (km/h)", first_result.ending_speed_mps,
             second_result.ending_speed_mps),
        ):
            speed_cells = (
                label,
                f"{a_speed * 3.6:.1f}" if a_speed is not None else "—",
                f"{b_speed * 3.6:.1f}" if b_speed is not None else "—",
                f"{(b_speed - a_speed) * 3.6:+.1f}"
                if a_speed is not None and b_speed is not None else "—",
            )
            for column, value in enumerate(speed_cells):
                tk.Label(
                    box, text=value, anchor="w" if column == 0 else "e",
                    relief="solid", bd=1, padx=6, pady=5,
                    font=("Consolas", 10) if column else FONT,
                ).grid(row=row_number, column=column, sticky="ew", padx=2, pady=2)
        first_seam = first_result.seam_speed_delta_mps
        second_seam = second_result.seam_speed_delta_mps
        seam_cells = (
            "Seam speed Δ (km/h)",
            f"{first_seam * 3.6:+.1f}" if first_seam is not None else "—",
            f"{second_seam * 3.6:+.1f}" if second_seam is not None else "—",
            f"{(second_seam - first_seam) * 3.6:+.1f}"
            if first_seam is not None and second_seam is not None else "—",
        )
        for column, value in enumerate(seam_cells):
            tk.Label(
                box, text=value, anchor="w" if column == 0 else "e",
                relief="solid", bd=1, padx=6, pady=5,
                font=("Consolas", 10) if column else FONT,
            ).grid(row=11, column=column, sticky="ew", padx=2, pady=2)
        for column in range(4):
            box.grid_columnconfigure(column, weight=1)
        tk.Label(
            box,
            text="*Equivalent pack-model energy. Seam speed Δ = finish minus start; "
                 "a nonzero value means a single initial-condition lap, not "
                 "a periodic steady-state lap. These are "
                 + ("synthetic course model comparisons." if self.course_spec.synthetic
                    else "model comparisons on the selected source course."),
            anchor="w", justify="left", wraplength=720,
        ).grid(row=12, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        tk.Label(
            box,
            text=f"Saved records: A {run_ids[0][:16]} · B {run_ids[1][:16]}",
            anchor="w", font=("Consolas", 9),
        ).grid(row=13, column=0, columnspan=4, sticky="ew", pady=(5, 0))
        self._apply_theme()


def main() -> None:
    root = tk.Tk()
    LapSimDesktop(root)
    root.mainloop()
