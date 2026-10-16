"""Build and execute actual wheel/sdist installs outside the source checkout."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tarfile
import venv
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
PROBE = r"""
from hashlib import sha256
import json
from pathlib import Path
import sys
import lapsim
from lapsim.diagnostics import check_runtime
from lapsim.resources import _io_path, build_identity, repository_root
assert Path(lapsim.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
root=repository_root()
assert root.resolve().is_relative_to(Path(sys.prefix).resolve())
info=build_identity()
assert info and info['build_kind']=='installed_python_resource_bundle'
actual={}
for name,expected in info['files_sha256'].items():
    actual[name]=sha256((_io_path(root)/name).read_bytes()).hexdigest()
    assert actual[name]==expected,name
    if name.startswith('src/'):
        installed=_io_path(Path(lapsim.__file__).parent.parent)/name[4:]
        assert sha256(installed.read_bytes()).hexdigest()==expected,name
assert sha256(json.dumps(actual,sort_keys=True,separators=(',',':')).encode()).hexdigest()==info['source_sha256']
result=check_runtime()
assert result['packaged_resources'] and result['controller_original_files']==419
assert result['comparison_runs_replayed']==2
from dataclasses import replace
from lapsim.experiments.closed_loop import run_closed_loop
from lapsim.experiments.control_study import DEFAULT_REQUEST, study_scenario
from lapsim.experiments.native_controller import NativeController, build_native_controller
receipt=build_native_controller(Path(sys.argv[2]))
scenario=study_scenario(dict(DEFAULT_REQUEST,duration_s=.1))
expected=run_closed_loop(scenario)['result']
native=NativeController(Path(receipt['binary']))
try:
    observed=run_closed_loop(replace(scenario,controller_backend_id='native_c'),native)
    assert observed['result']==expected
finally:
    native.close()
result['native_core']={'backend':'native_c','compiler':receipt['compiler_version'],'binary_sha256':receipt['binary_sha256']}
Path(sys.argv[1]).write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
"""


def run(argv: list[str], cwd: Path, log: Path, *, timeout=300, offline=False) -> None:
    env = dict(
        os.environ,
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        PYTHONUTF8="1",
        MPLBACKEND="Agg",
    )
    if offline:
        env.update(
            HTTP_PROXY="http://127.0.0.1:9",
            HTTPS_PROXY="http://127.0.0.1:9",
            NO_PROXY="",
        )
    with log.open("w", encoding="utf-8") as output:
        result = subprocess.run(
            [argv[0], "-X", "utf8", *argv[1:]],
            cwd=cwd,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    if result.returncode:
        raise RuntimeError(f"Installed-package check failed; inspect {log.name}")


def verify(output: Path, *, desktop: bool) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    artifacts = output / "artifacts"
    run(
        [sys.executable, "-m", "build", "--outdir", str(artifacts)],
        ROOT,
        output / "build.log",
    )
    packages = {
        "wheel": next(artifacts.glob("*.whl")),
        "sdist": next(artifacts.glob("*.tar.gz")),
    }
    probe = output / "probe.py"
    probe.write_text(PROBE, encoding="utf-8")
    results = {}
    # The spaces/non-ASCII directory and unrelated CWD exercise real installers
    # and installed code. Only these owned temporary environments are removed.
    with TemporaryDirectory(prefix="lapsim package λ ") as temporary:
        outside = Path(temporary)
        for kind, package in packages.items():
            environment = outside / kind
            venv.EnvBuilder(with_pip=True).create(environment)
            python = environment / (
                "Scripts/python.exe" if os.name == "nt" else "bin/python"
            )
            run(
                [
                    str(python),
                    "-I",
                    "-m",
                    "pip",
                    "--isolated",
                    "install",
                    "--no-user",
                    "--prefix",
                    str(environment),
                    "--disable-pip-version-check",
                    "--no-input",
                    "--constraint",
                    str(ROOT / "requirements-build.lock"),
                    str(package),
                ],
                outside,
                output / (kind + "-install.log"),
            )
            report = output / (kind + "-diagnostics.json")
            run(
                [
                    str(python),
                    "-I",
                    str(probe),
                    str(report),
                    str(output / (kind + "-native")),
                ],
                outside,
                output / (kind + "-runtime.log"),
                timeout=90,
            )
            results[kind] = json.loads(report.read_text(encoding="utf-8"))
            run(
                [
                    str(python),
                    "-I",
                    "-B",
                    "-c",
                    "import unittest,json,sys; from pathlib import Path; from lapsim.resources import repository_root; s=unittest.defaultTestLoader.discover(str(repository_root()/'controller/reference'),pattern='test_*.py'); r=unittest.TextTestRunner(verbosity=0).run(s); Path(sys.argv[1]).write_text(json.dumps({'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'skipped':len(r.skipped)})); raise SystemExit(not r.wasSuccessful())",
                    str(output / (kind + "-reference.json")),
                ],
                outside,
                output / (kind + "-reference.log"),
                timeout=120,
            )
            reference = json.loads((output / (kind + "-reference.json")).read_text())
            assert reference == {"tests": 538, "failures": 0, "errors": 0, "skipped": 0}
            results[kind]["reference_suite"] = reference
            if desktop:
                run(
                    [
                        str(python),
                        "-I",
                        "-m",
                        "lapsim.desktop",
                        "--self-test",
                        str(output / (kind + "-desktop.json")),
                    ],
                    outside,
                    output / (kind + "-desktop.log"),
                    timeout=120,
                )
        assert (
            results["wheel"]["source"]["source_sha256"]
            == results["sdist"]["source"]["source_sha256"]
        )
        extracted = outside / "source space λ"
        extracted.mkdir()
        with tarfile.open(packages["sdist"]) as archive:
            archive.extractall(extracted, filter="data")
        source = next(path for path in extracted.iterdir() if path.is_dir())
        launch = (
            ["--launch", "--desktop-self-test", str(output / "bootstrap-desktop.json")]
            if desktop
            else []
        )
        run(
            [sys.executable, str(source / "scripts/bootstrap.py"), *launch],
            outside,
            output / "bootstrap.log",
            timeout=420,
        )
        marker = source / ".venv/.lapsim-ready.json"
        previous = (marker.read_bytes(), marker.stat().st_mtime_ns)
        run(
            [sys.executable, str(source / "scripts/bootstrap.py"), "--check"],
            outside,
            output / "bootstrap-offline.log",
            timeout=90,
            offline=True,
        )
        assert previous == (marker.read_bytes(), marker.stat().st_mtime_ns)
    summary = {
        "schema": "lapsim.actual-package-verification.v1",
        "status": "passed",
        "python": sys.version.split()[0],
        "desktop_checked": desktop,
        "environments": results,
        "source_identity_preserved_through_sdist": True,
        "source_bootstrap_from_non_ascii_snapshot": True,
        "offline_readonly_repeat": True,
        "artifacts_published": False,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--desktop", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify(args.output_dir, desktop=args.desktop), indent=2))
