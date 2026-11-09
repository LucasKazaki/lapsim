"""Headless widget/control doubles, not Tk or Windows acceptance."""
import unittest
from unittest.mock import patch

from lapsim.tournament.ui import SessionPanel


class Widget:
    def __init__(self):
        self.options = {}

    def configure(self, **kwargs):
        self.options.update(kwargs)

    def set(self, value):
        self.value = value


class Master:
    def __init__(self):
        self.callbacks, self.cancelled, self.destroyed = [], [], False

    def after(self, ms, callback):
        self.callbacks.append((ms, callback))
        return len(self.callbacks)

    def after_cancel(self, token):
        self.cancelled.append(token)

    def destroy(self):
        self.destroyed = True


class Controller:
    operation = None
    output = None
    state = "idle"
    phase = "idle"
    detail = ""
    stop_requested = None
    progress_ticks = 0
    active = False
    can_continue = False
    close_requested = False
    cleanup_verified = True
    can_close = True

    def start(self, operation):
        self.operation = operation
        self.state, self.active, self.can_close, self.cleanup_verified = "running", True, False, False

    def poll(self):
        pass

    def stop(self):
        self.stop_requested = "user_stop"
        self.state = "stopping"

    def close(self):
        self.close_requested = True
        if self.active:
            self.stop()
        return self.can_close


class UiTests(unittest.TestCase):
    def setUp(self):
        # Exercise actual UI handlers/control rules without pretending these
        # widgets are a real Tcl interpreter or a native lifecycle provider.
        self.panel = SessionPanel.__new__(SessionPanel)
        p = self.panel
        p.master, p.controller, p.initial = Master(), Controller(), object()
        p.source, p.poll_ms, p._after = None, 100, None
        p._initial_used, p._destroyed = False, False
        for name in ("status", "progress", "detail", "start_button", "stop_button", "continue_button", "close_button"):
            setattr(p, name, Widget())

    def test_start_stop_controls_and_visible_pending_cleanup(self):
        p = self.panel
        p.refresh()
        self.assertIn("not launched", p.status.value)
        self.assertEqual(p.start_button.options["state"], "normal")
        p.start()
        self.assertEqual(p.start_button.options["state"], "disabled")
        self.assertEqual(p.stop_button.options["state"], "normal")
        p.stop()
        self.assertIn("cleanup: pending", p.status.value)
        self.assertEqual(p.continue_button.options["state"], "disabled")

    def test_close_keeps_window_and_polling_until_cleanup(self):
        p = self.panel
        p.start()
        p.close()
        self.assertFalse(p.master.destroyed)
        self.assertEqual(p.close_button.options["text"], "Waiting for cleanup")
        p.tick()
        self.assertEqual(len(p.master.callbacks), 1)
        p.controller.active = False
        p.controller.can_close = p.controller.cleanup_verified = True
        p.tick()
        self.assertTrue(p.master.destroyed)
        self.assertEqual(len(p.master.callbacks), 1)

    def test_poll_error_refreshes_blocked_state_and_rearms(self):
        p = self.panel
        p.start()

        def rejected():
            p.controller.state = "blocked"
            raise ValueError("unit native verification refusal")

        with patch.object(p.controller, "poll", side_effect=rejected):
            with self.assertRaisesRegex(ValueError, "verification refusal"):
                p.tick()
        self.assertIn("State: blocked", p.status.value)
        self.assertFalse(p.master.destroyed)
        self.assertEqual(len(p.master.callbacks), 1)

    def test_start_failure_stays_visible_without_retry(self):
        p = self.panel

        def refused(operation):
            p.controller.operation = operation
            p.controller.state = "blocked"
            p.controller.active = True
            p.controller.cleanup_verified = p.controller.can_close = False
            raise RuntimeError("unit uncertain launch")

        with patch.object(p.controller, "start", side_effect=refused):
            with self.assertRaises(RuntimeError):
                p.start()
        self.assertIn("State: blocked", p.status.value)
        self.assertEqual(p.start_button.options["state"], "disabled")
        with self.assertRaises(ValueError):
            p.start()

    def test_missing_fresh_continuation_data_keeps_pause(self):
        p = self.panel
        p.controller.state, p.controller.can_continue = "paused", True
        p.source = lambda previous, output: None
        p.continue_paused()
        self.assertEqual(p.controller.state, "paused")
        self.assertIn("inputs unavailable", p.detail.value)

    def test_primary_native_error_survives_presentation_error(self):
        p = self.panel
        with patch.object(p, "refresh", side_effect=RuntimeError("presentation unavailable")):
            with self.assertRaisesRegex(ValueError, "native failure"):
                p._action(lambda: (_ for _ in ()).throw(ValueError("native failure")))

    def test_continue_launch_failure_refreshes_blocked_controls(self):
        from lapsim.tournament.session import ContinuationOperation
        p = self.panel
        p.controller.state, p.controller.can_continue = "paused", True
        p.source = lambda previous, output: object.__new__(ContinuationOperation)

        def refused(operation):
            p.controller.state = "blocked"
            p.controller.active = True
            p.controller.can_continue = p.controller.cleanup_verified = p.controller.can_close = False
            raise RuntimeError("unit resume launch uncertainty")

        with patch.object(p.controller, "start", side_effect=refused):
            with self.assertRaises(RuntimeError):
                p.continue_paused()
        self.assertIn("State: blocked", p.status.value)
        self.assertEqual(p.continue_button.options["state"], "disabled")


if __name__ == "__main__":
    unittest.main()
