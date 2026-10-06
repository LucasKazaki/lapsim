"""The CSV-to-CourseBundle authoring path must fail before saving bad data."""

from __future__ import annotations

from hashlib import sha256
from math import pi
from pathlib import Path
import subprocess
import sys

import pytest

from lapsim.courses.course_bundle import CourseBundle, MAX_BUNDLE_BYTES
from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Track
from scripts.create_course_bundle import create_course_bundle


def _source_csv(tmp_path: Path) -> tuple[Path, SpatialTrack]:
    track = SpatialTrack.from_track(
        Track.from_segments([Curve(10.0, 2.0 * pi)]),
        maximum_cell_length_m=0.5,
    )
    return track.to_csv(tmp_path / "coherent.csv"), track


def _metadata() -> dict:
    return {
        "course_id": "terps_test_course",
        "revision": "2027-03-r1",
        "label": "Terps test course",
        "description": "Synthetic solver example; no surveyed boundaries.",
        "source_kind": "synthetic",
        "source_name": "Exact circle generator",
        "processing_method": "Analytic piecewise circular arcs",
        "review_note": "Software fixture, not a measured event course.",
        "frame_origin": "circle starting point",
        "frame_x_axis": "east",
        "frame_y_axis": "north",
        "travel_direction": "counterclockwise",
    }


def test_create_course_bundle_preserves_csv_digest_and_geometry(tmp_path: Path) -> None:
    source, track = _source_csv(tmp_path)
    output = tmp_path / "terps_test_r1.json"
    bundle = create_course_bundle(source, output, **_metadata())
    loaded = CourseBundle.load(output)
    assert loaded.catalog_id == "terps_test_course@2027-03-r1"
    assert loaded.track == track
    assert loaded.bundle_sha256 == bundle.bundle_sha256
    assert loaded.to_dict()["provenance"]["source_sha256"] == sha256(
        source.read_bytes()
    ).hexdigest()
    assert loaded.to_dict()["boundary_status"] == "absent"
    assert loaded.to_dict()["ai_defaults"]["width_source"] == "assumed_uniform"
    with pytest.raises(ValueError, match="already exists"):
        create_course_bundle(source, output, **_metadata())


def test_measured_option_records_source_hash_as_declared_provenance(tmp_path: Path) -> None:
    source, _ = _source_csv(tmp_path)
    metadata = _metadata()
    metadata["source_kind"] = "measured"
    bundle = create_course_bundle(source, tmp_path / "measured.json", **metadata)
    assert bundle.source_kind == "measured"
    assert bundle.to_dict()["provenance"]["source_sha256"] == sha256(
        source.read_bytes()
    ).hexdigest()


@pytest.mark.parametrize("change,expected", [
    (lambda lines: lines.__setitem__(1, lines[1].replace(",0.0,", ",0.1,", 1)), "not coherent"),
    (lambda lines: lines.__setitem__(-1, lines[-1] + "0.1"), "Final spatial-track CSV curvature"),
    (lambda lines: lines.__setitem__(0, "distance_m,x_m,y_m"), "missing columns"),
])
def test_malformed_csv_never_creates_output(tmp_path: Path, change, expected: str) -> None:
    source, _ = _source_csv(tmp_path)
    lines = source.read_text(encoding="utf-8").splitlines()
    change(lines)
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output = tmp_path / "bad.json"
    with pytest.raises(ValueError, match=expected):
        create_course_bundle(source, output, **_metadata())
    assert not output.exists()


def test_direction_units_and_scenario_bounds_are_validated_before_save(tmp_path: Path) -> None:
    source, _ = _source_csv(tmp_path)
    output = tmp_path / "bad.json"
    metadata = _metadata()
    metadata["travel_direction"] = "clockwise"
    with pytest.raises(ValueError, match="travel_direction disagrees"):
        create_course_bundle(source, output, **metadata)
    assert not output.exists()
    metadata = _metadata()
    with pytest.raises(ValueError, match="usable assumed corridor"):
        create_course_bundle(source, output, ai_half_width_m=1.0, **metadata)
    assert not output.exists()


def test_fused_legacy_course_cannot_be_labeled_as_coherent_bundle(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    source = repository / "analysis/data/track/gnss_imu_endurance_track.csv"
    if not source.exists():
        pytest.skip("shipped fused course data unavailable")
    output = tmp_path / "fused.json"
    with pytest.raises(ValueError, match="not coherent"):
        create_course_bundle(source, output, **_metadata())
    assert not output.exists()


def test_csv_input_size_cap_and_no_source_overwrite(tmp_path: Path) -> None:
    source, _ = _source_csv(tmp_path)
    with pytest.raises(ValueError, match="different files"):
        create_course_bundle(source, source, **_metadata())
    source.write_bytes(b" " * (MAX_BUNDLE_BYTES + 1))
    with pytest.raises(ValueError, match="4 MiB"):
        create_course_bundle(source, tmp_path / "large.json", **_metadata())


def test_cli_help_and_success(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    script = repository / "scripts/create_course_bundle.py"
    help_result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=repository, capture_output=True, text=True, check=False,
    )
    assert help_result.returncode == 0
    assert "does not derive curvature from raw survey points" in help_result.stdout
    assert "--frame-origin" in help_result.stdout
    source, _ = _source_csv(tmp_path)
    output = tmp_path / "cli.json"
    args = [str(source), str(output)]
    for name, value in _metadata().items():
        args.extend(("--" + name.replace("_", "-"), value))
    result = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=repository, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert output.exists()
    assert CourseBundle.load(output).catalog_id in result.stdout
