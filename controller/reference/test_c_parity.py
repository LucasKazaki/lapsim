"""Compile the actual C source, compare Python owners, and exercise ABI guards."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from c_parity import ROOT, build_library, find_compiler, main, uint32, verify_in_child


class PortableCParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.compiler = find_compiler()
        except ValueError as exc:
            raise unittest.SkipTest(str(exc)) from exc

    def test_compiled_contract_and_pipeline_parity_plus_abi_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            library, metadata = build_library(Path(directory), self.compiler)
            result = verify_in_child(library)
            self.assertEqual(metadata["build_diagnostics"], "")
            self.assertEqual(result["results"]["allocation_cases"], 2179)
            self.assertEqual(len(result["results"]["allocation_reasons"]), 10)
            self.assertEqual(result["results"]["cycles"], 8210)
            self.assertEqual(result["results"]["held_cycles"], 4142)
            self.assertEqual(result["results"]["allowed_cycles"], 4068)
            self.assertEqual(set(result["results"]["decision_states"]),
                             {"ready", "limited", "inhibited", "recovery_pending"})
            self.assertIn("null_input_initializes_exact_zero", result["boundary_checks"])
            self.assertIn("recovery_streak_overflow_state_4", result["boundary_checks"])
            self.assertIn("none_fault_ignores_buffer", result["boundary_checks"])
            self.assertGreaterEqual(len(result["boundary_checks"]), 30)
        # Windows cleanup succeeding here verifies that no loaded DLL is held
        # by this parent after the finite parity child exits.
        self.assertFalse(Path(directory).exists())

    def test_cli_receipts_repeat_with_identical_results_and_source_identity(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            paths = [Path(directory)/name for name in ("a.json", "b.json")]
            for path in paths:
                self.assertEqual(main(["--cc", self.compiler, "--output", str(path)]), 0)
            a, b = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
            self.assertEqual(a, b)
            self.assertTrue(a["repeat_agreement"])
            self.assertEqual(len(a["source_sha256"]), 19)
            self.assertEqual(a["schema"], "enme408-portable-c-parity/v2")
            self.assertEqual(a["numeric_contract_version"], 2)

    def test_fast_math_build_is_explicitly_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ)
            env["PATH"] = str(Path(self.compiler).parent) + os.pathsep + env.get("PATH", "")
            for flag, message in (("-ffast-math", "Fast-math is incompatible"),
                                  ("-ffinite-math-only", "Finite-math-only is incompatible")):
                for source in ("torque_contract.c", "torque_clock.c", "torque_pedal.c"):
                    result = subprocess.run([self.compiler, "-std=c11", flag, "-c", source,
                                              "-o", str(Path(directory)/"bad.o")], cwd=ROOT/"native", env=env,
                                             capture_output=True, text=True, errors="replace", timeout=30)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(message, result.stderr)

    def test_source_output_alias_is_rejected_before_build_or_write(self):
        source = ROOT/"native/torque_contract.c"
        original = source.read_bytes()
        with patch("c_parity.build_library") as build:
            with self.assertRaises(SystemExit):
                main(["--output", str(source)])
            # A real hardlink must share its source volume. Windows CI keeps
            # the checkout and default temporary directory on different drives.
            with tempfile.TemporaryDirectory(dir=source.parent) as directory:
                alias = Path(directory)/"aliased.json"
                os.link(source, alias)
                with self.assertRaises(SystemExit):
                    main(["--output", str(alias)])
                self.assertEqual(alias.read_bytes(), original)
            build.assert_not_called()
        self.assertEqual(source.read_bytes(), original)

    def test_scalar_counter_adapter_never_silently_wraps_or_coerces(self):
        self.assertEqual(uint32(2**32-1, "counter"), 2**32-1)
        for value in (-1, 2**32, True, "2", 2.):
            with self.subTest(value=value), self.assertRaises(ValueError):
                uint32(value, "counter")
        with patch.dict(os.environ, {"CC": "missing-enme408-compiler"}):
            with self.assertRaisesRegex(ValueError, "was not found"):
                find_compiler()


if __name__ == "__main__":
    unittest.main()
