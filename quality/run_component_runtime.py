"""Execute the real component desktop and retain its own-window screenshot."""

import json
import os
from copy import deepcopy
from pathlib import Path

from lapsim.ui._tk_runtime import configure_tk_libraries


def main():
    configure_tk_libraries()
    import tkinter as tk

    from PIL import ImageGrab

    from lapsim.experiments.component_study import replay_component_comparison
    from lapsim.experiments.dynamics_record import _canonical_json, _content_id
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
        from lapsim.ui import component_lab

        callback_errors = []
        root.report_callback_exception = lambda *error: callback_errors.append(error)
        original_save_picker = component_lab.filedialog.asksaveasfilename
        original_id = lab.record["run_id"]
        try:
            component_lab.filedialog.asksaveasfilename = lambda **kwargs: str(
                output / "missing-parent" / "comparison.json"
            )
            lab.save_button.invoke()
            root.update()
            assert lab.status.get().startswith("Could not save:")
            assert lab.record["run_id"] == original_id
            assert not callback_errors
            component_lab.filedialog.asksaveasfilename = lambda **kwargs: str(
                output / "save-retry.json"
            )
            lab.save_button.invoke()
            assert lab.status.get() == "Saved comparison: save-retry.json"
            assert (
                json.loads((output / "save-retry.json").read_text(encoding="utf-8"))[
                    "run_id"
                ]
                == original_id
            )
        finally:
            component_lab.filedialog.asksaveasfilename = original_save_picker
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
        malformed = deepcopy(lab.record)
        malformed["runs"]["A"]["result"]["nominal"]["mass_kg"] = 10**400
        for item in (malformed["runs"]["A"], malformed):
            item["run_id"] = _content_id(
                {key: value for key, value in item.items() if key != "run_id"}
            )
        malformed_path = output / "oversized-result.json"
        malformed_path.write_text(_canonical_json(malformed) + "\n", encoding="utf-8")
        from lapsim.ui import component_lab

        original_picker = component_lab.filedialog.askopenfilename
        try:
            component_lab.filedialog.askopenfilename = lambda **kwargs: str(
                malformed_path
            )
            lab.load()
        finally:
            component_lab.filedialog.askopenfilename = original_picker
        assert lab.record is None and "Could not replay:" in lab.status.get()
        assert lab.save_button.instate(["disabled"])
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
            "failed_save_reported_in_window_without_callback_traceback": True,
            "failed_save_keeps_record_and_retry_succeeds": True,
            "import_readonly": True,
            "oversized_integer_import_rejected_cleanly": True,
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
