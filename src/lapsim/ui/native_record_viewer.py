"""Passive plots of validated saved native telemetry; no physics is executed."""

from __future__ import annotations

from contextlib import suppress
import json
from math import isfinite
from pathlib import Path
from queue import Empty, Full, Queue
import threading
import tkinter as tk
from tkinter import filedialog

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from lapsim.experiments.suspension_compare import KINDS, compare_study_records
from lapsim.experiments.suspension_study import inspect_study_record, read_study_record

WHEELS = ("FL", "FR", "RL", "RR")
STYLES = ("-", "--", ":", "-.")
FONT = ("Segoe UI", 10)
SAVED_STATUS = "Saved samples only · settling metrics and historical timings remain recorded claims · Focus slider: Left/Right select, Home/End jump"


def _bounded_claim(value, limit=120):
    """Bound untrusted visible text and expose control/formatting characters."""
    parts, size = [], 0
    for character in value[:limit]:
        part = json.dumps(character, ensure_ascii=True)[1:-1]
        if size + len(part) > limit - 1:
            break
        parts.append(part)
        size += len(part)
    if len(parts) < len(value):
        parts.append("…")
    return "".join(parts)


def comparison_summary(report):
    """Present bounded API results; retain the complete report in Details."""
    compatibility = report["compatibility"]
    selected = compatibility["selected_field"]
    lines = [
        "Compatible recorded inputs"
        if compatibility["compatible_recorded_claims"]
        else "Recorded inputs are incompatible",
        f"{compatibility['allowed_scenario_field']} (s): Left {selected['left']:.9g}; Right {selected['right']:.9g}",
        "",
    ]
    reasons = compatibility["reasons"]
    if reasons:
        lines.extend(reasons[:5])
        if len(reasons) > 5:
            lines.append(f"{len(reasons) - 5} more reasons are in Details.")
        lines.append("No numerical result is available for incompatible inputs.")
    elif report["comparison_kind"] == "plant-step":
        result = report["result"]
        quantities = result["quantities"]
        lines.append(f"{'Quantity':28} {'Left':>15} {'Right':>15} {'Right - Left':>15}")
        rows = [
            ("World-X velocity (m/s)", quantities["world_x_velocity_mps"]),
            ("Chassis COM height (m)", quantities["chassis_com_height_m"]),
            *[
                (item["wheel"] + " spring length (m)", item)
                for item in quantities["spring_lengths_m"]
            ],
        ]
        for label, quantity in rows:
            lines.append(
                f"{label:28} {quantity['left']:15.9g} {quantity['right']:15.9g} {quantity['right_minus_left']:15.9g}"
            )
        context = result["final_observation_context"]
        lines.extend(
            (
                "",
                f"Stored endpoint state times: Left {context['left']['clocks']['time_s']!r} s; Right {context['right']['clocks']['time_s']!r} s",
                "Cached computed/applied forces retain their own origins in Details; no simultaneous force alignment is inferred.",
            )
        )
        criterion = result["criterion"]
        outcome = (
            " · " + ("passed" if criterion["passed"] else "failed")
            if "passed" in criterion
            else ""
        )
        lines.append(
            "Saved-fixture endpoint criterion: " + criterion["status"] + outcome
        )
        lines.extend(criterion.get("reasons", ()))
        lines.append(
            "This is a criterion on recorded fixture claims, not new native acceptance or a convergence proof."
        )
    else:
        result = report["result"]
        lines.extend(
            (
                f"Exact shared state timestamps: {result['shared']['count']}",
                f"Unmatched exports: Left {result['left_unmatched']['count']}; Right {result['right_unmatched']['count']}",
                f"Shared observations match: {'yes' if result['all_shared_observations_equal'] else 'no'}",
                f"Different shared observations: {result['different_shared_observations']}",
                "Counts use exact stored state timestamps; no interpolation or index alignment.",
                "Shared-only agreement does not establish equality of unmatched exports. Field counts and bounded timestamp listings are in Details.",
            )
        )
    lines.extend(("", "Current implementation-file inspection:"))
    for role in ("left", "right"):
        inspection = report["inputs"][role]["inspection"]
        lines.append(
            f"{role.title()}: {inspection['checks']['current_implementation_files']}"
        )
    recipe = report["comparison_recipe"]
    identifier = recipe["recipe_id"]
    lines.extend(
        (
            f"Comparison recipe: {recipe['status']} · ID {identifier[:12] if identifier else 'unavailable'}",
            "Recipe covers explicit comparison/validation source files; not a complete environment fingerprint or executable attestation.",
            f"Comparison report {report['report_id'][:12]} · comparison receipt {report['receipt_id'][:12]}",
            "Full IDs, observed source statuses and all API claims are in read-only Details. Filenames are display context.",
            "",
            report["scope"],
        )
    )
    return "\n".join(lines)


