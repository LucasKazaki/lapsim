"""Actual matched controller studies in a native, cancellable desktop session."""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from tkinter import filedialog, ttk
from uuid import uuid4

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from lapsim.experiments.basic_dynamics import decode_json
from lapsim.experiments.control_study import (
    CASES,
    DEFAULT_REQUEST,
    replay_control_comparison,
    run_control_comparison,
    study_scenario,
)
from lapsim.experiments.dynamics_record import default_dynamics_run_directory


class ControlLab:
    def __init__(self, parent: tk.Misc, *, dark: bool = False):
        self.window = tk.Toplevel(parent)
        self.window.title("LapSim · Rear-drive control study")
        self.window.geometry("1180x820")
        self.window.minsize(840, 700)
        self.closed = False
        self.busy = False
        self.record = None
        self.revision = 0
        self.loading = False
        self.imported = False
        self.dark = dark
        self.results = Queue()
        self.cancelled = Event()
        body = ttk.Frame(self.window, padding=20)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(2, weight=1)
        ttk.Label(
            body, text="Rear-drive control study", font=("Segoe UI", 20, "bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            body,
            text="Compare equal splitting and traction limiting with the same driver, sensors and limits.",
            wraplength=1000,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 18))
        shell = ttk.Frame(body, width=270)
        shell.grid(row=2, column=0, sticky="nsew", padx=(0, 20))
        self.control_canvas = tk.Canvas(
            shell, width=260, highlightthickness=0, takefocus=1
        )
        scrollbar = ttk.Scrollbar(shell, command=self.control_canvas.yview)
        scrollbar.pack(side="right", fill="y")
        self.control_canvas.configure(yscrollcommand=scrollbar.set)
        self.control_canvas.pack(side="left", fill="both", expand=True)
        controls = ttk.Frame(self.control_canvas)
        panel = self.control_canvas.create_window((0, 0), window=controls, anchor="nw")
        controls.bind(
            "<Configure>",
            lambda _event: self.control_canvas.configure(
                scrollregion=self.control_canvas.bbox("all")
            ),
        )
        self.control_canvas.bind(
            "<Configure>",
            lambda event: self.control_canvas.itemconfigure(panel, width=event.width),
        )
        ttk.Label(
            controls,
            text="Four-wheel dynamic plant\nTwo independent rear actuators · synthetic\nBackend: Python reference",
            wraplength=250,
            justify="left",
        ).pack(anchor="w", pady=(0, 18))
        self.case = tk.StringVar(value=CASES[DEFAULT_REQUEST["case_id"]])
        self.inputs = {}
        ttk.Label(controls, text="Scenario").pack(anchor="w")
        self.case_menu = ttk.Combobox(
            controls,
            textvariable=self.case,
            values=tuple(CASES.values()),
            state="readonly",
            width=28,
        )
        self.case_menu.pack(fill="x", pady=(4, 12))
        self.fields: list[ttk.Combobox | ttk.Entry] = [self.case_menu]
        for key, label, default in [
            ("speed_mps", "Starting speed (m/s)", "0"),
            ("steering_deg", "Road-wheel steering (deg)", "0"),
            ("duration_s", "Duration (s)", "1"),
        ]:
            ttk.Label(controls, text=label).pack(anchor="w")
            value = tk.StringVar(value=default)
            self.inputs[key] = value
            field = ttk.Entry(controls, textvariable=value)
            field.pack(fill="x", pady=(4, 12))
            self.fields.append(field)
            value.trace_add("write", self.invalidate)
        self.case.trace_add("write", self.invalidate)
        self.run_button = ttk.Button(
            controls, text="Run matched A/B study", command=self.run
        )
        self.run_button.pack(fill="x", pady=(6, 6))
        self.cancel_button = ttk.Button(
            controls, text="Cancel calculation", command=self.cancel, state="disabled"
        )
        self.cancel_button.pack(fill="x", pady=(0, 12))
        self.save_button = ttk.Button(
            controls, text="Save comparison JSON", command=self.save, state="disabled"
        )
        self.save_button.pack(fill="x", pady=3)
        self.load_button = ttk.Button(
            controls, text="Open and replay JSON", command=self.load
        )
        self.load_button.pack(fill="x", pady=3)
        self.inspect_button = ttk.Button(
            controls,
            text="Inspect stages and provenance",
            command=self.inspect,
            state="disabled",
        )
        self.inspect_button.pack(fill="x", pady=3)
        self.new_button = ttk.Button(controls, text="New preset", command=self.new)
        self.new_button.pack(fill="x", pady=(10, 3))
        ttk.Label(
            controls,
            text="Corner/road/braking presets may supply an initial speed when zero is entered. Inspect every effective value in the record.\n\nThis study does not assert the team car’s motor count or calibration.",
            wraplength=250,
            justify="left",
        ).pack(anchor="w", pady=12)
        for field in (self.control_canvas, *controls.winfo_children()):
            field.bind(
                "<MouseWheel>",
                lambda event: self.control_canvas.yview_scroll(
                    -int(event.delta / 120), "units"
                ),
            )
            field.bind(
                "<FocusIn>",
                lambda event: self.control_canvas.yview_moveto(
                    max(
                        0.0,
                        event.widget.winfo_y() / max(1, controls.winfo_reqheight())
                        - 0.2,
                    )
                ),
            )
        self.figure = Figure(figsize=(8, 6), dpi=100, layout="constrained")
        self.axes = self.figure.subplots(2, 2)
        if dark:
            self.figure.set_facecolor("#18212b")
        self.canvas = FigureCanvasTkAgg(self.figure, master=body)
        self.canvas.get_tk_widget().grid(row=2, column=1, sticky="nsew")
        self.table = ttk.Treeview(
            body, columns=("metric", "A", "B"), show="headings", height=5
        )
        for key, title, width in [
            ("metric", "Metric", 330),
            ("A", "A · Equal split", 170),
            ("B", "B · Traction limited", 170),
        ]:
            self.table.heading(key, text=title)
            self.table.column(key, width=width, stretch=True)
        self.table.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 8))
        self.status = tk.StringVar(
            value="Ready · synthetic comparison; no winner is presumed"
        )
        self.status_label = ttk.Label(body, textvariable=self.status, wraplength=1100)
        self.status_label.grid(row=4, column=0, columnspan=2, sticky="w")
        self.window.bind(
            "<Configure>",
            lambda event: (
                self.status_label.configure(wraplength=max(400, event.width - 40))
                if event.widget == self.window
                else None
            ),
        )
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Destroy>", self._on_destroy, add="+")
        self.poll_id = self.window.after(75, self._poll)
        self._draw()

    def invalidate(self, *args):
        if self.loading:
            return
        self.revision += 1
        self.record = None
        self.imported = False
        self.save_button.configure(state="disabled")
        self.inspect_button.configure(state="disabled")
        self.status.set("Settings changed · run a new matched comparison")
        self._draw()

    def new(self):
        if self.busy:
            return
        self.loading = True
        try:
            self.case.set(CASES["launch"])
            for key, value in self.inputs.items():
                value.set(str(DEFAULT_REQUEST[key]))
        finally:
            self.loading = False
        for field in self.fields:
            field.configure(state="readonly" if field is self.case_menu else "normal")
        self.run_button.configure(state="normal")
        self.invalidate()

    def _start(self, work, *, imported=False):
        if self.busy:
            return
        self.record = None
        self.revision += 1
        revision = self.revision
        self.busy = True
        self.cancelled = Event()
        self.save_button.configure(state="disabled")
        self.inspect_button.configure(state="disabled")
        self.load_button.configure(state="disabled")
        self.run_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.status.set(
            "Replaying imported comparison…"
            if imported
            else "Calculating both controller/plant loops…"
        )
        self._draw()

        def execute():
            try:
                self.results.put((revision, work(), None, imported))
            except Exception as error:  # noqa: BLE001 -- Deliver worker failures to the owning Tk thread.
                self.results.put((revision, None, str(error), imported))

        Thread(target=execute, daemon=True).start()

    def run(self):
        try:
            case = next(key for key, label in CASES.items() if label == self.case.get())
            request = dict(
                case_id=case,
                **{key: float(value.get()) for key, value in self.inputs.items()},
            )
            scenario = study_scenario(request)
        except (ValueError, StopIteration) as error:
            self.status.set("Cannot run: " + str(error))
            return
        self._start(
            lambda: run_control_comparison(scenario, cancel=self.cancelled.is_set)
        )

    def cancel(self):
        self.cancelled.set()
        self.status.set("Cancelling at the next plant boundary…")

    def _poll(self):
        if self.closed:
            return
        try:
            revision, record, error, imported = self.results.get_nowait()
        except Empty:
            pass
        else:
            self.busy = False
            self.cancel_button.configure(state="disabled")
            self.load_button.configure(state="normal")
            self.run_button.configure(state="normal")
            if revision != self.revision:
                self.status.set("Inputs changed · old result discarded")
            elif error:
                if self.imported:
                    self.new()
                self.status.set("Calculation failed: " + error)
            else:
                self.record = record
                self.imported = imported
                self.save_button.configure(state="normal")
                self.inspect_button.configure(state="normal")
                if imported:
                    for field in self.fields:
                        field.configure(state="disabled")
                    self.run_button.configure(state="disabled")
                    self.status.set(
                        "Imported comparison · both stored scenarios replayed; Inspect preserves their exact configuration. Choose New preset to edit."
                    )
                else:
                    source = record["runs"]["A"]["runtime"]["source"]
                    commit = source.get("code_commit")
                    self.status.set(
                        "Completed · Python reference · run "
                        + record["run_id"][:12]
                        + " · source "
                        + (commit[:12] if isinstance(commit, str) else "unavailable")
                        + (" (working changes)" if source.get("dirty_worktree") else "")
                    )
                self._draw()
        self.poll_id = self.window.after(75, self._poll)

    def _draw(self):
        specs = [
            ("World X (m)", "World Y (m)"),
            ("Time (s)", "Forward speed (m/s)"),
            ("Time (s)", "Maximum rear |slip|"),
            ("Time (s)", "Pack draw (J)"),
        ]
        for axis, (x, y) in zip(self.axes.flat, specs):
            axis.clear()
            axis.set_xlabel(x)
            axis.set_ylabel(y)
            axis.grid(alpha=0.2)
            if self.dark:
                axis.set_facecolor("#18212b")
                axis.tick_params(colors="#e7edf3")
                axis.xaxis.label.set_color("#e7edf3")
                axis.yaxis.label.set_color("#e7edf3")
                for spine in axis.spines.values():
                    spine.set_edgecolor("#8190a0")
        self.table.delete(*self.table.get_children())
        if self.record:
            for label, color, style in [
                ("A", "#75bdff" if self.dark else "#0877ce", "-"),
                ("B", "#ffbc80" if self.dark else "#b65400", "--"),
            ]:
                run = self.record["runs"][label]
                rows = run["result"]["observations"]
                times = [r["time_us"] / 1e6 for r in rows]
                values = [
                    (
                        [r["state"]["plant"]["x_m"] for r in rows],
                        [r["state"]["plant"]["y_m"] for r in rows],
                    ),
                    (times, [r["state"]["plant"]["u_mps"] for r in rows]),
                    (
                        times,
                        [
                            max(abs(w["slip_ratio"]) for w in r["plant"]["wheels"][2:])
                            for r in rows
                        ],
                    ),
                    (
                        times,
                        [
                            rows[0]["state"]["pack_energy_j"]
                            - r["state"]["pack_energy_j"]
                            for r in rows
                        ],
                    ),
                ]
                for axis, (x, y) in zip(self.axes.flat, values):
                    axis.plot(x, y, color=color, linestyle=style, label=label)
            self.axes[0, 0].set_aspect("equal", adjustable="datalim")
            for axis in self.axes.flat:
                legend = axis.legend(
                    loc="best",
                    title="A equal · B traction",
                    facecolor="#18212b" if self.dark else "white",
                    labelcolor="#e7edf3" if self.dark else "#172332",
                )
                legend.get_title().set_color("#e7edf3" if self.dark else "#172332")
            for key, title in [
                ("distance_x_m", "World X (m)"),
                ("final_speed_mps", "Final speed (m/s)"),
                ("peak_observed_rear_slip", "Peak observed rear |slip|"),
                ("pack_draw_j", "Pack draw (J)"),
                ("unmet_command_impulse_nm_s", "Unmet command impulse (N·m·s)"),
                (
                    "absolute_contact_force_error_ns",
                    "Raw driver/contact proxy error (N·s)",
                ),
            ]:
                self.table.insert(
                    "",
                    "end",
                    values=(
                        title,
                        *(
                            f"{self.record['metrics'][label][key]:.6g}"
                            for label in ("A", "B")
                        ),
                    ),
                )
        self.canvas.draw_idle()

    def save(self):
        if self.record is None:
            return
        directory = default_dynamics_run_directory().parent / "control_studies"
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self.status.set("Save failed: " + str(error))
            return
        chosen = filedialog.asksaveasfilename(
            parent=self.window,
            initialdir=directory,
            initialfile=self.record["run_id"] + ".json",
            defaultextension=".json",
            filetypes=(("Control comparison", "*.json"),),
        )
        if not chosen:
            return
        path = Path(chosen)
        temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
        try:
            temporary.write_text(
                json.dumps(self.record, allow_nan=False), encoding="utf-8"
            )
            temporary.replace(path)
            self.status.set("Saved · " + path.name)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            self.status.set("Save failed: " + str(error))

    def load(self):
        chosen = filedialog.askopenfilename(
            parent=self.window, filetypes=(("Control comparison", "*.json"),)
        )
        if not chosen:
            return

        def work():
            path = Path(chosen)
            if path.stat().st_size > 40_000_000:
                raise ValueError("comparison exceeds 40 MB")
            record = decode_json(path.read_bytes(), maximum_bytes=40_000_000)
            replay_control_comparison(record)
            return record

        self._start(work, imported=True)

    def inspect(self):
        if self.record is None:
            return
        window = tk.Toplevel(self.window)
        window.title("Control study · stages, assumptions and provenance")
        window.geometry("850x650")
        text = tk.Text(window, wrap="none", padx=16, pady=16, font=("Consolas", 10))
        scroll = ttk.Scrollbar(window, command=text.yview)
        scroll.pack(side="right", fill="y")
        text.configure(yscrollcommand=scroll.set)
        text.pack(fill="both", expand=True)
        text.insert("1.0", json.dumps(self.record, indent=2, allow_nan=False))
        text.configure(state="disabled")

    def _on_destroy(self, event):
        if event.widget is self.window:
            self._dispose()

    def _dispose(self):
        if self.closed:
            return
        self.closed = True
        self.cancelled.set()
        self.window.after_cancel(self.poll_id)
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
        if self.closed:
            return
        self._dispose()
        self.window.destroy()


def main():
    root = tk.Tk()
    root.withdraw()
    lab = ControlLab(root)

    def close():
        lab.close()
        root.destroy()

    lab.window.protocol("WM_DELETE_WINDOW", close)
    root.mainloop()


if __name__ == "__main__":
    main()
