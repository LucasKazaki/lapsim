"""Native, monochrome desktop interface for the LapSim model."""

from __future__ import annotations

from hashlib import sha256
import json
import queue
import threading
import time
import tkinter as tk
from dataclasses import asdict
from tkinter import messagebox, simpledialog
from typing import Any

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from lapsim.experiments import LapRunSettings, capture_lap_run, default_run_directory
from lapsim.profiles import build_vehicle, browse_records, list_profiles

from .comparison import summarize_lap
from .driver_view import DriverPlayback
from .garage import CAR_INPUT_KEYS, ProfileStore, SavedCarProfile
from .presets import VehicleSetup, make_prius_benchmark
from .simulation import (
    endurance_run_config,
    load_team_endurance_track,
    path_solver_settings,
    resample_track,
    run_one_lap,
)


FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 16, "bold")
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


class LapSimDesktop:
    """Build the Tk desktop application around the shared physics APIs."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("LapSim — Formula SAE Lap Simulator")
        self.root.geometry("1380x900")
        self.root.minsize(1080, 720)

        self.track = load_team_endurance_track()
        self.course_geometry_audit = self.track.geometry_audit()
        self.result_queue: queue.Queue[tuple[str, Any, BaseException | None]] = (
            queue.Queue()
        )
        self.run_started_at = 0.0
        self.run_in_progress = False
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
        self.ai_result_text = tk.StringVar(value="Select AI racing line to compare modeled paths.")
        self.ai_output_values: dict[str, tk.Label] = {}
        self.ai_entries: list[tk.Entry] = []
        self.ai_output_box: tk.LabelFrame | None = None
        self.ai_compare_button: tk.Button | None = None
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
        self._comparison_results: tuple[tuple[str, Any], tuple[str, Any]] | None = None
        self._active_tab = "Analysis"
        self.tab_buttons: dict[str, tk.Button] = {}
        self.driver_playback: DriverPlayback | None = None
        self.driver_canvas: tk.Canvas | None = None
        self.driver_play_button: tk.Button | None = None
        self.driver_run_label = tk.StringVar(value="Run a lap to load playback")
        self.driver_speed_var = tk.StringVar(value="1×")
        self.driver_progress_var = tk.DoubleVar(value=0.0)
        self.driver_values = {
            key: tk.StringVar(value="—")
            for key in ("time", "distance", "speed", "lateral", "heading")
        }
        self._driver_playing = False
        self._driver_playback_time_s = 0.0
        self._driver_last_clock_s = 0.0
        self._driver_after_id: str | None = None
        self._driver_updating_scale = False
        self._driver_look_ahead_m = 80.0
        self._build_window()
        self._refresh_profile_menus()
        self._select_profile("prius_2026_le")
        self._apply_theme()
        self.root.after(100, self._poll_result)

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
        self._build_outputs(input_panel)
        for widget in (left_canvas, input_panel, *self._walk_widgets(input_panel)):
            widget.bind(
                "<MouseWheel>",
                lambda event: left_canvas.yview_scroll(
                    -int(event.delta / 120), "units"
                ),
            )
        self._build_workspace_tabs(right)

        footer = tk.Label(
            self.root,
            text=(
                "Course: team endurance recording · profiles are modeling scenarios · "
                "lap outputs are estimates"
            ),
            anchor="w",
            padx=10,
            pady=5,
            font=("Segoe UI", 9),
        )
        footer.pack(fill="x")

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
            ("Solver step", "solver_step_m", "m"),
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

        self.run_button = tk.Button(
            box,
            text="Run one lap",
            command=self._start_run,
            relief="raised",
            bd=1,
            padx=8,
            pady=5,
            font=FONT_BOLD,
        )
        self.run_button.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(9, 3))
        self.status_text = tk.StringVar(value="Ready")
        tk.Label(
            box,
            textvariable=self.status_text,
            anchor="w",
            justify="left",
            wraplength=350,
        ).grid(row=12, column=0, columnspan=3, sticky="ew", pady=(4, 0))

        path_box = tk.LabelFrame(
            parent, text="Driving path", font=FONT_BOLD,
            padx=8, pady=8, bd=1, relief="solid",
        )
        path_box.pack(fill="x", pady=(0, 8), before=box)
        tk.Label(path_box, text="Mode", anchor="w").grid(row=0, column=0, sticky="w")
        self.driving_mode_menu = tk.OptionMenu(
            path_box, self.driving_mode_var,
            "Centerline (default)", "AI racing line (experimental)",
            command=lambda _value: self._on_driving_mode_change(),
        )
        self.driving_mode_menu.configure(relief="raised", bd=1, anchor="w", font=FONT)
        self.driving_mode_menu.grid(row=0, column=1, sticky="ew", pady=(0, 5))
        for row, (label, variable) in enumerate((
            ("Assumed half-width", self.ai_half_width_var),
            ("Vehicle width", self.ai_vehicle_width_var),
            ("Safety margin", self.ai_margin_var),
        ), start=1):
            tk.Label(path_box, text=label, anchor="w").grid(row=row, column=0, sticky="w", pady=2)
            entry = tk.Entry(
                path_box, textvariable=variable, width=11, justify="right",
                relief="solid", bd=1, font=FONT,
            )
            entry.grid(row=row, column=1, sticky="ew", pady=2)
            self.ai_entries.append(entry)
            tk.Label(path_box, text="m").grid(row=row, column=2, sticky="w", padx=(5, 0))
        path_box.grid_columnconfigure(1, weight=1)
        tk.Label(
            path_box,
            text=("AI mode uses a deterministic path optimizer and an assumed "
                  "uniform corridor. No measured course widths are available. "
                  "It uses a 2 m path grid and up to two model lap evaluations. "
                  "Its rebuilt x/y course has different lap times from the "
                  "default source-curvature course. Solver step above applies "
                  "to centerline mode."),
            justify="left", anchor="w", wraplength=350, font=("Segoe UI", 9),
        ).grid(row=4, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self._on_driving_mode_change()

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
            text="*Equivalent battery model; not measured Prius fuel or battery use.",
            anchor="w",
            justify="left",
            wraplength=315,
            font=("Segoe UI", 9),
        ).grid(row=3, column=0, columnspan=2, sticky="ew", padx=2, pady=(5, 0))

        self.ai_output_box = tk.LabelFrame(
            parent, text="Experimental path comparison", font=FONT_BOLD,
            padx=7, pady=7, bd=1, relief="solid",
        )
        for index, (label, key, unit) in enumerate((
            ("Geometric centerline", "baseline", "s"),
            ("Best tested AI path", "candidate", "s"),
            ("Candidate − centerline", "difference", "s"),
            ("Selected path length", "length", "m"),
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
            "The course is a historical team endurance recording. The Prius "
            "uses an idealized front-drive power source and assumed tire, drag, "
            "and battery values. TREV working profiles contain partial source "
            "inputs; unspecified parameters inherit the repository model. "
            "Lap-time differences are scenario sensitivity, not measured performance.",
            parent=self.root,
        )

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

        audit = self.course_geometry_audit
        if audit.cells_with_chord_excess:
            tk.Label(
                plot_box,
                text=(
                    f"Course data mismatch: {audit.cells_with_chord_excess:,} map "
                    f"segments exceed their assigned travel distance "
                    f"({audit.total_chord_excess_m:.1f} m combined excess). "
                    "The source map is a visual reference; default lap physics "
                    "uses its separate distance and curvature data."
                ),
                anchor="w", justify="left", wraplength=780, font=("Segoe UI", 9),
            ).grid(row=1, column=0, sticky="ew", pady=(0, 5))

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
            tk.Label(box, text=title, font=("Segoe UI", 8)).pack(anchor="w")
            tk.Label(
                box, textvariable=self.driver_values[key], font=("Consolas", 12),
                anchor="w",
            ).pack(anchor="w")
        tk.Label(
            parent,
            text=(
                "Reference-map playback: position and heading come from the "
                "distance-aligned x/y map; speed and lateral g come from the "
                "solved run. The physics uses a separate curvature channel. "
                "This is not a tracked vehicle pose or first-person camera."
            ),
            justify="left",
            anchor="w",
            wraplength=820,
            font=("Segoe UI", 9),
        ).grid(row=5, column=0, sticky="ew", pady=(2, 3))

    def _build_timed_sessions_tab(self, parent: tk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
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
                "records. Interactive driving, a live ghost, controller versions, "
                "complete session capture, and an end-to-end replay gate are not "
                "implemented in this tab yet."
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

    def _set_driver_run(
        self, name: str, result: Any, *, driving_mode: str = "Centerline",
        path_track: Any = None,
    ) -> None:
        """Load a solved lap for lightweight, station-aligned map playback.

        ``path_track`` lets another controller supply its own displayed x/y
        geometry.  The result must have aligned time, distance, speed and
        lateral-acceleration telemetry.  This does not synthesize a pose from
        the vehicle dynamics.
        """

        self._pause_driver_playback()
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
            if self.driver_play_button is not None:
                self.driver_play_button.configure(state="disabled")
            self._draw_driver_view()
            return
        self.driver_run_label.set(f"{driving_mode} · {name}")
        if self.driver_play_button is not None:
            self.driver_play_button.configure(state="normal")
        self._render_driver_frame()

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
            self._driver_after_id = self.root.after(50, self._driver_tick)

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
        self.driver_values["time"].set(f"{frame.time_s:.2f} / {playback.duration_s:.2f}")
        self.driver_values["distance"].set(
            f"{frame.distance_m:.1f} / {playback.track.length_m:.1f}"
        )
        self.driver_values["speed"].set(f"{frame.speed_mps * 3.6:.1f}")
        self.driver_values["lateral"].set(
            f"{frame.lateral_acceleration_mps2 / 9.80665:+.2f}"
        )
        self.driver_values["heading"].set(
            f"{float(np.degrees(frame.course_heading_rad)):+.1f}"
        )
        self._driver_updating_scale = True
        self.driver_progress_var.set(
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
        playback = self.driver_playback
        if playback is None:
            canvas.create_text(
                width / 2, height / 2,
                text="Run a lap, then play its distance-aligned map view",
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
            canvas.create_line(*coords, fill=foreground, width=2, smooth=False)
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
            width - 12, 12, text="MAP LINE ONLY", anchor="ne", fill=foreground,
            font=("Consolas", 9),
        )
        canvas.create_text(
            12, height - 12,
            text=f"Look-ahead {ahead_m:.0f} m · wheel to zoom",
            anchor="sw", fill=foreground, font=("Consolas", 9),
        )

    def _theme_colors(self) -> tuple[str, str]:
        return ("#000000", "#ffffff") if self.is_dark.get() else ("#ffffff", "#000000")

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
                label="Source map",
            )
            self.course_ax.plot(
                selected_x, selected_y, color=foreground, linewidth=1.7,
                label="Selected model path",
            )
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
            (f"Top-down source map · {self.track.length_m:.0f} m"
             if self._selected_path_track is None else
             f"Top-down model path · {self._selected_path_track.length_m:.0f} m"),
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

    def _read_run_settings(self) -> tuple[float, float]:
        try:
            torque_fraction = float(self.inputs["torque_request_percent"].get()) / 100.0
            solver_step_m = float(self.inputs["solver_step_m"].get())
        except ValueError as error:
            raise ValueError("Enter numeric driver request and solver step values.") from error
        if not np.isfinite(torque_fraction) or not 0.0 <= torque_fraction <= 1.0:
            raise ValueError("Driver request must be between 0 and 100%.")
        if not np.isfinite(solver_step_m) or not 0.0 < solver_step_m <= self.track.length_m:
            raise ValueError("Solver step must be finite and within the course length.")
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
        if not self._ai_mode_selected() and self.ai_output_box is not None:
            self.ai_output_box.pack_forget()

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
        self.compare_button.configure(state=state)
        self.profile_menu.configure(state=state)
        self.compare_a_menu.configure(state=state)
        self.compare_b_menu.configure(state=state)
        self.save_profile_button.configure(state=state)
        self.delete_profile_button.configure(state=state)
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
        track_id: str = "team_endurance_fused_gnss_imu",
        path_planning: dict[str, Any] | None = None,
    ) -> str:
        """Persist the exact effective setup and aligned lap telemetry."""

        settings = LapRunSettings.from_track(
            solver_track,
            track_id=track_id,
            solver_step_m=step_m,
            solver_settings=path_solver_settings(vehicle),
            torque_request_fraction=torque_fraction,
            endurance_config=endurance_run_config(vehicle),
            profile_id=profile_id,
            profile_label=profile_name,
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

    def _start_run(self) -> None:
        if self.run_in_progress:
            return
        try:
            setup, step_m, torque_fraction = self._read_run_inputs()
            ai_assumptions = self._read_ai_assumptions() if self._ai_mode_selected() else None
        except ValueError as error:
            messagebox.showerror("Check vehicle inputs", str(error), parent=self.root)
            return
        profile_id = self.profile_display_to_id[self.profile_var.get()]
        profile_name = self.profile_id_to_display[profile_id]
        if ai_assumptions is not None:
            self._path_comparison = None
            if self.ai_compare_button is not None:
                self.ai_compare_button.configure(state="disabled")
        self._set_busy(True)
        self.run_started_at = time.perf_counter()
        self.status_text.set(
            f"Calculating {profile_name}"
            + (" with experimental AI path…" if ai_assumptions else f" at {step_m:g} m spacing…")
        )
        worker = threading.Thread(
            target=self._calculate_ai_single if ai_assumptions else self._calculate_single,
            args=(profile_id, profile_name, setup, step_m, torque_fraction)
                 + ((ai_assumptions,) if ai_assumptions else ()),
            daemon=True,
        )
        worker.start()

    def _start_comparison(self) -> None:
        if self.run_in_progress:
            return
        try:
            torque_fraction, step_m = self._read_run_settings()
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
        self._set_busy(True)
        self.run_started_at = time.perf_counter()
        self.status_text.set(
            f"Comparing two cars on the same course at {step_m:g} m spacing…"
        )
        threading.Thread(
            target=self._calculate_comparison,
            args=(tuple(plans), step_m, torque_fraction),
            daemon=True,
        ).start()

    def _calculate_single(
        self,
        profile_id: str,
        profile_name: str,
        setup: VehicleSetup | None,
        step_m: float,
        torque_fraction: float,
    ) -> None:
        try:
            solver_track = resample_track(self.track, maximum_cell_length_m=step_m)
            vehicle, manifest = self._vehicle_for_profile(profile_id, setup)
            result = run_one_lap(
                vehicle,
                solver_track,
                torque_request_fraction=torque_fraction,
            )
            if result.completed:
                summarize_lap(result, self.track.length_m)
            run_id = self._save_run_record(
                result=result, vehicle=vehicle, manifest=manifest,
                solver_track=solver_track, profile_id=profile_id,
                profile_name=profile_name, setup=setup, step_m=step_m,
                torque_fraction=torque_fraction,
            )
            self.result_queue.put(
                ("single", (profile_name, step_m, result, run_id), None)
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
    ) -> None:
        """Compare geometry-derived paths without changing the default lap."""

        try:
            # Lazy import keeps the centerline button free of optimization work.
            from lapsim.optimization.racing_line import (
                RacingLinePlanner, TrackCorridor, compare_lines_with_lap_model,
            )

            half_width_m, vehicle_width_m, safety_margin_m = assumptions
            vehicle, manifest = self._vehicle_for_profile(profile_id, setup)
            corridor = TrackCorridor.constant(
                self.track,
                left_width_m=half_width_m,
                right_width_m=half_width_m,
                vehicle_width_m=vehicle_width_m,
                safety_margin_m=safety_margin_m,
                source="user-assumed uniform half-width; no surveyed boundaries",
            )
            planner = RacingLinePlanner()
            plan = planner.plan(self.track, corridor)
            comparison = compare_lines_with_lap_model(
                vehicle, plan, torque_request_fraction=torque_fraction,
            )
            selected_mode = comparison.selected_mode
            selected_run = comparison.selected_run
            selected_track = comparison.selected_track
            baseline_valid = comparison.baseline_time_s is not None
            if (
                not baseline_valid
                and comparison.candidate_run is not None
                and comparison.candidate_run.completed
            ):
                # Show the completed candidate, but never call it a time gain.
                selected_mode = "candidate_only_baseline_failed"
                selected_run = comparison.candidate_run
                selected_track = comparison.candidate_track
            if selected_run is None:
                # Preserve a failed attempt for diagnosis when the simulator
                # returned a run object for at least one path.
                selected_run = comparison.baseline_run or comparison.candidate_run
                selected_track = (
                    plan.baseline_track if comparison.baseline_run is not None
                    else comparison.candidate_track
                )
                selected_mode = "no_completed_path"
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
            path_planning = {
                "mode": "experimental_racing_line",
                "algorithm": "periodic_cubic_minimum_curvature_slsqp_v2_bounded_strength",
                "selected_mode": selected_mode,
                "candidate_offset_strength": comparison.candidate_strength,
                "selected_offset_strength": (
                    comparison.candidate_strength
                    if selected_mode.startswith("candidate")
                    else 0.0 if selected_mode == "centerline" else None
                ),
                "candidate_trials": [
                    {
                        "offset_strength": trial.strength,
                        "path_length_m": trial.path_length_m,
                        "lap_time_s": trial.lap_time_s,
                        "error": trial.error,
                    }
                    for trial in comparison.trials
                ],
                "comparison_is_valid": (
                    baseline_valid and comparison.candidate_time_s is not None
                ),
                "source_geometry_sha256": source_hash,
                "user_requested_centerline_step_m": step_m,
                "planner_sample_spacing_m": planner.sample_spacing_m,
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
                "baseline_error": comparison.baseline_error,
                "candidate_error": comparison.candidate_error,
                "baseline_length_m": plan.baseline_track.length_m,
                "candidate_length_m": comparison.candidate_track.length_m,
                "max_abs_offset_m": plan.max_abs_offset_m,
                "selected_max_abs_offset_m": (
                    plan.max_abs_offset_m * comparison.candidate_strength
                    if selected_mode.startswith("candidate")
                    and comparison.candidate_strength is not None
                    else 0.0 if selected_mode == "centerline" else None
                ),
                "max_constraint_violation_m": plan.max_constraint_violation_m,
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
            run_id = self._save_run_record(
                result=selected_run, vehicle=vehicle, manifest=manifest,
                solver_track=selected_track, profile_id=profile_id,
                profile_name=profile_name, setup=setup,
                step_m=max(selected_track.cell_length_m),
                torque_fraction=torque_fraction,
                track_id="team_endurance_xy_derived_assumed_corridor",
                path_planning=path_planning,
            )
            self.result_queue.put((
                "ai_single",
                (profile_name, selected_run, selected_track, selected_mode,
                 plan, comparison, assumptions, run_id),
                None,
            ))
        except Exception as error:
            self.result_queue.put(("ai_single", None, error))

    def _calculate_comparison(
        self,
        plans: tuple[tuple[str, str, VehicleSetup | None], ...],
        step_m: float,
        torque_fraction: float,
    ) -> None:
        try:
            solver_track = resample_track(self.track, maximum_cell_length_m=step_m)
            outcomes = []
            run_ids = []
            for profile_id, name, setup in plans:
                vehicle, manifest = self._vehicle_for_profile(profile_id, setup)
                result = run_one_lap(
                    vehicle, solver_track, torque_request_fraction=torque_fraction
                )
                run_id = self._save_run_record(
                    result=result, vehicle=vehicle, manifest=manifest,
                    solver_track=solver_track, profile_id=profile_id,
                    profile_name=name, setup=setup, step_m=step_m,
                    torque_fraction=torque_fraction,
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
                "comparison", (step_m, torque_fraction, tuple(outcomes), tuple(run_ids)),
                None,
            ))
        except Exception as error:
            self.result_queue.put(("comparison", None, error))

    def _poll_result(self) -> None:
        try:
            kind, payload, error = self.result_queue.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_result)
            return

        self._set_busy(False)
        elapsed_s = time.perf_counter() - self.run_started_at
        if error is not None:
            self.status_text.set(f"Calculation failed: {error}")
            messagebox.showerror("Lap calculation failed", str(error), parent=self.root)
        elif kind == "single":
            profile_name, step_m, result, run_id = payload
            if result.completed:
                self._comparison_results = None
                self._last_result = result
                self._selected_path_track = None
                self._show_result(result)
                self._activate_driver_playback(profile_name, result)
                self.status_text.set(
                    f"{profile_name} completed in {elapsed_s:.1f} s · "
                    f"{step_m:g} m spacing · saved run {run_id[:12]}"
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
             plan, comparison, assumptions, run_id) = payload
            self._path_comparison = (plan, comparison, assumptions)
            if self.ai_compare_button is not None:
                self.ai_compare_button.configure(
                    state=("normal" if comparison.baseline_time_s is not None
                           and comparison.candidate_time_s is not None else "disabled")
                )
            if self.ai_output_box is not None and not self.ai_output_box.winfo_manager():
                self.ai_output_box.pack(fill="x", pady=(0, 8))
            baseline_time = comparison.baseline_time_s
            candidate_time = comparison.candidate_time_s
            values = {
                "baseline": f"{baseline_time:.3f}" if baseline_time is not None else "—",
                "candidate": f"{candidate_time:.3f}" if candidate_time is not None else "—",
                "difference": (
                    f"{candidate_time - baseline_time:+.3f}"
                    if baseline_time is not None and candidate_time is not None else "—"
                ),
                "length": f"{selected_track.length_m:.1f}",
            }
            for key, value in values.items():
                self.ai_output_values[key].configure(text=value)
            half_width_m, vehicle_width_m, margin_m = assumptions
            if selected_mode == "no_completed_path":
                selection = "Neither geometric path completed. A failed run was saved for diagnosis."
            elif selected_mode == "candidate":
                selection = (
                    f"Faster AI path selected at {comparison.candidate_strength:g}× "
                    "of the proposed offset."
                )
            elif selected_mode == "candidate_only_baseline_failed":
                selection = (
                    f"AI path at {comparison.candidate_strength:g}× offset completed; "
                    "geometric centerline failed, so no time gain is established."
                )
            elif candidate_time is not None:
                selection = "Best tested AI path was slower; geometric centerline selected."
            else:
                selection = "No completed faster AI candidate; geometric centerline selected."
            self.ai_result_text.set(
                f"{selection} Assumed ±{half_width_m:g} m corridor, "
                f"{vehicle_width_m:g} m car, {margin_m:g} m margin. "
                f"Proposed max offset {plan.max_abs_offset_m:.2f} m; "
                f"{len(comparison.trials)} candidate trial(s). "
                f"source map length differs by {plan.source_vs_processed_length_fraction:+.1%}. "
                "Compare only the two times in this box; the default lap uses "
                "different source curvature. These are assumed model scenarios."
            )
            if result.completed:
                self._selected_path_track = selected_track
                self._last_result = result
                runs = []
                if comparison.baseline_run is not None and comparison.baseline_run.completed:
                    runs.append(("Geometric centerline", comparison.baseline_run))
                if comparison.candidate_run is not None and comparison.candidate_run.completed:
                    runs.append(("Best tested AI path", comparison.candidate_run))
                self._comparison_results = tuple(runs) if len(runs) == 2 else None
                self._show_result(result, track_length_m=selected_track.length_m)
                self._activate_driver_playback(
                    profile_name, result,
                    driving_mode=("AI path" if selected_mode.startswith("candidate")
                                  else "Geometric centerline"),
                    path_track=selected_track,
                )
                self.status_text.set(
                    f"Experimental path calculation: {selection} "
                    f"{elapsed_s:.1f} s · saved run {run_id[:12]}"
                )
            else:
                detail = comparison.baseline_error or result.failure_reason
                self.status_text.set(
                    f"Experimental path did not complete: {detail} · saved run {run_id[:12]}"
                )
                messagebox.showerror("Lap did not complete", str(detail), parent=self.root)
        else:
            step_m, torque_fraction, outcomes, run_ids = payload
            self._comparison_results = outcomes
            self._last_result = outcomes[0][1]
            self._selected_path_track = None
            self._show_result(outcomes[0][1])
            self._set_driver_run(outcomes[0][0], outcomes[0][1])
            self._show_comparison(outcomes, step_m, torque_fraction, run_ids)
            self.status_text.set(
                f"Comparison completed in {elapsed_s:.1f} s · "
                f"saved A {run_ids[0][:10]}, B {run_ids[1][:10]}"
            )
        self.root.after(100, self._poll_result)

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
        }
        for key, value in values.items():
            self.output_values[key].configure(text=value)
        self._draw_plots(preserve_course_view=True)

    def _show_path_comparison(self) -> None:
        if self._path_comparison is None:
            return
        plan, comparison, assumptions = self._path_comparison
        if (
            comparison.baseline_run is None or not comparison.baseline_run.completed
            or comparison.candidate_run is None or not comparison.candidate_run.completed
        ):
            return
        baseline = summarize_lap(
            comparison.baseline_run, plan.baseline_track.length_m
        )
        candidate = summarize_lap(
            comparison.candidate_run, comparison.candidate_track.length_m
        )
        window = tk.Toplevel(self.root)
        window.title("LapSim path comparison")
        window.geometry("800x440")
        body = tk.Frame(window, padx=12, pady=12)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="Experimental path comparison", font=FONT_TITLE).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 5)
        )
        tk.Label(
            body,
            text=(f"One car, one geometric source, assumed ±{assumptions[0]:g} m "
                  f"corridor. Best tested AI path uses {comparison.candidate_strength:g}× "
                  "proposed offset. Candidate − centerline; negative lap-time Δ is faster."),
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
        for column in range(4):
            body.grid_columnconfigure(column, weight=1)
        tk.Label(
            body,
            text=("Widths and vehicle envelope are assumptions. The source x/y map "
                  "and recorded curvature disagree; these times are comparable model "
                  "scenarios, not validated Terps lap predictions."),
            anchor="w", justify="left", wraplength=755,
        ).grid(row=9, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        self._apply_theme()

    def _show_comparison(
        self, outcomes: tuple[tuple[str, Any], ...], step_m: float,
        torque_fraction: float, run_ids: tuple[str, ...],
    ) -> None:
        first_name, first_result = outcomes[0]
        second_name, second_result = outcomes[1]
        first = summarize_lap(first_result, self.track.length_m)
        second = summarize_lap(second_result, self.track.length_m)
        window = tk.Toplevel(self.root)
        window.title("LapSim car comparison")
        window.geometry("760x490")
        box = tk.Frame(window, padx=12, pady=12)
        box.pack(fill="both", expand=True)
        tk.Label(box, text="Same course and run settings", font=FONT_TITLE).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 5)
        )
        tk.Label(
            box,
            text=f"Solver step: {step_m:g} m · driver request: "
                 f"{torque_fraction * 100:g}% · "
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
        for column in range(4):
            box.grid_columnconfigure(column, weight=1)
        tk.Label(
            box,
            text="*Equivalent pack-model energy. These are model comparisons, not "
                 "validated vehicle performance or measured energy use.",
            anchor="w", justify="left", wraplength=720,
        ).grid(row=9, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        tk.Label(
            box,
            text=f"Saved records: A {run_ids[0][:16]} · B {run_ids[1][:16]}",
            anchor="w", font=("Consolas", 9),
        ).grid(row=10, column=0, columnspan=4, sticky="ew", pady=(5, 0))
        self._apply_theme()


def main() -> None:
    root = tk.Tk()
    LapSimDesktop(root)
    root.mainloop()
