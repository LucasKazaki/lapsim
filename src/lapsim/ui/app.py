"""Native, monochrome desktop interface for the LapSim model."""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import Any

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from lapsim.profiles import build_vehicle, browse_records, list_profiles

from .comparison import summarize_lap
from .garage import CAR_INPUT_KEYS, ProfileStore, SavedCarProfile
from .presets import VehicleSetup, make_prius_benchmark
from .simulation import load_team_endurance_track, resample_track, run_one_lap


FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 16, "bold")


class LapSimDesktop:
    """Build the Tk desktop application around the shared physics APIs."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("LapSim — Formula SAE Lap Simulator")
        self.root.geometry("1380x900")
        self.root.minsize(1080, 720)

        self.track = load_team_endurance_track()
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
        self.compare_a_var = tk.StringVar()
        self.compare_b_var = tk.StringVar()
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
        self._build_comparison(right)
        self._build_plot(right)

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
            box, text="Comparisons use saved profile values. Save any edits first.",
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
        plot_box.grid_rowconfigure(1, weight=1)

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
        tk.Label(
            controls,
            text="Drag to pan · mouse wheel to zoom",
            anchor="e",
        ).pack(side="right", padx=4)

        self.figure = Figure(figsize=(9.0, 6.5), dpi=100, constrained_layout=True)
        self.course_ax = self.figure.add_subplot(2, 1, 1)
        self.speed_ax = self.figure.add_subplot(2, 1, 2)
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_box)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=1, column=0, sticky="nsew")
        self.canvas.mpl_connect("button_press_event", self._pan_start)
        self.canvas.mpl_connect("motion_notify_event", self._pan_move)
        self.canvas.mpl_connect("button_release_event", self._pan_end)
        self.canvas.mpl_connect("scroll_event", self._wheel_zoom)
        self._draw_plots()

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
                options["selectcolor"] = background
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
        self._draw_plots(preserve_course_view=True)

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
        self.course_ax.plot(x, y, color=foreground, linewidth=1.4)
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
            f"Top-down course · {self.track.length_m:.0f} m",
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

        if self._comparison_results is not None:
            for (name, result), line_style in zip(
                self._comparison_results, ("-", "--"), strict=True
            ):
                distance_m = np.asarray(
                    result.telemetry["vehicle.distance_m"], dtype=float
                )
                speed_kph = (
                    np.asarray(result.telemetry["vehicle.speed_mps"], dtype=float)
                    * 3.6
                )
                self.speed_ax.plot(
                    distance_m, speed_kph, color=foreground,
                    linestyle=line_style, linewidth=1.2, label=name,
                )
            self.speed_ax.legend(
                frameon=False, labelcolor=foreground, facecolor=background,
                fontsize=8,
            )
            self.speed_ax.set_title(
                "Speed by distance · comparison", color=foreground,
                loc="left", fontsize=11,
            )
        elif self._last_result is not None and self._last_result.telemetry is not None:
            distance_m = np.asarray(
                self._last_result.telemetry["vehicle.distance_m"], dtype=float
            )
            speed_kph = (
                np.asarray(self._last_result.telemetry["vehicle.speed_mps"], dtype=float)
                * 3.6
            )
            self.speed_ax.plot(distance_m, speed_kph, color=foreground, linewidth=1.2)
            self.speed_ax.set_title("Speed by distance", color=foreground, loc="left", fontsize=11)
        else:
            self.speed_ax.text(
                0.5,
                0.5,
                "Run one lap to display the speed trace",
                color=foreground,
                ha="center",
                va="center",
                transform=self.speed_ax.transAxes,
            )
            self.speed_ax.set_title("Speed by distance", color=foreground, loc="left", fontsize=11)
        self.speed_ax.set_xlabel("Distance (m)", color=foreground, fontsize=9)
        self.speed_ax.set_ylabel("Speed (km/h)", color=foreground, fontsize=9)
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
        editable = (
            self.profile_display_to_id.get(self.profile_var.get()) == "prius_2026_le"
            or self.profile_display_to_id.get(self.profile_var.get()) in self.saved_profiles
        )
        for key, entry in self.entry_by_key.items():
            entry.configure(
                state="disabled" if busy or (key in CAR_INPUT_KEYS and not editable) else "normal"
            )

    def _vehicle_for_profile(
        self, profile_id: str, setup: VehicleSetup | None
    ) -> Any:
        if profile_id == "prius_2026_le" or profile_id.startswith("user:"):
            if setup is None:
                raise ValueError("A saved Prius setup is required")
            return make_prius_benchmark(setup)
        vehicle, _manifest = build_vehicle(profile_id)
        return vehicle

    def _start_run(self) -> None:
        if self.run_in_progress:
            return
        try:
            setup, step_m, torque_fraction = self._read_run_inputs()
        except ValueError as error:
            messagebox.showerror("Check vehicle inputs", str(error), parent=self.root)
            return
        profile_id = self.profile_display_to_id[self.profile_var.get()]
        profile_name = self.profile_id_to_display[profile_id]
        self._set_busy(True)
        self.run_started_at = time.perf_counter()
        self.status_text.set(
            f"Calculating {profile_name} at {step_m:g} m spacing…"
        )
        worker = threading.Thread(
            target=self._calculate_single,
            args=(profile_id, profile_name, setup, step_m, torque_fraction),
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
            vehicle = self._vehicle_for_profile(profile_id, setup)
            result = run_one_lap(
                vehicle,
                solver_track,
                torque_request_fraction=torque_fraction,
            )
            if result.completed:
                summarize_lap(result, self.track.length_m)
            self.result_queue.put(("single", (profile_name, step_m, result), None))
        except Exception as error:
            self.result_queue.put(("single", None, error))

    def _calculate_comparison(
        self,
        plans: tuple[tuple[str, str, VehicleSetup | None], ...],
        step_m: float,
        torque_fraction: float,
    ) -> None:
        try:
            solver_track = resample_track(self.track, maximum_cell_length_m=step_m)
            outcomes = []
            for profile_id, name, setup in plans:
                vehicle = self._vehicle_for_profile(profile_id, setup)
                result = run_one_lap(
                    vehicle, solver_track, torque_request_fraction=torque_fraction
                )
                if not result.completed:
                    raise ValueError(f"{name} did not complete: {result.failure_reason}")
                summarize_lap(result, self.track.length_m)
                outcomes.append((name, result))
            self.result_queue.put(("comparison", (step_m, tuple(outcomes)), None))
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
            profile_name, step_m, result = payload
            if result.completed:
                self._comparison_results = None
                self._last_result = result
                self._show_result(result)
                self.status_text.set(
                    f"{profile_name} completed in {elapsed_s:.1f} s · {step_m:g} m spacing"
                )
            else:
                self.status_text.set(f"Lap did not complete: {result.failure_reason}")
                messagebox.showerror(
                    "Lap did not complete", str(result.failure_reason), parent=self.root
                )
        else:
            step_m, outcomes = payload
            self._comparison_results = outcomes
            self._last_result = outcomes[0][1]
            self._show_result(outcomes[0][1])
            self._show_comparison(outcomes, step_m)
            self.status_text.set(
                f"Comparison completed in {elapsed_s:.1f} s · {step_m:g} m spacing"
            )
        self.root.after(100, self._poll_result)

    def _show_result(self, result: Any) -> None:
        summary = summarize_lap(result, self.track.length_m)
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

    def _show_comparison(
        self, outcomes: tuple[tuple[str, Any], ...], step_m: float
    ) -> None:
        first_name, first_result = outcomes[0]
        second_name, second_result = outcomes[1]
        first = summarize_lap(first_result, self.track.length_m)
        second = summarize_lap(second_result, self.track.length_m)
        window = tk.Toplevel(self.root)
        window.title("LapSim car comparison")
        window.geometry("760x460")
        box = tk.Frame(window, padx=12, pady=12)
        box.pack(fill="both", expand=True)
        tk.Label(box, text="Same course and run settings", font=FONT_TITLE).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 5)
        )
        tk.Label(
            box,
            text=f"Solver step: {step_m:g} m · driver request: "
                 f"{self.inputs['torque_request_percent'].get()}% · "
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
        self._apply_theme()


def main() -> None:
    root = tk.Tk()
    LapSimDesktop(root)
    root.mainloop()
