"""Top-down, synthetic four-wheel maneuver comparison for the desktop app."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import dataclass, field
from math import degrees, isfinite, radians
from tkinter import messagebox
from typing import Any

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from lapsim.dynamics import (
    PlanarControls,
    PlanarEnvironment,
    PlanarRoad,
    PlanarRun,
    PlanarState,
    PlanarVehicleConfig,
    RectangularGripPatch,
    evaluate_planar_dynamics,
    run_planar_dynamics,
)
from lapsim.experiments.dynamics_record import (
    capture_dynamics_comparison,
    default_dynamics_run_directory,
)


SYNTHETIC_CONFIG = {
    "mass_kg": 300.0,
    "yaw_inertia_kgm2": 160.0,
    "cg_to_front_axle_m": 0.8,
    "cg_to_rear_axle_m": 0.8,
    "front_track_m": 1.2,
    "rear_track_m": 1.2,
    "wheel_radius_m": 0.2,
    "wheel_inertia_kgm2": 0.3,
    "tire_mu": 1.5,
    "longitudinal_stiffness_n_per_slip": 7000.0,
    "cornering_stiffness_n_per_rad": 8000.0,
}
WHEEL_ABBREVIATIONS = ("FL", "FR", "RL", "RR")
FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")


@dataclass(frozen=True, slots=True)
class ManeuverSettings:
    config: PlanarVehicleConfig
    initial_speed_mps: float
    steering_angle_rad: float
    duration_s: float
    output_step_s: float
    torque_a_nm: tuple[float, float, float, float]
    torque_b_nm: tuple[float, float, float, float]
    equal_total_required: bool = True
    environment: PlanarEnvironment = field(default_factory=PlanarEnvironment)

    def __post_init__(self) -> None:
        if not isinstance(self.config, PlanarVehicleConfig):
            raise ValueError("config must be PlanarVehicleConfig")
        if not isinstance(self.environment, PlanarEnvironment):
            raise ValueError("environment must be PlanarEnvironment")
        if not all(
            isfinite(value)
            for value in (
                self.initial_speed_mps,
                self.steering_angle_rad,
                self.duration_s,
                self.output_step_s,
                *self.torque_a_nm,
                *self.torque_b_nm,
            )
        ):
            raise ValueError("Maneuver inputs must be finite")
        if not 0.0 <= self.initial_speed_mps <= 40.0:
            raise ValueError("Starting speed must be between 0 and 40 m/s")
        if abs(degrees(self.steering_angle_rad)) > 30.0:
            raise ValueError("Steering must be within ±30° for this synthetic study")
        if not 0.0 < self.duration_s <= 10.0:
            raise ValueError("Duration must be greater than 0 and at most 10 s")
        if not 0.002 <= self.output_step_s <= 0.1:
            raise ValueError("Output step must be between 0.002 and 0.1 s")
        if any(abs(value) > 500.0 for value in (*self.torque_a_nm, *self.torque_b_nm)):
            raise ValueError("Each wheel torque must be within ±500 Nm")
        count = self.duration_s / self.output_step_s
        if not 1 <= round(count) <= 2000 or abs(count - round(count)) > 1e-8:
            raise ValueError("Duration must be an exact multiple of step, from 1 to 2000 steps")
        if self.equal_total_required and abs(sum(self.torque_a_nm) - sum(self.torque_b_nm)) > 1e-9:
            raise ValueError("A and B must have equal total wheel torque")

    @property
    def step_count(self) -> int:
        return round(self.duration_s / self.output_step_s)

    def controls(self, scenario: str) -> PlanarControls:
        if scenario not in {"A", "B"}:
            raise ValueError("scenario must be A or B")
        torques = self.torque_a_nm if scenario == "A" else self.torque_b_nm
        return PlanarControls(
            steering_angles_rad=(
                self.steering_angle_rad,
                self.steering_angle_rad,
                0.0,
                0.0,
            ),
            drive_torques_nm=torques,
        )


def run_maneuver_pair(settings: ManeuverSettings) -> tuple[PlanarRun, PlanarRun]:
    """Run the same synthetic car/steering maneuver with two torque vectors."""

    starting_wheel_speed = settings.initial_speed_mps / settings.config.wheel_radius_m
    initial_state = PlanarState(
        u_mps=settings.initial_speed_mps,
        wheel_speeds_rad_s=(starting_wheel_speed,) * 4,
    )
    runs = []
    for scenario in ("A", "B"):
        controls = settings.controls(scenario)
        runs.append(
            run_planar_dynamics(
                settings.config,
                initial_state,
                (controls,) * settings.step_count,
                settings.output_step_s,
                environment=settings.environment,
            )
        )
    return runs[0], runs[1]


class DynamicsLab:
    """A small desktop workspace for inspectable four-wheel dynamics studies."""

    def __init__(self, parent: tk.Tk, *, dark: bool = False) -> None:
        self.window = tk.Toplevel(parent)
        self.window.title("LapSim · Four-wheel dynamics lab")
        self.window.geometry("1380x870")
        self.window.minsize(1120, 720)
        self.is_dark = tk.BooleanVar(value=dark)
        self.config_vars = {
            key: tk.StringVar(value=f"{value:g}")
            for key, value in SYNTHETIC_CONFIG.items()
        }
        self.maneuver_vars = {
            "initial_speed_mps": tk.StringVar(value="12"),
            "steering_angle_deg": tk.StringVar(value="1"),
            "duration_s": tk.StringVar(value="1"),
            "output_step_s": tk.StringVar(value="0.01"),
        }
        default_torque = {
            "A": (0.0, 0.0, 120.0, 120.0),
            "B": (0.0, 0.0, 110.0, 130.0),
        }
        self.torque_vars = {
            scenario: tuple(tk.StringVar(value=f"{value:g}") for value in values)
            for scenario, values in default_torque.items()
        }
        self.equal_total = tk.BooleanVar(value=True)
        self.environment_vars = {
            "wind_world_x_mps": tk.StringVar(value="0"),
            "wind_world_y_mps": tk.StringVar(value="0"),
            "air_density_kgpm3": tk.StringVar(value="1.225"),
            "drag_area_m2": tk.StringVar(value="0.8"),
            "base_friction_multiplier": tk.StringVar(value="1"),
            "x_min_m": tk.StringVar(value="4"),
            "x_max_m": tk.StringVar(value="9"),
            "y_min_m": tk.StringVar(value="-1.5"),
            "y_max_m": tk.StringVar(value="0"),
            "patch_friction_multiplier": tk.StringVar(value="0.6"),
        }
        self.patch_enabled = tk.BooleanVar(value=False)
        self.inspected_scenario = tk.StringVar(value="A")
        self.status = tk.StringVar(value="Ready · synthetic model, not a team-car calibration")
        self.result_queue: queue.Queue[
            tuple[
                ManeuverSettings | None,
                tuple[PlanarRun, PlanarRun] | None,
                str | None,
                BaseException | None,
            ]
        ] = queue.Queue()
        self.settings: ManeuverSettings | None = None
        self.runs: tuple[PlanarRun, PlanarRun] | None = None
        self.figure: Figure | None = None
        self.canvas: FigureCanvasTkAgg | None = None
        self._build_window()
        self._apply_theme()
        self.window.after(100, self._poll_result)

    def _build_window(self) -> None:
        header = tk.Frame(self.window, padx=10, pady=8)
        header.pack(fill="x")
        tk.Label(
            header, text="Four-wheel dynamics lab", font=("Segoe UI", 16, "bold")
        ).pack(side="left")
        tk.Label(
            header, text="SYNTHETIC MANEUVER · A/B TORQUE ALLOCATION",
            font=("Segoe UI", 9), padx=12,
        ).pack(side="left", anchor="s", pady=3)
        tk.Checkbutton(
            header, text="Dark mode", variable=self.is_dark,
            command=self._apply_theme, font=FONT,
        ).pack(side="right")

        body = tk.Frame(self.window, padx=10, pady=4)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        sidebar = tk.Frame(body, width=340)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(0, weight=1)
        sidebar.grid_columnconfigure(0, weight=1)
        scroll_canvas = tk.Canvas(sidebar, highlightthickness=0, bd=0)
        scroll_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(sidebar, orient="vertical", command=scroll_canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        scroll_canvas.configure(yscrollcommand=scrollbar.set)
        panel = tk.Frame(scroll_canvas)
        panel_id = scroll_canvas.create_window((0, 0), window=panel, anchor="nw")
        panel.bind(
            "<Configure>",
            lambda _event: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all")),
        )
        scroll_canvas.bind(
            "<Configure>",
            lambda event: scroll_canvas.itemconfigure(panel_id, width=event.width),
        )
        self._build_inputs(panel)
        for widget in (scroll_canvas, panel, *self._walk_widgets(panel)):
            widget.bind(
                "<MouseWheel>",
                lambda event: scroll_canvas.yview_scroll(-int(event.delta / 120), "units"),
            )
        plot_frame = tk.Frame(body)
        plot_frame.grid(row=0, column=1, sticky="nsew")
        plot_frame.grid_rowconfigure(1, weight=1)
        plot_frame.grid_columnconfigure(0, weight=1)
        toolbar = tk.Frame(plot_frame)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        tk.Label(toolbar, text="Inspect car").pack(side="left")
        self.scenario_menu = tk.OptionMenu(
            toolbar, self.inspected_scenario, "A", "B",
            command=lambda _value: self._draw_results(),
        )
        self.scenario_menu.configure(width=5, relief="raised", bd=1)
        self.scenario_menu.pack(side="left", padx=5)
        tk.Label(
            toolbar, text="Slide time cursor to inspect wheel forces and slip",
        ).pack(side="left", padx=8)
        self.figure = Figure(figsize=(9.4, 6.8), dpi=100, constrained_layout=True)
        self.ax_path = self.figure.add_subplot(2, 2, 1)
        self.ax_yaw = self.figure.add_subplot(2, 2, 2)
        self.ax_slip = self.figure.add_subplot(2, 2, 3)
        self.ax_car = self.figure.add_subplot(2, 2, 4)
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas.get_tk_widget().grid(row=1, column=0, sticky="nsew")
        self.time_index = tk.IntVar(value=0)
        self.time_scale = tk.Scale(
            plot_frame, from_=0, to=1, orient="horizontal",
            variable=self.time_index, command=lambda _value: self._draw_results(),
            showvalue=False, label="Time cursor",
        )
        self.time_scale.grid(row=2, column=0, sticky="ew")
        metrics = tk.LabelFrame(
            plot_frame, text="Selected car at cursor", font=FONT_BOLD,
            padx=6, pady=5, bd=1, relief="solid",
        )
        metrics.grid(row=3, column=0, sticky="ew", pady=(3, 0))
        self.metric_values: dict[str, tk.StringVar] = {}
        for index, (key, label) in enumerate((
            ("time", "Time (s)"),
            ("forward", "Forward (m/s)"),
            ("lateral", "Leftward (m/s)"),
            ("heading", "Heading (deg)"),
            ("yaw", "Yaw rate (deg/s)"),
            ("moment", "Yaw moment (Nm)"),
            ("utilization", "Peak tire use (%)"),
            ("residual", "Power residual (W)"),
            ("airspeed", "Air speed (m/s)"),
            ("aero_x", "Aero Fx (N)"),
            ("aero_y", "Aero Fy (N)"),
            ("road", "Road coverage"),
        )):
            column = index % 4
            row = (index // 4) * 2
            tk.Label(metrics, text=label, font=("Segoe UI", 8)).grid(
                row=row, column=column, sticky="ew", padx=3,
            )
            value = tk.StringVar(value="—")
            self.metric_values[key] = value
            tk.Label(
                metrics, textvariable=value, relief="solid", bd=1,
                font=("Consolas", 10), padx=4, pady=2,
            ).grid(row=row + 1, column=column, sticky="ew", padx=3, pady=(0, 3))
            metrics.grid_columnconfigure(column, weight=1)
        self._draw_results()
        tk.Label(
            self.window,
            textvariable=self.status,
            anchor="w", padx=10, pady=5, font=("Segoe UI", 9),
        ).pack(fill="x")

    def _build_inputs(self, parent: tk.Widget) -> None:
        maneuver = tk.LabelFrame(
            parent, text="Maneuver", font=FONT_BOLD, padx=7, pady=6,
            bd=1, relief="solid",
        )
        maneuver.pack(fill="x", pady=(0, 8))
        labels = (
            ("Starting speed", "initial_speed_mps", "m/s"),
            ("Front steer", "steering_angle_deg", "deg"),
            ("Duration", "duration_s", "s"),
            ("Output step", "output_step_s", "s"),
        )
        for row, (label, key, unit) in enumerate(labels):
            tk.Label(maneuver, text=label, anchor="w").grid(row=row, column=0, sticky="w")
            tk.Entry(
                maneuver, textvariable=self.maneuver_vars[key], width=10,
                justify="right", relief="solid", bd=1,
            ).grid(row=row, column=1, sticky="ew", padx=5, pady=2)
            tk.Label(maneuver, text=unit, width=5, anchor="w").grid(
                row=row, column=2, sticky="w"
            )
        maneuver.grid_columnconfigure(1, weight=1)

        torques = tk.LabelFrame(
            parent, text="Wheel torque requests (Nm)", font=FONT_BOLD,
            padx=7, pady=6, bd=1, relief="solid",
        )
        torques.pack(fill="x", pady=(0, 8))
        for column, label in enumerate(("Wheel", "A", "B")):
            tk.Label(torques, text=label, font=FONT_BOLD).grid(
                row=0, column=column, sticky="ew", padx=3
            )
        for row, wheel in enumerate(WHEEL_ABBREVIATIONS, start=1):
            tk.Label(torques, text=wheel).grid(row=row, column=0, sticky="w", padx=3)
            for column, scenario in enumerate(("A", "B"), start=1):
                tk.Entry(
                    torques, textvariable=self.torque_vars[scenario][row - 1],
                    width=9, justify="right", relief="solid", bd=1,
                ).grid(row=row, column=column, sticky="ew", padx=3, pady=2)
        tk.Checkbutton(
            torques, text="Require equal total torque", variable=self.equal_total,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 0))
        torques.grid_columnconfigure(1, weight=1)
        torques.grid_columnconfigure(2, weight=1)

        environment = tk.LabelFrame(
            parent, text="Wind and road · synthetic", font=FONT_BOLD,
            padx=7, pady=6, bd=1, relief="solid",
        )
        environment.pack(fill="x", pady=(0, 8))
        condition_labels = (
            ("Wind world X", "wind_world_x_mps", "m/s"),
            ("Wind world Y", "wind_world_y_mps", "m/s"),
            ("Air density", "air_density_kgpm3", "kg/m³"),
            ("Drag area CdA", "drag_area_m2", "m²"),
            ("Base grip scale", "base_friction_multiplier", "×"),
        )
        for row, (label, key, unit) in enumerate(condition_labels):
            tk.Label(environment, text=label, anchor="w").grid(row=row, column=0, sticky="w")
            tk.Entry(
                environment, textvariable=self.environment_vars[key], width=9,
                justify="right", relief="solid", bd=1,
            ).grid(row=row, column=1, sticky="ew", padx=5, pady=2)
            tk.Label(environment, text=unit, width=7, anchor="w").grid(
                row=row, column=2, sticky="w",
            )
        tk.Checkbutton(
            environment, text="Enable low-grip rectangle", variable=self.patch_enabled,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 0))
        patch_labels = (
            ("Patch X min", "x_min_m", "m"),
            ("Patch X max", "x_max_m", "m"),
            ("Patch Y min", "y_min_m", "m"),
            ("Patch Y max", "y_max_m", "m"),
            ("Patch grip scale", "patch_friction_multiplier", "×"),
        )
        for row, (label, key, unit) in enumerate(patch_labels, start=6):
            tk.Label(environment, text=label, anchor="w").grid(row=row, column=0, sticky="w")
            tk.Entry(
                environment, textvariable=self.environment_vars[key], width=9,
                justify="right", relief="solid", bd=1,
            ).grid(row=row, column=1, sticky="ew", padx=5, pady=2)
            tk.Label(environment, text=unit, width=7, anchor="w").grid(
                row=row, column=2, sticky="w",
            )
        environment.grid_columnconfigure(1, weight=1)

        config = tk.LabelFrame(
            parent, text="Synthetic vehicle and tire", font=FONT_BOLD,
            padx=7, pady=6, bd=1, relief="solid",
        )
        config.pack(fill="x", pady=(0, 8))
        config_labels = (
            ("Mass", "mass_kg", "kg"),
            ("Yaw inertia", "yaw_inertia_kgm2", "kg·m²"),
            ("CG to front axle", "cg_to_front_axle_m", "m"),
            ("CG to rear axle", "cg_to_rear_axle_m", "m"),
            ("Front track", "front_track_m", "m"),
            ("Rear track", "rear_track_m", "m"),
            ("Wheel radius", "wheel_radius_m", "m"),
            ("Wheel inertia", "wheel_inertia_kgm2", "kg·m²"),
            ("Tire μ", "tire_mu", "—"),
            ("Longitudinal stiffness", "longitudinal_stiffness_n_per_slip", "N/slip"),
            ("Cornering stiffness", "cornering_stiffness_n_per_rad", "N/rad"),
        )
        for row, (label, key, unit) in enumerate(config_labels):
            tk.Label(config, text=label, anchor="w").grid(row=row, column=0, sticky="w")
            tk.Entry(
                config, textvariable=self.config_vars[key], width=9,
                justify="right", relief="solid", bd=1,
            ).grid(row=row, column=1, sticky="ew", padx=5, pady=2)
            tk.Label(config, text=unit, width=8, anchor="w").grid(
                row=row, column=2, sticky="w"
            )
        config.grid_columnconfigure(1, weight=1)
        self.run_button = tk.Button(
            parent, text="Compare A and B", command=self._start_run,
            font=FONT_BOLD, relief="raised", bd=1, pady=5,
        )
        self.run_button.pack(fill="x", pady=(0, 6))
        tk.Label(
            parent,
            text="Independent wheel spin and planar yaw. Constant static normal loads; "
                 "no motor, inverter, pack, suspension, load transfer, or measured "
                 "tire calibration. Synthetic results are for model checks only.",
            justify="left", anchor="w", wraplength=305, font=("Segoe UI", 9),
        ).pack(fill="x")

    def _read_settings(self) -> ManeuverSettings:
        try:
            config_values = {
                key: float(variable.get())
                for key, variable in self.config_vars.items()
            }
            maneuver_values = {
                key: float(variable.get())
                for key, variable in self.maneuver_vars.items()
            }
            torque_a = tuple(float(item.get()) for item in self.torque_vars["A"])
            torque_b = tuple(float(item.get()) for item in self.torque_vars["B"])
            environment_keys = (
                "wind_world_x_mps", "wind_world_y_mps", "air_density_kgpm3",
                "drag_area_m2", "base_friction_multiplier",
            )
            if self.patch_enabled.get():
                environment_keys += (
                    "x_min_m", "x_max_m", "y_min_m", "y_max_m",
                    "patch_friction_multiplier",
                )
            environment_values = {
                key: float(self.environment_vars[key].get())
                for key in environment_keys
            }
        except ValueError as error:
            raise ValueError("Enter a number in every maneuver, torque, car, wind, and road field") from error
        road_patches = ()
        if self.patch_enabled.get():
            road_patches = (RectangularGripPatch(
                x_min_m=environment_values["x_min_m"],
                x_max_m=environment_values["x_max_m"],
                y_min_m=environment_values["y_min_m"],
                y_max_m=environment_values["y_max_m"],
                friction_multiplier=environment_values["patch_friction_multiplier"],
                material_id="assumed_low_grip",
            ),)
        environment = PlanarEnvironment(
            wind_world_x_mps=environment_values["wind_world_x_mps"],
            wind_world_y_mps=environment_values["wind_world_y_mps"],
            air_density_kgpm3=environment_values["air_density_kgpm3"],
            drag_area_m2=environment_values["drag_area_m2"],
            road=PlanarRoad(
                base_friction_multiplier=environment_values["base_friction_multiplier"],
                patches=road_patches,
            ),
        )
        return ManeuverSettings(
            config=PlanarVehicleConfig(**config_values),
            initial_speed_mps=maneuver_values["initial_speed_mps"],
            steering_angle_rad=radians(maneuver_values["steering_angle_deg"]),
            duration_s=maneuver_values["duration_s"],
            output_step_s=maneuver_values["output_step_s"],
            torque_a_nm=torque_a,
            torque_b_nm=torque_b,
            equal_total_required=self.equal_total.get(),
            environment=environment,
        )

    def _start_run(self) -> None:
        try:
            settings = self._read_settings()
        except ValueError as error:
            messagebox.showerror("Check dynamics inputs", str(error), parent=self.window)
            return
        self.run_button.configure(state="disabled")
        self.status.set("Calculating two four-wheel maneuvers…")
        threading.Thread(target=self._calculate, args=(settings,), daemon=True).start()

    def _calculate(self, settings: ManeuverSettings) -> None:
        try:
            runs = run_maneuver_pair(settings)
            record = capture_dynamics_comparison(
                config=settings.config,
                environment=settings.environment,
                initial_state=runs[0].states[0],
                controls_a=(settings.controls("A"),) * settings.step_count,
                controls_b=(settings.controls("B"),) * settings.step_count,
                output_step_s=settings.output_step_s,
                run_a=runs[0],
                run_b=runs[1],
                equal_total_required=settings.equal_total_required,
            )
            record.save(default_dynamics_run_directory() / f"{record.run_id}.json")
            self.result_queue.put((settings, runs, record.run_id, None))
        except Exception as error:
            self.result_queue.put((None, None, None, error))

    def _poll_result(self) -> None:
        if not self.window.winfo_exists():
            return
        try:
            settings, runs, record_id, error = self.result_queue.get_nowait()
        except queue.Empty:
            self.window.after(100, self._poll_result)
            return
        self.run_button.configure(state="normal")
        if error is not None:
            self.status.set(f"Calculation failed: {error}")
            messagebox.showerror("Dynamics calculation failed", str(error), parent=self.window)
        else:
            self.settings = settings
            self.runs = runs
            self.time_scale.configure(to=settings.step_count)
            self.time_index.set(0)
            self._draw_results()
            yaw_a = degrees(runs[0].states[-1].yaw_rate_rad_s)
            yaw_b = degrees(runs[1].states[-1].yaw_rate_rad_s)
            residual = max(
                abs(item.energy_balance_residual_w)
                for run in runs for item in run.evaluations
            )
            if not all(run.road_valid for run in runs):
                invalid_count = sum(run.invalid_road_queries for run in runs)
                self.status.set(
                    f"INVALID ROAD DOMAIN · {invalid_count} wheel-force queries outside "
                    f"the supported area · A/B ranking withheld · saved {record_id[:12]}"
                )
            else:
                self.status.set(
                    f"A final yaw rate {yaw_a:.2f}°/s · B {yaw_b:.2f}°/s · "
                    f"B − A {yaw_b - yaw_a:+.2f}°/s · "
                    f"max equation residual {residual:.2e} W · saved {record_id[:12]}"
                )
        self.window.after(100, self._poll_result)

    def _theme_colors(self) -> tuple[str, str]:
        return ("#000000", "#ffffff") if self.is_dark.get() else ("#ffffff", "#000000")

    def _walk_widgets(self, parent: tk.Widget):
        for child in parent.winfo_children():
            yield child
            yield from self._walk_widgets(child)

    def _apply_theme(self) -> None:
        background, foreground = self._theme_colors()
        self.window.configure(background=background)
        for widget in self._walk_widgets(self.window):
            kind = widget.winfo_class()
            if kind == "Scrollbar":
                options = {
                    "background": background,
                    "activebackground": foreground,
                    "troughcolor": background,
                }
            elif kind in {"Frame", "Canvas"}:
                options = {"background": background}
            else:
                options = {"background": background, "foreground": foreground}
            if kind == "Entry":
                options.update(
                    insertbackground=foreground,
                    selectbackground=foreground,
                    selectforeground=background,
                    disabledbackground=background,
                    disabledforeground=foreground,
                )
            if kind in {"Button", "Checkbutton", "Menubutton", "Menu"}:
                options.update(activebackground=foreground, activeforeground=background)
            if kind == "Scale":
                options.update(activebackground=foreground, troughcolor=background)
            if kind == "Checkbutton":
                options["selectcolor"] = background
            try:
                widget.configure(**options)
            except tk.TclError:
                pass
        self._draw_results()

    def _draw_results(self) -> None:
        if self.figure is None or self.canvas is None:
            return
        background, foreground = self._theme_colors()
        self.figure.set_facecolor(background)
        for axis in (self.ax_path, self.ax_yaw, self.ax_slip, self.ax_car):
            axis.clear()
            axis.set_facecolor(background)
            axis.tick_params(axis="both", colors=foreground, labelsize=8)
            for spine in axis.spines.values():
                spine.set_color(foreground)
        if self.runs is None or self.settings is None:
            self.ax_path.text(
                0.5, 0.5, "Run A/B to see the paths", color=foreground,
                ha="center", va="center", transform=self.ax_path.transAxes,
            )
        else:
            selected = 0 if self.inspected_scenario.get() == "A" else 1
            sample_index = min(self.time_index.get(), self.settings.step_count)
            for patch in self.settings.environment.road.patches:
                self.ax_path.plot(
                    [patch.x_min_m, patch.x_max_m, patch.x_max_m, patch.x_min_m, patch.x_min_m],
                    [patch.y_min_m, patch.y_min_m, patch.y_max_m, patch.y_max_m, patch.y_min_m],
                    color=foreground, linestyle=":", linewidth=1.0,
                )
            for name, run, line_style in zip(
                ("A", "B"), self.runs, ("-", "--"), strict=True
            ):
                self.ax_path.plot(
                    [item.x_m for item in run.states],
                    [item.y_m for item in run.states],
                    color=foreground, linestyle=line_style, linewidth=1.3,
                    label=name,
                )
                self.ax_yaw.plot(
                    run.times_s,
                    [degrees(item.yaw_rate_rad_s) for item in run.states],
                    color=foreground, linestyle=line_style, linewidth=1.2,
                    label=name,
                )
            run = self.runs[selected]
            state = run.states[sample_index]
            time_s = run.times_s[sample_index]
            self.ax_path.plot(
                [state.x_m], [state.y_m], marker="o", markersize=6,
                markerfacecolor=background, markeredgecolor=foreground,
            )
            self.ax_yaw.axvline(time_s, color=foreground, linewidth=0.8, linestyle=":")
            evaluation = evaluate_planar_dynamics(
                self.settings.config,
                state,
                self.settings.controls(self.inspected_scenario.get()),
                environment=self.settings.environment,
            )
            for key, value in {
                "time": f"{time_s:.3f}",
                "forward": f"{state.u_mps:.3f}",
                "lateral": f"{state.v_mps:.3f}",
                "heading": f"{degrees(state.heading_rad):.2f}",
                "yaw": f"{degrees(state.yaw_rate_rad_s):.2f}",
                "moment": f"{evaluation.total_yaw_moment_nm:.1f}",
                "utilization": f"{100 * max(wheel.force_utilization for wheel in evaluation.wheels):.1f}",
                "residual": f"{evaluation.energy_balance_residual_w:.2e}",
                "airspeed": f"{evaluation.apparent_air_speed_mps:.3f}",
                "aero_x": f"{evaluation.aero_body_force_x_n:.1f}",
                "aero_y": f"{evaluation.aero_body_force_y_n:.1f}",
                "road": (
                    "ASSUMED" if self.settings.environment.road.valid_domain is None
                    else ("YES" if run.road_valid else "NO")
                ),
            }.items():
                self.metric_values[key].set(value)
            final_evaluation = evaluate_planar_dynamics(
                self.settings.config,
                run.states[-1],
                self.settings.controls(self.inspected_scenario.get()),
                environment=self.settings.environment,
            )
            for wheel, name, line_style in zip(
                range(4), WHEEL_ABBREVIATIONS, ("-", "--", ":", "-."), strict=True
            ):
                self.ax_slip.plot(
                    run.times_s,
                    [100.0 * item.wheels[wheel].slip_ratio for item in run.evaluations]
                    + [100.0 * final_evaluation.wheels[wheel].slip_ratio],
                    color=foreground, linestyle=line_style, linewidth=1.1,
                    label=name,
                )
            self.ax_slip.axvline(time_s, color=foreground, linewidth=0.8, linestyle=(0, (1, 3)))
            self._draw_car(evaluation, time_s, background, foreground)
            self.ax_path.legend(frameon=False, labelcolor=foreground, fontsize=8)
            self.ax_yaw.legend(frameon=False, labelcolor=foreground, fontsize=8)
            self.ax_slip.legend(frameon=False, labelcolor=foreground, fontsize=8, ncol=4)
        self.ax_path.set_title("Top-down path", color=foreground, loc="left")
        self.ax_path.set_xlabel("X (m)", color=foreground)
        self.ax_path.set_ylabel("Y (m)", color=foreground)
        self.ax_path.set_aspect("equal", adjustable="datalim")
        self.ax_yaw.set_title("Yaw response", color=foreground, loc="left")
        self.ax_yaw.set_xlabel("Time (s)", color=foreground)
        self.ax_yaw.set_ylabel("Yaw rate (deg/s)", color=foreground)
        self.ax_slip.set_title(
            f"Wheel slip · car {self.inspected_scenario.get()}",
            color=foreground, loc="left",
        )
        self.ax_slip.set_xlabel("Time (s)", color=foreground)
        self.ax_slip.set_ylabel("Slip ratio (%)", color=foreground)
        self.canvas.draw_idle()

    def _draw_car(
        self, evaluation: Any, time_s: float, background: str, foreground: str
    ) -> None:
        config = self.settings.config
        self.ax_car.set_title(
            f"Car {self.inspected_scenario.get()} at {time_s:.2f} s · body frame",
            color=foreground, loc="left",
        )
        self.ax_car.plot(
            [-config.cg_to_rear_axle_m, config.cg_to_front_axle_m],
            [0.0, 0.0], color=foreground, linewidth=1.0,
        )
        for name, (x_m, y_m), wheel in zip(
            WHEEL_ABBREVIATIONS, config.wheel_positions_m,
            evaluation.wheels, strict=True,
        ):
            self.ax_car.plot(
                [x_m], [y_m], marker="s", markersize=10,
                markerfacecolor=background, markeredgecolor=foreground,
            )
            offset = 0.16 if y_m > 0 else -0.16
            self.ax_car.text(
                x_m, y_m + offset,
                f"{name}  κ={wheel.slip_ratio:+.2f}\n"
                f"Fx={wheel.local_force_x_n:+.0f} N  "
                f"Fy={wheel.local_force_y_n:+.0f} N\n"
                f"Fz={wheel.normal_load_n:.0f} N  "
                f"grip×{wheel.road_friction_multiplier:.2f}",
                color=foreground, ha="center",
                va="bottom" if y_m > 0 else "top", fontsize=7,
            )
        self.ax_car.annotate(
            "front (+x)", xy=(config.cg_to_front_axle_m + 0.2, 0.0),
            color=foreground, ha="left", fontsize=8,
        )
        half_track = max(config.front_track_m, config.rear_track_m) / 2.0
        self.ax_car.set_xlim(
            -config.cg_to_rear_axle_m - 0.9,
            config.cg_to_front_axle_m + 1.1,
        )
        self.ax_car.set_ylim(-half_track - 0.75, half_track + 0.75)
        self.ax_car.set_aspect("equal", adjustable="box")
        self.ax_car.set_xlabel("Body x (m)", color=foreground)
        self.ax_car.set_ylabel("Body y (m)", color=foreground)


__all__ = ["DynamicsLab", "ManeuverSettings", "run_maneuver_pair"]
