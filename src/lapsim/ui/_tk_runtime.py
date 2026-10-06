"""Point Tk at the Tcl scripts belonging to this Python installation."""

from __future__ import annotations

import _tkinter
import os
from pathlib import Path
import sys


def configure_tk_libraries() -> None:
    """Use base-interpreter Tcl/Tk scripts when a Windows venv has them."""

    base_tcl = Path(sys.base_prefix) / "tcl"
    libraries = (
        ("TCL_LIBRARY", f"tcl{_tkinter.TCL_VERSION}", "init.tcl"),
        ("TK_LIBRARY", f"tk{_tkinter.TK_VERSION}", "tk.tcl"),
    )
    for variable, folder_name, required_file in libraries:
        candidate = base_tcl / folder_name
        if (candidate / required_file).is_file():
            os.environ[variable] = str(candidate)
        else:
            existing = os.environ.get(variable)
            if existing and not (Path(existing) / required_file).is_file():
                os.environ.pop(variable, None)
