"""Native, monochrome desktop interface for the LapSim model."""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox
from typing import Any

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from .presets import VehicleSetup, make_prius_benchmark
from .simulation import load_team_endurance_track, resample_track, run_one_lap


FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 16, "bold")
STANDARD_GRAVITY_MPS2 = 9.80665


class LapSimDesktop:
    """Build the Tk desktop application around the shared physics APIs."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("LapSim — Formula SAE Lap Simulator")
        self.root.geometry("1380x900")
        self.root.minsize(1080, 720)

        self.track = load_team_endurance_track()
        self.result_queue: queue.Queue[tuple[float, Any, BaseException | None]] = (
            queue.Queue()
        )
        self.run_started_at = 0.0
        self.run_in_progress = False
        self.is_dark = tk.BooleanVar(value=False)
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
        self.output_values: dict[str, tk.Label] = {}
        self.canvas: FigureCanvasTkAgg | None = None
        self.course_ax: Any = None
        self.speed_ax: Any = None
        self.figure: Figure | None = None
        self._pan_origin: tuple[
            float, float, tuple[float, float], tuple[float, float]
        ] | None = None
        self._last_result: Any = None
        self._build_window()
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

        left = tk.Frame(main, width=365)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        left.grid_propagate(False)
        right = tk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._build_inputs(left)
        self._build_outputs(left)
        self._build_notes(left)
        self._build_plot(right)

        footer = tk.Label(
            self.root,
            text=(
                "Course: team endurance recording · Prius values are a road-car "
                "placeholder · model outputs are estimates"
            ),
            anchor="w",
            padx=10,
            pady=5,
            font=("Segoe UI", 9),
        )
        footer.pack(fill="x")

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
        tk.Label(box, text="Toyota Prius LE · FWD benchmark", anchor="w", font=FONT_BOLD).grid(
            row=0, column=0, columnspan=3, sticky="ew", pady=(0, 3)
        )
        tk.Label(
            box,
            text="Edit a value, then run the lap. All units are shown.",
            anchor="w",
            justify="left",
            wraplength=315,
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
            wraplength=315,
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

    def _build_notes(self, parent: tk.Widget) -> None:
        box = tk.LabelFrame(
            parent,
            text="Model scope",
            font=FONT_BOLD,
            padx=8,
            pady=7,
            bd=1,
            relief="solid",
        )
        box.pack(fill="both", expand=True)
        note = (
            "The course is the team's earlier 989 m endurance recording. "
            "The Prius uses Toyota-published baseline values and an idealized "
            "front-wheel-drive power curve. Tire grip, drag, and battery data "
            "are model assumptions. This is not a calibrated Prius or the "
            "upcoming 2026–27 Formula SAE car."
        )
        tk.Label(
            box,
            text=note,
            anchor="nw",
            justify="left",
            wraplength=315,
        ).pack(fill="both", expand=True)

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
        plot_box.grid(row=0, column=0, sticky="nsew")
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

        self.figure = Figure(figsize=(10.5, 7.8), dpi=100, constrained_layout=True)
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
            if widget.winfo_class() in {"Frame", "Canvas", "Toplevel", "Menubutton"}:
                options["background"] = background
            else:
                options["background"] = background
                options["foreground"] = foreground
            if widget.winfo_class() in {"Button", "Labelframe", "Entry", "Checkbutton"}:
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

        if self._last_result is not None and self._last_result.telemetry is not None:
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

    def _read_setup(self) -> tuple[VehicleSetup, float]:
        try:
            numeric = {
                key: float(variable.get())
                for key, variable in self.inputs.items()
                if key != "solver_step_m"
            }
            torque_percent = numeric.pop("torque_request_percent")
            setup = VehicleSetup(
                **numeric,
                torque_request_fraction=torque_percent / 100.0,
            )
            solver_step_m = float(self.inputs["solver_step_m"].get())
        except (ValueError, TypeError) as error:
            raise ValueError("Enter a valid number in each input field.") from error
        if not np.isfinite(solver_step_m) or solver_step_m <= 0.0:
            raise ValueError("Solver step must be a finite number greater than zero.")
        if solver_step_m > self.track.length_m:
            raise ValueError("Solver step must be shorter than the course length.")
        return setup, solver_step_m

    def _start_run(self) -> None:
        if self.run_in_progress:
            return
        try:
            setup, step_m = self._read_setup()
        except ValueError as error:
            messagebox.showerror("Check vehicle inputs", str(error), parent=self.root)
            return

        self.run_in_progress = True
        self.run_started_at = time.perf_counter()
        self.run_button.configure(state="disabled")
        for entry in self.input_entries:
            entry.configure(state="disabled")
        self.status_text.set(
            f"Calculating path limits and one lap at {step_m:g} m solver spacing…"
        )
        worker = threading.Thread(
            target=self._calculate_in_background,
            args=(setup, step_m),
            daemon=True,
        )
        worker.start()

    def _calculate_in_background(self, setup: VehicleSetup, step_m: float) -> None:
        try:
            solver_track = resample_track(self.track, maximum_cell_length_m=step_m)
            vehicle = make_prius_benchmark(setup)
            result = run_one_lap(
                vehicle,
                solver_track,
                torque_request_fraction=setup.torque_request_fraction,
            )
            self.result_queue.put((step_m, result, None))
        except Exception as error:
            self.result_queue.put((step_m, None, error))

    def _poll_result(self) -> None:
        try:
            step_m, result, error = self.result_queue.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_result)
            return

        self.run_in_progress = False
        self.run_button.configure(state="normal")
        for entry in self.input_entries:
            entry.configure(state="normal")
        elapsed_s = time.perf_counter() - self.run_started_at
        if error is not None:
            self.status_text.set(f"Calculation failed: {error}")
            messagebox.showerror("Lap calculation failed", str(error), parent=self.root)
        elif result.completed:
            self._last_result = result
            self._show_result(result)
            self.status_text.set(
                f"Lap completed in {elapsed_s:.1f} s · solver spacing {step_m:g} m"
            )
        else:
            self.status_text.set(f"Lap did not complete: {result.failure_reason}")
            messagebox.showerror(
                "Lap did not complete",
                str(result.failure_reason),
                parent=self.root,
            )
        self.root.after(100, self._poll_result)

    def _show_result(self, result: Any) -> None:
        telemetry = result.telemetry
        if telemetry is None:
            return
        speed_mps = np.asarray(telemetry["vehicle.speed_mps"], dtype=float)
        lateral_mps2 = np.asarray(
            telemetry["vehicle.lateral_acceleration_mps2"], dtype=float
        )
        average_speed_kph = self.track.length_m / result.driving_time_s * 3.6
        values = {
            "lap_time": f"{result.driving_time_s:.2f}",
            "peak_speed": f"{float(np.max(speed_mps)) * 3.6:.1f}",
            "average_speed": f"{average_speed_kph:.1f}",
            "distance": f"{self.track.length_m:.0f}",
            "energy": f"{result.pack_energy_kwh:.3f}",
            "lateral_g": f"{float(np.max(np.abs(lateral_mps2))) / STANDARD_GRAVITY_MPS2:.2f}",
        }
        for key, value in values.items():
            self.output_values[key].configure(text=value)
        self._draw_plots(preserve_course_view=True)


def main() -> None:
    root = tk.Tk()
    LapSimDesktop(root)
    root.mainloop()
