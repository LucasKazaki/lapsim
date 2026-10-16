"""Optional actual CalculiX 2.23 cantilever refinement; never used at startup."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
from hashlib import sha256
from pathlib import Path

from lapsim.experiments.component_study import MATERIALS, GeometryCard, calculate


def run(executable: Path, output: Path) -> dict:
    executable = executable.resolve(strict=True)
    version_probe = subprocess.run(
        [str(executable), "-v"], capture_output=True, text=True, timeout=10, check=False
    )
    version = version_probe.stdout.strip()
    # This distributed Windows build returns 201 for its successful -v route.
    # Record it; solver jobs below still require zero and completion evidence.
    if version != "This is Version 2.23" or version_probe.returncode not in (0, 201):
        raise ValueError("benchmark requires CalculiX 2.23")
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    failed = False
    for material in MATERIALS.values():
        young, poisson = material.young_pa.nominal, material.poisson.nominal
        expected = calculate(material, GeometryCard(), torque_x_nm=0)["nominal"][
            "tip_deflection_m"
        ]
        for elements in (4, 8, 16, 32, 64, 128):
            row = {
                "material": material.card_id,
                "elements": elements,
                "element": "B32R PIPE",
                "analytic_eb_tip_y_m": expected,
                "command": [executable.name, "-i", "beam"],
                "status": "skipped" if failed else "failed",
                "solve_exit_code": None,
                "timed_out": False,
            }
            rows.append(row)
            if failed:
                row["reason"] = "not started after an earlier failed case"
                continue
            case = output / (material.card_id + "_" + str(elements))
            case.mkdir()
            nodes = [
                f"{i + 1}, {0.6 * i / (2 * elements):.17g}, 0, 0"
                for i in range(2 * elements + 1)
            ]
            members = [
                f"{i + 1}, {2 * i + 1}, {2 * i + 2}, {2 * i + 3}"
                for i in range(elements)
            ]
            tip = 2 * elements + 1
            deck = "\n".join(
                [
                    "*HEADING",
                    "Synthetic SI circular cantilever; mesh refinement, bending only",
                    "*NODE",
                    *nodes,
                    "*ELEMENT,TYPE=B32R,ELSET=BEAM",
                    *members,
                    "*NSET,NSET=ROOT",
                    "1",
                    "*NSET,NSET=TIP",
                    str(tip),
                    "*MATERIAL,NAME=SYNTHETIC",
                    "*ELASTIC",
                    f"{young:.17g}, {poisson:.17g}",
                    "*BEAM SECTION,ELSET=BEAM,MATERIAL=SYNTHETIC,SECTION=PIPE",
                    ".0125, .002",
                    "0,0,-1",
                    "*BOUNDARY",
                    "ROOT,1,6",
                    "*STEP",
                    "*STATIC",
                    "*CLOAD",
                    f"{tip},2,100",
                    "*NODE PRINT,NSET=TIP",
                    "U",
                    "*END STEP",
                    "",
                ]
            )
            path = case / "beam.inp"
            path.write_text(deck, encoding="ascii")
            row["input_sha256"] = sha256(path.read_bytes()).hexdigest()
            try:
                _solve(executable, case, tip, expected, row)
            except (
                OSError,
                ValueError,
                RuntimeError,
                subprocess.TimeoutExpired,
            ) as error:
                row["error"] = f"{type(error).__name__}: {error}"
                failed = True
    summary = {
        "schema": "lapsim.component-fe-benchmark.v1",
        "solver_version": version,
        "version_probe_exit_code": version_probe.returncode,
        "binary_sha256": sha256(executable.read_bytes()).hexdigest(),
        "cases": rows,
        "outcomes": {
            status: sum(row["status"] == status for row in rows)
            for status in ("passed", "failed", "skipped")
        },
        "limits": "Linear bending-only FE comparison, not torsion, material calibration or vehicle correlation; B32R expands to solid elements and includes shear.",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, allow_nan=False))
    if failed:
        raise RuntimeError(
            "CalculiX benchmark failed; inspect summary.json and case logs"
        )
    return summary


def _solve(executable: Path, case: Path, tip: int, expected: float, row: dict) -> None:
    """Retain actual process evidence even when a case cannot yield a result."""
    transcript = ""
    try:
        result = subprocess.run(
            [str(executable), "-i", "beam"],
            cwd=case,
            env=dict(
                os.environ,
                OMP_NUM_THREADS="1",
                OPENBLAS_NUM_THREADS="1",
                CCX_NPROC_RESULTS="1",
            ),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        row["solve_exit_code"] = result.returncode
        transcript = result.stdout + result.stderr
    except subprocess.TimeoutExpired as error:
        row["timed_out"] = True

        def decoded(value):
            return (
                value.decode("utf-8", errors="replace")
                if isinstance(value, bytes)
                else value or ""
            )

        transcript = decoded(error.stdout) + decoded(error.stderr)
        raise
    finally:
        log = case / "solver.log"
        log.write_text(transcript, encoding="utf-8")
        row["log_sha256"] = sha256(log.read_bytes()).hexdigest()
    if result.returncode or "Job finished" not in transcript or "*ERROR" in transcript:
        raise RuntimeError(f"CalculiX failed; inspect {case.name}/solver.log")
    data_path = case / "beam.dat"
    data = data_path.read_text(encoding="ascii")
    row["dat_sha256"] = sha256(data_path.read_bytes()).hexdigest()
    matches = re.findall(
        r"^\s*" + str(tip) + r"\s+([-+\d.Ee]+)\s+([-+\d.Ee]+)\s+([-+\d.Ee]+)\s*$",
        data,
        re.MULTILINE,
    )
    if len(matches) != 1:
        raise ValueError("expected one actual tip displacement row")
    displacement = float(matches[0][1])
    difference = abs(displacement / expected - 1)
    if not math.isfinite(displacement) or not math.isfinite(difference):
        raise ValueError("non-finite solver result")
    row.update(status="passed", fe_tip_y_m=displacement, relative_difference=difference)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ccx", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.ccx, args.output)
