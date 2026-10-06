"""Start the window without a console and show unexpected startup failures."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import traceback


def _report_startup_failure(details: str) -> None:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    log_path = base / "LapSim" / "logs" / "desktop_startup.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(details, encoding="utf-8")
        message = f"LapSim could not start.\n\nDetails were saved to:\n{log_path}"
    except OSError:
        message = f"LapSim could not start.\n\n{details[-1800:]}"
    ctypes.windll.user32.MessageBoxW(None, message, "LapSim startup error", 0x10)


def main() -> int:
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    try:
        from lapsim.ui._tk_runtime import configure_tk_libraries

        configure_tk_libraries()
        from lapsim.ui.app import main as start_app

        start_app()
    except Exception:
        _report_startup_failure(traceback.format_exc())
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