def recorded_model_claim(record):
    """Bound and escape a saved profile claim; never infer a current model."""
    prefix = "Recorded model claim: "
    model = record.get("payload", {}).get("model", {})
    profile = model.get("profile_id") if isinstance(model, dict) else None
    if not isinstance(profile, str) or not profile:
        return prefix + "not recorded"
    budget = 100 - len(prefix)
    parts, size = [], 0
    # Examine only a display-sized prefix, including for an 8 MB input string.
    # JSON escapes also make Unicode line and direction controls visible.
    for character in profile[:budget]:
        part = json.dumps(character, ensure_ascii=True)[1:-1]
        if size + len(part) > budget - 1:
            break
        parts.append(part)
        size += len(part)
    if len(parts) < len(profile):
        parts.append("…")
    return prefix + "".join(parts)


def force_samples(samples, wheel, kind):
    """Keep the selected force's actual source clock; omit unknown origins."""
    if kind == "Applied":
        clock, force = "applied_tire_force_source_time_s", "applied_wheel_force_world_n"
    elif kind == "Computed":
        clock, force = "tire_force_source_time_s", "wheel_force_world_n"
    else:
        raise ValueError("Choose Applied or Computed force")
    return [
        (sample[clock], sample[force][wheel][2])
        for sample in samples
        if sample[clock] is not None
    ]


def _time(value):
    return "unavailable" if value is None else f"{value:.6f} s"


def _check_plot_range(values):
    """A saved finite value can exceed the renderer's floating-point range."""
    if not values:
        return
    low, high = min(values), max(values)
    span = high - low
    margin = (span if span else max(abs(low), abs(high))) * 0.1
    if not all(isfinite(value) for value in (span, low - margin, high + margin)):
        raise ValueError("stored channel span exceeds the chart's floating-point range")


