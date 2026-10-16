"""Optional actual CalculiX 2.23 cantilever refinement; never used at startup."""

from __future__ import annotations

import argparse
import json
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
    for material in MATERIALS.values():
        young, poisson = material.young_pa.nominal, material.poisson.nominal
        expected = calculate(material, GeometryCard(), torque_x_nm=0)["nominal"][
            "tip_deflection_m"
        ]
        for elements in (4, 8, 16, 32, 64, 128):
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
            command = [str(executable), "-i", "beam"]
            result = subprocess.run(
                command,
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
            transcript = result.stdout + result.stderr
            (case / "solver.log").write_text(transcript, encoding="utf-8")
            if (
                result.returncode
                or "Job finished" not in transcript
                or "*ERROR" in transcript
            ):
                raise RuntimeError(f"CalculiX failed; inspect {case.name}/solver.log")
            data = (case / "beam.dat").read_text(encoding="ascii")
            matches = re.findall(
                r"^\s*"
                + str(tip)
                + r"\s+([-+\d.Ee]+)\s+([-+\d.Ee]+)\s+([-+\d.Ee]+)\s*$",
                data,
                re.MULTILINE,
            )
            if len(matches) != 1:
                raise ValueError("expected one actual tip displacement row")
            displacement = float(matches[0][1])
            rows.append(
                {
                    "material": material.card_id,
                    "elements": elements,
                    "element": "B32R PIPE",
                    "analytic_eb_tip_y_m": expected,
                    "fe_tip_y_m": displacement,
                    "relative_difference": abs(displacement / expected - 1),
                    "command": [executable.name, "-i", "beam"],
                    "input_sha256": sha256(path.read_bytes()).hexdigest(),
                    "dat_sha256": sha256((case / "beam.dat").read_bytes()).hexdigest(),
                    "log_sha256": sha256(
                        (case / "solver.log").read_bytes()
                    ).hexdigest(),
                }
            )
    summary = {
        "schema": "lapsim.component-fe-benchmark.v1",
        "solver_version": version,
        "version_probe_exit_code": version_probe.returncode,
        "binary_sha256": sha256(executable.read_bytes()).hexdigest(),
        "cases": rows,
        "limits": "Linear bending-only FE comparison, not torsion, material calibration or vehicle correlation; B32R expands to solid elements and includes shear.",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ccx", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.ccx, args.output)
