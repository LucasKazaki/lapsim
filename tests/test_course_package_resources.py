"""Installed course data must not fall back to an ambient source checkout."""

import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from lapsim import resources
from lapsim.courses.library import COURSE_IDS, course_library


ROOT = Path(__file__).resolve().parents[1]
COURSE_RESOURCES = {
    "configs/courses/catalog.json",
    *(f"configs/courses/{course_id}.json" for course_id in COURSE_IDS),
    "configs/courses/README.md",
    "configs/courses/upstream/amz-fssim/FSG.yaml",
    "configs/courses/upstream/amz-fssim/FSI.yaml",
    "configs/courses/upstream/amz-fssim/LICENSE.md",
    "configs/courses/online_image_traces.json",
    "configs/courses/gnss_imu_trajectory_trace.json",
    "configs/courses/acceptance_20261026.json",
}

WEB_RESOURCES = {
    "web/tournament.html", "web/tournament.css", "web/tournament.js",
    "web/torque-configurator.html", "web/torque-configurator.css",
    "web/torque-configurator.js", "web/course_library.js",
    "web/replay_loader.js", "web/replay_webgl.js", "web/telemetry.js",
    "web/fixture_comparison.js", "web/round_view.js",
    "web/vendor/three-0.160.0.min.js", "web/vendor/three-LICENSE.txt",
    "web/vendor/three-provenance.json", "web/vendor/README.md",
}


def test_all_nine_courses_and_provenance_are_explicit_wheel_resources():
    spec = importlib.util.spec_from_file_location(
        "course_resource_build_support", ROOT / "packaging/build_support.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    selected = {
        path.relative_to(builder.ROOT).as_posix()
        for path in builder.resource_files()
        if path.is_relative_to(builder.ROOT / "configs/courses")
    }
    assert selected == COURSE_RESOURCES


def test_installed_controller_pages_retain_static_dependencies_and_not_work():
    spec = importlib.util.spec_from_file_location(
        "web_resource_build_support", ROOT / "packaging/build_support.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    selected = {
        path.relative_to(builder.ROOT).as_posix() for path in builder.resource_files()
    }
    assert WEB_RESOURCES <= selected
    assert not any("work" in Path(name).parts for name in selected)


def test_installed_library_loads_all_nine_exact_saved_geometries(tmp_path, monkeypatch):
    module = tmp_path / "installed/lapsim/resources.py"
    bundle_root = module.parent / "_resources"
    bundle_root.mkdir(parents=True)
    (bundle_root / "build-info.json").write_text("{}", encoding="utf-8")
    for name in COURSE_RESOURCES:
        destination = bundle_root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    monkeypatch.setattr(resources, "__file__", str(module))
    catalog = course_library()
    expected = json.loads((ROOT / "configs/courses/catalog.json").read_bytes())
    assert [row["id"] for row in catalog["courses"]] == list(COURSE_IDS)
    for row, declaration in zip(catalog["courses"], expected["courses"], strict=True):
        assert row["geometry_sha256"] == declaration["geometry_sha256"]
        assert row["classification"] == declaration["classification"]
        assert row["description"] == declaration["description"]


def test_missing_installed_catalog_fails_without_source_fallback(tmp_path, monkeypatch):
    module = tmp_path / "installed/lapsim/resources.py"
    bundle_root = module.parent / "_resources"
    bundle_root.mkdir(parents=True)
    (bundle_root / "build-info.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(resources, "__file__", str(module))
    with pytest.raises(FileNotFoundError):
        course_library()
