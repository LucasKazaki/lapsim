"""The desktop cell-size entry controls the grid used by a lap calculation."""

from __future__ import annotations

from types import SimpleNamespace
import tkinter as tk
from unittest.mock import patch

import pytest

from lapsim.ui.app import LapSimDesktop


def test_cell_size_entry_changes_the_centerline_model_grid() -> None:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    try:
        app = LapSimDesktop(root)
        seen: list[tuple[float, object]] = []
        result = SimpleNamespace(completed=False)

        def model(_vehicle: object, track: object, **_kwargs: object) -> object:
            return result

        def save(**kwargs: object) -> str:
            seen.append((kwargs["step_m"], kwargs["solver_track"]))
            return f"run-{len(seen)}"

        with patch("lapsim.ui.app.run_one_lap", side_effect=model), patch.object(
            app, "_save_run_record", side_effect=save,
        ):
            for entered_size in ("2", "1"):
                app.inputs["solver_step_m"].set(entered_size)
                setup, step_m, torque_fraction = app._read_run_inputs()
                assert step_m == float(entered_size)
                app._calculate_single(
                    "prius_2026_le", "Prius", setup, step_m, torque_fraction,
                )
                kind, payload, error = app.result_queue.get_nowait()
                assert error is None, error
                assert kind == "single"
                assert payload[1] == step_m

        assert [step for step, _track in seen] == [2.0, 1.0]
        assert seen[1][1].cell_count > seen[0][1].cell_count
        assert max(seen[0][1].cell_length_m) <= 2.0 + 1e-10
        assert max(seen[1][1].cell_length_m) <= 1.0 + 1e-10
    finally:
        root.destroy()
