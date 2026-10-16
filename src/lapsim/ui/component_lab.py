"""Small, offline component comparison; no vehicle state or specialist tool."""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from uuid import uuid4

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from lapsim.experiments.component_study import (
    GeometryCard,
    Interval,
    load_component_json,
    replay_component_comparison,
    run_component_comparison,
)
from lapsim.experiments.dynamics_record import _canonical_json


class ComponentLab:
    def __init__(self, parent: tk.Misc):
        self.window = tk.Toplevel(parent)
        self.window.title("LapSim · Component materials study")
        self.window.geometry("1120x780")
        self.window.minsize(920, 740)
        self.record = None
        self.imported = False
        self.closed = False
        body = ttk.Frame(self.window, padding=20)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(2, weight=1)
        ttk.Label(
            body, text="Component materials study", font=("Segoe UI", 20, "bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            body,
            text="Compare two synthetic isotropic materials under the same tip force and torque.",
            wraplength=1050,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 18))
        shell = ttk.Frame(body)
        shell.grid(row=2, column=0, sticky="nsew", padx=(0, 24))
        self.controls_canvas = tk.Canvas(
            shell, width=270, highlightthickness=0, takefocus=1
        )
        scrollbar = ttk.Scrollbar(shell, command=self.controls_canvas.yview)
        scrollbar.pack(side="right", fill="y")
        self.controls_canvas.configure(yscrollcommand=scrollbar.set)
        self.controls_canvas.pack(side="left", fill="both", expand=True)
        controls = ttk.Frame(self.controls_canvas)
        panel = self.controls_canvas.create_window((0, 0), window=controls, anchor="nw")
        controls.bind(
            "<Configure>",
            lambda _event: self.controls_canvas.configure(
                scrollregion=self.controls_canvas.bbox("all")
            ),
        )
        self.controls_canvas.bind(
            "<Configure>",
            lambda event: self.controls_canvas.itemconfigure(panel, width=event.width),
        )
        for key, direction in (("<Up>", -1), ("<Down>", 1)):
            self.controls_canvas.bind(
                key,
                lambda _event, d=direction: self.controls_canvas.yview_scroll(
                    d, "units"
                ),
            )
        for key, direction in (("<Prior>", -1), ("<Next>", 1)):
            self.controls_canvas.bind(
                key,
                lambda _event, d=direction: self.controls_canvas.yview_scroll(
                    d, "pages"
                ),
            )
        ttk.Label(
            controls,
            text="Clamped circular cantilever\nA · light reference, E = 70 GPa\nB · dense reference, E = 200 GPa",
            justify="left",
        ).pack(anchor="w", pady=(0, 12))
        self.edit_controls = ttk.Frame(controls)
        self.edit_controls.pack(fill="x")
        self.inputs = {}
        self.entries = []
        for name, label, value in (
            ("length", "Span (m)", ".6"),
            ("outside", "Outside diameter A (m)", ".025"),
            ("inside", "Inside diameter, both (m)", ".021"),
            ("outside_b", "Outside diameter B (m)", ".025"),
            ("force", "Tip force Fy (N)", "100"),
            ("torque", "Tip torque Mx (N·m)", "20"),
        ):
            ttk.Label(self.edit_controls, text=label).pack(anchor="w", pady=(5, 2))
            variable = tk.StringVar(value=value)
            entry = ttk.Entry(self.edit_controls, textvariable=variable, width=27)
            entry.pack(fill="x")
            variable.trace_add("write", self.invalidate)
            self.inputs[name] = variable
            self.entries.append(entry)
        self.dimensions = tk.BooleanVar(value=True)
        self.bounds_check = ttk.Checkbutton(
            self.edit_controls,
            text="Include dimension bounds",
            variable=self.dimensions,
            command=self.invalidate,
        )
        self.bounds_check.pack(anchor="w", pady=(12, 2))
        ttk.Label(
            self.edit_controls,
            text="±1 mm span; ±0.1 mm diameters\nIndependent material bounds always included.",
            wraplength=260,
        ).pack(anchor="w", pady=(0, 12))
        self.saved_configuration = tk.StringVar()
        self.saved_configuration_label = ttk.Label(
            controls,
            textvariable=self.saved_configuration,
            wraplength=260,
            justify="left",
        )
        self.run_button = ttk.Button(controls, text="Calculate A/B", command=self.run)
        self.run_button.pack(fill="x", pady=3)
        self.save_button = ttk.Button(
            controls, text="Save comparison…", command=self.save, state="disabled"
        )
        self.save_button.pack(fill="x", pady=3)
        ttk.Button(controls, text="Open and replay…", command=self.load).pack(
            fill="x", pady=3
        )
        ttk.Button(controls, text="New study", command=self.new).pack(fill="x", pady=3)
        results = ttk.Frame(body)
        results.grid(row=2, column=1, sticky="nsew")
        self.figure = Figure(figsize=(7, 4), dpi=100, layout="constrained")
        self.axes = self.figure.subplots(2, 1)
        self.canvas = FigureCanvasTkAgg(self.figure, master=results)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.metrics = tk.StringVar(
            value="Calculate to see component stiffness, stress, mass and inertia."
        )
        metrics_label = ttk.Label(
            results, textvariable=self.metrics, justify="left", wraplength=710
        )
        metrics_label.pack(anchor="w", pady=(10, 4))
        results.bind(
            "<Configure>",
            lambda event: metrics_label.configure(wraplength=max(200, event.width - 8)),
        )
        self.status = tk.StringVar(
            value="Synthetic component benchmark · analytic Python · no chassis or vehicle coupling"
        )
        status_label = ttk.Label(body, textvariable=self.status, wraplength=860)
        status_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(16, 5))
        note_label = ttk.Label(
            body,
            text="Independent sensitivity envelopes are not confidence intervals. Illustrative yield values are not certified allowables. Geometry changes are manual; no optimization is performed.",
            wraplength=860,
        )
        note_label.grid(row=4, column=0, columnspan=2, sticky="w")
        body.bind(
            "<Configure>",
            lambda event: [
                label.configure(wraplength=max(300, event.width - 40))
                for label in (status_label, note_label)
            ],
        )

        def reveal(event):
            top = event.widget.winfo_rooty() - controls.winfo_rooty()
            bottom = top + event.widget.winfo_height()
            start = self.controls_canvas.canvasy(0)
            height = self.controls_canvas.winfo_height()
            total = max(1, controls.winfo_reqheight())
            if top < start:
                self.controls_canvas.yview_moveto(max(0, top) / total)
            elif bottom > start + height:
                self.controls_canvas.yview_moveto(max(0, bottom - height) / total)

        for item in [
            *self.entries,
            self.bounds_check,
            *[
                child
                for child in controls.winfo_children()
                if isinstance(child, ttk.Button)
            ],
        ]:
            item.bind("<FocusIn>", reveal)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Destroy>", self._destroy)
        self.render()

    def invalidate(self, *_):
        if self.imported:
            return
        self.record = None
        self.save_button.configure(state="disabled")
        if hasattr(self, "canvas"):
            self.metrics.set("Inputs changed. Calculate to refresh results.")
            self.status.set("Ready for a new calculation")
            self.render()

    def run(self):
        if self.imported:
            return
        self.record = None
        self.save_button.configure(state="disabled")
        try:
            values = {
                name: float(variable.get()) for name, variable in self.inputs.items()
            }

            def interval(value, half):
                delta = half if self.dimensions.get() else 0
                return Interval(value, max(0.0, value - delta), value + delta)

            first = GeometryCard(
                interval(values["length"], 0.001),
                interval(values["outside"], 0.0001),
                interval(values["inside"], 0.0001),
            )
            second = GeometryCard(
                first.length_m,
                interval(values["outside_b"], 0.0001),
                first.inside_diameter_m,
            )
            self.record = run_component_comparison(
                first,
                geometry_b=second,
                force_y_n=values["force"],
                torque_x_nm=values["torque"],
            )
            self.show()
        except (ValueError, TypeError, OverflowError) as exc:
            self.metrics.set("No current result")
            self.status.set(str(exc))
            self.render()

    def show(self):
        if self.record is None:
            raise ValueError("no current component result")
        lines = []
        warnings = []
        for key, run in self.record["runs"].items():
            out = run["result"]["nominal"]
            bounds = run["result"]["bounds"]
            lines.extend(
                [
                    f"{key} · mass {out['mass_kg']:.4g} kg · Kb {out['bending_stiffness_n_per_m']:.5g} N/m · Kt {out['torsional_stiffness_nm_per_deg']:.5g} N·m/degree",
                    f"    tip {out['tip_deflection_m'] * 1000:.4g} mm [{bounds['tip_deflection_m']['lower'] * 1000:.4g}, {bounds['tip_deflection_m']['upper'] * 1000:.4g}] · von Mises {out['root_von_mises_pa'] / 1e6:.4g} MPa",
                    f"    centroid Ix {out['centroid_ix_kgm2']:.4g}, Iy = Iz {out['centroid_iy_kgm2']:.4g} kg·m²",
                ]
            )
            warnings.extend(
                key + ": " + warning
                for warning in run["result"]["validity"]["warnings"]
            )
        self.metrics.set("\n".join(lines))
        policy = self.record["geometry_policy"].replace("_", " ")
        self.status.set(
            policy
            + " · "
            + (
                "; ".join(warnings)
                if warnings
                else "All interval corners within declared linear domain"
            )
            + " · "
            + self.record["run_id"][:12]
        )
        self.save_button.configure(state="normal")
        self.render()

    def render(self):
        for axis, label in zip(self.axes, ("Deflection y (mm)", "Twist x (degree)")):
            axis.clear()
            axis.set_xlabel("Span x (m)")
            axis.set_ylabel(label)
            axis.grid(alpha=0.15)
        if self.record:
            for key, run in self.record["runs"].items():
                shape = run["result"]["shape"]
                x = [point["x_m"] for point in shape]
                self.axes[0].plot(
                    x, [point["deflection_y_m"] * 1000 for point in shape], label=key
                )
                self.axes[1].plot(
                    x,
                    [point["twist_x_rad"] * 180 / 3.141592653589793 for point in shape],
                    label=key,
                )
            for axis in self.axes:
                axis.legend()
        self.canvas.draw()

    def save(self):
        if self.record is None:
            return
        name = filedialog.asksaveasfilename(
            parent=self.window,
            defaultextension=".json",
            filetypes=[("Comparison JSON", "*.json")],
        )
        if name:
            self.save_to(Path(name))

    def save_to(self, path: Path):
        if self.record is None:
            raise ValueError("calculate or replay before saving")
        temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
        try:
            temporary.write_text(_canonical_json(self.record) + "\n", encoding="utf-8")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def load(self):
        name = filedialog.askopenfilename(
            parent=self.window, filetypes=[("Comparison JSON", "*.json")]
        )
        if name:
            try:
                self.load_from(Path(name))
            except (OSError, ValueError, TypeError) as exc:
                self.status.set("Could not replay: " + str(exc))

    def load_from(self, path: Path):
        self.new()
        record = load_component_json(path)
        verified = replay_component_comparison(record)
        self.record = record
        self.imported = True
        lines = [
            "Saved configuration · read only",
            "Dimensions in m: nominal [lower, upper]",
        ]
        for key, run in record["runs"].items():
            geometry = run["configuration"]["geometry"]
            lines.append(key + " · " + geometry["card_id"])
            for name, label in (
                ("length_m", "Span"),
                ("outside_diameter_m", "OD"),
                ("inside_diameter_m", "ID"),
            ):
                value = geometry[name]
                lines.append(
                    f"{label} {value['nominal']:.6g} [{value['lower']:.6g}, {value['upper']:.6g}]"
                )
        loads = record["runs"]["A"]["configuration"]["loads"]
        lines.extend(
            [
                f"Fy {loads['force_y_n']:.6g} N",
                f"Mx {loads['torque_x_nm']:.6g} N·m",
                "Material bounds retained in both records.",
            ]
        )
        self.saved_configuration.set("\n".join(lines))
        self.edit_controls.pack_forget()
        self.saved_configuration_label.pack(
            before=self.run_button, fill="x", pady=(0, 12)
        )
        for entry in [*self.entries, self.bounds_check, self.run_button]:
            entry.configure(state="disabled")
        self.show()
        self.status.set(
            "Replayed saved comparison · read only · source "
            + ("matches" if verified["source_agreement"] else "differs")
            + " · "
            + record["run_id"][:12]
        )

    def new(self):
        self.imported = False
        self.saved_configuration_label.pack_forget()
        self.edit_controls.pack(before=self.run_button, fill="x")
        for entry in [*self.entries, self.bounds_check, self.run_button]:
            entry.configure(state="normal")
        self.invalidate()

    def _destroy(self, event):
        if event.widget is self.window:
            self._dispose()

    def _dispose(self):
        if self.closed:
            return
        self.closed = True
        widget = self.canvas.get_tk_widget()
        for attribute in ("_idle_draw_id", "_event_loop_id"):
            identifier = getattr(self.canvas, attribute, None)
            if identifier is not None:
                widget.after_cancel(identifier)
                setattr(self.canvas, attribute, None)
        photo = getattr(self.canvas, "_tkphoto", None)
        if photo is not None and photo.name:
            photo.tk.call("image", "delete", photo.name)
            photo.name = None

    def close(self):
        if not self.closed:
            self._dispose()
            self.window.destroy()
