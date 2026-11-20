"""Native keyboard and course view for the local Light simulator."""

import math
import threading
import time
from collections import deque


_KEYS = {
    "w": "throttle", "up": "throttle",
    "s": "brake", "down": "brake",
    "a": "left", "left": "left",
    "d": "right", "right": "right",
}


def _command(kind, steering=0.0, throttle=0.0, brake=0.0):
    return dict(kind=kind, steering=steering, throttle=throttle, brake=brake)


class Controls:
    """Current physical key state, owned by the Tk event loop."""

    def __init__(self):
        self.focused = False
        self.enabled = False
        self.held = set()
        self.suppressed = set()

    def pause(self):
        self.suppressed.update(self.held)
        self.held.clear()
        self.enabled = False

    def focus(self, focused):
        lost = self.focused and not focused
        self.focused = focused
        if lost:
            self.pause()
        return lost

    def resume(self):
        self.pause()
        self.enabled = self.focused
        return self.enabled

    def key(self, keysym, down):
        key = keysym.lower()
        if key not in _KEYS:
            return False
        if not down:
            self.held.discard(key)
            self.suppressed.discard(key)
        elif not self.focused or not self.enabled:
            self.suppressed.add(key)
        elif key not in self.suppressed:
            self.held.add(key)
        return True

    def demand(self):
        active = {_KEYS[key] for key in self.held}
        brake = "brake" in active
        return _command(
            "drive", float(("left" in active) - ("right" in active)),
            float("throttle" in active and not brake), float(brake),
        )


class ExchangeWorker:
    """One owner thread, one exchange at a time and no positive backlog."""

    def __init__(self, exchange):
        self._exchange = exchange
        self._condition = threading.Condition()
        self._pending = None
        self._active = None
        self._results = deque()
        self._closing = False
        self._thread = threading.Thread(target=self._run, name="Light demo driver")
        self._thread.start()

    def submit(self, command):
        with self._condition:
            if self._closing or self._pending or self._active or self._results:
                return False
            if command["kind"] == "drive":
                command = dict(command, cancelled=threading.Event())
            self._pending = command
            self._condition.notify()
            return True

    def cancel_drive(self):
        with self._condition:
            self._cancel_drive_locked()

    def _cancel_drive_locked(self):
        if self._pending and self._pending["kind"] == "drive":
            self._pending["cancelled"].set()
            self._pending = None
        if self._active and self._active["kind"] == "drive":
            self._active["cancelled"].set()

    def begin_close(self):
        with self._condition:
            self._cancel_drive_locked()
            self._pending = None
            self._closing = True
            self._condition.notify()

    def result(self):
        with self._condition:
            return self._results.popleft() if self._results else None

    def join(self):
        self._thread.join()

    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closing or self._pending)
                command = _command("close") if self._closing else self._pending
                self._pending = None
                self._active = command
            try:
                pose = self._exchange(command)
                error = None
            except Exception as exc:
                pose, error = None, str(exc) or type(exc).__name__
            with self._condition:
                self._active = None
                self._results.append((command["kind"], pose, error))
            if command["kind"] == "close":
                return


