"""Progress events identify real solver work without estimating convergence."""

from __future__ import annotations

from math import pi

from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Track
from lapsim.ui.simulation import (
    SpeedPeriodicPhaseSnapshot,
    run_speed_periodic_lap,
)
from vehicle_model import Vehicle


def test_speed_periodic_probe_and_final_pass_emit_ordered_phase_events() -> None:
    track = SpatialTrack.from_track(
        Track.from_segments([Curve(25.0, 2.0 * pi)]),
        maximum_cell_length_m=5.0,
    )
    events: list[SpeedPeriodicPhaseSnapshot | str] = []
    run_speed_periodic_lap(
        Vehicle(), track, torque_request_fraction=0.5,
        phase_progress_callback=events.append,
        progress_callback=lambda _snapshot: events.append("accepted_cell"),
    )

    assert events[0] == SpeedPeriodicPhaseSnapshot("speed_seam_probe", 1, 2)
    assert events[1] == SpeedPeriodicPhaseSnapshot("final_lap", 2, 2)
    assert "accepted_cell" in events[2:]
