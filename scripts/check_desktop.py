"""Check the installed Windows desktop environment before launching LapSim.

Run from a repository checkout with ``.venv/Scripts/python.exe``.  This is a
small startup check, not a physics simulation or a dependency installer.
"""

from __future__ import annotations

import os
import sys
import traceback

# Keep NumPy/OpenBLAS initialization bounded before Matplotlib or LapSim imports.
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"


def check_desktop() -> None:
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 or newer is required")
    if sys.maxsize <= 2**32:
        raise RuntimeError("A 64-bit Python installation is required")

    from lapsim.ui._tk_runtime import configure_tk_libraries

    configure_tk_libraries()
    import tkinter as tk

    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure

    from lapsim.ui.app import LapSimDesktop  # noqa: F401
    from lapsim.ui.simulation import ENDURANCE_TRACK_PATH, load_team_endurance_track

    if not ENDURANCE_TRACK_PATH.is_file():
        raise FileNotFoundError(
            f"the bundled endurance course is missing: {ENDURANCE_TRACK_PATH}"
        )
    track = load_team_endurance_track()
    if track.cell_count < 1 or track.length_m <= 0:
        raise RuntimeError("the bundled endurance course is empty")

    root = tk.Tk()
    try:
        root.withdraw()
        figure = Figure(figsize=(2, 1.5), dpi=100)
        canvas = FigureCanvasTkAgg(figure, master=root)
        canvas.draw()
        root.update_idletasks()
        canvas.get_tk_widget().destroy()
    finally:
        root.destroy()


def main() -> int:
    try:
        check_desktop()
    except Exception:
        print("LapSim desktop check failed. Run setup_lapsim.cmd again.", file=sys.stderr)
        traceback.print_exc()
        return 1
    print("LapSim desktop check passed: Python, TkAgg canvas, app imports, and default course are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
