"""Checks for the low-cost, station-aligned desktop driver playback."""

from __future__ import annotations

from math import cos, sin
from types import SimpleNamespace

import pytest

from lapsim.core.telemetry import Telemetry
from lapsim.courses.spatial_track import SpatialTrack
from lapsim.ui.driver_view import DriverPlayback


def straight_map() -> SpatialTrack:
    return SpatialTrack(
        distance_m=(0.0, 10.0, 20.0),
        x_m=(0.0, 10.0, 20.0),
        y_m=(0.0, 0.0, 0.0),
        curvature_per_m=(0.0, 0.0),
        closed=False,
    )


def lap_channels(**changes: tuple[float, ...]) -> Telemetry:
    channels = {
        "vehicle.time_s": (1.0, 2.0),
        "vehicle.distance_m": (10.0, 20.0),
        "vehicle.speed_mps": (10.0, 20.0),
        "vehicle.lateral_acceleration_mps2": (0.0, 9.80665),
    }
    channels.update(changes)
    return Telemetry(channels)


def test_driver_playback_interpolates_time_and_uses_map_station() -> None:
    playback = DriverPlayback(straight_map(), lap_channels())

    start = playback.frame_at(0.0)
    assert start.distance_m == pytest.approx(0.0)
    assert start.x_m == pytest.approx(0.0)
    halfway = playback.frame_at(1.5)
    assert halfway.distance_m == pytest.approx(15.0)
    assert halfway.x_m == pytest.approx(15.0)
    assert halfway.y_m == pytest.approx(0.0)
    assert halfway.course_heading_rad == pytest.approx(0.0)
    assert halfway.speed_mps == pytest.approx(15.0)
    assert halfway.lateral_acceleration_mps2 == pytest.approx(9.80665 / 2)
    assert playback.frame_at(100.0).distance_m == pytest.approx(20.0)


def test_playback_motion_matches_constant_acceleration_cells() -> None:
    # The endurance model records cell exits.  Its first entry speed can be
    # recovered from the first cell's distance, elapsed time, and exit speed.
    playback = DriverPlayback(
        straight_map(),
        lap_channels(**{
            "vehicle.speed_mps": (20.0, 0.0),
            "vehicle.lateral_acceleration_mps2": (0.0, 0.0),
        }),
    )

    assert playback.frame_at(0.0).speed_mps == pytest.approx(0.0)
    accelerating = playback.frame_at(0.5)
    assert accelerating.distance_m == pytest.approx(2.5)
    assert accelerating.x_m == pytest.approx(2.5)
    assert accelerating.speed_mps == pytest.approx(10.0)
    braking = playback.frame_at(1.5)
    assert braking.distance_m == pytest.approx(17.5)
    assert braking.speed_mps == pytest.approx(10.0)
    assert playback.frame_at(2.0).distance_m == pytest.approx(20.0)


def test_inconsistent_legacy_cell_keeps_linear_station_fallback() -> None:
    playback = DriverPlayback(straight_map(), lap_channels())

    # Between 1 and 2 s, speeds of 10 and 20 m/s imply 15 m of motion,
    # whereas this old fixture records 10 m.  Do not change its endpoints.
    halfway = playback.frame_at(1.5)
    assert halfway.distance_m == pytest.approx(15.0)
    assert halfway.speed_mps == pytest.approx(15.0)


def test_impossibly_short_imported_first_cell_time_keeps_finite_playback() -> None:
    playback = DriverPlayback(
        straight_map(),
        lap_channels(**{"vehicle.time_s": (1e-320, 2.0)}),
    )

    assert playback.frame_at(0.0).speed_mps == pytest.approx(10.0)


def test_local_path_is_car_fixed_and_open_course_does_not_wrap() -> None:
    playback = DriverPlayback(straight_map(), lap_channels())
    frame = playback.frame_at(1.5)

    samples = playback.local_path_m(
        frame, behind_m=5.0, ahead_m=5.0, spacing_m=5.0
    )
    assert samples[0] == pytest.approx((0.0, -5.0))
    assert samples[1] == pytest.approx((0.0, 0.0))
    assert samples[2] == pytest.approx((0.0, 5.0))
    start = playback.frame_at(0.0)
    start_samples = playback.local_path_m(
        start, behind_m=5.0, ahead_m=5.0, spacing_m=5.0
    )
    assert len(start_samples) == 2
    assert start_samples[0] == pytest.approx((0.0, 0.0))
    assert start_samples[1] == pytest.approx((0.0, 5.0))