class KeyboardView:
    """Tk displays accepted plant poses. The worker alone calls exchange."""

    def __init__(self, root, geometry, initial, exchange, startup_notice):
        import tkinter as tk
        from tkinter import ttk

        self.root = root
        self.pose = initial
        self.controls = Controls()
        self.worker = None
        self.pending = None
        self.resetting = False
        self.closing = False
        self.close_error = None
        self.startup_notice = startup_notice
        self.anchor = None
        self.last_drive = float("-inf")
        self.shortcut_holds = set()
        self.segments = tuple(zip(geometry["centerline"], geometry["centerline"][1:]))
        self.cones = tuple((cone["x"], cone["y"], self._cone_color(cone["side"]))
                           for cone in geometry["cones"])
        self.start = geometry["start"]
        self.bounds = self._course_bounds(geometry["centerline"])
        self.trail = deque(maxlen=220)
        self.dirty = True
        self.terminal = False
        self.error = None

        root.title("Formula SAE | Light simulator")
        root.configure(background="#111b24")
        root.geometry("1160x760")
        root.minsize(850, 550)

        def label(parent, text, size, color="#e6f1f7", bold=False):
            font = ("Segoe UI", size, "bold" if bold else "normal")
            return tk.Label(parent, text=text, bg="#111b24", fg=color, font=font,
                            anchor="w", justify="left")

        header = tk.Frame(root, bg="#111b24", padx=18, pady=12)
        header.pack(fill="x")
        label(header, "Synthetic stadium", 23, bold=True).pack(anchor="w")
        label(header, "Light physics  /  Single-motor RWD", 11, "#97baca").pack(anchor="w")

        body = tk.Frame(root, bg="#111b24", padx=18)
        body.pack(fill="both", expand=True)
        self.track = tk.Canvas(body, background="#17252e", highlightthickness=0)
        self.track.pack(side="left", fill="both", expand=True)
        panel = tk.Frame(body, bg="#111b24", width=255, padx=14)
        panel.pack(side="right", fill="y")
        panel.pack_propagate(False)

        self.status = label(panel, "", 11, "#76dfcb", bold=True)
        self.status.configure(wraplength=224)
        self.status.pack(fill="x", pady=(3, 0))
        self.speed = label(panel, "", 22, bold=True)
        self.speed.pack(fill="x", pady=(5, 0))
        self.telemetry = label(panel, "", 10, "#bbd2de")
        self.telemetry.pack(fill="x", pady=(0, 10))
        label(panel, "Full course", 10, "#97baca", bold=True).pack(fill="x")
        self.map = tk.Canvas(panel, background="#17252e", height=155, highlightthickness=0)
        self.map.pack(fill="x", pady=(4, 10))
        self.drive_button = ttk.Button(panel, text="Drive (Space)", command=self.toggle_drive)
        self.drive_button.pack(fill="x", pady=(0, 5))
        self.reset_button = ttk.Button(panel, text="Reset car (R)", command=self.reset)
        self.reset_button.pack(fill="x")
        label(panel, "W / ↑  Throttle     S / ↓  Brake\nA / ←  Left             D / →  Right",
              10, "#bbd2de").pack(fill="x", pady=(10, 0))

        footer = tk.Frame(root, bg="#111b24", padx=18, pady=10)
        footer.pack(fill="x")
        label(footer, "Generated synthetic stadium · Generated cones · "
                      "Uncalibrated car model", 10, "#bbd2de").pack(anchor="w")
        label(footer, "Focus loss pauses driving and clears held inputs.", 9, "#97baca").pack(anchor="w")

        root.bind("<KeyPress>", self.key_down)
        root.bind("<KeyRelease>", self.key_up)
        for button in (self.drive_button, self.reset_button):
            # Our Space shortcut wins over a focused ttk button's class binding.
            button.bind("<KeyPress>", self.key_down)
            button.bind("<KeyRelease>", self.key_up)
        root.bind("<FocusOut>", lambda event: root.after_idle(self.check_focus))
        root.bind("<FocusIn>", lambda event: root.after_idle(self.check_focus))
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.track.bind("<Configure>", self.invalidate)
        self.map.bind("<Configure>", self.invalidate)
        self._map_size = None
        if not startup_notice:
            self.worker = ExchangeWorker(exchange)
        root.after(0, self.tick)

    @staticmethod
    def _course_bounds(points):
        xs, ys = zip(*points)
        return min(xs), min(ys), max(xs), max(ys)

    @staticmethod
    def _cone_color(side):
        return {"left": "#62b8ff", "blue": "#62b8ff", "right": "#ffcf62",
                "yellow": "#ffcf62"}.get(str(side).lower(), "#f69b68")

    def invalidate(self, _event=None):
        self.dirty = True

    def check_focus(self):
        if self.closing:
            return
        widget = self.root.focus_displayof()
        focused = bool(widget is not None and widget.winfo_toplevel() == self.root
                       and self.root.state() != "iconic")
        if self.controls.focus(focused) and self.worker:
            self._pause()

    def key_down(self, event):
        key = event.keysym.lower()
        if key in ("space", "r"):
            if key not in self.shortcut_holds:
                self.shortcut_holds.add(key)
                self.reset() if key == "r" else self.toggle_drive()
            return "break"
        return self._set_key(key, True)

    def key_up(self, event):
        key = event.keysym.lower()
        if key in ("space", "r"):
            self.shortcut_holds.discard(key)
            return "break"
        return self._set_key(key, False)

    def _set_key(self, key, down):
        before = self.controls.demand()
        self.check_focus()
        if self.controls.key(key, down):
            if self.worker and before != self.controls.demand():
                self.worker.cancel_drive()
            return "break"
        return None

    def toggle_drive(self):
        if not self.worker or self.closing or self.resetting or self.terminal:
            return
        self.check_focus()
        if self.controls.enabled:
            self._pause()
        elif self.controls.resume():
            self.anchor = self.pose["sim_s"], time.monotonic()

    def _pause(self):
        self.controls.pause()
        self.worker.cancel_drive()
        if not self.resetting:
            self.pending = "pause"

    def reset(self):
        if not self.worker or self.closing or self.resetting:
            return
        self.controls.pause()
        self.worker.cancel_drive()
        self.pending = "reset"
        self.resetting = True

    def close(self):
        if not self.closing:
            self.closing = True
            self.controls.pause()
            if self.worker:
                self.worker.begin_close()
            else:
                self.root.destroy()

    def tick(self):
        if self.worker:
            result = self.worker.result()
            if result:
                kind, pose, error = result
                if kind == "close":
                    self.close_error = error
                    self.root.destroy()
                    return
                self._accept(kind, pose, error)
            if not self.closing:
                self.check_focus()
                now = time.monotonic()
                if self.pending:
                    if self.worker.submit(_command(self.pending)):
                        self.pending = None
                elif self.controls.enabled and now - self.last_drive >= 0.05:
                    if self.worker.submit(self.controls.demand()):
                        self.last_drive = now
        self._update_hud()
        if self.dirty:
            self._draw()
            self.dirty = False
        self.root.after(8, self.tick)

    def _accept(self, kind, pose, error):
        if kind == "reset":
            self.resetting = False
            self.anchor = None
            self.trail.clear()
            self.terminal = False
            self.error = None
        if error is not None:
            self.error = error
            self.controls.pause()
            self.terminal = True
            if kind != "pause" and not self.resetting:
                self.pending = "pause"
        elif pose is not None:
            if pose["sim_s"] > self.pose["sim_s"]:
                self.trail.append((pose["x"], pose["y"]))
            self.pose = pose
            self.dirty = True
            reason = pose.get("reason")
            if reason and reason not in {"ready", "paused", "running", "driving", "reset"}:
                self.terminal = True
                self.controls.pause()

    def _update_hud(self):
        pose = self.pose
        rate = None
        if self.anchor and self.controls.enabled:
            sim, start = self.anchor
            elapsed = time.monotonic() - start
            if elapsed >= 0.5:
                rate = max(0.0, pose["sim_s"] - sim) / elapsed
        if self.closing:
            status = "Closing simulator…"
        elif self.startup_notice:
            status = self.startup_notice
        elif self.error:
            status = f"Paused · {self.error}"
        elif self.terminal:
            status = f"{str(pose['reason']).replace('_', ' ').capitalize()} · Reset to drive"
        elif self.resetting:
            status = "Resetting…"
        elif self.controls.enabled:
            status = "Driving" if rate is None or rate >= 0.85 else "Driving · Slow motion"
        else:
            status = "Paused · Press Space to drive"
        demand = self.controls.demand()
        timing = f"{rate:.2f}× sim/wall" if rate is not None else ""
        self.status.configure(text=status)
        self.speed.configure(text=f"{pose['speed_mps'] * 3.6:.1f} km/h")
        self.telemetry.configure(text=(f"{pose['speed_mps']:.2f} m/s   {pose['sim_s']:.2f} s sim\n"
                                       f"Applied steer {math.degrees(pose['steer_rad']):+.1f}°\n"
                                       f"Requested throttle {demand['throttle']:.0%}\n"
                                       f"Requested brake {demand['brake']:.0%}\n{timing}"))
        locked = not self.worker or self.closing
        self.drive_button.configure(text="Pause (Space)" if self.controls.enabled else "Drive (Space)",
                                    state="disabled" if locked or self.resetting or self.terminal else "normal")
        self.reset_button.configure(state="disabled" if locked or self.resetting else "normal")

    def _draw(self):
        canvas = self.track
        canvas.delete("all")
        w, h = canvas.winfo_width(), canvas.winfo_height()
        pose = self.pose
        px, py = pose["x"], pose["y"]
        scale = max(4.0, min(w / 55, h / 41))

        def local(x, y):
            return w * 0.5 + (x - px) * scale, h * 0.53 - (y - py) * scale

        limits = (px - w / scale, py - h / scale, px + w / scale, py + h / scale)
        self._draw_course(canvas, local, limits)
        if len(self.trail) > 1:
            canvas.create_line(*(coord for x, y in self.trail for coord in local(x, y)),
                               fill="#72dccc", width=2)
        self._draw_car(canvas, local, max(6, scale * 0.75))
        canvas.create_line(18, h - 22, 18 + 5 * scale, h - 22, fill="#c3d6e0", width=2)
        canvas.create_text(18, h - 29, text="5 m", fill="#c3d6e0", anchor="sw")
        canvas.create_text(w - 13, h - 15, text="Car icon enlarged", fill="#c3d6e0", anchor="se")

        mini = self.map
        mw, mh = mini.winfo_width(), mini.winfo_height()
        minx, miny, maxx, maxy = self.bounds
        ratio = min(max(1, mw - 24) / max(1, maxx - minx),
                    max(1, mh - 24) / max(1, maxy - miny))

        def fit(x, y):
            return mw * 0.5 + (x - (minx + maxx) * 0.5) * ratio, mh * 0.5 - (y - (miny + maxy) * 0.5) * ratio

        if self._map_size != (mw, mh):
            self._map_size = mw, mh
            mini.delete("all")
            self._draw_course(mini, fit, None)
        mini.delete("car")
        mx, my = fit(px, py)
        mini.create_oval(mx - 4, my - 4, mx + 4, my + 4, fill="#72dccc", outline="white", tags="car")

    def _draw_course(self, canvas, project, limits):
        line = []
        for a, b in self.segments:
            if limits and (max(a[0], b[0]) < limits[0] or min(a[0], b[0]) > limits[2]
                           or max(a[1], b[1]) < limits[1] or min(a[1], b[1]) > limits[3]):
                if line:
                    canvas.create_line(*line, fill="#658395", width=1, dash=(4, 4))
                    line.clear()
                continue
            if not line:
                line.extend(project(*a))
            line.extend(project(*b))
        if line:
            canvas.create_line(*line, fill="#658395", width=1, dash=(4, 4))
        if limits:
            for x, y, color in self.cones:
                if limits[0] <= x <= limits[2] and limits[1] <= y <= limits[3]:
                    cx, cy = project(x, y)
                    canvas.create_polygon(cx, cy - 4, cx - 4, cy + 3, cx + 4, cy + 3, fill=color)
        sx, sy = project(*self.start)
        canvas.create_rectangle(sx - 3, sy - 3, sx + 3, sy + 3, fill="#fff", outline="")
        canvas.create_text(sx + 7, sy - 4, text="Start", fill="#d2e4ed", anchor="sw")

    def _draw_car(self, canvas, project, radius):
        x, y = project(self.pose["x"], self.pose["y"])
        heading = self.pose["heading"]
        cos, sin = math.cos(heading), math.sin(heading)
        points = []
        for front, left in ((1.25, 0), (0.22, 0.62), (-0.9, 0.5), (-0.9, -0.5), (0.22, -0.62)):
            points.extend((x + radius * (front * cos - left * sin),
                           y - radius * (front * sin + left * cos)))
        canvas.create_polygon(*points, fill="#72dccc", outline="#e6fffa", width=2)


def run(geometry, initial, exchange, *, startup_notice=None, on_ready=None):
    """Open the native demo until closed. All exchanges occur on its worker."""
    import tkinter as tk

    root = tk.Tk()
    view = KeyboardView(root, geometry, initial, exchange, startup_notice)
    if on_ready is not None:
        root.after_idle(lambda: on_ready(view))
    try:
        root.mainloop()
    finally:
        if view.worker:
            view.worker.begin_close()
            view.worker.join()
    if view.close_error:
        raise RuntimeError(view.close_error)
    return view.pose
