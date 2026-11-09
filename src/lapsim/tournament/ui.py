"""Tk controls for the bounded session controller; requires a real native host.

Importing this module creates no window or worker. The native bootstrap supplies
the controller and exact operation; no provider discovery or Start fallback.
"""
from .session import ContinuationOperation


class SessionPanel:
    """Actual Start/Stop/Continue/status UI. Close keeps polling until cleanup.

    continuation_source(previous_operation, output) supplies a fresh *data*
    proposal. The original host still authenticates/admit it. It must be bounded
    and nonblocking; it may return None when fresh admission inputs are absent.
    Exceptions intentionally propagate to the host application. Native fatal
    enforcement belongs inside its original lease, not Tk's exception handler.
    """
    def __init__(self, master, controller, initial_operation, *, continuation_source=None, poll_ms=100):
        from tkinter import StringVar, ttk
        if type(poll_ms) is not int or not 20 <= poll_ms <= 1000:
            raise ValueError("Bounded UI poll interval required")
        self.master, self.controller, self.initial = master, controller, initial_operation
        self.source, self.poll_ms, self._after = continuation_source, poll_ms, None
        self._initial_used, self._destroyed = False, False
        plan, _ = initial_operation.validate()
        first = plan["cells"][0]
        self.frame = ttk.Frame(master, padding=12)
        self.frame.pack(fill="both", expand=True)
        ttk.Label(self.frame, text="Light tournament — bounded serial session").pack(anchor="w")
        ttk.Label(self.frame, text=f"Selected: {first['policy_id']} / {first['origin']['checkpoint']['context']['course']['id']}").pack(anchor="w")
        ttk.Label(self.frame, text="One selected cell; six unrun. RAW development output; no winner or official points.").pack(anchor="w")
        self.status, self.progress, self.detail = StringVar(master), StringVar(master), StringVar(master)
        for variable in (self.status, self.progress, self.detail):
            ttk.Label(self.frame, textvariable=variable, wraplength=680).pack(anchor="w")
        buttons = ttk.Frame(self.frame)
        buttons.pack(anchor="w", pady=8)
        self.start_button = ttk.Button(buttons, text="Start one chunk", command=self.start)
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.stop)
        self.continue_button = ttk.Button(buttons, text="Continue paused chunk", command=self.continue_paused)
        self.close_button = ttk.Button(buttons, text="Close", command=self.close)
        for button in (self.start_button, self.stop_button, self.continue_button, self.close_button):
            button.pack(side="left", padx=4)
        master.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        self._schedule()

    def start(self):
        if self._initial_used:
            raise ValueError("Initial operation consumed; no implicit restart")
        self._initial_used = True
        self._action(lambda: self.controller.start(self.initial))

    def stop(self):
        self._action(self.controller.stop)

    def continue_paused(self):
        return self._action(self._continue_paused)

    def _continue_paused(self):
        if not self.controller.can_continue or self.source is None:
            raise ValueError("Authenticated paused output and fresh continuation inputs required")
        operation = self.source(self.controller.operation, self.controller.output)
        if operation is None:
            self.controller.detail = "Fresh continuation admission inputs unavailable; paused output retained"
        else:
            if type(operation) is not ContinuationOperation:
                raise ValueError("Exact continuation proposal required")
            self.controller.start(operation)

    def close(self):
        if self._action(self.controller.close):
            self._destroy()

    def _action(self, action):
        try:
            result = action()
        except BaseException:
            # Keep the original native/control failure, even if presentation
            # itself is unavailable while the window is closing.
            try:
                self.refresh()
            except Exception:
                pass
            raise
        self.refresh()
        return result

    def _destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        if self._after is not None:
            self.master.after_cancel(self._after)
            self._after = None
        self.master.destroy()

    def refresh(self):
        c = self.controller
        cleanup = "not launched" if c.operation is None else "verified" if c.cleanup_verified else "pending"
        eligibility = "not applicable" if c.state != "paused" else "verified for proposal" if c.paused_continuation_eligible else "not verified"
        self.status.set(f"State: {c.state}; phase: {c.phase}; cleanup: {cleanup}; Stop request: {c.stop_requested or 'none'}; paused continuation: {eligibility}")
        self.progress.set(f"Observed accepted/progress ticks: {c.progress_ticks}")
        self.detail.set(c.detail)
        self.start_button.configure(state="normal" if not self._initial_used and not c.active and not c.close_requested else "disabled")
        self.stop_button.configure(state="normal" if c.active and c.state != "stopping" else "disabled")
        self.continue_button.configure(state="normal" if c.can_continue and self.source is not None else "disabled")
        self.close_button.configure(text="Waiting for cleanup" if c.close_requested and not c.can_close else "Close")

    def _schedule(self):
        if not self._destroyed:
            self._after = self.master.after(self.poll_ms, self.tick)

    def tick(self):
        self._after = None
        # Preserve polling after a reportable callback error: never abandon an
        # owned handle just because presentation/status validation failed.
        try:
            self._action(self.controller.poll)
            if self.controller.close_requested and self.controller.can_close:
                self._destroy()
        finally:
            self._schedule()


def run_session_window(controller, initial_operation, *, continuation_source=None):
    """Native-bootstrap callable UI entry; no command-line native host is installed."""
    import tkinter as tk
    root = tk.Tk()
    root.title("Light EV tournament")
    panel = SessionPanel(root, controller, initial_operation, continuation_source=continuation_source)
    root.mainloop()
    return panel