def test_closed_view_samples_wrap_continuously_across_finish() -> None:
    track = SpatialTrack(
        distance_m=(0.0, 10.0, 20.0, 30.0, 40.0),
        x_m=(0.0, 10.0, 10.0, 0.0, 0.0),
        y_m=(0.0, 0.0, 10.0, 10.0, 0.0),
        curvature_per_m=(0.0, 0.0, 0.0, 0.0),
        closed=True,
    )
    playback = DriverPlayback(track, lap_channels(**{
        "vehicle.distance_m": (20.0, 40.0),
        "vehicle.speed_mps": (20.0, 20.0),
    }))
    frame = playback.frame_at(1.95)
    samples = playback.local_path_m(
        frame, behind_m=5.0, ahead_m=10.0, spacing_m=5.0
    )

    assert frame.distance_m == pytest.approx(39.0)
    assert len(samples) == 4
    for offset, sample in zip((-5.0, 0.0, 5.0, 10.0), samples, strict=True):
        x_m, y_m = playback.point_at(frame.distance_m + offset)
        dx, dy = x_m - frame.x_m, y_m - frame.y_m
        angle = frame.course_heading_rad
        expected = (
            sin(angle) * dx - cos(angle) * dy,
            cos(angle) * dx + sin(angle) * dy,
        )
        assert sample == pytest.approx(expected)


@pytest.mark.parametrize(
    ("last_y_m", "expected_right_m"),
    [(10.0, -10.0), (-10.0, 10.0)],
)
def test_local_path_right_sign_matches_screen_direction(
    last_y_m: float, expected_right_m: float,
) -> None:
    # At station 10 the car points east. North is its left, so the north
    # branch must appear on the left of the fixed forward-facing marker.
    track = SpatialTrack(
        distance_m=(0.0, 10.0, 20.0, 30.0),
        x_m=(0.0, 10.0, 20.0, 20.0),
        y_m=(0.0, 0.0, 0.0, last_y_m),
        curvature_per_m=(0.0, 0.0, 0.0),
        closed=False,
    )
    playback = DriverPlayback(
        track, lap_channels(**{"vehicle.distance_m": (10.0, 30.0)})
    )
    samples = playback.local_path_m(
        playback.frame_at(1.0), behind_m=0.0, ahead_m=20.0, spacing_m=10.0
    )
    assert samples[-1][0] == pytest.approx(expected_right_m)


@pytest.mark.parametrize(
    "changes",
    [
        {"vehicle.time_s": (1.0, 1.0)},
        {"vehicle.time_s": (0.0,), "vehicle.distance_m": (0.0,),
         "vehicle.speed_mps": (0.0,),
         "vehicle.lateral_acceleration_mps2": (0.0,)},
        {"vehicle.distance_m": (10.0, 9.0)},
        {"vehicle.distance_m": (10.0, 21.0)},
        {"vehicle.speed_mps": (-1.0, 2.0)},
        {"vehicle.speed_mps": (float("nan"), 2.0)},
    ],
)
def test_driver_playback_rejects_bad_alignment(changes: dict[str, tuple[float, ...]]) -> None:
    with pytest.raises(ValueError):
        DriverPlayback(straight_map(), lap_channels(**changes))


def test_missing_playback_channel_is_reported() -> None:
    with pytest.raises(ValueError, match="synchronized"):
        DriverPlayback(
            straight_map(),
            SimpleNamespace(__getitem__=lambda _name: None),
        )


def test_desktop_tabs_and_playback_smoke() -> None:
    import time
    import tkinter as tk

    from lapsim.ui.app import LapSimDesktop

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display unavailable")
    root.withdraw()
    try:
        app = LapSimDesktop(root)
        assert tuple(app.tab_panels) == (
            "Analysis", "Driver view", "Timed sessions · WIP"
        )
        assert app._active_tab == "Analysis"
        assert app.driver_play_button is not None
        assert app.driver_play_button["state"] == "disabled"

        result = SimpleNamespace(telemetry=lap_channels(
            **{"vehicle.distance_m": (app.track.length_m / 2, app.track.length_m)}
        ))
        app._set_driver_run("smoke car", result)
        app._switch_tab("Driver view")
        root.update()
        assert app.driver_play_button["state"] == "normal"
        assert app.driver_run_label.get() == "Centerline · smoke car"
        assert app.driver_values["distance"].get().startswith("0.0 /")
        app._on_driver_scrub("500")
        assert app.driver_values["time"].get().startswith("1.00 /")
        app._toggle_driver_playback()
        time.sleep(0.11)
        root.update()
        assert app._driver_playing
        assert app._driver_playback_time_s > 1.0
        app._switch_tab("Timed sessions · WIP")
        assert not app._driver_playing
    finally:
        root.destroy()
