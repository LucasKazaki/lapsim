"""Checks for the low-cost, station-aligned desktop driver playback."""

from __future__ import annotations

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
