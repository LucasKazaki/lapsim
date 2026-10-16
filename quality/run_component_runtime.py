"""Execute the real component desktop and retain its own-window screenshot."""

import json
import os
from pathlib import Path

from lapsim.ui._tk_runtime import configure_tk_libraries


def main():
    configure_tk_libraries()
    import tkinter as tk

    from PIL import ImageGrab

    from lapsim.experiments.component_study import replay_component_comparison
    from lapsim.ui.dynamics_lab import DynamicsLab

    output = Path("audit/component-study")
    output.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    root.withdraw()
    try:
        shell = DynamicsLab(root, dark=False)
        shell.window.withdraw()
        shell.component_study_button.invoke()
        lab = shell.latest_component_study
        lab.window.geometry("1120x780+20+20")
        lab.run_button.invoke()
        root.update()
        assert lab.record is not None
        assert replay_component_comparison(lab.record)["runs_replayed"] == 2
        lab.save_to(output / "comparison.json")
        root.update_idletasks()
        x, y = lab.window.winfo_rootx(), lab.window.winfo_rooty()
        screenshot = (
            ImageGrab.grab(window=lab.window.winfo_id())
            if os.name == "nt"
            else ImageGrab.grab(
                bbox=(x, y, x + lab.window.winfo_width(), y + lab.window.winfo_height())
            )
        )
        screenshot.save(output / "desktop.png")
        assert (
            lab.save_button.winfo_rooty() + lab.save_button.winfo_height()
            < y + lab.window.winfo_height()
        )
        lab.load_from(output / "comparison.json")
        assert lab.imported and lab.run_button.instate(["disabled"])
        lab.new()
        lab.inputs["outside_b"].set(".03")
        lab.inputs["force"].set("80")
        lab.inputs["torque"].set("-15")
        lab.dimensions.set(False)
        assert lab.record is None and lab.save_button.instate(["disabled"])
        lab.run_button.invoke()
        assert lab.record["geometry_policy"] == "manual_geometry_change"
        lab.save_to(output / "geometry-change.json")
        lab.inputs["force"].set("10")
        lab.load_from(output / "geometry-change.json")
        root.update_idletasks()
        assert not lab.edit_controls.winfo_ismapped()
        assert lab.saved_configuration_label.winfo_ismapped()
        assert "Fy 80 N" in lab.saved_configuration.get()
        assert "Mx -15 N·m" in lab.saved_configuration.get()
        assert "OD 0.03 [0.03, 0.03]" in lab.saved_configuration.get()
        lab.new()
        assert lab.edit_controls.winfo_manager() == "pack"
        lab.inputs["outside"].set(".01")
        lab.run_button.invoke()
        assert lab.record is None and lab.save_button.instate(["disabled"])
        summary = {
            "status": "passed",
            "actual_tk_calculate": True,
            "two_materials": True,
            "saved_record_replayed": True,
            "import_readonly": True,
            "nondefault_import_shows_stored_geometry_bounds_and_loads": True,
            "geometry_change_recalculates": True,
            "invalid_input_clears_result": True,
            "backend": "analytic_python",
            "browser_ui": "not implemented for this standalone component slice",
        }
        (output / "summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(summary))
        lab.close()
        shell.close()
    finally:
        root.destroy()


if __name__ == "__main__":
    main()
