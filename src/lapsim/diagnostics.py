"""Bounded offline startup checks for source, installed and frozen runtimes."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from .resources import _io_path, build_identity, repository_root


def check_runtime(*, desktop: bool = False) -> dict:
    if sys.version_info < (3, 11) or sys.maxsize <= 2**32:
        raise RuntimeError("Use 64-bit Python 3.11 or newer")
    root = repository_root()
    required = (
        "analysis/data/track/gnss_imu_endurance_track.csv",
        "analysis/data/track/gnss_imu_endurance_track.json",
        "docs/simulator_flowchart/index.html",
        "docs/simulator_flowchart/data/source-inventory.js",
        "controller/import-manifest.json",
        "src/lapsim/dynamics/bicycle.py",
        "src/lapsim/dynamics/powered_planar.py",
        "firmware/bench/main.c",
    )
    for name in required:
        if not (root / name).is_file():
            raise RuntimeError("Missing required package resource: " + name)
    spec = importlib.util.spec_from_file_location(
        "lapsim_startup_import_check", root / "scripts/check_controller_import.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Controller inventory verifier is unavailable")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    imported = checker.verify(_io_path(root))
    from .experiments.basic_dynamics import (
        BicycleScenario,
        replay_bicycle_record,
        run_bicycle_scenario,
    )
    from .experiments.control_study import (
        DEFAULT_REQUEST,
        replay_control_comparison,
        run_control_comparison,
        study_scenario,
    )
    from .experiments.dynamics_record import _code_identity

    bicycle = run_bicycle_scenario(BicycleScenario(duration_s=0.1))
    if not replay_bicycle_record(json.loads(json.dumps(bicycle)))["model_agreement"]:
        raise RuntimeError("Bicycle startup replay disagrees")
    comparison = run_control_comparison(
        study_scenario(dict(DEFAULT_REQUEST, duration_s=0.1))
    )
    if (
        replay_control_comparison(json.loads(json.dumps(comparison)))["runs_replayed"]
        != 2
    ):
        raise RuntimeError("Controller startup replay disagrees")
    if desktop:
        from .ui._tk_runtime import configure_tk_libraries

        configure_tk_libraries()
        import tkinter as tk

        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        from matplotlib.figure import Figure

        try:
            window = tk.Tk()
        except tk.TclError as error:
            raise RuntimeError(
                "Tk/display is unavailable; use the headless check or launch from a desktop session"
            ) from error
        try:
            window.withdraw()
            canvas = FigureCanvasTkAgg(Figure(figsize=(1, 1)), master=window)
            canvas.draw()
            window.update_idletasks()
            canvas.get_tk_widget().destroy()
        finally:
            window.destroy()
    build = build_identity()
    return {
        "schema": "lapsim.startup-check.v1",
        "status": "passed",
        "python": sys.version.split()[0],
        "desktop_checked": desktop,
        "packaged_resources": build is not None,
        "resource_layout": (
            "frozen_bundle"
            if getattr(sys, "frozen", False)
            else "installed_bundle"
            if (root / "src/lapsim/resources.py").resolve()
            != Path(__file__).with_name("resources.py").resolve()
            else "source_snapshot"
            if build
            else "source_tree"
        ),
        "source": {
            **_code_identity(),
            "source_sha256": build.get("source_sha256") if build else None,
        },
        "controller_original_files": imported["verified_original_files"],
        "bicycle_run_id": bicycle["run_id"],
        "comparison_run_id": comparison["run_id"],
        "comparison_runs_replayed": 2,
        "optional_backends": "Ordinary startup does not require native compiler/emulator/hardware",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = check_runtime(desktop=args.desktop)
        encoded = json.dumps(result, indent=2) + "\n"
        if args.output:
            args.output.write_text(encoded, encoding="utf-8")
        else:
            print(encoded, end="")
    except (OSError, RuntimeError, ValueError, ImportError) as error:
        parser.exit(2, "LapSim startup check failed: " + str(error) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
