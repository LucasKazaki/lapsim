"""Real compiled metadata adapters; source owners remain the parity authority."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from c_parity import ROOT, build_library, find_compiler
from pedal_parity import boolean, facts, main, ordinary, verify_in_child


class PortablePedalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.compiler = find_compiler()
        except ValueError as exc:
            raise unittest.SkipTest(str(exc)) from exc

    def test_compiled_predicates_and_adapters_match_actual_source_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            library, build = build_library(Path(directory), self.compiler)
            result = verify_in_child(library)
            self.assertEqual(build["build_diagnostics"], "")
            self.assertEqual(result["results"]["predicate_cases"], 2774)
            self.assertEqual(result["results"]["source_adapter_cases"], 2559)
            self.assertGreaterEqual(result["results"]["adapter_vetoes"], 172)
            self.assertEqual(result["results"]["composed_cycles"], 8248)
            self.assertEqual(result["results"]["allowed_cycles"], 4087)
            self.assertEqual(result["results"]["held_cycles"], 4161)
            self.assertGreater(result["boundaries"]["checks"], 5000)
        self.assertFalse(Path(directory).exists())

    def test_complete_receipts_repeat_with_identical_build_and_results(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            paths = [Path(directory)/name for name in ("a.json", "b.json")]
            for path in paths:
                self.assertEqual(main(["--cc", self.compiler, "--output", str(path)]), 0)
            a, b = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
            self.assertEqual(a, b)
            self.assertEqual(a["pedal_adapter_version"], 1)
            self.assertTrue(a["repeat_agreement"])

    def test_boolean_adapter_never_coerces_arbitrary_values(self):
        class Trap:
            def __bool__(self):
                raise AssertionError("custom bool conversion must not run")
            def __float__(self):
                raise AssertionError("custom numeric conversion must not run")
        self.assertEqual(boolean(False), 0)
        self.assertEqual(boolean(True), 1)
        for value in (0, 1, None, "true", Trap()):
            self.assertEqual(boolean(value), 2)
        candidate, inp, cfg, state, result = ordinary()
        from dataclasses import replace
        packed = facts(candidate, replace(inp, accelerator_fraction=Trap(), brake_active=Trap()), cfg, state, result)
        self.assertEqual(packed.accelerator.numeric, 0)
        self.assertEqual(packed.brake, 2)

    def test_source_aliases_are_rejected_before_build_and_write(self):
        source = ROOT/"native/torque_pedal.c"
        original = source.read_bytes()
        with patch("pedal_parity.build_library") as build:
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


if __name__ == "__main__": unittest.main()