class NativeRecordViewer:
    """One bounded loader, exact exported samples, and read-only inspection."""

    def __init__(self, parent, *, dark=False):
        self.window = tk.Toplevel(parent)
        self.window.title("LapSim · Saved native study")
        self.window.geometry("1180x840")
        self.window.minsize(960, 720)
        self.dark = dark
        self.closed = False
        self.stopped = threading.Event()
        self.load_lock = threading.Lock()
        self.busy = False
        self.generation = 0
        self.active_job = None
        self.results = Queue(maxsize=1)
        self.worker = None
        self.comparison_window = self.comparison_report = None
        self.comparison_details_window = None
        self.comparison_json = None
        self.record = self.summary = self.selected_sample = None
        self.path = None
        self.index = tk.IntVar(value=0)
        self.force_kind = tk.StringVar(value="Applied")
        self.status = tk.StringVar(
            value="Open a saved native study · viewing never reproduces physics"
        )
        self.identity = tk.StringVar(value="Saved telemetry · no record open")
        self.model_claim = tk.StringVar(value=recorded_model_claim({}))
        self.checks = tk.StringVar(
            value="Integrity and structure will be checked; native replay and calibration are not established by opening."
        )
        self.clocks = tk.StringVar(
            value="Source clocks appear here when a sample is selected."
        )
        self.values = tk.StringVar(value="")
        self.wheel_values = tk.StringVar(value="")
        self.sample_label = tk.StringVar(value="No sample")
        self._build()
        self.poll_id = self.window.after(80, self._poll)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Destroy>", self._on_destroy, add="+")

    def _build(self):
        bg, fg = ("#000000", "#ffffff") if self.dark else ("#ffffff", "#000000")
        self.background, self.foreground = bg, fg
        self.window.configure(background=bg)
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(3, weight=1)
        title = tk.Frame(self.window, background=bg, padx=12, pady=8)
        title.grid(row=0, column=0, sticky="ew")
        tk.Label(
            title,
            text="Saved native study",
            font=("Segoe UI", 16, "bold"),
            background=bg,
            foreground=fg,
        ).pack(side="left")
        actions = tk.Frame(self.window, background=bg, padx=12)
        actions.grid(row=1, column=0, sticky="ew")
        self.open_button = tk.Button(
            actions, text="Open native record…", command=self.open, font=FONT
        )
        self.open_button.pack(side="left", padx=(0, 8))
        self.details_button = tk.Button(
            actions,
            text="Record and sample details…",
            command=self.inspect,
            font=FONT,
            state="disabled",
        )
        self.details_button.pack(side="left")
        self.compare_button = tk.Button(
            actions,
            text="Compare saved record…",
            command=self.open_comparison,
            font=FONT,
            state="disabled",
        )
        self.compare_button.pack(side="left", padx=(8, 0))
        tk.Label(
            actions, text="Force channel", background=bg, foreground=fg, font=FONT
        ).pack(side="left", padx=(24, 4))
        self.force_menu = tk.OptionMenu(
            actions,
            self.force_kind,
            "Applied",
            "Computed",
            command=lambda _value: self.change_force(),
        )
        self.force_menu.configure(font=FONT)
        self.force_menu.pack(side="left")
        evidence = tk.Frame(self.window, background=bg, padx=12, pady=5)
        evidence.grid(row=2, column=0, sticky="ew")
        for variable in (self.identity, self.model_claim, self.checks):
            self._label(evidence, variable).pack(fill="x", anchor="w")
        self.figure = Figure(
            figsize=(10, 5), dpi=100, constrained_layout=True, facecolor=bg
        )
        self.axes = self.figure.subplots(2, 2)
        self.path_axes, self.height_axes, self.spring_axes, self.force_axes = (
            self.axes.flat
        )
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.window)
        self.canvas.get_tk_widget().grid(row=3, column=0, sticky="nsew", padx=8)
        self.canvas.get_tk_widget().bind("<Destroy>", self._cancel_canvas, add="+")
        cursor = tk.Frame(self.window, background=bg, padx=12)
        cursor.grid(row=4, column=0, sticky="ew")
        cursor.columnconfigure(2, weight=1)
        self.previous_button = tk.Button(
            cursor,
            text="Previous",
            command=lambda: self.step(-1),
            font=FONT,
            state="disabled",
        )
        self.previous_button.grid(row=0, column=0, padx=(0, 5))
        self.next_button = tk.Button(
            cursor,
            text="Next",
            command=lambda: self.step(1),
            font=FONT,
            state="disabled",
        )
        self.next_button.grid(row=0, column=1, padx=(0, 8))
        self.slider = tk.Scale(
            cursor,
            from_=0,
            to=1,
            orient="horizontal",
            variable=self.index,
            resolution=1,
            showvalue=False,
            state="disabled",
            command=lambda value: self.select(int(float(value))),
            background=bg,
            foreground=fg,
            highlightthickness=1,
            highlightcolor=fg,
            highlightbackground=bg,
        )
        self.slider.grid(row=0, column=2, sticky="ew")
        # Consume the widget event before Tk Scale's class binding can also step.
        # Other controls retain their own native arrow-key behavior.
        for widget in (self.slider, self.canvas.get_tk_widget()):
            widget.bind("<Left>", lambda _event: self._key_step(-1))
            widget.bind("<Right>", lambda _event: self._key_step(1))
            widget.bind("<Home>", lambda _event: self._key_select(0))
            widget.bind("<End>", lambda _event: self._key_select(10**9))
        self._label(cursor, self.sample_label).grid(row=0, column=3, padx=(8, 0))
        selected = tk.Frame(self.window, background=bg, padx=12, pady=4)
        selected.grid(row=5, column=0, sticky="ew")
        for variable in (self.clocks, self.values, self.wheel_values):
            self._label(selected, variable, font=("Consolas", 9)).pack(fill="x")
        self._label(self.window, self.status).grid(
            row=6, column=0, sticky="ew", padx=12, pady=(2, 8)
        )
        self._empty_plot()

    def _label(self, parent, variable, *, font=FONT):
        label = tk.Label(
            parent,
            textvariable=variable,
            anchor="w",
            justify="left",
            font=font,
            background=self.background,
            foreground=self.foreground,
            wraplength=900,
        )
        label.bind(
            "<Configure>",
            lambda event: label.configure(wraplength=max(200, event.width)),
        )
        return label

    def _style_axis(self, axis, title, xlabel, ylabel):
        axis.clear()
        axis.set_facecolor(self.background)
        axis.set_title(title, loc="left", color=self.foreground, fontsize=10)
        axis.set_xlabel(xlabel, color=self.foreground, fontsize=9)
        axis.set_ylabel(ylabel, color=self.foreground, fontsize=9)
        axis.tick_params(colors=self.foreground, labelsize=8)
        for spine in axis.spines.values():
            spine.set_color(self.foreground)

    def _empty_plot(self):
        for axis, title, xlabel, ylabel in (
            (
                self.path_axes,
                "Recorded COM path and wheel centers",
                "World X (m)",
                "World Y (m)",
            ),
            (self.height_axes, "Chassis COM height", "State time (s)", "World Z (m)"),
            (
                self.spring_axes,
                "Recorded spring lengths",
                "State time (s)",
                "Length (m)",
            ),
            (
                self.force_axes,
                "Cached tire forces · no simultaneous wrench",
                "Force source time (s)",
                "World Fz (N)",
            ),
        ):
            self._style_axis(axis, title, xlabel, ylabel)
        self.canvas.draw_idle()

    def open(self):
        if self.closed or self.busy:
            return
        chosen = filedialog.askopenfilename(
            parent=self.window, filetypes=(("Native study JSON", "*.json"),)
        )
        if chosen:
            self.load_path(Path(chosen))

    def load_path(self, path):
        if self.closed or self.busy:
            return False
        self.close_comparison()
        self.generation += 1
        generation = self.generation
        self.active_job = generation
        self.busy = True
        self.record = self.summary = self.selected_sample = None
        self.path = Path(path)
        self.open_button.configure(state="disabled")
        self.compare_button.configure(state="disabled")
        for widget in (
            self.details_button,
            self.previous_button,
            self.next_button,
            self.slider,
        ):
            widget.configure(state="disabled")
        self.identity.set("Opening " + self.path.name)
        self.model_claim.set(recorded_model_claim({}))
        self.checks.set("Checking saved integrity, structure and clocks…")
        self.clocks.set("")
        self.values.set("")
        self.wheel_values.set("")
        self.sample_label.set("No sample")
        self.status.set("Opening saved telemetry; no physics or replay is running")
        self._empty_plot()
        self.worker = threading.Thread(
            target=self._load, args=(self.path, generation), daemon=True
        )
        self.worker.start()
        return True

    def _load(self, path, generation):
        try:
            record = read_study_record(path)
            summary = inspect_study_record(record)
            value, error = (record, summary), None
        except Exception as failure:
            value, error = None, str(failure)
        self._publish(generation, "record", value, error)

    def _publish(self, generation, kind, value, error):
        with self.load_lock:
            if not self.stopped.is_set():
                with suppress(Full):
                    self.results.put_nowait((generation, kind, value, error))

    def _sync_comparison_controls(self):
        self.open_button.configure(state="disabled" if self.busy else "normal")
        self.compare_button.configure(
            state="normal" if self.record is not None else "disabled"
        )
        if self.comparison_window is not None:
            self.comparison_choose_button.configure(
                state="normal"
                if not self.busy and self.comparison_kind.get() in KINDS
                else "disabled"
            )
            self.comparison_details_button.configure(
                state="normal" if self.comparison_report is not None else "disabled"
            )

    def _accept_result(self, generation, kind, value, error):
        # A dismissed view invalidates publication, not ownership of its worker.
        # Release only the matching owner, even when its result is now stale.
        if generation != self.active_job:
            return
        self.active_job = None
        self.busy = False
        if generation == self.generation:
            if kind == "record":
                self._show_record(value, error)
            else:
                self._show_comparison(value, error)
        self._sync_comparison_controls()

    def _poll(self):
        if self.closed:
            return
        try:
            result = self.results.get_nowait()
        except Empty:
            pass
        else:
            self._accept_result(*result)
        self.poll_id = self.window.after(80, self._poll)

    def _show_record(self, value, error):
        if error is not None:
            self.checks.set("Record was not opened; no telemetry is displayed")
            self.status.set("Open failed: " + error)
        else:
            assert self.path is not None
            record, summary = value
            self.record, self.summary = record, summary
            self.identity.set(
                f"{self.path.name} · saved content {record['content_id'][:12]} · integrity and stored structure checked"
            )
            self.model_claim.set(recorded_model_claim(record))
            self.checks.set(
                "Current implementation: "
                + summary["checks"]["current_implementation_files"]
                + " · fresh native replay not run · calibration not established"
            )
            self.slider.configure(
                to=len(record["payload"]["samples"]) - 1, state="normal"
            )
            self.details_button.configure(state="normal")
            try:
                self._draw_record()
                self.select(0)
            except (ValueError, OverflowError) as failure:
                self.record = self.summary = self.selected_sample = None
                self.model_claim.set(recorded_model_claim({}))
                for widget in (
                    self.details_button,
                    self.previous_button,
                    self.next_button,
                    self.slider,
                ):
                    widget.configure(state="disabled")
                self._empty_plot()
                self.clocks.set("")
                self.values.set("")
                self.wheel_values.set("")
                self.sample_label.set("No sample")
                self.checks.set(
                    "Saved structure checked; channel ranges could not be plotted"
                )
                self.status.set("Open failed: " + str(failure))
            else:
                if self.force_plot_available:
                    self.status.set(SAVED_STATUS)

    def open_comparison(self):
        if self.closed or self.record is None or self.path is None:
            return None
        if self.comparison_window is not None:
            self.comparison_window.lift()
            return self.comparison_window
        window = self.comparison_window = tk.Toplevel(self.window)
        window.transient(self.window)
        window.title("LapSim · Compare saved native studies")
        window.geometry("860x680")
        window.minsize(720, 520)
        window.configure(background=self.background)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(4, weight=1)
        tk.Label(
            window,
            text="Compare saved native studies",
            font=("Segoe UI", 16, "bold"),
            background=self.background,
            foreground=self.foreground,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        self.comparison_left = tk.StringVar(
            value=f"Left: {_bounded_claim(self.path.name)} · saved content {self.record['content_id'][:12]}\n{recorded_model_claim(self.record)}"
        )
        self._label(window, self.comparison_left).grid(
            row=1, column=0, sticky="ew", padx=12
        )
        controls = tk.Frame(window, background=self.background)
        controls.grid(row=2, column=0, sticky="ew", padx=12, pady=8)
        tk.Label(
            controls,
            text="Recorded difference",
            font=FONT,
            background=self.background,
            foreground=self.foreground,
        ).pack(side="left", padx=(0, 8))
        self.comparison_kind = tk.StringVar(value="")
        self.comparison_kind_buttons = []
        for index, (label, kind) in enumerate(
            (
                ("Plant step", "plant-step"),
                ("Logging period", "logging-period"),
            )
        ):
            button = tk.Radiobutton(
                controls,
                text=label,
                value=kind,
                variable=self.comparison_kind,
                command=self._reset_comparison,
                font=FONT,
                background=self.background,
                foreground=self.foreground,
                activebackground=self.background,
                activeforeground=self.foreground,
                selectcolor=self.background,
            )
            for key, direction in (
                ("<Left>", -1),
                ("<Up>", -1),
                ("<Right>", 1),
                ("<Down>", 1),
            ):
                button.bind(
                    key,
                    lambda _event, at=index, step=direction: self._comparison_kind_key(
                        at, step
                    ),
                )
            button.pack(side="left", padx=(0, 8))
            self.comparison_kind_buttons.append(button)
        self.comparison_choose_button = tk.Button(
            controls,
            text="Choose second record…",
            command=self.choose_comparison,
            font=FONT,
            state="disabled",
        )
        self.comparison_choose_button.pack(side="left", padx=(8, 0))
        self.comparison_right = tk.StringVar(value="Right: no record selected")
        self._label(window, self.comparison_right).grid(
            row=3, column=0, sticky="ew", padx=12
        )
        panel = tk.Frame(window, background=self.background)
        panel.grid(row=4, column=0, sticky="nsew", padx=12, pady=8)
        self.comparison_text = tk.Text(
            panel,
            wrap="word",
            padx=10,
            pady=10,
            font=("Consolas", 10),
            background=self.background,
            foreground=self.foreground,
        )
        scroll = tk.Scrollbar(panel, command=self.comparison_text.yview)
        scroll.pack(side="right", fill="y")
        self.comparison_text.configure(yscrollcommand=scroll.set)
        self.comparison_text.pack(fill="both", expand=True)
        actions = tk.Frame(window, background=self.background)
        actions.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 10))
        self.comparison_details_button = tk.Button(
            actions,
            text="Comparison details…",
            command=self.inspect_comparison,
            font=FONT,
            state="disabled",
        )
        self.comparison_details_button.pack(side="left")
        tk.Button(actions, text="Close", command=self.close_comparison, font=FONT).pack(
            side="right"
        )
        window.protocol("WM_DELETE_WINDOW", self.close_comparison)
        window.bind("<Escape>", lambda _event: self.close_comparison())
        window.bind("<Destroy>", self._on_comparison_destroy, add="+")
        self._set_comparison_text(
            "A previous request is finishing. Choose again when it completes."
            if self.busy
            else "Choose Plant step or Logging period, then choose a second record.\nOnly saved observations and recorded claims are compared."
        )
        self.comparison_kind_buttons[0].focus_set()
        return window

    def _comparison_kind_key(self, index, direction):
        if not self.closed and self.comparison_window is not None:
            target = self.comparison_kind_buttons[
                (index + direction) % len(self.comparison_kind_buttons)
            ]
            target.focus_set()
            target.invoke()
        return "break"

    def _set_comparison_text(self, content):
        self.comparison_text.configure(state="normal")
        self.comparison_text.delete("1.0", "end")
        self.comparison_text.insert("1.0", content)
        self.comparison_text.configure(state="disabled")

    def _clear_comparison_details(self):
        details = self.comparison_details_window
        self.comparison_details_window = None
        if details is not None:
            with suppress(tk.TclError):
                details.destroy()

    def _reset_comparison(self):
        self.generation += 1
        self.comparison_report = self.comparison_json = None
        self._clear_comparison_details()
        if self.comparison_window is not None:
            self.comparison_right.set("Right: no record selected")
            self._set_comparison_text(
                "The previous request is finishing and its result will be discarded. Choose a second record when it completes."
                if self.busy
                else "Choose a second record for this explicit comparison kind.\nOnly saved observations and recorded claims are compared."
            )
            self._sync_comparison_controls()

    def choose_comparison(self):
        if self.closed or self.busy or self.comparison_kind.get() not in KINDS:
            return
        chosen = filedialog.askopenfilename(
            parent=self.comparison_window, filetypes=(("Native study JSON", "*.json"),)
        )
        if chosen:
            self.compare_path(Path(chosen))

    def compare_path(self, path):
        if (
            self.closed
            or self.busy
            or self.record is None
            or self.comparison_window is None
            or self.comparison_kind.get() not in KINDS
        ):
            return False
        self._reset_comparison()
        generation = self.generation
        self.active_job = generation
        self.busy = True
        path = Path(path)
        self.comparison_right.set("Opening Right: " + _bounded_claim(path.name))
        self._set_comparison_text(
            "Checking the second record and comparing saved observations…\nNo physics or replay is running."
        )
        self._sync_comparison_controls()
        self.worker = threading.Thread(
            target=self._load_comparison,
            args=(self.record, path, self.comparison_kind.get(), generation),
            daemon=True,
        )
        self.worker.start()
        return True

    def _load_comparison(self, left, path, kind, generation):
        try:
            right = read_study_record(path)
            report = compare_study_records(left, right, kind=kind)
            value = (
                report,
                comparison_summary(report),
                json.dumps(report, indent=2, allow_nan=False),
                f"Right: {_bounded_claim(path.name)} · saved content {right['content_id'][:12]}\n{recorded_model_claim(right)}",
            )
            error = None
        except Exception as failure:
            value, error = None, str(failure)
        self._publish(generation, "comparison", value, error)

    def _show_comparison(self, value, error):
        if self.comparison_window is None:
            return
        if error is not None:
            self.comparison_report = self.comparison_json = None
            self.comparison_right.set("Right: record was not opened")
            self._set_comparison_text(
                "Comparison failed: "
                + _bounded_claim(error, 320)
                + "\nNo comparison result is displayed. The primary saved record is unchanged."
            )
        else:
            self.comparison_report, text, self.comparison_json, right = value
            self.comparison_right.set(right)
            self._set_comparison_text(text)

    def inspect_comparison(self):
        if (
            self.closed
            or self.comparison_window is None
            or self.comparison_report is None
        ):
            return None
        self._clear_comparison_details()
        window = self.comparison_details_window = tk.Toplevel(self.comparison_window)
        window.title(
            "Saved comparison details · " + self.comparison_report["report_id"][:12]
        )
        window.geometry("850x620")
        text = tk.Text(
            window,
            wrap="word",
            padx=12,
            pady=12,
            font=("Consolas", 10),
            background=self.background,
            foreground=self.foreground,
        )
        scroll = tk.Scrollbar(window, command=text.yview)
        scroll.pack(side="right", fill="y")
        text.configure(yscrollcommand=scroll.set)
        text.pack(fill="both", expand=True)
        text.insert("1.0", self.comparison_json)
        text.configure(state="disabled")
        return window

    def _on_comparison_destroy(self, event):
        if event.widget is self.comparison_window:
            self.close_comparison()

    def close_comparison(self):
        window = self.comparison_window
        if window is None:
            return "break"
        self.generation += 1
        self.comparison_window = None
        self.comparison_report = self.comparison_json = None
        self.comparison_left.set("")
        self.comparison_right.set("Right: no record selected")
        self.comparison_kind.set("")
        self._clear_comparison_details()
        with suppress(tk.TclError):
            window.destroy()
            if not self.closed:
                self.compare_button.focus_force()
        return "break"

    def _draw_record(self):
        if self.record is None:
            return
        self._empty_plot()
        samples = self.record["payload"]["samples"]
        for dimension in range(2):
            _check_plot_range(
                [s["position_m"][dimension] for s in samples]
                + [point[dimension] for s in samples for point in s["wheel_position_m"]]
            )
        _check_plot_range([s["position_m"][2] for s in samples])
        _check_plot_range(
            [length for s in samples for length in s["suspension_spring_length_m"]]
        )
        times = [sample["time_s"] for sample in samples]
        self.path_axes.plot(
            [s["position_m"][0] for s in samples],
            [s["position_m"][1] for s in samples],
            color=self.foreground,
            linewidth=1,
        )
        (self.com_marker,) = self.path_axes.plot(
            [], [], "o", color=self.foreground, label="COM"
        )
        self.wheel_markers = []
        self.wheel_labels = []
        for wheel in WHEELS:
            (marker,) = self.path_axes.plot(
                [], [], "s", color=self.foreground, markerfacecolor=self.background
            )
            self.wheel_markers.append(marker)
            self.wheel_labels.append(
                self.path_axes.text(0, 0, wheel, color=self.foreground, fontsize=8)
            )
        points = [s["position_m"] for s in samples] + [
            point for s in samples for point in s["wheel_position_m"]
        ]
        for dimension, setter in (
            (0, self.path_axes.set_xlim),
            (1, self.path_axes.set_ylim),
        ):
            low, high = (
                min(p[dimension] for p in points),
                max(p[dimension] for p in points),
            )
            pad = max(0.2, (high - low) * 0.08)
            setter(low - pad, high + pad)
        self.path_axes.set_aspect("equal", adjustable="box")
        self.height_axes.plot(
            times, [s["position_m"][2] for s in samples], color=self.foreground
        )
        (self.height_marker,) = self.height_axes.plot(
            [], [], "o", color=self.foreground
        )
        self.height_cursor = self.height_axes.axvline(
            times[0], color=self.foreground, linestyle=":", linewidth=0.7
        )
        self.spring_markers = []
        for wheel, name, style in zip(range(4), WHEELS, STYLES, strict=True):
            self.spring_axes.plot(
                times,
                [s["suspension_spring_length_m"][wheel] for s in samples],
                linestyle=style,
                color=self.foreground,
                label=name,
            )
            (marker,) = self.spring_axes.plot(
                [], [], "o", color=self.foreground, markersize=4
            )
            self.spring_markers.append(marker)
        self.spring_axes.legend(
            frameon=False, labelcolor=self.foreground, fontsize=8, ncol=4
        )
        self.spring_cursor = self.spring_axes.axvline(
            times[0], color=self.foreground, linestyle=":", linewidth=0.7
        )
        # Validate the other panels with their selected markers before the
        # force-specific recovery path. A failure here invalidates the view.
        self.force_plot_available = False
        self.force_markers = []
        self.select(self.index.get())
        self.canvas.draw()
        self.change_force()

    def change_force(self):
        if self.closed or self.record is None:
            return
        self._style_axis(
            self.force_axes,
            self.force_kind.get() + " vertical tire forces",
            "Stored force source time (s)",
            "World Fz (N)",
        )
        self.force_markers = []
        self.force_plot_available = True
        try:
            traces = [
                force_samples(
                    self.record["payload"]["samples"], wheel, self.force_kind.get()
                )
                for wheel in range(4)
            ]
            _check_plot_range([pair[1] for trace in traces for pair in trace])
            for pairs, name, style in zip(traces, WHEELS, STYLES, strict=True):
                self.force_axes.plot(
                    [p[0] for p in pairs],
                    [p[1] for p in pairs],
                    color=self.foreground,
                    linestyle=style,
                    label=name,
                )
                (marker,) = self.force_axes.plot(
                    [], [], "o", color=self.foreground, markersize=4
                )
                self.force_markers.append(marker)
            self.force_axes.legend(
                frameon=False, labelcolor=self.foreground, fontsize=8, ncol=4
            )
            self.select(self.index.get())
            # Resolve locator/transform failures here, before a deferred Tk draw.
            self.canvas.draw()
        except (ValueError, OverflowError) as error:
            self.force_plot_available = False
            self.force_markers = []
            self._style_axis(
                self.force_axes,
                self.force_kind.get() + " vertical tire forces",
                "Stored force source time (s)",
                "World Fz (N)",
            )
            self.force_axes.text(
                0.5,
                0.5,
                "Channel range cannot be plotted.\nExact saved values remain in Details.",
                ha="center",
                va="center",
                transform=self.force_axes.transAxes,
                color=self.foreground,
            )
            self.status.set(
                self.force_kind.get() + " force plot unavailable: " + str(error)
            )
            self.select(self.index.get())
        else:
            self.status.set(SAVED_STATUS)

    def select(self, index):
        if self.closed or self.record is None:
            return
        samples = self.record["payload"]["samples"]
        index = min(max(int(index), 0), len(samples) - 1)
        if self.index.get() != index:
            self.index.set(index)
        sample = self.selected_sample = samples[index]
        t = sample["time_s"]
        self.sample_label.set(f"Sample {index + 1} / {len(samples)}")
        self.previous_button.configure(state="normal" if index else "disabled")
        self.next_button.configure(
            state="normal" if index < len(samples) - 1 else "disabled"
        )
        self.clocks.set(
            f"State {_time(t)} | computed force {_time(sample['tire_force_source_time_s'])} | slip {_time(sample['tire_kinematics_source_time_s'])}\nApplied cache origin {_time(sample['applied_tire_force_source_time_s'])} | applied geometry {_time(sample['applied_tire_force_geometry_time_s'])}"
        )

        def vector(values):
            return "[" + ", ".join(f"{v:.4g}" for v in values) + "]"

        command = sample["command"]
        self.values.set(
            f"COM {vector(sample['position_m'])} m | world velocity {vector(sample['velocity_mps'])} m/s | heading {sample['heading_rad']:.4g} rad\nCompleted interval request: shaft {command['driveshaft_torque_nm']:.4g} N m | steering {command['steering']:.4g} normalized | braking {command['braking']:.4g} normalized"
        )
        applied = self.force_kind.get() == "Applied"
        force = sample[
            "applied_wheel_force_world_n" if applied else "wheel_force_world_n"
        ]
        clock = sample[
            "applied_tire_force_source_time_s"
            if applied
            else "tire_force_source_time_s"
        ]
        self.wheel_values.set(
            f"FL / FR / RL / RR · spring lengths {vector(sample['suspension_spring_length_m'])} m | {self.force_kind.get().lower()} Fz {vector([value[2] for value in force])} N"
        )
        self.com_marker.set_data([sample["position_m"][0]], [sample["position_m"][1]])
        self.height_marker.set_data([t], [sample["position_m"][2]])
        self.height_cursor.set_xdata([t, t])
        self.spring_cursor.set_xdata([t, t])
        for wheel in range(4):
            point = sample["wheel_position_m"][wheel]
            self.wheel_markers[wheel].set_data([point[0]], [point[1]])
            self.wheel_labels[wheel].set_position((point[0] + 0.05, point[1] + 0.05))
            self.spring_markers[wheel].set_data(
                [t], [sample["suspension_spring_length_m"][wheel]]
            )
            if self.force_plot_available:
                self.force_markers[wheel].set_visible(clock is not None)
                if clock is not None:
                    self.force_markers[wheel].set_data([clock], [force[wheel][2]])
        self.canvas.draw_idle()

    def step(self, amount):
        self.select(self.index.get() + amount)

    def _key_step(self, amount):
        self.step(amount)
        return "break"

    def _key_select(self, index):
        self.select(index)
        return "break"

    def inspect(self):
        if self.closed or self.record is None or self.path is None:
            return None
        window = tk.Toplevel(self.window)
        window.title(
            f"Saved native details · {self.path.name} · {self.record['content_id'][:12]}"
        )
        window.geometry("850x620")
        text = tk.Text(window, wrap="word", padx=12, pady=12, font=("Consolas", 10))
        scroll = tk.Scrollbar(window, command=text.yview)
        scroll.pack(side="right", fill="y")
        text.configure(yscrollcommand=scroll.set)
        text.pack(fill="both", expand=True)
        text.insert(
            "1.0",
            json.dumps(
                {"inspection": self.summary, "selected_sample": self.selected_sample},
                indent=2,
                allow_nan=False,
            ),
        )
        text.configure(state="disabled")
        return window

    def _cancel_canvas(self, _event=None):
        widget = self.canvas.get_tk_widget()
        for attribute in ("_idle_draw_id", "_event_loop_id"):
            identifier = getattr(self.canvas, attribute, None)
            if identifier is not None:
                with suppress(tk.TclError):
                    widget.after_cancel(identifier)
                setattr(self.canvas, attribute, None)
        photo = getattr(self.canvas, "_tkphoto", None)
        if photo is not None and photo.name:
            with suppress(tk.TclError):
                photo.tk.call("image", "delete", photo.name)
            photo.name = None

    def _on_destroy(self, event):
        if event.widget is self.window:
            self._dispose()

    def _dispose(self):
        if self.closed:
            return
        self.closed = True
        self.close_comparison()
        with self.load_lock:
            self.stopped.set()
            while not self.results.empty():
                self.results.get_nowait()
        self.generation += 1
        self.active_job = None
        self.record = self.summary = self.selected_sample = None
        with suppress(tk.TclError):
            self.window.after_cancel(self.poll_id)
        self._cancel_canvas()

    def close(self):
        if not self.closed:
            self._dispose()
            self.window.destroy()
