"""Build and execute actual wheel/sdist installs outside the source checkout."""

from __future__ import annotations

import argparse
from hashlib import sha256
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


def _recipient_grid_identity(report: dict) -> dict:
    """Compare declared inputs across recipients, keeping run provenance separate."""
    try:
        if (
            report["status"] != "passed"
            or report["checks"]["imported_course_grid"] is not True
        ):
            raise ValueError("imported-course check did not pass")
        grid = report["recipient_grid"]
        if grid["status"] != "passed":
            raise ValueError("imported-course workflow did not pass")
        fixture = {
            name: grid["fixture"][name]
            for name in ("input_sha256", "bundle_sha256", "geometry_sha256")
        }
        if any(
            not isinstance(pin, str)
            or len(pin) != 64
            or set(pin) - set("0123456789abcdef")
            for pin in fixture.values()
        ):
            raise ValueError("fixture identities are missing or malformed")
        cases = grid["cases"]
        if [
            (row["requested_maximum_cell_length_m"], row["cell_count"]) for row in cases
        ] != [(5.0, 32), (0.5, 128)]:
            raise ValueError("imported-course grids differ from the contract")
        identities = []
        for row in cases:
            expected_hash = sha256(
                json.dumps(
                    row["expected_inputs"],
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
            if (
                row["expected_inputs_sha256"] != expected_hash
                or row["recorded_inputs_sha256"] != expected_hash
                or row["record_unchanged"] is not True
                or row["replay"]["model_agreement"] is not True
                or row["replay"]["replay_completed"] is not True
            ):
                raise ValueError("saved inputs or replay differ from the request")
            identities.append(
                {
                    "requested_maximum_cell_length_m": row[
                        "requested_maximum_cell_length_m"
                    ],
                    "cell_count": row["cell_count"],
                    "geometry_sha256": row["geometry_sha256"],
                    "inputs_sha256": expected_hash,
                }
            )
        return {"fixture": fixture, "cases": identities}
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            f"Recipient imported-grid report is invalid: {error}"
        ) from error


def _catalog_grid_identity(report: dict) -> dict:
    """Bind declared demo inputs without comparing per-run numerical traces."""
    try:
        if (
            report["status"] != "passed"
            or report["checks"]["catalog_course_grid"] is not True
        ):
            raise ValueError("catalog-course check did not pass")
        grid = report["recipient_catalog_grid"]
        if (
            grid["status"] != "passed"
            or grid["course_id"] != "synthetic_rounded_rectangle_v1"
            or len(grid["cases"]) != 1
        ):
            raise ValueError("catalog-course identity is incorrect")
        source = grid["source"]
        geometry = grid["source_geometry"]
        geometry_hash = sha256(
            json.dumps(
                geometry, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ).hexdigest()
        if (
            source["selected_course_id"] != grid["course_id"]
            or source["source_kind"] != "synthetic"
            or source["revision"] != "generator_v1"
            or source["source_generator"]
            != "lapsim.ui.course_catalog._synthetic_demo_track"
            or source["source_geometry_sha256"] != geometry_hash
        ):
            raise ValueError("catalog-source claims are incorrect")
        row = grid["cases"][0]
        inputs = row["expected_inputs"]
        inputs_hash = sha256(
            json.dumps(
                inputs, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ).hexdigest()
        if (
            row["requested_maximum_cell_length_m"] != 5.0
            or row["cell_count"] != 392
            or row["geometry"] != geometry
            or row["geometry_sha256"] != geometry_hash
            or row["expected_inputs_sha256"] != inputs_hash
            or row["recorded_inputs_sha256"] != inputs_hash
            or inputs["settings"]["track"]["source_course"] != source
            or inputs["settings"]["track"]["geometry"] != geometry
            or inputs["selected_profile_id"] != "repository_baseline"
            or row["record_unchanged"] is not True
            or row["replay"]["model_agreement"] is not True
            or row["replay"]["replay_completed"] is not True
        ):
            raise ValueError("catalog grid or saved inputs/replay are incorrect")
        return {
            "course_id": grid["course_id"],
            "source": source,
            "source_geometry_sha256": geometry_hash,
            "cases": [
                {
                    "requested_maximum_cell_length_m": 5.0,
                    "cell_count": 392,
                    "geometry_sha256": geometry_hash,
                    "inputs_sha256": inputs_hash,
                }
            ],
        }
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            f"Recipient catalog-grid report is invalid: {error}"
        ) from error


def _fused_grid_identity(report: dict, *, source_root: Path | None = None) -> dict:
    """Validate each fused context before comparing complete declared inputs."""
    import csv
    from fractions import Fraction
    from math import isclose, isfinite

    def digest(value):
        return sha256(
            json.dumps(
                value, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ).hexdigest()

    try:
        if (
            report["status"] != "passed"
            or report["checks"]["fused_course_grid"] is not True
        ):
            raise ValueError("fused-course check did not pass")
        grid = report["recipient_fused_grid"]
        course_id = "team_endurance_fused_gnss_imu"
        if (
            grid["status"] != "passed"
            or grid["course_id"] != course_id
            or len(grid["cases"]) != 1
        ):
            raise ValueError("fused-course identity is incorrect")
        names = {
            "fused_csv": "analysis/data/track/gnss_imu_endurance_track.csv",
            "fusion_metadata_json": "analysis/data/track/gnss_imu_endurance_track.json",
        }
        source = grid["source"]
        raw_hashes = source["source_artifact_sha256"]
        if set(raw_hashes) != set(names) or any(
            not isinstance(value, str)
            or len(value) != 64
            or set(value) - set("0123456789abcdef")
            for value in raw_hashes.values()
        ):
            raise ValueError("fused raw source hashes are missing or malformed")
        build = report["build"]
        if build is not None:
            # Installed bundles use compact JSON; the frozen builder uses spaces.
            encoded = (
                json.dumps(build["files_sha256"], sort_keys=True, allow_nan=False)
                if report["frozen"] is True
                else json.dumps(
                    build["files_sha256"],
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            ).encode("utf-8")
            if sha256(encoded).hexdigest() != build["source_sha256"]:
                raise ValueError("fused resource index hash is incorrect")
        observed_hashes = (
            {
                key: sha256(
                    ((ROOT if source_root is None else source_root) / name).read_bytes()
                ).hexdigest()
                for key, name in names.items()
            }
            if build is None
            else {key: build["files_sha256"][name] for key, name in names.items()}
        )
        if raw_hashes != observed_hashes:
            raise ValueError(
                "fused raw source hashes do not match the recipient resources"
            )
        reference_root = (
            ROOT if build is not None or source_root is None else source_root
        )
        with (reference_root / names["fused_csv"]).open(
            encoding="utf-8", newline=""
        ) as stream:
            rows = list(csv.DictReader(stream))
        stations = [Fraction(row["distance_m"]) for row in rows]
        if (
            stations != [Fraction(index, 2) for index in range(1979)]
            or rows[-1]["curvature_per_m"] != ""
        ):
            raise ValueError("fused source stations differ from the fixed source")
        curvature = [Fraction(row["curvature_per_m"]) for row in rows[:-1]]
        source_geometry = {
            "closed": True,
            "distance_m": [float(value) for value in stations],
            "x_m": [float(row["x_m"]) for row in rows],
            "y_m": [float(row["y_m"]) for row in rows],
            "curvature_per_m": [float(value) for value in curvature],
        }
        source_hash = digest(source_geometry)
        if (
            source_hash
            != "264e73a7cfeebcc902394d97140b2f754190a58e0274b8687a871884864e34ae"
            or grid["source_geometry"] != source_geometry
        ):
            raise ValueError("fused source geometry differs from the fixed source")
        expected_source = {
            "metadata_version": 1,
            "selected_course_id": course_id,
            "source_geometry_sha256": source_hash,
            "source_geometry_hash_scope": (
                "canonical loaded closed/distance_m/x_m/y_m/curvature_per_m"
            ),
            "source_kind": "recorded_fusion_unverified",
            "revision": "legacy_unversioned",
            "coordinate_frame": "legacy_map_registered_xy_unknown_origin",
            "boundary_status": "absent",
            "bundle_id": None,
            "bundle_sha256": None,
            "bundle_hash_scope": None,
        }
        if any(source[key] != value for key, value in expected_source.items()):
            raise ValueError("fused source claims differ from the legacy contract")
        coarse = [Fraction(index * 5) for index in range(198)] + [Fraction(989)]
        indices = [int(value * 2) for value in coarse]
        means = [
            float(
                sum(
                    (
                        curvature[index] * (stations[index + 1] - stations[index])
                        for index in range(first, stop)
                    ),
                    Fraction(0),
                )
                / (upper - lower)
            )
            for lower, upper, first, stop in zip(
                coarse[:-1], coarse[1:], indices[:-1], indices[1:], strict=True
            )
        ]
        row = grid["cases"][0]
        geometry = row["geometry"]
        if (
            set(geometry) != set(source_geometry)
            or geometry["closed"] is not True
            or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not isfinite(value)
                for key in ("distance_m", "x_m", "y_m", "curvature_per_m")
                for value in geometry[key]
            )
        ):
            raise ValueError("fused effective geometry is malformed or nonfinite")
        if (
            geometry["distance_m"] != [float(value) for value in coarse]
            or geometry["x_m"] != [float(rows[index]["x_m"]) for index in indices]
            or geometry["y_m"] != [float(rows[index]["y_m"]) for index in indices]
            or len(geometry["curvature_per_m"]) != 198
            or any(
                not isclose(value, expected, rel_tol=0.0, abs_tol=1e-12)
                for value, expected in zip(
                    geometry["curvature_per_m"], means, strict=True
                )
            )
        ):
            raise ValueError(
                "fused effective geometry fails the independent cell oracle"
            )
        geometry_hash = digest(geometry)
        inputs = row["expected_inputs"]
        inputs_hash = digest(inputs)
        track = inputs["settings"]["track"]
        if (
            row["requested_maximum_cell_length_m"] != 5.0
            or row["cell_count"] != 198
            or row["geometry_sha256"] != geometry_hash
            or row["expected_inputs_sha256"] != inputs_hash
            or row["recorded_inputs_sha256"] != inputs_hash
            or track["geometry"] != geometry
            or track["geometry_sha256"] != geometry_hash
            or track["source_course"] != source
            or track["id"] != course_id
            or track["cell_count"] != 198
            or track["length_m"] != 989.0
            or track["closed"] is not True
            or inputs["selected_profile_id"] != "repository_baseline"
            or row["record_unchanged"] is not True
            or row["replay"]["model_agreement"] is not True
            or row["replay"]["replay_completed"] is not True
        ):
            raise ValueError("fused saved inputs or replay differ from the request")
        replay = row["replay"]
        tolerances = {
            "driving_time_s": 0.01,
            "lap_time_s": 0.01,
            "starting_speed_mps": 0.01,
            "ending_speed_mps": 0.01,
            "pack_energy_kwh": 1e-5,
            "final_state_of_charge": 1e-5,
            "sample_time_s": 0.01,
            "sample_distance_m": 1e-8,
            "speed_trace_mps": 0.01,
            "path_speed_ceiling_mps": 0.01,
            "controls.motor_torque_request_nm": 0.0,
            "controls.front_brake_pressure_psi": 0.0,
            "controls.rear_brake_pressure_psi": 0.0,
            "controls.rear_regenerative_brake_force_request_n": 0.0,
            "controls.steering_angle_rad": 0.0,
            "controls.front_regenerative_brake_force_request_n": 0.0,
            "tire.road_grip_multiplier": 0.0,
        }
        if (
            not isinstance(row["record_run_id"], str)
            or len(row["record_run_id"]) != 64
            or set(row["record_run_id"]) - set("0123456789abcdef")
            or replay["run_id"] != row["record_run_id"]
            or replay["recorded_sample_count"] != 198
            or replay["replayed_sample_count"] != 198
            or replay["mismatch_reasons"] != []
            or not isinstance(replay["metrics"], list)
            or not replay["metrics"]
        ):
            raise ValueError("fused replay identity or accepted-cell counts differ")
        metric_names = [metric["name"] for metric in replay["metrics"]]
        if set(metric_names) != set(tolerances) or len(metric_names) != len(tolerances):
            raise ValueError("fused replay metrics are missing, extra or duplicated")
        for metric in replay["metrics"]:
            error, tolerance = metric["maximum_absolute_error"], metric["tolerance"]
            if (
                metric["passed"] is not True
                or any(
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not isfinite(value)
                    or value < 0.0
                    for value in (error, tolerance)
                )
                or tolerance != tolerances[metric["name"]]
                or error > tolerance
            ):
                raise ValueError("fused replay metric contradicts model agreement")
        # Remove only four reviewed contextual leaves after local validation.
        declared = json.loads(json.dumps(inputs, allow_nan=False))
        declared_track = declared["settings"]["track"]
        del declared_track["geometry"]
        del declared_track["geometry_sha256"]
        declared_raw = declared_track["source_course"]["source_artifact_sha256"]
        del declared_raw["fused_csv"]
        del declared_raw["fusion_metadata_json"]
        return {
            "identity": {
                "course_id": course_id,
                "source_geometry_sha256": source_hash,
                "declared_inputs_sha256": digest(declared),
            },
            "observed": {
                "raw_source_sha256": dict(raw_hashes),
                "geometry_sha256": geometry_hash,
                "expected_inputs_sha256": inputs_hash,
                "recorded_inputs_sha256": row["recorded_inputs_sha256"],
                "record_run_id": row["record_run_id"],
                "replay": replay,
            },
        }
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise RuntimeError(
            f"Recipient fused-grid report is invalid: {error}"
        ) from error


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
    bootstrap_fused = None
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
                desktop_report = output / (kind + "-desktop.json")
                run(
                    [
                        str(python),
                        "-I",
                        "-m",
                        "lapsim.desktop",
                        "--self-test",
                        str(desktop_report),
                    ],
                    outside,
                    output / (kind + "-desktop.log"),
                    timeout=120,
                )
                results[kind]["recipient_grid_inputs"] = _recipient_grid_identity(
                    json.loads(desktop_report.read_text(encoding="utf-8"))
                )
                results[kind]["catalog_grid_inputs"] = _catalog_grid_identity(
                    json.loads(desktop_report.read_text(encoding="utf-8"))
                )
                fused_report = json.loads(desktop_report.read_text(encoding="utf-8"))
                if (
                    fused_report["build"]["source_sha256"]
                    != results[kind]["source"]["source_sha256"]
                ):
                    raise RuntimeError(
                        "Desktop and probed package resource identities differ"
                    )
                results[kind]["fused_grid_inputs"] = _fused_grid_identity(fused_report)
        assert (
            results["wheel"]["source"]["source_sha256"]
            == results["sdist"]["source"]["source_sha256"]
        )
        if desktop and (
            results["wheel"]["recipient_grid_inputs"]
            != results["sdist"]["recipient_grid_inputs"]
        ):
            raise RuntimeError("Wheel and sdist imported-course inputs differ")
        if desktop and (
            results["wheel"]["catalog_grid_inputs"]
            != results["sdist"]["catalog_grid_inputs"]
        ):
            raise RuntimeError("Wheel and sdist catalog-course inputs differ")
        if desktop and (
            results["wheel"]["fused_grid_inputs"]["identity"]
            != results["sdist"]["fused_grid_inputs"]["identity"]
        ):
            raise RuntimeError("Wheel and sdist fused-course declared inputs differ")
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
        if desktop:
            bootstrap_grid = _recipient_grid_identity(
                json.loads(
                    (output / "bootstrap-desktop.json").read_text(encoding="utf-8")
                )
            )
            if bootstrap_grid != results["wheel"]["recipient_grid_inputs"]:
                raise RuntimeError(
                    "Source bootstrap and wheel imported-course inputs differ"
                )
            bootstrap_catalog = _catalog_grid_identity(
                json.loads(
                    (output / "bootstrap-desktop.json").read_text(encoding="utf-8")
                )
            )
            if bootstrap_catalog != results["wheel"]["catalog_grid_inputs"]:
                raise RuntimeError(
                    "Source bootstrap and wheel catalog-course inputs differ"
                )
            bootstrap_fused = _fused_grid_identity(
                json.loads(
                    (output / "bootstrap-desktop.json").read_text(encoding="utf-8")
                ),
                source_root=source,
            )
            if (
                bootstrap_fused["identity"]
                != results["wheel"]["fused_grid_inputs"]["identity"]
            ):
                raise RuntimeError(
                    "Source bootstrap and wheel fused-course declared inputs differ"
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
        "recipient_grid_inputs_match": True if desktop else None,
        "catalog_grid_inputs_match": True if desktop else None,
        "fused_grid_declared_inputs_match": True if desktop else None,
        "bootstrap_fused_grid_inputs": bootstrap_fused,
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
