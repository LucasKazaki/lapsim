"""The CSV-to-CourseBundle authoring path must fail before saving bad data."""

from __future__ import annotations

from hashlib import sha256
import json
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


def _corridor_csv(tmp_path: Path, track: SpatialTrack) -> Path:
    source = tmp_path / "widths.csv"
    lines = ["distance_m,left_width_m,right_width_m"]
    lines.extend(
        f"{station_m},{2.5 + index * 0.01},0.2"
        for index, station_m in enumerate(track.distance_m[:-1])
    )
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return source


def _corridor_metadata(source: Path) -> dict:
    return {
        "corridor_csv": source,
        "corridor_status": "assumed",
        "corridor_source_name": "Scenario width table r1",
        "corridor_processing_method": "Widths assigned to exact source cells",
        "corridor_review_note": "Illustrative source-relative widths only",
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


def test_v2_converter_hashes_exact_width_csv_and_keeps_assumed_ai_defaults(
    tmp_path: Path,
) -> None:
    source, track = _source_csv(tmp_path)
    widths = _corridor_csv(tmp_path, track)
    output = tmp_path / "with_widths.json"
    bundle = create_course_bundle(
        source, output, **_metadata(), **_corridor_metadata(widths),
    )
    loaded = CourseBundle.load(output)
    manifest = loaded.to_dict()
    corridor = manifest["corridor"]
    assert loaded.schema_version == 2
    assert loaded.bundle_sha256 == bundle.bundle_sha256
    assert manifest["boundary_status"] == "source_normal_offsets_assumed"
    assert manifest["ai_defaults"]["width_source"] == "assumed_uniform"
    assert corridor["reference_geometry_sha256"] == loaded.geometry_sha256
    assert corridor["provenance"]["source_sha256"] == sha256(widths.read_bytes()).hexdigest()
    assert corridor["right_width_m"] == [0.2] * track.cell_count
    assert corridor["corridor_sha256"] == sha256(
        json.dumps(
            {key: value for key, value in corridor.items() if key != "corridor_sha256"},
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


@pytest.mark.parametrize("change,expected", [
    (lambda lines: lines.pop(), "exactly one row"),
    (lambda lines: lines.append(lines[-1]), "exactly one row"),
    (lambda lines: lines.__setitem__(2, lines[1]), "duplicates a station"),
    (lambda lines: lines.__setitem__(1, "0.001,2.5,0.2"), "does not match source cell"),
    (lambda lines: lines.__setitem__(1, "0,nan,0.2"), "finite numbers"),
    (lambda lines: lines.__setitem__(1, "0,0,0.2"), "widths must be positive"),
    (lambda lines: lines.__setitem__(0, "distance_m,left_width_m,right_width_m,extra"), "header must be exactly"),
])
def test_v2_converter_rejects_bad_corridor_rows_before_saving(
    tmp_path: Path, change, expected: str,
) -> None:
    source, track = _source_csv(tmp_path)
    widths = _corridor_csv(tmp_path, track)
    lines = widths.read_text(encoding="utf-8").splitlines()
    change(lines)
    widths.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output = tmp_path / "bad_widths.json"
    with pytest.raises(ValueError, match=expected):
        create_course_bundle(
            source, output, **_metadata(), **_corridor_metadata(widths),
        )
    assert not output.exists()


def test_v2_converter_accepts_roundoff_but_not_measured_synthetic_widths(
    tmp_path: Path,
) -> None:
    source, track = _source_csv(tmp_path)
    widths = _corridor_csv(tmp_path, track)
    lines = widths.read_text(encoding="utf-8").splitlines()
    lines[1] = "0.0000000005,2.5,0.2"
    widths.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output = tmp_path / "tolerant.json"
    create_course_bundle(source, output, **_metadata(), **_corridor_metadata(widths))
    assert CourseBundle.load(output).schema_version == 2
    measured = _corridor_metadata(widths)
    measured["corridor_status"] = "measured"
    with pytest.raises(ValueError, match="measured source course"):
        create_course_bundle(source, tmp_path / "invalid.json", **_metadata(), **measured)
    measured_source = _metadata()
    measured_source["source_kind"] = "measured"
    accepted = create_course_bundle(
        source, tmp_path / "measured_widths.json", **measured_source, **measured,
    )
    assert accepted.source_cell_corridor is not None
    assert accepted.source_cell_corridor.status == "measured"


def test_v2_requires_complete_metadata_and_bounded_utf8_input(tmp_path: Path) -> None:
    source, track = _source_csv(tmp_path)
    widths = _corridor_csv(tmp_path, track)
    output = tmp_path / "invalid.json"
    with pytest.raises(ValueError, match="requires status"):
        create_course_bundle(source, output, **_metadata(), corridor_csv=widths)
    with pytest.raises(ValueError, match="requires --corridor-csv"):
        create_course_bundle(source, output, **_metadata(), corridor_status="assumed")
    widths.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="corridor CSV must be UTF-8"):
        create_course_bundle(source, output, **_metadata(), **_corridor_metadata(widths))
    widths.write_bytes(b" " * (MAX_BUNDLE_BYTES + 1))
    with pytest.raises(ValueError, match="corridor CSV exceeds the 4 MiB"):
        create_course_bundle(source, output, **_metadata(), **_corridor_metadata(widths))
    assert not output.exists()


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


def test_cli_opt_in_v2_corridor(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    script = repository / "scripts/create_course_bundle.py"
    source, track = _source_csv(tmp_path)
    widths = _corridor_csv(tmp_path, track)
    output = tmp_path / "cli_v2.json"
    args = [str(source), str(output)]
    for name, value in {**_metadata(), **_corridor_metadata(widths)}.items():
        args.extend(("--" + name.replace("_", "-"), str(value)))
    result = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=repository, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert CourseBundle.load(output).schema_version == 2
