"""Native basic-dynamics session; every new session selects the synthetic bicycle."""

from __future__ import annotations

from dataclasses import asdict, replace
import json
from math import degrees, radians
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from tkinter import filedialog, ttk
from uuid import uuid4

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from lapsim.dynamics.bicycle import MODEL_ID
from lapsim.experiments.basic_dynamics import (
    MAX_RECORD_BYTES,
    BicycleScenario,
    decode_json,
    replay_bicycle_record,
    run_bicycle_scenario,
)
from lapsim.experiments.dynamics_record import default_dynamics_run_directory


class BasicDynamicsLab:
    def __init__(self, parent: tk.Misc) -> None:
        self.window = tk.Toplevel(parent)
        self.window.title("LapSim · Basic dynamics")
        self.window.geometry("1100x760")
        self.window.minsize(760, 620)
        self.closed = False
        self.busy = False
        self.record: dict | None = None
        self.input_revision = 0
        self.applying_record = False
        self.config = BicycleScenario().config
        self.scenario = BicycleScenario()
        self.results: Queue = Queue()
        self.model_id = tk.StringVar(value=MODEL_ID)
        self.status = tk.StringVar(
            value="Ready · synthetic bicycle, Python plant, prescribed contact forces"
        )
        body = ttk.Frame(self.window, padding=20)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(3, weight=1)
        ttk.Label(body, text="Basic dynamics", font=("Segoe UI", 20, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(
            body,
            text="Explore longitudinal, lateral and yaw response on a synthetic vehicle.",
            wraplength=950,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 18))
        shell = ttk.Frame(body, width=275)
        shell.grid(row=2, column=0, rowspan=2, sticky="nsew", padx=(0, 20))
        shell.rowconfigure(0, weight=1)
        shell.columnconfigure(0, weight=1)
        self.control_canvas = tk.Canvas(shell, width=260, highlightthickness=0)
        self.control_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(shell, command=self.control_canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.control_canvas.configure(yscrollcommand=scrollbar.set)
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
        ttk.Label(controls, text="Model").pack(anchor="w")
        self.model_menu = ttk.Combobox(
            controls,
            textvariable=self.model_id,
            values=(MODEL_ID,),
            state="readonly",
            width=28,
        )
        self.model_menu.pack(fill="x", pady=(4, 12))
        ttk.Label(
            controls,
            text="Synthetic bicycle v1\nRWD axle-lumped force input\nController: absent",
            justify="left",
        ).pack(anchor="w", pady=(0, 14))
        self.inputs: dict[str, tk.StringVar] = {}
        for key, label, default in (
            ("speed", "Starting speed (m/s)", "8"),
            ("steer", "Road-wheel steering (deg)", "2.3"),
            ("force", "Rear contact-force request (N)", "200"),
            ("duration", "Duration (s)", "5"),
        ):
            ttk.Label(controls, text=label).pack(anchor="w")
            variable = tk.StringVar(value=default)
            entry = ttk.Entry(controls, textvariable=variable, width=24)
            entry.pack(fill="x", pady=(4, 12))
            self.inputs[key] = variable
            variable.trace_add("write", self._invalidate)
        self.run_button = ttk.Button(controls, text="Run bicycle", command=self.run)
        self.run_button.pack(fill="x", pady=(6, 8))
        self.save_button = ttk.Button(
            controls, text="Save checked record…", command=self.save, state="disabled"
        )
        self.save_button.pack(fill="x", pady=(0, 8))
        self.load_button = ttk.Button(
            controls, text="Load and replay record…", command=self.load
        )
        self.load_button.pack(fill="x", pady=(0, 14))
        ttk.Button(controls, text="Model and run details…", command=self.inspect).pack(
            fill="x", pady=(0, 14)
        )
        ttk.Label(
            controls,
            text="Independent wheel allocation:\nuse the separate Four-wheel lab.",
            wraplength=240,
        ).pack(anchor="w")
        for widget in controls.winfo_children():
            widget.bind(
                "<MouseWheel>",
                lambda event: self.control_canvas.yview_scroll(
                    -int(event.delta / 120), "units"
                ),
            )
            widget.bind(
                "<FocusIn>",
                lambda event: self.control_canvas.yview_moveto(
                    max(
                        0.0,
                        event.widget.winfo_y() / max(1, controls.winfo_reqheight())
                        - 0.2,
                    )
                ),
            )
        self.figure = Figure(figsize=(7, 5), constrained_layout=True)
        self.path_axes = self.figure.add_subplot(2, 1, 1)
        self.yaw_axes = self.figure.add_subplot(2, 1, 2)
        self.canvas = FigureCanvasTkAgg(self.figure, master=body)
        self.canvas.get_tk_widget().grid(row=2, column=1, rowspan=2, sticky="nsew")
        status_label = ttk.Label(body, textvariable=self.status, wraplength=1000)
        status_label.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(16, 8))
        self.assumptions = tk.StringVar(value=self._assumptions_text())
        assumptions_label = ttk.Label(
            body, textvariable=self.assumptions, wraplength=1000
        )
        assumptions_label.grid(row=5, column=0, columnspan=2, sticky="ew")
        for label in (status_label, assumptions_label):
            label.bind(
                "<Configure>",
                lambda event: event.widget.configure(wraplength=max(200, event.width)),
            )
        self._draw()
        self.poll_id = self.window.after(100, self._poll)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

    def _invalidate(self, *_args: object) -> None:
        if self.applying_record:
            return
        self.input_revision += 1
        self.record = None
        if hasattr(self, "save_button"):
            self.save_button.configure(state="disabled")
            self.status.set("Inputs changed · run to calculate these settings")
            self._draw()

    def _assumptions_text(self) -> str:
        c = self.config
        return (
            f"Synthetic: {c.mass_kg:g} kg, Iz {c.yaw_inertia_kgm2:g} kg·m², a/b {c.cg_to_front_axle_m:g}/{c.cg_to_rear_axle_m:g} m; "
            f"axle stiffness {c.front_cornering_stiffness_n_per_rad:g}/{c.rear_cornering_stiffness_n_per_rad:g} N/rad; μ={c.friction_coefficient:g}. "
            "Static loads, forward motion, regularized linear tires. No motor/pack model or car calibration."
        )

    def _draw(self) -> None:
        self.path_axes.clear()
        self.yaw_axes.clear()
        self.path_axes.set(
            xlabel="World X (m)", ylabel="World Y (m)", title="Simulated trajectory"
        )
        self.path_axes.set_aspect("equal", adjustable="datalim")
        self.yaw_axes.set(
            xlabel="Time (s)", ylabel="Yaw rate (rad/s)", title="Dynamic yaw response"
        )
        if self.record is not None:
            result = self.record["result"]
            states = result["states"]
            self.path_axes.plot(
                [state["x_m"] for state in states],
                [state["y_m"] for state in states],
                label="Bicycle",
            )
            self.yaw_axes.plot(
                result["time_s"],
                [state["yaw_rate_rad_s"] for state in states],
                label="Yaw rate",
            )
        for axes in (self.path_axes, self.yaw_axes):
            axes.grid(alpha=0.2)
        self.canvas.draw_idle()

    def _start(self, work) -> None:
        if self.busy:
            return
        self.busy = True
        self.record = None
        for button in (self.run_button, self.save_button, self.load_button):
            button.configure(state="disabled")
        self.status.set("Calculating and checking synthetic bicycle results…")
        self._draw()
        revision = self.input_revision

        def worker() -> None:
            try:
                self.results.put((revision, work(), None))
            except Exception as error:
                self.results.put((revision, None, str(error)))

        Thread(target=worker, daemon=True).start()

    def run(self) -> None:
        try:
            speed, steer, force, duration = (
                float(self.inputs[key].get())
                for key in ("speed", "steer", "force", "duration")
            )
            if not (
                0 <= speed <= 30
                and -15 <= steer <= 15
                and 0 <= force <= 1500
                and 0.1 <= duration <= 10
            ):
                raise ValueError(
                    "Use speed 0–30 m/s, steering ±15°, rear force 0–1500 N and duration 0.1–10 s."
                )
            scenario = replace(
                self.scenario,
                model_id=self.model_id.get(),
                duration_s=duration,
                config=self.config,
                initial_state=replace(self.scenario.initial_state, u_mps=speed),
                controls=replace(
                    self.scenario.controls,
                    steering_angle_rad=radians(steer),
                    rear_force_request_n=force,
                ),
            )
            self._start(lambda: run_bicycle_scenario(scenario))
        except ValueError as error:
            self._invalidate()
            self.status.set(str(error))

    def _poll(self) -> None:
        if self.closed:
            return
        try:
            revision, record, error = self.results.get_nowait()
        except Empty:
            pass
        else:
            self.busy = False
            self.run_button.configure(state="normal")
            self.load_button.configure(state="normal")
            if revision != self.input_revision:
                self.status.set(
                    "Inputs changed during calculation · result discarded; run the current settings"
                )
            elif error:
                self.status.set("Calculation/replay failed: " + error)
            else:
                scenario = BicycleScenario.from_dict(record["scenario"])
                self.scenario = scenario
                self.config = scenario.config
                self.applying_record = True
                try:
                    for key, value in (
                        ("speed", scenario.initial_state.u_mps),
                        ("steer", degrees(scenario.controls.steering_angle_rad)),
                        ("force", scenario.controls.rear_force_request_n),
                        ("duration", scenario.duration_s),
                    ):
                        self.inputs[key].set(str(value))
                finally:
                    self.applying_record = False
                self.assumptions.set(self._assumptions_text())
                self.record = record
                self.save_button.configure(state="normal")
                identity = record["runtime"]["source"]
                commit = identity.get("code_commit")
                source = commit[:12] if isinstance(commit, str) else "unavailable"
                self.status.set(
                    f"Completed · {record['scenario']['model_id']} · run {record['run_id'][:12]} · source {source}"
                    + (" (working changes)" if identity.get("dirty_worktree") else "")
                )
                self._draw()
        self.poll_id = self.window.after(100, self._poll)

    def save(self) -> None:
        if self.record is None:
            return
        directory = default_dynamics_run_directory().parent / "basic_dynamics_runs"
        directory.mkdir(parents=True, exist_ok=True)
        chosen = filedialog.asksaveasfilename(
            parent=self.window,
            initialdir=directory,
            initialfile=f"{self.record['run_id']}.json",
            defaultextension=".json",
            filetypes=(("Bicycle run", "*.json"),),
        )
        if chosen:
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

    def load(self) -> None:
        chosen = filedialog.askopenfilename(
            parent=self.window, filetypes=(("Bicycle run", "*.json"),)
        )
        if chosen:

            def work() -> dict:
                path = Path(chosen)
                if path.stat().st_size > MAX_RECORD_BYTES:
                    raise ValueError("record exceeds 20 MB")
                record = decode_json(path.read_bytes())
                replay_bicycle_record(record)
                return record

            self._start(work)

    def inspect(self) -> None:
        window = tk.Toplevel(self.window)
        window.title("Bicycle · model and run details")
        window.geometry("760x600")
        text = tk.Text(window, wrap="word", padx=16, pady=16, font=("Consolas", 10))
        scroll = ttk.Scrollbar(window, command=text.yview)
        scroll.pack(side="right", fill="y")
        text.configure(yscrollcommand=scroll.set)
        text.pack(fill="both", expand=True)
        value = (
            self.record
            if self.record is not None
            else {
                "reference_scenario": asdict(self.scenario),
                "note": "No current calculated result; edited controls must be run before saving.",
            }
        )
        text.insert(
            "1.0", json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)
        )
        text.configure(state="disabled")

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.window.after_cancel(self.poll_id)
        # Tk owns these scheduled commands on the canvas widget. Cancel them
        # before destroying that widget so a pending redraw cannot outlive it.
        widget = self.canvas.get_tk_widget()
        for attribute in ("_idle_draw_id", "_event_loop_id"):
            identifier = getattr(self.canvas, attribute, None)
            if identifier is not None:
                widget.after_cancel(identifier)
                setattr(self.canvas, attribute, None)
        self.window.destroy()


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    lab = BasicDynamicsLab(root)

    def close() -> None:
        lab.close()
        root.destroy()

    lab.window.protocol("WM_DELETE_WINDOW", close)
    root.mainloop()


if __name__ == "__main__":
    main()
