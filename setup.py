"""Setuptools hooks for a self-contained internal wheel/source distribution."""

import importlib.util
from pathlib import Path

from setuptools import setup

path = Path(__file__).parent / "packaging/build_support.py"
spec = importlib.util.spec_from_file_location("lapsim_build_support", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
setup(
    cmdclass={
        "build": module.ExtendedBuild,
        "install": module.NormalizedInstall,
        "build_py": module.BundledBuildPy,
        "sdist": module.VerifiedSdist,
    }
)
