"""Keyboard and worker scheduling checks without opening a native window."""

import threading
import time
import unittest

from keyboard_view import Controls, ExchangeWorker, _command


class KeyboardControlsTest(unittest.TestCase):
    def setUp(self):
        self.controls = Controls()
        self.controls.focus(True)
        self.controls.resume()

    def test_wasd_and_arrows_have_identical_demand(self):
        for original, alias, field, expected in (
            ("w", "Up", "throttle", 1), ("s", "Down", "brake", 1),
            ("a", "Left", "steering", 1), ("d", "Right", "steering", -1),
        ):
            with self.subTest(key=original):
                self.controls.key(original, True)
                self.assertEqual(self.controls.demand()[field], expected)
                self.controls.key(alias, True)
                self.controls.key(original, False)
                self.assertEqual(self.controls.demand()[field], expected)
                self.controls.key(alias, False)
                self.assertEqual(self.controls.demand(), _command("drive"))

    def test_brake_overrides_throttle_and_opposite_steering_cancels(self):
        for key in ("w", "Down", "a", "Right"):
            self.controls.key(key, True)
        self.assertEqual(self.controls.demand(), _command("drive", brake=1))
        self.controls.key("Down", False)
        self.assertEqual(self.controls.demand(), _command("drive", throttle=1))

    def test_lost_focus_requires_resume_and_drops_held_key_repeats(self):
        self.controls.key("w", True)
        self.assertTrue(self.controls.focus(False))
        self.assertFalse(self.controls.resume())
        self.controls.focus(True)
        self.assertFalse(self.controls.enabled)
        self.assertTrue(self.controls.resume())
        self.controls.key("w", True)  # auto-repeat from before focus loss
        self.assertEqual(self.controls.demand(), _command("drive"))
        self.controls.key("w", False)
        self.controls.key("w", True)
        self.assertEqual(self.controls.demand()["throttle"], 1.0)

    def test_keys_pressed_during_pause_must_be_released(self):
        self.controls.pause()  # used by Reset and Pause
        self.controls.key("a", True)
        self.controls.resume()
        self.controls.key("a", True)
        self.assertEqual(self.controls.demand(), _command("drive"))
        self.controls.key("a", False)
        self.controls.key("a", True)
        self.assertEqual(self.controls.demand()["steering"], 1.0)


class ExchangeWorkerTest(unittest.TestCase):
    def await_result(self, worker):
        deadline = time.monotonic() + 2
        result = worker.result()
        while result is None and time.monotonic() < deadline:
            time.sleep(0.001)
            result = worker.result()
        self.assertIsNotNone(result)
        return result

    def test_in_flight_drive_cancelled_and_no_positive_backlog(self):
        entered, release = threading.Event(), threading.Event()
        calls = []

        def exchange(command):
            kind = command["kind"]
            calls.append((threading.get_ident(), dict(command)))
            if kind == "drive":
                entered.set()
                release.wait(2)
            return kind

        worker = ExchangeWorker(exchange)
        try:
            self.assertTrue(worker.submit(_command("drive", throttle=1.0)))
            self.assertTrue(entered.wait(2))
            self.assertFalse(worker.submit(_command("drive", steering=1.0)))
            self.assertFalse(worker.submit(_command("pause")))
            worker.cancel_drive()
            self.assertTrue(calls[0][1]["cancelled"].is_set())
            release.set()
            self.assertEqual(self.await_result(worker), ("drive", "drive", None))
            self.assertTrue(worker.submit(_command("pause")))
            self.assertEqual(self.await_result(worker), ("pause", "pause", None))
        finally:
            release.set()
            worker.begin_close()
            worker.join()
        self.assertEqual(worker.result(), ("close", "close", None))
        self.assertEqual([command["kind"] for _, command in calls], ["drive", "pause", "close"])
        self.assertEqual(len({thread for thread, _ in calls}), 1)
        self.assertNotEqual(calls[0][0], threading.get_ident())
        self.assertEqual(calls[1][1], _command("pause"))
        self.assertEqual(calls[2][1], _command("close"))

    def test_close_cancels_active_drive_and_refuses_later_commands(self):
        entered = threading.Event()
        calls = []

        def exchange(command):
            calls.append(command)
            if command["kind"] == "drive":
                entered.set()
                return command["cancelled"].wait(2)
            return None

        worker = ExchangeWorker(exchange)
        try:
            self.assertTrue(worker.submit(_command("drive", throttle=1.0)))
            self.assertTrue(entered.wait(2))
            worker.begin_close()
            self.assertFalse(worker.submit(_command("drive", throttle=1.0)))
        finally:
            worker.begin_close()
            worker.join()
        self.assertEqual(worker.result(), ("drive", True, None))
        self.assertEqual(worker.result(), ("close", None, None))
        self.assertEqual(calls[-1], _command("close"))


if __name__ == "__main__":
    unittest.main()
