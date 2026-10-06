"""Course choice provenance and geometry, without desktop UI dependencies."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from math import pi

import pytest

from lapsim.ui.course_catalog import (
    COURSE_OPTIONS,
    DEFAULT_COURSE_ID,
    SYNTHETIC_DEMO_COURSE_ID,
    load_course,
    solver_cell_count_for_course,
    solver_track_for_course,
)


def test_course_options_keep_fused_source_as_explicit_default() -> None:
    assert tuple(option.course_id for option in COURSE_OPTIONS) == (
        DEFAULT_COURSE_ID, SYNTHETIC_DEMO_COURSE_ID,
    )
    assert len({option.label for option in COURSE_OPTIONS}) == len(COURSE_OPTIONS)
    source, demo = COURSE_OPTIONS
    assert not source.synthetic
    assert "GNSS/IMU" in source.label
    assert "not one geometrically consistent path" in source.description
    assert "No surveyed boundaries" in source.description
    assert demo.synthetic
    assert "Synthetic" in demo.label
    assert "assumed demonstration corridor" in demo.description
    assert "not a surveyed Racing Terps boundary" in demo.description
    assert (source.default_ai_half_width_m, source.default_ai_vehicle_width_m,
            source.default_ai_margin_m) == (2.0, 1.8, 0.2)
    assert (demo.default_ai_half_width_m, demo.default_ai_vehicle_width_m,
            demo.default_ai_margin_m) == (3.0, 1.8, 0.2)
    with pytest.raises(FrozenInstanceError):
        demo.label = "Measured course"  # type: ignore[misc]


def test_default_loader_returns_shipped_fused_course() -> None:
    default = load_course()
    explicit = load_course(DEFAULT_COURSE_ID)
    assert default.closed
    assert default.cell_count == 1978
    assert default.length_m == pytest.approx(989.0)
    assert default == explicit


def test_synthetic_demo_is_closed_coherent_segment_course() -> None:
    track = load_course(SYNTHETIC_DEMO_COURSE_ID)
    assert track.closed
    assert track.length_m == pytest.approx(120.0 + 24.0 * pi)
    assert max(track.cell_length_m) <= 0.5 + 1e-12
    assert track.x_m[-1] == pytest.approx(track.x_m[0], abs=1e-9)
    assert track.y_m[-1] == pytest.approx(track.y_m[0], abs=1e-9)
    assert set(round(value, 12) for value in track.curvature_per_m) == {
        0.0, round(1.0 / 12.0, 12),
    }
    audit = track.geometry_audit()
    assert audit.curvature_integrated_closure_gap_m < 1e-7
    assert audit.maximum_arc_chord_mismatch_m < 1e-7


def test_unknown_course_id_is_not_silently_replaced() -> None:
    with pytest.raises(ValueError, match="Unknown course ID"):
        load_course("made-up-course")


@pytest.mark.parametrize("requested_maximum_m", [0.25, 0.5, 5.0, 10.0])
def test_synthetic_solver_grid_keeps_exact_arcs(requested_maximum_m: float) -> None:
    source = load_course(SYNTHETIC_DEMO_COURSE_ID)
    solver = solver_track_for_course(
        SYNTHETIC_DEMO_COURSE_ID, source, requested_maximum_m,
    )
    assert max(solver.cell_length_m) <= min(requested_maximum_m, 0.5) + 1e-12
    assert solver.cell_count == solver_cell_count_for_course(
        SYNTHETIC_DEMO_COURSE_ID, source, requested_maximum_m,
    )
    assert solver.geometry_audit().curvature_integrated_closure_gap_m < 1e-7
    assert solver.geometry_audit().maximum_arc_chord_mismatch_m < 1e-7
    if requested_maximum_m >= 0.5:
        assert solver is source
    else:
        assert solver.cell_count > source.cell_count


def test_fused_solver_grid_still_uses_recorded_curvature() -> None:
    source = load_course()
    solver = solver_track_for_course(DEFAULT_COURSE_ID, source, 1.0)
    assert solver.cell_count == 989
    assert solver.geometry_audit().curvature_signed_turn_rad == pytest.approx(
        source.geometry_audit().curvature_signed_turn_rad
    )


@pytest.mark.parametrize("bad_step", [True, 0.0, -1.0, float("nan"), 1e-6])
def test_solver_grid_rejects_invalid_or_excessive_work(bad_step: float) -> None:
    source = load_course(SYNTHETIC_DEMO_COURSE_ID)
    with pytest.raises(ValueError):
        solver_track_for_course(SYNTHETIC_DEMO_COURSE_ID, source, bad_step)


def test_synthetic_segment_rounding_cannot_bypass_compute_cap() -> None:
    source = load_course(SYNTHETIC_DEMO_COURSE_ID)
    assert source.length_m / 0.0391 < 5000
    assert solver_cell_count_for_course(
        SYNTHETIC_DEMO_COURSE_ID, source, 0.0391,
    ) == 5004
    with pytest.raises(ValueError, match="5000-cell compute cap"):
        solver_track_for_course(SYNTHETIC_DEMO_COURSE_ID, source, 0.0391)
