"""Isolate test processes and emit one aggregate JUnit report."""
from __future__ import annotations

import argparse
from pathlib import Path
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

from defusedxml import ElementTree as SafeET


def merge_reports(paths: list[Path], destination: Path) -> dict[str, int]:
    """Combine measured reports without discarding failure or skip information."""
    aggregate = ET.Element("testsuites")
    totals = {name: 0 for name in ("tests", "failures", "errors", "skipped")}
    elapsed = 0.0
    for report in paths:
        if report.stat().st_size > 16 * 1024 * 1024:
            raise ValueError(f"JUnit report exceeds the 16 MiB limit: {report.name}")
        parsed = SafeET.parse(
            report, forbid_dtd=True, forbid_entities=True, forbid_external=True,
        )
        for suite in parsed.getroot().iter("testsuite"):
            aggregate.append(suite)
            for name in totals:
                totals[name] += int(suite.get(name, 0))
            elapsed += float(suite.get("time", 0))
    for name, value in totals.items():
        aggregate.set(name, str(value))
    aggregate.set("time", str(elapsed))
    ET.ElementTree(aggregate).write(destination, encoding="utf-8", xml_declaration=True)
    return totals


def run_module(path: Path, root: Path, reports: Path, environment: dict[str, str]) -> bool:
    """Use a fresh process and preserve native Tcl standard-file handles."""
    report = reports / (path.stem + ".xml")
    report.unlink(missing_ok=True)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-rs", "--capture=sys", str(path), f"--junitxml={report}"],
        cwd=root, env=environment,
    )
    return bool(result.returncode) or not report.is_file()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path,
        help="Write reports here instead of the repository's work directory",
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    output = args.output_dir.resolve() if args.output_dir is not None else root / "work"
    reports = output / "test-modules"
    reports.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        environment[name] = "1"
    if sys.platform == "win32":
        import _tkinter
        base_tcl = Path(sys.base_prefix) / "tcl"
        for name, folder, entry in (
            ("TCL_LIBRARY", f"tcl{_tkinter.TCL_VERSION}", "init.tcl"),
            ("TK_LIBRARY", f"tk{_tkinter.TK_VERSION}", "tk.tcl"),
        ):
            library = base_tcl / folder
            if (library / entry).is_file():
                environment[name] = str(library)
    tests = sorted((root / "tests").glob("test_*.py"))
    if not tests:
        raise SystemExit("No repository test modules were found")
    failed = False
    module_reports = []
    for index, path in enumerate(tests, start=1):
        print(f"[{index}/{len(tests)}] {path.name}", flush=True)
        failed |= run_module(path, root, reports, environment)
        report = reports / (path.stem + ".xml")
        if report.is_file():
            module_reports.append(report)
        else:
            failed = True
    destination = output / "test-results.xml"
    totals = merge_reports(module_reports, destination)
    print(f"Complete-suite report: {totals}; {len(module_reports)}/{len(tests)} module reports. {destination}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
