"""Preserve broad findings, block runtime defects and new type regressions."""

from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audit" / "static"
BASE = "1e8e35ac64093742caafa67c118ca02efa6e6537"


def execute(
    name: str, args: list[str], cwd: Path = ROOT
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, timeout=300, check=False
    )
    (OUT / f"{name}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    print(f"{name}: exit {result.returncode}", flush=True)
    return result


def fingerprints(report: dict, root: Path) -> Counter:
    return Counter(
        (
            str(Path(item["file"]).relative_to(root)),
            item.get("rule"),
            item["message"],
            item["severity"],
        )
        for item in report["generalDiagnostics"]
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    os.chdir(ROOT)
    (OUT / "commit.txt").write_text(
        subprocess.check_output(["git", "rev-parse", "HEAD"], text=True)
    )
    (OUT / "versions.txt").write_text(
        subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True)
    )
    broad = execute(
        "ruff-review",
        [
            "ruff",
            "check",
            ".",
            "--select",
            "E4,E7,E9,F,B,SIM,C4,PIE,UP,RUF",
            "--exclude",
            "audit,dist,build,work",
            "--output-format",
            "json",
        ],
    )
    formatting = execute(
        "format-review",
        ["ruff", "format", "--check", "src", "tests", "scripts", "quality", "web"],
    )
    critical = execute(
        "ruff-runtime-gate",
        [
            "ruff",
            "check",
            ".",
            "--select",
            "E9,F63,F7,F82",
            "--exclude",
            "audit,dist,build,work",
        ],
    )
    current = execute(
        "pyright", ["pyright", "src", "--pythonversion", "3.11", "--outputjson"]
    )
    current_report = json.loads(current.stdout)
    if current.returncode not in (0, 1):
        raise RuntimeError("Pyright did not complete")
    with tempfile.TemporaryDirectory(prefix="lapsim-type-baseline-") as folder:
        baseline_root = Path(folder)
        archive = subprocess.run(
            ["git", "archive", BASE], cwd=ROOT, capture_output=True, check=True
        )
        import io
        import tarfile

        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as source:
            source.extractall(baseline_root, filter="data")
        baseline = execute(
            "pyright-baseline",
            ["pyright", "src", "--pythonversion", "3.11", "--outputjson"],
            baseline_root,
        )
        baseline_report = json.loads(baseline.stdout)
        if baseline.returncode not in (0, 1):
            raise RuntimeError("Baseline Pyright did not complete")
        new_types = fingerprints(current_report, ROOT) - fingerprints(
            baseline_report, baseline_root
        )
    type_delta = [
        {
            "file": key[0],
            "rule": key[1],
            "message": key[2],
            "severity": key[3],
            "count": value,
        }
        for key, value in new_types.items()
    ]
    (OUT / "new-type-findings.json").write_text(json.dumps(type_delta, indent=2))
    security = execute(
        "semgrep",
        [
            "/tmp/lapsim-semgrep/bin/semgrep",
            "scan",
            "--config",
            "p/python",
            "--config",
            "p/javascript",
            "--metrics=off",
            "--error",
            "--json",
            "--output",
            str(OUT / "semgrep.json"),
            ".",
        ],
    )
    security_report = json.loads((OUT / "semgrep.json").read_text())
    summary = {
        "baseline_commit": BASE,
        "ruff_review_exit": broad.returncode,
        "format_review_exit": formatting.returncode,
        "ruff_runtime_exit": critical.returncode,
        "pyright": current_report["summary"],
        "pyright_baseline": baseline_report["summary"],
        "new_type_findings": type_delta,
        "security_matches": len(security_report["results"]),
        "security_errors": security_report["errors"],
        "security_files": len(security_report.get("paths", {}).get("scanned", [])),
        "note": "Existing broad lint, formatting, and type debt remains visible; this is not a clean-type certification. Newly introduced type diagnostics block integration.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)
    return int(
        critical.returncode != 0
        or bool(type_delta)
        or security.returncode != 0
        or bool(security_report["errors"])
    )


if __name__ == "__main__":
    raise SystemExit(main())
