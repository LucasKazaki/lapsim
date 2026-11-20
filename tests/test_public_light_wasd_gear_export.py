"""Exercise the isolated, synthetic Light archive without running a plant."""

import json
import subprocess
import sys
import unittest
from pathlib import Path


ARCHIVE = (
    Path(__file__).resolve().parents[1]
    / "research"
    / "light"
    / "public-light-wasd-gear-ab-20261119"
)


class TestPublicLightArchive(unittest.TestCase):
    def check_family(self, family: str) -> None:
        # A fresh isolated process prevents imports from another family or the
        # installed active simulator. The validator verifies every pinned file.
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                str(ARCHIVE / "validate_public.py"),
                family,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["family"], family)
        self.assertIs(result["zero_physics_ticks"], True)
        self.assertEqual(result["native_launches"], 0)
        self.assertEqual(result["source_imports"], 32)
        self.assertEqual(result["keyboard_tests"], 6 if family == "manual" else 0)

    def test_manual(self) -> None:
        self.check_family("manual")

    def test_gear_96(self) -> None:
        self.check_family("drag96")

    def test_gear_91(self) -> None:
        self.check_family("drag91")


if __name__ == "__main__":
    unittest.main()
