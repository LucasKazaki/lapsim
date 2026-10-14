"""Run a deterministic partition in isolated processes, retaining every result."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_all import merge_reports


def main() -> int:
    shard, count = map(int, sys.argv[1:])
    if not 0 <= shard < count:
        raise ValueError("shard must be in [0, count)")
    output = ROOT / "audit" / f"native-{shard}"
    output.mkdir(parents=True, exist_ok=True)
    env = dict(
        os.environ,
        MPLBACKEND="Agg",
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
    )
    modules = sorted((ROOT / "tests").glob("test_*.py"))[shard::count]
    if not modules:
        raise RuntimeError("empty test partition")
    results = []
    reports = []
    for module in modules:
        report = output / f"{module.stem}.xml"
        start = time.monotonic()
        command = [
            sys.executable,
            "-m",
            "pytest",
            str(module),
            "-q",
            "-ra",
            f"--junitxml={report}",
        ]
        with (output / f"{module.stem}.log").open("w") as log:
            try:
                code = subprocess.run(
                    command,
                    cwd=ROOT,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=900,
                    check=False,
                ).returncode
            except subprocess.TimeoutExpired:
                code = 124
        results.append(
            {
                "module": module.name,
                "exit_code": code,
                "seconds": round(time.monotonic() - start, 2),
            }
        )
        if report.is_file():
            reports.append(report)
        print(json.dumps(results[-1]), flush=True)
        print((output / f"{module.stem}.log").read_text()[-3000:], flush=True)
    totals = merge_reports(reports, output / "aggregate.xml")
    (output / "modules.json").write_text(json.dumps(results, indent=2))
    print(
        json.dumps(
            {
                "shard": shard,
                "modules": len(modules),
                "reports": len(reports),
                "totals": totals,
            }
        ),
        flush=True,
    )
    return int(len(reports) != len(modules) or any(row["exit_code"] for row in results))


if __name__ == "__main__":
    raise SystemExit(main())
