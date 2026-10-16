"""Compile real clock ownership and test source parity plus ABI/domain guards."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from c_parity import ROOT, build_library, find_compiler
from clock_parity import (UINT64_MAX, clock_input, clock_state, clock_policy,
                           main, verify_clock_in_child)
from cycle_clock import CycleClockState


class PortableClockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.compiler = find_compiler()
        except ValueError as exc:
            raise unittest.SkipTest(str(exc)) from exc

    def test_compiled_clock_and_native_final_gate_match_source_owners(self):
        with tempfile.TemporaryDirectory() as directory:
            library, build = build_library(Path(directory), self.compiler)
            result = verify_clock_in_child(library)
            self.assertEqual(build["build_diagnostics"], "")
            self.assertGreaterEqual(result["results"]["direct_cases"], 14000)
            self.assertEqual(result["results"]["stateful_cycles"], 4096)
            self.assertGreaterEqual(result["results"]["composed_cycles"], 8240)
            self.assertGreater(result["results"]["allowed_cycles"], 4000)
            self.assertGreater(result["results"]["held_cycles"], 4000)
            self.assertEqual(set(result["results"]["clock_reasons"]), {"accepted", "invalid_cycle_timestamp",
                "nonmonotonic_cycle_timestamp", "cycle_period_mismatch", "guard_period_mismatch"})
            self.assertEqual(result["boundaries"]["byte_tag_substitutions"], 768)
            self.assertGreater(result["boundaries"]["checks"], 780)
        self.assertFalse(Path(directory).exists())

    def test_receipts_repeat_without_temporary_build_path_or_source_drift(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            paths = [Path(directory)/name for name in ("first.json", "second.json")]
            for path in paths:
                self.assertEqual(main(["--cc", self.compiler, "--output", str(path)]), 0)
            first, second = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
            self.assertEqual(first, second)
            self.assertEqual(first["schema"], "enme408-portable-clock-parity/v1")
            self.assertEqual(first["clock_contract_version"], 1)
            self.assertEqual(first["numeric_contract_version"], 2)
            self.assertTrue(first["repeat_agreement"])

    def test_decoders_never_coerce_or_wrap_unrepresentable_time(self):
        self.assertEqual(clock_input(UINT64_MAX, .05).now_ms, UINT64_MAX)
        self.assertEqual(clock_state(CycleClockState(UINT64_MAX)).previous_tick, UINT64_MAX)
        for tick in (True, "50", 50., None, -1):
            self.assertFalse(clock_input(tick, .05).timestamp_valid)
        with self.assertRaisesRegex(ValueError, "uint64"):
            clock_input(UINT64_MAX+1, .05)
        for tick in (-1, True, 50., UINT64_MAX+1):
            with self.subTest(tick=tick), self.assertRaises(ValueError):
                clock_state(CycleClockState(tick))
        for period in (True, 0, -1, 50., 60001, 2**32):
            with self.subTest(period=period), self.assertRaises(ValueError):
                clock_policy(period)

    def test_source_and_hardlink_outputs_are_rejected_before_native_build(self):
        source = ROOT/"native/torque_clock.c"
        original = source.read_bytes()
        with patch("clock_parity.build_library") as build:
            with self.assertRaises(SystemExit):
                main(["--output", str(source)])
            with tempfile.TemporaryDirectory(dir=source.parent) as directory:
                alias = Path(directory)/"alias.json"
                os.link(source, alias)
                with self.assertRaises(SystemExit):
                    main(["--output", str(alias)])
                self.assertEqual(alias.read_bytes(), original)
            build.assert_not_called()
        self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
